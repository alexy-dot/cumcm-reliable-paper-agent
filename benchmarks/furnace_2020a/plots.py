"""Regenerate scientific figures from the frozen-data fit and computed solutions."""
import argparse
import os
import sys
from pathlib import Path
import numpy as np
import openpyxl
from model import temperature_curve, BASE_SETTINGS
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skill/cumcm-reliable-paper/scripts"))
from engine import read_json


def draw(run):
    cache = run / "tmp/matplotlib"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ["MPLCONFIGDIR"] = str(cache)
    os.environ["XDG_CACHE_HOME"] = str(run / "tmp")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    songti = Path("/System/Library/Fonts/Supplemental/Songti.ttc")
    if songti.exists():
        from fontTools.ttLib import TTCollection
        collection = TTCollection(songti)
        regular = cache / "SongtiSC-Regular.ttf"
        collection.fonts[6].save(regular)
        collection.close()
        font_manager.fontManager.addfont(str(regular))
        chinese_font = font_manager.FontProperties(fname=str(regular)).get_name()
    else:
        available = {font.name for font in font_manager.fontManager.ttflist}
        chinese_font = next((name for name in ("SimSun", "Noto Serif CJK SC", "Source Han Serif SC") if name in available), None)
        if chinese_font is None:
            raise RuntimeError("Install a Chinese serif font (Songti/SimSun/Noto Serif CJK SC) before rendering figures")
    plt.rcParams.update({"font.family": chinese_font, "font.size": 11, "mathtext.fontset": "stix", "axes.unicode_minus": False,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.grid": True, "grid.alpha": .2, "figure.dpi": 150})
    figures = run / "artifacts/figures"
    figures.mkdir(exist_ok=True)
    solution = read_json(run / "artifacts/solution.json")
    calibration = read_json(run / "artifacts/calibration.json")
    parameters = solution["parameters"]
    workbook = openpyxl.load_workbook(run / "sources/attachment_01__附件.xlsx", read_only=True, data_only=True)
    observed = np.asarray(list(workbook.active.values)[1:], float)
    workbook.close()
    fig, axes = plt.subplots(2, 1, figsize=(8.1, 5.6), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    t, y = temperature_curve(BASE_SETTINGS, 70, parameters, dx=.05)
    axes[0].plot(observed[:, 0], observed[:, 1], '.', ms=2, color="#5a6470", label="实测校准曲线")
    axes[0].plot(t, y, lw=1.5, color="#106a8a", label="分区模型拟合")
    axes[0].legend(frameon=False)
    axes[0].set_ylabel(r"温度 / $^{\circ}\mathrm{C}$")
    axes[1].plot(observed[:, 0], np.interp(observed[:, 0], t, y) - observed[:, 1], color="#b34e39", lw=.9)
    axes[1].axhline(0, color="black", lw=.6)
    axes[1].set(xlabel="进炉后时间 / s", ylabel=r"残差 / $^{\circ}\mathrm{C}$")
    fig.tight_layout()
    fig.savefig(figures / "calibration.png", dpi=220)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8.1, 3.7))
    q1 = solution["Q1"]
    t, y = temperature_curve(q1["settings"], 78, parameters, dx=.05)
    ax.plot(t, y, color="#106a8a", lw=1.8)
    for index, (name, point) in enumerate(q1["locations"].items()):
        ax.scatter(point["time_seconds"], point["temperature_c"], s=25, color="#b34e39")
        label = {"zone3_mid": "第3区中点", "zone6_mid": "第6区中点", "zone7_mid": "第7区中点", "zone8_end": "第8区结束"}[name]
        ax.annotate(label + f"\n{point['temperature_c']:.2f}" + r"$\,^{\circ}\mathrm{C}$", (point["time_seconds"], point["temperature_c"]),
                    xytext=(-10, -33 if index % 2 else 17), textcoords="offset points", fontsize=8)
    ax.set(xlabel="进炉后时间 / s", ylabel=r"中心温度 / $^{\circ}\mathrm{C}$", title="问题1：指定温区设置，速度78 cm/min")
    fig.tight_layout()
    fig.savefig(figures / "q1.png", dpi=220)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(8.1, 3.5))
    colors = {"Q2": "#7b6b90", "Q3": "#106a8a", "Q4": "#b34e39"}
    for name in ["Q2", "Q3", "Q4"]:
        point = solution[name]
        t, y = temperature_curve(point["settings"], point["speed_cm_min"], parameters, dx=.05)
        axes[0].plot(t, y, color=colors[name], label=f"{name}: {point['speed_cm_min']:.2f} cm/min")
        if name != "Q2":
            axes[1].plot(t - point["metrics"]["peak_time"], y, color=colors[name], label=name)
    axes[0].axhline(217, color="#999999", ls="--", lw=.8)
    axes[0].set(xlabel="进炉后时间 / s", ylabel=r"温度 / $^{\circ}\mathrm{C}$")
    axes[0].legend(fontsize=8, frameon=False)
    axes[1].set(xlim=(-50, 50), ylim=(215, 244), xlabel="距峰值时刻的时间 / s", ylabel=r"温度 / $^{\circ}\mathrm{C}$")
    axes[1].axvline(0, color="#999999", ls="--", lw=.8)
    axes[1].legend(frameon=False)
    fig.tight_layout()
    fig.savefig(figures / "optimization.png", dpi=220)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8.1, 3.2))
    names = list(calibration["models"])
    indices = np.arange(len(names))
    ax.bar(indices - .18, [calibration["models"][name]["rmse"] for name in names], width=.36, label="全样本拟合", color="#106a8a")
    ax.bar(indices + .18, [calibration["models"][name]["held_block_rmse"] for name in names], width=.36, label="模型选择留出块", color="#ca9860")
    ax.set(xticks=indices, xticklabels=["单常数", "边界混合", "辐射修正", "双节点", "平滑双节点", "分区模型"], ylabel=r"RMSE / $^{\circ}\mathrm{C}$")
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(figures / "model_comparison.png", dpi=220)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    draw(parser.parse_args().run.resolve())
