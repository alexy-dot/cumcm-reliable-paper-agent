# 历史题回放与证据

以下命令均从仓库根目录执行，需自行提供原始题面与附件。历史回放不等于新盲测，数值复核也不替代人工评阅。

## 2020 A：连续模型与约束优化

2020 A“炉温曲线”的项目内首次实测，在约30分钟内完成四问和671条采样输出，29项独立数值检查通过。原8页稿的结构、字体与公式排版不合格，先前的排版通过记录已撤回。当前22页修订稿采用摘要独页、背景与条件—逐问要求的重述、逐问分析、模型假设、符号说明与分问求解结构，并使用宋体、黑体和TeX数学公式。修订补充了完整优化约束、求解设置与同预算算法对照；数值验收与论文修订分别记录。

[训练稿 PDF](reports/furnace-2020a-paper.pdf) · [验收记录与边界](reports/furnace-2020a-summary.json)

第5.2—5.3节给出固定模型下的速度上界推导和温区参数非唯一性解释，配有[可复跑的恒等式与等价方案验证](reports/furnace-2020a-structural-evidence.json)。这些结论以参数可迁移等明确假设为前提，不替代新工况实验。

第5.4、6.1—6.2节比较面积—对称性权衡、候选模型决策差异和256个联合参数情景：[计算记录](reports/furnace-2020a-decision-evidence.json)。它揭示逐参数检验通过的留余量方案仍可能在联合扰动下越界；情景计数不冒充实际失败概率。

第6.3节针对反例重新进行[情景约束设计](reports/furnace-2020a-scenario-design.json)：161组设计参数，冻结候选后再以512组留出参数验证，三组方案均未发生制程越界。结果同时报告速度/面积代价，并明确不保证整个参数盒或实际生产可靠性。

算法是否值得增加，也用实测回答：[同预算对照](reports/furnace-2020a-optimizer-comparison/report.json)在两个优化问题上比较多起点SLSQP、DE和DE后SLSQP。每次2400次模型计算、6个固定种子，36个候选均通过独立连续积分后的严格约束检查；局部法与组合结果近乎相同，未显示增加DE的必要性。协议、逐次结果及失败判定都可复查；结论仅限该模型、起点策略与预算。

该留档仍是训练稿，尚未补齐正式提交所需的完整代码附录、AI详情及实际人工审查，不能将数值验收代替论文和规则验收。

![炉温曲线与峰值对齐比较](reports/furnace-2020a-curves.png)

自备原始题面与附件后可一键回放，包含算法对照（首次TeX下载另计）：

可选依赖建议装在项目虚拟环境：先运行 `python3 -m venv .venv`，macOS/Linux再用 `source .venv/bin/activate`，随后执行下面的命令。

```bash
python3 -m pip install -r benchmarks/furnace_2020a/requirements.txt -r requirements-paper.txt
python3 benchmarks/furnace_2020a/run_all.py --source-dir /path/2020/A --output runs/furnace
```

数学论文需要Tectonic或XeLaTeX（macOS可用 `brew install tectonic`），未在PATH中时加 `--latex-compiler /path/to/tectonic`。首次编译需要下载宏包；`--cache-dir`可指定缓存目录。回放不等于新盲测，真实人工评阅与正式提交审核仍待完成。

已有炉温运行结果时，可单独复跑方法对照，无需重新校准：

```bash
python3 benchmarks/furnace_2020a/optimizer_comparison.py runs/furnace --output runs/optimizer-study
```

输出目录须不存在。先写入固定协议，再执行搜索；独立复核后不重新选解，保留严格可行与数值容差可行两种判定。

## 2021 D：异常通知下的在线切割

[连铸切割训练稿](reports/casting-2021d-paper.pdf)覆盖12种尾坯与三种目标长度下各9次异常决策。尾坯用有理数枚举和凸性分配，在线方案用字典序动态规划；已启动的切口保持不变，未来通知不能提前进入决策。

| 目标长度 | 固定定长切割损失 | 在线调整损失 | 连续材料下界 |
| --- | ---: | ---: | ---: |
| 9.5 m | 76.0 m | 23.8 m | 23.8 m |
| 8.5 m | 68.0 m | 16.0 m | 16.0 m |
| 11.1 m | 88.8 m | 25.9 m | 25.9 m |

