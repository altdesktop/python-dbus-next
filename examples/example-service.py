#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))

from dbus_next.service import ServiceInterface, method, signal, dbus_property
from dbus_next.aio.message_bus import MessageBus
from dbus_next.variant import Variant

import asyncio


class ExampleInterface(ServiceInterface):
    def __init__(self, name):
        super().__init__(name)
        self._string_prop = 'kevin'

    @method()
    def Echo(self, what: 's') -> 's':
        return what

    @method()
    def EchoMultiple(self, what1: 's', what2: 's') -> 'ss':
        return [what1, what2]

    @method()
    def GetVariantDict(self) -> 'a{sv}':
        return {
            'foo': Variant('s', 'bar'),
            'bat': Variant('x', -55),
            'a_list': Variant('as', ['hello', 'world'])
        }

    @dbus_property(name='StringProp')
    def string_prop(self) -> 's':
        return self._string_prop

    @string_prop.setter
    def string_prop_setter(self, val: 's'):
        self._string_prop = val

    @signal()
    def signal_simple(self) -> 's':
        return 'hello'

    @signal()
    def signal_multiple(self) -> 'ss':
        return ['hello', 'world']


async def main():
    name = 'dbus.next.example.service'
    path = '/example/path'
    interface_name = 'example.interface'

    bus = await MessageBus().connect()
    await bus.request_name(name)
    interface = ExampleInterface(interface_name)
    bus.export('/example/path', interface)
    print(f'service up on name: "{name}", path: "{path}", interface: "{interface_name}"')
    await asyncio.get_event_loop().create_future()


asyncio.get_event_loop().run_until_complete(main())
