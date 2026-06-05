#!/usr/bin/env python3
"""
voiceit.py — Highlight text in any macOS app, hit Cmd+Shift+R, hear it.

Hotkeys:
  Cmd+Shift+R  read the current selection
  Cmd+Shift+S  stop playback / close overlay
"""

import os
import sys
import time
import bisect
import base64
import tempfile
import subprocess
import requests
import pyperclip
import tkinter as tk
from pynput import keyboard
from pynput.keyboard import Key, Controller

ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
VOICE_ID = os.environ.get("VOICEIT_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
MODEL_ID = os.environ.get("VOICEIT_MODEL", "eleven_turbo_v2_5")
AUDIO_OFFSET = float(os.environ.get("VOICEIT_SYNC_OFFSET", "0.22"))

SPEAK_MODS = {Key.cmd, Key.shift}
SPEAK_CHAR = "r"
STOP_CHAR = "s"

pressed = set()
kb = Controller()
hidden_root = None
current_window = {"win": None}
player = {"proc": None}


def stop_audio():
    p = player.get("proc")
    if p is not None:
        try:
            p.terminate()
        except Exception:
            pass
        player["proc"] = None
    subprocess.run(["killall", "afplay"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)


def play_audio(path: str):
    stop_audio()
    player["proc"] = subprocess.Popen(
        ["afplay", path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def is_playing() -> bool:
    p = player.get("proc")
    return bool(p and p.poll() is None)


def grab_selection() -> str:
    saved = pyperclip.paste()
    sentinel = "​__voiceit_probe__​"
    pyperclip.copy(sentinel)
    time.sleep(0.05)
    with kb.pressed(Key.cmd):
        kb.tap("c")
    time.sleep(0.18)
    text = pyperclip.paste()
    if text == sentinel:
        pyperclip.copy(saved)
        return ""
    pyperclip.copy(saved)
    return text.strip()


def fetch_tts(text: str):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/with-timestamps"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        },
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=60)
    except requests.RequestException as e:
        print(f"[voiceit] network error: {e}")
        return None, None
    if r.status_code != 200:
        print(f"[voiceit] elevenlabs {r.status_code}: {r.text[:300]}")
        return None, None
    data = r.json()
    audio = base64.b64decode(data["audio_base64"])
    align = data.get("alignment") or data.get("normalized_alignment")
    return audio, align


def build_word_segments(text, alignment):
    if not alignment or "character_start_times_seconds" not in alignment:
        return [{"start": 0, "end": len(text), "time": 0.0, "end_time": 0.5}]

    starts = alignment["character_start_times_seconds"]
    ends = alignment.get("character_end_times_seconds", starts)
    n = min(len(text), len(starts))

    words = []
    i = 0
    while i < n:
        while i < n and text[i].isspace():
            i += 1
        if i >= n:
            break
        j = i
        while j < n and not text[j].isspace():
            j += 1
        words.append({
            "start": i,
            "end": j,
            "time": starts[i],
            "end_time": ends[min(j - 1, n - 1)],
        })
        i = j

    return words if words else [{"start": 0, "end": len(text), "time": 0.0, "end_time": 0.5}]


def close_current():
    stop_audio()
    w = current_window.get("win")
    if w is not None:
        try:
            w.destroy()
        except Exception:
            pass
        current_window["win"] = None


def open_overlay(text: str, audio_path: str, alignment: dict | None):
    close_current()

    words = build_word_segments(text, alignment)
    word_times = [w["time"] for w in words]
    total_duration = words[-1]["end_time"] if words else 1.0

    win = tk.Toplevel(hidden_root)
    current_window["win"] = win
    win.title("voiceit")
    win.attributes("-topmost", True)
    win.attributes("-alpha", 0.95)
    win.configure(bg="#0e0e14")

    sw = win.winfo_screenwidth()
    ww, wh = 920, 210
    win.geometry(f"{ww}x{wh}+{(sw - ww) // 2}+36")
    win.lift()
    win.focus_force()

    # Drag support for borderless window
    drag = {"x": 0, "y": 0}

    def on_drag_start(e):
        drag["x"] = e.x
        drag["y"] = e.y

    def on_drag_motion(e):
        x = win.winfo_x() + e.x - drag["x"]
        y = win.winfo_y() + e.y - drag["y"]
        win.geometry(f"+{x}+{y}")

    txt = tk.Text(
        win, wrap="word",
        font=("Helvetica Neue", 23),
        bg="#0e0e14", fg="#2e2e3a",
        padx=40, pady=30,
        spacing2=10,
        relief="flat", highlightthickness=0, borderwidth=0,
        cursor="arrow",
    )
    txt.tag_config("upcoming", foreground="#2e2e3a")
    txt.tag_config("read", foreground="#7a7a90")
    txt.tag_config("current",
                   foreground="#ffffff",
                   background="#4f46e5",
                   font=("Helvetica Neue", 23, "bold"))
    txt.insert("1.0", text, "upcoming")
    txt.config(state="disabled")
    txt.pack(fill="both", expand=True, pady=(0, 6))

    txt.bind("<Button-1>", on_drag_start)
    txt.bind("<B1-Motion>", on_drag_motion)

    bar_track = tk.Canvas(win, height=4, bg="#1a1a26", highlightthickness=0, borderwidth=0)
    bar_fill = bar_track.create_rectangle(0, 0, 0, 4, fill="#4f46e5", outline="")
    bar_track.pack(fill="x", padx=40, pady=(0, 16))

    state = {"t0": None, "last_idx": -1}

    def tick():
        if current_window["win"] is not win:
            return
        if state["t0"] is None:
            win.after(16, tick)
            return

        elapsed = time.time() - state["t0"] - AUDIO_OFFSET

        pct = max(0.0, min(1.0, elapsed / total_duration)) if total_duration > 0 else 0
        try:
            bar_track.coords(bar_fill, 0, 0, int(pct * (ww - 80)), 4)
        except tk.TclError:
            return

        if elapsed < 0:
            win.after(16, tick)
            return

        idx = bisect.bisect_right(word_times, elapsed) - 1
        idx = max(0, min(idx, len(words) - 1))

        if idx != state["last_idx"]:
            state["last_idx"] = idx
            word = words[idx]
            try:
                txt.config(state="normal")
                txt.tag_remove("upcoming", "1.0", "end")
                txt.tag_remove("read", "1.0", "end")
                txt.tag_remove("current", "1.0", "end")

                if word["start"] > 0:
                    txt.tag_add("read", "1.0", f"1.0+{word['start']}c")
                txt.tag_add("current", f"1.0+{word['start']}c", f"1.0+{word['end']}c")
                if word["end"] < len(text):
                    txt.tag_add("upcoming", f"1.0+{word['end']}c", "end")

                txt.see(f"1.0+{word['start']}c")
                txt.config(state="disabled")
            except tk.TclError:
                return

        if is_playing() or (elapsed < total_duration + 0.5):
            win.after(16, tick)
        else:
            win.after(700, close_current)

    def start():
        state["t0"] = time.time()
        try:
            play_audio(audio_path)
        except Exception as e:
            print(f"[voiceit] playback error: {e}")
            close_current()
            return
        tick()

    win.after(50, start)


def do_speak():
    text = grab_selection()
    if not text:
        print("[voiceit] no text selected")
        return
    print(f"[voiceit] speaking: {text[:80]}{'...' if len(text) > 80 else ''}")
    audio, align = fetch_tts(text)
    if audio is None:
        return
    f = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    f.write(audio)
    f.close()
    open_overlay(text, f.name, align)


def do_stop():
    close_current()


def on_press(key):
    pressed.add(key)
    if not SPEAK_MODS.issubset(pressed):
        return
    ch = getattr(key, "char", None)
    if ch == SPEAK_CHAR:
        hidden_root.after(0, do_speak)
    elif ch == STOP_CHAR:
        hidden_root.after(0, do_stop)


def on_release(key):
    pressed.discard(key)


def main():
    global hidden_root
    if not ELEVENLABS_API_KEY:
        print("Set ELEVENLABS_API_KEY in your environment first.")
        sys.exit(1)

    hidden_root = tk.Tk()
    hidden_root.withdraw()

    listener = keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.daemon = True
    listener.start()

    print("voiceit running.")
    print("  Cmd+Shift+R  read selection")
    print("  Cmd+Shift+S  stop")
    print("  (Ctrl+C in this terminal to quit)")

    try:
        hidden_root.mainloop()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
