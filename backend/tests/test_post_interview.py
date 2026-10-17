"""Post-interview analysis (F5, F8-F10) and the consolidated assessment (F6)
with the real graphs, database and checkpointer; the LLM and the
knowledge-base search are fakes. Covers: Q&A units and their batched
evaluations, RAG for job and company answers, requirement coverage, the
interview review (CV claims, interview score, interview quality), the
number of AI requests, continuing after a failure without sending finished
steps again, the evidence check with its repair loop, the review (request
changes → version 2 → approve) and the API rules.
"""

import re
import time
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.ai.errors import AIServiceError
from app.analysis.qa_pairs import (
    DimensionScore,
    Evaluation,
    Evaluations,
    QAUnit,
    Segmentation,
)
from app.analysis.review import (
    ClaimCheck,
    InterviewReview,
    JudgedDimension,
    QuestionNote,
)
from app.auth.security import Role, create_access_token, hash_password
from app.core import clock
from app.db.database import SessionLocal
from app.db.models import (
    AssessmentReport,
    Candidate,
    CandidateScore,
    InterviewSession,
    Job,
    QAAnalysis,
    ScreeningRun,
    TranscriptTurn,
    User,
)
from app.db.models.assessment import ReviewStatus
from app.db.models.interview import InvitationStatus, SessionStatus, Speaker
from app.db.models.run import RunStatus
from app.graphs import final_assessment, qa_analysis
from app.graphs.final_assessment import Finding, Findings, Repair, RepairedFinding
from app.interviews import planning
from app.knowledge.search import Passage
from app.runs import runner

I, C = Speaker.INTERVIEWER, Speaker.CANDIDATE
TURNS = [
    (I, "Good morning, Alex. Thanks for joining."),
    (C, "Good morning!"),
    (I, "How do you use Laravel, and what do you usually test?"),
    (C, "I build REST APIs with Laravel and Eloquent."),
    (C, "I test controllers with PHPUnit and mock external services."),
    (I, "Can you give an example of a hard bug you fixed?"),
    (C, "A memory leak in the queue workers; I found it with profiling."),
    (I, "What do you know about our hybrid work policy?"),
    (C, "Two office days a week, the rest remote."),
]


# ---------- fakes ----------


class FakeLLM:
    """Stands in for invoke_llm(): answers by the structured type the caller
    asks for, and remembers every request."""

    def __init__(self, answers):
        self.answers = answers  # {schema: function(messages) -> answer}
        self.calls = []

    def __call__(self, messages, prepare=None):
        """Answer like the model would (or raise, to fake a failure)."""
        asked = {}

        class Spy:
            """Records the schema the caller wants."""

            def with_structured_output(self, schema):
                """Remember the schema."""
                asked["schema"] = schema
                return self

        prepare(Spy())
        schema = asked["schema"]
        self.calls.append((schema.__name__, messages))
        return self.answers[schema](messages)

    def count(self, name: str) -> int:
        """How many requests asked for this schema."""
        return sum(called == name for called, _messages in self.calls)


def score(value: int) -> DimensionScore:
    """One dimension's score."""
    return DimensionScore(score=value, reason="Reason.")


def units_asked(messages) -> dict[str, str]:
    """The units of an evaluation request: {unit id: question}."""
    return dict(
        re.findall(
            r"^Unit (\S+) .*\nQuestion: (.*)$", messages[1].content, re.MULTILINE
        )
    )


def evaluations(messages) -> Evaluations:
    """An evaluation of every unit asked, citing the answer lines; a question
    naming Laravel explores requirement 2 (Laravel)."""
    return Evaluations(
        evaluations=[
            Evaluation(
                unit=unit,
                relevance=score(90),
                accuracy=score(70 if "Hybrid" in question else 80),
                completeness=score(60),
                articulation=score(80),
                summary="Concrete and correct.",
                evidence_lines=[4, 5, 7, 9],
                requirements=[2] if "Laravel" in question else [],
                sources=[1],
            )
            for unit, question in units_asked(messages).items()
        ]
    )


