from dbus_next.aio import MessageBus
from dbus_next import Message

import pytest


@pytest.mark.asyncio
async def test_bus_disconnect_before_reply(event_loop):
    '''In this test, the bus disconnects before the reply comes in. Make sure
    the caller receives a reply with the error instead of hanging.'''

    bus = await MessageBus().connect()

    ping = bus.call(
        Message(destination='org.freedesktop.DBus',
                path='/org/freedesktop/DBus',
                interface='org.freedesktop.DBus',
                member='Ping'))

    event_loop.call_soon(bus.disconnect)

    with pytest.raises(EOFError):
        await ping

    assert bus._disconnected
