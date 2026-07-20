#!/bin/bash
# Portable launcher for shadowclash.sif — assembles the right display/audio
# passthrough flags for whatever Linux desktop it runs on (X11 or Wayland,
# PulseAudio or PipeWire). Game arguments pass straight through:
#
#   ./run_container.sh                       # menu
#   ./run_container.sh --mode singleplayer   # training pole
#   ./run_container.sh --mode join --ip A7K2QF
#
# Do NOT add --bind /dev/video0: Singularity mounts the host /dev by default,
# and a single-file device bind actually breaks camera access (EACCES).
set -e

SIF="${SIF:-$(dirname "$0")/../shadowclash.sif}"
[ -f "$SIF" ] || SIF="shadowclash.sif"
if [ ! -f "$SIF" ]; then
    echo "shadowclash.sif not found — set SIF=/path/to/shadowclash.sif" >&2
    exit 1
fi

FLAGS=()

# X11 socket (also serves Wayland desktops via XWayland)
[ -d /tmp/.X11-unix ] && FLAGS+=(--bind /tmp/.X11-unix)
[ -n "$DISPLAY" ] && FLAGS+=(--env "DISPLAY=$DISPLAY")

# X auth cookie: many desktops keep it under /run/user/<uid>; the same bind
# exposes the PulseAudio/PipeWire socket so hit sounds work
RUNDIR="/run/user/$(id -u)"
[ -d "$RUNDIR" ] && FLAGS+=(--bind "$RUNDIR")
[ -n "$XAUTHORITY" ] && [ -f "$XAUTHORITY" ] && FLAGS+=(--env "XAUTHORITY=$XAUTHORITY")

if [ -z "$DISPLAY" ]; then
    echo "warning: DISPLAY is not set — this game needs a desktop session" >&2
fi

exec singularity run "${FLAGS[@]}" "$SIF" "$@"
