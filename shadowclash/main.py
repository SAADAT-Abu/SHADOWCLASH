"""SHADOWCLASH entry point: mode selection and dispatch."""

import argparse

from shadowclash.utils.config_loader import load_config
from shadowclash.utils.logger import get_logger

log = get_logger("shadowclash")


def main() -> None:
    parser = argparse.ArgumentParser(prog="shadowclash", description="Full-Body Mirror Fight Arena")
    parser.add_argument(
        "--mode",
        choices=["menu", "posecheck", "singleplayer", "host", "join"],
        default="menu",
        help="menu (default), posecheck (M1 camera sanity check), singleplayer, host, join",
    )
    parser.add_argument("--ip", help="host IP for join mode")
    parser.add_argument("--port", type=int, help="UDP port (default from config)")
    parser.add_argument("--config", help="path to game_config.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    port = args.port or config["network"]["default_port"]
    mode, ip = args.mode, args.ip

    if mode == "menu":
        from shadowclash.ui.menu import run_menu

        mode, menu_ip = run_menu(config)
        ip = menu_ip or ip
        if mode == "quit":
            return

    if mode == "posecheck":
        from shadowclash.capture.pose_capture import run_posecheck

        run_posecheck(config)
    elif mode == "singleplayer":
        from shadowclash.modes.singleplayer_pole import run_singleplayer

        run_singleplayer(config)
    elif mode in ("host", "join"):
        if mode == "join" and not ip:
            parser.error("--ip is required for join mode")
        from shadowclash.modes.multiplayer_match import run_multiplayer

        run_multiplayer(config, host=(mode == "host"), ip=ip, port=port)


if __name__ == "__main__":
    main()
