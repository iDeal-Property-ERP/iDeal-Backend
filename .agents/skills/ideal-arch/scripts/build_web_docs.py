#!/usr/bin/env python3
"""Build standalone interactive HTML architecture documentation for iDeal.

Parses architecture and project markdown documents and generates a modern,
zero-dependency, responsive web viewer at docs/architecture/index.html with
embedded Mermaid diagrams, sidebar navigation, search, and dark/light themes.
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[4]
DOCS_DIR = BACKEND / "docs"
ARCH_DOCS_DIR = DOCS_DIR / "architecture"
PROJECT_DOCS_DIR = DOCS_DIR / "project"
OUTPUT_HTML = ARCH_DOCS_DIR / "index.html"

# Document sources in logical reading order
DOC_SOURCES = [
    {
        "id": "overview",
        "title": "Product Identity & Overview",
        "icon": "ri-apps-line",
        "path": PROJECT_DOCS_DIR / "00-overview.md",
    },
    {
        "id": "architecture",
        "title": "System Architecture & Stack",
        "icon": "ri-building-4-line",
        "path": PROJECT_DOCS_DIR / "01-architecture.md",
    },
    {
        "id": "data-models",
        "title": "Data Models & Storage",
        "icon": "ri-database-2-line",
        "path": PROJECT_DOCS_DIR / "02-data-models.md",
    },
    {
        "id": "api-design",
        "title": "API Strategy & Contracts",
        "icon": "ri-code-s-slash-line",
        "path": PROJECT_DOCS_DIR / "03-api-design.md",
    },
    {
        "id": "realtime-chat",
        "title": "WebSocket Realtime Protocol",
        "icon": "ri-chat-voice-line",
        "path": DOCS_DIR / "api" / "chat-realtime.md",
    },
    {
        "id": "django-q2",
        "title": "Background Tasks & Cron Jobs",
        "icon": "ri-timer-flash-line",
        "path": DOCS_DIR / "django_q2.md",
    },
    {
        "id": "mobile-booking",
        "title": "Mobile & Marketplace Flow",
        "icon": "ri-smartphone-line",
        "path": DOCS_DIR / "mobile-booking-rollout.md",
    },
    {
        "id": "refactor-audit",
        "title": "Codebase Audit & Standards",
        "icon": "ri-shield-check-line",
        "path": ARCH_DOCS_DIR / "backend-refactor-audit.md",
    },
]


def render_markdown_to_html(md_text: str) -> str:
    """Simple, clean markdown to HTML renderer for documentation."""
    lines = md_text.splitlines()
    html_out: list[str] = []
    in_code_block = False
    code_lang = ""
    code_buffer: list[str] = []
    in_table = False
    table_buffer: list[str] = []
    in_list = False
    list_type = ""

    def flush_table():
        nonlocal in_table, table_buffer
        if not table_buffer:
            in_table = False
            return
        out = ['<div class="table-container"><table>']
        header_done = False
        for row_str in table_buffer:
            if re.match(r"^\|?\s*[-:]+[-| :]*\s*\|?$", row_str):
                continue
            cols = [c.strip() for c in row_str.strip("|").split("|")]
            if not header_done:
                out.append("<thead><tr>")
                for c in cols:
                    out.append(f"<th>{inline_format(c)}</th>")
                out.append("</tr></thead><tbody>")
                header_done = True
            else:
                out.append("<tr>")
                for c in cols:
                    out.append(f"<td>{inline_format(c)}</td>")
                out.append("</tr>")
        if header_done:
            out.append("</tbody>")
        out.append("</table></div>")
        html_out.append("\n".join(out))
        table_buffer = []
        in_table = False

    def flush_list():
        nonlocal in_list, list_type
        if in_list:
            html_out.append(f"</{list_type}>")
            in_list = False
            list_type = ""

    def inline_format(text: str) -> str:
        # Code
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        # Bold
        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        # Italic
        text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
        # Links
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
        return text

    for line in lines:
        stripped = line.strip()

        # Code block boundary
        if stripped.startswith("```"):
            if in_code_block:
                code_content = "\n".join(code_buffer)
                if code_lang == "mermaid":
                    html_out.append(
                        f'<div class="mermaid-wrap"><pre class="mermaid">{html.escape(code_content)}</pre></div>'
                    )
                else:
                    html_out.append(
                        f'<div class="code-block"><div class="code-header"><span>{code_lang or "text"}</span><button class="copy-btn" onclick="copyCode(this)">Copy</button></div><pre><code class="language-{code_lang}">{html.escape(code_content)}</code></pre></div>'
                    )
                code_buffer = []
                in_code_block = False
                code_lang = ""
            else:
                flush_table()
                flush_list()
                in_code_block = True
                code_lang = stripped[3:].strip()
            continue

        if in_code_block:
            code_buffer.append(line)
            continue

        # Table rows
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_list()
            in_table = True
            table_buffer.append(stripped)
            continue
        elif in_table:
            flush_table()

        # Blank line
        if not stripped:
            flush_list()
            continue

        # Headings
        h_match = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if h_match:
            flush_list()
            level = len(h_match.group(1))
            heading_text = h_match.group(2)
            heading_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", heading_text.lower()).strip("-")
            html_out.append(
                f'<h{level} id="{heading_id}">{inline_format(heading_text)} <a class="heading-anchor" href="#{heading_id}">#</a></h{level}>'
            )
            continue

        # Horizontal rule
        if re.match(r"^---+$", stripped) or re.match(r"^\*\*\*+$", stripped):
            flush_list()
            html_out.append("<hr/>")
            continue

        # Blockquotes / Callouts
        if stripped.startswith(">"):
            flush_list()
            quote_text = stripped.lstrip("> ").strip()
            callout_type = "info"
            if quote_text.lower().startswith("**note:**") or quote_text.lower().startswith("[!note]"):
                callout_type = "note"
            elif quote_text.lower().startswith("**warning:**") or quote_text.lower().startswith("[!warning]"):
                callout_type = "warning"
            elif quote_text.lower().startswith("**tip:**") or quote_text.lower().startswith("[!tip]"):
                callout_type = "tip"
            html_out.append(
                f'<blockquote class="callout callout-{callout_type}">{inline_format(quote_text)}</blockquote>'
            )
            continue

        # Unordered list
        ul_match = re.match(r"^[-*+]\s+(.*)$", stripped)
        if ul_match:
            if not in_list or list_type != "ul":
                flush_list()
                in_list = True
                list_type = "ul"
                html_out.append("<ul>")
            html_out.append(f"<li>{inline_format(ul_match.group(1))}</li>")
            continue

        # Ordered list
        ol_match = re.match(r"^\d+\.\s+(.*)$", stripped)
        if ol_match:
            if not in_list or list_type != "ol":
                flush_list()
                in_list = True
                list_type = "ol"
                html_out.append("<ol>")
            html_out.append(f"<li>{inline_format(ol_match.group(1))}</li>")
            continue

        # Plain paragraph
        flush_list()
        html_out.append(f"<p>{inline_format(stripped)}</p>")

    if in_code_block:
        html_out.append(f"<pre><code>{html.escape(chr(10).join(code_buffer))}</code></pre>")
    flush_table()
    flush_list()

    return "\n".join(html_out)


def build_architecture_viewer() -> str:
    """Load all markdown documents, generate TOC, and embed into single HTML page."""
    sections: list[dict[str, Any]] = []

    for src in DOC_SOURCES:
        path: Path = src["path"]
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        rendered_html = render_markdown_to_html(content)
        sections.append(
            {
                "id": src["id"],
                "title": src["title"],
                "icon": src["icon"],
                "html": rendered_html,
                "raw_text": content,
            }
        )

    # Visual Architecture Diagram (Mermaid) to embed in main overview section
    c4_system_diagram = """
