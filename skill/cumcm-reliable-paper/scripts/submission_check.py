"""Source-bound national PDF/ZIP checks. Does not certify eligibility or award quality."""
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath


def _normalize(text):
    return re.sub(r"\s+", "", text)


def _inside(root, value):
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
        raise ValueError("use a nonempty run-relative artifact path")
    path = (root / value).resolve()
    path.relative_to(root)
    return path


def _heading_pages(pages, label):
    pattern = re.compile(r"^\s*(?:\d+(?:\.\d+)*[.、\s]*)?" + label + r"\s*(?:[：:].*)?$")
    return [(page_index, line_index) for page_index, page in enumerate(pages)
            for line_index, line in enumerate(page.splitlines()) if pattern.fullmatch(line)]


def check_submission(run_dir, paper, support, *, year, ai_used, identity_terms=(), no_code=False):
    if type(ai_used) is not bool or type(no_code) is not bool:
        raise ValueError("AI and no-code declarations must be explicit booleans")
    try:
        import fitz
    except ImportError as exc:
        raise ValueError("install scripts/requirements-submission.txt for PDF inspection") from exc
    root = Path(run_dir).resolve()
    profile_path = Path(__file__).resolve().parents[1] / "references" / f"submission-{year}.json"
    if not profile_path.is_file():
        raise ValueError(f"no verified submission profile for year {year}; do not reuse another year")
    profile_bytes = profile_path.read_bytes()
    profile = json.loads(profile_bytes)
    if profile.get("competition_year") != year:
        raise ValueError("submission profile year mismatch")
    checks = []
    manual = ["Regional submission requirements and latest notices",
              "Team-led modeling and actual human verification of AI contributions",
              "Semantic completeness, citation accuracy, actual executability and paper/support consistency",
              "Dedicated one-page abstract, correct appendix boundary and unknown identity disclosures"]
    def add(identifier, passed, detail, source="format", anchor="file", status=None):
        checks.append({"id": identifier, "status": status or ("PASS" if passed else "FAIL"), "detail": detail,
                       "source_url": profile["sources"][source]["url"], "source_anchor": anchor})
    def identity(text, location):
        hits = sum(bool(term) and _normalize(term).casefold() in _normalize(text).casefold() for term in identity_terms)
        if hits:
            add("IDENTITY", False, f"{hits} supplied identity terms matched at {location}; terms redacted", anchor="identity")
        return hits
    paper_path = _inside(root, paper)
    pages = []
    pdf = None
    if not paper_path.is_file():
        add("PAPER-FILE", False, "paper file missing")
    else:
        add("PAPER-SIZE", paper_path.stat().st_size <= profile["max_file_bytes"], f"bytes={paper_path.stat().st_size}; cap={profile['max_file_bytes']}")
        if paper_path.suffix.lower() != ".pdf":
            add("PAPER-PDF-INSPECTION", False, "Word is allowed by the rules but this checker inspects PDF only", status="UNAVAILABLE")
        else:
            try:
                pdf = fitz.open(paper_path)
                if pdf.needs_pass or not len(pdf):
                    raise ValueError("encrypted or empty PDF")
                pages = [page.get_text(sort=True) for page in pdf]
                add("PAPER-PDF-INSPECTION", True, f"pages={len(pdf)}")
            except Exception as exc:
                add("PAPER-PDF-INSPECTION", False, f"unreadable PDF: {type(exc).__name__}")
    paper_text = "\n".join(pages)
    normalized_paper = _normalize(paper_text)
    appendix_matches = _heading_pages(pages, r"附录(?:\s*[A-Z一二三四五六七八九十0-9]+)?")
    appendix = appendix_matches[0] if appendix_matches else None
    appendix_text = ""
    if appendix:
        page_index, line_index = appendix
        appendix_text = "\n".join(pages[page_index].splitlines()[line_index:]) + "\n" + "\n".join(pages[page_index + 1:])
    if pages:
        add("TEXT-EXTRACTION", all(page.strip() for page in pages), "text extraction required; scanned pages require OCR and manual review", status=None if all(page.strip() for page in pages) else "UNAVAILABLE")
        add("ABSTRACT-MARKERS", "摘要" in pages[0] and "关键词" in pages[0], "first page must contain abstract and keyword markers; semantics still need review", anchor="abstract")
        add("NO-COVER-PAGES", not _heading_pages(pages, r"(?:承诺书|编号专用页)"), "no commitment/numbering cover headings in electronic paper", anchor="abstract")
        main_pages = pages[:appendix[0] + 1] if appendix else pages
        add("NO-TOC", not _heading_pages(main_pages, r"(?:目\s*录|Contents|Table of Contents)"), "no contents heading before appendix", anchor="body")
        body_upper_bound = (appendix[0] if appendix else len(pages) - 1)
        add("BODY-PAGE-UPPER-BOUND", body_upper_bound <= profile["body_max_pages"],
            f"conservative body-page upper bound={body_upper_bound}; appendix detection needs review", anchor="body",
            status=None if body_upper_bound <= profile["body_max_pages"] else "REVIEW_REQUIRED")
        add("APPENDIX", appendix is not None, "appendix heading found" if appendix else "appendix heading not located", anchor="code")
        ai_headings = _heading_pages(pages, "AI工具使用声明")
        references = _heading_pages(pages, "参考文献")
        ordered = len(ai_headings) == 1 and bool(references) and ai_headings[0] < references[0]
        add("AI-DECLARATION-ORDER", ordered, "AI declaration heading must precede references", "ai", "declaration")
        declaration = ""
        if ordered:
            start_page, start_line = ai_headings[0]
            end_page, end_line = references[0]
            declaration = "\n".join(pages[start_page].splitlines()[start_line:])
            if end_page > start_page:
                declaration += "\n" + "\n".join(pages[start_page + 1:end_page + 1])
            declaration = declaration.split("参考文献", 1)[0]
        normalized_declaration = _normalize(declaration)
        required = "本参赛队在竞赛过程中使用了AI工具" if ai_used else "本参赛队在竞赛过程中未使用任何AI工具"
        declaration_ok = required in normalized_declaration
        contradictory = "未使用任何AI工具" if ai_used else "使用了AI工具"
        declaration_ok &= contradictory not in normalized_declaration
        if ai_used:
            declaration_ok &= "主要用于" in normalized_declaration and "详细使用情况见支撑材料" in normalized_declaration
            declaration_ok &= "【" not in normalized_declaration
        add("AI-DECLARATION-TEXT", declaration_ok, "declared use must match official wording and contain no unfilled purpose placeholder", "ai", "declaration")
        page_size_failures, margin_failures = [], []
        limit = profile["minimum_margin_mm"] * 72 / 25.4
        for index, page in enumerate(pdf):
            width, height = page.rect.width, page.rect.height
            if any(abs(value - expected * 72 / 25.4) > 1 for value,expected in zip(sorted((width,height)), profile["page_size_mm"])):
                page_size_failures.append(index + 1)
            for block in page.get_text("dict")["blocks"]:
                rect = fitz.Rect(block["bbox"])
                block_text = "".join(span["text"] for line in block.get("lines", []) for span in line["spans"]).strip()
                # Official centered footer page numbers occupy the footer margin.
                footer_number = (block.get("type") == 0 and block_text.isdigit() and rect.y0 > height - limit
                                 and abs((rect.x0 + rect.x1) / 2 - width / 2) < 18)
                if not footer_number and (rect.x0 < limit - 1 or rect.y0 < limit - 1 or rect.x1 > width - limit + 1 or rect.y1 > height - limit + 1):
                    margin_failures.append({"page": index + 1, "kind": "image" if block.get("type") == 1 else "text", "bbox": list(rect)})
            identity(pages[index], f"paper page {index + 1}")
        add("A4-PAGES", not page_size_failures, f"non-A4 pages={page_size_failures}", anchor="page")
        add("CONTENT-MARGINS", not margin_failures, {"minimum_mm": profile["minimum_margin_mm"], "tolerance_pt": 1,
                                                     "offending_blocks": margin_failures[:12], "count": len(margin_failures),
                                                     "scope": "extracted text and image bounds; vector drawings need visual review"}, anchor="page")
        identity(json.dumps(pdf.metadata, ensure_ascii=False), "PDF metadata")
    identity(paper, "paper filename")
    archive = None
    entries = []
    if support is None:
        add("SUPPORT-OMITTED", not ai_used and "本论文没有支撑材料" in normalized_paper,
            "omission requires explicit no-support statement and no AI details requirement", anchor="support")
    else:
        support_path = _inside(root, support)
        identity(support, "support filename")
        if not support_path.is_file():
            add("SUPPORT-FILE", False, "support file missing", anchor="support")
        else:
            add("SUPPORT-SIZE", support_path.stat().st_size <= profile["max_file_bytes"], f"bytes={support_path.stat().st_size}", anchor="support")
            if support_path.suffix.lower() != ".zip":
                add("SUPPORT-INSPECTION", False, "RAR is allowed but requires a separate archive reader; use ZIP for automated checks", anchor="support", status="UNAVAILABLE")
            else:
                try:
                    archive = zipfile.ZipFile(support_path)
                    entries = [item for item in archive.infolist() if not item.is_dir()]
                    paths = [item.filename for item in entries]
                    unsafe = any(PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or "\\" in name for name in paths)
                    unsafe |= any(stat.S_ISLNK(item.external_attr >> 16) or item.flag_bits & 1 for item in entries)
                    unsafe |= len(set(paths)) != len(paths)
                    add("SUPPORT-INSPECTION", bool(entries) and not unsafe, "nonempty ZIP with unique relative unencrypted regular entries", anchor="support")
                    if unsafe:
                        entries = []
                except zipfile.BadZipFile:
                    add("SUPPORT-INSPECTION", False, "invalid ZIP", anchor="support")
    source_entries = []
    detail_entries = []
    names = [PurePosixPath(item.filename).name for item in entries]
    for index, entry in enumerate(entries):
        name = PurePosixPath(entry.filename).name
        identity(entry.filename, f"archive member #{index + 1} filename")
        listed = _normalize(entry.filename) in _normalize(appendix_text) or (names.count(name) == 1 and _normalize(name) in _normalize(appendix_text))
        add("APPENDIX-FILE-LIST", listed, f"member #{index + 1}: support inventory in appendix", anchor="code",
            status=None if listed else "REVIEW_REQUIRED")
        if name == profile["ai_detail_filename"]:
            detail_entries.append(entry)
        if PurePosixPath(name).suffix.lower() in {".py", ".m", ".r", ".jl", ".c", ".cpp", ".h", ".js", ".ipynb"}:
            source_entries.append(entry)
        if entry.file_size > 20_000_000:
            add("SUPPORT-MEMBER-READ", False, f"member #{index + 1} exceeds this checker's resource limit; not an official uncompressed size rule", anchor="support", status="UNAVAILABLE")
            continue
        try:
            content = archive.read(entry)
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
            add("SUPPORT-MEMBER-READ", False, f"member #{index + 1} cannot be decoded or fails integrity check", anchor="support")
            continue
        if PurePosixPath(name).suffix.lower() in {".py", ".m", ".r", ".jl", ".c", ".cpp", ".h", ".js", ".ipynb", ".txt", ".md", ".json", ".csv"}:
            try:
                decoded = content.decode("utf-8-sig")
                identity(decoded, f"archive member #{index + 1} content")
                if entry in source_entries:
                    found = name in _normalize(appendix_text) and _normalize(decoded) in _normalize(appendix_text)
                    add("APPENDIX-SOURCE-CODE", found, f"member #{index + 1}: full normalized source and filename comparison",
                        anchor="code", status=None if found else "REVIEW_REQUIRED")
            except UnicodeDecodeError:
                add("SUPPORT-MEMBER-TEXT", False, f"member #{index + 1} is not UTF-8; needs other decoding", anchor="identity", status="UNAVAILABLE")
        elif PurePosixPath(name).suffix.lower() == ".pdf" and name != profile["ai_detail_filename"]:
            try:
                with fitz.open(stream=content, filetype="pdf") as other:
                    if other.needs_pass:
                        raise ValueError("encrypted PDF")
                    extracted = "\n".join(page.get_text() for page in other)
                    identity(extracted, f"archive member #{index + 1} PDF text")
                    identity(json.dumps(other.metadata, ensure_ascii=False), f"archive member #{index + 1} PDF metadata")
                    if not extracted.strip():
                        add("SUPPORT-PDF-TEXT", False, f"member #{index + 1} needs OCR or visual review", anchor="identity", status="REVIEW_REQUIRED")
            except Exception as exc:
                add("SUPPORT-PDF-READ", False, f"member #{index + 1} PDF unreadable: {type(exc).__name__}", anchor="identity", status="UNAVAILABLE")
        elif PurePosixPath(name).suffix.lower() != ".pdf":
            add("SUPPORT-VISUAL-OR-BINARY", False, f"member #{index + 1}: binary/image/spreadsheet content requires a suitable reader or visual review", anchor="identity", status="REVIEW_REQUIRED")
    add("SOURCE-PRESENCE", bool(source_entries) if not no_code else not source_entries and "本论文没有用到程序" in normalized_paper,
        f"source files found={len(source_entries)}; no-code declaration={no_code}", anchor="code")
    if ai_used:
        add("AI-DETAIL-FILE", len(detail_entries) == 1, f"required named PDF count={len(detail_entries)}", "ai", "detail")
        if len(detail_entries) == 1 and detail_entries[0].file_size <= 20_000_000:
            try:
                with fitz.open(stream=archive.read(detail_entries[0]), filetype="pdf") as detail:
                    if detail.needs_pass:
                        raise ValueError("encrypted AI details")
                    detail_text = "\n".join(page.get_text() for page in detail)
                    markers = [("工具", "版本", "型号"), ("目的", "用途", "环节"), ("提示", "过程"), ("采纳", "修改", "核验", "核实")]
                    content_ok = "工具" in detail_text and ("版本" in detail_text or "型号" in detail_text)
                    content_ok &= all(any(marker in detail_text for marker in group) for group in markers[1:])
                    add("AI-DETAIL-CONTENT-MARKERS", content_ok, "four content categories located; actual completeness and truth require review", "ai", "detail")
                    identity(detail_text, "AI detail PDF text")
                    identity(json.dumps(detail.metadata, ensure_ascii=False), "AI detail PDF metadata")
            except Exception as exc:
                add("AI-DETAIL-READ", False, f"cannot inspect AI detail PDF: {type(exc).__name__}", "ai", "detail")
    if not identity_terms:
        add("KNOWN-IDENTITY-SCAN", False, "no team/school/region identifiers supplied; no anonymity pass is inferred", anchor="identity", status="REVIEW_REQUIRED")
    elif not any(check["id"] == "IDENTITY" for check in checks):
        add("KNOWN-IDENTITY-SCAN", True, "no supplied identity terms matched in inspected surfaces; unknown identifiers and images require review", anchor="identity")
    if archive:
        archive.close()
    if pdf:
        pdf.close()
    fingerprints = {}
    for role, relative in (("paper", paper), ("support", support)):
        if relative is None:
            continue
        path = _inside(root, relative)
        if path.is_file():
            sha, md5 = hashlib.sha256(), hashlib.md5(usedforsecurity=False)
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    sha.update(chunk)
                    md5.update(chunk)
            fingerprints[role] = {"path": relative, "bytes": path.stat().st_size, "sha256": sha.hexdigest(), "md5": md5.hexdigest()}
    return {"year": year, "profile_verified_on": profile["verified_on"], "profile_sha256": hashlib.sha256(profile_bytes).hexdigest(),
            "scope": profile["scope"], "passed": all(check["status"] == "PASS" for check in checks),
            "submission_ready": False, "checks": checks, "manual_review_remaining": manual, "files": fingerprints,
            "failed_checks": [row["id"] for row in checks if row["status"] == "FAIL"],
            "unavailable_checks": [row["id"] for row in checks if row["status"] == "UNAVAILABLE"],
            "review_checks": [row["id"] for row in checks if row["status"] == "REVIEW_REQUIRED"],
            "note": "PASS covers only the named mechanical checks. Refresh official sources and complete substantive review before submission."}
