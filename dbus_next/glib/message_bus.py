from .._private.unmarshaller import Unmarshaller
from ..constants import BusType
from ..message import Message
from ..constants import MessageType, MessageFlag, NameFlag
from ..message_bus import BaseMessageBus
from .._private.auth import auth_external, auth_begin, auth_parse_line, AuthResponse
from ..errors import AuthError
from .proxy_object import ProxyObject

import logging
import io

# glib is optional
_import_error = None
try:
    from gi.repository import GLib
    _GLibSource = GLib.Source
except ImportError as e:
    _import_error = e

    class _GLibSource:
        pass


class _MessageSource(_GLibSource):
    def __init__(self, bus):
        self.unmarshaller = None
        self.bus = bus

    def prepare(self):
        return (False, -1)

    def check(self):
        return False

    def dispatch(self, callback, user_data):
        try:
            while self.bus._stream.readable():
                if not self.unmarshaller:
                    self.unmarshaller = Unmarshaller(self.bus._stream)

                if self.unmarshaller.unmarshall():
                    callback(self.unmarshaller.message)
                    self.unmarshaller = None
                else:
                    break
        except Exception as e:
            self.bus.disconnect()
            self.bus._finalize(e)
            return GLib.SOURCE_REMOVE

        return GLib.SOURCE_CONTINUE


class _MessageWritableSource(_GLibSource):
    def __init__(self, bus):
        self.bus = bus
        self.buf = b''
        self.message_stream = None
        self.chunk_size = 128

    def prepare(self):
        return (False, -1)

    def check(self):
        return False

    def dispatch(self, callback, user_data):
        try:
            if self.buf:
                self.bus._stream.write(self.buf)
                self.buf = b''

            if self.message_stream:
                while True:
                    self.buf = self.message_stream.read(self.chunk_size)
                    if self.buf == b'':
                        break
                    self.bus._stream.write(self.buf)
                    if len(self.buf) < self.chunk_size:
                        self.buf = b''
                        break
                    self.buf = b''

            self.bus._stream.flush()

            if not self.bus._buffered_messages:
                return GLib.SOURCE_REMOVE
            else:
                message = self.bus._buffered_messages.pop(0)
                self.message_stream = io.BytesIO(message._marshall())
                return GLib.SOURCE_CONTINUE
        except BlockingIOError:
            return GLib.SOURCE_CONTINUE
        except Exception as e:
            self.bus._finalize(e)
            return GLib.SOURCE_REMOVE


class _AuthLineSource(_GLibSource):
    def __init__(self, stream):
        self.stream = stream
        self.buf = b''

    def prepare(self):
        return (False, -1)

    def check(self):
        return False

    def dispatch(self, callback, user_data):
        self.buf += self.stream.read()
        if self.buf[-2:] == b'\r\n':
            callback(self.buf)
            return GLib.SOURCE_REMOVE

        return GLib.SOURCE_CONTINUE


