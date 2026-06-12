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

## Git and PR Workflow

Before changing files, check the branch state:
```bash
git fetch origin
git status --short --branch
git branch --show-current
```

If the working tree is dirty, preserve the user's changes and do not overwrite them. If the current branch is behind or has diverged from its upstream/target branch, update or report that before making edits.

When implementation and verification are complete, opening a pull request is enough. The PR will be merged shortly by the normal automation/process; do not wait for the merge unless explicitly asked.

After opening a PR, check whether it is mergeable and whether it has conflicts, for example with `gh pr view --json mergeable,mergeStateStatus,statusCheckRollup` or the GitHub PR page. If there are conflicts, fix them before handing off; if they cannot be fixed locally, clearly report the conflict status and affected files.

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

