# AGENTS.md

This file provides guidance to AI coding assistants (Claude Code, Codex, Copilot, etc.) working in this repository.

## Project Overview

Medical center management system for two Russian clinics. Handles clients (patients), medical encounters, document generation from Word/Excel/XML templates, blank form tracking, and legacy data import from Microsoft Access.

## Development Setup

**Prerequisites**: Docker (for PostgreSQL), Python 3.11+, Node.js 20+

**Start database:**
```bash
docker compose up -d
```

**Backend** (runs on port 8000):
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

**Frontend** (runs on port 5173):
```bash
cd frontend
npm install
npm run dev
```

**Interactive API docs**: http://localhost:8000/api/v1/openapi.json  
**Document template test page**: http://localhost:8000/test-documents

## Database Migrations

```bash
cd backend
alembic upgrade head                                    # apply migrations
alembic revision --autogenerate -m "description"       # generate new migration
alembic downgrade -1                                   # roll back one step
```

Default DB: `postgresql+psycopg://medcenters:medcenters@127.0.0.1:5434/medcenters`

### Mandatory Alembic / DB Checks

For any backend, database, seed-data, API, or migration-related change, verify migration history compatibility before publishing it:

- Check whether model, seed-data, or API changes depend on new or changed database columns or tables.
- Verify that the current head revision exists and `alembic heads` shows the expected single head.
- Run `alembic upgrade head` against a clean PostgreSQL database.
- If an existing database or dump is available, verify that upgrading it to head also succeeds.
- Never delete, rename, or revert a migration file that may already have been applied to live or staging. Add a new migration to change or remove obsolete schema instead.
- For a new application image, verify that the backend container starts, migrations apply, `/api/v1/health` reports the expected `build_revision`, and the frontend image contains the expected change.
- If live infrastructure is unavailable, explicitly state that live runtime and migrations were not verified.

`Can't locate revision identified by '<revision>'` means that a database expects a migration missing from the code or image. Treat this as a migration-history compatibility failure, not a deployment-tool failure.

## Git Delivery Workflow

`main` in `Zent7/vova-medcenter` (remote `origin`) is the default branch and the single integration point — `git remote show origin` reports `HEAD branch: main`. Work is delivered by pushing to `main`, not by branches or pull requests. Feature branches are deleted once integrated, so a `codex/*` branch still present locally is finished history: never start new work on top of one, and never assume its copy of this file is current.

Before changing files, check the branch state:
```bash
git fetch origin
git status --short --branch
git branch --show-current
git rev-list --left-right --count origin/main...HEAD   # commits only on main / only here
```

A non-zero left-hand count means the checkout is behind `main`. Rebase onto `origin/main` or move to a fresh worktree before editing: a change prepared on stale history is reviewed against the wrong code and can silently revert newer work.

**Repository-owner rule: no branches, no pull requests — every change goes straight into `main`.** After implementation and proportionate verification, commit and push directly to `origin/main`. Do not create a feature branch for the work, do not open a PR in `Zent7/vova-medcenter`, and do not ask the user which branch to use. The only exceptions are an explicit request from the user for a PR, or a direct push refused by permissions or branch protection — in that case report the exact blocker and leave the work committed locally, instead of silently falling back to a branch and PR.

When the current checkout is dirty or not based on current `origin/main`, use a clean isolated worktree for integration:
```bash
git worktree add <dir> --detach origin/main
# apply or cherry-pick the change there, commit, then
git push origin HEAD:main
git worktree remove <dir>
```

Preserve the original working tree and report any local changes that remain outside `main`. If the working tree is dirty, preserve the user's changes and do not overwrite them. To commit only what a task touched while unrelated changes stay staged or modified, pass explicit paths: `git add <paths>` followed by `git commit -- <paths>`.

Every push to `main` triggers the `Publish application images` workflow, which rebuilds both images and opens a downstream homelab delivery. Documentation- and tooling-only changes trigger it too, so state that side effect before pushing and let the user decide whether the deployment should happen now.

