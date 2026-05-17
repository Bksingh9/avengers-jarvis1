"""Intent dispatcher — turns spoken English into Mac-side actions.

Runs LOCALLY (no backend round-trip). Every intent has:
  * a list of phrase patterns that match flexible English
  * a handler that does the actual work via macOS shell commands
  * an ack JARVIS speaks before/instead of the cloud reply

If the spoken query matches no intent, the dispatcher returns None and the
caller falls back to the conversational /jarvis/converse endpoint — so the
Cap Brij experience is action-first, chat-fallback. Exactly how a real
voice assistant behaves.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
import webbrowser
from dataclasses import dataclass
from typing import Callable

# ---------------------------------------------------------------------------
# Configuration — what URLs / paths the intents open
# ---------------------------------------------------------------------------

DASHBOARD_BASE = os.environ.get(
    "JARVIS_DASHBOARD_BASE",
    "https://avengers-jarvis1-git-main-trends-nps.vercel.app",
).rstrip("/")

# Used to call backend endpoints for action-style intents like "run a brief".
API_BASE = os.environ.get("JARVIS_API_BASE", "").rstrip("/")
API_PATH_PREFIX = os.environ.get("JARVIS_API_PATH_PREFIX", "")
TOKEN = os.environ.get("JARVIS_TOKEN", "user:cap-brij")
TENANT = os.environ.get("JARVIS_TENANT", "jarvis")


# ---------------------------------------------------------------------------
# Helpers — Mac-side primitives the handlers compose
# ---------------------------------------------------------------------------

def _say(text: str, voice: str = "Daniel") -> None:
    """Speak via macOS `say` — non-blocking. Daniel = en-GB voice."""
    subprocess.Popen(["say", "-v", voice, "-r", "200", text[:600]])


def _open_url(url: str) -> None:
    """Open in the default browser. macOS uses `open`, falls back to webbrowser."""
    try:
        subprocess.run(["open", url], check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        webbrowser.open(url)


def _open_app(app_name: str) -> None:
    """`open -a "App Name"` — launches any macOS .app."""
    subprocess.Popen(["open", "-a", app_name])


def _notify(title: str, body: str) -> None:
    """Native macOS notification via AppleScript — works without extra deps."""
    safe_title = title.replace('"', "'")
    safe_body = body.replace('"', "'")
    script = f'display notification "{safe_body}" with title "{safe_title}"'
    subprocess.Popen(["osascript", "-e", script])


def _media(command: str) -> None:
    """Control any active media app (Music, Spotify, Safari video) via Media Keys.

    `pmset` won't work for this; use AppleScript's `key code` for the media keys.
    Key codes: play/pause = 16 (using NSEvent system-defined event 8 actually),
    but the simplest cross-app path is `osascript` telling Music/Spotify directly,
    or just the universal play/pause via cliclick if installed. Falling back to
    `osascript`'s tell-application-Music approach.
    """
    if command == "play":
        subprocess.Popen(["osascript", "-e", 'tell application "Music" to play'])
    elif command == "pause":
        subprocess.Popen(["osascript", "-e", 'tell application "Music" to pause'])
    elif command == "next":
        subprocess.Popen(["osascript", "-e", 'tell application "Music" to next track'])


def _api_post(path: str, body: dict | None = None) -> tuple[bool, str]:
    """Fire-and-forget POST. Returns (ok, message)."""
    import requests  # local import to keep startup cheap
    if not API_BASE:
        return False, "API base not configured"
    url = f"{API_BASE}{API_PATH_PREFIX}{path}"
    try:
        r = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            json=body or {},
            timeout=30,
        )
        r.raise_for_status()
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


# ---------------------------------------------------------------------------
# Intent registry
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class IntentResult:
    handled: bool
    spoken: str = ""           # text JARVIS says back
    quiet: bool = False        # if True, don't speak (e.g. mute commands)


Handler = Callable[[str, dict], IntentResult]


@dataclass(slots=True)
class Intent:
    name: str
    patterns: list[re.Pattern]
    handler: Handler
    description: str = ""


def _r(*pats: str) -> list[re.Pattern]:
    """Compile a list of regex patterns, case-insensitive."""
    return [re.compile(p, re.IGNORECASE) for p in pats]


# ---- Handlers --------------------------------------------------------------

def _open_dashboard(_q: str, _m: dict) -> IntentResult:
    _open_url(f"{DASHBOARD_BASE}/dashboard")
    return IntentResult(True, "Opening the dashboard, Cap Brij.")


def _open_jarvis_page(_q: str, _m: dict) -> IntentResult:
    _open_url(f"{DASHBOARD_BASE}/jarvis")
    return IntentResult(True, "Opening JARVIS, Cap Brij.")


def _open_agents(_q: str, _m: dict) -> IntentResult:
    _open_url(f"{DASHBOARD_BASE}/agents")
    return IntentResult(True, "Opening agents.")


def _open_approvals(_q: str, _m: dict) -> IntentResult:
    _open_url(f"{DASHBOARD_BASE}/approvals")
    return IntentResult(True, "Opening approvals.")


def _open_audit(_q: str, _m: dict) -> IntentResult:
    _open_url(f"{DASHBOARD_BASE}/audit")
    return IntentResult(True, "Opening audit.")


def _open_settings(_q: str, _m: dict) -> IntentResult:
    _open_url(f"{DASHBOARD_BASE}/settings")
    return IntentResult(True, "Opening settings.")


def _run_brief(_q: str, _m: dict) -> IntentResult:
    ok, msg = _api_post(f"/tenants/{TENANT}/briefs", {})
    if ok:
        _notify("JARVIS", "Morning brief generated.")
        return IntentResult(True, "Brief generated, Cap Brij. Notification sent.")
    return IntentResult(True, f"Couldn't generate brief: {msg}")


def _run_proactive(_q: str, _m: dict) -> IntentResult:
    ok, msg = _api_post(f"/tenants/{TENANT}/jarvis/proactive", {})
    if ok:
        return IntentResult(True, "Pulling your proactive push now.")
    return IntentResult(True, f"Proactive push failed: {msg}")


def _what_time(_q: str, _m: dict) -> IntentResult:
    now = time.strftime("%I:%M %p")
    return IntentResult(True, f"It's {now}, Cap Brij.")


def _what_day(_q: str, _m: dict) -> IntentResult:
    today = time.strftime("%A, %B %d")
    return IntentResult(True, f"It's {today}.")


def _stop(_q: str, _m: dict) -> IntentResult:
    # Kill any in-flight `say` processes
    subprocess.Popen(["killall", "say"])
    return IntentResult(True, quiet=True)


def _play_music(_q: str, _m: dict) -> IntentResult:
    _media("play")
    return IntentResult(True, "Playing music.")


def _pause_music(_q: str, _m: dict) -> IntentResult:
    _media("pause")
    return IntentResult(True, "Paused.")


def _next_track(_q: str, _m: dict) -> IntentResult:
    _media("next")
    return IntentResult(True, "Next track.")


def _open_app_intent(_q: str, m: dict) -> IntentResult:
    """Open any Mac app by name. Match group `app` captures the name."""
    app = m.get("app", "").strip().rstrip(".").title()
    if not app:
        return IntentResult(True, "Which app, Cap Brij?")
    _open_app(app)
    return IntentResult(True, f"Opening {app}.")


def _open_url_intent(_q: str, m: dict) -> IntentResult:
    """Open any URL or known site."""
    target = m.get("url", "").strip().lower().rstrip(".")
    SHORTCUTS = {
        "github":     "https://github.com",
        "gmail":      "https://mail.google.com",
        "calendar":   "https://calendar.google.com",
        "vercel":     "https://vercel.com/dashboard",
        "render":     "https://dashboard.render.com",
        "notion":     "https://notion.so",
        "jira":       "https://atlassian.com",
        "linear":     "https://linear.app",
        "slack":      "https://slack.com",
        "chatgpt":    "https://chatgpt.com",
        "claude":     "https://claude.ai",
        "youtube":    "https://youtube.com",
        "google":     "https://google.com",
    }
    if target in SHORTCUTS:
        _open_url(SHORTCUTS[target])
        return IntentResult(True, f"Opening {target}.")
    if target.startswith("http"):
        _open_url(target)
        return IntentResult(True, "Opening that link.")
    # Last resort — Google search
    _open_url(f"https://google.com/search?q={target}")
    return IntentResult(True, f"Searching for {target}.")


def _hello(_q: str, _m: dict) -> IntentResult:
    """When the user just says 'hey jarvis' with nothing else."""
    return IntentResult(True, "Yes Cap Brij?")


def _ack(_q: str, _m: dict) -> IntentResult:
    return IntentResult(True, "Acknowledged.")


def _capabilities(_q: str, _m: dict) -> IntentResult:
    return IntentResult(
        True,
        "I can open the dashboard, JARVIS page, agents, approvals, "
        "audit, or settings. I can run a brief, control music, "
        "open apps, search the web, or answer questions citing your data.",
    )


# ---- Registry --------------------------------------------------------------

INTENTS: list[Intent] = [
    # Navigation
    Intent("open_dashboard", _r(
        r"\b(open|show|bring up)\s+(the\s+)?dashboard\b",
        r"\b(my|the)\s+brief\s+(page|today|now)\b",
    ), _open_dashboard, "Open the morning-brief dashboard"),

    Intent("open_jarvis_page", _r(
        r"\bopen\s+(the\s+)?jarvis\s+(page|app|ui)\b",
    ), _open_jarvis_page, "Open the JARVIS chat page"),

    Intent("open_agents", _r(
        r"\b(open|show)\s+(my\s+)?agents?\b",
        r"\bagent\s+registry\b",
    ), _open_agents, "Open agents registry"),

    Intent("open_approvals", _r(
        r"\b(open|show)\s+(my\s+)?approvals?\b",
        r"\bapproval\s+queue\b",
    ), _open_approvals, "Open approvals queue"),

    Intent("open_audit", _r(
        r"\b(open|show)\s+(the\s+)?audit\b",
        r"\baudit\s+log\b",
    ), _open_audit, "Open audit log"),

    Intent("open_settings", _r(
        r"\b(open|show)\s+settings\b",
    ), _open_settings, "Open settings"),

    # Actions
    Intent("run_brief", _r(
        r"\b(run|generate|create|trigger)\s+(my\s+)?(morning\s+)?brief\b",
        r"\bgive\s+me\s+(my\s+)?(morning\s+)?brief\b",
        r"\bbrief\s+me\s+now\b",
    ), _run_brief, "Generate a new morning brief"),

    Intent("run_proactive", _r(
        r"\bwhat\s+(do\s+i\s+need\s+to\s+know|should\s+i\s+(do|look\s+at))\b",
        r"\banything\s+(urgent|important|to\s+know)\b",
    ), _run_proactive, "Pull a proactive what-you-need-to-know"),

    # Time / status
    Intent("what_time", _r(
        r"\bwhat(\'s|\s+is)\s+the\s+time\b",
        r"\bwhat\s+time\s+is\s+it\b",
    ), _what_time),

    Intent("what_day", _r(
        r"\bwhat\s+day\s+is\s+(it|today)\b",
        r"\btoday\'s\s+date\b",
    ), _what_day),

    # Control
    Intent("stop", _r(
        r"\b(stop|shut\s+up|quiet|silence|enough)\b",
    ), _stop, "Stop speaking"),

    # Media
    Intent("play_music", _r(
        r"\bplay\s+(some\s+)?music\b",
        r"\bresume\s+(music|playback)\b",
    ), _play_music, "Resume Music.app"),

    Intent("pause_music", _r(
        r"\bpause\s+(the\s+)?music\b",
        r"\bpause\s+(playback|the\s+song)\b",
    ), _pause_music, "Pause Music.app"),

    Intent("next_track", _r(
        r"\b(next|skip)\s+(track|song)\b",
    ), _next_track, "Skip to next track"),

    # Generic open-X
    Intent("open_app", _r(
        r"\bopen\s+(?P<app>[A-Za-z0-9 ]+?)\s+app\b",
        r"\blaunch\s+(?P<app>[A-Za-z0-9 ]+)\b",
    ), _open_app_intent, "Open any Mac app"),

    Intent("open_url", _r(
        r"\bopen\s+(?P<url>github|gmail|calendar|vercel|render|notion|jira|linear|slack|chatgpt|claude|youtube|google)\b",
        r"\bsearch\s+(for\s+)?(?P<url>.+?)$",
    ), _open_url_intent, "Open known site or web-search"),

    # Meta
    Intent("hello", _r(
        r"^(hey|hi|hello|yo)\s+jarvis[\s,.!?]*$",
        r"^jarvis[\s,.!?]*$",
    ), _hello, "Acknowledge wake without action"),

    Intent("ack", _r(
        r"^(ok|okay|cool|thanks|thank\s+you)[\s,.!?]*$",
    ), _ack),

    Intent("capabilities", _r(
        r"\bwhat\s+can\s+you\s+do\b",
        r"\bwhat\s+are\s+your\s+(capabilities|powers|skills)\b",
    ), _capabilities, "Tell user what's possible"),
]


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def dispatch(query: str) -> IntentResult | None:
    """Try each intent in order. Return the first match, or None if nothing fits.

    Order matters: more specific patterns come first. Generic `open <app>`
    and web-search are last so they don't shadow more specific intents.
    """
    if not query or not query.strip():
        return None

    cleaned = query.strip().lower()
    for intent in INTENTS:
        for pat in intent.patterns:
            m = pat.search(cleaned)
            if m:
                return intent.handler(query, m.groupdict())
    return None
