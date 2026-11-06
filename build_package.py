#!/usr/bin/env python3
"""Builds an ATS resume in DOCX from a single master.yaml.

ATS rules applied (all verifiable in the generated PDF):
 - 1 page when possible, no photo, no table, no column, no header/footer
 - standard headings (PROFESSIONAL SUMMARY / EXPERIENCE / EDUCATION / SKILLS)
 - simple font, 9.5pt, selectable text
 - action verbs in every bullet, metric wherever the master has one
 - zero invention: only what is in master.yaml

Usage:
  python3 build_package.py --out out
  python3 build_package.py --vaga job.json --id 0b1c32baa2326aa6
  python3 build_package.py --area "Solar / PV" --cargo "Solar Design Engineer"
"""
import argparse, os, re, sys, subprocess, yaml, datetime

TEMPLATE = """{nome}
{local} | {email} | {telefone} | {disponibilidade}

PROFESSIONAL SUMMARY

{resumo}

SKILLS

{competencias}

EXPERIENCE

{experiencia}

EDUCATION

{formacao}
"""

def load_master(path="master.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

def fmt_periodo(inicio, fim):
    def m(y):
        if not y or y == "atual":
            return "Present"
        y, mo = str(y).split("-")
        names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        return f"{names[int(mo)-1]} {y}"
    return f"{m(inicio)} - {m(fim)}"

def build_texto(m, resumo=None, competencias=None, jd_texto=None, jd_kws=None, vaga_id=None):
    """Assemble the plain-text resume. resumo/competencias allow a per-job override."""
    jd_kws = jd_kws or []
    exp_blocks, anteriores = [], []
    for e in m["experiencia"]:
        fim_raw = str(e["fim"])
        # anything that ended before 2010 collapses into one "Earlier experience" line
        if fim_raw != "atual" and int(fim_raw[:4]) < 2010:
            per = fmt_periodo(e['inicio'], e['fim']).replace(' - ', '-')
            anteriores.append(f"{e['cargo']}, {e['empresa']} ({per})")
            continue
        head = f"{e['cargo']} | {e['empresa']} | {e['local']} | {fmt_periodo(e['inicio'], e['fim'])}"
        ano_fim = 9999 if fim_raw == "atual" else int(fim_raw[:4])
        limite = 2 if ano_fim >= 2016 else 1
        bl = list(e["bullets"])
        _bv = (m.get("bullets_por_vaga") or {}).get(vaga_id or "", {})
        if e["empresa"] in _bv:
            bl = list(_bv[e["empresa"]])
            limite = 1 if len(_bv) > 5 else 2
        elif jd_texto:
            # rank bullets by how many job-description keywords they hit
            def peso(b):
                bb = b.lower()
                return -sum(1 for k in jd_kws if k in bb)
            bl = sorted(bl, key=peso)
        bullets = "\n".join(f"- {b}" for b in bl[:limite])
        exp_blocks.append(head + "\n" + bullets)
    if anteriores:
        exp_blocks.append("Earlier experience: " + "; ".join(anteriores) + ".")

    cursos = m["formacao"]
    # most recent degree on its own line, the rest compacted into a second line
    form_blocks = [f"{cursos[0]['curso']} | {cursos[0]['instituicao']}, {cursos[0]['ano']}"]
    resto = "  •  ".join(f"{c['curso']}, {c['instituicao']} {c['ano']}"
                         for c in cursos[1:])
    if resto:
        form_blocks.append(resto)

    comp = competencias or m["competencias"]
    comp_lines = []
    for grupo, itens in comp.items():
        if grupo == "idiomas":
            continue
        comp_lines.append(f"{grupo.replace('_',' ').title()}: " + ", ".join(itens))
    if not comp or "idiomas" in comp:
        lang = m["competencias"]["idiomas"]
        comp_lines.append("Languages: " + ", ".join(f"{k} ({v.lower()})" for k, v in lang.items()))

    texto = TEMPLATE.format(
        nome=m["identidade"]["nome"],
        local=m["identidade"]["local"],
        email=m["identidade"]["email"],
        telefone=m["identidade"]["telefone"],
        disponibilidade=m["identidade"]["disponibilidade"],
        resumo=(resumo or m["resumo"]["default"]).strip(),
        competencias="\n".join(comp_lines),
        experiencia="\n\n".join(exp_blocks),
        formacao="\n".join(form_blocks),
        idiomas="",
    )
    return re.sub(r"\n{3,}", "\n\n", texto).strip() + "\n"

def write_docx(texto, out_path, nome):
    """Single-column DOCX, no table — ATS-safe."""
    from docx import Document
    from docx.shared import Pt, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()
    sec = doc.sections[0]
    sec.top_margin = Inches(0.4); sec.bottom_margin = Inches(0.32)
    sec.left_margin = Inches(0.5); sec.right_margin = Inches(0.45)

    st = doc.styles["Normal"]
    FONTE = "Open Sans"
    st.font.name = FONTE; st.font.size = Pt(9.5)
    st.paragraph_format.space_after = Pt(0)
    st.paragraph_format.line_spacing = 1.0

    HEADINGS = {"PROFESSIONAL SUMMARY", "SKILLS", "EXPERIENCE",
                "EDUCATION", "LANGUAGES"}

    linhas = texto.split("\n")
    for i, linha in enumerate(linhas):
        linha = linha.rstrip()
        if not linha:
            continue
        p = doc.add_paragraph()
        r = p.add_run(linha)

        if i == 0:                                    # name
            r.bold = True; r.font.size = Pt(15); r.font.name = FONTE
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(2)
        elif linha in HEADINGS:
            r.bold = True; r.font.size = Pt(10); r.font.name = FONTE
            p.paragraph_format.space_before = Pt(5)
            p.paragraph_format.space_after = Pt(2)
            # bottom rule as a paragraph border — never a table
            pPr = p._p.get_or_add_pPr()
            from docx.oxml.ns import qn
            from docx.oxml import OxmlElement
            pbdr = OxmlElement("w:pBdr")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single"); bottom.set(qn("w:sz"), "6")
            bottom.set(qn("w:space"), "1"); bottom.set(qn("w:color"), "888888")
            pbdr.append(bottom); pPr.append(pbdr)
        elif linha.startswith("- "):
            # a REAL typographic bullet in the text, no Word list style:
            # "List Bullet" writes Symbol/\uf0b7 and breaks text extraction.
            r.text = "\u2022  " + linha[2:]
            r.font.size = Pt(9.5)
            r.font.name = FONTE
            p.paragraph_format.left_indent = Inches(0.22)
            p.paragraph_format.first_line_indent = Inches(-0.16)
            p.paragraph_format.space_after = Pt(0)
        elif linha.startswith("http") or "@" in linha and "|" in linha:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(4)
        else:
            r.font.size = Pt(9.5); r.font.name = FONTE
            p.paragraph_format.space_after = Pt(1)

    doc.save(out_path)
    return out_path

def to_pdf(docx_path, outdir):
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf",
                    "--outdir", outdir, docx_path],
                   check=True, capture_output=True)
    return os.path.join(outdir, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf")

def paginas(pdf):
    r = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True)
    for l in r.stdout.splitlines():
        if l.startswith("Pages:"):
            return int(l.split()[1])
    return None

