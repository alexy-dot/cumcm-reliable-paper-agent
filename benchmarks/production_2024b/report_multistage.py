"""Explain the multi-stage recursion, exact policy search and simulation evidence."""
import argparse
from pathlib import Path
from prepare import read_json,write_json,sha256_file


def report(run):
    folder=run/"artifacts/multistage";protocol=read_json(folder/"protocol.json");result=read_json(folder/"result.json");verified=read_json(folder/"verification.json")
    if not verified["passed"] or verified["result_sha256"]!=sha256_file(folder/"result.json") or result["protocol_sha256"]!=sha256_file(folder/"protocol.json"):
        raise ValueError("multistage evidence changed or failed")
    best=result["best_policies"][0]
    lines=["# 2024 B第三问：多层组装与返工", "",
        "原题第2页图1与表2：零件1/2/3构成半成品1，4/5/6构成半成品2，7/8构成半成品3，再组装成品。以下结果以独立次品、完美检测、拆解不损伤及无额外容量/时间成本为前提，目标是每个最终完成订单的期望利润。第四问的抽样率不确定性传播尚未完成，不将本文件当作四问完整论文。", "",
        "## 1. 先区分物理状态与可观察信息", "",
        "同一个坏零件被拆出来后仍然坏；已检测为好的零件保留质量知识。未检测零件的真实质量只由仿真器或概率计算内部使用，不能让决策提前看到。选择拆解时，对质量未知的直接子件逐一检测，坏子件递归修复到确认合格；已知合格子件直接复用。这个回收规则不包括选择性不检、限次返工或历史依赖报废策略，最优性范围限定于下面枚举的策略类。", "",
        "生产树没有跨支路共享零件。一个未检测半成品向上层传递取得成本C、缺陷概率b，以及发现它确实不合格后的条件修复成本R。它还保留检测成本t和是否已确认合格的标记。对检测合格的半成品，输出b=0；内部原有零件无须重新随机生成。", "",
        "## 2. 条件修复成本的递推", "",
        "设某组装节点的直接子件为j，单次组装的条件失效率为p，组装成本a、检测成本t、拆解成本d。新取得一套子件的成本为ΣCⱼ，组装成功概率为：", "",
        r"$$q=(1-p)\prod_j(1-b_j),\qquad b=1-q.$$", "",
        "若整个不合格节点报废，重新制作并检测至合格的成本G满足几何更新：", "",
        r"$$G_{\rm scrap}=\frac{\sum_j C_j+a+t}{q},\qquad R_{\rm scrap}=G_{\rm scrap}.$$", "",
        "若拆解，令u为未知子件检测成本之和，w=ΣbⱼRⱼ。关键条件关系是“子件坏必然使父节点坏”，所以父节点已判坏时，第j个子件坏的概率为bⱼ/b，而不是重新用采购次品率。线性期望允许逐项相加，不要求条件后的子件仍相互独立。", "",
        r"$$R_{\rm recover}=d+u+\frac{\sum_j b_jR_j}{b}+\frac{a+t+pd}{1-p}\quad(b>0),$$", "",
        r"$$G_{\rm recover}=\sum_j C_j+a+t+bR_{\rm recover}.$$", "",
        "第一项拆解并找出坏子件后，所有子件都已确认合格。随后只剩每次组装自身的失效，故出现(a+t+pd)/(1−p)，不能再重复购买一整套零件。若b=0，条件修复事件不可达，计算时其加权贡献为0。叶节点确认不合格后的修复是丢弃并购买检测至合格，R=(c+t)/(1−p)。", "",
        "最后成品允许不检就交付。其未检失败产生额外调换损失L，但顾客只支付一次售价。用z表示最终成品检测开关，若不拆解：", "",
        r"$$C_{\rm order,scrap}=\frac{\sum_jC_j+a+zt+b(1-z)L}{q}.$$", "",
        "若拆解，先计初次组装，再计失败后的检测、坏件修复及已知好件的重组装：", "",
        r"$$C_{\rm order,recover}=\sum_jC_j+a+zt+\sum_jb_jR_j+b\left[(1-z)L+d+u+\frac{a+zt+p\{d+(1-z)L\}}{1-p}\right].$$", "",
        "实现使用有理数保存全部成本与概率，不用有限返工深度近似无穷期望。递推可向更多树形工序扩展；若存在共享零件、库存耦合或检测误差，当前的独立支路表达需要扩展。", "",
        "## 3. 策略空间与答案", "",
        "枚举8个新购零件检测开关、3个新制半成品检测开关、3个半成品拆解开关，以及成品检测与拆解开关，共2¹⁶=65,536种组合。所有回收的未知子件均检测并修复，已确认好的子件不重复检测。每种方案由上述递推精确计算后比较有理数成本。", "",
        "| 策略 | 零件检测 | 半成品检测 | 各层拆解 | 成品检测 | 期望成本/元 | 期望利润/元 |", "| --- | --- | --- | --- | --- | ---: | ---: |"]
    all_rows=[("最优代表",best),("全检且拆解",result["baselines"]["inspect_and_recover_everywhere"]),("全不检且报废",result["baselines"]["no_inspection_no_recovery"])]
    for name,row in all_rows:
        lines.append(f"| {name} | {'全检' if all(row['part_tests']) else '不检'} | {'全检' if all(row['semi_tests']) else '不检'} | {'是' if row['final_dismantle'] and all(row['semi_dismantle']) else '否'} | {'是' if row['final_test'] else '否'} | {row['expected_cost']:.6f} | {row['profit']:.6f} |")
    lines += ["",f"最优成本的精确值为{best['cost_exact']}元，期望利润为{best['profit']:.6f}元。在当前枚举的策略类中最优解有{len(result['best_policies'])}个；不声称已证明其在所有可能的动态策略中最优。", "",
        "为什么最终成品不检：三个半成品已经确认合格，最终失效率为10%。逐次组装不检的额外调换损失为0.1×40=4元，小于每次6元检测费。两个方案都需要处理失败件和补交合格品，完整公式已经计入这些共同或相关费用。若顾客流失、时间罚款或检测成本变化，结论可能改变。", "",
        "## 4. 独立数值验证", "",
        "主程序只递推期望量；独立程序逐件创建带有真实质量、已知状态和内部子件的对象，模拟采购、检测、组装、回收和免费调换。未调用期望成本递推。最优方案用两个预定种子各模拟50000个订单，两个基线各模拟50000个订单。", "",
        "| 仿真方案 | 种子 | 订单数 | 精确成本 | 仿真平均成本 | 平均值标准误 |", "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in verified["checks"]:lines.append(f"| {row['policy']} | {row['seed']} | {row['orders']} | {row['expected_cost']:.5f} | {row['mean_cost']:.5f} | {row['standard_error']:.5f} |")
    lines += ["", "所有差异均在预先设定的6倍标准误加0.02元范围内；这是实现一致性检查，不是现场利润置信区间。另将递推退化为两零件系统，16类有效策略与前一阶段的有理数马尔可夫模型逐一严格相等；零次品率时退化为一次采购加四次组装。", "",
        "## 5. 后续仍需完成", "",
        "第四问需要把抽样计数与次品率不确定性传入整个递推。原题未给实际样本数及次品件数，不能把10%任意解释为10/100或100/1000，也不能将组装使用混合质量输入时观察到的缺陷率直接作为“正品子件条件下”的组装缺陷率。后续需要提供参数化接口，并将没有实际数据的试算明确标为情景。", ""]
    (run/"q3-report.md").write_text("\n".join(lines),encoding="utf-8")
    write_json(folder/"summary.json",{"source_sha256":protocol["source_sha256"],"policy_count":result["policy_count"],"best_policy":best,
        "simulation_orders":sum(r["orders"] for r in verified["checks"]),"verification_passed":verified["passed"],
        "result_sha256":sha256_file(folder/"result.json"),"verification_sha256":sha256_file(folder/"verification.json"),
        "unfinished":["Q4 sampled-rate propagation","complete four-question manuscript"],"submission_ready":False,"national_award_level":"NOT_ESTABLISHED"})
    print({"q3_cost":best["expected_cost"],"q3_profit":best["profit"],"policy_count":result["policy_count"]},flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);report(p.parse_args().run)
