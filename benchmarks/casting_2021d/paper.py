"""Write the three-question manuscript from computed, independently checked artifacts."""
import argparse
import hashlib
import json
import zipfile
from fractions import Fraction
from itertools import groupby
from pathlib import Path
from solve import read_json, write_json, sha256_file


def expression(values):
    parts=[]
    for value,group in groupby(map(Fraction,values)):
        count=len(list(group))
        base=str(value.numerator) if value.denominator==1 else rf"\frac{{{value.numerator}}}{{{value.denominator}}}"
        parts.append((str(count)+r"\times("+base+")") if count>1 else base)
    return "$"+"+".join(parts)+"$" if parts else "无"


def plan_text(pieces):
    if not pieces: return "首次通知，无前案"
    parts=[]
    for length,group in groupby(edge["end"]-edge["start"] for edge in pieces):
        count=len(list(group)); value=f"{length/10:.1f}"
        parts.append((str(count)+"×" if count>1 else "")+value)
    return "、".join(parts)


def support_appendix(run, support_root=None):
    archive = None
    if support_root is None:
        folder = run / "artifacts/submission-package"
        receipt = read_json(folder / "package_receipt.json")
        if receipt["sha256"] != sha256_file(folder / "support.zip"):
            raise ValueError("support ZIP changed after packaging")
        archive = zipfile.ZipFile(folder / "support.zip")
        read = archive.read
    else:
        root = Path(support_root).resolve()
        from reproduce import check_manifest
        check_manifest(root)
        read = lambda name: (root / name).read_bytes()
    try:
        manifest = json.loads(read("manifest.json"))
        blocks = [{"text": "下列文件与支撑包使用同一份源码，逐文件列出完整程序。独立复算命令为python3 -I reproduce.py --output reproduced；可选--paper重新生成图表和论文。复算从已核对的facts.json参数开始，不自动重新解释原题。"},
                  {"table": [["文件", "类别", "字节数"]] + [[item["path"], item["role"], item["bytes"]] for item in manifest["files"]] + [["manifest.json", "文件指纹清单", "随包生成"]]}]
        for item in manifest["files"]:
            content = read(item["path"])
            if hashlib.sha256(content).hexdigest() != item["sha256"]:
                raise ValueError("support source content differs: " + item["path"])
            if item["role"] == "code":
                blocks.append({"code": content.decode("utf-8-sig"), "filename": item["path"], "source_sha256": item["sha256"]})
        return {"id": "support-appendix", "title": "附录：支撑文件与完整源程序", "page_break_before": True, "blocks": blocks}
    finally:
        if archive is not None:
            archive.close()


