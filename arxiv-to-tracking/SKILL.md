---
name: arxiv-to-tracking
description: 将 arxiv-search 产生的 JSON 数据转换为月度论文跟踪和分类 markdown 文档。支持摘要翻译、概述提取、亮点判断、论文分类、关键词生成，可增量更新。
metadata:
  type: project
---

# arxiv-to-tracking Skill

## 概述

本 skill 将 `/arxiv-search` 产生的 JSON 论文数据自动转换为符合项目规范的月度跟踪文档和分类文档。

整个流程分为三个步骤：
1. **LLM 处理阶段** — 对每篇论文调用 LLM 完成摘要翻译、概述提取、亮点判断、分类、关键词生成
2. **月度文档生成阶段** — 将处理后的 JSON 按模板格式渲染为月度跟踪 Markdown
3. **分类文档生成阶段** — 将处理后的 JSON 按研究方向归类，生成分类索引 Markdown

所有逻辑通过 Python 脚本实现，使用 `uv` 管理 Python 环境。

## 输入

- `arxiv-search` 产生的 JSON 文件（数组，每篇论文包含 `arxiv_id`、`title`、`authors`、`category`、`abstract`、`submitted_date`、`comments`、`version` 等字段）

## 输出

- 处理后的中间 JSON 文件（包含 `cn_abstract`、`summary`、`is_highlight`、`highlight_info`、`categories`、`keywords` 等额外字段）
- 最终月度跟踪 Markdown 文档
- 分类索引 Markdown 文档

## 工作流程

### 阶段一：LLM 处理（`process_papers.py`）

```
输入 JSON → 逐篇论文 → LLM API → 输出 JSON
```

对每篇论文并行调用 LLM，一次性完成六个子任务：

1. **短名称提取** — 从标题提取简称（如 "PoseGaussian"），用于目录表格
2. **摘要翻译** — 将英文 abstract 翻译为简洁的中文摘要（约 80-150 字）
3. **概述提取** — 从 abstract 提取一句话概述（约 15-30 字），用于目录表格
4. **亮点判断** — 根据 title、abstract、comments 判断是否为顶会/顶刊录用论文
5. **分类** — 从参考类别中选择一个或多个类别名称（`categories` 数组）
6. **关键词** — 提取 3-5 个中文关键词，用逗号分隔

LLM 返回的 JSON 结构：
```json
{
  "short_name": "PoseGaussian",
  "cn_abstract": "中文翻译...",
  "summary": "一句话概述...",
  "is_highlight": true/false,
  "highlight_info": "CVPR'26",
  "categories": ["核心算法与优化", "几何与表面重建"],
  "keywords": "密度控制, 强化学习, 基元优化"
}
```

**亮点论文判断标准**（内置于 prompt）：
- 计算机视觉：CVPR、ICCV、ECCV
- 机器学习：NeurIPS、ICML、ICLR
- 图形学：SIGGRAPH、SIGGRAPH Asia、Eurographics
- 机器人：RSS、ICRA、IROS
- 多媒体：ACM MM
- 设计自动化：DAC、ISCA
- Highlight/Oral/Spotlight 子类别也标记
- 仅在论文明确标注录用信息时标记

### 阶段二：月度文档生成（`generate_tracking.py`）

```
处理后的 JSON + 现有文档(可选) → 月度跟踪 Markdown 文档
```

1. 按 `submitted_date` 降序排序论文
2. 按日期分组
3. 生成目录表格（包含锚点链接）
4. 生成每篇论文的详细信息区块
5. 亮点论文在表格中标记 `★ **` 并在概述末尾标注会议信息

### 阶段三：分类文档生成（`generate_category.py`）

```
处理后的 JSON → 分类索引 Markdown 文档
```

1. 读取每篇论文的 `categories` 和 `keywords` 字段
2. 按类别分组（一篇论文可出现在多个类别）
3. 为每个类别生成表格，论文链接指向月度文件的锚点
4. 亮点论文在类别表格中同样标记 `★ **`，关键词列末尾标注会议信息
5. 生成类别概要段落，汇总该类别下的论文关键词
6. 文档底部生成统计概览表格

类别锚点（`{#cat-xxx}`）可通过 LLM 生成，也可使用内置哈希回退方案。

