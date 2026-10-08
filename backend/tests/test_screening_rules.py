"""CV screening rules: parsing, matching and scoring (no database, no AI).

A fake embedding (word counts) stands in for the local model, so these
tests check the rules themselves.
"""

from datetime import date

from app.screening import matching, scoring
from app.screening.parsing import find_name, parse_cv, total_years
from app.screening.weights import DEFAULT_WEIGHTS, ScoringWeights

CV = """SYNTHETIC TEST CV: a made-up person for testing.
Sam Example
Senior PHP Developer
sam.example@example.com · +880 1700-000099
Work Experience
Senior PHP Developer · Jan 2022 – Present
Builds Laravel 10 APIs; every service runs in Docker.
PHP Developer · Mar 2019 – Dec 2022
Has not used Symfony. Built Lumen services.
Education
BSc in Computer Science, Sample University (2014 – 2018)
Certifications
AWS Certified Developer – Associate (2024)
"""
TODAY = date(2026, 10, 8)


def fake_vector(text: str) -> list[float]:
    """Bag-of-words vector: texts sharing words are similar."""
    vector = [0.0] * 64
    for word in text.lower().split():
        vector[hash(word) % 64] += 1.0
    return vector


def passages(text: str) -> list[tuple[str, str, list[float]]]:
    """CV lines with fake embeddings."""
    return [
        (s, line, fake_vector(line))
        for s, line in matching.cv_passages(parse_cv(text, TODAY))
    ]


def test_parsing_finds_the_main_facts():
    data = parse_cv(CV, TODAY)

    assert data["name"] == "Sam Example"
    assert data["email"] == "sam.example@example.com"
    assert data["degree"] == "bachelor"
    assert data["certifications"] == ["AWS Certified Developer – Associate (2024)"]
    # Mar 2019 – Oct 2026, with the overlapping 2022 counted once.
    assert data["years_experience"] == 7.7
    assert set(data["sections"]) >= {"experience", "education", "certifications"}


def test_overlapping_jobs_count_once():
    jobs = [
        {"start": "2020-01", "end": "2021-12"},
        {"start": "2021-06", "end": "2022-12"},
    ]

    assert total_years(jobs) == 3.0


def test_the_name_matching_the_email_wins():
    lines = ["Certified Kubernetes", "Application Developer", "Robin Stub"]

    assert find_name(lines, "robin.stub@example.com") == "Robin Stub"


def test_mentions_also_counts_related_and_negation(monkeypatch):
    monkeypatch.setattr(matching, "embed_query", fake_vector)
    lines = passages(CV)
    docker = {"text": "Docker", "level": "mandatory", "category": "skill"}
    sail = {
        "text": "Containers",
        "level": "required",
        "category": "skill",
        "also_counts": ["Docker"],
    }
    symfony = {
        "text": "Symfony",
        "level": "preferred",
        "category": "skill",
        "related": ["Lumen"],
    }
    kubernetes = {"text": "Kubernetes", "level": "preferred", "category": "skill"}

    found = {
        m["requirement"]: m
        for m in matching.match_requirements(
            [docker, sail, symfony, kubernetes], lines, 7.7
        )
    }

    assert (
        found["Docker"]["status"] == "met"
        and found["Docker"]["decided_by"] == "mention"
    )
    assert found["Containers"]["decided_by"] == "also_counts"
    # "Has not used Symfony" does not count; the related "Lumen" gives partly met.
    assert found["Symfony"]["status"] == "partial"
    assert found["Symfony"]["matched_name"] == "Lumen"
    assert (
        found["Kubernetes"]["status"] == "unmet"
        and found["Kubernetes"]["evidence"] is None
    )


def test_the_gate_excludes_missing_must_haves_and_too_few_years():
    matches = [
        {
            "requirement": "PHP",
            "level": "mandatory",
            "status": "met",
            "decided_by": "mention",
        },
        {
            "requirement": "Docker",
            "level": "mandatory",
            "status": "unmet",
            "decided_by": "meaning",
        },
        {
            "requirement": "Laravel",
            "level": "mandatory",
            "status": "partial",
            "decided_by": "meaning",
        },
        {
            "requirement": "Podman",
            "level": "mandatory",
            "status": "partial",
            "decided_by": "related",
        },
    ]

    reasons = scoring.check_gate(matches, years=2.5, min_years=5)

    assert len(reasons) == 3  # Docker, Laravel (meaning only) and the years
    assert any("Docker" in r for r in reasons) and any("Laravel" in r for r in reasons)
    assert not any("Podman" in r for r in reasons)  # a named close substitute passes


def test_scores_are_weighted_and_explained():
    matches = [
        {
            "requirement": "PHP",
            "level": "mandatory",
            "category": "skill",
            "status": "met",
        },
        {
            "requirement": "Redis",
            "level": "preferred",
            "category": "skill",
            "status": "partial",
        },
        {
            "requirement": "AWS certification",
            "level": "preferred",
            "category": "qualification",
            "status": "met",
        },
    ]

    skills, why = scoring.score_skills(matches)
    experience, _ = scoring.score_experience(8.0, 5, [{}, {}])
    qualifications, _ = scoring.score_qualifications("bachelor", matches)
    ats, _ = scoring.score_ats(
        "php redis laravel", ["php", "laravel", "docker", "aws"], 0.75
    )
    scores = {
        "skills": skills,
        "experience": experience,
        "qualifications": qualifications,
        "ats": ats,
    }

    assert skills == 88 and "1 of 2 skills met (PHP); partly: Redis" in why
    assert experience == 100  # 5 + 3 years = full marks
    assert qualifications == round(0.6 * 85 + 40)
    assert ats == round(100 * (0.6 * 0.5 + 0.4 * 1.0))
    assert scoring.combine(scores, DEFAULT_WEIGHTS) == round(
        sum(scores[d] * DEFAULT_WEIGHTS[d] for d in scores) / 100
    )


def test_weights_must_add_up_to_100():
    assert ScoringWeights(skills=40, experience=30, qualifications=10, ats=20)
    try:
        ScoringWeights(skills=50, experience=30, qualifications=10, ats=20)
    except ValueError as exc:
        assert "add up to 100" in str(exc)
    else:
        raise AssertionError("weights adding up to 110 were accepted")