def compose(run, support_root=None):
    data=read_json(run/"artifacts/solution.json")
    verified=read_json(run/"artifacts/independent.json")
    sensitivity=read_json(run/"artifacts/sensitivity.json")
    digest=sha256_file(run/"artifacts/solution.json")
    if verified["solution_sha256"]!=digest or sensitivity["solution_sha256"]!=digest or not verified["passed"]:
        raise ValueError("stale or failed numerical evidence")
    sections=[]
    text=lambda s:{"text":s}
    eq=lambda s:{"equation":s}
    table=lambda rows:{"table":rows}
    def section(title,blocks,level=1,page=False,key=None):
        sections.append({"title":title,"blocks":blocks,"level":level,"page_break_before":page,"id":key})
    losses={k:v["total_waste_m"] for k,v in data["online"].items()}
    max_seconds=max(r["planning_seconds"] for v in data["online"].values() for r in v["events"])
    section("摘要",[
        text("针对连铸尾坯处理与异常通知下的在线切割问题，本文将一次切割的运输长度限制与离线回收的产品长度要求分开建模，以报废总长度为第一目标、合格产品偏离目标长度的平方和为第二目标，形成尾坯解析分配与事件驱动动态规划相结合的求解方法。"),
        {"lead":"针对问题一：","text":"枚举合格产品数及整块报废件数，推导每种计数下的最大回收量，再由凸性确定等长分配。给出全部12种尾坯方案；其中109.0米和93.4米均可零损失回收，14.5米可回收9.7米。严格执行尾坯也需满足4.8米运输下限时，13.7米尾坯没有合格产品可回收。"},
        {"lead":"针对问题二：","text":f"按异常通知逐次更新已知报废区间，锁定已启动的切口，在0.1米网格上用字典序最短路重新规划。9.5米目标下，给定9次异常序列的最终损失为{losses['Q2']:.1f}米，达到连续材料分割理论下界。"},
        {"lead":"针对问题三：","text":f"保持信息边界和求解方法，仅替换产品区间。8.5米与11.1米目标下，最终损失分别为{losses['Q3a']:.1f}米和{losses['Q3b']:.1f}米，也达到相应下界。三组结果均给出原待执行方案、新方案和剩余计划损失。"},
        text(f"独立以单元占用图构造两阶段最小费用流线性规划，12种尾坯损失及27次事件的两级目标均与主算法一致。实测单次规划最多{max_seconds:.3f}秒；网格加密不改变三组损失，但会改善长度偏差。改变初始切口相位可改变最小损失，因此最优性结论明确限定初始状态、零切缝和所声明的二级偏好，不外推为未知未来异常下的普遍最优策略。"),
        text("关键词：连铸切割；在线决策；字典序优化；动态规划；最小费用流")],key="abstract")
    section("一、问题重述",[],page=True)
    section("1.1 背景与已知条件",[
        text("连铸钢坯以1.0米/分钟匀速通过切割机。每次切割从固定工作起点开始，切割机随钢坯移动3分钟，完成切断后用1分钟返回。结晶器中心到工作起点的钢坯长度为60.0米；异常发生时，切割工序立即获知，结晶器内长0.8米的报废段不能进入后续产品[1]。"),
        text("一次切下的钢坯必须长4.8—12.6米，才能被运走；下道工序接受8.0—11.6米的钢坯，还需满足用户给出的更窄目标范围。偏长钢坯可离线修剪，修剪部分报废；含缺陷钢坯也先整体切下，再离线回收其中符合要求的连续健康部分。题目要求优先减小报废长度，再尽量接近用户目标长度。")],2)
    section("1.2 逐问任务",[
        {"lead":"问题一：","text":"用户目标9.5米、范围9.0—10.0米，针对题目列出的12种尾坯长度，给出最优切割方案与损失。"},
        {"lead":"问题二：","text":"异常时刻为0.0、45.6、98.6、131.5、190.8、233.3、266.0、270.7及327.9分钟，目标及范围同问题一。针对每次通知给出新段方案、当前段调整或不调整，以及相应损失。"},
        {"lead":"问题三：","text":"沿用问题二的通知时刻与实时要求，分别将目标改为8.5米（范围8.0—9.0米）和11.1米（范围10.6—11.6米），给出两组完整方案。"}],2)
    section("二、问题分析",[])
    section("2.1 问题一的分析",[
        text("尾坯总长已知，没有未来信息问题。关键是同时处理合格品与废料的运输：末端不足4.8米不能直接当成允许丢弃的独立一次切割件。先确定合格品件数和整块报废件数，可将连续长度优化化为有限计数枚举，再利用凸性分配合格长度。")],2)
    section("2.2 问题二的分析",[
        text("异常通知比缺陷到达切割点早约60分钟，提供了调整尚未执行切口的时间。已启动的切割不能撤回；把所有9个异常提前输入一次离线优化，会改变题目。每次通知时应保存真实执行状态，仅对已知缺陷及其后健康延续规划，待新通知到达后再重算。"),
        text("一次切割最长12.6米，小于两个最短8.0米合格品的总长，因此每块一次切割件至多回收一个合格品。这使每条切割边的最大回收量可以直接计算，从而用无环图上的动态规划处理两级目标，无需为每块材料建立复杂的多件装箱模型。")],2)
    section("2.3 问题三的分析",[
        text("更换目标区间会改变健康间隔能容纳的产品数，影响并非简单按目标长度比例缩放。例如两次相邻异常之间若只有3.9米健康材料，三种目标均无法利用；而31.9米健康材料可容纳三块10.6米以上产品，却放不下四块8.0米产品。应复用同一算法重新计算，而不是直接改写问题二的结果。")],2)
    section("三、模型假设",[
        text("1．切缝宽度取零，离线加工不设额外时间及能力约束；题面未提供这些参数。若实际切缝或离线资源不可忽略，应将其长度损失和能力限制加入模型。"),
        text("2．0.8米报废段以结晶器中心为中心。以材料到达切割起点的时刻为坐标，则时刻t通知的报废区间为[t+59.6,t+60.4]米。图示未规定其他偏移，中心对齐属于明确采用的解释。"),
        text("3．初始状态取t=0时坐标0处的切割已经启动，该边界不能更改。同一时刻的新通知先于新的切割启动处理。初始相位原题未给定，下文报告半个目标长度的相位变更结果。"),
        text("4．严格将4.8—12.6米限制用于每块一次切割件，包括尾坯余段；离线修剪废料不受此运输下限约束。产品必须同时满足基本要求和正常要求。"),
        text("5．第二目标取合格产品长度偏差平方和；报废件不计入合格产品偏差。题面没有唯一指定偏差范数，因此这是一项可替换的偏好定义。在线规划采用0.1米网格，另用0.05米网格检验离散影响。")])
    section("四、符号说明",[table([["符号","含义","单位"],["$L$","尾坯总长度","m"],["$a,b$","一次切割长度上下限4.8、12.6","m"],["$l,u,d$","产品区间下限、上限与目标","m"],["$p_i,r_i$","第i块一次切割长度与回收长度","m"],["$W,V$","总报废长度与合格长度偏差平方和","m、m²"],["$s,t$","最近锁定切口与当前通知时刻","m、min"],["$D_j$","第j段已知报废区间","m"],["$h$","在线切口网格间距","m"]])])
    section("五、模型建立与求解",[])
    section("5.1 问题一：尾坯的连续长度优化",[
        text(r"设产生$n$个合格品、$m$个整块报废件。合格品长度在$[l,u]$中；相应一次切割件可比合格品更长，但不超过$b$。可行计数满足"),
        eq(r"nl+ma\le L\le(n+m)b,\qquad n,m\in\mathbb Z_{\ge0},\quad n+m\ge1."),
        text("对固定件数，产品总长度不能超过n个上限，也不能占用整块报废件所需的最短运输长度。因此最大可回收总量及损失为"),
        eq(r"R_{n,m}=\min\{nu,L-ma\},\qquad W_{n,m}=L-R_{n,m},\qquad R_{n,m}\ge nl."),
        text(r"在固定$R_{n,m}$下，平方偏差具有凸性。把每件合格品分配为$R_{n,m}/n$可达到最小二级目标；$n=0$时约定该目标为0。"),
        eq(r"V_{n,m}=n\left(\frac{R_{n,m}}n-d\right)^2\quad(n>0)."),
        text(r"枚举$n+m\le\lfloor L/a\rfloor$，按$(W,V)$字典序比较：只有损失相同时才比较长度偏差。取最少一次切割件数作为完全并列时的显示选择。给定回收长度后，将剩余材料分配给各一次切割件，容量均不超过$b$；上述总容量条件保证这种分配存在。本题用有理数计算，避免小数舍入改变质量守恒。"),
        text("表1列出全部尾坯。乘号表示连续相同长度的件数；分数保留精确长度，合格品列不包含整块报废件。一次切割件与合格品的长度差即离线废料。"),
        table([["尾坯/m","一次切割方案/m","合格品/m","损失/m"]]+[[f"{r['tail_m']:.1f}",expression(r["exact"]["primary"]),expression([v for v in r["exact"]["recovered"] if Fraction(v)]),f"{r['waste_m']:.1f}"] for r in data["tails"]]),
        text("尾坯损失依次为"+"、".join(f"{r['waste_m']:.1f}" for r in data["tails"])+"米。"),
        text("13.7米这一边界例尤其重要：若要得到一件至少9.0米产品，剩余最多4.7米，不能独立运走；又不能把13.7米整块切下，因为超过12.6米上限。两块均不足9.0米时，尽管其中一块可能达到基本工序的8.0米下限，仍不能满足本问正常要求。14.5米则可分为9.7与4.8米，回收前者。")],2,key="q1")
    section("5.2 问题二：异常通知下的在线规划",[
        text(r"令每个网格切口为图节点$x$，满足$a\le y-x\le b$时可从$x$连边至$y$。该边表示一次切下区间$[x,y]$。从此区间扣除当前已知报废段后，取最长连续健康部分长度$c(x,y)$，其最大回收量为"),
        eq(r"r(x,y)=\begin{cases}\min\{u,c(x,y)\},&c(x,y)\ge l,\\0,&c(x,y)<l.\end{cases}"),
        text("不能把报废段两侧不相连的健康长度相加；两侧各5米，即便总计10米，也不能得到一块9米以上的连续产品。边的两级代价分别为一次切割长度减去回收量，以及回收长度的平方偏差："),
        eq(r"w(x,y)=y-x-r(x,y),\qquad v(x,y)=\begin{cases}(r(x,y)-d)^2,&r(x,y)>0,\\0,&r(x,y)=0.\end{cases}"),
        text("通知到达时，以最近已经启动切割的坐标s为起点。首个新切口必须不早于当前通知时刻；其他边严格向右，不会回到已经经过的材料位置。题设速度为1米/分钟，4.8米最短运输长度对应至少4.8分钟切割间隔，大于3分钟切割加1分钟返回，因此运输下限已蕴含本题的机器周期限制。验证程序仍单独核对两者。"),
        eq(r"F(y)=\min_{x\to y}^{\mathrm{lex}}\{F(x)+(w(x,y),v(x,y))\},\qquad F(s)=(0,0)."),
        text("令z为最后一个已知报废段的结束位置，规划在第一个不小于z的切口终止。因为到该切口的一次切割最长b，候选终点只需考虑[z,z+b]；之后可恢复目标定长切割，直到新的异常通知。所有候选终点也按两级目标比较，完全并列时再依次选更少切口和更早终点。有限无环图的递推给出当前已知信息与网格约束下的精确最优方案。"),
        text("每次通知先执行上一方案中启动时间严格早于本次通知的切口，将这些切口永久保留；再加入新报废区间，只重算剩余部分。同一异常序列的任意前缀，必须与在更长序列中运行到该时刻的决策一致。全部异常仅用于最后的事后下界计算，不传入尚未到达的在线决策。"),
        text(f"问题二累计实际报废为{losses['Q2']:.1f}米。以下表中的方案均从“已锁定”切口向后依次列一次切割长度，顿号分隔、乘号合并连续等长件；“余下损失”是该时刻已知缺陷下的新待执行方案损失，不是当次新增损失，不能按行相加。下一刀“不变”表示最近的尚未启动切口不调整，其后的切口仍可重排。第一行给出首次方案，后续行保留修改前后的待切方案。")],2,key="q2")
    def event_tables(key,number,title,offset=0):
        rows=data["online"][key]["events"]
        for first in range(0,9,3):
            section(f"{number}.{offset+first//3+1} "+title+f"：第{first+1}—{first+3}次通知",[
                table([["通知/min；下一刀","已锁定/m","原待切长度/m","新待切长度/m","余下损失/m"]]+[
                    [f"{r['time_tick']/10:.1f}；"+("首次" if r["current_next_cut_changed"] is None else "调整" if r["current_next_cut_changed"] else "不变"),f"{r['locked_boundary']/10:.1f}",plan_text(r["previous_pending"]),plan_text(r["new_plan"]["pieces"]),f"{r['new_plan']['score'][0]/10:.1f}"] for r in rows[first:first+3]])],3)
    event_tables("Q2","5.2","问题二事件方案")
    section("5.3 问题三：替换产品区间后的决策",[
        text(f"问题三两组累计实际报废分别为{losses['Q3a']:.1f}米和{losses['Q3b']:.1f}米。沿用同一状态、回收定义和信息边界，只替换l、u、d，分别得到下列方案。每块一次切割件的绝对起止位置及离线回收区间另由event_plans.csv完整列出，可逐行核对正文长度表。"),
        text("在266.0与270.7分钟的两次异常之间，健康材料仅长4.7−0.8=3.9米，三种目标都不能回收。第二次通知时，这两段缺陷还在上游，相关切口尚可调整。图1以11.1米目标为例展示局部修改；橙色的新报废段在旧方案形成时尚未知，旧方案不是已经执行的错误切割。"),
        {"image":"artifacts/figures/online_adjustment.pdf","caption":"图1 相邻异常附近的待切方案调整。黑色短线为一次切口，蓝色为可回收区间，灰色为舍弃部分；两条均为局部截取。"}],2,key="q3")
    event_tables("Q3a","5.3","目标8.5米")
    event_tables("Q3b","5.3","目标11.1米",offset=3)
    section("六、验证与灵敏度分析",[])
    section("6.1 独立网络流复算与连续下界",[
        text("独立程序先把材料离散为健康/报废单元，逐单元扫描每条边中的最长健康连段，未调用主程序的区间回收函数。以单位流守恒构造最小费用流线性规划，先最小化损失，再固定最小损失求最小偏差，使用HiGHS求解。无环图的网络流可行域具有整数顶点；程序同时核对流量整数性与守恒残差。12种尾坯损失，以及27次在线决策的损失与偏差，均与主算法一致。尾坯连续偏差另按有理数恒等式核对，未将网格偏差冒充连续偏差。"),
        text(r"为判断总损失是否仍受网格限制，事后使用完整已实现异常序列构造连续下界。对长度$\ell_j$的有限健康间隔，最多形成$\lfloor\ell_j/l\rfloor$个合格品，总回收量不超过$\min\{\ell_j,u\lfloor\ell_j/l\rfloor\}$。再加上报废段本身，得"),
        eq(r"W_{\mathrm{LB}}=\sum_j|D_j|+\sum_j\left[\ell_j-\min\left\{\ell_j,u\left\lfloor\frac{\ell_j}{l}\right\rfloor\right\}\right]."),
        text("该下界放宽了运输、机器周期和在线限制，因此即使允许连续切口并提前知道全部异常，也不可能低于它。初始健康区间从声明的初始切口开始计算；最后报废段后的无限健康延续无需额外损失。"),
        table([["目标/m","在线实际损失/m","连续下界/m","是否达到"]]+[[f"{data['online'][k]['case']['target_m']:.1f}",f"{losses[k]:.1f}",f"{verified['online'][k]['continuous_lower_bound']['waste_m']:.1f}","是" if verified['online'][k]['continuous_lower_bound']['attained'] else "否"] for k in losses]),
        text("三组损失均达到下界，故第一目标在本初始状态和给定序列下已经最优。这不能推出该策略对任何未来序列均具有离线最优表现，也不能推出整个已实现序列的二级偏差全局最优；后者只在每次已知信息与当前网格的规划问题中得到最优性验证。")],2)
    section("6.2 基线、网格与初始相位",[
        text("固定目标长度切割作为基线，其切口完全不依据异常调整，仅在切下后尽量离线回收。它与在线策略均处理到最后报废段后的一个完整切口；多出的健康目标定长件不增加损失。基线与本文方案的差别反映调整切口的价值，不是换一个算法名称。"),
        table([["目标/m","定长基线损失/m","在线损失/m","0.1米偏差/m²","0.05米偏差/m²"]]+[[f"{data['online'][k]['case']['target_m']:.1f}",f"{s['fixed_target_baseline_waste_m']:.1f}",f"{s['nominal_waste_m']:.1f}",f"{s['nominal_deviation_m2']:.3f}",f"{s['fine_grid']['deviation_m2']:.3f}"] for k,s in sensitivity['cases'].items()]),
        text("网格加密至0.05米后，三种累计损失均不变，但长度偏差有所下降。这与损失已达到连续下界一致，也说明二级偏差仍有离散影响。将初始已启动切口移至负半个目标长度，所得损失如下："),
        table([["目标/m","初始切口/m","变更后损失/m","该状态下的下界/m"]]+[[f"{data['online'][k]['case']['target_m']:.1f}",f"{s['half_target_initial_phase']['initial_boundary_m']:.2f}",f"{s['half_target_initial_phase']['waste_m']:.2f}",f"{s['half_target_initial_phase']['lower_bound']['waste_m']:.2f}"] for k,s in sensitivity['cases'].items()]),
        text(f"初始相位改变了第一段可用健康材料的长度，不能把不同状态下的损失当成同一问题的相互矛盾答案。原题未给该状态，因此实际部署应读取最近已启动切口，而不是固定套用本文数值。0.1米网格下27次规划的本机最长耗时为{max_seconds:.3f}秒；计时不含事后独立LP验证，不构成设备实时性的硬保证。")],2)
    section("七、模型评价与改进",[
        text("模型利用一次运输件最多容纳一个合格产品的结构，避免多件装箱的额外组合变量；用字典序比较直接表达题目优先级，避免任意加权把少报废与接近目标混为一谈。在线执行记录保存已启动切口与每次通知前后的方案，能够检验是否偷用了未来信息。独立网络流与连续下界分别核对网格两级目标和连续总损失。"),
        text("主要边界是初始切口、缺陷中心对齐、零切缝和离线能力无限。实际切缝会改变每刀的质量守恒，离线容量可能使即时损失最小方案难以执行；需接入实际设备状态再规划。当前次优先级取平方偏差，其他用户偏好需重新求解。本文未给出所有可能异常序列下的竞争比，也未证明二级目标的连续最优性。")])
    section("八、结论",[
        text(f"在声明的初始状态及加工假设下，本文完成12种尾坯和三种目标下各9次异常决策。9.5、8.5、11.1米目标的在线累计损失分别为{losses['Q2']:.1f}、{losses['Q3a']:.1f}、{losses['Q3b']:.1f}米，均达到相应连续材料下界。方程、逐次方案与独立计算共同支撑这些条件结论；对初始相位与次优先级的边界已经明确。")])
    section("AI工具使用声明",[text("本训练稿使用AI工具参与题意分析、模型推导、代码编写、验证和文字排版。尚未完成参赛团队的人工审核、正式AI使用详情与比赛提交材料审查，不能作为已经获准提交的论文。")])
    section("参考文献",[text("[1] 全国大学生数学建模竞赛组委会. 2021年高教社杯全国大学生数学建模竞赛D题：连铸切割的在线优化[Z]. 2021. 原题两页及图1、图2；使用本项目冻结的原始PDF。")])
    sections.append(support_appendix(run, support_root))
    output=run/"paper";output.mkdir(exist_ok=True)
    write_json(output/"document.json",{"title":"连铸切割的在线优化与最优性验证","sections":sections})
    print({"sections":len(sections),"paragraph_characters":sum(len(b.get("text","")) for s in sections for b in s["blocks"])},flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("run",type=Path)
    compose(parser.parse_args().run)
