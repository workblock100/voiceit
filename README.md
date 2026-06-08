# voiceit

**Highlight text anywhere on your Mac, hit a hotkey, and hear it read aloud with a live karaoke overlay.**

`voiceit` is a small, single-file macOS utility that turns any selected text — in your browser, your editor, a PDF, a chat window, anywhere — into natural speech on a global keyboard shortcut. As the audio plays, a floating, always-on-top overlay highlights each word in time with the voice, so you can read along while you listen.

It uses [ElevenLabs](https://elevenlabs.io) for high-quality neural text-to-speech and the system `afplay` for playback, with no app to install and no window to keep in focus.

---

## What it does

1. You select text in **any** macOS application.
2. You press **Cmd+Shift+R**.
3. `voiceit` grabs the selection, sends it to ElevenLabs, and plays the result back through your speakers.
4. A borderless overlay appears at the top of your screen showing the text, highlighting each word the instant it's spoken, with a progress bar underneath.
5. Press **Cmd+Shift+S** at any time to stop playback and dismiss the overlay.

There is no menu bar icon and no main window — it runs quietly from the terminal and reacts to global hotkeys.

---

## Key features

- **Works in every app** — reads the current selection system-wide via a global hotkey, not tied to any single program.
- **Word-synced karaoke overlay** — a borderless, semi-transparent, always-on-top Tkinter window highlights each word exactly as it's spoken, using ElevenLabs' per-character timing data.
- **Live progress bar** — a thin fill bar tracks playback position in real time.
- **Draggable overlay** — click and drag the overlay anywhere on screen if it's in your way.
- **Clipboard-safe selection capture** — uses a sentinel-probe trick to detect when nothing is actually selected, and always restores whatever was on your clipboard beforehand.
- **Tunable timing** — an audio-sync offset is configurable so the highlight can be nudged to line up perfectly with your output device's latency.
- **Configurable voice & model** — pick any ElevenLabs voice ID and model via environment variables; defaults to a standard voice and the low-latency `eleven_turbo_v2_5` model.
- **Instant stop** — one hotkey kills playback and closes the overlay immediately.
- **Tiny footprint** — one Python file, three third-party dependencies, no build step.

---

## Tech stack

**Python 3.10+** · **Tkinter** (overlay UI) · **pynput** (global hotkeys + keystroke synthesis) · **pyperclip** (clipboard access) · **requests** (ElevenLabs API) · **ElevenLabs** text-to-speech with timestamps · macOS **`afplay`** for audio playback

---

## Requirements

- **macOS** (relies on the built-in `afplay` and `killall` commands).
- **Python 3.10 or newer** (the code uses `X | None` type syntax).
- An **ElevenLabs API key** ([sign up here](https://elevenlabs.io)).
- macOS **Accessibility** and **Input Monitoring** permissions for your terminal (so `voiceit` can read global hotkeys and synthesize the Cmd+C used to copy your selection — see *Setup* below).

---

## Setup

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/workblock100/voiceit.git
cd voiceit
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

> `tkinter` ships with most Python installs. On Homebrew Python you may need `brew install python-tk`.

### 3. Configure your environment

Copy the example file and fill in your own key:

```bash
cp .env.example .env
```

Then edit `.env`:

```bash
# Required — your ElevenLabs API key
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here

# Optional — override the voice, model, and highlight timing
VOICEIT_VOICE_ID=21m00Tcm4TlvDq8ikWAM   # any ElevenLabs voice ID
VOICEIT_MODEL=eleven_turbo_v2_5         # any ElevenLabs model ID
VOICEIT_SYNC_OFFSET=0.22                # seconds to offset the word highlight
```

> **Never commit your real `.env`.** It contains a live API key. The repository's `.gitignore` excludes it — keep it that way.

### 4. Grant macOS permissions

Because `voiceit` listens for global hotkeys and copies your selection by simulating Cmd+C, macOS will require your terminal app (Terminal, iTerm2, etc.) to be granted:

- **System Settings → Privacy & Security → Accessibility**
- **System Settings → Privacy & Security → Input Monitoring**

Add and enable your terminal in both, then restart the terminal.

---

## Usage

Start it with the helper script, which loads `.env`, activates the virtualenv, and runs the app with logging:

```bash
./start.sh
```

`start.sh` will refuse to start and print instructions if `ELEVENLABS_API_KEY` isn't set. Logs are written to `/tmp/voiceit.log`.

Or run it directly once your environment is active:

```bash
source .venv/bin/activate
export ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
python3 voiceit.py
```

Once it's running you'll see:

```
voiceit running.
  Cmd+Shift+R  read selection
  Cmd+Shift+S  stop
  (Ctrl+C in this terminal to quit)
```

Now select text in any app and press **Cmd+Shift+R**.

### Hotkeys

| Shortcut       | Action                              |
| -------------- | ----------------------------------- |
| `Cmd+Shift+R`  | Read the current selection aloud    |
| `Cmd+Shift+S`  | Stop playback and close the overlay |
| `Ctrl+C`       | Quit `voiceit` (in the terminal)    |

---

## How it works

- **Capturing the selection** — On the read hotkey, `voiceit` writes a unique sentinel string to the clipboard, simulates **Cmd+C** with `pynput`, and reads the clipboard back. If the clipboard still holds the sentinel, nothing was selected and it bails out cleanly. Either way, it restores whatever was on your clipboard before.
- **Synthesizing speech** — The captured text is POSTed to the ElevenLabs `text-to-speech/{voice_id}/with-timestamps` endpoint. The response includes base64-encoded MP3 audio **and** per-character start/end timestamps.
- **Playback** — The decoded MP3 is written to a temp file and played with macOS `afplay` as a subprocess, so stopping is as simple as terminating the process (and a `killall afplay` for good measure).
- **Karaoke highlighting** — The per-character timings are folded into word segments. A Tkinter overlay runs a ~60 fps tick loop that measures elapsed playback time (adjusted by `VOICEIT_SYNC_OFFSET`), binary-searches the current word, and recolors the text — already-read, currently-spoken, and upcoming — while advancing the progress bar. When playback finishes, the overlay fades out automatically.

---

## Configuration reference

| Variable               | Default                | Purpose                                                |
| ---------------------- | ---------------------- | ------------------------------------------------------ |
| `ELEVENLABS_API_KEY`   | *(required)*           | Your ElevenLabs API key.                               |
| `VOICEIT_VOICE_ID`     | `21m00Tcm4TlvDq8ikWAM` | ElevenLabs voice ID to speak with.                     |
| `VOICEIT_MODEL`        | `eleven_turbo_v2_5`    | ElevenLabs model ID.                                   |
| `VOICEIT_SYNC_OFFSET`  | `0.22`                 | Seconds to offset word highlighting from audio start.  |

---

## Notes & limitations

- **macOS only.** The audio playback and process control rely on `afplay` and `killall`.
- **Requires an internet connection** and a valid ElevenLabs account; usage counts against your ElevenLabs quota.
- The selection capture works by synthesizing Cmd+C, so it relies on the frontmost app supporting standard copy.

---

## License

No license file is currently included. Add one (e.g. MIT) before sharing if you intend others to reuse the code.


---

## 💼 Hire the author
Built by **Elijah** — I build custom MCP servers, Python automations, web scrapers, and AI chatbots. Fixed-price from $85, working sample before you pay.
- **Upwork:** https://www.upwork.com/freelancers/~01818ac5bd67ef7935
- **Email:** workblock100@gmail.com

**🛒 Ready-made products:** [MCP Server Starter Kit](https://workblocker.gumroad.com/l/qoqdkt) · [AI Lead-Gen Automation Pack](https://workblocker.gumroad.com/l/lokury)
