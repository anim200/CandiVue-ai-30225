"""Identity check (F7): the decision rules, consent and the face reference
(stored encrypted, deleted on withdrawal and after the retention time), the
interviewer's view (profile only on a confident match), "Check again", the
live comparison and the report line. No real faces: the face model is a
fake that reads a person's "face" from the first byte of the picture; one
test checks that the real models load and find no face in a blank image.
"""

from datetime import timedelta

import numpy as np
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select

from app.auth.security import Role, create_access_token
from app.core import clock
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import Candidate, FaceReference, InterviewSession, Job
from app.db.models.interview import IdentityConsent, InvitationStatus, SessionStatus
from app.identity import faces, references, watcher
from app.identity.faces import FaceError
from app.identity.matching import MATCH_FROM, Sample, decide, identity_summary
from app.interviews import planning

pytestmark = pytest.mark.usefixtures("database_available")

# Unit vectors standing for three people's faces.
ALEX, BEA, CAL = np.eye(3, 128, dtype=np.float32)


def fake_face(image) -> np.ndarray:
    """The fake face model: the picture's first byte says whose face it is
    (0 → no face, 9 → two faces, 1/2/3 → Alex/Bea/Cal)."""
    who = int(image[0])
    if who == 0:
        raise FaceError("no_face")
    if who == 9:
        raise FaceError("several_faces")
    return (ALEX, BEA, CAL)[who - 1]


def picture(who: int) -> bytes:
    """A "picture" of a person for the fake model."""
    return bytes([who, 0, 0])


@pytest.fixture(autouse=True)
def fake_faces(monkeypatch):
    """The fake face model, and a fresh encryption key."""
    monkeypatch.setattr(
        references, "decode_image", lambda data: np.frombuffer(data, np.uint8)
    )
    monkeypatch.setattr(references, "face_embedding", fake_face)
    monkeypatch.setattr(watcher, "face_embedding", fake_face)
    monkeypatch.setattr(
        get_settings(), "face_reference_key", SecretStr(Fernet.generate_key().decode())
    )


@pytest.fixture
def interview():
    """A job with two invited candidates (Alex and Bea), one interview each."""
    with SessionLocal() as db:
        job = Job(title="PHP Developer", profile={"requirements": []})
        db.add(job)
        db.flush()
        sessions = []
        for name in ("Alex Strong", "Bea Good"):
            candidate = Candidate(
                job_id=job.id,
                full_name=name,
                email=f"{name.split()[0].lower()}@example.com",
                cv_filename="cv.pdf",
                parsed_cv={
                    "years_experience": 6,
                    "years_source": "dates",
                    "jobs": [{"title": "PHP Developer"}],
                    "sections": {"skills": "PHP, Laravel, Docker"},
                },
            )
            db.add(candidate)
            db.flush()
            session = InterviewSession(
                candidate_id=candidate.id,
                job_id=job.id,
                scheduled_at=clock.now() + timedelta(hours=1),
                join_token_hash=planning.new_link_token()[1],
                invitation_status=InvitationStatus.SENT,
            )
            db.add(session)
            db.flush()
            sessions.append(session.id)
        db.commit()
        ids = {"job": job.id, "alex": sessions[0], "bea": sessions[1]}
    yield ids
    with SessionLocal() as db:
        db.delete(db.get(Job, ids["job"]))
        db.commit()


def as_candidate(session_id: int) -> dict:
    """The candidate's Authorization header for their interview."""
    return {
        "Authorization": f"Bearer {create_access_token(session_id, Role.CANDIDATE)}"
    }


def as_interviewer() -> dict:
    """An interviewer's Authorization header."""
    return {"Authorization": f"Bearer {create_access_token(1, Role.INTERVIEWER)}"}


def enrol(client, session_id: int, who: int, shots=(None, None, None)):
    """Send three pictures, as the candidate's page does."""
    files = [
        ("pictures", (f"{i}.jpg", picture(who if s is None else s), "image/jpeg"))
        for i, s in enumerate(shots)
    ]
    return client.post(
        "/api/candidate/identity", files=files, headers=as_candidate(session_id)
    )