def review(messages) -> InterviewReview:
    """The interview review: a contradiction on a real CV item, a claim on
    an invented item (dropped), a "supported" claim citing only the
    interviewer (shown as never discussed); one judged dimension with
    evidence, one without; a real and an invented low-signal question."""
    return InterviewReview(
        claims=[
            ClaimCheck(
                claim="Laravel since 2019",
                cv_item="CV1",
                result="contradiction",
                interview_says="Mentions only the last year.",
                lines=[7],
                follow_up="When did you start with Laravel?",
            ),
            ClaimCheck(
                claim="Invented",
                cv_item="CV99",
                result="supported",
                interview_says="",
                lines=[4],
                follow_up="?",
            ),
            ClaimCheck(
                claim="PHPUnit",
                cv_item="CV2",
                result="supported",
                interview_says="The interviewer asked.",
                lines=[3],
                follow_up="Which test was hardest?",
            ),
        ],
        problem_solving=JudgedDimension(
            score=70, reason="Profiled the leak.", lines=[7]
        ),
        experience_depth=JudgedDimension(score=90, reason="No lines.", lines=[]),
        low_signal_questions=[
            QuestionNote(unit="Q3", problem="Too broad."),
            QuestionNote(unit="Q99", problem="Invented."),
        ],
        suggestions=["Ask for one concrete example per skill.", " "],
    )


SEGMENTATION = Segmentation(
    units=[
        QAUnit(
            question="Good morning", question_lines=[1], answer_lines=[2], kind="other"
        ),
        QAUnit(
            question="How do you use Laravel?",
            question_lines=[3],
            answer_lines=[4],
            kind="job",
        ),
        QAUnit(
            question="What do you usually test?",
            question_lines=[3],
            answer_lines=[5],
            kind="job",
        ),
        QAUnit(
            question="Example of a hard bug?",
            question_lines=[6],
            answer_lines=[7],
            kind="job",
            follows_up=2,
        ),
        QAUnit(
            question="Hybrid work policy?",
            question_lines=[8],
            answer_lines=[9],
            kind="company",
        ),
        QAUnit(question="Invented", question_lines=[40], answer_lines=[41], kind="job"),
    ]
)


ANALYSIS_ANSWERS = {
    Segmentation: lambda m: SEGMENTATION,
    Evaluations: evaluations,
    InterviewReview: review,
}


def report_answer(changes="", **lists):
    """A Findings answer: each list from (text, sources) pairs."""

    def answer(messages):
        """The four lists (and what changed, on a revision)."""
        return Findings(
            **{
                name: [
                    Finding(text=t, sources=list(src)) for t, src in lists.get(name, ())
                ]
                for name in ("strengths", "weaknesses", "gaps", "verify")
            },
            changes=changes,
        )

    return answer


# ---------- fixtures ----------


