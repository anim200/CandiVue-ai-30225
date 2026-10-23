"""Q&A units (F5): the LLM's segmentation and evaluations are checked
against the transcript before anything is kept. No database or AI needed."""

from app.analysis import qa_pairs
from app.analysis.qa_pairs import DimensionScore, Evaluation, QAUnit
from app.analysis.transcript import Line, clock_text
from app.db.models.interview import Speaker

I, C = Speaker.INTERVIEWER, Speaker.CANDIDATE
LINES = [
    Line(1, 101, I, "Good morning, thanks for joining.", 0, 2000),
    Line(2, 102, C, "Good morning!", 2500, 3000),
    Line(3, 103, I, "How do you use Laravel, and what do you test?", 4000, 8000),
    Line(4, 104, C, "I build REST APIs with Laravel.", 8500, 12000),
    Line(5, 105, C, "I test controllers with PHPUnit.", 12500, 15000),
    Line(6, 106, I, "Can you give an example of a hard bug?", 16000, 18000),
    Line(7, 107, C, "A memory leak in queue workers.", 18500, 22000),
    Line(8, 108, I, "What do you know about our hybrid policy?", 23000, 26000),
]
REQUIREMENTS = [
    {"text": "PHP", "level": "mandatory"},
    {"text": "Laravel", "level": "mandatory"},
    {"text": "AWS Certification", "level": "preferred"},
]


def unit(question, asked, answered, kind="job", follows_up=None):
    """A unit as the LLM would return it."""
    return QAUnit(
        question=question,
        question_lines=asked,
        answer_lines=answered,
        kind=kind,
        follows_up=follows_up,
    )


def evaluation(score=80, evidence=(4,), requirements=(2,), sources=()):
    """An evaluation as the LLM would return it."""
    dimension = DimensionScore(score=score, reason="Clear and correct.")
    return Evaluation(
        relevance=dimension,
        accuracy=dimension,
        completeness=dimension,
        articulation=dimension,
        summary="Concrete example with the right tools.",
        evidence_lines=list(evidence),
        requirements=list(requirements),
        sources=list(sources),
    )


def test_units_are_ordered_numbered_and_linked():
    units = [
        unit("Hard bug?", [6], [7], follows_up=3),  # out of order: sorted by time
        unit("Good morning", [1], [2], kind="other"),
        unit("How do you use Laravel?", [3], [4]),
        unit("What do you test?", [3], [5]),  # same question lines: part 2
    ]

    pairs = qa_pairs.build_pairs(units, LINES)

    assert [p["id"] for p in pairs] == ["Q1", "Q2a", "Q2b", "Q3"]
    assert pairs[1]["part"] == [1, 2] and pairs[2]["part"] == [2, 2]
    assert pairs[0]["part"] is None
    # "follows_up" pointed at the LLM's unit 3, which became Q2a.
    assert pairs[3]["follow_up_of"] == "Q2a"
    assert pairs[1]["turn_ids"] == [103, 104] and pairs[1]["answer_turn_ids"] == [104]
    assert (pairs[3]["start_ms"], pairs[3]["end_ms"]) == (16000, 22000)


def test_lines_from_the_wrong_person_or_that_do_not_exist_are_dropped():
    units = [
        unit(
            "Laravel?", [3, 4, 99], [4, 3, 42]
        ),  # 4 is the candidate's, 3 the interviewer's
        unit("Candidate's own question", [2], [1]),  # the candidate never asks a unit
        unit("Not in the transcript", [50], [51]),
        unit("   ", [6], [7]),  # empty question text
        unit("Laravel?", [3], [4]),  # the same unit twice
    ]

    pairs = qa_pairs.build_pairs(units, LINES)

    assert len(pairs) == 1
    assert pairs[0]["lines"] == [3, 4]


def test_at_most_max_units_are_kept(monkeypatch):
    monkeypatch.setattr(qa_pairs, "MAX_UNITS", 2)
    units = [
        unit("Morning", [1], [2], "other"),
        unit("Laravel?", [3], [4]),
        unit("Bug?", [6], [7]),
    ]

    assert [p["question"] for p in qa_pairs.build_pairs(units, LINES)] == [
        "Morning",
        "Laravel?",
    ]


def test_a_follow_up_never_points_forward_or_to_itself():
    units = [
        unit("Laravel?", [3], [4], follows_up=2),
        unit("Bug?", [6], [7], follows_up=2),
    ]

    pairs = qa_pairs.build_pairs(units, LINES)

    assert [p["follow_up_of"] for p in pairs] == [None, None]


def test_only_answered_job_and_company_questions_are_scored():
    pairs = qa_pairs.build_pairs(
        [
            unit("Morning", [1], [2], kind="other"),
            unit("Laravel?", [3], [4]),
            unit("Hybrid policy?", [8], [], kind="company"),  # no answer
        ],
        LINES,
    )

    assert [qa_pairs.is_scored(p) for p in pairs] == [False, True, False]
    assert "not scored" in qa_pairs.not_scored(pairs[0])["reason"]
    assert "No answer" in qa_pairs.not_scored(pairs[2])["reason"]


def test_an_evaluation_keeps_only_valid_lines_requirements_and_sources():
    (pair,) = qa_pairs.build_pairs([unit("Laravel?", [3], [4])], LINES)
    passages = [{"filename": "laravel-guide.md", "excerpt": "Laravel routes..."}]

    scored = qa_pairs.apply_evaluation(
        pair,
        evaluation(evidence=(4, 7, 4), requirements=(2, 9, 2), sources=(1, 5)),
        REQUIREMENTS,
        passages,
    )

    assert scored["status"] == "scored"
    assert scored["evidence_turn_ids"] == [104]  # line 7 is another unit's
    assert scored["requirements"] == ["Laravel"]
    assert scored["sources"] == passages and scored["verified"] is True
    assert set(scored["scores"]) == set(qa_pairs.DIMENSIONS)


def test_without_valid_evidence_the_answer_itself_is_cited():
    (pair,) = qa_pairs.build_pairs([unit("Laravel?", [3], [4])], LINES)

    scored = qa_pairs.apply_evaluation(
        pair, evaluation(evidence=(8,)), REQUIREMENTS, []
    )

    assert scored["evidence_turn_ids"] == [104]
    assert scored["verified"] is False  # judged without a reference document


def test_coverage_shows_which_units_explored_each_requirement():
    pairs = [
        {"id": "Q1", "requirements": ["Laravel"]},
        {"id": "Q2", "requirements": ["Laravel", "PHP"]},
        {"id": "Q3"},  # not scored: no requirements
    ]

    covered = qa_pairs.coverage(REQUIREMENTS, pairs)

    assert [c["pair_ids"] for c in covered] == [["Q2"], ["Q1", "Q2"], []]
    assert covered[2] == {
        "requirement": "AWS Certification",
        "level": "preferred",
        "pair_ids": [],
    }


def test_times_read_like_a_clock():
    assert clock_text(167_000) == "02:47"
    assert clock_text(3_727_000) == "1:02:07"
    assert clock_text(-5) == "00:00"
    assert (
        LINES[2].as_prompt()
        == "L3 [00:04] Interviewer: How do you use Laravel, and what do you test?"
    )
