"""Turn CV text into structured data with simple, explainable rules (F1).

Extracts: contact details, sections (summary, experience, education,
certifications, skills, projects), jobs with their dates, total years of
experience (overlapping jobs counted once), the highest degree and the
certifications. No AI and no network: the same text always gives the same
result. Semantic matching happens later (matching.py).

When no job dates can be read, "years_source" is "unknown": the screening
workflow then asks the local model (local_model.py), and if that finds
nothing either, the years are not used to exclude anyone.
"""

import re
from datetime import UTC, date, datetime

# Bump when the rules change, so CVs parsed by older rules are parsed again.
PARSER_VERSION = 2

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"\+?\d[\d\s()-]{7,}\d")

# Section headings (a short line that is exactly one of these words).
SECTION_WORDS = {
    "summary": ("professional summary", "summary", "profile", "about me", "objective"),
    "experience": (
        "work experience",
        "experience",
        "professional experience",
        "employment",
        "employment history",
        "work history",
        "where i've worked",
        "career",
    ),
    "education": ("education", "learning", "academic background"),
    "certifications": (
        "certifications",
        "certificates",
        "badges",
        "licenses",
        "training",
    ),
    "skills": ("skills", "technical skills", "toolbox", "tech stack", "stack"),
    "projects": ("projects", "things i built", "selected projects"),
    "other": ("contact", "languages", "interests", "references"),
}
HEADING_TO_SECTION = {
    word: section for section, words in SECTION_WORDS.items() for word in words
}

MONTHS = {
    name: number
    for number, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for name in names
}
MONTH_NAMES = "|".join(sorted(MONTHS, key=len, reverse=True))
# "Jan 2020", "Jan. 2020", "Jan, 2020", "03/2020", "03.2020" or "2020".
POINT = rf"(?:(?:{MONTH_NAMES})\.?,?\s+\d{{4}}|\d{{1,2}}[/.]\d{{4}}|\d{{4}})"
NOW_WORDS = r"till date|till now|to date|present|current|today|ongoing|now|date"
DATE_RANGE = re.compile(
    rf"(?P<start>{POINT})\s*(?:–|—|-|to|until|till|through)\s*"
    rf"(?P<end>{POINT}|{NOW_WORDS})",
    re.IGNORECASE,
)
SINCE = re.compile(rf"\bsince\s+(?P<start>{POINT})", re.IGNORECASE)  # "Since 2019"

DEGREES = [  # (level name, score order, pattern) - highest first
    ("doctorate", 4, re.compile(r"\b(ph\.?\s?d|doctor(ate)? of)\b", re.IGNORECASE)),
    (
        "master",
        3,
        re.compile(
            # "Master" only as a degree ("Master of", "Master's in"), so
            # "Scrum Master" is not read as a master's degree.
            r"\b(m\.?\s?sc|mba|m\.?\s?eng|m\.?\s?tech|"
            r"masters?['’]?s?(?=\s+(?:of|in|degree)\b))",
            re.IGNORECASE,
        ),
    ),
    (
        "bachelor",
        2,
        re.compile(
            r"\b(b\.?\s?sc|bachelor'?s?|b\.?\s?eng|b\.?\s?tech|b\.?\s?a)\b",
            re.IGNORECASE,
        ),
    ),
    ("diploma", 1, re.compile(r"\b(diploma|associate degree)\b", re.IGNORECASE)),
]
CERTIFICATE = re.compile(r"\b(certified|certification|certificate)\b", re.IGNORECASE)
# Issuers that often name a certificate without the word "certified".
ISSUER = re.compile(
    r"\b(aws|amazon|google|microsoft|azure|oracle|cisco|kubernetes|zend|"
    r"scrum|pmp|comptia|red hat|linux foundation)\b",
    re.IGNORECASE,
)
YEAR = re.compile(r"\b(19|20)\d{2}\b")


def parse_cv(text: str, today: date | None = None) -> dict:
    """Structured data from CV text (all values are plain JSON types)."""
    today = today or datetime.now(UTC).date()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    sections = split_sections(lines)
    experience_lines = sections.get("experience") or [
        line for line in lines if line not in sections.get("education", [])
    ]
    jobs = find_jobs(experience_lines, today)
    email = (EMAIL.search(text) or [None])[0]
    return {
        "name": find_name(lines, email),
        "email": email,
        "phone": _clean_phone(PHONE.search(text)),
        "sections": {name: "\n".join(body) for name, body in sections.items()},
        "jobs": jobs,
        "years_experience": total_years(jobs),
        # "dates": from the job dates; "unknown": no job dates could be read
        # (the screening workflow may then fill it in, see local_model.py).
        "years_source": "dates" if jobs else "unknown",
        "years_evidence": [],
        "parser_version": PARSER_VERSION,
        "degree": highest_degree("\n".join(sections.get("education") or lines)),
        "certifications": find_certifications(lines, sections),
    }


def split_sections(lines: list[str]) -> dict[str, list[str]]:
    """Group the lines under the heading they follow ("intro" before any)."""
    sections: dict[str, list[str]] = {"intro": []}
    current = "intro"
    for line in lines:
        heading = re.sub(r"[^a-z' ]", "", line.lower()).strip()
        if len(heading.split()) <= 4 and heading in HEADING_TO_SECTION:
            current = HEADING_TO_SECTION[heading]
            sections.setdefault(current, [])
            continue
        sections[current].append(line)
    return {name: body for name, body in sections.items() if body}


