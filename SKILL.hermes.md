---
name: projects-registry
description: "SunoSavvy, JobbyJob, VerbalChainsaw, ARGUS, dev-pulse paths..."
---

# projects-registry

## Critical — where the script lives

This skill is installed at `C:/hermes/skills/projects-registry/` as
**SKILL.md only**. The actual `projects.py` script is **NOT bundled
here**. To invoke it, you MUST run the canonical-repo script:

```
python C:/Users/zerop/Development/projects-registry/projects.py <mention>
```

DO NOT run `python projects.py` from this skill's directory — that file
does not exist there. The script auto-resolves to its bundled
`projects.json` via `Path(__file__).parent` so the path above works
without any environment variable.

Single source of truth for project paths, aliases, and lead information.

The canonical source-of-truth lives in the repo at
`C:/Users/zerop/Development/projects-registry/`. This Hermes copy is
**SKILL.md only** — Hermes runtime does not bundle the script. Invoke
the canonical-path script to look up a project.

## When this fires

- Director says "the path to SunoSavvy", "JobbyJob stuff", "what's
  that project called", "where do I keep X", "the opencode fork",
  "argus family", "verbal chainsaw", "what's the test command for
  center-audit", etc.
- ANY mention of a registered project name — even casually — load the
  registry first, do NOT default to `find` / `ls` / `search_files`.
- When you need the build / test / typecheck command for a project.

## Procedure

```bash
python C:/Users/zerop/Development/projects-registry/projects.py <mention>
python C:/Users/zerop/Development/projects-registry/projects.py --path <mention>
python C:/Users/zerop/Development/projects-registry/projects.py --list
python C:/Users/zerop/Development/projects-registry/projects.py --selftest
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