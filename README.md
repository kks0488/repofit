# RepoFit

AI-powered GitHub Trending analyzer that learns your projects and recommends repos that fit your stack.

## Features

- **Trending Scraper**: GitHub Trending (daily/weekly/monthly) with language filters
- **GitHub Enrichment**: Topics, issues, license, and activity via GitHub API
- **AI Scoring & Summaries**: Gemini analysis with heuristic fallback when AI is disabled
- **Project Profiles**: Register projects with stack, tags, and goals
- **Smart Matching**: Two-stage matcher (pgvector similarity + stack overlap + quality)
- **Snapshots & History**: Save runs and track trending history over time
- **Slack Alerts (Optional)**: Notify on high-score matches
- **Web Dashboard**: Next.js UI for Trending, Projects, and Recommendations

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        RepoFit                               │
│                          │                                   │
│    ┌─────────────────────┼─────────────────────┐            │
│    │                     ▼                     │            │
│    │   ┌──────────┐  ┌──────────┐  ┌────────┐ │            │
│    │   │Collector │→ │ Enricher │→ │Analyzer│ │  Python    │
│    │   │(scraper) │  │(GH API)  │  │(Gemini)│ │  Backend   │
│    │   └──────────┘  └──────────┘  └────────┘ │            │
│    │         │              │           │     │            │
│    │         └──────────────┴───────────┘     │            │
│    │                     │                     │            │
│    │              ┌──────────────┐             │            │
│    │              │   Embedder   │             │            │
│    │              │  (Gemini)    │             │            │
│    │              └──────────────┘             │            │
│    │                     │                     │            │
│    │              ┌──────────────┐             │            │
│    │              │   Matcher    │             │            │
│    │              │ (2-stage)    │             │            │
│    │              └──────────────┘             │            │
│    └─────────────────────┼─────────────────────┘            │
│                          │                                   │
│                          ▼                                   │
│    ┌─────────────────────────────────────────┐              │
│    │           Supabase (PostgreSQL)          │              │
│    │  ┌─────────┐ ┌─────────┐ ┌───────────┐  │              │
│    │  │gt_repos │ │gt_projs │ │ pgvector  │  │              │
│    │  └─────────┘ └─────────┘ └───────────┘  │              │
│    └─────────────────────────────────────────┘              │
│                          │                                   │
│                          ▼                                   │
│    ┌─────────────────────────────────────────┐              │
│    │         Next.js Frontend (web/)          │   Frontend  │
│    │  Dashboard │ Projects │ Recommendations  │              │
│    └─────────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────┘
```

## 5-Minute Quickstart

1. Copy `.env` and fill in Supabase + Gemini keys (Gemini is required for recommendations).
2. Run `gt init` to generate `web/.env.local` (it will warn if the schema is missing).
3. Run `schema.sql` once in Supabase SQL Editor.
4. Run `gt quickstart` to seed trending data (and recommendations if Gemini is set).
5. Start the web app.

```bash
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -e .

gt init
gt quickstart

cd web
npm install
npm run dev
```

## Full Setup

### 1. Environment

Create a `.env` from the template:

```bash
cp .env.example .env
```

### 2. Database Setup

Run `schema.sql` in your Supabase SQL Editor to create tables with `gt_` prefix.
The default schema enables anonymous inserts for `gt_my_projects` and `gt_bookmarks` to keep the web UI frictionless for personal use.
For shared deployments, tighten RLS and move writes behind authenticated or server-side endpoints.

### 3. Backend (CLI)

```bash
cd ~/projects/repofit
python -m venv .venv && source .venv/bin/activate
pip install -e .

# Initialize env files
gt init

# Seed data quickly (uses AI if GEMINI_API_KEY is set)
gt quickstart

# Register your project
gt project-add --name "My App" --stack "python,fastapi,react" --tags "web,api"

# Get smart recommendations
gt match

# Full sync (fetch + analyze + match)
gt sync
```

### 4. Frontend (Web UI)

```bash
cd web
npm install
npm run dev
# Open http://localhost:3003
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `gt init` | Create env files and validate Supabase schema |
| `gt setup` | Validate configuration and show setup hints |
| `gt quickstart` | Seed trending data and recommendations quickly |
| `gt trending` | View trending repos |
| `gt trending --analyze` | With AI analysis |
| `gt trending --save` | Save to database |
| `gt inspect owner/repo` | Detailed repo analysis |
| `gt history owner/repo` | Trending history for a repo |
| `gt snapshots` | List saved trending snapshots |
| `gt projects` | List your projects |
| `gt project-add` | Register a project |
| `gt match` | Find matching repos |
| `gt match --project <id>` | Match a single project |
| `gt recommendations` | View AI recommendations |
| `gt sync` | Full pipeline (fetch → analyze → save → match) |
| `gt match --notify` | Match and send Slack notification |
| `gt sync --notify` | Full pipeline with Slack notification |

## Smart Matching

The recommendation engine uses a 2-stage approach:

1. **Stage 1 - Fast Filter**:
   - Tech stack overlap (languages, frameworks)
   - Keyword matching (tags, topics)
   - Quality threshold (stars, activity)

2. **Stage 2 - Semantic Rerank**:
   - Vector similarity using Gemini embeddings
   - Cosine distance between project ↔ repo embeddings

**Scoring Formula**:
```
score = 0.5 × embedding_similarity 
      + 0.3 × stack_overlap 
      + 0.2 × quality_score
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| CLI | Python, Typer, Rich |
| AI | Google Gemini (analysis + embeddings) |
| Database | Supabase (PostgreSQL + pgvector) |
| Frontend | Next.js 16, React 19, Tailwind CSS 4, React Query |
| HTTP | httpx (async) |

## Environment Variables

```bash
# Backend (.env)
SUPABASE_URL=your-supabase-url
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key
GEMINI_API_KEY=your-gemini-key
GEMINI_MODEL=gemini-2.5-flash-preview-05-20
GITHUB_TOKEN=optional-for-higher-rate-limits

# Slack Bot (optional)
SLACK_BOT_TOKEN=xoxb-xxx
SLACK_CHANNEL_ID=Cxxx
SLACK_NOTIFY_THRESHOLD=0.7

# Frontend (web/.env.local)
NEXT_PUBLIC_SUPABASE_URL=your-supabase-url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

## Daily Automation

Set up a cron job or GitHub Action to run daily:

```bash
# Cron example (every day at 9 AM)
0 9 * * * cd /path/to/repofit && .venv/bin/gt sync --lang python
```

## Slack Notifications

Get notified in Slack when high-scoring recommendations are found.

### Setup

1. **Create Slack App with Bot Token:**
   - Go to [Slack API](https://api.slack.com/apps) → Create New App
   - Add Bot Token Scopes: `chat:write`, `channels:read`
   - Install to Workspace → Copy Bot Token (`xoxb-...`)
   - Invite bot to your channel: `/invite @YourBot`

2. **Configure environment:**
   ```bash
   SLACK_BOT_TOKEN=xoxb-your-bot-token
   SLACK_CHANNEL_ID=C0A1CVD5153
   SLACK_NOTIFY_THRESHOLD=0.7
   ```

3. **Run with notifications:**
   ```bash
   gt match --notify
   gt match --notify --score-threshold 0.8
   gt sync --notify
   ```

### Notification Content

- Count of recommendations above threshold
- Top matching repositories with scores and project names
- First matching reason per repo and GitHub links
- Shortcut to `gt recommendations` and the local web UI

## License

MIT
