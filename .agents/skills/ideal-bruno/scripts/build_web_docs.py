#!/usr/bin/env python3
"""Build Bruno's standalone interactive HTML documentation from OpenCollection YAML."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


DEFAULT_COLLECTION = Path(__file__).resolve().parents[4] / "docs" / "api" / "bruno"
DEFAULT_OUTPUT = DEFAULT_COLLECTION / "index.html"
BRUNO_DOCS_CDN = "https://cdn.opencollection.com"


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = yaml.safe_load(handle) or {}
    if not isinstance(value, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return value


def item_sort_key(path: Path) -> tuple[int, str]:
    data = read_yaml(path / "folder.yml" if path.is_dir() else path)
    return int(data.get("info", {}).get("seq", 0)), path.name


def load_folder(path: Path) -> dict[str, Any]:
    folder = read_yaml(path / "folder.yml")
    items: list[dict[str, Any]] = []
    children = [child for child in path.iterdir() if child.is_dir() and (child / "folder.yml").exists()]
    files = [child for child in path.glob("*.yml") if child.name != "folder.yml"]
    for child in sorted(children, key=item_sort_key):
        items.append(load_folder(child))
    for child in sorted(files, key=item_sort_key):
        items.append(read_yaml(child))
    folder["items"] = items
    return folder


def load_environment(path: Path) -> dict[str, Any]:
    environment = read_yaml(path)
    # Keep secret values blank in the published HTML even if a local file is
    # accidentally populated before the build runs.
    for variable in environment.get("variables", []):
        if variable.get("secret"):
            variable["value"] = ""
    return environment


def build_collection(collection_path: Path) -> dict[str, Any]:
    root = read_yaml(collection_path / "opencollection.yml")
    root_info = root.get("info", {})
    folders = [child for child in collection_path.iterdir() if child.is_dir() and (child / "folder.yml").exists()]
    requests = [
        child
        for child in collection_path.glob("*.yml")
        if child.name != "opencollection.yml"
    ]
    collection: dict[str, Any] = {
        "opencollection": root.get("opencollection", "1.0.0"),
        "info": {
            "name": root_info.get("name", "iDeal"),
            "version": root_info.get("version", "1.0.0"),
            "summary": root_info.get("description", "iDeal Backend API documentation"),
        },
        "bundled": True,
        "items": [load_folder(folder) for folder in sorted(folders, key=item_sort_key)],
    }
    collection["items"].extend(read_yaml(path) for path in sorted(requests, key=item_sort_key))
    environments = collection_path / "environments"
    environment_files = sorted(environments.glob("*.yml")) if environments.exists() else []
    if environment_files:
        collection["config"] = {"environments": [load_environment(path) for path in environment_files]}
    return collection


def build_html(collection: dict[str, Any], git_collection_url: str | None) -> str:
    serialized = json.dumps(collection, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    source = json.dumps(git_collection_url) if git_collection_url else None
    source_argument = f", gitCollectionUrl: {source}" if source else ""
    title = json.dumps(collection["info"]["name"])
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{json.loads(title)} - API Documentation</title>
    <style>body {{ margin: 0; padding: 0; }} #opencollection-container {{ width: 100vw; height: 100vh; }}</style>
    <link rel="stylesheet" href="{BRUNO_DOCS_CDN}/docs.css">
    <script src="{BRUNO_DOCS_CDN}/docs.js"></script>
</head>
<body>
    <div id="opencollection-container"></div>
    <script>
        const collectionData = {serialized};
        new window.OpenCollection({{
            target: document.getElementById('opencollection-container'),
            opencollection: collectionData,
            theme: 'light'{source_argument}
        }});
    </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", type=Path, default=DEFAULT_COLLECTION)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--git-collection-url",
        default="https://github.com/iDeal-Property-ERP/iDeal-Backend/tree/production/docs/api/bruno",
    )
    args = parser.parse_args()
    collection = build_collection(args.collection)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(build_html(collection, args.git_collection_url), encoding="utf-8")
    print(f"Generated {args.output} ({len(args.output.read_bytes())} bytes)")


if __name__ == "__main__":
    main()
