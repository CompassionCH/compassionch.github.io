# Compassion Module Explorer

Interactive force-directed graph of the Odoo 14 module landscape. Lets a developer pick any module and see its dependencies, dependents, metadata, models and functions. Built to help the team navigate the complex module landscape, especially during the v14 → v18 migration.

## What it shows

- **Scope**: ~88 first-party Compassion modules across repos (compassion-modules, compassion-switzerland, compassion-website, compassion-accounting) PLUS the OCA/community modules they directly depend on. ~144 nodes, ~418 dependency edges.
- **Node color** = owning repo. First-party modules are solid dots; OCA dependencies are hollow/muted rings.
- **Per first-party module**: manifest metadata (version, category, license, status), git history (introduced date, last update, commit count, top contributors), Python LOC, and complete model list (_name/_inherit) with public/private methods and docstrings.

## Files

- `extract.py` — stdlib-only extractor. Walks every addons repo, parses manifests + git history + Python models via AST, writes `modules.json` and global stats. Re-run anytime to refresh. Computes per-module summaries (ai_summary), global counts, dependency edges, and top contributors with git-identity aliases merged.
- `summaries.json` — curated one-to-two sentence "what it does / used for" summaries per first-party module (hand-editable). `extract.py` merges these into modules.json as the `ai_summary` field on each module, so they survive re-running the extractor. To change a summary, edit summaries.json and re-run extract.py + build_artifact.py.
- `modules.json` — generated data (single source the webapp reads).
- `index.html` — the web app. Loads `modules.json` via fetch when self-hosted.
- `build_artifact.py` — inlines `modules.json` into `index.html` to produce `explorer.html`, a single self-contained file.
- `explorer.html` — generated standalone build.

## Usage

**1. Regenerate the data** (optional)

```bash
python3 extract.py
```

Optional flags: `--addons-root PATH` (point at a different addons checkout), `--out PATH`. The script autodetects the addons root as three directories up.

**2. Build the standalone file**

```bash
python3 build_artifact.py
```

Writes `explorer.html`.

**3. View it**

```bash
# Option A: open directly in a browser
open explorer.html

# Option B: self-host with live module.json
python3 -m http.server
# then open http://localhost:8000/index.html
```

## Using the app

### Graph and Diagram views

- **Drag** to pan, **scroll** to zoom
- **Click a module dot** to inspect it in the side panel; **click the module's text label** to open the detail panel
- The detail panel's **"What it does"** shows the generated summary
- **Click dependency chips** to jump between modules
- **Click a model row** to expand its functions
- **Graph | Diagram toggle** (top of header): switch between the force-directed graph and a layered ERD-style diagram view
- **In Diagram view**: the selected module is centered as a box. Modules it depends on appear in tiers above it; modules that depend on it appear in tiers below it. All are connected by curved edges. Use **depth −/+** controls to add/remove transitive tiers. Click any box to re-center the diagram on it. Drag to pan, scroll to zoom.
- **Search box** (top-left) to find a module
- **Legend chips** (top-right) to filter repos in/out
- **Double-click empty space** to release focus

### Left sidebar

- An alphabetical, **filterable list of all modules** on the left (each with a repo-colored dot)
- **Click a module** to open it
- **Collapse toggle** on the sidebar edge; auto-collapses to an overlay on mobile

### Stats

- The **bottom of the sidebar** shows landscape statistics: module counts, dependency edges, total commits, oldest/latest dates, and the most-used module
- A **Top Contributors bar chart** displays the most active contributors (with merged git-identity aliases)

## Keeping it fresh

The data is a snapshot. Re-run `extract.py` then `build_artifact.py` after pulling new code. This can be wired into CI to regenerate on merge.

## Odoo 18 migration

The same `extract.py` works for Odoo 18. Point `--addons-root` at the v18 addons checkout and update the `FIRST_PARTY_REPOS` set in extract.py if repo names change.
