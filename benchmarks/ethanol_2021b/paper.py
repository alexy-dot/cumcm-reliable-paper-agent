"""Compose a source-backed four-question statistical training manuscript."""
import argparse
from pathlib import Path
from prepare import read_json,write_json,sha256_file
from split_sensitivity import checked_report
from verify_linear_models import checked_report as checked_linear_report


def compose(run):
    data=read_json(run/"artifacts/observations.json");statistics=read_json(run/"artifacts/statistical_results.json")
    decision=read_json(run/"artifacts/decisions.json");check=read_json(run/"artifacts/independent_statistics.json")
    partitions=checked_report(run)
    linear=checked_linear_report(run)
    if not check["passed"] or check["results_sha256"]!=sha256_file(run/"artifacts/statistical_results.json") or check["decisions_sha256"]!=sha256_file(run/"artifacts/decisions.json"):
        raise ValueError("statistical or decision evidence is stale")
    sections=[];text=lambda s:{"text":s};eq=lambda s:{"equation":s};table=lambda rows:{"table":rows}
    def section(title,blocks,level=1,page=False):sections.append({"title":title,"blocks":blocks,"level":level,"page_break_before":page})
    names={"conversion_pct":"转化率","selectivity_pct":"C4选择性","yield_pct":"C4收率"}
    methods={"training_mean":"训练均值","temperature_only":"仅温度二次式","ridge":"岭回归内层选择","random_forest":"随机森林内层选择","nested_selection":"跨模型嵌套选择"}
    observed=decision["observed_best"];low=decision["observed_below_350_best"]
    stability=decision["stability"]["summary"]
    m=statistics["targets"]["selectivity_pct"]["models"]
    section("摘要",[
        text("针对乙醇偶合制备C4烯烃的实验分析与工艺选择问题，本文以21种催化剂组合的114条观测及一次稳定性实验的7个时点为依据，分别建立组合内温度关系、组合外预测比较、观测域候选决策与五次补充实验设计。将同一催化剂组合整体留出，避免同组温度观测跨训练和验证集。"),
        {"lead":"针对问题一：","text":f"逐组比较一次、二次温度多项式，用留一误差选择阶数并列出全部系数。350℃单次实验中，转化率由{stability['conversion_pct']['first']:.4f}%降至{stability['conversion_pct']['last']:.4f}%，相对变化{stability['conversion_pct']['relative_change_pct']:.2f}%；C4选择性变异系数为{stability['selectivity_pct']['cv_pct']:.2f}%，其时间变化小于转化率。"},
        {"lead":"针对问题二：","text":f"在相同的五折组合外验证中比较训练集均值、仅温度模型、岭回归和随机森林，超参数由内层分组验证选择。C4选择性的按组等权RMSE依次为{m['training_mean']['metrics']['group_rmse']:.3f}、{m['temperature_only']['metrics']['group_rmse']:.3f}、{m['ridge']['metrics']['group_rmse']:.3f}和{m['random_forest']['metrics']['group_rmse']:.3f}个百分点。随机森林并未在所有响应上优于简单模型，19组单因素匹配对照也显示效应随工况变化。"},
        {"lead":"针对问题三：","text":f"最高实测收率为{observed['group']}在{observed['temperature_c']}℃的{observed['yield_pct']:.4f}%；严格低于350℃时，最高已测点为{low['group']}在{low['temperature_c']}℃的{low['yield_pct']:.4f}%。A2局部多项式在低温开放区间只有趋近350℃的上确界，不能把某一网格终点称为连续最大值。"},
        {"lead":"针对问题四：","text":"提出两次A3/400℃重复、一次A3/425℃补点，以及A2/349℃与A2/325℃两次低温比较。若重复性不能满足实验室预先规定的标准，将剩余名额改为重复或对照，总数仍不超过五次。"},
        text("独立按原始表格与标量运算核对收率、观测候选及30项预测误差。各模型反映当前设计下的关联和预测能力，不能由此认定单个因素的因果效应，亦不能保证未测配方或新批次的全局最优。"),
        text("关键词：乙醇偶合；分组交叉验证；岭回归；随机森林；开放区间优化")])
    section("一、问题重述",[],page=True)
    section("1.1 背景与数据条件",[
        text("乙醇偶合可用于制备C4烯烃，工艺表现受到Co负载量、Co/SiO2与HAP装料、乙醇进料及温度等条件的影响。附件1记录多种催化剂组合在不同温度下的转化率和各产物选择性，其中A1—A14采用装料方式I，B1—B7采用方式II。附件2为350℃下给定某种组合在一次实验不同反应时间的测量[1]。"),
        text("题目以乙醇转化率与C4烯烃选择性的乘积定义收率。原表用0—100的百分数存储，因此计算百分数收率时需除以100。题面未给附件1的重复实验误差、批次及各温度测量对应的反应时间，也未给温度控制最小步长。")],2)
    section("1.2 逐问要求",[
        {"lead":"问题一：","text":"分别研究各催化剂组合的转化率、C4选择性与温度关系，并分析附件2的时间变化。"},
        {"lead":"问题二：","text":"探讨催化剂组合及温度对转化率和C4选择性的影响。"},
        {"lead":"问题三：","text":"选择催化剂组合与温度，使收率尽可能高；另研究温度严格低于350℃的情况。"},
        {"lead":"问题四：","text":"在最多增加五次实验的条件下，给出实验方案和详细理由。"}],2)
    section("二、问题分析",[])
    section("2.1 问题一的分析",[text("每组只有5—7个温度点，直接采用高阶多项式会增加端点振荡与过拟合风险。先逐组描述变化，再比较低阶模型，用交叉验证选择阶数。附件2是同一次实验的时间轨迹，不能把7个时点当成7次独立重复，也不能仅凭选择性相对平稳就判断整体产率稳定。")],2)
    section("2.2 问题二的分析",[text("数据不是完整析因随机实验，配方变量往往同时改变。预测时若随机拆分温度记录，同一配方可能同时进入训练与测试，不能反映新组合预测。采用整组留出，先问加入配方信息是否优于仅温度模型，再通过其他记录条件相同的配方对照说明可观察的差异。质量、总质量与比例具有代数依赖，不能逐列任意置换后解释成独立物理效应。")],2)
    section("2.3 问题三的分析",[text("需要区分已测点的最好记录、插值模型的最佳候选与未测域的化学最优。单次最高点缺乏重复性信息，模型在端点上升也不证明应持续提高温度。低温限制是严格不等式，若模型在350℃前仍上升，数学上可能只有上确界；实际候选必须结合控制分辨率及实验确认。")],2)
    section("2.4 问题四的分析",[text("新增实验应优先解决能够改变工艺选择的不确定性：最高观测能否重复、400—450℃之间是否存在更好点、低温边界附近能否保持优势。五次预算需要包含所有重复和补测；若重复性检查失败，后续名额应重新分配，不能额外无限增加实验。")],2)
    section("三、模型假设",[
        text("1．使用附件给定的温度、质量和百分数作为观测值，不人为补造误差分布；空白组合标签仅在原合并单元格范围内继承。"),
        text("2．以催化剂组合为预测验证的分组单位。不同组间未知的批次关联仍可能影响外推，因此组合外验证不等于新实验室或新催化剂批次验证。"),
        text("3．组内低阶多项式仅作实测温区内的经验关系，不代表已识别的反应动力学，其系数与留一误差按原始拟合值报告。组合外预测采用提前固定的0—100物理截断，同时保留未经截断的误差和越界数量。"),
        text("4．匹配对照只控制附件中记载的配方与温度，未观测因素仍可能混杂。A11同时改变HAP与石英砂，不能从这一组单独分离两者作用。"),
        text("5．349℃只是在假定1℃控制分辨率下的可执行示例，不将该分辨率添加为原题条件；重复性阈值须由实验室在新观测前确定。")])
    section("四、符号说明",[table([["符号","含义","单位"],["$T$","反应温度","℃"],["$X,S,Y$","转化率、C4选择性与收率","%"],["$g,G$","组合编号、组合总数","无量纲"],[r"$\mu_g,\sigma_g$","组内温度中心与尺度","℃"],["$a_2,a_1,a_0$","温度多项式系数","响应百分数"],[r"$\alpha$","岭回归惩罚系数","标准化后参数"],["$E_g$","第g组预测均方误差","百分点平方"]])])
    section("五、模型建立与求解",[])
    section("5.1 问题一：逐组温度关系与单次稳定性",[
        text("附件1核对得到114条观测、21种组合，各生成物选择性之和在记录精度内为100%。按配方说明解析Co/SiO2、HAP及石英砂质量、Co负载、进料和装料方式，原有质量与比例的重复表达不同时用作本次全局模型的输入。"),
        eq(r"Y=\frac{XS}{100},\qquad z_g=\frac{T-\mu_g}{\sigma_g},\qquad \widehat f_g(T)=a_2z_g^2+a_1z_g+a_0."),
        text("每组分别对X和S拟合一次与二次模型，以逐温度点留一RMSE较小者作为描述模型。一次模型记a2=0。以下列出全部21组的系数，足以在各组实测温区内重建曲线；留一误差参与了模型选择，因此不是选好阶数后另行获得的独立测试误差。")],2)
    for response,label in [("conversion_pct","转化率"),("selectivity_pct","C4选择性")]:
        for start in range(0,21,7):
            data_rows=[]
            for row in decision["local_models"][start:start+7]:
                model=row["response_models"][response];coeff=([0.]+model["coefficients"]) if model["degree"]==1 else model["coefficients"]
                data_rows.append([row["group"],f"{model['center']:.2f}",f"{model['scale']:.3f}",*[f"{v:.4f}" for v in coeff],f"{model['selection_loocv_rmse']:.3f}"])
            section(f"{label}温度方程：第{start+1}—{start+7}组",[table([["组合",r"$\mu_g$",r"$\sigma_g$","$a_2$","$a_1$","$a_0$","留一RMSE"]]+data_rows)],3)
    section("5.1.1 关系方向与稳定性",[
        text("以Spearman秩相关作描述：转化率与温度相关系数严格大于0.9的组合有"+str(sum(r["conversion_pct_spearman"]>.9 for r in statistics["group_relations"]))+"组，C4选择性对应有"+str(sum(r["selectivity_pct_spearman"]>.9 for r in statistics["group_relations"]))+"组。该计数表示样本内单调程度，不是显著性检验，也不说明每一温度段都持续上升。"),
        table([["响应","起始/%","末次/%","相对变化/%","全程变异系数/%"]]+[[names[name],f"{s['first']:.4f}",f"{s['last']:.4f}",f"{s['relative_change_pct']:.2f}",f"{s['cv_pct']:.2f}"] for name,s in stability.items()]),
        text("转化率和收率随反应时间下降，而C4选择性相对平稳，说明至少在这一次实验中，产率衰减主要伴随转化率变化。由于没有独立重复和催化剂状态测量，不能据此确定失活机制或推导可靠的重复实验方差。")],3)
    section("5.2 问题二：公平基线与组合外预测",[
        text("将21个组合分为五个外层折，同组全部温度点放在同一折。每个外层训练集中再作四折分组验证选择超参数；外层测试响应不参与标准化、拟合或选择。拟合按记录等权，选择与主要报告按组合等权，避免拥有7条记录的组合比5条记录的组合获得更多评价权重。"),
        eq(r"E_g=\frac1{n_g}\sum_{i\in g}(y_i-\widehat y_i)^2,\qquad \mathrm{RMSE}_{\mathrm{group}}=\sqrt{\frac1G\sum_{g=1}^G E_g}."),
        text("比较的基线是每折训练响应均值，以及仅用温度的二次回归。多变量岭回归比较一次/二次特征及惩罚1、10、100，特征标准化只在训练部分拟合；随机森林使用200棵树，比较叶节点最少2或4条记录，固定种子20210904。输入仅保留温度和六个原始配方描述，不同时加入总质量及比例。"),
        eq(r"\widehat\beta=\arg\min_\beta\left\{\sum_{i\in\mathrm{train}}(y_i-\beta_0-\phi(x_i)^\mathsf T\beta)^2+\alpha\lVert\beta\rVert_2^2\right\}."),
        text("除分别比较模型家族外，还将均值、仅温度、各岭回归和森林候选放进同一个内层选择集合，得到“跨模型嵌套选择”的外层预测。它评价的是选择流程本身，不能先用外层结果挑选最佳家族，再把同一误差当作这个后选模型的无偏成绩。"),
        table([["方法","转化率RMSE","C4选择性RMSE","收率RMSE"]]+[[label,*[f"{statistics['targets'][target]['models'][name]['metrics']['group_rmse']:.3f}" for target in names]] for name,label in methods.items()]),
        {"image":"artifacts/figures/grouped_prediction.pdf","caption":"图1 同一外层分组划分下的预测误差。单位为百分点，数值越小越好。"},
        text("在本次划分中，森林在转化率和收率上较好，选择性则由岭回归取得更低误差。跨模型选择流程没有总能选到外层表现最好的家族，这提示小样本模型选择仍不稳定；不能把一次排序升级成对所有催化剂数据的算法排名。全部逐行预测、折索引、内层候选分数、原始未截断误差均保留在计算记录中。")],2)
    section("5.2.1 配方对照与解释边界",[
        text("为回答因素影响，枚举只在一个记录特征上不同的组合对，在共同温度点逐一相减；下表是较大特征值组合减去较小值组合的平均差，单位百分点。其他记录条件虽然一致，批次、老化及顺序信息仍未知，故这些是受条件约束的描述对照。"),
        table([["组合对","变化因素","由→至","转化率均差","选择性均差"]]+[[p["from_group"]+"/"+p["to_group"],{"co_loading_pct":"Co负载","feed_ml_min":"进料","mode_II":"装料方式","co_mass_mg":"Co/SiO2质量","hap_mass_mg":"HAP质量","quartz_mass_mg":"石英砂质量"}[p["changed_feature"]],f"{p['from_value']:g}→{p['to_value']:g}",f"{p['mean_differences']['conversion_pct']:.3f}",f"{p['mean_differences']['selectivity_pct']:.3f}"] for p in decision["matched_contrasts"]]),
        text("A12/B1与A9/B5两组方式I→II对照的选择性变化方向不同，不能笼统宣布某一种装料方式总是更好。模型解释另采用整块配方描述在外层留出组合间的联合交换，保留一组配方内部的质量关系与模式标签。其误差变化只说明模型对整个配方块的预测依赖；温度与新配方的组合可能尚未测量，也不能解释为单因素因果效应。")],3)
    section("5.3 问题三：观测候选与严格低温边界",[
        table([["范围","组合","温度/℃","转化率/%","选择性/%","观测收率/%"]]+[[label,row["group"],str(row["temperature_c"]),f"{row['conversion_pct']:.4f}",f"{row['selectivity_pct']:.2f}",f"{row['yield_pct']:.4f}"] for label,row in [("全部观测",observed),("严格低温",low)]]),
        text("A3的配方为200mg 1wt%Co/SiO2与200mg HAP，进料0.9ml/min、方式I；A2为200mg 2wt%Co/SiO2与200mg HAP，进料1.68ml/min、方式I。上述表格直接回答当前已经测得的候选，不等于在所有连续配方中的最优。"),
        text("另对每组的收率拟合低阶温度多项式，在该组已测最小至最大温度内枚举端点及导数零点。A3的所选一次模型给出高温端450℃候选，而实测最高点在400℃，表明模型结构会改变决策；应先补测而不是把模型最高预测直接作为已证实工况。"),
        text("对严格低温条件，A2所选二次模型在250—350℃内持续上升，350℃处拟合值约26.9399%。由于350℃被排除，该值是上确界，不能取到。此前349.75℃来自0.25℃网格；更换网格会改变所谓最优温度，证明它不应被当成连续问题的唯一解。"),
        eq(r"\sup_{250\le T<350}\widehat Y_{\mathrm{A2}}(T)=\lim_{T\uparrow350}\widehat Y_{\mathrm{A2}}(T),\qquad \text{该区间内最大值不取到}."),
        {"image":"artifacts/figures/stability_and_boundary.pdf","caption":"图2 左：350℃单次实验的时间变化；右：A2经验曲线与被排除的350℃边界，空心点表示不能取到。"},
        text("若设备采用1℃设定步长，可把349℃作为待验证工况；若步长或控温误差不同，应给定小于350℃的实际可行上限后重新计算。没有重复实验时，不能从单条曲线推出精确的获益概率或可靠置信区间。")],2)
    section("5.4 问题四：五次补充实验",[
        table([["名额","组合","温度/℃","目的"]]+[[str(r["slot"]),r["group"],str(r["temperature_c"]),r["reason"]] for r in decision["experiment_design"]["base_plan"]]),
        text("前两次新增重复与原A3/400℃记录共形成三个值，可初步估计重复性，但自由度仍很小，不应夸大精度。A3/425℃填补当前高温候选之间的空缺；A2/349℃检验低温边界附近的模型推断，A2/325℃重复用于检查低温参照是否可靠。各配方沿用上一节明确的质量、负载、进料及装料方式。"),
        text("先由实验室预先规定重复性容限和统一采样反应时间。若前两次重复不满足容限，将剩余三个名额改为重复或批次对照，总新增次数仍为五次，不再沿用旧方案中凭空指定的10%阈值。通过重复性检查后，其余三次的执行顺序随机安排并记录批次；本设计针对当前决策不确定性，不声称信息量或收益全局最优。")],2)
    section("六、模型检验与灵敏度分析",[
        text("独立验证按原始行索引检查训练/测试组合不相交，再用标准库math.fsum逐项重算15组模型结果的行等权和组等权RMSE，共30项数值比较，误差均不超过预定的10⁻¹⁰。观测最高收率另从原Excel单元格用Decimal计算确认，未调用主提取函数的收率结果。"),
        text(f"进一步独立重建仅温度回归与岭回归：显式展开单项式，只用训练行计算中心和总体方差，再用NumPy奇异值分解求解；不调用主程序的特征展开、标准化器或scikit-learn回归估计器。原划分及三套额外划分共{linear['fold_models']}个折内模型、{linear['heldout_predictions']}个留出预测均吻合，未截断预测的最大绝对差为{linear['max_raw_error']:.12f}个百分点，小于事先确定的$10^{{-7}}$容差。截断前后均作比较，避免物理截断掩盖模型实现差异。这项复核以已记录的超参数为条件，没有独立重新选择内层参数，也没有重写随机森林。"),
        text("反例测试将某个外层测试折的响应大幅改变，该折选中的超参数、内层分数及预测必须保持不变；若改变则意味着测试标签参与了训练或选择。整组配方交换也检查质量加和与比例恒等式，禁止把温度这种组内变化特征当作组常量交换。"),
        text("每组只有5—7条温度记录，21个独立组合也不足以支持复杂模型稳定的普遍排名。留出组残差及家族选择结果需要与新实验持续对照。组间预测误差不是同一工况的重复实验噪声，不能拿它直接给A3/400℃与450℃的观测差异计算显著性。")])
    section("6.1 外层组划分对模型比较的影响",[
        text("为检验上一套分组划分是否左右模型选择，另外固定种子17、43、97，将21个组合打乱后按近似相等的组合数分为五折。三套完整索引在任何新拟合之前保存，分组只读取组合编号，不读取响应。模型候选、森林种子、内层四折选择和物理截断保持原协议，所有方法在同一套外层划分内比较。"),
        table([["响应","模型","RMSE中位数","RMSE范围"]]+[[names[target],methods[family],f"{values['median']:.3f}",f"{values['min']:.3f}—{values['max']:.3f}"]
              for target,output in partitions["summary"].items() for family,values in output["families"].items() if family!="training_mean"]),
        text("三套新划分中，固定家族的最低误差模型分别为："+"；".join(names[target]+"为"+(methods[output["fixed_family_winners"][0]] if len(set(output["fixed_family_winners"]))==1 else "随划分变化") for target,output in partitions["summary"].items())+"。这里分别比较固定家族和跨家族的自适应选择流程，不把后者的外层成绩当作某个事后选中模型的成绩。"),
        text(f"但局部两两比较存在翻转：C4选择性上，随机森林在新三套划分中有{partitions['summary']['selectivity_pct']['families']['random_forest']['better_than_temperature_count']}套优于仅温度模型，而原划分中稍差。因此不能把原表的一行差异推广为随机森林必定不如仅温度模型。相较之下，岭回归在本次各套划分中均优于二者，为当前数据的选择性建模提供了更一致的依据。"),
        text("跨模型嵌套选择也未必胜过一个固定家族：内层验证可能选错家族，外层误差应如实计入这一选择代价。新增三套划分共90项行/组RMSE由标量求和独立核对，同时重新检查训练均值与组隔离；每套仍覆盖全部114条记录。"),
        text("三次重分组反复使用同一批21个组合，结果彼此相关。表中的范围和优胜次数仅描述划分敏感性，不是置信区间、独立复现实验或获胜概率。这是见过原结果后的补充分析；更强的预测结论仍需独立新组合或新批次实验。")],2)
    section("七、模型评价与改进",[
        text("本方法把逐组描述、组合外预测和工艺决策分开验证，采用训练均值和仅温度基线，能够实际判断配方模型是否带来增量；匹配对照保留温度及其他记录条件一致的比较，避免只列算法重要性排名。对严格不等式显式区分上确界和可执行候选，五次实验预算也涵盖失败后的重新分配。"),
        text("不足在于原实验设计不均衡、缺少批次与老化信息、没有工况重复。最高记录与局部多项式尚不足以证明新的配方最优；岭回归与森林都只是经验模型。下一阶段应按实验设计取得真实新增数据，并用未参与选择的数据检验，而不是继续增加模型名称。")])
    section("八、结论",[text(f"在现有数据中，A3/400℃与A2/325℃分别是全部观测与严格低温域的最佳记录，收率为{observed['yield_pct']:.4f}%与{low['yield_pct']:.4f}%。不同响应适合的经验模型并不相同，随机森林不能统一替代简单模型。A2低温经验曲线的最佳极限位于被排除的350℃边界，实际推荐需先确定设备分辨率并实验确认。五次新增实验优先检验重复性和影响决策的温度区间。")])
    section("AI工具使用声明",[text("本历史题训练稿使用AI工具进行数据核对、建模、代码实现、独立复算和文字排版。参赛团队的实际人工审查及正式AI使用详情未完成，不能将本稿视为已经获准提交的参赛论文。")])
    section("参考文献",[text("[1] 全国大学生数学建模竞赛组委会. 2021年高教社杯全国大学生数学建模竞赛B题：乙醇偶合制备C4烯烃[Z]. 2021. 原题两页、附件1性能数据表及附件2稳定性测试。")])
    section("附录",[text("运行run_all.py可复跑本题。statistical_results.json保存预测与选模明细，decisions.json保存温度关系和实验方案，split_sensitivity目录保存各套分组与结果。通用计算见grouped_regression.py。正式提交仍需完整源码附录、支撑包和真实AI详情。")])
    # Use TeX for the validation tolerance as well as all substantive formulas.
    for s in sections:
        for b in s["blocks"]:
            if "text" in b:b["text"]=b["text"].replace("10⁻¹⁰",r"$10^{-10}$")
    (run/"paper").mkdir(exist_ok=True)
    write_json(run/"paper/document.json",{"title":"乙醇偶合制备C4烯烃的分组预测与实验设计","sections":sections})
    print({"sections":len(sections)},flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("run",type=Path);compose(p.parse_args().run)
