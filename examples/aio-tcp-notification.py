#!/usr/bin/env python3

# In order for this to work a local tcp connection to the DBus a port
# must be opened to forward to the dbus socket file. The easiest way
# to achieve this is using "socat":
# socat TCP-LISTEN:55556,reuseaddr,fork,range=127.0.0.1/32 UNIX-CONNECT:$(echo $DBUS_SESSION_BUS_ADDRESS | sed 's/unix:path=//g')
# For actual DBus transport over network the authentication might
# be a further problem. More information here:
# https://dbus.freedesktop.org/doc/dbus-specification.html#auth-mechanisms

import sys
import os

sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))

from dbus_next.aio import MessageBus

import asyncio

loop = asyncio.get_event_loop()


async def main():
    bus = await MessageBus(bus_address="tcp:host=127.0.0.1,port=55556").connect()
    introspection = await bus.introspect('org.freedesktop.Notifications',
                                         '/org/freedesktop/Notifications')
    obj = bus.get_proxy_object('org.freedesktop.Notifications', '/org/freedesktop/Notifications',
                               introspection)
    notification = obj.get_interface('org.freedesktop.Notifications')
    await notification.call_notify("test.py", 0, "", "DBus Test", "Test notification", [""], dict(),
                                   5000)


loop.run_until_complete(main())
