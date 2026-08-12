# ReadTrackr

Private, single-user book tracking built with FastAPI, SQLite, HTMX, and Docker.

## Run locally

1. Copy `.env.example` to `.env`, then set a username, generated password hash, and session secret.
2. `docker compose up --build`
3. Open `http://localhost:8080` and sign in.

Generate a password hash with:

```bash
docker compose run --rm readtrackr python -m app.auth hash-password
```

## Deployment

Copy `docker-compose.override.example.yml` to `docker-compose.override.yml` on the VPS to expose port 3005. Route the existing global Caddy instance to `host.docker.internal:3005`; this repository intentionally does not run Caddy.

The included GitHub Actions workflow builds on the VPS on pushes to `main`. Configure the secrets listed in `.github/workflows/deploy.yml` before enabling it.