@pytest.fixture
def ended(request, monkeypatch):
    """An ended interview with a transcript, a screened CV and a job profile;
    knowledge search finds one reference passage, no company passage."""
    request.getfixturevalue("database_available")
    monkeypatch.setattr(qa_analysis, "TRANSCRIPT_SETTLE_SECONDS", 0)
    searches = []

    def search(db, query, collections, limit):
        """A reference passage for job answers, nothing for company answers."""
        searches.append(collections[0])
        if collections[0] == "reference_library":
            return [
                Passage(
                    1, "laravel-docs.md", collections[0], "Laravel testing guide.", 0.8
                )
            ]
        return [
            Passage(2, "old-policy.md", collections[0], "Unrelated.", 0.2)
        ]  # too weak

    monkeypatch.setattr(qa_analysis, "search_knowledge", search)
    with SessionLocal() as db:
        user = User(
            email="post.interview@example.com",
            full_name="Sam Rivers",
            password_hash=hash_password("x" * 10),
        )
        job = Job(
            title="PHP Laravel Developer",
            profile={
                "requirements": [
                    {"text": "PHP", "level": "mandatory"},
                    {"text": "Laravel", "level": "mandatory"},
                    {"text": "AWS Certification", "level": "preferred"},
                ]
            },
        )
        db.add_all([user, job])
        db.flush()
        candidate = Candidate(
            job_id=job.id,
            full_name="Alex Strong",
            email="alex@example.com",
            cv_filename="alex.pdf",
            parsed_cv={
                "jobs": [
                    {
                        "title": "Laravel Developer at Acme",
                        "start": "2019-03",
                        "end": "now",
                    }
                ],
                "sections": {"skills": "PHP, Laravel, PHPUnit, alex@example.com"},
                "degree": "bachelor",
            },
        )
        db.add(candidate)
        db.flush()
        run = ScreeningRun(job_id=job.id, status=RunStatus.COMPLETED)
        db.add(run)
        db.flush()
        db.add(
            CandidateScore(
                screening_run_id=run.id,
                candidate_id=candidate.id,
                passed_gate=True,
                requirement_matches=[
                    {
                        "requirement": "PHP",
                        "level": "mandatory",
                        "status": "met",
                        "section": "experience",
                        "evidence": "Lead PHP Developer · Since March 2019",
                    }
                ],
                dimension_scores={
                    "skills": {
                        "label": "Technical skills",
                        "score": 90,
                        "reason": "2 of 2 met.",
                    }
                },
                overall_score=84,
                rank=1,
                summary="Overall 84/100.",
            )
        )
        started = clock.now() - timedelta(minutes=20)
        session = InterviewSession(
            candidate_id=candidate.id,
            job_id=job.id,
            interviewer_id=user.id,
            scheduled_at=started,
            join_token_hash=planning.new_link_token()[1],
            invitation_status=InvitationStatus.SENT,
            status=SessionStatus.ENDED,
            started_at=started,
            ended_at=clock.now() - timedelta(minutes=1),
        )
        db.add(session)
        db.flush()
        for n, (speaker, text) in enumerate(TURNS):
            db.add(
                TranscriptTurn(
                    session_id=session.id,
                    speaker=speaker,
                    text=text,
                    start_ms=n * 5000,
                    end_ms=n * 5000 + 4000,
                )
            )
        db.commit()
        data = {
            "session": session.id,
            "job": job.id,
            "user": user.id,
            "candidate": candidate.id,
            "searches": searches,
        }
    yield data
    with SessionLocal() as db:
        db.delete(db.get(Job, data["job"]))
        db.delete(db.get(User, data["user"]))
        db.commit()


@pytest.fixture
def interviewer(ended):
    """The test interviewer's Authorization header."""
    token = create_access_token(ended["user"], Role.INTERVIEWER)
    return {"Authorization": f"Bearer {token}"}


def saved_threads() -> set[str]:
    """Every saved workflow thread id."""
    with SessionLocal() as db:
        return set(db.scalars(text("SELECT DISTINCT thread_id FROM checkpoints")))


def analyse(session_id: int) -> QAAnalysis:
    """Create the interview's analysis and run it to the end (in this thread)."""
    with SessionLocal() as db:
        analysis_id = qa_analysis.start_analysis(db, session_id).id
    runner.execute_run(qa_analysis.RUN_KIND, analysis_id)
    with SessionLocal() as db:
        return db.get(QAAnalysis, analysis_id)


def report_of(session_id: int) -> AssessmentReport:
    """The interview's current report."""
    with SessionLocal() as db:
        return final_assessment.latest_report(db, session_id)


def good_findings():
    """Report lists that all cite valid evidence."""
    return report_answer(
        changes="The testing point now cites the answer.",
        strengths=[("Builds Laravel APIs", ["T4", "CV1"])],
        weaknesses=[("Little testing depth", ["T5"])],
        gaps=[("AWS certification never discussed", ["R3"])],
        verify=[("Ask for a queue debugging example", ["T7"])],
    )


# ---------- Q&A analysis (F5, F8-F10) ----------


