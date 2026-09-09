"""Compose the four-question training paper from the reviewed computed reports."""
import argparse
import re
from pathlib import Path
from prepare import read_json,write_json,sha256_file
from prior_sensitivity import checked_report
from exact_study import checked_report as checked_exact_report


def typography(text):
    replacements={"ΣbⱼRⱼ":r"$\sum_j b_jR_j$","ΣCⱼ":r"$\sum_j C_j$","bⱼ/b":r"$b_j/b$","bⱼ":r"$b_j$","Rⱼ":r"$R_j$",
                  "p₀":r"$p_0$","E⁺":r"$E^+$","E⁻":r"$E^-$","2¹⁶":r"$2^{16}$","0.9²²":r"$0.9^{22}$","0.1²":r"$0.1^2$"}
    for a,b in replacements.items():text=text.replace(a,b)
    return text


def cell(text):
    labels={"best":"最优方案","no_inspection_no_recovery":"不检不回收","inspect_and_recover_everywhere":"全检并回收",
            "新购检测1/2":"新购检测","回收未知件检测1/2":"回收检测"}
    if re.fullmatch(r"-?\d+\.\d{5,}",text):return f"{float(text):.3f}"
    return typography(labels.get(text,text))


def blocks(markdown):
    lines=markdown.strip().splitlines();result=[];table=[]
    def flush():
        if table:result.append({"table":list(table)});table.clear()
    for line in lines:
        line=line.strip()
        if line.startswith("|"):
            if not re.fullmatch(r"[| :\-]+",line):table.append([cell(c.strip()) for c in line.strip("|").split("|")])
            continue
        flush()
        if not line:continue
        if line.startswith("$$") and line.endswith("$$"):
            formula=line[2:-2]
            if formula.startswith(r"C_{\rm order,recover}"):
                formula=r"\begin{aligned}C_{\rm order,recover}={}&\sum_jC_j+a+zt+\sum_jb_jR_j\\&+b\left[(1-z)L+d+u+\frac{a+zt+p\{d+(1-z)L\}}{1-p}\right].\end{aligned}"
            result.append({"equation":formula})
        elif not line.startswith("#"):result.append({"text":typography(line)})
    flush();return result


