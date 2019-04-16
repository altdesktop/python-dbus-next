from ..message_bus import BaseMessageBus
from ..unmarshaller import Unmarshaller
from ..message import Message
from ..constants import BusType, NameFlag
from ..auth import auth_external, auth_parse_line, auth_begin, AuthResponse, AuthError
from .proxy_object import ProxyObject

import logging
import asyncio
import traceback


class MessageBus(BaseMessageBus):
    def __init__(self, bus_address=None, bus_type=BusType.SESSION, loop=None):
        super().__init__(bus_address, bus_type)
        self.loop = loop if loop else asyncio.get_event_loop()
        self.unmarshaller = Unmarshaller(self.stream)

    def message_reader(self):
        try:
            while True:
                if self.unmarshaller.unmarshall():
                    self.on_message(self.unmarshaller.message)
                    self.unmarshaller = Unmarshaller(self.stream)
                else:
                    break
        except Exception as e:
            self.loop.remove_reader(self.fd)
            self.finalize(e)

    async def auth_readline(self):
        buf = b''
        while buf[-2:] != b'\r\n':
            buf += await self.loop.sock_recv(self.sock, 2)
        return buf

    async def connect(self):
        future = self.loop.create_future()

        await self.loop.sock_sendall(self.sock, b'\0')
        await self.loop.sock_sendall(self.sock, auth_external())
        response, args = auth_parse_line(await self.auth_readline())

        if response != AuthResponse.OK:
            raise AuthError(f'authorization failed: {response.value}: {args}')

        self.stream.write(auth_begin())
        self.stream.flush()

        self.loop.add_reader(self.fd, self.message_reader)

        def on_hello(reply, err):
            if err:
                logging.error(f'sending "Hello" message failed: {err}\n{traceback.print_exc()}')
                self.disconnect(err)
                return
            self.name = reply.body[0]
            for m in self.buffered_messages:
                self.send(m)
            self.buffered_messages.clear()
            future.set_result(self)

        def on_match_added(reply, err):
            if err:
                logging.error(f'adding match to "NameOwnerChanged" failed')
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

        self.method_return_handlers[hello_msg.serial] = on_hello
        self.method_return_handlers[add_match_msg.serial] = on_match_added
        self.stream.write(hello_msg.marshall())
        self.stream.write(add_match_msg.marshall())
        self.stream.flush()

        return await future

    async def introspect(self, bus_name, path):
        future = self.loop.create_future()

        def reply_handler(reply, err):
            if err:
                future.set_exception(err)
            else:
                future.set_result(reply)

        super().introspect(bus_name, path, reply_handler)

        return await future

    async def request_name(self, name, flags=NameFlag.NONE):
        future = self.loop.create_future()

        def reply_handler(reply, err):
            if err:
                future.set_exception(err)
            else:
                future.set_result(reply)

        super().request_name(name, flags, reply_handler)

        return await future

    async def release_name(self, name):
        future = self.loop.create_future()

        def reply_handler(reply, err):
            if err:
                future.set_exception(err)
            else:
                future.set_result(reply)

        super().release_name(name, reply_handler)

        return await future

    async def call(self, msg):
        future = self.loop.create_future()

        def reply_handler(reply, err):
            if err:
                future.set_exception(err)
            else:
                future.set_result(reply)

        self._call(msg, reply_handler)

        await future

        return future.result()

    def send(self, msg):
        if not msg.serial:
            msg.serial = self.next_serial()

        if not self.name:
            # not connected yet, buffer the message
            self.buffered_messages.append(msg)
            return

        asyncio.ensure_future(self.loop.sock_sendall(self.sock, msg.marshall()))

    def get_proxy_object(self, bus_name, path, introspection):
        return ProxyObject(bus_name, path, introspection, self)
