"""Show how each requirement of the test job matches each synthetic CV.

Used to calibrate app/screening/matching.py. Prints status, how it was
decided (mention / also_counts / related / meaning), the
similarity and the evidence line, plus the time taken.
Run inside the backend image, with this folder mounted at /cvs and the
Ollama service running:
    docker compose run --rm -e PYTHONPATH=/app -v <this folder>:/cvs:ro tests \
        python /cvs/check_matching.py
"""

import time
from datetime import date
from pathlib import Path

from app.screening.matching import cv_passages, embed_passages, match_requirements
from app.screening.parsing import parse_cv
from app.screening.text import read_cv_text

# The "PHP Laravel Developer" test job (EXPECTED.md), with the kind of
# also_counts / related lists the Hiring Assistant adds to a profile.
REQUIREMENTS = [
    {"text": "PHP", "level": "mandatory", "category": "skill"},
    {
        "text": "Laravel",
        "level": "mandatory",
        "category": "skill",
        "also_counts": ["Lumen", "Livewire"],
        "related": [],  # CodeIgniter or Yii2 are other frameworks, not Laravel
    },
    {
        "text": "Docker",
        "level": "mandatory",
        "category": "skill",
        "also_counts": ["Docker Compose", "Dockerfile", "Dockerised", "Laravel Sail"],
        "related": ["Podman", "OCI containers"],
    },
    {
        "text": "AWS certification",
        "level": "preferred",
        "category": "qualification",
        "also_counts": ["AWS Certified"],
        "related": ["Google Cloud Associate", "Azure certification"],
    },
]


def main() -> None:
    """Print one block per CV and the total time."""
    started = time.perf_counter()
    for path in sorted(Path(__file__).parent.glob("[0-9][0-9]-*.*")):
        text = read_cv_text(path).text
        parsed = parse_cv(text, date(2026, 10, 8))
        lines = cv_passages(parsed)
        passages = [
            (section, line, vector)
            for (section, line), vector in zip(lines, embed_passages(lines), strict=True)
        ]
        results = match_requirements(REQUIREMENTS, passages, parsed["years_experience"])
        print(f"{path.name}  years={parsed['years_experience']}")
        for r in results:
            print(
                f"   {r['requirement']:18} {r['status']:8} {r['decided_by']:11} "
                f"{r['matched_name'] or '':14} {r['similarity']:.3f}  {r['evidence']}"
            )
    print(f"total time: {time.perf_counter() - started:.1f} s")


if __name__ == "__main__":
    main()
