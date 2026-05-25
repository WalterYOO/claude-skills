---
name: arxiv-search
description: Search arxiv for papers by keywords and date range. Use this skill whenever the user asks to search, find, or look up arxiv papers — e.g. "搜一下昨天的 3DGS 论文", "find recent papers on X", "arxiv 上有没有关于 Y 的新论文", "get me the latest on Z from arxiv". Also use when the user wants to track paper progress, check what's new in a research area, or browse arxiv search results. Use this even if the user doesn't explicitly mention "arxiv" but clearly wants to find academic papers on a topic.
---

Search arxiv for papers and extract structured information (title, authors, abstract, etc.) as JSON output.

## Rate Limiting (CRITICAL)

Arxiv enforces strict rate limits — violating them causes IP bans (1–24 hours, repeat offenders get permanent bans).

| 限制 | 规则 |
|------|------|
| 每秒 | ≤ 1 次请求，**必须间隔 ≥ 3 秒** |
| 每分钟 | ≤ 40 次 |
| 单次结果 | max_results ≤ 2000，建议分页 size ≤ 100 |
| 并发 | 不允许并发/多线程 |
| 违规 | 临时封禁 1–24h，反复违规永久封 IP |

**所有 curl 请求之间必须加 `sleep 3`**。翻页时逐页获取，每页之间都要等待。
**绝对不能并发请求**。

## Workflow

### Step 1: Construct the search URL

Build an arxiv advanced search URL from the user's keywords and date range:

```
https://arxiv.org/search/advanced?
  advanced=&
  terms-0-operator=AND&
  terms-0-term=<关键词 URL encoded>&
  terms-0-field=all&
  classification-physics_archives=all&
  classification-include_cross_list=include&
  date-year=&
  date-filter_by=date_range&
  date-from_date=<起始日期 YYYY-MM-DD>&
  date-to_date=<结束日期 YYYY-MM-DD>&
  date-date_type=submitted_date&
  abstracts=show&
  size=100&
  order=-announced_date_first
```

参数说明：

| 参数 | 说明 |
|------|------|
| `terms-0-term` | 搜索关键词（如 `3D+Gaussian+Splatting`） |
| `terms-0-field` | `all` 表示在所有字段搜索 |
| `date-filter_by` | `date_range` 表示按日期范围过滤 |
| `date-from_date` / `date-to_date` | 日期范围。**注意**：两者不能相等。若只需查单天（如 5 月 20 日），设为 `from=2026-05-20 & to=2026-05-21` |
| `date-date_type` | `submitted_date` 按提交日期 |
| `size` | 每页结果数，最大 `100` |
| `start` | 分页偏移量，默认为 `0`（第一页）。第二页设为 `start=<size>`，第三页 `start=<size>*2`，以此类推 |
| `order` | `-announced_date_first` 按日期降序 |

If the user doesn't specify a date range, ask or default to today's date (single day search).

### Step 2: Fetch the page

Use curl to save the HTML to a temp file:

```bash
curl -s -o /tmp/arxiv_search_$(date +%Y%m%d_%H%M%S).html "<SEARCH_URL>"
```

Verify the file was fetched:
```bash
wc -c /tmp/arxiv_search_*.html
```

### Step 3: Check for pagination and fetch all pages

After fetching the first page, use the bundled `get_pagination.py` script to extract pagination info via parsel:

```bash
uv run --with parsel \
  <skill-path>/scripts/get_pagination.py \
  /tmp/arxiv_search_page_1.html
```

Output example:
```json
{
    "has_more": true,
    "all_starts": [0, 50, 100],
    "remaining_starts": [50, 100]
}
```

- `has_more`: whether a visible Next button exists (false when results are few and no pagination is needed)
- `all_starts`: all `start=` values from pagination page links
- `remaining_starts`: `start=` values greater than 0 (pages not yet fetched)

**If `has_more` is false**: only one page, skip to Step 4.

**If `has_more` is true**: fetch each remaining page based on `remaining_starts`:

```bash
for start_val in 50 100; do
  sleep 3  # rate limit: 3s between requests
  curl -s -o /tmp/arxiv_search_page_${start_val}.html "<SEARCH_URL>&start=${start_val}"
  uv run --with parsel \
    <skill-path>/scripts/get_pagination.py \
    /tmp/arxiv_search_page_${start_val}.html
done
```

Check each newly fetched page for further pagination (the last page should return `has_more: false`). If it still shows `has_more: true`, continue fetching until exhausted.

Verify all pages:
```bash
wc -c /tmp/arxiv_search_page_*.html
```

**Important**: the `size` parameter controls how many results per page. Common values: `50` or `100` (max). The `start=` offset increments by `size`.

### Step 4: Parse all pages and combine

Run the bundled parser script on each HTML file separately (outputs JSON to stdout):

```bash
# Single page (no pagination)
uv run --with parsel --with parse \
  <skill-path>/scripts/parse_arxiv.py \
  /tmp/arxiv_search_page_1.html

# Multiple pages — parse each, then combine
for f in /tmp/arxiv_search_page_*.html; do
  uv run --with parsel --with parse \
    <skill-path>/scripts/parse_arxiv.py \
    "$f" --output "${f%.html}.json"
done

# Merge all JSON files, deduplicate by arxiv_id
uv run --with python -c "
import json, glob, sys
seen = set()
papers = []
for f in sorted(glob.glob('/tmp/arxiv_search_page_*.json')):
    for p in json.loads(open(f).read()):
        if p['arxiv_id'] not in seen:
            seen.add(p['arxiv_id'])
            papers.append(p)
json.dump(papers, open('/tmp/arxiv_papers.json', 'w'), ensure_ascii=False, indent=2)
print(f'Total unique papers: {len(papers)}')
"
```

脚本输出 JSON 数组，字段：
- `arxiv_id` - 论文编号（如 `2605.21112`）
- `version` - 版本（如 `v1`, `v2`）
- `title` - 完整标题
- `authors` - 作者列表，逗号分隔
- `category` - 类别，逗号分隔（如 `cs.CV, cs.GR`）
- `abstract` - 完整摘要
- `submitted_date` - 提交日期 `YYYY-MM-DD`
- `comments` - 备注（如会议录用信息）

如果用户要求保存到文件，加 `--output` 参数：

```bash
uv run --with parsel --with parse \
  <skill-path>/scripts/parse_arxiv.py \
  /tmp/arxiv_search_page_*.html \
  --output /tmp/arxiv_papers.json
```

### Step 5: Present results

Read the combined JSON output (`/tmp/arxiv_papers.json` for multi-page, or stdout for single-page) and present a summary table to the user:

```
Found N papers (from M pages):

| # | Title | arXiv | Date | Category | Notes |
|---|-------|-------|------|----------|-------|
| 1 | ... | [id](link) | YYYY-MM-DD | cs.CV | ... |
```

The full JSON data is saved at the output path for further processing.

## Dependencies

- `curl` - fetching web pages
- Python with `parsel`, `parse` - installed via `uv run --with`
