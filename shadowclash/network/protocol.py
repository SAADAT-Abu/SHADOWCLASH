"""Binary UDP packet format (struct-packed, see DECISIONS.md D-004/D-006).

Layout (network byte order):
  header:  4s magic 'SHCL' | B version | B player_id | B rounds (host's
           best-of-N setting, 0 = unset) | 12s player name (utf-8,
           null-padded) | I packet seq | Q timestamp ms
  pose:    B has_pose | 75 * 4 float32 (x, y, z, visibility), zeros if no pose
           (75 = 33 pose + 2x21 Holistic hand landmarks, D-011)
  events:  B count | count * (I event_seq | B zone_id | B blocked | f damage)

Damage events piggyback on the landmark stream: each client is authoritative
for damage its local player deals, and the peer applies received events
idempotently by event_seq.
"""

import struct
from dataclasses import dataclass

import numpy as np

from shadowclash.skeleton.skeleton_model import TOTAL_LANDMARKS

MAGIC = b"SHCL"
VERSION = 4  # v4: rounds byte; v3: player name; v2: 75 landmarks (D-011)
NUM_LANDMARKS = TOTAL_LANDMARKS
NAME_LEN = 12

_HEADER = struct.Struct(f"!4sBBB{NAME_LEN}sIQ")
_POSE = struct.Struct(f"!B{NUM_LANDMARKS * 4}f")
_EVENT_COUNT = struct.Struct("!B")
_EVENT = struct.Struct("!IBBf")

ZONE_IDS = {"head": 0, "torso": 1, "leg": 2}
ZONE_NAMES = {v: k for k, v in ZONE_IDS.items()}


@dataclass
class DamageEvent:
    event_seq: int
    zone: str
    blocked: bool
    damage: float


@dataclass
class Packet:
    player_id: int
    seq: int
    timestamp_ms: int
    pose: np.ndarray | None  # (NUM_LANDMARKS, 4) or None
    events: list[DamageEvent]
    name: str = ""
    rounds: int = 0  # host's best-of-N setting; joiner adopts it


def pack(packet: Packet) -> bytes:
    name_bytes = packet.name.encode("utf-8")[:NAME_LEN].ljust(NAME_LEN, b"\0")
    out = _HEADER.pack(
        MAGIC, VERSION, packet.player_id, packet.rounds, name_bytes,
        packet.seq, packet.timestamp_ms,
    )
    if packet.pose is not None:
        flat = np.asarray(packet.pose, dtype=np.float32).reshape(-1)
        out += _POSE.pack(1, *flat)
    else:
        out += _POSE.pack(0, *([0.0] * (NUM_LANDMARKS * 4)))
    out += _EVENT_COUNT.pack(len(packet.events))
    for ev in packet.events:
        out += _EVENT.pack(ev.event_seq, ZONE_IDS[ev.zone], int(ev.blocked), ev.damage)
    return out


def unpack(data: bytes) -> Packet | None:
    """Parse a datagram; returns None for anything malformed or foreign."""
    if len(data) < _HEADER.size + _POSE.size + _EVENT_COUNT.size:
        return None
    magic, version, player_id, rounds, name_bytes, seq, ts = _HEADER.unpack_from(data, 0)
    if magic != MAGIC or version != VERSION:
        return None
    name = name_bytes.rstrip(b"\0").decode("utf-8", errors="ignore")
    offset = _HEADER.size
    pose_fields = _POSE.unpack_from(data, offset)
    offset += _POSE.size
    pose = None
    if pose_fields[0]:
        pose = np.array(pose_fields[1:], dtype=np.float64).reshape(NUM_LANDMARKS, 4)
    (count,) = _EVENT_COUNT.unpack_from(data, offset)
    offset += _EVENT_COUNT.size
    events = []
    for _ in range(count):
        if offset + _EVENT.size > len(data):
            return None
        ev_seq, zone_id, blocked, damage = _EVENT.unpack_from(data, offset)
        offset += _EVENT.size
        if zone_id not in ZONE_NAMES:
            return None
        events.append(DamageEvent(ev_seq, ZONE_NAMES[zone_id], bool(blocked), damage))
    return Packet(player_id, seq, ts, pose, events, name, rounds)
