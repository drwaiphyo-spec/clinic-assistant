#!/usr/bin/env python3
"""
Smoke test: send a tiny synthetic image and verify the model responds.

Usage:
    python3 test.py                          # proxy at default http://127.0.0.1:8090/api
    python3 test.py http://127.0.0.1:8080/v1 # direct llama-server
    python3 test.py --ollama                 # Ollama at http://127.0.0.1:11434
"""
import base64, json, struct, sys, time, urllib.request, urllib.error, zlib

# ---- build a 4×4 checkerboard PNG in pure Python ----
def make_png(size=4):
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    rows = []
    for y in range(size):
        row = b"\x00"  # filter byte
        for x in range(size):
            if (x + y) % 2 == 0:
                row += b"\xFF\xFF\xFF"  # white
            else:
                row += b"\x00\x00\x00"  # black
        rows.append(row)

    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(b"".join(rows)))
    iend = chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


def run(base_url, fmt):
    png = make_png()
    b64 = "data:image/png;base64," + base64.b64encode(png).decode()
    prompt = "Describe this image in one sentence."

    if fmt == "openai":
        url = base_url.rstrip("/") + "/chat/completions"
        body = {
            "model": "test",
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": b64}},
                {"type": "text", "text": prompt},
            ]}],
            "max_tokens": 64,
            "stream": False,
        }
    else:  # ollama
        url = base_url.rstrip("/") + "/chat"
        body = {
            "model": "llava",
            "messages": [{"role": "user", "content": prompt,
                          "images": [b64.split(",", 1)[1]]}],
            "stream": False,
            "options": {"num_predict": 64},
        }

    print(f"POST {url}")
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    t0 = time.monotonic()
    try:
        resp = urllib.request.urlopen(req, timeout=90)
        elapsed = time.monotonic() - t0
        data = json.loads(resp.read())
        if fmt == "openai":
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        else:
            text = data.get("message", {}).get("content", "").strip()
        if not text:
            print(f"FAIL  Empty response body: {json.dumps(data)[:200]}")
            return False
        print(f"PASS  {elapsed:.1f}s — {text!r}")
        return True
    except urllib.error.HTTPError as e:
        body_text = e.read().decode(errors="replace")[:300]
        print(f"FAIL  HTTP {e.code}: {body_text}")
        return False
    except Exception as e:
        print(f"FAIL  {e}")
        return False


def check_health(base_url):
    health_url = base_url.rstrip("/") + "/models"
    try:
        urllib.request.urlopen(health_url, timeout=5)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    args = sys.argv[1:]
    ollama = "--ollama" in args
    args = [a for a in args if a != "--ollama"]

    if args:
        base = args[0]
    elif ollama:
        base = "http://127.0.0.1:11434/api"
    else:
        base = "http://127.0.0.1:8090/api"

    fmt = "ollama" if ollama else "openai"

    print(f"Smoke test  base={base}  format={fmt}")
    print("-" * 50)

    if not check_health(base):
        print(f"WARN  Health check failed for {base}/models — server may not be running.")

    ok = run(base, fmt)
    sys.exit(0 if ok else 1)