def test_the_analysis_scores_job_and_company_answers_and_maps_requirements(
    ended, monkeypatch, background_runs
):
    llm = FakeLLM(ANALYSIS_ANSWERS)
    monkeypatch.setattr(qa_analysis, "invoke_llm", llm)

    analysis = analyse(ended["session"])

    assert analysis.status == RunStatus.COMPLETED
    results = analysis.results
    pairs = {pair["id"]: pair for pair in results["pairs"]}
    assert list(pairs) == ["Q1", "Q2a", "Q2b", "Q3", "Q4"]  # the invented unit is gone
    assert pairs["Q1"]["status"] == "not_scored"  # greetings are kept, not scored
    assert pairs["Q2a"]["part"] == [1, 2] and pairs["Q3"]["follow_up_of"] == "Q2a"
    # Job answers were checked against the reference passage; the company
    # answer found only a weak match, so it was judged without a document.
    assert (
        pairs["Q2a"]["verified"] is True
        and pairs["Q2a"]["sources"][0]["filename"] == "laravel-docs.md"
    )
    assert pairs["Q4"]["kind"] == "company" and pairs["Q4"]["verified"] is False
    assert set(ended["searches"]) == {"reference_library", "company_policies"}
    assert results["scored"] == 4 and (analysis.processed, analysis.total) == (4, 4)
    coverage = {c["requirement"]: c["pair_ids"] for c in results["coverage"]}
    assert coverage["Laravel"] == ["Q2a"]  # only that question names Laravel
    assert results["unexplored"] == ["PHP", "AWS Certification"]
    # Names are removed from what the LLM reads (N18).
    transcript_sent = llm.calls[0][1][1].content
    assert "Alex" not in transcript_sent and "[name]" in transcript_sent
    # Three AI requests for the whole interview: split, evaluate, review.
    assert [name for name, _messages in llm.calls] == [
        "Segmentation",
        "Evaluations",
        "InterviewReview",
    ]
    # Finished: its saved workflow state is deleted (N16).
    assert f"qa_analysis-{analysis.id}" not in saved_threads()
    # The report starts as soon as the analysis is done (B5).
    assert background_runs[-1][0] == final_assessment.RUN_KIND


def test_the_review_checks_cv_claims_and_scores_the_interview(ended, monkeypatch):
    monkeypatch.setattr(qa_analysis, "invoke_llm", FakeLLM(ANALYSIS_ANSWERS))

    results = analyse(ended["session"]).results

    # F8: only claims on real CV items; "supported" without the candidate's
    # own words is shown as never discussed; follow-ups first.
    claims = results["claims"]
    assert [(c["claim"], c["result"]) for c in claims] == [
        ("Laravel since 2019", "contradiction"),
        ("PHPUnit", "never_discussed"),
    ]
    assert (
        claims[0]["cv"]["label"] == "CV · Work history"
        and len(claims[0]["turn_ids"]) == 1
    )
    assert claims[1]["turn_ids"] == [] and claims[1]["interview_says"] == ""
    # F9: four dimensions from the evaluations, two from the review; one
    # without evidence is shown as such and left out of the average.
    score = results["interview_score"]
    dimensions = {key: d["score"] for key, d in score["dimensions"].items()}
    assert dimensions == {
        "technical": 80,  # accuracy of the three job answers
        "communication": 80,
        "relevance": 90,
        "problem_solving": 70,
        "experience_depth": None,
        "job_alignment": 70,  # Laravel: (accuracy 80 + completeness 60) / 2
    }
    assert score["overall"] == 78  # (80 + 80 + 90 + 70 + 70) / 5
    # F10: a mandatory requirement never explored → needs attention.
    quality = results["quality"]
    assert quality["verdict"] == "needs_attention"
    assert quality["reasons"] == ["Not explored: PHP."]
    assert quality["talk"] == {"interviewer": 44, "candidate": 56}
    assert [n["pair_id"] for n in quality["low_signal"]] == ["Q3"]
    assert quality["suggestions"] == [
        "Ask about PHP next time.",
        "Ask for one concrete example per skill.",
    ]


def test_answers_are_evaluated_in_batches(ended, monkeypatch):
    monkeypatch.setattr(qa_analysis, "EVALUATE_BATCH", 3)

    def skip_company(messages):
        """Evaluates every unit except the company question."""
        answer = evaluations(messages)
        answer.evaluations = [e for e in answer.evaluations if e.unit != "Q4"]
        return answer

    llm = FakeLLM(ANALYSIS_ANSWERS | {Evaluations: skip_company})
    monkeypatch.setattr(qa_analysis, "invoke_llm", llm)

    results = analyse(ended["session"]).results

    assert llm.count("Evaluations") == 2  # 4 answers in batches of 3
    q4 = next(p for p in results["pairs"] if p["id"] == "Q4")
    assert q4["status"] == "not_scored" and "Analyse again" in q4["reason"]
    assert results["scored"] == 3


