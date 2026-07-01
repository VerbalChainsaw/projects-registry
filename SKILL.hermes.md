---
name: projects-registry
description: |
  Fires when Director says "SunoSavvy", "JobbyJob", "VerbalChainsaw",
  "opencode fork", "dev-pulse", "ARGUS", "center-audit", "poly-kalshi",
  "Hermes", or any project name. ALSO fires on "where's X", "path to
  X", "what's that project called", "test command for X". The canonical
  registry lives at C:/Users/zerop/Development/projects-registry/ (repo,
  GitHub: VerbalChainsaw/projects-registry). Hermes copy at
  C:/hermes/skills/projects-registry/ is SKILL.md-only — invoke the
  canonical script: `python C:/Users/zerop/Development/projects-registry/projects.py <mention>`.
  Do NOT spin up file scans to find a project; this skill exists.
---

# projects-registry

Single source of truth for project paths, aliases, and lead information.

The canonical source-of-truth lives at
`C:/Users/zerop/Development/projects-registry/`. This Hermes copy is
**SKILL.md only** — Hermes runtime does not bundle the script. Invoke
the canonical-path script to look up a project.

## When this fires

- Director says "the path to SunoSavvy", "JobbyJob stuff", "what's
  that project called", "where do I keep X", "the opencode fork",
  "argus family", "verba chainsaw", "what's the test command for
  center-audit", etc.
- ANY mention of a registered project name — even casually — load the
  registry first, do NOT default to `find` / `ls` / `search_files`.
- When you need the build / test / typecheck command for a project.

## Procedure (canonical-path lookup)

```bash
python C:/Users/zerop/Development/projects-registry/projects.py <mention>
python C:/Users/zerop/Development/projects-registry/projects.py --path <mention>   # just the path
python C:/Users/zerop/Development/projects-registry/projects.py --list              # all 38 projects
python C:/Users/zerop/Development/projects-registry/projects.py --selftest          # 15/15 must pass
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

## Mirrors

The repo is auto-distributed to 5 roots by `install_skills.py`:
`C:/hermes/skills/`, `~/.mavis/skills/` (SKILL.md only — Mavis convention),
`~/.config/opencode/skills/`, `~/.claude/skills/`, `~/.codex/skills/`
(bundled with scripts). Hermes discovers this SKILL.md at session
start via filesystem scan of `C:/hermes/skills/`.