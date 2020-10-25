"""This tests the ability to send and receive file descriptors in dbus messages"""
from dbus_next.service import ServiceInterface, method
from dbus_next.signature import SignatureTree, Variant
from dbus_next.aio import MessageBus
from dbus_next import Message, MessageFlag, MessageType
import os

import pytest


def open_file():
    return os.open(os.devnull, os.O_RDONLY)


class ExampleInterface(ServiceInterface):
    def __init__(self, name):
        super().__init__(name)
        self.fds = []
        self.files = []

    @method()
    async def ReturnsFd(self) -> 'h':
        fd = open_file()
        self.fds.append(fd)
        return fd

    @method()
    async def AcceptsFd(self, fd: 'h'):
        assert fd != 0
        self.fds.append(fd)

    def get_last_fd(self):
        return self.fds[-1]

    def cleanup(self):
        for fd in self.fds:
            os.close(fd)
        self.fds.clear()


def assert_fds_equal(fd1, fd2):
    stat1 = os.fstat(fd1)
    stat2 = os.fstat(fd2)

    assert stat1.st_dev == stat2.st_dev
    assert stat1.st_ino == stat2.st_ino
    assert stat1.st_rdev == stat2.st_rdev


@pytest.mark.asyncio
async def test_sending_file_descriptor_low_level():
    bus1 = await MessageBus(negotiate_unix_fd=True).connect()
    bus2 = await MessageBus(negotiate_unix_fd=True).connect()

    fd_before = open_file()
    fd_after = None

    msg = Message(destination=bus1.unique_name,
                  path='/org/test/path',
                  interface='org.test.iface',
                  member='SomeMember',
                  body=[0],
                  signature='h',
                  unix_fds=[fd_before])

    def message_handler(sent):
        nonlocal fd_after
        if sent.sender == bus2.unique_name and sent.serial == msg.serial:
            assert sent.path == msg.path
            assert sent.serial == msg.serial
            assert sent.interface == msg.interface
            assert sent.member == msg.member
            assert sent.body == [0]
            assert len(sent.unix_fds) == 1
            fd_after = sent.unix_fds[0]
            bus1.send(Message.new_method_return(sent, 's', ['got it']))
            bus1.remove_message_handler(message_handler)
            return True

    bus1.add_message_handler(message_handler)

    reply = await bus2.call(msg)
    assert reply.body == ['got it']
    assert fd_after is not None

    assert_fds_equal(fd_before, fd_after)

    for fd in [fd_before, fd_after]:
        os.close(fd)
    for bus in [bus1, bus2]:
        bus.disconnect()


@pytest.mark.asyncio
async def test_high_level_service_fd_passing():
    bus1 = await MessageBus(negotiate_unix_fd=True).connect()
    bus2 = await MessageBus(negotiate_unix_fd=True).connect()
    print(bus2.unique_name)

    interface = ExampleInterface('test.interface')
    export_path = '/test/path'

    async def call(member, signature='', body=[], unix_fds=[], flags=MessageFlag.NONE):
        return await bus2.call(
            Message(destination=bus1.unique_name,
                    path=export_path,
                    interface=interface.name,
                    member=member,
                    signature=signature,
                    body=body,
                    unix_fds=unix_fds,
                    flags=flags))

    bus1.export(export_path, interface)

    # test that an fd can be returned by the service
    reply = await call('ReturnsFd')
    assert reply.message_type == MessageType.METHOD_RETURN, reply.body
    assert reply.signature == 'h'
    assert len(reply.unix_fds) == 1
    assert_fds_equal(interface.get_last_fd(), reply.unix_fds[0])
    interface.cleanup()
    os.close(reply.unix_fds[0])

    # test that an fd can be sent to the service
    fd = open_file()
    reply = await call('AcceptsFd', signature='h', body=[0], unix_fds=[fd])
    assert reply.message_type == MessageType.METHOD_RETURN, reply.body
    assert_fds_equal(interface.get_last_fd(), fd)

    interface.cleanup()
    os.close(fd)

    for bus in [bus1, bus2]:
        bus.disconnect()


@pytest.mark.asyncio
@pytest.mark.skip
async def test_sending_file_descriptor_with_proxy():
    name = 'dbus.next.test.service'
    path = '/test/path'
    interface_name = 'test.interface'

    bus = await MessageBus(negotiate_unix_fd=True).connect()
    interface = ExampleInterface(interface_name)
    bus.export(path, interface)
    await bus.request_name(name)

    intr = await bus.introspect(name, path)

    proxy = bus.get_proxy_object(name, path, intr)
    proxy_interface = proxy.get_interface(interface_name)
    await proxy_interface.call_returns_fd()


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
