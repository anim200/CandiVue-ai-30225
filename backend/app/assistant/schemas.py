"""Shapes of what the Hiring Assistant saves: the job profile and the JD.

Everything the LLM produces is checked against these Pydantic models before
it is saved (secure by design: no unchecked AI output in the database).
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class RequirementLevel(StrEnum):
    """How strict a requirement is (design: Mandatory / Required / Preferred)."""

    MANDATORY = "mandatory"  # hard requirement: not met = excluded (F1)
    REQUIRED = "required"  # expected, scored
    PREFERRED = "preferred"  # nice to have


class RequirementCategory(StrEnum):
    """What a requirement is about, so screening can score each dimension (F2)."""

    SKILL = "skill"
    EXPERIENCE = "experience"
    QUALIFICATION = "qualification"
    OTHER = "other"


class Requirement(BaseModel):
    """One job requirement, e.g. "PostgreSQL" (required skill)."""

    text: str = Field(min_length=2, max_length=200)
    level: RequirementLevel
    category: RequirementCategory


class JobProfile(BaseModel):
    """The job requirement profile used for screening (F1)."""

    title: str = Field(min_length=2, max_length=120, description="Job title")
    min_years_experience: int | None = Field(
        default=None, ge=0, le=40, description="Minimum years of relevant experience"
    )
    requirements: list[Requirement] = Field(min_length=1, max_length=30)


class JobDescriptionContent(BaseModel):
    """The written job description. Its requirements are not stored here:
    they always come from the job profile, so screening stays consistent.
    Sections added later have defaults, so older drafts still load."""

    title: str = Field(min_length=2, max_length=120)
    about: str = Field(
        min_length=20, max_length=3000, description="About the role, 4-6 sentences"
    )
    responsibilities: list[str] = Field(min_length=1, max_length=12)
    work_arrangement: str = Field(
        default="", max_length=800, description="Where and how the team works"
    )
    what_we_offer: list[str] = Field(default_factory=list, max_length=8)
    equal_opportunity: str = Field(
        default="", max_length=800, description="Inclusive hiring statement"
    )
