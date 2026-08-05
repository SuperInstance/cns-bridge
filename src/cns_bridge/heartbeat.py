"""Background poller that watches the CNS inbox for new responses."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

from .packet import Packet
from .transport import FileSystemTransport


PacketHandler = Callable[[Packet], Any]


class HeartbeatPoller:
    """Poll the filesystem inbox and invoke a callback for new packets.

    The poller keeps track of packet IDs it has already delivered so each
    packet is only handled once. It runs in a background thread and can be
    started and stopped cleanly.

    Args:
        transport: FileSystemTransport instance to poll.
        agent_id: Only packets addressed to this agent (or originating from
            it, depending on filter) are delivered.
        callback: Function called with each new Packet.
        interval: Seconds between polls.
        filter_origin: If True, deliver packets whose ``origin_id`` matches
            ``agent_id``. If False, deliver packets whose ``destination_id``
            matches ``agent_id``.
    """

    def __init__(
        self,
        transport: FileSystemTransport,
        agent_id: str,
        callback: PacketHandler,
        interval: float = 1.0,
        filter_origin: bool = False,
    ) -> None:
        self.transport = transport
        self.agent_id = agent_id
        self.callback = callback
        self.interval = interval
        self.filter_origin = filter_origin
        self._seen: set[str] = set()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    def _match(self, packet: Packet) -> bool:
        if self.filter_origin:
            return packet.header.origin_id == self.agent_id
        return packet.header.destination_id == self.agent_id

    def _poll_once(self) -> None:
        for packet in list(self.transport.poll()):
            if not self._match(packet):
                continue
            pid = packet.header.packet_id
            with self._lock:
                if pid in self._seen:
                    continue
                self._seen.add(pid)
            try:
                self.callback(packet)
            except Exception:
                # A handler must not crash the poller. The packet ID stays in
                # _seen so a buggy handler is not retried endlessly.
                continue

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except Exception:
                # Transport errors should not terminate the background thread;
                # the next poll will retry.
                pass
            self._stop_event.wait(self.interval)

    def start(self) -> "HeartbeatPoller":
        """Start the background polling thread."""
        if self._thread is not None and self._thread.is_alive():
            return self
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def stop(self, timeout: float | None = None) -> None:
        """Signal the poller to stop and wait for the thread to finish."""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout)
        self._thread = None

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def reset_seen(self) -> None:
        """Clear the set of delivered packet IDs."""
        with self._lock:
            self._seen.clear()
