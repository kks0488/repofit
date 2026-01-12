import asyncio
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(
    name="gt",
    help="GitHub Trending Analyzer - AI-powered open source discovery",
    no_args_is_help=True,
)
console = Console()


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _write_env_file(path: Path, values: dict[str, str]) -> None:
    lines = [f"{key}={value}" for key, value in values.items()]
    path.write_text("\n".join(lines) + "\n")


@app.command()
def trending(
    language: str | None = typer.Option(None, "--lang", "-l", help="Filter by programming language"),
    since: str = typer.Option("daily", "--since", "-s", help="Time range: daily, weekly, monthly"),
    limit: int = typer.Option(25, "--limit", "-n", help="Number of repositories to show"),
    enrich: bool = typer.Option(True, "--enrich/--no-enrich", help="Fetch additional metadata from GitHub API"),
    analyze: bool = typer.Option(False, "--analyze/--no-analyze", "-a", help="Run AI analysis (requires Gemini API)"),
    save: bool = typer.Option(False, "--save", help="Save results to Supabase"),
) -> None:
    from src.analyzer import analyze_repos
    from src.collector import fetch_trending
    from src.enricher import enrich_repos
    from src.models import EnrichedRepo
    from src.reporter import print_trending
    from src.storage import SupabaseStorage

    async def run() -> None:
        with console.status("[bold green]Fetching trending repositories..."):
            repos = await fetch_trending(language=language, since=since)

        if not repos:
            console.print("[red]No trending repositories found.[/red]")
            raise typer.Exit(1)

        repos = repos[:limit]
        console.print(f"[green]Found {len(repos)} trending repositories[/green]")

        if enrich:
            with console.status("[bold blue]Enriching with GitHub API data..."):
                enriched_repos = await enrich_repos(repos)
        else:
            enriched_repos = [
                EnrichedRepo(
                    rank=r.rank,
                    owner=r.owner,
                    name=r.name,
                    full_name=r.full_name,
                    url=r.url,
                    description=r.description,
                    language=r.language,
                    stars=r.stars,
                    stars_today=r.stars_today,
                    forks=r.forks,
                )
                for r in repos
            ]

        analyzed_repos = enriched_repos
        if analyze:
            with console.status("[bold yellow]Running AI analysis..."):
                analyzed_repos = await analyze_repos(enriched_repos, skip_ai=False)
        else:
            analyzed_repos = await analyze_repos(enriched_repos, skip_ai=True)

        print_trending(analyzed_repos, title=f"Trending ({language or 'All'}, {since})")

        if save:
            with console.status("[bold magenta]Saving to Supabase..."):
                storage = SupabaseStorage()
                snapshot_id = storage.save_snapshot(analyzed_repos, language=language, since=since)
                console.print(f"[green]Saved snapshot: {snapshot_id}[/green]")

    asyncio.run(run())


@app.command()
def inspect(
    repo: str = typer.Argument(..., help="Repository name (owner/repo)"),
    analyze: bool = typer.Option(True, "--analyze/--no-analyze", "-a", help="Run AI analysis"),
) -> None:

    from src.analyzer import analyze_repos
    from src.enricher import enrich_repos
    from src.models import TrendingRepo
    from src.reporter import print_repo_detail

    async def run() -> None:
        if "/" not in repo:
            console.print("[red]Invalid repository format. Use: owner/repo[/red]")
            raise typer.Exit(1)

        owner, name = repo.split("/", 1)

        base_repo = TrendingRepo(
            rank=0,
            owner=owner,
            name=name,
            full_name=repo,
            url=f"https://github.com/{repo}",
        )

        with console.status(f"[bold blue]Fetching {repo}..."):
            enriched = await enrich_repos([base_repo])

        if not enriched:
            console.print(f"[red]Repository {repo} not found.[/red]")
            raise typer.Exit(1)

        with console.status("[bold yellow]Analyzing..."):
            analyzed = await analyze_repos(enriched, skip_ai=not analyze)

        print_repo_detail(analyzed[0])

    asyncio.run(run())


