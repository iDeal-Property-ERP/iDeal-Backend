#!/usr/bin/env python3
"""Inventory, generate, and validate the iDeal Bruno API collection.

The resolver is authoritative for mounted routes and application methods. DMR
OpenAPI supplies operation parameters, request schemas, response statuses, and
security metadata where available. Payment webhooks are mounted beside the
DMR router and are added explicitly.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, cast

import yaml

BACKEND = Path(__file__).resolve().parents[4]
COLLECTION = Path(__file__).resolve().parents[4] / "docs" / "api" / "bruno"
PYTHONPATHS = [str(BACKEND / "src"), str(BACKEND / "src" / "apps")]
for path in PYTHONPATHS:
    if path not in sys.path:
        sys.path.insert(0, path)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")


def setup_backend() -> None:
    import django

    django.setup()


def route_text(route: Any) -> str:
    return str(getattr(route, "pattern", route)).lstrip("^").rstrip("$")


def resolver_routes() -> list[dict[str, Any]]:
    from django.urls import URLPattern, URLResolver, get_resolver

    result: list[dict[str, Any]] = []

    def walk(patterns: list[Any], prefix: str = "") -> None:
        for item in patterns:
            if isinstance(item, URLResolver):
                walk(cast(list[Any], getattr(item, "url_patterns", [])), prefix + route_text(item.pattern))
                continue
            if not isinstance(item, URLPattern):
                continue
            path = (prefix + route_text(item.pattern)).lstrip("/")
            if not path.startswith("api/v1/"):
                continue
            callback = item.callback
            # http_method_names is Django's allow-list and would incorrectly
            # make every route appear to support every verb. Walk the view
            # class MRO instead: this includes inherited application handlers
            # (for example a detail controller's inherited GET/PATCH) while
            # excluding framework transport methods such as OPTIONS/HEAD.
            view_class = getattr(callback, "view_class", None)
            methods: list[str] = []
            cursor = view_class
            while cursor and cursor is not object:
                for name in ("get", "post", "put", "patch", "delete"):
                    if name in cursor.__dict__ and name not in methods:
                        methods.append(name)
                cursor = cursor.__base__
            methods = [m.upper() for m in methods]
            if not methods:
                continue
            result.append({"path": "/" + path, "methods": sorted(set(methods)), "name": item.name or ""})

    walk(cast(list[Any], getattr(get_resolver(), "url_patterns", [])))
    return result


def webhook_routes() -> list[dict[str, Any]]:
    return [
        {"path": "/api/v1/payment-webhooks/payme/", "methods": ["POST"], "name": "payme-callback"},
        {"path": "/api/v1/payment-webhooks/click/prepare/", "methods": ["POST"], "name": "click-prepare"},
        {"path": "/api/v1/payment-webhooks/click/complete/", "methods": ["POST"], "name": "click-complete"},
        {"path": "/api/v1/payment-webhooks/stripe/", "methods": ["POST"], "name": "stripe-webhook"},
    ]


def openapi_schema() -> dict[str, Any]:
    from dmr.openapi import build_schema
    from dmr.routing import Router

    from api.url_router import urlpatterns

    return build_schema(Router("api/", urlpatterns)).convert(skip_validation=True)


def normalized(path: str) -> str:
    return re.sub(r"<[^:>]+:([^>]+)>", r"{\1}", path) or "/"


def path_params(path: str) -> list[str]:
    return re.findall(r"<[^:>]+:([^>]+)>", path)


def ref_name(schema: dict[str, Any] | None) -> str | None:
    if not schema:
        return None
    ref = schema.get("$ref", "")
    return ref.rsplit("/", 1)[-1] if ref else None


def operation_for(schema: dict[str, Any], path: str, method: str) -> dict[str, Any]:
    return schema.get("paths", {}).get(normalized(path), {}).get(method.lower(), {})


def schema_for_request(operation: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None, str]:
    request = operation.get("requestBody", {}) or {}
    content = request.get("content", {}) or {}
    for content_type in (
        "application/json",
        "application/*+json",
        "multipart/form-data",
        "application/x-www-form-urlencoded",
    ):
        entry = content.get(content_type)
        if entry:
            schema = entry.get("schema") or {}
            return schema, ref_name(schema), content_type
    if content:
        content_type, entry = next(iter(content.items()))
        schema = entry.get("schema") or {}
        return schema, ref_name(schema), content_type
    return None, None, ""


def sample_scalar(schema: dict[str, Any], field: str = "") -> Any:
    if "default" in schema:
        return schema["default"]
    if schema.get("nullable"):
        return None
    if schema.get("enum"):
        return schema["enum"][0]
    typ = schema.get("type")
    fmt = schema.get("format", "")
    lower = field.lower()
    known_values = {
        "property_type": "apartment",
        "furnishing": "unfurnished",
        "tariff": "standard",
        "engagement_type": "managed",
        "currency": "USD",
        "ask_currency": "USD",
    }
    if lower in known_values:
        return known_values[lower]
    if lower in {"price_includes", "price_included"}:
        return ["utilities"]
    if fmt == "date-time" or "date" in lower and "update" not in lower:
        return "2026-01-01T00:00:00Z"
    if fmt == "date":
        return "2026-01-01"
    if fmt == "email" or "email" in lower:
        return "fixture@example.com"
    if "phone" in lower:
        return "+998901234567"
    if "uuid" in lower:
        return "00000000-0000-0000-0000-000000000001"
    if lower.endswith("_id") or lower in {"id", "pk"}:
        return 1
    if typ in {"integer", "number"}:
        return 1
    if typ == "boolean":
        return True
    if typ == "array":
        return [sample_value(schema.get("items", {}), field)]
    if typ == "object" or not typ:
        return sample_object(schema)
    return "fixture-value"


def sample_value(schema: dict[str, Any], field: str = "") -> Any:
    if not schema:
        return "fixture-value"
    if "oneOf" in schema:
        return sample_value(schema["oneOf"][0], field)
    if "anyOf" in schema:
        return sample_value(schema["anyOf"][0], field)
    return sample_scalar(schema, field)


def deref(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    ref = schema.get("$ref", "") if schema else ""
    if ref.startswith("#/components/schemas/") or ref.startswith("#/$defs/"):
        return components.get(ref.rsplit("/", 1)[-1], {})
    return schema or {}


def pydantic_schema(model: Any) -> dict[str, Any]:
    schema = model.model_json_schema()
    return schema


def manual_request_schema(path: str, method: str) -> dict[str, Any] | None:
    """Schemas for handlers whose Body[dict] or raw transport hides the model."""
    if path == "/api/v1/owner/listings/" and method == "POST":
        from api.v1.owner.schemas import OwnerListingCreateInput

        return pydantic_schema(OwnerListingCreateInput)
    if path == "/api/v1/owner/listings/<int:pk>/" and method == "PATCH":
        from api.v1.owner.schemas import OwnerListingUpdateInput

        return pydantic_schema(OwnerListingUpdateInput)
    if path == "/api/v1/marketplace/listings/submit/" and method == "POST":
        from api.v1.marketplace.schemas import PublicListingSubmitInput

        return pydantic_schema(PublicListingSubmitInput)
    if path == "/api/v1/chat/conversations/<int:pk>/read/" and method == "POST":
        from api.v1.chat.schemas import ChatReadInput

        return pydantic_schema(ChatReadInput)
    if path == "/api/v1/mobile/chat/conversations/<int:pk>/read/" and method == "POST":
        from api.v1.mobile.chat.schemas import MarkReadInput

        return pydantic_schema(MarkReadInput)
    return None


def sample_object(schema: dict[str, Any], components: dict[str, Any] | None = None) -> dict[str, Any]:
    components = components or {}
    schema = deref(schema, components)
    properties = schema.get("properties", {}) or {}
    return {name: sample_value(deref(value, components), name) for name, value in properties.items()}


def operation_record(route: dict[str, Any], method: str, schema: dict[str, Any]) -> dict[str, Any]:
    operation = operation_for(schema, route["path"], method)
    request_schema, request_ref, content_type = schema_for_request(operation)
    components = schema.get("components", {}).get("schemas", {})
    manual = manual_request_schema(route["path"], method)
    if manual is not None:
        request_schema = manual
        request_ref = None
        content_type = "application/json"
        components = {**components, **manual.get("$defs", {})}
    resolved_request = deref(request_schema or {}, components)
    params: list[dict[str, Any]] = []
    for name in path_params(route["path"]):
        params.append({"name": name, "in": "path", "required": True, "schema": {"type": "integer"}, "example": "1"})
    for param in operation.get("parameters", []) or []:
        if param.get("in") == "query":
            p = dict(param)
            p["schema"] = deref(p.get("schema") or {}, components)
            params.append(p)
    responses: list[int] = []
    for code in operation.get("responses", {}) or {}:
        try:
            responses.append(int(code))
        except ValueError, TypeError:
            continue
    responses = sorted(set(responses))
    if not responses:
        responses = [200]
    auth = "bearer" if operation.get("security") else "none"
    if route["path"].startswith("/api/v1/payment-webhooks/"):
        request_schema, request_ref, content_type = ({"type": "object"}, None, "application/json")
        resolved_request = {"type": "object", "properties": {}}
        auth = "none"
        responses = [200, 400]
    return {
        "path": route["path"],
        "method": method,
        "name": route.get("name", ""),
        "operation": operation,
        "params": params,
        "request_schema": request_schema,
        "request_ref": request_ref,
        "resolved_request": resolved_request,
        "content_type": content_type,
        "responses": responses,
        "auth": auth,
        "components": components,
    }


def inventory() -> dict[str, Any]:
    setup_backend()
    schema = openapi_schema()
    routes_by_path: dict[str, dict[str, Any]] = {}
    for route in resolver_routes() + webhook_routes():
        if route["path"] in routes_by_path:
            routes_by_path[route["path"]]["methods"] = sorted(
                set(routes_by_path[route["path"]]["methods"]) | set(route["methods"])
            )
        else:
            routes_by_path[route["path"]] = dict(route)
    records = [
        operation_record(route, method, schema) for route in routes_by_path.values() for method in route["methods"]
    ]
    return {
        "routes": sorted(routes_by_path.values(), key=lambda x: x["path"]),
        "operations": records,
        "counts": {
            "routes": len(routes_by_path),
            "application_methods": len(records),
            "methods": dict(Counter(r["method"] for r in records)),
        },
    }


def safe_name(path: str, method: str) -> str:
    bits = [method.lower()] + [b for b in path.strip("/").split("/") if b]
    return re.sub(r"[^a-zA-Z0-9_-]+", "-", "-".join(bits)).lower()


def humanize(segment: str) -> str:
    segment = re.sub(r"<[^:>]+:([^>]+)>", r"\1", segment).replace("_", " ").replace("-", " ")
    words = segment.split()
    return " ".join(word if word.isupper() else word.lower() for word in words)


def singular(segment: str) -> str:
    value = humanize(segment)
    irregular = {"leases": "lease", "statuses": "status", "processes": "process", "addresses": "address"}
    if value in irregular:
        return irregular[value]
    if value.endswith("ies"):
        return value[:-3] + "y"
    if value.endswith("ses"):
        return value[:-2]
    if value.endswith("s") and not value.endswith(("ss", "us")):
        return value[:-1]
    return value


def human_request_name(record: dict[str, Any]) -> str:
    """Create a concise display name without method/path noise."""
    special_names = {
        "/api/v1/auth/login/": "Login",
        "/api/v1/auth/logout/": "Logout",
        "/api/v1/auth/refresh/": "Refresh token",
        "/api/v1/auth/set-password/": "Set password",
        "/api/v1/auth/verify/": "Verify token",
        "/api/v1/mobile/account/me/": "Get my profile",
    }
    if record["path"] in special_names:
        return special_names[record["path"]]
    if record["path"].startswith("/api/v1/payment-webhooks/"):
        provider = record["path"].rstrip("/").split("/")[-1].replace("-", " ").title()
        return f"Handle {provider} webhook"
    path = record["path"].strip("/").split("/")[2:]
    path = [part for part in path if part]
    dynamic_index = next((index for index, part in enumerate(path) if part.startswith("<")), None)
    action_words = {
        "activate",
        "archive",
        "approve",
        "block",
        "cancel",
        "close-lost",
        "close-won",
        "complete",
        "confirm",
        "deactivate",
        "finalize",
        "hold",
        "mark-paid",
        "pause",
        "publish",
        "read",
        "reject",
        "release",
        "read-all",
        "remind",
        "renew",
        "resolve",
        "submit",
        "terminate",
        "unarchive",
        "unblock",
        "unmute",
        "verify",
        "mute",
    }
    action = path[-1] if path and path[-1] in action_words else None
    if action:
        resource_index = dynamic_index - 1 if dynamic_index is not None else len(path) - 2
        resource = singular(path[resource_index]) if resource_index >= 0 else "request"
        result = f"{humanize(action)} {resource}"
        return result[:1].upper() + result[1:]
    if dynamic_index is not None and dynamic_index + 1 < len(path):
        resource = singular(path[dynamic_index - 1]) if dynamic_index else "resource"
        subresource = path[dynamic_index + 1]
        verb = {"GET": "List", "POST": "Create", "PUT": "Update", "PATCH": "Update", "DELETE": "Delete"}.get(
            record["method"], record["method"].title()
        )
        object_name = humanize(subresource) if record["method"] == "GET" else singular(subresource)
        return f"{verb} {resource} {object_name}"
    if path and path[-1] in {"avatar", "photos", "image", "attachments", "messages"}:
        resource = singular(path[-1])
        if resource == "message":
            return "List messages"
        verb = {"avatar": "Update", "photo": "Add", "image": "Send", "attachment": "Add", "message": "List"}.get(
            resource, "Manage"
        )
        return f"{verb} {resource}"
    if dynamic_index is not None:
        resource = singular(path[dynamic_index - 1]) if dynamic_index else "resource"
        verb = {"GET": "Get", "POST": "Create", "PUT": "Update", "PATCH": "Update", "DELETE": "Delete"}.get(
            record["method"], record["method"].title()
        )
        return f"{verb} {resource}"
    resource = path[-1] if path else "request"
    if record["method"] == "GET":
        return f"List {humanize(resource)}"
    verb = {"POST": "Create", "PUT": "Update", "PATCH": "Update", "DELETE": "Delete", "GET": "Get"}.get(
        record["method"], record["method"].title()
    )
    return f"{verb} {singular(resource)}"


def domain(path: str) -> str:
    bits = [b for b in path.strip("/").split("/") if b]
    if len(bits) >= 2 and bits[0] == "api" and bits[1] == "v1":
        bits = bits[2:]
    if not bits:
        return "misc"

    section = bits[0]
    sub = bits[1] if len(bits) > 1 else ""

    if section == "mobile":
        return f"mobile/{sub}" if sub else "mobile"

    if section == "payment-webhooks":
        provider = sub or "general"
        return f"payment/webhook/{provider}"

    if section == "management":
        if sub in {"dashboard", "queue-counts", "vacancy", "assignees"}:
            return "management/overview"
        if sub in {"inquiries", "leads"}:
            return "management/leads"
        if sub in {"bookings"}:
            return "management/bookings"
        if sub in {"onboardings"}:
            return "management/onboardings"
        if sub in {"one-off-deals", "brokerage-commissions"}:
            return "management/one-off-deals"
        if sub in {"properties"}:
            return "management/properties"
        if sub in {"leases", "owner-agreements"}:
            return "management/contracts"
        if sub in {"payments", "payouts", "pnl", "settlements"}:
            return "management/finance"
        if sub in {"service-requests"}:
            return "management/service-requests"
        if sub in {"users"}:
            return "management/users"
        if sub in {"vas-orders", "vas-partners"}:
            return "management/vas"
        if sub in {"viewing-requests"}:
            return "management/viewing-requests"
        return f"management/{sub}" if sub else "management"

    if section == "finance":
        if sub in {"dashboard", "exchange-rates"}:
            return "finance/overview"
        if sub in {"payments", "payouts", "settlements", "pnl"}:
            return f"finance/{sub}"
        return f"finance/{sub}" if sub else "finance"

    if section == "contracts":
        if sub in {"leases", "owner-agreements"}:
            return f"contracts/{sub}"
        return f"contracts/{sub}" if sub else "contracts"

    if section == "owner":
        if sub in {"listings", "properties"}:
            return f"owner/{sub}"
        if sub in {"earnings", "settlements"}:
            return "owner/finance"
        if sub in {"onboarding", "public-offer", "why"}:
            return "owner/onboarding"
        return f"owner/{sub}" if sub else "owner"

    if section == "tenant":
        if sub:
            return f"tenant/{sub}"
        return "tenant"

    if section == "chat":
        if sub in {"conversations", "reports"}:
            return f"chat/{sub}"
        return "chat"

    if section == "marketplace":
        if sub in {"amenities", "districts", "faqs"}:
            return "marketplace/reference"
        if sub in {"listings", "inquiries"}:
            return f"marketplace/{sub}"
        return f"marketplace/{sub}" if sub else "marketplace"

    return section


def body_for(record: dict[str, Any]) -> Any:
    schema = record["resolved_request"]
    path = record["path"]
    if path == "/api/v1/payment-webhooks/payme/":
        return {
            "jsonrpc": "2.0",
            "id": "fixture-request-id",
            "method": "CheckPerformTransaction",
            "params": {"amount": 100000, "account": {"checkout": "{{checkout_public_token}}"}},
        }
    if path.startswith("/api/v1/payment-webhooks/click/"):
        return {
            "click_trans_id": "{{click_transaction_id}}",
            "service_id": "{{click_service_id}}",
            "merchant_trans_id": "{{checkout_public_token}}",
            "amount": "100000",
            "action": "1" if path.endswith("/prepare/") else "2",
            "sign_time": "2026-01-01 00:00:00",
            "sign_string": "{{click_signature}}",
        }
    if path == "/api/v1/payment-webhooks/stripe/":
        return {
            "id": "evt_fixture",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "{{stripe_session_id}}",
                    "client_reference_id": "{{checkout_public_token}}",
                    "amount_total": 100000,
                    "currency": "usd",
                    "metadata": {"public_token": "{{checkout_public_token}}"},
                }
            },
        }
    if not schema.get("properties"):
        return None
    return (
        sample_object(schema, record["components"]) if schema.get("type") in {"object", None} else sample_value(schema)
    )


def multipart_fields(record: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Return Bruno multipart data for handlers that read request.FILES."""
    path = record["path"]
    if path == "/api/v1/mobile/account/me/avatar/":
        return [{"name": "image", "type": "file", "path": "{{sample_image}}"}]
    if path.endswith("/messages/image/"):
        return [
            {"name": "image", "type": "file", "path": "{{sample_image}}"},
            {"name": "client_id", "type": "text", "value": "fixture-client-id"},
        ]
    if path.endswith("/photos/"):
        fields = [{"name": "images[]", "type": "file", "path": "{{sample_image}}"}]
        if "/inventory/acts/" in path:
            fields.append({"name": "item_id", "type": "text", "value": "1"})
        return fields
    if path == "/api/v1/management/properties/import/":
        return [{"name": "file", "type": "file", "path": "{{sample_csv}}"}]
    if path == "/api/v1/marketplace/listings/submit/":
        return [
            {"name": "payload", "type": "text", "value": json.dumps(body_for(record))},
            {"name": "images[]", "type": "file", "path": "{{sample_image}}"},
        ]
    if path.endswith("/receipt/attachments/"):
        return [{"name": "files[]", "type": "file", "path": "{{sample_image}}"}]
    return None


