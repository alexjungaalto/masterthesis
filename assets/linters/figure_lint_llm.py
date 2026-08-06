#!/usr/bin/env python3
"""Linter: visual quality of figures (ml-theses.org: "Ensure all figures
are clear, labelled, and have informative captions").

Looks at the RENDERED figures, not just their captions. For every figure
caption in the PDF the figure region is located and rendered, then checked
two ways:

Pixel heuristics (always, no LLM needed):
  [WARN] EXCESS-WHITESPACE  more than --max-white of the figure region is
                            blank background
  [WARN] LOW-RESOLUTION     embedded raster image below --min-dpi at its
                            printed size (pixelated in print)

Vision LLM judgement (default; skip with --no-llm). The rendered figure is
sent to a vision model together with the body-text font size for scale.
Categories reported (all [WARN]):
  FONT-TOO-SMALL     tick/axis/legend text clearly smaller than body text
  AXES-UNLABELED     axes without labels (or without units where needed)
  OVERLAPPING-TEXT   colliding/clipped labels
  LOW-CONTRAST       elements hard to distinguish (also in grayscale print)
  EXCESS-WHITESPACE  large empty areas inside the plot
  SCREENSHOT         raw screen capture of an IDE, terminal, spreadsheet,
                     or application window used in place of a prepared
                     figure or table (also flags non-English interface
                     text); NOT flagged when the interface itself is the
                     subject (UI of a system built/evaluated, study
                     stimulus)
  ILLEGIBLE          anything else that makes the figure hard to read

Gateway: the Aalto AI API by default (GPT-5 family is multimodal); on the
Aalto LLM Gateway the vision model Qwen3-VL is used (see aalto_llm.py).

Usage:
  python3 figure_lint_llm.py thesis.pdf
  python3 figure_lint_llm.py thesis.pdf --no-llm          # heuristics only
  python3 figure_lint_llm.py thesis.pdf --figures 3,7 --save-crops out/
Exit status: 0 clean, 1 findings, 2 usage error.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

from aalto_llm import (API_KEY_HELP, BASE_URL, BASE_URL_HELP,
                       default_vision_model, extract_json, make_client)
from lintutil import Report

CAPTION_RE = re.compile(r"^(Figure|Fig\.)\s+(\d+(?:\.\d+)*)\s*[:.]\s*(.*)",
                        re.S)
ZOOM = 2.0  # render at 144 dpi


class Figure:
    def __init__(self, number, page_no, caption, rect, raster_dpis):
        self.number = number
        self.page_no = page_no          # 1-based
        self.caption = caption
        self.rect = rect                # fitz.Rect of the figure region
        self.raster_dpis = raster_dpis  # effective dpi of embedded rasters


def body_font_size(doc) -> float:
    """Median font size of running text (points)."""
    sizes = []
    for pno in range(min(len(doc), 30)):
        for b in doc[pno].get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                for sp in ln.get("spans", []):
                    if len(sp.get("text", "").strip()) > 20:
                        sizes.append(round(sp["size"], 1))
    if not sizes:
        return 11.0
    sizes.sort()
    return sizes[len(sizes) // 2]


def find_figures(doc) -> List[Figure]:
    figs: List[Figure] = []
    for pno in range(len(doc)):
        page = doc[pno]
        pw, ph = page.rect.width, page.rect.height
        blocks = page.get_text("dict")["blocks"]
        captions = []
        for b in blocks:
            if b.get("type", 0) != 0:
                continue
            text = " ".join(sp.get("text", "")
                            for ln in b.get("lines", [])
                            for sp in ln.get("spans", []))
            m = CAPTION_RE.match(text.strip())
            if m:
                captions.append((fitz.Rect(b["bbox"]), m.group(2),
                                 m.group(3)))
        if not captions:
            continue
        img_infos = page.get_image_info()
        drawings = [d["rect"] for d in page.get_drawings()]
        for cap_rect, number, cap_text in captions:
            # Figure content: images/vector graphics ABOVE the caption
            # (standard placement), horizontally overlapping the caption
            # column. Fall back to the space between the previous text
            # block and the caption.
            top = 0.0
            for b in blocks:
                r = fitz.Rect(b["bbox"])
                if b.get("type", 0) == 0 and r.y1 <= cap_rect.y0 - 4:
                    text = " ".join(sp.get("text", "")
                                    for ln in b.get("lines", [])
                                    for sp in ln.get("spans", []))
                    if len(text.strip()) > 60 and not \
                            CAPTION_RE.match(text.strip()):
                        top = max(top, r.y1)
            region = None
            dpis = []
            for info in img_infos:
                r = fitz.Rect(info["bbox"])
                if r.y1 <= cap_rect.y0 + 8 and r.y0 >= top - 30 and \
                        r.intersects(fitz.Rect(0, top, pw, cap_rect.y0)):
                    region = r if region is None else region | r
                    if r.width > 8:
                        dpis.append(info["width"] / (r.width / 72.0))
            for r in drawings:
                if r.y1 <= cap_rect.y0 + 8 and r.y0 >= top - 10 and \
                        r.width > 20 and r.height > 20:
                    region = r if region is None else region | r
            if region is None or region.width < 40 or region.height < 30:
                region = fitz.Rect(36, max(top, 36), pw - 36,
                                   cap_rect.y0 - 2)
            if region.height < 30:
                continue
            region = region & page.rect
            figs.append(Figure(number, pno + 1, cap_text.strip()[:200],
                               region, dpis))
    return figs


def white_ratio(pix) -> float:
    """Fraction of near-white pixels, sampled on a grid."""
    n = pix.n if pix.n <= 3 else 3
    data = pix.samples
    w, h, stride = pix.width, pix.height, pix.stride
    total = white = 0
    step_y = max(1, h // 200)
    step_x = max(1, w // 200)
    for y in range(0, h, step_y):
        row = y * stride
        for x in range(0, w, step_x):
            off = row + x * pix.n
            if all(data[off + c] > 245 for c in range(n)):
                white += 1
            total += 1
    return white / max(1, total)


SYSTEM_PROMPT = (
    "You judge the visual quality of one figure from a master's thesis, "
    "rendered at 144 dpi. The thesis body text is {body_pt} pt, which at "
    "this rendering is about {body_px} pixels tall — use that as the "
    "yardstick for text sizes in the figure.\n\n"
    "Report ONLY clear defects a reader/printer would notice, in these "
    "categories:\n"
    "  FONT-TOO-SMALL: tick labels, axis labels, or legend text clearly "
    "smaller than ~70% of the body-text size (i.e. under ~{small_px} px "
    "tall in the image).\n"
    "  AXES-UNLABELED: plot axes missing labels, or quantities without "
    "units where units are meaningful.\n"
    "  OVERLAPPING-TEXT: labels/ticks colliding, clipped, or overprinting "
    "each other.\n"
    "  LOW-CONTRAST: series/elements hard to tell apart (thin light "
    "lines, similar colors that also collapse in grayscale print).\n"
    "  EXCESS-WHITESPACE: large empty areas inside the figure (data "
    "squeezed into a corner, huge empty margins between panels).\n"
    "  SCREENSHOT: the figure is a raw screen capture of an IDE, "
    "terminal, notebook, spreadsheet, or application window (telltales: "
    "window chrome, menu/tool bars, editor syntax colors, line numbers, "
    "scroll bars, mouse cursor) used in place of a prepared table or "
    "plot — results belong in typeset tables/figures. Mention in the "
    "comment if visible interface text is not in English. A deliberately "
    "cropped, clean code listing presented AS a listing is fine. A "
    "screenshot is ADEQUATE — do not flag — when the interface itself is "
    "the subject of the figure (the UI of a system the thesis built or "
    "evaluates, or what study participants saw); flag only when the "
    "interface is incidental and the actual content (numbers, tables, "
    "code output, data) should have been extracted and typeset.\n"
    "  ILLEGIBLE: anything else making the figure hard to read "
    "(pixelation, tiny markers, dense clutter).\n\n"
    "Diagrams/architecture sketches have no axes — do not demand axes "
    "for them. Be conservative: no nitpicks about style or aesthetics. "
    "Respond with STRICT JSON:\n"
    '{{"findings": [{{"category": "...", "comment": "..."}}], '
    '"overall": "ok|problematic"}}'
)


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Visual figure-quality linter (pixel heuristics + "
                    "vision LLM).")
    ap.add_argument("pdf", help="Path to the thesis PDF.")
    ap.add_argument("--base-url", default=BASE_URL, help=BASE_URL_HELP)
    ap.add_argument("--api-key", default=None, help=API_KEY_HELP)
    ap.add_argument("--model", default=None,
                    help="Vision model id (default depends on gateway).")
    ap.add_argument("--no-llm", action="store_true",
                    help="Pixel heuristics only, no LLM calls.")
    ap.add_argument("--figures", default=None,
                    help="Comma-separated figure numbers to check "
                         "(default: all).")
    ap.add_argument("--max-white", type=float, default=0.95,
                    help="EXCESS-WHITESPACE threshold on the blank-pixel "
                         "fraction (default 0.95; line plots are naturally mostly white).")
    ap.add_argument("--min-dpi", type=int, default=100,
                    help="LOW-RESOLUTION threshold for embedded rasters "
                         "(default 100).")
    ap.add_argument("--save-crops", metavar="DIR",
                    help="Save the rendered figure regions as PNGs here "
                         "(inspect what was judged).")
    args = ap.parse_args(argv)

    if fitz is None:
        print("ERROR: PyMuPDF required. pip install pymupdf",
              file=sys.stderr)
        return 2

    doc = fitz.open(args.pdf)
    body_pt = body_font_size(doc)
    figs = find_figures(doc)
    if args.figures:
        wanted = {s.strip() for s in args.figures.split(",")}
        figs = [f for f in figs if f.number in wanted]
    if not figs:
        print("ERROR: no figure captions found.", file=sys.stderr)
        return 2

    rep = Report("Figure lint report (visual quality)", args.pdf)
    client = model = None
    if not args.no_llm:
        model = args.model or default_vision_model(args.base_url)
        client = make_client(args.base_url, args.api_key)
        print(f"[info] gateway={args.base_url}\n[info] model={model}  "
              f"figures={len(figs)}  body-font={body_pt}pt",
              file=sys.stderr)

    crops_dir = None
    if args.save_crops:
        crops_dir = Path(args.save_crops)
        crops_dir.mkdir(parents=True, exist_ok=True)

    total_tokens = 0
    for fig in figs:
        where = f"p{fig.page_no}"
        label = f"Figure {fig.number}"
        page = doc[fig.page_no - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), clip=fig.rect)
        if crops_dir:
            pix.save(crops_dir / f"figure_{fig.number}.png")

        wr = white_ratio(pix)
        if wr > args.max_white:
            rep.add("WARN", "EXCESS-WHITESPACE", where,
                    f"{label}: {wr:.0%} of the figure region is blank "
                    f"background.")
        for dpi in fig.raster_dpis:
            if dpi < args.min_dpi:
                rep.add("WARN", "LOW-RESOLUTION", where,
                        f"{label}: embedded raster at ~{dpi:.0f} dpi at "
                        f"its printed size (min {args.min_dpi}).")

        if client is None:
            continue
        body_px = body_pt * ZOOM
        system = SYSTEM_PROMPT.format(body_pt=body_pt,
                                      body_px=round(body_px),
                                      small_px=round(0.7 * body_px))
        user = (f"{label} (page {fig.page_no}). Caption: "
                f"\"{fig.caption}\"\nJudge the attached rendering.")
        try:
            raw, usage = client.complete(model=model, system=system,
                                         user=user, timeout=300,
                                         images=[pix.tobytes("png")])
        except RuntimeError as e:
            rep.add("INFO", "LLM-ERROR", where, f"{label}: {e}")
            continue
        total_tokens += usage.get("total_tokens", 0)
        parsed = extract_json(raw) or {}
        finds = parsed.get("findings", [])
        print(f"[progress] {label} (p{fig.page_no}): "
              f"{len(finds) if isinstance(finds, list) else 0} finding(s), "
              f"white={wr:.0%}", file=sys.stderr)
        if not isinstance(finds, list):
            continue
        for f in finds:
            if not isinstance(f, dict):
                continue
            cat = str(f.get("category", "ILLEGIBLE")).strip().upper()
            comment = str(f.get("comment", "")).strip()
            rep.add("WARN", cat, where, f"{label}: {comment[:160]}")

    doc.close()
    print(rep.render())
    if total_tokens:
        print(f"\nTotal tokens used: {total_tokens}")
    return rep.exit_code()


if __name__ == "__main__":
    raise SystemExit(main())
