# CLAUDE.md — SHADOWCLASH: Full-Body Mirror Fight Arena

## Project Identity

**Game Name:** SHADOWCLASH
**Tagline:** *"Your body is the controller. Your shadow is your fighter."*
**Genre:** Real-time motion-mirrored 2-player fighting game (LAN multiplayer + single-player training mode)
**Core Mechanic:** Each player's real-world body movements are captured via webcam and mirrored 1:1 onto an in-game skeleton avatar. No move classification, no button inputs — physical punches/kicks/blocks are directly reproduced in-game, and collision physics between the two mirrored skeletons determines hits, damage, and score (Tekken-style health depletion by body zone).

This document is the single source of truth for Claude Code to build this project end-to-end. Follow it top to bottom. Do not deviate from the tech stack without explicit reason logged in `DECISIONS.md`.

> **Plan amendments (2026-07-20):** during the initial build, several spec-level issues were found and corrected — see `DECISIONS.md` for full reasoning. Summary: pose capture runs in a dedicated thread (D-003); each client is authoritative for damage its local player *deals*, with damage events piggybacked on UDP packets (D-004 — the "both clients compute identical damage" assumption does not hold under latency); strike velocity is measured in torso-lengths/sec so thresholds are camera-distance invariant (D-005); packets carry sequence numbers and stale ones are dropped (D-006); frames are mirror-flipped at capture (D-007); hit detection uses per-frame pymunk point queries instead of collision-handler callbacks, because Chipmunk never generates collisions between two non-dynamic bodies (D-010); `pymunk==6.6.2` does not exist on PyPI, using 6.11.1 (D-009); the Ubuntu 22.04 container needs the deadsnakes PPA for python3.11 (D-002).

---

## 1. High-Level Architecture

```
                    PLAYER A                         PLAYER B
                 (Webcam + PC)                     (Webcam + PC)
                       |                                  |
              [MediaPipe Pose]                   [MediaPipe Pose]
                       |                                  |
              [Landmark Extractor]               [Landmark Extractor]
                       |                                  |
                 [UDP Sender]  <----- LAN/WiFi ----->  [UDP Sender]
                       |                                  |
                 [UDP Receiver]                    [UDP Receiver]
                       |                                  |
              [Skeleton Renderer A]              [Skeleton Renderer B]
                       \                                  /
                        \                                /
                         [Shared Game Scene / Arena]
                                    |
                       [Collision & Hit Detection Engine]
                                    |
                        [Damage / Scoring System]
                                    |
                         [HUD: Health Bars, Timer]
```

Both players run the **same executable**. Each instance:
1. Captures its own local player's pose (always "Player A" locally)
2. Streams landmarks to the peer over UDP
3. Receives peer's landmarks and renders them as "Player B"
4. Both instances independently run identical collision/physics logic and stay in sync because both receive the same landmark streams

This is a **peer-to-peer, no-authoritative-server** design — acceptable for a 2-player LAN game where both clients compute the same deterministic collision outcome from the same inputs.

---

## 2. Tech Stack & Dependencies

| Component | Library | Version | Purpose |
|---|---|---|---|
| Language | Python | 3.11 | MediaPipe compatibility ceiling is 3.12; 3.11 is the safest stable choice |
| Pose detection | `mediapipe` | 0.10.x | 33-point body landmark extraction from webcam |
| Camera capture | `opencv-python` | 4.9.x | Webcam frame grabbing, preprocessing |
| Rendering / game loop | `pygame` | 2.5.x | 2D skeleton rendering, arena, HUD, game loop, sound |
| Physics / collision | `pymunk` | 6.11.x | 2D physics engine (built on Chipmunk2D); receive-zone shapes + point queries for hit detection (D-009/D-010) |
| Networking | Python built-in `socket` (UDP) | stdlib | LAN peer-to-peer landmark streaming |
| Numerical ops | `numpy` | 1.26.x | Vector math, smoothing filters |
| Config | `pyyaml` | 6.x | Game config (damage values, port numbers, thresholds) |
| Packaging | Singularity/Apptainer | 3.11+ | Container build for distribution |

### requirements.txt
```
mediapipe==0.10.14
opencv-python==4.9.0.80
pygame==2.5.2
pymunk==6.11.1
numpy==1.26.4
pyyaml==6.0.1
```

