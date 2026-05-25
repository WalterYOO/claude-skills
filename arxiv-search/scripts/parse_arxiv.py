#!/usr/bin/env python3
"""Parse arxiv search results HTML page and output paper info as JSON.

Usage:
    uv run --with parsel --with parse parse_arxiv.py <html-file>

Output:
    JSON array to stdout by default.
"""
import json
import re
import sys
from datetime import datetime
from parsel import Selector


def parse_paper(item):
    """Extract paper info from a single <li class='arxiv-result'> element."""
    # arXiv ID from link href
    arxiv_href = item.css("p.list-title a::attr(href)").get("")
    arxiv_id = arxiv_href.split("/")[-1] if arxiv_href else ""

    # Version from link text (e.g. "arXiv:2605.21112" or "arXiv:2406.14978v2")
    arxiv_link_text = item.css("p.list-title a::text").get("")
    ver_match = re.search(r"(\d+\.\d+)(v\d+)", arxiv_link_text)
    version = ver_match.group(2) if ver_match else "v1"

    # Title - strip tags, keep inline span text
    title_block = item.css("p.title.is-5").get("") or ""
    title = re.sub(r"<[^>]+>", "", title_block).strip()
    title = re.sub(r"\s+", " ", title)

    # Authors - extract <a> text values
    author_links = item.css("p.authors a::text").getall()
    authors = ", ".join(a.strip() for a in author_links if a.strip())

    # Category tags
    categories = item.css("div.tags span.tag::text").getall()
    category = ", ".join(c.strip() for c in categories if c.strip())

    # Abstract - prefer abstract-full, fallback to abstract-short
    abstract = ""
    abs_full_el = item.css("span.abstract-full")
    if abs_full_el:
        abstract = abs_full_el.getall()[0] if abs_full_el.getall() else ""
        abstract = re.sub(r"<a[^>]*>.*?</a>", "", abstract, flags=re.DOTALL)
        abstract = re.sub(r"<[^>]+>", "", abstract).strip()
        abstract = re.sub(r"\s+", " ", abstract)
    else:
        abs_short_el = item.css("span.abstract-short")
        if abs_short_el:
            abstract = abs_short_el.getall()[0] if abs_short_el.getall() else ""
            abstract = re.sub(r"<a[^>]*>.*?</a>", "", abstract, flags=re.DOTALL)
            abstract = re.sub(r"<[^>]+>", "", abstract).strip()
            abstract = re.sub(r"\s+", " ", abstract)

    # Submission date - from p.is-size-7 that has "Submitted" (not comments)
    submitted_date = ""
    submitted_p = item.css("p.is-size-7:not(p.comments)").get("") or ""
    date_match = re.search(r">Submitted</span>\s*([\d]+\s+[\w]+,\s*[\d]{4})", submitted_p)
    if date_match:
        raw_date = date_match.group(1).strip()
        try:
            dt = datetime.strptime(raw_date, "%d %B, %Y")
            submitted_date = dt.strftime("%Y-%m-%d")
        except ValueError:
            pass

    # Comments - only from p.comments
    comments = ""
    comments_el = item.css("p.comments span.has-text-grey-dark")
    if comments_el:
        comments = comments_el.get("") or ""
        comments = re.sub(r"<[^>]+>", "", comments).strip()
        comments = re.sub(r"\s+", " ", comments)

    return {
        "arxiv_id": arxiv_id,
        "version": version,
        "title": title,
        "authors": authors,
        "category": category,
        "abstract": abstract,
        "submitted_date": submitted_date,
        "comments": comments,
    }


def main():
    html_path = sys.argv[1] if len(sys.argv) > 1 else None
    output_path = None
    for i, arg in enumerate(sys.argv[2:], 2):
        if arg in ("--output", "-o"):
            output_path = sys.argv[i + 1] if i + 1 < len(sys.argv) else None

    if not html_path:
        print("Usage: parse_arxiv.py <html-file> [--output <json-file>]", file=sys.stderr)
        sys.exit(1)

    with open(html_path, encoding="utf-8") as f:
        sel = Selector(text=f.read())

    papers = []
    for item in sel.css("li.arxiv-result"):
        papers.append(parse_paper(item))

    json_str = json.dumps(papers, ensure_ascii=False, indent=2)

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json_str)
    else:
        print(json_str)


if __name__ == "__main__":
    main()
