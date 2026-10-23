"""Which model answers CV screening's AI checks (app/screening/ai_checks.py):
Gemini first, the local model as fallback, and what is sent. Fake models
only: no AI provider, no Ollama, no database."""

import pytest
from pydantic import SecretStr

from app.ai.errors import AIServiceError
from app.core.config import get_settings
from app.screening import ai_checks
from app.screening.ai_checks import YearsAnswer

CLOUD = "gemini-test-lite"
LOCAL = "local-test"
ANSWER = YearsAnswer(years=None, evidence=[])


@pytest.fixture
def models(monkeypatch):
    """Fake cloud and local models that record each question; a key is set,
    the cloud model is not blocked and no pause is running."""
    settings = get_settings()
    monkeypatch.setattr(settings, "screening_ai_model", CLOUD)
    monkeypatch.setattr(settings, "screening_model", LOCAL)
    monkeypatch.setattr(settings, "llm_api_key", SecretStr("test-key"))
    monkeypatch.setattr(ai_checks, "_cloud_paused_until", 0.0)
    monkeypatch.setattr(ai_checks.usage, "is_blocked", lambda name: False)
    asked = {"cloud": [], "local": [], "cloud_fails": False, "cloud_answer": ANSWER}

    def cloud(prompt, schema, name):
        """The cloud model: fails or answers, as the test says."""
        asked["cloud"].append(prompt)
        if asked["cloud_fails"]:
            raise AIServiceError("down")
        return asked["cloud_answer"]

    def local(prompt, schema):
        """The local model: always answers."""
        asked["local"].append(prompt)
        return ANSWER

    monkeypatch.setattr(ai_checks, "_ask_cloud", cloud)
    monkeypatch.setattr(ai_checks, "_ask_local", local)
    return asked


def test_gemini_answers_first_and_the_local_model_is_not_asked(models):
    assert ai_checks._ask("q", YearsAnswer) == (ANSWER, CLOUD)
    assert len(models["cloud"]) == 1 and models["local"] == []


def test_no_key_or_no_cloud_model_uses_the_local_model(models, monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_api_key", None)
    assert ai_checks._ask("q", YearsAnswer) == (ANSWER, LOCAL)

    monkeypatch.setattr(get_settings(), "llm_api_key", SecretStr("test-key"))
    monkeypatch.setattr(get_settings(), "screening_ai_model", "")  # local only
    assert ai_checks._ask("q", YearsAnswer) == (ANSWER, LOCAL)
    assert models["cloud"] == []


def test_a_used_up_quota_goes_straight_to_the_local_model(models, monkeypatch):
    monkeypatch.setattr(ai_checks.usage, "is_blocked", lambda name: name == CLOUD)

    assert ai_checks._ask("q", YearsAnswer) == (ANSWER, LOCAL)
    assert models["cloud"] == []  # no request that would only fail


def test_a_cloud_failure_falls_back_and_pauses_the_cloud(models):
    models["cloud_fails"] = True

    assert ai_checks._ask("q", YearsAnswer) == (ANSWER, LOCAL)
    assert ai_checks._ask("q2", YearsAnswer) == (ANSWER, LOCAL)
    assert len(models["cloud"]) == 1  # the next CV does not wait for it again
    assert len(models["local"]) == 2


def test_a_badly_formed_cloud_answer_is_ignored_not_asked_again(models):
    models["cloud_answer"] = None  # did not fit the schema

    assert ai_checks._ask("q", YearsAnswer) == (None, CLOUD)
    assert models["local"] == []  # no second request for it


def test_when_both_models_fail_the_run_stops_clearly(models, monkeypatch):
    models["cloud_fails"] = True

    def local_down(prompt, schema):
        """The local model cannot be reached either."""
        raise AIServiceError("The AI for CV screening is unavailable.")

    monkeypatch.setattr(ai_checks, "_ask_local", local_down)
    with pytest.raises(AIServiceError):
        ai_checks._ask("q", YearsAnswer)


def test_the_cv_is_sent_without_contact_details_or_the_name(models):
    cv = (
        "Rina Rahman\n"
        "rina.rahman@example.com | +880 1700 000 099 | https://example.com/rina\n"
        "Senior PHP Developer, 2014 - 2018\n"
    )

    ai_checks.read_years(cv, ai_checks.date(2026, 10, 23), ["Rina", "Rahman"])

    sent = models["cloud"][0]
    for private in ("Rina", "Rahman", "example.com", "1700"):
        assert private not in sent
    assert "Senior PHP Developer, 2014 - 2018" in sent  # dates stay (not a phone)
