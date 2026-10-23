"""Final ranking (§4B-15 f): only approved reports are ranked, by the
overall score, then the interview score; equal candidates share a rank;
everyone else gets the reason they are not ranked; a candidate interviewed
twice counts once (the latest interview). Pure function, no database."""

from datetime import UTC, datetime, timedelta

from app.analysis.final_ranking import NOT_RANKED, Entry, rank

DAY = datetime(2026, 10, 20, 10, 0, tzinfo=UTC)


def entry(
    interview_id, candidate_id, overall=None, interview=None, report="approved", day=0
):
    """One ended interview of the job."""
    return Entry(
        interview_id=interview_id,
        candidate_id=candidate_id,
        held_at=DAY + timedelta(days=day),
        report=report,
        overall=overall,
        interview=interview,
    )


def test_higher_overall_score_first_then_the_interview_score():
    places = rank(
        [
            entry(1, 1, overall=72, interview=70),
            entry(2, 2, overall=88, interview=80),
            entry(3, 3, overall=72, interview=90),  # same overall, better interview
        ]
    )

    assert places == {2: (1, None), 3: (2, None), 1: (3, None)}


def test_equal_candidates_share_a_rank():
    places = rank(
        [
            entry(1, 1, overall=80, interview=75),
            entry(2, 2, overall=80, interview=75),
            entry(3, 3, overall=60, interview=60),
        ]
    )

    assert places[1] == places[2] == (1, None)
    assert places[3] == (3, None)  # 1, 1, 3


def test_only_approved_reports_are_ranked_with_the_reason_for_the_others():
    places = rank(
        [
            entry(1, 1, overall=90, report="pending_review"),
            entry(2, 2, overall=85, report="changes_requested"),
            entry(3, 3, report="no_report"),
            entry(4, 4, report="failed"),
            entry(5, 5, overall=None),  # approved, but not enough evidence
            entry(6, 6, overall=50, interview=40),
        ]
    )

    assert places[1] == (None, NOT_RANKED["pending_review"])
    assert places[2] == (None, NOT_RANKED["changes_requested"])
    assert places[3] == (None, NOT_RANKED["no_report"])
    assert places[4] == (None, NOT_RANKED["failed"])
    assert places[5] == (None, NOT_RANKED["no_score"])
    assert places[6] == (1, None)  # the only approved one ranks first


def test_a_candidate_interviewed_twice_counts_once():
    places = rank(
        [
            entry(1, 7, overall=90, interview=90, day=0),  # earlier interview
            entry(2, 7, overall=60, interview=55, day=3),  # the latest one counts
            entry(3, 8, overall=70, interview=70),
        ]
    )

    assert places[1] == (None, NOT_RANKED["earlier"])
    assert places == places | {3: (1, None), 2: (2, None)}


def test_no_interviews_no_ranking():
    assert rank([]) == {}
