# python-dbus-next

The next great DBus library for Python.

*This project is unversioned and the public api is unstable*

python-dbus-next is an upcoming Python library for DBus that aims to be a fully featured high level library primarily geared towards integration of applications into Linux desktop and mobile environments.

Desktop application developers can use this library for integrating their applications into desktop environments by implementing common DBus standard interfaces or creating custom plugin interfaces.

Desktop users can use this library to create their own scripts and utilities to interact with those interfaces for customization of their desktop environment.

python-dbus-next plans to improve over other DBus libraries for Python in the following ways:

* Zero dependencies and pure Python 3.
* Support for multiple IO backends including asyncio and the GLib main loop.
* Nonblocking IO suitable for GUI development.
* Target the latest language features of Python for beautiful services and clients.
* Complete implementation of the DBus type system without ever guessing types.
* Integration tests for all features of the library.
* (TODO) Completely documented public API.

## The Client Interface

*The client interface is unstable*

```python
from dbus_next.aio.message_bus import MessageBus

import asyncio

loop = asyncio.get_event_loop()


async def main():
    bus = await MessageBus().connect()
    # the introspection xml would normally be included in your project, but
    # this is convenient for development
    introspection = await bus.introspect('org.mpris.MediaPlayer2.vlc', '/org/mpris/MediaPlayer2')

    obj = bus.get_proxy_object('org.mpris.MediaPlayer2.vlc', '/org/mpris/MediaPlayer2', introspection)
    player = obj.get_interface('org.mpris.MediaPlayer2.Player')
    properties = obj.get_interface('org.freedesktop.DBus.Properties')

    # call methods on the interface (this causes the media player to play)
    await player.call_play()

    volume = await player.get_volume()
    print(f'current volume: {volume}, setting to 0.5')

    await player.set_volume(0.5)

    # listen to signals
    def on_properties_changed(interface_name, changed_properties, invalidated_properties):
        for changed, variant in changed_properties.items():
            print(f'property changed: {changed} - {variant.value}')

    properties.on_properties_changed(on_properties_changed)

    await loop.create_future()

loop.run_until_complete(main())
```

## The Service Interface

*The service interface is unstable*

```python
from dbus_next.service import ServiceInterface, method, dbus_property, signal
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
    def GetVariantDict() -> 'a{sv}':
        return {
            'foo': Variant('s', 'bar'),
            'bat': Variant('x', -55),
            'a_list': Variant('as', ['hello', 'world'])
        }

    @dbus_property()
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
    bus = await MessageBus().connect()
    await bus.request_name('test.name')
    interface = ExampleInterface('test.interface')
    bus.export('/test/path', interface)
    await asyncio.get_event_loop().create_future()

asyncio.get_event_loop().run_until_complete(main())
```

## The Low-Level Interface

*The low-level interface is unstable*

```python
from dbus_next.message import Message
from dbus_next.constants import MessageType
from dbus_next.aio.message_bus import MessageBus

import asyncio
import json

loop = asyncio.get_event_loop()


async def main():
    bus = await MessageBus().connect()

    reply = await bus.call(
        Message(destination='org.freedesktop.DBus',
                path='/org/freedesktop/DBus',
                interface='org.freedesktop.DBus',
                member='ListNames'))

    if reply.message_type == MessageType.ERROR:
        raise Exception(reply.body[0])

    print(json.dumps(reply.body[0], indent=2))


loop.run_until_complete(main())
```

## The Type System

Values that are sent or received over the message bus always have an associated signature that specifies the types of those values. For the high-level client and service, these signatures are specified in XML data which is advertised in a [standard DBus interface](https://dbus.freedesktop.org/doc/dbus-specification.html#introspection-format). The high-level client dynamically creates classes based on this introspection data with methods and signals with arguments based on the type signature. The high-level service does the inverse by introspecting the class to create the introspection XML data which is advertised on the bus for clients.

Each code in the signature is mapped to a Python type as shown in the table below.

| Name        | Code | Python Type | Notes                                                               |
|-------------|------|-------------|---------------------------------------------------------------------|
| BYTE        | y    | int         | An integer 0-255. In an array, it is represented by `bytes`.        |
| BOOLEAN     | b    | bool        |                                                                     |
| INT16       | n    | int         |                                                                     |
| UINT16      | q    | int         |                                                                     |
| INT32       | i    | int         |                                                                     |
| UINT32      | u    | int         |                                                                     |
| INT64       | x    | int         |                                                                     |
| UINT64      | t    | int         |                                                                     |
| DOUBLE      | d    | float       |                                                                     |
| STRING      | s    | str         |                                                                     |
| OBJECT_PATH | o    | str         | Must be a valid object path.                                        |
| SIGNATURE   | g    | str         | Must be a valid signature.                                          |
| ARRAY       | a    | list        | Must be followed by a complete type which specifies the child type. |
| STRUCT      | (    | list        | Types in the Python Array must match the types between the parens.  |
| VARIANT     | v    | Variant     | This class is provided by the library.                              |
| DICT_ENTRY  | {    | dict        | Must be included in an array type to be a dict.                     |

The types `a`, `(`, `v`, and `{` are container types that hold other values. Examples of container types and Python examples are in the table below.

| Signature | Example                                | Notes                                                                                                                                     |
|-----------|----------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| `(su)`    | `[ 'foo', 5 ]`                         | Each element in the array must match the corresponding type of the struct member.                                                         |
| `as`      | `[ 'foo', 'bar' ]`                     | The child type comes immediately after the `a`. The array can have any number of elements, but they all must match the child type.        |
| `a{su}`   | `{ 'foo': 5 }`                         | An "array of dict entries" is represented by an Object. The type after `{` is the key type and the type before the `}` is the value type. |
| `ay`      | `b'\0x62\0x75\0x66'`                   | Special case: an array of bytes is represented by Python `bytes`.                                                                         |
| `v`       | `Variant('as', ['hello'])`             | Signature must be a single type. Value may be a container type.                                                                           |
| `(asv)`   | `[ ['foo'], Variant('s', 'bar') ]`     | Containers may be nested.                                                                                                                 |

For more information on the DBus type system, see [the specification](https://dbus.freedesktop.org/doc/dbus-specification.html#type-system).

## Contributing

Contributions are welcome. Development happens on [Github](https://github.com/acrisci/python-dbus-next).

### TODO

* properties cache
* documentation

# Copyright

You can use this code under an MIT license (see LICENSE).

© 2019, Tony Crisci
