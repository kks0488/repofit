import json
import shlex
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from typer.testing import CliRunner

from src import cli
from src import skill_preview as sp

COMMIT = "a" * 40


def answer(verdict="fit"):
    return {"source": "github:org/skills/skills/helper", "commit": COMMIT, "license": "MIT",
            "verdict": verdict, "counts": {"keep": 2, "drop": 1, "accept": 0, "needs-review": 0},
            "changes": [{"block": "b03", "file": "SKILL.md", "action": "drop",
                         "before": "Use another stack.", "after": "", "reason": "stack-mismatch"}],
            "rejectionReasons": ["scripts unsupported"] if verdict == "reject" else [], "jobId": "1234abcd"}


def client_for(paths=("skills/helper/SKILL.md",), truncated=False):
    def handle(request):
        if request.url.path.endswith("/commits/HEAD"):
            return httpx.Response(200, json={"sha": COMMIT})
        assert request.url.path.endswith("/git/trees/" + COMMIT)
        assert request.url.params["recursive"] == "1"
        return httpx.Response(200, json={"truncated": truncated, "tree": [
            {"type": "blob", "mode": "100644", "path": path} for path in paths
        ] + [{"type": "blob", "mode": "120000", "path": "link/SKILL.md"}]})
    return httpx.Client(transport=httpx.MockTransport(handle), headers={"Authorization": "Bearer fake-token"})


def git_project(tmp_path):
    project = tmp_path / "original"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    (project / "README.md").write_text("committed project text")
    (project / ".gitignore").write_text(".env\n")
    (project / ".env").write_text("PRIVATE_VALUE")
    subprocess.run(["git", "-C", str(project), "add", "README.md", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(project), "-c", "user.name=Test", "-c", "user.email=test@example.com",
                    "commit", "-qm", "Project snapshot"], check=True)
    (project / "README.md").write_text("uncommitted project text")
    return project


def snapshot(path):
    return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob("*") if p.is_file()}


def test_discovery_uses_pinned_git_tree_and_excludes_symlinks():
    with client_for(("SKILL.md", "skills/nested/SKILL.md", "README.md")) as client:
        assert sp.discover_skills(client, "org/skills") == (COMMIT, ["SKILL.md", "skills/nested/SKILL.md"])


def test_truncated_tree_is_an_explicit_failure():
    with client_for(truncated=True) as client, pytest.raises(ValueError, match="truncated"):
        sp.discover_skills(client, "org/skills")


def test_report_caps_skills_globally_and_includes_adoption_commands(tmp_path, monkeypatch):
    calls = []

    def run(command, target, token, tarball, **kwargs):
        calls.append((command, target, token))
        return answer("reject" if len(calls) == 2 else "fit")

    monkeypatch.setattr(sp, "run_preview", run)
    rows = [{"full_name": "org/first"}, {"full_name": "org/second"}]
    with client_for(("skills/a/SKILL.md", "skills/b/SKILL.md", "skills/c/SKILL.md")) as client:
        report = sp.preview_report(rows, client, target_dir=tmp_path, projects_dir=tmp_path, maximum=2)
    assert len(calls) == 2
    assert all(call[1:] == (tmp_path, "fake-token") for call in calls)
    assert [call[0][-2].split("/skills/")[0] for call in calls] == ["org/first", "org/second"]
    assert "Skills previewed: 2/2." in report
    assert "License: MIT" in report and f"Source commit: `{COMMIT}`" in report
    assert "scripts unsupported" in report and "b03" in report
    assert shlex.join(calls[0][0]) in report
    assert "--dry-run" not in report  # The displayed command is the eventual adoption command.
    assert str(tmp_path) not in report and "fake-token" not in report


def test_preview_copies_head_files_and_never_mutates_source(tmp_path, monkeypatch):
    project = git_project(tmp_path)
    external = tmp_path / "private"
    external.write_text("private external data")
    (project / "link").symlink_to(external)
    before = snapshot(project)
    actual_run = subprocess.run
    workspaces = []

    def run(args, **kwargs):
        if args[0] != "npx":
            return actual_run(args, **kwargs)
        cwd = Path(kwargs["cwd"])
        workspaces.append(cwd)
        assert cwd != project and (cwd / ".git").is_dir()
        assert (cwd / "README.md").read_text() == "committed project text"
        assert not (cwd / "link").exists() and not (cwd / ".env").exists()
        assert args[-4:] == ["--dry-run", "--json", "--worker", "codex"]
        assert kwargs["env"]["GITHUB_TOKEN"] == "not-printed"
        # Even a broken child that writes into the working project cannot affect the source.
        (cwd / "README.md").write_text("changed by child")
        return SimpleNamespace(returncode=1, stdout=json.dumps(answer("needs-review")), stderr="private ignored")

    monkeypatch.setattr(sp.subprocess, "run", run)
    data = sp.run_preview(sp.adoption_command("org/skills", "skills/helper/SKILL.md", COMMIT, "0.1.11"), project, "not-printed")
    assert data["verdict"] == "needs-review"
    assert snapshot(project) == before
    assert workspaces and not workspaces[0].exists()


