#!/usr/bin/env python3
"""Critical review of the resume and cover letter — persona: a recruiter who has
read 300+ resumes.

8-item rubric, score 0-10. Approves only with an average >= 8.0 AND no single
item below 6 — an average hides exactly the weakness you would get caught on.

Usage:
  python3 review.py out/resume.pdf
  python3 review.py out/resume.pdf --carta out/cover.pdf --jd job.txt
"""
import argparse, re, subprocess, sys

VERBS = ["designed", "managed", "led", "produced", "coordinated", "owned", "delivered",
         "inspect", "draft", "write", "directed", "cut", "issued", "reduced", "planned",
         "standardized", "performed", "served", "built", "improved", "implemented",
         "created", "developed", "signed", "shepherded", "reviewed", "authored"]

STOP = set("""a an the and or of to in for with on at by from as is are was were be been
this that these those it its their our your my we you they he she will would can could
should may might must not no nor but if then than so such into over under about across
per each other more most some any all both few many much several own same very
""".split())


def pdf_text(path):
    r = subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True)
    return r.stdout


def pdf_pages(path):
    r = subprocess.run(["pdfinfo", path], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    return 0


def keywords(txt, n=25):
    words = re.findall(r"[a-zA-Z][a-zA-Z+#.\-]{2,}", txt.lower())
    freq = {}
    for w in words:
        w = w.strip(".-")
        if w in STOP or len(w) < 3:
            continue
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:n]]


# pdftotext emits the List Bullet glyph in three shapes: alone on a line,
# glued to the text, or with a space. Normalise all of them to "bullet + text".
BULLET_GLYPHS = ("-", "\u2022", "\uf0b7", "\u00b7", "\u25aa", "\u25cf", "\u25e6")


def _normalise_bullet(line):
    t = line.strip()
    for g in BULLET_GLYPHS:
        if t == g:
            return "\u2022"                      # glyph alone: text comes on the next line
        if t.startswith(g):
            rest = t[len(g):].strip()
            if rest:
                return "\u2022 " + rest
    return line


def _lines(txt):
    out, pending = [], False
    for line in txt.splitlines():
        t = _normalise_bullet(line)
        if t == "\u2022":
            pending = True
            continue
        if pending and t.strip():
            out.append("\u2022 " + t.strip().lstrip("\u2022").strip())
            pending = False
        else:
            out.append(t)
    return out


def bullets(txt):
    bs = []
    for line in _lines(txt):
        t = line.strip()
        if t.startswith("\u2022"):
            body = t.lstrip("\u2022").strip()
            if len(body) > 25:
                bs.append(body)
    return bs


def has_metric(b):
    return bool(re.search(r"\d", b))


def starts_with_verb(b):
    first = re.split(r"[\s,]", b.strip().lower())[0]
    return first in VERBS


