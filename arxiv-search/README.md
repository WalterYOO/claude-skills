# arxiv-search

Claude Code skill for searching [arXiv](https://arxiv.org) papers by keywords and date range.

## What it does

- Searches arXiv via the advanced search interface
- Automatically handles pagination (fetches all pages)
- Parses HTML results into structured JSON (title, authors, abstract, category, etc.)
- Respects arXiv rate limits (≤1 req/s, no concurrency)

## Usage in Claude Code

Once installed, just ask Claude Code naturally:

> 搜一下昨天的 3D Gaussian Splatting 论文
> Find recent arxiv papers about NeRF
> 帮我查一下 arxiv 上周有没有 diffusion model 相关的论文

## Output format

```json
{
  "arxiv_id": "2605.21112",
  "version": "v1",
  "title": "...",
  "authors": "Author A, Author B, ...",
  "category": "cs.CV, cs.GR",
  "abstract": "...",
  "submitted_date": "2026-05-20",
  "comments": "ICLR 2026"
}
```

## Dependencies

- `curl` for fetching pages
- Python with `parsel`, `parse` (handled via `uv run --with`)

## Install

```bash
cp -r arxiv-search ~/.claude/skills/arxiv-search
```

Restart Claude Code.

## Rate limits

ArXiv enforces strict rate limits. This skill handles them automatically but be aware:

| Limit | Rule |
|-------|------|
| Per second | ≤ 1 request (≥3s interval enforced) |
| Per minute | ≤ 40 requests |
| Concurrency | None allowed |
| Violation | 1–24h IP ban |
