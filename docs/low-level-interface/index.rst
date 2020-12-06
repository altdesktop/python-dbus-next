The Low Level Interface
=======================

.. toctree::
   :maxdepth: 2

   message

The low-level interface allows you to work with messages directly through the :class:`MessageBus <dbus_next.message_bus.BaseMessageBus>` with the :class:`Message <dbus_next.Message>` class. This might be useful in the following cases:

- Implementing an application that works with DBus directly like ``dbus-send(1)`` or ``dbus-monitor(1)``.
- Creating a new implementation of the :class:`BaseMessageBus <dbus_next.message_bus.BaseMessageBus>`.
- Creating clients or services that use an alternative to the standard DBus interfaces.

The primary methods and classes of the low-level interface are:

- :class:`Message <dbus_next.Message>`
- :func:`MessageBus.send() <dbus_next.message_bus.BaseMessageBus.send>`
- :func:`MessageBus.add_message_handler() <dbus_next.message_bus.BaseMessageBus.add_message_handler>`
- :func:`MessageBus.remove_message_handler() <dbus_next.message_bus.BaseMessageBus.remove_message_handler>`
- :func:`MessageBus.next_serial() <dbus_next.message_bus.BaseMessageBus.next_serial>`
- :func:`aio.MessageBus.call() <dbus_next.aio.MessageBus.call>`
- :func:`glib.MessageBus.call() <dbus_next.glib.MessageBus.call>`
- :func:`glib.MessageBus.call_sync() <dbus_next.glib.MessageBus.call_sync>`

Mixed use of the low and high level interfaces on the same bus connection is not recommended.

:example: Call a standard interface

.. code-block:: python3

    bus = await MessageBus().connect()

    msg = Message(destination='org.freedesktop.DBus',
                  path='/org/freedesktop/DBus',
                  interface='org.freedesktop.DBus',
                  member='ListNames',
                  serial=bus.next_serial())

    reply = await bus.call(msg)

    assert reply.message_type == MessageType.METHOD_RETURN

    print(reply.body[0])

:example: A custom method handler. Note that to receive these messages, you must `add a match rule <https://dbus.freedesktop.org/doc/dbus-specification.html#message-bus-routing-match-rules>`_ for the types of messages you want to receive.

.. code-block:: python3

    bus = await MessageBus().connect()

    reply = await bus.call(
        Message(destination='org.freedesktop.DBus',
                path='/org/freedesktop/DBus',
                member='AddMatch',
                signature='s',
                body=["member='MyMember', interface='com.test.interface'"]))

    assert reply.message_type == MessageType.METHOD_RETURN

    def message_handler(msg):
        if msg.interface == 'com.test.interface' and msg.member == 'MyMember':
            return Message.new_method_return(msg, 's', ['got it'])

    bus.add_message_handler(message_handler)

    await bus.wait_for_disconnect()

:example: Emit a signal

.. code-block:: python3

    bus = await MessageBus().connect()

    await bus.send(Message.new_signal('/com/test/path',
                                      'com.test.interface',
                                      'SomeSignal',
                                      's', ['a signal']))

:example: Send a file descriptor. The message format will be the same when
          received on the client side. You are responsible for closing any file
          descriptor that is sent or received by the bus. You must set the
          ``negotiate_unix_fd`` flag to ``True`` in the ``MessageBus``
          constructor to use unix file descriptors.

.. code-block:: python3

    bus = await MessageBus().connect(negotiate_unix_fd=True)

    fd = os.open('/dev/null', os.O_RDONLY)

    msg = Message(destination='org.test.destination',
                  path='/org/test/destination',
                  interface='org.test.interface',
                  member='TestMember',
                  signature='h',
                  body=[0],
                  unix_fds=[fd])

    await bus.send(msg)
