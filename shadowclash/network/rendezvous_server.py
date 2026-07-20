#!/usr/bin/env python3
"""SHADOWCLASH rendezvous server: introduces two peers for UDP hole punching.

Runs standalone on a public VPS with nothing but the Python stdlib — deploy
this single file and run `python3 rendezvous_server.py`. Protocol (UDP text
datagrams, all prefixed "SHRV1"):

  client -> server
    SHRV1 HOST <local_ip:port>          register a room, get a token
    SHRV1 KEEP <token> <local_ip:port>  keep the room alive / NAT mapping open
    SHRV1 JOIN <token> <local_ip:port>  ask to be introduced to the host
    SHRV1 BYE <token>                   host cancels the room
  server -> client
    SHRV1 TOKEN <token>                          room created (reply to HOST)
    SHRV1 PEER <public_ip:port> <local_ip:port>  the other side's endpoints
    SHRV1 ERR <reason>                           e.g. unknown-token

On JOIN, both peers receive each other's public *and* private endpoints and
start firing game packets at both; whichever path gets through wins (the
private one matters when both players are behind the same NAT, where hairpin
routing often fails). The server never relays game traffic.
"""

import argparse
import secrets
import socket
import time

MAGIC = "SHRV1"
# No 0/O/1/I: tokens get read out loud between friends
TOKEN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TOKEN_LEN = 6
ROOM_TTL = 300.0  # seconds without a keepalive before a room expires


class RendezvousServer:
    def __init__(self):
        # token -> {"addr": (ip, port), "local": "ip:port", "seen": t}
        self.rooms: dict[str, dict] = {}

    def _purge(self, now: float) -> None:
        for token in [t for t, r in self.rooms.items() if now - r["seen"] > ROOM_TTL]:
            del self.rooms[token]

    def _token_for(self, addr) -> str:
        for token, room in self.rooms.items():
            if room["addr"] == addr:
                return token  # idempotent: repeated HOST keeps the same token
        while True:
            token = "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(TOKEN_LEN))
            if token not in self.rooms:
                return token

    def handle(self, data: bytes, addr: tuple, now: float) -> list[tuple[bytes, tuple]]:
        """Process one datagram; returns [(payload, destination), ...]."""
        self._purge(now)
        try:
            parts = data.decode("utf-8", errors="ignore").split()
        except Exception:
            return []
        if len(parts) < 2 or parts[0] != MAGIC:
            return []
        cmd = parts[1].upper()
        local = parts[-1] if len(parts) >= 3 and ":" in parts[-1] else ""

        if cmd == "HOST":
            token = self._token_for(addr)
            self.rooms[token] = {"addr": addr, "local": local, "seen": now}
            return [(f"{MAGIC} TOKEN {token}".encode(), addr)]

        if cmd == "KEEP" and len(parts) >= 3:
            room = self.rooms.get(parts[2].upper())
            if room is not None:
                room.update(addr=addr, seen=now)
                if local:
                    room["local"] = local
            return []

        if cmd == "BYE" and len(parts) >= 3:
            token = parts[2].upper()
            room = self.rooms.get(token)
            # Only the address that owns the room may cancel it
            if room is not None and room["addr"] == addr:
                del self.rooms[token]
            return []

        if cmd == "JOIN" and len(parts) >= 3:
            room = self.rooms.get(parts[2].upper())
            if room is None:
                return [(f"{MAGIC} ERR unknown-token".encode(), addr)]
            host_public = f"{room['addr'][0]}:{room['addr'][1]}"
            join_public = f"{addr[0]}:{addr[1]}"
            to_joiner = f"{MAGIC} PEER {host_public} {room['local']}".strip().encode()
            to_host = f"{MAGIC} PEER {join_public} {local}".strip().encode()
            return [(to_joiner, addr), (to_host, room["addr"])]

        return []


def main() -> None:
    parser = argparse.ArgumentParser(description="SHADOWCLASH rendezvous server")
    parser.add_argument("--port", type=int, default=5556)
    args = parser.parse_args()

    server = RendezvousServer()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", args.port))
    print(f"rendezvous listening on 0.0.0.0:{args.port} udp", flush=True)
    while True:
        try:
            data, addr = sock.recvfrom(512)
        except OSError:
            continue
        now = time.monotonic()
        for payload, dest in server.handle(data, addr, now):
            try:
                sock.sendto(payload, dest)
            except OSError:
                pass
        cmd = data.split(b" ")[1].decode(errors="ignore") if b" " in data else "?"
        print(f"{time.strftime('%H:%M:%S')} {addr[0]}:{addr[1]} {cmd} rooms={len(server.rooms)}", flush=True)


if __name__ == "__main__":
    main()
