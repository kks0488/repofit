import asyncio
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(
    name="gt",
    help="GitHub Trending Analyzer - AI-powered open source discovery",
    no_args_is_help=True,
)
console = Console()


@app.command()
def trending(
    language: Optional[str] = typer.Option(None, "--lang", "-l", help="Filter by programming language"),
    since: str = typer.Option("daily", "--since", "-s", help="Time range: daily, weekly, monthly"),
    limit: int = typer.Option(25, "--limit", "-n", help="Number of repositories to show"),
    enrich: bool = typer.Option(True, "--enrich/--no-enrich", help="Fetch additional metadata from GitHub API"),
    analyze: bool = typer.Option(False, "--analyze/--no-analyze", "-a", help="Run AI analysis (requires Gemini API)"),
    save: bool = typer.Option(False, "--save", help="Save results to Supabase"),
) -> None:
    from src.collector import fetch_trending
    from src.enricher import enrich_repos
    from src.analyzer import analyze_repos
    from src.reporter import print_trending
    from src.storage import SupabaseStorage
    from src.models import EnrichedRepo

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
    import httpx
    from datetime import datetime, timezone

    from src.models import TrendingRepo, EnrichedRepo
    from src.enricher import enrich_repos
    from src.analyzer import analyze_repos
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
    description: Optional[str] = typer.Option(None, "--desc", "-d"),
    stack: Optional[str] = typer.Option(None, "--stack", "-s", help="Comma-separated tech stack"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="Comma-separated tags"),
    goals: Optional[str] = typer.Option(None, "--goals", "-g"),
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
    project_id: Optional[str] = typer.Option(None, "--project", "-p", help="Project ID to match"),
    min_stars: int = typer.Option(100, "--min-stars", help="Minimum stars filter"),
    limit: int = typer.Option(10, "--limit", "-n"),
    notify: bool = typer.Option(False, "--notify", help="Send Slack notification for high-score matches"),
    score_threshold: float = typer.Option(0.7, "--score-threshold", help="Minimum score for notification (0.0-1.0)"),
) -> None:
    """Find trending repos that match your projects."""
    from rich.table import Table
    from src.matcher import Recommender

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
                score_threshold=score_threshold,
            )
            console.print(f"[green]Embedded {result['repos_embedded']} repos, {result['projects_embedded']} projects[/green]")
            console.print(f"[green]Generated {result['total_recommendations']} recommendations[/green]")
            if notify and result.get("notified_count", 0) > 0:
                console.print(f"[cyan]Sent Slack notification for {result['notified_count']} high-score matches[/cyan]")
            elif notify:
                console.print(f"[yellow]No recommendations above threshold ({score_threshold}), no notification sent[/yellow]")
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
    project_id: Optional[str] = typer.Option(None, "--project", "-p"),
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


@app.command()
def sync(
    language: Optional[str] = typer.Option(None, "--lang", "-l"),
    analyze: bool = typer.Option(True, "--analyze/--no-analyze", "-a"),
    notify: bool = typer.Option(False, "--notify", help="Send Slack notification for high-score matches"),
    score_threshold: float = typer.Option(0.7, "--score-threshold", help="Minimum score for notification (0.0-1.0)"),
) -> None:
    """Full sync: fetch trending, analyze, save, and match."""
    from src.collector import fetch_trending
    from src.enricher import enrich_repos
    from src.analyzer import analyze_repos
    from src.storage import SupabaseStorage
    from src.matcher import Recommender

    async def run() -> None:
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

        with console.status("[bold cyan]Running matching pipeline..."):
            recommender = Recommender()
            result = recommender.run_full_pipeline(
                notify=notify,
                score_threshold=score_threshold,
            )
            console.print(f"[green]Generated {result['total_recommendations']} recommendations[/green]")
            if notify and result.get("notified_count", 0) > 0:
                console.print(f"[cyan]Sent Slack notification for {result['notified_count']} high-score matches[/cyan]")

        console.print("\n[bold green]:white_check_mark: Sync complete![/bold green]")
        console.print("View recommendations: [cyan]gt recommendations[/cyan]")
        console.print("Or visit the web UI: [cyan]http://localhost:3003[/cyan]")

    asyncio.run(run())


if __name__ == "__main__":
    app()