@pytest.mark.parametrize("output,code", [("noise\n{}", 0), ("{}", 2), (json.dumps({**answer(), "commit": "b" * 40}), 0)])
def test_bad_worker_output_is_refused_and_temporary_copy_removed(tmp_path, monkeypatch, output, code):
    directories = []

    def copy(target, destination):
        destination.mkdir()
        directories.append(destination)

    monkeypatch.setattr(sp, "copy_project", copy)
    monkeypatch.setattr(sp.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=code, stdout=output))
    with pytest.raises(ValueError):
        sp.run_preview(sp.adoption_command("org/skills", "SKILL.md", COMMIT, "0.1.11"), tmp_path, None)
    assert directories and not directories[0].exists()


def test_tarball_invocation_for_unpublished_integration(tmp_path, monkeypatch):
    monkeypatch.setattr(sp, "copy_project", lambda target, destination: destination.mkdir())
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout=json.dumps(answer()))

    monkeypatch.setattr(sp.subprocess, "run", run)
    package = tmp_path / "skilladopt.tgz"
    command = sp.adoption_command("org/skills", "SKILL.md", COMMIT, "0.1.11")
    sp.run_preview(command, tmp_path, None, package)
    assert calls[0][:5] == ["npx", "--yes", "--package", str(package), "skilladopt"]
    assert calls[0][5:] == command[3:] + ["--dry-run", "--json", "--worker", "codex"]


def test_existing_digest_loader_is_reused(tmp_path, monkeypatch):
    digest = tmp_path / "digest.md"
    calls = []
    monkeypatch.setattr(sp, "load_repos", lambda source: (calls.append(source), [{"full_name": "org/a"}]))
    assert sp.load_candidates(digest, None) == [{"full_name": "org/a"}]
    assert calls == [digest]
    assert sp.load_candidates(None, "org/a,org/a, org/b") == [{"full_name": "org/a"}, {"full_name": "org/b"}]


def test_weekly_json_retains_matched_project_and_first_rank(tmp_path):
    file = tmp_path / "weekly.json"
    file.write_text(json.dumps({"recommendations": [
        {"full_name": "org/a", "project_name": "matched"},
        {"full_name": "org/a", "project_name": "other"},
    ]}))
    rows = sp.load_candidates(file, None)
    project = tmp_path / "category/matched"
    (project / ".git").mkdir(parents=True)
    assert sp.target_for(rows[0], tmp_path / "fallback", tmp_path) == project


def test_weekly_stored_results_include_recomputed_rows_with_old_creation_dates(monkeypatch):
    from src.storage import SupabaseStorage

    monkeypatch.setattr(SupabaseStorage, "__init__", lambda self: None)
    monkeypatch.setattr(SupabaseStorage, "get_recommendations", lambda self, **kwargs: [
        {"full_name": "org/new", "project_name": "matched", "recommended_at": datetime.now(UTC).isoformat()},
        {"full_name": "org/old", "recommended_at": "2000-01-01T00:00:00Z"},
    ])
    assert sp.load_candidates(None, None, True)[0]["project_name"] == "matched"
    assert len(sp.load_candidates(None, None, True)) == 2


@pytest.mark.parametrize("repos", ["bad", "org/a,", "org/../a"])
def test_bad_repository_input_refused(repos):
    with pytest.raises(ValueError):
        sp.load_candidates(None, repos)


def test_missing_target_and_child_errors_are_reported_without_private_details(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, ["PRIVATE_PATH"], stderr="SECRET_TOKEN")

    monkeypatch.setattr(sp, "run_preview", fail)
    with client_for() as client:
        report = sp.preview_report([{"full_name": "org/skills"}], client, target_dir=tmp_path, projects_dir=tmp_path)
    assert "Verdict: unavailable" in report and "Adoption command" in report
    assert "PRIVATE_PATH" not in report and "SECRET_TOKEN" not in report


