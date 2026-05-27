# arxiv-to-tracking

将 arXiv 论文 JSON 数据转换为月度跟踪和分类 Markdown 文档的 Claude Code 技能。

与 `arxiv-search` 配合使用：先搜索论文生成 JSON，再用此技能完成摘要翻译、概述提取、亮点判断、论文分类，最终生成规范的月度跟踪文档。

## 工作流程

```
arxiv-search → papers.json → process_papers.py → papers_processed.json
                                                   ↓
                                    ┌──────────────┴──────────────┐
                                    ↓                             ↓
                           generate_tracking.py           generate_category.py
                                    ↓                             ↓
                           月度跟踪 Markdown 文档           分类索引 Markdown 文档
```

### 阶段一：LLM 处理

对每篇论文并行调用 LLM，一次性完成六个子任务：短名称提取、摘要翻译、概述提取、亮点判断、分类、关键词生成。

### 阶段二：月度文档生成

按日期降序排列，生成带目录表格和详细论文区块的月度跟踪文档。支持增量更新。

### 阶段三：分类文档生成

按研究方向对论文分类，生成带交叉链接的分类索引文档，底部附统计概览。

## 使用

```bash
export PAPER_API_URL="http://your-llm-server:5000/v1/chat/completions"
export PAPER_API_KEY="sk-your-api-key-here"
export UV_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"

# 阶段一：LLM 处理
uv run --with requests python process_papers.py \
  --input papers.json --output papers_processed.json

# 阶段二：生成月度文档
uv run python generate_tracking.py \
  --input papers_processed.json --output 3dgs_2026-05.md \
  --title "3D Gaussian Splatting 论文跟踪" --month "2026年5月"

# 增量更新
uv run python generate_tracking.py \
  --input papers_processed.json --output 3dgs_2026-05.md \
  --title "3D Gaussian Splatting 论文跟踪" --month "2026年5月" \
  --existing 3dgs_2026-05.md

# 阶段三：生成分类文档
uv run --with requests python generate_category.py \
  --input papers_processed.json --output 3dgs_category_2026-05.md \
  --title "3D Gaussian Splatting 论文跟踪" --month "2026年5月"
```

## 依赖

- Python 3.10+
- `uv`（用于运行和依赖管理）
- 兼容 OpenAI API 格式的 LLM 服务

## 文件

| 文件 | 说明 |
|------|------|
| `process_papers.py` | LLM 处理阶段（摘要翻译、分类等） |
| `generate_tracking.py` | 月度文档生成（支持增量更新） |
| `generate_category.py` | 分类文档生成 |
| `SKILL.md` | Claude Code 技能定义 |
