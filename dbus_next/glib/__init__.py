from .message_bus import MessageBus
from .proxy_object import ProxyObject, ProxyInterface
from ..constants import BusType


def session_bus(bus_address=None, connect_notify=None):
    bus = MessageBus(bus_address=bus_address, bus_type=BusType.SESSION)
    bus.connect(connect_notify)
    return bus


def session_bus_sync(bus_address=None):
    return MessageBus(bus_address=bus_address, bus_type=BusType.SESSION).connect_sync()


def system_bus(bus_address=None, connect_notify=None):
    bus = MessageBus(bus_address=bus_address, bus_type=BusType.SYSTEM)
    bus.connect(connect_notify)
    return bus


def system_bus_sync(bus_address=None):
    return MessageBus(bus_address=bus_address, bus_type=BusType.SYSTEM).connect_sync()
