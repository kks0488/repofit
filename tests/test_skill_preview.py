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
    (project / "README.md").write_text("uncommitted project text")
    (project / ".gitignore").write_text(".env\n")
    (project / ".env").write_text("PRIVATE_VALUE")
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

    def run(command, target, token, tarball):
        calls.append((command, target, token))
        return answer("reject" if len(calls) == 2 else "fit")

    monkeypatch.setattr(sp, "run_preview", run)
    rows = [{"full_name": "org/first"}, {"full_name": "org/second"}]
    with client_for(("skills/a/SKILL.md", "skills/b/SKILL.md", "skills/c/SKILL.md")) as client:
        report = sp.preview_report(rows, client, target_dir=tmp_path, projects_dir=tmp_path, maximum=2)
    assert len(calls) == 2
    assert all(call[1:] == (tmp_path, "fake-token") for call in calls)
    assert "org/second" not in report
    assert "Skills previewed: 2/2." in report
    assert "License: MIT" in report and f"Source commit: `{COMMIT}`" in report
    assert "scripts unsupported" in report and "b03" in report
    assert shlex.join(calls[0][0]) in report
    assert "--dry-run" not in report  # The displayed command is the eventual adoption command.
    assert str(tmp_path) not in report and "fake-token" not in report


def test_preview_copies_current_files_and_never_mutates_source(tmp_path, monkeypatch):
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
        assert (cwd / "README.md").read_text() == "uncommitted project text"
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
    def fail(*args):
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
    monkeypatch.setattr(sp, "run_preview", lambda *args: answer())
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
