#!/usr/bin/env python3
"""Compassion Module Explorer — data extractor.

Walks every Odoo addons repo under the addons root, parses module manifests,
git history and Python models, and emits a single ``modules.json`` consumed by
the interactive webapp.

Scope of the emitted graph: all first-party Compassion modules plus the OCA /
community modules they *directly* depend on. The global module index is built
across every repo so dependency edges resolve even into out-of-scope addons.

Pure standard library — no install step. Re-run anytime to refresh the data.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

# Repos (immediate children of the addons root) that the team owns/writes.
FIRST_PARTY_REPOS = {
    "compassion-modules",
    "compassion-switzerland",
    "compassion-website",
    "compassion-accounting",
}

# Merge git identities that are the same person under different %an names.
AUTHOR_ALIASES = {
    "ecino": "Emanuel Cino",
}

# Default addons root = three levels up from this script
# (.../addons-compassion-switzerland/compassion-switzerland/tools/module-explorer).
DEFAULT_ADDONS_ROOT = Path(__file__).resolve().parents[3]


# --------------------------------------------------------------------------- #
# Discovery + manifest parsing
# --------------------------------------------------------------------------- #
def find_modules(addons_root: Path):
    """Yield (repo_name, module_name, module_path, manifest_path) for every module."""
    for repo in sorted(p for p in addons_root.iterdir() if p.is_dir()):
        for manifest in repo.rglob("__manifest__.py"):
            # Skip vendored copies inside test fixtures / nested setup dirs.
            if "/setup/" in str(manifest).replace(os.sep, "/"):
                continue
            module_path = manifest.parent
            yield repo.name, module_path.name, module_path, manifest


def parse_manifest(manifest_path: Path) -> dict | None:
    """Parse a manifest dict literal, ignoring the comment header."""
    try:
        source = manifest_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        tree = ast.parse(source, filename=str(manifest_path))
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            try:
                return ast.literal_eval(node)
            except (ValueError, SyntaxError):
                return None
    return None


# --------------------------------------------------------------------------- #
# Python model + method extraction
# --------------------------------------------------------------------------- #
def _str_value(node):
    """Return a string literal if the AST node is one, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def extract_models(module_path: Path) -> list[dict]:
    """Extract Odoo models (_name/_inherit) and their public methods via AST."""
    models = []
    for py_file in sorted(module_path.rglob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
            name = inherit = None
            for stmt in cls.body:
                if isinstance(stmt, ast.Assign):
                    target = stmt.targets[0]
                    if isinstance(target, ast.Name):
                        if target.id == "_name":
                            name = _str_value(stmt.value)
                        elif target.id == "_inherit":
                            inherit = _str_value(stmt.value)
            model_name = name or inherit
            if not model_name:
                continue  # not an Odoo model class
            methods = []
            for stmt in cls.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if stmt.name.startswith("__"):
                        continue
                    doc = ast.get_docstring(stmt)
                    methods.append({
                        "name": stmt.name,
                        "doc": (doc or "").strip().split("\n")[0][:160] or None,
                        "private": stmt.name.startswith("_"),
                    })
            models.append({
                "model": model_name,
                "new": name is not None,  # defines a new model vs inherits/extends
                "class": cls.name,
                "file": str(py_file.relative_to(module_path)),
                "methods": methods,
            })
    return models


# --------------------------------------------------------------------------- #
# Git history
# --------------------------------------------------------------------------- #
def _git(repo_root: Path, *args) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True, text=True, timeout=60,
        )
        return out.stdout if out.returncode == 0 else ""
    except (subprocess.SubprocessError, OSError):
        return ""


