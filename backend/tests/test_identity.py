"""Identity check (F7, §4B-15): the photo sent with the application is
processed once the applicant is invited (stored encrypted, deleted after
the retention time), the candidate checks in with three camera pictures,
the interviewer sees the photo and the match score (the profile only on a
match), and the candidate never sees the result.

No real faces: the face model is a fake that reads whose "face" a picture
shows from its first pixel value. The photo reading (types, size, EXIF
rotation) uses real images made here; one test checks that the real face
models load and find no face in a blank image.
"""

import io
from datetime import timedelta

import numpy as np
import pillow_heif
import pytest
from cryptography.fernet import Fernet
from PIL import Image
from pydantic import SecretStr
from sqlalchemy import select

from app.auth.security import Role, create_access_token
from app.core import clock
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import ApplicationPhoto, Candidate, InterviewSession, Job
from app.db.models.interview import InvitationStatus, PhotoStatus, SessionStatus
from app.identity import checkin, faces, photos, references
from app.identity.faces import FaceError
from app.identity.matching import decide, identity_summary, score
from app.identity.photos import PhotoError, read_photo
from app.interviews import planning

pytestmark = pytest.mark.usefixtures("database_available")

# Unit vectors standing for people's faces: Alex, Bea, Cal; then pictures
# that look 32 % and 10 % like Alex (similarity to ALEX: 0.32 and 0.10).
ALEX, BEA, CAL, OTHER = np.eye(4, 128, dtype=np.float32)


def like_alex(similarity: float) -> np.ndarray:
    """A face whose similarity to Alex is exactly `similarity`."""
    return (similarity * ALEX + np.sqrt(1 - similarity**2) * OTHER).astype(np.float32)


FACES = {1: ALEX, 2: BEA, 3: CAL, 4: like_alex(0.32), 5: like_alex(0.10)}
# 0: no face, 9: two people, 7: face too small, 8: too dark.
PROBLEMS = {0: "no_face", 9: "several_faces", 7: "too_small"}


def who(image) -> int:
    """Whose face the fake model sees: the picture's first pixel value."""
    return int(np.asarray(image).flat[0])


def fake_find_face(image) -> np.ndarray:
    """The fake detector: a face box, or the problem the value stands for."""
    if who(image) in PROBLEMS:
        raise FaceError(PROBLEMS[who(image)])
    return np.array([10, 10, 40, 40], np.float32)


def fake_check_light(image, face) -> None:
    """The fake light check: value 8 is too dark."""
    if who(image) == 8:
        raise FaceError("too_dark")


def fake_embedding(image, face=None) -> np.ndarray:
    """The fake recogniser: the face the value stands for."""
    return FACES.get(who(image), ALEX)


def picture(person: int) -> bytes:
    """A camera "picture" of a person for the fake model."""
    return bytes([person, 0, 0])


def photo_file(person: int, fmt: str = "PNG", size=(100, 100)) -> bytes:
    """A real image file whose first pixel value says whose photo it is."""
    buffer = io.BytesIO()
    Image.new("RGB", size, (0, 0, person)).save(buffer, fmt)  # BGR: blue first
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def fake_faces(monkeypatch):
    """The fake face model, and a fresh encryption key."""
    monkeypatch.setattr(
        faces, "decode_image", lambda data: np.frombuffer(data, np.uint8)
    )
    monkeypatch.setattr(faces, "find_face", fake_find_face)
    monkeypatch.setattr(faces, "check_light", fake_check_light)
    monkeypatch.setattr(faces, "face_embedding", fake_embedding)
    monkeypatch.setattr(
        get_settings(), "face_reference_key", SecretStr(Fernet.generate_key().decode())
    )


