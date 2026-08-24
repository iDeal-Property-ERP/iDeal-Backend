# Backend refactor audit

Updated: 2026-08-24. This is the migration ledger for the compatible v1
refactor. A status of **Open** is intentional and is not a silent deferral: it
names the required phase and completion evidence. Valid documented v1 payloads,
envelopes, identifiers, authentication transports, callbacks, and background
timing remain compatible. Unknown query keys remain ignored in v1.

## Baseline

- 210 resolved routes and 266 exposed application methods.
- 8,239 API-view lines; `api/v1/management/views.py` is 2,435 lines.
- 414 direct ORM references and 133 `request.GET` reads in views.
- 36 output/serialization helpers and 88 explicit output `model_dump()` calls.
- 47 service module functions; 28 static and 13 class methods; only five
  service/provider constructors.
- Baseline checks: system check, Ruff, and 258 unit tests passed. Integration
  baseline was 625 passed / 3 failed (the mobile recommendation failures are
  fixed in this slice; the full suite must establish the new baseline).

Current refactor gate: 891 tests pass, including 262 unit-selected tests; the
coverage gate is 81.90% against the enforced 80% threshold. The suite gained the
architecture/verb tests in this change; the prior integration failures are no
longer reproducible in the full current run.

## Ledger

| Confirmed smell | Evidence | Severity | Phase | Final status |
| --- | --- | --- | --- | --- |
| Raw success response dictionaries and `JsonResponse` bypass DMR | `core/api/views.py` built dicts and used `JsonResponse` for explicit statuses | Critical | 2 | **Partially fixed.** Core now emits `SuccessResponse`/`ErrorResponse` Pydantic envelopes and uses `Controller.to_response`/`to_error`. Remaining view-local raw data construction is **Open**, migrated context by context. |
| OpenAPI described bare outputs while runtime wrapped every result | Runtime envelope in `BaseController.ok`; bare output annotations throughout API | Critical | 2–5 | **Partially fixed.** Generic controllers and mobile home/favorites now annotate enveloped Pydantic outputs. Every remaining route is **Open** and blocks enabling global response validation. |
| Response validation globally disabled | `DMR_SETTINGS.validate_responses = False` | Critical | 2, 5 | **Retained temporarily.** Production fast path is correct; development/test enablement is **Open** until all endpoint annotations and error response specs are migrated. This is a tracked gate, not an exemption. |
| Generic lists serialized before slicing | `ListAPIView.get` materialized `to_output` for the whole queryset | High | 2 | **Fixed.** `build_paginated_response_from_queryset` slices first; generic and mobile discovery/favorites use it. Remaining local list implementations are **Open**. |
| Pagination accepted unbounded explicit page sizes | `ListQuery.per_page` had no bounds | High | 2–3 | **Partially fixed.** Shared and mobile query models enforce 1–100. Other endpoint-specific query models are **Open**. |
| Inline and inconsistent filters | 133 `request.GET` reads; no `FilterSet` use despite installed `django-filter` | High | 2–4 | **Partially fixed.** `PydanticFilterSet` is the query-model-first adapter; `ListingFilterSet` owns listing filtering/search/order while `ListingDiscoveryService` owns visibility/availability. All other contexts are **Open**. |
| Known malformed map/filter values silently ignored | `ListingFilters` swallowed bbox parse errors | High | 2–3 | **Partially fixed.** Mobile map/feed models reject invalid bbox, ranges, enums, page sizes, and ordering with standard 400s; legacy listing callers retain old bbox handling until their slice is migrated (**Open**). |
| Non-deterministic ordering | Listing ordering lacked an ID tie-breaker in several branches | Medium | 2 | **Fixed for listing discovery.** Every `ListingFilterSet` order ends in `-id`; other list resources are **Open**. |
| Mobile card/detail/map output helpers dumped intermediate dicts | `serialize_mobile_listing_*` in `mobile/home/views.py`; cross-view import from favorites | High | 3 | **Fixed for mobile home/favorites.** `MobileListing* .from_listing` factories return Pydantic objects with explicit request context; the favorites cross-view import is removed. Other `serialize_*` helpers are **Open**. |
| Contextual presentation constants lived in an API view and were imported by another API | mobile home imported `RESPONSE_TIME` / `_verification_checklist` from marketplace view | Medium | 3 | **Fixed.** Shared read-only facts moved to `marketplace.services.presentation`. Other cross-view imports (chat/property upload) are **Open**. |
| Static-only recommendation and favorite services | `RecommendationService` and `FavoriteListingService` were static namespaces | High | 3 | **Fixed for these services.** They are instantiable with injectable model/clock/filter dependencies and controllers obtain them through `get_service`. Booking, account deletion, finance, chat, and remaining static/class-only services are **Open**. |
| Controllers had no service factory seam | services invoked as module/class globals from views | High | 2 | **Partially fixed.** `ServiceControllerMixin` and `ServiceFactory` provide per-request cached construction and test override seam; all controllers not yet migrated are **Open**. |
| Accidental inherited HTTP verbs | `OneOffDealActionView(OneOffDealDetailView)` exposed GET/PATCH on POST actions | Critical | 2 | **Fixed.** Action base no longer inherits detail handlers; architecture and integration tests assert POST-only/405 behavior. Resolver-wide allowlist for all routes is **Open**. |
| Broad view exception catches collapse programmer/domain errors | management one-off actions and many other views catch `Exception` | High | 2–4 | **Open.** Central Pydantic error response rendering is in place, but typed application exceptions and removal of broad catches must migrate with each workflow. |
| Business workflows split between views, model saves, and signals | marketplace property→listing signal; finance payment→settlement signal; direct transactions in views | Critical | 3–4 | **Open.** No signal was removed because callers have not yet been migrated to explicit services; remove only after API/admin/task/provider paths are proven to use the service. |
| Management controller is a monolith | `api/v1/management/views.py` is 2,435 lines and combines resource domains | High | 3–4 | **Open.** One-off action inheritance is corrected, but the resource split and all management filters/services remain required. |
| Controller ORM access | 414 direct ORM references in views | High | 3–4 | **Open.** Mobile listing discovery/favorites now delegate visibility/filtering and activity behavior; every remaining controller must migrate before a zero-ORM architecture rule can be enforced. |
| Output models can cause N+1 queries | serializers call relations/counts without prepared querysets | High | 2–4 | **Partially fixed.** mobile factories state the prefetch requirement and use selected/prefetched listing querysets. Query-budget tests for every resource remain **Open**. |
| Empty legacy serializer modules | `inventory/serializers.py`, `notification/serializers.py`, `vas/serializers.py` | Low | 4 | **Open.** Delete only after imports and Bruno docs confirm no consumer. |
| Pydantic was only transitive and declared versions diverged from lock | `pyproject.toml` allowed Django 5.2/DMR 0.8; lock runs Django 6.0.5/DMR 0.10/Pydantic 2.13.4 | Medium | 1 | **Fixed.** Pydantic is direct and Django/DMR lower bounds match the lock; `uv.lock` was regenerated. |
| `just` did not use the project runtime | commands invoked bare `python`, `pytest`, and `ruff` | Medium | 1 | **Fixed.** All Python/test/check recipes now use `uv run`. |
| Recommendation activity POST returned inferred 201 instead of v1 200 | `MobileHomeRecommendedListingsView.post` lacked explicit 200 | Medium | 1 | **Fixed.** Explicit DMR 200 response and regression coverage. |
| Recommendation fixture called an unrelated candidate related through factory defaults | integration scorer test reused dimensions of its viewed seed | Medium | 1 | **Fixed.** Fixture now differs across district, type, rooms, price, tokens, area, furnishing, and tariff; the any-seed algorithm is unchanged. |
| Provider JSON-RPC/webhook endpoints use raw JSON responses | Payme, Click, and Stripe protocol callbacks | Medium | 3 | **Explicitly retained.** They are external provider protocol surfaces, not v1 DMR envelopes; convert only with provider contract tests and approval. |

