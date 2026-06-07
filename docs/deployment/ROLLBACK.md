# Rollback Procedure

## When to Rollback

Consider rolling back when a deployment causes:
- Application crashes or 500 errors (check health endpoint)
- Migration failures
- Performance degradation
- API response errors
- Monitoring alerts

## Prerequisites

- SSH access to the production server
- Previous images remain loaded on the server (tagged by commit SHA from the deploy workflow)
- Knowledge of which commit was previously stable

## Step-by-Step Rollback

### 1. SSH into the server

```bash
ssh {{SSH_USER}}@{{SSH_HOST}}
```

### 2. Identify available images

```bash
docker images ideal-web-prod
```

This lists all tagged images. Look for the commit SHA of the previous stable deploy (e.g., `ideal-web-prod:a1b2c3d`).

### 3. Revert the image tag

```bash
docker tag ideal-web-prod:<previous-sha> ideal-web-prod:latest
```

### 4. Roll back database migrations

If the failed deployment applied new migrations, the old image's entrypoint will try to run them again. You must first reverse them:

```bash
# Check which migrations are currently applied
docker compose run --rm web python manage.py showmigrations

# Reverse migrations applied by the failed deploy
# Go from the latest migration back to the one before the deploy
docker compose run --rm web python manage.py migrate <app_name> <previous_migration_number>

# Example:
# docker compose run --rm web python manage.py migrate account 0001_initial
```

If multiple apps had migrations, reverse them in dependency order.

### 5. Restart services

```bash
docker compose up -d
```

### 6. Verify rollback

```bash
# Check container status
docker compose ps

# Check health
curl -fsS http://127.0.0.1:${APP_PORT}/api/v1/health/

# Check logs for errors
docker compose logs web --tail 50
docker compose logs qcluster --tail 20
```

## Database Restore (last resort)

If migration reversal is too risky or complex:

1. Restore the database from the most recent backup taken before the failed deploy
2. Then deploy the old image as described above

Keep automated daily database backups for this purpose.

## Quick Reference

```bash
# List tagged images
docker images ideal-web-prod

# Rollback to specific commit
docker tag ideal-web-prod:<sha> ideal-web-prod:latest
docker compose up -d

# Reverse a migration
docker compose run --rm web python manage.py migrate <app> <prev_migration>

# Check migration state
docker compose run --rm web python manage.py showmigrations
```

## Prevention

- Always commit migration files to git — never rely on runtime-generated migrations
- Test migrations in a staging environment before deploying to production
- Take a database backup before every production deploy
- Monitor health endpoint immediately after deploy
