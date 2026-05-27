#!/usr/bin/env python3
"""Generate monthly tracking markdown from processed papers JSON."""

import argparse
import json
import re
from collections import OrderedDict
from pathlib import Path


def compute_short_name(title: str) -> str:
    """Extract short paper name from title."""
    match = re.match(r"^([A-Za-z0-9@#$%&+{}\-]+(?:\s+[A-Za-z0-9@#$%&+{}\-]+)?)\s*[:.–]", title)
    if match and len(match.group(1)) <= 20:
        return match.group(1).strip()
    return title[:30] + "..."


def compute_anchor(title: str, index: int) -> str:
    """Generate markdown anchor from paper title."""
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return f"{index}-{slug}"


def ensure_paper_fields(papers: list[dict]) -> None:
    """Compute _anchor and short_name if missing (when JSON is used directly without process_papers.py)."""
    current_date = None
    date_index = 0
    for paper in papers:
        if paper.get("submitted_date") != current_date:
            current_date = paper.get("submitted_date")
            date_index = 0
        date_index += 1
        paper["_date_index"] = date_index
        if "_anchor" not in paper:
            paper["_anchor"] = compute_anchor(paper["title"], date_index)
        if "short_name" not in paper:
            paper["short_name"] = compute_short_name(paper["title"])


def papers_by_date(papers: list[dict]) -> OrderedDict:
    """Group papers by date, preserving sort order (desc)."""
    groups = OrderedDict()
    for p in papers:
        date = p.get("submitted_date", "unknown")
        if date not in groups:
            groups[date] = []
        groups[date].append(p)
    return groups


def render_table_row(date: str, paper: dict) -> str:
    """Render a single table row for the directory."""
    short = paper.get("short_name", compute_short_name(paper["title"]))
    anchor = paper.get("_anchor", paper["title"].lower())
    arxiv_id = paper["arxiv_id"]
    category = paper.get("category", "")
    summary = paper.get("summary", "")

    if paper.get("is_highlight"):
        hl = paper.get("highlight_info", "")
        # Avoid duplicating highlight info if already in summary
        if hl and hl not in summary:
            hl_tag = f" ({hl})"
        else:
            hl_tag = ""
        name_cell = f"★ **[{short}](#{anchor})**"
        summary_cell = f"{summary}{hl_tag}"
    else:
        name_cell = f"[{short}](#{anchor})"
        summary_cell = summary

    return f"| {date} | {name_cell} | [{arxiv_id}](https://arxiv.org/abs/{arxiv_id}) | {category} | {summary_cell} |"


def render_paper_section(paper: dict, index: int) -> str:
    """Render a single paper detail section."""
    title = paper["title"]
    arxiv_id = paper["arxiv_id"]
    authors = paper.get("authors", "")
    category = paper.get("category", "")
    version = paper.get("version", "")
    comments = paper.get("comments", "")
    cn_abstract = paper.get("cn_abstract", "")

    # Version-tagged arxiv link
    if version and version != "v1":
        arxiv_link = f"[{arxiv_id}{version}](https://arxiv.org/abs/{arxiv_id})"
    else:
        arxiv_link = f"[{arxiv_id}](https://arxiv.org/abs/{arxiv_id})"

    lines = [
        f"",
        f"### {index}. {title}",
        f"",
        f"- **arXiv**: {arxiv_link}",
        f"- **作者**: {authors}",
        f"- **类别**: {category}",
    ]

    # Highlight note
    if paper.get("is_highlight") and paper.get("highlight_info"):
        hl = paper["highlight_info"]
        lines.append(f"- **备注**: {hl} 录用")

    # Comments field
    if comments and not paper.get("is_highlight"):
        lines.append(f"- **备注**: {comments}")

    lines.append("")
    lines.append(f"**摘要**: {cn_abstract}")

    return "\n".join(lines)


def render_tracking_doc(papers: list[dict], title: str, month: str) -> str:
    """Render the full tracking markdown document."""
    date_groups = papers_by_date(papers)

    parts = []
    parts.append(f"# {title}")
    parts.append("")
    parts.append(f"> {month}")
    parts.append("")

    # Check if there are highlight papers
    has_highlights = any(p.get("is_highlight") for p in papers)
    if has_highlights:
        parts.append("> 注：★ 表示被顶会录用。")
        parts.append("")

    parts.append("## 目录")
    parts.append("")
    parts.append("| 日期 | 论文 | arXiv | 类别 | 概述 |")
    parts.append("|------|------|-------|------|------|")

    for date, group in date_groups.items():
        for paper in group:
            parts.append(render_table_row(date, paper))

    # Paper sections
    for date, group in date_groups.items():
        parts.append("")
        parts.append(f"## {date}")
        for idx, paper in enumerate(group, 1):
            parts.append("")
            parts.append(render_paper_section(paper, idx))
            parts.append("")
            parts.append("---")

    return "\n".join(parts) + "\n"


def parse_existing_papers(existing_md: str) -> dict:
    """Parse existing tracking doc to extract arxiv_ids already present."""
    existing = {}
    current_arxiv = None
    in_abstract = False

    for line in existing_md.split("\n"):
        # Match arxiv line
        m = re.match(r"- \*\*arXiv\*\*: \[(\d+\.\d+)", line)
        if m:
            current_arxiv = m.group(1)
            in_abstract = False
            continue
        # Match abstract line
        if re.match(r"\*\*摘要\*\*:", line) and current_arxiv:
            in_abstract = True
            existing[current_arxiv]["cn_abstract"] = line.replace("**摘要**: ", "", 1).strip()
            continue
        if in_abstract and line.strip():
            existing[current_arxiv]["cn_abstract"] += " " + line.strip()
            continue

    return existing


