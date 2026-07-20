"""Client side of the rendezvous protocol (see rendezvous_server.py).

The client speaks over the *game's* UDP socket — that is essential: the NAT
mapping the server observes must be the same one the peer's game packets
will punch through. Replies are parsed by UdpReceiver (SHRV1-prefixed
datagrams never collide with game packets, whose magic is SHCL) and exposed
as rdv_* fields; this class just does the periodic sending.
"""

import re
import socket
import time

MAGIC = b"SHRV1"

_IP_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def is_ip(text: str) -> bool:
    """True if the join target looks like an IPv4 address, else it's a token."""
    return bool(_IP_RE.match(text.strip()))


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def parse_endpoint(text: str) -> tuple[str, int] | None:
    host, sep, port = text.rpartition(":")
    if not sep:
        return None
    try:
        return (host, int(port))
    except ValueError:
        return None


class RendezvousClient:
    """Drives HOST/KEEP or JOIN sends until the receiver reports peers."""

    def __init__(self, sock: socket.socket, receiver, server_addr: tuple[str, int]):
        self.sock = sock
        self.receiver = receiver
        self.server_addr = server_addr
        self._mode: str | None = None
        self._join_token = ""
        self._last_send = 0.0
        self._local = f"{local_ip()}:{sock.getsockname()[1]}"

    def start_host(self) -> None:
        self._mode = "host"

    def start_join(self, token: str) -> None:
        self._mode = "join"
        self._join_token = token.strip().upper()

    @property
    def token(self) -> str | None:
        return self.receiver.rdv_token

    @property
    def peers(self) -> list[tuple[str, int]]:
        return self.receiver.rdv_peers

    @property
    def error(self) -> str | None:
        return self.receiver.rdv_error

    def _send(self, text: str) -> None:
        try:
            self.sock.sendto(f"{MAGIC.decode()} {text}".encode(), self.server_addr)
        except OSError:
            pass

    def close(self) -> None:
        """Cancel the room server-side so the token dies with the host."""
        if self._mode == "host" and self.token:
            self._send(f"BYE {self.token}")

    def update(self, now: float | None = None) -> None:
        """Call every frame; sends at most one datagram per interval."""
        if self._mode is None or self.peers:
            return
        now = time.monotonic() if now is None else now
        if self._mode == "host":
            if self.token is None:
                if now - self._last_send >= 1.0:
                    self._send(f"HOST {self._local}")
                    self._last_send = now
            elif now - self._last_send >= 10.0:
                self._send(f"KEEP {self.token} {self._local}")
                self._last_send = now
        elif self._mode == "join" and self.error is None:
            if now - self._last_send >= 1.0:
                self._send(f"JOIN {self._join_token} {self._local}")
                self._last_send = now
