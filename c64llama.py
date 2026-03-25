#!/usr/bin/env python3
"""
C64LLAMA - Commodore 64 themed menu UI for llama on Raspberry Pi
"""

import curses
import os
import json
import textwrap
import urllib.request
import urllib.error

# ── colour pairs ─────────────────────────────────────────────────────────────
PAIR_TEXT  = 1   # white on blue
PAIR_CYAN  = 2   # cyan on blue
PAIR_HILIT = 3   # black on cyan  (selected item)
PAIR_YELLO = 4   # yellow on blue (status bar / headers)
PAIR_ERR   = 5   # red on blue    (errors)

BOOT_LINES = [
    "",
    "    **** COMMODORE 64 BASIC V2 ****",
    "",
    " 64K RAM SYSTEM  38911 BASIC BYTES FREE",
    "",
]

MENU = [
    ("CHAT WITH AI",  "TALK TO YOUR LOCAL LLAMA MODEL"),
    ("SETTINGS",      "CHANGE MODEL OR OLLAMA URL"),
    ("ABOUT",         "ABOUT C64LLAMA"),
    ("QUIT",          "RETURN TO BASIC"),
]

SYSTEM_PROMPT = (
    "You are an AI assistant on a Commodore 64 terminal. "
    "Keep responses concise. Plain ASCII only. UPPERCASE preferred."
)


# ── colour setup ─────────────────────────────────────────────────────────────

def setup_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(PAIR_TEXT,  curses.COLOR_WHITE,  curses.COLOR_BLUE)
    curses.init_pair(PAIR_CYAN,  curses.COLOR_CYAN,   curses.COLOR_BLUE)
    curses.init_pair(PAIR_HILIT, curses.COLOR_BLACK,  curses.COLOR_CYAN)
    curses.init_pair(PAIR_YELLO, curses.COLOR_YELLOW, curses.COLOR_BLUE)
    curses.init_pair(PAIR_ERR,   curses.COLOR_RED,    curses.COLOR_BLUE)


# ── drawing helpers ──────────────────────────────────────────────────────────

def safe_add(win, row, col, text, attr=0):
    h, w = win.getmaxyx()
    if row < 0 or row >= h:
        return
    text = text[:max(0, w - col - 1)]
    try:
        win.addstr(row, col, text, attr)
    except curses.error:
        pass


def status_bar(win, text):
    h, w = win.getmaxyx()
    safe_add(win, h - 1, 0, text[:w - 1].ljust(w - 1),
             curses.color_pair(PAIR_YELLO))


def draw_boot_header(win, start_row=0):
    for i, line in enumerate(BOOT_LINES):
        safe_add(win, start_row + i, 0, line,
                 curses.color_pair(PAIR_CYAN) | curses.A_BOLD)
    return start_row + len(BOOT_LINES)


# ── inline text input (replaces curses.getstr for better control) ────────────

def read_line(win, prompt_row, prompt_col, width, prefill=""):
    """Single-line input widget. Returns new string or prefill on ESC."""
    curses.curs_set(1)
    buf = list(prefill)

    while True:
        display = "".join(buf)[:width]
        safe_add(win, prompt_row, prompt_col,
                 display.ljust(width), curses.color_pair(PAIR_TEXT) | curses.A_BOLD)
        col = min(len(buf), width - 1)
        try:
            win.move(prompt_row, prompt_col + col)
        except curses.error:
            pass
        win.refresh()

        key = win.getch()
        if key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            break
        elif key == 27:  # ESC – cancel
            buf = list(prefill)
            break
        elif key in (curses.KEY_BACKSPACE, 127, 8):
            if buf:
                buf.pop()
        elif 32 <= key <= 126:
            buf.append(chr(key))

    curses.curs_set(0)
    return "".join(buf)


# ── main menu ────────────────────────────────────────────────────────────────

