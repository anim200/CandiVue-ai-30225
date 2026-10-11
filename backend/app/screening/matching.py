"""Match job requirements to a CV by meaning (F1 semantic matching).

Each CV line (passage) gets an embedding from the local model. For each job
requirement, in this order:
1. named in the CV (e.g. "Docker"), or one of its "also counts" names that
   the Hiring Assistant listed in the job profile (e.g. "Laravel Sail" runs
   on Docker) → met;
2. one of its "related" names (e.g. "Podman") → partly met;
3. otherwise the line closest in meaning decides (cosine similarity):
   met / partly met / not met. This lets "built REST services in Django"
   count for "Python web development" (F1).
A line that says the opposite ("has not used Laravel") or only a wish
("interested in learning Docker") never counts. A version number does not
hide a name ("PHP8" counts for PHP).
Evidence is always a real line of the CV, so every result can be checked.
No LLM is called here: the AI knowledge comes from the job profile, made
once per job. (A mandatory requirement still not found is checked once more
by the local model before anyone is excluded: see local_model.py.)
"""

import math
import re

from app.ai.embeddings import embed_documents, embed_query

# Similarity thresholds, calibrated on the synthetic test CVs
# (test-data/synthetic-cvs/check_matching.py).
MET_AT = 0.62
PARTLY_AT = 0.58
MAX_PASSAGE_CHARS = 400
MAX_NAME_WORDS = 4  # longer requirements are matched by meaning only
SKIP_SECTIONS = {"other"}  # contact, spoken languages, interests
# The embedding model works best when the question says what it is for.
INSTRUCTION = (
    "Instruct: Given a job requirement, find the CV line that shows the "
    "candidate has it\nQuery: "
)
YEARS_IN_TEXT = re.compile(r"(\d+)\s*\+?\s*years?", re.IGNORECASE)
EMAIL_OR_PHONE = re.compile(r"@|\+?\d[\d\s()-]{7,}\d")
# "Has not used Laravel", "No PHP experience": a mention that says the opposite.
# "not only" / "not just" are not a denial ("not only PHP but also Laravel").
NEGATION = (
    r"\b(?:no|not(?!\s+(?:only|just)\b)|never|without|lacks?|lacking|"
    r"hasn't|haven't|don't|doesn't)\b"
)
# Words that may stand between the denial and the name ("has not USED
# Laravel", "no EXPERIENCE WITH Docker"). Any other word ends the denial, so
# "no manual steps using Docker" still counts for Docker.
DENIAL_FILLER = (
    r"(?:used|use|using|worked|work|with|in|on|any|much|prior|real|"
    r"professional|professionally|commercial|hands-on|experience|knowledge|"
    r"of|familiar|exposure|to|the|a|an|yet)"
)
# "Interested in learning Docker": a wish, not experience.
WISH = (
    r"\b(?:interested in|keen to|eager to|wants? to|would like to|plans? to|"
    r"planning to|hopes? to|aspires? to|looking to|currently learning|"
    r"am learning|to learn)\b"
)

Passage = tuple[str, str, list[float]]  # (section, line, embedding)


def cv_passages(parsed: dict) -> list[tuple[str, str]]:
    """The CV as (section, line) pairs worth comparing; contact lines and
    very short lines are left out."""
    passages = []
    for section, body in parsed["sections"].items():
        if section in SKIP_SECTIONS:
            continue
        for line in body.splitlines():
            line = line.strip(" •·-*")
            if len(line) < 3 or EMAIL_OR_PHONE.search(line):
                continue
            passages.append((section, line[:MAX_PASSAGE_CHARS]))
    return passages


def embed_passages(passages: list[tuple[str, str]]) -> list[list[float]]:
    """Embeddings for the CV lines (stored, so this runs once per CV)."""
    return embed_documents([text for _section, text in passages]) if passages else []


def requirement_vectors(requirements: list[dict]) -> dict[str, list[float]]:
    """Embeddings of the requirement questions, made once per screening run
    and reused for every CV."""
    return {r["text"]: embed_query(INSTRUCTION + r["text"]) for r in requirements}


