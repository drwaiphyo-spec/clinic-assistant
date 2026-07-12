#!/usr/bin/env bash
# Start llama-server (with optional mmproj) + the proxy, then open the browser.
#
# Override defaults via env vars:
#   LLAMA_SERVER=/path/to/llama-server
#   LLAMA_MODEL=/path/to/model.gguf
#   LLAMA_MMPROJ=/path/to/mmproj.gguf   (leave unset to skip --mmproj)
#   MODEL_PORT=8080
#   PROXY_PORT=8090
#   CTX_SIZE=8192
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODEL_PORT="${MODEL_PORT:-8080}"
PROXY_PORT="${PROXY_PORT:-8090}"
CTX_SIZE="${CTX_SIZE:-8192}"

# ---- locate llama-server ----
LLAMA_SERVER="${LLAMA_SERVER:-$(command -v llama-server 2>/dev/null || true)}"
if [ -z "$LLAMA_SERVER" ] || [ ! -x "$LLAMA_SERVER" ]; then
  echo "ERROR: llama-server not found."
  echo "  Install it (e.g. brew install llama.cpp) or set LLAMA_SERVER=/path/to/llama-server"
  exit 1
fi

# ---- locate model ----
LLAMA_MODEL="${LLAMA_MODEL:-}"
if [ -z "$LLAMA_MODEL" ]; then
  # Try common default locations
  for candidate in \
    "$HOME/models/medgemma-4b-it-Q4_K_M.gguf" \
    "$HOME/models/medgemma-27b-it-Q4_K_M.gguf" \
    "$SCRIPT_DIR"/*.gguf; do
    if [ -f "$candidate" ]; then LLAMA_MODEL="$candidate"; break; fi
  done
fi
if [ -z "$LLAMA_MODEL" ] || [ ! -f "$LLAMA_MODEL" ]; then
  echo "ERROR: No model found. Set LLAMA_MODEL=/path/to/your-model.gguf"
  exit 1
fi

# ---- optional multimodal projector ----
LLAMA_MMPROJ="${LLAMA_MMPROJ:-}"
if [ -z "$LLAMA_MMPROJ" ]; then
  # Look for mmproj next to the model
  MODEL_DIR="$(dirname "$LLAMA_MODEL")"
  for candidate in "$MODEL_DIR"/mmproj*.gguf "$MODEL_DIR"/mmproj*.bin; do
    if [ -f "$candidate" ]; then LLAMA_MMPROJ="$candidate"; break; fi
  done
fi

# ---- free ports ----
for port in "$MODEL_PORT" "$PROXY_PORT"; do
  lsof -ti "tcp:$port" 2>/dev/null | xargs kill -9 2>/dev/null || true
done
sleep 0.5

# ---- start llama-server ----
echo "Starting llama-server on port $MODEL_PORT"
echo "  model:  $LLAMA_MODEL"
if [ -n "$LLAMA_MMPROJ" ]; then
  echo "  mmproj: $LLAMA_MMPROJ"
  "$LLAMA_SERVER" \
    --model "$LLAMA_MODEL" \
    --mmproj "$LLAMA_MMPROJ" \
    --port "$MODEL_PORT" \
    --host 127.0.0.1 \
    --ctx-size "$CTX_SIZE" \
    --log-disable \
    > /tmp/llama-server.log 2>&1 &
else
  echo "  mmproj: (none — images will be ignored by the model)"
  "$LLAMA_SERVER" \
    --model "$LLAMA_MODEL" \
    --port "$MODEL_PORT" \
    --host 127.0.0.1 \
    --ctx-size "$CTX_SIZE" \
    --log-disable \
    > /tmp/llama-server.log 2>&1 &
fi
LLAMA_PID=$!

# ---- start proxy ----
echo "Starting proxy on port $PROXY_PORT"
python3 "$SCRIPT_DIR/server.py" "$PROXY_PORT" > /tmp/visionpro-proxy.log 2>&1 &
PROXY_PID=$!

# ---- wait for model to be ready ----
echo -n "Waiting for model to load (logs: /tmp/llama-server.log) "
MAX_WAIT=120
for i in $(seq 1 $MAX_WAIT); do
  if ! kill -0 "$LLAMA_PID" 2>/dev/null; then
    echo ""
    echo "ERROR: llama-server exited early. Check /tmp/llama-server.log"
    kill "$PROXY_PID" 2>/dev/null || true
    exit 1
  fi
  if curl -sf "http://127.0.0.1:$MODEL_PORT/health" > /dev/null 2>&1; then
    echo " ready."
    break
  fi
  if [ "$i" -eq "$MAX_WAIT" ]; then
    echo ""
    echo "ERROR: Model didn't become ready in ${MAX_WAIT}s. Check /tmp/llama-server.log"
    kill "$LLAMA_PID" "$PROXY_PID" 2>/dev/null || true
    exit 1
  fi
  sleep 1
  [ $((i % 10)) -eq 0 ] && echo -n "." || echo -n "."
done

URL="http://127.0.0.1:$PROXY_PORT"
echo "Open $URL"
open "$URL" 2>/dev/null || xdg-open "$URL" 2>/dev/null || true

trap "echo 'Shutting down…'; kill $LLAMA_PID $PROXY_PID 2>/dev/null; exit 0" INT TERM
wait
