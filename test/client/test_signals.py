from dbus_next.service import ServiceInterface, signal
from dbus_next.aio import MessageBus
from dbus_next import Message

import pytest


class ExampleInterface(ServiceInterface):
    def __init__(self):
        super().__init__('test.interface')

    @signal()
    def SomeSignal(self) -> 's':
        return 'hello'

    @signal()
    def SignalMultiple(self) -> 'ss':
        return ['hello', 'world']


@pytest.mark.asyncio
async def test_signals():
    bus1 = await MessageBus().connect()
    bus2 = await MessageBus().connect()

    bus_intr = await bus1.introspect('org.freedesktop.DBus', '/org/freedesktop/DBus')
    bus_obj = bus1.get_proxy_object('org.freedesktop.DBus', '/org/freedesktop/DBus', bus_intr)
    stats = bus_obj.get_interface('org.freedesktop.DBus.Debug.Stats')

    await bus1.request_name('test.signals.name')
    service_interface = ExampleInterface()
    bus1.export('/test/path', service_interface)

    obj = bus2.get_proxy_object('test.signals.name', '/test/path',
                                bus1._introspect_export_path('/test/path'))
    interface = obj.get_interface(service_interface.name)

    async def ping():
        await bus2.call(
            Message(destination=bus1.unique_name,
                    interface='org.freedesktop.DBus.Peer',
                    path='/test/path',
                    member='Ping'))

    err = None

    single_counter = 0

    def single_handler(value):
        try:
            nonlocal single_counter
            nonlocal err
            assert value == 'hello'
            single_counter += 1
        except Exception as e:
            err = e

    multiple_counter = 0

    def multiple_handler(value1, value2):
        nonlocal multiple_counter
        nonlocal err
        try:
            assert value1 == 'hello'
            assert value2 == 'world'
            multiple_counter += 1
        except Exception as e:
            err = e

    await ping()
    match_rules = await stats.call_get_all_match_rules()
    assert bus2.unique_name in match_rules
    bus_match_rules = match_rules[bus2.unique_name]
    # the bus connection itself takes a rule on NameOwnerChange
    assert len(bus_match_rules) == 1
    assert len(bus2._user_message_handlers) == 0

    interface.on_some_signal(single_handler)
    interface.on_signal_multiple(multiple_handler)

    # Interlude: adding a signal handler with `on_[signal]` should add a match rule and
    # message handler. Removing a signal handler with `off_[signal]` should
    # remove the match rule and message handler to avoid memory leaks.
    await ping()
    match_rules = await stats.call_get_all_match_rules()
    assert bus2.unique_name in match_rules
    bus_match_rules = match_rules[bus2.unique_name]
    # test the match rule and user handler has been added
    assert len(bus_match_rules) == 2
    assert "type='signal',interface='test.interface',path='/test/path',sender='test.signals.name'" in bus_match_rules
    assert len(bus2._user_message_handlers) == 1

    service_interface.SomeSignal()
    await ping()
    assert err is None
    assert single_counter == 1

    service_interface.SignalMultiple()
    await ping()
    assert err is None
    assert multiple_counter == 1

    # special case: another bus with the same path and interface but on a
    # different name and connection will trigger the match rule of the first
    # (happens with mpris)
    bus3 = await MessageBus().connect()
    await bus3.request_name('test.signals.name2')
    service_interface2 = ExampleInterface()
    bus3.export('/test/path', service_interface2)

    obj = bus2.get_proxy_object('test.signals.name2', '/test/path',
                                bus3._introspect_export_path('/test/path'))
    # add the match rule
    obj.get_interface(service_interface2.name)
    await ping()

    # note the lack of any signal handler for this signal
    service_interface2.SomeSignal()
    await ping()
    # single_counter is not incremented for signals of the second interface
    assert single_counter == 1

    interface.off_some_signal(single_handler)
    interface.off_signal_multiple(multiple_handler)

    # After `off_[signal]`, the match rule and user handler should be removed
    await ping()
    match_rules = await stats.call_get_all_match_rules()
    assert bus2.unique_name in match_rules
    bus_match_rules = match_rules[bus2.unique_name]
    assert len(bus_match_rules) == 1
    assert "type='signal',interface='test.interface',path='/test/path',sender='test.signals.name'" not in bus_match_rules
    assert len(bus2._user_message_handlers) == 0

    bus1.disconnect()
    bus2.disconnect()
    bus3.disconnect()
