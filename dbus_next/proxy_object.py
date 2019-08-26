from .validators import assert_object_path_valid, assert_bus_name_valid
from . import message_bus
from .message import Message
from .constants import MessageType, ErrorType
from . import introspection as intr
from .errors import DBusError, InterfaceNotFoundError

from typing import Type, Union, List
import logging
import xml.etree.ElementTree as ET
import inspect
import re


class BaseProxyInterface:
    """An abstract class representing a proxy to an interface exported on the bus by another client.

    Implementations of this class are not meant to be constructed directly by
    users. Use :func:`BaseProxyObject.get_interface` to get a proxy interface.
    Each message bus implementation provides its own proxy interface
    implementation that will be returned by that method.

    Proxy interfaces can be used to call methods, get properties, and listen to
    signals on the interface. Proxy interfaces are created dynamically with a
    family of methods for each of these operations based on what members the
    interface exposes. Each proxy interface implementation exposes these
    members in a different way depending on the features of the backend. See
    the documentation of the proxy interface implementation you use for more
    details.

    :ivar bus_name: The name of the bus this interface is exported on.
    :vartype bus_name: str
    :ivar path: The object path exported on the client that owns the bus name.
    :vartype path: str
    :ivar introspection: Parsed introspection data for the proxy interface.
    :vartype introspection: :class:`Node <dbus_next.introspection.Interface>`
    :ivar bus: The message bus this proxy interface is connected to.
    :vartype bus: :class:`BaseMessageBus <dbus_next.message_bus.BaseMessageBus>`
    """

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
    """An abstract class representing a proxy to an object exported on the bus by another client.

    Implementations of this class are not meant to be constructed directly. Use
    :func:`BaseMessageBus.get_proxy_object()
    <dbus_next.message_bus.BaseMessageBus.get_proxy_object>` to get a proxy
    object. Each message bus implementation provides its own proxy object
    implementation that will be returned by that method.

    The primary use of the proxy object is to select a proxy interface to act
    on. Information on what interfaces are available is provided by
    introspection data provided to this class. This introspection data can
    either be included in your project as an XML file (recommended) or
    retrieved from the ``org.freedesktop.DBus.Introspectable`` interface at
    runtime.

    :ivar bus_name: The name of the bus this object is exported on.
    :vartype bus_name: str
    :ivar path: The object path exported on the client that owns the bus name.
    :vartype path: str
    :ivar introspection: Parsed introspection data for the proxy object.
    :vartype introspection: :class:`Node <dbus_next.introspection.Node>`
    :ivar bus: The message bus this proxy object is connected to.
    :vartype bus: :class:`BaseMessageBus <dbus_next.message_bus.BaseMessageBus>`
    :ivar ~.ProxyInterface: The proxy interface class this proxy object uses.
    :vartype ~.ProxyInterface: Type[:class:`BaseProxyInterface <dbus_next.proxy_object.BaseProxyObject>`]
    :ivar child_paths: A list of absolute object paths of the children of this object.
    :vartype child_paths: list(str)

    :raises:
        - :class:`InvalidBusNameError <dbus_next.InvalidBusNameError>` - If the given bus name is not valid.
        - :class:`InvalidObjectPathError <dbus_next.InvalidObjectPathError>` - If the given object path is not valid.
        - :class:`InvalidIntrospectionError <dbus_next.InvalidIntrospectionError>` - If the introspection data for the node is not valid.
    """

    def __init__(self, bus_name: str, path: str, introspection: Union[intr.Node, str, ET.Element],
                 bus: 'message_bus.BaseMessageBus', ProxyInterface: Type[BaseProxyInterface]):
        assert_object_path_valid(path)
        assert_bus_name_valid(bus_name)

        if not isinstance(bus, message_bus.BaseMessageBus):
            raise TypeError('bus must be an instance of BaseMessageBus')
        if not issubclass(ProxyInterface, BaseProxyInterface):
            raise TypeError('ProxyInterface must be an instance of BaseProxyInterface')

        if type(introspection) is intr.Node:
            self.introspection = introspection
        elif type(introspection) is str:
            self.introspection = intr.Node.parse(introspection)
        elif type(introspection) is ET.Element:
            self.introspection = intr.Node.from_xml(introspection)
        else:
            raise TypeError(
                'introspection must be xml node introspection or introspection.Node class')

        self.bus_name = bus_name
        self.path = path
        self.bus = bus
        self.ProxyInterface = ProxyInterface
        self.child_paths = [f'{path}/{n.name}' for n in self.introspection.nodes]

        self._interfaces = {}
        self._signal_handlers = {}

        # lazy loaded by get_children()
        self._children = None

    def get_interface(self, name: str) -> BaseProxyInterface:
        """Get an interface exported on this proxy object and connect it to the bus.

        :param name: The name of the interface to retrieve.
        :type name: str

        :raises:
            - :class:`InterfaceNotFoundError <dbus_next.InterfaceNotFoundError>` - If there is no interface by this name exported on the bus.
        """
        if name in self._interfaces:
            return self._interfaces[name]

        try:
            intr_interface = next(i for i in self.introspection.interfaces if i.name == name)
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
                            path=self.path) and msg.member in self._signal_handlers:
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

                for handler in self._signal_handlers[msg.member]:
                    handler(*msg.body)

        self.bus.add_message_handler(message_handler)

        self._interfaces[name] = interface
        return interface

    def get_children(self) -> List['BaseProxyObject']:
        """Get the child nodes of this proxy object according to the introspection data."""
        if self._children is None:
            self._children = [
                self.__class__(self.bus_name, self.path, child, self.bus)
                for child in self.introspection.nodes
            ]

        return self._children

    def _add_signal(self, intr_signal, interface):
        def on_signal_fn(fn):
            fn_signature = inspect.signature(fn)
            if not callable(fn) or len(fn_signature.parameters) != len(intr_signal.args):
                raise TypeError(
                    f'reply_notify must be a function with {len(intr_signal.args)} parameters')

            if intr_signal.name not in self._signal_handlers:
                self._signal_handlers[intr_signal.name] = []

            self._signal_handlers[intr_signal.name].append(fn)

        def off_signal_fn(fn):
            try:
                i = self._signal_handlers[intr_signal.name].index(fn)
                del self._signal_handlers[intr_signal.name][i]
            except (KeyError, ValueError):
                pass

        snake_case = BaseProxyInterface._to_snake_case(intr_signal.name)
        setattr(interface, f'on_{snake_case}', on_signal_fn)
        setattr(interface, f'off_{snake_case}', off_signal_fn)
