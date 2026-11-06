# ATS Resume Generator

Builds a one-page, ATS-parseable resume from a **single YAML file**, tailors the bullets to a specific job description, then **audits the PDF it produced** and refuses to call it done if anything an ATS depends on is missing.

Most resume tools stop at "here is a PDF". This one treats the PDF as a claim that has to be verified — the same way you would not trust a build that never ran the tests.

---

## Why the audit is the interesting part

An ATS parses text. A resume can look perfect on screen and still fail:

| Failure | What the ATS sees |
|---|---|
| Two-column layout | Columns interleaved, sentences spliced together |
| Tables used for layout | Cells read out of order |
| Text in an image | Nothing at all |
| `List Bullet` style in Word | The private-use character `\uf0b7` instead of a bullet |
| A font the machine lacks | Silently substituted, changing line breaks and page count |
| Header/footer | Some parsers skip them entirely — contact info lost |

So after generating the file, the tool reopens the PDF with `pdftotext` and `pdfinfo` and checks the conditions that matter:

```
[OK] 1 pagina
[OK] texto selecionavel
[OK] tem EXPERIENCE
[OK] tem EDUCATION
[OK] tem SKILLS
[OK] email presente
[OK] sem caractere de falha
```

If any check fails it exits non-zero. A resume that is 2 pages, or that lost its email to a header, never reaches the "done" state.

---

## Two bugs this caught on itself

**The `List Bullet` trap.** Using python-docx's built-in `List Bullet` style writes the bullet as the Symbol font glyph `\uf0b7`. The PDF renders it, a human sees a bullet, and the ATS sees a private-use codepoint. Fixed by writing a literal `•` into the run with a negative first-line indent — no list style, no font dependency.

**The invisible font substitution.** The generator asked for Calibri, which does not exist in the headless Linux container doing the DOCX to PDF conversion. LibreOffice quietly substituted Noto Serif: different metrics, different line breaks, different page count. The audit checks the PDF, so the substitution showed up. Fixed by using a font that is actually installed and verifying with `pdffonts` that the embedded font is the expected one.

Both were invisible by reading the code. They only appeared by running it and reading the output — which is the reason the audit step exists at all.

---

## Tailoring without inventing

The generator is allowed to **reorder and select** from the master file. It is never allowed to invent an achievement.

- `resumos_por_area` — a summary per target area (solar, power systems, drafting, project controls), written once and reused.
- `resumos_por_vaga` — an override keyed by job id, for a specific posting.
- `bullets_por_vaga` — the bullets to use for that role, keyed by job id.
- `competencias_por_vaga` — competencies reordered so what the job asks for comes first.

When no per-job override exists, bullets are ranked by how many of the job description's keywords they contain. Measured effect on the domain-term coverage of the generated resume: **27% before reordering, 85-88% after** — with no new claims added.

---

## Scoring, not just generating

`review.py` grades the output against an 8-item rubric (keyword coverage, quantified evidence, action verbs, length, tone, specificity) on a 0-10 scale and approves only with an average of 8.0 or more **and no single item below 6**.

That second condition matters. Trimming bullets to fit one page pushed "quantified evidence" down to 3/10 while the average still looked healthy — an average hides exactly the weakness you would get caught on. The rule now keeps a number in roughly 80% of bullets ("4 phases", "2 states", "20+ works", "6 plants", "BRL 4 million").

---

## Usage

```bash
pip install -r requirements.txt
# plus: soffice (LibreOffice), pdftotext, pdfinfo (poppler-utils)

cp master.example.yaml master.yaml     # then put your real history in it

# whole-profile resume
python3 build_package.py --master master.yaml --out out --nome-arquivo resume

# resume targeted at one job
python3 build_package.py --master master.yaml --vaga job.json --id <job_id>

# resume for an area, no job posting needed
python3 build_package.py --master master.yaml --area "Solar / PV" --cargo "Solar Design Engineer"

# grade the result
python3 review.py out/resume.pdf
```

Exit code 1 means the audit failed — wire it into CI and a broken resume cannot be published.

---

## The master file

One YAML file is the only source of truth: identity, summary, experience with bullets, education, competencies, plus the per-area and per-job overrides. Adding a new specialization means adding a summary section, not editing a document.

```yaml
experiencia:
  - empresa: Example Corp
    cargo: Analyst I — Electrical Engineer
    inicio: 2022-05
    fim: atual
    bullets:
      - "Inspect electrical projects for each of 4 completed phases."
```

Dates are structured (`YYYY-MM`) and rendered as `May 2022 - Present`, so a tenure can never be miscalculated by hand.

---

## Stack

Python 3 · python-docx (DOCX generation) · LibreOffice `soffice` (DOCX to PDF) · poppler `pdftotext`/`pdfinfo` (verification) · PyYAML.

## License

MIT
