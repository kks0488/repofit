"""Preview curated skills in disposable project copies, never in the original project."""

import json
import os
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from urllib.parse import quote

import httpx

from src.analyzer.fit import REPO_NAME, load_repos
from src.utils import build_github_api_headers

SKILLADOPT_VERSION = "0.1.11"


@contextmanager
def measure(timings: dict[str, float], stage: str):
    """Include failed stages as well as successful ones in elapsed time."""
    started = time.perf_counter()
    try:
        yield
    finally:
        timings[stage] = timings.get(stage, 0.0) + time.perf_counter() - started


def github_headers() -> dict[str, str]:
    headers = build_github_api_headers()
    if "Authorization" not in headers:
        token = os.environ.get("GH_TOKEN", "")
        if not token:
            try:
                token = subprocess.run(
                    ["gh", "auth", "token"], capture_output=True, text=True, check=True,
                    timeout=10,
                ).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                pass
        if token:
            headers["Authorization"] = f"Bearer {token}"
    return headers


def load_candidates(
    source: Path | None, repos: str | None, weekly: bool = False,
) -> list[dict]:
    if sum((source is not None, repos is not None, weekly)) > 1:
        raise ValueError("Choose only one of --input, --repos or --weekly-match")
    if repos is not None:
        rows = [{"full_name": name.strip()} for name in repos.split(",")]
    elif weekly:
        from src.storage import SupabaseStorage

        # This is the stored matching snapshot. recommended_at is the row's creation date,
        # not its latest matching run: upserts can recompute a row from an earlier week.
        rows = SupabaseStorage().get_recommendations(limit=1000)
    elif source is not None and source.suffix == ".json":
        payload = json.loads(source.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            rows = payload
        elif "recommendations" in payload:
            rows = payload["recommendations"]
        else:
            _, rows = load_repos(source)
    else:
        _, rows = load_repos(source)
    unique = {}
    for row in rows:
        name = row.get("full_name", "")
        if not isinstance(name, str) or not REPO_NAME.fullmatch(name):
            raise ValueError("Invalid repository name")
        # Preserve the highest-ranked project's match for each source repository.
        unique.setdefault(name.casefold(), row)
    if not unique:
        raise ValueError("No selected repositories; provide --repos or a current digest")
    return list(unique.values())


def discover_skills(client: httpx.Client, repo: str) -> tuple[str, list[str]]:
    base = f"https://api.github.com/repos/{repo}"
    response = client.get(f"{base}/commits/HEAD")
    response.raise_for_status()
    commit = response.json()["sha"]
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid source commit")
    response = client.get(f"{base}/git/trees/{commit}", params={"recursive": "1"})
    response.raise_for_status()
    tree = response.json()
    if tree.get("truncated"):
        raise ValueError("GitHub tree truncated; skill discovery is incomplete")
    paths = []
    for entry in tree["tree"]:
        path = entry["path"]
        parts = PurePosixPath(path).parts
        if (entry.get("type") == "blob" and entry.get("mode") in {"100644", "100755"}
                and parts and parts[-1] == "SKILL.md"):
            if path.startswith("/") or any(p in {"", ".", ".."} for p in path.split("/")):
                raise ValueError("Invalid skill path")
            paths.append(path)
    return commit, sorted(set(paths))


def target_for(row: dict, fallback: Path | None, projects_dir: Path) -> Path:
    if row.get("project_path"):
        return Path(row["project_path"]).expanduser().resolve(strict=True)
    name = row.get("project_name")
    if name:
        root = projects_dir.expanduser().resolve()
        # Names in weekly results are data, never arbitrary paths to open.
        if isinstance(name, str) and re.fullmatch(r"[\w.-]+", name) and name not in {".", ".."}:
            matches = [p for p in (root / name, *root.glob(f"*/{name}")) if (p / ".git").exists()]
            if len(matches) == 1:
                return matches[0].resolve()
            if len(matches) > 1:
                raise ValueError("Ambiguous matched project; use project_path in --input")
    if fallback is None:
        raise ValueError("No local matched project; supply --target-dir")
    return fallback.expanduser().resolve(strict=True)


def copy_project(target: Path, destination: Path) -> None:
    """Stream committed HEAD files into an independent, history-free Git repository.

    Local edits, untracked files, symlinks and submodule contents are excluded.
    Unlike a worktree, the copy never registers anything in the source repository.
    """
    result = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--path-format=absolute", "--git-path", "objects"],
        capture_output=True, text=True, check=True, timeout=30,
    )
    objects = result.stdout.strip()
    commit = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--verify", "HEAD"],
        capture_output=True, text=True, check=True, timeout=30,
    ).stdout.strip()
    subprocess.run(["git", "init", "-q", str(destination)], capture_output=True, check=True, timeout=30)
    attributes = destination / ".git/info/attributes"
    attributes.parent.mkdir(parents=True, exist_ok=True)
    # info/attributes overrides committed export rules. Project instructions must
    # neither disappear (export-ignore) nor be rewritten (export-subst).
    attributes.write_text("* -export-ignore -export-subst\n", encoding="utf-8")
    command = ["git", "-C", str(destination), "archive", "--format=tar", commit]
    # Only this read-only archive process sees the source object path. The new
    # repository keeps no alternates, worktree registration or source reference.
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env={**os.environ, "GIT_OBJECT_DIRECTORY": objects},
    )
    try:
        # Never extract links or metadata from the archive. Only regular file bytes
        # may enter the disposable project; no source hooks or Git config are copied.
        with tarfile.open(fileobj=process.stdout, mode="r|", bufsize=1024 * 1024) as archive:
            for member in archive:
                if not member.isfile():
                    continue
                name = member.name
                if name.startswith("/") or any(p in {"", ".", "..", ".git"} for p in name.split("/")):
                    raise ValueError("Invalid project file path")
                copied = destination / name
                copied.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as source, copied.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
        if process.wait(timeout=30) != 0:
            raise subprocess.CalledProcessError(process.returncode, command)
    finally:
        if process.poll() is None:
            process.kill()
        process.stdout.close()
        process.wait()
        attributes.unlink()