def test_a_failed_analysis_continues_without_repeating_finished_steps(
    ended, monkeypatch
):
    failing = {"left": 1}

    def flaky(messages):
        """The review fails once (after the answers were evaluated)."""
        if failing["left"]:
            failing["left"] -= 1
            time.sleep(0.3)
            raise AIServiceError("The AI model test-model has reached its usage limit.")
        return review(messages)

    llm = FakeLLM(ANALYSIS_ANSWERS | {InterviewReview: flaky})
    monkeypatch.setattr(qa_analysis, "invoke_llm", llm)

    failed = analyse(ended["session"])
    assert failed.status == RunStatus.FAILED
    assert failed.error == "The AI model test-model has reached its usage limit."

    with SessionLocal() as db:  # "Try again"
        qa_analysis.start_analysis(db, ended["session"])
    runner.execute_run(qa_analysis.RUN_KIND, failed.id)

    with SessionLocal() as db:
        done = db.get(QAAnalysis, failed.id)
    assert done.status == RunStatus.COMPLETED and done.results["scored"] == 4
    assert llm.count("Segmentation") == 1 and llm.count("Evaluations") == 1
    assert llm.count("InterviewReview") == 2  # only the failed step again


def test_an_interview_without_a_transcript_is_analysed_as_empty(ended, monkeypatch):
    with SessionLocal() as db:
        for turn in db.query(TranscriptTurn).filter_by(session_id=ended["session"]):
            db.delete(turn)
        db.commit()
    llm = FakeLLM({})
    monkeypatch.setattr(qa_analysis, "invoke_llm", llm)

    analysis = analyse(ended["session"])

    assert analysis.status == RunStatus.COMPLETED
    results = analysis.results
    assert results["pairs"] == [] and results["scored"] == 0
    assert len(results["unexplored"]) == 3
    assert results["interview_score"] is None and results["claims"] == []
    assert results["quality"]["verdict"] == "poor"
    assert "There is no transcript of this interview." in results["quality"]["reasons"]
    assert llm.calls == []  # nothing to send


# ---------- assessment report (F6) ----------


def prepare_report(ended, monkeypatch, answer, repair=None) -> FakeLLM:
    """Analyse the interview, then write its report up to the review."""
    monkeypatch.setattr(qa_analysis, "invoke_llm", FakeLLM(ANALYSIS_ANSWERS))
    analyse(ended["session"])
    llm = FakeLLM({Findings: answer, Repair: repair or (lambda m: Repair(findings=[]))})
    monkeypatch.setattr(final_assessment, "invoke_llm", llm)
    with SessionLocal() as db:
        report_id = final_assessment.start_report(db, ended["session"]).id
    runner.execute_run(final_assessment.RUN_KIND, report_id)
    return llm


def test_the_report_merges_scores_and_waits_for_review(ended, monkeypatch):
    llm = prepare_report(ended, monkeypatch, good_findings())

    report = report_of(ended["session"])
    assert report.status == RunStatus.WAITING_FOR_REVIEW
    assert report.review_status == ReviewStatus.PENDING_REVIEW
    assert llm.count("Findings") == 1  # one AI request for the report
    assert f"final_assessment-{report.id}" in saved_threads()  # waits for review
    content = report.content
    assert content["version"] == 1
    components = content["components"]
    assert components["cv"]["overall"] == 84
    assert components["interview"]["overall"] == 78  # the interview score (F9)
    assert components["coverage"] == {
        "explored": 1,
        "total": 3,
        "unexplored": ["PHP", "AWS Certification"],
    }
    # CV 84 and interview 78 → 81: the "Strong fit" step.
    assert content["position"] | {"headline": None} == {
        "key": "strong_fit",
        "label": "Strong fit",
        "score": 81,
        "headline": None,
    }
    assert content["position"]["headline"] == "Strong fit, with gaps to verify"
    # Every cited id is in the sources, with its label for the page.
    assert content["sources"]["T4"]["label"] == "Transcript 00:15"
    assert content["sources"]["CV1"]["label"] == "CV · Work history"
    # "Never discussed" rests on the requirement's coverage record.
    assert content["sources"]["R3"] == {
        "kind": "requirement",
        "label": "Requirement · AWS Certification",
        "text": "AWS Certification (preferred). CV screening: not checked. "
        "Interview: never explored.",
    }
    requirements = {r["requirement"]: r for r in content["requirements"]}
    assert requirements["PHP"]["cv"] == "met" and requirements["Laravel"][
        "pair_ids"
    ] == ["Q2a"]
    # CV claims to follow up (F8) cite the transcript; supported ones are left out.
    assert [(c["claim"], c["sources"]) for c in content["claims"]] == [
        ("Laravel since 2019", ["T7"]),
        ("PHPUnit", []),
    ]
    assert "T7" in content["sources"]
    assert content["quality"] == {
        "verdict": "needs_attention",
        "reasons": ["Not explored: PHP."],
    }
    assert content["identity"]["state"] == "not_checked"


