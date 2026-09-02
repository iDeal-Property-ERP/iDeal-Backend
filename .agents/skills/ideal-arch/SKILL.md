---
name: ideal-arch
description: Maintain and generate the iDeal system architecture documentation portal. Compiles architectural markdown, C4 models, Mermaid diagrams, and infrastructure topology into a standalone interactive web viewer at docs/architecture/index.html.
---

# iDeal Architecture Documentation

Maintain the system architecture documentation at `docs/architecture/` in the Backend repository.
This tooling integrates markdown compilation, Mermaid diagram rendering, and interactive navigation into a zero-dependency web viewer.

## Fast workflows

Run all commands from the `Backend` directory:

- **Build interactive architecture portal**:

  ```bash
  just arch-html
  # Or: uv run python .agents/skills/ideal-arch/scripts/build_web_docs.py
  ```

  Generates the standalone `docs/architecture/index.html`.

- **Build all documentation portals**:

  ```bash
  just docs-build
  ```

  Rebuilds DBML (`/db/`), Bruno API (`/api/`), Architecture (`/arch/`), and the unified Hub (`/`).
