# compassionch.github.io

Org-level GitHub Pages site for Compassion CH developer tools.

Live: **https://compassionch.github.io/** → **https://compassionch.github.io/module-explorer/**

## What's here

| Path | What |
|---|---|
| `index.html` | Tiny org-tools landing page (links to the explorer). |
| `module-explorer/index.html` | The **built, self-contained** Module Explorer (served by Pages). Generated — do not hand-edit. |
| `tools/module-explorer/` | The **source** of the explorer (extractor, builder, template, summaries). |
| `tools/module-explorer/ci/assemble_addons.py` | Reconstructs the addons tree in CI from each repo's `oca_dependencies.txt`. |
| `.github/workflows/build-module-explorer.yml` | Manual "refresh" workflow (rebuilds + republishes). |

## Module Explorer

Interactive map of the Odoo modules used by Compassion CH: a force-directed
dependency **Graph**, a layered ERD **Diagram** (centered module, dependencies
above / dependents below), a searchable module list, per-module detail
(summary, git dates, contributors, models/functions), and landscape stats.
See `tools/module-explorer/README.md` for the full feature list.

## One-time setup (needs repo admin)

1. **Create the repo** `compassionch.github.io` under the CompassionCH org (if it
   doesn't exist) and push this directory to it.
   - If the org *already* has a Pages site here, drop the root `index.html` and
     keep only the `module-explorer/`, `tools/`, and `.github/` paths.
2. **Enable Pages**: repo **Settings → Pages → Build and deployment**
   → Source = **Deploy from a branch**, Branch = `main`, Folder = **`/ (root)`**.
3. Wait ~1 min → the site is live at the URLs above.

## Refreshing the data (manual)

The map is a snapshot; the date is shown at the bottom of the explorer's stats
panel. To regenerate:

- **From the web**: click **"↻ refresh data"** in the explorer (bottom-left), or
  go to **Actions → Build Module Explorer → Run workflow**, pick the Odoo series
  (`14.0` default), and run it. It reassembles the addons, regenerates the data,
  rebuilds the page, and commits the result — Pages redeploys automatically.
- **Locally** (if you have the addons checked out):
  ```bash
  cd tools/module-explorer
  python3 extract.py --addons-root /path/to/addons-compassion-switzerland \
    --out modules.json
  python3 build_artifact.py --out ../../module-explorer/index.html
  git commit -am "Refresh module explorer" && git push
  ```

## Odoo 18

The same workflow handles v18: run it with `odoo_version = 18.0`. It clones the
`18.0` branches, and the built page is published to
**`/module-explorer/18.0/`** (the `14.0` map stays at `/module-explorer/`).
`extract.py` auto-detects the series from the manifests, so no code change is
needed. (A future enhancement could add an in-page v14/v18 toggle.)

## Editing summaries

Per-module "what it does" blurbs live in `tools/module-explorer/summaries.json`
(keyed by module name) and are merged into the data on every build, so they
survive regeneration. Edit there and re-run the workflow.
