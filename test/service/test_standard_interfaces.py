from dbus_next.service import ServiceInterface
from dbus_next.aio import MessageBus
from dbus_next import Message, MessageType, introspection as intr

import pytest

standard_interfaces_count = len(intr.Node.default().interfaces)


class ExampleInterface(ServiceInterface):
    def __init__(self, name):
        super().__init__(name)


@pytest.mark.asyncio
async def test_introspectable_interface():
    bus1 = await MessageBus().connect()
    bus2 = await MessageBus().connect()

    interface = ExampleInterface('test.interface')
    interface2 = ExampleInterface('test.interface2')

    export_path = '/test/path'
    bus1.export(export_path, interface)
    bus1.export(export_path, interface2)

    reply = await bus2.call(
        Message(destination=bus1.unique_name,
                path=export_path,
                interface='org.freedesktop.DBus.Introspectable',
                member='Introspect'))

    assert reply.message_type == MessageType.METHOD_RETURN, reply.body[0]
    assert reply.signature == 's'
    node = intr.Node.parse(reply.body[0])
    assert len(node.interfaces) == standard_interfaces_count + 2
    assert node.interfaces[-1].name == 'test.interface2'
    assert node.interfaces[-2].name == 'test.interface'
    assert not node.nodes

    # introspect works on every path
    reply = await bus2.call(
        Message(destination=bus1.unique_name,
                path='/path/doesnt/exist',
                interface='org.freedesktop.DBus.Introspectable',
                member='Introspect'))
    assert reply.message_type == MessageType.METHOD_RETURN, reply.body[0]
    assert reply.signature == 's'
    node = intr.Node.parse(reply.body[0])
    assert not node.interfaces
    assert not node.nodes


@pytest.mark.asyncio
async def test_peer_interface():
    bus1 = await MessageBus().connect()
    bus2 = await MessageBus().connect()

    reply = await bus2.call(
        Message(destination=bus1.unique_name,
                path='/path/doesnt/exist',
                interface='org.freedesktop.DBus.Peer',
                member='Ping'))

    assert reply.message_type == MessageType.METHOD_RETURN, reply.body[0]
    assert reply.signature == ''

    reply = await bus2.call(
        Message(destination=bus1.unique_name,
                path='/path/doesnt/exist',
                interface='org.freedesktop.DBus.Peer',
                member='GetMachineId',
                signature=''))

    assert reply.message_type == MessageType.METHOD_RETURN, reply.body[0]
    assert reply.signature == 's'
