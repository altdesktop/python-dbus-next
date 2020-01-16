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


class ExpectMessage:
    def __init__(self, bus1, bus2, timeout=1):
        self.future = asyncio.get_event_loop().create_future()
        self.bus1 = bus1
        self.bus2 = bus2
        self.timeout = timeout
        self.timeout_task = None

    def message_handler(self, msg):
        self.timeout_task.cancel()
        self.bus2.remove_message_handler(self.message_handler)
        self.future.set_result(msg)
        return True

    def timeout_cb(self):
        self.bus2.remove_message_handler(self.message_handler)
        self.future.set_result(TimeoutError())

    async def __aenter__(self):
        self.bus2.add_message_handler(self.message_handler)
        self.timeout_task = asyncio.get_event_loop().call_later(self.timeout, self.timeout_cb)

        return self.future

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


def assert_signal_ok(signal, interface_name, export_path, unique_name, member, signature, body):
    assert not isinstance(signal, TimeoutError)
    assert signal.message_type == MessageType.SIGNAL
    assert signal.interface == interface_name
    assert signal.path == export_path
    assert signal.sender == unique_name
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

    async with ExpectMessage(bus1, bus2) as expected_signal:
        interface.signal_empty()
        assert_signal_ok(
            signal=await expected_signal,
            interface_name=interface.name,
            export_path=export_path,
            unique_name=bus1.unique_name,
            member='signal_empty',
            signature='',
            body=[]
        )

    async with ExpectMessage(bus1, bus2) as expected_signal:
        interface.original_name()
        assert_signal_ok(
            signal=await expected_signal,
            interface_name=interface.name,
            export_path=export_path,
            unique_name=bus1.unique_name,
            member='renamed',
            signature='',
            body=[]
        )

    async with ExpectMessage(bus1, bus2) as expected_signal:
        interface.signal_simple()
        assert_signal_ok(
            signal=await expected_signal,
            interface_name=interface.name,
            export_path=export_path,
            unique_name=bus1.unique_name,
            member='signal_simple',
            signature='s',
            body=['hello']
        )

    async with ExpectMessage(bus1, bus2) as expected_signal:
        interface.signal_multiple()
        assert_signal_ok(
            signal=await expected_signal,
            interface_name=interface.name,
            export_path=export_path,
            unique_name=bus1.unique_name,
            member='signal_multiple',
            signature='ss',
            body=['hello', 'world']
        )

    with pytest.raises(SignalDisabledError):
        interface.signal_disabled()