def run_menu(stdscr, cfg):
    curses.curs_set(0)
    sel = 0

    while True:
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        stdscr.bkgd(" ", curses.color_pair(PAIR_TEXT))

        row = draw_boot_header(stdscr)

        safe_add(stdscr, row, 2, "MAIN MENU",
                 curses.color_pair(PAIR_YELLO) | curses.A_BOLD)
        row += 2

        for i, (label, _) in enumerate(MENU):
            pointer = "> " if i == sel else "  "
            text = f"  {pointer}{label}"
            if i == sel:
                safe_add(stdscr, row, 0, text.ljust(min(w - 1, 36)),
                         curses.color_pair(PAIR_HILIT) | curses.A_BOLD)
            else:
                safe_add(stdscr, row, 0, text, curses.color_pair(PAIR_TEXT))
            row += 1

        row += 1
        safe_add(stdscr, row, 2, MENU[sel][1], curses.color_pair(PAIR_CYAN))

        status_bar(stdscr,
                   f" MODEL: {cfg['model']}  |  "
                   "ARROWS+ENTER TO SELECT  |  NUMBER KEYS  |  Q=QUIT ")
        stdscr.refresh()

        key = stdscr.getch()

        if key == curses.KEY_UP:
            sel = (sel - 1) % len(MENU)
        elif key == curses.KEY_DOWN:
            sel = (sel + 1) % len(MENU)
        elif ord('1') <= key <= ord('1') + len(MENU) - 1:
            sel = key - ord('1')
            key = ord('\n')  # fall-through to execute

        if key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            if sel == 0:
                run_chat(stdscr, cfg)
            elif sel == 1:
                run_settings(stdscr, cfg)
            elif sel == 2:
                run_about(stdscr)
            elif sel == 3:
                break

        if key in (ord('q'), ord('Q')):
            break


# ── chat screen ──────────────────────────────────────────────────────────────

