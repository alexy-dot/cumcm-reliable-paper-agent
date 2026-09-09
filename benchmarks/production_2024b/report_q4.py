"""Explain sample-conditional decisions without fabricating measured sample counts."""
import argparse
from pathlib import Path
from prepare import read_json,write_json,sha256_file


def report(run,folders):
    scenarios=[]
    for folder in folders:
        protocol=read_json(folder/"protocol.json");result=read_json(folder/"result.json");checked=read_json(folder/"verification.json")
        if result["protocol_sha256"]!=sha256_file(folder/"protocol.json") or checked["result_sha256"]!=sha256_file(folder/"result.json") or not checked["passed"]:
            raise ValueError("posterior result or verification is stale")
        scenarios.append({"protocol":protocol,"result":result,"verification":checked})
    lines=["# 2024 B第四问：样本计数条件下的生产决策", "",
        "原题没有给出实际抽样样本量和次品件数，因此不存在仅凭表中名义次品率就能确定的唯一后验决策。本文提供接收各零件与工序抽样计数的接口，并用20件、200件两组明确标注的示例展示样本量作用。示例中的计数不是题面观测，也不是实验结果。", "",
        "## 1. 输入和统计模型", "",
        "每个质量参数输入(n,k)，n为检测件数、k为次品数。零件样本来自随机采购；半成品和最终组装的样本必须在全部输入子件确认合格的条件下取得，否则估计的是混合缺陷率，不能作为题目附录定义的条件组装次品率。", "",
        "采用独立Beta(1,1)先验和Bernoulli似然，得到Beta(k+1,n−k+1)后验。独立性及先验均为模型选择，需由实际抽样方式和经验判断；该后验概率与第一问的频率学错误率保证不是同一概念。若全样本均坏，在这一先验下平均的1/(1−p)发散，不能继续报告有限返工期望。", "",
        r"$$p_j\mid k_j,n_j\sim\mathrm{Beta}(k_j+1,n_j-k_j+1),\qquad\pi^*=\arg\min_{\pi\in\Pi}\mathbb E_{p\mid k,n}[C(\pi,p)].$$", "",
        "将同一组抽到的质量参数传入完整返工成本模型，再对条件期望成本积分；不能只把后验均值代入非线性成本公式。每件实物的质量仍保持不变，变化的是未知总体参数的后验抽样，不是在每次拆解时重抽实物好坏。", "",
        "## 2. 选择与验证分开", "",
        "使用512组参数样本比较第二问16类有效策略和第三问65,536类策略，保存前五个候选后冻结。另用8192组参数样本评价所选策略及名义次品率策略，不根据这批验证样本重新挑选。误差标准误只描述随机积分精度；参数分位数描述不同真实次品率下的条件期望成本，不是单个订单损失的分布。", "",
        "第二问另用每个参数16/32个Gauss-Jacobi节点的三维确定性积分核对全部有效策略，所选策略均达到该积分比较的最低成本。第三问所选策略恰好全部检测上游且全部拆解，可用Beta逆合格率矩得到解析期望：", "",
        r"$$\mathbb E[(1-p)^{-1}]=\frac{\alpha+\beta-1}{\beta-1},\qquad\mathbb E[p/(1-p)]=\frac\alpha{\beta-1},\quad\beta>1.$$", "",
        "## 3. 两组示例结果", "",
        "示例对每个参数取n=20或200，k=np₀；两种样本量都能精确表示原题5%、10%、20%的比例。它们有相同样本比例，但后验均值及分散程度不同。表中第二问使用确定性积分成本，第三问使用所选策略的解析期望。", "",
        "| 示例 | 问题 | 新购零件检测 | 成品检测 | 成品拆解 | 期望成本/元 | 期望利润/元 | 相对名义策略改变 |", "| --- | --- | --- | --- | --- | ---: | ---: | --- |"]
    compact=[]
    for scenario in scenarios:
        label=scenario["protocol"]["samples"]["label"];result=scenario["result"];verification=scenario["verification"]
        rows=[]
        for name,r in result["results"].items():
            policy=r["selected_policy"]
            cost=next(c["quadrature_selected_cost"] for c in verification["checks"] if c["problem"]==name) if name!="Q3" else verification["q3_analytic"].get("analytic_cost",r["selected"]["posterior_mean_cost"])
            price=200 if name=="Q3" else 56
            record={"problem":name,"selected_policy":policy,"expected_cost":cost,"expected_profit":price-cost,"changed":r["policy_changed"]}
            rows.append(record)
            lines.append(f"| {label} | {name} | {','.join(map(str,policy['part_tests']))} | {policy['final_test']} | {policy['final_dismantle']} | {cost:.5f} | {price-cost:.5f} | {'是' if r['policy_changed'] else '否'} |")
        compact.append({"label":label,"provenance":result["sample_provenance"],"results":rows,"verification_passed":verification["passed"]})
    lines += ["", "检测/拆解列的1表示执行、0表示不执行。第三问两个示例均检测全部零件和半成品、各层均拆解且不检最终成品；半成品的具体开关保留在结果JSON中。", "",
        "20件样本情景下，第二问的情形1、5、6改变策略；200件情景下六种情形都回到名义策略。第三问策略不变，但后验期望利润约从49.8333元增加至59.1833元，逐渐接近名义次品率下的60.2222元。这不是增加检测样本本身创造了这些利润：当前表未扣除新增抽样费用，且只是不同信息条件下的预测。", "",
        "第一问的抽样成本不能凭空设定。若需联合优化抽样与生产，必须再提供检测单价、批量、信息获取时点和决策损失；这里给出的目标是“已有抽样信息条件下”的生产策略。若需成本分位数、风险厌恶或最坏情景目标，应显式改写目标后重新选策略。", "",
        "## 4. 实际使用与边界", "",
        "将真实计数按示例JSON结构传入sampled_rates.py的--samples，注明provenance，并按阶段填写random_supply或good_inputs。接口拒绝缺少阶段、非法计数和条件不匹配的组装记录。--make-example只用于生成明确标注的示例，不默认补造实际计数。", "",
        "给定样本和先验的计算方案已实现；原题没有的真实样本结果仍未知。蒙特卡洛搜索并非对第三问所有参数情景的精确后验最优性证明，实际应用还需要先验合理性、样本代表性和人工复核。", ""]
    (run/"q4-report.md").write_text("\n".join(lines),encoding="utf-8")
    output={"scope":"Q4 conditional solution and two illustrative count scenarios; counts are not observed competition data", "scenarios":compact,
            "source_results":{folder.name:sha256_file(folder/"result.json") for folder in folders},"submission_ready":False,"national_award_level":"NOT_ESTABLISHED"}
    write_json(run/"artifacts/q4_summary.json",output)
    print({"scenarios":len(scenarios),"sample_provenance":"ILLUSTRATIVE_COUNTS_NOT_OBSERVED"},flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);p.add_argument("folders",type=Path,nargs="+");args=p.parse_args();report(args.run,args.folders)
