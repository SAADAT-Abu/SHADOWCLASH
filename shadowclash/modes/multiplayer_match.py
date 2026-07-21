"""Two-player match: local pose vs peer pose streamed over UDP.

Joining is normally by room token (DECISIONS.md D-016): the rendezvous server
introduces the peers, they punch directly, and if that fails within a few
seconds the same server relays the packets instead (D-020). A raw IP is still
accepted via `--ip` for offline LAN parties and loopback tests; the join input
is auto-detected, dotted-quad means IP and anything else is a token.

Damage authority (DECISIONS.md D-004): this client computes only the damage
its LOCAL player deals, applies it locally, and broadcasts it as damage
events. Damage taken by the local player arrives as events from the peer.
"""

import socket
import time

import pygame

from shadowclash.capture.pose_capture import PoseCapture
from shadowclash.capture.synthetic_pose import SyntheticPoseDriver
from shadowclash.modes.rounds import RoundTracker
from shadowclash.modes.singleplayer_vs import distance_hint, hit_zone_px
from shadowclash.network.rendezvous import RendezvousClient, is_ip, local_ip
from shadowclash.network.udp_receiver import UdpReceiver
from shadowclash.network.udp_sender import UdpSender
from shadowclash.physics.collision_engine import CollisionEngine
from shadowclash.physics.damage_system import DamageSystem
from shadowclash.physics.hitbox_manager import FighterHitboxes
from shadowclash.skeleton import skeleton_model as sm
from shadowclash.skeleton.skeleton_renderer import draw_skeleton
from shadowclash.ui.hud import Hud
from shadowclash.ui.scene import FightScene
from shadowclash.ui.sound import SoundBank
from shadowclash.utils.logger import get_logger

log = get_logger(__name__)

LOCAL_COLOR = (70, 160, 255)
PEER_COLOR = (255, 100, 90)