[独立网络流验证](reports/casting-2021d/independent.json)核对12种尾坯损失及27次事件的两级目标；在线总损失达到连续下界，提供了比“程序能运行”更直接的最优性依据。结论限定初始切口在0、零切缝及既定异常序列；初始相位改变时结果可能改变，次优先级也不冒充连续全局最优。

[独立复算支撑包](reports/casting-2021d-support.zip) · [全部方案与机器时刻CSV](reports/casting-2021d/event_plans.csv) · [回放边界](reports/casting-2021d-summary.json)

支撑包不依赖仓库目录：解压后安装依赖，运行以下命令即可重新求解、独立验证并比较全部切口与回收区间。论文附录从同一包中的8份完整源码生成。实际解压到仓库外、以Python隔离模式运行的证据见[复算记录](reports/casting-2021d/support_reproduction.json)。

```bash
python3 -m pip install -r requirements.txt
python3 -I reproduce.py --output reproduced
```

加`--paper --latex-compiler /path/to/tectonic`可重建图表、正文及源码附录。输出目录必须不存在。包内保留已核对的题面参数和原PDF指纹，原题需自行提供；复算不会自动重新理解题目，正式AI使用详情与人工审查仍待完成。

```bash
python3 -m pip install -r benchmarks/casting_2021d/requirements.txt -r requirements-paper.txt
python3 benchmarks/casting_2021d/run_all.py \
  --source /path/2021/D/CUMCM2021-D.pdf --output runs/casting
```

数学排版同样需要Tectonic/XeLaTeX及中文字体；支持上述`--latex-compiler`、`--cache-dir`和`--paper-python`参数。该回放是跨题型历史实测，不是严格盲测或正式提交认证。

## 2021 B：实验数据中的模型选择

[乙醇偶合训练稿](reports/ethanol-2021b-paper.pdf)完成21组温度关系、组合外预测、低温候选与五次实验设计。以催化剂组合整体留出，在训练组内部选择参数，比较训练均值、仅温度、岭回归与随机森林。复杂算法的收益随响应变化：

| 按组等权RMSE / 百分点 | 仅温度二次式 | 岭回归 | 随机森林 |
| --- | ---: | ---: | ---: |
| 转化率 | 14.264 | 13.047 | 10.248 |
| C4选择性 | 10.183 | 9.335 | 10.860 |
| C4收率 | 5.905 | 4.758 | 4.429 |

[计算与边界](reports/ethanol-2021b-summary.json) · [全部外层预测及内层选择](reports/ethanol-2021b/statistical_results.json) · [历史练习错误的复核](reports/ethanol-2021b/legacy_audit.json)

[三套额外分组划分](reports/ethanol-2021b/split_sensitivity/report.json)检验了上述排名的稳定性：固定家族中，转化率/收率仍由森林领先，选择性仍由岭回归领先；但森林与仅温度模型的选择性比较发生翻转。原表是单次划分的结果，重复划分范围不是置信区间或新实验成绩。

这次复核纠正了全样本均值基线、逐列打乱依赖配方变量，以及把349.75℃网格候选当作连续最优的问题。严格`T < 350`时，A2经验曲线只有趋近350℃的上确界。最高已测点仍为A3/400℃的44.7281%；不据此承诺新配方或新批次的化学全局最优。

```bash
python3 -m pip install -r benchmarks/ethanol_2021b/requirements.txt -r requirements-paper.txt
python3 benchmarks/ethanol_2021b/run_all.py --source-dir /path/2021/B --output runs/ethanol
```

通用分组比较已放入Skill的`grouped_regression.py`，可用于已审计的数值特征和明确的组编号。历史题重分析不算新盲测；正式源码附录、实验室复验和人工审查仍待完成。

## 大型原始输入审计

[真实输入集成记录](reports/intake-2020d.json)：2020 D的30个工作表、1,796,765行数据，与 openpyxl 独立读取及 math.fsum 计算的行数、缺失数、范围和均值全部一致。复跑需要自备题目附件并安装 openpyxl：

```bash
python3 benchmarks/verify_intake.py --source-dir /path/2020/D --output runs/intake
```

原始竞赛资料、个人运行目录和环境文件不随仓库分发。
