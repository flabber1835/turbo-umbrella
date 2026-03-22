# C64LLAMA

A Commodore 64-style terminal UI for interacting with **llama** models via [ollama](https://ollama.com), built for the Raspberry Pi 5.

```
    **** COMMODORE 64 BASIC V2 ****

 64K RAM SYSTEM  38911 BASIC BYTES FREE

READY.

>WHAT IS THE SPEED OF LIGHT?
THINKING...
THE SPEED OF LIGHT IN A VACUUM IS APPROXIMATELY
299,792,458 METRES PER SECOND (ABOUT 186,282
MILES PER SECOND).

READY.

>_
```

---

## Requirements

- Raspberry Pi 5 (or any Linux system)
- Python 3.10+  (uses only stdlib — no pip install needed)
- [ollama](https://ollama.com) running locally with at least one model pulled

## Setup

### 1. Install ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. Pull a model

```bash
ollama pull llama3.2        # ~2 GB, good default for RPi 5
# or
ollama pull tinyllama       # ~600 MB, faster on constrained hardware
# or
ollama pull mistral
```

### 3. Start ollama (if not already running)

```bash
ollama serve &
```

### 4. Run c64llama

```bash
python3 c64llama.py
# or specify a model
python3 c64llama.py --model tinyllama
```

---

## Usage

| Key / Command | Action |
|---|---|
| Type + Enter | Send message to llama |
| ESC | Clear current input |
| `/clear` | Reset conversation history |
| `/model NAME` | Switch to a different ollama model |
| `/help` | Show help |
| `/quit` | Exit |

Responses stream token-by-token, just like a slow 1980s modem would — except the content is actually useful.

---

## Options

```
python3 c64llama.py [--model MODEL] [--url URL]

  --model, -m   Ollama model name (default: llama3.2)
  --url         Ollama API base URL (default: http://localhost:11434/api/generate)
```

## Tips for Raspberry Pi 5

- `llama3.2:3b` runs well on 4 GB RPi 5; use `tinyllama` for 2 GB models.
- Run `ollama serve` as a systemd service so it starts on boot:

```bash
sudo systemctl enable ollama
sudo systemctl start ollama
```

- Add to `~/.bashrc` for a quick launch alias:

```bash
alias c64='python3 ~/turbo-umbrella/c64llama.py'
```
