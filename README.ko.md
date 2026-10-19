<p align="center">
  <img src="assets/banner-ko.png" alt="repofit: AI가 고른 GitHub 트렌딩을 내 프로젝트에 맞춰 추천" width="100%">
</p>

<p align="center">
  <a href="README.md"><b>English</b></a> · <b>한국어</b>
</p>

<h2 align="center">GitHub 트렌딩을 매일 뒤지지 마세요.<br>지금 만드는 프로젝트에 맞는 레포만 받아 보세요.</h2>

<p align="center">
  repofit은 매일 GitHub 트렌딩을 골라 Markdown 파일로 저장하고, Mac 알림으로 알려 줍니다.<br>
  매주 한 번은 저장된 레포를 내 프로젝트와 임베딩·기술 스택 기준으로 매칭합니다.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/github/license/kks0488/repofit?color=3fb950" alt="License"></a>
  <a href="https://github.com/kks0488/repofit/stargazers"><img src="https://img.shields.io/github/stars/kks0488/repofit?style=flat&color=58a6ff" alt="Stars"></a>
  <img src="https://img.shields.io/github/languages/top/kks0488/repofit?color=d2a8ff" alt="Top language">
  <img src="https://img.shields.io/github/last-commit/kks0488/repofit?color=8b949e" alt="Last commit">
</p>

<table>
<tr>
<td width="50%" valign="top">

### 그냥 목록이 아닌 큐레이션
트렌딩 레포를 GitHub API로 보강한 뒤 오늘 받은 별 수, 규모 대비 성장, 품질 점수로 순위를 매깁니다. 상위 몇 개만 남깁니다.

</td>
<td width="50%" valign="top">

### "왜 중요한지" 한 줄 요약
OpenAI 호환 모델이 레포마다 요약·활용 예·위험 요소를 씁니다. `--no-analyze`로 AI 없이도 쓸 수 있습니다.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 내 프로젝트와 매칭
프로젝트를 직접 등록하거나, GitHub 계정에서 가져오거나, 로컬 폴더를 스캔합니다. `gt weekly-match`가 스택·키워드로 거른 뒤 pgvector 임베딩으로 다시 정렬합니다.

</td>
<td width="50%" valign="top">

### 일일 파일과 Mac 알림
`gt digest`가 추천 레포·주목할 이유·우리 프로젝트 매칭을 `digests/YYYY-MM-DD.md`에 씁니다. 슬랙 전송은 기본으로 꺼져 있으며, 봇도 선택 사항입니다.

</td>
</tr>
</table>

## 설치

Python 3.11 이상이 필요합니다.

```bash
git clone https://github.com/kks0488/repofit.git && cd repofit
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

## 빠른 시작

**[날짜별 다이제스트 보기](https://github.com/kks0488/repofit/tree/main/digests)** — 서버나 데이터베이스 없이 읽을 수 있습니다.

데이터베이스나 AI 키 없이 오늘의 트렌딩 큐레이션을 볼 수 있습니다(`GITHUB_TOKEN`은 선택이며 API 한도만 늘려 줍니다).

```bash
gt trending --no-analyze -n 10
gt digest --no-analyze       # 오늘의 Markdown 파일과 JSON 스냅샷 저장
```

일일 파일에는 Supabase나 AI 키가 필요하지 않습니다. 아래 웹 UI·등록 프로젝트·주간 임베딩 매칭은 선택 기능입니다.

`gt fit`은 최신 digest(없으면 스냅샷)를 `~/projects/<분류>/<프로젝트>` 문서와 비교해 도입 여부를 판정합니다.
프로필은 설정한 LLM에만 보내며, 비공개 결과는 저장소 밖 `~/.local/share/repofit/fit/YYYY-MM-DD.md`에 저장합니다.
경로는 `--input`, `--projects-dir`, `--out-dir`로 바꾸며, 스킬 추천에는 `npx skilladopt add owner/repo`가 붙습니다.
LLM은 `--llm-base-url/--llm-model/--llm-key-cmd` 또는 `REPOFIT_FIT_BASE_URL`, `REPOFIT_FIT_MODEL`, `REPOFIT_FIT_KEY_CMD`로 설정합니다(기본: Hive·Mac 키체인).

```bash
cp .env.example .env        # Supabase, OpenAI, (선택) Slack 값 입력
gt init                     # env 파일 생성, Supabase 스키마(schema.sql) 확인
gt quickstart               # 첫 큐레이션 스냅샷 저장

gt project-add --name "MyApp" --stack "python,fastapi" --tags "api,web"
gt github-sync              # 또는 내 GitHub 레포를 프로젝트로 가져오기