@app.command()
def history(
    repo: str = typer.Argument(..., help="Repository name (owner/repo)"),
    limit: int = typer.Option(30, "--limit", "-n", help="Number of entries to show"),
) -> None:
    from rich.table import Table

    from src.storage import SupabaseStorage

    storage = SupabaseStorage()
    entries = storage.get_repo_history(repo, limit=limit)

    if not entries:
        console.print(f"[yellow]No history found for {repo}[/yellow]")
        raise typer.Exit(0)

    table = Table(title=f":clock1: Trending History: {repo}")
    table.add_column("Date", style="cyan")
    table.add_column("Rank", justify="right")
    table.add_column("Stars", justify="right")
    table.add_column("Stars Today", justify="right")

    for entry in entries:
        table.add_row(
            entry.get("collected_at", "")[:10],
            str(entry.get("rank", "-")),
            str(entry.get("stars", "-")),
            f"+{entry.get('stars_today', 0)}",
        )

    console.print(table)


@app.command()
def snapshots(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of snapshots to show"),
) -> None:
    from rich.table import Table

    from src.storage import SupabaseStorage

    storage = SupabaseStorage()
    snaps = storage.get_snapshots(limit=limit)

    if not snaps:
        console.print("[yellow]No snapshots found[/yellow]")
        raise typer.Exit(0)

    table = Table(title=":camera: Saved Snapshots")
    table.add_column("ID", style="dim", width=36)
    table.add_column("Date", style="cyan")
    table.add_column("Language", style="yellow")
    table.add_column("Period", style="magenta")
    table.add_column("Repos", justify="right")

    for snap in snaps:
        table.add_row(
            snap.get("id", "")[:8],
            snap.get("collected_at", "")[:16],
            snap.get("language") or "All",
            snap.get("since", "daily"),
            str(snap.get("repo_count", 0)),
        )

    console.print(table)


@app.command()
def setup() -> None:
    console.print("[bold]GitHub Trending Analyzer Setup[/bold]\n")

    from src.config import get_settings
    try:
        settings = get_settings()
        console.print("[green]:white_check_mark: Configuration loaded successfully[/green]")
        console.print(f"  Supabase URL: {settings.supabase_url[:50]}...")
        console.print(f"  Gemini Model: {settings.gemini_model}")
        console.print(f"  GitHub Token: {'Set' if settings.github_token else 'Not set (optional)'}")

        slack_configured = bool(settings.slack_bot_token and settings.slack_channel_id)
        slack_status = "Configured" if slack_configured else "Not configured"
        console.print(f"  Slack Bot: {slack_status}")
        if slack_configured:
            console.print(f"    Channel: {settings.slack_channel_id}")
            console.print(f"    Threshold: {settings.slack_notify_threshold}")
    except Exception as e:
        console.print(f"[red]:x: Configuration error: {e}[/red]")
        raise typer.Exit(1)

    console.print("\n[bold]Database Setup[/bold]")
    console.print("Run the following SQL in your Supabase SQL Editor:")
    console.print("[dim]See: schema.sql in the project root[/dim]")


