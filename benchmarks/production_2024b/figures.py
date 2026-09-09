"""Source-bound assembly topology and exact linear cost decomposition figures."""
import argparse
from copy import deepcopy
from fractions import Fraction as F
import os
from pathlib import Path
from prepare import read_json,write_json,sha256_file
from multistage import leaf,assembly,order_cost

CATEGORIES=("purchase","part_inspection","semi_assembly","semi_inspection","semi_dismantle","final_assembly","final_inspection","final_dismantle","customer_exchange_loss")


def policy_cost(tree,policy):
    parts=[leaf(p["p"],p["purchase"],p["test"],policy["part_tests"][i]) for i,p in enumerate(tree["parts"])]
    semis=[assembly([parts[j] for j in node["children"]],node["p"],node["assembly"],node["test"],node["dismantle"],
            policy["semi_tests"][i],policy["semi_dismantle"][i]) for i,node in enumerate(tree["semis"])]
    node=tree["final"]
    return order_cost(semis,node["p"],node["assembly"],node["test"],node["dismantle"],node["exchange_loss"],policy["final_test"],policy["final_dismantle"])


def breakdown(tree,policy):
    components={}
    # Fixed-policy expected cost is linear in primitive monetary costs. Activate
    # one category at a time without changing defects, tests or recovery decisions.
    for category in CATEGORIES:
        isolated=deepcopy(tree)
        for part in isolated["parts"]:
            for key,name in (("purchase","purchase"),("test","part_inspection")):
                if category!=name:part[key]=0
        for node in isolated["semis"]:
            for key in ("assembly","test","dismantle"):
                name="semi_"+{"assembly":"assembly","test":"inspection","dismantle":"dismantle"}[key]
                if category!=name:node[key]=0
        for key,name in (("assembly","final_assembly"),("test","final_inspection"),("dismantle","final_dismantle"),("exchange_loss","customer_exchange_loss")):
            if category!=name:isolated["final"][key]=0
        components[category]=policy_cost(isolated,policy)
    total=policy_cost(tree,policy)
    if sum(components.values())!=total or total!=F(policy["cost_exact"]):
        raise ValueError("component costs do not reproduce recorded policy total")
    return {"components":{k:float(v) for k,v in components.items()},"exact_components":{k:str(v) for k,v in components.items()},
            "total":float(total),"exact_total":str(total)}


