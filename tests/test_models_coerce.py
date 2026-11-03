from src.models import AnalyzedRepo

BASE = {"rank": 1, "owner": "o", "name": "n", "full_name": "o/n", "url": "https://github.com/o/n"}


def test_numbers_in_text_fields_are_kept_as_text():
    repo = AnalyzedRepo(**BASE, summary=1.5, integration_tips=2, use_cases=[1.5, "a"], potential_risks=3)
    assert repo.summary == "1.5"
    assert repo.integration_tips == "2"
    assert repo.use_cases == ["1.5", "a"]
    assert repo.potential_risks == ["3"]


def test_normal_values_unchanged():
    repo = AnalyzedRepo(**BASE, summary="ok", use_cases=["x"], potential_risks=[])
    assert repo.summary == "ok" and repo.use_cases == ["x"] and repo.potential_risks == []
