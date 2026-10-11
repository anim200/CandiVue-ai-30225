"""Scoring weights per dimension (F2): who sets them and which ones apply.

Order of priority (human control first):
1. the interviewer's weights (job page, "Scoring weights"),
2. else the Hiring Assistant's suggestion, made from the interviewer's
   description of the job ("AI determines the weights from the prompt"),
3. else fixed defaults.
Weights are whole percentages that add up to 100.
"""

from pydantic import BaseModel, Field, model_validator

from app.db.models import Job

DIMENSIONS = ("skills", "experience", "qualifications", "ats")
DIMENSION_LABELS = {
    "skills": "Technical skills",
    "experience": "Relevant experience",
    "qualifications": "Qualifications",
    "ats": "ATS CV–JD match",
}
DEFAULT_WEIGHTS = {"skills": 35, "experience": 30, "qualifications": 15, "ats": 20}


class ScoringWeights(BaseModel):
    """Four whole-number percentages that add up to 100."""

    skills: int = Field(ge=0, le=100, description="Technical skills, %")
    experience: int = Field(ge=0, le=100, description="Relevant experience, %")
    qualifications: int = Field(ge=0, le=100, description="Qualifications, %")
    ats: int = Field(ge=0, le=100, description="ATS-style CV to JD match, %")

    @model_validator(mode="after")
    def adds_up_to_100(self):
        """The four weights must add up to exactly 100."""
        if self.skills + self.experience + self.qualifications + self.ats != 100:
            raise ValueError("The four weights must add up to 100.")
        return self


class SuggestedWeights(ScoringWeights):
    """The Hiring Assistant's suggestion, with a one-line reason."""

    reason: str = Field(
        min_length=5, max_length=300, description="One sentence: why these weights"
    )


def effective_weights(job: Job) -> dict:
    """The weights screening uses for this job, with their source:
    {"skills": .., "experience": .., "qualifications": .., "ats": ..,
     "source": "interviewer" | "ai" | "default", "reason": str | None}."""
    if job.weights:
        return {**_only_weights(job.weights), "source": "interviewer", "reason": None}
    if job.ai_weights:
        return {
            **_only_weights(job.ai_weights),
            "source": "ai",
            "reason": job.ai_weights.get("reason"),
        }
    return {**DEFAULT_WEIGHTS, "source": "default", "reason": None}


def _only_weights(saved: dict) -> dict:
    """The four dimension values from a saved weights dict."""
    return {dimension: int(saved[dimension]) for dimension in DIMENSIONS}
