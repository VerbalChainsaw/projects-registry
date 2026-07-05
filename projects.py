#!/usr/bin/env python3
"""projects-registry lookup.

One-call, deterministic, in-process. No network, no DB, no cache.

Usage:
    python projects.py <mention>           # full record for mention
    python projects.py --list              # all projects, one line each
    python projects.py --path <mention>    # just the path (faster machine-use)
    python projects.py --exists <mention>  # exit 0 if known, 1 if not
    python projects.py --selftest          # run 10-case verification
    python projects.py --scan              # scan filesystem for candidate projects
                                           # (prints JSON to stdout, NEVER mutates registry)
    python projects.py --scan --diff       # only show projects NOT already in registry
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Canonical registry lives in the repo (this script's dir). Override with
# PROJECTS_REGISTRY env var if you have a stale mirror you want to read.
REGISTRY = Path(os.environ.get("PROJECTS_REGISTRY", str(Path(__file__).parent / "projects.json")))

# Roots the scanner walks. Curated list, not auto-discovery — these are where
# Director's project workspaces actually live.
SCAN_ROOTS = [
    Path(r"C:/Users/zerop/Development"),
    Path(r"C:/Users/zerop/Claude/Projects"),
]

# Skip names: known noise (cache dirs, dotfiles, archives).
# Matched against dir basename. Case-insensitive.
SCAN_SKIP_NAMES = frozenset({
    ".git", ".github", ".vscode", ".idea", ".cache", "__pycache__",
    "node_modules", "venv", ".venv", ".tox", "dist", "build",
    "coverage", "out", "target", "_stashed", "_agent-workspace",
    "backups", "archives", "scratchpads", "downloads", "documents",
    "uploads", "textgen", "recent", "media", "desktop", "application data",
    "local settings", "my documents", "bin", "lib",
    "include", "scripts", "prompts", "datasets", "docs", "research",
    "files", "img", "notes", "notes-old", "pets", "mavis", "hermes",
    "taxes", "finances", "naea", "youtube", "reddit", "resumes",
})

# Skip names containing any of these substrings.
SCAN_SKIP_NAME_PATTERNS = (
    re.compile(r"backup[-_]", re.I),
    re.compile(r"\.bak$", re.I),
    re.compile(r"-old$", re.I),
    re.compile(r"-copy$", re.I),
    re.compile(r"-archive$", re.I),
)

# Canonical project markers. A dir qualifies as a candidate if it has at
# least one of these. Ponytail: .git alone is NOT enough — an empty
# version-controlled dir isn't a project. AGENTS.md/README.md alone ARE
# enough (docs-only repo) — that's still a real project.
SCAN_MARKERS = (
    "package.json", "pyproject.toml", "Cargo.toml", "go.mod",
    "setup.py", "Gemfile", "composer.json", "build.gradle",
    "pubspec.yaml", "mix.exs", "README.md", "AGENTS.md",
    "requirements.txt", "main.py", "app.py", "index.js",
    "index.ts", "src", "lib", "tests", "test",
)


def _load() -> dict:
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


def _index(data: dict) -> dict:
    """Precompute lowercase alias -> project name. First wins on duplicates."""
    idx = {}
    for p in data["projects"]:
        for k in [p["name"]] + p.get("aliases", []):
            idx.setdefault(k.lower(), p["name"])
    return idx


def _norm(s: str) -> str:
    """Lowercase, collapse - _ space to a common token for substring match."""
    return re.sub(r"[\s_-]+", "", s.lower())


def lookup(mention: str, idx: dict, data: dict) -> list[dict]:
    """Return all candidate projects matching `mention`.

    Match logic: case-insensitive, separator-insensitive substring match
    (mention in alias, OR alias in mention). Combined pool sorted longest-
    alias-first. Empty mention returns [].

    Multiple candidates means the mention is genuinely ambiguous (e.g.
    "argus" → Hermes + ARGUS_*) — the caller must disambiguate. Single
    candidate returns as the unambiguous match.
    """
    m = _norm(mention)
    if not m:
        return []
    pool: dict[str, int] = {}          # pname -> longest matching alias length
    for alias, pname in idx.items():
        a = _norm(alias)
        if not a:
            continue
        if m == a or m in a or a in m:
            if pname not in pool or len(a) > pool[pname]:
                pool[pname] = len(a)

    # ponytail: O(n*aliases) per call, fine for n=20 projects. Add prefix index if n>500.
    candidates = sorted(pool.keys(), key=lambda n: -pool[n])
    out = []
    for n in candidates:
        match = next((p for p in data["projects"] if p["name"] == n), None)
        if match is None:
            # index points to a name not in projects — corrupted registry
            sys.exit(f"registry corrupt: alias index references {n!r} but no project with that name exists")
        out.append(match)
    return out


def format_record(p: dict) -> str:
    """Render a project record as a human-readable block. Ponytail: missing
    optional fields render as '<missing>' rather than literal 'None' so the
    output stays grep-able."""
    lines = [
        f"PROJECT: {p.get('name') or '<missing>'}",
        f"PATH: {p.get('path') or '<missing>'}",
        f"ALIASES: {', '.join([p.get('name', '')] + (p.get('aliases') or []))}",
        f"TEST: {p.get('test_cmd') or '—'}",
        f"DESCRIPTION: {p.get('description') or '<missing>'}",
    ]
    anchors = p.get("memory_anchors") or []
    lines.append(f"MEMORY ANCHORS: {'; '.join(anchors) if anchors else 'none'}")
    return "\n".join(lines)


# =========================================================================
# Scanner — discovers candidate projects on the filesystem.
#
# NEVER mutates the registry. Emits JSON to stdout only. The user reviews
# and merges manually with `patch` or a small merge script.
#
# Bounded: walks at most 2 curated roots (SCAN_ROOTS), only first-level
# children. O(n_dirs × n_markers) syscalls, ~80 dirs × 13 markers = ~1000.
# Sub-second on a warm disk.
# =========================================================================

def _scan_read_description(path: Path) -> str | None:
    """Extract first meaningful line from README.md / readme.md. Returns None
    on any read/decode failure so one bad README can't kill the scan."""
    for name in ("README.md", "readme.md", "Readme.md"):
        rp = path / name
        if not rp.exists():
            continue
        try:
            txt = rp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        # Skip blank lines and headings; first non-heading prose line wins.
        for line in txt.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("#", "!", "<", "[", "{")):
                continue
            return stripped[:300]
    return None


