# iDeal Database Schema & DBML Documentation

This directory contains the Git-tracked database schema documentation for the iDeal backend, maintained using **[DBML (Database Markup Language)](https://dbml.dbdiagram.io/)** and the official **[`@dbml/cli`](https://dbml.dbdiagram.io/cli/)** tooling.

## Quick Links

- **Interactive Visual Diagram**: Open [`index.html`](./index.html) in any browser (zero server setup required, 100% offline).
- **Master DBML Schema**: [`schema.dbml`](./schema.dbml)
- **PostgreSQL DDL Export**: [`schema.sql`](./schema.sql)

---

## Directory Structure

```text
docs/db/db-diagram/
├── README.md                      # This documentation
├── schema.dbml                    # Consolidated master DBML bundle
├── schema.sql                     # Exported PostgreSQL DDL
├── index.html                     # Standalone interactive ER diagram & table inspector
├── common/
│   ├── enums.dbml                 # Shared choices / enums (ConstantChoices)
│   └── groups.dbml                # TableGroup definitions for visual grouping
└── domains/                       # Modular DBML files per Django app
    ├── account.dbml               # Users, authentication, tokens
    ├── agent.dbml                 # Agents, brokerage deals, performance
    ├── chat.dbml                  # Realtime conversations, messages, reports
    ├── contract.dbml              # Leases, owner agreements, public offers
    ├── finance.dbml               # Payments, payouts, settlements, allocations
    ├── inventory.dbml             # Condition acts, passportization items, photos
    ├── maintenance.dbml           # Service requests, comments, assignments
    ├── marketplace.dbml           # Listings, viewing requests, bookings, checkouts
    ├── mobile_config.dbml         # Mobile app update policies & version ranges
    ├── notification.dbml          # In-app notifications, push tokens, preferences
    ├── property.dbml              # Properties, amenities, photos, verification visits
    └── vas.dbml                   # Value-added services catalog & orders
```

---

## CLI & Development Workflows

All commands can be run via `just` or directly via `uv`:

### 1. Regenerate Schema from Django Models

Whenever Django models (`src/apps/*`) or migrations are updated, regenerate the DBML schema:

```bash
cd Backend
just dbml-generate
```

*What this does:*

- Introspects all Django models, columns, field constraints, defaults, and relations.
- Updates modular domain files under `domains/`.
- Updates `common/enums.dbml` with choice constants.
- Bundles everything into `schema.dbml`.
- Automatically rebuilds the standalone `index.html` viewer.

### 2. Validate DBML Syntax & Referential Integrity

Verify that all foreign keys resolve and that `@dbml/cli` parses the schema with 0 errors:

```bash
cd Backend
just dbml-validate
```

### 3. Export PostgreSQL DDL

Generate clean PostgreSQL SQL DDL:

```bash
cd Backend
just dbml-sql
```

### 4. Rebuild Interactive HTML Viewer Only

```bash
cd Backend
just dbml-html
```

---

## Importing into dbdiagram.io or dbdocs.io

You can copy the contents of [`schema.dbml`](./schema.dbml) directly into [dbdiagram.io](https://dbdiagram.io) for collaborative editing, or publish via `dbdocs`:

```bash
npx dbdocs build docs/db/db-diagram/schema.dbml
```

---

## Conventions & Rules

1. **Table Names**: Must exactly match Django `Meta.db_table`.
2. **Foreign Keys**: Documented explicitly using `Ref: table.col > target.id` (or `[ref: > target.id]`).
3. **Choice Sets**: Stored in `common/enums.dbml` and named using lowercase snake_case (e.g. `user_role`, `property_status`).
4. **Model Documentation**: Docstrings in Django models are automatically exported to DBML `Note: '...'`.