**Why Pygame + Pymunk instead of Unity:** Since the design mirrors real player motion directly (no move-classification ML needed), we don't need a heavyweight 3D engine. A 2D skeleton-based arena (think "shadow boxing silhouettes" side by side) is fully sufficient, dramatically simpler to containerize in Singularity (single Python process, no separate engine binary/license), and faster for Claude Code to implement and test end-to-end.

---

## 3. Repository Structure

```
shadowclash/
├── CLAUDE.md                      # this file
├── DECISIONS.md                   # log any deviations from spec here
├── requirements.txt
├── config/
│   └── game_config.yaml           # damage tables, thresholds, network ports
├── shadowclash/
│   ├── __init__.py
│   ├── main.py                    # entry point, mode selection (menu)
│   ├── capture/
│   │   ├── pose_capture.py        # MediaPipe wrapper, webcam loop
│   │   └── landmark_smoother.py   # moving-average / Kalman-lite filter
│   ├── network/
│   │   ├── udp_sender.py          # serialize + send local landmarks
│   │   ├── udp_receiver.py        # receive + deserialize peer landmarks
│   │   └── protocol.py            # packet format definition
│   ├── skeleton/
│   │   ├── skeleton_model.py      # maps 33 landmarks -> limb segments
│   │   └── skeleton_renderer.py   # pygame drawing of stick-figure avatar
│   ├── physics/
│   │   ├── hitbox_manager.py      # pymunk bodies for head/torso/legs/arms
│   │   ├── collision_engine.py    # collision callbacks, velocity checks
│   │   └── damage_system.py       # Tekken-style zone damage + cooldowns
│   ├── modes/
│   │   ├── singleplayer_pole.py   # kicking-pole training mode
│   │   └── multiplayer_match.py   # 2-player LAN match orchestration
│   ├── ui/
│   │   ├── hud.py                 # health bars, timer, round counter
│   │   └── menu.py                # main menu, mode select, IP entry
│   └── utils/
│       └── logger.py
├── assets/
│   ├── sounds/                    # hit sfx, round start/end
│   └── fonts/
├── tests/
│   ├── test_landmark_smoother.py
│   ├── test_collision_engine.py
│   └── test_damage_system.py
├── Singularity.def                # container definition
└── scripts/
    ├── run_local_test.sh
    └── build_container.sh
```

---

## 4. Core Game Logic

### 4.1 Pose Capture (`capture/pose_capture.py`)
- Open webcam via OpenCV (`cv2.VideoCapture(0)`)
- Run each frame through `mediapipe.solutions.pose.Pose()` with `min_detection_confidence=0.6`, `min_tracking_confidence=0.6`
- Extract all 33 `PoseLandmark` points as `(x, y, z, visibility)`, normalized 0–1 by MediaPipe
- Discard/hold-last-known-good frame if visibility for a critical joint (wrist, ankle, hip) drops below 0.5, to avoid jitter from occlusion

### 4.2 Landmark Smoothing (`capture/landmark_smoother.py`)
- Apply a simple exponential moving average per landmark: `smoothed = alpha * new + (1-alpha) * previous`, with `alpha ≈ 0.4`
- This prevents jittery, false-positive "hits" caused by MediaPipe landmark noise

### 4.3 Skeleton Model (`skeleton/skeleton_model.py`)
Map MediaPipe's 33 landmarks into game-relevant **limb segments**, each becoming a physics hitbox:

| Segment | MediaPipe Landmarks Used | Hitbox Type |
|---|---|---|
| Head | NOSE, LEFT_EAR, RIGHT_EAR | Circle (high damage zone) |
| Torso | LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_HIP, RIGHT_HIP | Polygon (medium damage zone) |
| Left/Right Fist | LEFT_WRIST / RIGHT_WRIST | Small circle (striking hitbox, attached to attacker) |
| Left/Right Foot | LEFT_ANKLE / RIGHT_ANKLE | Small circle (striking hitbox, attached to attacker) |
| Left/Right Leg | KNEE + ANKLE segment | Capsule (low damage zone, receiving hitbox) |

Each player has two hitbox roles simultaneously:
- **Striking hitboxes** (fists, feet) — used to detect when *this player* hits the opponent
- **Receiving hitboxes** (head, torso, legs) — used to detect when *this player* gets hit

### 4.4 Collision & Physics Engine (`physics/collision_engine.py`)

