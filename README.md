# 国赛可信论文 Agent

**把题意变成模型，把计算变成有据可查的中文论文。**

面向全国大学生数学建模竞赛（CUMCM）的 Codex Skill 与 Python 校验引擎。
适合赛前训练、团队建模协作和论文复核。核心运行只需 Python 3.10+，无需 API 密钥或第三方库。

[快速体验](#快速体验) · [历史题实测](benchmarks/README.md) · [工作流](skill/cumcm-reliable-paper/SKILL.md) · [贡献](CONTRIBUTING.md) · [MIT License](LICENSE)

## 能做什么

| 环节 | 实际能力 |
| --- | --- |
| 读题与读数据 | 冻结原始文件；提取 DOCX 段落；全量检查 CSV/XLSX 行数、缺失、重复和异常值 |
| 建模与复核 | 独立输出比对；分组验证、公平基线、内层选模与划分敏感性工具 |
| 写作与追溯 | 论文主张绑定结果 ID；台账直接匹配 JSON 产物；从同一稿件生成 Markdown 与嵌入字体的PDF |
| 修改与交付 | 检测内容变化；核对2026官方PDF/ZIP格式、代码附录、AI声明与详情；保留评阅及文件指纹 |

```text
题面与附件 → 模型与代码 → 独立数值复核 → 论文草稿 → 人工评阅与封存
```

## 快速体验

克隆后，在仓库根目录运行：

```bash
python3 skill/cumcm-reliable-paper/scripts/cumcm_agent.py doctor
python3 examples/production/run.py --output runs/demo
```

示例分别用穷举和动态规划求得最优利润 **121**，生成`runs/demo/paper/main.md`、计算记录和可独立复算的`artifacts/submission-package/support.zip`。输出目录须不存在；这是合成示例，真实人工评阅仍待完成。

解压支撑包后运行`python3 solver.py --output reproduced.json`，两种方法应再次得到121。

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

## 先检查运行环境

`doctor`实际导入所选环境的依赖，不自动安装、修改运行记录或下载宏包：

```bash
python3 skill/cumcm-reliable-paper/scripts/cumcm_agent.py doctor --profile statistics
python3 skill/cumcm-reliable-paper/scripts/cumcm_agent.py doctor --profile paper \
  --smoke --latex-compiler /path/to/tectonic --cache-dir /path/to/tex-cache
```

配置可选`core`、`paper`、`statistics`、`submission`或`all`。`paper --smoke`用项目排版器试编译中文、公式、表格及源码字符；仅找到编译器不算编译通过。空缓存可能需要先正常编译以获取宏包。

完整环境可一次安装。以下为已测Python 3.12组合（macOS/Linux）：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-all.txt -c constraints-python312.txt
.venv/bin/python skill/cumcm-reliable-paper/scripts/cumcm_agent.py doctor --profile all
```

之后统一用`.venv/bin/python`运行回放，无需切换排版解释器。版本约束仅记录已测直接依赖，不是跨平台锁文件。轻量使用仍可只安装`requirements-paper.txt`、`requirements-submission.txt`或统计模块依赖。

[统一环境实测](benchmarks/reports/unified-runtime.json)：三类历史题均由同一Python完成求解到PDF，核对范围内的数值与此前发布记录一致。导入超时会标为未确认，不误报为缺少依赖。

数学论文还需要Tectonic或XeLaTeX及中文字体，Python安装不会代装它们。各题回放命令和适用边界见[实测说明](benchmarks/README.md)。

## 三类历史题实测

| 题目 | 已展示的能力 | 结果 |
| --- | --- | --- |
| 2020 A 炉温曲线 | 参数辨识、约束优化、连续积分复核、同预算对照 | [论文](benchmarks/reports/furnace-2020a-paper.pdf) · [记录](benchmarks/reports/furnace-2020a-summary.json) |
| 2021 D 连铸切割 | 在线决策、精确尾坯分配、独立网络流与连续下界 | [论文](benchmarks/reports/casting-2021d-paper.pdf) · [独立复算包](benchmarks/reports/casting-2021d-support.zip) |
| 2021 B 乙醇偶合 | 组合外预测、嵌套选模、开放温度边界与实验设计 | [论文](benchmarks/reports/ethanol-2021b-paper.pdf) · [记录](benchmarks/reports/ethanol-2021b-summary.json) |

[完整结果、反例与回放命令](benchmarks/README.md)保留初稿失败记录和适用边界；历史重分析不等于新盲测。

## 验证与交付

```bash
python3 -m unittest discover -s tests -v
```

GitHub Actions覆盖Python 3.10/3.12/3.13、数值内核、分组统计、PDF和提交检查。缺少可选依赖时，相应测试明确跳过。程序测试通过不等于科学结论通过。

`paper_structure.py`按题目合同检查各问章节覆盖；`submission-check`按已核对的2026全国规则检查PDF/ZIP、源码附录和AI材料。命令及来源见[台账与交付说明](skill/cumcm-reliable-paper/references/artifact-contracts.md)。仍需核对最新赛区通知、内容真实性和实际人工复核。

## 当前边界

当前是国奖导向的辅助工具，**已覆盖炉温优化、在线切割与实验数据统计建模三类历史题，但尚未证明国奖级可靠性，不保证奖项**。首次限时稿未通过论文验收，后续修订不补算为盲测成绩。通用题型求解、赛区差异与更广泛的独立评阅仍在完善。规则摘录的权利归原发布者，代码适用MIT许可证。

数据读取不等于题意理解；第一存储行暂作表头候选，图示、单位、日期和公式缓存需结合原文解释。数值一致不证明两种算法真正独立；人工签核字段不认证身份，文件哈希也不是防篡改认证。项目会明确区分合成示例、历史回放和陌生题验收。

历年论文研究范围见 `project_manifest.json`；这是继承的研究记录，本发布版未重新审计，不声称45篇全部研究完成。
