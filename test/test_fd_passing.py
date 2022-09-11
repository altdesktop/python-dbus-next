"""This tests the ability to send and receive file descriptors in dbus messages"""
from dbus_next.service import ServiceInterface, method, signal, dbus_property
from dbus_next.signature import SignatureTree, Variant
from dbus_next.aio import MessageBus
from dbus_next import Message, MessageType
import os

import pytest


def open_file():
    return os.open(os.devnull, os.O_RDONLY)


class ExampleInterface(ServiceInterface):
    def __init__(self, name):
        super().__init__(name)
        self.fds = []

    @method()
    def ReturnsFd(self) -> 'h':
        fd = open_file()
        self.fds.append(fd)
        return fd

    @method()
    def AcceptsFd(self, fd: 'h'):
        assert fd != 0
        self.fds.append(fd)

    def get_last_fd(self):
        return self.fds[-1]

    def cleanup(self):
        for fd in self.fds:
            os.close(fd)
        self.fds.clear()

    @signal()
    def SignalFd(self) -> 'h':
        fd = open_file()
        self.fds.append(fd)
        return fd

    @dbus_property()
    def PropFd(self) -> 'h':
        if not self.fds:
            fd = open_file()
            self.fds.append(fd)
        return self.fds[-1]

    @PropFd.setter
    def PropFd(self, fd: 'h'):
        assert fd
        self.fds.append(fd)


def assert_fds_equal(fd1, fd2):
    assert fd1
    assert fd2

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
async def test_high_level_service_fd_passing(event_loop):
    bus1 = await MessageBus(negotiate_unix_fd=True).connect()
    bus2 = await MessageBus(negotiate_unix_fd=True).connect()

    interface_name = 'test.interface'
    interface = ExampleInterface(interface_name)
    export_path = '/test/path'

    async def call(member, signature='', body=[], unix_fds=[], iface=interface.name):
        return await bus2.call(
            Message(destination=bus1.unique_name,
                    path=export_path,
                    interface=iface,
                    member=member,
                    signature=signature,
                    body=body,
                    unix_fds=unix_fds))

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

    # signals
    fut = event_loop.create_future()

    def fd_listener(msg):
        if msg.sender == bus1.unique_name and msg.message_type == MessageType.SIGNAL:
            fut.set_result(msg)

    reply = await bus2.call(
        Message(destination='org.freedesktop.DBus',
                path='/org/freedesktop/DBus',
                member='AddMatch',
                signature='s',
                body=[f"sender='{bus1.unique_name}'"]))
    assert reply.message_type == MessageType.METHOD_RETURN

    bus2.add_message_handler(fd_listener)
    interface.SignalFd()
    reply = await fut

    assert len(reply.unix_fds) == 1
    assert reply.body == [0]
    assert_fds_equal(reply.unix_fds[0], interface.get_last_fd())

    interface.cleanup()
    os.close(reply.unix_fds[0])

    # properties
    reply = await call('Get',
                       'ss', [interface_name, 'PropFd'],
                       iface='org.freedesktop.DBus.Properties')
    assert reply.message_type == MessageType.METHOD_RETURN, reply.body
    assert reply.body[0].signature == 'h'
    assert reply.body[0].value == 0
    assert len(reply.unix_fds) == 1
    assert_fds_equal(interface.get_last_fd(), reply.unix_fds[0])
    interface.cleanup()
    os.close(reply.unix_fds[0])

    fd = open_file()
    reply = await call('Set',
                       'ssv', [interface_name, 'PropFd', Variant('h', 0)],
                       iface='org.freedesktop.DBus.Properties',
                       unix_fds=[fd])
    assert reply.message_type == MessageType.METHOD_RETURN, reply.body
    assert_fds_equal(interface.get_last_fd(), fd)
    interface.cleanup()
    os.close(fd)

    reply = await call('GetAll', 's', [interface_name], iface='org.freedesktop.DBus.Properties')
    assert reply.message_type == MessageType.METHOD_RETURN, reply.body
    assert reply.body[0]['PropFd'].signature == 'h'
    assert reply.body[0]['PropFd'].value == 0
    assert len(reply.unix_fds) == 1
    assert_fds_equal(interface.get_last_fd(), reply.unix_fds[0])
    interface.cleanup()
    os.close(reply.unix_fds[0])

    for bus in [bus1, bus2]:
        bus.disconnect()


@pytest.mark.asyncio
async def test_sending_file_descriptor_with_proxy(event_loop):
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

    # test fds are replaced correctly in all high level interfaces
    fd = await proxy_interface.call_returns_fd()
    assert_fds_equal(interface.get_last_fd(), fd)
    interface.cleanup()
    os.close(fd)

    fd = open_file()
    await proxy_interface.call_accepts_fd(fd)
    assert_fds_equal(interface.get_last_fd(), fd)
    interface.cleanup()
    os.close(fd)

    fd = await proxy_interface.get_prop_fd()
    assert_fds_equal(interface.get_last_fd(), fd)
    interface.cleanup()
    os.close(fd)

    fd = open_file()
    await proxy_interface.set_prop_fd(fd)
    assert_fds_equal(interface.get_last_fd(), fd)
    interface.cleanup()
    os.close(fd)

    fut = event_loop.create_future()

    def on_signal_fd(fd):
        fut.set_result(fd)
        proxy_interface.off_signal_fd(on_signal_fd)

    proxy_interface.on_signal_fd(on_signal_fd)
    interface.SignalFd()
    fd = await fut
    assert_fds_equal(interface.get_last_fd(), fd)
    interface.cleanup()
    os.close(fd)


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
