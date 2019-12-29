from ..message_bus import BaseMessageBus
from .._private.unmarshaller import Unmarshaller
from ..message import Message
from ..constants import BusType, NameFlag, RequestNameReply, ReleaseNameReply, MessageType, MessageFlag
from ..service import ServiceInterface
from .._private.auth import auth_external, auth_parse_line, auth_begin, AuthResponse
from ..errors import AuthError, DBusError
from .proxy_object import ProxyObject
from .. import introspection as intr

import logging
import asyncio
import traceback
from typing import Optional


class MessageBus(BaseMessageBus):
    """The message bus implementation for use with asyncio.

    The message bus class is the entry point into all the features of the
    library. It sets up a connection to the DBus daemon and exposes an
    interface to send and receive messages and expose services.

    You must call :func:`connect() <dbus_next.aio.MessageBus.connect>` before
    using this message bus.

    :param bus_type: The type of bus to connect to. Affects the search path for
        the bus address.
    :type bus_type: :class:`BusType <dbus_next.BusType>`
    :param bus_address: A specific bus address to connect to. Should not be
        used under normal circumstances.

    :ivar unique_name: The unique name of the message bus connection. It will
        be :class:`None` until the message bus connects.
    :vartype unique_name: str
    """

    def __init__(self, bus_address: str = None, bus_type: BusType = BusType.SESSION):
        super().__init__(bus_address, bus_type, ProxyObject)
        self._loop = asyncio.get_event_loop()
        self._unmarshaller = Unmarshaller(self._stream)

    async def connect(self) -> 'MessageBus':
        """Connect this message bus to the DBus daemon.

        This method must be called before the message bus can be used.

        :returns: This message bus for convenience.
        :rtype: :class:`MessageBus <dbus_next.aio.MessageBus>`

        :raises:
            - :class:`AuthError <dbus_next.AuthError>` - If authorization to \
              the DBus daemon failed.
            - :class:`Exception` - If there was a connection error.
        """
        future = self._loop.create_future()

        await self._loop.sock_sendall(self._sock, b'\0')
        await self._loop.sock_sendall(self._sock, auth_external())
        response, args = auth_parse_line(await self._auth_readline())

        if response != AuthResponse.OK:
            raise AuthError(f'authorization failed: {response.value}: {args}')

        self._stream.write(auth_begin())
        self._stream.flush()

        self._loop.add_reader(self._fd, self._message_reader)

        def on_hello(reply, err):
            if err:
                logging.error(f'sending "Hello" message failed: {err}\n{traceback.print_exc()}')
                self.disconnect()
                self._finalize(err)
                future.set_exception(err)
                return
            self.unique_name = reply.body[0]
            for m in self._buffered_messages:
                self.send(m)
            self._buffered_messages.clear()
            future.set_result(self)

        def on_match_added(reply, err):
            if err:
                logging.error(f'adding match to "NameOwnerChanged" failed')
                self.disconnect()
                self._finalize(err)
            elif reply.message_type == MessageType.ERROR:
                logging.error(f'adding match to "NameOwnerChanged" failed')
                self.disconnect()
                self._finalize(DBusError._from_message(reply))

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

        return await future

    async def introspect(self, bus_name: str, path: str, timeout: float = 30.0) -> intr.Node:
        """Get introspection data for the node at the given path from the given
        bus name.

        Calls the standard ``org.freedesktop.DBus.Introspectable.Introspect``
        on the bus for the path.

        :param bus_name: The name to introspect.
        :type bus_name: str
        :param path: The path to introspect.
        :type path: str
        :param timeout: The timeout to introspect.
        :type timeout: float

        :returns: The introspection data for the name at the path.
        :rtype: :class:`Node <dbus_next.introspection.Node>`

        :raises:
            - :class:`InvalidObjectPathError <dbus_next.InvalidObjectPathError>` \
                    - If the given object path is not valid.
            - :class:`InvalidBusNameError <dbus_next.InvalidBusNameError>` - If \
                  the given bus name is not valid.
            - :class:`DBusError <dbus_next.DBusError>` - If the service threw \
                  an error for the method call or returned an invalid result.
            - :class:`Exception` - If a connection error occurred.
            - :class:`asyncio.TimeoutError` - Waited for future but time run out.
        """
        future = self._loop.create_future()

        def reply_handler(reply, err):
            if err:
                future.set_exception(err)
            else:
                future.set_result(reply)

        super().introspect(bus_name, path, reply_handler)

        return await asyncio.wait_for(future, timeout=timeout)

    async def request_name(self, name: str, flags: NameFlag = NameFlag.NONE) -> RequestNameReply:
        """Request that this message bus owns the given name.

        :param name: The name to request.
        :type name: str
        :param flags: Name flags that affect the behavior of the name request.
        :type flags: :class:`NameFlag <dbus_next.NameFlag>`

        :returns: The reply to the name request.
        :rtype: :class:`RequestNameReply <dbus_next.RequestNameReply>`

        :raises:
            - :class:`InvalidBusNameError <dbus_next.InvalidBusNameError>` - If \
                  the given bus name is not valid.
            - :class:`DBusError <dbus_next.DBusError>` - If the service threw \
                  an error for the method call or returned an invalid result.
            - :class:`Exception` - If a connection error occurred.
        """
        future = self._loop.create_future()

        def reply_handler(reply, err):
            if err:
                future.set_exception(err)
            else:
                future.set_result(reply)

        super().request_name(name, flags, reply_handler)

        return await future

    async def release_name(self, name: str) -> ReleaseNameReply:
        """Request that this message bus release the given name.

        :param name: The name to release.
        :type name: str

        :returns: The reply to the release request.
        :rtype: :class:`ReleaseNameReply <dbus_next.ReleaseNameReply>`

        :raises:
            - :class:`InvalidBusNameError <dbus_next.InvalidBusNameError>` - If \
                  the given bus name is not valid.
            - :class:`DBusError <dbus_next.DBusError>` - If the service threw \
                  an error for the method call or returned an invalid result.
            - :class:`Exception` - If a connection error occurred.
        """
        future = self._loop.create_future()

        def reply_handler(reply, err):
            if err:
                future.set_exception(err)
            else:
                future.set_result(reply)

        super().release_name(name, reply_handler)

        return await future

    async def call(self, msg: Message) -> Optional[Message]:
        """Send a method call and wait for a reply from the DBus daemon.

        :param msg: The method call message to send.
        :type msg: :class:`Message <dbus_next.Message>`

        :returns: A message in reply to the message sent. If the message does
            not expect a reply based on the message flags or type, returns
            ``None`` immediately.
        :rtype: :class:`Message <dbus_next.Message>`

        :raises:
            - :class:`DBusError <dbus_next.DBusError>` - If the service threw \
                  an error for the method call or returned an invalid result.
            - :class:`Exception` - If a connection error occurred.
        """
        if msg.flags & MessageFlag.NO_REPLY_EXPECTED or msg.message_type is not MessageType.METHOD_CALL:
            self.send(msg)
            return None

        future = self._loop.create_future()

        def reply_handler(reply, err):
            if err:
                future.set_exception(err)
            else:
                future.set_result(reply)

        self._call(msg, reply_handler)

        await future

        return future.result()

    def send(self, msg: Message):
        if not msg.serial:
            msg.serial = self.next_serial()

        if not self.unique_name:
            # not connected yet, buffer the message
            self._buffered_messages.append(msg)
            return

        asyncio.ensure_future(self._loop.sock_sendall(self._sock, msg._marshall()))

    def get_proxy_object(self, bus_name: str, path: str, introspection: intr.Node) -> ProxyObject:
        return super().get_proxy_object(bus_name, path, introspection)

    @classmethod
    def _make_method_handler(cls, interface, method):
        if not asyncio.iscoroutinefunction(method.fn):
            return super()._make_method_handler(interface, method)

        def handler(msg, send_reply):
            def done(fut):
                with send_reply:
                    result = fut.result()
                    body = ServiceInterface._fn_result_to_body(result, method.out_signature_tree)
                    send_reply(Message.new_method_return(msg, method.out_signature, body))

            fut = asyncio.ensure_future(method.fn(interface, *msg.body))
            fut.add_done_callback(done)

        return handler

    def _message_reader(self):
        try:
            while True:
                if self._unmarshaller.unmarshall():
                    self._on_message(self._unmarshaller.message)
                    self._unmarshaller = Unmarshaller(self._stream)
                else:
                    break
        except Exception as e:
            self._loop.remove_reader(self._fd)
            self._finalize(e)

    async def _auth_readline(self):
        buf = b''
        while buf[-2:] != b'\r\n':
            buf += await self._loop.sock_recv(self._sock, 2)
        return buf
