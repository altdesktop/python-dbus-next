from dbus_next.aio import MessageBus
from dbus_next import Message
from dbus_next._private.address import parse_address

import asyncio
import pytest
import os


@pytest.mark.asyncio
async def test_tcp_connection_with_forwarding(event_loop):
    closables = []
    host = '127.0.0.1'
    port = '55556'

    addr_info = parse_address(os.environ.get('DBUS_SESSION_BUS_ADDRESS'))
    assert addr_info
    assert 'abstract' in addr_info[0][1]
    path = f'\0{addr_info[0][1]["abstract"]}'

    async def handle_connection(tcp_reader, tcp_writer):
        unix_reader, unix_writer = await asyncio.open_unix_connection(path)
        closables.append(tcp_writer)
        closables.append(unix_writer)

        async def handle_read():
            while True:
                data = await tcp_reader.read(1)
                if not data:
                    break
                unix_writer.write(data)

        async def handle_write():
            while True:
                data = await unix_reader.read(1)
                if not data:
                    break
                tcp_writer.write(data)

        asyncio.run_coroutine_threadsafe(handle_read(), event_loop)
        asyncio.run_coroutine_threadsafe(handle_write(), event_loop)

    server = await asyncio.start_server(handle_connection, host, port)
    closables.append(server)

    bus = await MessageBus(bus_address=f'tcp:host={host},port={port}').connect()

    # basic tests to see if it works
    result = await bus.call(
        Message(destination='org.freedesktop.DBus',
                path='/org/freedesktop/DBus',
                interface='org.freedesktop.DBus.Peer',
                member='Ping'))
    assert result

    intr = await bus.introspect('org.freedesktop.DBus', '/org/freedesktop/DBus')
    obj = bus.get_proxy_object('org.freedesktop.DBus', '/org/freedesktop/DBus', intr)
    iface = obj.get_interface('org.freedesktop.DBus.Peer')
    await iface.call_ping()

    assert bus._sock.getpeername()[0] == host
    assert bus._sock.getsockname()[0] == host
    assert bus._sock.gettimeout() == 0
    assert bus._stream.closed is False

    for c in closables:
        c.close()