## Architecture rules now enforced

- Pydantic success/error envelopes and typed pagination are the core response
  primitives.
- A controller may construct services only through the per-request factory.
- A migrated query model parses known keys; a `PydanticFilterSet` applies only
  filtering/search/order to a service-prepared queryset.
- Generic pagination slices before Pydantic output conversion.
- One-off action URLs are POST-only; the ratchet test verifies the controller
  method set and HTTP 405 responses.
- New architecture tests deliberately cover only migrated slices. The test
  suite must grow the ratchet as each bounded context migrates rather than
  falsely allowing the pre-existing repository-wide violations.

## Required gates before declaring the refactor complete

1. Migrate identity/communication, property lifecycle, and operations/finance
   domains (including each public, mobile, and management controller).
2. Replace every remaining output helper, raw response dictionary, broad catch,
   direct controller ORM workflow, static-only service, and API cross-import.
3. Move cross-aggregate model/signal behavior into application services and
   remove business-critical signals only after all callers are migrated.
4. Add resolver-wide method manifest, per-endpoint response/OpenAPI parity,
   full filter matrices, service transaction/idempotency tests, and query-count
   budgets.
5. Enable DMR response validation in development/tests, regenerate/validate
   Bruno and browser documentation after each route slice, and run final system
   checks, Ruff, migrations, coverage, and full tests. Existing non-mobile
   integration baseline failures must be reported separately if still present.
