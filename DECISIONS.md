# DECISIONS.md — Deviations & Amendments to CLAUDE.md

Log of every deviation from the spec, with reasoning. Newest at bottom.

## D-001 — Python 3.12 instead of 3.11 (local dev)
**Date:** 2026-07-20
**What:** Local venv uses Python 3.12 (`/usr/bin/python3.12`); the host (Fedora) does not ship 3.11.
**Why:** CLAUDE.md itself states MediaPipe's compatibility ceiling is 3.12, so 3.12 is within spec. MediaPipe 0.10.14 publishes cp312 wheels. The container still targets a pinned Python for reproducibility (see D-002).

## D-002 — Singularity.def fix: deadsnakes PPA for python3.11
**What:** Ubuntu 22.04 repos do not contain a `python3.11` package (jammy ships 3.10). The spec's `%post` would fail at `apt-get install python3.11`. Added `software-properties-common` + `add-apt-repository ppa:deadsnakes/ppa` before installing python3.11, and `python3.11-distutils` for pip.
**Why:** Without this, M8 container build fails outright.

## D-003 — Threaded pose capture
**What:** `pose_capture.py` runs webcam grab + MediaPipe inference in a dedicated daemon thread; the game loop reads the most recent smoothed landmark set via a lock. Spec implied (did not forbid) inline capture.
**Why:** Pose inference costs ~20–40 ms/frame. Inline, it caps the entire game loop below ~30 FPS and adds input latency. Decoupling lets rendering/physics run at 60 FPS while capture runs at camera rate.

## D-004 — Damage authority split (multiplayer desync fix)
**What:** Spec assumed both clients compute identical damage from "the same landmark streams." They don't: each client pairs its *live* local pose against a *delayed* peer pose, so collision geometry differs per machine and HP diverges. Amendment: each client is authoritative for damage **dealt by its local player**; damage events (zone, amount, event seq) are piggybacked on the UDP landmark packets and applied idempotently by the peer.
**Why:** Prevents silent HP divergence with zero extra round-trips; keeps the no-server design.

## D-005 — Torso-normalized strike velocity
**What:** Strike velocity is measured in units of *torso lengths per second* (torso = mean shoulder→hip distance), not raw normalized-camera units.
**Why:** Raw normalized velocity scales with how close the player stands to the webcam; a close player would trigger hits by twitching. Torso normalization makes `min_strike_velocity` framing-invariant.

## D-006 — Binary protocol with sequence numbers
**What:** `struct.pack` binary packets (spec already preferred binary) with a header: magic, version, player_id, packet seq, timestamp — plus appended damage events (D-004). Receiver drops packets older than the last seen seq.
**Why:** UDP reorders; without seq filtering the peer avatar visibly jumps backwards in time.

## D-007 — Mirror-flip camera frame at capture
**What:** Frames are `cv2.flip(frame, 1)`-ed before MediaPipe so the avatar behaves like a mirror (raise right hand → avatar on your right raises hand).
**Why:** Without it every lateral movement feels reversed; this is the standard fix for camera-driven avatars.

## D-009 — pymunk 6.11.1 instead of 6.6.2
**What:** The spec's pin `pymunk==6.6.2` does not exist on PyPI (only 6.6.0 exists in the 6.6 line). Using 6.11.1, the last 6.x release.
**Why:** Same 6.x `add_collision_handler` API as the spec assumes (7.x changed it), and it ships Python 3.12 wheels.

## D-011 — MediaPipe Holistic for real finger tracking
**Date:** 2026-07-20
**What:** Capture switched from `mp.solutions.pose` to `mp.solutions.holistic`, which adds 21 true landmarks per hand on top of the 33 pose landmarks. The landmark array is now (75, 4): rows 0-32 pose, 33-53 left hand, 54-74 right hand (visibility 1.0 while tracked, 0.0 when the hand is lost; the smoother holds last-known positions across dropouts and snaps on reappearance). The renderer draws real per-finger bones when hand data is live and falls back to the stylized knuckle hand otherwise. Wire protocol bumped to v2 with 75 landmarks (~1.2 KB/packet, still trivial for LAN). Physics still keys strikes off the wrist/ankle pose landmarks, so hit tuning is unaffected.
**Why:** User feedback — extrapolated fingers from pose-only knuckle points looked wrong; punches/slaps need real hand articulation. Costs extra inference per frame, absorbed by the capture thread (D-003).

