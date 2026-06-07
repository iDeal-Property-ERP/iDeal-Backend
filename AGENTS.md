# iDeal-Backend Agent Guide

## Commands

All commands run from project root with `just` (loads `.env` automatically).

```bash
just test              # pytest src/tests (all 19 tests)
just test-unit         # pytest -m unit src/tests
just test-integration  # pytest -m integration src/tests
just test-cov          # sequential coverage with HTML report
just run               # python src/manage.py runserver
just migrate           # python src/manage.py migrate
just makemigrations    # python src/manage.py makemigrations (pass app="name" for one app)
just startapp <name>   # python src/manage.py startapp <name> [--ver v1]
just check             # python src/manage.py check
```

Lint and format:
```bash
ruff check src/        # lint (0 errors required)
ruff check --fix src/  # auto-fix
ruff format src/       # format in place
```

## Architecture

```
src/
├── manage.py              # sys.path appends src/apps
├── apps/                  # Django apps (imported bare: `import account`, `import property`)
│   ├── account/           # User model (AUTH_USER_MODEL)
│   ├── property/          # District, Property, PropertyPhoto
│   └── core/              # Base models, constants, shared tooling
├── api/                   # DMR controllers (versioned)
│   └── v1/
│       ├── account/       # Account API stubs
│       ├── property/      # Property CRUD (schemas, views, urls)
│       └── core/          # Auth (JWT), health, test endpoints
├── config/
│   ├── settings/
│   │   ├── base.py        # shared settings
│   │   ├── dev.py         # DEBUG=True, debug toolbar
│   │   ├── prod.py        # DEBUG=False, manifest storage
│   │   └── test.py        # fast hashing, in-memory storage, silent logging
│   └── urls/              # Root URL config
└── tests/                 # pytest root (pythonpath = src, src/apps)
    ├── conftest.py         # shared fixtures (api_client, user, owner, jwt_header, etc.)
    ├── factories/          # factory-boy factories (UserFactory, DistrictFactory, PropertyFactory)
    ├── unit/               # fast, no DB (except @pytest.mark.django_db models)
    └── integration/        # API integration tests
```

**Key oddity**: `manage.py` adds `src/apps` to `sys.path`, so apps are imported without the `apps.` prefix (e.g. `account.models`, not `apps.account.models`). Pytest handles this via `pythonpath = ["src", "src/apps"]` and `--import-mode=importlib`.

## Framework: DMR (django-modern-rest)

This project uses DMR v0.10.0 with `PydanticFastSerializer`, NOT Django REST Framework.

- No `serializers.py` — use Pydantic models in `api/v1/<app>/schemas.py`
- No `APIView` — controllers extend `BaseController` → DMR `Controller[PydanticFastSerializer]`
- CRUD mixins at `core/api/views.py`: `CreateAPIView`, `ListAPIView`, `RetrieveAPIView`, `UpdateAPIView`, `PartialUpdateAPIView`, `DeleteAPIView`
- All views require JWT auth by default (`auth = (JWTSyncAuth(),)` on `BaseController`)
- Response envelope: `{"success": bool, "message": str, "data": ...}`

### Creating a new app + API

1. `just startapp <name>` — creates `src/apps/<name>/` and `src/api/v1/<name>/`, adds to `LOCAL_APPS`
2. Add models in `src/apps/<name>/models.py` (extend `core.models.TimestampedModel` + `SoftDeleteModel`)
3. Add Pydantic schemas in `src/api/v1/<name>/schemas.py` (use `from_attributes=True`)
4. Add views in `src/api/v1/<name>/views.py` extending CRUD mixins + `GenericController`
5. Add URLs in `src/api/v1/<name>/urls.py` using manual `path()` (not `make_urlpatterns_from_views` — not in DMR)
6. Register route in `src/api/v1/urls.py`
7. Register in admin: `src/apps/<name>/admin.py` (extend `core.admin.BaseModelAdmin` or `BaseSoftDeleteModelAdmin`)
8. `just makemigrations` + `just migrate`

## Models

- Every model that persists data inherits `TimestampedModel` and `SoftDeleteModel` from `core.models`
- `TimestampedModel`: `created_at`, `updated_at` (auto-managed)
- `SoftDeleteModel`: `deleted_at`, `restored_at`, `transaction_id` + soft-delete querysets (`objects`, `deleted_objects`, `global_objects`)
- All tables have explicit `db_table`: `users`, `districts`, `properties`, `property_photos`
- `AUTH_USER_MODEL = "account.User"` — FK references use `"account.User"`
- ForeignKey fields in Pydantic schemas use `_id` suffix (`district_id`, `owner_id`) — Django ORM accepts these for creation

## Choices system

Choice constants live in `src/core/constants.py` using a custom `ConstantChoices` class (not Django's `TextChoices`):

```python
class PropertyStatus(ConstantChoices):
    VACANT = "vacant"
    RENTED = "rented"
    CHOICES = [(VACANT, _("Vacant")), (RENTED, _("Rented"))]
```

- `PropertyStatus.choices()` returns the list of tuples for model fields
- `PropertyStatus.VACANT` is a plain string `"vacant"`, usable as `default=`
- All CHOICES display labels must be wrapped with `_()` (gettext_lazy)

## Translation

All user-facing strings must be wrapped with `_()`:
- `verbose_name`, `verbose_name_plural` in model `Meta`
- Admin `fieldsets` labels
- `CHOICES` display text in `core/constants.py`
- API response messages in views (use `str(_("..."))` in method bodies — lazy proxies break msgspec serialization)

The test `test_no_untranslated_user_facing_strings` in `tests/unit/core/test_translation_coverage.py` enforces this via AST scanning.

## Testing

- Tests use **pytest** (not Django `manage.py test`)
- Test settings: `config.settings.test` (DJANGO_SETTINGS_MODULE in `pyproject.toml`)
- Test DB isolation: pytest-django handles `@pytest.mark.django_db` per test
- Running a single test: `pytest src/tests/unit/property/test_models.py -k test_name`
- Test classes auto-marked `unit` or `integration` by their directory's `conftest.py`
- Broken test names will be caught — underscores are needed literally in `test_` prefixes, not dashes

### Factories

```python
from tests.factories import UserFactory, OwnerFactory, DistrictFactory, PropertyFactory

user = UserFactory()
owner = OwnerFactory()      # role=owner preset
district = DistrictFactory(name="Custom", city="Toshkent")
prop = PropertyFactory(district=district, owner=owner)
```

### JWT in tests

```python
# Use the jwt_header fixture (from conftest.py) or:
from tests.integration.property.test_api import _make_jwt
auth = _make_jwt(user)
response = client.get("/api/v1/properties/", **auth)
```

## Common pitfalls

- **Do NOT use `from apps.xxx import ...`** — apps are on `src/apps` path, import bare: `from property.models import ...`
- **DMR vs DRF**: This is NOT Django REST Framework. No DRF serializers, no DRF viewsets, no DRF test client (`APIClient`). Use Django's `Client` with JWT headers.
- **Pydantic ValidationError in CreateAPIView**: Caught in `core/api/views.py` with try/except, returns `self.fail()`. API tests check `body["success"] is False` and `"error" in body`.
- **Pagination format**: Uses `count/num_pages/per_page/page.number/page.object_list`, not `items/pagination`. Query params: `?page=2&per_page=10`.
- **SECRET_KEY must be ≥32 chars** for HS256 JWT.
- **Ruff F405** is ignored in `src/config/settings/*.py` (star imports from base).
- **Ruff S101** (assert) is ignored in test files.
- **Line length**: 120 chars (both ruff and black).
- **Quote style**: double quotes (ruff format).
