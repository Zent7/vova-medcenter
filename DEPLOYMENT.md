# Production deployment checklist

## Immutable application images

Backend and frontend are built from repository Dockerfiles and published by
`.github/workflows/publish-images.yml` to GHCR. Every image is tagged with the
full Git commit SHA:

```text
ghcr.io/zent7/vova-medcenter-backend:<full-commit-sha>
ghcr.io/zent7/vova-medcenter-frontend:<full-commit-sha>
```

Production compose files must pin both images to the same full SHA, use
`pull_policy: always`, and must not contain `build`, `dockerfile_inline`, or a
`FROM vova-medcenter-*` overlay. The backend health response and frontend
`/build.json` expose the embedded `build_revision` for post-deploy checks.

The GHCR packages must either be public or the deployment host must be logged
in with a read-only `read:packages` token. Public packages are preferred for
this public demo so Komodo can pull them without a host credential.

This project is prepared for a standard VPS deployment:

1. PostgreSQL database on the server.
2. FastAPI backend as a persistent service.
3. Built frontend from `frontend/dist` served by Nginx.
4. Nginx reverse proxy from `/api` to backend.
5. HTTPS certificate through Certbot.
6. Scheduled database backups with `backup-db.ps1` locally or `pg_dump` on Linux.

Recommended production environment variables:

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/medcenters
FRONTEND_ORIGIN=https://your-domain.ru
GENERATED_DOCUMENTS_DIR=/var/lib/medcenters/generated
DOCUMENT_TEMPLATE_OVERRIDES_DIR=/var/lib/medcenters/template-overrides
DELETION_NOTIFY_EMAIL=admin@your-domain.ru
SMTP_HOST=smtp.your-provider.ru
SMTP_PORT=587
SMTP_USER=admin@your-domain.ru
SMTP_PASSWORD=change-me
SMTP_FROM=admin@your-domain.ru
```

Backend service command:

```bash
cd /opt/medcenters/backend
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Health-check after deploy:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

The response must include `"database_dialect":"postgresql"`.

Frontend build:

```bash
cd /opt/medcenters/frontend
npm ci
npm run build
```

Nginx should serve `frontend/dist` and proxy `/api/v1/` to `http://127.0.0.1:8000/api/v1/`.

## Local Windows backup contour

For the local Windows production-like setup:

- use `backup-db.ps1` for PostgreSQL and runtime documents backup;
- use `restore-db.ps1` for database-only, documents-only, or full restore;
- use `register-backup-task.ps1` to register a daily Windows Task Scheduler job;
- review the operational runbook in `docs/Резервное_копирование.md`.

The runtime documents path must point to `GENERATED_DOCUMENTS_DIR` instead of repo-only templates. The default local value is `storage/generated`.
Client-edited templates must be kept outside the application image in `DOCUMENT_TEMPLATE_OVERRIDES_DIR` (default `storage/template-overrides`) and included in backups.
