from ._private.address import get_bus_address, parse_address
from .message import Message
from .constants import BusType, MessageFlag, MessageType, ErrorType, NameFlag, RequestNameReply, ReleaseNameReply
from .service import ServiceInterface
from .validators import assert_object_path_valid, assert_bus_name_valid
from .errors import DBusError, InvalidAddressError
from .signature import Variant
from .proxy_object import BaseProxyObject
from . import introspection as intr
from contextlib import suppress

import inspect
import traceback
import socket
import logging
import xml.etree.ElementTree as ET

from typing import Type, Callable, Optional, Union


class BaseMessageBus:
    """An abstract class to manage a connection to a DBus message bus.

    The message bus class is the entry point into all the features of the
    library. It sets up a connection to the DBus daemon and exposes an
    interface to send and receive messages and expose services.

    This class is not meant to be used directly by users. For more information,
    see the documentation for the implementation of the message bus you plan to
    use.

    :param bus_type: The type of bus to connect to. Affects the search path for
        the bus address.
    :type bus_type: :class:`BusType <dbus_next.BusType>`
    :param bus_address: A specific bus address to connect to. Should not be
        used under normal circumstances.
    :type bus_address: str
    :param ProxyObject: The proxy object implementation for this message bus.
        Must be passed in by an implementation that supports the high-level client.
    :type ProxyObject: Type[:class:`BaseProxyObject
        <dbus_next.proxy_object.BaseProxyObject>`]

    :ivar unique_name: The unique name of the message bus connection. It will
        be :class:`None` until the message bus connects.
    :vartype unique_name: str
    """

    def __init__(self,
                 bus_address: Optional[str] = None,
                 bus_type: BusType = BusType.SESSION,
                 ProxyObject: Optional[Type[BaseProxyObject]] = None):
        self.unique_name = None
        self._disconnected = False

        self._method_return_handlers = {}
        # buffer messages until connect
        self._buffered_messages = []
        self._serial = 0
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_NONBLOCK)
        self._stream = self._sock.makefile('rwb')
        self._fd = self._sock.fileno()
        self._user_message_handlers = []
        self._name_owners = {}
        self._path_exports = {}
        self._bus_address = parse_address(bus_address) if bus_address else parse_address(
            get_bus_address(bus_type))
        self._ProxyObject = ProxyObject

        # machine id is lazy loaded
        self._machine_id = None

        self._setup_socket()

    def export(self, path: str, interface: ServiceInterface):
        """Export the service interface on this message bus to make it available
        to other clients.

        :param path: The object path to export this interface on.
        :type path: str
        :param interface: The service interface to export.
        :type interface: :class:`ServiceInterface
            <dbus_next.service.ServiceInterface>`

        :raises:
            - :class:`InvalidObjectPathError <dbus_next.InvalidObjectPathError>` - If the given object path is not valid.
            - :class:`ValueError` - If an interface with this name is already exported on the message bus at this path
        """
        assert_object_path_valid(path)
        if not isinstance(interface, ServiceInterface):
            raise TypeError('interface must be a ServiceInterface')

        if path not in self._path_exports:
            self._path_exports[path] = []

        for f in self._path_exports[path]:
            if f.name == interface.name:
                raise ValueError(
                    f'An interface with this name is already exported on this bus at path "{path}": "{interface.name}"'
                )

        self._path_exports[path].append(interface)
        ServiceInterface._add_bus(interface, self)
        self._emit_interface_added(path, interface)

    def unexport(self, path: str, interface: Optional[Union[ServiceInterface, str]] = None):
        """Unexport the path or service interface to make it no longer
        available to clients.

        :param path: The object path to unexport.
        :type path: str
        :param interface: The interface instance or the name of the interface
            to unexport. If ``None``, unexport every interface on the path.
        :type interface: :class:`ServiceInterface
            <dbus_next.service.ServiceInterface>` or str or None

        :raises:
            - :class:`InvalidObjectPathError <dbus_next.InvalidObjectPathError>` - If the given object path is not valid.
        """
        assert_object_path_valid(path)
        if type(interface) not in [str, type(None)] and not isinstance(interface, ServiceInterface):
            raise TypeError('interface must be a ServiceInterface or interface name')

        if path not in self._path_exports:
            return

        exports = self._path_exports[path]

        if type(interface) is str:
            try:
                interface = next(iface for iface in exports if iface.name == interface)
            except StopIteration:
                return

        removed_interfaces = []
        if interface is None:
            del self._path_exports[path]
            for iface in filter(lambda e: not self._has_interface(e), exports):
                removed_interfaces.append(iface.name)
                ServiceInterface._remove_bus(iface, self)
        else:
            for i, iface in enumerate(exports):
                if iface is interface:
                    removed_interfaces.append(iface.name)
                    del self._path_exports[path][i]
                    if not self._path_exports[path]:
                        del self._path_exports[path]
                    if not self._has_interface(iface):
                        ServiceInterface._remove_bus(iface, self)
                    break
        self._emit_interface_removed(path, removed_interfaces)

    def introspect(self, bus_name: str, path: str,
                   callback: Callable[[Optional[intr.Node], Optional[Exception]], None]):
        """Get introspection data for the node at the given path from the given
        bus name.

        Calls the standard ``org.freedesktop.DBus.Introspectable.Introspect``
        on the bus for the path.

        :param bus_name: The name to introspect.
        :type bus_name: str
        :param path: The path to introspect.
        :type path: str
        :param callback: A callback that will be called with the introspection
            data as a :class:`Node <dbus_next.introspection.Node>`.
        :type callback: :class:`Callable`

        :raises:
            - :class:`InvalidObjectPathError <dbus_next.InvalidObjectPathError>` - If the given object path is not valid.
            - :class:`InvalidBusNameError <dbus_next.InvalidBusNameError>` - If the given bus name is not valid.
        """
        BaseMessageBus._check_callback_type(callback)

        def reply_notify(reply, err):
            try:
                BaseMessageBus._check_method_return(reply, err, 's')
                result = intr.Node.parse(reply.body[0])
            except Exception as e:
                callback(None, e)
                return

            callback(result, None)

        self._call(
            Message(destination=bus_name,
                    path=path,
                    interface='org.freedesktop.DBus.Introspectable',
                    member='Introspect'), reply_notify)

    def _emit_interface_added(self, path, interface):
        """Emit the ``org.freedesktop.DBus.ObjectManager.InterfacesAdded`` signal.

        This signal is intended to be used to alert clients when
        a new interface has been added.

        :param path: Path of exported object.
        :type path: str
        :param interface: Exported service interface.
        :type interface: :class:`ServiceInterface
            <dbus_next.service.ServiceInterface>`
        """
        body = {interface.name: {}}
        properties = interface._get_properties(interface)

        for prop in properties:
            with suppress(Exception):
                body[interface.name][prop.name] = Variant(prop.signature, prop.prop_getter(interface))

        self.send(
            Message.new_signal(path=path,
                               interface='org.freedesktop.DBus.ObjectManager',
                               member='InterfacesAdded',
                               signature='oa{sa{sv}}',
                               body=[path, body]))

    def _emit_interface_removed(self, path, removed_interfaces):
        """Emit the ``org.freedesktop.DBus.ObjectManager.InterfacesRemoved` signal.

        This signal is intended to be used to alert clients when
        a interface has been removed.

        :param path: Path of removed (unexported) object.
        :type path: str
        :param removed_interfaces: List of unexported service interfaces.
        :type removed_interfaces: list[str]
        """
        self.send(
            Message.new_signal(path=path,
                               interface='org.freedesktop.DBus.ObjectManager',
                               member='InterfacesRemoved',
                               signature='oas',
                               body=[path, removed_interfaces]))

    def request_name(self,
                     name: str,
                     flags: NameFlag = NameFlag.NONE,
                     callback: Optional[
                         Callable[[Optional[RequestNameReply], Optional[Exception]], None]] = None):
        """Request that this message bus owns the given name.

        :param name: The name to request.
        :type name: str
        :param flags: Name flags that affect the behavior of the name request.
        :type flags: :class:`NameFlag <dbus_next.NameFlag>`
        :param callback: A callback that will be called with the reply of the
            request as a :class:`RequestNameReply <dbus_next.RequestNameReply>`.
        :type callback: :class:`Callable`

        :raises:
            - :class:`InvalidBusNameError <dbus_next.InvalidBusNameError>` - If the given bus name is not valid.
        """
        assert_bus_name_valid(name)

        if callback is not None:
            BaseMessageBus._check_callback_type(callback)

        def reply_notify(reply, err):
            try:
                BaseMessageBus._check_method_return(reply, err, 'u')
                result = RequestNameReply(reply.body[0])
            except Exception as e:
                callback(None, e)
                return

            callback(result, None)

        if type(flags) is not NameFlag:
            flags = NameFlag(flags)

        self._call(
            Message(destination='org.freedesktop.DBus',
                    path='/org/freedesktop/DBus',
                    interface='org.freedesktop.DBus',
                    member='RequestName',
                    signature='su',
                    body=[name, flags]), reply_notify if callback else None)

    def release_name(self,
                     name: str,
                     callback: Optional[
                         Callable[[Optional[ReleaseNameReply], Optional[Exception]], None]] = None):
        """Request that this message bus release the given name.

        :param name: The name to release.
        :type name: str
        :param callback: A callback that will be called with the reply of the
            release request as a :class:`ReleaseNameReply
            <dbus_next.ReleaseNameReply>`.
        :type callback: :class:`Callable`

        :raises:
            - :class:`InvalidBusNameError <dbus_next.InvalidBusNameError>` - If the given bus name is not valid.
        """
        assert_bus_name_valid(name)

        if callback is not None:
            BaseMessageBus._check_callback_type(callback)

        def reply_notify(reply, err):
            try:
                BaseMessageBus._check_method_return(reply, err, 'u')
                result = ReleaseNameReply(reply.body[0])
            except Exception as e:
                callback(None, e)
                return

            callback(result, None)

        self._call(
            Message(destination='org.freedesktop.DBus',
                    path='/org/freedesktop/DBus',
                    interface='org.freedesktop.DBus',
                    member='ReleaseName',
                    signature='s',
                    body=[name]), reply_notify if callback else None)

    def get_proxy_object(self, bus_name: str, path: str,
                         introspection: Union[intr.Node, str, ET.Element]) -> BaseProxyObject:
        """Get a proxy object for the path exported on the bus that owns the
        name. The object is expected to export the interfaces and nodes
        specified in the introspection data.

        This is the entry point into the high-level client.

        :param bus_name: The name on the bus to get the proxy object for.
        :type bus_name: str
        :param path: The path on the client for the proxy object.
        :type path: str
        :param introspection: XML introspection data used to build the
            interfaces on the proxy object.
        :type introspection: :class:`Node <dbus_next.introspection.Node>` or str or :class:`ElementTree`

        :returns: A proxy object for the given path on the given name.
        :rtype: :class:`BaseProxyObject <dbus_next.proxy_object.BaseProxyObject>`

        :raises:
            - :class:`InvalidBusNameError <dbus_next.InvalidBusNameError>` - If the given bus name is not valid.
            - :class:`InvalidObjectPathError <dbus_next.InvalidObjectPathError>` - If the given object path is not valid.
            - :class:`InvalidIntrospectionError <dbus_next.InvalidIntrospectionError>` - If the introspection data for the node is not valid.
        """
        if self._ProxyObject is None:
            raise Exception('the message bus implementation did not provide a proxy object class')

        return self._ProxyObject(bus_name, path, introspection, self)

    def disconnect(self):
        """Disconnect the message bus by closing the underlying connection asynchronously.

        All pending  and future calls will error with a connection error.
        """
        self._sock.shutdown(socket.SHUT_RDWR)

    def next_serial(self) -> int:
        """Get the next serial for this bus. This can be used as the ``serial``
        attribute of a :class:`Message <dbus_next.Message>` to manually handle
        the serial of messages.

        :returns: The next serial for the bus.
        :rtype: int
        """
        self._serial += 1
        return self._serial

    def add_message_handler(self, handler: Callable[[Message], Optional[Union[Message, bool]]]):
        """Add a custom message handler for incoming messages.

        The handler should be a callable that takes a :class:`Message
        <dbus_next.Message>`. If the message is a method call, you may return
        another Message as a reply and it will be marked as handled. You may
        also return ``True`` to mark the message as handled without sending a
        reply.

        :param handler: A handler that will be run for every message the bus
            connection received.
        :type handler: :class:`Callable` or None
        """
        error_text = 'a message handler must be callable with a single parameter'
        if not callable(handler):
            raise TypeError(error_text)

        handler_signature = inspect.signature(handler)
        if len(handler_signature.parameters) != 1:
            raise TypeError(error_text)

        self._user_message_handlers.append(handler)

    def remove_message_handler(self, handler: Callable[[Message], Optional[Union[Message, bool]]]):
        """Remove a message handler that was previously added by
        :func:`add_message_handler()
        <dbus_next.message_bus.BaseMessageBus.add_message_handler>`.

        :param handler: A message handler.
        :type handler: :class:`Callable`
        """
        for i, h in enumerate(self._user_message_handlers):
            if h == handler:
                del self._user_message_handlers[i]
                break

    def send(self, msg: Message):
        """Asynchronously send a message on the message bus.

        :param msg: The message to send.
        :type msg: :class:`Message <dbus_next.Message>`
        """
        raise NotImplementedError('the "send" method must be implemented in the inheriting class')

    def _finalize(self, err):
        '''should be called after the socket disconnects with the disconnection
        error to clean up resources and put the bus in a disconnected state'''
        if self._disconnected:
            return

        for handler in self._method_return_handlers.values():
            handler(None, err)

        self._method_return_handlers.clear()

        for path in list(self._path_exports.keys()):
            self.unexport(path)

        self._disconnected = True

    def _has_interface(self, interface: ServiceInterface) -> bool:
        for _, exports in self._path_exports.items():
            for iface in exports:
                if iface is interface:
                    return True

        return False

    def _interface_signal_notify(self, interface, interface_name, member, signature, body):
        path = None
        for p, ifaces in self._path_exports.items():
            for i in ifaces:
                if i is interface:
                    path = p

        if path is None:
            raise Exception('Could not find interface on bus (this is a bug in dbus-next)')

        self.send(
            Message.new_signal(path=path,
                               interface=interface_name,
                               member=member,
                               signature=signature,
                               body=body))

    def _introspect_export_path(self, path):
        assert_object_path_valid(path)

        if path in self._path_exports:
            node = intr.Node.default(path)
            for interface in self._path_exports[path]:
                node.interfaces.append(interface.introspect())
        else:
            node = intr.Node(path)

        children = set()

        for export_path in self._path_exports:
            try:
                child_path = export_path.split(path, maxsplit=1)[1]
            except IndexError:
                continue

            child_path = child_path.lstrip('/')
            child_name = child_path.split('/', maxsplit=1)[0]

            children.add(child_name)

        node.nodes = [intr.Node(name) for name in children if name]

        return node

    def _setup_socket(self):
        err = None

        for transport, options in self._bus_address:
            filename = None

            if transport == 'unix':
                if 'path' in options:
                    filename = options['path']
                elif 'abstract' in options:
                    filename = f'\0{options["abstract"]}'
                else:
                    raise InvalidAddressError('got unix transport with unknown path specifier')
            else:
                raise InvalidAddressError(f'got unknown address transport: {transport}')

            try:
                self._sock.connect(filename)
                break
            except Exception as e:
                err = e

        if err:
            raise err

    def _call(self, msg, callback):
        BaseMessageBus._check_callback_type(callback)

        if not msg.serial:
            msg.serial = self.next_serial()

        def reply_notify(reply, err):
            if reply:
                self._name_owners[msg.destination] = reply.sender
            callback(reply, err)

        self._method_return_handlers[msg.serial] = reply_notify

        self.send(msg)

        if msg.flags & MessageFlag.NO_REPLY_EXPECTED:
            callback(None, None)

    @staticmethod
    def _check_callback_type(callback):
        """Raise a TypeError if the user gives an invalid callback as a parameter"""

        text = 'a callback must be callable with two parameters'

        if not callable(callback):
            raise TypeError(text)

        fn_signature = inspect.signature(callback)
        if len(fn_signature.parameters) != 2:
            raise TypeError(text)

    @staticmethod
    def _check_method_return(msg, err, signature):
        if err:
            raise err
        elif msg.message_type == MessageType.METHOD_RETURN and msg.signature == signature:
            return
        elif msg.message_type == MessageType.ERROR:
            raise DBusError._from_message(msg)
        else:
            raise DBusError(ErrorType.INTERNAL_ERROR, 'invalid message type for method call', msg)

    def _on_message(self, msg):
        try:
            self._process_message(msg)
        except Exception as e:
            logging.error(
                f'got unexpected error processing a message: {e}.\n{traceback.format_exc()}')

    def _send_reply(self, msg):
        bus = self

        class SendReply:
            def __enter__(self):
                return self

            def __call__(self, reply):
                if msg.flags & MessageFlag.NO_REPLY_EXPECTED:
                    return

                bus.send(reply)

            def __exit__(self, type, value, tb):
                if type == DBusError:
                    self(value._as_message(msg))

                if type == Exception:
                    self(
                        Message.new_error(
                            msg, ErrorType.SERVICE_ERROR,
                            f'The service interface raised an error: {value}.\n{traceback.format_tb(tb)}'
                        ))

        return SendReply()

    def _process_message(self, msg):
        handled = False

        for handler in self._user_message_handlers:
            try:
                result = handler(msg)
                if result:
                    if type(result) is Message:
                        self.send(result)
                    handled = True
                    break
            except DBusError as e:
                if msg.message_type == MessageType.METHOD_CALL:
                    self.send(e._as_message(msg))
                    handled = True
                    break
                else:
                    logging.error(
                        f'A message handler raised an exception: {e}.\n{traceback.format_exc()}')
            except Exception as e:
                logging.error(
                    f'A message handler raised an exception: {e}.\n{traceback.format_exc()}')
                if msg.message_type == MessageType.METHOD_CALL:
                    self.send(
                        Message.new_error(
                            msg, ErrorType.INTERNAL_ERROR,
                            f'An internal error occurred: {e}.\n{traceback.format_exc()}'))
                    handled = True
                    break

        if msg.message_type == MessageType.SIGNAL:
            if msg._matches(sender='org.freedesktop.DBus',
                            path='/org/freedesktop/DBus',
                            interface='org.freedesktop.DBus',
                            member='NameOwnerChanged'):
                [name, old_owner, new_owner] = msg.body
                if new_owner:
                    self._name_owners[name] = new_owner
                elif old_owner in self._name_owners:
                    del self._name_owners[old_owner]

        elif msg.message_type == MessageType.METHOD_CALL:
            if not handled:
                handler = self._find_message_handler(msg)

                send_reply = self._send_reply(msg)

                with send_reply:
                    if handler:
                        handler(msg, send_reply)
                    else:
                        send_reply(
                            Message.new_error(
                                msg, ErrorType.UNKNOWN_METHOD,
                                f'{msg.interface}.{msg.member} with signature "{msg.signature}" could not be found'
                            ))

        else:
            # An ERROR or a METHOD_RETURN
            if msg.reply_serial in self._method_return_handlers:
                if not handled:
                    handler = self._method_return_handlers[msg.reply_serial]
                    handler(msg, None)
                del self._method_return_handlers[msg.reply_serial]

    @classmethod
    def _make_method_handler(cls, interface, method):
        def handler(msg, send_reply):
            result = method.fn(interface, *msg.body)
            body = ServiceInterface._fn_result_to_body(result, method.out_signature_tree)
            send_reply(Message.new_method_return(msg, method.out_signature, body))

        return handler

    def _find_message_handler(self, msg):
        handler = None

        if msg._matches(interface='org.freedesktop.DBus.Introspectable',
                        member='Introspect',
                        signature=''):
            handler = self._default_introspect_handler

        elif msg._matches(interface='org.freedesktop.DBus.Properties'):
            handler = self._default_properties_handler

        elif msg._matches(interface='org.freedesktop.DBus.Peer'):
            if msg._matches(member='Ping', signature=''):
                handler = self._default_ping_handler
            elif msg._matches(member='GetMachineId', signature=''):
                handler = self._default_get_machine_id_handler
        elif msg._matches(interface='org.freedesktop.DBus.ObjectManager',
                          member='GetManagedObjects'):
            handler = self._default_get_managed_objects_handler

        else:
            for interface in self._path_exports.get(msg.path, []):
                for method in ServiceInterface._get_methods(interface):
                    if method.disabled:
                        continue
                    if msg._matches(interface=interface.name,
                                    member=method.name,
                                    signature=method.in_signature):
                        handler = self._make_method_handler(interface, method)
                        break
                if handler:
                    break

        return handler

    def _default_introspect_handler(self, msg, send_reply):
        introspection = self._introspect_export_path(msg.path).tostring()
        send_reply(Message.new_method_return(msg, 's', [introspection]))

    def _default_ping_handler(self, msg, send_reply):
        send_reply(Message.new_method_return(msg))

    def _default_get_machine_id_handler(self, msg, send_reply):
        if self._machine_id:
            send_reply(Message.new_method_return(msg, 's', self._machine_id))
            return

        def reply_handler(reply, err):
            if err:
                # the bus has been disconnected, cannot send a reply
                return

            if reply.message_type == MessageType.METHOD_RETURN:
                self._machine_id = reply.body[0]
                send_reply(Message.new_method_return(msg, 's', [self._machine_id]))
            elif reply.message_type == MessageType.ERROR:
                send_reply(Message.new_error(msg, reply.error_name, reply.body))
            else:
                send_reply(Message.new_error(msg, ErrorType.FAILED, 'could not get machine_id'))

        self._call(
            Message(destination='org.freedesktop.DBus',
                    path='/org/freedesktop/DBus',
                    interface='org.freedesktop.DBus.Peer',
                    member='GetMachineId'), reply_handler)

    def _default_get_managed_objects_handler(self, msg, send_reply):
        result = {}

        for node in self._path_exports:
            if not node.startswith(msg.path + '/') and msg.path != '/':
                continue

            result[node] = {}
            for interface in self._path_exports[node]:
                result[node][interface.name] = self._get_all_properties(interface)

        send_reply(Message.new_method_return(msg, 'a{oa{sa{sv}}}', [result]))

    def _default_properties_handler(self, msg, send_reply):
        methods = {'Get': 'ss', 'Set': 'ssv', 'GetAll': 's'}
        if msg.member not in methods or methods[msg.member] != msg.signature:
            raise DBusError(
                ErrorType.UNKNOWN_METHOD,
                f'properties interface doesn\'t have method "{msg.member}" with signature "{msg.signature}"'
            )

        interface_name = msg.body[0]
        if interface_name == '':
            raise DBusError(
                ErrorType.NOT_SUPPORTED,
                'getting and setting properties with an empty interface string is not supported yet'
            )
        elif msg.path not in self._path_exports:
            raise DBusError(ErrorType.UNKNOWN_OBJECT, f'no interfaces at path: "{msg.path}"')

        match = [iface for iface in self._path_exports[msg.path] if iface.name == interface_name]
        if not match:
            raise DBusError(
                ErrorType.UNKNOWN_INTERFACE,
                f'could not find an interface "{interface_name}" at path: "{msg.path}"')

        interface = match[0]
        properties = ServiceInterface._get_properties(interface)

        if msg.member == 'Get' or msg.member == 'Set':
            prop_name = msg.body[1]
            match = [prop for prop in properties if prop.name == prop_name and not prop.disabled]
            if not match:
                raise DBusError(
                    ErrorType.UNKNOWN_PROPERTY,
                    f'interface "{msg.interface}" does not have property "{prop_name}"')

            prop = match[0]
            if msg.member == 'Get':
                if not prop.access.readable():
                    raise DBusError(ErrorType.UNKNOWN_PROPERTY,
                                    'the property does not have read access')
                prop_value = getattr(interface, prop.prop_getter.__name__)
                send_reply(
                    Message.new_method_return(msg, 'v', [Variant(prop.signature, prop_value)]))
            elif msg.member == 'Set':
                if not prop.access.writable():
                    raise DBusError(ErrorType.PROPERTY_READ_ONLY, 'the property is readonly')
                value = msg.body[2]
                if value.signature != prop.signature:
                    raise DBusError(ErrorType.INVALID_SIGNATURE,
                                    f'wrong signature for property. expected "{prop.signature}"')
                assert prop.prop_setter
                setattr(interface, prop.prop_setter.__name__, value.value)
                send_reply(Message.new_method_return(msg))

        elif msg.member == 'GetAll':
            result = self._get_all_properties(interface)
            send_reply(Message.new_method_return(msg, 'a{sv}', [result]))
        else:
            assert False

    def _get_all_properties(self, interface):
        result = {}

        for prop in ServiceInterface._get_properties(interface):
            if prop.disabled or not prop.access.readable():
                continue
            result[prop.name] = Variant(prop.signature, getattr(interface,
                                                                prop.prop_getter.__name__))

        return result
