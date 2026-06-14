#!/usr/bin/env python3
"""
Compile a list of supervised master thesis projects at TU Wien and Aalto University.

Reads thesis data from a CSV file (theses.csv) and generates:
  - A summary printed to the console
  - A Markdown file (theses.md) with tables grouped by university
  - Basic statistics (per year, per industry partner, ongoing vs completed)

Usage:
    python compile_theses.py                  # print summary
    python compile_theses.py --markdown       # also write theses.md
    python compile_theses.py --stats          # print statistics
"""

import argparse
import csv
import os
from collections import Counter
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = SCRIPT_DIR / "theses.csv"
DEFAULT_MD = SCRIPT_DIR / "theses.md"
DEFAULT_TEX = SCRIPT_DIR / "theses.tex"


def load_theses(csv_path: Path) -> list[dict]:
    """Load thesis records from a CSV file."""
    theses = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["number"] = int(row["number"])
            theses.append(row)
    return theses


def filter_theses(
    theses: list[dict],
    university: str | None = None,
    status: str | None = None,
    year: str | None = None,
    industry: str | None = None,
) -> list[dict]:
    """Filter thesis records by university, status, year, or industry partner."""
    result = theses
    if university:
        result = [t for t in result if t["university"].lower() == university.lower()]
    if status:
        result = [t for t in result if t["status"].lower() == status.lower()]
    if year:
        result = [t for t in result if t["date"].endswith(year) or t["date"].startswith(year)]
    if industry:
        result = [t for t in result if industry.lower() in t["industry"].lower()]
    return result


def print_summary(theses: list[dict]) -> None:
    """Print a plain-text summary grouped by university."""
    by_uni = {}
    for t in theses:
        by_uni.setdefault(t["university"], []).append(t)

    for uni, records in by_uni.items():
        print(f"\n{'='*70}")
        print(f"  {uni}  ({len(records)} theses)")
        print(f"{'='*70}")
        for t in records:
            status_tag = " [ongoing]" if t["status"].lower() == "ongoing" else ""
            industry_tag = f"  (industry: {t['industry']})" if t["industry"] else ""
            url_tag = f"  {t['url']}" if t["url"] else ""
            print(f"  {t['number']:>3}. {t['author']}, {t['title']}{status_tag}{industry_tag}")
            if url_tag:
                print(f"       {t['url']}")
    print()


def generate_markdown(theses: list[dict], output_path: Path) -> None:
    """Write a Markdown file with thesis tables grouped by university."""
    by_uni = {}
    for t in theses:
        by_uni.setdefault(t["university"], []).append(t)

    lines = ["# Supervised Master Theses\n"]

    for uni, records in by_uni.items():
        ongoing = [r for r in records if r["status"].lower() == "ongoing"]
        completed = [r for r in records if r["status"].lower() != "ongoing"]

        lines.append(f"## {uni} ({len(records)} total)\n")

        if ongoing:
            lines.append(f"### Ongoing ({len(ongoing)})\n")
            lines.append("| # | Author | Title | Industry | Recording |")
            lines.append("|---|--------|-------|----------|-----------|")
            for i, t in enumerate(ongoing, 1):
                rec = f"[video]({t['recording']})" if t.get("recording") else ""
                lines.append(
                    f"| {i} | {t['author']} | {t['title']} | {t['industry']} | {rec} |"
                )
            lines.append("")

        if completed:
            lines.append(f"### Completed ({len(completed)})\n")
            lines.append("| # | Author | Title | Date | Industry | Recording |")
            lines.append("|---|--------|-------|------|----------|-----------|")
            for i, t in enumerate(completed, 1):
                title = f"[{t['title']}]({t['url']})" if t["url"] else t["title"]
                rec = f"[video]({t['recording']})" if t.get("recording") else ""
                lines.append(
                    f"| {i} | {t['author']} | {title} "
                    f"| {t['date']} | {t['industry']} | {rec} |"
                )
            lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Markdown written to {output_path}")


def tex_escape(s: str) -> str:
    """Escape LaTeX special characters in a string."""
    if not s:
        return ""
    replacements = [
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]
    for a, b in replacements:
        s = s.replace(a, b)
    return s


