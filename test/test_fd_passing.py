"""This tests the ability to send and receive file descriptors in dbus messages"""
from dbus_next.service import ServiceInterface, method
from dbus_next.signature import SignatureTree, Variant
from dbus_next.aio import MessageBus
from dbus_next import Message, MessageFlag
import socket

import pytest


class ExampleInterface(ServiceInterface):
    def __init__(self, name):
        super().__init__(name)
        self.fd = 0

    @method()
    async def echofd(self) -> 'h':
        f = socket.socket()
        return f


@pytest.mark.asyncio
async def test_sending_file_descriptor():
    bus1 = await MessageBus().connect()
    bus2 = await MessageBus().connect()

    interface = ExampleInterface('test.interface')
    export_path = '/test/path'

    async def call(member, signature='', body=[], flags=MessageFlag.NONE):
        return await bus2.call(
            Message(destination=bus1.unique_name,
                    path=export_path,
                    interface=interface.name,
                    member=member,
                    signature=signature,
                    body=body,
                    flags=flags))

    bus1.export(export_path, interface)

    reply = await call('echofd')

    sock = socket.fromfd(reply.unix_fds[0], family=-1, type=-1)
    assert sock


@pytest.mark.asyncio
async def test_sending_file_descriptor_with_proxy():
    name = 'dbus.next.test.service'
    path = '/test/path'
    interface_name = 'test.interface'

    bus = await MessageBus().connect()
    interface = ExampleInterface(interface_name)
    bus.export(path, interface)
    await bus.request_name(name)

    intr = await bus.introspect(name, path)

    proxy = bus.get_proxy_object(name, path, intr)
    proxy_interface = proxy.get_interface(interface_name)
    reply = await proxy_interface.call_echofd()
    sock = socket.fromfd(reply, family=-1, type=-1)
    assert sock


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result, out_signature, expected",
    [
        pytest.param(5, 'h', ([0], [5]), id='Signature: "h"'),
        pytest.param([5, "foo"], 'hs', ([0, "foo"], [5]), id='Signature: "hs"'),
        pytest.param([5, 7], 'hh', ([0, 1], [5, 7]), id='Signature: "hh"'),
        pytest.param([5, 7], 'ah', ([[0, 1]], [5, 7]), id='Signature: "ah"'),
        pytest.param([9], 'ah', ([[0]], [9]), id='Signature: "ah"'),
        pytest.param([3], '(h)', ([[0]], [3]), id='Signature: "(h)"'),
        pytest.param([3, "foo"], '(hs)', ([[0, "foo"]], [3]), id='Signature: "(hs)"'),
        pytest.param([[7, "foo"], [8, "bar"]],
                     'a(hs)', ([[[0, "foo"], [1, "bar"]]], [7, 8]),
                     id='Signature: "a(hs)"'),
        pytest.param({"foo": 3}, 'a{sh}', ([{
            "foo": 0
        }], [3]), id='Signature: "a{sh}"'),
        pytest.param({
            "foo": 3,
            "bar": 6
        },
                     'a{sh}', ([{
                         "foo": 0,
                         "bar": 1
                     }], [3, 6]),
                     id='Signature: "a{sh}"'),
        pytest.param(
            {"foo": [3, 8]}, 'a{sah}', ([{
                "foo": [0, 1]
            }], [3, 8]), id='Signature: "a{sah}"'),
        pytest.param({'foo': Variant('t', 100)},
                     'a{sv}', ([{
                         'foo': Variant('t', 100)
                     }], []),
                     id='Signature: "a{sv}"'),
        pytest.param(['one', ['two', [Variant('s', 'three')]]],
                     '(s(s(v)))', ([['one', ['two', [Variant('s', 'three')]]]], []),
                     id='Signature: "(s(s(v)))"'),
        pytest.param(Variant('h', 2), 'v', ([Variant('h', 0)], [2]), id='Variant with: "h"'),
        pytest.param(Variant('(hh)', [2, 8]),
                     'v', ([Variant('(hh)', [0, 1])], [2, 8]),
                     id='Variant with: "(hh)"'),
        pytest.param(
            Variant('ah', [2, 4]), 'v', ([Variant('ah', [0, 1])], [2, 4]), id='Variant with: "ah"'),
        pytest.param(Variant('(ss)', ['hello', 'world']),
                     'v', ([Variant('(ss)', ['hello', 'world'])], []),
                     id='Variant with: "(ss)"'),
        pytest.param(Variant('v', Variant('t', 100)),
                     'v', ([Variant('v', Variant('t', 100))], []),
                     id='Variant with: "v"'),
        pytest.param([
            Variant('v', Variant('(ss)', ['hello', 'world'])), {
                'foo': Variant('t', 100)
            }, ['one', ['two', [Variant('s', 'three')]]]
        ],
                     'va{sv}(s(s(v)))', ([
                         Variant('v', Variant('(ss)', ['hello', 'world'])), {
                             'foo': Variant('t', 100)
                         }, ['one', ['two', [Variant('s', 'three')]]]
                     ], []),
                     id='Variant with: "va{sv}(s(s(v)))"'),
    ],
)
async def test_fn_result_to_body(result, out_signature, expected):
    out_signature_tree = SignatureTree(out_signature)
    assert ServiceInterface._fn_result_to_body(result, out_signature_tree) == expected