def _scan_detect_stack(path: Path) -> list[str]:
    """Ponytail: one Path.exists() check per marker. Returns short stack tags."""
    stack = []
    if (path / "package.json").exists():
        stack.append("node")
    if (path / "tsconfig.json").exists():
        stack.append("typescript")
    if (path / "pyproject.toml").exists() or (path / "setup.py").exists():
        stack.append("python")
    if (path / "Cargo.toml").exists():
        stack.append("rust")
    if (path / "go.mod").exists():
        stack.append("go")
    return stack


# Ponytail: bounds — never read more than this many docs per project, never
# return more than this many entry points / endpoints per project. Keeps
# total scan cost O(n × 3 × file_cap) regardless of how fat READMEs get.
_ENTRY_DOCS = ("package.json", "README.md", "readme.md", "AGENTS.md")
_MAX_ENTRIES_PER_PROJECT = 10

# URL / port patterns. Cap = avoid matching 200 examples in a single README.
_URL_RX = re.compile(
    r"https?://[^\s<>\"'`)\]]+",
    re.I,
)
# Ponytail: PORT/HOST/URL/ENDPOINT must be followed by an actual port number,
# not an IP address. Match digits only between `=` and a non-digit boundary.
_PORT_RX = re.compile(
    r"\b(?:PORT|ENDPOINT)\s*=\s*[\"']?(\d{2,5})\b|"
    r"\b(?:port|localhost|127\.0\.0\.1|0\.0\.0\.0):(\d{2,5})\b",
    re.I,
)
# Skip URLs that are clearly not endpoints (images, badges, package registries,
# CDNs, model hosting, agent skill registries, docs sites).
_URL_SKIP_PATTERNS = (
    re.compile(r"\.(?:png|jpg|jpeg|gif|svg|ico)(\?|$)", re.I),
    re.compile(r"https?://(?:img\.shields\.io|github\.com/|www\.github\.com/|githubusercontent\.com/)", re.I),
    re.compile(r"npmjs\.com/|pypi\.org/|crates\.io/|pkg\.pr\.new/", re.I),
    re.compile(r"https?://unpkg\.com/|https?://cdn\.jsdelivr\.net/|https?://cdnjs\.cloudflare\.com/", re.I),
    re.compile(r"https?://huggingface\.co/|https?://openai\.com/|https?://anthropic\.com/", re.I),
    re.compile(r"https?://colab\.research\.google\.com/|https?://kaggle\.com/", re.I),
    re.compile(r"https?://agentskills\.io|https?://opensource\.org/|https?://creativecommons\.org/", re.I),
    re.compile(r"https?://(?:localhost|127\.0\.0\.1):\d+/(?:dist|src|lib|test|tests|node_modules|docs)/", re.I),
)