def adoption_command(repo: str, path: str, commit: str, version: str) -> list[str]:
    folder = str(PurePosixPath(path).parent)
    spec = repo + (f"/{folder}" if folder != "." else "") + f"#{commit}"
    skill = PurePosixPath(folder).name if folder != "." else repo.split("/")[-1]
    return ["npx", "--yes", f"skilladopt@{version}", spec, skill]


def external_temp_dir(target: Path) -> Path:
    target = target.resolve()
    root = next((p for p in (target, *target.parents) if (p / ".git").exists()), target)
    for candidate in (Path(tempfile.gettempdir()), Path("/tmp"), Path("/var/tmp")):
        candidate = candidate.resolve()
        if candidate.is_dir() and not candidate.is_relative_to(root):
            return candidate
    raise ValueError("No temporary directory outside the target project is available")


def run_preview(
    command: list[str], target: Path, token: str | None, tarball: Path | None = None,
    *, timings: dict[str, float] | None = None,
) -> dict:
    if timings is None:
        timings = {}
    with tempfile.TemporaryDirectory(prefix="repofit-preview-", dir=external_temp_dir(target)) as temporary:
        copy = Path(temporary) / "project"
        with measure(timings, "copy"):
            copy_project(target, copy)
        env = {**os.environ, "SKILLADOPT_HOME": str(Path(temporary) / "cache"), "NO_COLOR": "1"}
        if token:
            env["GITHUB_TOKEN"] = token
        invocation = command
        if tarball is not None:
            invocation = ["npx", "--yes", "--package", str(tarball), "skilladopt", *command[3:]]
        with measure(timings, "skilladopt"):
            result = subprocess.run(
                [*invocation, "--dry-run", "--json", "--worker", "codex"], cwd=copy, env=env,
                capture_output=True, text=True, timeout=900,
            )
        # Refusals and reviews intentionally exit 1; their JSON still belongs in the report.
        if result.returncode not in {0, 1, 2} or len(result.stdout.strip().splitlines()) != 1:
            raise ValueError("skilladopt failed to return one JSON result")
        data = json.loads(result.stdout)
        required = {"source", "commit", "license", "verdict", "counts", "changes", "rejectionReasons", "jobId"}
        if not isinstance(data, dict) or not required <= data.keys():
            raise ValueError("Incompatible skilladopt JSON; use a version with --dry-run")
        if (data["verdict"] not in {"fit", "no-op", "reject", "needs-review", "invalid"}
                or not isinstance(data["changes"], list) or len(data["changes"]) > 5
                or not isinstance(data["rejectionReasons"], list)):
            raise ValueError("Invalid skilladopt preview result")
        counts = data["counts"]
        if (not isinstance(counts, dict) or set(counts) != {"keep", "drop", "accept", "needs-review"}
                or any(type(n) is not int or n < 0 for n in counts.values())
                or not isinstance(data["jobId"], str)
                or not all(isinstance(reason, str) for reason in data["rejectionReasons"])):
            raise ValueError("Invalid skilladopt decision counts")
        for change in data["changes"]:
            if (not isinstance(change, dict)
                    or not {"block", "file", "action", "before", "after", "reason"} <= change.keys()
                    or not all(isinstance(change[key], str) for key in ("block", "file", "action", "before", "after", "reason"))):
                raise ValueError("Invalid skilladopt change summary")
        if data["commit"] != command[-2].rsplit("#", 1)[1]:
            raise ValueError("skilladopt source commit does not match discovery")
        return data


