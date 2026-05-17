"""JARVIS desktop helper — system-wide "Hey JARVIS" wake word for macOS.

Runs as a background daemon. Listens to the default microphone continuously.
When it hears "hey jarvis" / "ok jarvis" / "yo jarvis", it records the next
~8 seconds of speech, POSTs to your deployed /jarvis/converse endpoint, and
speaks the reply back through macOS `say`.

Works from anywhere — terminal, Slack, fullscreen video, locked-ish Mac
(as long as the daemon is running and not killed by lid-close).

Stack:
  * SpeechRecognition (PyPI) — wraps Google's free streaming STT for the
    wake-word loop. Free, no API key, works offline-when-online.
  * sounddevice + numpy — record the actual query audio after the wake.
  * requests — POST to the backend.
  * subprocess + macOS `say` — speak the reply (no install).

Install (one time):
  brew install portaudio                 # mic backend
  pip3 install --user SpeechRecognition pyaudio sounddevice numpy requests

Run interactively (to see logs):
  JARVIS_API_BASE=https://your-fly-url \\
  JARVIS_TOKEN=user:cap-brij \\
  python3 jarvis-desktop/listener.py

Run as login daemon: copy `com.capbrij.jarvis.plist` to ~/Library/LaunchAgents/
and run `launchctl load ~/Library/LaunchAgents/com.capbrij.jarvis.plist`.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

import requests
import sounddevice as sd
import speech_recognition as sr

# ---------- configuration --------------------------------------------------

API_BASE   = os.environ.get("JARVIS_API_BASE", "https://your-fly-url.fly.dev").rstrip("/")
TENANT     = os.environ.get("JARVIS_TENANT", "jarvis")
TOKEN      = os.environ.get("JARVIS_TOKEN", "user:cap-brij")
SAMPLE_RATE = int(os.environ.get("JARVIS_SAMPLE_RATE", "16000"))
QUERY_SECS = int(os.environ.get("JARVIS_QUERY_SECS", "8"))
WAKE_PHRASES = ("hey jarvis", "ok jarvis", "okay jarvis", "yo jarvis", "hi jarvis")

# Quieter logging in the daemon mode; flip to DEBUG for diagnostics.
logging.basicConfig(
    level=os.environ.get("JARVIS_LOG_LEVEL", "INFO"),
    format="%(asctime)s [jarvis-desktop] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


# ---------- helpers --------------------------------------------------------

def say(text: str) -> None:
    """Speak via macOS `say`. Truncate to keep it punchy."""
    short = text[:600]
    log.info("JARVIS: %s", short[:120])
    subprocess.Popen(
        ["say", "-v", "Daniel", "-r", "200", short],  # Daniel = en-GB voice
    )


def record_query(seconds: int = QUERY_SECS) -> Path:
    """Record `seconds` of mic audio to a temp .wav. Returns the path."""
    log.info("recording %ds…", seconds)
    audio = sd.rec(
        int(seconds * SAMPLE_RATE),
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
    )
    sd.wait()
    tmp = Path(tempfile.gettempdir()) / f"jarvis-query-{int(time.time())}.wav"
    with wave.open(str(tmp), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    return tmp


def transcribe(wav_path: Path) -> str | None:
    """STT via Google's free recognizer (no key)."""
    rec = sr.Recognizer()
    with sr.AudioFile(str(wav_path)) as src:
        audio = rec.record(src)
    try:
        return rec.recognize_google(audio, language="en-IN")
    except (sr.UnknownValueError, sr.RequestError) as exc:
        log.warning("STT failed: %s", exc)
        return None


def ask_jarvis(query: str) -> dict | None:
    """POST to /jarvis/converse. Returns the parsed JSON or None on error."""
    url = f"{API_BASE}/api/avengers/tenants/{TENANT}/jarvis/converse"
    try:
        r = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            json={"query": query, "voice_mode": True},
            timeout=45,
        )
        r.raise_for_status()
        return r.json()
    except requests.RequestException as exc:
        log.error("converse failed: %s", exc)
        return None


def matches_wake(transcript: str) -> bool:
    t = transcript.lower()
    return any(w in t for w in WAKE_PHRASES)


# ---------- main loop ------------------------------------------------------

def listen_for_wake() -> None:
    """Continuously listen for the wake phrase via SpeechRecognition's
    streaming recognizer. On match, record the query and round-trip to JARVIS.
    """
    rec = sr.Recognizer()
    rec.dynamic_energy_threshold = True
    mic = sr.Microphone(sample_rate=SAMPLE_RATE)

    with mic as src:
        log.info("calibrating ambient noise for 1s…")
        rec.adjust_for_ambient_noise(src, duration=1.0)
        log.info("ready. Say 'Hey JARVIS' from anywhere.")

        while True:
            try:
                # Phrase-based listening so we get a chunk per utterance.
                audio = rec.listen(src, timeout=None, phrase_time_limit=5)
            except sr.WaitTimeoutError:
                continue
            try:
                heard = rec.recognize_google(audio, language="en-IN")
            except sr.UnknownValueError:
                continue
            except sr.RequestError as exc:
                log.warning("STT request failed (network?): %s — sleeping 2s", exc)
                time.sleep(2)
                continue

            log.debug("heard: %s", heard)
            if not matches_wake(heard):
                continue

            log.info("wake word detected: %r", heard)
            say("Yes Cap Brij.")
            time.sleep(0.4)  # let the say() finish before recording

            wav = record_query()
            query = transcribe(wav)
            wav.unlink(missing_ok=True)
            if not query:
                say("I didn't catch that, Cap Brij.")
                continue

            log.info("query: %s", query)
            resp = ask_jarvis(query)
            if not resp:
                say("JARVIS backend is unreachable.")
                continue
            say(resp.get("speakable") or resp.get("text") or "Nothing to report.")


def main() -> int:
    if API_BASE == "https://your-fly-url.fly.dev":
        log.error(
            "JARVIS_API_BASE is unset. Set it to your deployed backend URL, e.g.:\n"
            "  export JARVIS_API_BASE=https://avengers-api.fly.dev\n"
            "  export JARVIS_TOKEN=user:cap-brij\n"
            "  python3 jarvis-desktop/listener.py"
        )
        return 1
    try:
        listen_for_wake()
    except KeyboardInterrupt:
        log.info("bye Cap Brij.")
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
