"""Re-synthesise a note at the natural speaking rate.

A note synthesised faster than 1x (because a chat channel without a speed control got
the speed baked in) cannot be played cleanly at 1x: slowing synthetic speech down is
what sounds metallic. This asks the kit's voice-note.py for a new recording of the same
text at 1.0 (no delivery, no hub registration) and swaps it in.

One note costs its text length in TTS characters (about 1.500), which is why this runs
on demand from the player, or in bulk only with an explicit `avh resynth --all`.
"""

import os
import subprocess
import sys
import tempfile

from .store import segment_timeline


def resynth(store, cfg, note):
    text = (note.get("spoken") or note.get("text") or "").strip()
    if not text:
        raise RuntimeError("this note has no text, so it cannot be re-recorded")
    script = os.path.expanduser(cfg.get("AVH_VOICE_NOTE") or "")
    if not os.path.exists(script):
        raise RuntimeError("voice-note.py not found at %s (set AVH_VOICE_NOTE)" % script)
    fd, out = tempfile.mkstemp(suffix=".ogg")
    os.close(fd)
    try:
        cmd = [sys.executable, script, "--no-send", "--no-hub", "--no-opener",
               "--speed", "1.0", "--lang", note.get("lang") or "en", "--out", out,
               "--file", "-"]
        if note.get("voice"):
            cmd += ["--voice", note["voice"]]
        proc = subprocess.run(cmd, input=text.encode("utf-8"), stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=600)
        if proc.returncode != 0 or not os.path.getsize(out):
            raise RuntimeError("synthesis failed: %s"
                               % proc.stderr.decode("utf-8", "replace").strip()[-200:])
        return store.replace_audio(note["id"], out, speech_rate=1.0, spoken=text)
    finally:
        try:
            os.unlink(out)
        except OSError:
            pass


def chars_needed(notes):
    return sum(len((n.get("spoken") or n.get("text") or "")) for n in notes)
