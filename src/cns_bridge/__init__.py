"""CNS Bridge — plug any agent into the Hermes CNS bus via USCP."""

from .agent import Agent
from .bus_space import BusSpace, Ring
from .compaction_guardian import (
    CaptureRecord,
    CompactionGuardian,
    CompactionState,
    extract_recent_insights,
)
from .heartbeat import HeartbeatPoller
from .log_graph import ConsequenceEdge, DecisionNode, LedgerGraph
from .packet import Body, Header, Packet, PacketBuilder, Signature
from .protocol import EscalationRule, Intent, Priority, ProtocolContext
from .token_estimator import (
    HealthLevel,
    TokenEstimate,
    context_health,
    context_pressure,
    estimate_messages,
    estimate_tokens,
    estimate_tokens_detailed,
    format_health,
    should_trigger_creative_break,
    tokens_remaining,
)
from .transport import FileSystemTransport

__version__ = "0.2.0"

__all__ = [
    "Agent",
    "Body",
    "BusSpace",
    "CaptureRecord",
    "CompactionGuardian",
    "CompactionState",
    "ConsequenceEdge",
    "DecisionNode",
    "EscalationRule",
    "FileSystemTransport",
    "HealthLevel",
    "Header",
    "HeartbeatPoller",
    "Intent",
    "LedgerGraph",
    "Packet",
    "PacketBuilder",
    "Priority",
    "ProtocolContext",
    "Ring",
    "Signature",
    "TokenEstimate",
    "context_health",
    "context_pressure",
    "estimate_messages",
    "estimate_tokens",
    "estimate_tokens_detailed",
    "extract_recent_insights",
    "format_health",
    "should_trigger_creative_break",
    "tokens_remaining",
]