def _text(value: object) -> str:
    text = " ".join(str(value).split())[:500]
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("`", "'").replace("|", "\\|")


def preview_report(
    rows: list[dict], client: httpx.Client, *, target_dir: Path | None,
    projects_dir: Path, maximum: int = 5, version: str = SKILLADOPT_VERSION,
    tarball: Path | None = None, per_repo: int = 2, started_at: float | None = None,
) -> str:
    started = time.perf_counter() if started_at is None else started_at
    timings = {"copy": 0.0, "skilladopt": 0.0, "github": 0.0}
    if not 1 <= maximum <= 5:
        raise ValueError("--max must be between 1 and 5")
    if per_repo < 1:
        raise ValueError("--per-repo must be at least 1")
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?", version):
        raise ValueError("--skilladopt-version must be an exact version")
    lines = ["# Weekly skill preview", "", "Preview only. No skills were installed.", ""]
    sources = []
    seen = set()
    for row in rows:
        if len(sources) >= maximum:
            break
        repo = row["full_name"]
        if not REPO_NAME.fullmatch(repo):
            raise ValueError("Invalid repository name")
        if repo.casefold() in seen:
            continue
        seen.add(repo.casefold())
        try:
            with measure(timings, "github"):
                commit, paths = discover_skills(client, repo)
        except (httpx.HTTPError, ValueError, KeyError):
            lines.extend([f"- {_text(repo)}: discovery failed; check GitHub access or tree limits.", ""])
            continue
        if not paths:
            lines.extend([f"- {_text(repo)}: no SKILL.md found.", ""])
        if paths:
            sources.append((row, commit, paths[:per_repo]))
    # Give every eligible repository one turn before selecting a second skill.
    selected = [
        (row, commit, paths[index])
        for index in range(min(per_repo, maximum))
        for row, commit, paths in sources if index < len(paths)
    ][:maximum]
    counts = Counter(row["full_name"] for row, _, _ in selected)
    for count, (row, commit, path) in enumerate(selected, 1):
        repo = row["full_name"]
        command = adoption_command(repo, path, commit, version)
        lines.extend([f"## {count}. {_text(repo)} / {_text(path)}", "", f"- Source commit: `{commit}`"])
        try:
            target = target_for(row, target_dir, projects_dir)
            auth = client.headers.get("Authorization", "")
            token = auth.removeprefix("Bearer ") or None
            data = run_preview(command, target, token, tarball, timings=timings)
            lines.extend([
                f"- License: {_text(data['license'] or 'UNKNOWN')}",
                f"- Verdict: {_text(data['verdict'])}",
                "- Decisions: " + _text(json.dumps(data["counts"], ensure_ascii=False)),
                f"- Job: {_text(data['jobId'])} (preview only, not saved)",
                "- Changed blocks:",
            ])
            for change in data["changes"]:
                lines.append(f"  - {_text(change['block'])} ({_text(change['file'])}, {_text(change['action'])}): "
                             f"{_text(change['before'])} -> {_text(change['after'])}; {_text(change['reason'])}")
            if not data["changes"]:
                lines.append("  - None.")
            reasons = "; ".join(str(reason) for reason in data["rejectionReasons"]) or "None."
            lines.append(f"- Refusal reason: {_text(reasons)}")
        except (OSError, subprocess.SubprocessError, tarfile.TarError, ValueError, KeyError, TypeError):
            # Subprocess errors can contain credentials, private paths or project text.
            lines.extend(["- License: UNKNOWN", "- Verdict: unavailable",
                          "- Refusal reason: preview failed; check target Git repository, worker and skilladopt version."])
        url = f"https://github.com/{repo}/blob/{commit}/{quote(path)}"
        lines.extend([f"- Skill: {url}", "- Adoption command (run in the chosen project after review):",
                      "", "```bash", shlex.join(command), "```", ""])
    lines.extend([f"Skills previewed: {len(selected)}/{maximum}.", ""])
    elapsed = time.perf_counter() - started
    summary = [
        "# Weekly skill preview", "",
        f"- Total elapsed: {elapsed:.3f} s",
        f"- Temporary copies (tracked HEAD files only): {timings['copy']:.3f} s",
        f"- skilladopt / Codex (including startup and source fetch): {timings['skilladopt']:.3f} s",
        f"- GitHub discovery: {timings['github']:.3f} s",
        f"- Other (setup, validation, cleanup): {max(0.0, elapsed - sum(timings.values())):.3f} s",
        f"- Skills selected by repository (limit {per_repo} each): "
        + (", ".join(f"{_text(repo)}: {number}" for repo, number in counts.items()) or "None."),
        "",
    ]
    return "\n".join(summary + lines[2:])