class MessageBus(BaseMessageBus):
    def __init__(self, bus_address=None, bus_type=BusType.SESSION, main_context=None):
        if _import_error:
            raise _import_error

        super().__init__(bus_address, bus_type)
        self.main_context = main_context if main_context else GLib.main_context_default()

    def connect(self, connect_notify=None):
        self._stream.write(b'\0')
        self._stream.write(auth_external())
        self._stream.flush()

        def on_authline(line):
            response, args = auth_parse_line(line)

            if response != AuthResponse.OK:
                raise AuthError(f'authorization failed: {response.value}: {args}')

            self._stream.write(auth_begin())
            self._stream.flush()

            self.message_source = _MessageSource(self)
            self.message_source.set_callback(self._on_message)
            self.message_source.attach(self.main_context)

            self.writable_source = None

            self.message_source.add_unix_fd(self._fd, GLib.IO_IN)

            def on_hello(reply, err):
                if err:
                    if connect_notify:
                        connect_notify(reply, err)
                    return

                self.unique_name = reply.body[0]

                for m in self._buffered_messages:
                    self.send(m)

                if connect_notify:
                    connect_notify(self, err)

            def on_match_added(reply, err):
                if err:
                    logging.error(f'adding match to "NameOwnerChanged" failed: {err}')
                    self.disconnect()
                    return

            hello_msg = Message(destination='org.freedesktop.DBus',
                                path='/org/freedesktop/DBus',
                                interface='org.freedesktop.DBus',
                                member='Hello',
                                serial=self.next_serial())

            match = "sender='org.freedesktop.DBus',interface='org.freedesktop.DBus',path='/org/freedesktop/DBus',member='NameOwnerChanged'"
            add_match_msg = Message(destination='org.freedesktop.DBus',
                                    path='/org/freedesktop/DBus',
                                    interface='org.freedesktop.DBus',
                                    member='AddMatch',
                                    signature='s',
                                    body=[match],
                                    serial=self.next_serial())

            self._method_return_handlers[hello_msg.serial] = on_hello
            self._method_return_handlers[add_match_msg.serial] = on_match_added
            self._stream.write(hello_msg._marshall())
            self._stream.write(add_match_msg._marshall())
            self._stream.flush()

        self._auth_readline(on_authline)

    def connect_sync(self):
        main = GLib.MainLoop()
        connection_error = None

        def connect_notify(bus, err):
            nonlocal connection_error
            connection_error = err
            main.quit()

        self.connect(connect_notify)
        main.run()

        if connection_error:
            raise connection_error

        return self

    def call_sync(self, msg):
        if msg.message_type != MessageType.METHOD_CALL:
            raise Exception('only METHOD_CALL message types can expect a return value')

        if not msg.serial:
            msg.serial = self.next_serial()

        main = GLib.MainLoop()
        handler_reply = None
        connection_error = None

        def reply_handler(reply, err):
            nonlocal handler_reply
            nonlocal connection_error

            handler_reply = reply
            connection_error = err

            main.quit()

        if msg.flags & MessageFlag.NO_REPLY_EXPECTED:
            return None
        else:
            self._method_return_handlers[msg.serial] = reply_handler
            self.send(msg)
            main.run()

            if connection_error:
                raise connection_error

            return handler_reply

    def introspect_sync(self, bus_name, path):
        main = GLib.MainLoop()
        request_result = None
        request_error = None

        def reply_notify(result, err):
            nonlocal request_result
            nonlocal request_error

            request_result = result
            request_error = err

            main.quit()

        super().introspect(bus_name, path, reply_notify)
        main.run()

        if request_error:
            raise request_error

        return request_result

    def request_name_sync(self, name, flags=NameFlag.NONE):
        main = GLib.MainLoop()
        request_result = None
        request_error = None

        def reply_notify(result, err):
            nonlocal request_result
            nonlocal request_error

            request_result = result
            request_error = err

            main.quit()

        super().request_name(name, flags, reply_notify)
        main.run()

        if request_error:
            raise request_error

        return request_result

    def release_name_sync(self, name):
        main = GLib.MainLoop()
        release_result = None
        release_error = None

        def reply_notify(result, err):
            nonlocal release_result
            nonlocal release_error

            release_result = result
            release_error = err

            main.quit()

        super().release_name(name, reply_notify)
        main.run()

        if release_error:
            raise release_error

        return release_result

    def send(self, msg):
        if not msg.serial:
            msg.serial = self.next_serial()

        self._buffered_messages.append(msg)

        if self.unique_name:
            self._schedule_write()

    def call(self, msg, reply_notify=None):
        self._call(msg, reply_notify)

    def get_proxy_object(self, bus_name, path, introspection):
        return ProxyObject(bus_name, path, introspection, self)

    def _schedule_write(self):
        if self.writable_source is None or self.writable_source.is_destroyed():
            self.writable_source = _MessageWritableSource(self)
            self.writable_source.attach(self.main_context)
            self.writable_source.add_unix_fd(self._fd, GLib.IO_OUT)

    def _auth_readline(self, callback):
        readline_source = _AuthLineSource(self._stream)
        readline_source.set_callback(callback)
        readline_source.add_unix_fd(self._fd, GLib.IO_IN)
        readline_source.attach(self.main_context)
        # make sure it doesnt get cleaned up
        self._readline_source = readline_source
