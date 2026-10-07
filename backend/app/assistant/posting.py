"""Posting an approved job description to the job board (§4B-2, Figure 3
"post_to_job_board", runs only after approval).

Secure by design:
- every piece of text is HTML-escaped, so the post can never carry code;
- the application form link must be a Google Forms address;
- if posting fails, the approved JD stays saved and the error is recorded.
"""

import html
import logging
import re
from urllib.parse import parse_qsl, urlencode, urlparse

from sqlalchemy import select

from app.assistant.schemas import JobDescriptionContent, JobProfile
from app.collector.collect import job_reference
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import Job, JobDescription
from app.db.models.job import JobBoardStatus, JobDescriptionStatus
from app.integrations.job_board import JobBoardError, publish_job_post

logger = logging.getLogger(__name__)

FORM_HOSTS = {"docs.google.com", "forms.gle"}


def clean_form_url(url: str) -> str:
    """Return the link if it is a Google Forms address; raise ValueError if not."""
    url = url.strip()
    parts = urlparse(url)
    is_form = parts.scheme == "https" and parts.hostname in FORM_HOSTS
    if parts.hostname == "docs.google.com":
        is_form = is_form and parts.path.startswith("/forms/")
    if not is_form or len(url) > 500:
        raise ValueError(
            "The application form link must be a Google Forms link (https://forms.gle/... or https://docs.google.com/forms/...)."
        )
    return url


def _list(title: str, items: list[str]) -> str:
    """An escaped heading with a bullet list (empty when there are no items)."""
    if not items:
        return ""
    rows = "".join(f"<li>{html.escape(item)}</li>" for item in items)
    return f"<h3>{html.escape(title)}</h3><ul>{rows}</ul>"


def _text(title: str, text: str) -> str:
    """An escaped heading with a paragraph (empty when there is no text)."""
    return f"<h3>{html.escape(title)}</h3><p>{html.escape(text)}</p>" if text else ""


def application_link(form_url: str, job_id: int, title: str) -> str:
    """The form link with "Position applied for" already filled in
    ("JOB-12 · title"), so the CV Collector knows which job a CV is for.
    Unchanged if GOOGLE_FORM_POSITION_FIELD is not set."""
    field = get_settings().google_form_position_field or ""
    parts = urlparse(form_url)
    if not re.fullmatch(r"entry\.\d+", field) or parts.hostname != "docs.google.com":
        return form_url  # short forms.gle links cannot be pre-filled
    query = [(k, v) for k, v in parse_qsl(parts.query) if k not in ("usp", field)]
    query += [("usp", "pp_url"), (field, job_reference(job_id, title))]
    return parts._replace(query=urlencode(query)).geturl()


def render_post_html(
    content: JobDescriptionContent, profile: JobProfile, form_url: str
) -> str:
    """Build the job post body: the JD sections, requirements from the profile
    and the application form link. All text is escaped."""
    by_level = {
        level: [r.text for r in profile.requirements if r.level == level]
        for level in ("mandatory", "required", "preferred")
    }
    requirements = by_level["mandatory"] + by_level["required"]
    if profile.min_years_experience is not None and not any(
        r.category == "experience" for r in profile.requirements
    ):
        requirements.insert(
            0, f"{profile.min_years_experience}+ years of relevant experience"
        )

    return "".join(
        [
            _text("About the role", content.about),
            _list("Key responsibilities", content.responsibilities),
            _list("Requirements", requirements),
            _list("Nice to have", by_level["preferred"]),
            _text("Work arrangement", content.work_arrangement),
            _list("What we offer", content.what_we_offer),
            _text("Equal opportunity", content.equal_opportunity),
            "<h3>How to apply</h3>",
            (
                f'<p><a href="{html.escape(form_url, quote=True)}">'
                "Apply through our application form</a> and upload your CV "
                "(PDF or Word).</p>"
            ),
        ]
    )


def post_job(job_id: int) -> dict:
    """Post the job's approved JD and record the outcome on the job.

    Returns {"status": "posted" | "failed" | "needs_form", "message", "url",
    "form_url"}; never raises for a job board failure.
    """
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        jd = db.scalar(
            select(JobDescription)
            .where(
                JobDescription.job_id == job_id,
                JobDescription.status == JobDescriptionStatus.APPROVED,
            )
            .order_by(JobDescription.version.desc())
            .limit(1)
        )
        if jd is None:
            return {
                "status": "failed",
                "message": "There is no approved job description to post.",
                "url": None,
                "form_url": None,
            }
        if not job.google_form_url:
            return {
                "status": "needs_form",
                "message": "Not posted yet: the application form link is missing.",
                "url": None,
                "form_url": None,
            }
        content = JobDescriptionContent.model_validate_json(jd.content)
        # The link pre-fills the job, so collected CVs find the right job.
        form_url = application_link(job.google_form_url, job.id, job.title)
        body = render_post_html(
            content, JobProfile.model_validate(job.profile), form_url
        )
        try:
            post = publish_job_post(content.title, body, ["Jobs"])
        except JobBoardError as exc:
            job.job_board_status = JobBoardStatus.FAILED
            db.commit()
            logger.warning("Job post failed: job %d", job_id)
            return {
                "status": "failed",
                "message": str(exc),
                "url": None,
                "form_url": form_url,
            }
        job.job_board_status = JobBoardStatus.POSTED
        job.job_board_post_url = post["url"]
        db.commit()
        logger.info("Job posted: job %d", job_id)
        return {
            "status": "posted",
            "message": "Posted to the job board.",
            "url": post["url"],
            "form_url": form_url,
        }