def git_stats(repo_root: Path, module_path: Path) -> dict:
    """Introduced date, last update, commit count and top contributors."""
    rel = module_path.relative_to(repo_root).as_posix()
    dates = _git(repo_root, "log", "--format=%ad", "--date=short", "--", rel)
    date_lines = [d for d in dates.splitlines() if d.strip()]
    authors = _git(repo_root, "log", "--format=%an", "--", rel).splitlines()
    author_counts = Counter(AUTHOR_ALIASES.get(a, a) for a in authors if a.strip())
    return {
        "introduced": date_lines[-1] if date_lines else None,
        "last_update": date_lines[0] if date_lines else None,
        "commit_count": len(date_lines),
        "top_contributors": [
            {"name": n, "commits": c} for n, c in author_counts.most_common(5)
        ],
        "_all_authors": dict(author_counts),   # used for global aggregation, dropped per-module
    }


def count_lines(module_path: Path) -> dict:
    """Rough size signal: python LOC and file count."""
    py_files = [p for p in module_path.rglob("*.py") if "__pycache__" not in p.parts]
    loc = 0
    for p in py_files:
        try:
            loc += sum(1 for _ in p.open("r", encoding="utf-8", errors="ignore"))
        except OSError:
            pass
    return {"py_files": len(py_files), "py_loc": loc}


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def load_summaries() -> dict:
    """Curated 'what it does / used for' summaries (generated once, hand-kept).

    Kept in a side file so they survive re-running the extractor.
    """
    path = Path(__file__).resolve().parent / "summaries.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            print(f"  WARN: could not read {path}", file=sys.stderr)
    return {}


