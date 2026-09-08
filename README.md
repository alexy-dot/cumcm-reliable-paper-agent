# 国赛可信论文 Agent

**从原始题面到有据可查的论文，把容易漏掉的错误挡在交稿前。**

面向全国大学生数学建模竞赛（CUMCM）的 Codex Skill 与 Python 校验引擎。
适合赛前训练、团队建模协作和论文复核。核心运行只需 Python 3.10+，无需 API 密钥或第三方库。

[快速体验](#快速体验) · [工作流](skill/cumcm-reliable-paper/SKILL.md) · [贡献](CONTRIBUTING.md) · [MIT License](LICENSE)

## 能做什么

| 环节 | 实际能力 |
| --- | --- |
| 读题与读数据 | 冻结原始文件；提取 DOCX 段落；全量检查 CSV/XLSX 行数、缺失、重复和异常值 |
| 建模与复核 | 记录题意、约束、假设；提前确定容差，逐项比较两份独立计算输出 |
| 写作与追溯 | 论文主张绑定结果 ID；台账直接匹配 JSON 产物；从同一稿件生成 Markdown 与嵌入字体的PDF |
| 修改与交付 | 检测内容变化；核对2026官方PDF/ZIP格式、代码附录、AI声明与详情；保留评阅及文件指纹 |

```text
题面与附件 → 模型与代码 → 独立数值复核 → 论文草稿 → 人工评阅与封存
```

## 快速体验

克隆后在仓库根目录运行：

```bash
python3 examples/production/run.py --output runs/demo
```

约一秒内完成一套合成生产计划：读取冻结数据，分别运行穷举和动态规划，核对最优利润 **121**，输出：

- `runs/demo/paper/main.md`：由计算结果生成的中文论文草稿；
- `runs/demo/artifacts/`：两种算法各自的 JSON 输出；
- `runs/demo/demo_validation.json`：校验结果，真实人工评阅仍待完成。

输出目录必须为空。示例不会伪造审批或将演示结果标成正式提交稿；它不是国赛盲测成绩。

## 看一次完整题目实测

2020 A“炉温曲线”的项目内首次实测，在约30分钟内完成四问和671条采样输出，29项独立数值检查通过。原8页稿的结构、字体与公式排版不合格，先前的排版通过记录已撤回。当前14页修订稿采用摘要独页、逐问分析、模型假设、符号说明与分问求解结构，并使用宋体、黑体和TeX数学公式。数值验收与论文修订分别记录。

[训练稿 PDF](benchmarks/reports/furnace-2020a-paper.pdf) · [验收记录与边界](benchmarks/reports/furnace-2020a-summary.json)

该留档仍是训练稿，尚未补齐正式提交所需的完整代码附录、AI详情及实际人工审查，不能将数值验收代替论文和规则验收。

![炉温曲线与峰值对齐比较](benchmarks/reports/furnace-2020a-curves.png)

自备原始题面与附件后可一键回放（约一分钟，取决于机器）：

可选依赖建议装在项目虚拟环境：先运行 `python3 -m venv .venv`，macOS/Linux再用 `source .venv/bin/activate`，随后执行下面的命令。

```bash
python3 -m pip install -r benchmarks/furnace_2020a/requirements.txt -r requirements-paper.txt
python3 benchmarks/furnace_2020a/run_all.py --source-dir /path/2020/A --output runs/furnace
```

数学论文需要Tectonic或XeLaTeX（macOS可用 `brew install tectonic`），未在PATH中时加 `--latex-compiler /path/to/tectonic`。首次编译需要下载宏包；`--cache-dir`可指定缓存目录。回放不等于新盲测，真实人工评阅与正式提交审核仍待完成。

## 用于自己的题目

将 `skill/cumcm-reliable-paper` 整个目录放入个人 Codex skills 目录，或在 Codex 中指定该目录下的 `SKILL.md`：

> 使用 cumcm-reliable-paper，读取我提供的题面和附件，先核对要求，再建模、复核并生成论文。

命令行也可单独使用：

```bash
python3 skill/cumcm-reliable-paper/scripts/cumcm_agent.py init \
  --problem /path/problem.docx --attachment /path/data.xlsx \
  --output /path/run --title "题目"
python3 skill/cumcm-reliable-paper/scripts/cumcm_agent.py status /path/run
```

`inspect` 重建输入审计；`validate` 检查当前或指定阶段；`advance` 推进；`signoffs` 显示评阅对象；`seal` 封存。字段和迁移说明统一见[台账合同](skill/cumcm-reliable-paper/references/artifact-contracts.md)。

提交前，可按已核实的2026全国规则检查PDF论文与ZIP支撑包：

```bash
python3 -m pip install -r requirements-submission.txt
python3 skill/cumcm-reliable-paper/scripts/cumcm_agent.py submission-check /path/run \
  --year 2026 --ai-used yes --paper paper/main.pdf --support support.zip \
  --identity-term "学校名称" --report artifacts/submission_report.json
```

来源：[官方格式规范](https://www.mcm.edu.cn/html_cn/node/4cd596519c9eb9fbd866398f6df0caa3.html)、[AI工具使用规定](https://www.mcm.edu.cn/upload_cn/node/785/Glps6mBh6563c55c45300fede72ddbf6eb33d3a8.pdf)，2026-09-08核对。机械检查通过仍需核对赛区通知、内容真实性与实际人工复核；Word/RAR需另行检查，不会冒充已通过。

## 验证依据

```bash
python3 -m unittest discover -s tests -v
```

核心测试覆盖文件尾部损坏、稀疏表格、编码、数值不一致、伪独立复核、版本漂移和封存变更。GitHub Actions 在 Python 3.10、3.12、3.13 上执行测试与示例，并分别检查科学计算内核和PDF字体嵌入；缺少可选PDF依赖时，核心测试会明确跳过相应两项。

[真实输入集成记录](benchmarks/reports/intake-2020d.json)：2020 D的30个工作表、1,796,765行数据，与 openpyxl 独立读取及 math.fsum 计算的行数、缺失数、范围和均值全部一致。复跑需要自备题目附件并安装 openpyxl：

```bash
python3 benchmarks/verify_intake.py --source-dir /path/2020/D --output runs/intake
```

原始竞赛资料、个人运行目录和环境文件不随仓库分发。

## 当前边界

当前是国奖导向的辅助工具，**历史题已完成一次限时成稿实测，但尚未证明国奖级可靠性，不保证奖项**。通用题型求解、赛区差异与更广泛的独立评阅仍在完善。规则摘录的权利归原发布者，代码适用MIT许可证。

数据读取不等于题意理解；第一存储行暂作表头候选，图示、单位、日期和公式缓存需结合原文解释。数值一致不证明两种算法真正独立；人工签核字段不认证身份，文件哈希也不是防篡改认证。项目会明确区分合成示例、历史回放和陌生题验收。

历年论文研究范围见 `project_manifest.json`；这是继承的研究记录，本发布版未重新审计，不声称45篇全部研究完成。
