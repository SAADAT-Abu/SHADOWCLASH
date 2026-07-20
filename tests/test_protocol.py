import numpy as np

from shadowclash.network import protocol
from shadowclash.network.protocol import DamageEvent, Packet


def test_roundtrip_with_pose_and_events():
    pose = np.random.default_rng(7).random((protocol.NUM_LANDMARKS, 4))
    packet = Packet(
        player_id=1,
        seq=42,
        timestamp_ms=123456789,
        pose=pose,
        events=[DamageEvent(3, "head", True, 4.5), DamageEvent(4, "leg", False, 4.0)],
        name="SAADAT",
    )
    out = protocol.unpack(protocol.pack(packet))
    assert out is not None
    assert (out.player_id, out.seq, out.timestamp_ms) == (1, 42, 123456789)
    assert out.name == "SAADAT"
    assert np.allclose(out.pose, pose, atol=1e-6)  # float32 on the wire
    assert out.events == [DamageEvent(3, "head", True, 4.5), DamageEvent(4, "leg", False, 4.0)]


def test_roundtrip_without_pose():
    packet = Packet(player_id=0, seq=1, timestamp_ms=0, pose=None, events=[])
    out = protocol.unpack(protocol.pack(packet))
    assert out is not None
    assert out.pose is None
    assert out.events == []


def test_name_truncated_to_wire_limit():
    packet = Packet(0, 1, 0, None, [], name="A VERY LONG FIGHTER NAME")
    out = protocol.unpack(protocol.pack(packet))
    assert out.name == "A VERY LONG "[: protocol.NAME_LEN]
    # Empty name survives the roundtrip too
    assert protocol.unpack(protocol.pack(Packet(0, 1, 0, None, []))).name == ""


def test_rounds_roundtrip():
    out = protocol.unpack(protocol.pack(Packet(0, 1, 0, None, [], rounds=5)))
    assert out.rounds == 5
    # Unset rounds stays 0 (joiner falls back to its own config)
    assert protocol.unpack(protocol.pack(Packet(0, 1, 0, None, []))).rounds == 0


def test_rejects_garbage_and_truncated():
    assert protocol.unpack(b"nonsense") is None
    good = protocol.pack(Packet(0, 1, 0, None, [DamageEvent(1, "head", False, 5.0)]))
    assert protocol.unpack(good[:-3]) is None
    assert protocol.unpack(b"XXXX" + good[4:]) is None
