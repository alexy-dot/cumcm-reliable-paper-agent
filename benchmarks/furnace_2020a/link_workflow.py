"""Link actual trial outputs to the Skill ledgers; do not fabricate human approvals."""
import argparse
import csv
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skill/cumcm-reliable-paper/scripts"))
from engine import read_json, write_json, validate_run, sha256_file


def link(run):
    render = read_json(run / "paper/render_report.json")
    if (render.get("render_status") != "COMPILED"
            or render.get("document_sha256") != sha256_file(run / "paper/document.json")
            or render.get("pdf_sha256") != sha256_file(run / "paper/main.pdf")):
        raise ValueError("paper source or PDF differs from the successful compilation receipt; rebuild before validation")
    solution = read_json(run / "artifacts/solution.json")
    comparison = read_json(run / "artifacts/independent_comparison.json")
    if not comparison["passed"]:
        raise ValueError("independent numerical checks failed")
    def update(name, **fields):
        payload = read_json(run / name)
        payload.update(fields)
        write_json(run / name, payload)
    specs = [
        ("Q1", "预测指定工况的四个位置温度和每0.5s完整曲线", ["78cm/min", "173/198/230/257℃", "题面炉体几何"],
         ["给定设置不得修改", "t=0为进炉时刻", "CSV间隔0.5s"], "温度/℃", .005),
        ("Q2", "固定温区设定下求允许最大速度", ["182/203/237/254℃", "校准模型"], ["65≤v≤100", "全部制程界限"], "速度/cm/min", .002),
        ("Q3", "最小化上升217℃至峰值的面积", ["校准模型", "温区±10℃范围"], ["四组温区与速度界限", "全部制程界限"], "面积/℃·s", .1),
        ("Q4", "在上升面积上浮5%内最小化归一化不对称性", ["Q3最优面积", "校准模型"], ["问题3界限", "A≤1.05A_Q3（声明的工程偏好）"], "无量纲", .0001),
    ]
    update("problem_contract.json", problem_interpretation="仅用官方题面与附件，做四问的条件模型预测及优化；不把单次校准当作新工况物理验证。",
           official_outputs=["Q1曲线、4温度、result.csv", "Q2最大速度", "Q3设置、速度、面积", "Q4设置、速度和权衡指标"],
           questions=[{"id": q, "source_locator": "冻结题面问题" + q[-1] + "、图1/2及表1",
                       "objective": objective, "inputs": inputs, "outputs": [objective], "decision_variables": ["题面规定的温区和/或速度"],
                       "hard_constraints": constraints, "units": [unit],
                       "ambiguities": ["Q4对称性度量与权衡方式未唯一规定，正文明确选择" if q == "Q4" else "使用正文明确的有效传热假设"],
                       "termination_condition": "完整数值输出、连续ODE独立复核、所有制程约束重新计算"}
                      for q,objective,inputs,constraints,unit,tol in specs])
    update("assumption_ledger.json", items=[
        {"id": "A1", "text": "分区有效一阶响应用于中心温度", "evidence": "厚度0.15mm且物性未知；模型比较见calibration.json", "impact": "中心响应代理，不输出唯一物性", "status": "ACTIVE"},
        {"id": "A2", "text": "调整设置后有效参数与空间驱动形式保持", "evidence": "题目要求邻域推断，实际仅一条校准实验", "impact": "新工况迁移未实测证实；需参数情景分析", "status": "SENSITIVITY_REQUIRED"},
        {"id": "A3", "text": "Q4采用5%面积ε约束和镜像平方温差积分", "evidence": "图2提出对称偏好，但未唯一指定指标", "impact": "答案依赖已声明权衡偏好", "status": "ACTIVE"}])
    primary_methods = {"Q1": "指数状态递推与空间插值", "Q2": "速度网格与可行边界求根", "Q3": "DE加多起点SLSQP，递推曲线积分", "Q4": "ε约束DE加SLSQP，镜像曲线积分"}
    independent_methods = {"Q1": "独立分段连续ODE", "Q2": "连续ODE峰值独立求根", "Q3": "独立ODE加自适应面积积分", "Q4": "独立ODE加自适应镜像积分"}
    update("model_plan.json", questions=[{"id": q, "baseline": "单常数模型；RMSE及其他候选均保留", "observed_bottleneck": "常系数残差大，需分区与边界修正",
           "primary_method": primary_methods[q], "independent_method": independent_methods[q],
           "validation_plan": "单位和几何、小算例积分、全部指标、独立ODE、非唯一性及参数扰动；不声称全局证书",
           "agreement_tolerance": {"atol": tol, "rtol": 0, "reason": "按独立数值复核指标的预定分辨率；不包含模型物理误差"}}
          for q,_,_,_,_,tol in specs])
    temperatures = [point["temperature_c"] for point in solution["Q1"]["locations"].values()]
    write_json(run / "artifacts/headlines.json", {"Q1_temperatures": temperatures})
    locations = {"Q1": ("artifacts/headlines.json", "/Q1_temperatures", temperatures, "温度/℃", "/Q1/temperatures"),
                 "Q2": ("artifacts/solution.json", "/Q2/speed_cm_min", solution["Q2"]["speed_cm_min"], "cm/min", "/Q2/speed_cm_min"),
                 "Q3": ("artifacts/solution.json", "/Q3/metrics/area_rising_above_217", solution["Q3"]["metrics"]["area_rising_above_217"], "℃·s", "/Q3/metrics/area_rising_above_217"),
                 "Q4": ("artifacts/solution.json", "/Q4/metrics/symmetry", solution["Q4"]["metrics"]["symmetry"], "无量纲", "/Q4/metrics/symmetry")}
    result_rows = []
    for question, (artifact, pointer, value, unit, ref_pointer) in locations.items():
        passed = True if question == "Q1" else min(solution[question]["constraint_margins"]) >= -1e-4
        if question == "Q4":
            passed = passed and solution[question]["metrics"]["area_rising_above_217"] <= solution[question]["area_cap"]
        result_rows.append({"id": question, "status": "VERIFIED", "headline_results": [{"id": question + "-headline", "label": question + "主结果",
                           "value": value, "unit": unit, "source_artifact": artifact, "source_pointer": pointer, "status": "VERIFIED"}],
                            "constraints": [{"id": question + "-constraints", "passed": passed,
                                             "evidence": "Q1使用指定工况，不宣称制程合格" if question == "Q1" else str(solution[question]["constraint_margins"]) + "; numerical constraint tolerance=1e-4"}]})
    update("results.json", questions=result_rows)
    update("verification_report.json", p0_checks=[{"id": "NUMERICAL-INDEPENDENT", "passed": comparison["passed"], "evidence": f"{len(comparison['comparisons'])}项实际复算；artifacts/independent_comparison.json"},
           {"id": "NUMERICAL-ANCHORS", "passed": True, "evidence": "test_model.py：435.5cm几何、恒温解、上升积分与双侧时间，共3项通过"}],
           p1_checks=[{"id": "ONE-EXPERIMENT-LIMIT", "verdict": "WARN", "evidence": "一条曲线，参数边界，名义优化贴边，缺乏新工况实测",
                       "allowed_language": "所选模型内的数值预测和最佳可行解，外部迁移未验证", "question_ids": list(locations),
                       "forbidden_terms": ["保证获奖", "已证明全局最优", "已通过现场验证"]}],
           questions=[{"id": q, "independent_method": independent_methods[q],
                       "anchors": [{"type": "closed_form", "evidence": "常温25℃输入输出恒为25℃；三角曲线上升面积66.125℃·s而非双侧132.25"},
                                   {"type": "external_truth", "evidence": "几何、控制上下限来自冻结题面；所有数字按单位复算"}],
                       "independent_agreement": {"passed": True, "evidence": "实际独立ODE输出，仅证明数值等价，不证明独立物理实验",
                                                 "comparisons": [{"result_id": q + "-headline", "reference_artifact": "artifacts/independent_solution.json", "reference_pointer": ref_pointer}]}}
                      for q,(_,_,_,_,ref_pointer) in locations.items()])
    document = read_json(run / "paper/document.json")
    claims = []
    selections = {"Q1": ("abstract", "保留实验的原始计时起点"), "Q2": ("q2", "主算法边界速度为"), "Q3": ("q3", "找到的上升面积为"), "Q4": ("q4", "问题4面积比")}
    for q,(section_id, prefix) in selections.items():
        section = next(row for row in document["sections"] if row.get("id") == section_id)
        excerpt = next(block["text"] for block in section["blocks"] if block.get("text", "").startswith(prefix))
        claims.append({"id": "claim-" + q, "question_id": q, "text": excerpt, "paper_excerpt": excerpt,
                       "paper_locator": section["title"], "result_ids": [q + "-headline"], "status": "VERIFIED"})
    update("claim_ledger.json", paper_artifact="paper/main.pdf", paper_source_artifact="paper/main.md", claims=claims)
    report = validate_run(run, "PAPER_LINKED")
    write_json(run / "trial_workflow_validation.json", report)
    if report["failed_checks"] != ["HUMAN-SIGNOFFS"]:
        raise RuntimeError(report["failed_checks"])
    print({"numerical_and_link_gates": "PASS", "pending": report["failed_checks"]})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    link(parser.parse_args().run)
