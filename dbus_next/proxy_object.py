from .introspection import Interface, Method, Signal, Property
from .validators import assert_object_path_valid, assert_bus_name_valid
from . import message_bus
from .message import Message
from .constants import MessageType, ErrorType, MessageFlag
from . import introspection as intr
from .errors import DBusError, InterfaceNotFoundError
from ._private.util import replace_idx_with_fds

from typing import Type, Union, List, Coroutine, Callable
import logging
import xml.etree.ElementTree as ET
import inspect
import re
import asyncio


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
    def __init__(self, bus_name: str, path: str, introspection: Interface,
                 bus: 'message_bus.BaseMessageBus'):

        self.bus_name: str = bus_name
        self.path: str = path
        self.introspection: Interface = introspection
        self.bus: 'message_bus.BaseMessageBus' = bus
        self._signal_handlers: dict[str, List[Callable]] = {}
        self._signal_match_rule = f"type='signal',sender={bus_name},interface={introspection.name},path={path}"

    def __getattr__(self, name):
        sync = False
        if name.startswith('on_'):
            signal_name = self._to_camel_case(name.split('on_', 1)[1])
            signal = self.introspection.get_signal(signal_name)

            def signal_on_wrapper(*args):
                fn: Callable = args[0]
                return self._call_on_signal(signal, fn)

            return signal_on_wrapper
        elif name.startswith('off_'):
            signal_name = self._to_camel_case(name.split('off_', 1)[1])
            signal = self.introspection.get_signal(signal_name)

            def signal_off_wrapper(*args):
                fn: Callable = args[0]
                return self._call_off_signal(signal, fn)

            return signal_off_wrapper
        elif name.startswith('call_'):
            method_str = name.split('call_', 1)[1]
            if method_str.endswith('_sync'):
                sync = True
                method_str = method_str.rsplit('_sync', 1)[0]
            method_name = self._to_camel_case(method_str)
            method = self.introspection.get_method(method_name)

            def method_wrapper(*args, **kwargs):
                margs = args
                flags = kwargs.get('flags', MessageFlag.NONE)
                return self._call_method(method, margs, mflags=flags, sync=sync)

            return method_wrapper
        elif name.startswith('get_'):
            property_str = name.split('get_', 1)[1]
            if property_str.endswith('_sync'):
                sync = True
                property_str = property_str.rsplit('_sync', 1)[0]
            property_name = self._to_camel_case(property_str)
            property = self.introspection.get_property(property_name)

            def property_get_wrapper():
                return self._get_property(property, sync=sync)

            return property_get_wrapper
        elif name.startswith('set_'):
            property_str = name.split('set_', 1)[1]
            if property_str.endswith('_sync'):
                sync = True
                property_str = property_str.rsplit('_sync', 1)[0]
            property_name = self._to_camel_case(property_str)
            property = self.introspection.get_property(property_name)

            def property_set_wrapper(*args):
                val = args[0]
                return self._set_property(property, val, sync=sync)

            return property_set_wrapper
        raise AttributeError(name)

    _underscorer1 = re.compile(r'(.)([A-Z][a-z]+)')
    _underscorer2 = re.compile(r'([a-z0-9])([A-Z])')

    @staticmethod
    def _to_camel_case(member):
        return ''.join(word.title() for word in member.split('_'))

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

    def _call_method(self, intr_method: Method, args, mflags=MessageFlag.NONE, sync=False):
        raise NotImplementedError('this must be implemented in the inheriting class')

    def _get_property(self, intr_property: Property, sync=False):
        raise NotImplementedError('this must be implemented in the inheriting class')

    def _set_property(self, intr_property: Property, val, sync=False):
        raise NotImplementedError('this must be implemented in the inheriting class')

    def _message_handler(self, msg):
        if not msg._matches(message_type=MessageType.SIGNAL,
                            interface=self.introspection.name,
                            path=self.path) or msg.member not in self._signal_handlers:
            return

        if msg.sender != self.bus_name and self.bus._name_owners.get(self.bus_name,
                                                                     '') != msg.sender:
            # The sender is always a unique name, but the bus name given might
            # be a well known name. If the sender isn't an exact match, check
            # to see if it owns the bus_name we were given from the cache kept
            # on the bus for this purpose.
            return

        match = [s for s in self.introspection.signals if s.name == msg.member]
        if not len(match):
            return
        intr_signal = match[0]
        if intr_signal.signature != msg.signature:
            logging.warning(
                f'got signal "{self.introspection.name}.{msg.member}" with unexpected signature "{msg.signature}"'
            )
            return

        body = replace_idx_with_fds(msg.signature, msg.body, msg.unix_fds)
        for handler in self._signal_handlers[msg.member]:
            cb_result = handler(*body)
            if isinstance(cb_result, Coroutine):
                asyncio.create_task(cb_result)

    def _call_on_signal(self, intr_signal: Signal, fn):
        def on_signal_fn(fn: Callable):
            fn_signature = inspect.signature(fn)
            if not callable(fn) or len(fn_signature.parameters) != len(intr_signal.args):
                raise TypeError(
                    f'reply_notify must be a function with {len(intr_signal.args)} parameters')

            if not self._signal_handlers:
                self.bus._add_match_rule(self._signal_match_rule)
                self.bus.add_message_handler(self._message_handler)

            if intr_signal.name not in self._signal_handlers:
                self._signal_handlers[intr_signal.name] = []

            self._signal_handlers[intr_signal.name].append(fn)

        return on_signal_fn(fn)

    def _call_off_signal(self, intr_signal: Signal, fn):
        def off_signal_fn(fn: Callable):
            try:
                i = self._signal_handlers[intr_signal.name].index(fn)
                del self._signal_handlers[intr_signal.name][i]
                if not self._signal_handlers[intr_signal.name]:
                    del self._signal_handlers[intr_signal.name]
            except (KeyError, ValueError):
                return

            if not self._signal_handlers:
                self.bus._remove_match_rule(self._signal_match_rule)
                self.bus.remove_message_handler(self._message_handler)

        return off_signal_fn(fn)


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

        intr_interface = self.introspection.get_interface(name)
        if intr_interface is None:
            raise InterfaceNotFoundError(f'interface not found on this object: {name}')

        interface = self.ProxyInterface(self.bus_name, self.path, intr_interface, self.bus)

        def get_owner_notify(msg, err):
            if err:
                logging.error(f'getting name owner for "{name}" failed, {err}')
                return
            if msg.message_type == MessageType.ERROR:
                if msg.error_name != ErrorType.NAME_HAS_NO_OWNER.value:
                    logging.error(f'getting name owner for "{name}" failed, {msg.body[0]}')
                return

            self.bus._name_owners[self.bus_name] = msg.body[0]

        if self.bus_name[0] != ':' and not self.bus._name_owners.get(self.bus_name, ''):
            self.bus._call(
                Message(destination='org.freedesktop.DBus',
                        interface='org.freedesktop.DBus',
                        path='/org/freedesktop/DBus',
                        member='GetNameOwner',
                        signature='s',
                        body=[self.bus_name]), get_owner_notify)

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
