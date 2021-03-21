#!/usr/bin/env python3
import sys
import os

sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))

from dbus_next.aio import MessageBus

import asyncio

loop = asyncio.get_event_loop()


async def main():
    bus = await MessageBus().connect()
    # the introspection xml would normally be included in your project, but
    # this is convenient for development
    introspection = await bus.introspect('org.mpris.MediaPlayer2.vlc', '/org/mpris/MediaPlayer2')

    obj = bus.get_proxy_object('org.mpris.MediaPlayer2.vlc', '/org/mpris/MediaPlayer2',
                               introspection)
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

    await bus.wait_for_disconnect()


loop.run_until_complete(main())
