"""Chinese quantitative figures from verified supply-plan artifacts."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from prepare import write


def draw(run):
    out=run/"artifacts/figures";out.mkdir(parents=True,exist_ok=True)
    cache=run/"tmp/plot-cache";cache.mkdir(parents=True,exist_ok=True)
    os.environ["MPLCONFIGDIR"]=str(cache.resolve())
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib import pyplot as plt,font_manager
    fontpath=Path("/System/Library/Fonts/Supplemental/Songti.ttc")
    if fontpath.exists():
        from fontTools.ttLib import TTCollection
        fonts=TTCollection(fontpath);fp=cache/"Songti.ttf";fonts.fonts[6].save(fp);fonts.close()
        font_manager.fontManager.addfont(str(fp));family=font_manager.FontProperties(fname=str(fp)).get_name()
    else:
        family=next((v.name for v in font_manager.fontManager.ttflist if v.name in ("SimSun","Noto Serif CJK SC","Source Han Serif SC")),None)
        if family is None:raise ValueError("Chinese serif font required")
    plt.rcParams.update({"font.family":family,"font.size":11,"axes.unicode_minus":False,"pdf.fonttype":42})
    p=json.loads((run/"artifacts/plans.json").read_text());r=json.loads((run/"artifacts/ranking.json").read_text())
    alt=json.loads((run/"artifacts/alternatives.json").read_text());sens=json.loads((run/"artifacts/capacity-sensitivity.json").read_text())
    def save(fig,name):
        fig.savefig(out/(name+".pdf"),bbox_inches="tight");fig.savefig(out/(name+".png"),dpi=200,bbox_inches="tight");plt.close(fig)
    fig,ax=plt.subplots(figsize=(8,4));top=r[:20]
    ax.bar(np.arange(20),[v["marginal_weekly_product_equivalent"] for v in top],color=[{"A":"#0072B2","B":"#E69F00","C":"#009E73"}[v["kind"]] for v in top])
    ax.set_xticks(np.arange(20),[v["supplier"] for v in top],rotation=50,ha="right")
    ax.set_ylabel("平均边际保障量 / 产品立方米每周");ax.set_xlabel("供应商编号（前20名）")
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=c,label=k+"类") for k,c in zip("ABC",("#0072B2","#E69F00","#009E73"))],frameon=False)
    ax.spines[["top","right"]].set_visible(False);fig.tight_layout();save(fig,"supplier-importance")
    fig,ax=plt.subplots(figsize=(8,3.8));labels=["问题二：26家","问题三：全体候选","问题三：前50家候选"]
    plans=[p["Q2"],p["Q3"],alt["Q3_top50"]];left=np.zeros(3)
    for k,color in zip("ABC",("#0072B2","#E69F00","#009E73")):
        v=np.array([x["raw_by_type"][k]/10000 for x in plans]);ax.barh(labels,v,left=left,label=k+"类",color=color);left+=v
    ax.set_xlabel("24周采购原材料 / 万立方米");ax.invert_yaxis();ax.legend(ncol=3,frameon=False,loc="upper center",bbox_to_anchor=(.5,1.16))
    ax.spines[["top","right"]].set_visible(False);fig.tight_layout();save(fig,"material-tradeoff")
    fig,ax=plt.subplots(figsize=(8,3.8));rows=sens[:5]
    ax.plot([v["contract_capacity_scale"] for v in rows],[v["steady_capacity"]/10000 for v in rows],"o-",label="稳态供应上限",color="#0072B2")
    ax.plot([v["contract_capacity_scale"] for v in rows],[v["immediate_capacity"]/10000 for v in rows],"s--",label="固定初始库存的立即增产",color="#D55E00")
    ax.axhline(2.82,color="#555555",ls=":",label="现有产能")
    ax.set(xlabel="合同供货能力倍数",ylabel="产品产能 / 万立方米每周");ax.legend(frameon=False)
    ax.spines[["top","right"]].set_visible(False);fig.tight_layout();save(fig,"capacity-inventory")
    fig,ax=plt.subplots(figsize=(8,3.8));t=np.arange(1,25);a=np.array(json.loads((run/"artifacts/facts.json").read_text())["conversion"])
    loss=np.array(json.loads((run/"artifacts/facts.json").read_text())["carrier_mean_loss"])
    for m,color in ((1.,"#0072B2"),(.9,"#E69F00"),(.8,"#D55E00")):
        y=np.array(p["Q2"]["shipments"]);arr=(y*m*(1-loss)[None,None,:]/a[None,:,None]).sum((1,2))
        inv=56400+np.cumsum(arr-28200);ax.plot(t,inv/10000,label=f"供货为模型值的{m:.0%}",color=color)
    ax.axhline(5.64,color="#555555",ls="--",lw=1,label="两周库存目标");ax.axhline(0,color="#222222",lw=1)
    ax.set(xlabel="计划周",ylabel="库存结余 / 万产品立方米当量",xticks=[1,4,8,12,16,20,24]);ax.legend(frameon=False,fontsize=9,ncol=2)
    ax.spines[["top","right"]].set_visible(False);fig.tight_layout();save(fig,"supply-stress")
    names=("supplier-importance","material-tradeoff","capacity-inventory","supply-stress")
    write(out/"evidence.json",{"source_sha256":{name:hashlib.sha256((run/"artifacts"/name).read_bytes()).hexdigest() for name in ("plans.json","ranking.json","alternatives.json","capacity-sensitivity.json")},
                                "figures":{name:hashlib.sha256((out/name).read_bytes()).hexdigest() for stem in names for name in (stem+".pdf",stem+".png")}})
    print({"figures":len(names)},flush=True)


if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("run",type=Path);draw(ap.parse_args().run)
