---
name: ideal-dbml
description: Maintain the iDeal backend DBML database schema documentation, visual diagram, and PostgreSQL DDL export. Use for schema inventory, DBML generation from Django models, syntax & referential integrity validation via @dbml/cli, SQL export, and interactive HTML viewer builds.
---

# iDeal DBML Schema Management

Maintain the database schema documentation at `docs/db/db-diagram/` in the Backend repository.
The Django models (`src/apps/*`) and database migrations are the authoritative source of truth.
This tooling integrates [DBML CLI](https://dbml.dbdiagram.io/cli/) (`@dbml/cli`) for validation and SQL export.

## Fast workflows

Run all commands from the `Backend` directory:

- **Inventory schema and model stats**:

  ```bash
  just dbml-inventory
  # Or: uv run python .agents/skills/ideal-dbml/scripts/dbml_tool.py inventory
  ```

- **Generate or refresh modular DBML and HTML viewer**:

  ```bash
  just dbml-generate
  # Or: uv run python .agents/skills/ideal-dbml/scripts/dbml_tool.py generate
  ```

  This introspects all 16 Django apps, updates `docs/db/db-diagram/domains/*.dbml`,
  assembles `docs/db/db-diagram/schema.dbml`, and regenerates `docs/db/db-diagram/index.html`.

- **Validate DBML syntax and referential integrity**:

  ```bash
  just dbml-validate
  # Or: uv run python .agents/skills/ideal-dbml/scripts/dbml_tool.py validate
  ```

  Validates that all foreign key target tables exist and runs `@dbml/cli` (`npx @dbml/cli dbml2sql`).

- **Export PostgreSQL DDL**:

  ```bash
  just dbml-sql
  # Or: uv run python .agents/skills/ideal-dbml/scripts/dbml_tool.py export-sql
  ```

  Exports clean PostgreSQL schema DDL to `docs/db/db-diagram/schema.sql`.

- **Rebuild standalone interactive web viewer**:

  ```bash
  just dbml-html
  # Or: uv run python .agents/skills/ideal-dbml/scripts/build_web_docs.py
  ```

  Generates the zero-dependency, standalone `docs/db/db-diagram/index.html`.

## Layout & Structure

The schema documentation under `docs/db/db-diagram/` is structured as follows:

```text
docs/db/db-diagram/
├── README.md                      # Schema documentation & CLI quickstart
├── schema.dbml                    # Master consolidated DBML bundle
├── index.html                     # Standalone interactive ER diagram & documentation viewer
├── common/
│   ├── enums.dbml                 # Shared choices / enums (ConstantChoices)
│   └── groups.dbml                # TableGroup definitions for canvas grouping
└── domains/                       # Modular DBML files per Django app
    ├── account.dbml
    ├── agent.dbml
    ├── chat.dbml
    ├── contract.dbml
    ├── finance.dbml
    ├── inventory.dbml
    ├── maintenance.dbml
    ├── marketplace.dbml
    ├── mobile_config.dbml
    ├── notification.dbml
    ├── property.dbml
    └── vas.dbml
```

## Non-negotiable conventions

- **Exact Table Names**: Table names in DBML must match Django `db_table` exact names (e.g. `users`, `properties`, `one_off_deals`).
- **Explicit Foreign Keys**: Always document relationship direction and cardinality:
  - Many-to-One: `Ref: child_table.parent_id > parent_table.id`
  - One-to-One: `Ref: child_table.parent_id - parent_table.id` (with `unique` setting on column)
  - Many-to-Many: Document explicit junction table (e.g. `properties_amenities`).
- **Shared Enums**: Place reusable choices (`ConstantChoices`) in `common/enums.dbml`. Name enums using lowercase snake_case (e.g. `user_role`, `property_status`, `listing_status`).
- **Documentation Notes**:
  - Keep model docstrings synchronized with table notes: `Note: '...'`.
  - Field `help_text` and `verbose_name` must be reflected as column notes: `[note: '...']`.
- **Pre-commit Automation**:
  - Pre-commit hook automatically verifies DBML syntax and regenerates `index.html` on commits modifying models or DBML files.
