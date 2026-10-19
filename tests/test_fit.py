import json
import shlex
import subprocess
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from src import cli
from src.analyzer import fit


class FakeClient:
    def __init__(self, answers):
        self.answers = iter(answers)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        answer = next(self.answers)
        if isinstance(answer, Exception):
            raise answer
        content = json.dumps(answer, ensure_ascii=False)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def decision(verdict="skip", project="", use="근거 없음", is_skill=False):
    return dict(verdict=verdict, project=project, use=use, is_skill=is_skill)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    repo = tmp_path / "public-repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "digests").mkdir()
    digest = repo / "digests/2026-10-19.md"
    digest.write_text("\n".join(
        f"### {i}. [org/tool-{i}](https://github.com/org/tool-{i})\n\n"
        f"- **Why it matters / 주목할 이유:** 공개 요약 {i}\n"
        for i in range(1, 5)
    ))
    projects = tmp_path / "projects"
    project = projects / "업무/앱"
    project.mkdir(parents=True)
    (project / "AGENTS.md").write_text("PRIVATE_PROFILE_MARKER" + "가" * 1600)
    (project / "README.md").write_text("기존 음성 기능 사용 중")
    monkeypatch.chdir(repo)
    return SimpleNamespace(repo=repo, projects=projects, digest=digest, out=tmp_path / "private")


def test_profiles_read_two_levels_and_limit_each_file(workspace):
    root = workspace.projects
    (root / "README.md").write_text("not a project")
    (root / "업무/README.md").write_text("not a project")
    (root / "업무/empty").mkdir()
    (root / "업무/empty/package.json").write_text("{}")
    (root / "업무/empty/deeper").mkdir()
    (root / "업무/empty/deeper/README.md").write_text("too deep")
    (root / "업무/앱/README.ko.md").write_text("나" * 2000)
    profiles = fit.load_profiles(root)
    assert [p["name"] for p in profiles] == ["업무/앱"]
    documents = profiles[0]["documents"]
    assert len(documents["AGENTS.md"]) == len(documents["README.ko.md"]) == 1500
    assert documents["README.md"] == "기존 음성 기능 사용 중"


def test_fit_private_output_order_skill_and_no_public_mutation(workspace, monkeypatch):
    before = {p: p.read_bytes() for p in workspace.repo.rglob("*") if p.is_file()}
    client = FakeClient([
        decision("watch", "업무/앱", "연결 방식을 검토한다."),
        decision("skip", use="PRIVATE_SKIP_REASON"),
        decision("adopt", "업무/앱", "스킬로 문서 작업을 보완한다.", True),
        decision("adopt", "업무/앱", "배포 점검을 보완한다."),
    ])
    monkeypatch.setattr(fit, "create_fit_client", lambda *args: client)
    result = CliRunner().invoke(cli.app, [
        "fit", "--projects-dir", str(workspace.projects), "--out-dir", str(workspace.out),
    ])
    assert result.exit_code == 0, result.output
    assert "adopt: 2 · watch: 1 · skip: 1" in result.output
    text = (workspace.out / f"{date.today()}.md").read_text()
    assert text.index("org/tool-3") < text.index("org/tool-4") < text.index("org/tool-1")
    assert "`npx skilladopt add org/tool-3`" in text
    assert text.count("npx skilladopt") == 1
    assert "skip: 1개" in text and "org/tool-2" not in text and "PRIVATE_SKIP_REASON" not in text
    assert "PRIVATE_PROFILE_MARKER" not in text + result.output
    assert len(client.calls) == 4
    for call in client.calls:
        assert call["response_format"] == {"type": "json_object"}
        data = json.loads(call["messages"][1]["content"])
        assert data["projects"][0]["documents"]["AGENTS.md"].startswith("PRIVATE_PROFILE_MARKER")
        assert data["repository"]["summary"].startswith("공개 요약")
        assert "같은 기능" in call["messages"][0]["content"]
    after = {p: p.read_bytes() for p in workspace.repo.rglob("*") if p.is_file()}
    assert before == after
    assert (workspace.out / f"{date.today()}.md").stat().st_mode & 0o777 == 0o600