def form_fields(record: dict[str, Any]) -> list[dict[str, Any]] | None:
    if record["path"].startswith("/api/v1/payment-webhooks/click/"):
        return [{"name": key, "type": "text", "value": str(value)} for key, value in body_for(record).items()]
    return None


def nullable(schema: dict[str, Any]) -> bool:
    return bool(schema.get("nullable") or any(item.get("type") == "null" for item in schema.get("anyOf", [])))


def documented_fields(
    schema: dict[str, Any], components: dict[str, Any], prefix: str = ""
) -> list[tuple[str, bool, bool, str]]:
    schema = deref(schema, components)
    required = set(schema.get("required", []))
    rows: list[tuple[str, bool, bool, str]] = []
    for name, raw_field in (schema.get("properties", {}) or {}).items():
        field = deref(raw_field, components)
        field_name = f"{prefix}.{name}" if prefix else name
        constraints: list[str] = []
        if "default" in field:
            constraints.append(f"default={field['default']!r}")
        if field.get("enum"):
            constraints.append("enum=" + ", ".join(map(str, field["enum"])))
        if field.get("minimum") is not None:
            constraints.append(f"min={field['minimum']}")
        if field.get("maximum") is not None:
            constraints.append(f"max={field['maximum']}")
        rows.append((field_name, name in required, nullable(field), "; ".join(constraints) or "fixture value"))
        nested = field
        if nested.get("type") == "array":
            nested = deref(nested.get("items", {}), components)
        if nested.get("properties"):
            rows.extend(
                documented_fields(nested, components, field_name + ("[]" if field.get("type") == "array" else ""))
            )
    return rows


