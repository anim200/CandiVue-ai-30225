"""Consolidated assessment rules (F6) and the interview score (F9):
component scores, the suitability position, evidence checks and the
printable report. No database or AI."""

from datetime import UTC, datetime

from app.analysis.assessment import check_sources, component_scores, suitability
from app.analysis.interview_score import interview_score
from app.analysis.report_html import render_report

SCREENING = {
    "overall": 82.4,
    "rank": 2,
    "ranked_count": 5,
    "dimensions": {
        "skills": {"label": "Technical skills", "score": 90, "reason": "3 of 3 met."}
    },
}


def pair(pair_id, relevance, accuracy, completeness, articulation, status="scored"):
    """A Q&A unit with its four scores."""
    values = {
        "relevance": relevance,
        "accuracy": accuracy,
        "completeness": completeness,
        "articulation": articulation,
    }
    return {
        "id": pair_id,
        "kind": "job",
        "status": status,
        "scores": {
            name: {"score": score, "reason": ""} for name, score in values.items()
        },
    }


def test_the_interview_score_has_six_dimensions_with_evidence():
    pairs = [
        pair("Q1", 90, 70, 60, 80),
        pair("Q2", 80, 80, 70, 90),
        pair("Q3", 0, 0, 0, 0, "not_scored"),
    ]
    coverage = [
        {"requirement": "PHP", "pair_ids": ["Q1", "Q2"]},
        {"requirement": "AWS Certification", "pair_ids": []},
    ]
    judged = {
        "problem_solving": {"score": 60, "reason": "Steps explained.", "turn_ids": [7]},
        "experience_depth": None,  # the review cited no evidence
    }

    score = interview_score(pairs, coverage, judged)

    dimensions = score["dimensions"]
    assert {key: d["score"] for key, d in dimensions.items()} == {
        "technical": 75,  # accuracy of the job answers
        "communication": 85,
        "relevance": 85,
        "problem_solving": 60,
        "experience_depth": None,
        "job_alignment": 75,  # PHP: best of (70+60)/2 and (80+70)/2
    }
    assert dimensions["technical"]["pair_ids"] == ["Q1", "Q2"]
    assert (
        dimensions["experience_depth"]["reason"]
        == "Not enough evidence in the interview."
    )
    assert score["overall"] == round((75 + 85 + 85 + 60 + 75) / 5)
    assert score["scored"] == 2


def test_without_scored_answers_there_is_no_interview_score():
    pairs = [pair("Q1", 0, 0, 0, 0, "not_scored")]
    assert interview_score(pairs, [], {}) is None

    components = component_scores(SCREENING, None, [])

    assert components["cv"]["overall"] == 82 and components["cv"]["rank"] == 2
    assert components["interview"] is None
    # The position then rests on the CV score alone.
    assert suitability(components) == {
        "key": "strong_fit",
        "label": "Strong fit",
        "score": 82,
    }


def test_the_position_steps_follow_the_combined_score():
    def position(cv, interview):
        """The position for a CV score and an interview score."""
        return suitability(
            {
                "cv": {"overall": cv} if cv is not None else None,
                "interview": {"overall": interview} if interview is not None else None,
            }
        )

    assert position(90, 80)["key"] == "strong_fit"  # 85
    assert position(70, 62)["key"] == "good_fit"  # 66
    assert position(60, 40)["key"] == "partial_fit"  # 50
    assert position(40, 30)["key"] == "not_yet_suitable"  # 35
    assert position(82, None) == {
        "key": "strong_fit",
        "label": "Strong fit",
        "score": 82,
    }
    assert position(None, None)["key"] == "not_enough_evidence"


def test_only_existing_evidence_ids_are_kept():
    known = {"CV1": {}, "T4": {}}
    findings = [
        {"text": "Strong Laravel", "sources": ["T4", "T99", "T4", "CV1"]},
        {"text": "Invented", "sources": ["X1"]},
    ]

    checked = check_sources(findings, known)

    assert checked[0]["sources"] == ["T4", "CV1"]
    assert checked[1]["sources"] == []


