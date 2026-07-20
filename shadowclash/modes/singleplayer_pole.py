"""Single-player training mode: hit the static kicking pole.

Runs the full pose -> hitbox -> collision -> damage pipeline against a
static target, with a debug overlay for tuning thresholds (milestone M3/M4).
"""

import time

import pygame

from shadowclash.capture.pose_capture import PoseCapture
from shadowclash.physics.collision_engine import CollisionEngine
from shadowclash.physics.damage_system import DamageSystem
from shadowclash.physics.hitbox_manager import FighterHitboxes, PoleHitboxes
from shadowclash.skeleton import skeleton_model as sm
from shadowclash.skeleton.skeleton_renderer import draw_pole, draw_skeleton
from shadowclash.ui.hud import Hud
from shadowclash.ui.scene import FightScene
from shadowclash.ui.sound import SoundBank
from shadowclash.utils.logger import get_logger

log = get_logger(__name__)

PLAYER_COLOR = (70, 160, 255)


def run_singleplayer(config: dict) -> None:
    pygame.init()
    disp = config["display"]
    screen = pygame.display.set_mode((disp["width"], disp["height"]), pygame.RESIZABLE)
    pygame.display.set_caption("SHADOWCLASH")
    clock = pygame.time.Clock()
    arena = screen.get_rect()

    from shadowclash.ui.menu import run_settings_panel

    if not run_settings_panel(
        screen, config, "TRAINING",
        "kicking pole practice (camera stays off until you start)",
    ):
        return

    capture = PoseCapture(config)
    capture.start()

    damage = DamageSystem(config, fighters=("A", "B"))
    pole_hp_max = config["singleplayer"]["pole_hp"]
    damage.hp["B"] = float(pole_hp_max)
    damage.starting_hp = pole_hp_max  # pole heals back to its own max
    regen = config["singleplayer"]["pole_regen_per_sec"]

    engine = CollisionEngine(config, damage)
    player = FighterHitboxes(engine.space, "A")
    PoleHitboxes(engine.space, "B")
    hud = Hud(screen)
    scene = FightScene(arena.size)
    sounds = SoundBank()

    show_debug = False
    last_hit_time = 0.0
    running = True
    log.info("Pole mode started — Esc quits, D toggles debug overlay")

    while running:
        dt = clock.tick(disp["fps"]) / 1000.0
        now_ms = time.monotonic() * 1000.0
        arena = screen.get_rect()
        if scene.size != arena.size:
            scene = FightScene(arena.size)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_d:
                    show_debug = not show_debug

        pose, _ = capture.get_pose()
        hits = []
        if pose is not None:
            xy = sm.to_arena(pose)
            player.update(xy, dt)
            hits = engine.check_strikes(player, "B", now_ms)

        for hit in hits:
            last_hit_time = now_ms
            zone_x, zone_y, _ = PoleHitboxes.ZONES[hit.zone]
            pos = (int(zone_x * arena.width) - 40, int(zone_y * arena.height))
            hud.add_hit_popup(hit.zone, hit.damage, hit.blocked, pos)
            scene.add_hit_spark(pos, heavy=hit.zone == "head")
            sounds.hit(hit.zone, hit.damage, hit.blocked)

        if damage.is_ko("B"):
            damage.reset("B")  # pole resets after "defeat" so training continues
        elif now_ms - last_hit_time > 1500:
            damage.heal("B", regen * dt)

        scene.draw_background(screen)
        draw_pole(screen, PoleHitboxes.ZONES, damage.hp["B"] / pole_hp_max, arena)
        if pose is not None:
            xy = sm.to_arena(pose)
            scene.draw_fighter_shadow(screen, xy, arena)
            draw_skeleton(screen, xy, PLAYER_COLOR, arena, visibility=pose[:, 3])
        else:
            hud.draw_center_message("NO POSE", "step into the camera view")
        scene.update_and_draw_particles(screen, dt)

        hud.draw_health_bar("POLE", damage.hp["B"], pole_hp_max, right=True)
        hud.draw_popups()
        if show_debug:
            fastest = max((v for _, v in player.strikes.values()), default=0.0)
            last = engine.last_hit
            hud.draw_debug(
                [
                    f"render fps: {clock.get_fps():.0f}   capture fps: {capture.capture_fps:.0f}",
                    f"limb velocity (torso-lengths/s): {fastest:.2f}  "
                    f"(threshold {engine.min_strike_velocity})",
                    f"max velocity seen: {engine.max_velocity_seen:.2f}",
                    f"last hit: {last.zone} -{last.damage:.1f}" if last else "last hit: —",
                ]
            )
        pygame.display.flip()

    capture.stop()
