#!/usr/bin/env python3
"""Generate category markdown from processed papers JSON."""

import argparse
import json
import re
import os
import sys
from collections import OrderedDict
from pathlib import Path

import requests

CATEGORY_ANCHOR_PROMPT = """你是文档结构专家。根据以下中文分类名称，为每个分类生成一个简短的英文锚点标识符。

要求：
- 锚点格式为 "cat-" 后接小写英文短横线分隔的词组
- 简短（不超过20字符）
- 与中文语义对应

参考映射：
- 核心算法与优化 → cat-core-opt
- 渲染加速与压缩 → cat-render-accel
- 新视角合成 → cat-nvs
- 动态场景与4D → cat-dynamic-4d
- 语义分割与场景理解 → cat-seg-understand
- 视觉定位 → cat-visloc
- 安全与版权 → cat-security
- 几何与表面重建 → cat-geo-recon
- 生成式模型 → cat-generative
- 风格迁移与编辑 → cat-style-edit
- 逆渲染与光照 → cat-inverserender
- 流媒体与编码 → cat-streaming
- 自动驾驶应用 → cat-autodrive
- SLAM与建图 → cat-slam
- 机器人仿真与具身智能 → cat-robotics
- 数字人与人体重建 → cat-human
- 无线与射频传播 → cat-rf
- 领域应用 → cat-domain-app
- 其他应用 → cat-other-app

返回严格的 JSON 对象，键为中文名称，值为锚点：
{{"核心算法与优化": "cat-core-opt", "新类别": "cat-new-cat"}}

分类名称：
{categories}
"""


