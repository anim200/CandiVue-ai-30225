"""Checks on the table definitions. No database needed."""

import app.db.models  # noqa: F401  (registers every table)
from app.db.base import Base

EXPECTED_TABLES = {
    "users",
    "jobs",
    "job_descriptions",
    "candidates",
    "screening_runs",
    "candidate_scores",
    "interview_messages",
    "interview_sessions",
    "transcript_turns",
    "qa_analyses",
    "assessment_reports",
    "knowledge_documents",
    "knowledge_chunks",
    "llm_models",
    "cv_passages",
    "rediscovery_runs",
    "rediscovery_matches",
}

# N20: these must never be stored as candidate data.
PROTECTED_ATTRIBUTES = {
    "age",
    "date_of_birth",
    "gender",
    "ethnicity",
    "nationality",
    "religion",
    "marital_status",
}


def test_all_tables_are_defined():
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_no_protected_attribute_columns():
    for table in Base.metadata.tables.values():
        assert not PROTECTED_ATTRIBUTES & set(table.columns.keys()), table.name


def test_candidate_data_is_deleted_with_the_candidate():
    """Every link to candidates (directly) uses ON DELETE CASCADE (N19).
    One exception: an application added from the talent pool only forgets
    where it came from, since it is the person's own application now."""
    for table in Base.metadata.tables.values():
        for key in table.foreign_keys:
            if key.column.table.name == "candidates":
                name = f"{table.name}.{key.parent.name}"
                expected = (
                    "SET NULL"
                    if name == "candidates.rediscovered_from_id"
                    else "CASCADE"
                )
                assert key.ondelete == expected, name
