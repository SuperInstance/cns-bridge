"""Tests for the background heartbeat poller."""

import time
from pathlib import Path

import pytest

from cns_bridge import FileSystemTransport, HeartbeatPoller, Intent, Packet, PacketBuilder


def _drop_inbox(transport: FileSystemTransport, packet: Packet) -> None:
    """Place a packet directly into the agent's inbox (simulating Hermes)."""
    filename = f"{packet.header.origin_id}_{packet.header.packet_id}.uscp.json"
    path = transport.inbox_path / filename
    path.write_text(packet.to_json(), encoding="utf-8")


@pytest.fixture
def transport(tmp_path: Path) -> FileSystemTransport:
    return FileSystemTransport(
        inbox_path=tmp_path / "inbox",
        outbox_path=tmp_path / "outbox",
    )


def test_poller_delivers_matching_packet(transport: FileSystemTransport) -> None:
    received = []

    poller = HeartbeatPoller(
        transport=transport,
        agent_id="lucineer",
        callback=received.append,
        interval=0.1,
    )
    poller.start()

    response = PacketBuilder(origin_id="hermes").to("lucineer").build()
    _drop_inbox(transport, response)

    time.sleep(0.35)
    poller.stop()

    assert len(received) == 1
    assert received[0].header.packet_id == response.header.packet_id


def test_poller_ignores_non_matching_packet(transport: FileSystemTransport) -> None:
    received = []

    poller = HeartbeatPoller(
        transport=transport,
        agent_id="lucineer",
        callback=received.append,
        interval=0.1,
    )
    poller.start()

    other = PacketBuilder(origin_id="hermes").to("wesley").build()
    _drop_inbox(transport, other)

    time.sleep(0.35)
    poller.stop()

    assert len(received) == 0


def test_poller_dedupes_seen_packets(transport: FileSystemTransport) -> None:
    received = []

    poller = HeartbeatPoller(
        transport=transport,
        agent_id="lucineer",
        callback=received.append,
        interval=0.1,
    )
    poller.start()

    response = PacketBuilder(origin_id="hermes").to("lucineer").build()
    _drop_inbox(transport, response)

    time.sleep(0.35)
    # Send the same file again (simulating a duplicate write).
    _drop_inbox(transport, response)

    time.sleep(0.35)
    poller.stop()

    assert len(received) == 1


def test_poller_can_filter_origin(transport: FileSystemTransport) -> None:
    received = []

    poller = HeartbeatPoller(
        transport=transport,
        agent_id="lucineer",
        callback=received.append,
        interval=0.1,
        filter_origin=True,
    )
    poller.start()

    outgoing = PacketBuilder(origin_id="lucineer").to("hermes").build()
    _drop_inbox(transport, outgoing)

    time.sleep(0.35)
    poller.stop()

    assert len(received) == 1
    assert received[0].header.origin_id == "lucineer"


def test_poller_stop_is_idempotent(transport: FileSystemTransport) -> None:
    poller = HeartbeatPoller(
        transport=transport,
        agent_id="lucineer",
        callback=lambda p: None,
        interval=0.1,
    )
    poller.start()
    assert poller.is_running()
    poller.stop()
    assert not poller.is_running()
    poller.stop()  # should not raise
