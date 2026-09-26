# LabForge — Research-Grade Upgrade

This package upgrades the earlier MVP into a research-oriented prototype with eight previously missing areas: stronger application security, complex experiment logic, reproducible randomization/counterbalancing, conditional branching, browser timing diagnostics, PostgreSQL/Redis production infrastructure, consent/debrief workflow, and research-oriented audit/export surfaces.

## 1. Project layout

```text
labforge_platform_merged/
├── backend/
│   ├── app/
│   ├── migrations/
│   ├── tests/
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── Dockerfile
│   └── docker-compose.yml
├── research-ui/
├── participant-ui/
├── docker-compose.full.yml
└── START_HERE.md
```

## 2. Recommended Windows local setup

Use a normal Windows CPython installation, preferably Python 3.13 for this project. Avoid the MSYS2/MinGW Python interpreter used earlier in the setup.

### Backend terminal

```powershell
cd "C:\Users\<YOUR_NAME>\Desktop\labforge_platform_merged\backend"
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Open `.env` and set a long random `JWT_SECRET`.

For local development the default SQLite setting is fine:

```env
DATABASE_URL=sqlite:///./labforge.db
ENVIRONMENT=development
```

Start the backend without reload first:

```powershell
python -m uvicorn app.main:app
```

Open:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/docs`

Do not copy the previous broken `--reload` setup into production. The production container runs migrations and starts multiple workers directly.

## 3. Researcher UI terminal

```powershell
cd "C:\Users\<YOUR_NAME>\Desktop\labforge_platform_merged\research-ui"
npm install
npm run dev -- --port 5173
```

Open `http://localhost:5173`.

## 4. Participant UI terminal

```powershell
cd "C:\Users\<YOUR_NAME>\Desktop\labforge_platform_merged\participant-ui"
npm install
npm run dev -- --port 5174
```

Open `http://localhost:5174`.

## 5. The complete local flow

```text
Researcher UI :5173
      |
      | JWT-authenticated API calls
      v
FastAPI :8000
      |
      +---- SQLite (local)
      |
      | public participant API + session token
      v
Participant UI :5174
      |
      | responses + timing diagnostics
      v
FastAPI :8000
      |
      v
Researcher results/export
```

## 6. Build your first research-grade experiment

In the Researcher UI create a new experiment.

Suggested flow:

```text
Consent (recorded before session creation)
        ↓
Instructions
        ↓
Fixation 500 ms
        ↓
Trial Group
   ├── BLUE → F
   ├── RED  → J
   ├── BLUE → F
   └── ...
        ↓
Set Variable: score += 1
        ↓
Branch: variables.score >= 3
   ├── true  → high-score block
   └── false → normal block
        ↓
Debrief
```

The Trial Group can be repeated and randomized. The API creates a deterministic per-session execution plan from a cryptographically random seed, then stores the exact plan with the participant session.

## 7. Security model

Researcher endpoints require JWT bearer authentication and ownership checks.

Participant sessions use a separate random participant token. The raw token is returned only when the session is created; the database stores a SHA-256 hash. Session tokens expire automatically.

The API also includes:

- password hashing with scrypt
- short-lived researcher JWTs
- request-size limiting
- per-IP rate limiting
- optional Redis-backed rate limiting
- security response headers
- audit events for researcher actions
- published-definition hashes
- strict session/plan validation

For real production deployment, use HTTPS, a managed secret store, a managed PostgreSQL database, and a reverse proxy/WAF. This package is a production-oriented prototype, not a compliance certification.

## 8. Complex experiment logic

The definition format now supports:

- instruction blocks
- consent blocks
- fixation/delay blocks
- stimulus blocks
- response blocks
- repeated/randomized Trial Groups
- Set/Increment/Decrement Variable blocks
- Branch blocks
- experiment variables
- participant-level counterbalance group assignment

Branch expressions are deliberately restricted; the participant runner does not execute arbitrary JavaScript from a branch condition.

Examples:

```text
variables.score >= 3
variables.score >= 3 && last_correct == true
variables.condition_group == "B"
```

## 9. Timing diagnostics

At session start the participant UI measures:

- `performance.now()` resolution
- display refresh interval/rate estimate
- refresh jitter
- visibility changes
- browser/platform information

During response capture it records:

- stimulus onset performance timestamp
- response performance timestamp
- reaction time
- timing error estimate
- timing flags such as page-hidden-before-response

This is designed to make browser timing limitations measurable and auditable. It does **not** prove that every participant device has laboratory-equivalent hardware timing.

## 10. Consent and debrief

Consent is configured under Researcher → Research-grade settings.

The participant must accept the configured consent version before the session is created. The backend records the consent version and server acceptance time.

The configured debrief text is returned by the completion endpoint and shown at the end of the study.

## 11. PostgreSQL + Redis production mode

The backend contains:

- Alembic migration environment
- PostgreSQL connection pooling
- Redis-backed rate limiting when `REDIS_URL` is configured
- non-root Docker image
- health checks
- multiple API workers in the production container

Start the whole stack from the project root:

```powershell
docker compose -f docker-compose.full.yml up --build
```

This starts:

```text
PostgreSQL
Redis
FastAPI
Researcher UI
Participant UI
```

Local production-style URLs:

- API: `http://localhost:8000`
- Researcher UI: `http://localhost:5173`
- Participant UI: `http://localhost:5174`

Before exposing the stack to the public internet, replace the demo credentials/secrets and put the services behind HTTPS.

## 12. Database migrations

For a clean production database, the backend container runs:

```bash
alembic upgrade head
```

For manual local development:

```powershell
alembic upgrade head
```

The migration environment is kept in source control so database schema changes are reproducible.

## 13. Tests

Backend integration tests should cover at least:

1. researcher registration/login
2. experiment creation/versioning/publishing
3. consent enforcement
4. participant token authentication
5. reproducible execution-plan generation
6. timing-diagnostics ingestion
7. response validation against the session execution plan
8. completion and CSV/JSON export

Run:

```powershell
python -m pytest -q
```

## 14. Production checklist

Before a public deployment:

- create a fresh strong JWT secret
- use managed PostgreSQL
- use Redis
- set real HTTPS CORS origins
- use HTTPS everywhere
- put API behind a reverse proxy/WAF
- configure backups and restore drills
- define data retention/deletion policy
- define the participant privacy notice and consent language for the institution
- review the study protocol/ethics requirements with the relevant institution
- add monitoring/log aggregation
- validate timing across the actual target browsers/devices
- document exclusion rules for poor timing-quality sessions

## 15. Important scientific limitation

This system measures browser-side timing with high-resolution clocks and explicit timing diagnostics. That makes timing quality visible and allows studies to reject poor sessions, but it does not make a commodity browser/device physically identical to dedicated laboratory hardware.