def docs_for(record: dict[str, Any]) -> str:
    lines = [
        f"# {record['method']} {record['path']}",
        "",
        f"Authentication: **{record['auth']}**.",
        "",
        "## Request field notes",
        "",
    ]
    if record["params"]:
        lines += ["| Field | Location | Required | Example | Notes |", "|---|---|---:|---|---|"]
        for p in record["params"]:
            schema = p.get("schema", {})
            nullable = "nullable" if schema.get("nullable") else "non-nullable"
            lines.append(
                f"| `{p['name']}` | {p.get('in', 'query')} | {'yes' if p.get('required') else 'no'} | `{p.get('example', 'fixture-value')}` | {nullable}; fixture value; replace with a real ID when running. |"
            )
    else:
        lines.append("No path or query parameters.")
    schema = record["resolved_request"]
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    if properties:
        lines += ["", "| Body field | Required | Nullable | Notes |", "|---|---:|---:|---|"]
        for name, required, is_nullable, notes in documented_fields(schema, record["components"]):
            lines.append(
                f"| `{name}` | {'yes' if required else 'no'} | {'yes' if is_nullable else 'no'} | {notes}; replace fixture values with domain-valid data before runtime execution. |"
            )
    multipart = multipart_fields(record)
    form = form_fields(record)
    if multipart or form:
        lines += ["", "| Multipart field | Type | Required | Notes |", "|---|---|---:|---|"]
        for item in multipart or form or []:
            lines.append(
                f"| `{item['name']}` | {item.get('type', 'text')} | yes | Fixture value; replace the file or provider payload before runtime execution. |"
            )
    if record["path"] == "/api/v1/management/properties/import/":
        lines += [
            "",
            "CSV columns: `name`, `address`, `district_id`, `rooms`, `area_sqm`, `floor`, `owner_id`, `ask_price`, `owner_guaranteed_price`, and `tenant_charge_price` are required; optional columns are documented in the owning view.",
        ]
    if record["path"].startswith("/api/v1/payment-webhooks/"):
        lines += [
            "",
            "Provider transport is unauthenticated at the Django route but provider verification is required: Payme uses Basic `Paycom` plus the webhook key, Click uses its signed form fields, and Stripe uses `Stripe-Signature`.",
        ]
    lines += [
        "",
        "## Saved examples",
        "",
        "Examples are static source-backed contract fixtures. Capture runtime responses with the local environment when fixtures and providers are available.",
    ]
    return "\n".join(lines)


