#!/usr/bin/env python3
"""Install Hermes-authored skills to every agent skill root on this machine.

Idempotent. Re-running is safe — existing copies are overwritten
(dirs_exist_ok=True), and each copy is verified by running the skill's
own selftest when one exists.

Roots:
  C:/Users/zerop/Development/projects-registry/        (this repo, projects-registry)
  C:/hermes/skills/devops/external-model-routing/      (Hermes, external-model-routing)
  C:/Users/zerop/.config/opencode/skills/              (opencode)
  C:/Users/zerop/.claude/skills/                       (Claude Code)
  C:/Users/zerop/.codex/skills/                        (Codex)

Usage:
    python install_skills.py                          # install all known skills
    python install_skills.py --skill projects-registry # one skill
    python install_skills.py --dry-run                # show what would happen
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

# (skill name, absolute source dir, selftest script relative to skill dir,
#  install mode: 'full' = copy everything, 'skill_md_only' = copy only SKILL.md
#  (used for roots that don't bundle scripts, e.g. Mavis))
SKILLS = [
    ("projects-registry",      Path(r"C:/Users/zerop/Development/projects-registry"), "projects.py"),
    ("external-model-routing", Path(r"C:/hermes/skills/devops/external-model-routing"), None),
]

# (root path, install mode for THIS root)
TARGETS = [
    (Path(r"C:/Users/zerop/.mavis/skills"),                 "skill_md_only"),
    (Path(r"C:/Users/zerop/.config/opencode/skills"),       "full"),
    (Path(r"C:/Users/zerop/.claude/skills"),                "full"),
    (Path(r"C:/Users/zerop/.codex/skills"),                 "full"),
]


def _run_selftest(skill_dir: Path, script: str, dry: bool) -> tuple[bool, str]:
    """Run `<interpreter> <script> --selftest` in the skill dir. Return (ok, output)."""
    if dry:
        return True, "(dry-run, skipped)"
    py = skill_dir / script
    try:
        r = subprocess.run(
            [sys.executable, str(py), "--selftest"],
            cwd=skill_dir,
            capture_output=True,
            text=True,
            timeout=30,
        )
        ok = r.returncode == 0
        # ponytail: tail only — full output explodes for long selftests
        return ok, (r.stdout + r.stderr).strip()[-400:]
    except subprocess.TimeoutExpired:
        return False, "selftest timed out after 30s"
    except FileNotFoundError as e:
        return False, f"selftest script missing: {e}"
    except OSError as e:
        return False, f"selftest failed to launch: {e}"


def _install_skill(name: str, src: Path, selftest: str | None, dry: bool) -> dict:
    """Copy skill from source to every target. Return per-target status."""
    if not src.is_dir():
        return {"name": name, "src": str(src), "error": f"source missing: {src}", "targets": []}
    if not (src / "SKILL.md").exists():
        return {"name": name, "src": str(src), "error": f"SKILL.md missing in source: {src}", "targets": []}

    target_results = []
    for dst_root, mode in TARGETS:
        dst = dst_root / name
        label = f"{dst_root.parent.name}/{name}"
        if not dst_root.exists():
            target_results.append({"label": label, "skipped": True, "reason": f"root missing: {dst_root}"})
            continue

        # ponytail: skill_md_only roots (e.g. Mavis) ignore everything except SKILL.md.
        # Always exclude .git/ — git pack objects have read-only ACLs and break shutil.copytree.
        patterns = [".git", ".gitignore"]
        if mode == "skill_md_only":
            patterns += ["*.py", "*.json", "*.md.bak"]
        ignore_fn = shutil.ignore_patterns(*patterns)
        try:
            if not dry:
                shutil.copytree(src, dst, dirs_exist_ok=True, ignore=ignore_fn)
                # skill_md_only: prune anything that snuck through besides SKILL.md
                if mode == "skill_md_only":
                    for f in dst.iterdir():
                        if f.name != "SKILL.md":
                            if f.is_dir():
                                shutil.rmtree(f)
                            else:
                                f.unlink()
        except PermissionError as e:
            target_results.append({"label": label, "ok": False, "reason": f"permission denied: {e}"})
            continue
        except OSError as e:
            target_results.append({"label": label, "ok": False, "reason": f"copy failed: {e}"})
            continue

        # verify SKILL.md landed; selftest only for full-mode targets (where scripts exist)
        if not dry:
            sm_ok = (dst / "SKILL.md").exists()
            if not sm_ok:
                target_results.append({"label": label, "ok": False, "reason": "SKILL.md missing after copy"})
                continue

            if selftest and mode == "full":
                ok, out = _run_selftest(dst, selftest, dry)
                target_results.append({
                    "label": label,
                    "ok": ok,
                    "selftest": out,
                })
            else:
                target_results.append({"label": label, "ok": True, "selftest": f"(skipped, mode={mode})" if mode != "full" else "(none)"})
        else:
            target_results.append({"label": label, "ok": True, "selftest": "(dry-run)"})

    return {"name": name, "src": str(src), "error": None, "targets": target_results}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Install Hermes skills to all agent roots.")
    ap.add_argument("--skill", help="install only this skill (default: all)")
    ap.add_argument("--dry-run", action="store_true", help="show what would happen, don't copy")
    args = ap.parse_args(argv)

    selected = SKILLS
    if args.skill:
        selected = [s for s in SKILLS if s[0] == args.skill]
        if not selected:
            sys.exit(f"unknown skill: {args.skill}\n  known: {', '.join(s[0] for s in SKILLS)}")

    print(f"[install_skills] dry-run={args.dry_run} skills={[s[0] for s in selected]}")
    print(f"[install_skills] targets: {len(TARGETS)}")
    overall_ok = True

    for name, src, selftest in selected:
        result = _install_skill(name, src, selftest, args.dry_run)
        if result["error"]:
            print(f"  [FAIL] {name}: {result['error']}")
            overall_ok = False
            continue
        for t in result["targets"]:
            if t.get("skipped"):
                print(f"  [skip] {t['label']}: {t['reason']}")
            elif t.get("ok"):
                st = t['selftest']
                # ponytail: guard against empty output (Flash + Reasoner both flagged this)
                last = st.splitlines()[-1] if st else "(no output)"
                print(f"  [ OK ] {t['label']:50s} selftest={last}")
            else:
                print(f"  [FAIL] {t['label']}: {t.get('reason') or t.get('selftest', '?')}")
                overall_ok = False

    print(f"[install_skills] done — overall {'OK' if overall_ok else 'FAILED'}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))