@app.command()
def init(
    force: bool = typer.Option(False, "--force", help="Overwrite generated env files"),
) -> None:
    """Initialize env files and validate Supabase schema."""
    root = Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    env_example_path = root / ".env.example"
    web_env_path = root / "web" / ".env.local"

    if not env_path.exists():
        if env_example_path.exists():
            env_path.write_text(env_example_path.read_text())
            console.print("[yellow]Created .env from .env.example. Update it with your keys.[/yellow]")
        else:
            console.print("[red].env.example not found.[/red]")
            raise typer.Exit(1)
    else:
        console.print("[green].env already exists[/green]")

    env_values = _read_env_file(env_path)
    supabase_url = env_values.get("SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
    supabase_anon = env_values.get("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_ANON_KEY", "")

    if web_env_path.exists() and not force:
        console.print("[green]web/.env.local already exists[/green]")
    elif supabase_url and supabase_anon:
        web_env_path.parent.mkdir(parents=True, exist_ok=True)
        _write_env_file(
            web_env_path,
            {
                "NEXT_PUBLIC_SUPABASE_URL": supabase_url,
                "NEXT_PUBLIC_SUPABASE_ANON_KEY": supabase_anon,
            },
        )
        console.print("[green]Created web/.env.local[/green]")
    else:
        console.print("[yellow]Skipping web/.env.local (missing SUPABASE_URL or SUPABASE_ANON_KEY).[/yellow]")

    from src.config import get_settings
    try:
        _ = get_settings()
    except Exception:
        console.print("[yellow]Fill in .env and rerun `gt init` to validate Supabase.[/yellow]")
        raise typer.Exit(0)

    from src.storage import SupabaseStorage
    try:
        storage = SupabaseStorage()
        storage.get_snapshots(limit=1)
        console.print("[green]Supabase schema looks ready.[/green]")
    except Exception:
        console.print("[yellow]Supabase schema not found. Run schema.sql in Supabase SQL Editor.[/yellow]")

    console.print("Next: run `gt quickstart` to seed data.")


@app.command()
def quickstart(
    language: str | None = typer.Option(None, "--lang", "-l"),
    limit: int = typer.Option(25, "--limit", "-n", help="Number of repositories to fetch"),
    analyze: bool | None = typer.Option(
        None,
        "--analyze/--no-analyze",
        "-a",
        help="Run AI analysis when GEMINI_API_KEY is set",
    ),
) -> None:
    """Seed trending data and optionally generate recommendations."""
    from src.analyzer import analyze_repos
    from src.collector import fetch_trending
    from src.config import get_settings
    from src.enricher import enrich_repos
    from src.matcher import Recommender
    from src.storage import SupabaseStorage

    try:
        settings = get_settings()
    except Exception as exc:
        console.print(f"[red]Configuration error: {exc}[/red]")
        raise typer.Exit(1)

    storage = SupabaseStorage()
    try:
        storage.get_snapshots(limit=1)
    except Exception:
        console.print("[yellow]Supabase schema not found. Run schema.sql in Supabase SQL Editor.[/yellow]")
        raise typer.Exit(1)

    if analyze is None:
        use_ai = bool(settings.gemini_api_key)
    elif analyze and not settings.gemini_api_key:
        console.print("[yellow]GEMINI_API_KEY not set. Running without AI analysis.[/yellow]")
        use_ai = False
    else:
        use_ai = bool(analyze)

    async def run() -> None:
        with console.status("[bold green]Fetching trending..."):
            repos = await fetch_trending(language=language, since="daily")

        if not repos:
            console.print("[red]No trending repositories found.[/red]")
            raise typer.Exit(1)

        repos = repos[:limit]
        with console.status("[bold blue]Enriching..."):
            enriched = await enrich_repos(repos)

        with console.status("[bold yellow]Analyzing..."):
            analyzed = await analyze_repos(enriched, skip_ai=not use_ai)

        with console.status("[bold magenta]Saving to database..."):
            snapshot_id = storage.save_snapshot(analyzed, language=language)
            console.print(f"[green]Saved snapshot: {snapshot_id}[/green]")

        if settings.gemini_api_key:
            with console.status("[bold cyan]Running matching pipeline..."):
                recommender = Recommender()
                result = recommender.run_full_pipeline()
                console.print(f"[green]Generated {result['total_recommendations']} recommendations[/green]")
        else:
            console.print("[yellow]GEMINI_API_KEY not set. Skipping recommendations.[/yellow]")

        console.print("Next steps: `gt recommendations` or `cd web && npm run dev`")

    asyncio.run(run())


@app.command()
def discover(
    project_id: str | None = typer.Option(None, "--project", "-p", help="Project ID to discover for"),
    query: str | None = typer.Option(None, "--query", "-q", help="Custom GitHub search query"),
    limit: int = typer.Option(30, "--limit", "-n", help="Max repositories to return"),
    min_stars: int = typer.Option(50, "--min-stars", help="Minimum stars filter"),
    enrich: bool = typer.Option(True, "--enrich/--no-enrich", help="Fetch additional metadata from GitHub API"),
    analyze: bool | None = typer.Option(
        None,
        "--analyze/--no-analyze",
        "-a",
        help="Run AI analysis when GEMINI_API_KEY is set",
    ),
    save: bool = typer.Option(True, "--save/--no-save", help="Save results to Supabase"),
) -> None:
    """Discover GitHub repositories that fit your projects."""
    from src.analyzer import analyze_repos
    from src.collector import build_project_queries, search_github_repos
    from src.config import get_settings
    from src.enricher import enrich_repos
    from src.models import EnrichedRepo, TrendingRepo
    from src.reporter import print_trending
    from src.storage import SupabaseStorage

    try:
        settings = get_settings()
    except Exception as exc:
        console.print(f"[red]Configuration error: {exc}[/red]")
        raise typer.Exit(1)

    if analyze is None:
        use_ai = bool(settings.gemini_api_key)
    elif analyze and not settings.gemini_api_key:
        console.print("[yellow]GEMINI_API_KEY not set. Running without AI analysis.[/yellow]")
        use_ai = False
    else:
        use_ai = bool(analyze)

    storage = SupabaseStorage()
    queries: list[str] = []

    if query:
        queries = [query]
    else:
        projects = [storage.get_project(project_id)] if project_id else storage.get_projects()
        projects = [p for p in projects if p]
        if not projects:
            console.print("[yellow]No projects found. Add one with gt project-add.[/yellow]")
            raise typer.Exit(0)

        for project in projects:
            queries.extend(build_project_queries(project, min_stars=min_stars))

    queries = list(dict.fromkeys([q.strip() for q in queries if q.strip()]))
    if not queries:
        console.print("[red]No search queries generated.[/red]")
        raise typer.Exit(1)

    per_query = max(5, min(50, limit))
    if len(queries) > 1:
        per_query = max(5, min(50, max(1, limit // len(queries))))

    async def run() -> None:
        all_repos = []
        with console.status("[bold green]Searching GitHub..."):
            for q in queries:
                repos = await search_github_repos(q, per_page=per_query)
                all_repos.extend(repos)

        if not all_repos:
            console.print("[red]No repositories found.[/red]")
            raise typer.Exit(1)

        repo_map: dict[str, TrendingRepo] = {}
        for repo in all_repos:
            existing = repo_map.get(repo.full_name)
            if existing is None or repo.stars > existing.stars:
                repo_map[repo.full_name] = repo

        repos = list(repo_map.values())
        if min_stars > 0:
            repos = [repo for repo in repos if repo.stars >= min_stars]

        repos = sorted(repos, key=lambda r: r.stars, reverse=True)
        repos = repos[:limit]
        for rank, repo in enumerate(repos, start=1):
            repo.rank = rank

        console.print(f"[green]Found {len(repos)} unique repositories[/green]")

        if enrich:
            with console.status("[bold blue]Enriching with GitHub API data..."):
                enriched_repos = await enrich_repos(repos)
        else:
            enriched_repos = [EnrichedRepo(**repo.model_dump()) for repo in repos]

        with console.status("[bold yellow]Analyzing..."):
            analyzed = await analyze_repos(enriched_repos, skip_ai=not use_ai)

        print_trending(analyzed, title="Discover Results")

        if save:
            with console.status("[bold magenta]Saving to database..."):
                storage.upsert_repositories(analyzed)
            console.print("[green]Saved discovered repositories.[/green]")
            console.print("Next: run [cyan]gt match[/cyan] to score against your projects.")

    asyncio.run(run())


# ==================== PROJECT MANAGEMENT ====================

@app.command()
def projects() -> None:
    """List registered projects."""
    from rich.table import Table

    from src.storage import SupabaseStorage

    storage = SupabaseStorage()
    projs = storage.get_projects()

    if not projs:
        console.print("[yellow]No projects registered yet.[/yellow]")
        console.print("Use [cyan]gt project-add[/cyan] to add your first project.")
        raise typer.Exit(0)

    table = Table(title=":package: My Projects")
    table.add_column("ID", style="dim", width=8)
    table.add_column("Name", style="cyan")
    table.add_column("Tech Stack", style="yellow")
    table.add_column("Tags", style="magenta")

    for p in projs:
        table.add_row(
            p.get("id", "")[:8],
            p.get("name", ""),
            ", ".join(p.get("tech_stack", [])[:3]),
            ", ".join(p.get("tags", [])[:3]),
        )

    console.print(table)


@app.command(name="project-add")
def project_add(
    name: str = typer.Option(..., "--name", "-n", prompt="Project name"),
    description: str | None = typer.Option(None, "--desc", "-d"),
    stack: str | None = typer.Option(None, "--stack", "-s", help="Comma-separated tech stack"),
    tags: str | None = typer.Option(None, "--tags", "-t", help="Comma-separated tags"),
    goals: str | None = typer.Option(None, "--goals", "-g"),
) -> None:
    """Register a new project for smart recommendations."""
    from src.storage import SupabaseStorage

    tech_stack = [s.strip() for s in stack.split(",")] if stack else []
    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    storage = SupabaseStorage()
    project = storage.create_project(
        name=name,
        description=description,
        tech_stack=tech_stack,
        tags=tag_list,
        goals=goals,
    )

    console.print(f"[green]:white_check_mark: Project '{name}' created![/green]")
    console.print(f"[dim]ID: {project['id']}[/dim]")
    console.print("\nRun [cyan]gt match[/cyan] to find matching trending repos.")


@app.command()
def match(
    project_id: str | None = typer.Option(None, "--project", "-p", help="Project ID to match"),
    min_stars: int = typer.Option(100, "--min-stars", help="Minimum stars filter"),
    limit: int = typer.Option(10, "--limit", "-n"),
    notify: bool = typer.Option(False, "--notify", help="Send Slack notification for high-score matches"),
    score_threshold: float | None = typer.Option(
        None,
        "--score-threshold",
        help="Minimum score for notification (0.0-1.0)",
    ),
) -> None:
    """Find trending repos that match your projects."""
    from rich.table import Table

    from src.config import get_settings
    from src.matcher import Recommender

    settings = get_settings()
    threshold = score_threshold if score_threshold is not None else settings.slack_notify_threshold

    recommender = Recommender()

    with console.status("[bold blue]Embedding new repos and projects..."):
        recommender.embed_new_repos()
        recommender.embed_new_projects()

    if project_id:
        with console.status("[bold yellow]Finding matches..."):
            recs = recommender.match_project_to_repos(
                project_id=project_id,
                min_stars=min_stars,
                limit=limit,
            )
    else:
        with console.status("[bold yellow]Running full matching pipeline..."):
            result = recommender.run_full_pipeline(
                min_stars=min_stars,
                notify=notify,
                score_threshold=threshold,
            )
            console.print(f"[green]Embedded {result['repos_embedded']} repos, {result['projects_embedded']} projects[/green]")
            console.print(f"[green]Generated {result['total_recommendations']} recommendations[/green]")
            if notify and result.get("notified_count", 0) > 0:
                console.print(f"[cyan]Sent Slack notification for {result['notified_count']} high-score matches[/cyan]")
            elif notify:
                console.print(f"[yellow]No recommendations above threshold ({threshold}), no notification sent[/yellow]")
            return

    if not recs:
        console.print("[yellow]No matches found. Try lowering --min-stars[/yellow]")
        raise typer.Exit(0)

    table = Table(title=":dart: Matching Repositories")
    table.add_column("Score", style="green", width=6)
    table.add_column("Repository", style="cyan")
    table.add_column("Why?", style="yellow")

    for r in recs:
        reasons_text = "; ".join([reason["text"] for reason in r.get("reasons", [])][:2])
        table.add_row(
            f"{r['score']:.2f}",
            r["full_name"],
            reasons_text or "-",
        )

    console.print(table)


@app.command()
def recommendations(
    project_id: str | None = typer.Option(None, "--project", "-p"),
    limit: int = typer.Option(20, "--limit", "-n"),
) -> None:
    """Show AI-powered recommendations."""
    from rich.table import Table

    from src.storage import SupabaseStorage

    storage = SupabaseStorage()
    recs = storage.get_recommendations(project_id=project_id, limit=limit)

    if not recs:
        console.print("[yellow]No recommendations yet.[/yellow]")
        console.print("Run [cyan]gt match[/cyan] first to generate recommendations.")
        raise typer.Exit(0)

    table = Table(title=":bulb: Smart Recommendations")
    table.add_column("Score", style="green", width=6)
    table.add_column("For Project", style="magenta")
    table.add_column("Repo", style="cyan")
    table.add_column("Stars", justify="right")

    for r in recs:
        table.add_row(
            f"{r.get('score', 0):.2f}",
            r.get("project_name", "-"),
            r.get("full_name", "-"),
            str(r.get("stars", 0)),
        )

    console.print(table)


def _next_run_at(hour: int, minute: int) -> datetime:
    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


async def _run_sync_pipeline(
    *,
    language: str | None,
    analyze: bool,
    notify: bool,
    score_threshold: float,
) -> None:
    from src.analyzer import analyze_repos
    from src.collector import fetch_trending
    from src.enricher import enrich_repos
    from src.matcher import Recommender
    from src.notifier import SlackNotifier
    from src.storage import SupabaseStorage

    with console.status("[bold green]Fetching trending..."):
        repos = await fetch_trending(language=language, since="daily")

    console.print(f"[green]Found {len(repos)} trending repos[/green]")

    with console.status("[bold blue]Enriching..."):
        enriched = await enrich_repos(repos)

    with console.status("[bold yellow]Analyzing..."):
        analyzed = await analyze_repos(enriched, skip_ai=not analyze)

    with console.status("[bold magenta]Saving to database..."):
        storage = SupabaseStorage()
        snapshot_id = storage.save_snapshot(analyzed, language=language)
        console.print(f"[green]Saved snapshot: {snapshot_id}[/green]")

    trending_summary = {
        "language": language,
        "total_repos": len(analyzed),
        "top_repos": [
            {
                "full_name": repo.full_name,
                "stars": repo.stars,
                "stars_today": repo.stars_today,
                "language": repo.language,
            }
            for repo in analyzed[:5]
        ],
    }

    with console.status("[bold cyan]Running matching pipeline..."):
        recommender = Recommender()
        result = recommender.run_full_pipeline(
            notify=notify,
            score_threshold=score_threshold,
            trending_summary=trending_summary,
        )
        console.print(f"[green]Generated {result['total_recommendations']} recommendations[/green]")
        if notify and result.get("notified_count", 0) > 0:
            console.print(f"[cyan]Sent Slack notification for {result['notified_count']} high-score matches[/cyan]")
        elif notify:
            notifier = SlackNotifier()
            if notifier.notify_trending_summary(
                total_repos=trending_summary["total_repos"],
                language=trending_summary["language"],
                top_repos=trending_summary["top_repos"],
            ):
                console.print("[cyan]Sent daily Slack summary[/cyan]")

    console.print("\n[bold green]:white_check_mark: Sync complete![/bold green]")
    console.print("View recommendations: [cyan]gt recommendations[/cyan]")
    console.print("Or visit the web UI: [cyan]http://localhost:3003[/cyan]")


@app.command()
def sync(
    language: str | None = typer.Option(None, "--lang", "-l"),
    analyze: bool = typer.Option(True, "--analyze/--no-analyze", "-a"),
    notify: bool = typer.Option(False, "--notify", help="Send Slack notification for high-score matches"),
    score_threshold: float | None = typer.Option(
        None,
        "--score-threshold",
        help="Minimum score for notification (0.0-1.0)",
    ),
) -> None:
    """Full sync: fetch trending, analyze, save, and match."""
    from src.config import get_settings

    settings = get_settings()
    threshold = score_threshold if score_threshold is not None else settings.slack_notify_threshold

    asyncio.run(
        _run_sync_pipeline(
            language=language,
            analyze=analyze,
            notify=notify,
            score_threshold=threshold,
        )
    )


@app.command()
def schedule(
    hour: int = typer.Option(19, "--hour", "-H", help="Local hour to run (0-23)"),
    minute: int = typer.Option(0, "--minute", "-M", help="Local minute to run (0-59)"),
    language: str | None = typer.Option(None, "--lang", "-l"),
    analyze: bool = typer.Option(True, "--analyze/--no-analyze", "-a"),
    notify: bool = typer.Option(True, "--notify/--no-notify", help="Send Slack notification"),
    score_threshold: float | None = typer.Option(
        None,
        "--score-threshold",
        help="Minimum score for notification (0.0-1.0)",
    ),
) -> None:
    """Run daily sync at a fixed local time."""
    from src.config import get_settings

    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        console.print("[red]Invalid time. Use --hour 0-23 and --minute 0-59.[/red]")
        raise typer.Exit(1)

    settings = get_settings()
    threshold = score_threshold if score_threshold is not None else settings.slack_notify_threshold

    console.print(
        f"[green]Scheduler started. Daily sync at {hour:02d}:{minute:02d} (local time).[/green]"
    )
    console.print("[dim]Press Ctrl+C to stop.[/dim]")

    try:
        while True:
            run_at = _next_run_at(hour, minute)
            wait_seconds = max(0, (run_at - datetime.now()).total_seconds())
            console.print(f"[cyan]Next run: {run_at}[/cyan]")
            time.sleep(wait_seconds)
            try:
                asyncio.run(
                    _run_sync_pipeline(
                        language=language,
                        analyze=analyze,
                        notify=notify,
                        score_threshold=threshold,
                    )
                )
            except Exception as exc:
                console.print(f"[red]Scheduled sync failed: {exc}[/red]")
                if notify:
                    try:
                        from src.notifier import SlackNotifier

                        notifier = SlackNotifier()
                        if notifier.is_configured():
                            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            error_text = str(exc)[:200] if str(exc) else "unknown error"
                            notifier.send_message(
                                text=f"RepoFit daily sync failed at {timestamp}: {error_text}"
                            )
                    except Exception as notify_exc:
                        console.print(f"[red]Slack failure notification failed: {notify_exc}[/red]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Scheduler stopped.[/yellow]")


# ==================== AUTO-DISCOVERY ====================

@app.command(name="github-sync")
def github_sync(
    starred: bool = typer.Option(False, "--starred", help="Also show starred repos"),
    private: bool = typer.Option(True, "--private/--public", help="Include private repos"),
) -> None:
    """Sync your GitHub repos as projects."""
    from rich.table import Table

    from src.config import get_settings
    from src.enricher.github_sync import sync_github_repos

    settings = get_settings()
    if not settings.github_token:
        console.print("[red]GITHUB_TOKEN not set. Add it to .env[/red]")
        raise typer.Exit(1)

    with console.status("[bold green]Syncing GitHub repos..."):
        result = sync_github_repos(
            include_starred=starred,
            include_private=private,
        )

    console.print(f"[green]Logged in as: {result['user']}[/green]")
    console.print(f"[green]Found {len(result['repos'])} repos[/green]")
    console.print(f"[cyan]Created {result['created']} new projects[/cyan]")
    console.print(f"[dim]Skipped {result['skipped']} existing[/dim]")

    if result.get("starred"):
        console.print(f"[yellow]Starred repos: {len(result['starred'])}[/yellow]")

    # Show created projects
    if result["created"] > 0:
        table = Table(title="New Projects from GitHub")
        table.add_column("Name", style="cyan")
        table.add_column("Tech Stack", style="yellow")
        table.add_column("Stars", justify="right")

        for repo in result["repos"][:10]:
            from src.enricher.github_sync import extract_tech_stack
            stack = extract_tech_stack(repo)
            table.add_row(
                repo.get("name", ""),
                ", ".join(stack[:3]),
                str(repo.get("stargazers_count", 0)),
            )

        console.print(table)

    console.print("\nNext: run [cyan]gt match[/cyan] to find matching repos.")


@app.command(name="scan-projects")
def scan_projects(
    path: str = typer.Argument("~/projects", help="Path to scan"),
    auto_match: bool = typer.Option(True, "--match/--no-match", help="Auto-run matching after scan"),
) -> None:
    """Scan local folder for projects and auto-register."""
    from rich.table import Table

    from src.scanner import scan_projects_folder

    with console.status(f"[bold green]Scanning {path}..."):
        result = scan_projects_folder(path, auto_sync=True)

    console.print(f"[green]Scanned: {result['path']}[/green]")
    console.print(f"[green]Found {result['count']} projects[/green]")
    console.print(f"[cyan]Created {result.get('created', 0)} new projects[/cyan]")
    console.print(f"[dim]Skipped {result.get('skipped', 0)} existing[/dim]")

    if result.get("recommendations"):
        console.print(f"[yellow]Generated {result['recommendations']} recommendations[/yellow]")

    # Show detected projects
    if result["projects"]:
        table = Table(title="Detected Projects")
        table.add_column("Name", style="cyan")
        table.add_column("Tech Stack", style="yellow")
        table.add_column("Description", style="dim", max_width=40)

        for proj in result["projects"][:15]:
            table.add_row(
                proj.get("name", ""),
                ", ".join(proj.get("tech_stack", [])[:4]),
                (proj.get("description") or "")[:40],
            )

        console.print(table)

    console.print("\nView recommendations: [cyan]gt recommendations[/cyan]")


@app.command()
def bot(
    projects_path: str = typer.Option("~/projects", "--path", "-p", help="Projects folder to scan"),
) -> None:
    """Start Slack auto-reply bot (Socket Mode)."""
    from src.notifier.bot import run_bot

    run_bot(projects_path=projects_path)


if __name__ == "__main__":
    app()
