"""Check the selected runtime without installing packages or changing a contest run."""
from __future__ import annotations
import contextlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROFILES={"core":[],"paper":["reportlab","pypdf"],"statistics":["numpy","scipy","sklearn"],
          "submission":["fitz"],"all":["reportlab","pypdf","numpy","scipy","sklearn","fitz","openpyxl","matplotlib","fontTools"]}
INSTALL_NAMES={"sklearn":"scikit-learn","fitz":"PyMuPDF","fontTools":"fonttools"}
IMPORT_PROBE=r'''
import importlib, json, sys
try:
    module=importlib.import_module(sys.argv[1])
    print(json.dumps({"passed":True,"version":str(getattr(module,"__version__",getattr(module,"VersionBind","unknown")))}))
except Exception as exc:
    print(json.dumps({"passed":False,"error":type(exc).__name__+": "+str(exc)}))
    raise SystemExit(1)
'''


def probe_import(name,python=sys.executable):
    try:
        with tempfile.TemporaryDirectory(prefix="cumcm-import-") as folder:
            env=os.environ.copy();env["MPLCONFIGDIR"]=folder;env["XDG_CACHE_HOME"]=folder
            result=subprocess.run([python,"-I","-B","-c",IMPORT_PROBE,name],cwd=folder,env=env,capture_output=True,text=True,timeout=20)
        lines=result.stdout.strip().splitlines()
        info=json.loads(lines[-1]) if lines else {"passed":False,"error":result.stderr[-1200:] or "import produced no result"}
        info["passed"]=result.returncode==0 and info.get("passed") is True
        return {"module":name,"package":INSTALL_NAMES.get(name,name),**info}
    except (OSError,subprocess.TimeoutExpired,json.JSONDecodeError) as exc:
        return {"module":name,"package":INSTALL_NAMES.get(name,name),"passed":False,"error":type(exc).__name__+": "+str(exc)}


def find_compiler(explicit=None):
    if explicit:
        path=shutil.which(str(explicit))
        if path is None:return None
        return str(Path(path).resolve())
    for name in ("tectonic","xelatex"):
        if shutil.which(name):return str(Path(shutil.which(name)).resolve())
    # Codex plugin installs may be callable but absent from PATH.
    codex_root=Path(os.environ.get("CODEX_HOME",str(Path.home()/".codex")))
    candidates=sorted((codex_root/"plugins/cache/openai-bundled/latex").glob("*/bin/tectonic"),reverse=True)
    return next((str(p.resolve()) for p in candidates if p.is_file() and os.access(p,os.X_OK)),None)


def probe_compiler(path):
    if path is None:return {"passed":False,"path":None,"error":"Tectonic/XeLaTeX not found; supply --latex-compiler or install one"}
    try:
        result=subprocess.run([path,"--version"],capture_output=True,text=True,timeout=10)
        output=result.stdout or result.stderr
        supported=any(name in output.lower() for name in ("tectonic","xetex","xelatex"))
        return {"passed":result.returncode==0 and supported,"path":path,
                "version":output.splitlines()[0] if output.splitlines() else "unknown",
                "error":None if result.returncode==0 and supported else "not an executable Tectonic/XeLaTeX runtime"}
    except (OSError,subprocess.TimeoutExpired) as exc:
        return {"passed":False,"path":path,"error":str(exc)}