def test_empty_and_failed_discovery_are_visible(tmp_path):
    with client_for(()) as client:
        assert "no SKILL.md" in sp.preview_report([{"full_name": "org/a"}], client, target_dir=None, projects_dir=tmp_path)
    with client_for(truncated=True) as client:
        assert "discovery failed" in sp.preview_report([{"full_name": "org/a"}], client, target_dir=None, projects_dir=tmp_path)


def test_cli_report_output_and_original_unchanged(tmp_path, monkeypatch):
    project = git_project(tmp_path)
    before = snapshot(project)
    monkeypatch.setattr(sp, "github_headers", lambda: {})
    monkeypatch.setattr(sp, "discover_skills", lambda client, repo: (COMMIT, ["SKILL.md"]))
    monkeypatch.setattr(sp, "run_preview", lambda *args, **kwargs: answer())
    output = tmp_path / "preview.md"
    result = CliRunner().invoke(cli.app, ["skill-preview", "--repos", "org/skills", "--max", "2",
                                          "--target-dir", str(project), "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert "Verdict: fit" in output.read_text()
    assert snapshot(project) == before
    bad = CliRunner().invoke(cli.app, ["skill-preview", "--repos", "org/skills", "--target-dir", str(project),
                                       "--output", str(project / "preview.md")])
    assert bad.exit_code == 1
    assert snapshot(project) == before


def test_gh_auth_token_is_captured_and_not_printed(monkeypatch, capsys):
    monkeypatch.setattr(sp, "build_github_api_headers", lambda: {})
    monkeypatch.delenv("GH_TOKEN", raising=False)
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout="secret-token\n")

    monkeypatch.setattr(sp.subprocess, "run", run)
    assert sp.github_headers()["Authorization"] == "Bearer secret-token"
    assert calls[0][0] == ["gh", "auth", "token"] and calls[0][1]["capture_output"]
    assert capsys.readouterr() == ("", "")


def test_tempdir_inside_target_cannot_make_repofit_write_there(tmp_path, monkeypatch):
    project = git_project(tmp_path)
    before = snapshot(project)
    monkeypatch.setattr(sp.tempfile, "gettempdir", lambda: str(project))
    copies = []

    def copy(target, destination):
        assert not destination.is_relative_to(project)
        copies.append(destination)
        destination.mkdir()

    monkeypatch.setattr(sp, "copy_project", copy)
    monkeypatch.setattr(sp.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout=json.dumps(answer()),
    ))
    sp.run_preview(sp.adoption_command("org/skills", "SKILL.md", COMMIT, "0.1.11"), project, None)
    assert copies and not copies[0].exists()
    assert snapshot(project) == before


def commit_project(project):
    subprocess.run(["git", "-C", str(project), "add", "."], check=True)
    subprocess.run(["git", "-C", str(project), "-c", "user.name=Test", "-c", "user.email=test@example.com",
                    "commit", "-qm", "Tracked project files"], check=True)


def test_archive_is_independent_and_keeps_summary_files_from_head(tmp_path):
    project = git_project(tmp_path)
    (project / "package.json").write_text('{"scripts":{"test":"pytest"}}')
    (project / "pyproject.toml").write_text('[project]\nname="example"\n')
    (project / "AGENTS.md").write_text("Keep the project conventions.")
    (project / "nested").mkdir()
    (project / "nested/file.py").write_text("print('tracked')")
    (project / "link").symlink_to(tmp_path / "outside")
    commit_project(project)
    (project / "README.md").write_text("local edits are excluded")
    (project / "untracked.txt").write_text("untracked files are excluded")
    (project / ".git/private-history-marker").write_bytes(b"x" * 1024 * 1024)
    before = snapshot(project)
    destination = tmp_path / "copy"
    sp.copy_project(project / "nested", destination)
    assert snapshot(project) == before  # Includes index, refs, config and worktree metadata.
    assert (destination / "README.md").read_text() == "uncommitted project text"
    for file in ("package.json", "pyproject.toml", "AGENTS.md", "nested/file.py"):
        assert (destination / file).read_bytes() == (project / file).read_bytes()
    assert not (destination / "untracked.txt").exists()
    assert not (destination / "link").is_symlink()
    assert not (destination / ".env").exists()
    assert not (destination / ".git/private-history-marker").exists()
    assert not (destination / ".git/objects/info/alternates").exists()
    assert not (destination / ".git/worktrees").exists()
    assert subprocess.check_output(["git", "-C", str(destination), "rev-parse", "--show-toplevel"], text=True).strip() == str(destination)