def match_requirements(
    requirements: list[dict],
    passages: list[Passage],
    years_experience: float | None,
    vectors: dict[str, list[float]] | None = None,
) -> list[dict]:
    """met / partly / unmet for each requirement, with the evidence line.
    `years_experience`: None when the CV's years could not be read.
    `vectors`: requirement embeddings from requirement_vectors() (optional)."""
    return [
        match_requirement(
            requirement,
            passages,
            years_experience,
            (vectors or {}).get(requirement["text"]),
        )
        for requirement in requirements
    ]


def match_requirement(
    requirement: dict,
    passages: list[Passage],
    years_experience: float | None,
    vector: list[float] | None = None,
) -> dict:
    """Decide one requirement (see the module docstring for the order).
    "decided_by" says how: mention, also_counts, related or meaning."""
    text = requirement["text"]
    names = [text, *requirement.get("also_counts", [])]
    status, decided_by, similarity, found = "unmet", "meaning", 0.0, None
    mention = _mention(names, passages)
    if mention:
        status, similarity, found = "met", 1.0, mention
        decided_by = "mention" if mention[2] == text else "also_counts"
    elif related := _mention(requirement.get("related", []), passages):
        status, decided_by, similarity, found = "partial", "related", 1.0, related
    else:
        status, similarity, found = _closest(text, passages, vector)
    if too_few_years(text, years_experience):
        status = "unmet" if status != "met" else "partial"
    show = status != "unmet" and found is not None
    return {
        "requirement": text,
        "level": requirement["level"],
        "category": requirement["category"],
        "status": status,
        "decided_by": decided_by,
        "matched_name": found[2] if show and decided_by != "meaning" else None,
        "similarity": round(similarity, 3),
        "evidence": found[1] if show else None,
        "section": found[0] if show else None,
    }


def too_few_years(requirement_text: str, years_experience: float | None) -> bool:
    """ "5 years of PHP": True when the CV has fewer years (whole career, see
    README). Unknown years (None) never count against the candidate."""
    needed = YEARS_IN_TEXT.search(requirement_text)
    return bool(
        needed
        and years_experience is not None
        and years_experience < int(needed.group(1))
    )


def _name_pattern(name: str) -> str:
    """Regex for a name as a whole word (so "Java" does not match
    "JavaScript"); a version number may follow ("PHP8", "Laravel10")."""
    return rf"(?<![\w-]){re.escape(name)}(?![A-Za-z_-])"


def negated(line: str, name: str) -> bool:
    """True when the line does not claim it: it denies it ("has not used
    Laravel") or only wishes for it ("interested in learning Docker")."""
    name_re = _name_pattern(name)
    denied = re.search(
        rf"{NEGATION}(?:\s+{DENIAL_FILLER}){{0,3}}\s+{name_re}", line, re.IGNORECASE
    )
    wished = re.search(rf"{WISH}[^.;]{{0,40}}{name_re}", line, re.IGNORECASE)
    return bool(denied or wished)


def _mention(names: list[str], passages: list[Passage]) -> tuple[str, str, str] | None:
    """(section, line, name) of the first line naming one of the short names,
    preferring work experience; None when none is named."""
    hits = []
    for name in names:
        if not name or len(name.split()) > MAX_NAME_WORDS:
            continue
        pattern = re.compile(_name_pattern(name), re.IGNORECASE)
        for section, line, _vector in passages:
            if pattern.search(line) and not negated(line, name):
                hits.append((section, line, name))
    hits.sort(key=lambda hit: hit[0] != "experience")  # work history first
    return hits[0] if hits else None


def _closest(
    text: str, passages: list[Passage], vector: list[float] | None = None
) -> tuple[str, float, tuple[str, str, str] | None]:
    """The line closest in meaning (skipping lines that deny it) and the
    status it gives. `vector`: the requirement's embedding if already made."""
    usable = [p for p in passages if not negated(p[1], text)]
    if not usable:
        return "unmet", 0.0, None
    query = vector or embed_query(INSTRUCTION + text)
    best = max(usable, key=lambda passage: _cosine(query, passage[2]))
    similarity = _cosine(query, best[2])
    if similarity >= MET_AT:
        status = "met"
    elif similarity >= PARTLY_AT:
        status = "partial"
    else:
        status = "unmet"
    return status, similarity, (best[0], best[1], text)


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors (1 = same meaning)."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0