def test_without_scored_answers_the_report_says_it_rests_on_the_cv(ended, monkeypatch):
    with SessionLocal() as db:
        for turn in db.query(TranscriptTurn).filter_by(session_id=ended["session"]):
            db.delete(turn)
        db.commit()
    prepare_report(
        ended,
        monkeypatch,
        report_answer(gaps=[("The interview was not transcribed", ["R1", "R2", "R3"])]),
    )

    content = report_of(ended["session"]).content
    assert content["components"]["interview"] is None
    assert content["position"]["headline"] == (
        "Strong fit on the CV alone: no interview answers were scored"
    )


def test_unsupported_conclusions_are_repaired_then_marked(ended, monkeypatch):
    attempts = []

    def repair(messages):
        """Finds evidence for the weakness, never for the invented claim."""
        attempts.append(messages[1].content)
        fixes = [RepairedFinding(number=n, text="", sources=["X9"]) for n in (1, 2)]
        if len(attempts) == 1:  # the weakness gets real evidence on the first try
            fixes[0] = RepairedFinding(
                number=1, text="Little testing depth", sources=["T5"]
            )
        return Repair(findings=fixes)

    answer = report_answer(
        strengths=[("Builds Laravel APIs", ["T4"])],
        weaknesses=[("Little testing depth", ["T99"])],  # no such line
        verify=[("Invented claim", ["made-up"])],
    )
    prepare_report(ended, monkeypatch, answer, repair)

    content = report_of(ended["session"]).content
    assert len(attempts) == final_assessment.MAX_REPAIRS  # then it stops trying
    assert content["findings"]["weaknesses"] == [
        {"text": "Little testing depth", "sources": ["T5"]}
    ]
    assert content["findings"]["verify"] == [
        {"text": "Invented claim", "sources": [], "unsupported": True}
    ]
    assert "X9" not in content["sources"] and "made-up" not in content["sources"]
    # No evidence gaps were found, so the headline does not mention any.
    assert content["position"]["headline"] == "Strong fit"


def test_changes_requested_then_approved(ended, monkeypatch, interviewer, client):
    llm = prepare_report(ended, monkeypatch, good_findings())
    monkeypatch.setattr(final_assessment, "start_run", runner.execute_run)
    url = f"/api/interviews/{ended['session']}/report"

    changed = client.post(
        f"{url}/review",
        json={
            "action": "request_changes",
            "feedback": "The testing point ignores 00:20.",
        },
        headers=interviewer,
    )

    assert changed.status_code == 200
    # The page then polls the report (here the run already finished).
    report = client.get(url, headers=interviewer).json()["report"]
    assert (
        report["status"] == "waiting_for_review"
        and report["review_status"] == "pending_review"
    )
    content = report["content"]
    assert content["version"] == 2
    assert content["feedback"] == "The testing point ignores 00:20."
    assert content["changes"] == "The testing point now cites the answer."
    # Written again in one request with the comment and the reviewed version,
    # which also said what changed.
    revisions = [m[0].content for name, m in llm.calls if name == "Findings"]
    assert len(revisions) == 2
    assert "ignores 00:20" in revisions[1] and "Previous version" in revisions[1]

    approved = client.post(
        f"{url}/review", json={"action": "approve"}, headers=interviewer
    )

    assert approved.status_code == 200
    report = client.get(url, headers=interviewer).json()["report"]
    assert report["status"] == "completed" and report["review_status"] == "approved"
    # Kept while it waited for the review, deleted once approved (N16).
    assert f"final_assessment-{report['id']}" not in saved_threads()
    assert report["approved_at"] is not None and report["reviewed_by"] == "Sam Rivers"
    assert report["content"]["version"] == 2  # the reviewed version is the final one
    again = client.post(
        f"{url}/review", json={"action": "approve"}, headers=interviewer
    )
    assert again.status_code == 409  # nothing waits for review any more


