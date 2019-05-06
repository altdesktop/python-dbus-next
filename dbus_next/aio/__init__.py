from .message_bus import MessageBus
from .proxy_object import ProxyObject, ProxyInterface
from ..constants import BusType


async def session_bus(bus_address=None):
    return await MessageBus(bus_address=bus_address, bus_type=BusType.SESSION).connect()


async def system_bus(bus_address=None):
    return await MessageBus(bus_address=bus_address, bus_type=BusType.SYSTEM).connect()
