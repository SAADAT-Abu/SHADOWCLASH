"""Sound effects: loads the procedurally generated wavs from assets/sounds.

Degrades gracefully — if the mixer can't initialize (headless test runs) or
files are missing, every play call becomes a no-op.
"""

from pathlib import Path

import pygame

from shadowclash.utils.logger import get_logger

log = get_logger(__name__)

SOUNDS_DIR = Path(__file__).resolve().parents[2] / "assets" / "sounds"


class SoundBank:
    def __init__(self):
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        try:
            pygame.mixer.init()
        except pygame.error as exc:
            log.warning("Audio unavailable (%s) — running silent", exc)
            return
        for name in ("hit_light", "hit_heavy", "block", "bell", "ko", "count"):
            path = SOUNDS_DIR / f"{name}.wav"
            if path.exists():
                self._sounds[name] = pygame.mixer.Sound(str(path))
        if not self._sounds:
            log.warning("No sound files in %s — run scripts/generate_sounds.py", SOUNDS_DIR)

    def _play(self, name: str) -> None:
        sound = self._sounds.get(name)
        if sound is not None:
            sound.play()

    def hit(self, zone: str, damage: float, blocked: bool) -> None:
        if blocked:
            self._play("block")
        elif zone == "head" or damage >= 10:
            self._play("hit_heavy")
        else:
            self._play("hit_light")

    def bell(self) -> None:
        self._play("bell")

    def ko(self) -> None:
        self._play("ko")

    def count(self) -> None:
        self._play("count")
