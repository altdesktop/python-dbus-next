The High Level Client
=====================

.. toctree::
   :maxdepth: 2

   base-proxy-object
   base-proxy-interface
   aio-proxy-object
   aio-proxy-interface
   glib-proxy-object
   glib-proxy-interface

DBus interfaces are defined with an XML-based `introspection data format <https://dbus.freedesktop.org/doc/dbus-specification.html#introspection-format>`_  which is exposed over the standard `org.freedesktop.DBus.Introspectable <https://dbus.freedesktop.org/doc/dbus-specification.html#standard-interfaces-introspectable>`_ interface. Calling the ``Introspect`` at a particular object path may return XML data similar to this:

.. code-block:: xml

    <!DOCTYPE node PUBLIC "-//freedesktop//DTD D-BUS Object Introspection 1.0//EN"
     "http://www.freedesktop.org/standards/dbus/1.0/introspect.dtd">
    <node name="/com/example/sample_object0">
      <interface name="com.example.SampleInterface0">
        <method name="Frobate">
          <arg name="foo" type="i" direction="in"/>
          <arg name="bar" type="s" direction="out"/>
          <arg name="baz" type="a{us}" direction="out"/>
        </method>
        <method name="Bazify">
          <arg name="bar" type="(iiu)" direction="in"/>
          <arg name="bar" type="v" direction="out"/>
        </method>
        <method name="Mogrify">
          <arg name="bar" type="(iiav)" direction="in"/>
        </method>
        <signal name="Changed">
          <arg name="new_value" type="b"/>
        </signal>
        <property name="Bar" type="y" access="readwrite"/>
      </interface>
      <node name="child_of_sample_object"/>
      <node name="another_child_of_sample_object"/>
   </node>

The object at this path (a ``node``) may contain interfaces and child nodes. Nodes like this are represented in the library by a :class:`ProxyObject <dbus_next.proxy_object.BaseProxyObject>`. The interfaces contained in the nodes are represented by a :class:`ProxyInterface <dbus_next.proxy_object.BaseProxyInterface>`. The proxy interface exposes the methods, signals, and properties specified by the interface definition.

The proxy object is obtained by the :class:`MessageBus <dbus_next.message_bus.BaseMessageBus>` through the :func:`get_proxy_object() <dbus_next.message_bus.BaseMessageBus.get_proxy_object>` method. This method takes the name of the client to send messages to, the path exported by that client that is expected to export the node, and the XML introspection data. If you can, it is recommended to include the XML in your project and pass it to that method as a string. But you may also use the :func:`introspect() <dbus_next.message_bus.BaseMessageBus.introspect>` method of the message bus to get this data dynamically at runtime.

Once you have a proxy object, use the :func:`get_proxy_interface() <dbus_next.proxy_object.BaseProxyObject.get_interface>` method to create an interface passing the name of the interface to get. Each message bus has its own implementation of the proxy interface which behaves slightly differently. This is an example of how to use a proxy interface for the asyncio :class:`MessageBus <dbus_next.aio.MessageBus>`.

:example:

.. code-block:: python3

    from dbus_next.aio import MessageBus
    from dbus_next import Variant

    bus = await MessageBus().connect()

    with open('introspection.xml', 'r') as f:
        introspection = f.read()

    # alternatively, get the data dynamically:
    # introspection = await bus.introspect('com.example.name',
    #                                      '/com/example/sample_object0')

    proxy_object = bus.get_proxy_object('com.example.name',
                                        '/com/example/sample_object0',
                                        introspection)

    interface = proxy_object.get_interface('com.example.SampleInterface0')

    # Use call_[METHOD] in snake case to call methods, passing the
    # in args and receiving the out args. The `baz` returned will
    # be type 'a{us}' which translates to a Python dict with `int`
    # keys and `str` values.
    baz = await interface.call_frobate(5, 'hello')

    # `bar` will be a Variant.
    bar = await interface.call_bazify([-5, 5, 5])

    await interface.call_mogrify([5, 5, [ Variant('s', 'foo') ])

    # Listen to signals by defining a callback that takes the args 
    # specified by the signal definition and registering it on the
    # interface with on_[SIGNAL] in snake case.

    def changed_notify(new_value):
        print(f'The new value is: {new_value}')

    interface.on_changed(changed_notify)

    # Use get_[PROPERTY] and set_[PROPERTY] with the property in
    # snake case to get and set the property.

    bar_value = await interface.get_bar()

    await interface.set_bar(105)

