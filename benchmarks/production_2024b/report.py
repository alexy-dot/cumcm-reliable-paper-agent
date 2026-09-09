"""Generate reviewable Q1/Q2 findings; explicitly keep Q3/Q4 unfinished."""
import argparse
from pathlib import Path
from prepare import read_json,write_json,sha256_file


def report(run):
    sampling=read_json(run/"artifacts/sampling.json");rework=read_json(run/"artifacts/rework.json");verification=read_json(run/"artifacts/verification.json")
    if not verification["passed"] or verification["rework_sha256"]!=sha256_file(run/"artifacts/rework.json") or verification["sampling_sha256"]!=sha256_file(run/"artifacts/sampling.json"):
        raise ValueError("results changed after independent verification")
    lines=["# 2024 B：抽样与两零件返工决策阶段结果", "",
        "本轮仅完成问题1的抽样方案与问题2的两零件策略比较。问题3的八零件多工序、问题4的抽样率不确定性传播尚未完成。本文件是可复查的建模结果，不是四问完整论文或国奖认证。", "",
        "## 1. 抽样：固定样本置信度不能直接套到反复观察", "",
        "假定批量足够大、逐件检测相互独立且检测无误，以p表示真实次品率，p₀=0.1。批量大小原题未给，因此未声称有限总体不放回抽样的精确结论。", "",
        "预先固定样本量时，22件全好满足0.9²²≤0.1，可按单侧检验拒绝p≥0.1；2件全坏满足0.1²≤0.05，可拒绝p≤0.1。两种是不同的固定样本示例，不是把它们逐件重复使用就仍有效的统一序贯方案。", "",
        "设前n件中发现k件次品，构造两个方向的混合似然比：", "",
        r"$$E_n^- = \frac{1}{p_0}\int_0^{p_0}\frac{q^k(1-q)^{n-k}}{p_0^k(1-p_0)^{n-k}}\,dq,\qquad E_n^+ = \frac{1}{1-p_0}\int_{p_0}^1\frac{q^k(1-q)^{n-k}}{p_0^k(1-p_0)^{n-k}}\,dq.$$", "",
        "若E⁺≥20则拒收；若E⁻≥10则接收；否则继续。达到预设上限300仍不触发时报告未决，不能强制判定。均匀混合分布只定义检验统计量，不意味着假定实际次品率服从该分布，也不是将E值当成后验概率。", "",
        "对每个q>p₀，若真实p≤p₀，单次似然比增量的条件期望为1+(p-p₀)(q-p₀)/[p₀(1-p₀)]≤1；积分后E⁺是初值1的非负超鞅。由Ville不等式，任意停止时刻的误拒概率不超过1/20。E⁻方向同理控制p≥p₀时的误接概率不超过1/10。该保证依赖独立Bernoulli观测和预先确定的检验。", "",
        "| 已检n | 接收：次品数至多 | 拒收：次品数至少 |", "| ---: | ---: | ---: |"]
    for n in (2,22,34,50,100,200,300):
        row=sampling["boundaries"][n-1];lines.append(f"| {n} | {row['accept_at_most'] if row['accept_at_most'] is not None else '不触发'} | {row['reject_at_least'] if row['reject_at_least'] is not None else '不触发'} |")
    lines += ["", "使用概率状态递推计算全部停止路径，得到：", "", "| 真实次品率 | 接收概率 | 拒收概率 | 未决概率 | 期望检测数（至300件） |", "| ---: | ---: | ---: | ---: | ---: |"]
    for r in sampling["operating_characteristics"]:
        lines.append(f"| {r['true_defect_rate']:.0%} | {r['accept_probability']:.5f} | {r['reject_probability']:.5f} | {r['unresolved_probability']:.5f} | {r['expected_tests_up_to_cap']:.2f} |")
    naive=sampling["naive_repeated_fixed_tests_at_boundary"]
    lines += ["",f"对照反例：在p=0.1时，逐次套用固定样本阈值的拒收概率为{naive['reject_probability']:.5f}，接收概率为{naive['accept_probability']:.5f}，均超过对应的序贯错误率上限。混合检验在阈值附近有较多未决，这是数据难以区分的结果，不能用更好看的强制决策代替。", "",
        "原题未指定与10%的最小可区分差异、检验功效、采购损失或检测单价，因此无法证明某个方案具有唯一最小样本量。本方案给出可随时停止的有效规则与实测效率，不声称已解决所有可能代价定义下的样本量最优。", "",
        "## 2. 返工：保留真实质量与已知信息", "",
        "以完成一个顾客订单的期望利润为比较指标。售价只收取一次；未检测的次品交付后需免费调换，另付题面给出的物流/信誉损失。不得将每一次补发都算作新的销售收入。", "",
        "每个零件分为三种内部状态：坏且未检、好但未检、已检测为好，共9种物理与知识状态。策略看不到前两类的真实质量差异，只能选择检测与否；检测后才知道好坏。组装次品率仅在两个零件都好时适用。零件质量随拆解保留，组装过程的失效在每次重新组装时独立发生。", "",
        "枚举六个开关：新购零件1/2检测、回收且质量未知的零件1/2检测、成品检测、拆解。已知好的零件不重复检测；回收坏件被检出时丢弃，并采购检测至取得好件。若没有拆解则重新采购一整套。这是声明的64种平稳策略类，未声称覆盖所有历史依赖策略。", "",
        "对每个可达状态写成本方程C=c+QC，以有理数高斯消元计算(I−Q)C=c；新订单另加初次采购及检测成本。无合格吸收出口的可达循环导致矩阵奇异，必须标记无法终止，不能用任意返工次数截断后报有限利润。", "",
        "| 情形 | 新购检测1/2 | 回收未知件检测1/2 | 成品检测 | 拆解 | 期望成本/元 | 利润/元 | 期望组装次数 |", "| ---: | --- | --- | --- | --- | ---: | ---: | ---: |"]
    selected=[]
    for row in rework["cases"]:
        best=row["optimal_policies"][0];b=best["bits"];yes=lambda v:"是" if v else "否"
        lines.append(f"| {row['case']} | {yes(b[0])}/{yes(b[1])} | {yes(b[2])}/{yes(b[3])} | {yes(b[4])} | {yes(b[5])} | {best['expected_cost']:.6f} | {best['profit']:.6f} | {best['expected_assemblies']:.6f} |")
        selected.append({"case":row["case"],"bits":b,"cost_exact":best["cost_exact"],"profit":best["profit"]})
    lines += ["", "表中仅列一个代表策略。新购已检测为好的零件不会变成未知件，所以部分回收检测开关永远不执行，形成等价最优策略；所有并列解保留在rework.json。六种情形均有50个可终止策略、14个非终止策略，不将后者当作高收益解。", "",
        "例如两种新购零件都不检、回收也不检但始终拆解，只要购入的任一零件有缺陷，该缺陷便一直存在，后续成品永不合格。把每轮零件次品率重置为采购概率，会错误地把这个死循环变成可完成的几何过程。", "",
        "独立仿真逐件生成采购、检测、组装、返工和调换，保留每个零件的真实质量与已检测标记。每种情形模拟50000个完整订单，六组平均成本与有理数期望值均在预先约定的6倍标准误加0.02元范围内。它核对实现，不意味着现场成本或真实质量波动已经验证。", "",
        "## 3. 验证与下一步", "",
        "抽样混合似然用独立数值积分核对10个计数/方向组合；12次观测的小规模全路径穷举核对停止概率与期望样本量。生产模型另以无次品、无拆解几何重购、全已知好件等闭式算例检查成本与收入。", "",
        "问题3仍需建立多层半成品的可观测状态与回收转移；问题4缺少实际抽样成功/失败计数，不能把名义次品率凭空变成某个后验分布。后续应输出条件于抽样记录的决策与不确定性分析，分别说明输入缺失和可计算的情景。", ""]
    path=run/"q1-q2-report.md";path.write_text("\n".join(lines),encoding="utf-8")
    write_json(run/"summary.json",{"source_sha256":read_json(run/"artifacts/facts.json")["source_sha256"],"completed_scope":["Q1 anytime-valid sampling candidate with explicit unresolved outcomes","Q2 exact comparison of 64 declared stationary policies"],
        "unfinished":["Q3 multi-stage eight-component model","Q4 propagation from actual or declared sample counts","full four-question manuscript"],
        "selected_policies":selected,"sampling_at_boundary":next(r for r in sampling["operating_characteristics"] if r["true_defect_rate"]==.1),
        "verification_passed":verification["passed"],"source_outputs":{name:sha256_file(run/"artifacts"/name) for name in ("facts.json","protocol.json","sampling.json","rework.json","verification.json")},
        "submission_ready":False,"national_award_level":"NOT_ESTABLISHED"})
    print({"report":str(path),"scope":"Q1/Q2 only"},flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);report(p.parse_args().run)
