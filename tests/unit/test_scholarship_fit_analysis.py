from datetime import datetime, timedelta, timezone

from app.domains.finance.models.scholarship_fit import ScholarshipFitAction, ScholarshipFitReason
from app.domains.finance.scholarships.fit_analysis import (
    _build_profile_snapshot,
    _build_scholarship_snapshot,
    _evaluate_rules,
    _level_for_score,
)


def _sources(**overrides):
    now = datetime.now(timezone.utc)
    base = {
        "scholarship": {
            "id": "00000000-0000-0000-0000-000000000001",
            "name": "Merit Scholarship",
            "description": "For Software Engineering students.",
            "eligibility_criteria": "GPA and IELTS are considered.",
            "benefits": "Tuition support",
            "provider": "Student360",
            "target_majors": ["Software Engineering"],
            "target_universities": ["FPT University"],
            "minimum_gpa": 3.2,
            "minimum_gpa_scale": 4,
            "level": "Undergraduate",
            "is_active": True,
            "application_deadline": now + timedelta(days=30),
            "category_name": "Merit",
        },
        "requirements": [
            {
                "title": "English certificate",
                "description": "IELTS or TOEIC certificate is preferred",
                "is_required": True,
                "sort_order": 1,
            }
        ],
        "documents": [{"document_name": "Transcript", "is_required": True}],
        "user": {"country": "Vietnam", "career_goal": "Software Engineer"},
        "academics": [
            {
                "major": "Software Engineering",
                "faculty": "Information Technology",
                "university": "FPT University",
                "degree_level": "Undergraduate",
                "gpa": 3.6,
                "current_year": 3,
                "current_semester": 6,
            }
        ],
        "certificates": [
            {
                "certificate_name": "IELTS Academic",
                "certificate_type": "language",
                "final_score": "7.0",
                "status": "active",
            }
        ],
        "skills": [],
        "interests": [],
    }
    base.update(overrides)
    return base


def _run(sources):
    reasons: list[ScholarshipFitReason] = []
    actions: list[ScholarshipFitAction] = []
    hard_blockers: list[ScholarshipFitReason] = []
    profile = _build_profile_snapshot(sources)
    scholarship = _build_scholarship_snapshot(sources)
    score, cap = _evaluate_rules(
        sources=sources,
        profile_snapshot=profile,
        scholarship_snapshot=scholarship,
        reasons=reasons,
        actions=actions,
        hard_blockers=hard_blockers,
        now=datetime.now(timezone.utc),
    )
    final = 0 if hard_blockers else max(0, min(round(score), cap))
    return final, _level_for_score(final), reasons, actions, hard_blockers


def test_active_match_gpa_meets_is_high():
    score, level, reasons, _actions, blockers = _run(_sources())

    assert not blockers
    assert level == "high"
    assert score >= 75
    assert any(reason.code == "gpa_meets_requirement" for reason in reasons)


def test_gpa_below_requirement_is_improvable_not_impossible():
    sources = _sources(
        academics=[
            {
                "major": "Software Engineering",
                "faculty": "Information Technology",
                "university": "FPT University",
                "gpa": 3.0,
            }
        ]
    )
    _score, _level, reasons, actions, blockers = _run(sources)

    assert not blockers
    assert any(reason.code == "gpa_below_requirement" and reason.severity == "improvable" for reason in reasons)
    assert any(action.code == "improve_gpa" for action in actions)


def test_inactive_scholarship_is_impossible():
    score, _level, reasons, _actions, blockers = _run(
        _sources(scholarship={**_sources()["scholarship"], "is_active": False})
    )

    assert score == 0
    assert blockers
    assert any(reason.code == "scholarship_inactive" for reason in reasons)


def test_missing_language_certificate_is_improvable():
    _score, _level, reasons, actions, blockers = _run(_sources(certificates=[]))

    assert not blockers
    assert any(reason.code == "missing_language_certificate" for reason in reasons)
    assert any(action.code == "add_language_certificate" for action in actions)
