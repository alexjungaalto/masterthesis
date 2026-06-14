#!/usr/bin/env python3
"""
Compile the catalog of available master's thesis topics.

Reads topic proposals from a CSV file (topics.csv) and generates:
  - A summary printed to the console
  - A Markdown file (Topics.md) grouping open topics by research area

This mirrors compile_theses.py: topics.csv is the single source of truth
(hand-edited), and Topics.md is a build artifact regenerated from it.

Usage:
    python compile_topics.py                  # print summary of open topics
    python compile_topics.py --markdown       # also write Topics.md
    python compile_topics.py --all            # include taken/closed topics
"""

import argparse
import csv
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = SCRIPT_DIR / "topics.csv"
DEFAULT_MD = SCRIPT_DIR / "Topics.md"

CONTACT_EMAIL = "alex.jung@aalto.fi"


def load_topics(csv_path: Path) -> list[dict]:
    """Load topic records from a CSV file."""
    topics = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["id"] = int(row["id"])
            topics.append(row)
    return topics


def filter_topics(
    topics: list[dict],
    area: str | None = None,
    status: str | None = None,
    difficulty: str | None = None,
) -> list[dict]:
    """Filter topic records by area, status, or difficulty."""
    result = topics
    if area:
        result = [t for t in result if area.lower() in t["area"].lower()]
    if status:
        result = [t for t in result if t["status"].lower() == status.lower()]
    if difficulty:
        result = [t for t in result if t["difficulty"].lower() == difficulty.lower()]
    return result


def print_summary(topics: list[dict]) -> None:
    """Print a plain-text summary grouped by research area."""
    by_area = {}
    for t in topics:
        by_area.setdefault(t["area"] or "Other", []).append(t)

    for area, records in by_area.items():
        print(f"\n{'='*70}")
        print(f"  {area}  ({len(records)} topics)")
        print(f"{'='*70}")
        for t in records:
            taken = "" if t["status"].lower() == "open" else f"  [{t['status']}]"
            print(f"  {t['id']:>3}. {t['title']}{taken}")
            meta = [t["difficulty"]]
            if t["data_source"]:
                meta.append(f"data: {t['data_source']}")
            print(f"       ({' | '.join(m for m in meta if m)})")
    print()


def generate_markdown(topics: list[dict], output_path: Path) -> None:
    """Write a Markdown catalog of topics grouped by research area."""
    by_area = {}
    for t in topics:
        by_area.setdefault(t["area"] or "Other", []).append(t)

    lines = [
        "# Available Master's Thesis Topics",
        "",
        "Open topics for a master's thesis supervised by "
        "[Alex Jung](https://machinelearningforall.github.io/about/), "
        "Associate Professor for Machine Learning at Aalto University.",
        "",
        "To discuss a topic or propose your own, get in touch — see the contact "
        "links in the [thesis guide](index.md#feedback-and-questions).",
        "",
    ]

    for area, records in by_area.items():
        lines.append(f"## {area}")
        lines.append("")
        for t in records:
            lines.append(f"### {t['title']}")
            lines.append("")

            meta = []
            if t["difficulty"]:
                meta.append(f"**Difficulty:** {t['difficulty']}")
            if t["data_source"]:
                meta.append(f"**Data source:** {t['data_source']}")
            if t["status"].lower() != "open":
                meta.append(f"**Status:** {t['status']}")
            if meta:
                lines.append(" · ".join(meta))
                lines.append("")

            if t["description"]:
                lines.append(t["description"])
                lines.append("")

            if t["url"]:
                lines.append(f"[Read the full proposal]({t['url']})")
                lines.append("")

            subject = t["title"].replace(" ", "%20")
            lines.append(
                f"[Ask about this topic](mailto:{CONTACT_EMAIL}"
                f"?subject=Thesis%20topic:%20{subject})"
            )
            lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Markdown written to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Compile the thesis topic catalog.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Path to topics.csv")
    parser.add_argument("--markdown", action="store_true", help="Generate Topics.md")
    parser.add_argument("--output", type=Path, default=DEFAULT_MD, help="Markdown output path")
    parser.add_argument("--all", action="store_true", help="Include taken/closed topics")
    parser.add_argument("--area", type=str, help="Filter by research area")
    parser.add_argument("--status", type=str, help="Filter by status (open/taken)")
    parser.add_argument("--difficulty", type=str, help="Filter by difficulty")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"Error: CSV file not found at {args.csv}")
        print("Please create it first. See topics.csv for the expected format.")
        return 1

    topics = load_topics(args.csv)
    topics = filter_topics(topics, args.area, args.status, args.difficulty)

    # By default the published catalog lists only open topics.
    if not args.all and not args.status:
        topics = [t for t in topics if t["status"].lower() == "open"]

    print_summary(topics)

    if args.markdown:
        generate_markdown(topics, args.output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