gt digest                   # 오늘의 Markdown 저장 (--notify를 붙이면 슬랙도 전송)
gt weekly-match             # 저장된 레포를 내 프로젝트와 매칭
```

## 데모

`gt trending --no-analyze` 실제 실행 결과(2026년 10월)와 테스트 실행입니다.

<p align="center"><img src="assets/demo.svg" alt="터미널 데모: gt trending이 GitHub 트렌딩을 가져와 순위표를 출력" width="100%"></p>

## 동작 방식

```mermaid
flowchart LR
    A[GitHub 트렌딩<br/>수집] --> B[GitHub API<br/>보강]
    B --> C[AI 분석<br/>선택]
    C --> J[일일 Markdown<br/>저장소 커밋 + Mac 알림]
    C --> D[(Supabase<br/>+ pgvector)]
    D --> E[선택적 슬랙<br/>--notify]
    D --> F[gt weekly-match<br/>임베딩]
    G[내 프로젝트<br/>직접 · GitHub · 폴더 스캔] --> F
    D --> H[Next.js 웹 UI]
```

- **일일 점수:** `0.5 × 추세(오늘 별 / 250) + 0.3 × 성장(오늘 별 ÷ 전체 별 × 8) + 0.2 × 품질`, 각 항목 최대 1.
- **주간 매칭:** 1단계에서 기술 스택·키워드·품질로 거르고, 2단계에서 임베딩 유사도(`text-embedding-3-small`)로 다시 정렬합니다.
  `score = 0.5 × embedding_similarity + 0.3 × stack_overlap + 0.2 × quality_score`

## 자주 묻는 질문

**OpenAI가 꼭 필요한가요?**
일일 파일과 언어·주제 매칭에는 필요하지 않습니다. AI 요약에는 OpenAI 호환 API가, 주간 임베딩 매칭에는 `OPENAI_EMBEDDING_API_KEY`가 필요합니다.

**왜 Supabase인가요?**
웹 UI·등록 프로젝트·주간 임베딩 매칭용 선택 기능입니다. 일일 파일에는 쓰지 않습니다. 사용하려면 Supabase SQL 편집기에서 `schema.sql`을 한 번 실행하세요.

**정해진 시간에 자동으로 돌릴 수 있나요?**
네. `gt schedule`(계속 실행), `scripts/`의 systemd 타이머, cron, GitHub Actions 중 하나를 쓰면 됩니다. 아래 기술 세부 사항을 보세요.

## 로드맵 (계획, 아직 구현 안 됨)

- `pipx install`용 CLI 패키지.
- 슬랙 다이제스트의 언어·주제 필터.
- 웹 UI 공개 데모.

---

<details>
<summary><b>기술 세부 사항</b></summary>

### CLI 명령

| 명령 | 설명 |
|------|------|
| `gt init` | env 파일 생성, Supabase 스키마 확인 |
| `gt setup` | 설정 확인과 안내 |
| `gt quickstart` | 일일 큐레이션 데이터 빠르게 저장 |
| `gt` / `gt trending` | 오늘의 트렌딩 큐레이션 보기(`--lang`, `--since`, `-n`, `--no-enrich`, `--no-analyze`, `--save`) |
| `gt digest` | 오늘의 Markdown·프로젝트 매칭 저장 (`--notify`로 슬랙 추가) |
| `gt inspect owner/repo` | 레포 상세 분석 |
| `gt history owner/repo` | 레포의 트렌딩 이력 |
| `gt snapshots` | 저장된 스냅샷 목록 |
| `gt projects` | 내 프로젝트 목록 |
| `gt project-add` | 프로젝트 등록 |
| `gt github-sync` | 내 GitHub 레포를 프로젝트로 동기화(`--starred`는 별표 레포도 표시) |
| `gt scan-projects ~/projects` | 로컬 폴더에서 프로젝트 찾기 |
| `gt weekly-match` | 전체 프로젝트 주간 매칭(`--project <id>`로 하나만) |
| `gt match` | `gt weekly-match`의 별칭 |
| `gt recommendations` | AI 추천 보기 |
| `gt discover` | 내 프로젝트에 맞는 레포를 GitHub에서 검색 |
| `gt sync` | 일일 동기화(수집 → 분석 → 저장), `--notify`면 다이제스트도 전송 |
| `gt schedule` | 정해진 시각(기본 19:00)에 일일 동기화 |
| `gt bot` | 슬랙 자동 응답 봇 시작(Socket Mode) |

### 환경 변수

```bash
# 백엔드 (.env)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-key
OPENAI_API_KEY=your-openai-key
OPENAI_BASE_URL=https://api.openai.com/v1   # OpenAI 호환 엔드포인트
OPENAI_MODEL=gpt-5.2
OPENAI_EMBEDDING_API_KEY=your-openai-embedding-key
GITHUB_TOKEN=your-github-token              # github-sync, API 한도 증가

# 슬랙 (선택)
SLACK_BOT_TOKEN=xoxb-xxx
SLACK_APP_TOKEN=xapp-xxx                    # Socket Mode, gt bot용
SLACK_CHANNEL_ID=C0123456789
SLACK_NOTIFY_THRESHOLD=0.7

# 프런트엔드 (web/.env.local)
NEXT_PUBLIC_SUPABASE_URL=your-supabase-url
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

`OPENAI_BASE_URL`을 비워 두면 코드 기본값은 로컬 OpenAI 호환 프록시(`http://localhost:8317/v1`)입니다. OpenAI API를 쓸 때는 직접 지정하세요.

