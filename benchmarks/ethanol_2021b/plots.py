"""Chinese result figures: grouped predictive error, stability and open temperature boundary."""
import argparse
import os
from pathlib import Path
import numpy as np
from prepare import read_json


def draw(run):
    cache=run/"tmp/matplotlib";cache.mkdir(parents=True,exist_ok=True)
    os.environ["MPLCONFIGDIR"]=str(cache.resolve());os.environ["XDG_CACHE_HOME"]=str((run/"tmp").resolve())
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    songti=Path("/System/Library/Fonts/Supplemental/Songti.ttc")
    if songti.exists():
        from fontTools.ttLib import TTCollection
        collection=TTCollection(songti);font=cache/"Songti.ttf";collection.fonts[6].save(font);collection.close()
        font_manager.fontManager.addfont(str(font));family=font_manager.FontProperties(fname=str(font)).get_name()
    else:
        names={x.name for x in font_manager.fontManager.ttflist};family=next((x for x in ("SimSun","Noto Serif CJK SC","Source Han Serif SC") if x in names),None)
        if family is None:raise ValueError("Chinese serif font needed for figures")
    plt.rcParams.update({"font.family":family,"font.size":11,"axes.unicode_minus":False,"mathtext.fontset":"stix",
                         "axes.spines.top":False,"axes.spines.right":False,"pdf.fonttype":42})
    out=run/"artifacts/figures";out.mkdir(exist_ok=True)
    def save(fig,name):
        fig.tight_layout();fig.savefig(out/(name+".pdf"),bbox_inches="tight");fig.savefig(out/(name+".png"),dpi=300,bbox_inches="tight");plt.close(fig)
    result=read_json(run/"artifacts/statistical_results.json");decisions=read_json(run/"artifacts/decisions.json")
    fig,axes=plt.subplots(1,3,figsize=(9,3.8))
    methods=["training_mean","temperature_only","ridge","random_forest","nested_selection"]
    labels=["训练均值","仅温度","岭回归","随机森林","嵌套选模"]
    for ax,(target,output),label in zip(axes,result["targets"].items(),["乙醇转化率","C4选择性","C4收率"]):
        values=[output["models"][name]["metrics"]["group_rmse"] for name in methods]
        bars=ax.barh(labels,values,color=["#9aa2a6","#E69F00","#009E73","#0072B2","#CC79A7"])
        for bar,value in zip(bars,values):ax.text(value+.15,bar.get_y()+bar.get_height()/2,f"{value:.2f}",va="center",fontsize=9)
        ax.invert_yaxis();ax.set(xlim=(0,max(values)*1.25),title=label,xlabel="按实验组等权RMSE / 百分点");ax.grid(axis="x",alpha=.15)
    save(fig,"grouped_prediction")
    fig,axes=plt.subplots(1,2,figsize=(8.5,3.6))
    stability=decisions["stability"]["measurements"]
    for key,label,marker,color in [("conversion_pct","转化率","o","#0072B2"),("selectivity_pct","C4选择性","s","#D55E00"),("yield_pct","C4收率","^","#009E73")]:
        axes[0].plot([r["time_min"] for r in stability],[r[key] for r in stability],marker=marker,label=label,color=color)
    axes[0].set(xlabel="反应时间 / min",ylabel="百分数 / %",title="350℃单次实验的时间变化");axes[0].legend(frameon=False,fontsize=9);axes[0].grid(alpha=.15)
    model=next(m for m in decisions["local_models"] if m["group"]=="A2")["response_models"]["yield_pct"]
    t=np.linspace(250,350,201);prediction=np.polyval(model["coefficients"],(t-model["center"])/model["scale"])
    axes[1].plot(t,prediction,color="#0072B2")
    axes[1].scatter([350],[prediction[-1]],facecolors="white",edgecolors="#D55E00",zorder=4,s=60)
    axes[1].axvline(350,color="#D55E00",linestyle="--",linewidth=1)
    axes[1].set(xlabel="温度 / ℃",ylabel="拟合C4收率 / %",title="A2：350℃为被排除的边界",xlim=(245,357));axes[1].grid(alpha=.15)
    save(fig,"stability_and_boundary")


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("run",type=Path);draw(p.parse_args().run)
