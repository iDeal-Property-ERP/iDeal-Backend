#!/usr/bin/env python3
"""Build standalone interactive HTML schema diagram & documentation for iDeal DBML.

Parses schema.dbml and embeds full schema metadata, relationship graph, and UI
into a zero-dependency, standalone index.html viewer.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[4]
DEFAULT_SCHEMA = BACKEND / "docs" / "db" / "db-diagram" / "schema.dbml"
DEFAULT_OUTPUT = BACKEND / "docs" / "db" / "db-diagram" / "index.html"


def parse_dbml(content: str) -> dict[str, Any]:
    """Parse DBML content into structured tables, enums, groups, and relationships."""
    enums: dict[str, dict[str, Any]] = {}
    tables: dict[str, dict[str, Any]] = {}
    table_groups: dict[str, list[str]] = {}
    relationships: list[dict[str, Any]] = []

    # 1. Parse Enums
    enum_matches = re.finditer(r"Enum\s+([a-zA-Z0-9_]+)\s*\{([^}]+)\}", content, re.MULTILINE)
    for em in enum_matches:
        enum_name = em.group(1)
        body = em.group(2)
        values = []
        for line in body.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            val_match = re.match(r'^(?:"([^"]+)"|([a-zA-Z0-9_]+))(?:\s*\[note:\s*\'([^\']*)\'\])?', line)
            if val_match:
                val = val_match.group(1) or val_match.group(2)
                note = val_match.group(3) or ""
                values.append({"value": val, "note": note})
        enums[enum_name] = {"name": enum_name, "values": values}

    # 2. Parse TableGroups
    group_matches = re.finditer(r"TableGroup\s+([a-zA-Z0-9_]+)\s*\{([^}]+)\}", content, re.MULTILINE)
    for gm in group_matches:
        group_name = gm.group(1)
        body = gm.group(2)
        tbl_names = [
            line.strip() for line in body.strip().splitlines() if line.strip() and not line.strip().startswith("//")
        ]
        table_groups[group_name] = tbl_names

    # 3. Parse Tables
    # Match Table blocks, handling multi-line notes
    table_pattern = re.compile(r"Table\s+([a-zA-Z0-9_]+)\s*\{([\s\S]*?)\n\}", re.MULTILINE)
    for tm in table_pattern.finditer(content):
        table_name = tm.group(1)
        body = tm.group(2)

        fields: list[dict[str, Any]] = []
        indexes: list[dict[str, Any]] = []
        table_note = ""

        # Extract table note if present
        note_match = re.search(r"Note:\s*(?:'''([\s\S]*?)'''|'([^']*)')", body)
        if note_match:
            table_note = (note_match.group(1) or note_match.group(2) or "").strip()

        # Extract indexes block
        idx_match = re.search(r"indexes\s*\{([\s\S]*?)\}", body)
        if idx_match:
            idx_body = idx_match.group(1)
            for idx_line in idx_body.strip().splitlines():
                idx_line = idx_line.strip()
                if not idx_line or idx_line.startswith("//"):
                    continue
                indexes.append({"definition": idx_line})

        # Remove indexes and Note blocks to parse field lines cleanly
        clean_body = re.sub(r"indexes\s*\{[\s\S]*?\}", "", body)
        clean_body = re.sub(r"Note:\s*(?:'''[\s\S]*?'''|'[^']*')", "", clean_body)

        for line in clean_body.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue

            # Field regex: col_name col_type [settings]
            field_match = re.match(r"^([a-zA-Z0-9_]+)\s+([a-zA-Z0-9_(),\s]+?)(?:\s*\[(.*)\])?$", line)
            if not field_match:
                continue

            col_name = field_match.group(1)
            col_type = field_match.group(2).strip()
            raw_settings = field_match.group(3) or ""

            is_pk = "pk" in raw_settings
            is_increment = "increment" in raw_settings
            is_unique = "unique" in raw_settings
            is_not_null = "not null" in raw_settings

            default_match = re.search(r"default:\s*(`[^`]+`|'[^']*'|[^\],]+)", raw_settings)
            default_val = default_match.group(1).strip() if default_match else None

            note_m = re.search(r"note:\s*'([^']*)'", raw_settings)
            col_note = note_m.group(1) if note_m else ""

            # Check ref
            ref_match = re.search(r"ref:\s*([-><])\s*([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)", raw_settings)
            ref_data = None
            if ref_match:
                op = ref_match.group(1)
                target_table = ref_match.group(2)
                target_col = ref_match.group(3)
                ref_data = {
                    "source_table": table_name,
                    "source_col": col_name,
                    "target_table": target_table,
                    "target_col": target_col,
                    "op": op,
                }
                relationships.append(ref_data)

            fields.append(
                {
                    "name": col_name,
                    "type": col_type,
                    "is_pk": is_pk,
                    "is_increment": is_increment,
                    "is_unique": is_unique,
                    "is_not_null": is_not_null,
                    "default": default_val,
                    "note": col_note,
                    "ref": ref_data,
                    "raw_settings": raw_settings,
                }
            )

        # Determine app/domain from table_groups or heuristics
        app_domain = "General"
        for grp_name, tbls in table_groups.items():
            if table_name in tbls:
                app_domain = grp_name
                break

        tables[table_name] = {
            "name": table_name,
            "domain": app_domain,
            "doc": table_note,
            "fields": fields,
            "indexes": indexes,
        }

    # 4. Standalone Ref definitions
    ref_pattern = re.compile(r"Ref:\s*([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)\s*([-><])\s*([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)")
    for rm in ref_pattern.finditer(content):
        source_tbl, source_c, op, target_tbl, target_c = rm.groups()
        # Avoid duplicate
        already = any(
            r["source_table"] == source_tbl and r["source_col"] == source_c and r["target_table"] == target_tbl
            for r in relationships
        )
        if not already:
            relationships.append(
                {
                    "source_table": source_tbl,
                    "source_col": source_c,
                    "target_table": target_tbl,
                    "target_col": target_c,
                    "op": op,
                }
            )

    return {
        "tables": tables,
        "enums": enums,
        "table_groups": table_groups,
        "relationships": relationships,
    }


def generate_html(parsed: dict[str, Any], raw_dbml: str) -> str:
    """Generate standalone interactive HTML with zero runtime network requirements."""
    schema_json = json.dumps(parsed, ensure_ascii=False)
    dbml_escaped = json.dumps(raw_dbml)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>iDeal Database Schema Diagram (DBML)</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg-base: #0b0f19;
      --bg-surface: #111827;
      --bg-surface-elevated: #1f2937;
      --bg-card: #141c2e;
      --bg-card-header: #1e293b;
      --border-subtle: #1e293b;
      --border-strong: #334155;
      --border-focus: #6366f1;
      --text-primary: #f8fafc;
      --text-secondary: #94a3b8;
      --text-muted: #64748b;
      --accent: #6366f1;
      --accent-hover: #4f46e5;
      --accent-soft: rgba(99, 102, 241, 0.15);
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --pk-color: #f59e0b;
      --fk-color: #38bdf8;
      --type-color: #a78bfa;
      --font-sans: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      --font-mono: 'JetBrains Mono', monospace;
      --sidebar-width: 320px;
      --header-height: 64px;
    }}

    [data-theme="light"] {{
      --bg-base: #f8fafc;
      --bg-surface: #ffffff;
      --bg-surface-elevated: #f1f5f9;
      --bg-card: #ffffff;
      --bg-card-header: #f8fafc;
      --border-subtle: #e2e8f0;
      --border-strong: #cbd5e1;
      --border-focus: #4f46e5;
      --text-primary: #0f172a;
      --text-secondary: #475569;
      --text-muted: #94a3b8;
      --accent: #4f46e5;
      --accent-hover: #4338ca;
      --accent-soft: rgba(79, 70, 229, 0.1);
      --pk-color: #d97706;
      --fk-color: #0284c7;
      --type-color: #7c3aed;
    }}

    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: var(--font-sans);
      background-color: var(--bg-base);
      color: var(--text-primary);
      overflow: hidden;
      height: 100vh;
      display: flex;
      flex-direction: column;
      user-select: none;
    }}

    /* Top App Header */
    header {{
      height: var(--header-height);
      background: var(--bg-surface);
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 20px;
      z-index: 30;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
    }}

    .brand {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}

    .logo-badge {{
      background: linear-gradient(135deg, #6366f1, #3b82f6);
      color: #fff;
      font-weight: 700;
      font-size: 14px;
      padding: 4px 8px;
      border-radius: 6px;
      letter-spacing: 0.5px;
    }}

    .brand h1 {{
      font-size: 16px;
      font-weight: 600;
      color: var(--text-primary);
    }}

    .stats-bar {{
      display: flex;
      align-items: center;
      gap: 16px;
      font-size: 13px;
      color: var(--text-secondary);
    }}

    .stat-badge {{
      display: flex;
      align-items: center;
      gap: 6px;
      background: var(--bg-surface-elevated);
      padding: 4px 10px;
      border-radius: 6px;
      border: 1px solid var(--border-subtle);
    }}

    .stat-badge strong {{
      color: var(--text-primary);
    }}

    .header-actions {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    .btn {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: var(--bg-surface-elevated);
      color: var(--text-primary);
      border: 1px solid var(--border-subtle);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
      font-family: var(--font-sans);
    }}

    .btn:hover {{
      background: var(--border-subtle);
      border-color: var(--border-strong);
    }}

    .btn-primary {{
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }}

    .btn-primary:hover {{
      background: var(--accent-hover);
      border-color: var(--accent-hover);
    }}

    /* Layout Body */
    .layout {{
      display: flex;
      flex: 1;
      height: calc(100vh - var(--header-height));
      position: relative;
    }}

    /* Left Sidebar */
    aside.sidebar {{
      width: var(--sidebar-width);
      background: var(--bg-surface);
      border-right: 1px solid var(--border-subtle);
      display: flex;
      flex-direction: column;
      z-index: 20;
    }}

    .search-box {{
      padding: 14px;
      border-bottom: 1px solid var(--border-subtle);
    }}

    .search-input-wrapper {{
      position: relative;
      width: 100%;
    }}

    .search-input {{
      width: 100%;
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 8px 12px 8px 34px;
      font-size: 13px;
      color: var(--text-primary);
      outline: none;
      font-family: var(--font-sans);
    }}

    .search-input:focus {{
      border-color: var(--border-focus);
    }}

    .search-icon {{
      position: absolute;
      left: 10px;
      top: 50%;
      transform: translateY(-50%);
      color: var(--text-muted);
      pointer-events: none;
    }}

    .sidebar-tabs {{
      display: flex;
      border-bottom: 1px solid var(--border-subtle);
      background: var(--bg-surface-elevated);
    }}

    .tab-btn {{
      flex: 1;
      padding: 10px;
      text-align: center;
      font-size: 12px;
      font-weight: 600;
      color: var(--text-secondary);
      background: transparent;
      border: none;
      border-bottom: 2px solid transparent;
      cursor: pointer;
    }}

    .tab-btn.active {{
      color: var(--accent);
      border-bottom-color: var(--accent);
      background: var(--bg-surface);
    }}

    .sidebar-scroll {{
      flex: 1;
      overflow-y: auto;
      padding: 12px;
    }}

    .domain-group {{
      margin-bottom: 16px;
    }}

    .domain-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      color: var(--text-muted);
      letter-spacing: 0.5px;
      padding: 6px 8px;
      cursor: pointer;
      border-radius: 4px;
    }}

    .domain-header:hover {{
      background: var(--bg-surface-elevated);
      color: var(--text-secondary);
    }}

    .table-list-item {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 7px 10px;
      border-radius: 6px;
      font-size: 13px;
      cursor: pointer;
      margin-top: 2px;
      color: var(--text-secondary);
      transition: all 0.15s ease;
    }}

    .table-list-item:hover {{
      background: var(--bg-surface-elevated);
      color: var(--text-primary);
    }}

    .table-list-item.active {{
      background: var(--accent-soft);
      color: var(--accent);
      font-weight: 600;
    }}

    .col-count-badge {{
      font-size: 11px;
      background: var(--bg-surface-elevated);
      padding: 2px 6px;
      border-radius: 4px;
      color: var(--text-muted);
      font-family: var(--font-mono);
    }}

    /* Canvas Area */
    main.canvas-viewport {{
      flex: 1;
      position: relative;
      background-color: var(--bg-base);
      background-image: radial-gradient(var(--border-subtle) 1px, transparent 1px);
      background-size: 24px 24px;
      overflow: hidden;
      cursor: grab;
    }}

    main.canvas-viewport:active {{
      cursor: grabbing;
    }}

    #canvas-container {{
      position: absolute;
      transform-origin: 0 0;
      width: 10000px;
      height: 10000px;
      pointer-events: auto;
    }}

    svg#relationships-layer {{
      position: absolute;
      top: 0;
      left: 0;
      width: 10000px;
      height: 10000px;
      pointer-events: none;
      z-index: 5;
    }}

    .rel-line {{
      stroke: var(--border-strong);
      stroke-width: 1.5;
      fill: none;
      transition: stroke 0.2s ease, stroke-width 0.2s ease;
      opacity: 0.6;
    }}

    .rel-line.highlighted {{
      stroke: var(--fk-color);
      stroke-width: 2.5;
      opacity: 1;
      filter: drop-shadow(0 0 4px var(--fk-color));
    }}

    /* Table Card Nodes on Canvas */
    .table-node {{
      position: absolute;
      width: 320px;
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
      z-index: 10;
      user-select: none;
      cursor: pointer;
      transition: border-color 0.15s ease, box-shadow 0.15s ease, opacity 0.2s ease;
    }}

    .table-node:hover {{
      border-color: var(--border-focus);
      box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
      z-index: 15;
    }}

    .table-node.selected {{
      border-color: var(--accent);
      box-shadow: 0 0 0 2px var(--accent-soft), 0 8px 24px rgba(0, 0, 0, 0.4);
      z-index: 16;
    }}

    .table-node.dimmed {{
      opacity: 0.25;
    }}

    .table-node-header {{
      background: var(--bg-card-header);
      padding: 10px 14px;
      border-top-left-radius: 7px;
      border-top-right-radius: 7px;
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}

    .table-node-title {{
      font-weight: 700;
      font-size: 13px;
      color: var(--text-primary);
      font-family: var(--font-mono);
    }}

    .table-node-domain {{
      font-size: 10px;
      text-transform: uppercase;
      background: var(--accent-soft);
      color: var(--accent);
      padding: 2px 6px;
      border-radius: 4px;
      font-weight: 600;
    }}

    .table-node-fields {{
      padding: 6px 0;
      max-height: 380px;
      overflow-y: auto;
    }}

    .field-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 5px 12px;
      font-size: 12px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.03);
      transition: background 0.1s ease;
    }}

    .field-row:hover {{
      background: var(--bg-surface-elevated);
    }}

    .field-row.highlighted {{
      background: var(--accent-soft);
    }}

    .field-left {{
      display: flex;
      align-items: center;
      gap: 6px;
      overflow: hidden;
    }}

    .badge-pk {{
      font-size: 9px;
      font-weight: 700;
      color: var(--pk-color);
      background: rgba(245, 158, 11, 0.15);
      padding: 1px 4px;
      border-radius: 3px;
    }}

    .badge-fk {{
      font-size: 9px;
      font-weight: 700;
      color: var(--fk-color);
      background: rgba(56, 189, 248, 0.15);
      padding: 1px 4px;
      border-radius: 3px;
    }}

    .field-name {{
      font-family: var(--font-mono);
      color: var(--text-primary);
      white-space: nowrap;
      text-overflow: ellipsis;
      overflow: hidden;
    }}

    .field-type {{
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--type-color);
      white-space: nowrap;
    }}

    /* Floating Canvas Controls */
    .canvas-controls {{
      position: absolute;
      bottom: 24px;
      right: 24px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 6px;
      z-index: 25;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
    }}

    .ctrl-btn {{
      width: 34px;
      height: 34px;
      background: var(--bg-surface-elevated);
      color: var(--text-primary);
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      font-size: 14px;
    }}

    .ctrl-btn:hover {{
      background: var(--border-subtle);
    }}

    /* Slide-over Detail Drawer */
    .drawer {{
      position: fixed;
      top: var(--header-height);
      right: -480px;
      width: 480px;
      height: calc(100vh - var(--header-height));
      background: var(--bg-surface);
      border-left: 1px solid var(--border-subtle);
      box-shadow: -8px 0 24px rgba(0, 0, 0, 0.4);
      z-index: 40;
      transition: right 0.25s cubic-bezier(0.16, 1, 0.3, 1);
      display: flex;
      flex-direction: column;
    }}

    .drawer.open {{
      right: 0;
    }}

    .drawer-header {{
      padding: 16px 20px;
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}

    .drawer-header h2 {{
      font-size: 16px;
      font-family: var(--font-mono);
      color: var(--text-primary);
    }}

    .close-btn {{
      background: transparent;
      border: none;
      color: var(--text-muted);
      cursor: pointer;
      font-size: 18px;
    }}

    .close-btn:hover {{
      color: var(--text-primary);
    }}

    .drawer-content {{
      flex: 1;
      overflow-y: auto;
      padding: 20px;
    }}

    .section-title {{
      font-size: 12px;
      text-transform: uppercase;
      color: var(--text-muted);
      font-weight: 700;
      letter-spacing: 0.5px;
      margin: 16px 0 8px 0;
    }}

    .section-title:first-child {{
      margin-top: 0;
    }}

    .doc-box {{
      background: var(--bg-surface-elevated);
      border: 1px solid var(--border-subtle);
      padding: 12px;
      border-radius: 6px;
      font-size: 13px;
      color: var(--text-secondary);
      line-height: 1.5;
      margin-bottom: 16px;
    }}

    .fields-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
      margin-bottom: 16px;
    }}

    .fields-table th, .fields-table td {{
      padding: 8px;
      text-align: left;
      border-bottom: 1px solid var(--border-subtle);
    }}

    .fields-table th {{
      color: var(--text-muted);
      font-weight: 600;
    }}

    .fields-table td {{
      color: var(--text-primary);
      font-family: var(--font-mono);
    }}

    .code-box {{
      background: var(--bg-base);
      border: 1px solid var(--border-subtle);
      border-radius: 6px;
      padding: 12px;
      font-family: var(--font-mono);
      font-size: 12px;
      color: var(--text-primary);
      overflow-x: auto;
      max-height: 240px;
      white-space: pre;
    }}

    /* Modal for Full Export */
    .modal-backdrop {{
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.6);
      backdrop-filter: blur(4px);
      z-index: 50;
      display: none;
      align-items: center;
      justify-content: center;
    }}

    .modal-backdrop.open {{
      display: flex;
    }}

    .modal-dialog {{
      width: 720px;
      max-width: 90vw;
      max-height: 80vh;
      background: var(--bg-surface);
      border: 1px solid var(--border-subtle);
      border-radius: 12px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }}

    .modal-header {{
      padding: 16px 20px;
      border-bottom: 1px solid var(--border-subtle);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}

    .modal-body {{
      flex: 1;
      overflow-y: auto;
      padding: 20px;
    }}

    .modal-footer {{
      padding: 12px 20px;
      border-top: 1px solid var(--border-subtle);
      display: flex;
      justify-content: flex-end;
      gap: 10px;
    }}
  </style>
</head>
<body>

  <!-- App Header -->
  <header>
    <div class="brand">
      <span class="logo-badge">DBML</span>
      <h1>iDeal Database Schema</h1>
    </div>

    <div class="stats-bar">
      <div class="stat-badge">
        <span>Tables:</span>
        <strong id="stat-tables-count">0</strong>
      </div>
      <div class="stat-badge">
        <span>Columns:</span>
        <strong id="stat-columns-count">0</strong>
      </div>
      <div class="stat-badge">
        <span>Foreign Keys:</span>
        <strong id="stat-refs-count">0</strong>
      </div>
      <div class="stat-badge">
        <span>Enums:</span>
        <strong id="stat-enums-count">0</strong>
      </div>
    </div>

    <div class="header-actions">
      <button class="btn" id="btn-theme-toggle">🌓 Theme</button>
      <button class="btn" id="btn-view-raw-dbml">📄 DBML</button>
      <button class="btn" id="btn-download-dbml">💾 Download</button>
      <button class="btn btn-primary" id="btn-fit-screen">🎯 Center All</button>
    </div>
  </header>

  <!-- Main Layout -->
  <div class="layout">
    <!-- Left Navigation Sidebar -->
    <aside class="sidebar">
      <div class="search-box">
        <div class="search-input-wrapper">
          <span class="search-icon">🔍</span>
          <input type="text" id="table-search" class="search-input" placeholder="Search tables, columns...">
        </div>
      </div>

      <div class="sidebar-tabs">
        <button class="tab-btn active" data-tab="tables">Tables</button>
        <button class="tab-btn" data-tab="enums">Enums</button>
      </div>

      <div class="sidebar-scroll" id="sidebar-tables-view">
        <div id="domains-list"></div>
      </div>

      <div class="sidebar-scroll" id="sidebar-enums-view" style="display: none;">
        <div id="enums-list"></div>
      </div>
    </aside>

    <!-- Interactive Canvas -->
    <main class="canvas-viewport" id="viewport">
      <div id="canvas-container">
        <svg id="relationships-layer">
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#38bdf8" />
            </marker>
            <marker id="arrow-default" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#475569" />
            </marker>
          </defs>
        </svg>
        <div id="tables-layer"></div>
      </div>

      <div class="canvas-controls">
        <button class="ctrl-btn" id="btn-zoom-in" title="Zoom In">+</button>
        <button class="ctrl-btn" id="btn-zoom-out" title="Zoom Out">-</button>
        <button class="ctrl-btn" id="btn-zoom-reset" title="Reset Zoom">1:1</button>
        <button class="ctrl-btn" id="btn-fit-canvas" title="Fit to View">⛶</button>
      </div>
    </main>

    <!-- Detail Drawer -->
    <div class="drawer" id="table-drawer">
      <div class="drawer-header">
        <h2 id="drawer-table-title">Table Details</h2>
        <button class="close-btn" id="btn-close-drawer">✕</button>
      </div>
      <div class="drawer-content">
        <div class="section-title">Documentation</div>
        <div class="doc-box" id="drawer-doc">No description provided.</div>

        <div class="section-title">Columns</div>
        <table class="fields-table">
          <thead>
            <tr>
              <th>Column</th>
              <th>Type</th>
              <th>Details</th>
            </tr>
          </thead>
          <tbody id="drawer-fields-body"></tbody>
        </table>

        <div class="section-title">Foreign Key Relations</div>
        <div class="doc-box" id="drawer-relations">None</div>

        <div class="section-title">DBML Definition</div>
        <pre class="code-box" id="drawer-dbml"></pre>
      </div>
    </div>
  </div>

  <!-- Raw DBML Modal -->
  <div class="modal-backdrop" id="raw-modal">
    <div class="modal-dialog">
      <div class="modal-header">
        <h3>Master DBML Schema (schema.dbml)</h3>
        <button class="close-btn" id="btn-close-modal">✕</button>
      </div>
      <div class="modal-body">
        <pre class="code-box" id="raw-modal-code" style="max-height: 55vh;"></pre>
      </div>
      <div class="modal-footer">
        <button class="btn" id="btn-copy-dbml">📋 Copy DBML</button>
        <button class="btn btn-primary" id="btn-modal-close-action">Close</button>
      </div>
    </div>
  </div>

  <script>
    const SCHEMA_DATA = {schema_json};
    const RAW_DBML = {dbml_escaped};

    // State
    let zoom = 0.85;
    let panX = 60;
    let panY = 60;
    let isDragging = false;
    let startX, startY;
    let selectedTable = null;
    let tablePositions = {{}};

    // DOM Elements
    const viewport = document.getElementById('viewport');
    const container = document.getElementById('canvas-container');
    const tablesLayer = document.getElementById('tables-layer');
    const relsLayer = document.getElementById('relationships-layer');
    const drawer = document.getElementById('table-drawer');

    // Initialize stats
    function initStats() {{
      const tables = Object.values(SCHEMA_DATA.tables);
      document.getElementById('stat-tables-count').textContent = tables.length;
      let cols = 0;
      tables.forEach(t => cols += t.fields.length);
      document.getElementById('stat-columns-count').textContent = cols;
      document.getElementById('stat-refs-count').textContent = SCHEMA_DATA.relationships.length;
      document.getElementById('stat-enums-count').textContent = Object.keys(SCHEMA_DATA.enums).length;
    }}

    // Auto-layout tables in grouped grid
    function computeLayout() {{
      const domains = {{}};
      Object.values(SCHEMA_DATA.tables).forEach(tbl => {{
        if (!domains[tbl.domain]) domains[tbl.domain] = [];
        domains[tbl.domain].push(tbl);
      }});

      let currentX = 100;
      let currentY = 100;
      const CARD_WIDTH = 340;
      const GAP_X = 60;
      const GAP_Y = 40;
      const COLS_PER_DOMAIN = 3;

      Object.entries(domains).forEach(([domain, tbls]) => {{
        let rowX = currentX;
        let rowY = currentY;
        let maxHeightInRow = 0;

        tbls.forEach((tbl, idx) => {{
          const colIdx = idx % COLS_PER_DOMAIN;
          if (idx > 0 && colIdx === 0) {{
            rowX = currentX;
            rowY += maxHeightInRow + GAP_Y;
            maxHeightInRow = 0;
          }}

          const estimatedHeight = 60 + (tbl.fields.length * 28);
          if (estimatedHeight > maxHeightInRow) maxHeightInRow = estimatedHeight;

          tablePositions[tbl.name] = {{
            x: rowX,
            y: rowY,
            width: CARD_WIDTH,
            height: estimatedHeight,
          }};

          rowX += CARD_WIDTH + GAP_X;
        }});

        currentY = rowY + maxHeightInRow + 100;
      }});
    }}

    // Render Table Nodes
    function renderTables() {{
      tablesLayer.innerHTML = '';
      Object.values(SCHEMA_DATA.tables).forEach(tbl => {{
        const pos = tablePositions[tbl.name] || {{ x: 100, y: 100 }};
        const el = document.createElement('div');
        el.className = 'table-node';
        el.id = `node-${{tbl.name}}`;
        el.style.left = `${{pos.x}}px`;
        el.style.top = `${{pos.y}}px`;

        let fieldsHtml = '';
        tbl.fields.forEach(f => {{
          let badge = '';
          if (f.is_pk) badge = '<span class="badge-pk">PK</span>';
          else if (f.ref) badge = '<span class="badge-fk">FK</span>';

          fieldsHtml += `
            <div class="field-row" data-table="${{tbl.name}}" data-col="${{f.name}}">
              <div class="field-left">
                ${{badge}}
                <span class="field-name" title="${{f.name}}">${{f.name}}</span>
              </div>
              <span class="field-type" title="${{f.type}}">${{f.type}}</span>
            </div>
          `;
        }});

        el.innerHTML = `
          <div class="table-node-header">
            <span class="table-node-title">${{tbl.name}}</span>
            <span class="table-node-domain">${{tbl.domain}}</span>
          </div>
          <div class="table-node-fields">
            ${{fieldsHtml}}
          </div>
        `;

        el.addEventListener('click', (e) => {{
          e.stopPropagation();
          selectTable(tbl.name);
        }});

        tablesLayer.appendChild(el);
      }});
    }}

    // Render Relationships SVG Lines
    function renderRelationships() {{
      // Keep defs
      const defs = relsLayer.querySelector('defs').outerHTML;
      let linesHtml = defs;

      SCHEMA_DATA.relationships.forEach((rel, idx) => {{
        const srcPos = tablePositions[rel.source_table];
        const tgtPos = tablePositions[rel.target_table];
        if (!srcPos || !tgtPos) return;

        // Calculate connector points
        const x1 = srcPos.x + srcPos.width;
        const y1 = srcPos.y + 40;
        const x2 = tgtPos.x;
        const y2 = tgtPos.y + 40;

        const dx = Math.abs(x2 - x1) * 0.5;
        const d = `M ${{x1}} ${{y1}} C ${{x1 + dx}} ${{y1}}, ${{x2 - dx}} ${{y2}}, ${{x2}} ${{y2}}`;

        linesHtml += `
          <path class="rel-line" id="rel-${{idx}}" d="${{d}}"
            data-src-table="${{rel.source_table}}"
            data-tgt-table="${{rel.target_table}}"
            marker-end="url(#arrow-default)" />
        `;
      }});

      relsLayer.innerHTML = linesHtml;
    }}

    // Select Table and Open Drawer
    function selectTable(tableName) {{
      selectedTable = tableName;
      const tbl = SCHEMA_DATA.tables[tableName];
      if (!tbl) return;

      // Update selection classes
      document.querySelectorAll('.table-node').forEach(node => {{
        if (node.id === `node-${{tableName}}`) {{
          node.classList.add('selected');
          node.classList.remove('dimmed');
        }} else {{
          node.classList.remove('selected');
        }}
      }});

      // Highlight connections
      const connectedTables = new Set([tableName]);
      document.querySelectorAll('.rel-line').forEach(line => {{
        const src = line.getAttribute('data-src-table');
        const tgt = line.getAttribute('data-tgt-table');
        if (src === tableName || tgt === tableName) {{
          line.classList.add('highlighted');
          line.setAttribute('marker-end', 'url(#arrow)');
          connectedTables.add(src);
          connectedTables.add(tgt);
        }} else {{
          line.classList.remove('highlighted');
          line.setAttribute('marker-end', 'url(#arrow-default)');
        }}
      }});

      // Populate Drawer
      document.getElementById('drawer-table-title').textContent = tbl.name;
      document.getElementById('drawer-doc').textContent = tbl.doc || 'No model docstring provided.';

      let rows = '';
      tbl.fields.forEach(f => {{
        let details = [];
        if (f.is_pk) details.push('PK');
        if (f.is_not_null) details.push('NOT NULL');
        if (f.is_unique) details.push('UNIQUE');
        if (f.default) details.push(`default: ${{f.default}}`);
        if (f.ref) details.push(`→ ${{f.ref.target_table}}.${{f.ref.target_col}}`);
        if (f.note) details.push(`Note: ${{f.note}}`);

        rows += `
          <tr>
            <td><strong>${{f.name}}</strong></td>
            <td style="color: var(--type-color)">${{f.type}}</td>
            <td style="color: var(--text-secondary); font-size: 11px;">${{details.join(', ')}}</td>
          </tr>
        `;
      }});
      document.getElementById('drawer-fields-body').innerHTML = rows;

      // Relations
      const outgoing = SCHEMA_DATA.relationships.filter(r => r.source_table === tableName);
      const incoming = SCHEMA_DATA.relationships.filter(r => r.target_table === tableName);
      let relHtml = '';
      if (outgoing.length) {{
        relHtml += '<strong>Outgoing Foreign Keys:</strong><br>';
        outgoing.forEach(r => relHtml += `• <code>${{r.source_col}}</code> → <code>${{r.target_table}}.${{r.target_col}}</code><br>`);
      }}
      if (incoming.length) {{
        relHtml += '<br><strong>Incoming References:</strong><br>';
        incoming.forEach(r => relHtml += `• <code>${{r.source_table}}.${{r.source_col}}</code> points here<br>`);
      }}
      document.getElementById('drawer-relations').innerHTML = relHtml || 'No foreign key relations.';

      // DBML snippet
      let dbmlSnippet = `Table ${{tbl.name}} {{\\n`;
      tbl.fields.forEach(f => {{
        const settings = f.raw_settings ? ` [${{f.raw_settings}}]` : '';
        dbmlSnippet += `  ${{f.name.padEnd(24)}} ${{f.type.padEnd(16)}}${{settings}}\\n`;
      }});
      dbmlSnippet += `}}`;
      document.getElementById('drawer-dbml').textContent = dbmlSnippet;

      drawer.classList.add('open');

      // Update sidebar active item
      document.querySelectorAll('.table-list-item').forEach(item => {{
        item.classList.toggle('active', item.dataset.table === tableName);
      }});
    }}

    // Sidebar lists
    function renderSidebar() {{
      const domainsContainer = document.getElementById('domains-list');
      const domains = {{}};
      Object.values(SCHEMA_DATA.tables).forEach(tbl => {{
        if (!domains[tbl.domain]) domains[tbl.domain] = [];
        domains[tbl.domain].push(tbl);
      }});

      let html = '';
      Object.entries(domains).sort().forEach(([domain, tbls]) => {{
        html += `<div class="domain-group">`;
        html += `<div class="domain-header"><span>${{domain}}</span><span>${{tbls.length}}</span></div>`;
        tbls.sort((a,b) => a.name.localeCompare(b.name)).forEach(tbl => {{
          html += `
            <div class="table-list-item" data-table="${{tbl.name}}">
              <span>${{tbl.name}}</span>
              <span class="col-count-badge">${{tbl.fields.length}}</span>
            </div>
          `;
        }});
        html += `</div>`;
      }});
      domainsContainer.innerHTML = html;

      // Enums list
      const enumsContainer = document.getElementById('enums-list');
      let enumHtml = '';
      Object.values(SCHEMA_DATA.enums).sort((a,b) => a.name.localeCompare(b.name)).forEach(e => {{
        enumHtml += `
          <div style="margin-bottom: 14px; background: var(--bg-surface-elevated); padding: 10px; border-radius: 6px;">
            <div style="font-weight: 600; font-size: 13px; font-family: var(--font-mono); color: var(--type-color);">${{e.name}}</div>
            <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">
              ${{e.values.map(v => `<code>${{v.value}}</code>`).join(', ')}}
            </div>
          </div>
        `;
      }});
      enumsContainer.innerHTML = enumHtml;

      // Sidebar click events
      document.querySelectorAll('.table-list-item').forEach(el => {{
        el.addEventListener('click', () => {{
          const tblName = el.dataset.table;
          selectTable(tblName);
          focusTable(tblName);
        }});
      }});
    }}

    // Pan / Zoom Controls
    function updateTransform() {{
      container.style.transform = `translate(${{panX}}px, ${{panY}}px) scale(${{zoom}})`;
    }}

    function focusTable(tableName) {{
      const pos = tablePositions[tableName];
      if (!pos) return;
      const rect = viewport.getBoundingClientRect();
      panX = (rect.width / 2) - (pos.x + pos.width / 2) * zoom;
      panY = (rect.height / 2) - (pos.y + pos.height / 2) * zoom;
      updateTransform();
    }}

    viewport.addEventListener('mousedown', (e) => {{
      if (e.target.closest('.table-node') || e.target.closest('.canvas-controls')) return;
      isDragging = true;
      startX = e.clientX - panX;
      startY = e.clientY - panY;
    }});

    window.addEventListener('mousemove', (e) => {{
      if (!isDragging) return;
      panX = e.clientX - startX;
      panY = e.clientY - startY;
      updateTransform();
    }});

    window.addEventListener('mouseup', () => isDragging = false);

    viewport.addEventListener('wheel', (e) => {{
      e.preventDefault();
      const delta = e.deltaY > 0 ? 0.9 : 1.1;
      zoom = Math.min(Math.max(0.2, zoom * delta), 2.5);
      updateTransform();
    }});

    document.getElementById('btn-zoom-in').addEventListener('click', () => {{
      zoom = Math.min(zoom * 1.2, 2.5);
      updateTransform();
    }});

    document.getElementById('btn-zoom-out').addEventListener('click', () => {{
      zoom = Math.max(zoom * 0.8, 0.2);
      updateTransform();
    }});

    document.getElementById('btn-zoom-reset').addEventListener('click', () => {{
      zoom = 1;
      updateTransform();
    }});

    document.getElementById('btn-fit-screen').addEventListener('click', () => {{
      zoom = 0.55;
      panX = 40;
      panY = 40;
      updateTransform();
    }});

    document.getElementById('btn-fit-canvas').addEventListener('click', () => {{
      zoom = 0.55;
      panX = 40;
      panY = 40;
      updateTransform();
    }});

    // Drawer close
    document.getElementById('btn-close-drawer').addEventListener('click', () => {{
      drawer.classList.remove('open');
      document.querySelectorAll('.table-node').forEach(n => {{
        n.classList.remove('selected');
        n.classList.remove('dimmed');
      }});
      document.querySelectorAll('.rel-line').forEach(l => {{
        l.classList.remove('highlighted');
        l.setAttribute('marker-end', 'url(#arrow-default)');
      }});
    }});

    // Search filter
    document.getElementById('table-search').addEventListener('input', (e) => {{
      const q = e.target.value.toLowerCase().trim();
      document.querySelectorAll('.table-list-item').forEach(item => {{
        const name = item.dataset.table.toLowerCase();
        item.style.display = (!q || name.includes(q)) ? 'flex' : 'none';
      }});
      document.querySelectorAll('.table-node').forEach(node => {{
        const name = node.id.replace('node-', '').toLowerCase();
        node.style.display = (!q || name.includes(q)) ? 'block' : 'none';
      }});
    }});

    // Tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {{
      btn.addEventListener('click', () => {{
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tab = btn.dataset.tab;
        document.getElementById('sidebar-tables-view').style.display = tab === 'tables' ? 'block' : 'none';
        document.getElementById('sidebar-enums-view').style.display = tab === 'enums' ? 'block' : 'none';
      }});
    }});

    // Theme toggle
    document.getElementById('btn-theme-toggle').addEventListener('click', () => {{
      const current = document.documentElement.getAttribute('data-theme');
      const next = current === 'light' ? 'dark' : 'light';
      document.documentElement.setAttribute('data-theme', next);
    }});

    // Raw DBML Modal
    const rawModal = document.getElementById('raw-modal');
    document.getElementById('btn-view-raw-dbml').addEventListener('click', () => {{
      document.getElementById('raw-modal-code').textContent = RAW_DBML;
      rawModal.classList.add('open');
    }});

    document.getElementById('btn-close-modal').addEventListener('click', () => rawModal.classList.remove('open'));
    document.getElementById('btn-modal-close-action').addEventListener('click', () => rawModal.classList.remove('open'));
    document.getElementById('btn-copy-dbml').addEventListener('click', () => {{
      navigator.clipboard.writeText(RAW_DBML);
      alert('DBML copied to clipboard!');
    }});

    // Download DBML
    document.getElementById('btn-download-dbml').addEventListener('click', () => {{
      const blob = new Blob([RAW_DBML], {{ type: 'text/plain' }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'schema.dbml';
      a.click();
      URL.revokeObjectURL(url);
    }});

    // Init
    initStats();
    computeLayout();
    renderTables();
    renderRelationships();
    renderSidebar();
    updateTransform();
  </script>
</body>
</html>
"""


def build_html_docs(schema_file: Path = DEFAULT_SCHEMA, output_file: Path = DEFAULT_OUTPUT) -> None:
    """Build index.html from schema.dbml."""
    schema_path = schema_file.resolve()
    target_output = output_file.resolve()
    if not schema_path.exists():
        raise FileNotFoundError(f"DBML schema not found: {schema_path}")
    raw_dbml = schema_path.read_text(encoding="utf-8")
    parsed = parse_dbml(raw_dbml)
    html = generate_html(parsed, raw_dbml)
    target_output.parent.mkdir(parents=True, exist_ok=True)
    target_output.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build DBML interactive HTML documentation")
    parser.add_argument("-s", "--schema", type=Path, default=DEFAULT_SCHEMA, help="Path to schema.dbml")
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUTPUT, help="Path to output index.html")
    args = parser.parse_args()

    build_html_docs(args.schema, args.output)
    print(f"Generated DBML web docs: {args.output}")


if __name__ == "__main__":
    main()
