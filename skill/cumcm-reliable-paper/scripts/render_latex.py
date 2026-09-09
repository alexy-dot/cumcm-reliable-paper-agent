"""Typeset Chinese papers with real inline/display mathematics using XeTeX/Tectonic."""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path


def escape_text(text):
    replacements = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
                    "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(replacements.get(character, character) for character in str(text))


def inline(text):
    text = str(text)
    if text.count("$") % 2:
        raise ValueError("unbalanced inline math delimiters")
    return "".join(piece if piece.startswith("$") and piece.endswith("$") else plain_with_units(piece)
                   for piece in re.split(r"(\$[^$]*\$)", text))


def plain_with_units(text):
    units = {"cm·min⁻¹": r"$\mathrm{cm}\,\mathrm{min}^{-1}$", "℃·s": r"${}^{\circ}\mathrm{C}\!\cdot\!\mathrm{s}$",
             "℃/s": r"${}^{\circ}\mathrm{C}/\mathrm{s}$", "℃": r"${}^{\circ}\mathrm{C}$"}
    pattern = "(" + "|".join(re.escape(unit) for unit in units) + ")"
    return "".join(units.get(piece, escape_text(piece)) for piece in re.split(pattern, text))


def render_latex(run, source, *, compiler=None, cache_dir=None, compile_pdf=True):
    run = Path(run).resolve()
    source = Path(source).resolve()
    if (run / "state.json").exists() and json.loads((run / "state.json").read_text())["stage"] == "VERIFIED":
        raise ValueError("create a new version before typesetting a sealed run")
    data = json.loads(source.read_text(encoding="utf-8"))
    output = run / "paper"
    output.mkdir(exist_ok=True)
    document_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
    (output / "render_report.json").write_text(json.dumps({"render_status": "PENDING", "source": source.name,
                                                          "document_sha256": document_sha256,
                                                          "note": "An existing PDF may be from an earlier generation; not accepted until compilation succeeds."},
                                                         ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if platform.system() == "Darwin":
        fonts = r"\setmainfont{Times New Roman}\setCJKmainfont{Songti SC}\setCJKsansfont{Heiti SC}"
    else:
        fonts = r"\setmainfont{TeX Gyre Termes}\setCJKmainfont{FandolSong-Regular.otf}[BoldFont=FandolSong-Bold.otf]\setCJKsansfont{FandolHei-Regular.otf}"
    preamble = r"""\documentclass[12pt,a4paper]{article}
\usepackage{fontspec,xeCJK,amsmath,amssymb,geometry,graphicx,booktabs,tabularx,array}
\usepackage{titlesec,caption,placeins,indentfirst,float}
\geometry{margin=28mm,footskip=12mm}
FONTS
\XeTeXlinebreaklocale "zh"
\XeTeXlinebreakskip=0pt plus 1pt
\setlength{\parindent}{2em}
\setlength{\parskip}{0.25em}
\linespread{1.35}
\titleformat{\section}{\sffamily\bfseries\large}{}{0em}{}
\titleformat{\subsection}{\sffamily\bfseries\normalsize}{}{0em}{}
\titleformat{\subsubsection}{\sffamily\normalsize}{}{0em}{}
\titlespacing*{\section}{0pt}{1.2em}{0.7em}
\captionsetup{font=small,skip=6pt}
\renewcommand{\arraystretch}{1.35}
\setlength{\emergencystretch}{2em}
\begin{document}
""".replace("FONTS", fonts)
    lines = [preamble, r"\begin{center}{\sffamily\bfseries\LARGE " + inline(data["title"]) + r"}\end{center}"]
    markdown = ["# " + data["title"], ""]
    if data.get("status_note"):
        lines.append(r"\begin{center}\small " + inline(data["status_note"]) + r"\end{center}")
        markdown.extend(["> " + data["status_note"], ""])
    for section in data["sections"]:
        lines.append(r"\FloatBarrier")
        if section.get("page_break_before"):
            lines.append(r"\clearpage")
        level = section.get("level", 1)
        if level not in (1, 2, 3):
            raise ValueError("section level must be 1, 2 or 3")
        command = {1: "section", 2: "subsection", 3: "subsubsection"}[level]
        lines.append("\\" + command + "*{" + inline(section["title"]) + "}")
        markdown.extend(["#" * (level + 1) + " " + section["title"], ""])
        for block in section["blocks"]:
            if "text" in block:
                lead = block.get("lead", "")
                prefix = r"{\sffamily\bfseries " + inline(lead) + "}" if lead else ""
                lines.extend([prefix + inline(block["text"]), r"\par"])
                markdown.extend([("**" + lead + "** " if lead else "") + block["text"], ""])
            elif "equation" in block:
                formula = block["equation"]
                lines.extend([r"\begin{equation}", formula, r"\end{equation}"])
                markdown.extend(["$$", formula, "$$", ""])
            elif "table" in block:
                rows = block["table"]
                columns = len(rows[0])
                if any(len(row) != columns for row in rows):
                    raise ValueError("ragged paper table")
                lines.extend([r"\begin{table}[H]\centering\small",
                              r"\begin{tabularx}{\linewidth}{" + r">{\raggedright\arraybackslash}X" * columns + "}", r"\toprule"])
                for index, row in enumerate(rows):
                    formatted = []
                    for cell in row:
                        if index == 0 and "/" in str(cell) and "$" not in str(cell):
                            label, unit = str(cell).split("/", 1)
                            formatted.append(r"\shortstack[l]{" + inline(label) + r"\\(" + inline(unit) + ")}")
                        else:
                            formatted.append(inline(cell))
                    lines.append(" & ".join(formatted) + r" \\")
                    if index == 0:
                        lines.append(r"\midrule")
                    markdown.append("| " + " | ".join(str(cell) for cell in row) + " |")
                    if index == 0:
                        markdown.append("| " + " | ".join("---" for _ in row) + " |")
                lines.extend([r"\bottomrule\end{tabularx}\end{table}"])
                markdown.append("")
            elif "image" in block:
                image = (run / block["image"]).resolve()
                image.relative_to(run)
                relative = os.path.relpath(image, output).replace(os.sep, "/")
                if any(character in relative for character in "{}%\n\r"):
                    raise ValueError("unsupported characters in figure path")
                lines.extend([r"\begin{figure}[H]\centering",
                              r"\includegraphics[width=\linewidth]{\detokenize{" + relative + "}}"])
                if block.get("caption"):
                    lines.append(r"\caption*{" + inline(block["caption"]) + "}")
                lines.append(r"\end{figure}")
                markdown.extend([f"![{block.get('caption', '')}]({relative})", ""])
            else:
                raise ValueError("unknown paper block")
    lines.append(r"\end{document}")
    tex = output / "main.tex"
    tex.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output / "main.md").write_text("\n".join(markdown), encoding="utf-8")
    if compile_pdf:
        executable = compiler or shutil.which("tectonic") or shutil.which("xelatex")
        if not executable:
            raise ValueError("TeX source written; install Tectonic/XeLaTeX or supply --compiler. Do not fall back to plaintext formulas.")
        env = os.environ.copy()
        env["TECTONIC_CACHE_DIR"] = str(Path(cache_dir).resolve() if cache_dir else run / "tmp/tectonic-cache")
        if "tectonic" in Path(executable).name.lower():
            command = [str(executable), "-X", "compile", "--untrusted", "--keep-logs", "--outdir", str(output), str(tex)]
        else:
            command = [str(executable), "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "-output-directory", str(output), str(tex)]
        completed = subprocess.run(command, cwd=output, env=env, capture_output=True, text=True)
        (output / "typesetting.log").write_text(completed.stdout + completed.stderr, encoding="utf-8")
        if completed.returncode:
            raise RuntimeError("TeX compilation failed; inspect paper/typesetting.log")
        log = (output / "main.log").read_text(encoding="utf-8", errors="replace") if (output / "main.log").is_file() else completed.stdout + completed.stderr
        if "Missing character:" in log:
            raise RuntimeError("TeX reported missing glyphs; inspect paper/main.log")
        from pypdf import PdfReader
        pdf = PdfReader(output / "main.pdf")
        font_names = sorted({str(font.get_object().get("/BaseFont", "")) for page in pdf.pages
                             for font in page["/Resources"].get("/Font", {}).values()})
        report = {"pages": len(pdf.pages), "encrypted": pdf.is_encrypted,
                  "text_characters": sum(len(page.extract_text() or "") for page in pdf.pages),
                  "visual_review": "PENDING", "source": source.name, "backend": "latex",
                  "fonts": font_names, "pdf_sha256": hashlib.sha256((output / "main.pdf").read_bytes()).hexdigest(),
                  "document_sha256": document_sha256, "render_status": "COMPILED"}
        (output / "render_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({"tex": str(tex), "pdf_compiled": compile_pdf, "visual_review": "PENDING"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--compiler")
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    render_latex(args.run, args.source, compiler=args.compiler, cache_dir=args.cache_dir, compile_pdf=not args.source_only)