def response_body(status: int) -> dict[str, Any]:
    if status < 300:
        return {"success": True, "message": "OK", "data": {}}
    if status == 401:
        return {"success": False, "message": "Authentication required", "error": "unauthorized"}
    if status == 403:
        return {"success": False, "message": "Permission denied", "error": "forbidden"}
    if status == 404:
        return {"success": False, "message": "Not found", "error": "not_found"}
    if status == 409:
        return {"success": False, "message": "Conflict", "error": "conflict"}
    return {"success": False, "message": "Validation error", "error": {"field": ["Invalid value."]}}


def provider_response(record: dict[str, Any], error: bool = False) -> dict[str, Any]:
    path = record["path"]
    if "/payment-webhooks/payme/" in path:
        return (
            {
                "jsonrpc": "2.0",
                "id": "fixture-request-id",
                "error": {
                    "code": -31050,
                    "message": {"ru": "Checkout not found", "uz": "Checkout not found", "en": "Checkout not found"},
                },
            }
            if error
            else {"jsonrpc": "2.0", "id": "fixture-request-id", "result": {"allow": True}}
        )
    if "click" in path:
        return (
            {
                "click_trans_id": "{{click_transaction_id}}",
                "merchant_trans_id": "{{checkout_public_token}}",
                "error": -5,
                "error_note": "USER DOES NOT EXIST",
            }
            if error
            else {
                "click_trans_id": "{{click_transaction_id}}",
                "merchant_trans_id": "{{checkout_public_token}}",
                "error": 0,
                "error_note": "Success",
            }
        )
    return {"error": "invalid_signature"} if error else {"received": True}