def run_multiplayer(
    config: dict, host: bool, ip: str | None, port: int, input_source: str = "camera"
) -> None:
    """`ip` is the join target: an IPv4 address (LAN) or a room token."""
    net_cfg = config["network"]
    rdv_server = None
    if net_cfg.get("rendezvous_host"):
        rdv_server = (net_cfg["rendezvous_host"], net_cfg.get("rendezvous_port", 5556))

    join_token = None if host or ip is None or is_ip(ip) else ip.strip().upper()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if host:
        sock.bind(("", port))
        log.info("Hosting on %s:%s, waiting for peer packets", local_ip(), port)
        target = None  # learned from the first received packet or rendezvous
    elif join_token is not None:
        sock.bind(("", 0))
        target = None  # resolved via the rendezvous server
        log.info("Joining room token %s via %s", join_token, rdv_server)
    else:
        sock.bind(("", 0))
        target = (ip, port)
        log.info("Joining %s:%s", ip, port)

    receiver = UdpReceiver(sock)
    receiver.start()
    sender = UdpSender(sock, player_id=0 if host else 1, target=target)

    rdv = None
    if rdv_server is not None and (host or join_token is not None):
        rdv = RendezvousClient(sock, receiver, rdv_server)
        if host:
            rdv.start_host()
        else:
            rdv.start_join(join_token)
    elif join_token is not None:
        log.error("Token join requested but no rendezvous server configured")
        sock.close()
        receiver.stop()
        return

    pygame.init()
    disp = config["display"]
    screen = pygame.display.set_mode((disp["width"], disp["height"]), pygame.RESIZABLE)
    pygame.display.set_caption("SHADOWCLASH")
    clock = pygame.time.Clock()
    arena = screen.get_rect()

    from shadowclash.ui.menu import run_name_entry, run_settings_panel, run_start_screen

    # Bot input (loopback testing) skips the interactive panels entirely.
    # Otherwise: name entry first, then the match creator (host) gets the
    # settings panel; the joiner just gets the start gate.
    from shadowclash.ui.menu import ROUNDS_ROW, SETTING_ROWS

    player_name = "BOT"
    if input_source != "bot":
        player_name = run_name_entry(screen, config)
        proceed = player_name is not None
        if proceed and host:
            proceed = run_settings_panel(
                screen, config, "VS MODE (HOST)", "the camera stays off until you start",
                rows=SETTING_ROWS + [ROUNDS_ROW],
            )
        elif proceed:
            proceed = run_start_screen(
                screen, "VS MODE (JOIN)", "the camera stays off until you start"
            )
        if not proceed:
            if rdv is not None:
                rdv.close()
            receiver.stop()
            sock.close()
            return

    sender.player_name = player_name

    if input_source == "bot":
        capture = SyntheticPoseDriver(config)
    else:
        capture = PoseCapture(config)
    capture.start()

    damage = DamageSystem(config, fighters=("A", "B"))
    damage.scale = config["damage"].get("vs_scale", 1.0)
    engine = CollisionEngine(config, damage)
    local_fighter = FighterHitboxes(engine.space, "A")
    peer_fighter = FighterHitboxes(engine.space, "B")
    hud = Hud(screen)
    scene = FightScene(arena.size)
    sounds = SoundBank()
    peer_seen = False
    smoothed_ratio = 1.0

    starting_hp = config["match"]["starting_hp"]
    round_time = config["match"]["round_time_seconds"]
    gap_seconds = config["match"].get("round_gap_seconds", 30)
    rounds_total = config["match"].get("vs_rounds", 3)
    if host:
        sender.rounds = rounds_total  # joiner adopts this from our packets
    peer_timeout = config["network"]["peer_timeout_ms"] / 1000.0
    send_interval = 1.0 / config["network"]["packet_rate_hz"]

    # Match phases: waiting (peer not connected, nothing runs) -> countdown
    # (gap_seconds until the round starts) -> fighting (timer + damage live)
    # -> round_over (result splash) -> countdown ... -> match_over.
    phase = "waiting"
    tracker: RoundTracker | None = None
    countdown_end = 0.0
    last_beep_second = -1
    fight_flash_until = 0.0
    round_over_until = 0.0
    round_msg = ""
    round_start = time.monotonic()
    seconds_left = float(round_time)
    last_send = 0.0
    ko_message: str | None = None
    token_logged = False
    peer_locked = False
    punch_started = 0.0
    relay_after = net_cfg.get("relay_after_seconds", 6)
    running = True

    while running:
        dt = clock.tick(disp["fps"]) / 1000.0
        now = time.monotonic()
        now_ms = now * 1000.0
        arena = screen.get_rect()
        if scene.size != arena.size:
            scene = FightScene(arena.size)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        if rdv is not None:
            rdv.update(now)
            if host and rdv.token and not token_logged:
                token_logged = True
                log.info("Room token: %s", rdv.token)

        # Lock onto the address real game packets arrive from, once and for
        # good, so a late straggler on the losing path cannot flip us back
        if receiver.peer_addr is not None and not peer_locked:
            peer_locked = True
            sender.target = receiver.peer_addr
            sender.punch_targets = []
            via = "relay" if receiver.peer_addr == rdv_server else "direct"
            log.info("Peer connected from %s (%s)", receiver.peer_addr, via)
        elif not peer_locked and rdv is not None and rdv.peers and sender.target is None:
            sender.target = rdv.peers[0]
            sender.punch_targets = list(rdv.peers[1:])
            punch_started = now
            log.info("Hole punching toward %s", rdv.peers)

        # Symmetric NAT makes punching impossible (D-020): after a few seconds
        # of silence, add the rendezvous server as a destination and let it
        # forward. Both paths stay live; the receiver dedupes by seq.
        if (
            rdv is not None and not peer_locked and not rdv.relaying
            and punch_started and now - punch_started >= relay_after
        ):
            rdv.start_relay()
            sender.punch_targets = [*sender.punch_targets, rdv_server]
            log.info(
                "No direct path after %.0fs, falling back to relay via %s:%s",
                relay_after, *rdv_server,
            )

        local_pose, _ = capture.get_pose()
        peer_pose, last_rx = receiver.get_pose()
        peer_lagging = peer_pose is None or (now - last_rx) > peer_timeout
        if peer_pose is not None and not peer_seen:
            peer_seen = True
            if not host:
                rounds_total = receiver.peer_rounds or rounds_total
            tracker = RoundTracker(rounds_total)
            phase = "countdown"
            countdown_end = now + gap_seconds
            last_beep_second = -1
            log.info(
                "Peer stream active — round 1 in %ds (best of %d)",
                gap_seconds, rounds_total,
            )

        if phase == "countdown":
            remaining = countdown_end - now
            if remaining <= 0:
                phase = "fighting"
                damage.reset()
                round_start = now
                fight_flash_until = now + 1.0
                sounds.bell()
                log.info("Round %d: fight", tracker.round_no)
            else:
                sec = int(remaining) + 1
                if sec <= 5 and sec != last_beep_second:
                    last_beep_second = sec
                    sounds.count()

        local_xy = peer_xy = None
        if local_pose is not None:
            local_xy = sm.to_arena(local_pose)
            local_fighter.update(local_xy, dt)
        if peer_pose is not None:
            peer_xy = sm.to_arena(peer_pose, flip=True)
            peer_fighter.update(peer_xy, dt)

        # Damage dealt by the local player — computed here, broadcast to peer
        if phase == "fighting" and local_xy is not None and peer_xy is not None and not peer_lagging:
            for hit in engine.check_strikes(local_fighter, "B", now_ms, defender_xy=peer_xy):
                sender.queue_damage_event(hit.zone, hit.blocked, hit.damage)
                pos = hit_zone_px(peer_xy, hit.zone, arena)
                hud.add_hit_popup(hit.zone, hit.damage, hit.blocked, pos)
                scene.add_hit_spark(pos, heavy=hit.zone == "head")
                sounds.hit(hit.zone, hit.damage, hit.blocked)
                log.info("HIT dealt: %s -%.1f%s", hit.zone, hit.damage, " (blocked)" if hit.blocked else "")

        # Damage taken by the local player — authoritative events from peer
        for ev in receiver.drain_events():
            if phase == "fighting":
                damage.apply_damage("A", ev.damage)
                pos = hit_zone_px(local_xy, ev.zone, arena) if local_xy is not None else arena.center
                hud.add_hit_popup(ev.zone, ev.damage, ev.blocked, pos)
                scene.add_hit_spark(pos, heavy=ev.zone == "head")
                sounds.hit(ev.zone, ev.damage, ev.blocked)
                log.info("HIT taken: %s -%.1f (hp %.1f)", ev.zone, ev.damage, damage.hp["A"])

        if now - last_send >= send_interval:
            sender.send(local_pose)
            last_send = now

        peer_name = receiver.peer_name or "OPPONENT"
        if phase == "fighting":
            seconds_left = round_time - (now - round_start)
            winner: str | None = None
            round_ended = False
            if damage.is_ko("A"):
                winner, round_ended = "B", True
            elif damage.is_ko("B"):
                winner, round_ended = "A", True
            elif seconds_left <= 0:
                round_ended = True
                if damage.hp["A"] > damage.hp["B"]:
                    winner = "A"
                elif damage.hp["B"] > damage.hp["A"]:
                    winner = "B"
            if round_ended:
                tracker.record(winner)
                sounds.ko()
                if winner is None:
                    round_msg = f"ROUND {tracker.round_no}: DRAW"
                else:
                    winner_name = player_name if winner == "A" else peer_name
                    round_msg = f"{winner_name} TAKES ROUND {tracker.round_no}"
                log.info("%s (score %d-%d)", round_msg, tracker.wins["A"], tracker.wins["B"])
                phase = "round_over"
                round_over_until = now + 4.0

        if phase == "round_over" and now >= round_over_until:
            if tracker.decided():
                phase = "match_over"
                score = f"{tracker.wins['A']}-{tracker.wins['B']}"
                match_winner = tracker.match_winner()
                if match_winner is None:
                    ko_message = f"MATCH DRAW {score}"
                else:
                    winner_name = player_name if match_winner == "A" else peer_name
                    ko_message = f"{winner_name} WINS THE MATCH {score}"
                sounds.ko()
                log.info("Match over: %s", ko_message)
            else:
                tracker.advance()
                phase = "countdown"
                countdown_end = now + gap_seconds
                last_beep_second = -1
                log.info("Round %d in %ds", tracker.round_no, gap_seconds)

        scene.draw_background(screen)
        if local_xy is not None:
            scene.draw_fighter_shadow(screen, local_xy, arena)
        if peer_xy is not None:
            scene.draw_fighter_shadow(screen, peer_xy, arena)
        if local_xy is not None:
            draw_skeleton(screen, local_xy, LOCAL_COLOR, arena, visibility=local_pose[:, 3])
        if peer_xy is not None:
            draw_skeleton(screen, peer_xy, PEER_COLOR, arena, visibility=peer_pose[:, 3])
        scene.update_and_draw_particles(screen, dt)

        hud.draw_health_bar(player_name, damage.hp["A"], starting_hp)
        hud.draw_health_bar(peer_name, damage.hp["B"], starting_hp, right=True)
        if phase == "fighting":
            hud.draw_timer(seconds_left)
        elif phase in ("waiting", "countdown"):
            hud.draw_timer(round_time)
        else:
            hud.draw_timer(0)
        if tracker is not None:
            hud.draw_level_banner(f"ROUND {tracker.round_no}/{tracker.total}")
            hud.draw_round_pips(tracker.wins["A"], tracker.wins_needed)
            hud.draw_round_pips(tracker.wins["B"], tracker.wins_needed, right=True)
        hud.draw_popups()

        # Distance coach: nudge the player until both avatars share a scale
        if (
            phase in ("countdown", "fighting")
            and local_xy is not None and peer_xy is not None and not peer_lagging
        ):
            ratio = sm.torso_length(local_xy) / sm.torso_length(peer_xy)
            smoothed_ratio += (ratio - smoothed_ratio) * min(dt * 3.0, 1.0)
            hint = distance_hint(smoothed_ratio, 1.0)
            if hint is not None:
                hud.draw_distance_hint(hint)

        # Exactly one center overlay per phase — never stacked
        if phase == "waiting":
            # Name the stage we are actually stuck at, so a failure is never
            # just a blank screen (D-020)
            if receiver.bad_packets >= 10:
                hud.draw_center_message(
                    "VERSION MISMATCH", "both players need the same SHADOWCLASH version"
                )
            elif rdv is not None and rdv.error:
                hud.draw_center_message("TOKEN NOT FOUND", "check the code, Esc to go back")
            elif rdv is not None and rdv.peers:
                hud.draw_center_message(
                    "PEER FOUND",
                    "connecting via relay..." if rdv.relaying else "connecting...",
                )
            elif host:
                token_str = rdv.token if rdv is not None and rdv.token else "..."
                hud.draw_center_message(
                    "WAITING", f"room token: {token_str}  (Esc cancels)"
                )
            elif join_token is not None:
                hud.draw_center_message("CONNECTING", f"room token {join_token} (Esc cancels)")
            else:
                hud.draw_center_message("CONNECTING", f"{ip}:{port} (Esc cancels)")
        elif phase == "countdown":
            hud.draw_countdown(
                f"ROUND {tracker.round_no}",
                int(countdown_end - now) + 1,
                "fight starts at zero",
            )
        elif phase == "fighting" and now < fight_flash_until:
            hud.draw_center_message("FIGHT!", color=(255, 214, 90))
        elif phase == "round_over":
            hud.draw_center_message(
                round_msg, f"score {tracker.wins['A']} - {tracker.wins['B']}", color=(255, 214, 90)
            )
        elif phase == "match_over":
            hud.draw_center_message(ko_message, "Esc to exit")
        if peer_seen and peer_lagging and phase != "match_over":
            hud.draw_debug(["connection lag: peer avatar frozen"])
        pygame.display.flip()

    if rdv is not None:
        rdv.close()  # host: tell the server to drop the room immediately
    receiver.stop()
    capture.stop()
    sock.close()
