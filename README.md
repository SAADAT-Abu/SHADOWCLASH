# SHADOWCLASH

*Your body is the controller. Your shadow is your fighter.*

SHADOWCLASH is a full-body motion fighting game. Your webcam tracks your real
punches, kicks and blocks and mirrors them 1:1 onto your in-game fighter. No
gamepad, no buttons: if you throw a punch, your shadow throws a punch. Fight a
ladder of 10 AI villains, train on a kicking pole, or battle another player
over LAN or the internet.

**Game modes**

- **Single Player**: beat 10 villains with rising difficulty, from STREET PUNK
  to SHADOW KING
- **Training**: practice strikes on a kicking pole with a live debug overlay
- **VS Mode**: fight another player. On the same network, join by IP. Across
  the internet, the host gets a 6-letter room token the other player types in.
  No port forwarding needed.

**How fighting works**: faster strikes deal more damage. Head hits hurt most,
leg hits least. Raise your forearms or join both hands in front of you (like a
Tekken guard) to block. Stand back so your whole body is in the camera frame.

---

## How to Setup and Play

### Windows

1. Download `shadowclash-windows-x64.zip` from the
   [latest release](https://github.com/SAADAT-Abu/SHADOWCLASH/releases/latest).
2. Extract the zip anywhere.
3. Run `shadowclash.exe` inside the extracted folder.
4. If SmartScreen warns about an unknown publisher, click **More info**, then
   **Run anyway**. Allow camera access if Windows asks.

### macOS

1. Download `shadowclash-macos-arm64.zip` (Apple Silicon, M1 or newer) from the
   [latest release](https://github.com/SAADAT-Abu/SHADOWCLASH/releases/latest).
   Intel Macs: use "Running from source" below instead.
2. Extract the zip, then open Terminal in the extracted folder and run:

   ```bash
   xattr -dr com.apple.quarantine shadowclash
   ./shadowclash/shadowclash
   ```

   (The `xattr` line is needed once, because the app is not notarized by
   Apple.)
3. Allow camera access when macOS asks.

### Linux

**Option A, container image (recommended):** a single file with everything
inside, runs on any distro with [Apptainer](https://apptainer.org) installed.
Download it from [Zenodo](https://zenodo.org/records/21469739) and see
[PLAY_ON_LINUX.md](PLAY_ON_LINUX.md) for the two-command setup and
troubleshooting.

**Option B, release bundle:** download `shadowclash-linux-x64.zip` from the
[latest release](https://github.com/SAADAT-Abu/SHADOWCLASH/releases/latest),
extract, and run `./shadowclash/shadowclash`.

### Running from source (any OS)

```bash
git clone https://github.com/SAADAT-Abu/SHADOWCLASH.git
cd SHADOWCLASH
python3.11 -m venv ~/.venvs/shadowclash
source ~/.venvs/shadowclash/bin/activate   # Windows: %USERPROFILE%\shadowclash-venv\Scripts\activate
pip install -r requirements.txt
python -m shadowclash.main
```

---

## Playing with a friend over the internet

1. One player picks **VS Mode, Host** and reads out the 6-letter room token
   shown on the waiting screen.
2. The other picks **VS Mode, Join** and types the token (or the host's IP if
   you are on the same network).
3. The host picks how many rounds the match runs (best of 3, 5 or 7) in the
   settings panel; the joiner picks that up automatically.
4. Once both players are in, a 30 second countdown runs, then the fight
   starts. The same countdown separates each round.

Both players must run the **same version** of the game. VS Mode uses a
versioned network protocol, so a v1.0.0 build cannot see a v1.0.1 build.

## Requirements

- A webcam and a reasonably modern CPU (pose tracking runs on CPU)
- A desktop session (the game opens a window; it cannot run headless)
- For internet VS Mode: an open internet connection, UDP traffic allowed