Built on **Pymunk** (2D physics):
1. Every frame, update each hitbox's `pymunk.Body` position to match the current smoothed landmark position, and compute **velocity** as `(current_pos - previous_pos) / delta_time`
2. Register Pymunk collision handlers between Player A's striking hitboxes and Player B's receiving hitboxes (and vice versa)
3. On `collision_begin` callback:
   - Check the **striking limb's velocity magnitude** — only register a hit if velocity exceeds `MIN_STRIKE_VELOCITY` (config value, tuned experimentally, prevents slow/incidental touches from counting)
   - Identify which receiving zone was hit (head/torso/leg)
   - Trigger `damage_system.apply_hit(attacker, defender, zone, velocity)`
4. Apply a **hit cooldown** of ~600ms per limb-pair after a registered hit, to prevent a single continuous touch from repeatedly triggering damage

### 4.5 Damage System (`physics/damage_system.py`)

Tekken-style zone-based damage, starting HP = 100 per player:

| Hit Zone | Base Damage | Notes |
|---|---|---|
| Head | 15 | Highest risk/reward |
| Torso | 8 | Standard punch/kick zone |
| Leg | 4 | Low-risk chip damage |

- Actual damage = `base_damage * min(velocity / REFERENCE_VELOCITY, 1.5)` — harder/faster strikes do more damage, capped at 1.5x multiplier to avoid absurd scaling from tracking noise
- **Block detection:** if defender's forearm hitboxes are raised above shoulder landmark height *and* positioned between attacker's strike vector and the defender's torso/head at the moment of collision, damage is reduced by 70% ("blocked")
- **KO condition:** HP reaches 0 → round ends, "KO" overlay, winner declared
- **Round timer:** default 99 seconds; if timer expires, higher HP wins the round

### 4.6 Single-Player Mode: The Kicking Pole (`modes/singleplayer_pole.py`)

This is your **testing and training mode**, and should be built and validated *before* multiplayer networking:

- Spawns one **static kicking pole** object in the arena — a fixed vertical `pymunk.Body` (type `STATIC`) with three stacked circular hitboxes matching head/torso/leg height zones, same as a real player would have
- Player's own mirrored skeleton is rendered and fully driven by local webcam pose, identical pipeline to multiplayer mode
- All collision, velocity, and damage logic runs exactly as in a real match, but against the static pole instead of a networked opponent
- Pole has its own HP bar (e.g., 100) purely for feedback; hitting head/torso/leg zones shows the same damage numbers/hit-zone feedback that will be used in real matches
- **Why this matters:** this mode lets you validate the entire pose→hitbox→collision→damage pipeline with zero networking complexity. Build this first, get it feeling right (strike velocity thresholds, hit registration accuracy, cooldown tuning), then layer multiplayer on top.
- Optional: pole slowly regenerates HP or resets after being "defeated" so training is continuous
- Display real-time debug overlay: current limb velocity, last hit zone, damage dealt — critical for tuning thresholds

### 4.7 Multiplayer Mode: LAN Match (`modes/multiplayer_match.py`)

**Network Protocol (`network/protocol.py`):**
- UDP packet per frame containing: `player_id`, `frame_timestamp`, 33 × (x, y, z, visibility) floats
- Packet size ≈ 33 × 4 × 4 bytes ≈ 528 bytes — trivially small for LAN, safe to send every frame (~30–60Hz) without congestion
- Use simple JSON or `struct.pack` binary encoding (binary preferred for lower latency/overhead)

