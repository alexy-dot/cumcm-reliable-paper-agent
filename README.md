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
| 写作与追溯 | 论文主张绑定结果 ID；台账数值直接匹配 JSON 产物，阻止“程序算2、论文依据写3” |
| 修改与交付 | 检测已通过阶段的内容变化；记录人工评阅；封存文件清单与哈希 |

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

## 验证依据

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖文件尾部损坏、稀疏表格、编码、数值不一致、伪独立复核、版本漂移和封存变更。GitHub Actions 在 Python 3.10、3.12、3.13 上执行测试与示例。

[真实输入集成记录](benchmarks/reports/intake-2020d.json)：2020 D的30个工作表、1,796,765行数据，与 openpyxl 独立读取及 math.fsum 计算的行数、缺失数、范围和均值全部一致。复跑需要自备题目附件并安装 openpyxl：

```bash
python3 benchmarks/verify_intake.py --source-dir /path/2020/D --output runs/intake
```

原始竞赛资料、个人运行目录和环境文件不随仓库分发。

## 当前边界

当前是国奖导向的辅助工具，**尚未通过完整陌生题限时验收，不保证奖项**。通用题型求解、自动 PDF 成稿和正式比赛规则校验仍在完善。

数据读取不等于题意理解；第一存储行暂作表头候选，图示、单位、日期和公式缓存需结合原文解释。数值一致不证明两种算法真正独立；人工签核字段不认证身份，文件哈希也不是防篡改认证。项目会明确区分合成示例、历史回放和陌生题验收。

历年论文研究范围见 `project_manifest.json`；这是继承的研究记录，本发布版未重新审计，不声称45篇全部研究完成。
