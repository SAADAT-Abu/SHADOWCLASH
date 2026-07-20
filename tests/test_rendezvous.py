from shadowclash.network.rendezvous import is_ip, parse_endpoint
from shadowclash.network.rendezvous_server import ROOM_TTL, RendezvousServer


def test_is_ip_detection():
    assert is_ip("192.168.1.42")
    assert is_ip("65.20.110.24")
    assert is_ip(" 127.0.0.1 ")
    assert not is_ip("ABC123")
    assert not is_ip("MYROOM")
    assert not is_ip("192.168.1")
    assert not is_ip("play.example.com")


def test_parse_endpoint():
    assert parse_endpoint("1.2.3.4:5555") == ("1.2.3.4", 5555)
    assert parse_endpoint("no-port") is None
    assert parse_endpoint("host:notanum") is None


def test_host_gets_token_idempotently():
    server = RendezvousServer()
    host_addr = ("9.9.9.9", 41000)
    (reply1, dest1), = server.handle(b"SHRV1 HOST 192.168.1.5:5555", host_addr, now=0.0)
    assert dest1 == host_addr
    token = reply1.decode().split()[2]
    assert len(token) == 6
    # Re-sending HOST from the same address keeps the same token
    (reply2, _), = server.handle(b"SHRV1 HOST 192.168.1.5:5555", host_addr, now=1.0)
    assert reply2 == reply1


def test_join_introduces_both_peers():
    server = RendezvousServer()
    host_addr = ("9.9.9.9", 41000)
    join_addr = ("8.8.4.4", 52000)
    (reply, _), = server.handle(b"SHRV1 HOST 192.168.1.5:5555", host_addr, now=0.0)
    token = reply.decode().split()[2]

    replies = server.handle(
        f"SHRV1 JOIN {token} 10.0.0.7:39000".encode(), join_addr, now=5.0
    )
    by_dest = {dest: payload.decode() for payload, dest in replies}
    # Joiner learns the host's public and private endpoints
    assert by_dest[join_addr] == "SHRV1 PEER 9.9.9.9:41000 192.168.1.5:5555"
    # Host learns the joiner's public and private endpoints
    assert by_dest[host_addr] == "SHRV1 PEER 8.8.4.4:52000 10.0.0.7:39000"


def test_join_unknown_token_and_expiry():
    server = RendezvousServer()
    (bad, dest), = server.handle(b"SHRV1 JOIN NOPE12 10.0.0.7:1", ("8.8.4.4", 5), now=0.0)
    assert b"ERR" in bad
    (reply, _), = server.handle(b"SHRV1 HOST 10.0.0.1:5555", ("9.9.9.9", 41000), now=0.0)
    token = reply.decode().split()[2]
    # After TTL with no keepalive the room is gone
    (expired, _), = server.handle(
        f"SHRV1 JOIN {token} 10.0.0.7:1".encode(), ("8.8.4.4", 5), now=ROOM_TTL + 1.0
    )
    assert b"ERR" in expired


def test_keepalive_extends_room():
    server = RendezvousServer()
    host_addr = ("9.9.9.9", 41000)
    (reply, _), = server.handle(b"SHRV1 HOST 10.0.0.1:5555", host_addr, now=0.0)
    token = reply.decode().split()[2]
    server.handle(f"SHRV1 KEEP {token} 10.0.0.1:5555".encode(), host_addr, now=ROOM_TTL - 1)
    replies = server.handle(
        f"SHRV1 JOIN {token} 10.0.0.7:1".encode(), ("8.8.4.4", 5), now=ROOM_TTL + 100
    )
    assert len(replies) == 2  # room still alive thanks to the keepalive


def test_bye_cancels_room():
    server = RendezvousServer()
    host_addr = ("9.9.9.9", 41000)
    (reply, _), = server.handle(b"SHRV1 HOST 10.0.0.1:5555", host_addr, now=0.0)
    token = reply.decode().split()[2]
    # A stranger cannot cancel someone else's room
    server.handle(f"SHRV1 BYE {token}".encode(), ("6.6.6.6", 1), now=1.0)
    assert token in server.rooms
    # The host can
    server.handle(f"SHRV1 BYE {token}".encode(), host_addr, now=2.0)
    (err, _), = server.handle(f"SHRV1 JOIN {token} 10.0.0.7:1".encode(), ("8.8.4.4", 5), now=3.0)
    assert b"ERR" in err


def test_garbage_is_ignored():
    server = RendezvousServer()
    assert server.handle(b"\xff\xfe garbage", ("1.1.1.1", 1), now=0.0) == []
    assert server.handle(b"SHRV1", ("1.1.1.1", 1), now=0.0) == []
    assert server.handle(b"OTHER HOST x", ("1.1.1.1", 1), now=0.0) == []