# projects-registry

A standalone Python project that gives any AI agent deterministic, sub‑millisecond
lookup of project paths, aliases, and lead information from a single JSON registry.

No network, no DB, no daemon. One JSON file + one Python script.

## What's in here

| File | Purpose |
|---|---|
| `projects.json` | The registry — one record per project (name, aliases, path, stack, test/build commands, memory anchors). |
| `projects.py` | Lookup script. One call, deterministic, sub‑ms. |
| `SKILL.md` | Skill description for agent frameworks (Hermes, Claude, Codex, opencode). |
| `deepseek_review.py` | Opt‑in reviewer that posts code to DeepSeek for outside opinion. |
| `install_skills.py` | Fan‑out installer — copies this skill to multiple agent roots. |

## Usage

```bash
# Lookup a project by name or alias
python projects.py sunosavvy
python projects.py --path argus                # just the path (exit 0/1/2)
python projects.py --exists verbalchainsaw     # exit 0 if known
python projects.py --list                      # all projects

# Verify the lookup works
python projects.py --selftest                  # 10/10 must pass

# Distribute to every agent root
python install_skills.py                       # copies to opencode/.claude/.codex
python install_skills.py --dry-run

# Get an outside code review from DeepSeek
python deepseek_review.py projects.py
python deepseek_review.py --model deepseek-v4-pro SKILL.md
python deepseek_review.py --selftest           # offline verification
```

## Editing the registry

Edit `projects.json` directly. Required per project: `name`, `aliases`,
`path`, `description`. Optional: `repo_path`, `alt_paths`, `stack`,
`test_cmd`, `build_cmd`, `typecheck_cmd`, `memory_anchors`.

Add aliases Director actually uses. Run `--selftest` after every edit.

## Verification is non‑optional

`python projects.py --selftest` is the lift oracle. Green selftest is
the only deterministic signal the registry produces correct lookups.
File existence is not a signal.

## License

MIT — do whatever, no warranty.