"""Role guards (N9): candidates can never reach interviewer data.

The last test checks EVERY /api route of the real app: a route must require
the interviewer role unless it is listed below on purpose. A new route that
forgets its guard makes this test fail.
"""

from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.auth.dependencies import require_candidate, require_interviewer
from app.auth.security import Role, create_access_token
from app.main import app

# Routes that do not need the interviewer role, and why.
OPEN_ROUTES = {
    "/api/health",  # used by Docker and the status badge
    "/api/auth/login",  # how an interviewer gets a token
    "/api/auth/candidate",  # how a candidate gets a token from the link
    "/api/auth/me",  # any signed-in user may ask who they are
}
# Routes for the candidate's own interview: must require the candidate role.
CANDIDATE_ROUTES: set[str] = set()


def guarded_test_app() -> TestClient:
    """Build a tiny app with one interviewer-only and one candidate-only route."""
    test_app = FastAPI()

    @test_app.get("/scores", dependencies=[Depends(require_interviewer)])
    def scores():
        """Pretend interviewer-only route that returns a score."""
        return {"score": 82}

    @test_app.get("/my-interview", dependencies=[Depends(require_candidate)])
    def my_interview():
        """Pretend candidate-only route."""
        return {"ok": True}

    return TestClient(test_app)


def auth(role: Role) -> dict:
    """Return an Authorization header with a token for the given role."""
    return {"Authorization": f"Bearer {create_access_token(1, role)}"}


def test_no_token_gets_401():
    response = guarded_test_app().get("/scores")

    assert response.status_code == 401
    assert response.json()["detail"] == "Please sign in to continue."


def test_bad_token_gets_401():
    response = guarded_test_app().get(
        "/scores", headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 401


def test_candidate_cannot_see_scores():
    response = guarded_test_app().get("/scores", headers=auth(Role.CANDIDATE))

    assert response.status_code == 403
    assert "score" not in response.json()


def test_interviewer_can_see_scores():
    response = guarded_test_app().get("/scores", headers=auth(Role.INTERVIEWER))

    assert response.status_code == 200


def test_candidate_route_rejects_interviewer():
    client = guarded_test_app()

    assert client.get("/my-interview", headers=auth(Role.CANDIDATE)).status_code == 200
    assert (
        client.get("/my-interview", headers=auth(Role.INTERVIEWER)).status_code == 403
    )


def dependencies_of(dependant):
    """Every dependency function a route uses, including nested ones."""
    for dependency in dependant.dependencies:
        yield dependency.call
        yield from dependencies_of(dependency)


def test_every_api_route_is_guarded():
    unguarded = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api"):
            continue
        if route.path in OPEN_ROUTES:
            continue
        needed = (
            require_candidate if route.path in CANDIDATE_ROUTES else require_interviewer
        )
        if needed not in set(dependencies_of(route.dependant)):
            unguarded.append(route.path)

    assert unguarded == [], f"add require_interviewer (or list on purpose): {unguarded}"