def example(
    record: dict[str, Any], label: str, status: int, response: Any, request_body: dict[str, Any] | None = None
) -> dict[str, Any]:
    url = "{{base_url}}" + re.sub(r"<[^:>]+:([^>]+)>", r":\1", record["path"])
    request: dict[str, Any] = {
        "url": url,
        "method": record["method"],
        "headers": [{"name": "accept", "value": "application/json"}],
    }
    if record["auth"] == "bearer":
        request["headers"].append({"name": "authorization", "value": "Bearer {{access_token}}"})
    if "/payment-webhooks/payme/" in record["path"]:
        request["auth"] = {"type": "basic", "username": "Paycom", "password": "{{payme_key}}"}
    if "stripe" in record["path"]:
        request["headers"].append({"name": "Stripe-Signature", "value": "{{stripe_signature}}"})
    if record["params"]:
        request["params"] = [
            {"name": p["name"], "value": str(p.get("example", "1")), "type": p.get("in", "query")}
            for p in record["params"]
            if p.get("in") == "query"
        ]
    if request_body is not None:
        request["body"] = request_body
    elif request_body is None and record["method"] in {"POST", "PUT", "PATCH"}:
        body = body_for(record)
        if body is not None:
            request["body"] = {"type": "json", "data": json.dumps(body, indent=2)}
    return {
        "name": label,
        "request": request,
        "response": {
            "status": status,
            "statusText": "OK" if status < 300 else "Error",
            "headers": [{"name": "content-type", "value": "application/json"}],
            "body": {"type": "json", "data": json.dumps(response, indent=2)},
        },
    }


