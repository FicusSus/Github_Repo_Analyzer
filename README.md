# GitHub Repository Analyzer

A full-stack application that analyzes public GitHub repositories and turns raw GitHub REST API
data into development-activity statistics: commit frequency and trends, language distribution,
contributor concentration, and how all of these change over time.

- **Backend:** Python 3.12+, FastAPI, async SQLAlchemy 2, PostgreSQL, Alembic, Pandas, httpx
- **Frontend:** Vue 3 + TypeScript, Vue Router, Chart.js (via vue-chartjs), Vite
- **Infrastructure:** Docker Compose (PostgreSQL, API, nginx serving the SPA), GitHub Actions CI
- **Quality:** pytest (118 tests, 96% coverage, mocked GitHub API, real PostgreSQL in CI),
  Vitest, Ruff, mypy `--strict`, vue-tsc

No GitHub token is required: public repositories are analyzed with GitHub's anonymous API
quota. A server-side token can be configured to raise the limit.

---

## Contents

- [Features](#features)
- [Screenshots](#screenshots)
- [Architecture](#architecture)
- [GitHub API integration](#github-api-integration)
- [How the statistics are computed](#how-the-statistics-are-computed)
- [REST API](#rest-api)
- [Running with Docker](#running-with-docker)
- [Local development](#local-development)
- [Configuration](#configuration)
- [Testing](#testing)
- [Project structure](#project-structure)
- [Design decisions and limitations](#design-decisions-and-limitations)

## Features

**Repository analysis** — submit a URL in any common form (`https://github.com/owner/repo`,
`owner/repo`, `git@github.com:owner/repo.git`, deep links such as `/tree/main/docs`) and get:
name, description, owner, topics, license, primary language, stars, forks, open issues and pull
requests, watchers, contributor count, total commits on the default branch, creation, update and
last-push dates, and the latest commits.

**Commit analysis** — commits per week and per month (zero-filled, so quiet periods are visible),
a 4-week rolling average, a weekday distribution, the most active authors in the analyzed window,
recent activity (last 7/30 days), and a trend classification (increasing / decreasing / stable)
based on a least-squares fit over the last 12 complete weeks.

**Languages** — byte-based distribution with percentages, shown as a segmented bar, and a
side-by-side comparison across repositories.

**Contributors** — usernames, contribution counts and shares, plus concentration metrics:
bus factor, top-1 and top-5 share, and the Gini coefficient. Bots are flagged.

**History** — every analysis is stored in PostgreSQL. The UI lists past analyses, shows how
stars, forks, issues, contributors and commit activity changed between snapshots, and compares
the latest snapshots of 2–5 repositories (metrics table, weekly activity overlay, language mix).

**Dashboard** — responsive Vue dashboard with light and dark themes. Every chart has a
*Chart / Table* toggle so all values are readable without hovering or relying on colour.

## Screenshots

> These screenshots were captured locally. The capture environment had no direct access to
> `api.github.com`, so the backend was pointed (via `GITHUB_API_URL`) at a local stand-in for
> the GitHub API populated from the **real git history** of `fastapi/fastapi`, `pallets/flask`
> and `encode/httpx`. Commit data is real; language bytes and contributor lists were derived from
> the clones, so they differ slightly from GitHub's own numbers. Run the app to see live data.

| Repository analysis (dark) | Repository analysis (light) |
| --- | --- |
| ![Analysis page, dark theme](docs/screenshots/analysis-dark.png) | ![Analysis page, light theme](docs/screenshots/analysis-light.png) |

| Home | Comparison |
| --- | --- |
| ![Home page with analyzed repositories](docs/screenshots/home.png) | ![Comparison of three repositories](docs/screenshots/compare.png) |

| Analysis history | Mobile |
| --- | --- |
| ![History of stored analyses](docs/screenshots/history.png) | ![Analysis page on a phone](docs/screenshots/mobile.png) |

## Architecture

```mermaid
flowchart LR
    user([Browser])

    subgraph web["frontend container (nginx)"]
        spa["Vue 3 SPA<br/>Chart.js dashboards"]
    end

    subgraph api["backend container (FastAPI + uvicorn)"]
        routes["API routes<br/>/api/analyses, /api/repositories,<br/>/api/compare, /api/health"]
        service["AnalysisService<br/>cache TTL · per-repo locks"]
        analyzer["RepositoryAnalyzer<br/>parallel GitHub fetch"]
        stats["statistics.py<br/>Pandas / NumPy"]
        insights["insights.py<br/>history · comparison"]
        client["GitHubClient (httpx)<br/>pagination · ETag cache ·<br/>rate limits · retries"]
        store["AnalysisStore<br/>SQLAlchemy 2 (async)"]
    end

    db[("PostgreSQL<br/>repositories · analyses ·<br/>analysis_languages · analysis_contributors")]
    github[["GitHub REST API<br/>api.github.com"]]

    user -->|HTTP| spa
    spa -->|"/api/* (same origin, proxied)"| routes
    routes --> service
    service --> analyzer
    analyzer --> client
    client -->|HTTPS| github
    analyzer --> stats
    service --> insights
    service --> store
    store --> db
```

**Request flow for `POST /api/analyses`:**

1. The reference is parsed and validated (`app/github/url.py`).
2. A per-repository `asyncio.Lock` ensures two simultaneous requests for the same repository
   cost one round of GitHub calls; the second request is served from the stored result.
3. If a stored analysis is younger than `ANALYSIS_CACHE_TTL_SECONDS`, it is returned
   (`200 OK`, `from_cache: true`) without touching GitHub.
4. Otherwise the repository is fetched first (an unknown repository fails after one request),
   then languages, contributors, commit count and commit history are fetched **concurrently**
   with an `asyncio.TaskGroup`. No database transaction is held open during network I/O.
5. Pure Pandas functions compute the statistics; the result is persisted in one transaction and
   returned (`201 Created`).

**Layers**

| Layer | Module | Responsibility |
| --- | --- | --- |
| HTTP | `app/api` | Routing, validation, dependency injection, one JSON error envelope |
| Use cases | `app/services` | Caching, locking, orchestration, history and comparison views |
| Domain | `app/analysis` | Deterministic statistics (no I/O; `now` is always injected) |
| Integration | `app/github` | GitHub REST client, payload models, URL parsing |
| Persistence | `app/db` | ORM models, all SQL queries, async engine |

**Data model.** `repositories` is keyed by GitHub's immutable numeric id, so renamed or
transferred repositories keep their history. Each row in `analyses` is a snapshot: metrics that
are filtered, sorted or charted over time are real columns; languages and contributors are
normalised child tables; derived series (weekly/monthly buckets, trend, authors) are validated
Pydantic documents stored as `JSONB`. The schema is managed by Alembic, and CI fails if the
models and migrations drift apart (`alembic check`).

## GitHub API integration

All GitHub traffic goes through `app/github/client.py`.

**Endpoints used per analysis**

| Call | Endpoint | Requests |
| --- | --- | --- |
| Repository metadata | `GET /repos/{owner}/{repo}` | 1 |
| Language bytes | `GET /repos/{owner}/{repo}/languages` | 1 |
| Top contributors | `GET /repos/{owner}/{repo}/contributors?per_page=100` | 1 |
| Contributor count | same endpoint with `per_page=1` | 0–1 (only when > 100 contributors) |
| Total commits | `GET /repos/{owner}/{repo}/commits?per_page=1` | 1 |
| Commit history | `GET /repos/{owner}/{repo}/commits?since=…&per_page=100` | 1–`COMMITS_MAX_PAGES` |
| Latest commits of an inactive repo | `GET /repos/{owner}/{repo}/commits?per_page=10` | 0–1 |
| Budget display | `GET /rate_limit` (free, not counted by GitHub) | — |

A typical analysis costs **5–10 requests**, so the anonymous limit of 60 requests/hour allows
roughly 6–12 fresh analyses per hour; cached results cost nothing.

**Techniques**

- **Counting without downloading.** Totals (commits, contributors) are read from the page number
  in the `rel="last"` link of a `per_page=1` request — one request instead of paging through
  thousands of items.
- **Pagination** follows `Link: rel="next"` with a hard page cap. When the cap cuts the commit
  history short, the result is flagged `truncated` and statistics start at the first *complete*
  week that was fetched, so the oldest weeks are not reported as artificially empty.
- **Rate limits** follow GitHub's guidance: `x-ratelimit-*` headers are recorded on every
  response; when `remaining` is 0 the client fails fast until the reset time instead of sending
  doomed requests; secondary limits honour `retry-after` (or wait 60 s when it is absent). The
  API answers `429` with a `Retry-After` header and the reset time, and the UI shows how long to
  wait.
- **Retries** with exponential backoff and jitter for network errors and `5xx` responses only;
  `4xx` responses are never retried.
- **Conditional requests.** Responses are kept in an LRU ETag cache and re-requested with
  `If-None-Match`; a `304 Not Modified` reuses the cached body. With a token, GitHub does not
  count `304` responses against the primary limit.
- **Edge cases handled:** private/missing repositories (`404`), renamed repositories (GitHub's
  `301` redirect is followed and the canonical name stored), empty repositories (`409` on commit
  endpoints → zero commits), empty contributor lists (`204`), and repositories whose history is
  too large for GitHub to list contributors (`403`) — the analysis still succeeds with
  contributor data marked as unavailable.
- **Typed payloads.** Only the fields the analyzer needs are declared in Pydantic models, so new
  fields in GitHub responses never break parsing, and malformed payloads raise a clear error.
- **Tokens never leave the server.** `GITHUB_TOKEN` is optional, read from the environment and
  stored as a `SecretStr`; it is never committed, logged or sent to the browser.

## How the statistics are computed

All calculations live in `app/analysis/statistics.py` and are pure functions over Pandas
DataFrames, which makes them easy to unit-test.

- **Time buckets.** Weeks start on Monday 00:00 UTC, months on the 1st. Buckets are re-indexed
  over the whole window and filled with zeros. Commits with clock-skewed future dates count as
  "now"; duplicate SHAs are dropped.
- **Rolling average.** 4-week rolling mean of weekly counts.
- **Trend.** Least-squares slope over the last 12 *complete* weeks (the current, partial week
  is excluded). The projected change over the window is compared with the mean weekly volume:
  more than +20% is *increasing*, less than −20% *decreasing*, otherwise *stable*. Fewer than
  4 weeks or fewer than 20 commits in the window gives *insufficient data* — with sparse,
  bursty activity a slope is noise.
- **Most active authors.** Commits are grouped by GitHub login, falling back to the normalised
  author name for commits whose email is not linked to an account.
- **Bus factor.** The smallest number of contributors that together account for at least 50% of
  the listed contributions.
- **Gini coefficient.** Inequality of contribution counts: 0 means perfectly even, values close
  to 1 mean the work is concentrated in very few people.
- **Comparison.** Weekly series of different repositories are aligned on week start dates with
  `pandas.concat`; weeks outside a repository's analyzed window are `null` (shown as gaps).

## REST API

Interactive OpenAPI documentation is served at **`/api/docs`** (Swagger UI) and `/api/redoc`;
the schema is at `/api/openapi.json`.

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/api/analyses` | Analyze a repository. Body: `{"repository": "owner/name", "force": false}`. `201` for a new analysis, `200` when a recent one is reused. |
| `GET` | `/api/analyses` | Paginated stored analyses, newest first. Query: `limit` (1–100), `offset`, `repository`. |
| `GET` | `/api/analyses/{id}` | Full stored analysis. |
| `DELETE` | `/api/analyses/{id}` | Delete an analysis (the repository is removed with its last analysis). |
| `GET` | `/api/repositories` | Analyzed repositories with their latest snapshot. Query: `limit`, `offset`, `search`. |
| `GET` | `/api/repositories/{owner}/{name}/latest` | Latest analysis of a repository. |
| `GET` | `/api/repositories/{owner}/{name}/history` | All snapshots (oldest first) and the change of each metric. |
| `GET` | `/api/compare?repositories=a/b&repositories=c/d` | Compare the latest analyses of 2–5 repositories. |
| `GET` | `/api/github/rate-limit` | Remaining GitHub API budget of the server. |
| `GET` | `/api/health` | Liveness and database check (`503` when the database is down). |

**Example**

```bash
curl -s -X POST http://localhost:8080/api/analyses \
  -H 'Content-Type: application/json' \
  -d '{"repository": "https://github.com/pallets/flask"}' | jq '.metrics'
```

```json
{
  "stars": 74700,
  "forks": 17000,
  "open_issues": 4,
  "watchers": 2100,
  "size_kb": 10000,
  "contributors_count": 859,
  "total_commits": 5566
}
```

**Errors** always use one envelope:

```json
{
  "error": {
    "code": "github_rate_limited",
    "message": "GitHub API rate limit reached. Try again later (in about 23 min).",
    "details": { "reset_at": "2026-11-27T13:05:00Z", "retry_after_seconds": 1380 }
  }
}
```

| Status | `code` | Cause |
| --- | --- | --- |
| 404 | `repository_not_found` | Repository does not exist or is private |
| 404 | `analysis_not_found`, `repository_not_tracked` | Unknown analysis / repository never analyzed |
| 422 | `invalid_repository`, `validation_error`, `invalid_comparison` | Bad input |
| 429 | `github_rate_limited` | GitHub quota exhausted (`Retry-After` header set) |
| 502 | `github_unavailable`, `github_auth_failed`, `github_error` | GitHub unreachable, bad server token, unexpected response |

## Running with Docker

Requirements: Docker with Compose v2.

```bash
cp .env.example .env          # set POSTGRES_PASSWORD; GITHUB_TOKEN is optional
docker compose up --build
```

Open <http://localhost:8080>. The API is available under the same origin at
<http://localhost:8080/api/docs>.

The stack consists of three services:

- **db** — PostgreSQL 17 with a named volume and a health check;
- **backend** — runs `alembic upgrade head` on start (see `backend/docker-entrypoint.sh`), then
  uvicorn as a non-root user; health-checked via `/api/health`;
- **frontend** — multi-stage build (Node → nginx); nginx serves the SPA with history fallback,
  long-lived caching for hashed assets, and proxies `/api/` to the backend, so the browser never
  needs CORS.

To stop and remove data: `docker compose down -v`.

## Local development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# A PostgreSQL instance, e.g. only the db service from compose:
docker compose up -d db   # run from the repository root, with .env in place
export DATABASE_URL=postgresql+asyncpg://analyzer:<password>@localhost:5432/analyzer
```

The compose file does not publish the database port; for local development either add
`ports: ["5432:5432"]` to the `db` service or use a local PostgreSQL. Then:

```bash
alembic upgrade head
uvicorn app.asgi:app --reload       # http://localhost:8000/api/docs
```

Settings can also be placed in `backend/.env` (it is git-ignored).

Creating a migration after changing models:

```bash
alembic revision --autogenerate -m "describe the change"
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api to http://localhost:8000
```

`VITE_API_PROXY_TARGET` changes the proxy target; `VITE_API_BASE_URL` makes the built app call
an API on another origin (then add that origin to `CORS_ORIGINS`).

## Configuration

Backend settings are environment variables (see `app/config.py`):

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://analyzer:analyzer@localhost:5432/analyzer` | Async SQLAlchemy URL |
| `GITHUB_TOKEN` | *(empty)* | Optional token; raises the limit from 60 to 5000 requests/hour. No scopes needed. |
| `GITHUB_API_URL` | `https://api.github.com` | API base URL (e.g. GitHub Enterprise Server) |
| `GITHUB_TIMEOUT_SECONDS` | `15` | Per-request timeout |
| `GITHUB_MAX_RETRIES` | `3` | Retries for network errors and 5xx |
| `GITHUB_ETAG_CACHE_SIZE` | `512` | Entries in the conditional-request cache (0 disables it) |
| `COMMIT_WINDOW_DAYS` | `365` | Length of the analyzed commit window |
| `COMMITS_MAX_PAGES` | `5` | Commit pages (100 commits each) fetched per analysis |
| `CONTRIBUTORS_MAX_PAGES` | `1` | Contributor pages (100 each) stored per analysis |
| `RECENT_COMMITS_LIMIT` | `10` | Commits listed as "recent" |
| `ANALYSIS_CACHE_TTL_SECONDS` | `600` | Reuse an analysis younger than this; `0` disables reuse |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma-separated origins allowed to call the API directly |
| `LOG_LEVEL` | `INFO` | Python logging level |

## Testing

### Backend

```bash
cd backend
pytest                                   # 118 tests
pytest --cov --cov-report=term-missing   # coverage report (96%)
ruff check . && ruff format --check .
mypy app                                 # strict mode
```

By default database tests use a temporary SQLite file so the suite runs anywhere. To run them
against PostgreSQL, as CI does, point `TEST_DATABASE_URL` at an **empty, disposable** database
(the tests drop and recreate all tables):

```bash
TEST_DATABASE_URL=postgresql+asyncpg://analyzer:analyzer@localhost:5432/analyzer_test pytest
```

GitHub is never called by the tests. `respx` intercepts `httpx` and serves realistic payloads
(`tests/factories.py`); `FakeRepository` in `tests/conftest.py` emulates GitHub's pagination,
`Link` headers, `since` filtering and rate-limit headers.

| Test module | Covers |
| --- | --- |
| `test_url.py` | URL/SSH/shorthand parsing and validation |
| `test_github_client.py` | Headers, pagination, counting, ETags, retries, primary and secondary rate limits, 401/403/404/409/204, malformed payloads |
| `test_statistics.py` | Buckets, zero-filling, truncation, trend detection, authors, bus factor, Gini, languages |
| `test_analyzer.py` | End-to-end analysis against the mocked API, degraded contributors, inactive and renamed repos |
| `test_store.py` | Repository upserts (rename, recreation), UTC round-trips, pagination, aggregates, cascades |
| `test_insights.py` | Comparison alignment with gaps, history changes |
| `test_api.py` | Every endpoint, caching, `force`, error envelope and status codes |

### Frontend

```bash
cd frontend
npm test              # Vitest: API client error handling, formatting, input parsing
npm run type-check    # vue-tsc
npm run build
```

### Continuous integration

`.github/workflows/ci.yml` runs lint, strict type checks, migration drift detection
(`alembic upgrade` → `alembic check` → `alembic downgrade`), backend tests against a PostgreSQL
service container with a 90% coverage gate, frontend type-check/tests/build, and finally builds
both Docker images.

## Project structure

```text
.
├── backend
│   ├── alembic/                 # migrations (async env, timestamptz rendering)
│   ├── app
│   │   ├── analysis/            # statistics.py (Pandas) + persisted stat models
│   │   ├── api/                 # routes, dependencies, error handlers
│   │   ├── db/                  # ORM models, AnalysisStore (all SQL), engine
│   │   ├── github/              # REST client, payload models, URL parsing, errors
│   │   ├── services/            # analyzer, analysis service, history/comparison
│   │   ├── config.py            # pydantic-settings
│   │   ├── schemas.py           # API request/response models + mappers
│   │   └── main.py              # app factory and lifespan
│   ├── tests/
│   ├── Dockerfile
│   ├── docker-entrypoint.sh
│   ├── pyproject.toml
│   └── requirements.lock        # pinned runtime dependencies for the image
├── frontend
│   ├── src
│   │   ├── api/                 # typed fetch client + response types
│   │   ├── charts/              # Chart.js registration, shared options, theme colours
│   │   ├── components/          # ChartCard, StatCard, LanguageBar, RepoSearch, …
│   │   ├── composables/         # useAsync (abortable loading state), useTheme
│   │   ├── utils/               # formatting, language grouping, input parsing
│   │   └── views/               # Home, Analysis, History, Repository history, Compare
│   ├── Dockerfile
│   └── nginx.conf
├── docs/screenshots/
├── .github/workflows/ci.yml
├── docker-compose.yml
└── .env.example
```

## Design decisions and limitations

- **Commit list instead of `/stats/*` endpoints.** GitHub's statistics endpoints answer `202`
  while computing and are cached unpredictably. Paging through `/commits` is deterministic and
  allows per-author and per-weekday breakdowns. The cost is the page cap: very active
  repositories are analyzed over a shorter period, which the UI states explicitly.
- **Default branch only.** Commit statistics reflect the default branch, like GitHub's own
  contributor graphs.
- **`open_issues` includes pull requests**, because that is how GitHub's repository endpoint
  counts them; the UI labels it "Open issues & PRs".
- **Contributors are all-time and capped** at `CONTRIBUTORS_MAX_PAGES × 100` stored entries; the
  total count is exact. Concentration metrics are computed over the stored contributors.
- **Snapshots, not polling.** History grows when a repository is analyzed again (a cached result
  is reused for `ANALYSIS_CACHE_TTL_SECONDS`). A scheduled re-analysis job would be a natural
  extension.
- **In-process locks and ETag cache.** They are per API process; with several replicas the
  worst case is a duplicate analysis, never inconsistent data.
- **Accessible charts.** Categorical colours were checked for colour-vision-deficiency
  separation in both themes, every chart has a table view, colours follow the entity (a
  repository keeps its colour when others are removed from a comparison), and no chart uses
  dual axes.

## License

MIT — see [LICENSE](LICENSE).
