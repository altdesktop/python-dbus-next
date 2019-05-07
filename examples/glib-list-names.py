#!/usr/bin/env python3
import sys
import os
sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))

from dbus_next import Message
from dbus_next.glib import MessageBus

import json
import signal
from gi.repository import GLib

main = GLib.MainLoop()
bus = MessageBus().connect_sync()


def reply_handler(reply, err):
    main.quit()

    if err:
        raise err

    print(json.dumps(reply.body[0], indent=2))


bus.call(
    Message('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'ListNames'),
    reply_handler)

signal.signal(signal.SIGINT, signal.SIG_DFL)
main.run()
