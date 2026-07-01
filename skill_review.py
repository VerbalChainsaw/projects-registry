#!/usr/bin/env python3
"""Markdown / SKILL.md review — separate from deepseek_review.py.

Use when the artifact is documentation rather than Python source.
Reuses the same auth / redaction / selftest as deepseek_review.py.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
KEY_FILE = Path(r"C:/Users/zerop/.deepcode/settings.json")

SKILL_REVIEW_PROMPT = """\
You are reviewing SKILL.md file(s) for a project-registry feature
consumed by an LLM agent at session start. The skill is the documentation
layer of a project registry.

Runtime context you should know:
- Hermes skill scanner (agent/skill_utils.py:extract_skill_description)
  truncates frontmatter description to 60 chars.
- Hermes runtime copy at C:/hermes/skills/projects-registry/ has SKILL.md
  only (no projects.py bundled). The script lives at the canonical repo
  path C:/Users/zerop/Development/projects-registry/projects.py.
- The 4 other roots (opencode/.claude/.codex + mavis) have full copies.
- install_skills.py is the orchestrator that fans the skill out to 5 roots.
- projects.py --selftest returns 15/15.

These are MARKDOWN docs, not Python. Do not run them. Read carefully.

The skill must:
1. Match the trigger words Director Gabriel actually uses for project names.
2. Give the agent a runnable command (path must be accurate).
3. Not contradict the runtime reality.
4. Be self-consistent.

Output EXACTLY this structure:
VERDICT: APPROVE | APPROVE_WITH_NITS | CHANGES_REQUESTED | REJECT
LIFT: one sentence
RISKS: comma-separated, empty if none
NITS: comma-separated, empty if none
REWRITE: <only if CHANGES_REQUESTED or REJECT — minimal patch>

{body}
"""


def _key() -> str:
    if not KEY_FILE.exists():
        sys.exit(f"key file missing: {KEY_FILE}")
    data = json.loads(KEY_FILE.read_text(encoding="utf-8"))
    return data.get("env", {}).get("API_KEY") or sys.exit(
        f"API_KEY not found in {KEY_FILE}"
    )


def review_skill(path: str, model: str = "deepseek-v4-pro") -> dict:
    src = Path(path).read_text(encoding="utf-8")
    src_path = Path(path)
    size_bytes = src_path.stat().st_size
    if size_bytes > 64 * 1024:
        sys.exit(f"file too large: {size_bytes} bytes (max 65536)")
    prompt = SKILL_REVIEW_PROMPT.format(body=f"=== {path} ({size_bytes} bytes) ===\n{src}")
    key = _key()
    try:
        r = requests.post(
            DEEPSEEK_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4000,
            },
            timeout=120,
        )
        r.raise_for_status()
    except requests.exceptions.Timeout:
        sys.exit("deepseek timed out")
    except requests.exceptions.HTTPError as e:
        sys.exit(f"deepseek HTTP {e.response.status_code if e.response else '?'}: {e}")
    except requests.exceptions.RequestException as e:
        sys.exit(f"deepseek failed: {e}")
    return r.json()


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv[0] == "--selftest":
        # Same offline checks as deepseek_review.py
        if not _key() or len(_key()) < 8:
            print("FAIL: key missing/short")
            return 1
        if "{body}" not in SKILL_REVIEW_PROMPT:
            print("FAIL: prompt template missing {body}")
            return 1
        print("OK: skill-review prompt template + key")
        return 0
    model = "deepseek-v4-pro"
    paths = []
    i = 0
    if "--model" in argv:
        idx = argv.index("--model")
        model = argv[idx + 1]
        paths = [p for p in argv[:idx] + argv[idx + 2:] if p]
    else:
        paths = [p for p in argv if not p.startswith("--")]
    for p in paths:
        resp = review_skill(p, model)
        msg = resp["choices"][0]["message"]
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning_content") or ""
        if reasoning:
            print("--- reasoning (truncated) ---")
            print(reasoning[:1500])
            print("--- verdict ---")
        print(content)
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))