#!/usr/bin/env python3
"""Bibliography linter: verify that cited references exist and that their
author list, title, and publication venue are correct.

Sources checked against (no API keys needed):
  - Crossref  (api.crossref.org)   - primary, journals + proceedings
  - arXiv     (export.arxiv.org)   - entries citing an arXiv identifier
  - DBLP      (dblp.org)           - secondary for CS venues; best-effort
                                     (DBLP rate-limits aggressively; failures
                                     are tolerated)

Input formats:
  *.bib  - BibTeX file (lightweight built-in parser, no dependencies)
  *.pdf  - compiled manuscript with an IEEE-style numbered reference list
           ("[1] A. Author, ...\"Title,\" Venue, year."); the References
           section is located and split automatically.

Findings (severity in brackets):
  [ERROR] NOT-FOUND         no plausible match in any database -- entry may be
                            hallucinated, garbled, or too incomplete to verify
  [ERROR] AUTHOR-MISMATCH   matched record's authors differ from the citation
  [WARN]  TITLE-DRIFT       best match found but title similarity is imperfect
  [WARN]  VENUE-MISMATCH    cited venue disagrees with the matched record
  [WARN]  PREPRINT          cited as arXiv/SSRN/URL-only although a published
                            venue exists for the same work
  [WARN]  YEAR-MISMATCH     year differs by more than 1 from the matched record
  [INFO]  INCOMPLETE        entry lacks a parseable title/author/year
  [INFO]  WEB-SOURCE        dataset/website/repository citation -- not checked
                            against publication databases
  [INFO]  UNVERIFIED        all database queries failed (network/rate limit)

Results are cached in a JSON file (--cache, default .bibcheck_cache.json next
to the input) so re-runs are cheap. Queries are rate-limited (--delay).

Usage:
  python3 bibliography_linter.py thesis.pdf
  python3 bibliography_linter.py refs.bib --max 20 --delay 1.0
Exit status: 0 if no ERROR/WARN findings, 1 otherwise, 2 usage error.
"""

import argparse
import difflib
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