def draw(run):
    folder=run/"artifacts/multistage";protocol=read_json(folder/"protocol.json");result=read_json(folder/"result.json")
    if result["protocol_sha256"]!=sha256_file(folder/"protocol.json"):raise ValueError("source tree protocol changed")
    tree=protocol["tree"]
    data={name:breakdown(tree,policy) for name,policy in [("best",result["best_policies"][0]),*result["baselines"].items()]}
    out=run/"artifacts/figures";out.mkdir(exist_ok=True)
    cache=run/"tmp/matplotlib";cache.mkdir(parents=True,exist_ok=True)
    os.environ["MPLCONFIGDIR"]=str(cache.resolve());os.environ["XDG_CACHE_HOME"]=str((run/"tmp").resolve())
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import FancyBboxPatch
    fontpath=Path("/System/Library/Fonts/Supplemental/Songti.ttc")
    if fontpath.exists():
        from fontTools.ttLib import TTCollection
        collection=TTCollection(fontpath);font=cache/"Songti.ttf";collection.fonts[6].save(font);collection.close()
        font_manager.fontManager.addfont(str(font));family=font_manager.FontProperties(fname=str(font)).get_name()
    else:
        available={f.name for f in font_manager.fontManager.ttflist}
        family=next((name for name in ("SimSun","Noto Serif CJK SC","Source Han Serif SC") if name in available),None)
        if family is None:raise ValueError("install a Chinese serif font before rendering figures")
    plt.rcParams.update({"font.family":family,"font.size":11,"axes.unicode_minus":False,"pdf.fonttype":42,"svg.fonttype":"none"})
    def save(fig,name):
        fig.savefig(out/(name+".pdf"),bbox_inches="tight")
        fig.savefig(out/(name+".svg"),bbox_inches="tight")
        svg=out/(name+".svg")
        svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines())+"\n",encoding="utf-8")
        fig.savefig(out/(name+".png"),dpi=220,bbox_inches="tight")
        plt.close(fig)
    fig,ax=plt.subplots(figsize=(8.1,4.5));ax.set(xlim=(0,1),ylim=(0,1));ax.axis("off")
    ys=[.92-i*.112 for i in range(8)]
    def box(x,y,w,h,label,color):
        ax.add_patch(FancyBboxPatch((x-w/2,y-h/2),w,h,boxstyle="round,pad=0.009",facecolor=color,edgecolor="#5c6b73",linewidth=.8))
        ax.text(x,y,label,ha="center",va="center",fontsize=11)
    edges=[]
    for i,part in enumerate(tree["parts"]):box(.13,ys[i],.19,.066,"零件"+part["id"],"#eef3f6")
    for i,node in enumerate(tree["semis"]):
        y=sum(ys[j] for j in node["children"])/len(node["children"])
        box(.52,y,.23,.12,"半成品"+node["id"]+f"\n条件次品率 {node['p']:.0%}","#dceee8")
        for j in node["children"]:
            ax.annotate("",xy=(.395,y),xytext=(.235,ys[j]),arrowprops={"arrowstyle":"->","color":"#526b78","lw":1.1})
            edges.append(["part-"+str(j+1),"semi-"+node["id"]])
        ax.annotate("",xy=(.77,.53),xytext=(.645,y),arrowprops={"arrowstyle":"->","color":"#526b78","lw":1.1})
        edges.append(["semi-"+node["id"],"final"])
    box(.87,.53,.18,.14,"成品\n条件次品率\n"+f"{tree['final']['p']:.0%}","#fff0d5")
    ax.text(.5,-.025,"箭头表示组装关系；组装次品率以全部输入子件合格为条件。",ha="center",va="top",fontsize=10)
    fig.tight_layout();save(fig,"assembly_tree")
    ordered=[("best","最优代表"),("inspect_and_recover_everywhere","全检并回收"),("no_inspection_no_recovery","不检不回收")]
    grouped=[("购买",["purchase"],"#0072B2"),("检测",["part_inspection","semi_inspection","final_inspection"],"#009E73"),
             ("组装",["semi_assembly","final_assembly"],"#E69F00"),("拆解",["semi_dismantle","final_dismantle"],"#CC79A7"),("额外调换损失",["customer_exchange_loss"],"#D55E00")]
    fig,ax=plt.subplots(figsize=(8.1,3.9));positions=list(range(3));left=[0.]*3
    for label,keys,color in grouped:
        values=[sum(data[name]["components"][key] for key in keys) for name,_ in ordered]
        ax.barh(positions,values,left=left,label=label,color=color,height=.5,edgecolor="white",linewidth=.6)
        left=[a+b for a,b in zip(left,values)]
    for i,(name,_) in enumerate(ordered):ax.text(left[i]+4,i,f"{data[name]['total']:.3f}",va="center",fontsize=10)
    ax.set(yticks=positions,yticklabels=[label for _,label in ordered],xlabel="每个完成订单的期望成本 / 元",xlim=(0,max(left)*1.13))
    ax.invert_yaxis();ax.grid(axis="x",alpha=.15);ax.set_axisbelow(True)
    ax.spines[["top","right"]].set_visible(False)
    ax.legend(loc="upper center",bbox_to_anchor=(.5,-.2),ncol=3,frameon=False,fontsize=10)
    fig.subplots_adjust(left=.15,right=.96,top=.94,bottom=.29);save(fig,"cost_breakdown")
    record={"source_protocol_sha256":sha256_file(folder/"protocol.json"),"source_result_sha256":sha256_file(folder/"result.json"),
            "topology_edges":edges,"policy_costs":data,"scope":"exact fixed-policy expected cost decomposition, not simulation estimates or field cost measurements",
            "figure_sha256":{name:sha256_file(out/name) for stem in ("assembly_tree","cost_breakdown") for name in (stem+".pdf",stem+".svg",stem+".png")}}
    write_json(out/"figure_evidence.json",record)
    print({"figures":2,"topology_edges":len(edges),"totals":{k:v["total"] for k,v in data.items()}},flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("run",type=Path);draw(p.parse_args().run)
