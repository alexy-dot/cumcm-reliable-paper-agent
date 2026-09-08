"""Compose the complete training paper from computed artifacts, without manual numbers."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skill/cumcm-reliable-paper/scripts"))
from engine import read_json, write_json


def compose(run):
    solution = read_json(run / "artifacts/solution.json")
    calibration = read_json(run / "artifacts/calibration.json")
    independent = read_json(run / "artifacts/independent_comparison.json")
    reference = read_json(run / "artifacts/independent_solution.json")
    sensitivity = read_json(run / "artifacts/sensitivity.json")
    selected = calibration["models"]["zoned"]
    q1, q2, q3, q4 = [solution[name] for name in ["Q1", "Q2", "Q3", "Q4"]]
    f = lambda value, n=3: f"{value:.{n}f}"
    text = lambda value: {"text": value}
    table = lambda rows: {"table": rows}
    figure = lambda filename, caption: {"image": "artifacts/figures/" + filename + ".png", "caption": caption}
    sections = []
    def section(title, blocks, page=False):
        sections.append({"title": title, "blocks": blocks, "page_break_before": page and title.startswith("1 ")})

    area_change = (q4["metrics"]["area_rising_above_217"] / q3["metrics"]["area_rising_above_217"] - 1) * 100
    symmetry_change = (1 - q4["metrics"]["symmetry"] / q3["metrics"]["symmetry"]) * 100
    section("摘要", [
        text("回焊炉工艺调整需要同时控制升降温速率、保温与回流时间及峰值温度。本文依据题面几何尺寸和一条实测炉温曲线，建立机理启发的分区有效传热模型，用固定空间热驱动与一阶热惯性描述焊接中心响应，研究给定工况预测、最大过炉速度、回流前段面积及对称性优化。"),
        text(f"对附件{calibration['n']}个观测值保留原始计时起点，比较单时间常数、边界混合、辐射修正与双节点等候选模型。选定分区模型的全样本均方根误差为{f(selected['rmse'])}℃，留出时间块误差为{f(selected['held_block_rmse'])}℃；该留出只用于模型选择，不能代替不同工况实验。"),
        text("问题1在指定78 cm/min下计算完整温度曲线，四个指定位置温度依次为" + "、".join(f(point["temperature_c"]) for point in q1["locations"].values()) + f"℃，并生成{q1['sample_count']}个间隔0.5 s的CSV数据点。"),
        text(f"问题2在固定温区设定下得到模型允许最大速度约{f(q2['speed_cm_min'])} cm/min，峰值温度下限为活动约束。问题3用差分进化与多起点约束优化，找到上升回流面积为{f(q3['metrics']['area_rising_above_217'])}℃·s的可行解，速度{f(q3['speed_cm_min'])} cm/min；多组前段温区参数具有近乎相同目标值，不宣称参数唯一或已获全局最优证明。"),
        text(f"问题4以归一化镜像温差平方积分衡量不对称性，在问题3面积上浮不超过5%的约束下，得到面积{f(q4['metrics']['area_rising_above_217'])}℃·s、对称性指标{f(q4['metrics']['symmetry'],6)}；相较问题3，面积增加{f(area_change,2)}%，不对称性下降{f(symmetry_change,2)}%。"),
        text(f"另用独立编写的连续ODE、求根和自适应积分复算，{len(independent['comparisons'])}项数值一致性检查通过。参数扰动显示名义最优解贴近约束边界，必须区分模型内最优与实际生产可靠性，并报告留有余量的备选运行速度。"),
        text("关键词：回焊炉；有效传热；参数辨识；约束优化；独立数值复核")])

    section("1 问题理解、数据与计算口径", [
        text("题面给出11个小温区，单区长度30.5 cm，相邻间隙5 cm，炉前与炉后各25 cm。因此总行程为25+11×30.5+10×5+25=435.5 cm，第i区起点为25+(i−1)×35.5 cm。传送速度v以cm/min给出，内部统一为v/60 cm/s，位置与时间关系为x=vt/60。"),
        text(f"附件只有一条温度响应曲线，共{calibration['n']}点，记录从{f(calibration['record_start_seconds'],1)} s开始至{f(calibration['record_end_seconds'],1)} s结束。传感器达到30℃才开始记录，不能将第一条记录重置为t=0。模型从进炉瞬间T(0)=25℃开始推进，拟合时再对齐实际观测时刻。全量读取未发现空单元格、重复行或非有限数。"),
        table([["问题", "输入", "必须交付", "关键口径"],
               ["1", "173/198/230/257℃，78 cm/min", "曲线、4个位置温度、result.csv", "每0.5秒；冷却区设定25℃"],
               ["2", "182/203/237/254℃", "允许的最大速度", "所有制程约束同时成立"],
               ["3", "各温区±10℃；65≤v≤100", "温区、速度、上升回流面积", "只积分上升217℃至峰值"],
               ["4", "问题3约束与对称性偏好", "曲线与明确指标", "面积与对称性的权衡须声明"]]),
        text("问题3、4的四组温区决策范围分别为[165,185]、[185,205]、[225,245]、[245,265]℃。1—5区同温，8—9区同温，10—11区控制设定维持25℃。只对题目允许的四组设定与速度优化。"),
        text("150—190℃持续时间只统计上升过程；217℃以上持续时间包括上升和下降两段；面积指标以217℃水平线为基线且止于峰值。所有表格为显示精度，复算使用JSON中的完整数值。")], True)

    section("2 有效传热模型与假设", [
        text("焊接区域厚度仅0.15 mm，但题面未给材料密度、比热、导热系数及对流参数，不能直接计算Biot数或唯一反推出物性。将中心响应近似为分区热惯性，质量、比热、有效换热面积等并入时间常数τ。该模型用于有限邻域内的工况推断，不能把拟合参数当作独立测量的物性。"),
        text("由能量收支的集中参数形式得到：dT/dt = [U(x)−T]/τ_g，x=vt/60，T(0)=25℃。其中U是等效热驱动，τ_g单位为秒；g按位置依次在200、235.5、271、342 cm处分段。分区允许不同对流与接触条件形成不同有效速率。"),
        text("加热平台的U取相应温区设定，温区间5 cm间隙作线性过渡。炉口采用光滑入口函数：U=25+(T_1−25)(3s²−2s³)，s=min{x/(25+w),1}，0≤w≤30.5 cm；它表示炉口与第一小温区边界效应，而非把记录起点人为后移。"),
        text("冷却前边界位置为339.5 cm，采用U=25+(T_8−25)exp[−(x−339.5)/L]表示热惯性与非理想边界合并后的等效驱动。该变量不直接等同冷却区控制测点的空气温度，也不改变冷却区设定25℃。从单条中心温度曲线，驱动场与换热速率存在混淆；L的迁移是本模型的重要假设。"),
        table([["假设", "依据与用途", "可能失效的情形"],
               ["恒速与稳定炉况", "题面明确，可用位置代表热环境", "启动阶段或速度波动"],
               ["中心可用有效一阶响应描述", "薄焊接区，参数通过实测校准", "层间温差、相变或结构改变"],
               ["邻近设定下参数保持", "题目调整范围有限", "气流与辐射改变导致系数变化"],
               ["等效驱动可按空间迁移", "炉内稳态边界的近似", "冷却段实际机理与拟合形式不符"]]),
        text("数值计算将空间等分，使用每段中点热驱动和精确指数状态更新：T_(n+1)=U_n+(T_n−U_n)exp(−Δt/τ_g)。该更新对分段常驱动精确；连续驱动的离散误差通过缩小网格与独立连续积分检验。校准网格0.1 cm，搜索0.25 cm，最终指标复算至0.05 cm或更细。")])

    names = {"baseline":"单常数", "mixing":"边界混合", "radiative":"辐射修正", "two_node":"双节点", "smooth_two_node":"平滑双节点", "zoned":"分区有效模型"}
    section("3 校准、模型选择与可辨识性", [
        text("采用有界非线性最小二乘。先按时间分块留出若干连续区间，以其余数据拟合并评估留出块误差，再用全部观测校准用于四问的参数。尝试多个候选形式是针对残差结构的修正过程，留出块已参与模型选择，因此其误差不能称为最终独立测试误差。"),
        table([["模型", "参数数", "全样本RMSE/℃", "留出块RMSE/℃"]] + [[names[name], len(row["parameters"]), f(row["rmse"]), f(row["held_block_rmse"])] for name,row in calibration["models"].items()]),
        figure("model_comparison", "图1 候选模型比较。复杂模型并非必然优于简单模型；保留失败候选。"),
        text("选定模型参数为：" + "；".join(f"{name}={f(value,5)}" for name,value in zip(["τ1—5", "τ6", "τ7", "τ8—9", "τ冷却", "w", "L"], solution["parameters"])) + "。前五项单位为s，后两项为cm。"),
        text(f"全样本RMSE为{f(selected['rmse'])}℃，最大绝对残差{f(selected['max_abs_error'])}℃。留出块包含{selected['held_count']}点，训练部分{selected['train_count']}点。入口参数w触及上界，表明该边界形式仍不足以完全解释炉口响应；需要保留模型形式误差。"),
        figure("calibration", "图2 选定模型与实测曲线及残差。初始记录从19秒开始，不把未观测区当作实测数据。"),
        text("Jacobian条件数与近似参数标准误仅作数值诊断。残差具有时间相关性，不能将独立同分布误差公式生成的标准误当作可靠置信区间。只有一条物理实验曲线，也无法严格区分驱动场误差和换热系数变化；需新增速度或温区扰动实验来检验参数迁移。")])

    section("4 问题1：指定工况的曲线与四个温度", [
        text("将指定的四组温区温度与78 cm/min代入，不重新拟合参数。位置由题面几何直接计算，再以x/(78/60)换算时间，避免以数组下标或温区编号直接当作时刻。"),
        table([["位置", "距入口/cm", "进炉后时间/s", "中心温度/℃"]] + [[label, f(point["x_cm"],2), f(point["time_seconds"]), f(point["temperature_c"])] for label,point in zip(["第3区中点", "第6区中点", "第7区中点", "第8区结束"], q1["locations"].values())]),
        figure("q1", "图3 问题1炉温曲线与指定位置。"),
        text(f"result.csv按0.5秒间隔从0秒输出至模型行程终点，共{q1['sample_count']}条温度记录；文件使用UTF-8 BOM以便常用表格软件读取。计算覆盖整个435.5 cm行程。"),
        text(f"该指定工况的模型峰值约{f(reference['Q1']['metrics']['peak'])}℃。问题1要求预测指定设置，并不允许为了使结果满足制程界限而改写给定温区温度或速度。")], True)

    metric_names = [("max_rise", "最大升温速率", "≤3℃/s"), ("max_cooling", "最大降温速率绝对值", "≤3℃/s"),
                    ("soak_150_190", "上升150—190℃时间", "60—120s"), ("time_above_217", "高于217℃总时间", "40—90s"), ("peak", "峰值", "240—250℃")]
    section("5 问题2：固定温区下的最大速度", [
        text("固定182、203、237、254℃，在65—100 cm/min内以0.1 cm/min间隔检查全部制程限制，定位最高可行区间，再对活动边界求根。独立程序从连续ODE和峰值条件重新求根，核对速度。有限网格不能形式证明不存在极窄的漏检可行岛，结果为当前模型与搜索范围下的数值边界。"),
        text(f"主算法边界速度为{f(q2['speed_cm_min'],6)} cm/min；独立连续积分求得{f(reference['Q2']['speed_cm_min'],6)} cm/min。活动约束是峰值降至240℃，其余指标保有名义余量。"),
        table([["制程指标", "要求", "问题2计算值"]] + [[name,limit,f(q2["metrics"][key],4)] for key,name,limit in metric_names]),
        text("精确数值边界附近，模型误差、计算容差及控制分辨率都会影响合格判定。不能将显示为240.000℃理解为实物温度精确等于240℃；下文另给参数情景下的留余量方案。")])

    section("6 问题3：最小化上升回流面积", [
        text("目标为A=∫[t_up, t_peak] (T(t)−217)dt，单位℃·s。所有温区、速度范围与制程限制均保留。采用差分进化搜索并以SLSQP精修，不把惩罚较小但仍不可行的点作为答案；最终用更细网格和独立自适应积分复核。"),
        table([["方案", "1—5区/℃", "6区/℃", "7区/℃", "8—9区/℃", "速度/cm·min⁻¹"]] + [["Q3", *[f(value,3) for value in q3["settings"]], f(q3["speed_cm_min"],3)]]),
        text(f"找到的上升面积为{f(q3['metrics']['area_rising_above_217'],6)}℃·s，峰值时刻{f(q3['metrics']['peak_time'])}s，上升越过217℃时刻{f(q3['metrics']['t217_up'])}s。速度100 cm/min与8—9区265℃达到允许上界，峰值接近240℃下界。"),
        table([["制程指标", "要求", "问题3计算值"]] + [[name,limit,f(q3["metrics"][key],4)] for key,name,limit in metric_names]),
        text("不同起点得到的最优面积几乎一致，但前段温区组合不同。后段回流过程主要受进入高温平台时的状态、平台温度和速度控制，前段参数可在满足保温时间的条件下互相补偿。因此应交付一组可行代表及替代解，不宣称该设定唯一。"),
        table([["代表起点", "1—5区/℃", "6区/℃", "7区/℃", "面积/℃·s"]] + [[str(row["seed"]), *[f(value,3) for value in row["settings_speed"][:3]], f(row["objective"]*1000,6)] for row in q3["attempts"][:3]]),
        text("多起点一致性是搜索稳定性的证据，不是非线性优化的全局证书。题面所求最优曲线在本文中被明确解释为所选有效模型下找到的最佳可行数值解。")], True)

    section("7 问题4：面积与对称性的可解释权衡", [
        text("令t_p为峰值时刻，D=max(t_p−t_up,t_down−t_p)，E(t)=max(T(t)−217,0)。定义J=∫[0,D](E(t_p−u)−E(t_p+u))²du / [D(T_peak−217)²]。J无量纲，越小越对称；积分覆盖较长一侧，多出来的尾部不会被忽略。"),
        text("为了结合问题3而非单独追求对称，预先声明采用ε约束：A≤1.05A_Q3，再最小化J。5%是可更改的工程偏好，不是题面额外规定；改变容许面积上浮比例，应重新给出相应权衡解。"),
        table([["方案", "1—5区/℃", "6区/℃", "7区/℃", "8—9区/℃", "速度/cm·min⁻¹"]] + [["Q4", *[f(value,3) for value in q4["settings"]], f(q4["speed_cm_min"],3)]]),
        table([["方案", "上升面积/℃·s", "不对称性J", "高于217℃时间/s", "峰值/℃"],
               ["Q3",f(q3["metrics"]["area_rising_above_217"]),f(q3["metrics"]["symmetry"],6),f(q3["metrics"]["time_above_217"]),f(q3["metrics"]["peak"])],
               ["Q4",f(q4["metrics"]["area_rising_above_217"]),f(q4["metrics"]["symmetry"],6),f(q4["metrics"]["time_above_217"]),f(q4["metrics"]["peak"])]]),
        text(f"问题4面积比问题3增加{f(area_change,2)}%，不对称性降低{f(symmetry_change,2)}%；面积上限{f(q4['area_cap'])}℃·s未用尽。最终升降温、保温、回流和峰值限制均以原始高精度参数检查。"),
        figure("optimization", "图4 三个决策工况的曲线，以及按峰值时刻对齐的Q3、Q4曲线。")])

    worst = max(independent["comparisons"], key=lambda row: row["error"] / row["tolerance"])
    section("8 数值复核、扰动与实际使用限制", [
        text("独立程序未调用主模型的热驱动或递推函数，而是重新构造分段空间驱动，通过分段solve_ivp积分，连续求解阈值交点与峰值，并用自适应积分计算面积及对称性。两条路径共享的是已声明的数学模型与参数，不是程序输出；它们不构成第二次物理实验。"),
        text(f"共{len(independent['comparisons'])}项检查通过。容差按指标预先区分：指定位置与峰值0.005℃，阈值持续时间0.01s，上升面积0.1℃·s，对称性0.0001，速度0.002 cm/min等。占容差比例最大的检查为{worst['question']}的{worst['metric']}，误差{f(worst['error'],8)}、容差{worst['tolerance']}，未通过改写容差掩盖差异。"),
        text("对六个拟合时间/长度参数逐一±2%扰动，入口参数因触及原几何界限而不向界外扩大。该分析包含名义点共13个情景，不能替代联合扰动、相关参数不确定性或实物复测。"),
        table([["问题", "名义速度", "越界情景/13", "留余量速度", "备选面积/℃·s"]] + [[name, f(solution[name]["speed_cm_min"]), str(row["failed_scenarios"]), f(row["interior_suggestion"]["speed_cm_min"],1) if row["interior_suggestion"] else "未找到", f(row["interior_suggestion"]["nominal_metrics"]["area_rising_above_217"]) if row["interior_suggestion"] else "—"] for name,row in sensitivity["questions"].items()]),
        text("备选方案保持相应温区设定，仅降低速度，在所列情景下给制程指标保留余量。它们不是原目标的最优解，尤其Q4备选的面积可能超过前述5%偏好上限，应作为重新权衡的候选，而不能冒充原Q4答案。"),
        text("主要限制有三项。第一，一条中心曲线不足以验证其他速度、温区和板材下的迁移；建议补充至少一条改变速度与一条改变高温平台的独立实验。第二，入口参数顶到边界及早期残差说明驱动形式有偏差；应增加炉口附近测点或实测空气场。第三，搜索结果是条件数值最优，且峰值贴下界；生产前应按测温误差、控制分辨率及工艺风险重新设置余量。")], True)

    section("9 结论与复现说明", [
        text("本文完成四问所需的温度预测、速度边界、上升回流面积和对称性方案，并给出原始计算产物、独立复核与情景分析。结论的适用范围始终限定在明确的有效传热模型与输入数据；拟合良好和两套算法一致都不能替代新工况实验。"),
        text("复现依次执行prepare.py、calibrate.py、solve.py、independent.py、sensitivity.py、plots.py与paper.py，最后用Skill中的render_paper.py排版。所有输入从冻结sources目录读取；result.csv位于artifacts。复现脚本和依赖版本随仓库提供，不分发原始竞赛附件。"),
        text("AI使用说明：本训练稿的题意分析、程序、数值检验与文字由AI辅助完成；真实团队复核、当年度AI申报与正式提交格式审核尚未完成。本次计时为项目内首次实测，不能排除基础模型预训练曾见过公开题目，不能据此声称严格未知题认证或国奖保证。"),
        text("参考资料：[1] 全国大学生数学建模竞赛组委会. 2020年高教社杯全国大学生数学建模竞赛A题：炉温曲线及附件. 用户提供的原始题面与实验数据。本文能量收支、阈值和目标函数均在正文定义，未添加无法核实的引文。")])
    paper = {"title": "基于分区有效传热与独立复核的回焊炉工艺优化",
             "status_note": "2020 A题项目内训练稿｜名义计算已复核，真实人工评阅与正式提交审核待完成",
             "sections": sections}
    write_json(run / "paper/document.json", paper)
    print({"sections": len(sections), "paragraph_characters": sum(len(block.get("text", "")) for section in sections for block in section["blocks"])})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    compose(parser.parse_args().run)