def write_yaml(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(yaml.safe_dump(value, sort_keys=False, allow_unicode=False) or ""), encoding="utf-8")


def environments(root: Path) -> None:
    common = [
        ("access_token", "", True),
        ("refresh_token", "", True),
        ("pk", "1", False),
        ("photo_id", "1", False),
        ("agent_id", "1", False),
        ("listing_id", "1", False),
        ("property_id", "1", False),
        ("sample_image", "", False),
        ("sample_csv", "", False),
        ("webhook_secret", "", True),
        ("webhook_signature", "", True),
        ("payme_key", "", True),
        ("checkout_public_token", "fixture-checkout-token", False),
        ("click_transaction_id", "fixture-click-transaction", False),
        ("click_service_id", "", False),
        ("click_signature", "", True),
        ("stripe_session_id", "cs_fixture", False),
        ("stripe_signature", "", True),
        ("idempotency_key", "fixture-idempotency-key", False),
    ]
    for name, base in (
        ("Local", "http://127.0.0.1:8000"),
        ("Dev", "https://REPLACE_WITH_DEV_API_HOST"),
        ("Prod", "https://REPLACE_WITH_PROD_API_HOST"),
    ):
        variables = [{"name": "base_url", "value": base, "enabled": True, "secret": False, "type": "text"}]
        variables += [
            {"name": key, "value": value, "enabled": True, "secret": secret, "type": "text"}
            for key, value, secret in common
        ]
        write_yaml(root / "environments" / f"{name}.yml", {"name": name, "variables": variables})


