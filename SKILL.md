---
name: projects-registry
description: Fires when Director says "SunoSavvy", "JobbyJob", "VerbalChainsaw", "opencode fork", "dev-pulse", "ARGUS", "center-audit", "poly-kalshi", "Hermes", or any project name. ALSO fires on "where's X", "path to X", "what's that project called", "test command for X". Resolves project paths via C:/hermes/projects.json — call `python C:/hermes/skills/projects-registry/projects.py <mention>` for a one-shot deterministic lookup. Do NOT spin up file scans to find a project; this skill exists.
---

# projects-registry

Single source of truth for project paths, aliases, and lead
information. Lives at **`C:/hermes/projects.json`**.

This skill covers the **class** of work: maintaining the registry
(declared, not discovered) and resolving project-name mentions to
their canonical record. If the user asks about any project, look
here first.

## When this fires

- Director says "the path to SunoSavvy", "JobbyJob stuff", "what's
  that project called", "where do I keep X", "the opencode fork",
  "argus family", "verba chainsaw", "what's the test command for
  center-audit", etc.
- ANY mention of a registered project name — even casually — load
  the registry first, do NOT default to `search_files` / `ls`.
- When you need the build / test / typecheck command for a project.
- When adding a new project to the registry (use the grounding
  recipe — don't synthesize from the project name).

## Procedure (script is the source of truth)

Run the lookup. One call, deterministic, <1ms:

```bash
python C:/hermes/skills/projects-registry/projects.py <mention>
python C:/hermes/skills/projects-registry/projects.py --path <mention>   # just the path
python C:/hermes/skills/projects-registry/projects.py --list              # all projects
python C:/hermes/skills/projects-registry/projects.py --selftest          # 10-case verification
```

Match is case-insensitive, separator-insensitive (space / `-` / `_`
collapse). Ambiguous mentions return all candidates with exit code 2;
non-matches return exit code 1. Read `projects.py` for the exact
algorithm if you need to extend it.

## Adding a project

Edit `C:/hermes/projects.json` directly. Required per project: `name`,
`aliases`, `path`, `description`. Optional: `repo_path`, `alt_paths`,
`stack`, `test_cmd`, `build_cmd`, `typecheck_cmd`, `memory_anchors`.

Aliases: include every variant Director actually uses. Pull from
`session_search` transcripts if unsure. Run `--selftest` after adding
to catch separator-variant typos.

## Boot-time injection

The registry is consulted **on demand** when a project name appears,
NOT injected into every prompt — listing all projects up-front
wastes tokens on sessions that never mention one. Skill trigger
does the lookup when needed. SOUL.md carries the boot-force
directive ("load the registry, don't `find` for it").

## Verification — selftest is non-optional

`projects.py --selftest` is the lift oracle. Ship it the first time,
run it after every edit, and run it once before declaring "this
works." A green selftest is the **only** deterministic signal that
the registry produces correct lookups; the existence of the file is
not a signal. The 10 cases cover: exact alias, substring alias,
separator variants (space / `-` / `_`), uppercase, ambiguous match,
missing match.

Bootstrap verification requires a fresh Hermes session — the skill
scanner (`agent/skill_commands.py:348`) reads `C:/hermes/skills/`
at session start. The agent cannot force a rescan mid-session. Tell
the user: "restart Hermes (`hermes` again) and run `/skills` —
`projects-registry` should appear." Don't claim the skill fires
until that's done.

After editing the registry:

```bash
python C:/hermes/skills/projects-registry/projects.py --selftest  # MUST be 10/10
python C:/hermes/skills/projects-registry/projects.py --list      # sanity check counts
```

## Pitfalls (live-build lessons, 2026-07-01)

- **Never synthesize descriptions from the project name.** Every
  description must be grounded in a real source file (README,
  AGENTS.md, package.json `description`).
- **Aliases come from actual user speech patterns**, not what makes
  sense to the agent. Use `session_search` for the project name.
- **Multi-match is real, not a bug.** "argus" intentionally matches
  both Hermes and ARGUS_OSINT — disambiguation is the right answer.
- **Don't add internal codenames or component names** as aliases.
- **Paths can go stale.** A project move or archive invalidates the
  registry silently. `test -d <path>` before acting on a command.
- **Typos ≠ separator variants.** `_norm()` collapses `-` `_` ` `
  equivalently but cannot rescue a missing letter. Don't add aliases
  for typos; accept fuzzy-match as YAGNI until the user hits a real
  typo in production.