def build(addons_root: Path) -> dict:
    summaries = load_summaries()
    # Pass 1 — cheap discovery of every module across every repo (for the
    # global name index, so edges resolve even into out-of-scope addons).
    discovered = list(find_modules(addons_root))
    name_index = {}          # technical name -> repo
    duplicate_names = set()
    for repo, mod, _path, _manifest in discovered:
        if mod in name_index and name_index[mod] != repo:
            duplicate_names.add(mod)
        name_index.setdefault(mod, repo)

    print(f"Discovered {len(discovered)} modules across "
          f"{len({r for r, *_ in discovered})} repos.", file=sys.stderr)
    if duplicate_names:
        print(f"  note: {len(duplicate_names)} module names exist in >1 repo "
              f"(first wins): {sorted(duplicate_names)[:5]}...", file=sys.stderr)

    # Resolve scope: first-party modules + their direct dependencies.
    manifests = {}  # module name -> (repo, path, manifest)
    for repo, mod, path, manifest_path in discovered:
        m = parse_manifest(manifest_path)
        if m is None:
            print(f"  WARN: unparseable manifest: {manifest_path}", file=sys.stderr)
            continue
        manifests.setdefault(mod, (repo, path, m))

    first_party = {
        mod for mod, (repo, _p, _m) in manifests.items()
        if repo in FIRST_PARTY_REPOS
    }
    direct_deps = set()
    for mod in first_party:
        _repo, _path, m = manifests[mod]
        for dep in m.get("depends", []) or []:
            direct_deps.add(dep)
    in_scope = first_party | (direct_deps & set(manifests))

    print(f"Scope: {len(first_party)} first-party + "
          f"{len(in_scope) - len(first_party)} direct-dep modules "
          f"= {len(in_scope)} nodes.", file=sys.stderr)

    # Pass 2 — full extraction only for in-scope modules (git + AST are costly).
    modules = []
    edges = []
    global_authors = Counter()
    total_commits = 0
    for i, mod in enumerate(sorted(in_scope), 1):
        repo, path, manifest = manifests[mod]
        repo_root = addons_root / repo
        is_fp = repo in FIRST_PARTY_REPOS
        print(f"  [{i}/{len(in_scope)}] {mod} ({repo})", file=sys.stderr)

        record = {
            "name": mod,
            "repo": repo,
            "is_first_party": is_fp,
            "display_name": manifest.get("name", mod),
            "summary": manifest.get("summary"),
            "ai_summary": summaries.get(mod),
            "description": (manifest.get("description") or "").strip()[:2000] or None,
            "version": manifest.get("version"),
            "category": manifest.get("category"),
            "author": manifest.get("author"),
            "maintainers": manifest.get("maintainers"),
            "license": manifest.get("license"),
            "development_status": manifest.get("development_status"),
            "installable": manifest.get("installable", True),
            "auto_install": manifest.get("auto_install", False),
            "application": manifest.get("application", False),
            "external_dependencies": manifest.get("external_dependencies"),
            "depends": list(manifest.get("depends", []) or []),
        }
        # Models + methods only for first-party (the detail users care about);
        # OCA deps stay lightweight context nodes.
        if is_fp:
            record["models"] = extract_models(path)
            gs = git_stats(repo_root, path)
            for author, c in gs.pop("_all_authors", {}).items():
                global_authors[author] += c
            record.update(gs)
            record.update(count_lines(path))
            total_commits += record.get("commit_count", 0) or 0
        else:
            record["models"] = []
        modules.append(record)

        for dep in record["depends"]:
            edges.append({"source": mod, "target": dep,
                          "resolved": dep in in_scope})

    # Reverse dependencies (who depends on me) — within scope.
    dependents = {m["name"]: [] for m in modules}
    for e in edges:
        if e["target"] in dependents:
            dependents[e["target"]].append(e["source"])
    for m in modules:
        m["dependents"] = sorted(dependents.get(m["name"], []))

    # ---- headline stats (for the webapp's stats panel) ----
    fp_mods = [m for m in modules if m["is_first_party"]]
    dated = [m for m in fp_mods if m.get("introduced")]
    updated = [m for m in fp_mods if m.get("last_update")]
    oldest = min(dated, key=lambda m: m["introduced"]) if dated else None
    newest = max(updated, key=lambda m: m["last_update"]) if updated else None
    busiest = max(fp_mods, key=lambda m: m.get("commit_count") or 0) if fp_mods else None
    most_dep = max(modules, key=lambda m: len(m["dependents"])) if modules else None
    repo_counts = Counter(m["repo"] for m in modules)
    # Odoo series auto-detected from first-party manifest versions (e.g. "14.0",
    # "18.0"), so the same extractor works across versions with no code change.
    series_counts = Counter(
        ".".join((m.get("version") or "").split(".")[:2])
        for m in fp_mods if m.get("version")
    )
    odoo_version = series_counts.most_common(1)[0][0] if series_counts else "unknown"

    stats = {
        "total_discovered": len(discovered),
        "first_party": len(first_party),
        "in_scope": len(in_scope),
        "dependencies": len(in_scope) - len(first_party),
        "edges": len(edges),
        "total_commits": total_commits,
        "modules_per_repo": dict(repo_counts),
        "top_contributors": [
            {"name": n, "commits": c} for n, c in global_authors.most_common(8)
        ],
        "oldest": {"name": oldest["name"], "date": oldest["introduced"]} if oldest else None,
        "newest_update": {"name": newest["name"], "date": newest["last_update"]} if newest else None,
        "busiest": {"name": busiest["name"], "commits": busiest.get("commit_count")} if busiest else None,
        "most_depended": {"name": most_dep["name"], "count": len(most_dep["dependents"])} if most_dep else None,
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "addons_root": str(addons_root),
        "odoo_version": odoo_version,
        "first_party_repos": sorted(FIRST_PARTY_REPOS),
        "stats": stats,
        "modules": modules,
        "edges": edges,
    }


def main():
    parser = argparse.ArgumentParser(description="Extract Odoo module graph data.")
    parser.add_argument("--addons-root", type=Path, default=DEFAULT_ADDONS_ROOT,
                        help="Path to the addons root (default: autodetected).")
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parent / "modules.json")
    args = parser.parse_args()

    if not args.addons_root.is_dir():
        sys.exit(f"addons root not found: {args.addons_root}")

    data = build(args.addons_root)
    args.out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {args.out} "
          f"({args.out.stat().st_size // 1024} KB, "
          f"{len(data['modules'])} modules, {len(data['edges'])} edges).",
          file=sys.stderr)


if __name__ == "__main__":
    main()