@pytest.fixture
def interview():
    """A job with two invited applicants (Alex and Bea), one interview each,
    both with a photo and consent from the form (not processed yet)."""
    with SessionLocal() as db:
        job = Job(title="PHP Developer", profile={"requirements": []})
        db.add(job)
        db.flush()
        ids = {"job": job.id}
        for key, name in (("alex", "Alex Strong"), ("bea", "Bea Good")):
            candidate = Candidate(
                job_id=job.id,
                full_name=name,
                email=f"{key}@example.com",
                cv_filename="cv.pdf",
                photo_file_id=f"photo-{key}",
                photo_consent=True,
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
            ids[key], ids[f"{key}_candidate"] = session.id, candidate.id
        db.commit()
    yield ids
    with SessionLocal() as db:
        db.delete(db.get(Job, ids["job"]))
        db.commit()


def give_photo(candidate_id: int, person: int) -> PhotoStatus:
    """Process an application photo as the CV Collector does."""
    with SessionLocal() as db:
        return references.save_photo(
            db, db.get(Candidate, candidate_id), photo_file(person)
        )


def as_candidate(session_id: int) -> dict:
    """The candidate's Authorization header for their interview."""
    return {
        "Authorization": f"Bearer {create_access_token(session_id, Role.CANDIDATE)}"
    }


def as_interviewer() -> dict:
    """An interviewer's Authorization header."""
    return {"Authorization": f"Bearer {create_access_token(1, Role.INTERVIEWER)}"}


def check_in(client, session_id: int, person: int, shots=(None, None, None)):
    """Send three camera pictures, as the candidate's page does."""
    files = [
        ("pictures", (f"{i}.jpg", picture(person if s is None else s), "image/jpeg"))
        for i, s in enumerate(shots)
    ]
    return client.post(
        "/api/candidate/identity", files=files, headers=as_candidate(session_id)
    )


def view(client, session_id: int) -> dict:
    """What the interviewer sees for the interview."""
    return client.get(
        f"/api/interviews/{session_id}/identity", headers=as_interviewer()
    ).json()


# ---------- the match score and the decision rules ----------


def test_the_match_score_scale():
    assert [score(s) for s in (-0.2, 0, 0.14, 0.28, 0.363, 0.70, 0.95)] == [
        0,
        0,
        20,
        40,  # the "unsure" line
        60,  # SFace's own same-person line
        100,
        100,
    ]


def test_the_decision_rules():
    assert decide([0.8, 0.75, 0.82], [])["state"] == "matched"
    assert decide([0.8, 0.75, 0.82], [])["score"] == 100
    assert decide([0.32, 0.33, 0.34], [])["state"] == "not_confirmed"
    assert decide([0.1, 0.05, 0.12], [])["state"] == "no_match"
    # A good average with one clearly different picture is not a match.
    assert decide([0.9, 0.9, 0.1], [])["state"] == "not_confirmed"
    # Clearly closer to another applicant of the job: named.
    other = decide([0.1, 0.1, 0.1], [("Bea Good", [0.9, 0.85, 0.88])])
    assert other["state"] == "other_applicant" and other["other"] == "Bea Good"
    # Another applicant only a little closer does not count.
    assert decide([0.6] * 3, [("Bea Good", [0.65] * 3)])["state"] == "matched"


# ---------- the application photo ----------


def test_only_invited_applicants_with_consent_have_their_photo_processed(interview):
    with SessionLocal() as db:
        waiting = {c.id for c in references.photos_to_process(db)}
        assert waiting == {interview["alex_candidate"], interview["bea_candidate"]}

        alex = db.get(Candidate, interview["alex_candidate"])
        alex.photo_consent = False  # did not tick the photo consent
        bea_session = db.get(InterviewSession, interview["bea"])
        bea_session.invitation_status = InvitationStatus.PENDING  # not emailed yet
        db.commit()
        assert references.photos_to_process(db) == []


def test_a_photo_is_stored_encrypted_with_a_small_copy(interview):
    assert give_photo(interview["alex_candidate"], 1) == PhotoStatus.READY

    with SessionLocal() as db:
        photo = db.scalar(
            select(ApplicationPhoto).where(
                ApplicationPhoto.candidate_id == interview["alex_candidate"]
            )
        )
        assert photo.embedding[:5] == b"gAAAA" and photo.thumbnail[:5] == b"gAAAA"
        small = Image.open(
            io.BytesIO(references.thumbnail(db, interview["alex_candidate"]))
        )
        assert small.format == "JPEG" and small.size == (photos.THUMBNAIL_SIDE,) * 2
        own = references.job_photos(db, db.get(InterviewSession, interview["alex"]))[
            "own"
        ]
        assert np.allclose(own, ALEX)
        assert references.photos_to_process(db)[0].id == interview["bea_candidate"]


@pytest.mark.parametrize(
    "person, status",
    [
        (0, PhotoStatus.NO_FACE),
        (9, PhotoStatus.SEVERAL_FACES),
        (7, PhotoStatus.TOO_SMALL),
    ],
    ids=["no face", "two people", "face too small"],
)
def test_an_unusable_photo_keeps_only_the_reason(interview, client, person, status):
    assert give_photo(interview["alex_candidate"], person) == status

    shown = view(client, interview["alex"])
    assert shown["state"] == "no_photo" and shown["photo"]["available"] is False
    assert (
        shown["photo"]["text"]
        == photos.TEXTS[status][0].lower() + photos.TEXTS[status][1:]
    )
    with SessionLocal() as db:
        assert references.thumbnail(db, interview["alex_candidate"]) is None


def test_a_failed_download_is_tried_again_a_few_times(interview):
    with SessionLocal() as db:
        alex = db.get(Candidate, interview["alex_candidate"])
        for _ in range(references.MAX_DOWNLOAD_TRIES):
            assert alex.id in {c.id for c in references.photos_to_process(db)}
            references.photo_download_failed(db, alex)
        assert alex.id not in {c.id for c in references.photos_to_process(db)}
        assert references.photo_state(db, alex) == "download_failed"


def test_photo_types_size_and_rotation_are_handled():
    assert read_photo(photo_file(1, "JPEG")).shape == (100, 100, 3)
    assert read_photo(photo_file(1, "WEBP")).shape == (100, 100, 3)
    heic = io.BytesIO()
    pillow_heif.from_pillow(Image.new("RGB", (64, 48), (0, 0, 1))).save(
        heic, quality=90
    )
    assert read_photo(heic.getvalue()).shape == (48, 64, 3)  # an iPhone photo

    # A phone photo stored sideways with an EXIF note is turned upright.
    sideways = io.BytesIO()
    exif = Image.Exif()
    exif[0x0112] = 6  # "rotate 90° to show"
    Image.new("RGB", (120, 80)).save(sideways, "JPEG", exif=exif)
    assert read_photo(sideways.getvalue()).shape[:2] == (120, 80)

    # Very large photos are scaled down before the face search.
    assert (
        max(read_photo(photo_file(1, "PNG", (3000, 2000))).shape[:2]) == photos.MAX_SIDE
    )

    for data, status in (
        (b"%PDF-1.4 not a photo", PhotoStatus.UNREADABLE),
        (b"\xff\xd8\xff" + b"broken", PhotoStatus.UNREADABLE),
        (b"\xff\xd8\xff" + bytes(photos.MAX_PHOTO_BYTES), PhotoStatus.TOO_LARGE),
    ):
        with pytest.raises(PhotoError) as error:
            read_photo(data)
        assert error.value.status == status


# ---------- check-in ----------


def test_the_candidate_checks_in_only_when_the_photo_is_ready(client, interview):
    url, headers = "/api/candidate/interview", as_candidate(interview["alex"])
    assert client.get(url, headers=headers).json()["identity"]["available"] is False
    assert (
        check_in(client, interview["alex"], 1).status_code == 422
    )  # nothing to compare

    give_photo(interview["alex_candidate"], 1)

    assert client.get(url, headers=headers).json()["identity"] == {
        "available": True,
        "consent": None,
        "retention_days": 30,
    }


def test_a_matching_check_in_shows_the_score_and_profile(client, interview):
    give_photo(interview["alex_candidate"], 1)

    answer = check_in(client, interview["alex"], 1)

    assert answer.status_code == 200
    candidate_side = answer.json()["identity"]
    assert candidate_side["consent"] == "given"
    assert "score" not in str(answer.json()) and "match" not in str(answer.json())  # N9
    shown = view(client, interview["alex"])
    assert shown["state"] == "matched" and shown["score"] == 100
    assert shown["text"] == "Matches the application photo"
    assert shown["photo"]["available"] is True
    assert shown["profile"]["name"] == "Alex Strong"
    assert shown["profile"]["skills"] == ["PHP", "Laravel", "Docker"]


@pytest.mark.parametrize(
    "person, state, score_range",
    [(4, "not_confirmed", (40, 59)), (5, "no_match", (0, 39)), (3, "no_match", (0, 0))],
    ids=["unsure", "different person", "stranger"],
)
def test_a_doubtful_check_in_never_shows_the_profile(
    client, interview, person, state, score_range
):
    give_photo(interview["alex_candidate"], 1)

    assert check_in(client, interview["alex"], person).status_code == 200

    shown = view(client, interview["alex"])
    assert shown["state"] == state and shown["profile"] is None
    assert score_range[0] <= shown["score"] <= score_range[1]


def test_another_applicant_at_the_check_in_is_named(client, interview):
    give_photo(interview["alex_candidate"], 1)
    give_photo(interview["bea_candidate"], 2)

    check_in(client, interview["alex"], 2)  # Bea attends Alex's interview

    shown = view(client, interview["alex"])
    assert shown["state"] == "other_applicant"
    assert "looks like Bea Good, another applicant" in shown["text"]


@pytest.mark.parametrize(
    "shots, message",
    [
        ((1, 0, 1), "No face found"),
        ((1, 9, 1), "More than one face"),
        ((1, 7, 1), "too far from the camera"),
        ((1, 8, 1), "too dark"),
        ((1, 2, 1), "do not look alike"),
    ],
    ids=["no face", "two people", "too far", "too dark", "different people"],
)
def test_unusable_pictures_are_refused_with_what_to_change(
    client, interview, shots, message
):
    give_photo(interview["alex_candidate"], 1)

    answer = check_in(client, interview["alex"], 1, shots=shots)

    assert answer.status_code == 422 and message in answer.json()["detail"]
    assert view(client, interview["alex"])["state"] == "waiting"


def test_after_too_many_tries_the_candidate_continues_without(client, interview):
    give_photo(interview["alex_candidate"], 1)
    for _ in range(checkin.MAX_ATTEMPTS - 1):
        assert (
            check_in(client, interview["alex"], 1, shots=(1, 0, 1)).status_code == 422
        )

    last = check_in(client, interview["alex"], 1, shots=(1, 0, 1))

    assert last.status_code == 422 and "after several tries" in last.json()["detail"]
    candidate = client.get(
        "/api/candidate/interview", headers=as_candidate(interview["alex"])
    )
    assert (
        candidate.json()["identity"]["consent"] == "given"
    )  # goes on to the waiting room
    shown = view(client, interview["alex"])
    assert shown["state"] == "failed" and shown["score"] is None
    assert check_in(client, interview["alex"], 1).status_code == 422  # no more tries


def test_declining_deletes_the_photo_at_once(client, interview):
    give_photo(interview["alex_candidate"], 1)

    answer = client.delete(
        "/api/candidate/identity", headers=as_candidate(interview["alex"])
    )

    assert answer.json()["identity"]["consent"] == "declined"
    assert view(client, interview["alex"])["state"] == "declined"
    with SessionLocal() as db:
        assert (
            references.photo_state(db, db.get(Candidate, interview["alex_candidate"]))
            == "no_consent"
        )
        assert not db.scalar(
            select(ApplicationPhoto.id).where(
                ApplicationPhoto.candidate_id == interview["alex_candidate"]
            )
        )


def test_without_the_key_the_candidate_is_not_asked(client, interview, monkeypatch):
    give_photo(interview["alex_candidate"], 1)
    monkeypatch.setattr(get_settings(), "face_reference_key", None)

    shown = client.get(
        "/api/candidate/interview", headers=as_candidate(interview["alex"])
    )

    assert shown.json()["identity"]["available"] is False
    assert check_in(client, interview["alex"], 1).status_code == 409
    assert view(client, interview["alex"])["state"] == "off"


# ---------- what the interviewer sees ----------


@pytest.mark.parametrize(
    "change, reason",
    [
        ({"photo_file_id": None}, "no photo was sent with the application."),
        (
            {"photo_consent": False},
            "the applicant did not agree to the use of their photo.",
        ),
        ({}, "the application photo has not been processed yet."),
    ],
    ids=["no photo", "no consent", "not processed yet"],
)
def test_the_interviewer_is_told_why_nothing_was_compared(
    client, interview, change, reason
):
    with SessionLocal() as db:
        candidate = db.get(Candidate, interview["alex_candidate"])
        for key, value in change.items():
            setattr(candidate, key, value)
        db.commit()

    shown = view(client, interview["alex"])

    assert shown["state"] == "no_photo" and shown["text"] == f"No comparison: {reason}"
    assert shown["score"] is None


def test_the_photo_is_shown_to_interviewers_only(client, interview):
    url = f"/api/interviews/{interview['alex']}/identity/photo"
    assert client.get(url, headers=as_interviewer()).status_code == 404  # none yet

    give_photo(interview["alex_candidate"], 1)
    shown = client.get(url, headers=as_interviewer())

    assert shown.status_code == 200 and shown.headers["content-type"] == "image/jpeg"
    assert shown.headers["cache-control"] == "no-store"
    assert client.get(url, headers=as_candidate(interview["alex"])).status_code == 403


def test_the_waiting_room_banner_carries_the_check_in_result(client, interview):
    give_photo(interview["alex_candidate"], 1)
    check_in(client, interview["alex"], 5)  # clearly someone else
    client.post("/api/candidate/waiting", headers=as_candidate(interview["alex"]))

    lobby = client.post(
        f"/api/interviews/{interview['alex']}/presence", headers=as_interviewer()
    ).json()

    assert lobby["candidate_waiting"] is True
    assert lobby["identity"]["state"] == "no_match"
    assert lobby["identity"]["score"] < 40


def test_the_interviews_list_shows_the_photo_state(client, interview):
    give_photo(interview["alex_candidate"], 9)

    listed = client.get("/api/interviews", headers=as_interviewer()).json()

    states = {row["id"]: row["photo"] for row in listed}
    assert states[interview["alex"]] == "several_faces"
    assert states[interview["bea"]] == "pending"


def test_candidates_never_see_the_result(client, interview):
    candidate = as_candidate(interview["alex"])
    base = f"/api/interviews/{interview['alex']}/identity"

    assert client.get(base, headers=candidate).status_code == 403
    assert client.get(f"{base}/photo", headers=candidate).status_code == 403


def test_the_report_says_whether_the_photo_matched(client, interview):
    give_photo(interview["alex_candidate"], 1)
    with SessionLocal() as db:
        session = db.get(InterviewSession, interview["alex"])
        assert identity_summary(db, session)["state"] == "not_checked"

    check_in(client, interview["alex"], 1)
    with SessionLocal() as db:
        session = db.get(InterviewSession, interview["alex"])
        assert identity_summary(db, session) == {
            "state": "confirmed",
            "text": "Matched the application photo at check-in (match score 100%).",
        }

    check_in(client, interview["alex"], 5)
    with SessionLocal() as db:
        summary = identity_summary(db, db.get(InterviewSession, interview["alex"]))
        assert (
            summary["state"] == "not_confirmed"
            and "Different person" in summary["text"]
        )


# ---------- deletion ----------


def test_photos_are_deleted_after_the_retention_time(interview):
    give_photo(interview["alex_candidate"], 1)
    give_photo(interview["bea_candidate"], 2)
    with SessionLocal() as db:
        alex = db.get(InterviewSession, interview["alex"])
        alex.status, alex.ended_at = (
            SessionStatus.ENDED,
            clock.now() - timedelta(days=31),
        )
        db.commit()

        assert references.purge_expired(db) == 1  # Bea's interview is still to come
        left = db.scalars(select(ApplicationPhoto.candidate_id)).all()
        assert (
            interview["alex_candidate"] not in left
            and interview["bea_candidate"] in left
        )

        db.get(InterviewSession, interview["bea"]).status = SessionStatus.CANCELLED
        db.commit()
        assert references.purge_expired(db) == 1  # cancelled: deleted


def test_a_recent_interview_keeps_its_photo(interview):
    give_photo(interview["alex_candidate"], 1)
    with SessionLocal() as db:
        alex = db.get(InterviewSession, interview["alex"])
        alex.status, alex.ended_at = (
            SessionStatus.ENDED,
            clock.now() - timedelta(days=2),
        )
        db.commit()
        assert references.purge_expired(db) == 0


# ---------- the real face models ----------


def test_the_real_face_models_load_and_find_no_face_in_a_blank_picture(monkeypatch):
    monkeypatch.undo()  # the real models, not the fakes
    with pytest.raises(FaceError) as error:
        faces.find_face(np.full((240, 320, 3), 200, np.uint8))

    assert error.value.reason == "no_face"
