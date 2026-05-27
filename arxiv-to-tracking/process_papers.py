#!/usr/bin/env python3
"""Process arxiv papers JSON: translate abstract, extract summary, detect highlights."""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

SYSTEM_PROMPT = """你是学术论文摘要处理专家。你需要完成六个任务：
1. 提取论文的短名称（short_name）：从标题提取简称，通常是冒号前的核心词（如 "PanoWorld"、"SurfSplat"），若无可提取简称则用首词，不超过15字符
2. 将论文摘要翻译为中文（80-150字，简洁准确）
3. 提取一句话概述（15-30字，用于目录表格，包含核心方法与创新点）
4. 判断该论文是否被顶会/顶刊录用
5. 为论文分类（categories）：从参考类别中选出论文所属的一个或多个类别名称。一篇论文可属于多个类别。
6. 提取关键词（keywords）：3-5个中文关键词，概括论文核心技术点，用逗号分隔

顶会/顶刊范围：CVPR、ICCV、ECCV、NeurIPS、ICML、ICLR、SIGGRAPH、SIGGRAPH Asia、Eurographics、RSS、ICRA、IROS、ACM MM、DAC、ISCA。Highlight/Oral/Spotlight 子类别也标记。

仅在论文的 comments 或 abstract 中**明确标注**了录用信息时才标记为亮点论文。
仅出现会议名称但没说"录用"、"accepted"、"to appear"等，不要标记。

参考类别（从中选择，也可新增）：
- 核心算法与优化、渲染加速与压缩、新视角合成、动态场景与4D
- 语义分割与场景理解、视觉定位、安全与版权、几何与表面重建
- 生成式模型、风格迁移与编辑、逆渲染与光照、流媒体与编码
- 自动驾驶应用、SLAM与建图、机器人仿真与具身智能
- 数字人与人体重建、无线与射频传播、领域应用、其他应用

返回严格的 JSON，不要包含任何其他文本：
{"short_name": "...", "cn_abstract": "...", "summary": "...", "is_highlight": true/false, "highlight_info": "CVPR'26", "categories": ["核心算法与优化", "几何与表面重建"], "keywords": "密度控制, 强化学习, 基元优化"}
"""


def call_llm(api_url: str, api_key: str, model: str, paper: dict) -> dict | None:
    """Call LLM API to process a single paper."""
    user_msg = (
        f"标题: {paper['title']}\n"
        f"类别: {paper['category']}\n"
        f"Comments: {paper.get('comments', '')}\n"
        f"摘要: {paper['abstract'][:1500]}"
    )
    resp = requests.post(
        api_url,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
            "temperature": 0.3,
            "max_tokens": 32768,
        },
        timeout=3600,
    )
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"].strip()
    raw = re.sub(r"^```json\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"```\s*$", "", raw)
    return json.loads(raw.strip())


def extract_short_name(title: str) -> str:
    """Extract short paper name from title."""
    match = re.match(r"^([A-Za-z0-9@#$%&+{}\-]+(?:\s+[A-Za-z@#$%&+{}\-]+)?)\s*[:.–]", title)
    if match and len(match.group(1)) <= 20:
        return match.group(1).strip()
    first_word = title.split()[0].rstrip(":.") if title.split() else title[:20]
    if len(first_word) <= 15:
        return first_word
    return title[:30] + "..."


def make_anchor(title: str, index: int) -> str:
    """Generate markdown anchor from paper title."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return f"{index}-{slug}"


def process_paper(api_url: str, api_key: str, model: str, idx: int, paper: dict) -> dict:
    """Process a single paper with LLM, with retries."""
    for attempt in range(3):
        try:
            res = call_llm(api_url, api_key, model, paper)
            if res is not None:
                return res
        except Exception as e:
            print(f"  [{idx}] Attempt {attempt+1}/3 failed: {e}", file=sys.stderr)
            if attempt < 2:
                time.sleep(1 * (attempt + 1))
    return {
        "short_name": extract_short_name(paper["title"]),
        "cn_abstract": paper["abstract"],
        "summary": paper["abstract"][:50] + "...",
        "is_highlight": False,
        "highlight_info": "",
        "categories": [],
        "keywords": "",
    }


def main():
    parser = argparse.ArgumentParser(description="Process arxiv papers with LLM")
    parser.add_argument("--input", required=True, help="Input JSON file path")
    parser.add_argument("--output", required=True, help="Output processed JSON file path")
    parser.add_argument("--api-url", default=os.environ.get("PAPER_API_URL", ""), help="LLM API URL")
    parser.add_argument("--api-key", default=os.environ.get("PAPER_API_KEY", ""), help="API key")
    parser.add_argument("--model", default="Qwen3.6-27B-FP8", help="Model name")
    parser.add_argument("--batch-size", type=int, default=32, help="Concurrent batch size")
    args = parser.parse_args()

    if not args.api_url:
        print("Error: --api-url or PAPER_API_URL env var required", file=sys.stderr)
        sys.exit(1)
    if not args.api_key:
        print("Error: --api-key or PAPER_API_KEY env var required", file=sys.stderr)
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        papers = json.load(f)

    print(f"Processing {len(papers)} papers...")
    results = {}
    with ThreadPoolExecutor(max_workers=args.batch_size) as executor:
        futures = {
            executor.submit(process_paper, args.api_url, args.api_key, args.model, i, p): i
            for i, p in enumerate(papers)
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                results[idx] = future.result()
                print(f"  [{idx+1}/{len(papers)}] Done: {papers[idx]['title'][:50]}")
            except Exception as e:
                print(f"  [{idx+1}/{len(papers)}] Failed: {e}", file=sys.stderr)
                results[idx] = {
                    "short_name": extract_short_name(papers[idx]['title']),
                    "cn_abstract": papers[idx]["abstract"],
                    "summary": papers[idx]["abstract"][:50] + "...",
                    "is_highlight": False,
                    "highlight_info": "",
                    "categories": [],
                    "keywords": "",
                }

    for idx, result in results.items():
        papers[idx]["cn_abstract"] = result["cn_abstract"]
        papers[idx]["summary"] = result["summary"]
        papers[idx]["is_highlight"] = result["is_highlight"]
        papers[idx]["highlight_info"] = result.get("highlight_info", "")
        papers[idx]["short_name"] = result.get("short_name", extract_short_name(papers[idx]['title']))
        papers[idx]["categories"] = result.get("categories", [])
        papers[idx]["keywords"] = result.get("keywords", "")

    papers.sort(key=lambda p: p.get("submitted_date", ""), reverse=True)

    current_date = None
    date_index = 0
    for paper in papers:
        if paper.get("submitted_date") != current_date:
            current_date = paper.get("submitted_date")
            date_index = 0
        date_index += 1
        paper["_date_index"] = date_index
        paper["_anchor"] = make_anchor(paper["title"], date_index)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)

    print(f"Done! Saved {len(papers)} papers to {args.output}")
    print(f"Highlight papers: {sum(1 for p in papers if p.get('is_highlight'))}")


if __name__ == "__main__":
    main()