def merge_with_existing(papers: list[dict], existing_md: str, _title: str, month: str) -> str:
    """Merge new papers with existing doc content, inserting at correct date boundaries."""
    existing_ids = set(re.findall(r"- \*\*arXiv\*\*: \[(\d+\.\d+)", existing_md))

    new_papers = [p for p in papers if p["arxiv_id"] not in existing_ids]
    if not new_papers:
        print("No new papers to insert.")
        return existing_md

    print(f"Merging {len(new_papers)} new papers (skipping {len(papers) - len(new_papers)} existing)...")

    new_date_groups = papers_by_date(new_papers)
    result = existing_md

    table_lines = []
    in_table = False
    all_new_dates = set(new_date_groups.keys())

    for line in result.split("\n"):
        if re.match(r"\| 日期 \| 论文 \|", line):
            in_table = True
            table_lines.append(line)
            continue
        if re.match(r"\|------\|------\|", line):
            table_lines.append(line)
            continue
        if in_table:
            # Check if this is a data row
            row_date_m = re.match(r"\| (\d{4}-\d{2}-\d{2}) \|", line)
            if row_date_m:
                row_date = row_date_m.group(1)
                # Insert new date rows before this row if they should come first
                dates_to_insert = sorted(
                    [d for d in all_new_dates if d >= row_date],
                    reverse=True,
                )
                for nd in dates_to_insert:
                    for paper in new_date_groups[nd]:
                        table_lines.append(render_table_row(nd, paper))
                    all_new_dates.discard(nd)
            table_lines.append(line)
            # Detect end of table (empty line or non-table line after data rows)
            if not re.match(r"\|", line) and len(table_lines) > 2:
                # Insert remaining dates
                for nd in sorted(all_new_dates, reverse=True):
                    for paper in new_date_groups[nd]:
                        table_lines.append(render_table_row(nd, paper))
                    all_new_dates.discard(nd)
                in_table = False
                # Add highlights note if needed and not present
                if any(p.get("is_highlight") for p in new_papers):
                    hl_note = "> 注：★ 表示被顶会录用。"
                    if hl_note not in "\n".join(table_lines[-5:]):
                        # Insert after month line, before table
                        pass  # We'll handle this separately
        else:
            table_lines.append(line)

    result = "\n".join(table_lines)

    # Now insert body sections
    # Find the last date section in existing doc and insert after it
    # (or at correct boundary if new dates are between existing dates)
    body_parts = []
    inserted_dates = set()
    current_section_date = None

    lines = result.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        date_m = re.match(r"^## (\d{4}-\d{2}-\d{2})$", line)
        if date_m:
            current_section_date = date_m.group(1)

            # Before writing this section, check if new dates should go here
            dates_to_insert = sorted(
                [d for d in new_date_groups.keys()
                 if d < current_section_date and d not in inserted_dates]
            )
            for nd in reversed(dates_to_insert):
                body_parts.append(render_date_section(nd, new_date_groups[nd]))
                body_parts.append("")
                inserted_dates.add(nd)

        body_parts.append(line)

        # Detect end of a date section (--- separator followed by blank or new section)
        if line.strip() == "---" and current_section_date:
            # Check if next non-blank line is a new date section or end
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            next_date_m = re.match(r"^## (\d{4}-\d{2}-\d{2})$", lines[j]) if j < len(lines) else None

            # Insert dates that come after this section's date
            if not next_date_m or next_date_m.group(1) < current_section_date:
                # We're at end, insert remaining
                dates_to_insert = sorted(
                    [d for d in new_date_groups.keys()
                     if d <= current_section_date and d not in inserted_dates],
                    reverse=True,
                )
                for nd in dates_to_insert:
                    body_parts.append("")
                    body_parts.append(render_date_section(nd, new_date_groups[nd]))
                    body_parts.append("")
                    inserted_dates.add(nd)

        i += 1

    # Insert any remaining dates at the end
    for nd in sorted(set(new_date_groups.keys()) - inserted_dates):
        body_parts.append("")
        body_parts.append(render_date_section(nd, new_date_groups[nd]))
        body_parts.append("")

    result = "\n".join(body_parts)

    # Add highlight note if needed
    if any(p.get("is_highlight") for p in new_papers):
        hl_note = "> 注：★ 表示被顶会录用。"
        if hl_note not in result:
            # Insert after month line
            result = result.replace(f"> {month}\n", f"> {month}\n\n{hl_note}\n", 1)

    return result


def render_date_section(date: str, group: list[dict]) -> str:
    """Render a full date section including header and papers."""
    parts = [f"## {date}"]
    for idx, paper in enumerate(group, 1):
        parts.append("")
        parts.append(render_paper_section(paper, idx))
        parts.append("")
        parts.append("---")
    return "\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Generate tracking markdown from processed papers")
    parser.add_argument("--input", required=True, help="Processed JSON file path")
    parser.add_argument("--output", required=True, help="Output markdown file path")
    parser.add_argument("--title", required=True, help="Document title")
    parser.add_argument("--month", required=True, help="Month label (e.g., '2026年5月')")
    parser.add_argument("--existing", default=None, help="Existing doc path for incremental update")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        papers = json.load(f)

    # Sort and compute anchors/short_names
    papers.sort(key=lambda p: p.get("submitted_date", ""), reverse=True)
    ensure_paper_fields(papers)

    if args.existing and Path(args.existing).exists():
        print(f"Incremental update mode: reading existing doc from {args.existing}")
        with open(args.existing, "r", encoding="utf-8") as f:
            existing_md = f.read()
        result = merge_with_existing(papers, existing_md, args.title, args.month)
    else:
        result = render_tracking_doc(papers, args.title, args.month)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result)

    print(f"Tracking doc written to {args.output}")
    print(f"Total papers: {len(papers)}")


if __name__ == "__main__":
    main()