def generate(root: Path, report: bool = True) -> dict[str, Any]:
    data = inventory()
    root.mkdir(parents=True, exist_ok=True)
    environments(root)
    for old in root.glob("**/*.yml"):
        if old.parent.name != "environments" and old.name not in {"opencollection.yml"}:
            old.unlink()
    for directory in sorted(root.glob("**/*"), key=lambda p: len(p.parts), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()) and directory.name != "environments":
            directory.rmdir()
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in data["operations"]:
        groups[domain(record["path"])].append(record)
    used_names: set[str] = set()

    # Build folder hierarchy and write folder.yml for all levels
    tree: dict[str, list[str]] = defaultdict(list)
    for group in groups:
        parts = group.split("/")
        for i in range(len(parts)):
            parent = "/".join(parts[:i])
            child = parts[i]
            if child not in tree[parent]:
                tree[parent].append(child)

    if "" in tree:
        top_items = sorted(tree[""])
        if "mobile" in top_items:
            top_items.remove("mobile")
            top_items.insert(0, "mobile")
        tree[""] = top_items

    for parent, children in tree.items():
        if parent != "":
            children = sorted(children)
            tree[parent] = children
        for seq, child in enumerate(children, 1):
            rel_path = f"{parent}/{child}".lstrip("/")
            folder_path = root / rel_path
            folder_name = child.replace("-", " ").title()
            write_yaml(folder_path / "folder.yml", {"info": {"name": folder_name, "type": "folder", "seq": seq}})

    for group, records in sorted(groups.items()):
        folder = root / group
        for index, record in enumerate(sorted(records, key=lambda x: (x["path"], x["method"])), 1):
            display_name = human_request_name(record)
            if display_name in used_names:
                display_name = f"{display_name} {humanize(group.replace('/', ' '))}"
            suffix = 2
            base_display_name = display_name
            while display_name in used_names:
                display_name = f"{base_display_name} {suffix}"
                suffix += 1
            used_names.add(display_name)
            multipart = multipart_fields(record) if record["method"] in {"POST", "PUT", "PATCH"} else None
            form = form_fields(record) if record["method"] in {"POST", "PUT", "PATCH"} else None
            body = (
                body_for(record)
                if record["method"] in {"POST", "PUT", "PATCH"} and not multipart and not form
                else None
            )
            request: dict[str, Any] = {
                "info": {"name": display_name, "type": "http", "seq": index},
                "http": {
                    "method": record["method"],
                    "url": "{{base_url}}" + re.sub(r"<[^:>]+:([^>]+)>", r":\1", record["path"]),
                },
                "settings": {"encodeUrl": True, "timeout": 0, "followRedirects": True, "maxRedirects": 5},
                "docs": docs_for(record),
            }
            if "/payment-webhooks/payme/" in record["path"]:
                request["http"]["auth"] = {"type": "basic", "username": "Paycom", "password": "{{payme_key}}"}
            elif record["auth"] == "bearer":
                request["http"]["auth"] = {"type": "bearer", "token": "{{access_token}}"}
            else:
                request["http"]["auth"] = {"type": "none"}
            params = []
            for p in record["params"]:
                if p.get("in") == "path":
                    params.append({"name": p["name"], "value": "{{" + p["name"] + "}}", "type": "path"})
                else:
                    schema = p.get("schema", {})
                    params.append(
                        {
                            "name": p["name"],
                            "value": str(p.get("example") or sample_value(schema, p["name"])),
                            "type": "query",
                        }
                    )
            if params:
                request["http"]["params"] = params
            if multipart is not None:
                request["http"]["body"] = {"type": "multipart-form", "data": multipart}
            elif form is not None:
                request["http"]["body"] = {"type": "form-urlencoded", "data": form}
            elif body is not None:
                request["http"]["body"] = {"type": "json", "data": json.dumps(body, indent=2)}
            statuses = record["responses"]
            success = next((s for s in statuses if 200 <= s < 300), 200)
            request_body = (
                {"type": "multipart-form", "data": multipart}
                if multipart is not None
                else ({"type": "form-urlencoded", "data": form} if form is not None else None)
            )
            if record["path"].startswith("/api/v1/payment-webhooks/"):
                provider_request = request_body or {"type": "json", "data": json.dumps(body_for(record), indent=2)}
                examples = [example(record, "success", 200, provider_response(record), provider_request)]
                examples.append(
                    example(
                        record,
                        "provider error",
                        200 if "/payment-webhooks/payme/" in record["path"] or "click" in record["path"] else 400,
                        provider_response(record, True),
                        provider_request,
                    )
                )
            else:
                examples = [example(record, "success", success, response_body(success), request_body)]
            failure_statuses = []
            for status in (400, 401, 403, 404, 409):
                if (
                    status in statuses
                    or (status == 404 and record["params"] and any(p.get("in") == "path" for p in record["params"]))
                    or (status in {400, 409} and record["method"] in {"POST", "PUT", "PATCH", "DELETE"})
                ):
                    failure_statuses.append(status)
            for status in failure_statuses:
                examples.append(
                    example(
                        record,
                        {
                            400: "validation error",
                            401: "unauthorized",
                            403: "forbidden",
                            404: "not found",
                            409: "conflict",
                        }[status],
                        status,
                        response_body(status),
                        request_body,
                    )
                )
            request["examples"] = examples
            write_yaml(folder / f"{index:03d}-{safe_name(record['path'], record['method'])}.yml", request)
    write_yaml(
        root / "opencollection.yml",
        {
            "opencollection": "1.0.0",
            "info": {
                "name": "iDeal",
                "version": "1.0.0",
                "description": "Source-backed iDeal Backend API collection. Use Local/Dev/Prod environments; Dev and Prod hosts are placeholders until deployment URLs are supplied.",
            },
            "bundled": False,
            "extensions": {"bruno": {"ignore": ["node_modules", ".git", ".env*"]}},
        },
    )
    if report:
        print(json.dumps(data["counts"], indent=2, sort_keys=True))
    return data


