import sys
import types

import pytest

fake_supabase = types.ModuleType("supabase")
fake_supabase.Client = object
fake_supabase.create_client = lambda *args, **kwargs: None
sys.modules.setdefault("supabase", fake_supabase)

import src.matcher.recommender as recommender_module


class FakeStorage:
    def __init__(self) -> None:
        self.saved: list[dict] = []

    def get_project(self, project_id: str) -> dict | None:
        return {
            "id": project_id,
            "tech_stack": ["python", "fastapi"],
            "tags": ["api"],
        }

    def find_similar_repos(self, project_id: str, limit: int, min_stars: int) -> list[dict]:
        return [
            {"repository_id": "repo-1", "full_name": "owner/repo-1", "similarity": 0.8},
            {"repository_id": "repo-2", "full_name": "owner/repo-2", "similarity": 0.4},
        ]

    def get_repo_metadata_by_ids(self, repo_ids: list[str]) -> dict[str, dict]:
        return {
            "repo-1": {
                "language": "Python",
                "topics": ["fastapi", "docker"],
                "overall_score": 90,
                "stars_today": 150,
                "stars": 1000,
            },
            "repo-2": {
                "language": "JavaScript",
                "topics": ["react"],
                "overall_score": 50,
                "stars_today": 0,
                "stars": 100,
            },
        }

    def save_recommendation(self, **kwargs) -> dict:
        self.saved.append(kwargs)
        return kwargs


def test_match_project_to_repos_uses_weighted_score(monkeypatch) -> None:
    monkeypatch.setattr(recommender_module, "SupabaseStorage", FakeStorage)
    recommender = recommender_module.Recommender()

    recs = recommender.match_project_to_repos(project_id="project-1", limit=2)

    assert len(recs) == 2
    assert recs[0]["full_name"] == "owner/repo-1"

    expected_top_score = 0.5 * 0.8 + 0.3 * (2 / 3) + 0.2 * 0.9
    assert recs[0]["score"] == pytest.approx(expected_top_score)
    assert recs[1]["score"] == pytest.approx(0.5 * 0.4 + 0.3 * 0.0 + 0.2 * 0.5)
