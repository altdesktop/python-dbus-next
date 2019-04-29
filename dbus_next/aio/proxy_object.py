from ..proxy_object import BaseProxyObject, BaseProxyInterface
from ..message import Message
from ..variant import Variant
from ..errors import DBusError
from ..constants import ErrorType


class ProxyInterface(BaseProxyInterface):
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


class ProxyObject(BaseProxyObject):
    def __init__(self, bus_name, path, introspection, bus):
        super().__init__(bus_name, path, introspection, bus, ProxyInterface)
