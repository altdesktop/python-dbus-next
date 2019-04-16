from dbus_next.aio.message_bus import MessageBus
from dbus_next.glib.message_bus import MessageBus as GLibMessageBus
from dbus_next.message import Message
from dbus_next.constants import MessageType
from dbus_next.service_interface import ServiceInterface, method

import pytest


class ExampleInterface(ServiceInterface):
    def __init__(self):
        super().__init__('example.interface')

    @method()
    def echo_bytes(self, what: 'ay') -> 'ay':
        return what


@pytest.mark.asyncio
async def test_aio_big_message():
    'this tests that nonblocking reads and writes actually work for aio'
    bus1 = await MessageBus().connect()
    bus2 = await MessageBus().connect()
    interface = ExampleInterface()
    bus1.export('/test/path', interface)

    # two megabytes
    big_body = [bytes(1000000) * 2]
    result = await bus2.call(
        Message(destination=bus1.name,
                path='/test/path',
                interface=interface.name,
                member='echo_bytes',
                signature='ay',
                body=big_body))
    assert result.message_type == MessageType.METHOD_RETURN, result.body[0]
    assert result.body[0] == big_body[0]


def test_glib_big_message():
    'this tests that nonblocking reads and writes actually work for glib'
    bus1 = GLibMessageBus().connect_sync()
    bus2 = GLibMessageBus().connect_sync()
    interface = ExampleInterface()
    bus1.export('/test/path', interface)

    # two megabytes
    big_body = [bytes(1000000) * 2]
    result = bus2.call_sync(
        Message(destination=bus1.name,
                path='/test/path',
                interface=interface.name,
                member='echo_bytes',
                signature='ay',
                body=big_body))
    assert result.message_type == MessageType.METHOD_RETURN, result.body[0]
    assert result.body[0] == big_body[0]
