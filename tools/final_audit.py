"""Final offline audit (TASKS.md T18).

1. Fresh-clone simulation: export the tracked tree to a temp dir WITHOUT
   `.env`, `.privacy-patterns`, or `out/`, then run the test suite there
   (A7, A9).
2. Privacy scan: every tracked file is matched against the privacy
   patterns (`.privacy-patterns` if present locally, else
   `.privacy-patterns.example`; one case-insensitive regex per line,
   `#` comments stripped), then the same patterns are scanned across
   the full git history (`git grep` over `git rev-list --all`). Any
   hit — working tree or history — exits non-zero (A10).
3. Prints a one-page MUST checklist summary (D1-D6, A1-A11, B1), reading
   status markers from IMPLEMENTATIONPLAN.md tracker rows where
   parseable, else listed as manual-check.

Usage: py tools/final_audit.py   (exit 0 = all clear)
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

EXCLUDED = {".env", ".privacy-patterns"}
EXCLUDED_DIRS = {"out"}

D_ITEMS = {
    "D1": "Post published on DEV before deadline, submission template + tags",
    "D2": "Required template sections present",
    "D3": "Optional sections (Agent Session, First User, Prize Categories)",
    "D4": "Every screenshot renders on the live page",
    "D5": "Demo link opens a working demo",
    "D6": "Repo public, first commit inside Oct 12-18 window",
}
A_ITEMS = {
    "A1": "Tone guide + review paste entry",
    "A2": "Every review triaged",
    "A3": "Needs-a-human: no draft, reason only",
    "A4": "Draft in owner's voice",
    "A5": "No invented facts (verifier + template fallback)",
    "A6": "Model via configurable endpoint; key in gitignored config only",
    "A7": "Fresh clone runs demo offline from fixtures",
    "A8": "Pages demo renders fixture output at replydeskhq.tech",
    "A9": "Suite passes offline, network mocked",
    "A10": "No real data/locations/secrets anywhere",
    "A11": "Every commit made by the agent",
}
B_ITEMS = {"B1": "Real local business owner used it on their own reviews"}


def tracked_files(repo: Path = REPO) -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"],
        capture_output=True, check=True,
    ).stdout
    return [Path(p.decode()) for p in out.split(b"\0") if p]


def export_tree(files: list[Path], dest: Path, repo: Path = REPO) -> None:
    for f in files:
        if f.name in EXCLUDED or any(part in EXCLUDED_DIRS for part in f.parts):
            continue
        target = dest / f
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((repo / f).read_bytes())


def load_patterns(path: Path) -> list[str]:
    """One case-insensitive ERE per line; blank and # lines stripped."""
    if not path.exists():
        return []
    patterns = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def scan_text(patterns: list[str], text: str) -> list[str]:
    """Return the pattern strings that hit anywhere in text."""
    return [p for p in patterns
            if re.search(p, text, re.IGNORECASE | re.MULTILINE)]


def scan_files(patterns: list[str], files: list[Path], repo: Path = REPO
               ) -> dict[Path, list[str]]:
    hits: dict[Path, list[str]] = {}
    for f in files:
        if f.name in EXCLUDED:
            continue
        try:
            text = (repo / f).read_text(encoding="utf-8")
        except (UnicodeDecodeError, ValueError):
            continue  # binary (PNG etc.)
        found = scan_text(patterns, text)
        if found:
            hits[f] = found
    return hits