def evaluate(cv_txt, carta_txt=None, jd_txt=None):
    scores, notes = {}, {}

    # 1. Job-description match in the top 15% (what a human reads in 6 seconds)
    if jd_txt:
        kws = keywords(jd_txt, 30)
        top = " ".join(_lines(cv_txt)[:6]).lower()
        hit = sum(1 for k in kws if re.search(r"\b" + re.escape(k) + r"\b", top))
        scores["1 JD match at the top"] = min(10, round(hit / max(1, len(kws) * 0.25) * 10))
        notes["1 JD match at the top"] = f"{hit}/{len(kws)} job keywords in the top 15%"
    else:
        scores["1 JD match at the top"] = 8
        notes["1 JD match at the top"] = "no job description given - neutral score"

    # 2. Quantified evidence
    bs = bullets(cv_txt)
    if bs:
        pct = sum(1 for b in bs if has_metric(b)) / len(bs)
        scores["2 Quantified evidence"] = min(10, round(pct * 20))
        notes["2 Quantified evidence"] = (f"{sum(1 for b in bs if has_metric(b))}/{len(bs)} "
                                         f"bullets ({pct:.0%}) carry a number")
    else:
        scores["2 Quantified evidence"] = 0
        notes["2 Quantified evidence"] = "no bullets detected"

    # 3. Target role obvious at the top
    top = cv_txt[:300].lower()
    has_title = any(t in top for t in ["engineer", "analyst", "designer", "developer",
                                        "specialist", "manager", "consultant"])
    scores["3 Target role visible"] = 9 if has_title else 3
    notes["3 Target role visible"] = "job title on the first line" if has_title else "title missing"

    # 4. Exact keywords from the description
    if jd_txt:
        kws = keywords(jd_txt, 20)
        body = cv_txt.lower()
        hit = sum(1 for k in kws if re.search(r"\b" + re.escape(k) + r"\b", body))
        scores["4 Exact keywords"] = min(10, round(hit / max(1, len(kws) * 0.4) * 10))
        cov = hit / max(1, len(kws))
        notes["4 Exact keywords"] = f"{hit}/{len(kws)} present in the body ({cov:.0%} coverage)"
    else:
        scores["4 Exact keywords"] = 7
        notes["4 Exact keywords"] = "no job description given - neutral score"

    # 5. Density in the first half
    half = cv_txt[:len(cv_txt) // 2].lower()
    dens = sum(1 for k in keywords(cv_txt, 20) if k in half)
    scores["5 First half carries the terms"] = min(10, round(dens / 20 * 10))
    notes["5 First half carries the terms"] = (f"{dens}/20 key terms in the first half "
                                               f"({dens/20:.0%})")

    # 6. Tone
    weak = ["humbly", "i believe", "i think", "hopefully", "perhaps", "maybe",
            "i hope", "wish", "please consider", "dear sir or madam",
            "to whom it may concern"]
    found = [w for w in weak if w in cv_txt.lower()]
    scores["6 Confident tone"] = 10 if not found else max(3, 10 - 2 * len(found))
    notes["6 Confident tone"] = "no hedging" if not found else ", ".join(found)

    # 7. Bullets open with an action verb
    if bs:
        ok = sum(1 for b in bs if starts_with_verb(b))
        scores["7 Action verbs"] = min(10, round(ok / len(bs) * 10))
        notes["7 Action verbs"] = f"{ok}/{len(bs)} bullets open with a verb"
    else:
        scores["7 Action verbs"] = 0
        notes["7 Action verbs"] = "no bullets"

    # 8. Specific cover letter
    if carta_txt:
        generic = ["i am writing to express", "i am writing to apply",
                   "to whom it may concern", "dear hiring manager"]
        g = [x for x in generic if x in carta_txt.lower()]
        n_words = len(carta_txt.split())
        ok_len = 120 <= n_words <= 250
        scores["8 Specific cover letter"] = max(2, (10 if ok_len else 5) - 3 * len(g))
        notes["8 Specific cover letter"] = (f"{n_words} words" +
                                            ("" if ok_len else " (outside 120-250)") +
                                            (f"; cliches: {', '.join(g)}" if g else ""))
    else:
        scores["8 Specific cover letter"] = 6
        notes["8 Specific cover letter"] = "no cover letter given - neutral score"

    return scores, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cv")
    ap.add_argument("--carta", help="cover letter PDF")
    ap.add_argument("--jd", help="text file with the job description")
    a = ap.parse_args()

    cv_txt = pdf_text(a.cv)
    carta_txt = pdf_text(a.carta) if a.carta else None
    jd_txt = open(a.jd, encoding="utf-8").read() if a.jd else None

    if len(cv_txt.strip()) < 300:
        print("ERROR: PDF has no extractable text (probably a scan).", file=sys.stderr)
        return 2

    scores, notes = evaluate(cv_txt, carta_txt, jd_txt)
    avg = sum(scores.values()) / len(scores)
    worst = min(scores.values())
    approved = avg >= 8.0 and worst >= 6

    print(f"\nCRITICAL REVIEW - {a.cv}")
    print(f"{pdf_pages(a.cv)} page(s), {len(cv_txt.split())} words\n")
    for k in sorted(scores):
        mark = "OK     " if scores[k] >= 8 else ("WATCH  " if scores[k] >= 6 else "FAIL   ")
        print(f"  [{mark}] {k:<32} {scores[k]:>3}/10   {notes[k]}")
    print(f"\n  AVERAGE: {avg:.2f}/10   |   WORST ITEM: {worst}/10")
    print(f"  VERDICT: {'APPROVED' if approved else 'REWRITE'}")
    if not approved:
        weak_items = [k for k, v in scores.items() if v < 8]
        print("\n  What to rewrite, worst first:")
        for k in sorted(weak_items, key=lambda x: scores[x]):
            print(f"   - {k} ({scores[k]}/10): {notes[k]}")
    return 0 if approved else 1


if __name__ == "__main__":
    sys.exit(main())