def test_a_change_request_needs_a_comment(ended, monkeypatch, interviewer, client):
    prepare_report(ended, monkeypatch, good_findings())

    answer = client.post(
        f"/api/interviews/{ended['session']}/report/review",
        json={"action": "request_changes", "feedback": "   "},
        headers=interviewer,
    )

    assert answer.status_code == 422
    assert report_of(ended["session"]).review_status == ReviewStatus.PENDING_REVIEW


def test_the_export_is_a_printable_html_file(ended, monkeypatch, interviewer, client):
    prepare_report(ended, monkeypatch, good_findings())

    answer = client.get(
        f"/api/interviews/{ended['session']}/report/export", headers=interviewer
    )

    assert answer.status_code == 200
    assert answer.headers["content-type"].startswith("text/html")
    assert "attachment" in answer.headers["content-disposition"]
    assert "Alex Strong" in answer.text and "Not yet approved" in answer.text
    assert "Transcript 00:15" in answer.text
    assert (
        "CV claims to follow up" in answer.text and "Interview quality" in answer.text
    )


def test_the_reports_of_a_job_list_every_ended_interview(
    ended, monkeypatch, interviewer, client
):
    prepare_report(ended, monkeypatch, good_findings())

    answer = client.get(f"/api/jobs/{ended['job']}/reports", headers=interviewer)

    (row,) = answer.json()
    assert (
        row["interview_id"] == ended["session"]
        and row["candidate_name"] == "Alex Strong"
    )
    assert row["analysis_status"] == "completed"
    assert row["report"]["content"]["position"]["key"] == "strong_fit"


# ---------- API rules ----------


def test_only_an_ended_interview_is_analysed(ended, interviewer, client):
    with SessionLocal() as db:
        db.get(InterviewSession, ended["session"]).status = SessionStatus.LIVE
        db.commit()

    answer = client.post(
        f"/api/interviews/{ended['session']}/analysis", json={}, headers=interviewer
    )

    assert answer.status_code == 409 and "not ended" in answer.json()["detail"]


def test_ending_an_interview_starts_its_analysis(
    ended, interviewer, client, background_runs
):
    with SessionLocal() as db:
        db.get(InterviewSession, ended["session"]).status = SessionStatus.LIVE
        db.commit()

    client.post(f"/api/interviews/{ended['session']}/end", headers=interviewer)

    analysis = client.get(
        f"/api/interviews/{ended['session']}/analysis", headers=interviewer
    )
    assert analysis.json()["run"]["status"] == "pending"
    assert background_runs[-1][0] == qa_analysis.RUN_KIND


def test_analysing_again_replaces_the_analysis_and_the_report(
    ended, monkeypatch, interviewer, client
):
    prepare_report(ended, monkeypatch, good_findings())
    before = report_of(ended["session"]).id

    answer = client.post(
        f"/api/interviews/{ended['session']}/analysis",
        json={"again": True},
        headers=interviewer,
    )

    assert (
        answer.json()["run"]["status"] == "pending" and answer.json()["results"] is None
    )
    assert (
        report_of(ended["session"]) is None
    )  # rests on the new analysis: made again later
    with SessionLocal() as db:
        assert db.get(AssessmentReport, before) is None


def test_a_report_needs_a_finished_analysis(ended, interviewer, client):
    answer = client.post(
        f"/api/interviews/{ended['session']}/report", json={}, headers=interviewer
    )

    assert (
        answer.status_code == 409
        and "Q&A analysis must finish" in answer.json()["detail"]
    )


def test_candidates_never_see_analyses_or_reports(ended, client):
    token = create_access_token(ended["session"], Role.CANDIDATE)
    candidate = {"Authorization": f"Bearer {token}"}
    base = f"/api/interviews/{ended['session']}"

    for url in (f"{base}/analysis", f"{base}/report", f"{base}/report/export"):
        assert client.get(url, headers=candidate).status_code == 403
    assert (
        client.get(f"/api/jobs/{ended['job']}/reports", headers=candidate).status_code
        == 403
    )
    assert (
        client.post(
            f"{base}/report/review", json={"action": "approve"}, headers=candidate
        ).status_code
        == 403
    )
