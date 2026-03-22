# SeekSpider

A Seek.com.au job scraper system built on the Plombery task scheduling framework, designed for automated collection of Australian IT job listings.

## Features

- **Multi-Region Support** - Scrape jobs from Perth, Sydney, Melbourne, Brisbane, Adelaide, Canberra and more
- **Automated Scraping** - Scheduled crawling of Seek.com.au IT job listings
- **AI Analysis** - Automatic tech stack extraction and salary normalization using AI
- **Web UI** - Visual task management interface powered by Plombery
- **Database Storage** - PostgreSQL/Supabase data persistence
- **Multi-Pipeline Scheduling** - Support for multiple data collection pipelines running in parallel

## Supported Regions

| Region | Seek Location |
|--------|---------------|
| Perth | All Perth WA |
| Sydney | All Sydney NSW |
| Melbourne | All Melbourne VIC |
| Brisbane | All Brisbane QLD |
| Gold Coast | All Gold Coast QLD |
| Adelaide | All Adelaide SA |
| Canberra | All Canberra ACT |
| Hobart | All Hobart TAS |
| Darwin | All Darwin NT |

## Project Structure

```
SeekSpider/
├── pipeline/                    # Pipeline definitions
│   └── src/
│       ├── app.py              # Application entry point
│       ├── seek_spider_pipeline.py     # Seek scraper pipeline
│       ├── flow_meter_pipeline.py      # Flow meter data pipeline
│       └── ...                         # Other pipelines
├── scraper/                     # Scraper modules
│   └── SeekSpider/             # Seek spider
│       ├── spiders/
│       │   └── seek.py         # Main spider logic
│       ├── core/
│       │   ├── config.py       # Configuration management
│       │   ├── database.py     # Database operations
│       │   ├── regions.py      # Australian regions configuration
│       │   └── ai_client.py    # AI API client
│       ├── utils/
│       │   ├── tech_stack_analyzer.py    # Tech stack analysis
│       │   ├── salary_normalizer.py      # Salary normalization
│       │   └── tech_frequency_analyzer.py # Tech frequency statistics
│       ├── scripts/
│       │   └── add_region_column.py      # Database migration script
│       ├── pipelines.py        # Scrapy pipeline
│       └── settings.py         # Scrapy settings
├── src/plombery/               # Plombery core
├── frontend/                   # React frontend
└── .env                        # Environment configuration
```

## Quick Start

### 1. Install Dependencies

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `scraper/.env.example` to `scraper/.env` and fill in your configuration:

```env
# Database configuration (PostgreSQL mode - default)
DATABASE_ENGINE=postgres
POSTGRESQL_HOST=your_host
POSTGRESQL_PORT=5432
POSTGRESQL_USER=your_user
POSTGRESQL_PASSWORD=your_password
POSTGRESQL_DATABASE=your_database
DATABASE_TABLE=seek_jobs
POSTGRESQL_TABLE=seek_jobs

# Backward-compatible aliases are still supported:
# POSTGRES_HOST / POSTGRES_PORT / POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB / POSTGRES_TABLE

# Database configuration (SQLite mode)
# DATABASE_ENGINE=sqlite
# SQLITE_DB_PATH=./data/seek_jobs.db
# DATABASE_TABLE=seek_jobs

# AI API configuration (for post-processing)
# Multiple keys supported (comma-separated) - auto-switches on rate limit or insufficient balance
AI_API_KEYS=key1,key2,key3
AI_API_URL=https://api.siliconflow.cn/v1/chat/completions
AI_MODEL=deepseek-ai/DeepSeek-V2.5
```

Validation behavior:
- `DATABASE_ENGINE=postgres`: requires current PostgreSQL fields and table name.
- `DATABASE_ENGINE=sqlite`: requires `SQLITE_DB_PATH` and table name.

### 3. Run

```bash
# Option 1: Run via Pipeline (recommended)
cd pipeline
./run.sh

# Option 2: Run spider directly for a specific region
cd scraper
scrapy crawl seek -a region=Perth
scrapy crawl seek -a region=Sydney
scrapy crawl seek -a region=Melbourne
```

Access the Web UI at `http://localhost:8000`.

## Run Modes

### SQLite Quick Start (recommended for local)

1. Set `.env` to SQLite mode:

```env
DATABASE_ENGINE=sqlite
SQLITE_DB_PATH=./data/seek_jobs.sqlite3
DATABASE_TABLE=seek_jobs
```

2. Start services (SQLite-first compose):

```bash
docker compose up -d scheduler api
```

3. Verify API:

```bash
curl http://127.0.0.1:6059/health
curl http://127.0.0.1:6059/regions
curl "http://127.0.0.1:6059/jobs?limit=5"
```

Notes:
- SQLite schema is auto-initialized on startup (table + indexes) for empty DB files.
- The DB file is shared between containers through `./data:/app/data`.

### PostgreSQL Compatibility Mode (optional)

1. Set `.env` to PostgreSQL mode:

```env
DATABASE_ENGINE=postgres
POSTGRESQL_HOST=postgres
POSTGRESQL_PORT=5432
POSTGRESQL_USER=seekuser
POSTGRESQL_PASSWORD=seekpass
POSTGRESQL_DATABASE=seekdb
DATABASE_TABLE=seek_jobs
```

2. Start with PostgreSQL profile:

```bash
docker compose --profile postgres up -d
```

3. API remains at:

```bash
http://127.0.0.1:6059
```

## Seek Spider Pipeline

### Capabilities

- Scrapes IT job listings from Seek.com.au across multiple Australian regions
- Covers all IT subcategories (Development, Architecture, DevOps, Testing, etc.)
- Automatically extracts job details (salary, location, job description, etc.)
- AI post-processing: tech stack extraction, salary normalization
- Region-aware job expiry tracking (jobs are marked expired per region)

### Scheduled Tasks

The pipeline is configured with scheduled triggers for each region (Perth timezone):

| Region | Morning | Evening |
|--------|---------|---------|
| Perth | 6:00 AM | 6:00 PM |
| Sydney | 6:15 AM | 6:15 PM |
| Melbourne | 6:30 AM | 6:30 PM |
| Brisbane | 6:45 AM | 6:45 PM |
| Adelaide | 7:00 AM | 7:00 PM |
| Canberra | 7:15 AM | 7:15 PM |

### Configuration Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `region` | Australian region (Perth, Sydney, Melbourne, etc.) | Perth |
| `classification` | Job classification code | 6281 (IT) |
| `run_post_processing` | Run AI post-processing | true |
| `concurrent_requests` | Number of concurrent requests | 16 |
| `download_delay` | Request delay (seconds) | 2.0 |

## Database Schema

The spider stores data in PostgreSQL with the following main fields:

| Field | Description |
|-------|-------------|
| Id | Job ID (Seek Job ID) |
| JobTitle | Job title |
| BusinessName | Company name |
| WorkType | Work type (Full-time/Part-time/Contract) |
| JobType | Job category |
| PayRange | Salary range |
| Region | Australian region (Perth, Sydney, Melbourne, etc.) |
| Area | Detailed region/area |
| Suburb | Detailed location |
| JobDescription | Job description (HTML) |
| TechStack | Tech stack (AI extracted) |
| Url | Job URL |
| PostedDate | Posted date |
| IsActive | Whether the job is active |

### Database Migration

Current migration/initialization paths:

- SQLite: no manual schema migration needed for first run; startup auto-creates `seek_jobs` + indexes.
- PostgreSQL: initialization SQL is in `docker/postgres/init/001-init-seek_jobs.sql` (applied by postgres container entrypoint).
- Backfill job descriptions (both engines):

```bash
cd scraper
python -m SeekSpider.backfill --region Melbourne --limit 100
```

Useful backfill variants:

```bash
python -m SeekSpider.backfill --region-filter Melbourne --workers 3
python -m SeekSpider.backfill --include-inactive --limit 50
```

## Validation Checklist

Run these checks after setup/migration:

1. Spider run creates/updates rows
	- Run spider once for a region and confirm rows exist in `seek_jobs`.
	- Re-run same region and confirm existing IDs are updated (not duplicated).

2. Expiry marking works
	- After a new run, verify jobs not in current scrape are marked inactive for that region.
	- Confirm `IsActive` becomes false/0 and `ExpiryDate` is set.

3. Backfill updates `JobDescription`
	- Run backfill with a small limit.
	- Confirm `JobDescription` is populated for processed rows.

4. API endpoints return expected results
	- `GET /health` returns healthy
	- `GET /regions` returns known regions
	- `GET /jobs` supports filters/pagination/sort
	- `GET /jobs/{id}` returns the expected row

## SQLite Troubleshooting

### `database is locked` / write lock contention

Symptoms:
- Errors like `sqlite3.OperationalError: database is locked`
- Frequent concurrent writers (scraper + backfill + other tools)

Mitigations:
- Prefer a single active writer process when possible.
- Keep write transactions short (already handled in code paths that commit quickly).
- Use WAL mode for better read/write concurrency.

Enable WAL mode:

```bash
sqlite3 ./data/seek_jobs.sqlite3 "PRAGMA journal_mode=WAL;"
sqlite3 ./data/seek_jobs.sqlite3 "PRAGMA synchronous=NORMAL;"
```

Check current mode:

```bash
sqlite3 ./data/seek_jobs.sqlite3 "PRAGMA journal_mode;"
```

Known limitations in SQLite mode:
- Less suitable than PostgreSQL for heavy concurrent write workloads.
- Large backfill + scraping at the same time can increase lock contention.

## Docker Deployment

```bash
# Build and start
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

## Tech Stack

- **Scraping Framework**: Scrapy
- **Task Scheduling**: Plombery (APScheduler)
- **Web Framework**: FastAPI
- **Frontend**: React + Vite
- **Database**: PostgreSQL
- **AI API**: DeepSeek / OpenAI-compatible API

## License

MIT License
