#!/usr/bin/env python3
"""projects-registry lookup.

One-call, deterministic, in-process. No network, no DB, no cache.

Usage:
    python projects.py <mention>           # full record for mention
    python projects.py --list              # all projects, one line each
    python projects.py --path <mention>    # just the path (faster machine-use)
    python projects.py --exists <mention>  # exit 0 if known, 1 if not
    python projects.py --selftest          # run 10-case verification
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REGISTRY = Path(os.environ.get("PROJECTS_REGISTRY", r"C:/hermes/projects.json"))


def _load():
    try:
        return json.loads(REGISTRY.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"registry missing: {REGISTRY}\n  fix: create the file or set PROJECTS_REGISTRY env var to the right path")
    except PermissionError as e:
        sys.exit(f"registry not readable: {REGISTRY}\n  reason: {e}\n  fix: check file ACLs or run from a user with read access")
    except UnicodeDecodeError as e:
        sys.exit(f"registry not UTF-8: {REGISTRY}\n  reason: {e}\n  fix: re-save the file as UTF-8 (no BOM)")
    except json.JSONDecodeError as e:
        sys.exit(f"registry corrupt: {REGISTRY}\n  reason: {e}\n  fix: run `python -c \"import json; json.load(open(r'{REGISTRY}'))\"` to see the exact line")
    except OSError as e:
        sys.exit(f"registry read failed: {REGISTRY}\n  reason: {e}\n  fix: check the path exists and the disk is healthy")


def _index(data):
    """Precompute lowercase alias -> project name. First wins on duplicates."""
    idx = {}
    for p in data["projects"]:
        for k in [p["name"]] + p.get("aliases", []):
            idx.setdefault(k.lower(), p["name"])
    return idx


def _norm(s: str) -> str:
    """Lowercase, collapse - _ space to a common token for substring match."""
    return re.sub(r"[\s_-]+", "", s.lower())


def lookup(mention: str, idx, data) -> list[dict]:
    """Return all candidate projects matching `mention` (substring, case-insensitive,
    space/hyphen/underscore-insensitive). Sorted longest-alias-first so 'dev-pulse'
    beats 'pulse' on 'pulse' input."""
    m = _norm(mention)
    if not m:
        return []
    hits = []
    for alias, pname in idx.items():
        a = _norm(alias)
        if m == a or m in a or a in m:
            hits.append((len(a), pname))
    # ponytail: O(n*aliases) per call, fine for n=20 projects. Add prefix index if n>500.
    seen = {}
    for length, pname in hits:
        if pname not in seen or length > seen[pname]:
            seen[pname] = length
    candidates = sorted(seen.keys(), key=lambda n: -seen[n])
    out = []
    for n in candidates:
        match = next((p for p in data["projects"] if p["name"] == n), None)
        if match is None:
            # index points to a name not in projects — corrupted registry
            sys.exit(f"registry corrupt: alias index references {n!r} but no project with that name exists")
        out.append(match)
    return out


def format_record(p: dict) -> str:
    lines = [
        f"PROJECT: {p.get('name', '<missing>')}",
        f"PATH: {p.get('path', '<missing>')}",
        f"ALIASES: {', '.join([p.get('name', '')] + (p.get('aliases') or []))}",
        f"TEST: {p.get('test_cmd') or '—'}",
        f"DESCRIPTION: {p.get('description', '<missing>')}",
    ]
    anchors = p.get("memory_anchors") or []
    lines.append(f"MEMORY ANCHORS: {'; '.join(anchors) if anchors else 'none'}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    data = _load()
    idx = _index(data)

    if not argv:
        print(__doc__, file=sys.stderr)
        return 1

    if argv == ["--list"]:
        for p in data["projects"]:
            print(f"- {p['name']:30s} path={p['path']}")
        return 0

    if argv[0] == "--exists":
        candidates = lookup(argv[1], idx, data) if len(argv) > 1 else []
        return 0 if candidates else 1

    if argv[0] == "--path":
        candidates = lookup(argv[1], idx, data) if len(argv) > 1 else []
        if not candidates:
            print("NO MATCH", file=sys.stderr)
            return 1
        if len(candidates) > 1:
            print(f"AMBIGUOUS: {' | '.join(c['name'] for c in candidates)}", file=sys.stderr)
            return 2
        print(candidates[0]["path"])
        return 0

    # default: full record lookup
    candidates = lookup(argv[0], idx, data)
    if not candidates:
        print(f"NO MATCH for {argv[0]!r}. Run with --list to see known projects.")
        return 1
    if len(candidates) > 1:
        print(f"AMBIGUOUS ({len(candidates)} candidates):")
        for c in candidates:
            print(f"  - {c['name']} ({c['path']})")
        return 2
    print(format_record(candidates[0]))
    return 0


def _selftest() -> int:
    """Smoke test: 10 must-hit lookups. Returns 0 on pass, 1 on fail.

    Case shape: (mention, want) where want is one of:
      - ("name", "<ProjectName>")       : unique match, name must equal
      - ("any_of", ["A", "B"])          : ambiguous, expected names must all appear
      - ("miss",)                       : must return 0 candidates
    """
    cases = [
        ("sunosavvy",          ("name",   "SunoSavvy")),
        ("jobby",              ("name",   "JobbyJob")),
        ("verbal-chainsaw",    ("name",   "VerbalChainsaw OpenCode")),  # hyphen variant
        ("verbal_chainsaw",    ("name",   "VerbalChainsaw OpenCode")),  # underscore variant
        ("opencode fork",      ("name",   "VerbalChainsaw OpenCode")),  # space + alias
        ("SUNOSAVVY",          ("name",   "SunoSavvy")),                 # uppercase
        ("argus",              ("any_of", ["Hermes", "ARGUS_OSINT"])),
        ("dev-pulse",          ("name",   "dev-pulse")),
        ("kalshi",             ("name",   "poly-kalshi-dashboard")),
        ("xyzzy-no-such",      ("miss",)),
    ]
    data = _load()
    idx = _index(data)
    fails = 0
    for mention, want in cases:
        cands = lookup(mention, idx, data)
        kind = want[0]
        if kind == "miss":
            if cands:
                print(f"FAIL: {mention!r} should miss, got {[c['name'] for c in cands]}")
                fails += 1
            else:
                print(f"OK: {mention!r} correctly misses")
            continue
        if kind == "any_of":
            names = [c["name"] for c in cands]
            missing = [n for n in want[1] if n not in names]
            if missing:
                print(f"FAIL: {mention!r} missing {missing}, got {names}")
                fails += 1
            else:
                print(f"OK: {mention!r} -> {names} (ambiguous as expected)")
            continue
        # name
        if not cands:
            print(f"FAIL: {mention!r} returned 0 candidates, want {want[1]}")
            fails += 1
            continue
        if cands[0]["name"] != want[1]:
            print(f"FAIL: {mention!r} -> {cands[0]['name']}, want {want[1]}")
            fails += 1
            continue
        print(f"OK: {mention!r} -> {want[1]}")
    return 1 if fails else 0


if __name__ == "__main__":
    # ponytail: global lock not needed — file is read once per call, 8KB, sub-ms parse
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        sys.exit(_selftest())
    sys.exit(main(sys.argv[1:]))