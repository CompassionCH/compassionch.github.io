#!/usr/bin/env python3
"""Inline modules.json into index.html to produce a standalone, self-contained
HTML file suitable for publishing as a Claude Artifact, hosting on GitHub
Pages, or opening directly from disk with no web server.

Default output is ./explorer.html. Pass --out to write elsewhere (the CI
workflow points it at ../../module-explorer/index.html, the Pages-served path).
"""
import argparse
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="Inline data into the explorer HTML.")
    parser.add_argument("--data", type=Path, default=HERE / "modules.json")
    parser.add_argument("--template", type=Path, default=HERE / "index.html")
    parser.add_argument("--out", type=Path, default=HERE / "explorer.html")
    parser.add_argument("--versions", type=Path, default=None,
                        help="Optional versions.json; injects the v14/v18 switcher config. "
                             "Omit for standalone/artifact builds (no switcher).")
    args = parser.parse_args()

    template = args.template.read_text(encoding="utf-8")
    data = json.loads(args.data.read_text(encoding="utf-8"))
    # Compact JSON; escape </script> so it can't break out of the tag.
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    out = template.replace("__DATA_PLACEHOLDER__", payload)

    # Inject the multi-version switcher config (Pages site only).
    if args.versions and args.versions.exists():
        vers = json.loads(args.versions.read_text(encoding="utf-8"))
        snippet = ("<script>window.EXPLORER_VERSIONS="
                   + json.dumps(vers, separators=(",", ":")).replace("</", "<\\/")
                   + ";</script>\n")
        out = out.replace('<script id="module-data"', snippet + '<script id="module-data"', 1)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(out, encoding="utf-8")
    kb = len(out.encode("utf-8")) // 1024
    print(f"Wrote {args.out} ({kb} KB, {len(data['modules'])} modules embedded).")


if __name__ == "__main__":
    main()