# Ponytail: bound — never read more than this per file. Caps memory under
# pathological READMEs (100MB binary-as-text would otherwise allocate fully).
_MAX_READ_BYTES = 256 * 1024


def _scan_read_text(path: Path) -> str:
    """Read text file safely. Returns empty string on any failure. Caps reads
    at _MAX_READ_BYTES so a giant README can't spike memory."""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            return f.read(_MAX_READ_BYTES)
    except OSError:
        return ""


def _scan_extract_entry_points(path: Path) -> list[str]:
    """Discover the project's primary entry point(s). Read-only.

    Strategy:
      - Node: package.json "main" field, plus any "scripts.start" / "scripts.dev"
        that references a JS file.
      - Python: pyproject.toml "scripts" entries, plus well-known root files
        (main.py, app.py, launcher.py, __main__.py).
      - Capped at _MAX_ENTRIES_PER_PROJECT.

    Returns [] if nothing found.
    """
    found: list[str] = []

    # Node: package.json
    pj = path / "package.json"
    if pj.exists():
        try:
            data = json.loads(_scan_read_text(pj))
        except (json.JSONDecodeError, OSError):
            data = None
        if isinstance(data, dict):
            main = data.get("main")
            if isinstance(main, str) and main:
                found.append(main)
            scripts = data.get("scripts")
            if isinstance(scripts, dict):
                for key in ("start", "dev", "serve"):
                    cmd = scripts.get(key)
                    if isinstance(cmd, str) and cmd:
                        # Extract just the file path from the command (best-effort).
                        # e.g. "node src/server/app.js" → "src/server/app.js"
                        parts = cmd.split()
                        for p in parts:
                            if p.endswith((".js", ".mjs", ".ts", ".cjs")) and not p.startswith("-"):
                                if p not in found:
                                    found.append(p)
                                break

    # Python: well-known root files
    for candidate in ("main.py", "app.py", "launcher.py", "__main__.py", "run.py"):
        if (path / candidate).exists() and candidate not in found:
            found.append(candidate)

    # Ponytail: drop the pyproject.toml [scripts] branch — Reasoner flagged
    # that the literal string "pyproject.toml [scripts]" isn't a real entry
    # point and would confuse consumers. Parsing TOML inline is more code
    # than it's worth; surface the well-known root files instead.

    return found[:_MAX_ENTRIES_PER_PROJECT]