graph TB
    subgraph ClientTier ["Client Tier (Web & Mobile)"]
        WebSPA["Next.js App Router (SPA)<br/>(Web Application)"]
        MobileApp["Flutter Mobile App<br/>(iOS & Android)"]
    end

    subgraph EdgeTier ["Edge & Reverse Proxy"]
        Nginx["Nginx Edge Proxy<br/>(SSL / HTTP/2 / Static Cache / Rate Limiting)"]
    end

    subgraph AppTier ["Application Tier (Dockerized Django 5.2)"]
        ASGI["ASGI Server (Uvicorn / Django Channels)"]
        RESTAPI["DMR REST API Layer<br/>(JWT Auth, Pydantic, OpenAPI)"]
        WSHub["WebSocket Event Hub<br/>(Realtime Chat & Alerts)"]
        Q2Worker["Django-Q2 Worker Cluster<br/>(Async Cron & Background Tasks)"]
    end

    subgraph DataTier ["Data & Cache Storage Tier"]
        Postgres[("PostgreSQL 16 Database<br/>(Relational Stores, ACID, SoftDeletes)")]
        RedisDB[("Redis 7 In-Memory<br/>(Cache, Channel Layers, Task Broker)")]
        S3Storage[("S3 / CDN Media Storage<br/>(Photos, Acts, Documents)")]
    end

    subgraph ExternalServices ["External Integrations"]
        Eskiz["Eskiz SMS Gateway<br/>(OTP Verification)"]
        Payments["Click / Payme / Stripe<br/>(Payment Webhooks & Gateways)"]
        FCM["Firebase Cloud Messaging<br/>(Push Notifications)"]
    end

    WebSPA -->|HTTPS / REST API| Nginx
    MobileApp -->|HTTPS / REST API| Nginx
    WebSPA -.->|WSS / WebSocket| Nginx
    MobileApp -.->|WSS / WebSocket| Nginx

    Nginx -->|Proxy Pass| ASGI
    ASGI --> RESTAPI
    ASGI --> WSHub

    RESTAPI --> Postgres
    RESTAPI --> RedisDB
    RESTAPI --> S3Storage

    WSHub <--> RedisDB
    Q2Worker <--> RedisDB
    Q2Worker --> Postgres

    RESTAPI --> Eskiz
    RESTAPI --> FCM
    Payments -->|Webhooks| Nginx
