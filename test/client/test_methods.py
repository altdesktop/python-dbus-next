from dbus_next.message import MessageFlag
from dbus_next.service import ServiceInterface, method
import dbus_next.introspection as intr
from dbus_next import aio, glib, DBusError
from test.util import check_gi_repository, skip_reason_no_gi

import pytest

has_gi = check_gi_repository()


class ExampleInterface(ServiceInterface):
    def __init__(self):
        super().__init__('test.interface')

    @method()
    def Ping(self):
        pass

    @method()
    def EchoInt64(self, what: 'x') -> 'x':
        return what

    @method()
    def EchoString(self, what: 's') -> 's':
        return what

    @method()
    def ConcatStrings(self, what1: 's', what2: 's') -> 's':
        return what1 + what2

    @method()
    def EchoThree(self, what1: 's', what2: 's', what3: 's') -> 'sss':
        return [what1, what2, what3]

    @method()
    def ThrowsError(self):
        raise DBusError('test.error', 'something went wrong')


@pytest.mark.asyncio
async def test_aio_proxy_object():
    bus_name = 'aio.client.test.methods'

    bus = await aio.MessageBus().connect()
    bus2 = await aio.MessageBus().connect()
    await bus.request_name(bus_name)
    service_interface = ExampleInterface()
    bus.export('/test/path', service_interface)
    # add some more to test nodes
    bus.export('/test/path/child1', ExampleInterface())
    bus.export('/test/path/child2', ExampleInterface())

    introspection = await bus2.introspect(bus_name, '/test/path')
    assert type(introspection) is intr.Node
    obj = bus2.get_proxy_object(bus_name, '/test/path', introspection)
    interface = obj.get_interface(service_interface.name)

    children = obj.get_children()
    assert len(children) == 2
    for child in obj.get_children():
        assert type(child) is aio.ProxyObject

    result = await interface.call_ping()
    assert result is None

    result = await interface.call_echo_string('hello')
    assert result == 'hello'

    result = await interface.call_concat_strings('hello ', 'world')
    assert result == 'hello world'

    result = await interface.call_echo_three('hello', 'there', 'world')
    assert result == ['hello', 'there', 'world']

    result = await interface.call_echo_int64(-10000)
    assert result == -10000

    result = await interface.call_echo_string('no reply', flags=MessageFlag.NO_REPLY_EXPECTED)
    assert result is None

    with pytest.raises(DBusError):
        try:
            await interface.call_throws_error()
        except DBusError as e:
            assert e.reply is not None
            assert e.type == 'test.error'
            assert e.text == 'something went wrong'
            raise e

    bus.disconnect()
    bus2.disconnect()


@pytest.mark.skipif(not has_gi, reason=skip_reason_no_gi)
def test_glib_proxy_object():
    bus_name = 'glib.client.test.methods'
    bus = glib.MessageBus().connect_sync()
    bus.request_name_sync(bus_name)
    service_interface = ExampleInterface()
    bus.export('/test/path', service_interface)

    bus2 = glib.MessageBus().connect_sync()
    introspection = bus2.introspect_sync(bus_name, '/test/path')
    assert type(introspection) is intr.Node
    obj = bus.get_proxy_object(bus_name, '/test/path', introspection)
    interface = obj.get_interface(service_interface.name)

    result = interface.call_ping_sync()
    assert result is None

    result = interface.call_echo_string_sync('hello')
    assert result == 'hello'

    result = interface.call_concat_strings_sync('hello ', 'world')
    assert result == 'hello world'

    result = interface.call_echo_three_sync('hello', 'there', 'world')
    assert result == ['hello', 'there', 'world']

    with pytest.raises(DBusError):
        try:
            result = interface.call_throws_error_sync()
            assert False, result
        except DBusError as e:
            assert e.reply is not None
            assert e.type == 'test.error'
            assert e.text == 'something went wrong'
            raise e

    bus.disconnect()
    bus2.disconnect()
