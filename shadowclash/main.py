"""SHADOWCLASH entry point: mode selection and dispatch."""

import argparse

from shadowclash.utils.config_loader import load_config
from shadowclash.utils.logger import get_logger

log = get_logger("shadowclash")


def main() -> None:
    parser = argparse.ArgumentParser(prog="shadowclash", description="Full-Body Mirror Fight Arena")
    parser.add_argument(
        "--mode",
        choices=["menu", "posecheck", "singleplayer", "versus", "host", "join"],
        default="menu",
        help="menu (default), posecheck (M1 camera sanity check), singleplayer "
        "(pole training), versus (fight the shadow bot), host, join",
    )
    parser.add_argument(
        "--ip",
        help="join target: room token, or a host IP for offline LAN play",
    )
    parser.add_argument("--port", type=int, help="UDP port (default from config)")
    parser.add_argument("--config", help="path to game_config.yaml")
    parser.add_argument(
        "--input",
        choices=["camera", "bot"],
        default="camera",
        help="bot substitutes a synthetic fighter for the webcam (multiplayer testing)",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    port = args.port or config["network"]["default_port"]

    def run_mode(mode: str, ip: str | None) -> None:
        if mode == "posecheck":
            from shadowclash.capture.pose_capture import run_posecheck

            run_posecheck(config)
        elif mode == "singleplayer":
            from shadowclash.modes.singleplayer_pole import run_singleplayer

            run_singleplayer(config)
        elif mode == "versus":
            from shadowclash.modes.singleplayer_vs import run_versus

            run_versus(config)
        elif mode in ("host", "join"):
            if mode == "join" and not ip:
                parser.error("--ip is required for join mode")
            from shadowclash.modes.multiplayer_match import run_multiplayer

            run_multiplayer(
                config, host=(mode == "host"), ip=ip, port=port, input_source=args.input
            )

    try:
        if args.mode == "menu":
            # Menu-driven session: modes return here (Esc cancels a room or
            # fight back to the menu) until the player picks Quit
            from shadowclash.ui.menu import run_menu

            while True:
                mode, menu_ip = run_menu(config)
                if mode == "quit":
                    return
                run_mode(mode, menu_ip or args.ip)
        else:
            run_mode(args.mode, args.ip)
    finally:
        import pygame

        pygame.quit()


if __name__ == "__main__":
    main()