"""

    c4_mermaid_block = f"""
<div class="c4-hero-card">
    <div class="c4-hero-header">
        <div>
            <span class="badge badge-primary">C4 Level 2</span>
            <h3 style="margin: 6px 0 0 0; font-size: 1.25rem;">iDeal High-Level System Container Diagram</h3>
        </div>
        <button class="btn btn-sm" onclick="toggleMermaidZoom(this)">Expand Diagram</button>
    </div>
    <div class="mermaid-wrap">
        <pre class="mermaid">
{c4_system_diagram.strip()}
        </pre>
    </div>
</div>
"""

    html_template = f"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>iDeal System Architecture & Technical Specifications</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/remixicon@4.2.0/fonts/remixicon.css">
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.0/dist/mermaid.min.js"></script>
    <style>
        :root {{
            --bg-body: #0a0d14;
            --bg-sidebar: #0f1420;
            --bg-card: #141a29;
            --bg-card-hover: #1b2337;
            --border-color: #232c42;
            --border-color-light: #2e3b58;
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            --text-dim: #64748b;
            --primary: #3b82f6;
            --primary-light: #60a5fa;
            --primary-bg: rgba(59, 130, 246, 0.12);
            --accent: #10b981;
            --accent-bg: rgba(16, 185, 129, 0.12);
            --warning: #f59e0b;
            --warning-bg: rgba(245, 158, 11, 0.12);
            --danger: #ef4444;
            --font-sans: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
            --header-h: 64px;
            --sidebar-w: 300px;
        }}

        [data-theme="light"] {{
            --bg-body: #f8fafc;
            --bg-sidebar: #ffffff;
            --bg-card: #ffffff;
            --bg-card-hover: #f1f5f9;
            --border-color: #e2e8f0;
            --border-color-light: #cbd5e1;
            --text-main: #0f172a;
            --text-muted: #475569;
            --text-dim: #94a3b8;
            --primary: #2563eb;
            --primary-light: #3b82f6;
            --primary-bg: rgba(37, 99, 235, 0.08);
            --accent: #059669;
            --accent-bg: rgba(5, 150, 105, 0.08);
            --warning: #d97706;
            --warning-bg: rgba(217, 119, 6, 0.08);
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: var(--font-sans);
            background: var(--bg-body);
            color: var(--text-main);
            line-height: 1.6;
            font-size: 15px;
            display: flex;
            min-height: 100vh;
            overflow-x: hidden;
        }}

        /* Header */
        .top-header {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            height: var(--header-h);
            background: var(--bg-sidebar);
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 24px;
            z-index: 100;
        }}

        .brand-logo {{
            display: flex;
            align-items: center;
            gap: 12px;
            text-decoration: none;
            color: var(--text-main);
            font-weight: 800;
            font-size: 1.25rem;
            letter-spacing: -0.02em;
        }}

        .brand-badge {{
            font-size: 0.7rem;
            font-weight: 700;
            background: var(--primary-bg);
            color: var(--primary-light);
            padding: 2px 8px;
            border-radius: 6px;
            border: 1px solid rgba(59, 130, 246, 0.3);
            text-transform: uppercase;
        }}

        .header-links {{
            display: flex;
            align-items: center;
            gap: 12px;
        }}

        .nav-pill {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            border-radius: 8px;
            text-decoration: none;
            color: var(--text-muted);
            font-size: 0.85rem;
            font-weight: 600;
            border: 1px solid transparent;
            transition: all 0.2s;
        }}

        .nav-pill:hover {{
            background: var(--bg-card);
            color: var(--text-main);
            border-color: var(--border-color);
        }}

        .nav-pill.active {{
            background: var(--primary-bg);
            color: var(--primary-light);
            border-color: rgba(59, 130, 246, 0.4);
        }}

        .theme-toggle {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            color: var(--text-muted);
            width: 36px;
            height: 36px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .theme-toggle:hover {{
            color: var(--text-main);
            border-color: var(--primary);
        }}

        /* Sidebar */
        .sidebar {{
            position: fixed;
            top: var(--header-h);
            left: 0;
            bottom: 0;
            width: var(--sidebar-w);
            background: var(--bg-sidebar);
            border-right: 1px solid var(--border-color);
            overflow-y: auto;
            padding: 20px 16px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            z-index: 90;
        }}

        .search-box {{
            position: relative;
            margin-bottom: 12px;
        }}

        .search-box input {{
            width: 100%;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 8px 12px 8px 36px;
            color: var(--text-main);
            font-family: inherit;
            font-size: 0.85rem;
            outline: none;
            transition: border-color 0.2s;
        }}

        .search-box input:focus {{
            border-color: var(--primary);
        }}

        .search-box i {{
            position: absolute;
            left: 12px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-dim);
            font-size: 1rem;
        }}

        .sidebar-nav {{
            display: flex;
            flex-direction: column;
            gap: 4px;
        }}

        .nav-item {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 12px;
            border-radius: 8px;
            color: var(--text-muted);
            text-decoration: none;
            font-size: 0.88rem;
            font-weight: 500;
            transition: all 0.15s;
        }}

        .nav-item:hover {{
            background: var(--bg-card-hover);
            color: var(--text-main);
        }}

        .nav-item.active {{
            background: var(--primary-bg);
            color: var(--primary-light);
            font-weight: 600;
        }}

        .nav-item i {{
            font-size: 1.1rem;
        }}

        /* Main Content */
        .main-content {{
            margin-left: var(--sidebar-w);
            margin-top: var(--header-h);
            padding: 40px 48px 100px;
            max-width: 1100px;
            width: calc(100% - var(--sidebar-w));
        }}

        .section-block {{
            margin-bottom: 60px;
            scroll-margin-top: calc(var(--header-h) + 20px);
        }}

        h1, h2, h3, h4, h5, h6 {{
            color: var(--text-main);
            font-weight: 700;
            line-height: 1.3;
            margin: 28px 0 16px;
            position: relative;
        }}

        h1 {{
            font-size: 2.2rem;
            letter-spacing: -0.03em;
            margin-top: 0;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border-color);
        }}

        h2 {{
            font-size: 1.5rem;
            letter-spacing: -0.02em;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--border-color);
        }}

        h3 {{
            font-size: 1.2rem;
        }}

        p {{
            margin-bottom: 16px;
            color: var(--text-main);
        }}

        .heading-anchor {{
            color: var(--text-dim);
            text-decoration: none;
            opacity: 0;
            margin-left: 6px;
            font-size: 0.9em;
            transition: opacity 0.2s;
        }}

        h1:hover .heading-anchor,
        h2:hover .heading-anchor,
        h3:hover .heading-anchor {{
            opacity: 1;
        }}

        /* Code & Tables */
        code {{
            font-family: var(--font-mono);
            font-size: 0.88em;
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            padding: 2px 6px;
            border-radius: 4px;
            color: var(--primary-light);
        }}

        .code-block {{
            background: var(--bg-sidebar);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            margin: 16px 0;
            overflow: hidden;
        }}

        .code-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: var(--bg-card);
            padding: 6px 14px;
            font-size: 0.75rem;
            color: var(--text-dim);
            font-family: var(--font-mono);
            border-bottom: 1px solid var(--border-color);
        }}

        .copy-btn {{
            background: transparent;
            border: 1px solid var(--border-color);
            color: var(--text-muted);
            border-radius: 4px;
            padding: 2px 8px;
            font-size: 0.7rem;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .copy-btn:hover {{
            background: var(--bg-card-hover);
            color: var(--text-main);
        }}

        pre {{
            padding: 16px;
            overflow-x: auto;
            font-family: var(--font-mono);
            font-size: 0.88rem;
            line-height: 1.5;
        }}

        pre code {{
            background: transparent;
            border: none;
            padding: 0;
            color: var(--text-main);
        }}

        .table-container {{
            overflow-x: auto;
            margin: 20px 0;
            border: 1px solid var(--border-color);
            border-radius: 10px;
            background: var(--bg-sidebar);
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.9rem;
            text-align: left;
        }}

        th {{
            background: var(--bg-card);
            color: var(--text-muted);
            font-weight: 600;
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-color);
        }}

        td {{
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-color);
            color: var(--text-main);
        }}

        tr:last-child td {{
            border-bottom: none;
        }}

        ul, ol {{
            margin: 12px 0 20px 24px;
        }}

        li {{
            margin-bottom: 6px;
        }}

        hr {{
            border: none;
            border-top: 1px solid var(--border-color);
            margin: 32px 0;
        }}

        /* Hero / C4 Card */
        .c4-hero-card {{
            background: var(--bg-sidebar);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            margin: 24px 0 32px;
        }}

        .c4-hero-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }}

        .badge {{
            font-size: 0.75rem;
            font-weight: 700;
            padding: 3px 8px;
            border-radius: 6px;
            text-transform: uppercase;
        }}

        .badge-primary {{
            background: var(--primary-bg);
            color: var(--primary-light);
            border: 1px solid rgba(59, 130, 246, 0.3);
        }}

        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 6px 12px;
            border-radius: 6px;
            border: 1px solid var(--border-color);
            background: var(--bg-card);
            color: var(--text-main);
            font-size: 0.8rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .btn:hover {{
            background: var(--bg-card-hover);
            border-color: var(--primary);
        }}

        .mermaid-wrap {{
            background: var(--bg-body);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 20px;
            overflow-x: auto;
            display: flex;
            justify-content: center;
        }}

        .mermaid {{
            text-align: center;
        }}

        .callout {{
            border-left: 4px solid var(--primary);
            background: var(--primary-bg);
            padding: 14px 18px;
            border-radius: 0 8px 8px 0;
            margin: 16px 0;
            font-size: 0.95rem;
        }}

        .callout-warning {{
            border-left-color: var(--warning);
            background: var(--warning-bg);
        }}

        .callout-note {{
            border-left-color: var(--accent);
            background: var(--accent-bg);
        }}

        @media (max-width: 900px) {{
            .sidebar {{
                display: none;
            }}
            .main-content {{
                margin-left: 0;
                width: 100%;
                padding: 24px;
            }}
        }}
    </style>
</head>
<body>
    <header class="top-header">
        <a href="/" class="brand-logo">
            <span>🏢 iDeal</span>
            <span class="brand-badge">Docs Hub</span>
        </a>
        <div class="header-links">
            <a href="/db/" class="nav-pill">
                <i class="ri-database-2-line"></i> DB Schema & ER
            </a>
            <a href="/api/" class="nav-pill">
                <i class="ri-code-s-slash-line"></i> Bruno API
            </a>
            <a href="/arch/" class="nav-pill active">
                <i class="ri-building-4-line"></i> Architecture
            </a>
            <button class="theme-toggle" onclick="toggleTheme()" title="Toggle Light/Dark Theme">
                <i class="ri-moon-line" id="theme-icon"></i>
            </button>
        </div>
    </header>

    <aside class="sidebar">
        <div class="search-box">
            <i class="ri-search-line"></i>
            <input type="text" id="searchInput" placeholder="Search architecture docs..." onkeyup="filterDocs()">
        </div>
        <nav class="sidebar-nav">
"""

    for s in sections:
        html_template += f"""
            <a href="#{s["id"]}" class="nav-item" onclick="setActiveNav(this)">
                <i class="{s["icon"]}"></i>
                <span>{s["title"]}</span>
            </a>
"""

    html_template += f"""
        </nav>
    </aside>

    <main class="main-content" id="mainContent">
        <div class="section-block" id="overview-hero">
            <h1>iDeal Architecture & Technical Documentation</h1>
            <p style="font-size: 1.1rem; color: var(--text-muted); margin-bottom: 24px;">
                Comprehensive system architecture, C4 container topologies, relational database domain models, REST API specifications, and operational execution standards.
            </p>
            {c4_mermaid_block}
        </div>
"""

    for s in sections:
        html_template += f"""
        <section class="section-block doc-section" id="{s["id"]}">
            <div class="section-header">
                <h2><i class="{s["icon"]}" style="margin-right: 8px; color: var(--primary);"></i> {s["title"]}</h2>
            </div>
            {s["html"]}
        </section>
"""

    html_template += """
    </main>

    <script>
        mermaid.initialize({
            startOnLoad: true,
            theme: document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'default',
            securityLevel: 'loose',
            flowchart: { useMaxWidth: true, htmlLabels: true, curve: 'basis' }
        });

        function toggleTheme() {
            const current = document.documentElement.getAttribute('data-theme');
            const next = current === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next);
            localStorage.setItem('ideal-theme', next);
            document.getElementById('theme-icon').className = next === 'dark' ? 'ri-moon-line' : 'ri-sun-line';
            location.reload();
        }

        const savedTheme = localStorage.getItem('ideal-theme');
        if (savedTheme) {
            document.documentElement.setAttribute('data-theme', savedTheme);
            document.getElementById('theme-icon').className = savedTheme === 'dark' ? 'ri-moon-line' : 'ri-sun-line';
        }

        function setActiveNav(element) {
            document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
            element.classList.add('active');
        }

        function copyCode(btn) {
            const codeBlock = btn.closest('.code-block').querySelector('code');
            navigator.clipboard.writeText(codeBlock.innerText).then(() => {
                btn.innerText = 'Copied!';
                setTimeout(() => { btn.innerText = 'Copy'; }, 2000);
            });
        }

        function filterDocs() {
            const query = document.getElementById('searchInput').value.toLowerCase();
            const sections = document.querySelectorAll('.doc-section');
            const navItems = document.querySelectorAll('.nav-item');

            sections.forEach((sec, idx) => {
                const text = sec.innerText.toLowerCase();
                const match = text.includes(query);
                sec.style.display = match ? 'block' : 'none';
                if (navItems[idx]) {
                    navItems[idx].style.display = match ? 'flex' : 'none';
                }
            });
        }

        function toggleMermaidZoom(btn) {
            const wrap = btn.closest('.c4-hero-card').querySelector('.mermaid-wrap');
            if (wrap.style.maxHeight === 'none') {
                wrap.style.maxHeight = '500px';
                btn.innerText = 'Expand Diagram';
            } else {
                wrap.style.maxHeight = 'none';
                btn.innerText = 'Collapse Diagram';
            }
        }
    </script>
</body>
</html>
"""
    return html_template


def main():
    print(f"Compiling architecture documentation into {OUTPUT_HTML}...")
    OUTPUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    html_content = build_architecture_viewer()
    OUTPUT_HTML.write_text(html_content, encoding="utf-8")
    print(f"Generated standalone Architecture documentation portal: {OUTPUT_HTML} ({len(html_content)} bytes)")


if __name__ == "__main__":
    main()