### 增量更新模式

当目标月度文档已存在时：
- 读取现有文档中的论文（通过 arxiv_id 去重）
- 仅插入新论文，不覆盖已有内容
- 表格行和正文区块同步插入到正确的日期边界

## 使用方式

### 在 Claude Code 中调用

Agent 应按以下步骤执行：

```bash
# 设置清华PyPI镜像源
export UV_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"

# 运行 LLM 处理阶段（--with requests 自动安装依赖）
uv run --with requests python process_papers.py \
  --input /path/to/papers.json \
  --output /path/to/papers_processed.json \
  --api-url http://your-llm-server:5000/v1/chat/completions \
  --api-key sk-your-api-key-here

# 运行月度文档生成阶段
uv run python generate_tracking.py \
  --input /path/to/papers_processed.json \
  --output /path/to/3dgs_2026-05.md \
  --title "3D Gaussian Splatting 论文跟踪" \
  --month "2026年5月"

# 增量更新模式（--existing 指向已有文档）
uv run python generate_tracking.py \
  --input /path/to/papers_processed.json \
  --output /path/to/3dgs_2026-05.md \
  --title "3D Gaussian Splatting 论文跟踪" \
  --month "2026年5月" \
  --existing /path/to/3dgs_2026-05.md

# 运行分类文档生成阶段
uv run --with requests python generate_category.py \
  --input /path/to/papers_processed.json \
  --output /path/to/3dgs_category_2026-05.md \
  --title "3D Gaussian Splatting 论文跟踪" \
  --month "2026年5月" \
  --monthly-file "3dgs_2026-05.md"
```

### CLI 参数

`process_papers.py`:
| 参数 | 必填 | 说明 |
|------|------|------|
| `--input` | 是 | 输入 JSON 文件路径 |
| `--output` | 是 | 输出处理后 JSON 文件路径 |
| `--api-url` | 否 | LLM API 地址（默认读取环境变量 `PAPER_API_URL`） |
| `--api-key` | 否 | API Key（默认读取环境变量 `PAPER_API_KEY`） |
| `--model` | 否 | 模型名称（默认 `Qwen3.6-27B-FP8`） |
| `--batch-size` | 否 | 并发批处理大小（默认 5） |

`generate_tracking.py`:
| 参数 | 必填 | 说明 |
|------|------|------|
| `--input` | 是 | 处理后的 JSON 文件路径 |
| `--output` | 是 | 输出 Markdown 文件路径 |
| `--title` | 是 | 文档标题（如 "3D Gaussian Splatting 论文跟踪"） |
| `--month` | 是 | 月份标注（如 "2026年5月"） |
| `--existing` | 否 | 现有文档路径，用于增量更新 |

`generate_category.py`:
| 参数 | 必填 | 说明 |
|------|------|------|
| `--input` | 是 | 处理后的 JSON 文件路径 |
| `--output` | 是 | 输出分类 Markdown 文件路径 |
| `--title` | 是 | 文档标题（如 "3D Gaussian Splatting 论文跟踪"） |
| `--month` | 是 | 月份标注（如 "2026年5月"） |
| `--monthly-file` | 否 | 月度跟踪文件名，用于论文链接（默认自动生成） |
| `--api-url` | 否 | LLM API 地址，用于类别锚点生成（默认读取环境变量 `PAPER_API_URL`） |
| `--api-key` | 否 | API Key（默认读取环境变量 `PAPER_API_KEY`） |
| `--model` | 否 | 模型名称（默认 `Qwen3.6-27B-FP8`） |

## 环境配置

可通过 `--api-url` 和 `--api-key` 参数直接传递，或设置环境变量：

```bash
export PAPER_API_URL="http://your-llm-server:5000/v1/chat/completions"
export PAPER_API_KEY="sk-your-api-key-here"
export UV_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
```

`UV_INDEX_URL` 用于让 `uv run` 使用清华 PyPI 镜像源加速依赖下载。

## 文件结构

```
.claude/skills/arxiv-to-tracking/
├── SKILL.md                  # 本文件
├── process_papers.py         # LLM 处理阶段
├── generate_tracking.py      # 月度文档生成阶段
└── generate_category.py      # 分类文档生成阶段
```
