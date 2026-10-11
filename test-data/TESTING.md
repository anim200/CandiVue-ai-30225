# Testing one job from start to finish

Everything here is **synthetic** (made-up people, the fictional company
"Example Freight Ltd.", example.com addresses). It is for development and
testing only; the final demo uses the trainer's sample CVs (requirement.md
N13, CN5).

| Folder | What | Where it goes |
|---|---|---|
| `knowledge-base/` | 6 reference documents, one folder per collection | Knowledge base page |
| `synthetic-cvs/` | 28 CVs (PDF, Word, a scanned PDF, two-column layouts) and `EXPECTED.md`, the answer key | Job page, **Add CV** |
| `edge-cases/` | `not-really-a-pdf.pdf`: text with a .pdf name | Job page, **Add CV** (must be refused) |

The test job is **PHP Laravel Developer**, the job `EXPECTED.md` was written for.

## 1. Knowledge base

1. Open **Knowledge base**. For each folder in `knowledge-base/`, pick the
   collection with the same name under **Add to**, then drop its file(s):
   - `company-policies/` → Company policies (2 files)
   - `previous-job-profiles/` → Previous job profiles
   - `reference-library/` → Reference library
   - `email-templates/` → Email templates
   - `question-bank/` → Interview question bank
2. Each document shows **Indexing**, then **Ready** with its passage count
   (needs the local Ollama models).
3. **Try a search**: "How many days do engineers work in the office?" should
   find the hybrid work policy first.

## 2. Create the job in the Hiring Assistant

1. **Jobs → Create job with Hiring Assistant**.
2. Send this message:

   > We need a PHP Laravel Developer with at least 5 years of experience.
   > PHP, Laravel and Docker are must-haves. An AWS certification is nice to
   > have. Use our company policies and the previous senior PHP developer
   > profile when you write the job description.

3. Expect: a profile card (mandatory PHP, Laravel, Docker; preferred AWS
   certification; 5+ years; suggested weights), a step line "Looked at …
   passages in the knowledge base", and job description version 1 **waiting
   for your approval**, with "Based on" chips.
4. Try **Reject with feedback** ("Shorter, and mention hybrid work"), then
   **Edit**, then **Approve**.
5. "Post this job to the job board?" → **Don't post** is fine for this test.
   (Posting needs a valid Blogger refresh token and the Google Form link.)

## 3. Applicants

1. Open the job from **Jobs**. If the profile is not saved yet, the page says
   why **Screen CVs** is disabled.
2. **Add CV** → select all 28 files in `synthetic-cvs/` (PDF and DOCX).
   The result box shows how many were added.
3. **Add CV** → `edge-cases/not-really-a-pdf.pdf` → it is refused and the
   applicant row says **File refused**.
4. Remove one applicant with the bin icon: a confirm dialog, then a
   "Removed …" message top right.

## 4. Screening

1. **Screen CVs**: a striped progress bar counts "n of 28 CVs". The first run
   takes a few minutes on a laptop CPU; later runs reuse the parsed CVs.
2. When it ends: a **Screening finished** message, the ranking, the
   **Excluded** list and the applicants list folded below.
3. Compare with `synthetic-cvs/EXPECTED.md`: groups (top / middle / excluded)
   should match; order inside a group may differ.
4. Click a candidate: the side panel shows the score breakdown and each
   requirement with its evidence line from the CV.
5. Change a weight and **Save weights**: a "Weights saved" message, then the
   yellow note "The weights changed since the last screening" with
   **Screen again**.
6. **Jobs** list: the job shows "n ranked". In the Hiring Assistant, the
   progress bar ticks **CVs screened**.