def validate(root: Path) -> int:
    data = inventory()
    expected_records = {(normalized(r["path"]).rstrip("/"), r["method"]): r for r in data["operations"]}
    files = [
        p
        for p in root.glob("**/*.yml")
        if p.parent.name != "environments" and p.name != "opencollection.yml" and p.name != "folder.yml"
    ]
    errors: list[str] = []
    found: list[tuple[str, str]] = []
    names: dict[str, Path] = {}
    secret_pattern = re.compile(r"(?i)(sk_(?:live|test)_[A-Za-z0-9]+|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]+ KEY-----)")
    for path in files:
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            doc: dict[str, Any] = loaded if isinstance(loaded, dict) else {}
        except Exception as exc:
            errors.append(f"{path}: YAML parse: {exc}")
            continue
        info, http = doc.get("info", {}), doc.get("http", {})
        if doc.get("body") is not None or doc.get("params") is not None:
            errors.append(f"{path}: request body/params must be inside http")
        request_name = info.get("name")
        if request_name in names:
            errors.append(f"{path}: duplicate request name also used by {names[request_name]}")
        elif request_name:
            names[request_name] = path
        method, url = http.get("method"), http.get("url", "")
        route = url.replace("{{base_url}}", "").split("?", 1)[0].rstrip("/") or "/"
        route = re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", r"{\1}", route)
        found.append((route, method))
        expected_record = expected_records.get((route, method))
        if not info.get("name") or not method or "{{base_url}}" not in url:
            errors.append(f"{path}: missing info/method/base_url")
        if not isinstance(doc.get("examples"), list) or not any(
            e.get("name") == "success" for e in doc.get("examples", [])
        ):
            errors.append(f"{path}: missing success example")
        body = http.get("body") or doc.get("body")
        params = http.get("params") or doc.get("params") or []
        if body and body.get("type") == "json":
            try:
                parsed_body = json.loads(body.get("data", ""))
                if expected_record and not expected_record["path"].startswith("/api/v1/payment-webhooks/"):
                    expected_fields = set((expected_record["resolved_request"].get("properties") or {}).keys())
                    if expected_fields and isinstance(parsed_body, dict) and not expected_fields.issubset(parsed_body):
                        errors.append(f"{path}: body missing fields {sorted(expected_fields - set(parsed_body))}")
            except Exception as exc:
                errors.append(f"{path}: invalid JSON body: {exc}")
        if expected_record:
            auth = http.get("auth")
            if expected_record["auth"] == "bearer" and not (
                isinstance(auth, dict) and auth.get("type") == "bearer" and "{{access_token}}" in str(auth)
            ):
                errors.append(f"{path}: expected bearer auth")
            if (
                expected_record["auth"] == "none"
                and expected_record["path"] != "/api/v1/payment-webhooks/payme/"
                and not (isinstance(auth, dict) and auth.get("type") == "none")
            ):
                errors.append(f"{path}: expected no auth")
            expected_path = set(path_params(expected_record["path"]))
            actual_path = {p.get("name") for p in params if p.get("type") == "path"}
            if expected_path != actual_path:
                errors.append(f"{path}: path params expected {sorted(expected_path)}, found {sorted(actual_path)}")
            expected_query = {p["name"] for p in expected_record["params"] if p.get("in") == "query"}
            actual_query = {p.get("name") for p in params if p.get("type") == "query"}
            if expected_query != actual_query:
                errors.append(f"{path}: query params expected {sorted(expected_query)}, found {sorted(actual_query)}")
            if any(p.get("disabled") for p in params):
                errors.append(f"{path}: a path/query parameter is disabled")
            expected_multipart = multipart_fields(expected_record)
            expected_form = form_fields(expected_record)
            expected_fields = expected_multipart or expected_form
            if expected_fields and method in {"POST", "PUT", "PATCH"}:
                actual_body = body or {}
                actual_names = (
                    {
                        str(item.get("name"))
                        for item in actual_body.get("data", [])
                        if isinstance(item, dict) and item.get("name") is not None
                    }
                    if actual_body.get("type") in {"multipart-form", "form-urlencoded"}
                    else set()
                )
                required_names = {
                    str(item.get("name"))
                    for item in expected_fields
                    if isinstance(item, dict) and item.get("name") is not None
                }
                if actual_names != required_names:
                    errors.append(
                        f"{path}: form fields expected {sorted(required_names)}, found {sorted(actual_names)}"
                    )
        raw_text = path.read_text(encoding="utf-8")
        if secret_pattern.search(raw_text):
            errors.append(f"{path}: possible hard-coded secret")
        if "Bearer " in raw_text and "{{access_token}}" not in raw_text:
            errors.append(f"{path}: possible hard-coded bearer token")
    expected = {(normalized(r["path"]).rstrip("/"), m) for r in data["routes"] for m in r["methods"]}
    actual = set(found)
    missing = expected - actual
    extra = actual - expected
    errors += [f"missing {method} {path}" for path, method in sorted(missing)]
    errors += [f"unexpected {method} {path}" for path, method in sorted(extra)]
    env_files = list((root / "environments").glob("*.yml"))
    envs = {p.stem for p in env_files}
    if envs != {"Local", "Dev", "Prod"}:
        errors.append(f"environments: expected Local/Dev/Prod, found {sorted(envs)}")
    env_variable_sets = []
    for env_file in env_files:
        try:
            loaded_env = yaml.safe_load(env_file.read_text(encoding="utf-8"))
            env_data: dict[str, Any] = loaded_env if isinstance(loaded_env, dict) else {}
            vars_list: list[Any] = env_data.get("variables", [])
            env_variable_sets.append(
                {str(item.get("name")) for item in vars_list if isinstance(item, dict) and item.get("name") is not None}
            )
        except Exception as exc:
            errors.append(f"{env_file}: invalid environment YAML: {exc}")
    if env_variable_sets and len({frozenset(items) for items in env_variable_sets}) != 1:
        errors.append("environments: variable names differ between Local, Dev, and Prod")
    print(
        json.dumps(
            {
                "expected_routes": len(data["routes"]),
                "expected_methods": len(expected),
                "request_files": len(files),
                "errors": len(errors),
                "error_details": errors[:50],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["inventory", "generate", "validate"])
    parser.add_argument("--collection", type=Path, default=COLLECTION)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.command == "inventory":
        data = inventory()
        output = json.dumps(data, indent=2, default=str)
        if args.out:
            args.out.write_text(output + "\n", encoding="utf-8")
        else:
            print(output)
        return 0
    if args.command == "generate":
        generate(args.collection)
        return 0
    return validate(args.collection)


if __name__ == "__main__":
    raise SystemExit(main())
