"""Serializes and sends the local player's landmarks + damage events."""

import socket
import time

import numpy as np

from shadowclash.network import protocol
from shadowclash.network.protocol import DamageEvent, Packet


class UdpSender:
    def __init__(self, sock: socket.socket, player_id: int, target: tuple[str, int] | None = None):
        self.sock = sock
        self.player_id = player_id
        self.target = target
        self._seq = 0
        self._event_seq = 0
        self._pending_events: list[DamageEvent] = []

    def queue_damage_event(self, zone: str, blocked: bool, damage: float) -> None:
        self._event_seq += 1
        self._pending_events.append(DamageEvent(self._event_seq, zone, blocked, damage))
        # Keep re-sending recent events for a few packets so UDP loss
        # doesn't drop damage; the peer dedupes by event_seq.
        self._pending_events = self._pending_events[-8:]

    def send(self, pose: np.ndarray | None) -> None:
        if self.target is None:
            return
        self._seq += 1
        packet = Packet(
            player_id=self.player_id,
            seq=self._seq,
            timestamp_ms=int(time.monotonic() * 1000),
            pose=pose,
            events=list(self._pending_events),
        )
        try:
            self.sock.sendto(protocol.pack(packet), self.target)
        except OSError:
            pass
