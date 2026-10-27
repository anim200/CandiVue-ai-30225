"""Interview quality rules (F10): the verdict and its reasons, suggestions
and the comparison with the job's other interviews. Plain code, no
database or AI."""

from app.analysis.interview_quality import consistency, interview_quality
from app.analysis.transcript import Line
from app.db.models.interview import Speaker

I, C = Speaker.INTERVIEWER, Speaker.CANDIDATE
COVERAGE = [
    {"requirement": "PHP", "level": "mandatory", "pair_ids": ["Q1"]},
    {"requirement": "Laravel", "level": "mandatory", "pair_ids": ["Q2"]},
    {"requirement": "AWS", "level": "preferred", "pair_ids": []},
]


def lines(*spoken: tuple[Speaker, int]) -> list[Line]:
    """Transcript lines with the given speakers and lengths in seconds."""
    start, result = 0, []
    for number, (speaker, seconds) in enumerate(spoken, start=1):
        result.append(Line(number, number, speaker, "…", start, start + seconds * 1000))
        start += seconds * 1000
    return result


def answered(count: int) -> list[dict]:
    """That many scored answers."""
    return [{"id": f"Q{n}", "status": "scored"} for n in range(1, count + 1)]


def test_a_balanced_interview_that_explores_the_job_is_good():
    quality = interview_quality(answered(4), COVERAGE, lines((I, 10), (C, 30)), None)

    assert quality["verdict"] == "good" and quality["reasons"] == []
    assert quality["talk"] == {"interviewer": 25, "candidate": 75}
    assert quality["mandatory"] == {"explored": 2, "total": 2}


def test_an_interviewer_who_does_the_talking_makes_a_poor_interview():
    review = {"low_signal": [], "suggestions": ["Ask for an example."]}

    quality = interview_quality(answered(4), COVERAGE, lines((I, 80), (C, 20)), review)

    assert quality["verdict"] == "poor"
    assert quality["reasons"] == ["The interviewer did 80% of the talking."]
    assert quality["suggestions"] == [
        "Ask shorter, open questions and let the candidate talk more.",
        "Ask for an example.",
    ]


def test_too_few_answers_or_too_little_coverage_is_poor():
    unexplored = [c | {"pair_ids": []} for c in COVERAGE]

    quality = interview_quality(answered(2), unexplored, lines((I, 10), (C, 30)), None)

    assert quality["verdict"] == "poor"
    assert quality["reasons"] == [
        "Only 2 job-related questions were answered.",
        "Only 0 of 2 mandatory requirements were explored.",
    ]
    assert quality["suggestions"][:2] == [
        "Ask about PHP next time.",
        "Ask about Laravel next time.",
    ]


def test_low_signal_questions_need_attention():
    review = {"low_signal": [{"pair_id": "Q1"}, {"pair_id": "Q2"}], "suggestions": []}

    quality = interview_quality(answered(4), COVERAGE, lines((I, 10), (C, 30)), review)

    assert quality["verdict"] == "needs_attention"
    assert quality["reasons"] == ["2 questions gave little evidence."]


def test_the_interview_is_compared_with_the_jobs_other_interviews():
    this = {
        "scored": 3,
        "coverage": [
            COVERAGE[0] | {"pair_ids": ["Q1"]},
            COVERAGE[1] | {"pair_ids": []},
        ],
    }
    others = [
        {"scored": 6, "coverage": COVERAGE},
        {"scored": 8, "coverage": COVERAGE},
    ]

    assert consistency(this, []) is None
    assert (
        consistency(this, [{"scored": 0, "coverage": []}]) is None
    )  # empty ones don't count
    assert consistency(this, others) == {
        "compared_with": 2,
        "answered": {"this": 3, "typical": 7},
        "explored": {"this": 1, "typical": 2},
        "missing_usual": ["Laravel"],
    }
