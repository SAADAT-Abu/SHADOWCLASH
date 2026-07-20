# SHADOWCLASH: Play on Linux

*Your body is the controller. Your shadow is your fighter.*

SHADOWCLASH is a motion-mirrored fighting game: your webcam tracks your real
punches, kicks and blocks and mirrors them onto your in-game fighter. Play
against AI villains, a training pole, or another player over LAN or internet.

## What you need

- A Linux PC with a desktop session, a webcam, and about 1 GB of disk space
- [Apptainer](https://apptainer.org) or SingularityCE installed:

  ```bash
  # Fedora
  sudo dnf install apptainer

  # Ubuntu / Debian
  sudo apt install apptainer

  # Arch
  sudo pacman -S apptainer
  ```

  (If you have `singularity` instead of `apptainer`, every command below works
  the same, just swap the program name.)

## Download

```bash
wget -O shadowclash.sif "https://zenodo.org/records/21461081/files/shadowclash.sif?download=1"
```

Optional integrity check, the output should be `af087a9423fee8bdea3e4a28f61a453f`:

```bash
md5sum shadowclash.sif
```

## Run

```bash
apptainer run \
  --bind /tmp/.X11-unix \
  --bind /run/user/$(id -u) \
  --env DISPLAY=$DISPLAY \
  --env XAUTHORITY=$XAUTHORITY \
  shadowclash.sif
```

That opens the menu. Pick a mode with the arrow keys or mouse:

- **Single Player**: fight a ladder of 10 villains with rising difficulty
- **Training**: practice strikes on the kicking pole with a debug overlay (press D)
- **VS Mode**: fight another player
  - **Host** shows your LAN address and a 6-letter room token
  - **Join** takes either the host's LAN IP (same network) or the room token
    (anywhere on the internet)

Step back until your whole body is visible to the camera. Fast strikes do more
damage; joining both hands in front of you blocks like a Tekken guard.

## If something does not work

- **Window fails to open** ("Authorization required"): run `xhost +local:`
  once, then launch again without the `--env XAUTHORITY=...` line.
- **Camera fails to open**: do NOT add `--bind /dev/video0`, it breaks camera
  access. The container already sees your devices. If your webcam is not
  device 0, check with `v4l2-ctl --list-devices`.
- **No sound**: harmless, the game plays on. Sound needs the
  `--bind /run/user/$(id -u)` line.
- **VS Mode over the internet**: only the room token is needed, no port
  forwarding. If joining by token fails on both ends, your network may block
  UDP hole punching; play on the same LAN with the IP instead.