def _scan_extract_endpoints(path: Path) -> list[str]:
    """Discover URLs / ports the project instantiates. Read-only.

    Searches README.md, AGENTS.md, and package.json for URL + port patterns.
    Filters out image URLs and known badge registries. Capped.

    Returns [] if nothing found. Format: ['http://127.0.0.1:4098', 'https://...'].
    """
    urls: list[str] = []

    def _extract(text: str) -> None:
        for m in _URL_RX.findall(text):
            if any(pat.search(m) for pat in _URL_SKIP_PATTERNS):
                continue
            if m not in urls:
                urls.append(m)
                if len(urls) >= _MAX_ENTRIES_PER_PROJECT:
                    return
        for m in _PORT_RX.findall(text):
            # Port regex has two groups; pick the non-empty one.
            port = m[0] or m[1]
            if not port:
                continue
            synthetic = f"http://127.0.0.1:{port}"
            if synthetic not in urls:
                urls.append(synthetic)
                if len(urls) >= _MAX_ENTRIES_PER_PROJECT:
                    return

    for doc in _ENTRY_DOCS:
        p = path / doc
        if p.exists():
            _extract(_scan_read_text(p))
            if len(urls) >= _MAX_ENTRIES_PER_PROJECT:
                break

    return urls[:_MAX_ENTRIES_PER_PROJECT]


def _scan_classify(path: Path) -> dict | None:
    """If path looks like a project, return a candidate record. Else None.

    Ponytail: skip ALL symlinks — symlink targets inside SCAN_ROOTS still
    create duplicate hits and risk following outside the roots if a target
    later gets moved. Real path only.
    """
    name = path.name
    if not name or name.startswith("."):
        return None  # skip dotfiles wholesale — keeps noise low
    if name.lower() in SCAN_SKIP_NAMES:
        return None
    for pat in SCAN_SKIP_NAME_PATTERNS:
        if pat.search(name):
            return None
    if not path.is_dir():
        return None
    if path.is_symlink():
        return None  # ponytail: don't follow symlinks — bounds blast radius

    # Has at least one canonical marker.
    markers = [m for m in SCAN_MARKERS if (path / m).exists()]
    if not markers:
        return None

    return {
        "name": name,
        "path": str(path).replace("\\", "/"),
        "stack": _scan_detect_stack(path),
        "markers": markers,
        "description": _scan_read_description(path),
        "entry_points": _scan_extract_entry_points(path),
        "endpoints": _scan_extract_endpoints(path),
    }


def scan_projects(roots: list[Path] | None = None) -> list[dict]:
    """Walk SCAN_ROOTS (or supplied list), return candidate project dicts.

    Stable order: by (root, name) so reruns produce identical output.
    Idempotent: no side effects, no caching, no global state mutation.
    """
    roots = roots or SCAN_ROOTS
    out: list[dict] = []
    for root in roots:
        if not root.exists():
            continue
        try:
            children = sorted(root.iterdir(), key=lambda p: p.name.lower())
        except (PermissionError, OSError) as e:
            # ponytail: log and skip — one inaccessible root must not kill the scan.
            print(f"scan: skipping {root}: {e}", file=sys.stderr)
            continue
        for child in children:
            try:
                info = _scan_classify(child)
            except (PermissionError, OSError) as e:
                print(f"scan: skipping {child}: {e}", file=sys.stderr)
                continue
            if info is not None:
                out.append(info)
    return out


def _scan_diff(known_paths: set[str]) -> list[dict]:
    """Return candidates not already in registry (by normalized path)."""
    candidates = scan_projects()
    norm_known = {p.rstrip("/").lower() for p in known_paths}
    return [c for c in candidates if c["path"].rstrip("/").lower() not in norm_known]


