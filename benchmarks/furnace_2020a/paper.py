"""Compose the complete training paper from computed artifacts, without manual numbers."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skill/cumcm-reliable-paper/scripts"))
from engine import read_json, write_json, sha256_file


def compose(run):
    solution = read_json(run / "artifacts/solution.json")
    calibration = read_json(run / "artifacts/calibration.json")
    independent = read_json(run / "artifacts/independent_comparison.json")
    reference = read_json(run / "artifacts/independent_solution.json")
    sensitivity = read_json(run / "artifacts/sensitivity.json")
    structural = read_json(run / "artifacts/structural_evidence.json")
    decision = read_json(run / "artifacts/decision_evidence.json")
    scenario = read_json(run / "artifacts/scenario_design.json")
    if not scenario.get("passed") or scenario["candidates"]["source_sha256"] != sha256_file(run/"artifacts/solution.json"):
        raise ValueError("scenario design is incomplete, failed or bound to an earlier solution")
    if scenario["candidate_sha256"] != sha256_file(run/"artifacts/scenario_candidates.json"):
        raise ValueError("candidate record changed after held-out validation")
    if decision.get("status") != "COMPLETE" or not decision.get("passed"):
        raise ValueError("decision sensitivity evidence is incomplete or failed")
    for name in ("solution.json","calibration.json","sensitivity.json"):
        if decision.get("source_sha256",{}).get(name) != sha256_file(run / "artifacts" / name):
            raise ValueError("decision evidence is stale; rerun against the current source artifacts")
    if not structural["passed"]:
        raise ValueError("model-structure evidence must pass before citing the conditional proofs")
    selected = calibration["models"]["zoned"]
    q1, q2, q3, q4 = [solution[name] for name in ["Q1", "Q2", "Q3", "Q4"]]
    f = lambda value, n=3: f"{value:.{n}f}"
    def scientific(value):
        mantissa, exponent = f"{value:.2e}".split("e")
        return f"${mantissa}\\times10^{{{int(exponent)}}}$"
    text = lambda value: {"text": value}
    equation = lambda value: {"equation": value}
    table = lambda rows: {"table": rows}
    figure = lambda filename, caption: {"image": "artifacts/figures/" + filename + ".png", "caption": caption}
    sections = []
    def section(title, blocks, page=False, level=1, key=None):
        sections.append({"title": title, "blocks": blocks, "page_break_before": page,
                         "level": level, "id": key})

    area_change = (q4["metrics"]["area_rising_above_217"] / q3["metrics"]["area_rising_above_217"] - 1) * 100
    symmetry_change = (1 - q4["metrics"]["symmetry"] / q3["metrics"]["symmetry"]) * 100
    section("摘要", [
        text("针对回焊炉温度曲线预测与工艺调整问题，本文从能量收支出发，建立分区有效传热模型，将温区空间驱动、中心温度响应与制程约束相联系，在同一模型下研究最大过炉速度、上升回流面积及曲线对称性的优化。"),
        {"lead": "针对问题一：", "text": f"保留实验的原始计时起点，采用有界最小二乘辨识有效时间常数与边界参数。选定模型的拟合RMSE为{f(selected['rmse'])}℃，模型选择留出块RMSE为{f(selected['held_block_rmse'])}℃。问题1在指定78 cm/min下的四个位置温度依次为" + "、".join(f(point["temperature_c"]) for point in q1["locations"].values()) + f"℃，并生成{q1['sample_count']}条间隔0.5 s的温度序列。"},
        {"lead": "针对问题二：", "text": f"固定温区设定，将各项制程指标表示为速度的函数，通过可行区间搜索与边界求根得到最大速度约{f(q2['speed_cm_min'])} cm/min，活动约束为峰值温度达到240℃下限。"},
        {"lead": "针对问题三：", "text": f"以上升超过217℃至峰值的面积为目标，结合差分进化与多起点SLSQP求解，得到最佳可行面积{f(q3['metrics']['area_rising_above_217'])}℃·s，速度{f(q3['speed_cm_min'])} cm/min。不同前段温区组合具有近乎相同的目标值，故同时报告代表解与替代解。"},
        {"lead": "针对问题四：", "text": f"定义覆盖峰值两侧较长区间的归一化镜像温差平方积分，在面积上浮不超过5%的约束下优化对称性，得到速度{f(q4['speed_cm_min'])} cm/min、面积{f(q4['metrics']['area_rising_above_217'])}℃·s及不对称性指标{f(q4['metrics']['symmetry'],6)}。与问题三相比，面积增加{f(area_change,2)}%，不对称性下降{f(symmetry_change,2)}%。"},
        text("通过独立连续积分、阈值求根和自适应积分核对主要结果；进一步比较面积权衡、模型形式与参数联合扰动，发现5%的面积预算未用尽，逐参数检验通过的留余量方案仍可能在联合扰动下越界。上述结论适用于所选模型与设定情景，跨工况迁移仍需新实验检验。"),
        text("关键词：回焊炉；有效传热；参数辨识；约束优化；独立数值复核")], key="abstract")

    section("一、问题重述", [], True)
    section("1.1 问题背景与已知条件", [
        text("回焊炉通过预热、恒温、回流和冷却等阶段完成电路板焊接。焊接区域中心温度随时间形成的炉温曲线影响焊接质量，题目要求在实验数据的基础上，利用机理模型分析温度变化并优化工艺设置[1]。"),
        text("所用回焊炉包括11个小温区，每区长30.5 cm，相邻温区间隔5 cm，炉前和炉后区域各长25 cm；车间温度为25℃。电路板匀速通过达到稳定状态的炉体，炉前、炉后及间隙区域不单独控温，其温度受邻近温区影响。"),
        text("附件给出一次实验的炉温曲线：小温区1—5、6、7、8—9分别设为175、195、235、255℃，10—11区设为25℃，速度为70 cm/min，焊接区域厚度为0.15 mm。进炉时开始计时，中心温度达到30℃后传感器开始记录。"),
        text("允许在上述实验设定基础上将加热温区调整±10℃，其中1—5区保持同温、8—9区保持同温、10—11区保持25℃；速度范围为65—100 cm/min。制程要求升温斜率为0—3℃/s、降温斜率为−3—0℃/s，上升过程中150—190℃停留60—120 s，高于217℃共停留40—90 s，峰值温度为240—250℃。")], level=2)
    section("1.2 问题要求", [
        {"lead": "问题一：", "text": "建立焊接中心的温度变化模型。当速度为78 cm/min，1—5、6、7、8—9区分别为173、198、230、257℃时，给出炉温曲线及第3、6、7区中点和第8区结束处的中心温度，并将每隔0.5 s的温度存入result.csv。"},
        {"lead": "问题二：", "text": "当1—5、6、7、8—9区分别设为182、203、237、254℃时，确定满足制程界限的最大允许过炉速度。"},
        {"lead": "问题三：", "text": "在允许的温区与速度范围内，并满足制程界限，使温度在上升阶段超过217℃至峰值所覆盖的面积最小，给出相应温区设定、速度、炉温曲线及面积。"},
        {"lead": "问题四：", "text": "在满足制程界限的同时，希望峰值时刻两侧高于217℃的曲线尽量对称。结合问题三进一步确定温区设定、速度和炉温曲线，并给出相应评价指标。"}], level=2)

    section("二、问题分析", [text("四问构成由温度预测到受约束决策的递进链条。首先从实验曲线辨识有效传热响应，再保持该模型不变求解给定工况及速度边界，随后引入面积与对称性目标。各问共用同一物理坐标、计时零点和制程指标，避免前后采用不同口径。")])
    section("2.1 问题一的分析", [
        text("问题一同时包含模型建立和指定工况预测。困难在于只观测了焊接中心温度，没有沿炉程的空气温度及材料物性，不能把温区设定直接当作中心温度。应从能量收支建立动态响应，以少量有效参数表征热惯性，再比较候选边界形式对实验数据的解释能力。"),
        text("温度传感器在达到30℃后才开始记录，所以第一条记录不等于进炉初始时刻。应保留原始时间，从进炉时刻开始积分；给定速度后，四个几何位置换算为时间，再插值得到所需温度，并按0.5秒间隔输出完整曲线。")], level=2)
    section("2.2 问题二的分析", [
        text("问题二固定温区温度，仅以传送速度为决策变量。提高速度可提高吞吐，但会改变加热程度及各温度区间的停留时间，因此不能只检验峰值。需要把全部制程指标写成速度的函数，扫描允许区间，定位最高可行区间，并对活动约束边界进一步求根。")], level=2)
    section("2.3 问题三的分析", [
        text("问题三同时调整四组温区和速度，属于带多重制程限制的非线性优化。面积只覆盖温度在上升阶段超过217℃至峰值的区间，积分上下限本身随决策变化，不能将下降段算入。应使用同一温度模型动态求取交点和峰值，再进行全局启发式搜索及局部精修。"),
        text("前段温区可能通过热状态传递相互补偿，从而形成目标相同但参数不同的方案。因此需要保存多个起点的可行结果、逐项复查限制，并区分数值搜索稳定性与全局最优性证明。")], level=2)
    section("2.4 问题四的分析", [
        text("问题四在问题三的基础上引入以峰值时刻为轴的对称偏好，成为多目标权衡问题。只比较两侧持续时间可能忽略曲线形状差异；只在短侧区间比较又会遗漏长侧尾部。因此采用覆盖较长一侧的镜像温差指标，并以面积上浮上限约束性能损失。"),
        text("题面没有唯一指定对称性度量和权重，应明确公布所选指标及权衡规则，再给出对应结果。对贴近制程边界的方案，还需通过参数扰动分析说明其实际使用限制。")], level=2)

    section("三、模型假设", [
        text("在题设恒速传送、炉况达到稳定及车间温度25℃的条件基础上，采用以下模型近似。"),
        text("假设1：进炉前电路板与车间达到近似热平衡，中心初温取25℃。该假设用于补足传感器启动前的未观测区；若进炉前存在预热，应另行测量初温。"),
        text("假设2：用分区有效一阶热响应近似焊接中心的温度变化。焊接区域较薄，但缺少材料物性，无法证明严格的集中参数条件；因此时间常数只作为辨识参数，不解释为唯一的真实材料属性。"),
        text("假设3：温区间有效热驱动连续过渡，炉口与冷却边界可用低参数函数近似。冷却段等效驱动不直接等同控制测点空气温度，且不改变冷却温区设定25℃这一题设。"),
        text("假设4：在题目允许的温区与速度调整范围内，辨识参数及有效驱动的空间形式保持不变。此假设使单次实验可用于邻近工况预测，但其迁移能力需要新的物理实验检验。"),
        text("假设5：不单独辨识不同材料层及可能相变对应的热参数，将其作用合并进有效时间常数。若板材、厚度或焊料发生变化，应重新校准，而不能直接套用本文参数。")])

    section("四、符号说明", [
        table([["符号", "含义", "单位"],
               [r"$T(t)$", "焊接区域中心温度", "℃"], [r"$U(x)$", "沿炉程的等效热驱动", "℃"],
               [r"$x(t)$", "距炉前入口的位置", "cm"], [r"$v$", "传送带过炉速度", "cm/min"],
               [r"$T_1,T_6,T_7,T_8$", "四组可调温区设定温度", "℃"],
               [r"$\tau_g$", "第g段有效时间常数", "s"], [r"$w$", "炉口有效过渡延伸长度", "cm"],
               [r"$L$", "冷却段有效驱动特征长度", "cm"],
               [r"$t_{150},t_{190}$", "上升过程达到150℃、190℃的时刻", "s"],
               [r"$t_{\uparrow},t_{\downarrow}$", "上升、下降过程达到217℃的时刻", "s"],
               [r"$t_{\mathrm p},T_{\max}$", "峰值时刻与峰值温度", "s，℃"],
               [r"$A$", "上升超过217℃至峰值的面积", "℃·s"],
               [r"$E(t)$", "超过217℃的非负温升", "℃"], [r"$D$", "峰值两侧比较的最大时间范围", "s"],
               [r"$J$", "归一化不对称性指标", "无量纲"]])])

    section("五、模型的建立与求解", [])
    section("5.1 问题一：温度响应模型与曲线预测", [])
    sections[-1]["level"] = 2

    section("5.1.1 温度响应模型的建立", [
        text(r"根据题面尺寸，总行程为$25+11\times30.5+10\times5+25=435.5$ cm，第$i$区起点为$25+(i-1)\times35.5$ cm。将速度$v$由cm/min换算为$v/60$ cm/s，位置与时间满足$x=vt/60$。依据初始热平衡假设，从进炉时刻$T(0)=25\,{}^{\circ}\mathrm C$开始求解。"),
        text("焊接区域厚度仅0.15 mm，但题面未给材料密度、比热、导热系数及对流参数，不能直接计算Biot数或唯一反推出物性。将中心响应近似为分区热惯性，质量、比热、有效换热面积等并入时间常数τ。该模型用于有限邻域内的工况推断，不能把拟合参数当作独立测量的物性。"),
        text(r"由能量收支的集中参数形式得到下式。其中$U$为等效热驱动，$\tau_g$为有效时间常数，单位为秒；分区指标$g$按位置在200、235.5、271、342 cm处切换。分区允许不同对流与接触条件形成不同有效速率。"),
        equation(r"\frac{\mathrm d T}{\mathrm d t}=\frac{U(x)-T}{\tau_g},\qquad x=\frac{vt}{60},\qquad T(0)=25\,{}^\circ\mathrm C."),
        text(r"加热平台的$U$取相应温区设定，温区间5 cm间隙作线性过渡。炉口采用以下光滑入口函数，其中$0\le w\le30.5$ cm。它表示炉口与第一小温区的边界效应，而非把记录起点人为后移。"),
        equation(r"U(x)=25+(T_1-25)(3s^2-2s^3),\qquad s=\min\!\left\{\frac{x}{25+w},1\right\}."),
        text(r"冷却前边界位于339.5 cm，使用下式表示热惯性与非理想边界合并后的等效驱动。该变量不直接等同冷却区控制测点的空气温度，也不改变冷却区设定25℃。从单条中心曲线，驱动场与换热速率存在混淆；$L$的迁移是本模型的重要假设。"),
        equation(r"U(x)=25+(T_8-25)\exp\!\left(-\frac{x-339.5}{L}\right),\qquad x>339.5\,\mathrm{cm}."),
        text("数值计算将空间等分，使用每段中点热驱动进行指数状态更新。该更新对分段常驱动精确；连续驱动的离散误差通过缩小网格与独立连续积分检验。校准网格0.1 cm，搜索0.25 cm，最终指标复算至0.05 cm或更细。"),
        equation(r"T_{n+1}=U_n+(T_n-U_n)\exp\!\left(-\frac{\Delta t}{\tau_g}\right).")], level=3)

    names = {"baseline":"单常数", "mixing":"边界混合", "radiative":"辐射修正", "two_node":"双节点", "smooth_two_node":"平滑双节点", "zoned":"分区有效模型"}
    section("5.1.2 参数校准与模型检验", [
        text(f"附件包含{calibration['n']}个观测点，原始记录时间为{f(calibration['record_start_seconds'],1)}—{f(calibration['record_end_seconds'],1)} s，全量检查未发现空单元格、重复行或非有限数。首条记录对应传感器启动而非进炉时刻，拟合时保留其原时间，并与从进炉初值推进的温度曲线对齐。"),
        text("采用有界非线性最小二乘。先按时间分块留出若干连续区间，以其余数据拟合并评估留出块误差，再用全部观测校准用于四问的参数。尝试多个候选形式是针对残差结构的修正过程，留出块已参与模型选择，因此其误差不能称为最终独立测试误差。"),
        text(f"模型选择关注同一验证口径下的改进，而非算法名称。与辐射修正模型相比，分区模型的留出块RMSE下降约{f((1-selected['held_block_rmse']/calibration['models']['radiative']['held_block_rmse'])*100,2)}%。其新增参数对应不同炉段的响应差异，能够保留控制变量与温度变化之间的解释链，因此选为后续四问的统一计算模型。"),
        table([["模型", "参数数", "全样本RMSE/℃", "留出块RMSE/℃"]] + [[names[name], len(row["parameters"]), f(row["rmse"]), f(row["held_block_rmse"])] for name,row in calibration["models"].items()]),
        figure("model_comparison", "图1 候选模型比较。复杂模型并非必然优于简单模型；保留失败候选。"),
        table([["参数", "数值", "单位"]] + [[name, f(value,5), "s" if index<5 else "cm"] for index,(name,value) in enumerate(zip([r"$\tau_{1\text{--}5}$", r"$\tau_6$", r"$\tau_7$", r"$\tau_{8\text{--}9}$", r"$\tau_{\mathrm{cool}}$", "$w$", "$L$"], solution["parameters"]))]),
        text(f"全样本RMSE为{f(selected['rmse'])}℃，最大绝对残差{f(selected['max_abs_error'])}℃。留出块包含{selected['held_count']}点，训练部分{selected['train_count']}点。入口参数w触及上界，表明该边界形式仍不足以完全解释炉口响应；需要保留模型形式误差。"),
        figure("calibration", "图2 选定模型与实测曲线及残差。初始记录从19秒开始，不把未观测区当作实测数据。"),
        text("Jacobian条件数与近似参数标准误仅作数值诊断。残差具有时间相关性，不能将独立同分布误差公式生成的标准误当作可靠置信区间。只有一条物理实验曲线，也无法严格区分驱动场误差和换热系数变化；需新增速度或温区扰动实验来检验参数迁移。")], level=3)

    section("5.1.3 指定工况的求解结果", [
        text("将指定的四组温区温度与78 cm/min代入，不重新拟合参数。位置由题面几何直接计算，再以x/(78/60)换算时间，避免以数组下标或温区编号直接当作时刻。"),
        table([["位置", "距入口/cm", "进炉后时间/s", "中心温度/℃"]] + [[label, f(point["x_cm"],2), f(point["time_seconds"]), f(point["temperature_c"])] for label,point in zip(["第3区中点", "第6区中点", "第7区中点", "第8区结束"], q1["locations"].values())]),
        figure("q1", "图3 问题1炉温曲线与指定位置。"),
        text(f"result.csv按0.5秒间隔从0秒输出至模型行程终点，共{q1['sample_count']}条温度记录；文件使用UTF-8 BOM以便常用表格软件读取。计算覆盖整个435.5 cm行程。"),
        text(f"该指定工况的模型峰值约{f(reference['Q1']['metrics']['peak'])}℃。问题1要求预测指定设置，并不允许为了使结果满足制程界限而改写给定温区温度或速度。")], level=3)

    metric_names = [("max_rise", "最大升温速率", "≤3℃/s"), ("max_cooling", "最大降温速率绝对值", "≤3℃/s"),
                    ("soak_150_190", "上升150—190℃时间", "60—120s"), ("time_above_217", "高于217℃总时间", "40—90s"), ("peak", "峰值", "240—250℃")]
    section("5.2 问题二：固定温区下的最大速度", [
        text("固定182、203、237、254℃，先在65—100 cm/min内检查全部制程限制并定位活动边界，再通过峰值温度下限求根。为说明该边界为何给出最大速度，而非仅是网格上最后一个可行点，下面利用一阶响应的正核性质证明峰值关于速度的单调性。"),
        text(r"在本文假设下，$\tau_g>0$及驱动$U(x)$均不随速度改变。定义变换坐标$z(x)=\int_0^x\tau_g(\xi)^{-1}\,\mathrm d\xi$、$Y_v=T_v-25$和$F=U-25$，则响应满足"),
        equation(r"\frac{\mathrm dY_v}{\mathrm dz}=\lambda_v(F-Y_v),\qquad\lambda_v=\frac{60}{v},\qquad Y_v(0)=0."),
        text(r"取$v_1<v_2$，记$r=v_1/v_2\in(0,1)$。由线性方程的卷积解可得同一位置处两种速度的响应关系："),
        equation(r"Y_{v_2}(z)=rY_{v_1}(z)+(1-r)\lambda_{v_2}\int_0^z e^{-\lambda_{v_2}(z-s)}Y_{v_1}(s)\,\mathrm ds."),
        text(r"设有限炉程内$Y_{v_1}$的最大值为$M_1>0$。上式权重非负，总和为$1-(1-r)e^{-\lambda_{v_2}z}<1$，故在整个有限区间内$Y_{v_2}(z)<M_1$。于是中心温度峰值严格随速度增大而减小。此证明不要求各制程时间单调，也不要求先假定可行速度集合只有一个区间。"),
        text(f"独立连续积分在70与90 cm/min两条曲线上验证该恒等式，最大温差为{scientific(structural['speed_comparison_identity']['max_identity_error_c'])}℃。求得峰值等于240℃的边界后，只要该点通过其余制程要求，所有更高速度必因峰值不足而不可行。由此得到模型内最大速度的条件证明；若实际换热参数随速度改变，证明不再适用。"),
        text(f"主算法边界速度为{f(q2['speed_cm_min'],6)} cm/min；独立连续积分求得{f(reference['Q2']['speed_cm_min'],6)} cm/min。活动约束是峰值降至240℃，其余指标保有名义余量。"),
        table([["制程指标", "要求", "问题2计算值"]] + [[name,limit,f(q2["metrics"][key],4)] for key,name,limit in metric_names]),
        figure("speed_boundary", "图4 固定温区下峰值随速度下降；240℃交点给出速度上界，边界处其余制程要求另行核验。"),
        text("精确数值边界附近，模型误差、计算容差及控制分辨率都会影响合格判定。不能将显示为240.000℃理解为实物温度精确等于240℃；下文另给参数情景下的留余量方案。")], level=2, key="q2")

    section("5.3 问题三：最小化上升回流面积", [
        text(r"目标面积$A$由下式定义，单位为℃·s；$t_{\uparrow}$为上升至217℃的时刻，$t_{\mathrm p}$为峰值时刻。所有温区、速度范围与制程限制均保留。采用差分进化搜索并以SLSQP精修，不把惩罚较小但仍不可行的点作为答案；最终用更细网格和独立自适应积分复核。"),
        equation(r"\min A,\qquad A=\int_{t_{\uparrow}}^{t_{\mathrm p}}\bigl[T(t)-217\bigr]\,\mathrm dt."),
        table([["方案", "1—5区/℃", "6区/℃", "7区/℃", "8—9区/℃", "速度/cm·min⁻¹"]] + [["Q3", *[f(value,3) for value in q3["settings"]], f(q3["speed_cm_min"],3)]]),
        text(f"找到的上升面积为{f(q3['metrics']['area_rising_above_217'],6)}℃·s，峰值时刻{f(q3['metrics']['peak_time'])}s，上升越过217℃时刻{f(q3['metrics']['t217_up'])}s。速度100 cm/min与8—9区265℃达到允许上界，峰值接近240℃下界。"),
        table([["制程指标", "要求", "问题3计算值"]] + [[name,limit,f(q3["metrics"][key],4)] for key,name,limit in metric_names]),
        text(r"不同起点得到的面积几乎一致，但前段温区组合不同。这不仅是搜索输出的观察：固定速度和辨识参数后，热驱动对四组设定温度呈仿射关系，一阶响应方程又是线性的。因此，用四个单位温升响应$b_j(x)$，可写成"),
        equation(r"T(x)=25+\sum_{j\in\{1,6,7,8\}}b_j(x)(T_j-25)."),
        text(r"第8区起点$x_e=273.5$ cm之后，热驱动只与后段设定$T_8$有关。因此固定$v,T_8$并保持入口温度$T(x_e)$，便由解的唯一性得到相同的后段曲线。前段温区满足以下线性补偿关系即可保持该入口状态："),
        equation(r"b_1(x_e)\Delta T_1+b_6(x_e)\Delta T_6+b_7(x_e)\Delta T_7=0,\qquad\Delta T_8=0."),
        text(f"取第1组温区改变±0.25℃、第7区不变，并补偿第6区，得到下表三组可行设置。三组均在第8区之后才上升越过217℃，因此本题面积目标所覆盖的曲线也相同。单位响应叠加与直接求解的最大差为{scientific(structural['q3_superposition']['max_error_c'])}℃；这里证明的是模型内等价方案的存在，不是问题三全局最优性。"),
        table([["1—5区/℃", "6区/℃", "入口温度/℃", "上升面积/℃·s", "保温时间/s"]] +
              [[f(row["settings"][0],4),f(row["settings"][1],4),f(row["entry_temperature_c"],6),f(row["area"],6),f(60+row["constraint_margins"][2],4)] for row in structural["q3_superposition"]["alternatives"]]),
        text("多起点一致性是搜索稳定性的证据，不是非线性优化的全局证书。题面所求最优曲线在本文中被明确解释为所选有效模型下找到的最佳可行数值解。")], level=2, key="q3")

    section("5.4 问题四：面积与对称性的权衡", [
        text(r"令$t_{\mathrm p}$为峰值时刻，$t_{\downarrow}$为下降至217℃的时刻。定义两侧比较范围$D$与超过217℃的温升$E(t)$："),
        equation(r"D=\max\{t_{\mathrm p}-t_{\uparrow},\;t_{\downarrow}-t_{\mathrm p}\},\qquad E(t)=\max\{T(t)-217,\;0\}."),
        text(r"采用归一化镜像温差平方积分$J$衡量不对称性。它无量纲，越小越对称；积分覆盖较长一侧，多出来的尾部不会被忽略。"),
        equation(r"J=\frac{\displaystyle\int_0^D\!\bigl[E(t_{\mathrm p}-u)-E(t_{\mathrm p}+u)\bigr]^2\,\mathrm du}{D\bigl[T(t_{\mathrm p})-217\bigr]^2}."),
        text(r"为了结合问题3而非单独追求对称，采用$\varepsilon$约束$A\le1.05A_{\mathrm{Q3}}$，再最小化$J$。5%是可更改的工程偏好，不是题面额外规定；改变容许面积上浮比例，应重新给出相应权衡解。"),
        table([["方案", "1—5区/℃", "6区/℃", "7区/℃", "8—9区/℃", "速度/cm·min⁻¹"]] + [["Q4", *[f(value,3) for value in q4["settings"]], f(q4["speed_cm_min"],3)]]),
        table([["方案", "上升面积/℃·s", "不对称性J", "回流时间/s", "峰值/℃"],
               ["Q3",f(q3["metrics"]["area_rising_above_217"]),f(q3["metrics"]["symmetry"],6),f(q3["metrics"]["time_above_217"]),f(q3["metrics"]["peak"])],
               ["Q4",f(q4["metrics"]["area_rising_above_217"]),f(q4["metrics"]["symmetry"],6),f(q4["metrics"]["time_above_217"]),f(q4["metrics"]["peak"])]]),
        text(f"问题4面积比问题3增加{f(area_change,2)}%，不对称性降低{f(symmetry_change,2)}%；面积上限{f(q4['area_cap'])}℃·s未用尽。最终升降温、保温、回流和峰值限制均以原始高精度参数检查。"),
        figure("optimization", "图5 三个决策工况的曲线，以及按峰值时刻对齐的Q3、Q4曲线。")], level=2, key="q4")

    section("5.4.1 面积约束与对称性权衡", [
        text("5%的面积上限只是先前声明的工程偏好，并非题面指定。为检验该选择是否影响决策，分别将问题三面积结果的0.1%、0.25%、0.5%、1%、2%、5%和10%作为允许增量，以同样的两个随机种子搜索并局部精修，再用独立连续积分复核各候选的面积、对称性与制程限制。放宽上限时保留此前可行解，避免新搜索退化被误解为权衡关系。"),
        table([["允许面积增量/%", "实际面积增量/%", "不对称性$J$", "速度/cm·min⁻¹"]] +
              [[f(row["allowed_area_increase_pct"],2),f(row["actual_area_increase_pct"],3),f(row["metrics"]["symmetry"],6),f(row["speed_cm_min"],3)] for row in decision["tradeoff"]]),
        text("面积上限较紧时，对称性改善随容许面积增加而逐步提升；从1%放宽至10%后，本次搜索得到的最佳指标已无实质改善，实际面积增加约0.66%。因此，至少在当前模型和搜索结果中，不需要耗尽5%的增量预算。若更强调面积，可选择0.5%这一较严格的候选；若更强调对称性，约1%的上限已容纳目前找到的最佳方案。"),
        text("表中0%行只列问题三既有可行解，并未在零松弛面上重新最小化对称性。其余各行也是多起点搜索得到的候选，而非经全局证明的Pareto前沿；不能据此断言不存在更优权衡。"),
        figure("decision_tradeoff", "图6 面积预算与对称性的数值权衡，以及名义方案和逐参数留余量方案在联合扰动下的越界计数。情景计数不表示实际风险概率。")],level=3)

    worst = max(independent["comparisons"], key=lambda row: row["error"] / row["tolerance"])
    section("六、模型检验与灵敏度分析", [
        text("独立程序未调用主模型的热驱动或递推函数，而是重新构造分段空间驱动，通过分段solve_ivp积分，连续求解阈值交点与峰值，并用自适应积分计算面积及对称性。两条路径共享的是已声明的数学模型与参数，不是程序输出；它们不构成第二次物理实验。"),
        text(f"共{len(independent['comparisons'])}项检查通过。容差按指标预先区分：指定位置与峰值0.005℃，阈值持续时间0.01s，上升面积0.1℃·s，对称性0.0001，速度0.002 cm/min等。占容差比例最大的检查为{worst['question']}的{worst['metric']}，误差{f(worst['error'],8)}、容差{worst['tolerance']}，未通过改写容差掩盖差异。"),
        text("对六个拟合时间/长度参数逐一±2%扰动，入口参数因触及原几何界限而不向界外扩大。该分析包含名义点共13个情景，不能替代联合扰动、相关参数不确定性或实物复测。"),
        table([["问题", "名义速度", "越界情景/13", "留余量速度", "备选面积/℃·s"]] + [[name, f(solution[name]["speed_cm_min"]), str(row["failed_scenarios"]), f(row["interior_suggestion"]["speed_cm_min"],1) if row["interior_suggestion"] else "未找到", f(row["interior_suggestion"]["nominal_metrics"]["area_rising_above_217"]) if row["interior_suggestion"] else "—"] for name,row in sensitivity["questions"].items()]),
        text("备选方案保持相应温区设定，仅降低速度，在所列情景下给制程指标保留余量。它们不是原目标的最优解，尤其Q4备选的面积可能超过前述5%偏好上限，应作为重新权衡的候选，而不能冒充原Q4答案。"),
    ])

    model_names={"mixing":"边界混合", "radiative":"辐射修正", "two_node":"双节点", "smooth_two_node":"平滑双节点", "zoned":"分区模型"}
    section("6.1 模型形式对速度决策的影响", [
        text("拟合更好不自动等于换工况后的预测更准。保留各候选在原实验上校准的参数，将问题二相同的温区设定及79.202 cm/min名义速度分别代入，再用0.1 cm/min网格搜索各自满足制程要求的最高速度。这样可直接观察模型选择对决策的影响，而不只比较拟合误差。"),
        table([["候选模型", "留出RMSE/℃", "名义峰值/℃", "最高速度/cm·min⁻¹"]] +
              [[model_names[row["model"]],f(row["selection_block_rmse_c"]),f(row["fixed_q2_peak_c"]),
                f(row["largest_feasible_grid_speed_cm_min"],1) if row["largest_feasible_grid_speed_cm_min"] is not None else "未找到"] for row in decision["alternative_models"]]),
        text("不同形式下可行速度的变化，说明优化结果对传热代理的选择具有依赖性。候选模型并非同等可信的真实系统，也不能把它们的结果范围当作置信区间。分区模型仍有最低的模型选择留出误差，但在获得新速度工况的实验数据前，其优势只支持当前样本内的相对选择，不能证实79.202 cm/min在实物上可直接采用。")],level=2)

    section("6.2 参数联合扰动与备选方案的适用范围", [
        text("进一步使用固定种子的256个Sobol设计点，使七个参数同时变化：五个时间常数及冷却特征长度在名义值±2%内变化，触及上界的入口延伸长度只从−2%变至名义值。该盒形范围是人为设定的压力情景，没有从单次实验中估计出联合概率分布，因此越界数量仅用于比较方案脆弱性。"),
        table([["问题", "方案", "速度/cm·min⁻¹", "制程越界数/256", "峰值范围/℃"]] +
              [[row["question"],"名义优化" if row["kind"]=="nominal_optimum" else "逐参数留余量",f(row["speed_cm_min"],3),str(row["process_violations"]),
                f(row["peak_range_c"][0],3)+"—"+f(row["peak_range_c"][1],3)] for row in decision["joint_scenarios"]["cases"]]),
        text("联合扰动下，原先逐参数检验通过的三组留余量方案仍出现越界，说明逐个参数变化的结论不能外推为同时变化时的保证。问题四备选方案还会在大量设计点中超过原5%的面积上限，故其用途仅是制程余量的局部参考，不满足对原优化目标的普遍保证。后续应以新增工况测量约束参数相关性，并重新进行有明确不确定集合的稳健优化。")],level=2)

    section("6.3 由反例驱动的情景约束工艺设计", [
        text("为回应上述越界反例，在相同参数变化范围内另建情景约束决策。设计集包含名义参数、七维盒形集合的128个顶点及32个内部Sobol点，共161组。要求所有设计情景均满足制程限制，并预留升降温速率0.005℃/s、各时间界限0.1s及峰值上下限0.02℃的数值余量。这些余量是显式设计选择，不是已测得的仪器误差。"),
        text(r"令$\mathcal S$为有限设计情景集合，$\boldsymbol u$为温区与速度控制。问题二保持指定温区不变并最大化速度；问题三最小化设计集中的最坏上升面积；问题四在新的面积上限内最小化最坏不对称性，可写为"),
        equation(r"\min_{\boldsymbol u,\eta_A}\eta_A,\quad A(\boldsymbol u,\boldsymbol\theta)\le\eta_A,\quad \boldsymbol\theta\in\mathcal S;"),
        equation(r"\min_{\boldsymbol u,\eta_J}\eta_J,\quad J(\boldsymbol u,\boldsymbol\theta)\le\eta_J,\quad A(\boldsymbol u,\boldsymbol\theta)\le1.05\eta_A^*,\quad\boldsymbol\theta\in\mathcal S."),
        text(r"两式均同时施加所有设计情景下的制程与控制约束。这里$\eta_A^*$指情景问题三找到的最坏面积，不是名义问题三的面积，故这是一组额外的风险折中方案，不能替代前文原题的名义解。采用多起点SLSQP进行局部求解；结果只能称为找到的情景可行候选。"),
        table([["情景方案","1—5区/℃","6区/℃","7区/℃","8—9区/℃","速度/cm·min⁻¹"]] +
              [[name,*[f(v,3) for v in scenario["candidates"][name]["controls"][:4]],f(scenario["candidates"][name]["controls"][4],3)] for name in ("Q2","Q3","Q4")]),
        text("在读入验证情景之前，将三组控制参数写入文件并冻结哈希。随后另用独立种子的512个Sobol点作留出验证，整个验证期间未修改控制参数。并对留出集中峰值下界或保温时间下界最不利的点进行独立连续ODE复算。"),
        table([["方案","留出越界数/512","名义面积/℃·s","设计最坏面积/℃·s","留出最坏面积/℃·s"]] +
              [[name,str(scenario["checks"][name]["process_violations"]),f(scenario["checks"][name]["nominal_metrics"]["area_rising_above_217"],2),f(scenario["candidates"][name]["design_worst_area"],2),f(scenario["checks"][name]["worst_area"],2)] for name in ("Q2","Q3","Q4")]),
        text(f"三组方案在512个留出情景中均未发生制程越界；情景Q4在新的面积上限{f(scenario['candidates']['Q4']['q4_area_cap'],2)}℃·s下也未越界。代价是相对名义最优值降低传送速度并增加面积，不能只展示零越界而隐去性能损失。原来的逐参数备选只通过逐个变化的检查，这里的结果对应更广的联合设计与留出检验，两者不应混为同一种保证。"),
        text("虽然设计集包含全部顶点，但各时间指标和面积对参数并不一定单调，顶点检查不能证明盒内所有点安全；512点留出也不能推出真实失败概率为零。这项验证仅证明有限设计集和固定留出集上的可行性，仍需考虑模型形式误差、新工况实验、控制精度及整体参数集合的进一步检验。")],level=2)

    section("七、模型评价与改进", [
        text("模型的优点在于：从题面几何与实验时间直接建立位置—时间关系，参数和控制变量含义明确；四问共用同一响应模型与制程指标，避免前后口径不一致；保留失败模型、多起点结果与独立计算路径，使拟合误差、数值误差和方案非唯一性均可检查。"),
        text("模型的局限及改进方向包括三点。第一，不同候选对速度决策给出不同判断，一条中心曲线不足以验证工况迁移，建议补充改变速度与高温平台的实验。第二，入口参数顶到边界及早期残差说明驱动形式有偏差，应增加炉口附近测点或实测空气场。第三，有限情景设计虽修复了所测联合扰动下的越界，但无法覆盖全部模型形式和参数不确定性；新增实验后应更新不确定集合并重新设计。")])

    section("八、结论", [
        text("本文完成四问所需的温度预测、速度边界、上升回流面积和对称性方案，并给出原始计算产物、独立复核与情景分析。结论的适用范围始终限定在明确的有效传热模型与输入数据；拟合良好和两套算法一致都不能替代新工况实验。"),
        text(f"给定工况下的四个位置温度分别为" + "、".join(f(point["temperature_c"]) for point in q1["locations"].values()) + f"℃；问题二最大速度约{f(q2['speed_cm_min'])} cm/min；问题三最佳可行面积为{f(q3['metrics']['area_rising_above_217'])}℃·s；问题四在所声明权衡下，以{f(area_change,2)}%的面积增加换取{f(symmetry_change,2)}%的不对称性下降。")])
    section("AI工具使用声明", [text("本训练稿使用了AI工具，主要用于题意分析、程序实现、数值复核与文字排版。真实参赛队对核心内容的逐项人工审查、AI详情记录及正式提交审核尚未完成；本稿不作为已经审核合格的正式参赛作品。")])
    section("参考文献", [text("[1] 全国大学生数学建模竞赛组委会. 2020年高教社杯全国大学生数学建模竞赛A题：炉温曲线及附件[Z]. 2020. 使用用户提供的原始题面与实验数据。")])
    section("附录", [
        text("附录A列出训练程序和主要输出，复现入口为run_all.py，输入读取冻结sources目录，源码与依赖声明随项目提供。正式提交前还须按当年要求补齐完整源码附录与AI工具使用详情。"),
        table([["文件", "作用"], ["model.py / calibrate.py", "温度模型与实验参数校准"], ["solve.py", "四问求解与0.5秒结果输出"],
               ["independent.py", "连续ODE、求根与自适应积分复核"], ["sensitivity.py", "参数情景与留余量方案"],
               ["plots.py / paper.py", "由计算产物生成图表和论文内容"], ["run_all.py", "全流程回放入口"], ["result.csv", "问题一671条温度采样输出"]]),
    ], page=True)
    paper = {"title": "基于分区有效传热与独立复核的回焊炉工艺优化",
             "status": "TRAINING_DRAFT",
             "sections": sections}
    write_json(run / "paper/document.json", paper)
    print({"sections": len(sections), "paragraph_characters": sum(len(block.get("text", "")) for section in sections for block in section["blocks"])})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    compose(parser.parse_args().run)