UA = {"User-Agent": "bibliography-linter/1.0 (thesis supervision; mailto:alex.jung@aalto.fi)"}
ARXIV_ID_RE = re.compile(r"(?:ar[xX]iv[:\s]*|abs/)(\d{4}\.\d{4,5}|[a-z\-]+/\d{7})",
                         re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+|www\.\S+|doi\.org/\S+", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
WEB_HOST_RE = re.compile(
    r"kaggle|roboflow|zenodo|hugging\s*face|huggingface|github|gitlab|medium\.com|"
    r"towardsdatascience|wikipedia|blog|\bdataset\b", re.IGNORECASE)
PREPRINT_RE = re.compile(r"arxiv|preprint|corr\b|ssrn|techrxiv|biorxiv", re.IGNORECASE)
STOPWORDS = {"the", "a", "an", "of", "for", "and", "with", "via", "using",
             "from", "towards", "toward", "on", "in", "to", "by"}


def title_tokens(s):
    return [t for t in re.sub(r"[^a-z0-9]+", " ", s.lower()).split()
            if t not in STOPWORDS and len(t) > 2]


# --------------------------------------------------------------------------
# parsing: BibTeX
# --------------------------------------------------------------------------

def parse_bib(path: Path):
    text = path.read_text(encoding="utf-8", errors="replace")
    entries = []
    for m in re.finditer(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", text):
        etype, key = m.group(1).lower(), m.group(2)
        if etype in {"comment", "string", "preamble"}:
            continue
        # take the balanced-brace body
        depth, i = 1, m.end()
        while i < len(text) and depth:
            depth += {"{": 1, "}": -1}.get(text[i], 0)
            i += 1
        body = text[m.end():i - 1]
        fields = {}
        for fm in re.finditer(r"(\w+)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|\w+)",
                              body):
            fields[fm.group(1).lower()] = fm.group(2).strip("{}\"").strip()
        title = re.sub(r"[{}]", "", fields.get("title", ""))
        authors = [a.strip() for a in
                   re.split(r"\s+and\s+", fields.get("author", "")) if a.strip()]
        venue = fields.get("journal") or fields.get("booktitle") or \
            fields.get("publisher") or fields.get("howpublished") or ""
        raw = f"@{etype}{{{key}}} {fields.get('author','')} \"{title}\" {venue}"
        entries.append({
            "id": key, "title": title, "authors": authors, "venue": venue,
            "year": fields.get("year", ""), "arxiv": _find_arxiv(body),
            "url": fields.get("url", ""), "raw": raw,
        })
    return entries


def _find_arxiv(text):
    m = ARXIV_ID_RE.search(text)
    return m.group(1) if m else ""


# --------------------------------------------------------------------------
# parsing: PDF with IEEE-style numbered references
# --------------------------------------------------------------------------

def extract_pdf_text(path: Path):
    try:
        out = subprocess.run(["pdftotext", "-layout", str(path), "-"],
                             capture_output=True, check=True)
        return out.stdout.decode("utf-8", errors="replace")
    except (FileNotFoundError, subprocess.CalledProcessError):
        import fitz
        with fitz.open(path) as doc:
            return "\f".join(p.get_text() for p in doc)


def parse_pdf_references(path: Path):
    text = extract_pdf_text(path)
    # find the References heading closest to the end
    heads = [m.start() for m in
             re.finditer(r"^\s*(References|Bibliography)\s*$", text, re.MULTILINE)]
    if not heads:
        sys.exit(f"error: no 'References' section found in {path}")
    refs_text = text[heads[-1]:]
    # stop at an appendix heading if one follows
    stop = re.search(r"^\s*(?:A\s+)?Appendix\b", refs_text, re.MULTILINE)
    if stop and stop.start() > 100:
        refs_text = refs_text[:stop.start()]

    # split on bracketed numbers at line starts, joining wrapped lines
    chunks = re.split(r"(?m)^\s*\[(\d+)\]", refs_text)
    entries = []
    for i in range(1, len(chunks) - 1, 2):
        num, body = chunks[i], re.sub(r"\s+", " ", chunks[i + 1]).strip()
        entries.append(_parse_ieee_entry(num, body))
    return [e for e in entries if e]


def _parse_ieee_entry(num, body):
    title_m = re.search(r"[\"“]\s*(.+?)[,.]?\s*[\"”]", body)
    title = title_m.group(1).strip() if title_m else ""
    authors_part = body[:title_m.start()].strip(" ,") if title_m else ""
    rest = body[title_m.end():].strip(" ,") if title_m else body
    authors = [a.strip() for a in
               re.split(r",\s*(?:and\s+)?|\s+and\s+", authors_part)
               if a.strip() and not a.strip().lower().startswith("et al")]
    # arXiv ids ("arXiv:1905.11946") and URLs contain digit runs that must not
    # be mistaken for years
    body_for_year = URL_RE.sub("", ARXIV_ID_RE.sub("", body))
    year_m = list(YEAR_RE.finditer(body_for_year))
    year = year_m[-1].group(0) if year_m else ""
    venue = re.split(r",\s*(?:vol|no|pp|p)\.\s", rest)[0]
    venue = YEAR_RE.sub("", venue).strip(" ,.")
    return {
        "id": f"[{num}]", "title": title, "authors": authors, "venue": venue,
        "year": year, "arxiv": _find_arxiv(body), "url": URL_RE.search(body).group(0)
        if URL_RE.search(body) else "", "raw": body[:220],
    }


# --------------------------------------------------------------------------
# database queries
# --------------------------------------------------------------------------

def _get(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def query_crossref(title):
    q = urllib.parse.quote(title)
    data = json.loads(_get(
        f"https://api.crossref.org/works?query.bibliographic={q}&rows=5"))
    out = []
    for it in data.get("message", {}).get("items", []):
        out.append({
            "title": (it.get("title") or [""])[0],
            "authors": [a.get("family", "") for a in it.get("author", [])],
            "venue": (it.get("container-title") or [""])[0]
            or it.get("publisher", ""),
            "year": str((it.get("issued", {}).get("date-parts") or [[None]])[0][0] or ""),
            "type": it.get("type", ""), "doi": it.get("DOI", ""),
            "source": "crossref",
        })
    return out


def query_dblp(title):
    q = urllib.parse.quote(title)
    data = json.loads(_get(f"https://dblp.org/search/publ/api?q={q}&format=json&h=5"))
    hits = data.get("result", {}).get("hits", {}).get("hit", []) or []
    out = []
    for h in hits:
        info = h.get("info", {})
        auth = info.get("authors", {}).get("author", [])
        if isinstance(auth, dict):
            auth = [auth]
        # DBLP disambiguates homonyms with numeric suffixes ("Mark Sandler 0002")
        names = [re.sub(r"\s+\d{4}$", "", a.get("text", "")).split()
                 for a in auth if a.get("text")]
        out.append({
            "title": info.get("title", ""),
            "authors": [n[-1] for n in names if n],
            "venue": info.get("venue", ""), "year": info.get("year", ""),
            "type": info.get("type", ""), "doi": info.get("doi", ""),
            "source": "dblp",
        })
    return out


def query_s2(arxiv_id):
    """Semantic Scholar: resolves an arXiv id to its canonical (published)
    record even when the title changed between preprint and publication."""
    data = json.loads(_get(
        f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{arxiv_id}"
        f"?fields=title,venue,year,authors,externalIds"))
    if str(data.get("code")) == "429" or "Too Many Requests" in str(data.get("message", "")):
        raise RuntimeError("HTTP 429: semanticscholar rate limit")
    if "title" not in data:
        return []
    return [{
        "title": data.get("title", ""),
        "authors": [(a.get("name", "")).split()[-1]
                    for a in data.get("authors", []) if a.get("name")],
        "venue": data.get("venue", ""), "year": str(data.get("year") or ""),
        "type": "record",
        "doi": (data.get("externalIds") or {}).get("DOI", ""),
        "source": "semanticscholar",
    }]


def query_arxiv(arxiv_id):
    xml = _get(f"https://export.arxiv.org/api/query?id_list={arxiv_id}&max_results=1")
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml)
    e = root.find("a:entry", ns)
    if e is None or e.find("a:title", ns) is None:
        return []
    title = re.sub(r"\s+", " ", e.find("a:title", ns).text or "").strip()
    if title.lower() == "error":
        return []
    return [{
        "title": title,
        "authors": [(a.find("a:name", ns).text or "").split()[-1]
                    for a in e.findall("a:author", ns)],
        "venue": "arXiv", "year": (e.find("a:published", ns).text or "")[:4],
        "type": "preprint", "doi": "", "source": "arxiv",
    }]


# --------------------------------------------------------------------------
# comparison
# --------------------------------------------------------------------------

def cached_query(cache, key, fn, arg, delay, log, backoff0=1.5):
    """Query with cache; retry with backoff on 429/503; never cache failures."""
    if cache.get(key) is not None:
        return cache[key], None
    backoff, last = max(delay, backoff0), ""
    for _ in range(4):
        try:
            res = fn(arg)
            cache[key] = res
            time.sleep(delay)
            return res, None
        except Exception as ex:
            last = str(ex)
            if "429" in last or "503" in last:
                log(f"    ~ {key.split(':', 1)[0]} rate limited, retrying in {backoff:.0f}s")
                time.sleep(backoff)
                backoff *= 2.5
            else:
                break
    log(f"    ! {key.split(':', 1)[0]} query failed: {last[:100]}")
    return None, last


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def sim(a, b):
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def last_names(authors):
    out = []
    for a in authors:
        a = re.sub(r"[{}\\.]", "", a).strip()
        parts = [p for p in a.split() if len(p) > 1 or not p.isupper()]
        if parts:
            out.append(norm(parts[-1]))
    return [x for x in out if x]


def check_entry(entry, cache, delay, log):
    findings = []  # (severity, code, message)
    title, venue = entry["title"], entry["venue"]

    if not title:
        if entry["url"] or WEB_HOST_RE.search(entry["raw"]):
            return [("INFO", "WEB-SOURCE", "no quoted title; looks like a web/"
                     "dataset source -- check the URL manually")]
        return [("INFO", "INCOMPLETE", "no title could be parsed; entry cannot "
                 "be verified (check completeness of the entry)")]
    if WEB_HOST_RE.search(venue) or (not venue and entry["url"]
                                     and not entry["arxiv"]):
        return [("INFO", "WEB-SOURCE",
                 f"web/dataset source ('{(venue or entry['url'])[:60]}') -- "
                 f"not checked against publication databases")]

    candidates, errors = [], []
    for name, fn, arg in (("crossref", query_crossref, title),
                          ("dblp", query_dblp, title),
                          ("arxiv", query_arxiv, entry["arxiv"])):
        if name == "arxiv" and not entry["arxiv"]:
            continue
        res, err = cached_query(cache, f"{name}:{arg}", fn, arg, delay, log)
        if err:
            errors.append(f"{name}: {err[:60]}")
        if res:
            candidates.extend(res)

    if not candidates:
        if errors:
            return [("INFO", "UNVERIFIED",
                     f"all database queries failed ({'; '.join(errors)[:120]})")]
        return [("ERROR", "NOT-FOUND",
                 f"no database match for title '{title[:70]}'")]

    best = max(candidates, key=lambda c: sim(title, c["title"]))
    best_sim = sim(title, best["title"])
    if best_sim < 0.55:
        return [("ERROR", "NOT-FOUND",
                 f"no plausible match for title '{title[:70]}' "
                 f"(closest: '{best['title'][:70]}' [{best['source']}], "
                 f"similarity {best_sim:.2f})")]
    if best_sim < 0.85:
        findings.append(("WARN", "TITLE-DRIFT",
                         f"cited title '{title[:60]}' vs matched "
                         f"'{best['title'][:60]}' [{best['source']}] "
                         f"(similarity {best_sim:.2f})"))

    # authors: compare last names; citation may truncate with 'et al.'
    cited, found = last_names(entry["authors"]), [norm(x) for x in best["authors"]]
    if cited and found:
        def name_eq(c, f):
            return c == f or c in f or f in c or sim(c, f) > 0.85
        overlap = sum(1 for c in cited if any(name_eq(c, f) for f in found))
        first_ok = not found or not cited or name_eq(cited[0], found[0]) \
            or any(name_eq(cited[0], f) for f in found)
        if overlap < max(1, len(cited) // 2) or not first_ok:
            findings.append(("ERROR", "AUTHOR-MISMATCH",
                             f"cited authors {cited[:6]} vs matched "
                             f"{found[:6]} [{best['source']}]"))

    # year
    if entry["year"] and best["year"]:
        try:
            if abs(int(entry["year"]) - int(best["year"])) > 1:
                findings.append(("WARN", "YEAR-MISMATCH",
                                 f"cited year {entry['year']} vs matched "
                                 f"{best['year']} [{best['source']}]"))
        except ValueError:
            pass

    # venue / preprint status
    cited_preprint = bool(PREPRINT_RE.search(venue)) or (not venue and entry["arxiv"])
    if not venue and not entry["arxiv"] and not entry["url"]:
        findings.append(("WARN", "INCOMPLETE",
                         "no publication venue, arXiv id, or URL given -- the "
                         "entry cannot be located from the citation alone"))
    published = [c for c in candidates
                 if sim(title, c["title"]) > 0.85
                 and c["venue"] and not PREPRINT_RE.search(c["venue"])
                 and c.get("type") not in {"preprint", "posted-content", "Informal and Other Publications"}]
    if cited_preprint and entry["arxiv"] and not published:
        # title may have changed at publication: resolve via Semantic Scholar
        res, err = cached_query(cache, f"s2:{entry['arxiv']}", query_s2,
                                entry["arxiv"], delay, log, backoff0=6.0)
        if res is None and err:
            findings.append(("INFO", "PREPRINT-UNCHECKED",
                             "could not determine whether a published version "
                             f"of arXiv:{entry['arxiv']} exists "
                             f"({err[:60]}) -- re-run to retry"))
        published = [c for c in res or []
                     if c["venue"] and not PREPRINT_RE.search(c["venue"])]
    if cited_preprint and entry["arxiv"] and not published:
        # Semantic Scholar keeps some renamed papers as separate records
        # (e.g. the Krum paper, arXiv:1703.02757 vs. its NIPS 2017 version):
        # search DBLP for first author + distinctive title words and accept a
        # real-venue hit whose title contains (nearly) all cited title words.
        first = (last_names(entry["authors"]) or [""])[0]
        tokens = title_tokens(title)
        if first and tokens:
            q = " ".join([first] + tokens[:3])
            res, _ = cached_query(cache, f"dblp:{q}", query_dblp, q, delay, log)
            cited_tok = set(tokens)
            for c in res or []:
                if not c["venue"] or PREPRINT_RE.search(c["venue"]) \
                        or c.get("type") in {"preprint", "posted-content",
                                             "Informal and Other Publications"}:
                    continue
                if first not in {norm(x) for x in c["authors"]}:
                    continue
                if len(cited_tok - set(title_tokens(c["title"]))) \
                        <= len(cited_tok) // 3:
                    published = [c]
                    break
    if cited_preprint and published:
        p = max(published, key=lambda c: sim(title, c["title"]))
        findings.append(("WARN", "PREPRINT",
                         f"cited as preprint but published version exists: "
                         f"'{p['title'][:60]}', {p['venue']} {p['year']} "
                         f"[{p['source']}"
                         + (f", doi:{p['doi']}]" if p['doi'] else "]")))
    elif venue and not cited_preprint and best["venue"]:
        v_sim = sim(venue, best["venue"])
        tokens_c = set(norm(venue).split()) - {"proceedings", "of", "the", "on",
                                               "in", "conference", "international"}
        tokens_f = set(norm(best["venue"]).split())
        token_overlap = bool(tokens_c & tokens_f)
        abbrev = "".join(w[0] for w in norm(best["venue"]).split() if w)
        if v_sim < 0.5 and not token_overlap and norm(venue).replace(" ", "") \
                not in abbrev and abbrev not in norm(venue).replace(" ", ""):
            findings.append(("WARN", "VENUE-MISMATCH",
                             f"cited venue '{venue[:50]}' vs matched "
                             f"'{best['venue'][:50]}' [{best['source']}]"))

    if not findings:
        findings.append(("OK", "OK", f"verified against {best['source']} "
                        f"('{best['title'][:60]}', {best['venue'][:40]} "
                        f"{best['year']})"))
    return findings


# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description="Verify bibliography entries "
                                 "against Crossref, DBLP, and arXiv.")
    ap.add_argument("path", help=".bib file or .pdf with IEEE-style references")
    ap.add_argument("--max", type=int, default=0, help="check only first N entries")
    ap.add_argument("--delay", type=float, default=0.7,
                    help="seconds between API queries (default 0.7)")
    ap.add_argument("--cache", default="",
                    help="cache file (default: .bibcheck_cache.json beside input)")
    ap.add_argument("--only", default="",
                    help="comma-separated entry numbers/keys to check, e.g. 2,5,42")
    ap.add_argument("-q", "--quiet", action="store_true",
                    help="only print findings, no per-entry progress")
    args = ap.parse_args(argv)

    path = Path(args.path)
    if not path.is_file():
        sys.exit(f"error: no such file: {path}")
    entries = parse_bib(path) if path.suffix.lower() == ".bib" \
        else parse_pdf_references(path)
    if args.only:
        wanted = {w.strip() for w in args.only.split(",")}
        entries = [e for e in entries
                   if e["id"].strip("[]") in wanted or e["id"] in wanted]
    if args.max:
        entries = entries[:args.max]

    cache_path = Path(args.cache) if args.cache else \
        path.with_name(".bibcheck_cache.json")
    cache = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text())

    log = (lambda *a: None) if args.quiet else print
    counts = {"ERROR": 0, "WARN": 0, "INFO": 0, "OK": 0}
    try:
        for e in entries:
            log(f"{e['id']} {e['raw'][:90]}")
            for sev, code, msg in check_entry(e, cache, args.delay, log):
                counts[sev] += 1
                if sev == "OK":
                    log(f"    ok: {msg}")
                else:
                    print(f"{path}:{e['id']}: [{sev}] {code}: {msg}")
    finally:
        cache_path.write_text(json.dumps(cache))

    print(f"\nchecked {len(entries)} entr(ies): {counts['OK']} verified, "
          f"{counts['ERROR']} error(s), {counts['WARN']} warning(s), "
          f"{counts['INFO']} unverifiable/skipped   (cache: {cache_path})")
    return 1 if counts["ERROR"] or counts["WARN"] else 0


if __name__ == "__main__":
    sys.exit(main())
