"""Build a deterministic support ZIP and complete source appendix from explicit files."""
import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def _relative(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("use a portable relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in (".", "..") for part in value.split("/")):
        raise ValueError("paths must remain inside their root")
    return path


def package_support(run, selection, output="artifacts/submission-package"):
    run = Path(run).resolve()
    if (run / "state.json").is_file() and json.loads((run / "state.json").read_text())["stage"] == "VERIFIED":
        raise ValueError("sealed runs are read-only; package a new version")
    destination = run / _relative(output)
    destination.resolve().relative_to(run)
    if destination.exists():
        raise ValueError("package destination already exists; choose a new version")
    if not isinstance(selection, dict) or not isinstance(selection.get("files"), list) or not selection["files"]:
        raise ValueError("selection must list the files to include")
    entries = []
    names = set()
    for item in selection["files"]:
        if not isinstance(item, dict) or item.get("role") not in ("code", "data", "document"):
            raise ValueError("each file requires role code/data/document")
        source = run / _relative(item.get("source"))
        source.resolve().relative_to(run)
        if any(parent.is_symlink() for parent in [source, *source.parents] if parent != run and run in parent.parents):
            raise ValueError("select regular files, not symbolic links")
        if not source.is_file():
            raise ValueError("selected file does not exist")
        name = str(_relative(item.get("archive_path")))
        if name.casefold() in names or name.casefold() in {"manifest.json", "appendix.json"}:
            raise ValueError("duplicate or reserved archive filename")
        names.add(name.casefold())
        if source.stat().st_size > 50_000_000:
            raise ValueError("selected file exceeds packager memory limit (not an official rule)")
        content = source.read_bytes()
        code = content.decode("utf-8-sig") if item["role"] == "code" else None
        entries.append({"path": name, "role": item["role"], "bytes": len(content),
                        "sha256": hashlib.sha256(content).hexdigest(), "content": content, "code": code})
    entries.sort(key=lambda entry: entry["path"])
    manifest = {"schema_version": "1.0", "scope": "explicitly selected support files; completeness requires task review",
                "files": [{key: row[key] for key in ("path", "role", "bytes", "sha256")} for row in entries]}
    blocks = [{"text": "以下文件与支撑包同源生成，完整代码逐文件列出。此清单不表示人工核验或正式提交已经完成。"},
              {"table": [["文件", "用途类别", "字节数"]] + [[row["path"], row["role"], row["bytes"]] for row in entries] + [["manifest.json", "文件校验清单", "随包生成"]], "long_table": True}]
    blocks.extend({"code": row["code"], "filename": row["path"], "source_sha256": row["sha256"]}
                  for row in entries if row["role"] == "code")
    appendix = {"id": "support-appendix", "title": "附录：支撑文件与完整源程序", "page_break_before": True, "blocks": blocks}
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".package-", dir=destination.parent))
    try:
        archive_path = temporary / "support.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            def add(name, content):
                info = zipfile.ZipInfo(name, date_time=(2000,1,1,0,0,0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                archive.writestr(info, content)
            for row in entries:
                add(row["path"], row["content"])
            add("manifest.json", (json.dumps(manifest, ensure_ascii=False, indent=2)+"\n").encode())
        if archive_path.stat().st_size > 20_000_000:
            raise ValueError("support ZIP exceeds conservative 20 MB limit")
        appendix_path = temporary / "appendix.json"
        appendix_path.write_text(json.dumps(appendix, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
        receipt = {"archive": "support.zip", "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                   "md5": hashlib.md5(archive_path.read_bytes(), usedforsecurity=False).hexdigest(),
                   "appendix_sha256": hashlib.sha256(appendix_path.read_bytes()).hexdigest(),
                   "file_count": len(entries), "code_count": sum(row["role"] == "code" for row in entries),
                   "submission_ready": False, "manual_review": "PENDING", "manifest": manifest}
        (temporary / "package_receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        os.rename(temporary,destination)
    except BaseException:
        shutil.rmtree(temporary)
        raise
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run",type=Path)
    parser.add_argument("--selection",type=Path,required=True)
    parser.add_argument("--output",default="artifacts/submission-package")
    args = parser.parse_args()
    result=package_support(args.run,json.loads(args.selection.read_text(encoding="utf-8")),args.output)
    print(json.dumps({key:value for key,value in result.items() if key!="manifest"},ensure_ascii=False,indent=2))
