#!/usr/bin/env python3
"""Extract pagination info from an arxiv search results page.

Usage:
    uv run --with parsel get_pagination.py <html-file>

Output:
    JSON object to stdout:
    {
        "has_more": true/false,
        "all_starts": [0, 50, 100],
        "remaining_starts": [50, 100]
    }

    has_more:       whether a visible Next button exists
    all_starts:     all start= values found in pagination page links
    remaining_starts: start= values greater than 0 (pages not yet fetched)
"""
import json
import sys
from urllib.parse import parse_qs, urlparse

from parsel import Selector


def get_pagination_info(html_path: str) -> dict:
    """Return pagination metadata from a single HTML file."""
    with open(html_path, encoding="utf-8") as f:
        sel = Selector(text=f.read())

    nav = sel.css("nav[aria-label='pagination']")
    if not nav:
        return {"has_more": False, "all_starts": [], "remaining_starts": []}

    # Extract all page links with their start= values
    page_links = nav.css("ul.pagination-list a.pagination-link")
    all_starts = set()
    for link in page_links:
        href = link.css("::attr(href)").get("")
        if href:
            params = parse_qs(urlparse(href).query)
            if "start" in params:
                all_starts.add(int(params["start"][0]))

    # Check if Next button exists and is NOT invisible
    next_btn = nav.css("a.pagination-next")
    has_more = False
    if next_btn:
        classes = next_btn.css("::attr(class)").get("")
        has_more = "is-invisible" not in classes

    remaining = sorted(s for s in all_starts if s > 0)
    return {
        "has_more": has_more,
        "all_starts": sorted(all_starts),
        "remaining_starts": remaining,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: get_pagination.py <html-file>", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(get_pagination_info(sys.argv[1]), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
