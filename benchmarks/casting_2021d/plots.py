"""Plot numerical cut intervals and defect locations with Chinese labels."""
import argparse
import os
from pathlib import Path
from solve import read_json


def draw(run):
    cache=run/"tmp/matplotlib"; cache.mkdir(parents=True,exist_ok=True)
    os.environ["MPLCONFIGDIR"]=str(cache.resolve())
    os.environ["XDG_CACHE_HOME"]=str((run/"tmp").resolve())
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.patches import Patch
    songti=Path("/System/Library/Fonts/Supplemental/Songti.ttc")
    if songti.exists():
        from fontTools.ttLib import TTCollection
        fonts=TTCollection(songti); path=cache/"SongtiSC-Regular.ttf"
        fonts.fonts[6].save(path); fonts.close()
        font_manager.fontManager.addfont(str(path))
        family=font_manager.FontProperties(fname=str(path)).get_name()
    else:
        available={f.name for f in font_manager.fontManager.ttflist}
        family=next((f for f in ("SimSun","Noto Serif CJK SC","Source Han Serif SC") if f in available),None)
        if not family: raise RuntimeError("A Chinese serif font is needed for the paper figures")
    plt.rcParams.update({"font.family":family,"font.size":11,"axes.unicode_minus":False,
                         "axes.spines.top":False,"axes.spines.right":False,"pdf.fonttype":42})
    result=read_json(run/"artifacts/solution.json")
    row=result["online"]["Q3b"]["events"][7]
    fig,ax=plt.subplots(figsize=(8.1,3.4))
    for y,edges in [(1,row["previous_pending"]),(0,row["new_plan"]["pieces"])]:
        for piece in edges:
            a,b=piece["start"]/10,piece["end"]/10
            if b<310 or a>344: continue
            ax.broken_barh([(a,b-a)],(y-.16,.32),facecolors="#d7dce0",edgecolors="white",linewidth=1)
            if piece["recovered"]:
                left,right=[x/10 for x in piece["recovered"]]
                ax.broken_barh([(left,right-left)],(y-.16,.32),facecolors="#0072B2")
            if 311<a<343: ax.vlines(a,y-.22,y+.22,color="#303030",linewidth=1)
            if 311<b<343: ax.vlines(b,y-.22,y+.22,color="#303030",linewidth=1)
    for a,b in [(325.6,326.4),(330.3,331.1)]:
        ax.axvspan(a,b,color="#D55E00",alpha=.35)
    ax.annotate("旧异常",(326,1.2),xytext=(322.2,1.55),arrowprops={"arrowstyle":"-","color":"#555"})
    ax.annotate("270.7分时新获知",(330.7,1.2),xytext=(330.7,1.55),arrowprops={"arrowstyle":"-","color":"#555"},ha="center")
    ax.set(xlim=(310,344),ylim=(-.65,1.95),yticks=[0,1],yticklabels=["新通知后的方案","通知前的待执行方案"],
           xlabel="材料坐标 / m（亦为到达切割起点的时刻 / min）")
    ax.legend(handles=[Patch(facecolor="#0072B2",label="可回收产品"),Patch(facecolor="#d7dce0",label="待舍弃部分"),
                       Patch(facecolor="#D55E00",alpha=.35,label="报废段位置")],loc="lower center",ncol=3,frameon=False,fontsize=10)
    ax.grid(axis="x",alpha=.15); fig.tight_layout()
    out=run/"artifacts/figures";out.mkdir(exist_ok=True)
    fig.savefig(out/"online_adjustment.pdf",bbox_inches="tight")
    fig.savefig(out/"online_adjustment.png",dpi=300,bbox_inches="tight")
    plt.close(fig)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("run",type=Path)
    draw(parser.parse_args().run)
