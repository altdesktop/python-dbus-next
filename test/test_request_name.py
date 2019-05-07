from dbus_next import aio, glib, Message, MessageType, NameFlag, RequestNameReply, ReleaseNameReply
from test.util import check_gi_repository, skip_reason_no_gi

import pytest

has_gi = check_gi_repository()


@pytest.mark.asyncio
async def test_name_requests():
    test_name = 'aio.test.request.name'

    bus1 = await aio.MessageBus().connect()
    bus2 = await aio.MessageBus().connect()

    async def get_name_owner(name):
        reply = await bus1.call(
            Message(destination='org.freedesktop.DBus',
                    path='/org/freedesktop/DBus',
                    interface='org.freedesktop.DBus',
                    member='GetNameOwner',
                    signature='s',
                    body=[name]))

        assert reply.message_type == MessageType.METHOD_RETURN
        return reply.body[0]

    reply = await bus1.request_name(test_name)
    assert reply == RequestNameReply.PRIMARY_OWNER
    reply = await bus1.request_name(test_name)
    assert reply == RequestNameReply.ALREADY_OWNER

    reply = await bus2.request_name(test_name, NameFlag.ALLOW_REPLACEMENT)
    assert reply == RequestNameReply.IN_QUEUE

    reply = await bus1.release_name(test_name)
    assert reply == ReleaseNameReply.RELEASED

    reply = await bus1.release_name('name.doesnt.exist')
    assert reply == ReleaseNameReply.NON_EXISTENT

    reply = await bus1.release_name(test_name)
    assert reply == ReleaseNameReply.NOT_OWNER

    new_owner = await get_name_owner(test_name)
    assert new_owner == bus2.unique_name

    reply = await bus1.request_name(test_name, NameFlag.DO_NOT_QUEUE)
    assert reply == RequestNameReply.EXISTS

    reply = await bus1.request_name(test_name, NameFlag.DO_NOT_QUEUE | NameFlag.REPLACE_EXISTING)
    assert reply == RequestNameReply.PRIMARY_OWNER

    bus1.disconnect()
    bus2.disconnect()


@pytest.mark.skipif(not has_gi, reason=skip_reason_no_gi)
def test_request_name_glib():
    test_name = 'glib.test.request.name'
    bus = glib.MessageBus().connect_sync()

    reply = bus.request_name_sync(test_name)
    assert reply == RequestNameReply.PRIMARY_OWNER

    reply = bus.release_name_sync(test_name)
    assert reply == ReleaseNameReply.RELEASED

    bus.disconnect()
