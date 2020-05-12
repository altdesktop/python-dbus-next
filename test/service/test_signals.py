from dbus_next.service import ServiceInterface, signal, SignalDisabledError, dbus_property
from dbus_next.aio import MessageBus
from dbus_next import Message, MessageType
from dbus_next.constants import PropertyAccess
from dbus_next.signature import Variant

import pytest
import asyncio


class ExampleInterface(ServiceInterface):
    def __init__(self, name):
        super().__init__(name)

    @signal()
    def signal_empty(self):
        assert type(self) is ExampleInterface

    @signal()
    def signal_simple(self) -> 's':
        assert type(self) is ExampleInterface
        return 'hello'

    @signal()
    def signal_multiple(self) -> 'ss':
        assert type(self) is ExampleInterface
        return ['hello', 'world']

    @signal(name='renamed')
    def original_name(self):
        assert type(self) is ExampleInterface

    @signal(disabled=True)
    def signal_disabled(self):
        assert type(self) is ExampleInterface

    @dbus_property(access=PropertyAccess.READ)
    def test_prop(self) -> 'i':
        return 42


class SecondExampleInterface(ServiceInterface):
    def __init__(self, name):
        super().__init__(name)

    @dbus_property(access=PropertyAccess.READ)
    def str_prop(self) -> 's':
        return "abc"

    @dbus_property(access=PropertyAccess.READ)
    def list_prop(self) -> 'ai':
        return [1, 2, 3]


class ExpectMessage:
    def __init__(self, bus1, bus2, interface_name, timeout=1):
        self.future = asyncio.get_event_loop().create_future()
        self.bus1 = bus1
        self.bus2 = bus2
        self.interface_name = interface_name
        self.timeout = timeout
        self.timeout_task = None

    def message_handler(self, msg):
        if msg.sender == self.bus1.unique_name and msg.interface == self.interface_name:
            self.timeout_task.cancel()
            self.future.set_result(msg)
            return True

    def timeout_cb(self):
        self.future.set_exception(TimeoutError)

    async def __aenter__(self):
        self.bus2.add_message_handler(self.message_handler)
        self.timeout_task = asyncio.get_event_loop().call_later(self.timeout, self.timeout_cb)

        return self.future

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.bus2.remove_message_handler(self.message_handler)


def assert_signal_ok(signal, export_path, member, signature, body):
    assert signal.message_type == MessageType.SIGNAL
    assert signal.path == export_path
    assert signal.member == member
    assert signal.signature == signature
    assert signal.body == body


@pytest.mark.asyncio
async def test_signals():
    bus1 = await MessageBus().connect()
    bus2 = await MessageBus().connect()

    interface = ExampleInterface('test.interface')
    export_path = '/test/path'
    bus1.export(export_path, interface)

    await bus2.call(
        Message(destination='org.freedesktop.DBus',
                path='/org/freedesktop/DBus',
                interface='org.freedesktop.DBus',
                member='AddMatch',
                signature='s',
                body=[f'sender={bus1.unique_name}']))

    async with ExpectMessage(bus1, bus2, interface.name) as expected_signal:
        interface.signal_empty()
        assert_signal_ok(signal=await expected_signal,
                         export_path=export_path,
                         member='signal_empty',
                         signature='',
                         body=[])

    async with ExpectMessage(bus1, bus2, interface.name) as expected_signal:
        interface.original_name()
        assert_signal_ok(signal=await expected_signal,
                         export_path=export_path,
                         member='renamed',
                         signature='',
                         body=[])

    async with ExpectMessage(bus1, bus2, interface.name) as expected_signal:
        interface.signal_simple()
        assert_signal_ok(signal=await expected_signal,
                         export_path=export_path,
                         member='signal_simple',
                         signature='s',
                         body=['hello'])

    async with ExpectMessage(bus1, bus2, interface.name) as expected_signal:
        interface.signal_multiple()
        assert_signal_ok(signal=await expected_signal,
                         export_path=export_path,
                         member='signal_multiple',
                         signature='ss',
                         body=['hello', 'world'])

    with pytest.raises(SignalDisabledError):
        interface.signal_disabled()


@pytest.mark.asyncio
async def test_interface_add_remove_signal():
    bus1 = await MessageBus().connect()
    bus2 = await MessageBus().connect()

    await bus2.call(
        Message(destination='org.freedesktop.DBus',
                path='/org/freedesktop/DBus',
                interface='org.freedesktop.DBus',
                member='AddMatch',
                signature='s',
                body=[f'sender={bus1.unique_name}']))

    first_interface = ExampleInterface('test.interface.first')
    second_interface = SecondExampleInterface('test.interface.second')
    export_path = '/test/path'

    # add first interface
    async with ExpectMessage(bus1, bus2, 'org.freedesktop.DBus.ObjectManager') as expected_signal:
        bus1.export(export_path, first_interface)
        assert_signal_ok(
            signal=await expected_signal,
            export_path=export_path,
            member='InterfacesAdded',
            signature='oa{sa{sv}}',
            body=[export_path, {
                'test.interface.first': {
                    'test_prop': Variant('i', 42)
                }
            }])

    # add second interface
    async with ExpectMessage(bus1, bus2, 'org.freedesktop.DBus.ObjectManager') as expected_signal:
        bus1.export(export_path, second_interface)
        assert_signal_ok(signal=await expected_signal,
                         export_path=export_path,
                         member='InterfacesAdded',
                         signature='oa{sa{sv}}',
                         body=[
                             export_path, {
                                 'test.interface.second': {
                                     'str_prop': Variant('s', "abc"),
                                     'list_prop': Variant('ai', [1, 2, 3])
                                 }
                             }
                         ])

    # remove single interface
    async with ExpectMessage(bus1, bus2, 'org.freedesktop.DBus.ObjectManager') as expected_signal:
        bus1.unexport(export_path, second_interface)
        assert_signal_ok(signal=await expected_signal,
                         export_path=export_path,
                         member='InterfacesRemoved',
                         signature='oas',
                         body=[export_path, ['test.interface.second']])

    # add second interface again
    async with ExpectMessage(bus1, bus2, 'org.freedesktop.DBus.ObjectManager') as expected_signal:
        bus1.export(export_path, second_interface)
        await expected_signal

    # remove multiple interfaces
    async with ExpectMessage(bus1, bus2, 'org.freedesktop.DBus.ObjectManager') as expected_signal:
        bus1.unexport(export_path)
        assert_signal_ok(signal=await expected_signal,
                         export_path=export_path,
                         member='InterfacesRemoved',
                         signature='oas',
                         body=[export_path, ['test.interface.first', 'test.interface.second']])
