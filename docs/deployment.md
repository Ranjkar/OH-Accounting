# Deployment

## Images

```
docker build -t onholland-backend ./backend
docker build -t onholland-frontend ./frontend
```

Both build successfully as of this phase (verified with a real `docker build`, not just written and assumed). Both run as a non-root `appuser` (verified: `docker run --rm onholland-backend whoami` → `appuser`) and carry a `HEALTHCHECK` against their own `/health` (backend) or `/login` (frontend) endpoint.

## Development

```
docker compose up
```

Exposes Postgres on the host, uses weak hardcoded dev credentials deliberately (local dev only — see the file's own header comment).

## Production-oriented

```
cp .env.prod.example .env.prod   # fill in every value -- no defaults are baked in
docker compose -f docker-compose.prod.yml up -d
```

Differences from the dev compose, by design:
- Postgres has **no host port at all** — only reachable from `backend`, on an `internal: true` Docker network with no route out.
- **No credentials are hardcoded** — `POSTGRES_PASSWORD` and `NEXT_PUBLIC_API_URL` have no default and the compose file refuses to start without them (`${VAR:?error message}` syntax).
- `depends_on` uses `condition: service_healthy` for **both** `postgres` and `backend` — frontend waits for a backend that's actually passing its own healthcheck, not just "container started."
- A reverse proxy terminating real TLS sits in front of this stack — see `docs/production-deployment.md`'s nginx example. Deliberately not included as a container here: certificate paths and domain name are environment-specific and must not be guessed at in a generic compose file.

Validated with `docker compose -f docker-compose.prod.yml config` this session (confirmed valid syntax; not deployed anywhere).

## Rollback

This project has no blue/green or canary infrastructure. Rollback is:

1. `git checkout <previous-tag-or-commit>` on the deployment host/CI.
2. Rebuild and redeploy the images from that commit.
3. **Database migrations are forward-only** — `alembic downgrade` exists for every migration in this repo (checked), but running one against data written by the newer schema can lose information (e.g. downgrading after Phase 12's `users.token_version` column was in active use would silently drop session-revocation data). Prefer rolling the **application code** back while leaving the schema at the newer revision, unless a specific migration's downgrade has been reviewed for the actual data involved.

## What is not covered

- No CI/CD pipeline is defined in this repository (no `.github/workflows`, etc.) — building and deploying the images above is currently a manual operator action.
- No zero-downtime deployment strategy (rolling update, blue/green) is implemented.
