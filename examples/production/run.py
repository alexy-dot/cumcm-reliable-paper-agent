"""One-command synthetic modeling example. Human approvals remain pending."""
import argparse
import csv
import shutil
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "skill/cumcm-reliable-paper/scripts"))
from engine import initialize_run, read_json, write_json, validate_run
from package_support import package_support
from solver import enumerate_plans, dynamic_profit




def build_run(output):
    source = Path(__file__).parent
    initialize_run(output, source / "problem.txt", [source / "products.csv"], "合成生产计划演示", "synthetic-production")
    manifest = read_json(output / "source_manifest.json")
    frozen_data = output / manifest["sources"][1]["frozen_path"]
    with frozen_data.open(encoding="utf-8", newline="") as stream:
        products = [{"product": row["product"], **{key: int(row[key]) for key in ("hours", "material", "profit")}} for row in csv.DictReader(stream)]
    primary = enumerate_plans(products, 40, 48)
    independent = {"profit": dynamic_profit(products, 40, 48)}
    write_json(output / "artifacts/enumeration.json", primary)
    write_json(output / "artifacts/dynamic-programming.json", independent)
    # An exact tiny-case anchor with one product and hand-checkable capacity.
    tiny = enumerate_plans(products[:1], 6, 4)
    anchor_pass = tiny["profit"] == dynamic_profit(products[:1], 6, 4) == 14
    if not anchor_pass or primary["profit"] != independent["profit"]:
        raise RuntimeError("independent solver or known-case disagreement")

    def ledger(name, **fields):
        data = read_json(output / name)
        data.update(fields)
        write_json(output / name, data)

    ledger("problem_contract.json", problem_interpretation="非负整数生产计划，最大化总利润，不能超过工时和材料预算。",
           official_outputs=["最优计划", "最优利润", "资源余量", "非唯一性"], questions=[{
               "id": "Q1", "source_locator": "problem.txt 问题1与预算段落", "objective": "最大化贡献利润",
               "inputs": ["冻结的 products.csv", "40工时", "48材料单位"], "outputs": ["计划、利润、余量和最优解集合"],
               "decision_variables": ["各产品批次（非负整数）"], "hard_constraints": ["总工时<=40", "总材料<=48", "整数非负"],
               "units": ["工时", "材料单位", "利润单位"], "ambiguities": ["未发现；原题明确忽略其他费用"],
               "termination_condition": "逐产品容量上界构成有限搜索空间"}])
    ledger("assumption_ledger.json", items=[{"id": "A1", "text": "批次消耗和利润线性累加",
           "evidence": "每批固定消耗、贡献利润；题面忽略其他费用", "impact": "可采用整数线性目标与资源约束", "status": "ACTIVE"}])
    ledger("model_plan.json", questions=[{"id": "Q1", "baseline": "仅生产单位工时利润最高的B产品，共12批，利润96",
           "observed_bottleneck": "该方案先耗尽材料而仍余16工时，混合产品可能改善目标",
           "primary_method": "有界整数向量穷举", "independent_method": "剩余双资源状态动态规划",
           "validation_plan": "精确目标一致、所有容量约束、单产品小算例、全部并列最优计划",
           "agreement_tolerance": {"atol": 0, "rtol": 0, "reason": "所有输入和目标为小整数，可精确比较"}}])
    ledger("results.json", questions=[{"id": "Q1", "status": "VERIFIED", "headline_results": [{
           "id": "profit", "label": "最大利润", "value": primary["profit"], "unit": "利润单位",
           "source_artifact": "artifacts/enumeration.json", "source_pointer": "/profit", "status": "VERIFIED"}],
           "constraints": [{"id": "capacity", "passed": primary["hours_slack"] >= 0 and primary["material_slack"] >= 0,
                            "evidence": f"工时余量{primary['hours_slack']}，材料余量{primary['material_slack']}；枚举变量均为非负整数"}]}])
    ledger("verification_report.json", p0_checks=[{"id": "capacity-units", "passed": True,
           "evidence": "从冻结CSV逐项累加资源与利润，两个容量余量非负，离散批次单位一致"}],
           p1_checks=[{"id": "independent-objective", "verdict": "PASS", "evidence": "两个实际运行的算法目标值相同"}],
           questions=[{"id": "Q1", "independent_method": "剩余双资源状态动态规划",
                       "anchors": [{"type": "enumeration", "evidence": f"遍历{primary['feasible_plans']}个可行计划"},
                                   {"type": "hand_calculation", "evidence": "只有A产品且预算6工时、4材料时，最多2批，利润14"}],
                       "independent_agreement": {"passed": True, "evidence": "从两个JSON目标值重新核对", "comparisons": [{
                           "result_id": "profit", "reference_artifact": "artifacts/dynamic-programming.json", "reference_pointer": "/profit"}]}}])
    statement = f"在题设两种资源上限下，最大利润为{primary['profit']}利润单位。"
    quantities = primary["quantities"]
    uniqueness = "有限整数域穷举得到唯一最优计划。" if len(primary["optima"]) == 1 else f"共有{len(primary['optima'])}个最优计划，选取其中一个报告。"
    paper = f"""# 两种资源约束下的整数生产计划

> 合成演示；数值已复核，人工评阅未完成，不是国赛提交稿。

## 摘要

针对三类产品的整数生产决策，建立固定批次利润下的双资源约束模型。
采用有限穷举求解，并以剩余资源动态规划独立核对目标值。{statement}
{uniqueness}

## 模型与基线

令a、b、c为三种产品批次数，均为非负整数。最大化7a+8b+12c，
满足3a+2b+5c≤40及2a+4b+3c≤48。只生产单位工时利润最高的B产品时，
最多12批，利润96，仍剩16工时，说明单资源比率不足以解决本题。

## 求解与结果

产品数量上界分别由两类资源单独计算，取较小者。穷举其笛卡尔积后，
逐条检查容量，再比较利润，共得到{primary['feasible_plans']}个可行计划。
一个最优计划是A={quantities[0]}、B={quantities[1]}、C={quantities[2]}。
工时剩余{primary['hours_slack']}，材料剩余{primary['material_slack']}。
所有最优计划（按A、B、C排列）：{primary['optima']}。

## 独立复核与局限

另建V(h,m)为剩余工时h、材料m下的最优利润，递推取“不再生产”与
“生产一种可行产品后进入剩余资源状态”的最大值。动态规划未读取穷举结果，
最终目标为{independent['profit']}，与穷举严格相等。另以A产品预算(6,4)验证利润14。
整数穷举对当前有限范围给出最优性证据；规模扩大后，搜索时间会迅速增长。
未建模的需求、换线、交期和价格不确定性可能改变实际生产决策。

## 复现

运行仓库的examples/production/run.py。输入来自冻结CSV，论文数值由同一结果对象生成。
可在artifacts中检查两种算法各自输出。台账和论文尚待真实人类评阅。
"""
    (output / "paper/main.md").write_text(paper, encoding="utf-8")
    ledger("claim_ledger.json", paper_artifact="paper/main.md", paper_source_artifact="paper/main.md", claims=[{
           "id": "C1", "question_id": "Q1", "text": statement, "result_ids": ["profit"],
           "paper_locator": "摘要", "paper_excerpt": statement, "status": "VERIFIED"}])
    report = validate_run(output, "PAPER_LINKED")
    write_json(output / "demo_validation.json", report)
    reproducible = output / "artifacts/reproduction"
    reproducible.mkdir()
    shutil.copyfile(source / "solver.py", reproducible / "solver.py")
    shutil.copyfile(frozen_data, reproducible / "products.csv")
    (reproducible / "README.txt").write_text("Synthetic example, not a contest submission.\nRun: python3 solver.py --output reproduced.json\nExpected profit: 121; both algorithms must agree. Human review remains pending.\n",encoding="utf-8")
    selection = {"files":[{"source": "artifacts/reproduction/"+name, "archive_path": name, "role": role}
                          for name,role in [("solver.py","code"),("products.csv","data"),("README.txt","document")]]}
    package = package_support(output,selection)
    appendix = read_json(output / "artifacts/submission-package/appendix.json")
    sections = []
    for paragraph in paper.split("\n\n"):
        if paragraph.startswith("## "):
            sections.append({"title":paragraph[3:].strip(),"blocks":[]})
        elif paragraph.strip() and sections:
            sections[-1]["blocks"].append({"text": " ".join(paragraph.splitlines())})
    sections.append(appendix)
    write_json(output / "paper/document.json", {"title":"两种资源约束下的整数生产计划", "status_note":"合成示例，数值已复核，真实人工评阅待完成", "sections":sections})
    # The demo never fabricates approvals, advances history or seals a submission.
    if report["failed_checks"] != ["HUMAN-SIGNOFFS"]:
        raise RuntimeError(report["failed_checks"])
    return {"numerical_checks_passed": True, "submission_verified": False,
            "pending": "human review", "profit": primary["profit"], "optima": primary["optima"],
            "paper": str(output / "paper/main.md"), "support_zip": "artifacts/submission-package/support.zip",
            "support_sha256": package["sha256"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(build_run(parser.parse_args().output.resolve()))
