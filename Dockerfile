FROM python:3.12-slim

WORKDIR /app

# ncurses is needed for the curses library
RUN apt-get update && apt-get install -y --no-install-recommends \
    libncurses6 \
 && rm -rf /var/lib/apt/lists/*

COPY c64llama.py .

ENV TERM=xterm-256color
ENV OLLAMA_URL=http://ollama:11434/api/generate

ENTRYPOINT ["python3", "c64llama.py"]