def ollama_stream(cfg, prompt, history, on_token):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": prompt})
    full_prompt = "\n".join(
        ("USER" if m["role"] == "user" else
         "ASSISTANT" if m["role"] == "assistant" else "SYSTEM")
        + ": " + m["content"]
        for m in messages
    )
    payload = json.dumps({
        "model": cfg["model"],
        "prompt": full_prompt,
        "stream": True,
    }).encode()
    req = urllib.request.Request(
        cfg["url"], data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            full = []
            for raw in resp:
                line = raw.decode().strip()
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
        msg = f"?NETWORK ERROR: {e.reason}"
        on_token(msg)
        return msg
    except Exception as e:
        msg = f"?ERROR: {e}"
        on_token(msg)
        return msg


def run_chat(stdscr, cfg):
    curses.curs_set(0)
    history = []
    lines = list(BOOT_LINES) + [
        "CHAT MODE  (/back TO MENU  /clear TO RESET)",
        "",
    ]
    input_buf = ""
    cursor_on = True
    blink = 0

    def redraw():
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        stdscr.bkgd(" ", curses.color_pair(PAIR_TEXT))
        for i, ln in enumerate(lines[-(h - 2):]):
            if i >= h - 2:
                break
            safe_add(stdscr, i, 0, ln[:w - 1], curses.color_pair(PAIR_TEXT))
        prompt = ">" + input_buf + ("\u2588" if cursor_on else " ")
        safe_add(stdscr, h - 2, 0, prompt[:w - 1],
                 curses.color_pair(PAIR_CYAN) | curses.A_BOLD)
        status_bar(stdscr,
                   f" CHAT | MODEL: {cfg['model']} | /back  /clear  ESC=MENU ")
        stdscr.refresh()

    def append(text):
        _, w = stdscr.getmaxyx()
        wrapped = textwrap.wrap(text, w - 1) if text.strip() else [""]
        lines.extend(wrapped or [""])
        redraw()

    def append_char(ch):
        _, w = stdscr.getmaxyx()
        for c in ch:
            if c == "\n":
                lines.append("")
            else:
                if not lines:
                    lines.append("")
                last = lines[-1] + c
                if len(last) >= w - 1:
                    lines.append("")
                    last = c
                lines[-1] = last
        redraw()

    curses.halfdelay(5)
    redraw()

    while True:
        try:
            key = stdscr.getch()
        except curses.error:
            key = -1

        blink += 1
        if blink >= 4:
            cursor_on = not cursor_on
            blink = 0
            redraw()

        if key == -1:
            continue

        cursor_on = True

        if key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            user_input = input_buf.strip()
            input_buf = ""

            if not user_input:
                lines.append("")
                redraw()
                continue

            append(f">{user_input}")

            if user_input.lower() in ("/back", "/menu", "/exit"):
                break
            if user_input.lower() == "/clear":
                history.clear()
                lines[:] = list(BOOT_LINES) + [
                    "CHAT MODE  (/back TO MENU  /clear TO RESET)", ""
                ]
                redraw()
                continue
            if user_input.startswith("/"):
                append("UNKNOWN COMMAND. TRY /back OR /clear")
                append("")
                continue

            append("THINKING...")
            lines.append("")
            result = ollama_stream(cfg, user_input, history, append_char)

            for i, ln in enumerate(lines):
                if ln == "THINKING...":
                    lines.pop(i)
                    break

            history.append({"role": "user",      "content": user_input})
            history.append({"role": "assistant",  "content": result})
            append("")
            append("READY.")
            append("")

        elif key in (curses.KEY_BACKSPACE, 127, 8):
            input_buf = input_buf[:-1]
            redraw()
        elif key == 27:  # ESC
            break
        elif 32 <= key <= 126:
            input_buf += chr(key)
            redraw()

    curses.cbreak()  # restore from halfdelay


# ── settings screen ──────────────────────────────────────────────────────────

FIELDS = [
    ("MODEL", "model", 22),
    ("URL",   "url",   50),
]


def run_settings(stdscr, cfg):
    curses.curs_set(0)
    sel = 0
    edits = {k: cfg[k] for _, k, _ in FIELDS}

    def redraw(editing_field=None, msg=""):
        h, w = stdscr.getmaxyx()
        stdscr.erase()
        stdscr.bkgd(" ", curses.color_pair(PAIR_TEXT))
        row = draw_boot_header(stdscr)
        safe_add(stdscr, row, 2, "SETTINGS",
                 curses.color_pair(PAIR_YELLO) | curses.A_BOLD)
        row += 2

        for i, (label, key, _) in enumerate(FIELDS):
            lattr = (curses.color_pair(PAIR_HILIT) | curses.A_BOLD
                     if i == sel else curses.color_pair(PAIR_CYAN))
            safe_add(stdscr, row, 2, f"{label}:", lattr)
            safe_add(stdscr, row, 10, edits[key][:w - 12],
                     curses.color_pair(PAIR_TEXT))
            row += 2

        if msg:
            safe_add(stdscr, row + 1, 2, msg, curses.color_pair(PAIR_CYAN))

        status_bar(stdscr,
                   " SETTINGS | ARROWS=SELECT  ENTER=EDIT  S=SAVE  ESC=CANCEL ")
        stdscr.refresh()
        return row

    while True:
        row = redraw()
        key = stdscr.getch()

        if key == curses.KEY_UP:
            sel = (sel - 1) % len(FIELDS)
        elif key == curses.KEY_DOWN:
            sel = (sel + 1) % len(FIELDS)
        elif key in (curses.KEY_ENTER, ord('\n'), ord('\r')):
            label, k, maxlen = FIELDS[sel]
            field_row = len(BOOT_LINES) + 2 + sel * 2
            redraw(msg=f"EDITING {label} - ENTER TO CONFIRM  ESC TO CANCEL")
            new_val = read_line(stdscr, field_row, 10, maxlen, prefill=edits[k])
            if new_val:
                edits[k] = new_val
        elif key in (ord('s'), ord('S')):
            cfg.update(edits)
            redraw(msg="SAVED.")
            stdscr.getch()
            break
        elif key == 27:
            break


# ── about screen ─────────────────────────────────────────────────────────────

def run_about(stdscr):
    stdscr.erase()
    stdscr.bkgd(" ", curses.color_pair(PAIR_TEXT))
    row = draw_boot_header(stdscr)
    for line in [
        "  C64LLAMA",
        "",
        "  COMMODORE 64 THEMED INTERFACE FOR",
        "  LLAMA MODELS VIA OLLAMA.",
        "",
        "  RUNS ON RASPBERRY PI.",
        "  PULL IMAGE FROM GHCR:",
        "",
        "  DOCKER RUN -IT --RM \\",
        "    -E OLLAMA_URL=http://<host>:11434/api/generate \\",
        "    GHCR.IO/FLABBER1835/TURBO-UMBRELLA:LATEST",
        "",
        "  PRESS ANY KEY...",
    ]:
        safe_add(stdscr, row, 0, line, curses.color_pair(PAIR_CYAN))
        row += 1
    status_bar(stdscr, " ABOUT | PRESS ANY KEY TO RETURN ")
    stdscr.refresh()
    stdscr.getch()


# ── entry point ──────────────────────────────────────────────────────────────

def main(stdscr):
    setup_colors()
    cfg = {
        "model": os.environ.get("OLLAMA_MODEL", "llama3.2"),
        "url":   os.environ.get("OLLAMA_URL",
                                "http://localhost:11434/api/generate"),
    }
    run_menu(stdscr, cfg)


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except KeyboardInterrupt:
        pass
    print("\nGOODBYE.")