def scan_history(patterns: list[str], repo: Path = REPO) -> dict[str, list[str]]:
    """Scan every commit's tree AND commit message for pattern hits
    (A10 history leg).

    Returns {short-rev: [pattern, ...]}. Line contents are never
    reported — only which pattern hit in which commit.
    """
    if not patterns:
        return {}
    revs = subprocess.run(
        ["git", "-C", str(repo), "rev-list", "--all"],
        capture_output=True, check=True,
    ).stdout
    hits: dict[str, list[str]] = {}
    for rev in revs.split():
        short = rev.decode()[:12]
        for pat in patterns:
            proc = subprocess.run(
                ["git", "-C", str(repo), "grep", "-I", "-E", "-i",
                 "-e", pat, rev],
                capture_output=True,
            )
            if proc.returncode == 0:
                hits.setdefault(short, []).append(pat)
                continue
        msg = subprocess.run(
            ["git", "-C", str(repo), "log", "-1", "--format=%B", rev],
            capture_output=True, check=True,
        ).stdout.decode("utf-8", "replace")
        msg_hits = [p for p in patterns
                    if re.search(p, msg, re.IGNORECASE | re.MULTILINE)]
        if msg_hits:
            hits.setdefault(short, []).extend(msg_hits)
    return hits


def tracker_statuses(plan_text: str) -> dict[str, str]:
    """Parse tracker rows: task id in first cell, status mark in a cell."""
    statuses = {}
    for line in plan_text.splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) >= 3 and re.fullmatch(r"T\d+[a-z0-9]*", cells[1] or ""):
            m = re.search(r"(✅|❌|⏳|BLOCKED|pending)", line)
            if m:
                statuses[cells[1]] = m.group(1)
    return statuses


def checklist_summary(plan_path: Path) -> str:
    plan = plan_path.read_text(encoding="utf-8") if plan_path.exists() else ""
    statuses = tracker_statuses(plan)
    lines = ["", "MUST checklist (implementer-tracked; verify before publish)",
             "-" * 60]

    def mark(done: bool) -> str:
        return "tracked-done" if done else "MANUAL-CHECK"

    done_tasks = [t for t, s in statuses.items() if s == "✅"]
    lines.append("Submission:")
    lines += [f"  {k}: {v}  [{mark(k == 'D1' and 'T16' in ' '.join(done_tasks))}]"
              for k, v in D_ITEMS.items()]
    lines.append("App:")
    a_map = {"A7": "T12", "A9": "T12", "A10": "T18", "A11": "process"}
    lines += [f"  {k}: {v}  [{mark(a_map.get(k) in done_tasks)}]"
              for k, v in A_ITEMS.items()]
    lines.append("Bonus:")
    lines += [f"  {k}: {v}  [MANUAL-CHECK]" for k, v in B_ITEMS.items()]
    return "\n".join(lines)


def run_suite(dest: Path) -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests"],
        cwd=dest, capture_output=True, text=True,
    )
    tail = "\n".join(proc.stderr.strip().splitlines()[-3:])
    print(f"[fresh-clone suite] exit={proc.returncode}\n{tail}")
    return proc.returncode


def main() -> int:
    files = tracked_files()
    fail = False

    # 1. fresh-clone simulation
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / "clone"
        export_tree(files, dest)
        if run_suite(dest) != 0:
            fail = True
            print("FAIL: suite did not pass in fresh-clone export")

    # 2. privacy scan
    local = REPO / ".privacy-patterns"
    pattern_file = local if local.exists() else REPO / ".privacy-patterns.example"
    patterns = load_patterns(pattern_file)
    print(f"[privacy scan] {len(patterns)} patterns from {pattern_file.name}")
    hits = scan_files(patterns, files)
    if hits:
        fail = True
        print("FAIL: privacy pattern hits:")
        for f, found in hits.items():
            for p in found:
                print(f"  {f}: /{p}/")
    else:
        print("[privacy scan] clean")

    # 2b. git-history scan (same patterns across all commits)
    hhits = scan_history(patterns)
    if hhits:
        fail = True
        print("FAIL: privacy pattern hits in git history:")
        for rev, found in sorted(hhits.items()):
            for p in found:
                print(f"  {rev}: /{p}/")
    else:
        print("[history scan] clean")

    # 3. checklist summary
    print(checklist_summary(REPO / "IMPLEMENTATIONPLAN.md"))

    print("\nAUDIT:", "FAIL" if fail else "PASS")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
