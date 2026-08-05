"""CNS Bridge — plug any agent into the Hermes CNS bus via USCP."""

from .agent import Agent
from .heartbeat import HeartbeatPoller
from .packet import Body, Header, Packet, PacketBuilder, Signature
from .protocol import EscalationRule, Intent, Priority, ProtocolContext
from .transport import FileSystemTransport

__version__ = "0.1.0"

__all__ = [
    "Agent",
    "Body",
    "EscalationRule",
    "FileSystemTransport",
    "Header",
    "HeartbeatPoller",
    "Intent",
    "Packet",
    "PacketBuilder",
    "Priority",
    "ProtocolContext",
    "Signature",
]
