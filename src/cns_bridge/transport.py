"""Filesystem transport for the Hermes CNS bus.

Agents write packets to the CNS outbox and read responses from the CNS inbox.
The default paths point to the Windows-side Hermes directories used in the
SuperInstance stack, but they can be overridden for any host.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Iterable

from .packet import Packet


DEFAULT_INBOX = "/mnt/c/Users/casey/.hermes/cns_inbox"
DEFAULT_OUTBOX = "/mnt/c/Users/casey/.hermes/cns_outbox"

ENV_INBOX = "CNS_INBOX"
ENV_OUTBOX = "CNS_OUTBOX"


class FileSystemTransport:
    """Read and write USCP packets through a pair of filesystem directories.

    Args:
        inbox_path: Directory where the agent reads incoming packets from.
        outbox_path: Directory where the agent writes outgoing packets to.
        extension: Filename suffix used for packet files.
        create_dirs: If True, ensure inbox and outbox directories exist on
            first use.
    """

    def __init__(
        self,
        inbox_path: str | Path | None = None,
        outbox_path: str | Path | None = None,
        extension: str = ".uscp.json",
        create_dirs: bool = True,
    ) -> None:
        self.inbox_path = Path(
            inbox_path or os.environ.get(ENV_INBOX, DEFAULT_INBOX)
        )
        self.outbox_path = Path(
            outbox_path or os.environ.get(ENV_OUTBOX, DEFAULT_OUTBOX)
        )
        self.extension = extension
        self.create_dirs = create_dirs
        if create_dirs:
            self.inbox_path.mkdir(parents=True, exist_ok=True)
            self.outbox_path.mkdir(parents=True, exist_ok=True)

    def _packet_files(self, directory: Path) -> list[Path]:
        if not directory.exists():
            return []
        files = sorted(
            (p for p in directory.iterdir() if p.is_file() and p.name.endswith(self.extension)),
            key=lambda p: p.stat().st_mtime,
        )
        return files

    def send(self, packet: Packet) -> Path:
        """Serialize a packet and atomically write it to the outbox.

        Returns the path of the written file.
        """
        if self.create_dirs:
            self.outbox_path.mkdir(parents=True, exist_ok=True)

        filename = f"{packet.header.origin_id}_{packet.header.packet_id}{self.extension}"
        target = self.outbox_path / filename
        temp_fd, temp_path = tempfile.mkstemp(
            suffix=self.extension, dir=self.outbox_path, prefix=".tmp_"
        )
        try:
            with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                f.write(packet.to_json())
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, target)
        except Exception:
            try:
                os.unlink(temp_path)
            except FileNotFoundError:
                pass
            raise
        return target

    def receive(self, origin_id: str | None = None) -> Packet | None:
        """Read and remove the oldest matching packet from the inbox.

        If ``origin_id`` is given, only packets from that origin are returned.
        """
        packet_path = self._next_inbox_file(origin_id)
        if packet_path is None:
            return None
        return self._read_and_remove(packet_path)

    def peek(self, origin_id: str | None = None) -> Packet | None:
        """Return the oldest matching inbox packet without removing it."""
        packet_path = self._next_inbox_file(origin_id)
        if packet_path is None:
            return None
        return Packet.from_json(packet_path.read_text(encoding="utf-8"))

    def _next_inbox_file(self, origin_id: str | None) -> Path | None:
        for path in self._packet_files(self.inbox_path):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                # Skip corrupt or unreadable files.
                continue
            if origin_id is None:
                return path
            if data.get("header", {}).get("origin_id") == origin_id:
                return path
        return None

    def _read_and_remove(self, path: Path) -> Packet:
        text = path.read_text(encoding="utf-8")
        packet = Packet.from_json(text)
        path.unlink()
        return packet

    def list_inbox(self) -> list[Path]:
        return self._packet_files(self.inbox_path)

    def list_outbox(self) -> list[Path]:
        return self._packet_files(self.outbox_path)

    def poll(self, origin_id: str | None = None) -> Iterable[Packet]:
        """Yield every matching packet currently in the inbox, removing each."""
        for path in list(self._packet_files(self.inbox_path)):
            if origin_id is None:
                yield self._read_and_remove(path)
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("header", {}).get("origin_id") == origin_id:
                    yield self._read_and_remove(path)
            except (json.JSONDecodeError, OSError):
                continue
