# VisionPro Medical

A private, local-first multimodal console for medical image analysis. Drop in DICOM, TIFF, or standard images, ask questions in a running conversation, and get responses from a vision-language model running entirely on your own machine — no data leaves the device.

![status](https://img.shields.io/badge/status-active-teal) ![license](https://img.shields.io/badge/license-MIT-blue)

---

## Features

- **Multimodal chat** — attach one or more images per turn; the full conversation history (including images) is sent with each request for multi-turn context
- **DICOM support** — uncompressed and JPEG Baseline transfer syntaxes; multi-slice CT/MRI opens a slice scrubber with window/level controls and CT presets (soft tissue, lung, bone, brain, abdomen)
- **TIFF support** — pathology/histology exports decoded via UTIF
- **Two API formats** — llama.cpp / OpenAI-style (`/v1/chat/completions`) and Ollama native (`/api/chat`)
- **Session persistence** — conversations auto-save to localStorage and can be restored on reload; history panel keeps the last 15 sessions
- **Markdown export** — download any conversation as a `.md` file
- **Live status dot** — heartbeat polls the model endpoint every 30 s and updates the indicator in real time
- **Fully offline** — the proxy and frontend are static files; no telemetry, no cloud calls

---

## Quick start

### 1. Install llama.cpp

```bash
brew install llama.cpp        # macOS
# or build from source: https://github.com/ggml-org/llama.cpp
```

### 2. Download a vision model

MedGemma (recommended for medical imaging):
```bash
# 4B parameter, Q4_K_M quantisation — fits in 8 GB RAM
huggingface-cli download google/medgemma-4b-it-GGUF \
  medgemma-4b-it-Q4_K_M.gguf --local-dir ~/models

# Multimodal projector (required for image understanding)
huggingface-cli download google/medgemma-4b-it-GGUF \
  mmproj-medgemma-4b-it-f32.gguf --local-dir ~/models
```

Any other llava-compatible GGUF model works too (LLaVA 1.6, BakLLaVA, etc.).

### 3. Start everything

```bash
git clone https://github.com/drwaiphyo-spec/clinic-assistant
cd clinic-assistant

# Defaults: looks for model in ~/models/, proxy on :8090, llama-server on :8080
./start.sh

# Or specify paths explicitly
LLAMA_MODEL=~/models/medgemma-4b-it-Q4_K_M.gguf \
LLAMA_MMPROJ=~/models/mmproj-medgemma-4b-it-f32.gguf \
./start.sh
```

The script starts llama-server and the proxy, waits for the model to load, then opens `http://127.0.0.1:8090` in your browser. Press `Ctrl-C` to stop both processes.

### 4. Verify (optional)

```bash
python3 test.py                           # against the proxy (default)
python3 test.py http://127.0.0.1:8080/v1  # direct to llama-server
python3 test.py --ollama                  # Ollama on :11434
```

---

## Manual setup

If you prefer to manage processes yourself:

```bash
# Terminal 1 — model server
llama-server \
  --model ~/models/medgemma-4b-it-Q4_K_M.gguf \
  --mmproj ~/models/mmproj-medgemma-4b-it-f32.gguf \
  --port 8080 --host 127.0.0.1 --ctx-size 8192

# Terminal 2 — static + proxy server
python3 server.py        # listens on :8090
```

Then open `http://127.0.0.1:8090`.

---

## Settings

Open the settings drawer (`⌘K` or the gear icon) to configure:

| Setting | Default | Notes |
|---|---|---|
| API format | llama.cpp / OpenAI | Switch to Ollama native if using `ollama serve` |
| Base URL | `http://127.0.0.1:8090/api` | Points at the proxy; change to `:8080/v1` to bypass it |
| Model | `medgemma-4b-it-Q4_K_M.gguf` | Must match `--model` alias on the server |
| System prompt | Medical assistant | Customise per session |
| Temperature | 0.2 | Lower = more deterministic |
| Max tokens | 1024 | |
| Streaming | On | |

---

## DICOM notes

- **Supported transfer syntaxes**: Explicit/Implicit Little Endian (uncompressed), JPEG Baseline (`1.2.840.10008.1.2.4.50`)
- **Unsupported**: JPEG 2000, JPEG-LS, RLE — re-export as Explicit Little Endian or JPEG Baseline from your PACS/viewer
- Multi-frame files (CT/MRI volumes) open a slice scrubber; use "Add this slice" or "Sample 5 slices" to pick frames to send
- Window/level controls appear automatically for grayscale DICOM; CT presets apply when modality tag is `CT`
- PACS exports without a `.dcm` extension are auto-detected by the `DICM` magic bytes at offset 128

---

## Architecture

```
Browser (index.html)
    │
    │  POST /api/chat/completions   GET /api/models
    ▼
server.py  :8090
    │  (proxies /api/* → /v1/* on upstream)
    │
    ▼
llama-server  :8080
    (or Ollama :11434 — pointed at directly, no proxy needed)
```

The proxy exists solely to add CORS headers and forward `Authorization`, so the single-file frontend can run from any origin during development.

---

## Disclaimer

This tool is intended to support qualified clinicians — not to replace clinical judgement. All findings should be verified independently. Do not use as the sole basis for diagnosis or treatment decisions.