def compile_smoke(compiler,cache_dir=None):
    from render_latex import render_latex
    try:
        with tempfile.TemporaryDirectory(prefix="cumcm-paper-smoke-") as folder:
            root=Path(folder);(root/"paper").mkdir()
            source=root/"paper/document.json"
            source.write_text(json.dumps({"title":"中文排版自检","sections":[{"title":"摘要","blocks":[
                {"text":"检验中文正文、关键词与数学公式。"},{"equation":r"Y=\frac{XS}{100},\qquad T<350\,{}^\circ\mathrm C"},
                {"table":[["符号","含义","单位"],["$T$","温度","℃"]]},
                {"code":"temperature = '℃'\nrate_unit = 'cm·min⁻¹'\n# 中文代码注释\n","filename":"smoke.py"}]}]},ensure_ascii=False),encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):render_latex(root,source,compile_pdf=False)
            env=os.environ.copy();env["TECTONIC_CACHE_DIR"]=str(Path(cache_dir).resolve() if cache_dir else root/"cache")
            if "tectonic" in Path(compiler).name.lower():
                command=[compiler,"-X","compile","--only-cached","--untrusted","--keep-logs","--outdir",str(root/"paper"),str(root/"paper/main.tex")]
            else:
                command=[compiler,"-no-shell-escape","-interaction=nonstopmode","-halt-on-error","-output-directory",str(root/"paper"),str(root/"paper/main.tex")]
            result=subprocess.run(command,cwd=root/"paper",env=env,capture_output=True,text=True,timeout=45)
            log_path=root/"paper/main.log"
            log=log_path.read_text(errors="replace") if log_path.exists() else ""
            pdf=root/"paper/main.pdf"
            passed=result.returncode==0 and pdf.is_file() and pdf.stat().st_size>0 and "Missing character:" not in log
            report={"attempted":True,"passed":passed,"network_downloads":False,
                    "scope":"actual project renderer: Chinese, formula, table and Unicode source text; not a visual review or full-paper guarantee"}
            if passed:
                from pypdf import PdfReader
                document=PdfReader(pdf)
                text="".join(p.extract_text() or "" for p in document.pages)
                report["passed"]=all(token in text for token in ("中文","temperature","关键词"))
                report["pages"]=len(document.pages)
                report["fonts"]=sorted({str(f.get_object().get("/BaseFont","")) for page in document.pages for f in page["/Resources"].get("/Font",{}).values()})
            if not report["passed"]:
                report["error"]=(result.stdout+result.stderr+log)[-3000:]
                report["next_step"]="Check the cache directory and Chinese/code fonts; first-time Tectonic packages may need an explicitly network-enabled normal compilation"
            return report
    except (OSError,ValueError,subprocess.TimeoutExpired,ImportError) as exc:
        return {"attempted":True,"passed":False,"network_downloads":False,"error":type(exc).__name__+": "+str(exc)}


def check_environment(profiles=None,compiler=None,smoke=False,cache_dir=None):
    profiles=list(dict.fromkeys(profiles or ["core"]))
    if any(name not in PROFILES for name in profiles):raise ValueError("unknown environment profile")
    if smoke and not any(name in profiles for name in ("paper","all")):
        raise ValueError("--smoke requires --profile paper or all")
    modules=list(dict.fromkeys(module for profile in profiles for module in PROFILES[profile]))
    imports=[probe_import(name) for name in modules]
    result={"passed":sys.version_info>=(3,10) and all(row["passed"] for row in imports),
            "profiles":profiles,"python":{"executable":sys.executable,"version":platform.python_version(),"minimum":"3.10"},
            "imports":imports,"scope":"selected environment checks only; no modeling, manuscript or submission certification",
            "installs_performed":False,"network_downloads":False}
    if any(name in profiles for name in ("paper","all")):
        runtime=probe_compiler(find_compiler(compiler));result["compiler"]=runtime
        result["passed"] &= runtime["passed"]
        result["paper_smoke"]={"attempted":False,"passed":None,"reason":"request --smoke for an actual offline project compile"}
        if smoke:
            if runtime["passed"] and all(row["passed"] for row in imports if row["module"]=="pypdf"):
                result["paper_smoke"]=compile_smoke(runtime["path"],cache_dir)
            else:result["paper_smoke"]={"attempted":False,"passed":False,"reason":"compiler or pypdf prerequisite failed"}
            result["passed"] &= result["paper_smoke"]["passed"] is True
    result["missing_packages"]=[row["package"] for row in imports if not row["passed"]]
    return result