# ---------- the decision rules ----------


def test_one_bad_picture_never_decides_and_identity_is_never_assumed():
    same, unsure, other = Sample(own=0.8), Sample(own=0.33), Sample(own=0.1)

    assert decide([same])["state"] == "checking"  # not enough pictures yet
    assert decide([same, same])["state"] == "matched"
    assert decide([same, Sample(problem="no_face"), same])["state"] == "matched"
    assert decide([unsure, unsure, same])["state"] == "low_confidence"
    assert decide([other, other])["state"] == "no_match"
    assert decide([Sample(problem="several_faces")] * 3)["state"] == "several_faces"
    assert decide([Sample(problem="camera_off")] * 3)["state"] == "camera_off"
    # Clearly another applicant of the job: no match, with their name.
    someone = Sample(own=0.3, other=("Bea Good", 0.9))
    assert decide([someone, someone]) == {
        "state": "no_match",
        "similarity": 0.3,
        "other": "Bea Good",
    }
    assert MATCH_FROM > 0.363  # a margin above SFace's own threshold


# ---------- consent and the face reference ----------


def test_the_reference_is_stored_encrypted_and_only_with_consent(client, interview):
    before = client.get(
        "/api/candidate/interview", headers=as_candidate(interview["alex"])
    )
    assert before.json()["identity"] == {
        "available": True,
        "consent": None,
        "retention_days": 30,
    }

    given = enrol(client, interview["alex"], who=1)

    assert given.status_code == 200 and given.json()["identity"]["consent"] == "given"
    with SessionLocal() as db:
        stored = db.scalar(
            select(FaceReference).where(FaceReference.session_id == interview["alex"])
        )
        assert stored.embedding[:5] == b"gAAAA"  # Fernet ciphertext, not the numbers
        own = references.job_references(
            db, db.get(InterviewSession, interview["alex"])
        )["own"]
        assert np.allclose(own[0], ALEX)


@pytest.mark.parametrize(
    "shots, message",
    [
        ((1, 0, 1), "No face found"),
        ((1, 9, 1), "More than one face"),
        ((1, 2, 1), "do not look alike"),
    ],
    ids=["no face", "two faces", "different people"],
)
def test_unusable_pictures_are_refused_with_the_reason(
    client, interview, shots, message
):
    answer = enrol(client, interview["alex"], who=1, shots=shots)

    assert answer.status_code == 422 and message in answer.json()["detail"]
    with SessionLocal() as db:
        assert not db.scalar(
            select(FaceReference.id).where(
                FaceReference.session_id == interview["alex"]
            )
        )


def test_withdrawing_deletes_the_reference_at_once(client, interview):
    enrol(client, interview["alex"], who=1)

    answer = client.delete(
        "/api/candidate/identity", headers=as_candidate(interview["alex"])
    )

    assert answer.json()["identity"]["consent"] == "declined"
    with SessionLocal() as db:
        assert not db.scalar(
            select(FaceReference.id).where(
                FaceReference.session_id == interview["alex"]
            )
        )


def test_without_the_key_the_candidate_is_not_asked(client, interview, monkeypatch):
    monkeypatch.setattr(get_settings(), "face_reference_key", None)

    shown = client.get(
        "/api/candidate/interview", headers=as_candidate(interview["alex"])
    )

    assert shown.json()["identity"]["available"] is False
    assert enrol(client, interview["alex"], who=1).status_code == 409


def test_references_are_deleted_after_the_retention_time(client, interview):
    enrol(client, interview["alex"], who=1)
    enrol(client, interview["bea"], who=2)
    with SessionLocal() as db:
        alex = db.get(InterviewSession, interview["alex"])
        alex.status, alex.ended_at = (
            SessionStatus.ENDED,
            clock.now() - timedelta(days=31),
        )
        db.commit()

        assert references.purge_expired(db) == 1  # Bea's interview is still to come
        left = db.scalars(select(FaceReference.session_id)).all()
        assert interview["alex"] not in left and interview["bea"] in left

        db.get(InterviewSession, interview["bea"]).status = SessionStatus.CANCELLED
        db.commit()
        assert references.purge_expired(db) == 1  # cancelled: deleted


