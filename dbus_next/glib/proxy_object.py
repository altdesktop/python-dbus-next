from ..introspection import Method, Property
from ..proxy_object import BaseProxyObject, BaseProxyInterface
from ..message_bus import BaseMessageBus
from ..message import Message
from ..errors import DBusError
from ..signature import Variant
from ..constants import ErrorType
from .. import introspection as intr
import xml.etree.ElementTree as ET

from typing import Union, List

# glib is optional
try:
    from gi.repository import GLib
except ImportError:
    pass


class ProxyInterface(BaseProxyInterface):
    """A class representing a proxy to an interface exported on the bus by
    another client for the GLib :class:`MessageBus <dbus_next.glib.MessageBus>`
    implementation.

    This class is not meant to be constructed directly by the user. Use
    :func:`ProxyObject.get_interface()
    <dbus_next.glib.ProxyObject.get_interface>` on a GLib proxy
    object to get a proxy interface.

    This class exposes methods to call DBus methods, listen to signals, and get
    and set properties on the interface that are created dynamically based on
    the introspection data passed to the proxy object that made this proxy
    interface.

    A *method call* takes this form:

    .. code-block:: python3

        def callback(error: Exception, result: list(Any)):
            pass

        interface.call_[METHOD](*args, callback)
        result = interface.call_[METHOD]_sync(*args)

    Where ``METHOD`` is the name of the method converted to snake case.

    To call a method, provide ``*args`` that correspond to the *in args* of the
    introspection method definition.

    To *asynchronously* call a method, provide a callback that takes an error
    as the first argument and a list as the second argument. If the call
    completed successfully, ``error`` will be :class:`None`. If the service
    returns an error, it will be a :class:`DBusError <dbus_next.DBusError>`
    with information about the error returned from the bus. The result will be
    a list of values that correspond to the *out args* of the introspection
    method definition.

    To *synchronously* call a method, use the ``call_[METHOD]_sync()`` form.
    The ``result`` corresponds to the *out arg* of the introspection method
    definition. If the method has more than one otu arg, they are returned
    within a :class:`list`.

    To *listen to a signal* use this form:

    .. code-block:: python3

        interface.on_[SIGNAL](callback)

    To *stop listening to a signal* use this form:

    .. code-block:: python3

        interface.off_[SIGNAL](callback)

    Where ``SIGNAL`` is the name of the signal converted to snake case.

    DBus signals are exposed with an event-callback interface. The provided
    ``callback`` will be called when the signal is emitted with arguments that
    correspond to the *out args* of the interface signal definition.

    To *get or set a property* use this form:

    .. code-block:: python3

        def get_callback(error: Exception, value: Any):
            pass

        def set_callback(error: Exception)
            pass

        interface.get_[PROPERTY](get_callback)
        value: Any = interface.get_[PROPERTY]_sync()

        interface.set_[PROPERTY](set_callback)
        interface.set_[PROPERTY]_sync(value)

    Where ``PROPERTY`` is the name of the property converted to snake case.

    The ``value`` must correspond to the type of the property in the interface
    definition.

    To asynchronously get or set a property, provide a callback that takes an
    :class:`Exception` as the first argument. If the call completed
    successfully, ``error`` will be :class:`None`. If the service returns an
    error, it will be a :class:`DBusError <dbus_next.DBusError>` with
    information about the error returned from the bus.

    If the service returns an error for a synchronous DBus call, a
    :class:`DBusError <dbus_next.DBusError>` will be raised with information
    about the error.
    """
    def _call_method(self, intr_method: Method, margs, mflags=None, sync=False):
        in_len = len(intr_method.in_args)
        out_len = len(intr_method.out_args)

        def method_fn(args):
            if len(args) != in_len + 1:
                raise TypeError(
                    f'method {intr_method.name} expects {in_len} arguments and a callback (got {len(args)} args)'
                )

            args = list(args)
            # TODO type check: this callback takes two parameters
            # (MessageBus.check_callback(cb))
            callback = args.pop()

            def call_notify(msg, err):
                if err:
                    callback([], err)
                    return

                try:
                    BaseProxyInterface._check_method_return(msg, intr_method.out_signature)
                except DBusError as e:
                    err = e

                callback(msg.body, err)

            self.bus.call(
                Message(destination=self.bus_name,
                        path=self.path,
                        interface=self.introspection.name,
                        member=intr_method.name,
                        signature=intr_method.in_signature,
                        body=list(args)), call_notify)

        def method_fn_sync(args):
            main = GLib.MainLoop()
            call_error = None
            call_body = None

            def callback(body, err):
                nonlocal call_error
                nonlocal call_body
                call_error = err
                call_body = body
                main.quit()

            args += (callback, )
            method_fn(args)

            main.run()

            if call_error:
                raise call_error

            if not out_len:
                return None
            elif out_len == 1:
                return call_body[0]
            else:
                return call_body

        if sync:
            return method_fn_sync(margs)
        else:
            return method_fn(margs)

    def _get_property(self, intr_property: Property, sync=False):
        def property_getter(callback):
            def call_notify(msg, err):
                if err:
                    callback(None, err)
                    return

                try:
                    BaseProxyInterface._check_method_return(msg)
                except Exception as e:
                    callback(None, e)
                    return

                variant = msg.body[0]
                if variant.signature != intr_property.signature:
                    err = DBusError(ErrorType.CLIENT_ERROR,
                                    'property returned unexpected signature "{variant.signature}"',
                                    msg)
                    callback(None, err)
                    return

                callback(variant.value, None)

            self.bus.call(
                Message(destination=self.bus_name,
                        path=self.path,
                        interface='org.freedesktop.DBus.Properties',
                        member='Get',
                        signature='ss',
                        body=[self.introspection.name, intr_property.name]), call_notify)

        def property_getter_sync():
            property_value = None
            reply_error = None

            main = GLib.MainLoop()

            def callback(value, err):
                nonlocal property_value
                nonlocal reply_error
                property_value = value
                reply_error = err
                main.quit()

            property_getter(callback)
            main.run()
            if reply_error:
                raise reply_error
            return property_value

        if sync:
            return property_getter_sync()
        else:
            return property_getter()

    def _set_property(self, intr_property: Property, val, sync=False):
        def property_setter(value, callback):
            def call_notify(msg, err):
                if err:
                    callback(None, err)
                    return
                try:
                    BaseProxyInterface._check_method_return(msg)
                except Exception as e:
                    callback(None, e)
                    return

                return callback(None, None)

            variant = Variant(intr_property.signature, value)
            self.bus.call(
                Message(destination=self.bus_name,
                        path=self.path,
                        interface='org.freedesktop.DBus.Properties',
                        member='Set',
                        signature='ssv',
                        body=[self.introspection.name, intr_property.name, variant]), call_notify)

        def property_setter_sync(val):
            reply_error = None

            main = GLib.MainLoop()

            def callback(value, err):
                nonlocal reply_error
                reply_error = err
                main.quit()

            property_setter(val, callback)
            main.run()
            if reply_error:
                raise reply_error
            return None

        if sync:
            return property_setter_sync(val)
        else:
            return property_setter(val)


class ProxyObject(BaseProxyObject):
    """The proxy object implementation for the asyncio :class:`MessageBus <dbus_next.aio.MessageBus>`.

    For more information, see the :class:`BaseProxyObject <dbus_next.proxy_object.BaseProxyObject>`.
    """
    def __init__(self, bus_name: str, path: str, introspection: Union[intr.Node, str, ET.Element],
                 bus: BaseMessageBus):
        super().__init__(bus_name, path, introspection, bus, ProxyInterface)

    def get_interface(self, name: str) -> ProxyInterface:
        return super().get_interface(name)

    def get_children(self) -> List['ProxyObject']:
        return super().get_children()
