import uuid

import pytest

from src.models import AnalyzedRepo
from src.storage.supabase_client import SupabaseStorage


class _UniqueViolation(Exception):
    pass


class _Query:
    def __init__(self, table: "_FakeTable") -> None:
        self.table = table
        self.op = "select"
        self.filters: list = []
        self.payload = None
        self.on_conflict = None

    def select(self, _cols):
        return self

    def in_(self, col, values):
        self.filters.append(lambda r: r.get(col) in values)
        return self

    def eq(self, col, value):
        self.filters.append(lambda r: r.get(col) == value)
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def upsert(self, rows, on_conflict):
        self.op, self.payload, self.on_conflict = "upsert", rows, on_conflict
        return self

    def execute(self):
        rows = self.table.rows
        if self.op == "select":
            data = [dict(r) for r in rows if all(f(r) for f in self.filters)]
        elif self.op == "update":
            data = []
            for r in rows:
                if all(f(r) for f in self.filters):
                    r.update(self.payload)
                    data.append(dict(r))
        else:
            data = []
            for incoming in self.payload:
                key = self.on_conflict
                target = next((r for r in rows if r.get(key) == incoming[key]), None)
                if target is None:
                    target = {"id": str(uuid.uuid4()), "github_id": None}
                    rows.append(target)
                target.update(incoming)
                data.append(dict(target))
        self.table.check_unique()
        return type("Resp", (), {"data": data})()


class _FakeTable:
    def __init__(self, rows):
        self.rows = rows

    def check_unique(self):
        for col in ("full_name", "github_id"):
            values = [r[col] for r in self.rows if r.get(col) is not None]
            if len(values) != len(set(values)):
                raise _UniqueViolation(col)


class _FakeClient:
    def __init__(self, rows):
        self.repos = _FakeTable(rows)

    def table(self, _name):
        return _Query(self.repos)


def _storage(rows):
    storage = SupabaseStorage.__new__(SupabaseStorage)
    storage._client = _FakeClient(rows)
    return storage


def _repo(full_name, github_id):
    owner, name = full_name.split("/")
    return AnalyzedRepo(
        rank=1, full_name=full_name, owner=owner, name=name,
        url=f"https://github.com/{full_name}", github_id=github_id,
    )


def _upsert(storage, repos):
    from datetime import UTC, datetime
    return storage._upsert_repository_rows(repos, datetime.now(UTC))


def test_renamed_repo_updates_existing_row_instead_of_conflicting():
    rows = [{"id": "old", "github_id": 1079456184, "full_name": "K-Dense-AI/claude-scientific-skills"}]
    storage = _storage(rows)

    ids = _upsert(storage, [_repo("K-Dense-AI/scientific-skills", 1079456184)])

    assert ids == {"K-Dense-AI/scientific-skills": "old"}
    assert len(rows) == 1
    assert rows[0]["full_name"] == "K-Dense-AI/scientific-skills"


def test_legacy_row_without_github_id_is_adopted():
    rows = [{"id": "legacy", "github_id": None, "full_name": "org/repo"}]
    storage = _storage(rows)

    ids = _upsert(storage, [_repo("org/repo", 42)])

    assert ids == {"org/repo": "legacy"}
    assert rows == [rows[0]] and rows[0]["github_id"] == 42


def test_reused_name_moves_old_row_aside():
    rows = [
        {"id": "gone", "github_id": 1, "full_name": "org/repo"},
        {"id": "real", "github_id": 2, "full_name": "org/old-name"},
    ]
    storage = _storage(rows)

    ids = _upsert(storage, [_repo("org/repo", 2)])

    assert ids == {"org/repo": "real"}
    assert {r["id"]: r["full_name"] for r in rows} == {
        "gone": "org/repo#stale-gone",
        "real": "org/repo",
    }


def test_repo_without_github_id_still_upserts_by_full_name():
    rows = [{"id": "x", "github_id": None, "full_name": "org/repo"}]
    storage = _storage(rows)

    assert _upsert(storage, [_repo("org/repo", None), _repo("org/new", None)])["org/repo"] == "x"
    assert len(rows) == 2


def test_fake_enforces_unique_github_id():
    # Guard: the old full_name-only upsert reproduces the production 23505 error in this fake.
    rows = [{"id": "old", "github_id": 7, "full_name": "a/old"}]
    client = _FakeClient(rows)
    with pytest.raises(_UniqueViolation):
        client.table("gt_repositories").upsert(
            [{"full_name": "a/new", "github_id": 7}], on_conflict="full_name"
        ).execute()