def test_latest_digest_supplements_existing_metadata(workspace):
    (workspace.repo / "digests/2026-10-18.md").write_text("old")
    (workspace.repo / "repofit-snapshot.json").write_text(json.dumps({"repositories": [{
        "full_name": "org/tool-1", "description": "public description",
        "topics": ["skills"], "readme_summary": "cached readme", "summary": "old summary",
    }]}))
    source, repos = fit.load_repos()
    assert source.name == "2026-10-19.md"
    assert repos[0] == dict(full_name="org/tool-1", description="public description",
                           topics=["skills"], readme_summary="cached readme", summary="공개 요약 1")
    assert len(repos) == 4


def test_snapshot_fallback_respects_curated_order(workspace):
    for path in (workspace.repo / "digests").iterdir():
        path.unlink()
    payload = {"repositories": [{"full_name": f"org/tool-{i}"} for i in range(1, 5)],
               "curated_repositories": ["org/tool-3", "org/tool-1"]}
    (workspace.repo / "repofit-snapshot.json").write_text(json.dumps(payload))
    source, repos = fit.load_repos()
    assert source.name == "repofit-snapshot.json"
    assert [r["full_name"] for r in repos] == ["org/tool-3", "org/tool-1"]


@pytest.mark.parametrize("symlink", [False, True])
def test_repository_output_rejected_before_reading_profiles_or_key(workspace, monkeypatch, symlink):
    out = workspace.repo / "digests"
    if symlink:
        out = workspace.out
        out.symlink_to(workspace.repo / "digests", target_is_directory=True)
    monkeypatch.setattr(fit, "load_profiles", lambda *args: pytest.fail("Must reject before reading"))
    result = CliRunner().invoke(cli.app, ["fit", "--out-dir", str(out)])
    assert result.exit_code == 1
    assert len(list((workspace.repo / "digests").iterdir())) == 1


def test_output_file_symlink_to_repository_rejected(workspace):
    workspace.out.mkdir()
    (workspace.out / f"{date.today()}.md").symlink_to(workspace.digest)
    with pytest.raises(ValueError, match="outside repositories"):
        fit.private_output_path(workspace.out, date.today())


@pytest.mark.parametrize("answer", [
    RuntimeError("PRIVATE_PROFILE_MARKER SECRET_API_KEY"),
    decision("adopt", "unknown/project", "설명"),
    decision("adopt", "업무/앱", ""),
    decision("unknown"),
    decision(is_skill="true"),
    {"verdict": "skip"},
])
def test_errors_do_not_leak_or_replace_previous_result(workspace, monkeypatch, answer):
    workspace.out.mkdir()
    path = workspace.out / f"{date.today()}.md"
    path.write_text("previous")
    monkeypatch.setattr(fit, "create_fit_client", lambda *args: FakeClient([answer]))
    result = CliRunner().invoke(cli.app, [
        "fit", "--projects-dir", str(workspace.projects), "--out-dir", str(workspace.out),
    ])
    assert result.exit_code == 1
    assert "PRIVATE_PROFILE_MARKER" not in result.output and "SECRET_API_KEY" not in result.output
    assert path.read_text() == "previous"


def test_skip_only_notification_contains_three_public_names(workspace, monkeypatch):
    monkeypatch.setattr(fit, "create_fit_client", lambda *args: FakeClient([decision()] * 4))
    result = CliRunner().invoke(cli.app, [
        "fit", "--projects-dir", str(workspace.projects), "--out-dir", str(workspace.out), "--notification",
    ])
    assert result.exit_code == 0
    assert result.output == "org/tool-1,org/tool-2,org/tool-3\n"


