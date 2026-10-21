"""End-to-end media and fade checks for the Windows release runner."""

from __future__ import annotations

import math
import struct
import subprocess
import tempfile
import time
import wave
from pathlib import Path

from PySide6.QtWidgets import QApplication

from main import PlayerWindow, ffmpeg_executable


def wait_until(app: QApplication, predicate, timeout: float = 8.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return False


def make_samples(folder: Path) -> list[Path]:
    wav = folder / "sample.wav"
    with wave.open(str(wav), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(44100)
        samples = (int(8000 * math.sin(2 * math.pi * 440 * i / 44100)) for i in range(88200))
        output.writeframes(b"".join(struct.pack("<h", sample) for sample in samples))

    ffmpeg = ffmpeg_executable()
    assert ffmpeg, "FFmpeg binary not available"
    mp3 = folder / "sample.mp3"
    wma = folder / "sample.wma"
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(wav), str(mp3)], check=True)
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(wav), "-c:a", "wmav2", str(wma)], check=True)
    return [wav, mp3, wma]


def main() -> None:
    app = QApplication([])
    with tempfile.TemporaryDirectory(prefix="hifamily-player-smoke-") as directory:
        samples = make_samples(Path(directory))
        window = PlayerWindow()
        window.fade_seconds.setValue(1)
        window.add_files(samples)
        assert len(window.paths) == 3
        for index, path in enumerate(samples):
            window.load_track(index)
            expected = path if path.suffix != ".wma" else None
            assert wait_until(
                app,
                lambda: (
                    window.player.source().isLocalFile()
                    and (expected is None or Path(window.player.source().toLocalFile()) == expected)
                    and not window.converting
                    and window.player.duration() >= 1800
                ),
            ), f"Could not load {path.suffix}"
            assert window.current == index
            print(f"OK {path.suffix}: {window.player.duration()} ms", flush=True)

        window._cancel_fade()
        window.auto_faded = True
        window.audio.setVolume(0.8)
        window._begin_fade(0.0, "")
        assert wait_until(app, lambda: not window.fade_timer.isActive(), timeout=3.0)
        assert window.audio.volume() <= 0.01, "Fade out did not reach silence"
        window.close()
    print("Windows smoke test passed", flush=True)


if __name__ == "__main__":
    main()
