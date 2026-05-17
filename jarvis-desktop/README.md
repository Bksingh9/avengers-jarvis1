# JARVIS Desktop Helper — "Hey JARVIS" from anywhere on macOS

A 200-line Python daemon that listens for "Hey JARVIS" continuously on your
Mac and round-trips your spoken question to the deployed JARVIS backend.
Works from any app, full-screen, locked screen (as long as the daemon is
running) — no browser needed.

## Install (one time)

```bash
# 1. System mic backend
brew install portaudio

# 2. Python deps (use your normal pip; works with anaconda)
pip3 install --user SpeechRecognition pyaudio sounddevice numpy requests

# 3. Permissions
#    System Settings → Privacy & Security → Microphone → allow Terminal.app
#    (or whichever shell you'll run this from). For launchd autostart,
#    allow /usr/bin/python3 too.
```

## Run interactively first to confirm it works

```bash
cd ~/thrive-record-hub/avengers
export JARVIS_API_BASE=https://avengers-api.fly.dev    # ← your Fly URL
export JARVIS_TOKEN=user:cap-brij
export JARVIS_LOG_LEVEL=DEBUG                          # optional, more verbose
python3 jarvis-desktop/listener.py
```

You should see `ready. Say 'Hey JARVIS' from anywhere.`

Try it: say **"Hey JARVIS, what broke overnight?"** — within a second:
- "Yes Cap Brij." (immediate ack)
- recording 8s of your question
- JARVIS thinks (~2s)
- JARVIS speaks the reply through macOS `say`

Press Ctrl+C to stop.

## Run as a login daemon (truly always-on)

```bash
# 1. Edit the plist — replace the two TEMPLATE_ placeholders:
#       TEMPLATE_REPO_PATH = absolute path to ~/thrive-record-hub/avengers
#       TEMPLATE_FLY_URL   = https://<your-fly-app>.fly.dev
sed -i '' \
  -e "s|TEMPLATE_REPO_PATH|$HOME/thrive-record-hub/avengers|g" \
  -e "s|TEMPLATE_FLY_URL|https://avengers-api.fly.dev|g" \
  jarvis-desktop/com.capbrij.jarvis.plist

# 2. Install + load
cp jarvis-desktop/com.capbrij.jarvis.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.capbrij.jarvis.plist

# 3. Confirm it's running
launchctl list | grep capbrij

# 4. Tail the logs
tail -f /tmp/jarvis-desktop.log
```

JARVIS now wakes on login. Logs at `/tmp/jarvis-desktop.log`.

## Stop / disable

```bash
launchctl unload ~/Library/LaunchAgents/com.capbrij.jarvis.plist
rm ~/Library/LaunchAgents/com.capbrij.jarvis.plist
```

## Wake phrases

The matcher is loose — anything containing one of these triggers JARVIS:
- "hey jarvis"
- "ok jarvis" / "okay jarvis"
- "hi jarvis"
- "yo jarvis"

Edit `WAKE_PHRASES` in `listener.py` to add your own.

## Tuning

| Env var               | Default                      | What it does |
|-----------------------|------------------------------|--------------|
| `JARVIS_API_BASE`     | (required)                   | Your Fly backend, no trailing slash |
| `JARVIS_TOKEN`        | `user:cap-brij`              | Bearer token for the API |
| `JARVIS_TENANT`       | `jarvis`                     | Tenant ID |
| `JARVIS_QUERY_SECS`   | `8`                          | How long to record your question after the wake |
| `JARVIS_SAMPLE_RATE`  | `16000`                      | Mic sample rate (16k is plenty for speech) |
| `JARVIS_LOG_LEVEL`    | `INFO`                       | DEBUG for verbose, WARN for quiet |

## Privacy

The wake-word loop sends short (~5s) audio frames to Google's free STT for
each utterance. If you say something private, the matcher rejects (no wake
phrase) and the audio is discarded immediately — never stored, never sent
to JARVIS. Only on a wake match does the next 8 seconds get sent to JARVIS.

For truly local wake-word detection (no audio leaves your Mac for the
matcher), swap `speech_recognition` for [openwakeword](https://github.com/dscripka/openWakeWord)
which runs a small on-device model. That's a future upgrade.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `OSError: PortAudio not found` | `brew install portaudio` |
| `audio device not available` | System Settings → Mic permissions for Terminal / python3 |
| `STT request failed` | You're offline; reconnect |
| `converse failed: 401` | Wrong `JARVIS_TOKEN` |
| `converse failed: 404` | Wrong `JARVIS_API_BASE` (note: `/api/avengers/...` is appended automatically) |
| Wake fires too easily | Tighten the wake list to just `"hey jarvis"` |
| Daemon doesn't start | `tail /tmp/jarvis-desktop.err` |
