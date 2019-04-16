from .constants import BusType, MessageFlag
from .address import get_bus_address, parse_address, InvalidAddressError
from .message import Message
from .constants import MessageType, ErrorType, NameFlag, RequestNameReply, ReleaseNameReply
from .service_interface import ServiceInterface
from .validators import assert_object_path_valid, assert_bus_name_valid
from .errors import DBusError
from .variant import Variant
from . import introspection as intr

import inspect
import traceback
import socket
import logging


class BaseMessageBus():
    def __init__(self, bus_address=None, bus_type=BusType.SESSION):
        self.name = None
        self.method_return_handlers = {}
        # buffer messages until connect
        self.buffered_messages = []
        self.serial = 0
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_NONBLOCK)
        self.stream = self.sock.makefile('rwb')
        self.fd = self.sock.fileno()
        self.user_message_handlers = []
        self.name_owners = {}
        self.path_exports = {}
        self.disconnected = False

        # machine id is lazy loaded
        self.machine_id = None

        if bus_address:
            self.bus_address = parse_address(bus_address)
        else:
            self.bus_address = parse_address(get_bus_address(bus_type))

        self.setup_socket()

    def export(self, path, interface):
        assert_object_path_valid(path)
        if not isinstance(interface, ServiceInterface):
            raise TypeError('interface must be a ServiceInterface')

        if path not in self.path_exports:
            self.path_exports[path] = []

        for f in self.path_exports[path]:
            if f.name == interface.name:
                raise ValueError(
                    f'An interface with this name is already exported on this bus at path "{path}": "{interface.name}"'
                )

        for path, ifaces in self.path_exports.items():
            for i in ifaces:
                if i is interface:
                    raise ValueError(
                        f'This interface is already exported on this bus at path "{path}": "{interface.name}"'
                    )

        self.path_exports[path].append(interface)
        ServiceInterface.add_bus(interface, self)

    def unexport(self, path, interface=None):
        assert_object_path_valid(path)
        if interface and not isinstance(interface, ServiceInterface):
            raise TypeError('interface must be a ServiceInterface')

        if path not in self.path_exports:
            return

        if interface is None:
            for iface in self.path_exports[path]:
                ServiceInterface.remove_bus(iface, self)
            del self.path_exports[path]
        else:
            for i, iface in enumerate(self.path_exports[path]):
                if iface is interface:
                    ServiceInterface.remove_bus(iface, self)
                    del self.path_exports[path][i]
                    if not self.path_exports[path]:
                        del self.path_exports[path]
                    break

    @staticmethod
    def check_method_return(msg, err, signature):
        if err:
            raise err
        elif msg.message_type == MessageType.METHOD_RETURN and msg.signature == signature:
            return
        elif msg.message_type == MessageType.ERROR:
            raise DBusError.from_message(msg)
        else:
            raise DBusError(ErrorType.INTERNAL_ERROR, 'invalid message type for method call', msg)

    def introspect(self, bus_name, path, callback):
        def reply_notify(reply, err):
            try:
                BaseMessageBus.check_method_return(reply, err, 's')
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

    def request_name(self, name, flags=NameFlag.NONE, callback=None):
        assert_bus_name_valid(name)

        def reply_notify(reply, err):
            try:
                BaseMessageBus.check_method_return(reply, err, 'u')
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

    def release_name(self, name, callback=None):
        assert_bus_name_valid(name)

        def reply_notify(reply, err):
            try:
                BaseMessageBus.check_method_return(reply, err, 'u')
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

    def get_proxy_object(self, bus_name, path, introspection):
        # TODO pass in the proxy object class to the constructor and implement this here
        raise NotImplementedError('this method must be implemented in the child class')

    def disconnect(self):
        self.sock.shutdown(socket.SHUT_RDWR)

    def finalize(self, err):
        '''should be called after the socket disconnects with the disconnection
        error to clean up resources and put the bus in a disconnected state'''
        if self.disconnected:
            return

        for handler in self.method_return_handlers.values():
            handler(None, err)

        self.method_return_handlers.clear()

        for path in list(self.path_exports.keys()):
            self.unexport(path)

        self.disconnected = True

    def interface_signal_notify(self, interface, interface_name, member, signature, body):
        path = None
        for p, ifaces in self.path_exports.items():
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

    def introspect_export_path(self, path):
        assert_object_path_valid(path)

        node = None
        if path in self.path_exports:
            node = intr.Node.default(path)
            [
                node.interfaces.append(interface.introspect())
                for interface in self.path_exports[path]
            ]
        else:
            node = intr.Node(path)

        path_split = [path for path in path.split('/') if path]

        for export_path in self.path_exports.keys():
            export_path_split = [path for path in export_path.split('/') if path]
            if len(export_path_split) <= len(path_split):
                continue
            if all(path == export_path_split[i] for i, path in enumerate(path_split)):
                child = intr.Node(export_path_split[len(path_split)])
                node.nodes.append(child)

        return node

    def setup_socket(self):
        err = None

        for transport, options in self.bus_address:
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
                self.sock.connect(filename)
                break
            except Exception as e:
                err = e

        if err:
            raise err

    def next_serial(self):
        self.serial += 1
        return self.serial

    def add_message_handler(self, handler):
        self.user_message_handlers.append(handler)

    def remove_message_handler(self, handler):
        for i, h in enumerate(self.user_message_handlers):
            if h == handler:
                del self.user_message_handlers[i]
                break

    def send(self, msg):
        raise NotImplementedError('the "send" method must be implemented in the inheriting class')

    # for reply notify, the first argument is the message and the second is an
    # error
    def _call(self, msg, reply_notify=None):
        fn_signature = inspect.signature(reply_notify)
        if not callable(reply_notify) or len(fn_signature.parameters) != 2:
            raise TypeError('reply_notify must be a function with two parameters')

        if not msg.serial:
            msg.serial = self.next_serial()

        def notify(reply, err):
            if reply:
                self.name_owners[msg.destination] = reply.sender
            reply_notify(reply, err)

        if reply_notify:
            self.method_return_handlers[msg.serial] = notify

        self.send(msg)

        if reply_notify and msg.flags & MessageFlag.NO_REPLY_EXPECTED:
            reply_notify(None, None)

    def on_message(self, msg):
        try:
            self.process_message(msg)
        except Exception as e:
            logging.error(
                f'got unexpected error processing a message: {e}.\n{traceback.format_exc()}')

    def process_message(self, msg):
        handled = False

        for handler in self.user_message_handlers:
            try:
                result = handler(msg)
                if result:
                    if type(result) is Message:
                        self.send(result)
                    handled = True
                    break
            except DBusError as e:
                self.send(e.as_message(msg))
            except Exception as e:
                self.send(
                    Message.new_error(
                        msg, ErrorType.INTERNAL_ERROR,
                        f'An internal error occurred: {e}.\n{traceback.format_exc()}'))

        if msg.message_type == MessageType.SIGNAL:
            if msg.matches(sender='org.freedesktop.DBus',
                           path='/org/freedesktop/DBus',
                           interface='org.freedesktop.DBus',
                           member='NameOwnerChanged'):
                [name, old_owner, new_owner] = msg.body
                if new_owner:
                    self.name_owners[name] = new_owner
                elif old_owner in self.name_owners:
                    del self.name_owners[old_owner]

        elif msg.message_type == MessageType.METHOD_CALL:
            if not handled:
                handler = self.find_message_handler(msg)
                if handler:
                    try:
                        result = handler(msg)
                        if type(result) is Message:
                            self.send(result)
                    except DBusError as e:
                        self.send(e.as_message(msg))
                    except Exception as e:
                        self.send(
                            Message.new_error(
                                msg, ErrorType.SERVICE_ERROR,
                                f'The service interface raised an error: {e}.\n{traceback.format_exc()}'
                            ))

                else:
                    self.send(
                        Message.new_error(
                            msg, ErrorType.UNKNOWN_METHOD,
                            f'{msg.interface}.{msg.member} with signature "{msg.signature}" could not be found'
                        ))

        else:
            # An ERROR or a METHOD_RETURN
            if msg.reply_serial in self.method_return_handlers:
                if not handled:
                    handler = self.method_return_handlers[msg.reply_serial]
                    handler(msg, None)
                del self.method_return_handlers[msg.reply_serial]

    def find_message_handler(self, msg):
        handler = None

        if msg.matches(interface='org.freedesktop.DBus.Introspectable',
                       member='Introspect',
                       signature=''):
            handler = self.default_introspect_handler

        elif msg.matches(interface='org.freedesktop.DBus.Properties'):
            handler = self.default_properties_handler

        elif msg.matches(interface='org.freedesktop.DBus.Peer'):
            if msg.matches(member='Ping', signature=''):
                handler = self.default_ping_handler
            elif msg.matches(member='GetMachineId', signature=''):
                handler = self.default_get_machine_id_handler

        else:
            for interface in self.path_exports.get(msg.path, []):
                for method in ServiceInterface.get_methods(interface):
                    if method.disabled:
                        continue
                    if msg.matches(interface=interface.name,
                                   member=method.name,
                                   signature=method.in_signature):
                        handler = ServiceInterface.make_method_handler(interface, method)
                        break
                if handler:
                    break

        return handler

    def default_introspect_handler(self, msg):
        introspection = self.introspect_export_path(msg.path).tostring()
        return Message.new_method_return(msg, 's', [introspection])

    def default_ping_handler(self, msg):
        return Message.new_method_return(msg)

    def default_get_machine_id_handler(self, msg):
        if self.machine_id:
            self.send(Message.new_method_return(msg, 's', self.machine_id))
            return

        def reply_handler(reply, err):
            if err:
                # the bus has been disconnected, cannot send a reply
                return

            if reply.message_type == MessageType.METHOD_RETURN:
                self.machine_id = reply.body[0]
                self.send(Message.new_method_return(msg, 's', [self.machine_id]))
            elif reply.message_type == MessageType.ERROR:
                self.send(Message.new_error(msg, reply.error_name, reply.body))
            else:
                self.send(Message.new_error(msg, ErrorType.FAILED, 'could not get machine_id'))

        self._call(
            Message(destination='org.freedesktop.DBus',
                    path='/org/freedesktop/DBus',
                    interface='org.freedesktop.DBus.Peer',
                    member='GetMachineId'), reply_handler)

    def default_properties_handler(self, msg):
        methods = {'Get': 'ss', 'Set': 'ssv', 'GetAll': 's'}
        if msg.member not in methods or methods[msg.member] != msg.signature:
            raise DBusError(
                ErrorType.UNKNOWN_METHOD,
                'properties interface doesn\'t have method "{msg.member}" with signature "{msg.signature}"'
            )

        interface_name = msg.body[0]
        if interface_name == '':
            raise DBusError(
                ErrorType.NOT_SUPPORTED,
                'getting and setting properties with an empty interface string is not supported yet'
            )
        elif msg.path not in self.path_exports:
            raise DBusError(ErrorType.UNKNOWN_OBJECT, f'no interfaces at path: "{msg.path}"')

        match = [iface for iface in self.path_exports[msg.path] if iface.name == interface_name]
        if not match:
            raise DBusError(
                ErrorType.UNKNOWN_INTERFACE,
                f'could not find an interface "{interface_name}" at path: "{msg.path}"')

        interface = match[0]
        properties = ServiceInterface.get_properties(interface)

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
                return Message.new_method_return(msg, 'v', [Variant(prop.signature, prop_value)])
            elif msg.member == 'Set':
                if not prop.access.writable():
                    raise DBusError(ErrorType.PROPERTY_READ_ONLY, 'the property is readonly')
                value = msg.body[2]
                if value.signature != prop.signature:
                    raise DBusError(ErrorType.INVALID_SIGNATURE,
                                    f'wrong signature for property. expected "{prop.signature}"')
                assert prop.prop_setter
                setattr(interface, prop.prop_setter.__name__, value.value)
                return Message.new_method_return(msg)

        elif msg.member == 'GetAll':
            result = {}
            for prop in ServiceInterface.get_properties(interface):
                if prop.disabled or not prop.access.readable():
                    continue
                result[prop.name] = Variant(prop.signature,
                                            getattr(interface, prop.prop_getter.__name__))

            return Message.new_method_return(msg, 'a{sv}', [result])
        else:
            assert False
