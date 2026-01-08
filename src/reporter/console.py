from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.models import AnalyzedRepo

console = Console()

SCORE_COLORS = {
    "excellent": "green",
    "good": "yellow",
    "fair": "orange1",
    "poor": "red",
}


def _score_to_color(score: int) -> str:
    if score >= 80:
        return SCORE_COLORS["excellent"]
    elif score >= 60:
        return SCORE_COLORS["good"]
    elif score >= 40:
        return SCORE_COLORS["fair"]
    return SCORE_COLORS["poor"]


def _score_to_emoji(score: int) -> str:
    if score >= 80:
        return "[green]A[/green]"
    elif score >= 60:
        return "[yellow]B[/yellow]"
    elif score >= 40:
        return "[orange1]C[/orange1]"
    return "[red]D[/red]"


def _format_number(n: int) -> str:
    if n >= 1000:
        return f"{n/1000:.1f}k"
    return str(n)


def print_trending(repos: list[AnalyzedRepo], title: str = "GitHub Trending") -> None:
    table = Table(title=f":fire: {title}", show_header=True, header_style="bold magenta")

    table.add_column("#", style="dim", width=3)
    table.add_column("Repository", style="cyan", min_width=30)
    table.add_column("Lang", style="yellow", width=12)
    table.add_column(":star:", justify="right", width=8)
    table.add_column(":chart_increasing:", justify="right", width=6)
    table.add_column("Score", justify="center", width=6)
    table.add_column("Status", justify="center", width=8)

    for repo in repos:
        score_display = _score_to_emoji(repo.overall_score)
        status = "[green]Active[/green]" if repo.is_active else "[red]Stale[/red]"
        stars_today = f"+{repo.stars_today}" if repo.stars_today > 0 else "-"

        table.add_row(
            str(repo.rank),
            f"[link={repo.url}]{repo.full_name}[/link]",
            repo.language or "-",
            _format_number(repo.stars),
            stars_today,
            score_display,
            status,
        )

    console.print(table)
    console.print()


def print_repo_detail(repo: AnalyzedRepo) -> None:
    title = f":package: {repo.full_name}"

    info_text = Text()
    info_text.append(f"Stars: ", style="bold")
    info_text.append(f"{_format_number(repo.stars)} ", style="yellow")
    info_text.append(f"(+{repo.stars_today} today)\n", style="green")

    info_text.append(f"Forks: ", style="bold")
    info_text.append(f"{_format_number(repo.forks)}\n", style="cyan")

    info_text.append(f"Language: ", style="bold")
    info_text.append(f"{repo.language or 'Unknown'}\n", style="magenta")

    info_text.append(f"License: ", style="bold")
    info_text.append(f"{repo.license or 'Unknown'}\n", style="blue")

    if repo.topics:
        info_text.append(f"Topics: ", style="bold")
        info_text.append(f"{', '.join(repo.topics[:5])}\n", style="dim")

    console.print(Panel(info_text, title=title, border_style="blue"))

    scores_table = Table(show_header=False, box=None)
    scores_table.add_column("Metric", style="bold")
    scores_table.add_column("Score", justify="right")
    scores_table.add_column("Bar", width=20)

    for name, score in [
        ("Overall", repo.overall_score),
        ("Health", repo.health_score),
        ("Activity", repo.activity_score),
        ("Community", repo.community_score),
        ("Documentation", repo.documentation_score),
    ]:
        color = _score_to_color(score)
        bar_len = int(score / 5)
        bar = f"[{color}]{'█' * bar_len}[/{color}]{'░' * (20 - bar_len)}"
        scores_table.add_row(name, f"[{color}]{score}[/{color}]", bar)

    console.print(Panel(scores_table, title=":chart_with_upwards_trend: Scores", border_style="green"))

    if repo.summary:
        console.print(Panel(repo.summary, title=":bulb: Summary", border_style="yellow"))

    if repo.use_cases:
        use_cases_text = "\n".join([f"• {uc}" for uc in repo.use_cases])
        console.print(Panel(use_cases_text, title=":dart: Use Cases", border_style="cyan"))

    if repo.integration_tips:
        console.print(Panel(repo.integration_tips, title=":wrench: Integration Tips", border_style="magenta"))

    if repo.potential_risks:
        risks_text = "\n".join([f"⚠️  {risk}" for risk in repo.potential_risks])
        console.print(Panel(risks_text, title=":warning: Potential Risks", border_style="red"))