def generate_tex(theses: list[dict], output_path: Path) -> None:
    """Write a standalone LaTeX file with thesis tables grouped by university."""
    by_uni = {}
    for t in theses:
        by_uni.setdefault(t["university"], []).append(t)

    lines = [
        r"\documentclass[11pt,a4paper]{article}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{lmodern}",
        r"\usepackage[margin=2cm]{geometry}",
        r"\usepackage{longtable}",
        r"\usepackage{array}",
        r"\usepackage{booktabs}",
        r"\usepackage[hidelinks]{hyperref}",
        r"\usepackage{xurl}",
        r"\setlength{\parindent}{0pt}",
        r"\setlength{\parskip}{0.5em}",
        r"",
        r"\title{Co-Supervised Master Theses \\[0.3em]"
        r" \large by Alex Jung, Assoc.\ Prof.\ for Machine Learning}",
        r"\author{}",
        r"\date{\today}",
        r"",
        r"\begin{document}",
        r"\maketitle",
        r"",
    ]

    for uni, records in by_uni.items():
        ongoing = [r for r in records if r["status"].lower() == "ongoing"]
        completed = [r for r in records if r["status"].lower() != "ongoing"]

        lines.append(rf"\section*{{{tex_escape(uni)} ({len(records)} total)}}")
        lines.append("")

        if ongoing:
            lines.append(rf"\subsection*{{Ongoing ({len(ongoing)})}}")
            lines.append("")
            lines.append(r"\begin{longtable}{@{}r p{3cm} p{6.5cm} p{2.8cm} p{2cm}@{}}")
            lines.append(r"\toprule")
            lines.append(r"\# & Author & Title & Industry & Recording \\")
            lines.append(r"\midrule")
            lines.append(r"\endfirsthead")
            lines.append(r"\toprule")
            lines.append(r"\# & Author & Title & Industry & Recording \\")
            lines.append(r"\midrule")
            lines.append(r"\endhead")
            lines.append(r"\bottomrule")
            lines.append(r"\endfoot")
            for i, t in enumerate(ongoing, 1):
                rec = rf"\href{{{t['recording']}}}{{video}}" if t.get("recording") else ""
                lines.append(
                    f"{i} & {tex_escape(t['author'])} & "
                    f"{tex_escape(t['title'])} & {tex_escape(t['industry'])} & {rec} \\\\"
                )
            lines.append(r"\end{longtable}")
            lines.append("")

        if completed:
            lines.append(rf"\subsection*{{Completed ({len(completed)})}}")
            lines.append("")
            lines.append(r"\begin{longtable}{@{}r p{2.8cm} p{6.3cm} p{1.6cm} p{2cm} p{1.8cm}@{}}")
            lines.append(r"\toprule")
            lines.append(r"\# & Author & Title & Date & Industry & Recording \\")
            lines.append(r"\midrule")
            lines.append(r"\endfirsthead")
            lines.append(r"\toprule")
            lines.append(r"\# & Author & Title & Date & Industry & Recording \\")
            lines.append(r"\midrule")
            lines.append(r"\endhead")
            lines.append(r"\bottomrule")
            lines.append(r"\endfoot")
            for i, t in enumerate(completed, 1):
                title_tex = tex_escape(t['title'])
                if t['url']:
                    title_tex = rf"\href{{{t['url']}}}{{{title_tex}}}"
                rec = rf"\href{{{t['recording']}}}{{video}}" if t.get("recording") else ""
                lines.append(
                    f"{i} & {tex_escape(t['author'])} & {title_tex} & "
                    f"{tex_escape(t['date'])} & {tex_escape(t['industry'])} & {rec} \\\\"
                )
            lines.append(r"\end{longtable}")
            lines.append("")

    lines.append(r"\end{document}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"LaTeX written to {output_path}")


def print_stats(theses: list[dict]) -> None:
    """Print summary statistics."""
    print(f"\nTotal theses: {len(theses)}")

    # By university
    uni_counts = Counter(t["university"] for t in theses)
    print("\nBy university:")
    for uni, count in uni_counts.most_common():
        print(f"  {uni}: {count}")

    # Ongoing vs completed
    ongoing = sum(1 for t in theses if t["status"].lower() == "ongoing")
    print(f"\nOngoing: {ongoing}")
    print(f"Completed: {len(theses) - ongoing}")

    # By year (completed only)
    completed = [t for t in theses if t["status"].lower() != "ongoing"]
    year_counts = Counter()
    for t in completed:
        parts = t["date"].replace(",", "").split()
        for part in parts:
            if part.isdigit() and len(part) == 4:
                year_counts[part] += 1
                break
    print("\nCompleted by year:")
    for year, count in sorted(year_counts.items()):
        print(f"  {year}: {count}")

    # Top industry partners
    partners = [t["industry"] for t in theses if t["industry"]]
    partner_counts = Counter(partners)
    print(f"\nIndustry-partnered theses: {len(partners)}")
    print("Top industry partners:")
    for partner, count in partner_counts.most_common(10):
        print(f"  {partner}: {count}")


def main():
    parser = argparse.ArgumentParser(description="Compile supervised master thesis list.")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="Path to theses.csv")
    parser.add_argument("--markdown", action="store_true", help="Generate theses.md")
    parser.add_argument("--output", type=Path, default=DEFAULT_MD, help="Markdown output path")
    parser.add_argument("--tex", action="store_true", help="Generate theses.tex")
    parser.add_argument("--tex-output", type=Path, default=DEFAULT_TEX, help="LaTeX output path")
    parser.add_argument("--stats", action="store_true", help="Print statistics")
    parser.add_argument("--university", type=str, help="Filter by university")
    parser.add_argument("--status", type=str, help="Filter by status (ongoing/completed)")
    parser.add_argument("--year", type=str, help="Filter by year")
    parser.add_argument("--industry", type=str, help="Filter by industry partner")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"Error: CSV file not found at {args.csv}")
        print(f"Please create it first. See theses.csv for the expected format.")
        return 1

    theses = load_theses(args.csv)
    theses = filter_theses(theses, args.university, args.status, args.year, args.industry)

    print_summary(theses)

    if args.stats:
        print_stats(theses)

    if args.markdown:
        generate_markdown(theses, args.output)

    if args.tex:
        generate_tex(theses, args.tex_output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
