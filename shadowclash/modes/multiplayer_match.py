"""Two-player LAN match: local pose vs peer pose streamed over UDP.

Damage authority (DECISIONS.md D-004): this client computes only the damage
its LOCAL player deals, applies it locally, and broadcasts it as damage
events. Damage taken by the local player arrives as events from the peer.
"""

import socket
import time

import pygame

from shadowclash.capture.pose_capture import PoseCapture
from shadowclash.network.udp_receiver import UdpReceiver
from shadowclash.network.udp_sender import UdpSender
from shadowclash.physics.collision_engine import CollisionEngine
from shadowclash.physics.damage_system import DamageSystem
from shadowclash.physics.hitbox_manager import FighterHitboxes
from shadowclash.skeleton import skeleton_model as sm
from shadowclash.skeleton.skeleton_renderer import draw_skeleton
from shadowclash.ui.hud import Hud
from shadowclash.utils.logger import get_logger

log = get_logger(__name__)

LOCAL_COLOR = (70, 160, 255)
PEER_COLOR = (255, 100, 90)
BG_COLOR = (18, 18, 24)


def local_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def run_multiplayer(config: dict, host: bool, ip: str | None, port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    if host:
        sock.bind(("", port))
        log.info("Hosting on %s:%s — waiting for peer packets", local_ip(), port)
        target = None  # learned from the first received packet
    else:
        sock.bind(("", 0))
        target = (ip, port)
        log.info("Joining %s:%s", ip, port)

    receiver = UdpReceiver(sock)
    receiver.start()
    sender = UdpSender(sock, player_id=0 if host else 1, target=target)

    pygame.init()
    disp = config["display"]
    screen = pygame.display.set_mode((disp["width"], disp["height"]))
    pygame.display.set_caption(f"SHADOWCLASH — {'Host' if host else 'Join'}")
    clock = pygame.time.Clock()
    arena = screen.get_rect()

    from shadowclash.ui.menu import run_settings_panel, run_start_screen

    # The match creator (host) gets the settings panel; the joiner just starts
    if host:
        proceed = run_settings_panel(
            screen, config, "HOST MATCH", "the camera stays off until you start"
        )
    else:
        proceed = run_start_screen(screen, "JOIN MATCH", "the camera stays off until you start")
    if not proceed:
        receiver.stop()
        sock.close()
        pygame.quit()
        return

    capture = PoseCapture(config)
    capture.start()

    damage = DamageSystem(config, fighters=("A", "B"))
    engine = CollisionEngine(config, damage)
    local_fighter = FighterHitboxes(engine.space, "A")
    peer_fighter = FighterHitboxes(engine.space, "B")
    hud = Hud(screen)

    starting_hp = config["match"]["starting_hp"]
    round_time = config["match"]["round_time_seconds"]
    peer_timeout = config["network"]["peer_timeout_ms"] / 1000.0
    send_interval = 1.0 / config["network"]["packet_rate_hz"]

    round_start = time.monotonic()
    last_send = 0.0
    ko_message: str | None = None
    running = True

    while running:
        dt = clock.tick(disp["fps"]) / 1000.0
        now = time.monotonic()
        now_ms = now * 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False

        if host and sender.target is None and receiver.peer_addr is not None:
            sender.target = receiver.peer_addr
            log.info("Peer connected from %s", receiver.peer_addr)
            round_start = now

        local_pose, _ = capture.get_pose()
        peer_pose, last_rx = receiver.get_pose()
        peer_lagging = peer_pose is None or (now - last_rx) > peer_timeout

        local_xy = peer_xy = None
        if local_pose is not None:
            local_xy = sm.to_arena(local_pose)
            local_fighter.update(local_xy, dt)
        if peer_pose is not None:
            peer_xy = sm.to_arena(peer_pose, flip=True)
            peer_fighter.update(peer_xy, dt)

        # Damage dealt by the local player — computed here, broadcast to peer
        if ko_message is None and local_xy is not None and peer_xy is not None and not peer_lagging:
            for hit in engine.check_strikes(local_fighter, "B", now_ms, defender_xy=peer_xy):
                sender.queue_damage_event(hit.zone, hit.blocked, hit.damage)
                strike_px = arena.centerx, arena.centery - 60
                hud.add_hit_popup(hit.zone, hit.damage, hit.blocked, strike_px)

        # Damage taken by the local player — authoritative events from peer
        for ev in receiver.drain_events():
            if ko_message is None:
                damage.apply_damage("A", ev.damage)
                hud.add_hit_popup(ev.zone, ev.damage, ev.blocked, (arena.centerx - 200, arena.centery))

        if now - last_send >= send_interval:
            sender.send(local_pose)
            last_send = now

        seconds_left = round_time - (now - round_start)
        if ko_message is None:
            if damage.is_ko("A"):
                ko_message = "KO — YOU LOSE"
            elif damage.is_ko("B"):
                ko_message = "KO — YOU WIN"
            elif seconds_left <= 0:
                if damage.hp["A"] == damage.hp["B"]:
                    ko_message = "TIME — DRAW"
                else:
                    ko_message = "TIME — " + ("YOU WIN" if damage.hp["A"] > damage.hp["B"] else "YOU LOSE")

        screen.fill(BG_COLOR)
        if local_xy is not None:
            draw_skeleton(screen, local_xy, LOCAL_COLOR, arena, visibility=local_pose[:, 3])
        if peer_xy is not None:
            draw_skeleton(screen, peer_xy, PEER_COLOR, arena, visibility=peer_pose[:, 3])

        hud.draw_health_bar("YOU", damage.hp["A"], starting_hp)
        hud.draw_health_bar("OPPONENT", damage.hp["B"], starting_hp, right=True)
        hud.draw_timer(seconds_left if ko_message is None else 0)
        hud.draw_popups()

        if sender.target is None:
            hud.draw_center_message("WAITING", f"share your IP: {local_ip()}:{port}")
        elif peer_lagging:
            hud.draw_debug(["connection lag — peer avatar frozen"])
        if ko_message is not None:
            hud.draw_center_message(ko_message, "Esc to exit")
        pygame.display.flip()

    receiver.stop()
    capture.stop()
    sock.close()
    pygame.quit()
