"""Receives peer landmark packets on a background thread.

Drops out-of-order packets (seq filtering, D-006), dedupes damage events by
event_seq (D-004), tracks the peer address (host learns it from the first
packet) and the last receive time for the lag indicator.
"""

import socket
import threading
import time

import numpy as np

from shadowclash.network import protocol
from shadowclash.network.protocol import DamageEvent
from shadowclash.utils.logger import get_logger

log = get_logger(__name__)


class UdpReceiver:
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self._lock = threading.Lock()
        self._latest_pose: np.ndarray | None = None
        self._last_seq = 0
        self._applied_event_seq = 0
        self._new_events: list[DamageEvent] = []
        self.peer_addr: tuple[str, int] | None = None
        self.peer_name: str = ""
        self.peer_rounds: int = 0  # host's best-of-N, 0 until first packet
        self.last_rx_time: float = 0.0
        # Rendezvous replies (SHRV1 datagrams share the game socket)
        self.rdv_token: str | None = None
        self.rdv_peers: list[tuple[str, int]] = []
        self.rdv_error: str | None = None
        self.rdv_relay_ok = False
        # Datagrams that looked like ours but did not parse: almost always a
        # peer running a different build, which is otherwise invisible.
        self.bad_packets = 0
        self._warned_bad = False
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True
        self.sock.settimeout(0.25)
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)

    def get_pose(self) -> tuple[np.ndarray | None, float]:
        with self._lock:
            pose = None if self._latest_pose is None else self._latest_pose.copy()
            return pose, self.last_rx_time

    def drain_events(self) -> list[DamageEvent]:
        """New damage events since the last call, in order, deduplicated."""
        with self._lock:
            events, self._new_events = self._new_events, []
            return events

    def _handle_rendezvous(self, data: bytes) -> None:
        from shadowclash.network.rendezvous import parse_endpoint

        parts = data.decode("utf-8", errors="ignore").split()
        if len(parts) < 2:
            return
        with self._lock:
            if parts[1] == "TOKEN" and len(parts) >= 3:
                self.rdv_token = parts[2]
            elif parts[1] == "PEER":
                peers = [ep for ep in map(parse_endpoint, parts[2:]) if ep is not None]
                if peers:
                    self.rdv_peers = peers
            elif parts[1] == "RELAY":
                self.rdv_relay_ok = True
            elif parts[1] == "ERR":
                self.rdv_error = " ".join(parts[2:]) or "error"

    def _recv_loop(self) -> None:
        while self._running:
            try:
                data, addr = self.sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if data.startswith(b"SHRV1 "):
                self._handle_rendezvous(data)
                continue
            packet = protocol.unpack(data)
            if packet is None:
                with self._lock:
                    self.bad_packets += 1
                    warn = self.bad_packets == 10 and not self._warned_bad
                    self._warned_bad = self._warned_bad or warn
                if warn:
                    log.warning(
                        "Unreadable packets from %s: the other player is almost "
                        "certainly running a different SHADOWCLASH version",
                        addr,
                    )
                continue
            with self._lock:
                self.peer_addr = addr
                if packet.name:
                    self.peer_name = packet.name
                if packet.rounds:
                    self.peer_rounds = packet.rounds
                self.last_rx_time = time.monotonic()
                if packet.seq <= self._last_seq:
                    continue  # stale or duplicate datagram
                self._last_seq = packet.seq
                if packet.pose is not None:
                    self._latest_pose = packet.pose
                for ev in sorted(packet.events, key=lambda e: e.event_seq):
                    if ev.event_seq > self._applied_event_seq:
                        self._applied_event_seq = ev.event_seq
                        self._new_events.append(ev)
