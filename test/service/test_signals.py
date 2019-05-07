from dbus_next.service import ServiceInterface, signal, SignalDisabledError
from dbus_next.aio import MessageBus
from dbus_next import Message, MessageType

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

    async def wait_for_message():
        # TODO timeout
        future = asyncio.get_event_loop().create_future()

        def message_handler(signal):
            if signal.sender == bus1.unique_name and signal.interface == interface.name:
                bus1.remove_message_handler(message_handler)
                future.set_result(signal)

        bus2.add_message_handler(message_handler)
        return await future

    def assert_signal_ok(signal, member, signature, body):
        assert signal.message_type == MessageType.SIGNAL, signal.body[0]
        assert signal.interface == interface.name
        assert signal.path == export_path
        assert signal.sender == bus1.unique_name
        assert signal.member == member
        assert signal.signature == signature
        assert signal.body == body

    interface.signal_empty()
    signal = await wait_for_message()
    assert_signal_ok(signal, 'signal_empty', '', [])

    interface.original_name()
    signal = await wait_for_message()
    assert_signal_ok(signal, 'renamed', '', [])

    interface.signal_simple()
    signal = await wait_for_message()
    assert_signal_ok(signal, 'signal_simple', 's', ['hello'])

    interface.signal_multiple()
    signal = await wait_for_message()
    assert_signal_ok(signal, 'signal_multiple', 'ss', ['hello', 'world'])

    with pytest.raises(SignalDisabledError):
        interface.signal_disabled()