After pushing `main`:

- Confirm that the remote `main` SHA matches the intended commit.
- Monitor the `Publish application images` GitHub Actions run through all jobs.
- Treat a failed or cancelled run as incomplete delivery and report the failing job and step.
- Delete obsolete remote feature branches after their commits are integrated or archived with a recovery tag.

If the user explicitly asks for a PR, check mergeability, conflicts, and status checks before handoff. The `gh` CLI is not installed on every machine used with this repository — check `gh --version` first, and without it push the branch and hand off the PR-creation URL that `git push` prints.

## GitHub Actions

The active workflow is `.github/workflows/publish-images.yml` (`Publish application images`). It runs for pushes to `main`, exceptional `codex/**` branches, and manual dispatches.

- `publish` builds backend and frontend images, tags them with the immutable source commit SHA, and pushes them to `ghcr.io/zent7`.
- `update-homelab` runs only after a successful `main` publication. It resolves both image digests, checks out `ravilushqa/homelab` with `HOMELAB_DEPLOY_KEY`, updates `komodo/stacks/vova-medcenter/compose.yaml`, and pushes `automation/vova-medcenter-<short-sha>`.
- The downstream homelab automation opens and processes the delivery PR. Do not create a duplicate homelab PR when that automation succeeds.
- The required repository secret is `HOMELAB_DEPLOY_KEY`. A missing secret or failed homelab job blocks delivery even if both images were published.
- Concurrency is scoped by Git ref and cancels stale in-progress runs, preventing an older push from overtaking a newer one.

Action majors currently used and intentionally tracked: `actions/checkout@v7`, `docker/setup-buildx-action@v4`, `docker/login-action@v4`, `docker/build-push-action@v7`, and `imjasonh/setup-crane@v0.7`. Review their official releases before changing majors.

## Code Review

`.claude/agents/codex-review.md` defines a `codex-review` subagent that runs an independent review with the OpenAI Codex CLI and re-verifies every finding against the actual files before reporting it. `.claude/scripts/codex-review.sh` is the runner:

```bash
bash .claude/scripts/codex-review.sh --out <dir> --uncommitted    # working tree
bash .claude/scripts/codex-review.sh --out <dir> --base main      # checkout vs main
bash .claude/scripts/codex-review.sh --out <dir> --commit <sha>   # a single commit
```

