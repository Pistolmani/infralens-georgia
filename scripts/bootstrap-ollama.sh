#!/usr/bin/env bash
set -euo pipefail

OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
OLLAMA_REASONING_MODEL="${OLLAMA_REASONING_MODEL:-qwen3:8b}"
OLLAMA_EMBED_MODEL="${OLLAMA_EMBED_MODEL:-bge-m3}"

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required to bootstrap Ollama models." >&2
  exit 1
fi

pull_model() {
  local model="$1"
  echo "Pulling Ollama model: ${model}"
  curl -fsS "${OLLAMA_BASE_URL%/}/api/pull" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"${model}\"}" >/dev/null
}

curl -fsS "${OLLAMA_BASE_URL%/}/api/tags" >/dev/null
pull_model "${OLLAMA_REASONING_MODEL}"
pull_model "${OLLAMA_EMBED_MODEL}"

echo "Ollama bootstrap complete."