def test_adopt_notification_limits_pairs_and_excludes_private_use():
    repos = [{"full_name": f"org/tool-{i}"} for i in range(4)]
    results = [(r, fit.FitDecision(**decision("adopt", "업무/앱", "PRIVATE_USE"))) for r in repos]
    assert fit.notification_text(repos, results) == "도입 추천 4: org/tool-0→업무/앱, org/tool-1→업무/앱"


def test_llm_settings_env_and_option_precedence(workspace, monkeypatch):
    calls = []
    clients = []
    for key, value in (("BASE_URL", "https://env.invalid/v1"), ("MODEL", "env-model"), ("KEY_CMD", "env-key")):
        monkeypatch.setenv("REPOFIT_FIT_" + key, value)

    def create(base, key):
        calls.append((base, key))
        client = FakeClient([decision()] * 4)
        clients.append(client)
        return client

    monkeypatch.setattr(fit, "create_fit_client", create)
    args = ["fit", "--projects-dir", str(workspace.projects), "--out-dir", str(workspace.out)]
    assert CliRunner().invoke(cli.app, args).exit_code == 0
    assert calls == [("https://env.invalid/v1", "env-key")]
    assert {c["model"] for c in clients[0].calls} == {"env-model"}
    result = CliRunner().invoke(cli.app, args + [
        "--llm-base-url", "https://option.invalid/v1", "--llm-key-cmd", "option-key", "--llm-model", "option-model",
    ])
    assert result.exit_code == 0
    assert calls[-1] == ("https://option.invalid/v1", "option-key")
    assert {c["model"] for c in clients[1].calls} == {"option-model"}


def test_key_command_captured_without_shell_or_retry(monkeypatch, capsys):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="secret-key\n", stderr="private warning")

    monkeypatch.setattr(fit.subprocess, "run", run)
    monkeypatch.setattr(fit, "OpenAI", lambda **kwargs: kwargs)
    client = fit.create_fit_client("https://hive.invalid/v3", "security find -s 'hive api'")
    assert calls == [(["security", "find", "-s", "hive api"], dict(capture_output=True, text=True, timeout=30))]
    assert client["api_key"] == "secret-key" and client["max_retries"] == 0
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("fit_exit,fit_text,expected", [
    (0, "도입 추천 1: org/tool-1→업무/앱", "도입 추천 1: org/tool-1→업무/앱"),
    (0, "org/tool-1,org/tool-2,org/tool-3", "org/tool-1,org/tool-2,org/tool-3"),
    (1, "", "org/tool-1,org/tool-2,org/tool-3"),
])
def test_notify_script_fit_and_failure_fallback(workspace, monkeypatch, fit_exit, fit_text, expected):
    # Run the real shell flow with only its external executables replaced.
    original = Path(cli.__file__).resolve().parent.parent / "scripts/repofit-notify.sh"
    scripts = workspace.repo / "scripts"
    scripts.mkdir()
    stub_dir = workspace.out
    stub_dir.mkdir()
    capture = stub_dir / "alert"
    stubs = {
        "git": "exit 0\n",
        "uv": f"printf '%s\\n' {shlex.quote(fit_text)}\nexit {fit_exit}\n",
        "osascript": f"printf '%s' \"$2\" > {shlex.quote(str(capture))}\n",
    }
    for name, body in stubs.items():
        path = stub_dir / name
        path.write_text("#!/bin/bash\n" + body)
        path.chmod(0o700)
    script = original.read_text().replace("/usr/bin/git", shlex.quote(str(stub_dir / "git"))).replace(
        "/usr/bin/osascript", shlex.quote(str(stub_dir / "osascript")),
    )
    (scripts / "repofit-notify.sh").write_text(script)
    monkeypatch.setenv("PATH", str(stub_dir) + ":/usr/bin:/bin")
    result = subprocess.run(["/bin/bash", str(scripts / "repofit-notify.sh")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    prefix = "" if date.today() == date(2026, 10, 19) else "[2026-10-19] "
    assert capture.read_text() == prefix + expected