CONTENT = {
    "version": 2,
    "position": {"headline": "Good fit, with gaps to verify"},
    "components": {
        "cv": {
            "overall": 82,
            "dimensions": {"skills": {"label": "Technical skills", "score": 90}},
        },
        "interview": {
            "overall": 77,
            "dimensions": {
                "technical": {"label": "Technical competency", "score": 74},
                "experience_depth": {"label": "Experience depth", "score": None},
            },
        },
        "coverage": {"explored": 2, "total": 3, "unexplored": ["AWS Certification"]},
    },
    "findings": {
        "strengths": [
            {
                "text": "Fixes slow APIs <script>alert(1)</script>",
                "sources": ["T4", "CV1"],
            }
        ],
        "weaknesses": [{"text": "Little deployment experience", "sources": ["T4"]}],
        "gaps": [],
        "verify": [{"text": "Ask about Docker", "sources": [], "unsupported": True}],
    },
    "requirements": [
        {"requirement": "PHP", "level": "mandatory", "cv": "met", "pair_ids": []}
    ],
    "claims": [
        {
            "claim": "Five years of Laravel",
            "cv": {"label": "CV · Work history", "text": "Laravel (2019 to now)"},
            "result": "contradiction",
            "interview_says": "Started with Laravel last year.",
            "follow_up": "When did you start with Laravel?",
            "sources": ["T4"],
        }
    ],
    "quality": {"verdict": "needs_attention", "reasons": ["Not explored: AWS."]},
    "identity": {
        "state": "confirmed",
        "text": "Confirmed by face recognition at 00:04.",
    },
    "sources": {
        "T4": {"label": "Transcript 02:47", "text": "I added an index."},
        "CV1": {"label": "CV · Work history", "text": "PHP Developer (2019 to now)"},
    },
}


def render(approved_at=None):
    """The report as HTML, approved or as a draft."""
    return render_report(
        CONTENT,
        candidate="Candidate C",
        job_title="Sample Job: PHP Developer",
        interview_at=datetime(2026, 10, 14, 4, 1, tzinfo=UTC),
        duration_minutes=32,
        approved_by="Interviewer A" if approved_at else None,
        approved_at=approved_at,
    )


def test_the_printable_report_escapes_text_and_numbers_its_sources():
    html = render()

    assert "<script>" not in html and "&lt;script&gt;" in html
    # T4 is cited first, so it is [1]; CV1 is [2]; reused numbers stay the same.
    assert html.count('<span class="ref">[1]</span>') == 4  # also cited by the claim
    assert "[2]</span> CV · Work history" in html
    assert "No supporting source found" in html  # the unsupported conclusion
    assert "None noted." in html  # no evidence gaps
    assert "Never explored" in html
    assert "Interview Wed 14 Oct 2026, 10:01, 32 min" in html  # local time (Dhaka)
    # F9 score (a dimension without evidence shows a dash), F8, F10 and F7.
    assert "Interview: Technical competency" in html and ">–</td>" in html
    assert "Contradiction:</strong> Five years of Laravel" in html
    assert "Follow up: When did you start with Laravel?" in html
    assert "Interview quality: Needs attention (Not explored: AWS.)" in html
    assert "Identity: Confirmed by face recognition at 00:04." in html


def test_a_draft_is_marked_on_every_page_and_an_approval_is_named():
    draft = render()
    final = render(approved_at=datetime(2026, 10, 14, 5, 5, tzinfo=UTC))

    assert "Not yet approved" in draft and 'class="watermark"' in draft
    assert "not yet reviewed and approved by a person" in draft
    assert "watermark" not in final.split("</style>")[1]
    assert "Approved by Interviewer A" in final
    assert "reviewed and approved by a person." in final
