"""Rendezvous server: room lifecycle and the relay fallback (D-020)."""

from shadowclash.network.rendezvous_server import (
    RELAY_TTL,
    ROOM_TTL,
    RendezvousServer,
)

HOST_ADDR = ("203.0.113.10", 41000)
JOIN_ADDR = ("203.0.113.20", 52000)
GAME = b"SHCL\x04\x00\x03payload"


def make_room(server, now=0.0):
    replies = server.handle(b"SHRV1 HOST 10.0.0.5:5555", HOST_ADDR, now)
    return replies[0][0].decode().split()[2]


def test_host_gets_token_and_join_introduces_both_sides():
    server = RendezvousServer()
    token = make_room(server)
    replies = server.handle(f"SHRV1 JOIN {token} 172.16.0.9:5555".encode(), JOIN_ADDR, 1.0)
    dests = {dest for _, dest in replies}
    assert dests == {HOST_ADDR, JOIN_ADDR}
    to_joiner = next(p for p, d in replies if d == JOIN_ADDR).decode()
    assert "203.0.113.10:41000" in to_joiner  # host's public endpoint
    assert "10.0.0.5:5555" in to_joiner  # host's private endpoint


def test_relay_forwards_game_packets_once_both_sides_registered():
    server = RendezvousServer()
    token = make_room(server)

    # Only one side registered: nothing to forward to yet
    server.handle(f"SHRV1 RLY {token} host 10.0.0.5:5555".encode(), HOST_ADDR, 1.0)
    assert server.handle(GAME, HOST_ADDR, 1.1) == []

    reply = server.handle(f"SHRV1 RLY {token} join 172.16.0.9:5555".encode(), JOIN_ADDR, 2.0)
    assert reply[0][0] == f"SHRV1 RELAY {token}".encode()

    assert server.handle(GAME, HOST_ADDR, 2.1) == [(GAME, JOIN_ADDR)]
    assert server.handle(GAME, JOIN_ADDR, 2.2) == [(GAME, HOST_ADDR)]
    assert server.relayed == 2


def test_relay_rejects_unknown_token_and_ignores_strangers():
    server = RendezvousServer()
    reply = server.handle(b"SHRV1 RLY ZZZZZZ host 10.0.0.5:5555", HOST_ADDR, 0.0)
    assert b"ERR unknown-token" in reply[0][0]
    # A game packet from an address in no relay pair is dropped, not echoed
    assert server.handle(GAME, ("198.51.100.7", 9999), 0.1) == []


def test_nat_rebind_replaces_the_stale_endpoint():
    server = RendezvousServer()
    token = make_room(server)
    server.handle(f"SHRV1 RLY {token} host 10.0.0.5:5555".encode(), HOST_ADDR, 1.0)
    server.handle(f"SHRV1 RLY {token} join 172.16.0.9:5555".encode(), JOIN_ADDR, 1.0)

    rebound = (JOIN_ADDR[0], 52999)
    server.handle(f"SHRV1 RLY {token} join 172.16.0.9:5555".encode(), rebound, 2.0)

    assert server.handle(GAME, HOST_ADDR, 2.1) == [(GAME, rebound)]
    assert server.handle(GAME, JOIN_ADDR, 2.2) == []  # dead mapping, unrouted


def test_relay_traffic_keeps_the_room_alive_past_its_ttl():
    server = RendezvousServer()
    token = make_room(server)
    server.handle(f"SHRV1 RLY {token} host 10.0.0.5:5555".encode(), HOST_ADDR, 1.0)
    server.handle(f"SHRV1 RLY {token} join 172.16.0.9:5555".encode(), JOIN_ADDR, 1.0)

    # A long match with no HOST/KEEP, only RLY keepalives
    for t in range(2, int(ROOM_TTL) + 120, 2):
        server.handle(f"SHRV1 RLY {token} host 10.0.0.5:5555".encode(), HOST_ADDR, float(t))
    assert token in server.rooms
    assert server.handle(GAME, JOIN_ADDR, float(t)) == [(GAME, HOST_ADDR)]


def test_idle_relay_and_room_expire():
    server = RendezvousServer()
    token = make_room(server)
    server.handle(f"SHRV1 RLY {token} host 10.0.0.5:5555".encode(), HOST_ADDR, 1.0)
    server.handle(f"SHRV1 RLY {token} join 172.16.0.9:5555".encode(), JOIN_ADDR, 1.0)

    # Any SHRV1 datagram triggers the purge sweep
    server.handle(b"SHRV1 HOST 10.0.0.9:5555", ("198.51.100.1", 1), 1.0 + RELAY_TTL + 1)
    assert server.relays == {} and server.routes == {}
    assert server.handle(GAME, HOST_ADDR, 1.0 + RELAY_TTL + 2) == []


def test_bye_tears_down_the_relay():
    server = RendezvousServer()
    token = make_room(server)
    server.handle(f"SHRV1 RLY {token} host 10.0.0.5:5555".encode(), HOST_ADDR, 1.0)
    server.handle(f"SHRV1 RLY {token} join 172.16.0.9:5555".encode(), JOIN_ADDR, 1.0)

    server.handle(f"SHRV1 BYE {token}".encode(), JOIN_ADDR, 2.0)  # not the owner
    assert server.handle(GAME, HOST_ADDR, 2.1) == [(GAME, JOIN_ADDR)]

    server.handle(f"SHRV1 BYE {token}".encode(), HOST_ADDR, 3.0)
    assert server.rooms == {} and server.routes == {}
    assert server.handle(GAME, HOST_ADDR, 3.1) == []
