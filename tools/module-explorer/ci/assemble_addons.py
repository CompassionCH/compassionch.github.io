#!/usr/bin/env python3
"""Reconstruct the Compassion Odoo addons tree for a given Odoo series so the
extractor can run in CI (where the repos aren't checked out).

Strategy:
  * Clone the four first-party CompassionCH repos with FULL history — their git
    log drives the introduced / last-update / contributor stats.
  * Parse each first-party repo's `oca_dependencies.txt` (the OCA convention)
    and SHALLOW-clone every dependency repo it lists — only their manifests are
    needed (dependency nodes carry no git stats), so depth-1 is enough and fast.

The result is an addons root identical in shape to a local dev checkout, which
`extract.py --addons-root <dest>` consumes unchanged.

Usage:
  python3 assemble_addons.py --version 14.0 --dest ./_addons
"""
import argparse
import subprocess
import sys
from pathlib import Path

FIRST_PARTY = [
    "compassion-modules",
    "compassion-switzerland",
    "compassion-website",
    "compassion-accounting",
]
COMPASSION_ORG = "https://github.com/CompassionCH"
OCA_ORG = "https://github.com/OCA"


def run(cmd):
    print("  $", " ".join(cmd), file=sys.stderr)
    return subprocess.run(cmd, capture_output=True, text=True)


def clone(url, branch, dest, shallow):
    if dest.exists():
        return True
    cmd = ["git", "clone", "--quiet", "--branch", branch]
    if shallow:
        cmd += ["--depth", "1"]
    cmd += [url, str(dest)]
    res = run(cmd)
    if res.returncode != 0:
        print(f"  WARN: could not clone {url}@{branch}: {res.stderr.strip()[:200]}",
              file=sys.stderr)
        return False
    return True


def parse_oca_dependencies(path):
    """Yield (repo_name, url, branch_override) from an oca_dependencies.txt."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        name = parts[0]
        url = parts[1] if len(parts) > 1 else f"{OCA_ORG}/{name}"
        branch = parts[2] if len(parts) > 2 else None
        yield name, url, branch


def main():
    parser = argparse.ArgumentParser(description="Assemble Compassion addons tree.")
    parser.add_argument("--version", required=True, help="Odoo series branch, e.g. 14.0 or 18.0")
    parser.add_argument("--dest", type=Path, required=True, help="Destination addons root")
    args = parser.parse_args()

    dest = args.dest
    dest.mkdir(parents=True, exist_ok=True)
    ver = args.version

    # 1) first-party, full history
    print(f"Cloning first-party repos @ {ver} (full history)…", file=sys.stderr)
    for repo in FIRST_PARTY:
        clone(f"{COMPASSION_ORG}/{repo}", ver, dest / repo, shallow=False)

    # 2) dependency repos from each first-party oca_dependencies.txt (shallow)
    print("Resolving OCA dependency repos (shallow)…", file=sys.stderr)
    seen = set(FIRST_PARTY)
    for repo in FIRST_PARTY:
        for name, url, branch in parse_oca_dependencies(dest / repo / "oca_dependencies.txt"):
            if name in seen:
                continue
            seen.add(name)
            clone(url, branch or ver, dest / name, shallow=True)

    cloned = sorted(p.name for p in dest.iterdir() if (p / ".git").exists() or p.is_dir())
    print(f"\nAssembled {len(cloned)} repos under {dest}", file=sys.stderr)


if __name__ == "__main__":
    main()