### 슬랙 설정 (선택, 기본 꺼짐)

1. [api.slack.com/apps](https://api.slack.com/apps)에서 앱을 만들고 봇 토큰 권한 `chat:write`, `channels:read`, `channels:history`를 추가합니다. 설치 후 `xoxb-` 토큰을 복사하고 채널에서 `/invite @YourBot`.
2. 봇을 쓰려면 Socket Mode를 켜고 `connections:write` 권한의 앱 토큰(`xapp-`)을 만든 뒤, 이벤트에서 `message.channels`, `app_mention`을 구독합니다.
3. 토큰과 채널 ID를 `.env`에 넣습니다.

채널이나 스레드에 입력하는 봇 명령:

| 메시지 | 동작 |
|--------|------|
| `스캔` / `scan` | 프로젝트 폴더 스캔 → 등록 → 매칭 |
| `추천` / `recommend` | 추천 결과 전송 |
| `트렌딩` / `trending` | 트렌딩 TOP 10 전송 |
| `매칭` / `match` | 매칭 실행 후 결과 전송 |

그 밖의 질문에는 저장된 레포 데이터를 검색해 답합니다(langchain + pgvector).

다이제스트 형태 예시(가상의 레포):

```
📌 RepoFit Daily Trending Curation
🌐 All languages • 10 picks from 25 trending repos
────────────────────────────
*AI/ML*
  owner/repo-a ⭐ 12,421 · +684 today ⚡ Rising fast
  Why: High-velocity open-source agent framework with practical tooling.
────────────────────────────
Top 10 only: highest momentum + quality signals
```

### 일일 자동화

systemd 사용자 타이머:

```bash
mkdir -p ~/.config/systemd/user
cp scripts/repofit-daily.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now repofit-daily.timer
```

cron:

```bash
0 19 * * * cd /path/to/repofit && ./scripts/daily-digest.sh   # 매일 다이제스트
0 9 * * 1 cd /path/to/repofit && ./scripts/weekly-match.sh    # 월요일 주간 매칭
```

GitHub Actions: `.github/workflows/daily-sync.yml`이 매일 **한국 시간 07:17**(UTC 전날 22:17)에
실행되어 `digests/YYYY-MM-DD.md`를 한국 날짜로 커밋합니다. 추천 레포·주목할 이유와 함께
계정 소유자의 공개 프로젝트 중 보관 처리·포크를 제외하고 언어 외 주제·키워드가 겹치는 프로젝트를 레포당 최대 3개 보여 줍니다.
실제 적용을 검증한 결과는 아닙니다. 데이터베이스·슬랙·AI 키 없이 실행되며, 선택적으로
`NEBIUS_API_KEY` 또는 `OPENAI_API_KEY` 시크릿을 넣으면 AI 요약을 씁니다.
JSON과 Markdown 파일은 실행 기록에도 90일간 보관됩니다.

사장님 Mac의 `~/Library/LaunchAgents/com.kks.repofit-notify.plist`가 매일 **현지 시간 08:07**에
`scripts/repofit-notify.sh`를 실행합니다. 최신 `main`을 받아 `gt fit`을 실행하고 도입 추천 최대 2개(없거나 실패하면 상위 레포 3개)를
**repofit 오늘의 오픈소스** 알림으로 표시합니다. GitHub 실행이 늦으면 가장 최근 파일의 날짜를 함께 표시합니다.
스크립트를 직접 실행해 시험할 수 있으며, 배너 표시는 macOS 알림 설정을 따릅니다.
슬랙은 `gt digest --notify`, `gt sync --notify` 또는 직접 켠 `gt bot`으로만 사용합니다.

### 웹 UI

```bash
cd web
npm install
npm run dev   # http://localhost:3003
```

최신 트렌딩, 내 프로젝트(추가·목록), 추천 화면이 있으며 모두 Supabase에서 읽습니다.

### 기술 스택

| 구성 | 기술 |
|------|------|
| CLI | Python, Typer, Rich |
| AI | OpenAI 호환 API(분석 + 임베딩), langchain |
| 데이터베이스 | Supabase(PostgreSQL + pgvector) |
| 프런트엔드 | Next.js 16, React 19, Tailwind CSS 4, TanStack Query |
| HTTP / 수집 | httpx(async), selectolax |
| 전달 | 일일 Markdown 커밋, macOS 알림; 선택적 슬랙 |

### 테스트

```bash
pip install -e ".[dev]"
pytest -q
```

### 문제 해결

- **스키마 없음:** Supabase SQL 편집기에서 `schema.sql` 실행.
- **추천 없음:** `OPENAI_EMBEDDING_API_KEY` 설정 후 `gt weekly-match`.
- **슬랙 안 됨:** `SLACK_BOT_TOKEN`, `SLACK_CHANNEL_ID` 확인.
- **프로젝트 매칭 없음:** 먼저 `gt project-add`로 프로젝트 등록.
- **GitHub 동기화 실패:** `GITHUB_TOKEN` 권한(repo) 확인.

</details>

## 라이선스

[MIT](LICENSE) © 2026 Kyoungsoo Kim
