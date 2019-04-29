from .validators import assert_object_path_valid, assert_bus_name_valid
from .message_bus import BaseMessageBus
from .message import Message
from .constants import MessageType, ErrorType
from . import introspection as intr
from .errors import DBusError, InterfaceNotFoundError

import logging
import xml.etree.ElementTree as ET
import inspect
import re


class BaseProxyInterface:
    def __init__(self, bus_name, path, introspection, bus):
        self.bus_name = bus_name
        self.path = path
        self.introspection = introspection
        self.bus = bus

    _underscorer1 = re.compile(r'(.)([A-Z][a-z]+)')
    _underscorer2 = re.compile(r'([a-z0-9])([A-Z])')

    @staticmethod
    def _to_snake_case(member):
        subbed = BaseProxyInterface._underscorer1.sub(r'\1_\2', member)
        return BaseProxyInterface._underscorer2.sub(r'\1_\2', subbed).lower()

    @staticmethod
    def _check_method_return(msg, signature=None):
        if msg.message_type == MessageType.ERROR:
            raise DBusError._from_message(msg)
        elif msg.message_type != MessageType.METHOD_RETURN:
            raise DBusError(ErrorType.CLIENT_ERROR, 'method call didnt return a method return', msg)
        elif signature is not None and msg.signature != signature:
            raise DBusError(ErrorType.CLIENT_ERROR,
                            f'method call returned unexpected signature: "{msg.signature}"', msg)

    def _add_method(self, intr_method):
        raise NotImplementedError('this must be implemented in the inheriting class')

    def _add_property(self, intr_property):
        raise NotImplementedError('this must be implemented in the inheriting class')


class BaseProxyObject:
    def __init__(self, bus_name, path, node, bus, ProxyInterface):
        assert_object_path_valid(path)
        assert_bus_name_valid(bus_name)

        if not isinstance(bus, BaseMessageBus):
            raise TypeError('bus must be an instance of BaseMessageBus')
        if not issubclass(ProxyInterface, BaseProxyInterface):
            raise TypeError('ProxyInterface must be an instance of BaseProxyInterface')

        if type(node) is intr.Node:
            self.node = node
        elif type(node) is str:
            self.node = intr.Node.parse(node)
        elif type(node) is ET.Element:
            self.node = intr.Node.from_xml(node)
        else:
            raise TypeError('node must be xml node introspection or introspection.Node class')

        self.bus_name = bus_name
        self.path = path
        self.bus = bus
        self.ProxyInterface = ProxyInterface

        self.interfaces = []
        self.child_names = [f'{path}/{n.name}' for n in self.node.nodes]
        self.signal_handlers = {}

    def get_interface(self, name):
        try:
            intr_interface = next(i for i in self.node.interfaces if i.name == name)
        except StopIteration:
            raise InterfaceNotFoundError(f'interface not found on this object: {name}')

        interface = self.ProxyInterface(self.bus_name, self.path, intr_interface, self.bus)

        for intr_method in intr_interface.methods:
            interface._add_method(intr_method)
        for intr_property in intr_interface.properties:
            interface._add_property(intr_property)
        for intr_signal in intr_interface.signals:
            self._add_signal(intr_signal, interface)

        def add_match_notify(msg, err):
            if err:
                logging.error(f'add match request failed. match="{match_rule}", {err}')
            if msg.message_type == MessageType.ERROR:
                logging.error(f'add match request failed. match="{match_rule}", {msg.body[0]}')

        def get_owner_notify(msg, err):
            if err:
                logging.error(f'getting name owner for "{name}" failed, {err}')
            if msg.message_type == MessageType.ERROR:
                logging.error(f'getting name owner for "{name}" failed, {msg.body[0]}')

            self.bus._name_owners[self.bus_name] = msg.body[0]

        if self.bus_name[0] != ':':
            self.bus._call(
                Message(destination='org.freedesktop.DBus',
                        interface='org.freedesktop.DBus',
                        path='/org/freedesktop/DBus',
                        member='GetNameOwner',
                        signature='s',
                        body=[self.bus_name]), get_owner_notify)

        match_rule = f"type='signal',sender={self.bus_name},interface={name},path={self.path}"
        self.bus._call(
            Message(destination='org.freedesktop.DBus',
                    interface='org.freedesktop.DBus',
                    path='/org/freedesktop/DBus',
                    member='AddMatch',
                    signature='s',
                    body=[match_rule]), add_match_notify)

        def message_handler(msg):
            if msg._matches(message_type=MessageType.SIGNAL,
                            interface=intr_interface.name,
                            path=self.path) and msg.member in self.signal_handlers:
                if msg.sender != self.bus_name and self.bus._name_owners.get(self.bus_name,
                                                                             '') != msg.sender:
                    return
                match = [s for s in intr_interface.signals if s.name == msg.member]
                if not len(match):
                    return
                intr_signal = match[0]
                if intr_signal.signature != msg.signature:
                    logging.warning(
                        f'got signal "{intr_interface.name}.{msg.member}" with unexpected signature "{msg.signature}"'
                    )
                    return

                for handler in self.signal_handlers[msg.member]:
                    handler(*msg.body)

        self.bus.add_message_handler(message_handler)

        return interface

    def get_children(self):
        return [
            self.__class__(self.bus_name, self.path, child, self.bus) for child in self.node.nodes
        ]

    def _add_signal(self, intr_signal, interface):
        def on_signal_fn(fn):
            fn_signature = inspect.signature(fn)
            if not callable(fn) or len(fn_signature.parameters) != len(intr_signal.args):
                raise TypeError(
                    f'reply_notify must be a function with {len(intr_signal.args)} parameters')

            if intr_signal.name not in self.signal_handlers:
                self.signal_handlers[intr_signal.name] = []

            self.signal_handlers[intr_signal.name].append(fn)

        def off_signal_fn(fn):
            try:
                i = self.signal_handlers[intr_signal.name].index(fn)
                del self.signal_handlers[intr_signal.name][i]
            except (KeyError, ValueError):
                pass

        snake_case = BaseProxyInterface._to_snake_case(intr_signal.name)
        setattr(interface, f'on_{snake_case}', on_signal_fn)
        setattr(interface, f'off_{snake_case}', off_signal_fn)