def find_name(lines: list[str], email: str | None) -> str | None:
    """The person's name: a line of 2-4 capitalised words (letters only, not
    a heading or a certificate). The one whose words are in the email address
    wins (two-column CVs can put other lines first); else the first one."""
    candidates = []
    for line in lines[:40]:
        words = line.split()
        if not 2 <= len(words) <= 4 or line.lower() in HEADING_TO_SECTION:
            continue
        if CERTIFICATE.search(line) or ISSUER.search(line):
            continue  # e.g. "Certified Kubernetes" is not a name
        if all(re.fullmatch(r"[A-Z][a-z]+(?:-[A-Z][a-z]+)?", word) for word in words):
            candidates.append(line)
    local_part = email.split("@")[0].lower() if email else ""
    for line in candidates:
        if local_part and all(word.lower() in local_part for word in line.split()):
            return line
    return candidates[0] if candidates else None


def find_jobs(lines: list[str], today: date) -> list[dict]:
    """Each line with a date range ("Jan 2020 – Till Date") or "Since 2019"
    is a job: its title and its months."""
    jobs = []
    for line in lines:
        match = DATE_RANGE.search(line) or SINCE.search(line)
        if not match:
            continue
        start = _point(match["start"], is_end=False)
        ends_now = "end" not in match.groupdict() or re.fullmatch(
            NOW_WORDS, match["end"], re.IGNORECASE
        )
        end = today_point(today) if ends_now else _point(match["end"], is_end=True)
        if not start or not end or end < start:
            continue
        title = re.sub(r"[\s·|,–—-]+$", "", line[: match.start()]).strip()
        jobs.append(
            {
                "title": title or None,
                "start": f"{start[0]}-{start[1]:02d}",
                "end": f"{end[0]}-{end[1]:02d}",
                "months": _months(start, end),
            }
        )
    return jobs


def total_years(jobs: list[dict]) -> float:
    """Years of experience with overlapping jobs counted once (one decimal)."""
    spans = sorted((_index(job["start"]), _index(job["end"])) for job in jobs)
    months, current_start, current_end = 0, None, None
    for start, end in spans:
        if current_end is None or start > current_end + 1:
            if current_end is not None:
                months += current_end - current_start + 1
            current_start, current_end = start, end
        else:
            current_end = max(current_end, end)
    if current_end is not None:
        months += current_end - current_start + 1
    return round(months / 12, 1)


def highest_degree(text: str) -> str | None:
    """The highest degree mentioned: doctorate, master, bachelor or diploma."""
    for name, _order, pattern in DEGREES:
        if pattern.search(text):
            return name
    return None


def find_certifications(lines: list[str], sections: dict[str, list[str]]) -> list[str]:
    """Certificate lines: any line saying "certified/certificate", and lines of
    the certifications section that name an issuer or a year (in two-column
    CVs that section can run into other text, which this leaves out)."""
    found = []
    for entry in _join_wrapped(sections.get("certifications", [])):
        short = len(entry.split()) <= 14
        if short and (CERTIFICATE.search(entry) or ISSUER.search(entry)):
            found.append(entry)
    for line in lines:
        is_cert_line = CERTIFICATE.search(line) and len(line.split()) <= 14
        already = any(line in entry for entry in found)  # a piece of a joined entry
        if is_cert_line and not already and "certifications" not in line.lower():
            found.append(line)
    return [line[:200] for line in found[:15]]


def _join_wrapped(lines: list[str]) -> list[str]:
    """Join lines that a narrow column wrapped: an entry ends at a line with a
    year (e.g. "... Associate (2024)"); lines after the last one stay alone."""
    entries, current = [], []
    for line in lines:
        current.append(line)
        if YEAR.search(line):
            entries.append(" ".join(current))
            current = []
    return entries + current


def today_point(today: date) -> tuple[int, int]:
    """(year, month) for "present"."""
    return today.year, today.month


def _point(text: str, is_end: bool) -> tuple[int, int] | None:
    """(year, month) from "Jan 2020", "Jan, 2020", "03/2020", "03.2020" or
    "2020" (a bare year means January for a start and December for an end)."""
    text = text.strip().lower().rstrip(".").replace(",", " ")
    if re.fullmatch(r"\d{1,2}[/.]\d{4}", text):
        month, year = re.split(r"[/.]", text)
        return int(year), int(month) if 1 <= int(month) <= 12 else 1
    parts = text.replace(".", " ").split()
    if len(parts) == 2:
        return int(parts[1]), MONTHS.get(parts[0], 1)
    return int(parts[0]), 12 if is_end else 1


def _months(start: tuple[int, int], end: tuple[int, int]) -> int:
    """Months from start to end, both included."""
    return (end[0] - start[0]) * 12 + end[1] - start[1] + 1


def _index(point: str) -> int:
    """A "YYYY-MM" string as a month number, for comparing and merging."""
    year, month = point.split("-")
    return int(year) * 12 + int(month) - 1


def _clean_phone(match) -> str | None:
    """The phone number found, without extra spaces."""
    return re.sub(r"\s+", " ", match.group(0)).strip() if match else None