**Connection flow:**
1. Player A starts game in "Host" mode, displays local IP + port
2. Player B enters Player A's IP in "Join" mode
3. Both clients begin sending/receiving landmark streams over UDP as soon as connected
4. Both run identical local simulation: each client renders **both** avatars (its own local pose + peer's received pose) in the same arena layout, mirrored so the match looks correct on both screens
5. Both clients independently compute collisions and damage — because both receive the same landmark data streams, results should be consistent, but the *design assumption* is that occasional desync (due to packet loss/latency) is acceptable for a casual LAN party game. Do not over-engineer server-authoritative reconciliation for v1.

**Latency handling:**
- If no packet received from peer for >200ms, freeze peer avatar in last known pose and show "connection lag" indicator
- Do not attempt lag compensation/rollback in v1 — LAN/WiFi latency is low enough (~5–30ms) that direct mirroring is acceptable

---

## 5. Build Order for Claude Code (Milestones)

Build strictly in this order. Each milestone should be independently runnable and testable before moving to the next.

1. **M1 — Pose capture sanity check:** Webcam opens, MediaPipe draws skeleton overlay on live video feed (no game yet)
2. **M2 — Skeleton renderer:** Replace raw video overlay with a clean stick-figure/avatar rendered in a Pygame window, driven by live local pose
3. **M3 — Single-player pole mode:** Implement hitboxes, static pole, collision detection, velocity-based hit registration, damage system, HUD. This is your first fully playable/testable build.
4. **M4 — Tune physics:** Playtest pole mode extensively; tune `MIN_STRIKE_VELOCITY`, damage values, cooldowns, block detection until it feels responsive and fair
5. **M5 — Networking layer:** Implement UDP sender/receiver in isolation, test with two terminal processes on same machine (loopback) printing received landmark data
6. **M6 — Multiplayer integration:** Replace the static pole with a second live networked player avatar, reuse the exact same collision/damage engine from M3
7. **M7 — Menu & polish:** Main menu, host/join screen, round timer, KO screen, sound effects
8. **M8 — Containerization:** Package everything into the Singularity image (see Section 6)

---

## 6. Singularity Container

Goal: a **single `.sif` file** that contains Python 3.11, all dependencies, and the full game — so anyone can run `singularity run shadowclash.sif` and immediately play, with only their webcam and display needing to be passed through.

### 6.1 `Singularity.def`

```singularity
Bootstrap: docker
From: ubuntu:22.04

%labels
    Author AbuSaadat
    Game SHADOWCLASH
    Version 1.0

%post
    export DEBIAN_FRONTEND=noninteractive

    apt-get update && apt-get install -y \
        python3.11 python3.11-venv python3.11-dev python3-pip \
        libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender1 \
        libx11-6 libxcb1 libxau6 libxdmcp6 \
        libasound2 libpulse0 \
        v4l-utils \
        ffmpeg \
        git \
        && rm -rf /var/lib/apt/lists/*

    python3.11 -m pip install --upgrade pip setuptools wheel

    mkdir -p /opt/shadowclash
    cd /opt/shadowclash

    # Game source is copied in via %files below

    python3.11 -m pip install --no-cache-dir -r /opt/shadowclash/requirements.txt

%files
    ./shadowclash /opt/shadowclash/shadowclash
    ./config /opt/shadowclash/config
    ./assets /opt/shadowclash/assets
    ./requirements.txt /opt/shadowclash/requirements.txt

%environment
    export PYTHONPATH=/opt/shadowclash:$PYTHONPATH
    export SDL_AUDIODRIVER=pulse
    export DISPLAY=$DISPLAY

%runscript
    echo "=================================================="
    echo "   SHADOWCLASH — Full-Body Mirror Fight Arena"
    echo "=================================================="
    echo "If the camera or window fails to open, see:"
    echo "  singularity run-help shadowclash.sif"
    echo "=================================================="
    cd /opt/shadowclash
    exec python3.11 -m shadowclash.main "$@"

%help
    SHADOWCLASH: motion-mirrored 2-player fighting game.

    Portable launch (any Linux PC with a webcam and desktop session):

      singularity run \
        --bind /tmp/.X11-unix \
        --bind /run/user/$(id -u) \
        --env DISPLAY=$DISPLAY \
        --env XAUTHORITY=$XAUTHORITY \
        shadowclash.sif

    (Do NOT bind /dev/video0 — see D-017 and section 6.3 notes.)

    Single-player training mode (kicking pole):
      singularity run shadowclash.sif --mode singleplayer

    Multiplayer host:
      singularity run shadowclash.sif --mode host --port 5555

    Multiplayer join (LAN IP or internet room token):
      singularity run shadowclash.sif --mode join --ip 192.168.1.42 --port 5555
      singularity run shadowclash.sif --mode join --ip A7K2QF
```

### 6.2 Build the container (`scripts/build_container.sh`)

```bash
#!/bin/bash
set -e
echo "Building SHADOWCLASH Singularity image..."
sudo singularity build shadowclash.sif Singularity.def
echo "Build complete: shadowclash.sif"
echo "Share this single file — recipients only need Singularity/Apptainer installed."
```

### 6.3 Running the container

Easiest: use the portable launcher, which auto-detects display/audio passthrough
on any Linux desktop (X11 or Wayland, PulseAudio or PipeWire):

```bash
./scripts/run_container.sh                              # menu
./scripts/run_container.sh --mode singleplayer          # training pole
./scripts/run_container.sh --mode host --port 5555
./scripts/run_container.sh --mode join --ip <HOST_IP or room token>
```

Equivalent manual command (D-017):

```bash
singularity run \
  --bind /tmp/.X11-unix \
  --bind /run/user/$(id -u) \
  --env DISPLAY=$DISPLAY \
  --env XAUTHORITY=$XAUTHORITY \
  shadowclash.sif [--mode ...]
```

**Notes for Linux hosts:**
- Do **not** pass `--bind /dev/video0` — Singularity mounts the host `/dev` by default, and a single-file device bind breaks camera access with EACCES (D-017)
- The `/run/user/$(id -u)` bind supplies the X11 auth cookie (Wayland/XWayland desktops) and the Pulse/PipeWire socket; on plain X11 hosts without `XAUTHORITY`, drop that `--env` and run `xhost +local:` once instead
- If the webcam is not device index 0 (check `v4l2-ctl --list-devices`), copy `config/game_config.yaml`, set `camera.index`, and pass `--config <path>`

### 6.4 Windows / macOS builds (D-018)

The `.sif` is Linux-only. For Windows and Mac, `shadowclash.spec` +
`.github/workflows/build-desktop.yml` build standalone PyInstaller bundles
(windows-x64, macos-arm64, macos-intel, linux-x64). Push the repo to GitHub and
trigger the workflow manually, or push a `v*` tag to get zips attached to a
release. Local Linux check of the same spec: `pyinstaller shadowclash.spec`
then `./dist/shadowclash/shadowclash`.
- On systems without a physical X server (e.g., pure headless servers), this game cannot run — it requires a local display for the Pygame window; this is a LAN party / same-room game by design, not a cloud/remote-desktop game

---

## 7. Local Development (without container)

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# M1-M3: run single-player pole mode
python -m shadowclash.main --mode singleplayer

# M5-M6: run multiplayer, two terminals on same machine for loopback testing
python -m shadowclash.main --mode host --port 5555
python -m shadowclash.main --mode join --ip 127.0.0.1 --port 5555
```

---

## 8. Configuration (`config/game_config.yaml`)

```yaml
camera:
  index: 0
  width: 640
  height: 480
  fps: 30

pose:
  min_detection_confidence: 0.6
  min_tracking_confidence: 0.6
  smoothing_alpha: 0.4

physics:
  min_strike_velocity: 3.0      # torso-lengths/sec (D-005), tune during M4
  reference_velocity: 6.0
  max_damage_multiplier: 1.5
  hit_cooldown_ms: 600

damage:
  head: 15
  torso: 8
  leg: 4
  block_reduction: 0.7

match:
  starting_hp: 100
  round_time_seconds: 99

network:
  default_port: 5555
  packet_rate_hz: 30
  peer_timeout_ms: 200

singleplayer:
  pole_hp: 100
  pole_regen_per_sec: 2
```

---

## 9. Testing Plan

1. **Unit tests** (`tests/`): landmark smoothing math, collision velocity calculation, damage formula, cooldown logic — pure functions, no camera/network required
2. **Manual test — M3 milestone:** Play single-player pole mode for at least 10 minutes; log false-positive hits (registered without a real strike) and false negatives (real kick not registered); adjust `min_strike_velocity` and `smoothing_alpha` accordingly
3. **Manual test — M6 milestone:** Two machines on same WiFi, run host/join, verify avatar sync latency feels real-time (<100ms perceived delay) and hits register correctly on both screens
4. **Container test:** Build `.sif`, run on a clean machine with only Singularity + a webcam installed, verify zero missing dependencies

---

## 10. Non-Goals for v1 (explicitly out of scope)

- No true 3D rendering (2D skeleton arena only)
- No server-authoritative netcode / rollback (acceptable desync tolerance for casual LAN play)
- No online matchmaking (LAN/same-WiFi only, as specified)
- No move classification/ML gesture recognition (removed by design — direct mirroring only)
- No character customization/skins in v1

---

## 11. Future Roadmap (post-v1, not for initial build)

- Add a third static training dummy with moving/swinging pole for dodge practice
- Optional cloud relay for internet play (would require true server-authoritative sync)
- 3D avatar upgrade using the MediaPipe→Unity pipeline pattern if 2D proves too limiting
- Replay recording/playback for reviewing matches