def _cmd_scan(argv: list[str]) -> int:
    """Handle the --scan flag. Prints JSON to stdout. Returns 0."""
    diff_only = "--diff" in argv
    if diff_only:
        # --diff requires the registry to compare against; let _load() error
        # out naturally if it's missing. No silent fallback that hides a
        # real config issue.
        data = _load()
        known = {p["path"] for p in data.get("projects", [])}
        out = _scan_diff(known)
    else:
        out = scan_projects()
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 1
    # --scan runs WITHOUT loading the registry — scanner is read-only on the FS.
    if argv[0] == "--scan":
        return _cmd_scan(argv[1:])

    data = _load()
    idx = _index(data)

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
    """Smoke test: 10 must-hit lookups + 4 scan invariants. Returns 0 on pass, 1 on fail.

    Lookup case shape: (mention, want) where want is one of:
      - ("name", "<ProjectName>")       : unique match, name must equal
      - ("any_of", ["A", "B"])          : ambiguous, expected names must all appear
      - ("miss",)                       : must return 0 candidates
    """
    cases = [
        ("sunosavvy",          ("name",   "SunoSavvy")),
        ("jobby",              ("any_of", ["JobbyJob"])),  # ambiguous: JobbyJob + JobbyJob Design System both match
        ("verbal-chainsaw",    ("name",   "VerbalChainsaw OpenCode")),  # hyphen variant
        ("verbal_chainsaw",    ("name",   "VerbalChainsaw OpenCode")),  # underscore variant
        ("opencode fork",      ("name",   "VerbalChainsaw OpenCode")),  # space + alias
        ("SUNOSAVVY",          ("name",   "SunoSavvy")),                 # uppercase
        ("argus",              ("any_of", ["ARGUS", "ARGUS_OSINT"])),  # Hermes "argus" alias shadowed by new Development/ARGUS (alpha first-wins)
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

    # === Scanner invariants ===
    # Ponytail: scan must be bounded (no more than ~200 entries — keeps output
    # from ever being a megabyte-level dump if a recursive symlink explodes).
    scan_a = scan_projects()
    scan_b = scan_projects()  # idempotency check
    if len(scan_a) > 200:
        print(f"FAIL: scan returned {len(scan_a)} candidates (cap 200)")
        fails += 1
    else:
        print(f"OK: scan bounded ({len(scan_a)} candidates, cap 200)")
    if len(scan_a) != len(scan_b):
        print(f"FAIL: scan not idempotent (run 1: {len(scan_a)}, run 2: {len(scan_b)})")
        fails += 1
    else:
        print(f"OK: scan idempotent (2 runs both {len(scan_a)})")
    # Each candidate has required keys + types
    required = {"name", "path", "stack", "markers", "description",
                "entry_points", "endpoints"}
    bad = [c for c in scan_a if not required.issubset(c.keys())
           or not isinstance(c["stack"], list)
           or not isinstance(c["markers"], list)
           or not isinstance(c["entry_points"], list)
           or not isinstance(c["endpoints"], list)]
    if bad:
        print(f"FAIL: {len(bad)} candidates missing required keys or wrong types")
        for c in bad[:3]:
            print(f"  - {c.get('name')!r}: {set(c.keys()) ^ required}")
        fails += 1
    else:
        print(f"OK: scan candidates well-formed ({len(scan_a)} entries)")
    # entry_points + endpoints must respect the per-project cap.
    over_cap = [c["name"] for c in scan_a
                if len(c["entry_points"]) > _MAX_ENTRIES_PER_PROJECT
                or len(c["endpoints"]) > _MAX_ENTRIES_PER_PROJECT]
    if over_cap:
        print(f"FAIL: scan cap violated for {len(over_cap)} projects: {over_cap[:3]}")
        fails += 1
    else:
        print(f"OK: scan respects per-project cap ({_MAX_ENTRIES_PER_PROJECT})")
    # No mutation: registry must be unchanged after scan.
    data_after = _load()
    if data_after != data:
        print(f"FAIL: registry mutated by scan")
        fails += 1
    else:
        print(f"OK: scan did not mutate registry")

    return 1 if fails else 0


if __name__ == "__main__":
    # ponytail: global lock not needed — file is read once per call, 8KB, sub-ms parse
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        sys.exit(_selftest())
    sys.exit(main(sys.argv[1:]))