def test_archive_without_head_is_reported_and_cleaned_up(tmp_path):
    project = tmp_path / "empty"
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    before = snapshot(project)
    with client_for() as client:
        report = sp.preview_report([{"full_name": "org/skills"}], client,
                                   target_dir=project, projects_dir=tmp_path)
    assert "Verdict: unavailable" in report
    assert snapshot(project) == before
    assert "Total elapsed:" in report


def test_archive_preserves_head_files_despite_export_attributes(tmp_path):
    project = git_project(tmp_path)
    (project / "AGENTS.md").write_text("Keep these instructions.")
    (project / "version.txt").write_text("$Format:%H$")
    (project / ".gitattributes").write_text("AGENTS.md export-ignore\nversion.txt export-subst\n")
    commit_project(project)
    # Local info attributes have higher priority than the committed rules too.
    (project / ".git/info/attributes").write_text("README.md export-ignore\n")
    before = snapshot(project)
    destination = tmp_path / "copy"
    sp.copy_project(project, destination)
    for file in ("AGENTS.md", "README.md", "version.txt", ".gitattributes"):
        expected = subprocess.check_output(["git", "-C", str(project), "show", f"HEAD:{file}"])
        assert (destination / file).read_bytes() == expected
    assert not (destination / ".git/info/attributes").exists()
    assert not (destination / ".git/objects/info/alternates").exists()
    assert snapshot(project) == before


@pytest.mark.parametrize("name", ["../escape", "/absolute", ".git/config", "nested/../../escape"])
def test_archive_rejects_paths_outside_copy(tmp_path, monkeypatch, name):
    import io
    import tarfile

    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as archive:
        member = tarfile.TarInfo(name)
        member.size = 1
        archive.addfile(member, io.BytesIO(b"x"))
    payload.seek(0)
    process = SimpleNamespace(stdout=payload, returncode=0, poll=lambda: 0, wait=lambda **kwargs: 0)
    monkeypatch.setattr(sp.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(stdout=str(tmp_path)))
    monkeypatch.setattr(sp.subprocess, "Popen", lambda *args, **kwargs: process)
    with pytest.raises(ValueError, match="Invalid project file path"):
        sp.copy_project(tmp_path, tmp_path / "copy")
    assert not (tmp_path / "escape").exists()
    assert payload.closed


@pytest.mark.parametrize("per_repo,expected", [
    (1, ["first", "second", "third"]),
    (2, ["first", "second", "third", "first", "second"]),
    (3, ["first", "second", "third", "first", "second"]),
])
def test_selection_rotates_and_respects_repository_cap(tmp_path, monkeypatch, per_repo, expected):
    calls = []

    def run(command, *args, **kwargs):
        calls.append(command)
        return answer()

    monkeypatch.setattr(sp, "run_preview", run)
    rows = [{"full_name": f"org/{name}"} for name in ("first", "second", "third")]
    with client_for(("skills/a/SKILL.md", "skills/b/SKILL.md", "skills/c/SKILL.md")) as client:
        report = sp.preview_report(rows, client, target_dir=tmp_path, projects_dir=tmp_path,
                                   maximum=5, per_repo=per_repo)
    assert [command[-2].split("/")[1] for command in calls] == expected
    assert "Skills selected by repository" in report.split("## 1.")[0]
    for name in dict.fromkeys(expected):
        assert f"org/{name}: {expected.count(name)}" in report.split("## 1.")[0]


