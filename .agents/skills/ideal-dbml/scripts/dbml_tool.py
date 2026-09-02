#!/usr/bin/env python3
"""Inventory, generate, validate, and export DBML schema documentation for iDeal Backend.

Uses Django model introspection to extract models, tables, columns, constraints,
enums (ConstantChoices), indexes, and foreign-key/M2M relationships into modular DBML
files and a consolidated schema bundle.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[4]
DOCS_DIR = BACKEND / "docs" / "db" / "db-diagram"
DOMAINS_DIR = DOCS_DIR / "domains"
COMMON_DIR = DOCS_DIR / "common"
SCHEMA_PATH = DOCS_DIR / "schema.dbml"
ENUMS_PATH = COMMON_DIR / "enums.dbml"
GROUPS_PATH = COMMON_DIR / "groups.dbml"
SQL_PATH = DOCS_DIR / "schema.sql"

PYTHONPATHS = [str(BACKEND / "src"), str(BACKEND / "src" / "apps")]
for path in PYTHONPATHS:
    if path not in sys.path:
        sys.path.insert(0, path)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")


def setup_backend() -> None:
    import django

    django.setup()


# ---------------------------------------------------------------------------
# Helpers for Field & Enum Extraction
# ---------------------------------------------------------------------------


def sanitize_dbml_string(text: str) -> str:
    """Escape or clean string for DBML notes and comments."""
    if not text:
        return ""
    # Strip excessive newlines and escape single quotes
    cleaned = text.strip().replace("'", "\\'")
    return cleaned


def extract_enum_name_from_choices(choices: Any, field_name: str, model_name: str) -> str:
    """Derive a canonical snake_case enum name from choices."""
    if hasattr(choices, "__qualname__"):
        name = choices.__qualname__.split(".")[0]
        # Convert PascalCase to snake_case
        s1 = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", name)
        return re.sub("([a-z0-9])([A-Z])", r"\1_\2", s1).lower()
    return f"{model_name.lower()}_{field_name}_enum"


def format_enum_value(val: Any) -> str:
    """Format an enum value for DBML."""
    s = str(val)
    if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", s):
        return s
    return f'"{s}"'


def get_field_type_and_enum(
    field: Any, model_name: str, enums_registry: dict[str, dict[str, Any]]
) -> tuple[str, str | None]:
    """Map Django model field to DBML type and register choices enum if present."""
    # Check for choices enum
    if field.choices:
        choices_list = list(field.choices)
        if choices_list:
            # Check if this choice class has an identifiable name
            enum_name = None
            # Check constants.py or field declaration
            for attr in ("_choices_class", "choices_class", "enum"):
                cls = getattr(field, attr, None)
                if cls and hasattr(cls, "__name__"):
                    enum_name = extract_enum_name_from_choices(cls, field.name, model_name)
                    break

            if not enum_name:
                enum_name = f"{field.model._meta.db_table}_{field.name}"
                # Normalize common names
                if field.name in ("status", "currency", "priority", "kind", "method", "platform", "role"):
                    # Check if already in registry with same choices
                    existing_matching = None
                    for reg_name, reg_data in enums_registry.items():
                        if [c[0] for c in reg_data["choices"]] == [c[0] for c in choices_list]:
                            existing_matching = reg_name
                            break
                    enum_name = existing_matching or f"{field.model._meta.model_name}_{field.name}"

            if enum_name not in enums_registry:
                enums_registry[enum_name] = {
                    "name": enum_name,
                    "choices": [(str(val), str(label)) for val, label in choices_list],
                    "doc": getattr(field, "verbose_name", "") or "",
                }
            return enum_name, enum_name

    internal_type = field.get_internal_type()

    type_mapping = {
        "BigAutoField": "bigint",
        "AutoField": "bigint",
        "SmallAutoField": "smallint",
        "BigIntegerField": "bigint",
        "PositiveBigIntegerField": "bigint",
        "IntegerField": "integer",
        "PositiveIntegerField": "integer",
        "SmallIntegerField": "smallint",
        "PositiveSmallIntegerField": "smallint",
        "CharField": f"varchar({field.max_length})" if getattr(field, "max_length", None) else "varchar",
        "SlugField": f"varchar({field.max_length})" if getattr(field, "max_length", None) else "varchar",
        "EmailField": f"varchar({field.max_length or 254})",
        "URLField": f"varchar({field.max_length or 200})",
        "FilePathField": f"varchar({field.max_length or 255})",
        "TextField": "text",
        "BooleanField": "boolean",
        "NullBooleanField": "boolean",
        "DateTimeField": "timestamptz",
        "DateField": "date",
        "TimeField": "time",
        "DurationField": "interval",
        "DecimalField": f"decimal({field.max_digits}, {field.decimal_places})"
        if hasattr(field, "max_digits") and field.max_digits
        else "decimal",
        "FloatField": "float",
        "BinaryField": "bytea",
        "UUIDField": "uuid",
        "JSONField": "jsonb",
        "ImageField": "varchar(255)",
        "FileField": "varchar(255)",
    }

    if field.is_relation:
        target_model = field.remote_field.model
        target_pk = target_model._meta.pk
        if target_pk:
            target_type = target_pk.get_internal_type()
            return type_mapping.get(target_type, "bigint"), None
        return "bigint", None

    return type_mapping.get(internal_type, "varchar"), None


def format_default_value(field: Any) -> str | None:
    """Format default value for DBML setting."""
    if not field.has_default():
        return None
    default = field.default
    if callable(default):
        name = getattr(default, "__name__", "")
        if name in ("now", "timezone_now"):
            return "`now()`"
        if name == "uuid4":
            return "`gen_random_uuid()`"
        return None
    if isinstance(default, bool):
        return "true" if default else "false"
    if isinstance(default, (int, float)):
        return str(default)
    if isinstance(default, str):
        # Clean default string
        if not default:
            return "''"
        return f"'{default}'"
    return None


# ---------------------------------------------------------------------------
# Core Schema Introspection
# ---------------------------------------------------------------------------


def inspect_schema() -> dict[str, Any]:
    """Introspect all local Django apps and return structured schema data."""
    from django.apps import apps
    from django.conf import settings

    enums_registry: dict[str, dict[str, Any]] = {}
    apps_data: dict[str, dict[str, Any]] = {}
    all_tables: set[str] = set()
    relationships: list[dict[str, Any]] = []

    for app_name in settings.LOCAL_APPS:
        app_config = apps.get_app_config(app_name)
        models_list = list(app_config.get_models())
        if not models_list:
            continue

        tables_data = []
        for model in models_list:
            table_name = model._meta.db_table
            all_tables.add(table_name)
            model_doc = (model.__doc__ or "").strip()
            if model_doc.startswith(f"{model.__name__}(") or model_doc.startswith(f"{model.__name__} object"):
                model_doc = ""

            fields_data = []
            table_indexes = []

            for field in model._meta.fields:
                col_name = field.column
                col_type, enum_used = get_field_type_and_enum(field, model.__name__, enums_registry)

                settings_list = []
                if field.primary_key:
                    settings_list.append("pk")
                    if field.get_internal_type() in ("AutoField", "BigAutoField", "SmallAutoField"):
                        settings_list.append("increment")
                else:
                    if not field.null:
                        settings_list.append("not null")
                    if field.unique:
                        settings_list.append("unique")

                default_val = format_default_value(field)
                if default_val is not None:
                    settings_list.append(f"default: {default_val}")

                # Inline relationship
                ref_info = None
                if field.is_relation and hasattr(field, "remote_field") and field.remote_field:
                    target_model = field.remote_field.model
                    if hasattr(target_model, "_meta"):
                        target_table = target_model._meta.db_table
                        target_col = target_model._meta.pk.column if target_model._meta.pk else "id"
                        is_one_to_one = field.one_to_one
                        rel_op = "-" if is_one_to_one else ">"
                        ref_info = {
                            "source_table": table_name,
                            "source_col": col_name,
                            "target_table": target_table,
                            "target_col": target_col,
                            "op": rel_op,
                            "type": "one_to_one" if is_one_to_one else "many_to_one",
                        }
                        relationships.append(ref_info)
                        settings_list.append(f"ref: {rel_op} {target_table}.{target_col}")

                # Column note
                note_parts = []
                help_text = str(field.help_text).strip() if field.help_text else ""
                verbose_name = str(field.verbose_name).strip() if field.verbose_name else ""
                if help_text:
                    note_parts.append(help_text)
                elif verbose_name and verbose_name.lower() != field.name.replace("_", " ").lower():
                    note_parts.append(verbose_name)

                if note_parts:
                    note_str = sanitize_dbml_string(" - ".join(note_parts))
                    if note_str:
                        settings_list.append(f"note: '{note_str}'")

                if field.db_index and not field.primary_key and not field.unique:
                    table_indexes.append({"columns": [col_name], "unique": False, "name": None})

                fields_data.append(
                    {
                        "name": col_name,
                        "field_name": field.name,
                        "type": col_type,
                        "enum": enum_used,
                        "settings": settings_list,
                        "is_pk": field.primary_key,
                        "is_fk": field.is_relation,
                        "ref": ref_info,
                        "null": field.null,
                        "unique": field.unique,
                        "note": " - ".join(note_parts) if note_parts else "",
                    }
                )

            # Meta unique_together & indexes
            for ut in model._meta.unique_together:
                cols = [model._meta.get_field(f).column for f in ut]
                table_indexes.append({"columns": cols, "unique": True, "name": None})

            for idx in model._meta.indexes:
                cols = []
                for f in idx.fields:
                    clean_f = f.lstrip("-")
                    try:
                        cols.append(model._meta.get_field(clean_f).column)
                    except Exception:
                        cols.append(clean_f)
                if cols:
                    table_indexes.append({"columns": cols, "unique": False, "name": idx.name})

            # M2M relations & through tables
            m2m_data = []
            for m2m in model._meta.many_to_many:
                through_model = m2m.remote_field.through
                target_model = m2m.remote_field.model
                m2m_data.append(
                    {
                        "name": m2m.name,
                        "target_table": target_model._meta.db_table,
                        "through_table": through_model._meta.db_table,
                        "auto_created": bool(through_model._meta.auto_created),
                    }
                )

            tables_data.append(
                {
                    "model_name": model.__name__,
                    "table_name": table_name,
                    "app": app_name,
                    "doc": model_doc,
                    "fields": fields_data,
                    "indexes": table_indexes,
                    "m2m": m2m_data,
                }
            )

        apps_data[app_name] = {
            "app_name": app_name,
            "verbose_name": app_config.verbose_name or app_name.capitalize(),
            "tables": tables_data,
        }

    return {
        "apps": apps_data,
        "enums": enums_registry,
        "relationships": relationships,
        "all_tables": sorted(all_tables),
    }


# ---------------------------------------------------------------------------
# DBML Code Generators
# ---------------------------------------------------------------------------


def render_enum_dbml(enum_data: dict[str, Any]) -> str:
    """Render a single DBML Enum definition."""
    lines = [f"Enum {enum_data['name']} {{"]
    for val, label in enum_data["choices"]:
        formatted_val = format_enum_value(val)
        label_clean = sanitize_dbml_string(label)
        if label_clean and label_clean.lower() != str(val).lower():
            lines.append(f"  {formatted_val} [note: '{label_clean}']")
        else:
            lines.append(f"  {formatted_val}")
    lines.append("}\n")
    return "\n".join(lines)


def render_table_dbml(table: dict[str, Any]) -> str:
    """Render a single DBML Table definition."""
    lines = [f"Table {table['table_name']} {{"]

    # Compute column spacing for tidy alignment
    max_col_len = max((len(f["name"]) for f in table["fields"]), default=10)
    max_type_len = max((len(f["type"]) for f in table["fields"]), default=10)

    for f in table["fields"]:
        col_str = f["name"].ljust(max_col_len)
        type_str = f["type"].ljust(max_type_len)
        settings_str = f" [{', '.join(f['settings'])}]" if f["settings"] else ""
        lines.append(f"  {col_str} {type_str}{settings_str}")

    # Indexes block
    if table["indexes"]:
        lines.append("\n  indexes {")
        for idx in table["indexes"]:
            cols = idx["columns"]
            cols_str = f"({', '.join(cols)})" if len(cols) > 1 else cols[0]
            opts = []
            if idx["unique"]:
                opts.append("unique")
            if idx.get("name"):
                opts.append(f"name: '{idx['name']}'")
            opts_str = f" [{', '.join(opts)}]" if opts else ""
            lines.append(f"    {cols_str}{opts_str}")
        lines.append("  }")

    # Table Note
    if table["doc"]:
        clean_doc = sanitize_dbml_string(table["doc"])
        if "\n" in clean_doc:
            lines.append(f"\n  Note: '''\n  {clean_doc}\n  '''")
        else:
            lines.append(f"\n  Note: '{clean_doc}'")

    lines.append("}\n")
    return "\n".join(lines)


def render_m2m_through_tables(tables: list[dict[str, Any]]) -> str:
    """Render auto-created junction tables for M2M relationships."""
    rendered_throughs = set()
    blocks = []

    for table in tables:
        for m2m in table["m2m"]:
            if m2m["auto_created"] and m2m["through_table"] not in rendered_throughs:
                rendered_throughs.add(m2m["through_table"])
                source_table = table["table_name"]
                target_table = m2m["target_table"]
                through_name = m2m["through_table"]

                # Extract foreign key column names based on Django standard naming
                source_col = f"{table['model_name'].lower()}_id"
                # Target column
                target_col = f"{target_table.rstrip('s')}_id"
                if target_table == "amenities":
                    target_col = "amenity_id"

                block = f"""Table {through_name} {{
  id bigint [pk, increment]
  {source_col} bigint [not null, ref: > {source_table}.id]
  {target_col} bigint [not null, ref: > {target_table}.id]

  indexes {{
    ({source_col}, {target_col}) [unique]
  }}

  Note: 'Auto-created junction table for {source_table}.{m2m["name"]} -> {target_table}'
}}
"""
                blocks.append(block)

    return "\n".join(blocks)


def render_groups_dbml(apps_data: dict[str, dict[str, Any]]) -> str:
    """Render TableGroup definitions for visual grouping on diagram canvas."""
    blocks = []
    for app_info in sorted(apps_data.values(), key=lambda a: a["app_name"]):
        tables = [t["table_name"] for t in app_info["tables"]]
        # Add M2M through tables
        for t in app_info["tables"]:
            for m2m in t["m2m"]:
                if m2m["auto_created"] and m2m["through_table"] not in tables:
                    tables.append(m2m["through_table"])
        if not tables:
            continue
        group_name = app_info["verbose_name"].replace(" ", "_")
        lines = [f"TableGroup {group_name} {{"]
        for tbl in sorted(tables):
            lines.append(f"  {tbl}")
        lines.append("}\n")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def command_inventory() -> None:
    """Print schema inventory summary."""
    setup_backend()
    schema = inspect_schema()

    total_tables = sum(len(a["tables"]) for a in schema["apps"].values())
    total_fields = sum(sum(len(t["fields"]) for t in a["tables"]) for a in schema["apps"].values())
    total_enums = len(schema["enums"])
    total_refs = len(schema["relationships"])

    print(f"\n{'=' * 70}")
    print(" iDeal Backend DBML Schema Inventory")
    print(f"{'=' * 70}")
    print(f"Total Apps:          {len(schema['apps']):>5}")
    print(f"Total Tables:        {total_tables:>5}")
    print(f"Total Columns:       {total_fields:>5}")
    print(f"Total Foreign Keys:  {total_refs:>5}")
    print(f"Total Shared Enums:  {total_enums:>5}")
    print(f"{'-' * 70}")
    print(f"{'App':<18} | {'Tables':<8} | {'Columns':<8} | {'Table Names'}")
    print(f"{'-' * 70}")

    for app_name, app_info in sorted(schema["apps"].items()):
        t_count = len(app_info["tables"])
        f_count = sum(len(t["fields"]) for t in app_info["tables"])
        table_names = ", ".join(t["table_name"] for t in app_info["tables"])
        print(f"{app_name:<18} | {t_count:<8} | {f_count:<8} | {table_names}")

    print(f"{'=' * 70}\n")


def command_generate(check: bool = False) -> None:
    """Generate modular DBML files, enums, groups, master schema, and HTML viewer."""
    setup_backend()
    schema = inspect_schema()

    # Ensure directories exist
    DOMAINS_DIR.mkdir(parents=True, exist_ok=True)
    COMMON_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Generate common/enums.dbml
    enum_content_parts = [
        "// iDeal Database Enums (Auto-generated from Django Model Choices & Constants)\n",
    ]
    for enum_data in sorted(schema["enums"].values(), key=lambda e: e["name"]):
        enum_content_parts.append(render_enum_dbml(enum_data))
    enums_dbml = "\n".join(enum_content_parts)

    # 2. Generate common/groups.dbml
    groups_dbml = "// iDeal Table Groups (Canvas organization by Django application domain)\n\n" + render_groups_dbml(
        schema["apps"]
    )

    # 3. Generate domains/<app>.dbml
    domain_files_content: dict[str, str] = {}
    for app_name, app_info in schema["apps"].items():
        parts = [
            f"// iDeal DBML Domain: {app_name.capitalize()} (app: {app_name})\n",
        ]
        for table in app_info["tables"]:
            parts.append(render_table_dbml(table))

        m2m_through = render_m2m_through_tables(app_info["tables"])
        if m2m_through:
            parts.append("// Junction Tables\n" + m2m_through)

        domain_files_content[app_name] = "\n".join(parts)

    # 4. Generate master schema.dbml
    master_parts = [
        "// ===========================================================================",
        "// iDeal Backend - Consolidated Database Schema (DBML)",
        "// Auto-generated by .agents/skills/ideal-dbml/scripts/dbml_tool.py",
        "// Tooling & Validator: https://dbml.dbdiagram.io/cli/",
        "// ===========================================================================\n",
        "// ---------------------------------------------------------------------------",
        "// SHARED ENUMS & CONSTANTS",
        "// ---------------------------------------------------------------------------\n",
        enums_dbml.strip(),
        "\n// ---------------------------------------------------------------------------",
        "// DOMAIN TABLES",
        "// ---------------------------------------------------------------------------\n",
    ]

    for app_name in sorted(domain_files_content.keys()):
        master_parts.append(domain_files_content[app_name].strip())
        master_parts.append("")

    master_parts.append("// ---------------------------------------------------------------------------")
    master_parts.append("// TABLE GROUPS")
    master_parts.append("// ---------------------------------------------------------------------------\n")
    master_parts.append(groups_dbml.strip())
    master_parts.append("")

    master_dbml = "\n".join(master_parts)

    if check:
        # Check for drift
        drift = False
        if not SCHEMA_PATH.exists() or SCHEMA_PATH.read_text(encoding="utf-8") != master_dbml:
            print(f"Drift detected in {SCHEMA_PATH}")
            drift = True
        if not ENUMS_PATH.exists() or ENUMS_PATH.read_text(encoding="utf-8") != enums_dbml:
            print(f"Drift detected in {ENUMS_PATH}")
            drift = True
        if drift:
            sys.exit(1)
        print("Schema is up to date (no drift).")
        return

    # Write files
    ENUMS_PATH.write_text(enums_dbml, encoding="utf-8")
    GROUPS_PATH.write_text(groups_dbml, encoding="utf-8")

    for app_name, content in domain_files_content.items():
        domain_file = DOMAINS_DIR / f"{app_name}.dbml"
        domain_file.write_text(content, encoding="utf-8")

    SCHEMA_PATH.write_text(master_dbml, encoding="utf-8")
    print(f"Generated {len(domain_files_content)} domain files in {DOMAINS_DIR}")
    print(f"Generated {ENUMS_PATH}")
    print(f"Generated {GROUPS_PATH}")
    print(f"Generated consolidated {SCHEMA_PATH}")

    # Rebuild HTML documentation
    command_build_html()


def command_validate() -> None:
    """Validate referential integrity and DBML syntax via @dbml/cli."""
    setup_backend()
    schema = inspect_schema()

    print("Running Python referential integrity check...")
    errors = []
    all_tables = set(schema["all_tables"])

    # Include junction tables
    for app_info in schema["apps"].values():
        for t in app_info["tables"]:
            for m2m in t["m2m"]:
                if m2m["auto_created"]:
                    all_tables.add(m2m["through_table"])

    # Check foreign keys
    for rel in schema["relationships"]:
        if rel["target_table"] not in all_tables:
            errors.append(
                f"Foreign key in {rel['source_table']}.{rel['source_col']} points to nonexistent table '{rel['target_table']}'"
            )

    if errors:
        print("\nReferential integrity errors:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    print("Referential integrity check passed (all foreign keys resolve to existing tables).")

    # Run DBML CLI validation if npx is available
    if not SCHEMA_PATH.exists():
        print(f"Schema file not found at {SCHEMA_PATH}. Generating first...")
        command_generate()

    print("\nRunning @dbml/cli validation (npx -p @dbml/cli dbml2sql --postgres)...")
    try:
        proc = subprocess.run(
            ["npx", "--yes", "-p", "@dbml/cli", "dbml2sql", "--postgres", str(SCHEMA_PATH)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            print(f"DBML validation failed with code {proc.returncode}:\n{proc.stderr}")
            sys.exit(proc.returncode)
        print("DBML CLI syntax and structure validation passed successfully!")
    except FileNotFoundError:
        print("Note: npx not found in PATH; skipping @dbml/cli execution.")
    finally:
        # Clean up any error log left by dbml cli if created
        err_log = Path.cwd() / "dbml-error.log"
        if err_log.exists():
            err_log.unlink()


def command_export_sql(out_path: Path | None = None) -> None:
    """Export PostgreSQL DDL from schema.dbml using @dbml/cli."""
    if not SCHEMA_PATH.exists():
        command_generate()

    destination = out_path or SQL_PATH
    print(f"Exporting PostgreSQL DDL to {destination}...")
    proc = subprocess.run(
        ["npx", "--yes", "-p", "@dbml/cli", "dbml2sql", "--postgres", str(SCHEMA_PATH), "-o", str(destination)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(f"Failed to export SQL:\n{proc.stderr}")
        sys.exit(proc.returncode)
    print(f"Exported PostgreSQL DDL to {destination}")


def command_build_html() -> None:
    """Build standalone interactive HTML documentation."""
    from build_web_docs import build_html_docs

    output_path = DOCS_DIR / "index.html"
    build_html_docs(SCHEMA_PATH, output_path)
    print(f"Built interactive HTML viewer at {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="iDeal DBML Schema Tool")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # inventory
    subparsers.add_parser("inventory", help="Display schema statistics and table inventory")

    # generate
    gen_parser = subparsers.add_parser("generate", help="Generate DBML files from Django models")
    gen_parser.add_argument("--check", action="store_true", help="Check for drift without writing files")

    # validate
    subparsers.add_parser("validate", help="Validate DBML syntax and referential integrity")

    # export-sql
    sql_parser = subparsers.add_parser("export-sql", help="Export PostgreSQL DDL from DBML")
    sql_parser.add_argument("-o", "--output", type=Path, default=None, help="Output SQL file path")

    # build-html
    subparsers.add_parser("build-html", help="Build interactive HTML documentation viewer")

    args = parser.parse_args()

    if args.subcommand == "inventory":
        command_inventory()
    elif args.subcommand == "generate":
        command_generate(check=args.check)
    elif args.subcommand == "validate":
        command_validate()
    elif args.subcommand == "export-sql":
        command_export_sql(out_path=args.output)
    elif args.subcommand == "build-html":
        command_build_html()


if __name__ == "__main__":
    main()