## D-012 — Hand tracking optional, match-creator settings panel
**Date:** 2026-07-20
**What:** After playtesting, Holistic finger tracking (D-011) felt slow, so hand tracking is now a toggle, default **off** (pose-only capture + stylized hands — fastest path). The match creator (singleplayer or host) gets a settings panel before the camera starts: hand tracking on/off, model complexity (Fast/Balanced/Accurate), camera FPS (15/30/60). Both capture paths fill the same 75-landmark array (pose-only leaves hand rows at visibility 0), so the renderer and the v2 wire protocol are unchanged — the peer automatically renders whatever level of hand detail the other side streams, no settings handshake needed.
**Why:** User feedback: Holistic is "a bit slow but usable" — quality/perf should be the player's choice per match, not hardcoded. (Spec's "no customization in v1" non-goal refers to skins; performance settings were explicitly requested.)

## D-013 — Polish pass: fight scene, sounds, VS mode, bot input
**Date:** 2026-07-20
**What:** (a) `ui/scene.py`: cached dusk-dojo background (gradient sky, moon, mountain/pagoda silhouettes, plank floor, lanterns, vignette), fighter ground shadows, additive hit-spark particles — used by every mode and as the menu backdrop. (b) Procedural sound effects generated by `scripts/generate_sounds.py` (numpy synthesis, no external samples) played via `ui/sound.py` on hits/blocks/bell/KO; silent-degrades when audio is unavailable. (c) `capture/synthetic_pose.py`: an animated synthetic fighter (guard stance, sway, punches/kicks above the strike threshold) that powers both the new **Versus — Shadow Fighter** single-player mode (`modes/singleplayer_vs.py`, full match rules: timer, KO, rematch) and `--input bot` for automated multiplayer testing. (d) Menus/settings/start screens restyled over the scene backdrop via shared `ui/theme.py`.
**Why:** User direction after playtests: pole mode alone is a sandbox, not a game; graphics needed a real scene; hits needed audio feedback; and multiplayer needed an automated two-instance test (verified over loopback: hits dealt on each side exactly equal hits taken on the other).

## D-014 — Villain ladder, post-KO fix, distance coach, menu upgrades
**Date:** 2026-07-20
**What:** (a) VS mode is now a 10-level ladder of named villains (STREET PUNK → SHADOW KING) with escalating attack rate and strike speed (faster strikes hit harder since damage scales with velocity); the opponent's health bar shows the villain's name and each has its own skeleton color. Beating a boss unlocks the next via R. (b) Bug fix: the bot kept swinging after KO — damage was already gated, but the animation wasn't; `SyntheticPoseDriver.fighting = False` now drops it to idle when the round ends. (c) Distance coach in VS and multiplayer: compares the player's torso length to the opponent's and shows "step CLOSER/BACK from the camera" when the ratio leaves [0.8, 1.25], so both fighters render at the same scale. (d) Main menu: mouse hover/click support, selection highlight, footer hints, and a live sparring shadow fighter in the backdrop.
**Why:** User feedback and feature requests after playing the first VS build.

## D-015 — Expanded boss move-set + Tekken-style joined-hands guard
**Date:** 2026-07-20
**What:** (a) `SyntheticPoseDriver` gained a weighted move system: jab, slap (arcing swing; fills the 21 real hand landmarks with an open palm when the hand-tracking setting is on), kick, flying kick (airborne, whole body lifts, leg extends high), and somersault (full 360° body flip — spinning limbs strike at close range). Each villain has its own `move_weights`; the ladder introduces moves progressively (slaps from level 1, kicks from 2, flying kicks from 5, somersaults from 7). Body landmarks are clipped to [0,1] so airborne moves can't leave the frame. (b) New defense: `is_guarding` — both wrists joined (within 0.35 torso-lengths) held above hip height near the body's center line counts as a Tekken-style guard and blocks head/torso hits (same 70% reduction), in addition to the existing raised-forearm block. Works for the player in every mode and over the network (block detection runs on the defender's pose stream).
**Why:** User request: bosses felt punch-only, and blocking needed an intentional, readable gesture.

## D-010 — Query-based hit detection instead of pymunk collision handlers
**What:** The spec calls for `collision_begin` callbacks. Chipmunk2D (pymunk's core) never generates collisions between two non-dynamic bodies — and pose-driven hitboxes are exactly that (shapes teleported to landmark positions each frame, no simulated dynamics). Handler callbacks would never fire against the STATIC pole. Instead, receiving zones (head/torso/legs) are pymunk shapes kept in the space, and each frame every striking limb runs a `space.point_query` (point + strike radius, category-filtered). Velocity gating, per-limb-pair cooldowns, and damage flow are unchanged from spec.
**Why:** Correctness (handlers silently never fire for static-vs-static), plus it re-evaluates velocity every frame of contact, so a strike that accelerates mid-contact still registers.

## D-008 — Physics runs in normalized arena space
**What:** Pymunk coordinates are normalized arena units (x ∈ [0,1], y ∈ [0,1], y down), renderer scales to pixels. Config thresholds stay in normalized units as written.
**Why:** Keeps config values resolution-independent; pymunk is unit-agnostic.