def test_single_repository_stops_at_default_cap_even_with_duplicates(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(sp, "run_preview", lambda command, *args, **kwargs: calls.append(command) or answer())
    rows = [{"full_name": "org/only"}, {"full_name": "ORG/ONLY"}]
    with client_for(("a/SKILL.md", "b/SKILL.md", "c/SKILL.md")) as client:
        report = sp.preview_report(rows, client, target_dir=tmp_path, projects_dir=tmp_path)
    assert len(calls) == 2
    assert "Skills previewed: 2/5." in report
    assert "org/only: 2" in report


def test_failed_and_empty_repositories_do_not_block_later_picks(tmp_path, monkeypatch):
    calls = []

    def discover(client, repo):
        calls.append(repo)
        if repo == "org/broken":
            raise ValueError("private error")
        return COMMIT, [] if repo == "org/empty" else ["SKILL.md", "next/SKILL.md"]

    monkeypatch.setattr(sp, "discover_skills", discover)
    monkeypatch.setattr(sp, "run_preview", lambda *args, **kwargs: answer())
    rows = [{"full_name": f"org/{name}"} for name in ("broken", "empty", "good", "also-good", "unused")]
    with client_for() as client:
        report = sp.preview_report(rows, client, target_dir=tmp_path, projects_dir=tmp_path, maximum=2)
    assert calls == ["org/broken", "org/empty", "org/good", "org/also-good"]
    assert "org/good: 1, org/also-good: 1" in report
    assert "private error" not in report


@pytest.mark.parametrize("cap", [0, -1])
def test_invalid_per_repository_limit_refused(tmp_path, cap):
    with client_for() as client, pytest.raises(ValueError, match="--per-repo"):
        sp.preview_report([], client, target_dir=tmp_path, projects_dir=tmp_path, per_repo=cap)
    result = CliRunner().invoke(cli.app, ["skill-preview", "--per-repo", str(cap)])
    assert result.exit_code == 2


def test_report_timing_includes_all_stages_and_cli_setup(tmp_path, monkeypatch):
    now = [10.0]
    monkeypatch.setattr(sp.time, "perf_counter", lambda: now[0])

    def discover(*args):
        now[0] += 3
        return COMMIT, ["SKILL.md"]

    def copy(target, destination):
        now[0] += 2
        destination.mkdir()

    def run(*args, **kwargs):
        now[0] += 5
        return SimpleNamespace(returncode=0, stdout=json.dumps(answer()))

    monkeypatch.setattr(sp, "discover_skills", discover)
    monkeypatch.setattr(sp, "copy_project", copy)
    monkeypatch.setattr(sp.subprocess, "run", run)
    with client_for() as client:
        report = sp.preview_report([{"full_name": "org/skills"}], client, target_dir=tmp_path,
                                   projects_dir=tmp_path, started_at=7.0)
    heading = report.split("## 1.")[0]
    assert "Total elapsed: 13.000 s" in heading
    assert "Temporary copies (tracked HEAD files only): 2.000 s" in heading
    assert "skilladopt / Codex (including startup and source fetch): 5.000 s" in heading
    assert "GitHub discovery: 3.000 s" in heading
    assert "Other (setup, validation, cleanup): 3.000 s" in heading
    assert "org/skills: 1" in heading


@pytest.mark.parametrize("failed_stage", ["copy", "skilladopt", "github"])
def test_failed_stages_are_timed_and_reported(tmp_path, monkeypatch, failed_stage):
    now = [0.0]
    monkeypatch.setattr(sp.time, "perf_counter", lambda: now[0])
    destinations = []

    def discover(*args):
        now[0] += 3
        if failed_stage == "github":
            raise ValueError("private error")
        return COMMIT, ["SKILL.md"]

    def copy(target, destination):
        destinations.append(destination)
        destination.mkdir()
        now[0] += 2
        if failed_stage == "copy":
            raise OSError("private error")

    def run(*args, **kwargs):
        now[0] += 5
        raise subprocess.TimeoutExpired(["private command"], 5)

    monkeypatch.setattr(sp, "discover_skills", discover)
    monkeypatch.setattr(sp, "copy_project", copy)
    monkeypatch.setattr(sp.subprocess, "run", run)
    with client_for() as client:
        report = sp.preview_report([{"full_name": "org/skills"}], client, target_dir=tmp_path, projects_dir=tmp_path)
    assert "GitHub discovery: 3.000 s" in report
    if failed_stage != "github":
        assert "Temporary copies (tracked HEAD files only): 2.000 s" in report
        assert "Verdict: unavailable" in report
    if failed_stage == "skilladopt":
        assert "skilladopt / Codex (including startup and source fetch): 5.000 s" in report
    if failed_stage == "github":
        assert "Skills selected by repository (limit 2 each): None." in report
        assert "Skills previewed: 0/5." in report
    assert all(not path.exists() for path in destinations)
    assert "private error" not in report and "private command" not in report


def test_cli_passes_per_repository_limit(tmp_path, monkeypatch):
    project = git_project(tmp_path)
    monkeypatch.setattr(sp, "github_headers", lambda: {})
    monkeypatch.setattr(sp, "discover_skills", lambda *args: (COMMIT, ["a/SKILL.md", "b/SKILL.md"]))
    monkeypatch.setattr(sp, "run_preview", lambda *args, **kwargs: answer())
    output = tmp_path / "report.md"
    result = CliRunner().invoke(cli.app, ["skill-preview", "--repos", "org/skills", "--per-repo", "1",
                                          "--target-dir", str(project), "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert "org/skills: 1" in output.read_text()
    assert "Skills previewed: 1/5." in output.read_text()
