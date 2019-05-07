from dbus_next.aio import MessageBus
from dbus_next import Message, MessageType, MessageFlag

import pytest


@pytest.mark.asyncio
async def test_standard_interfaces():
    bus = await MessageBus().connect()
    msg = Message(destination='org.freedesktop.DBus',
                  path='/org/freedesktop/DBus',
                  interface='org.freedesktop.DBus',
                  member='ListNames',
                  serial=bus.next_serial())
    reply = await bus.call(msg)

    assert reply.message_type == MessageType.METHOD_RETURN
    assert reply.reply_serial == msg.serial
    assert reply.signature == 'as'
    assert bus.unique_name in reply.body[0]

    msg.interface = 'org.freedesktop.DBus.Introspectable'
    msg.member = 'Introspect'
    msg.serial = bus.next_serial()

    reply = await bus.call(msg)
    assert reply.message_type == MessageType.METHOD_RETURN
    assert reply.reply_serial == msg.serial
    assert reply.signature == 's'
    assert type(reply.body[0]) is str

    msg.member = 'MemberDoesNotExist'
    msg.serial = bus.next_serial()

    reply = await bus.call(msg)
    assert reply.message_type == MessageType.ERROR
    assert reply.reply_serial == msg.serial
    assert reply.error_name
    assert reply.signature == 's'
    assert type(reply.body[0]) is str


@pytest.mark.asyncio
async def test_sending_messages_between_buses():
    bus1 = await MessageBus().connect()
    bus2 = await MessageBus().connect()

    msg = Message(destination=bus1.unique_name,
                  path='/org/test/path',
                  interface='org.test.iface',
                  member='SomeMember',
                  serial=bus2.next_serial())

    def message_handler(sent):
        if sent.sender == bus2.unique_name and sent.serial == msg.serial:
            assert sent.path == msg.path
            assert sent.serial == msg.serial
            assert sent.interface == msg.interface
            assert sent.member == msg.member
            bus1.send(Message.new_method_return(sent, 's', ['got it']))
            bus1.remove_message_handler(message_handler)
            return True

    bus1.add_message_handler(message_handler)

    reply = await bus2.call(msg)

    assert reply.message_type == MessageType.METHOD_RETURN
    assert reply.sender == bus1.unique_name
    assert reply.signature == 's'
    assert reply.body == ['got it']
    assert reply.reply_serial == msg.serial

    def message_handler_error(sent):
        if sent.sender == bus2.unique_name and sent.serial == msg.serial:
            assert sent.path == msg.path
            assert sent.serial == msg.serial
            assert sent.interface == msg.interface
            assert sent.member == msg.member
            bus1.send(Message.new_error(sent, 'org.test.Error', 'throwing an error'))
            bus1.remove_message_handler(message_handler_error)
            return True

    bus1.add_message_handler(message_handler_error)

    msg.serial = bus2.next_serial()

    reply = await bus2.call(msg)

    assert reply.message_type == MessageType.ERROR
    assert reply.sender == bus1.unique_name
    assert reply.reply_serial == msg.serial
    assert reply.error_name == 'org.test.Error'
    assert reply.signature == 's'
    assert reply.body == ['throwing an error']

    msg.serial = bus2.next_serial()
    msg.flags = MessageFlag.NO_REPLY_EXPECTED
    reply = await bus2.call(msg)
    assert reply is None


@pytest.mark.asyncio
async def test_sending_signals_between_buses(event_loop):
    bus1 = await MessageBus().connect()
    bus2 = await MessageBus().connect()

    add_match_msg = Message(destination='org.freedesktop.DBus',
                            path='/org/freedesktop/DBus',
                            interface='org.freedesktop.DBus',
                            member='AddMatch',
                            signature='s',
                            body=[f'sender={bus2.unique_name}'])

    await bus1.call(add_match_msg)

    async def wait_for_message():
        future = event_loop.create_future()

        def message_handler(signal):
            if signal.sender == bus2.unique_name:
                bus1.remove_message_handler(message_handler)
                future.set_result(signal)

        bus1.add_message_handler(message_handler)
        return await future

    bus2.send(
        Message.new_signal('/org/test/path', 'org.test.interface', 'SomeSignal', 's', ['a signal']))

    signal = await wait_for_message()

    assert signal.message_type == MessageType.SIGNAL
    assert signal.path == '/org/test/path'
    assert signal.interface == 'org.test.interface'
    assert signal.member == 'SomeSignal'
    assert signal.signature == 's'
    assert signal.body == ['a signal']
