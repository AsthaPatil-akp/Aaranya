#!/bin/sh
set -e
MODEL="${OLLAMA_MODEL:-llama3.2:3b}"
ollama serve &
pid=$!
i=0
while [ "$i" -lt 60 ]; do
  if ollama list >/dev/null 2>&1; then
    break
  fi
  i=$((i + 1))
  sleep 1
done
ollama pull "$MODEL"
wait "$pid"