def achar_texto(pdf):
    r = subprocess.run(["pdftotext", pdf, "-"], capture_output=True, text=True)
    return r.stdout

def auditar(pdf, texto_esperado, EMAIL=""):
    """Objective ATS checks — fail loudly when something essential is missing."""
    txt = achar_texto(pdf)
    n = paginas(pdf)
    checks = {
        "1 page": n == 1,
        "selectable text": len(txt.strip()) > 1500,
        "has EXPERIENCE": "EXPERIENCE" in txt,
        "has EDUCATION": "EDUCATION" in txt,
        "has SKILLS": "SKILL" in txt,
        "email present": bool(EMAIL) and EMAIL in txt,
        "no replacement character": "\ufffd" not in txt,
    }
    return n, checks, txt

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", default="master.yaml")
    ap.add_argument("--out", default="out")
    ap.add_argument("--nome-arquivo", default="resume")
    ap.add_argument("--vaga", help="job json to tailor against")
    ap.add_argument("--id", help="job id inside that json")
    ap.add_argument("--area", help="generate from an area summary (no job json)")
    ap.add_argument("--cargo", help="target title, used in the file name")
    a = ap.parse_args()

    m = load_master(a.master)

    if a.area:
        resumo = (m.get("resumos_por_area") or {}).get(a.area)
        if not resumo:
            print(f"area '{a.area}' has no summary. options: "
                  f"{list((m.get('resumos_por_area') or {}).keys())}", file=sys.stderr)
            return 2
        a.nome_arquivo = re.sub(r"[^a-z0-9]+", "_", (a.cargo or a.area).lower())[:48]
        texto = build_texto(m, resumo, None)
        os.makedirs(a.out, exist_ok=True)
        docx_path = os.path.join(a.out, a.nome_arquivo + ".docx")
        write_docx(texto, docx_path, m["identidade"]["nome"])
        pdf = to_pdf(docx_path, a.out)
        n, checks, txt = auditar(pdf, texto, m["identidade"].get("email", ""))
        print(f"PDF : {pdf}  ({n} page(s), {len(txt)} chars)")
        print(f"  summary used: {a.area}")
        falhou = [k for k, ok in checks.items() if not ok]
        for k, ok in checks.items():
            print(f"  [{'OK' if ok else 'FAIL'}] {k}")
        return 1 if falhou else 0

    resumo = None
    comp = None
    jd_txt, jd_kws = None, []

    if a.vaga and a.id:
        import json
        d = json.load(open(a.vaga, encoding="utf-8"))
        v = next((x for x in d["vagas"] if x["id"] == a.id), None)
        if not v:
            print(f"job {a.id} not found", file=sys.stderr); return 2
        # reorder competencies: what the job asks for comes first (never invent)
        jd_txt = v.get("descricao") or ""
        jd = jd_txt.lower()
        import re as _re
        _STOP = set("a an the and or of to in for with on at by from as is are was were be been "
                    "this that these those it its their our your my we you they he she will would "
                    "can could should may might must not no nor but if then than so such into over "
                    "under about across per each other more most some any all both few many much "
                    "several own same very experience work working team role position company years "
                    "year requirements required responsibilities ability skills including".split())
        _w = [x.strip(".-") for x in _re.findall(r"[a-zA-Z][a-zA-Z+#.\-]{2,}", jd)]
        _f = {}
        for x in _w:
            if x in _STOP or len(x) < 3:
                continue
            _f[x] = _f.get(x, 0) + 1
        jd_kws = [k for k, _ in sorted(_f.items(), key=lambda p: -p[1])[:30]]
        _cv = (m.get("competencias_por_vaga") or {}).get(a.id or "")
        comp = _cv if _cv else {}
        _kwset = set(jd_kws)
        if not _cv:
            for grupo, itens in m["competencias"].items():
                if grupo == "idiomas":
                    continue
                def _peso_comp(it, _k=_kwset):
                    toks = set(_re.findall(r"[a-z]{3,}", it.lower()))
                    return -len(toks & _k)
                comp[grupo] = sorted(itens, key=_peso_comp)
        por_vaga = (m.get("resumos_por_vaga") or {}).get(a.id or "")
        resumo_area = (m.get("resumos_por_area") or {}).get(v.get("area"))
        resumo = por_vaga or resumo_area or m["resumo"]["default"]
        a.nome_arquivo = (f"{re.sub(r'[^a-z0-9]+', '_', v['empresa'].lower())[:20]}_"
                          f"{re.sub(r'[^a-z0-9]+', '_', v['titulo'].lower())[:25]}")

    os.makedirs(a.out, exist_ok=True)
    texto = build_texto(m, resumo, comp, jd_texto=jd_txt, jd_kws=jd_kws, vaga_id=a.id)
    docx_path = os.path.join(a.out, a.nome_arquivo + ".docx")
    write_docx(texto, docx_path, m["identidade"]["nome"])
    pdf = to_pdf(docx_path, a.out)

    n, checks, txt = auditar(pdf, texto, m["identidade"].get("email", ""))
    print(f"DOCX: {docx_path}")
    print(f"PDF : {pdf}  ({n} page(s), {len(txt)} extractable chars)")
    falhou = [k for k, ok in checks.items() if not ok]
    for k, ok in checks.items():
        print(f"  [{'OK' if ok else 'FAIL'}] {k}")
    return 1 if falhou else 0

if __name__ == "__main__":
    sys.exit(main())
