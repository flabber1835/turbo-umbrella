FROM python:3.12-slim

# Install git + ncurses
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libncurses6 \
 && rm -rf /var/lib/apt/lists/*

# Clone the app directly from GitHub
RUN git clone --depth 1 https://github.com/flabber1835/turbo-umbrella.git /app

WORKDIR /app

ENV TERM=xterm-256color
# Override at runtime: -e OLLAMA_URL=http://<your-host>:11434/api/generate
ENV OLLAMA_URL=http://host.docker.internal:11434/api/generate
ENV OLLAMA_MODEL=llama3.2

ENTRYPOINT ["python3", "c64llama.py"]
