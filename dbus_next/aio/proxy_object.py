import logging

from ..proxy_object import BaseProxyObject, BaseProxyInterface
from ..message_bus import BaseMessageBus
from ..message import Message
from ..signature import Variant
from ..errors import DBusError
from ..constants import ErrorType
from .. import introspection as intr
import xml.etree.ElementTree as ET

from typing import Union, List


class ProxyInterface(BaseProxyInterface):
    """A class representing a proxy to an interface exported on the bus by
    another client for the asyncio :class:`MessageBus
    <dbus_next.aio.MessageBus>` implementation.

    This class is not meant to be constructed directly by the user. Use
    :func:`ProxyObject.get_interface()
    <dbus_next.aio.ProxyObject.get_interface>` on a asyncio proxy object to get
    a proxy interface.

    This class exposes methods to call DBus methods, listen to signals, and get
    and set properties on the interface that are created dynamically based on
    the introspection data passed to the proxy object that made this proxy
    interface.

    A *method call* takes this form:

    .. code-block:: python3

        result = await interface.call_[METHOD](*args)

    Where ``METHOD`` is the name of the method converted to snake case.

    DBus methods are exposed as coroutines that take arguments that correpond
    to the *in args* of the interface method definition and return a ``result``
    that corresponds to the *out arg*. If the method has more than one out arg,
    they are returned within a :class:`list`.

    To *listen to a signal* use this form:

    .. code-block:: python3

        interface.on_[SIGNAL](callback)

    Where ``SIGNAL`` is the name of the signal converted to snake case.

    DBus signals are exposed with an event-callback interface. The provided
    ``callback`` will be called when the signal is emitted with arguments that
    correspond to the *out args* of the interface signal definition.

    To *get or set a property* use this form:

    .. code-block:: python3

        value = await interface.get_[PROPERTY]()
        await interface.set_[PROPERTY](value)

    Where ``PROPERTY`` is the name of the property converted to snake case.

    DBus property getters and setters are exposed as coroutines. The ``value``
    must correspond to the type of the property in the interface definition.

    If the service returns an error for a DBus call, a :class:`DBusError
    <dbus_next.DBusError>` will be raised with information about the error.
    """
    def _add_method(self, intr_method):
        async def method_fn(*args):
            msg = await self.bus.call(
                Message(destination=self.bus_name,
                        path=self.path,
                        interface=self.introspection.name,
                        member=intr_method.name,
                        signature=intr_method.in_signature,
                        body=list(args)))

            BaseProxyInterface._check_method_return(msg, intr_method.out_signature)

            out_len = len(intr_method.out_args)
            if not out_len:
                return None
            elif out_len == 1:
                return msg.body[0]
            else:
                return msg.body

        method_name = f'call_{BaseProxyInterface._to_snake_case(intr_method.name)}'
        setattr(self, method_name, method_fn)

    def _add_property(self, intr_property):
        async def property_getter():
            msg = await self.bus.call(
                Message(destination=self.bus_name,
                        path=self.path,
                        interface='org.freedesktop.DBus.Properties',
                        member='Get',
                        signature='ss',
                        body=[self.introspection.name, intr_property.name]))

            BaseProxyInterface._check_method_return(msg, 'v')
            variant = msg.body[0]
            if variant.signature != intr_property.signature:
                raise DBusError(ErrorType.CLIENT_ERROR,
                                'property returned unexpected signature "{variant.signature}"', msg)
            return variant.value

        async def property_setter(val):
            variant = Variant(intr_property.signature, val)
            msg = await self.bus.call(
                Message(destination=self.bus_name,
                        path=self.path,
                        interface='org.freedesktop.DBus.Properties',
                        member='Set',
                        signature='ssv',
                        body=[self.introspection.name, intr_property.name, variant]))

            BaseProxyInterface._check_method_return(msg)

        snake_case = BaseProxyInterface._to_snake_case(intr_property.name)
        setattr(self, f'get_{snake_case}', property_getter)
        setattr(self, f'set_{snake_case}', property_setter)

    def _teardown(self):
        loop = self.bus._loop
        try:
            loop.call_soon_threadsafe(BaseProxyInterface._safe_teardown, self.bus,
                                      self._added_handler, self._match_rule)
        except RuntimeError as e:
            logging.warning(f'Runtime error while calling teardown: {e}')


class ProxyObject(BaseProxyObject):
    """The proxy object implementation for the GLib :class:`MessageBus <dbus_next.glib.MessageBus>`.

    For more information, see the :class:`BaseProxyObject <dbus_next.proxy_object.BaseProxyObject>`.
    """

    def __init__(self, bus_name: str, path: str, introspection: Union[intr.Node, str, ET.Element],
                 bus: BaseMessageBus):
        super().__init__(bus_name, path, introspection, bus, ProxyInterface)

    def get_interface(self, name: str) -> ProxyInterface:
        return super().get_interface(name)

    def get_children(self) -> List['ProxyObject']:
        return super().get_children()
