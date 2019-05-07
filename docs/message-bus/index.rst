The Message Bus
===============

.. toctree::
   :maxdepth: 2

   base-message-bus.rst
   aio-message-bus.rst
   glib-message-bus.rst

The message bus manages a connection to the DBus daemon. It's capable of sending and receiving messages and wiring up the classes of the high level interfaces.

There are currently two implementations of the message bus depending on what main loop implementation you want to use. Use :class:`aio.MessageBus <dbus_next.aio.MessageBus>` if you are using an asyncio main loop. Use :class:`glib.MessageBus <dbus_next.glib.MessageBus>` if you are using a GLib main loop.

For standalone applications, the asyncio message bus is preferable because it has a nice async/await api in place of the callback/synchronous interface of the GLib message bus. If your application is using other libraries that use the GLib main loop, such as a GTK application, the GLib implementation will be needed. However neither library is a requirement.

For more information on how to use the message bus, see the documentation for the specific interfaces you plan to use.
