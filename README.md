# 道路养护规范更新 Skill

[![Tests](https://github.com/FreeLiiives/road-maintenance-standards-skill/actions/workflows/ci.yml/badge.svg)](https://github.com/FreeLiiives/road-maintenance-standards-skill/actions/workflows/ci.yml)
[![Weekly update](https://github.com/FreeLiiives/road-maintenance-standards-skill/actions/workflows/weekly-update.yml/badge.svg)](https://github.com/FreeLiiives/road-maintenance-standards-skill/actions/workflows/weekly-update.yml)

面向道路病害识别课题的轻量规范知识库与 Codex Skill：**查询规范 → 追溯官方依据 → 检查版本变化 → 关联病害检索词**。

Python 3.10+，仅用标准库，Windows / Linux / macOS 可运行；无需 GPU、数据库服务或 API Key。YOLO 训练环境与此项目相互独立。

## 能做什么

- **离线检索**：按编号、中文关键词、旧版编号或项目 YOLO 标签查询。
- **官方证据目录**：首版核对 9 条交通运输部规范公告/实施通知，保存编号、日期、来源和核对时间。
- **每周自动监测**：GitHub Actions 每周一北京时间 **09:17** 抓取官方列表和公告，提交候选记录与报告；电脑无需开机。
- **变化与失败可追踪**：区分新发现、首次建立基线、正文变化、访问失败；保留上次成功记录和 Git 历史。
- **关系导出**：输出有来源支持的替代关系，以及明确标为项目索引的主题关系。
- **Skill 调用**：提供可安装的 `SKILL.md`、界面元数据和引用核验流程。

> 这是周期性公告监测与检索工具，不是实时、完整或经官方认证的现行标准数据库。自动候选不会直接变成“现行标准”。首版自动覆盖交通运输部部分公开列表，国家标准平台与地方标准仍需按需求人工核验。

## 快速运行

下载仓库 ZIP 并解压，或执行：

```powershell
git clone https://github.com/FreeLiiives/road-maintenance-standards-skill.git
cd road-maintenance-standards-skill
python skills/road-maintenance-standards/scripts/standards.py search "裂缝"
python skills/road-maintenance-standards/scripts/standards.py search "Pothole" --json
python skills/road-maintenance-standards/scripts/standards.py search "JTG/T E61-2014"
python skills/road-maintenance-standards/scripts/standards.py list
python skills/road-maintenance-standards/scripts/standards.py graph
```

若 Windows 没有 `python` 命令，可换成 `py -3` 或已安装的 Python 可执行文件完整路径。所有命令在仓库根目录执行。

更新与测试：

```powershell
python skills/road-maintenance-standards/scripts/standards.py sync
python -m unittest discover -s tests -v
```

`sync` 退出码 **0** 表示本轮目标均成功读取；**2** 表示覆盖不完整。请查看 [最新报告](skills/road-maintenance-standards/reports/latest.md)，不要将失败理解为“没有更新”。网络阻断、TLS 错误或网页改版时离线查询仍可用。

## 安装为个人 Skill

```powershell
python scripts/install_skill.py
```

安装到 `$CODEX_HOME/skills/road-maintenance-standards`，未设置 `CODEX_HOME` 时使用 `~/.codex/skills/road-maintenance-standards`。如果目标已存在，安装器会停止，避免覆盖个人修改；先查看差异并另行备份再更新。重新打开 Codex 会话后输入：

```text
$road-maintenance-standards 帮我查询坑槽识别对应的公路养护规范，说明实施时间并给出官方依据。
```

也可以把 `skills/road-maintenance-standards` 整个目录手动复制到个人 skills 目录。安装副本不会自动随 GitHub 更新；在副本运行 `scripts/standards.py sync` 可同步候选，目录内容更新则需要获取新版仓库。

## 首版目录

公告元数据人工核对日期：**2026-10-01**。下表“实施日期”来自公告，不代表已穷尽核验所有后续修订或废止记录。

| 标准 | 名称 | 公告实施日期 |
| --- | --- | --- |
| JTG 5110-2023 | 公路养护技术标准 | 2024-03-01 |
| JTG 5142-2019 | 公路沥青路面养护技术规范 | 2019-09-01 |
| JTG 5210-2018 | 公路技术状况评定标准 | 2019-05-01 |
| JTG 5421-2018 | 公路沥青路面养护设计规范 | 2019-03-01 |
| JTG H30-2015 | 公路养护安全作业规程 | 2015-06-01 |
| JTG/T 5310-2026 | 公路养护决策技术规范 | 2026-06-01 |
| JTG/T 5212-2026 | 公路路面技术状况自动化检测规程 | 2026-09-01 |
| JTG/T 5410-2026 | 公路养护工程设计规范 | 2026-11-01 |
| JTG/T 5111-2026 | 公路冬季养护技术规范 | 2026-09-01 |

每条证据链接见 [catalog.json](skills/road-maintenance-standards/data/catalog.json)。例如 5212-2026 的公告明确说明旧版 JTG/T E61-2014 同时废止；5410-2026 在首版核对日属于**已发布、尚未实施**，没有仅凭名称推断它替代 5421-2018。

## 自动更新怎么工作

```mermaid
flowchart LR
  A[官方公告列表] --> B[候选发现]
  B --> C[公告正文指纹与访问记录]
  C --> D[每周报告与 Git 历史]
  D --> E[核对原文、日期、替代关系]
  E --> F[已核对元数据目录]
  F --> G[Skill 查询与引用]
  H[YOLO 类别] --> I[检索词映射]
  I --> G
```

每次读取两个配置列表、9 条初始目录来源及最多 20 条候选详情。只抓取允许域名的 HTTPS 页面，保留证书校验；限制响应大小、超时和重试。列表无法识别时报告失败。抓取范围不是全网搜索，附件变化也不等于公告正文变化；详见 [证据与维护说明](skills/road-maintenance-standards/references/evidence.md)。

GitHub 的 [Actions 页面](https://github.com/FreeLiiives/road-maintenance-standards-skill/actions) 可查看测试、手动执行 **Weekly standards update → Run workflow**。工作流仅写入候选监测记录与报告，不改已核对规范目录。使用内置 `GITHUB_TOKEN`，无需自己提交令牌。仓库规则若禁止直接推送，会明确报错，报告仍作为运行附件保存。

计划任务可能延迟；公开仓库长期无活动时也可能被暂停，需在 Actions 中检查并恢复，见 [GitHub schedule 文档](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。首次发布会通过代码推送触发试运行。

## 与 YOLO 课题如何衔接

项目类别 `Crack / Manhole / Net / Pothole / Patch-Crack / Patch-Net / Patch-Pothole / Other` 映射到检索关键词，见 [映射表](skills/road-maintenance-standards/data/yolo-labels.json)。例如 `Pothole → 坑槽 → 路况评定/路面养护/自动化检测规范入口`。

检测类别不是标准病害等级。计算 PCI、确定损坏程度或制定养护措施，还需要真实尺寸、标定、面积/长度、路面类型、现场检测和具体标准条文。`Manhole` 不自动视为病害，当前目录没有井盖专项规范；`Other` 不做无依据推断。

课题展示可表述为：**构建可追溯的道路养护规范元数据知识库，按周监测权威公告，并将道路病害识别类别关联到规范检索入口。** 不宜宣称全网实时同步、自动法律效力认定、完整知识图谱复现或由检测框直接生成规范级养护决策。

## 设计参考与许可

Yang et al. (2022), *Development and application of a field knowledge graph and search engine for pavement engineering*, Scientific Reports 12, 7796. [DOI: 10.1038/s41598-022-11604-y](https://doi.org/10.1038/s41598-022-11604-y)。本项目借鉴知识组织与领域检索思路，采用轻量目录和关系索引，没有复现论文的模型或实验。

原创代码与说明采用 [MIT](LICENSE)。官方标准、网页和论文保留原权利；仓库不分发标准全文、训练图片或模型权重。