# ---------- the live check and the interviewer's view ----------


def test_the_live_check_compares_with_the_job_references(client, interview):
    enrol(client, interview["alex"], who=1)
    enrol(client, interview["bea"], who=2)
    with SessionLocal() as db:
        refs = references.job_references(
            db, db.get(InterviewSession, interview["alex"])
        )

    alex = watcher.compare(np.array([1], np.uint8), refs)
    bea = watcher.compare(np.array([2], np.uint8), refs)
    nobody = watcher.compare(np.array([0], np.uint8), refs)

    assert alex.own == pytest.approx(1.0) and alex.other == (
        "Bea Good",
        pytest.approx(0.0),
    )
    assert (
        decide([bea, bea])["state"] == "no_match"
        and decide([bea, bea])["other"] == "Bea Good"
    )
    assert nobody.problem == "no_face"


def test_a_candidate_without_consent_is_never_checked(client, interview):
    with SessionLocal() as db:
        assert (
            references.job_references(db, db.get(InterviewSession, interview["alex"]))
            is None
        )

    view = client.get(
        f"/api/interviews/{interview['alex']}/identity", headers=as_interviewer()
    ).json()

    assert view["state"] == "no_reference" and view["profile"] is None


def test_the_profile_is_shown_only_on_a_confident_match(client, interview):
    enrol(client, interview["alex"], who=1)
    url = f"/api/interviews/{interview['alex']}/identity"

    def show(result):
        """Save a live result, then read the interviewer's view."""
        with SessionLocal() as db:
            db.get(InterviewSession, interview["alex"]).identity_result = result
            db.commit()
        return client.get(url, headers=as_interviewer()).json()

    unsure = show({"state": "low_confidence", "similarity": 0.33})
    matched = show({"state": "matched", "similarity": 0.81, "confirmed_at_ms": 4000})

    assert unsure["profile"] is None and "Low confidence" in unsure["text"]
    profile = matched["profile"]
    assert profile["name"] == "Alex Strong" and profile["skills"] == [
        "PHP",
        "Laravel",
        "Docker",
    ]
    assert (
        profile["headline"] == "About 6 years of experience, latest role: PHP Developer"
    )

    rechecked = client.post(f"{url}/recheck", headers=as_interviewer()).json()

    assert rechecked["state"] == "checking" and rechecked["profile"] is None
    with SessionLocal() as db:
        session = db.get(InterviewSession, interview["alex"])
        assert session.identity_recheck_at is not None
        assert session.identity_result["confirmed_at_ms"] == 4000  # kept for the report


def test_the_report_says_whether_the_identity_was_confirmed(interview):
    with SessionLocal() as db:
        session = db.get(InterviewSession, interview["alex"])
        assert identity_summary(session)["state"] == "not_checked"
        session.identity_consent = IdentityConsent.GIVEN
        session.identity_result = {"state": "matched", "confirmed_at_ms": 4000}
        assert identity_summary(session) == {
            "state": "confirmed",
            "text": "Confirmed by face recognition at 00:04 against the reference "
            "given with consent.",
        }
        session.identity_result = {"state": "no_match", "confirmed_at_ms": None}
        assert identity_summary(session)["state"] == "not_confirmed"


def test_candidates_never_see_the_identity_result(client, interview):
    candidate = as_candidate(interview["alex"])
    url = f"/api/interviews/{interview['alex']}/identity"

    assert client.get(url, headers=candidate).status_code == 403
    assert client.post(f"{url}/recheck", headers=candidate).status_code == 403


def test_the_real_face_models_load_and_find_no_face_in_a_blank_picture():
    with pytest.raises(FaceError) as error:
        faces.face_embedding(np.full((240, 320, 3), 200, np.uint8))

    assert error.value.reason == "no_face"
