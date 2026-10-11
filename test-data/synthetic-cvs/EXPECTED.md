# Synthetic test CVs: answer key

28 **made-up** CVs (example.com emails, fake phone numbers, "SYNTHETIC TEST CV"
on each). They are for development and testing only; the final demo uses the
trainer's sample CVs (requirement.md N13, CN5). Re-create them with
`python test-data/synthetic-cvs/make_cvs.py` (needs Microsoft Edge and
python-docx).

**Test job: PHP Laravel Developer.** Minimum 5 years. Mandatory: PHP, Laravel,
Docker. Preferred: AWS certification. Years are counted up to October 2026.

## Expected screening result

| # | File | Years | Expected | Why / what it tests |
|---|---|---|---|---|
| 1 | 01-jordan-sample.pdf | ~7.7 | **Top group** | All mandatory + AWS Developer cert, BSc CSE |
| 2 | 02-alex-rowan.pdf | ~6.8 | **Top group** | Docker + Kubernetes, two AWS certs, MSc |
| 3 | 03-sam-kader.pdf | ~8.7 | **Top group** | Strong, but Google Cloud cert, not AWS |
| 4 | 04-priya-example.pdf | ~5.5 | **Top group** | Two-column layout; AWS Solutions Architect cert |
| 5 | 05-noor-testwell.pdf | ~9.3 | **Top group** | Most senior; AWS Professional cert |
| 6 | 06-chris-mock.pdf | 5.0 | Middle | Exactly the minimum; "Docker (basic)"; diploma |
| 7 | 07-taylor-draft.pdf | ~6.0 | Middle | Docker only in CI pipelines; 3 years Laravel |
| 8 | 08-morgan-pilot.pdf | ~5.1 | Middle | **Semantic:** Docker only as "Laravel Sail" (runs on Docker) |
| 9 | 09-jamie-fixture.pdf | ~7.0 | Middle–low | Mostly WordPress; only ~2.8 years Laravel |
| 10 | 10-robin-stub.pdf | ~5.0 | Middle–low | **Semantic:** "OCI containers with Podman", not Docker: partly met at best |
| 11 | 11-casey-proto.pdf | ~6.7 | Middle | One-year career break (2023); MSc |
| 12 | 12-riley-example.pdf | ~2.8 | **Excluded** | Below 5 years; **no Docker** (two-column layout) |
| 13 | 13-dana-null.pdf | ~8.8 | **Excluded** | **No Laravel** (Yii2 / CodeIgniter only) |
| 14 | 14-lee-placeholder.pdf | ~6.3 | **Excluded** | **No Docker** (Laravel Forge, plain servers) |
| 15 | 15-kai-demo.pdf | ~2.0 | **Excluded** | Below the 5-year minimum |
| 16 | 16-avery-mockup.pdf | ~6.8 | **Excluded** | **No PHP or Laravel** (Node.js developer) |
| 17 | 17-quinn-scan.pdf | ~5.8 | Middle–high | **OCR test:** image-only PDF, no text layer |
| 18 | 18-reese-docx.docx | ~5.1 | Middle | **DOCX test:** Word file, with a skills table |
| 19 | 19-skyler-twocol.pdf | ~7.9 | Top–middle | **Layout test:** two columns, odd headings ("Where I've worked", "Toolbox"), dates like "03/2022 – now" |
| 20 | 20-drew-minimal.pdf | ~10 | Middle–low | **Missing sections:** no summary, no education, one line of skills, "2016 – present" |
| 21 | 21-jesse-undated.pdf | 7 (stated) | Top–middle | **No job dates:** years only in the summary ("7 years of experience"), read by the local model with the quote |
| 22 | 22-parker-tilldate.pdf | ~8.8 | Middle | **Rule gaps:** "Jan 2020 – Till Date" and "01.2018 – 12.2019"; Docker only in "no manual steps using Docker" (still counts); "PHP8"; "Certified Scrum Master" with no education (no degree) |
| 23 | 23-nia-nodates.docx | unknown | Ranked + ⚠ | **No dates, no years anywhere:** not excluded; experience 0; "please check" calendar icon |
| 24 | 24-omar-sixwords.docx | 6 (stated) | Ranked | **No dates, years in words** ("Over six years"): read by the local model |
| 25 | 25-lina-threeyears.docx | 3 (stated) | **Excluded** | **No dates, 3 years stated:** "About 3 years (read by the local model; no job dates found)" |
| 26 | 26-hana-wishful.docx | ~9.8 | **Excluded** | **Wish only:** "Interested in learning Docker" does not count (the second look agrees) |
| 27 | 27-ravi-containers.docx | ~8.8 | Ranked | **Docker never named:** "container images ... Compose files", found by meaning or by the local model's second look |
| 28 | 28-mei-since.docx | ~10.4 | Top group | **New date formats:** "Since March 2019" and "06.2016 – 02.2019"; MSc; AWS cert |

Notes:
- 23-28 are small Word files for trying the local-model cases by hand
  (upload them with **Add CV** on the job page).
- "Excluded" = fails a mandatory requirement, so not ranked (trainer
  clarification, requirement.md F1).
- The minimum years are treated as mandatory here (the profile says "5+ years").
- Order inside a group may differ; the groups are what matters.
