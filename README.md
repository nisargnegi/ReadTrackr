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

ReadTrackr follows the VPS-wide reverse-proxy architecture: it exposes host port `3006` and **does not** bundle Caddy. The GitHub Actions workflow creates this project-local `docker-compose.override.yml` on its first deployment:

```yaml
services:
  readtrackr:
    ports:
      - "3006:8080"
```

On the VPS, add a subdomain route to `~/reverse-proxy/Caddyfile` (preferred because the app uses normal root-relative URLs):

```caddyfile
books.your-domain.duckdns.org {
    reverse_proxy host.docker.internal:3006
}
```

Then reload the existing Caddy stack from `~/reverse-proxy/`. The VPS deploy user needs an SSH deploy key with read access to this private GitHub repository, because the workflow clones using `git@github.com:nisargnegi/ReadTrackr.git`.

## Cover backfill

After adding `GOOGLE_BOOKS_API_KEY` to GitHub Actions secrets and deploying, run this on the VPS to enrich every book missing a cover:

```bash
cd ~/apps/readtrackr
docker compose exec readtrackr python -m app.backfill --all
```

This calls Google Books only; it does not use DeepSeek credits.

The included GitHub Actions workflow builds on the VPS on pushes to `main`. Configure the secrets listed in `.github/workflows/deploy.yml` before enabling it.
