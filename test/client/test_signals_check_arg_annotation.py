from dbus_next.service import ServiceInterface, signal
from dbus_next.aio import MessageBus
from dbus_next import Message
from dbus_next.introspection import Node
from dbus_next.constants import RequestNameReply
from dbus_next.error import AnnotationMismatchError

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
async def test_signals_check_arg_annotation():
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

    err_correct_annotation = None
    err_wrong_annotation = None
    err_no_annotation = None
    err_multiple_mixed_correct_annotation = None
    err_multiple_mixed_wrong_annotation = None
    
    single_counter = 0
    multiple_counter = 0

    def single_handler_correct_annotation(value: 's'):
        try:
            nonlocal single_counter
            nonlocal err_correct_annotation
            assert value == 'hello'
            single_counter += 1
        except Exception as e:
            err_correct_annotation = e

    def single_handler_wrong_annotation(value: 'b'):
        try:
            nonlocal single_counter
            nonlocal err_wrong_annotation
            assert value == 'hello'
            single_counter += 1
        except Exception as e:
            err_wrong_annotation = e

    def single_handler_no_annotation(value):
        try:
            nonlocal single_counter
            nonlocal err_no_annotation
            assert value == 'hello'
            single_counter += 1
        except Exception as e:
            err_no_annotation = e

    def multiple_handler_mixed_correct_annotation(value1:'s', value2):
        nonlocal multiple_counter
        nonlocal err_multiple_mixed_correct_annotation
        try:
            assert value1 == 'hello'
            assert value2 == 'world'
            multiple_counter += 1
        except Exception as e:
            err_multiple_mixed_correct_annotation = e

    def multiple_handler_mixed_wrong_annotation(value1:'b', value2):
        nonlocal multiple_counter
        nonlocal err_multiple_mixed_wrong_annotation
        try:
            assert value1 == 'hello'
            assert value2 == 'world'
            multiple_counter += 1
        except Exception as e:
            err_multiple_mixed_wrong_annotation = e
            
    
    await ping()

    interface.on_some_signal(single_handler_correct_annotation)
    interface.on_some_signal(single_handler_wrong_annotation)
    interface.on_some_signal(single_handler_no_annotation)
    
    interface.on_signal_multiple(multiple_handler_mixed_correct_annotation)
    interface.on_signal_multiple(multiple_handler_mixed_wrong_annotation)

    service_interface.SomeSignal()
    await ping()
    assert err_correct_annotation is None
    assert err_wrong_annotation is AnnotationMismatchError
    assert err_no_annotation is None
    assert single_counter == 3

    service_interface.SignalMultiple()
    await ping()
    assert err_multiple_mixed_correct_annotation is None
    assert err_multiple_mixed_wrong_annotation is AnnotationMismatchError
    assert multiple_counter == 2

    interface.off_some_signal(single_handler_correct_annotation)
    interface.off_some_signal(single_handler_wrong_annotation)
    interface.off_some_signal(single_handler_no_annotation)
    interface.off_signal_multiple(multiple_handler_mixed_correct_annotation)
    interface.off_signal_multiple(multiple_handler_mixed_wrong_annotation)
    
    bus1.disconnect()
    bus2.disconnect()

