#!/usr/bin/env python3
"""
C64LLAMA - Commodore 64 UI for llama (via ollama) on Raspberry Pi 5
Simulates the classic C64 BASIC boot screen with an AI-powered READY prompt.
"""

import curses
import sys
import json
import urllib.request
import urllib.error
import textwrap
import time
import threading
import argparse

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3.2"

C64_BLUE_BG  = 1   # background
C64_BLUE_FG  = 2   # light blue text on blue
C64_WHITE_FG = 3   # white text on blue
C64_CYAN_FG  = 4   # cyan for cursor / accents
C64_YELLOW   = 5   # yellow for system messages

BOOT_LINES = [
    "",
    "    **** COMMODORE 64 BASIC V2 ****",
    "",
    " 64K RAM SYSTEM  38911 BASIC BYTES FREE",
    "",
    "READY.",
    "",
]

SYSTEM_PROMPT = (
    "You are an AI assistant accessed through a Commodore 64 terminal. "
    "Keep responses concise and appropriate for a small screen. "
    "Use plain ASCII only - no markdown, no emoji. "
    "UPPERCASE is preferred, but lowercase is fine."
)


def call_ollama(model: str, prompt: str, history: list[dict]) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    full_prompt = "\n".join(
        f"{'USER' if m['role'] == 'user' else 'ASSISTANT' if m['role'] == 'assistant' else 'SYSTEM'}: {m['content']}"
        for m in messages
    )

    payload = json.dumps({
        "model": model,
        "prompt": full_prompt,
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            return data.get("response", "").strip()
    except urllib.error.URLError as e:
        return f"?NETWORK ERROR - {e.reason}"
    except Exception as e:
        return f"?ERROR - {e}"


def stream_ollama(model: str, prompt: str, history: list[dict], on_token):
    """Stream tokens from ollama, calling on_token(token_str) for each."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": prompt})

    full_prompt = "\n".join(
        f"{'USER' if m['role'] == 'user' else 'ASSISTANT' if m['role'] == 'assistant' else 'SYSTEM'}: {m['content']}"
        for m in messages
    )

    payload = json.dumps({
        "model": model,
        "prompt": full_prompt,
        "stream": True,
    }).encode()

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            full = []
            for raw_line in resp:
                line = raw_line.decode().strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = chunk.get("response", "")
                if token:
                    full.append(token)
                    on_token(token)
                if chunk.get("done"):
                    break
            return "".join(full)
    except urllib.error.URLError as e:
        msg = f"?NETWORK ERROR - {e.reason}"
        on_token(msg)
        return msg
    except Exception as e:
        msg = f"?ERROR - {e}"
        on_token(msg)
        return msg


class C64Screen:
    def __init__(self, stdscr, model: str):
        self.scr = stdscr
        self.model = model
        self.history: list[dict] = []
        self.lines: list[str] = []   # display buffer
        self.input_buf = ""
        self.cursor_visible = True
        self._setup_colors()
        self._init_screen()

    def _setup_colors(self):
        curses.start_color()
        curses.use_default_colors()
        # C64 palette approximations with curses colour indices
        curses.init_pair(C64_BLUE_BG,  curses.COLOR_BLUE,  curses.COLOR_BLUE)
        curses.init_pair(C64_BLUE_FG,  curses.COLOR_CYAN,  curses.COLOR_BLUE)
        curses.init_pair(C64_WHITE_FG, curses.COLOR_WHITE, curses.COLOR_BLUE)
        curses.init_pair(C64_CYAN_FG,  curses.COLOR_CYAN,  curses.COLOR_BLUE)
        curses.init_pair(C64_YELLOW,   curses.COLOR_YELLOW, curses.COLOR_BLUE)

    def _init_screen(self):
        self.scr.bkgd(" ", curses.color_pair(C64_BLUE_FG))
        self.scr.clear()
        curses.curs_set(0)
        for line in BOOT_LINES:
            self.lines.append(line)
        self._redraw()

    def _redraw(self):
        h, w = self.scr.getmaxyx()
        self.scr.erase()
        self.scr.bkgd(" ", curses.color_pair(C64_BLUE_FG))

        display_lines = self.lines[-(h - 2):]  # leave one row for input

        for row, line in enumerate(display_lines):
            if row >= h - 2:
                break
            text = line[:w - 1]
            try:
                self.scr.addstr(row, 0, text, curses.color_pair(C64_WHITE_FG))
            except curses.error:
                pass

        # input row
        input_row = h - 2
        prefix = ">"
        inp = f"{prefix}{self.input_buf}"
        if self.cursor_visible:
            inp += "\u2588"  # block cursor char
        inp = inp[:w - 1]
        try:
            self.scr.addstr(input_row, 0, inp, curses.color_pair(C64_CYAN_FG) | curses.A_BOLD)
        except curses.error:
            pass

        # status bar
        status = f" MODEL: {self.model}  |  /quit to exit  |  /clear to reset "
        status = status[:w - 1].ljust(w - 1)
        try:
            self.scr.addstr(h - 1, 0, status, curses.color_pair(C64_YELLOW))
        except curses.error:
            pass

        self.scr.refresh()

    def append_line(self, text: str):
        h, w = self.scr.getmaxyx()
        wrapped = textwrap.wrap(text, w - 1) if text.strip() else [""]
        for line in (wrapped or [""]):
            self.lines.append(line.upper() if text == text.upper() else line)
        self._redraw()

    def append_char(self, ch: str):
        """Append a single character/token to the last output line."""
        h, w = self.scr.getmaxyx()
        if not self.lines:
            self.lines.append("")
        # Build up last line; wrap if needed
        last = self.lines[-1]
        for c in ch:
            if c == "\n":
                self.lines.append("")
                last = ""
            else:
                last += c
                if len(last) >= w - 1:
                    self.lines.append("")
                    last = ""
                self.lines[-1] = last
        self._redraw()

    def handle_command(self, cmd: str) -> bool:
        """Returns True if the main loop should exit."""
        cmd = cmd.strip()
        if cmd.lower() in ("/quit", "/exit", "exit", "quit"):
            return True
        if cmd.lower() == "/clear":
            self.history.clear()
            self.lines = list(BOOT_LINES)
            self._redraw()
            return False
        if cmd.lower().startswith("/model "):
            self.model = cmd.split(None, 1)[1].strip()
            self.append_line(f"MODEL SET TO: {self.model}")
            self.append_line("")
            return False
        if cmd.lower() == "/help":
            self.append_line("COMMANDS:")
            self.append_line("  /clear       - RESET CONVERSATION")
            self.append_line("  /model NAME  - SWITCH OLLAMA MODEL")
            self.append_line("  /quit        - EXIT")
            self.append_line("")
            return False
        return False

    def run(self):
        curses.halfdelay(5)  # 0.5s timeout for cursor blink

        blink_counter = 0
        while True:
            try:
                key = self.scr.getch()
            except curses.error:
                key = -1

            # cursor blink
            blink_counter += 1
            if blink_counter >= 4:
                self.cursor_visible = not self.cursor_visible
                blink_counter = 0
                self._redraw()

            if key == -1:
                continue

            self.cursor_visible = True

            if key in (curses.KEY_ENTER, ord("\n"), ord("\r")):
                user_input = self.input_buf.strip()
                self.input_buf = ""

                if not user_input:
                    self.append_line("")
                    continue

                self.append_line(f">{user_input}")

                if self.handle_command(user_input):
                    break

                if user_input.startswith("/"):
                    continue

                # Show thinking indicator
                self.append_line("THINKING...")
                self._redraw()

                # Stream response
                response_lines_start = len(self.lines)
                self.lines.append("")  # placeholder for response

                collected = []

                def on_token(token):
                    collected.append(token)
                    self.append_char(token)

                result = stream_ollama(self.model, user_input, self.history, on_token)

                # Remove "THINKING..." line
                think_idx = None
                for i, ln in enumerate(self.lines):
                    if ln == "THINKING...":
                        think_idx = i
                        break
                if think_idx is not None:
                    self.lines.pop(think_idx)

                self.history.append({"role": "user", "content": user_input})
                self.history.append({"role": "assistant", "content": result})

                self.append_line("")
                self.append_line("READY.")
                self.append_line("")

            elif key in (curses.KEY_BACKSPACE, 127, 8):
                self.input_buf = self.input_buf[:-1]
                self._redraw()

            elif key == curses.KEY_DC:
                self.input_buf = self.input_buf[:-1]
                self._redraw()

            elif 32 <= key <= 126:
                self.input_buf += chr(key)
                self._redraw()

            elif key == 27:  # ESC - clear input
                self.input_buf = ""
                self._redraw()


def main():
    parser = argparse.ArgumentParser(description="Commodore 64 UI for llama via ollama")
    parser.add_argument(
        "--model", "-m",
        default=DEFAULT_MODEL,
        help=f"Ollama model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--url",
        default=OLLAMA_URL,
        help=f"Ollama API URL (default: {OLLAMA_URL})",
    )
    args = parser.parse_args()

    global OLLAMA_URL
    OLLAMA_URL = args.url

    def _run(stdscr):
        screen = C64Screen(stdscr, args.model)
        screen.run()

    try:
        curses.wrapper(_run)
    except KeyboardInterrupt:
        pass
    print("\nGOODBYE.")


if __name__ == "__main__":
    main()
