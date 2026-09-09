"""Build support files and the same-source complete program appendix."""
import argparse
import json
import shutil
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
COMMON=HERE/"renderer"
if not COMMON.exists():COMMON=HERE.parents[1]/"skill/cumcm-reliable-paper/scripts"
sys.path.insert(0,str(COMMON))
from package_support import package_support


def package(run):
    staging=run/"artifacts/support-input";staging.mkdir(parents=True,exist_ok=False)
    selection=[]
    names=("prepare.py","solve.py","verify.py","alternatives.py","figures.py","paper.py","workbooks.mjs","check_workbooks.py","run_all.py","package.py","test_supply.py","requirements.txt")
    for name in names:
        target=staging/name;shutil.copy2(HERE/name,target)
        selection.append({"source":str(target.relative_to(run)),"archive_path":name,"role":"document" if name.endswith(".txt") else "code"})
    for name in ("render_paper.py","render_latex.py","package_support.py"):
        target=staging/"renderer"/name;target.parent.mkdir(exist_ok=True);shutil.copy2(COMMON/name,target)
        selection.append({"source":str(target.relative_to(run)),"archive_path":"renderer/"+name,"role":"code"})
    for path in sorted((run/"artifacts/submission").glob("*.xlsx")):
        selection.append({"source":str(path.relative_to(run)),"archive_path":path.name,"role":"data"})
    for name in ("facts.json","plans.json","ranking.json","data-analysis.json","verification.json","workbook-verification.json","alternatives.json","capacity-sensitivity.json"):
        selection.append({"source":"artifacts/"+name,"archive_path":"results/"+name,"role":"data"})
    readme=staging/"使用说明.txt"
    readme.write_text("2021 C限时演练支撑文件\n\n安装 requirements.txt 后，运行：\npython run_all.py --source 官方原题及四份工作簿目录 --output 新输出目录\n\n默认独立复算四问数值及情景，不读取预先发布的结果来求解。原题和原始工作簿由使用者提供，文件指纹在 results/data-analysis.json。\n加 --deliver 可重建结果工作簿、图表和包含源码附录的论文，需要本机Codex的artifact-tool Node运行时、Tectonic或XeLaTeX及中文字体。可用 --node、--artifact-modules、--latex-compiler、--cache-dir 指定已有环境；程序不自动安装。\n\n附件A和附件B填写的是问题2、3、4主方案。43家材料结构备选与48家边界保护方案在 results/alternatives.json。归一化采购费不是已知人民币费用。能力结论依赖标准合同规模、供货响应和初始库存假设。\n\n重新回放不改变首次限时成绩；实际队伍审核和比赛规则核验仍需真实完成。\n",encoding="utf-8")
    selection.append({"source":str(readme.relative_to(run)),"archive_path":readme.name,"role":"document"})
    receipt=package_support(run,{"files":selection})
    print({"support_files":receipt["file_count"],"complete_source_files":receipt["code_count"],"sha256":receipt["sha256"]},flush=True)


if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("run",type=Path);package(ap.parse_args().run)
