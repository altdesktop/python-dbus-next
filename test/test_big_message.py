from dbus_next import aio, glib, Message, MessageType
from dbus_next.service import ServiceInterface, method
from test.util import check_gi_repository, skip_reason_no_gi

import pytest

has_gi = check_gi_repository()


class ExampleInterface(ServiceInterface):
    def __init__(self):
        super().__init__('example.interface')

    @method()
    def echo_bytes(self, what: 'ay') -> 'ay':
        return what


@pytest.mark.asyncio
async def test_aio_big_message():
    'this tests that nonblocking reads and writes actually work for aio'
    bus1 = await aio.MessageBus().connect()
    bus2 = await aio.MessageBus().connect()
    interface = ExampleInterface()
    bus1.export('/test/path', interface)

    # two megabytes
    big_body = [bytes(1000000) * 2]
    result = await bus2.call(
        Message(destination=bus1.unique_name,
                path='/test/path',
                interface=interface.name,
                member='echo_bytes',
                signature='ay',
                body=big_body))
    assert result.message_type == MessageType.METHOD_RETURN, result.body[0]
    assert result.body[0] == big_body[0]


@pytest.mark.skipif(not has_gi, reason=skip_reason_no_gi)
def test_glib_big_message():
    'this tests that nonblocking reads and writes actually work for glib'
    bus1 = glib.MessageBus().connect_sync()
    bus2 = glib.MessageBus().connect_sync()
    interface = ExampleInterface()
    bus1.export('/test/path', interface)

    # two megabytes
    big_body = [bytes(1000000) * 2]
    result = bus2.call_sync(
        Message(destination=bus1.unique_name,
                path='/test/path',
                interface=interface.name,
                member='echo_bytes',
                signature='ay',
                body=big_body))
    assert result.message_type == MessageType.METHOD_RETURN, result.body[0]
    assert result.body[0] == big_body[0]
