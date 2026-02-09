# RepoFit

AI-curated GitHub trending digest - daily curation + weekly project matching

## Features

### Core Features
- **Daily Trending Curation (Primary)**: AI-scored, category-grouped picks from GitHub Trending
- **AI "Why it matters" Summaries**: One-line rationale per repo in Slack digest
- **Rising Fast Signals**: Detects repos with unusually high `stars_today / total_stars`
- **Weekly Project Matching (Secondary)**: Deeper project-to-repo matching pass
- **Snapshots & History**: Save daily runs and track trend movement over time

### Slack & Bot
- **Slack Daily Digest**: Send curated top picks immediately with `gt digest`
- **Weekly Match Alerts**: Optional Slack notifications for high-score weekly matches
- **RAG-powered Bot**: AI answers using stored repo data (langchain + OpenAI)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        RepoFit                               │
│                          │                                   │
│    ┌─────────────────────┼─────────────────────┐            │
│    │                     ▼                     │            │
│    │   ┌──────────┐  ┌──────────┐  ┌────────┐ │            │
│    │   │Collector │→ │ Enricher │→ │Analyzer│ │  Python    │
│    │   │(scraper) │  │(GH API)  │  │(OpenAI)│ │  Backend   │
│    │   └──────────┘  └──────────┘  └────────┘ │            │
│    │         │              │           │     │            │
│    │         └──────────────┴───────────┘     │            │
│    │                     │                     │            │
│    │              ┌──────────────┐             │            │
│    │              │   Embedder   │             │            │
│    │              │  (OpenAI)    │             │            │
│    │              └──────────────┘             │            │
│    │                     │                     │            │
│    │              ┌──────────────┐             │            │
│    │              │   Matcher    │             │            │
│    │              │  (2-stage)   │             │            │
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
│              ┌───────────┴───────────┐                      │
│              ▼                       ▼                      │
│    ┌─────────────────┐    ┌─────────────────┐              │
│    │  Next.js Web UI │    │  Slack Notifier │              │
│    └─────────────────┘    └─────────────────┘              │
└─────────────────────────────────────────────────────────────┘
```

## 5-Minute Quickstart

```bash
cp .env.example .env
python -m venv .venv && source .venv/bin/activate
pip install -e .

gt init
gt quickstart

# Register your project
gt project-add --name "MyApp" --stack "python,fastapi" --tags "api,web"

# Or sync from GitHub
gt github-sync

# Send daily curated digest to Slack
gt digest

# Run deeper weekly project matching
gt weekly-match
```

## CLI Commands

### Core Commands

| Command | Description |
|---------|-------------|
| `gt init` | Create env files and validate Supabase schema |
| `gt setup` | Validate configuration and show setup hints |
| `gt quickstart` | Seed daily curation data quickly |
| `gt` | Default command, same as `gt trending` |
| `gt trending` | View daily curated trending repos |
| `gt digest` | Send daily curated Slack digest immediately |
| `gt inspect owner/repo` | Detailed repo analysis |
| `gt history owner/repo` | Trending history for a repo |
| `gt snapshots` | List saved trending snapshots |

### Project Management

| Command | Description |
|---------|-------------|
| `gt projects` | List your projects |
| `gt project-add` | Register a project |
| `gt github-sync` | Sync your GitHub repos as projects |
| `gt github-sync --starred` | Also show starred repos |
| `gt scan-projects ~/projects` | Scan local folder for projects |
| `gt weekly-match` | Thorough weekly matching for all projects |
| `gt weekly-match --project <id>` | Weekly match for one project |
| `gt match` | Compatibility alias for `gt weekly-match` |
| `gt recommendations` | View AI recommendations |
| `gt discover` | Discover GitHub repos that fit your projects |

### Automation

| Command | Description |
|---------|-------------|
| `gt sync` | Daily curation sync (fetch → analyze → save) |
| `gt sync --notify` | Daily curation sync + Slack digest |
| `gt schedule` | Run daily curation sync at a fixed local time (default 19:00) |
| `gt bot` | Start Slack auto-reply bot (requires Socket Mode) |

## Weekly Project Matching

`gt weekly-match` uses a 2-stage approach across stored repositories:

1. **Stage 1 - Fast Filter**:
   - Tech stack overlap (languages, frameworks)
   - Keyword matching (tags, topics)
   - Quality threshold (stars, activity)

2. **Stage 2 - Semantic Rerank**:
   - Vector similarity using OpenAI embeddings
   - Cosine distance between project ↔ repo embeddings

**Scoring Formula**:
```
score = 0.5 × embedding_similarity
      + 0.3 × stack_overlap
      + 0.2 × quality_score
