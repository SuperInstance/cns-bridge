# CNS Bridge

A Python library that lets any agent plug into the Hermes Central Nervous
System (CNS) bus. Agents communicate through a pair of filesystem inboxes and
outboxes using the **Universal Sensory/Command Packet (USCP)** protocol.

```text
        ┌─────────────┐          outbox          ┌─────────────┐
        │   Agent A   │ ───────────────────────► │   Hermes    │
        │  (any code) │                            │    CNS      │
        └─────────────┘          inbox           └─────────────┘
                ▲ ◄────────────────────────
                │
                └ Heartbeat poller watches for responses
```

## Quick start

```python
from cns_bridge import Agent, FileSystemTransport, Intent, Priority

transport = FileSystemTransport(
    inbox_path="/tmp/hermes/inbox",
    outbox_path="/tmp/hermes/outbox",
)

agent = Agent(agent_id="my_agent", transport=transport, secret="shared-secret")

agent.send(
    intent=Intent.QUERY,
    message="Hello Hermes, what is the fleet status?",
    priority=Priority.NORMAL,
)
```

## Install

```bash
pip install /home/eileen/projects/cns-bridge
```

For development:

```bash
cd /home/eileen/projects/cns-bridge
pip install -e ".[dev]"
pytest
```

## Default paths

The default inbox and outbox point to the Windows-side Hermes directories used
by the SuperInstance stack:

- Inbox: `/mnt/c/Users/casey/.hermes/cns_inbox/`
- Outbox: `/mnt/c/Users/casey/.hermes/cns_outbox/`

These can be overridden per instance, through environment variables, or both:

```python
FileSystemTransport(
    inbox_path="/custom/inbox",
    outbox_path="/custom/outbox",
)
```

```bash
export CNS_INBOX=/custom/inbox
export CNS_OUTBOX=/custom/outbox
```

## The USCP protocol

Every message on the CNS bus is a **Universal Sensory/Command Packet**. It is a
single JSON object with three top-level keys:

```json
{
  "header": { ... },
  "body": { ... },
  "signature": { ... }
}
```

### Header

The header introduces the message.

| Field            | Type     | Description                                    |
|------------------|----------|------------------------------------------------|
| `origin_id`      | string   | Identity of the sending agent.                 |
| `packet_id`      | UUID     | Unique identifier for this packet.             |
| `intent`         | string   | Kind of message (see Intents below).           |
| `priority`       | string   | Urgency level: `low`, `normal`, `high`, `critical`. |
| `destination_id` | string   | Target agent or `"hermes"` for the CNS.        |
| `timestamp`      | ISO-8601 | UTC timestamp of creation.                     |
| `version`        | string   | USCP protocol version, currently `"1.0"`.      |
| `correlation_id` | string?  | Optional ID linking to a prior packet.         |

### Body

The body carries the need: commands, queries, sensory data, or responses.

| Field       | Type     | Description                                      |
|-------------|----------|--------------------------------------------------|
| `data`      | object   | Arbitrary structured payload.                    |
| `message`   | string   | Human-readable summary.                          |
| `mime_type` | string   | Content type, defaults to `application/json`.    |
| `encoding`  | string   | Character encoding, defaults to `utf-8`.         |
| `schema`    | string?  | Optional schema identifier for the payload.      |

### Signature

The signature records integrity metadata. The default algorithm is
**HMAC-SHA256** over a canonical JSON serialization of the header and body.

| Field       | Type    | Description                                      |
|-------------|---------|--------------------------------------------------|
| `value`     | string  | Base64-encoded HMAC digest.                      |
| `algorithm` | string  | Algorithm name, e.g. `HMAC-SHA256`.              |
| `key_id`    | string  | Identifier for the signing key.                  |
| `verified`  | bool?   | Optional verification state.                     |

### Intents

- `sense` — Report sensory data or state.
- `command` — Request an action.
- `query` — Ask a question.
- `response` — Reply to a query or command.
- `alert` — Raise an issue.
- `heartbeat` — Periodic keep-alive.
- `register` — Announce presence on the bus.
- `escalation` — Priority escalation notice.

### Priorities

Priorities are ordered:

```text
low < normal < high < critical
```

Agents and the CNS may use priority to decide routing order, retry behavior,
and alerting.

### Escalation rules

An `EscalationRule` describes when a packet should be bumped to a higher
priority because it has not received a response. For example, a `high` packet
that is unanswered for 30 seconds may be escalated to `critical`.

```python
from cns_bridge import EscalationRule, Priority, ProtocolContext

context = ProtocolContext(
    escalation_rules=[
        EscalationRule(
            min_priority=Priority.HIGH,
            no_response_seconds=30.0,
            bump_to=Priority.CRITICAL,
        )
    ]
)
```

## API overview

### `PacketBuilder`

Fluent construction of USCP packets:

```python
from cns_bridge import PacketBuilder, Intent, Priority

packet = (
    PacketBuilder(origin_id="lucineer")
    .to("hermes")
    .with_intent(Intent.QUERY)
    .with_priority(Priority.HIGH)
    .with_data(question="status")
    .with_message("Fleet status request")
    .signed_with("shared-secret", key_id="lucineer")
    .build()
)
```

### `FileSystemTransport`

Read/write packets to inbox/outbox directories:

```python
transport.send(packet)
packet = transport.receive(origin_id="hermes")
packet = transport.peek()
packets = list(transport.poll(origin_id="hermes"))
```

### `Agent`

Base class with `send`, `receive`, and `handle` methods, plus optional
background heartbeat polling:

```python
from cns_bridge import Agent

class MyAgent(Agent):
    def handle(self, packet):
        print(f"Got packet from {packet.header.origin_id}")

agent = MyAgent(agent_id="my_agent", transport=transport)
agent.start_heartbeat(interval=1.0)
```

### `HeartbeatPoller`

Background thread that watches the inbox and invokes a callback for each new
packet addressed to the agent:

```python
from cns_bridge import HeartbeatPoller

poller = HeartbeatPoller(
    transport=transport,
    agent_id="my_agent",
    callback=on_packet,
    interval=1.0,
)
poller.start()
```

## Examples

- `examples/lucineer_agent.py` — Lucineer queries Hermes and receives a response.
- `examples/wesley_agent.py` — Wesley sends night-school training results.

Run an example:

```bash
python examples/lucineer_agent.py
```

## Running tests

```bash
pytest
```

## License

MIT — see [LICENSE](LICENSE).
