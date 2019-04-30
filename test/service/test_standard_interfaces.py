from dbus_next.service import ServiceInterface
from dbus_next.aio import MessageBus
from dbus_next import Message, MessageType, introspection as intr

import pytest

standard_interfaces_count = len(intr.Node.default().interfaces)


class ExampleInterface(ServiceInterface):
    def __init__(self, name):
        super().__init__(name)


@pytest.mark.asyncio
async def test_export_unexport():
    interface = ExampleInterface('test.interface')
    interface2 = ExampleInterface('test.interface2')
    export_path = '/test/path'
    export_path2 = '/test/path/child'
    bus = await MessageBus().connect()
    bus.export(export_path, interface)
    assert export_path in bus._path_exports
    assert len(bus._path_exports[export_path]) == 1
    assert bus._path_exports[export_path][0] is interface
    bus.export(export_path2, interface2)

    node = bus._introspect_export_path(export_path)
    assert len(node.interfaces) == standard_interfaces_count + 1
    assert len(node.nodes) == 1
    # relative path
    assert node.nodes[0].name == 'child'

    bus.unexport(export_path, interface)
    assert export_path not in bus._path_exports

    bus.export(export_path2, interface)
    assert len(bus._path_exports[export_path2]) == 2
    bus.unexport(export_path2)
    assert not bus._path_exports

    node = bus._introspect_export_path('/path/doesnt/exist')
    assert type(node) is intr.Node
    assert not node.interfaces
    assert not node.nodes


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
