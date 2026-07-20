"""Procedurally generates the game's sound effects into assets/sounds/.

Run once (or after tweaking): python scripts/generate_sounds.py
Pure numpy synthesis — no external sample dependencies.
"""

import wave
from pathlib import Path

import numpy as np

SR = 44100
OUT_DIR = Path(__file__).resolve().parents[1] / "assets" / "sounds"


def save(name: str, samples: np.ndarray) -> None:
    samples = samples / (np.max(np.abs(samples)) + 1e-9)
    pcm = (samples * 0.85 * 32767).astype(np.int16)
    with wave.open(str(OUT_DIR / name), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(pcm.tobytes())
    print(f"wrote {name} ({len(samples) / SR:.2f}s)")


def t_axis(duration: float) -> np.ndarray:
    return np.linspace(0, duration, int(SR * duration), endpoint=False)


def thump(freq: float, duration: float, punch_noise: float) -> np.ndarray:
    """Low-frequency body impact: decaying sine with a pitch drop + noise snap."""
    t = t_axis(duration)
    sweep = freq * (1.0 - 0.4 * t / duration)
    body = np.sin(2 * np.pi * sweep * t) * np.exp(-t * 18)
    noise = np.random.default_rng(1).normal(0, 1, len(t)) * np.exp(-t * 90) * punch_noise
    return body + noise


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)

    save("hit_light.wav", thump(120, 0.18, 0.5))
    save("hit_heavy.wav", thump(75, 0.30, 0.8))

    # Block: short bright slap, no body
    t = t_axis(0.09)
    slap = rng.normal(0, 1, len(t)) * np.exp(-t * 70)
    save("block.wav", np.diff(slap, prepend=0.0))  # differencing = crude high-pass

    # Round-start bell: bright partials, medium decay
    t = t_axis(1.1)
    bell = sum(a * np.sin(2 * np.pi * f * t) for f, a in [(660, 1.0), (1320, 0.6), (1975, 0.35)])
    save("bell.wav", bell * np.exp(-t * 4))

    # KO gong: dense low partials, long decay, soft noise attack
    t = t_axis(2.4)
    gong = sum(
        a * np.sin(2 * np.pi * f * t + p)
        for f, a, p in [(140, 1.0, 0.0), (211, 0.7, 1.1), (287, 0.5, 2.3), (395, 0.35, 0.4)]
    )
    attack = rng.normal(0, 1, len(t)) * np.exp(-t * 40) * 0.4
    save("ko.wav", (gong + attack) * np.exp(-t * 1.6))


if __name__ == "__main__":
    main()