```

## Slack Notifications

### Setup

1. **Create Slack App with Bot Token:**
   - Go to [Slack API](https://api.slack.com/apps) → Create New App
   - Add Bot Token Scopes: `chat:write`, `channels:read`, `channels:history`
   - Install to Workspace → Copy Bot Token (`xoxb-...`)
   - Invite bot to your channel: `/invite @YourBot`

2. **Enable Socket Mode (for auto-reply bot):**
   - Slack App Settings → Socket Mode → Enable
   - Create App-Level Token with `connections:write` scope
   - Copy the token (`xapp-...`)
   - Event Subscriptions → Enable Events
   - Subscribe to bot events: `message.channels`, `app_mention`

3. **Configure environment:**
   ```bash
   SLACK_BOT_TOKEN=xoxb-your-bot-token
   SLACK_APP_TOKEN=xapp-your-app-token  # Socket Mode용
   SLACK_CHANNEL_ID=C0A1CVD5153
   SLACK_NOTIFY_THRESHOLD=0.7
   ```

### Slack Bot (RAG-powered)

RepoFit 봇은 langchain + OpenAI + pgvector를 사용하여 저장된 레포 데이터를 검색하고 더 정확한 답변을 제공합니다.

```bash
gt bot  # 봇 시작 (백그라운드로 실행 권장)
```

**채널 명령어 (새 메시지로 결과 전송):**

| 채널/스레드에 입력 | 동작 |
|------------------|------|
| `스캔` / `scan` | 프로젝트 폴더 스캔 → 등록 → 매칭 |
| `추천` / `recommend` | 추천 결과 → 채널에 새 메시지 |
| `트렌딩` / `trending` | 트렌딩 TOP 10 → 채널에 새 메시지 |
| `매칭` / `match` | 매칭 실행 → 결과 채널에 |

**일반 질문 (RAG 응답):**
```
[Slack 스레드]
├─ 🤖 RepoFit: 📊 오늘의 다이제스트...
├─ 👤 나: "fastapi랑 langchain 조합하면 뭐 만들 수 있어?"
└─ 🤖 RepoFit: (저장된 레포 정보 검색 후 구체적 답변)
```

### Sample Daily Digest

```
📌 RepoFit Daily Trending Curation
🌐 All languages • 10 picks from 25 trending repos
────────────────────────────
*AI/ML*
  owner/repo-a ⭐ 12,421 · +684 today ⚡ Rising fast
  Why: High-velocity open-source agent framework with practical tooling.
────────────────────────────
*Frontend*
  owner/repo-b ⭐ 8,130 · +311 today
  Why: Solves real production UI performance bottlenecks.
────────────────────────────
Top 10 only: highest momentum + quality signals
```

### Daily Notifications

```bash
# One-off run (send curated daily digest immediately)
gt digest

# Daily schedule at 19:00 local time (keep process running)
gt schedule --hour 19 --minute 0 --notify

# Weekly match run
gt weekly-match --notify
```

## Environment Variables

```bash
# Backend (.env)
SUPABASE_URL=your-supabase-url
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key
OPENAI_API_KEY=your-openai-key
OPENAI_BASE_URL=http://100.68.66.51:8317/v1
OPENAI_MODEL=gpt-5.2
OPENAI_EMBEDDING_API_KEY=your-openai-embedding-key
GITHUB_TOKEN=your-github-token  # For github-sync

# Slack Bot (optional but recommended)
SLACK_BOT_TOKEN=xoxb-xxx
SLACK_APP_TOKEN=xapp-xxx  # Socket Mode
SLACK_CHANNEL_ID=Cxxx
SLACK_NOTIFY_THRESHOLD=0.7

# Frontend (web/.env.local)
NEXT_PUBLIC_SUPABASE_URL=your-supabase-url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

## Daily Automation

### systemd (recommended)

```bash
mkdir -p ~/.config/systemd/user
cp scripts/repofit-daily.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now repofit-daily.timer
```

To change the time, edit `~/.config/systemd/user/repofit-daily.timer` and update `OnCalendar=`.

### Cron Job

```bash
# Every day at 7 PM - full digest
0 19 * * * cd /path/to/repofit && ./scripts/daily-digest.sh

# Every Monday at 9 AM - weekly project matching
0 9 * * 1 cd /path/to/repofit && ./scripts/weekly-match.sh
```

### GitHub Actions

Use `.github/workflows/daily-sync.yml` with secrets:
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_KEY`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID`

## Tech Stack

| Component | Technology |
|-----------|------------|
| CLI | Python, Typer, Rich |
| AI | OpenAI-compatible API (analysis + embeddings) |
| AI SDK | openai, langchain |
| RAG | langchain + pgvector retrieval |
| Database | Supabase (PostgreSQL + pgvector) |
| Frontend | Next.js 16, React 19, Tailwind CSS 4 |
| HTTP | httpx (async) |
| Notifications | Slack Block Kit, slack-bolt (Socket Mode) |

## Troubleshooting

- **Schema missing**: Run `schema.sql` in Supabase SQL Editor
- **No recommendations**: Set `OPENAI_EMBEDDING_API_KEY`, then run `gt weekly-match`
- **Slack not working**: Check `SLACK_BOT_TOKEN` and `SLACK_CHANNEL_ID`
- **No project matches**: Register projects with `gt project-add` first, then run `gt weekly-match`
- **GitHub sync fails**: Check `GITHUB_TOKEN` permissions (repo scope)

## License

MIT
