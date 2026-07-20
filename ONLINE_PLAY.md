# ONLINE_PLAY.md — Strategies for connecting players across networks

The v1 design is LAN-only peer-to-peer UDP. These are the realistic paths to
internet play, ordered by effort. The core obstacle is NAT: both players are
behind home routers, so neither can receive unsolicited UDP packets.

## Option 1 — VPN overlay (Tailscale / ZeroTier) — zero code changes ⭐ short-term pick
Both players install [Tailscale](https://tailscale.com) (or ZeroTier) and log
into a shared network. Each machine gets a stable virtual IP (e.g.
`100.x.y.z`) that works from anywhere; the existing Host/Join flow is used
unchanged with that IP. Tailscale does its own NAT traversal (direct WireGuard
tunnel when possible, DERP relay as fallback).

- **Effort:** none in our code; players install an app once.
- **Latency:** near-direct when hole punching succeeds (typical), relayed otherwise.
- **Verdict:** the right first step — lets remote friends play *today*. Just
  document it in the README/help screen.

## Option 2 — Port forwarding on the host's router — zero code changes
Host forwards UDP 5555 to their PC and shares their public IP. Works with the
current code because the join side sends first and the host replies to the
observed source address (our host already learns the peer from the first
packet, and the joiner's NAT allows the reply because it initiated).

- **Effort:** none in code; per-player router fiddling, breaks with CGNAT.
- **Verdict:** viable fallback, poor UX. Document, don't build on it.

## Option 3 — Rendezvous server + UDP hole punching — the proper v2 feature
A tiny public "matchmaker" on a cheap VPS (~50 lines of Python, UDP):

1. Host sends `REGISTER <room-code>` to the server; server records the host's
   *public* `ip:port` as seen from outside (that's the key trick — the NAT
   mapping is created by the outbound packet).
2. Joiner sends `JOIN <room-code>`; the server sends each peer the other's
   public endpoint.
3. Both peers start firing UDP packets at each other's public endpoint. Each
   side's outbound packets open its own NAT mapping, so the streams "punch
   through" and meet in the middle. After the first packets cross, the server
   is out of the loop — pure P2P, same latency as a direct connection.

Works through the common NAT types (full-cone, restricted, port-restricted).
Fails on *symmetric* NATs (some mobile carriers, CGNAT) — those need Option 4.

- **Effort:** ~a day: small server script + a `--room CODE` join flow +
  keepalive packets (NAT mappings expire in ~30s of silence; our 30Hz stream
  more than covers it).
- **Cost:** one $3-5/mo VPS handles thousands of matches (it only brokers
  introductions).

## Option 4 — Relay server (TURN-style) — the always-works fallback
When hole punching fails, both peers send their streams to the VPS and it
forwards each stream to the other player. Adds one hop of latency (region
matters — pick a VPS near the players) and consumes server bandwidth
(~2 x 40 KB/s per match at 30Hz — modest).

- **Effort:** small once Option 3's server exists; it's the same server with a
  forwarding mode.
- **Verdict:** build as the automatic fallback for Option 3, not standalone.

## Option 5 — WebRTC data channels (aiortc) / managed services
`aiortc` gives ICE+STUN+TURN (hole punching + relay fallback) as a library,
and Steam Datagram Relay / Epic Online Services give it as a platform. All are
heavier dependencies and pull in an async stack; overkill for a two-player
hobby title unless it heads to Steam.

## Gameplay caveat for any internet play
Internet RTT (20-100ms+) widens the window where the two clients disagree
about where each fighter is. Our damage authority model (DECISIONS.md D-004 —
each client owns the damage it deals, events are reliable-ish via re-send +
dedupe) already prevents HP divergence, so casual play degrades gracefully:
hits just feel slightly late rather than desyncing. True fairness at high
latency would need rollback/lag compensation — explicitly out of scope
(CLAUDE.md section 10).

## Recommended roadmap
1. **Now:** document Tailscale in the README (Option 1) — remote play with zero code.
2. **v2:** room-code rendezvous + hole punching (Option 3) with relay fallback
   (Option 4) on one small VPS.
3. **Later, if distribution grows:** consider WebRTC/SDR (Option 5).