def call_llm_for_anchors(api_url: str, api_key: str, model: str, categories: list[str]) -> dict[str, str]:
    """Call LLM to generate anchor IDs for category names."""
    user_msg = CATEGORY_ANCHOR_PROMPT.format(categories="\n".join(f"- {c}" for c in categories))
    try:
        resp = requests.post(
            api_url,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": "返回严格的 JSON，不要包含任何其他文本。"},
                    {"role": "user", "content": user_msg},
                ],
                "temperature": 0.1,
                "max_tokens": 32768,
            },
            timeout=30,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        raw = re.sub(r"^```json\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"```\s*$", "", raw)
        return json.loads(raw.strip())
    except Exception as e:
        print(f"  LLM anchor generation failed: {e}, using fallback", file=sys.stderr)
        return {}


def fallback_anchor(name: str) -> str:
    """Generate anchor from Chinese category name via hash-based slug."""
    import hashlib
    h = hashlib.md5(name.encode()).hexdigest()[:8]
    return f"cat-{h}"


def compute_category_anchors(categories: list[str], api_url: str | None = None, api_key: str | None = None, model: str = "Qwen3.6-27B-FP8") -> dict[str, str]:
    """Get anchor mapping for all categories, with LLM call or fallback."""
    if api_url and api_key and categories:
        result = call_llm_for_anchors(api_url, api_key, model, categories)
        for cat in categories:
            if cat not in result:
                result[cat] = fallback_anchor(cat)
        return result
    return {cat: fallback_anchor(cat) for cat in categories}


def papers_by_category(papers: list[dict]) -> OrderedDict:
    """Group papers by category. A paper can appear in multiple categories."""
    groups = OrderedDict()
    for p in papers:
        cats = p.get("categories", [])
        if not cats:
            cats = ["其他应用"]
        for cat in cats:
            if cat not in groups:
                groups[cat] = []
            groups[cat].append(p)
    return groups


def render_category_table_row(paper: dict, monthly_file: str) -> str:
    """Render a single table row for a category."""
    date = paper.get("submitted_date", "")
    short = paper.get("short_name", paper["title"][:20])
    anchor = paper.get("_anchor", paper["title"].lower())
    arxiv_id = paper["arxiv_id"]
    version = paper.get("version", "")
    keywords = paper.get("keywords", "")

    # Version-tagged arxiv link
    arxiv_link = f"{arxiv_id}{version}" if version and version != "v1" else arxiv_id

    # Link to monthly doc anchor
    paper_link = f"[{short}]({monthly_file}#{anchor})"

    if paper.get("is_highlight"):
        hl = paper.get("highlight_info", "")
        hl_tag = f" {hl}" if hl else ""
        paper_link = f"★ **[{short}]({monthly_file}#{anchor})**"
        keywords = f"{keywords}{hl_tag}" if keywords else hl_tag

    return f"| {date} | {paper_link} | {arxiv_link} | {keywords} |"


def render_category_section(cat_name: str, cat_anchor: str, papers: list[dict], cat_num: str, monthly_file: str) -> str:
    """Render a full category section."""
    parts = []
    parts.append(f"## {cat_num}、{cat_name} {{#{cat_anchor}}}")
    parts.append("")
    parts.append("| 日期 | 论文 | arXiv | 关键词 |")
    parts.append("|------|------|-------|--------|")

    for paper in papers:
        parts.append(render_category_table_row(paper, monthly_file))

    parts.append("")
    parts.append("---")
    parts.append("")

    return "\n".join(parts)


def generate_category_summary(_cat_name: str, papers: list[dict]) -> str:
    """Generate a summary paragraph for the category using paper keywords."""
    kw_set = set()
    for p in papers:
        kws = p.get("keywords", "")
        if kws:
            for kw in kws.split(","):
                kw = kw.strip()
                if kw:
                    kw_set.add(kw)

    kw_str = "、".join(list(kw_set)[:8])
    return f"**概要**: 本类论文涉及{kw_str}等研究方向，共 {len(papers)} 篇。"


def render_category_doc(papers: list[dict], title: str, month: str, monthly_file: str, api_url: str = "", api_key: str = "", model: str = "Qwen3.6-27B-FP8") -> str:
    """Render the full category markdown document."""
    cat_groups = papers_by_category(papers)
    categories = list(cat_groups.keys())

    # Generate anchors via LLM or fallback
    cat_anchors = compute_category_anchors(categories, api_url, api_key, model)

    parts = []
    parts.append(f"# {title} 分类索引 ({month})")
    parts.append("")
    parts.append(f"> 基于 `{monthly_file}` 中收集的论文，按研究方向细分类。")
    parts.append("> ★ 表示被顶会/顶刊录用。")
    parts.append("")

    # Table of contents
    parts.append("## 目录")
    parts.append("")
    parts.append(f"- [{title} 分类索引 ({month})](#{title}-分类索引-{month})")
    parts.append("  - [目录](#目录)")

    chinese_nums = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
                    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十"]

    for i, cat in enumerate(categories):
        num = chinese_nums[i] if i < len(chinese_nums) else str(i + 1)
        anchor = cat_anchors[cat]
        parts.append(f"  - [{num}、{cat}](#{anchor})")

    parts.append("  - [统计概览](#统计概览)")
    parts.append("")
    parts.append("---")

    # Category sections
    total_papers_count = 0
    stats_rows = []

    for i, cat in enumerate(categories):
        num = chinese_nums[i] if i < len(chinese_nums) else str(i + 1)
        anchor = cat_anchors[cat]
        group = cat_groups[cat]

        if not group:
            continue

        section = render_category_section(cat, anchor, group, num, monthly_file)
        summary = generate_category_summary(cat, group)
        section = section.rstrip()
        section = section.replace("\n---", f"\n{summary}\n\n---", 1)

        parts.append("")
        parts.append(section)
        total_papers_count += len(group)
        stats_rows.append(f"| {cat} | {len(group)} |")

    # Stats overview
    parts.append("")
    parts.append("## 统计概览")
    parts.append("")
    parts.append("| 类别 | 论文数 |")
    parts.append("|------|--------|")
    for row in stats_rows:
        parts.append(row)
    parts.append(f"| **合计** | **{total_papers_count}** |")

    return "\n".join(parts) + "\n"


def main():
    parser = argparse.ArgumentParser(description="Generate category markdown from processed papers")
    parser.add_argument("--input", required=True, help="Processed JSON file path")
    parser.add_argument("--output", required=True, help="Output category markdown file path")
    parser.add_argument("--title", required=True, help="Document title (e.g., '3D Gaussian Splatting 论文跟踪')")
    parser.add_argument("--month", required=True, help="Month label (e.g., '2026年5月')")
    parser.add_argument("--monthly-file", default="", help="Monthly tracking file name for cross-links")
    parser.add_argument("--api-url", default=os.environ.get("PAPER_API_URL", ""), help="LLM API URL for anchor generation")
    parser.add_argument("--api-key", default=os.environ.get("PAPER_API_KEY", ""), help="API key")
    parser.add_argument("--model", default="Qwen3.6-27B-FP8", help="Model name")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        papers = json.load(f)

    # Sort by date descending
    papers.sort(key=lambda p: p.get("submitted_date", ""), reverse=True)

    # Compute anchors if missing
    current_date = None
    date_index = 0
    for paper in papers:
        if paper.get("submitted_date") != current_date:
            current_date = paper.get("submitted_date")
            date_index = 0
        date_index += 1
        paper.setdefault("_date_index", date_index)
        if "_anchor" not in paper:
            slug = re.sub(r"[^a-z0-9]+", "-", paper["title"].lower())
            slug = re.sub(r"-+", "-", slug).strip("-")
            paper["_anchor"] = f"{date_index}-{slug}"
        if "short_name" not in paper:
            match = re.match(r"^([A-Za-z0-9@#$%&+{}\-]+(?:\s+[A-Za-z0-9@#$%&+{}\-]+)?)\s*[:.–]", paper["title"])
            paper["short_name"] = match.group(1).strip() if match and len(match.group(1)) <= 20 else paper["title"][:20]

    # Generate category doc
    monthly_file = args.monthly_file or "3dgs_" + args.month.replace("年", "-").replace("月", "") + ".md"

    result = render_category_doc(papers, args.title, args.month, monthly_file, args.api_url, args.api_key, args.model)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result)

    cat_groups = papers_by_category(papers)
    print(f"Category doc written to {args.output}")
    print(f"Categories: {len(cat_groups)}")
    for cat, group in cat_groups.items():
        print(f"  - {cat}: {len(group)} papers")


if __name__ == "__main__":
    main()