def compose(run):
    priors=checked_report(run)
    exact=checked_exact_report(run)
    q2=read_json(run/"artifacts/rework.json");q3=read_json(run/"artifacts/multistage/result.json");q4=read_json(run/"artifacts/q4_summary.json")
    verification=read_json(run/"artifacts/verification.json");multi=read_json(run/"artifacts/multistage/verification.json")
    figures=read_json(run/"artifacts/figures/figure_evidence.json")
    if figures["source_protocol_sha256"]!=sha256_file(run/"artifacts/multistage/protocol.json") or figures["source_result_sha256"]!=sha256_file(run/"artifacts/multistage/result.json"):
        raise ValueError("figure evidence predates current production model")
    for name,digest in figures["figure_sha256"].items():
        if sha256_file(run/"artifacts/figures"/name)!=digest:raise ValueError("figure changed after evidence recording")
    if not verification["passed"] or verification["rework_sha256"]!=sha256_file(run/"artifacts/rework.json") or not multi["passed"] or multi["result_sha256"]!=sha256_file(run/"artifacts/multistage/result.json"):
        raise ValueError("Q2/Q3 verification is stale")
    for name,digest in q4["source_results"].items():
        folder=run/"artifacts"/name
        if sha256_file(folder/"result.json")!=digest or not read_json(folder/"verification.json")["passed"]:raise ValueError("Q4 verification is stale")
    best=q3["best_policies"][0];sections=[]
    def section(title,content,level=1,page=False):sections.append({"title":title,"blocks":content,"level":level,"page_break_before":page})
    text=lambda s:{"text":s}
    section("摘要",[
        text("针对采购抽样与多层电子产品生产中的质量决策问题，本文建立允许随时停止的抽样检验、保留零件质量的返工模型，以及抽样计数条件下的后验成本决策。统一以完成顾客订单的期望利润为生产指标，售价只计一次，免费补发及额外调换损失均计入成本。"),
        {"lead":"针对问题一：","text":"用双向混合似然比构造序贯接收与拒收规则，在独立Bernoulli假设下分别控制10%误接与5%误拒上界；最多检测300件仍不触发时保留未决结果。名义次品率10%时，误拒概率约2.75%，未决概率约90.57%，不以强制判定掩盖边界附近的信息不足。"},
        {"lead":"针对问题二：","text":"以零件的真实质量和已检测知识构造马尔可夫成本方程，精确比较64类声明策略，识别14类不能终止的策略。六种情形各给出最佳可终止方案，再以每种5万个完整订单的逐件仿真核对。"},
        {"lead":"针对问题三：","text":f"在八零件组装树上递推取得成本、缺陷概率与条件修复成本，精确比较65,536类策略。最优代表检测全部零件和半成品、各层拆解，但不检最终成品，期望成本{best['expected_cost']:.4f}元、利润{best['profit']:.4f}元。另以20万个订单的对象树仿真核对最优方案及基线。"},
        {"lead":"针对问题四：","text":"提供按各阶段样本数与次品数计算的接口，用独立Beta先验传播不确定性，并以有理数后验矩递推精确比较声明策略。原题未给计数，故明确标注20件与200件示例。小样本情景中第二问三种情况改变策略；第三问所选方案的后验成本分别为150.1667元和140.8167元。"},
        text("最优性限定所枚举策略类；第四问示例不是实际观测。新样本的代表性、成本口径和检测条件需人工确认，结果不等于现场验证。"),
        text("关键词：序贯检验；马尔可夫成本；条件期望；返工决策；贝叶斯决策")])
    section("一、问题重述",[],page=True)
    section("1.1 背景与给定条件",[
        text("企业购买零配件并装配电子产品；任一输入零件不合格会导致产品不合格，即使输入均合格，装配仍可能失败。企业可检测零件和产品，丢弃次品或支付费用拆解。拆解不损伤内部零件；未检次品进入市场后必须免费调换，并产生额外损失[1]。"),
        text("原题表1给出两零件产品的六种质量和成本情形；表2及图1给出八零件经三个半成品再形成最终成品的结构。半成品与成品次品率均以全部输入子件为正品为条件。金额单位为元/件。")],2)
    section("1.2 逐问任务",[
        {"lead":"问题一：","text":"设计尽可能节省检测次数的采购抽样方案，并对10%标称次品率下的95%拒收信度和90%接收信度给出具体结果。"},
        {"lead":"问题二：","text":"针对六种情形决定新购零件检测、成品检测、次品拆解与用户退货处理，给出依据和指标。"},
        {"lead":"问题三：","text":"将生产决策扩展至多工序、多零件，具体计算原题两层八零件结构。"},
        {"lead":"问题四：","text":"当各次品率来自抽样检测时，重新研究问题二、三的生产方案。原题未给具体抽样计数，需区分参数化解法与示例计算。"}],2)
    section("二、问题分析",[])
    for i,description in enumerate([
        "固定样本置信阈值若在每次检测后重复使用，可能累积过高误判率。应先确定序贯规则和停止条件，再计算错误率、未决率与样本量；缺少功效、间隔与成本要求时，不能宣称唯一的最小样本方案。",
        "返工的关键是保留零件身份和检测知识，不能把坏零件在下一轮重抽成好零件。必须检查策略是否能最终交付，并将免费补发与新销售区分。",
        "上游未检半成品的坏件率及修复费用影响最终成本。利用组装树递推条件期望，可以避免将全部状态显式展开；但父节点已坏会使子件质量发生条件相关，不能按原边际概率独立处理。",
        "相同样本次品比例未必给出相同决策，因为样本量影响不确定性。生产成本为次品率的非线性函数，应对整个成本积分，而不能仅代入后验均值。缺失实际计数时需给出可输入真实记录的计算程序。"],1):section(f"2.{i} 问题{'一二三四'[i-1]}的分析",[text(description)],2)
    section("三、模型假设",[
        text("1．采购样本和新购零件符合独立Bernoulli质量模型；未给有限批量大小，因此不声称不放回有限总体的精确抽样结论。检测无误且不损伤好件。"),
        text("2．组装失败在全部输入子件合格时按给定概率独立发生；每次重新组装可重新发生工艺失败，内部零件本身的质量不变。"),
        text("3．一次订单仅收取一次售价，免费调换直到提供合格品；未给库存、时间、能力约束、残值与检测损伤成本，故不额外补造这些数值。"),
        text("4．问题二比较新购与回收检测可分别选择的64类策略；问题三和四的有效策略在拆解后检测未知直接子件、递归修复坏件、复用已知好件。最优性不扩展至所有历史依赖策略。"),
        text("5．第四问选择独立Beta(1,1)先验，组装抽样要求全部输入确认合格。20件和200件仅为说明接口的情景；实际先验、抽样记录及依赖关系需另行确认。")])
    section("四、符号说明",[{"table":[["符号","含义","单位"],["$p_j$","阶段j的条件次品率","无量纲"],["$n,k$","抽样总数、次品数","件"],["$C,b,R$","取得成本、缺陷概率、已知坏件修复成本","元、无量纲、元"],["$a,t,d,L$","组装、检测、拆解与额外调换损失","元/件"],["$q$","本次组装整体成功概率","无量纲"],["$z$","成品检测开关","0或1"]]}])
    section("五、模型建立与求解",[])
    first=(run/"q1-q2-report.md").read_text()
    segments=re.split(r"\n## \d+\. ",first)
    first_blocks=blocks(segments[1].split("\n",1)[1])
    sampling=read_json(run/"artifacts/sampling.json")
    def probability(value):
        if value and (value<.001 or value>0.999):
            if value>0.999:return f"{value:.6f}"
            mantissa,exponent=f"{value:.2e}".split("e")
            return "$"+mantissa+r"\times10^{"+str(int(exponent))+"}$"
        return f"{value:.4f}"
    for block in first_blocks:
        if "table" in block and block["table"][0][0]=="真实次品率":
            block["table"]=[block["table"][0]]+[[f"{r['true_defect_rate']:.0%}",*[probability(r[key]) for key in ("accept_probability","reject_probability","unresolved_probability")],f"{r['expected_tests_up_to_cap']:.2f}"] for r in sampling["operating_characteristics"]]
    section("5.1 问题一：有效的序贯抽样方案",first_blocks,2)
    section("5.2 问题二：两零件的质量状态与成本",blocks(segments[2].split("\n",1)[1]),2)
    third=(run/"q3-report.md").read_text();parts=re.split(r"\n## \d+\. ",third)
    section("5.3 问题三：多层组装与条件修复",[
        text("图1按原题图1的组装关系重绘：零件1—3构成半成品1，4—6构成半成品2，7—8构成半成品3，三者再组装为成品。箭头表示材料进入上层组装；拆解后仍是原来的子件，质量与已有检测知识不重置。"),
        {"image":"artifacts/figures/assembly_tree.pdf","caption":"图1 原题八零件组装树。节点中的10%为全部输入子件合格时的条件组装次品率，不是混合输入的总体次品率。"}],2)
    for i,part in enumerate(parts[1:5],1):
        title,body=part.split("\n",1);content=blocks(body)
        if i==3:
            best_costs=figures["policy_costs"]["best"]["components"]
            all_costs=figures["policy_costs"]["inspect_and_recover_everywhere"]["components"]
            content.extend([
                {"image":"artifacts/figures/cost_breakdown.pdf","caption":"图2 三种策略每个完成订单的精确期望成本分解。各分项之和与有理数总成本严格相等，图中未用仿真均值代替理论值。"},
                text(f"购买、检测、组装、拆解和额外调换损失在同一完成订单口径下比较。最优代表不检最终成品，对应额外调换损失{best_costs['customer_exchange_loss']:.4f}元；全检方案省去该项，但增加最终检测费用{all_costs['final_inspection']:.4f}元。两者在本组条件下的其他期望费用相同，因此成本相差{all_costs['final_inspection']-best_costs['customer_exchange_loss']:.4f}元。成品检测减少顾客收到次品的风险，但本题成本目标不支持一律全检。")])
        section(f"5.3.{i} {title}",content,3)
    fourth=(run/"q4-report.md").read_text();parts=re.split(r"\n## \d+\. ",fourth)
    section("5.4 问题四：抽样率不确定性下的策略",[text("原题未给各阶段实际抽样计数，以下先给一般条件模型，再给明确标注的样本量示例。")],2)
    for i,part in enumerate(parts[1:],1):
        title,body=part.split("\n",1)
        # Split scenario rows into two manageable tables instead of shrinking a long table.
        content=blocks(body)
        for block in content:
            if "table" in block and len(block["table"][0])==8:
                rows=block["table"]
                block["table"]=[[r[0].replace("illustrative_n","n="),r[1],r[2],r[3]+"/"+r[4],r[5],r[6],r[7]] for r in rows]
                block["table"][0]=["示例","问题","零件检测","成品检/拆","成本/元","利润/元","改变"]
                for r in block["table"][1:]:
                    if r[1]=="Q3":r[2]="全检"
        section(f"5.4.{i} {title}",content,3)
    section("六、模型检验与灵敏度分析",[
        text("抽样部分以独立数值积分核对混合似然，以12步全部路径枚举核对停止概率。问题二以闭式几何重购与无次品例核对边界，并逐件模拟六种情形；问题三以原两零件马尔可夫模型核对退化特例，再用对象树模拟验证层级关系。"),
        text("第四问向量化成本在多组参数和策略上与有理数计算一致；第二问后验成本由16/32阶Gauss-Jacobi积分核对全部有效策略，第三问已选全上游检测方案由解析Beta矩核对。选择样本和验证样本分离，验证结果不用于重新调参。"),
        text("样本量从20增至200时，部分第二问策略改变，表明不能只保留一个次品率点估计。由于两个样本量都是示例，变化只支持条件敏感性，不代表企业真的获得了这些观测，也不证明实际利润改善。")])
    section("6.1 后验矩的存在条件与先验敏感性",[
        text("有限次数抽样总能产生有限的样本均值和样本标准差，但这不证明总体矩存在。若后验为Beta(α,β)，返工成本中的逆合格率矩满足下式："),
        {"equation":r"\mathbb E[(1-p)^{-2}]=\frac{(\alpha+\beta-1)(\alpha+\beta-2)}{(\beta-1)(\beta-2)},\qquad\beta>2."},
        text("β≤1时，逆合格率均值发散；1<β≤2时，均值有限但方差发散。例如Beta(1,2)不能据普通随机积分的样本标准误宣称数值误差已控制。本项目的随机积分与标准误验算接口要求各阶段β>2，否则在计算前明确报出不适用，并要求改用有依据的解析或确定性积分。该要求不等于宣称均值不存在；前文20件与200件示例均满足有限方差条件。"),
        text("保持同一批示例计数、成本和策略类，另用Jeffreys先验Beta(0.5,0.5)，以及均值0.1、强度20的Beta(2,18)先验比较。后者是假设性的先验信息，不是从原题得到的经验事实。每个先验仍先用512组参数选择，再用8192组新参数及独立积分验证，不在看到验证结果后重新挑选。"),
        {"table":[["样本量","先验","问题","确定性期望成本/元","策略改变"]]+[
            [str(r["n"]),"Beta(0.5,0.5)" if r["prior"]["name"]=="Jeffreys" else "Beta(2,18)",r["problem"],f"{r['deterministic_selected_cost']:.3f}","是" if r["changed_from_uniform_prior"] else "否"]
            for r in priors["results"] if r["problem"] in ("Q2-1","Q2-5","Q3")]},
        text("表中改变指相对于相同样本量、原均匀先验Beta(1,1)的策略。20件时，情形1在两个替代先验下改变，情形5在Beta(2,18)下改变；200件时，本次比较中全部策略保持一致。第三问策略虽不变，预测成本仍随先验变化，不能把不同先验的成本差理解为同一真实工厂的实际节省。"),
        text("四组先验/样本量情景的第二问推荐均由确定性积分核对其在16类策略中的最低期望成本，第三问已选策略的成本由解析Beta矩核对。敏感性分析仅覆盖这些明确选择，不保证对所有先验稳健；真实使用仍需先验和抽样设计评估。")],2)
    section("6.2 后验期望成本的精确积分与策略比较",[
        text("当前模型采用独立阶段先验与无共享子件的组装树，后验期望成本可以进一步解析递推，无须依赖有限组参数样本来排序。对每个子树保留以下五个后验矩，其中g=1−b为给定质量参数下该子树输出合格的概率，C为其取得成本，W=bR为缺陷加权修复成本："),
        {"equation":r"\overline C=\mathbb E[C],\quad G=\mathbb E[g],\quad U=\mathbb E[g^{-1}],\quad H=\mathbb E[C/g],\quad\overline W=\mathbb E[bR]."},
        text(r"跨子树的参数独立，但子树内的$C$与$g$不先假定独立，故显式保留联合矩$H$。对子件集合定义如下乘积与交叉项；组装自身令$r=\mathbb E[1-p]$、$v=\mathbb E[(1-p)^{-1}]$："),
        {"equation":r"G_* =\prod_jG_j,\qquad U_* =\prod_jU_j,\qquad H_* =\sum_jH_j\prod_{k\ne j}U_k."},
        text(r"未检测输出节点的四个基本矩依次为$\sum_j\overline C_j+a$、$rG_*$、$vU_*$与$v(H_*+aU_*)$。缺陷加权修复矩取决于报废或拆解，其中$u$为未知直接子件的检测费用之和："),
        {"equation":r"\begin{aligned}\overline W_{\rm scrap}&=v[H_*+(a+t)U_*]-(\sum_j\overline C_j+a+t),\\\overline W_{\rm recover}&=\sum_j\overline W_j+u(1-rG_*)+(a+t+d)(v-G_*).\end{aligned}"},
        text(r"若节点输出检测至合格，取得成本变为$\sum_j\overline C_j+a+t+\overline W$，而输出合格概率为1、加权修复成本为0。由此逐层递推到成品。成品检测开关$z$、未检调换损失$\ell=(1-z)L$下，两种处理方式的后验期望交付成本为："),
        {"equation":r"\mathbb E[C_{\rm order,scrap}]=v[H_*+(a+zt+\ell)U_*]-\ell,"},
        {"equation":r"\begin{aligned}\mathbb E[C_{\rm order,recover}]={}&\sum_j\overline C_j+a+zt+\sum_j\overline W_j\\&+u(1-rG_*)+(a+zt+d+\ell)(v-G_*).\end{aligned}"},
        text("乘积分解只用于原先独立的子树参数，不用于假定父节点失败后的子件质量仍独立。Beta后验的r与v均有解析式；将声明的十进制先验参数与整数计数转成有理数后，成本比较没有随机积分误差。该路径只需各阶段β>1，因此也可处理1<β≤2的有限均值情形，不输出不存在的方差或蒙特卡罗标准误。"),
        text("对均匀、Jeffreys及Beta(2,18)三种先验与20/200件两种示例，共六个情景重新精确枚举：每个情景的第二问六种情况各16类有效策略，第三问65,536类策略。此前随机搜索选中的全部策略都达到相应精确最小后验期望成本，原推荐无需改动。现在的最优性证据直接来自完整声明策略类的有理数比较，而不是仅比较随机搜索保留的少数候选。"),
        text("独立验证对每个情景的96个第二问策略成本作确定性积分比较，并对第三问已选策略使用另一解析式核对，共582项数值比较通过；另以混合检测和拆解的两层模型作四维积分测试。此精确性依赖模型结构、独立先验和所枚举策略，不延伸到相关质量参数、共享库存或自适应生产策略。")],2)
    section("七、模型评价与改进",[
        text("模型直接利用题意中的条件次品率、拆解不损伤、免费调换等约束，保留质量身份，避免无穷返工被有限截断掩盖。层级条件期望将复杂内部结构压缩为可逐层解释的量，且可用独立对象仿真验证。"),
        text("主要限制是独立质量与完美检测假设、所选回收策略类，以及缺失的库存和时间成本。序贯检验在阈值附近可能长期未决，贝叶斯决策也依赖先验和抽样条件。实际应用应先核对检测性能和抽样设计，再决定是否扩展状态与目标。")])
    section("八、结论",[
        text("本文给出四问的条件建模与可复算结果：序贯采购检验控制可选停止错误，生产模型保留坏件身份和已知质量，多层组装在声明策略类下精确比较，抽样记录通过完整成本的后验积分进入决策。第三问代表策略的期望利润为60.2222元；第四问示例只说明信息条件的影响，不替代真实样本或现场验收。")])
    section("AI工具使用声明",[text("本历史题训练稿使用AI工具协助建模、程序实现、独立核对和文字排版。尚未完成参赛团队人工审核与正式AI使用详情，不属于已经获准提交的竞赛论文。")])
    section("参考文献",[text("[1] 全国大学生数学建模竞赛组委会. 2024年高教社杯全国大学生数学建模竞赛B题：生产过程中的决策问题[Z]. 2024. 原题两页、图1与表1—2。")])
    section("附录",[text("项目benchmarks/production_2024b保存抽样、两零件返工、多层递推、后验积分及各自独立验证程序；结果JSON保留策略、成本、样本来源、参数及种子。正式提交仍需按当年要求整理完整源码附录、支撑包与实际AI使用详情。")])
    (run/"paper").mkdir(exist_ok=True)
    write_json(run/"paper/document.json",{"title":"基于序贯检验与条件返工成本的生产决策","sections":sections})
    print({"sections":len(sections)},flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);compose(p.parse_args().run)