It resolves the newest installed `codex` binary — the desktop app keeps several builds under `%LOCALAPPDATA%\OpenAI\Codex\bin\`, and the older launcher there rejects the model configured in `~/.codex/config.toml` — and writes `review.md`, `events.jsonl` and `codex.log` into `<dir>`. A review takes several minutes, so run it in the background. `codex_models_manager` warnings in `codex.log` are noise, not review failures.

Findings come back as `- [Pn] <title> — <absolute path>:<lines>`, P0 highest. Treat them as claims to check rather than conclusions: Codex line numbers drift when code moved in the diff, it flags the deliberate conventions documented in this file, and a review of a stale checkout reports problems that `main` already fixed.

## Backend Architecture

**Stack**: FastAPI + SQLAlchemy 2.0 (async-style sync sessions) + Pydantic v2 + Alembic + PostgreSQL 16

**Layer structure**:
- `app/core/config.py` — Pydantic `Settings` loaded from `.env`; SQLite is blocked by default (`ALLOW_SQLITE=true` to override for diagnostics only)
- `app/db/session.py` — `SessionLocal` factory; routes use `Depends(get_db)` to get a `Session`
- `app/models/` — SQLAlchemy ORM models; all use soft-delete (`deleted_at` column), most use `TimestampMixin` for `created_at`/`updated_at`
- `app/schemas/` — Pydantic v2 request/response schemas, separate from ORM models
- `app/services/` — business logic; route handlers call services, not ORM directly
- `app/api/v1/routes/` — one module per resource, all mounted in `app/api/router.py` under `/api/v1`

**Auth**: Simple SHA-256 password hash (no JWT). Token is opaque and stored in localStorage on the frontend. Auth routes are in `app/api/v1/routes/auth.py`.

**Key env vars** (see `.env.example`):
- `DATABASE_URL` — full SQLAlchemy URL
- `GENERATED_DOCUMENTS_DIR` — where generated files land (default `storage/generated`)
- `DELETION_NOTIFY_EMAIL`, `SMTP_*` — optional email notifications on soft-delete

## Document Generation

The core business feature. Entry point: `app/services/document_generator.py::generate_document()`.

**Template types** (stored in `assets/templates/`):
- `.docx` — token replacement via XML manipulation of `word/document.xml` inside the zip. Tokens: `[TokenName]` or `[|TokenName|]`. Handles split tokens across XML runs and Word bookmark-based replacement.
- `.xls` — old Excel format via `xlrd`/`xlutils`. Some sheets have named handlers (e.g., `"086"`, `"Договор !"`, `"Водительская Лицевая"`); yellow-highlighted cells (`bg_index == 13`) use auto-label matching to fill values without hardcoded coordinates.
- `.xml` — simple text token replacement.

**Document context** is built in `app/services/document_context.py::build_document_context()`. It returns a `dict[str, str]` with 100+ named tokens covering client demographics, address parts, encounter details, doctor exam results, and driver license categories.

**Blank forms** (`app/services/blank_forms.py`): numbered medical certificate blanks issued from center-specific ranges. Once issued for a document, the same blank is reused if the document is regenerated.

**Generated files** are recorded in `generated_documents` table and stored on disk. Contract templates go into `storage/generated/contracts/`.

## Frontend Architecture

**Stack**: Vite serving the approved delivery demo UI.

The only active frontend interface is the client-approved demo in `frontend/public/demo/`.

Important paths:
- `/` redirects to `/demo/index.html`
- `/demo/index.html` is the delivery UI that should be shown to reviewers and clients
- `frontend/src/` was intentionally removed to avoid shipping two different interfaces

Do not reintroduce a second React UI unless the delivery demo is first ported into that frontend shell.

## Live Site Delivery

The live demo is maintained through the automated image and homelab workflow:

- Live demo: https://vova-medcenter.ravil.space/demo/index.html

Default workflow for site changes:

- Publish verified site/demo changes directly to `main` unless the user explicitly requests local-only work.
- Make the change in this repository, usually under `frontend/public/demo/` for UI behavior and styling.
- Verify locally with the relevant checks for the touched files.
- Let `Publish application images` publish immutable images and hand the digest-pinned update to homelab automation.
- Verify the application workflow and resulting homelab PR instead of reusing or hard-coding an old PR URL.
- Do not claim the live site is updated until the downstream PR is merged and the runtime health/build revision is verified.
- Report whether the change is local-only, in `main`, published as images, merged into homelab, or verified live.

## Utility Scripts

Located in `backend/scripts/`, run directly with Python (not as package modules):

- `import_legacy_mdb.py` — import from Access `.mdb` via `pyodbc` (Windows only)
- `import_legacy_excel.py` — import from client Excel exports
- `audit_all_document_templates.py` — scan all templates for unknown tokens
- `scan_document_tokens.py` — extract all tokens from a template file
- `runtime_api_smoke_check.py` — quick health check against a running backend

## Domain Model Key Relationships

```
Client → Encounter (many) → EncounterService (many) → Service
                           → DoctorExam (many)        (doctor_role_id is a string key like "therapist")
                           → GeneratedDocument (many) → DocumentTemplate
                           → Payment (many)
                           → MedicalRecord → MedicalRecordEntry
Client → BlankForm (many, issued per encounter/center)
Center → CertificateNumberRange (many)
```

`doctor_role_id` in `DoctorExam` is a freeform string key used to look up exams by specialty (e.g., `"therapist"`, `"ophthalmologist"`, `"psychiatrist-narcologist"`). These keys also appear in `_xls_auto_marker_values` and `_exam_map` in the document generator.

