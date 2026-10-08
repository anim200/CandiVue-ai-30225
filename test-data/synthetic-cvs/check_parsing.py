"""Print what the CV parser finds in each synthetic CV (a quick check).

Run inside the backend image, with this folder mounted at /cvs:
    docker compose run --rm --no-deps -v <this folder>:/cvs:ro tests \
        python /cvs/check_parsing.py
"""

import sys
from datetime import date
from pathlib import Path

from app.screening.parsing import parse_cv
from app.screening.text import UnreadableCv, read_cv_text

TODAY = date(2026, 10, 8)  # fixed, so the years match EXPECTED.md


def main() -> None:
    """Parse every CV in this folder and print one line per CV."""
    for path in sorted(Path(__file__).parent.glob("[0-9][0-9]-*.*")):
        try:
            cv = read_cv_text(path)
        except UnreadableCv as exc:
            print(f"{path.name:28} UNREADABLE: {exc}")
            continue
        data = parse_cv(cv.text, TODAY)
        print(
            f"{path.name:28} ocr={'yes' if cv.used_ocr else 'no ':3} "
            f"name={data['name']!s:16} email={'yes' if data['email'] else 'no ':3} "
            f"years={data['years_experience']:4} jobs={len(data['jobs'])} "
            f"degree={data['degree']!s:8} certs={len(data['certifications'])} "
            f"sections={','.join(s for s in data['sections'] if s != 'intro')}"
        )
        if "--details" in sys.argv:  # also list the certifications found
            for certificate in data["certifications"]:
                print(f"{'':28}   cert: {certificate}")


if __name__ == "__main__":
    main()
