from dbus_next.service import ServiceInterface, method
from dbus_next.aio import MessageBus
from dbus_next import Message, MessageType, introspection as intr

import pytest

standard_interfaces_count = len(intr.Node.default().interfaces)


class ExampleInterface(ServiceInterface):
    def __init__(self, name):
        self._method_called = False
        super().__init__(name)

    @method()
    def some_method(self):
        self._method_called = True


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
    assert len(ServiceInterface._get_buses(interface)) == 1

    bus.export(export_path2, interface2)

    node = bus._introspect_export_path(export_path)
    assert len(node.interfaces) == standard_interfaces_count + 1
    assert len(node.nodes) == 1
    # relative path
    assert node.nodes[0].name == 'child'

    bus.unexport(export_path, interface)
    assert export_path not in bus._path_exports
    assert len(ServiceInterface._get_buses(interface)) == 0

    bus.export(export_path2, interface)
    assert len(bus._path_exports[export_path2]) == 2

    # test unexporting the whole path
    bus.unexport(export_path2)
    assert not bus._path_exports
    assert not ServiceInterface._get_buses(interface)
    assert not ServiceInterface._get_buses(interface2)

    # test unexporting by name
    bus.export(export_path, interface)
    bus.unexport(export_path, interface.name)
    assert not bus._path_exports
    assert not ServiceInterface._get_buses(interface)

    node = bus._introspect_export_path('/path/doesnt/exist')
    assert type(node) is intr.Node
    assert not node.interfaces
    assert not node.nodes


@pytest.mark.asyncio
async def test_export_alias():
    bus = await MessageBus().connect()

    interface = ExampleInterface('test.interface')

    export_path = '/test/path'
    export_path2 = '/test/path/child'

    bus.export(export_path, interface)
    bus.export(export_path2, interface)

    result = await bus.call(
        Message(destination=bus.unique_name,
                path=export_path,
                interface='test.interface',
                member='some_method'))
    assert result.message_type is MessageType.METHOD_RETURN, result.body[0]

    assert interface._method_called
    interface._method_called = False

    result = await bus.call(
        Message(destination=bus.unique_name,
                path=export_path2,
                interface='test.interface',
                member='some_method'))
    assert result.message_type is MessageType.METHOD_RETURN, result.body[0]
    assert interface._method_called


@pytest.mark.asyncio
async def test_export_introspection():
    interface = ExampleInterface('test.interface')
    interface2 = ExampleInterface('test.interface2')

    export_path = '/test/path'
    export_path2 = '/test/path/child'

    bus = await MessageBus().connect()
    bus.export(export_path, interface)
    bus.export(export_path2, interface2)

    root = bus._introspect_export_path('/')
    assert len(root.nodes) == 1
