set dotenv-load := true
set export := true
set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

default:
    @just --list

help:
    @just --list

# Local development
install:
    uv sync

run host="127.0.0.1" port="8000":
    uv run python src/manage.py runserver {{host}}:{{port}}

migrate:
    uv run python src/manage.py migrate

makemigrations app="":
    if [ -n "{{app}}" ]; then uv run python src/manage.py makemigrations "{{app}}"; else uv run python src/manage.py makemigrations; fi

collectstatic:
    uv run python src/manage.py collectstatic --noinput

superuser:
    uv run python src/manage.py createsuperuser

shell:
    uv run python src/manage.py shell

test:
    uv run pytest src/tests

test-unit:
    uv run pytest -m unit src/tests

test-integration:
    uv run pytest -m integration src/tests

test-cov:
    uv run pytest -n 0 --cov=src/apps --cov=src/api --cov=src/core --cov=src/config --cov-report=html:htmlcov --cov-fail-under=80 src/tests

check:
    uv run python src/manage.py check
    uv run python src/manage.py test

startapp name ver="v1":
    uv run python src/manage.py startapp {{name}} --ver {{ver}}

health-local port="8000":
    curl -fsS "http://127.0.0.1:{{port}}/api/v1/health/" > /dev/null
    @echo "Healthcheck passed on :{{port}}"

# Docker development
up:
    docker compose up --build -d

down:
    docker compose down

restart:
    docker compose down
    docker compose up --build -d

logs service="web":
    docker compose logs -f {{service}}

health:
    curl -fsS "http://127.0.0.1:${APP_PORT:-8005}/api/v1/health/" > /dev/null
    @echo "Healthcheck passed on :${APP_PORT:-8005}"

# Docker production profile
up-prod:
    docker compose -f docker-compose.prod.yml up --build -d

down-prod:
    docker compose -f docker-compose.prod.yml down

logs-prod service="web":
    docker compose -f docker-compose.prod.yml logs -f {{service}}
