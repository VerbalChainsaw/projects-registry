---
name: projects-registry
description: Fires when Director says "SunoSavvy", "JobbyJob", "VerbalChainsaw", "opencode fork", "dev-pulse", "ARGUS", "center-audit", "poly-kalshi", "Hermes", or any project name. ALSO fires on "where's X", "path to X", "what's that project called", "test command for X". Resolves project paths via the canonical registry at C:/Users/zerop/Development/projects-registry/projects.json — call `python C:/Users/zerop/Development/projects-registry/projects.py <mention>` for a one-shot deterministic lookup. Do NOT spin up file scans to find a project; this skill exists.
---

# projects-registry

Single source of truth for project paths, aliases, and lead information.

Canonical source: `C:/Users/zerop/Development/projects-registry/` (repo,
GitHub: VerbalChainsaw/projects-registry). This skill is mirrored to
5 roots via `install_skills.py`:

| Root | Mode |
|---|---|
| `C:/hermes/skills/` | SKILL.md only — invoke canonical path for the script |
| `~/.mavis/skills/` | SKILL.md only — Mavis convention |
| `~/.config/opencode/skills/` | full (scripts bundled) |
| `~/.claude/skills/` | full (scripts bundled) |
| `~/.codex/skills/` | full (scripts bundled) |

All roots resolve to the same `projects.json` via `Path(__file__).parent`
in `projects.py`.

## When this fires

- Director says "the path to SunoSavvy", "JobbyJob stuff", "what's
  that project called", "where do I keep X", "the opencode fork",
  "argus family", "verba chainsaw", "what's the test command for
  center-audit", etc.
- ANY mention of a registered project name — even casually — load
  the registry first, do NOT default to `find` / `ls` / `search_files`.
- When you need the build / test / typecheck command for a project.

## Procedure

```bash
python C:/Users/zerop/Development/projects-registry/projects.py <mention>
python C:/Users/zerop/Development/projects-registry/projects.py --path <mention>   # just the path
python C:/Users/zerop/Development/projects-registry/projects.py --list              # all 38 projects
python C:/Users/zerop/Development/projects-registry/projects.py --selftest          # 15/15 must pass
python C:/Users/zerop/Development/projects-registry/projects.py --scan              # scan filesystem for candidate projects
python C:/Users/zerop/Development/projects-registry/projects.py --scan --diff       # only show projects NOT already in registry
```

Match is case-insensitive, separator-insensitive (space / `-` / `_`
collapse). Ambiguous mentions return all candidates with exit code 2;
non-matches return exit code 1.

Output shape on a hit:

```
PROJECT: <name>
PATH: <path>
ALIASES: <list>
TEST: <test command or —>
DESCRIPTION: <description>
MEMORY ANCHORS: <joined, or none>
```

If a project isn't in the registry, **ask Director to add it** — do NOT
`find`. The whole point of this skill is to prevent the half-hour
scavenger hunt.

## Adding a project

Edit `C:/Users/zerop/Development/projects-registry/projects.json`
directly. Required per project: `name`, `aliases`, `path`,
`description`. Optional: `repo_path`, `alt_paths`, `stack`,
`test_cmd`, `build_cmd`, `typecheck_cmd`, `memory_anchors`.

Aliases: include every variant Director actually uses. Run
`--selftest` after adding to catch separator-variant typos.

## Verification — selftest is non-optional

`projects.py --selftest` is the lift oracle. Ship it the first time,
run it after every edit, and run it once before declaring "this
works." A green selftest is the **only** deterministic signal that
the registry produces correct lookups.

After editing the registry:

```bash
python C:/Users/zerop/Development/projects-registry/projects.py --selftest   # MUST be 15/15
python C:/Users/zerop/Development/projects-registry/projects.py --list       # sanity check counts
python C:/Users/zerop/Development/projects-registry/install_skills.py        # fan out to 5 roots
```

The 15 selftest cases cover: exact alias, substring alias, separator
variants (space / `-` / `_`), uppercase, ambiguous match, missing
match, scanner bounded, scanner idempotent, scanner well-formed,
scanner cap, scanner no-mutation.

## Pitfalls (live-build lessons, 2026-07-01)

- **Never synthesize descriptions from the project name.** Every
  description must be grounded in a real source file (README,
  AGENTS.md, package.json `description`).
- **Aliases come from actual user speech patterns**, not what makes
  sense to the agent.
- **Multi-match is real, not a bug.** "argus" intentionally matches
  multiple ARGUS_* projects — disambiguation is the right answer.
- **Don't add internal codenames or component names** as aliases.
- **Paths can go stale.** A project move or archive invalidates the
  registry silently.
- **Typos ≠ separator variants.** `_norm()` collapses `-` `_` ` `
  equivalently but cannot rescue a missing letter.
- **Don't ship empty `references/` / `templates/` dirs.** If you
  create the dir in a first pass and don't populate it, delete it.
- **Hermes runtime truncates skill descriptions to 60 chars.**
  Front-load trigger words; long instructions go in the body.
- **Hermes skill copy has NO `projects.py`** — invoke the canonical
  repo path, not the skill's own dir.
- **Don't ship stale copies.** Re-run `install_skills.py` after every
  edit; the installer is idempotent.