#!/usr/bin/env python3
"""Get an outside code review from DeepSeek.

Usage:
    python deepseek_review.py <file>          # review a single file
    python deepseek_review.py --json <file>   # raw JSON response
    python deepseek_review.py --model M <file> # override model

Uses the DeepSeek API key from C:/Users/zerop/.deepcode/settings.json.
The key is flagged-as-burned in memory (2026-06-25 leak note). Use it
because it's what's wired up; rotate at provider when convenient.
Output is redacted to avoid leaking the key if the response is piped
somewhere.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-reasoner")
KEY_FILE = Path(r"C:/Users/zerop/.deepcode/settings.json")

REVIEW_PROMPT = """\
You are reviewing a Python utility for a senior dev's project registry.
Be terse, technical, no fluff. Output EXACTLY this structure:

VERDICT: <one of: APPROVE / APPROVE_WITH_NITS / CHANGES_REQUESTED / REJECT>
LIFT: <does it actually produce value, or is it decoration? one sentence>
RISKS: <comma-separated list, empty if none>
NITS: <comma-separated list of small fixes, empty if none>
REWRITE: <only if CHANGES_REQUESTED or REJECT — minimal corrected code>

File under review ({path}, {size} bytes):

```python
{src}
```

Context: this is one piece of a multi-file "projects-registry" feature
(JSON registry + lookup script + skill + SOUL.md hook + installer + this
reviewer). The reviewer script (`deepseek_review.py`) is opt-in dev
tooling — it is NOT part of the sub-ms runtime lookup path. The runtime
lookup is network-free and deterministic; the reviewer exists so
Director can get an outside opinion before shipping.
"""


def _key() -> str:
    if not KEY_FILE.exists():
        sys.exit(f"key file missing: {KEY_FILE}")
    data = json.loads(KEY_FILE.read_text(encoding="utf-8"))
    return data.get("env", {}).get("API_KEY") or sys.exit(
        f"API_KEY not found in {KEY_FILE}\n  expected: env.API_KEY"
    )


def _redact(text: str, key: str) -> str:
    # ponytail: belt-and-suspenders — strip the key if it shows up in output
    if key and len(key) > 8:
        return text.replace(key, "<<REDACTED>>")
    return text


def review(path: str, model: str = DEFAULT_MODEL) -> dict:
    src_path = Path(path)
    src = src_path.read_text(encoding="utf-8")
    # ponytail: cap payload at 64KB to avoid token-burn on accidental mega-files.
    # 64KB is ~16K tokens which fits comfortably in the 4K-max response budget.
    MAX_BYTES = 64 * 1024
    size_bytes = src_path.stat().st_size
    if size_bytes > MAX_BYTES:
        sys.exit(f"file too large for review: {size_bytes} bytes (max {MAX_BYTES})\n  fix: review a smaller excerpt, or split the file first")
    prompt = REVIEW_PROMPT.format(path=path, size=size_bytes, src=src)
    key = _key()
    try:
        r = requests.post(
            DEEPSEEK_URL,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4000,
            },
            timeout=120,
        )
        r.raise_for_status()
    except requests.exceptions.Timeout:
        sys.exit(f"deepseek timed out after 120s\n  fix: try a smaller file, or retry with --model deepseek-v4-flash for faster response")
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        body = ""
        if e.response is not None:
            # redact BEFORE including in error message — e.response.text may echo the key
            body = _redact(e.response.text[:200], key)
        sys.exit(f"deepseek HTTP {code}\n  reason: {body or e}\n  fix: 401=bad key (rotate at provider), 429=rate-limited (wait), 5xx=retry")
    except requests.exceptions.ConnectionError as e:
        sys.exit(f"deepseek unreachable: {e}\n  fix: check network / VPN / firewall; api.deepseek.com must be reachable")
    except requests.exceptions.RequestException as e:
        sys.exit(f"deepseek request failed: {e}")
    try:
        return r.json()
    except json.JSONDecodeError as e:
        sys.exit(f"deepseek returned non-JSON: {e}\n  body head: {_redact(repr(r.text[:200]), key)}")


def _selftest() -> int:
    """Offline verification: no network. Checks key loads, JSON parses,
    prompt template formats, response shape is what we expect."""
    fails = 0

    # 1. key loads
    try:
        k = _key()
        if len(k) < 8:
            print(f"FAIL: key too short ({len(k)} chars)")
            fails += 1
        else:
            # ponytail: zero preview — Pro flagged partial-key leak risk. Length only.
            print(f"OK: key loaded ({len(k)} chars, masked)")
    except SystemExit as e:
        print(f"FAIL: key load: {e}")
        fails += 1
        return 1

    # 2. prompt template formats
    try:
        out = REVIEW_PROMPT.format(path="x.py", size=42, src="print('hi')")
        if "VERDICT:" not in out or "x.py" not in out or "print('hi')" not in out:
            print(f"FAIL: prompt template missing expected fields")
            fails += 1
        else:
            print("OK: prompt template formats")
    except KeyError as e:
        print(f"FAIL: prompt template missing field: {e}")
        fails += 1

    # 3. redaction works
    sample = f"hello {k} world"
    red = _redact(sample, k)
    if k in red:
        print(f"FAIL: redaction left key in output")
        fails += 1
    else:
        print(f"OK: redaction strips key from output")

    # 4. response shape parsing — synthesize a fake DeepSeek response
    fake = {
        "choices": [{"message": {"content": "VERDICT: APPROVE", "reasoning_content": ""}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "completion_tokens_details": {"reasoning_tokens": 3}},
    }
    try:
        msg = fake.get("choices", [{}])[0].get("message", {})
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        usage = fake.get("usage", {})
        rt = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
        if content != "VERDICT: APPROVE" or rt != 3:
            print(f"FAIL: response parse wrong: content={content!r} rt={rt}")
            fails += 1
        else:
            print("OK: response shape parse")
    except (KeyError, IndexError, AttributeError) as e:
        print(f"FAIL: response parse crashed: {e}")
        fails += 1

    return 1 if fails else 0


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--selftest":
        return _selftest()

    model = DEFAULT_MODEL
    raw = False
    i = 0
    while i < len(argv) and argv[i].startswith("--"):
        if argv[i] == "--json":
            raw = True
            i += 1
        elif argv[i] == "--model":
            if i + 1 >= len(argv):
                sys.exit(f"--model requires a value\n  usage: --model <name>")
            model = argv[i + 1]
            i += 2
        else:
            break
    if i >= len(argv):
        sys.exit(f"missing <file> argument\n  usage: deepseek_review.py [--json] [--model M] <file>")
    path = argv[i]
    if not Path(path).exists():
        sys.exit(f"file not found: {path}")

    resp = review(path, model)
    if raw:
        print(_redact(json.dumps(resp, indent=2), _key()))
        return 0

    choices = resp.get("choices") or []
    msg = choices[0].get("message", {}) if choices else {}
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning_content") or ""
    key = _key()
    if reasoning:
        print("--- reasoning (truncated) ---")
        print(_redact(reasoning[:1500], key))
        print("--- verdict ---")
    print(_redact(content, key))
    usage = resp.get("usage") or {}
    rt = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
    print(f"\n[tokens: prompt={usage.get('prompt_tokens')} "
          f"completion={usage.get('completion_tokens')} "
          f"reasoning={rt}]")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))