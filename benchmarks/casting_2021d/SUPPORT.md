# 连铸切割：独立复算包

Python 3.10+。先安装依赖，再在解压目录运行：

```bash
python3 -m pip install -r requirements.txt
python3 -I reproduce.py --output reproduced
```

输出目录必须不存在。程序检查包内文件指纹，然后重新计算12种尾坯、27次在线方案、独立网络流验证，以及网格/初始相位敏感性。全部计算完成后才读取`expected-results.json`比较。除运行耗时及其关联文件指纹外，比较完整切口、回收区间、两级目标和状态记录。

`reproduced/reproduction_report.json`记录是否一致；完整切割计划见`reproduced/artifacts/event_plans.csv`。CSV包含一次切割件起止坐标、切断开始/完成/返回时刻、回收区间及废料长度。

`facts.json`是从2021 D原题人工核对得到的参数和明确假设，保留原PDF的SHA-256。原题PDF未分发，本命令复算从该结构化输入开始，不声称重新理解了原题。自备PDF时可添加`--source /path/CUMCM2021-D.pdf`核对指纹。

需要重新生成论文及完整代码附录时：

```bash
python3 -I reproduce.py --output reproduced-paper --paper --latex-compiler /path/to/tectonic
```

需要Tectonic或XeLaTeX及中文字体。macOS使用宋体/黑体，代码使用Menlo；其他系统图表需要SimSun、Noto Serif CJK SC或Source Han Serif SC之一，LaTeX使用Fandol，完整源码中的Unicode符号建议安装DejaVu Sans Mono。首次编译可能下载宏包，`--cache-dir`可指定缓存。排版依赖在另一个Python中时，可加`--paper-python /path/to/python`。

首次复算的Python/NumPy/SciPy版本见`environment.json`。版本或平台可能改变运行耗时、求解器诊断和PDF字节；时间不是科学结果。结果不一致会保留输出并返回非零，不会静默更新参考值。

第一目标的最优性限于声明的初始切口、零切缝和给定异常序列；二级平方偏差仅在各次已知信息和所选网格下优化。此包不包含正式竞赛AI使用详情或团队人工审批。文件指纹用于检查一致性，不构成身份认证、正式提交许可或获奖保证。
