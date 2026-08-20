#!/usr/bin/env bash
#
# Assemble and build the ml-theses.org static site.
#
# The repo's source-of-truth files (README.md, Topics.md, theses.csv) stay at
# the repository root. This script regenerates theses.md from the CSV, copies
# the relevant files into a clean docs/ directory, and runs MkDocs to produce
# the static site in site/.
#
# Both docs/ and site/ are build artifacts (git-ignored) — never edit them by
# hand.
#
# Usage:
#   ./build_site.sh          # build static site into site/
#   ./build_site.sh serve    # live-preview at http://127.0.0.1:8000
#
set -euo pipefail

cd "$(dirname "$0")"

# Fail fast if the linter checksum manifest is stale. assets/linters/SHA256SUMS
# lets students verify downloaded scripts before running them (see the linter
# README); a manifest that has drifted from the actual scripts is worse than
# none, so block the build — and therefore the deploy — until it is regenerated
# with `shasum -a 256 $(ls *.py | sort) > SHA256SUMS` from assets/linters/.
echo "==> Verifying assets/linters/SHA256SUMS is current"
(
  cd assets/linters
  if command -v sha256sum >/dev/null 2>&1; then
    SHACMD=(sha256sum)          # Linux / CI (coreutils)
  else
    SHACMD=(shasum -a 256)      # macOS (no sha256sum by default)
  fi
  # Compare a freshly computed manifest (same file set and sort order used to
  # generate it) against the committed one. diff catches a changed hash, a new
  # .py that was never added, and a deleted .py still listed — all three.
  if ! diff <("${SHACMD[@]}" $(ls *.py | sort)) SHA256SUMS >/dev/null; then
    echo "Error: assets/linters/SHA256SUMS is out of date." >&2
    echo "  A linter script changed (or was added/removed) without updating" >&2
    echo "  the checksum manifest. Regenerate and commit it:" >&2
    echo "    cd assets/linters && shasum -a 256 \$(ls *.py | sort) > SHA256SUMS" >&2
    exit 1
  fi
)

# Resolve the mkdocs executable: prefer a local virtualenv, then PATH, then
# `python3 -m mkdocs`. Avoids "mkdocs: not found" when the venv isn't active.
if [[ -x ".venv/bin/mkdocs" ]]; then
  MKDOCS=".venv/bin/mkdocs"
elif command -v mkdocs >/dev/null 2>&1; then
  MKDOCS="mkdocs"
elif python3 -c "import mkdocs" >/dev/null 2>&1; then
  MKDOCS="python3 -m mkdocs"
else
  echo "Error: mkdocs not found. Install the site dependencies first:" >&2
  echo "  python3 -m venv .venv && ./.venv/bin/pip install -r requirements-docs.txt" >&2
  exit 1
fi

echo "==> Regenerating theses.md from theses.csv"
python3 compile_theses.py --markdown

echo "==> Regenerating Topics.md from topics.csv"
python3 compile_topics.py --markdown

echo "==> Assembling docs/ from source files"
rm -rf docs site
mkdir -p docs

# README is the landing page; its internal links to Topics.md / theses.md /
# material/* resolve unchanged once those files sit alongside it.
cp README.md   docs/index.md
cp Topics.md   docs/Topics.md
cp theses.md   docs/theses.md
cp -R material docs/material

# Strip files that should not be published with the materials.
rm -f docs/material/.DS_Store docs/material/creategraphtex.py

# Custom stylesheet (table layout tweaks etc.).
mkdir -p docs/stylesheets
cp web/extra.css docs/stylesheets/extra.css

# robots.txt (points crawlers at the auto-generated sitemap). Copied to the
# docs root so MkDocs publishes it at site root: https://ml-theses.org/robots.txt
cp web/robots.txt docs/robots.txt

# Standalone tool scripts (e.g. the forward-reference linter) served under
# /assets/. Copied so a README link like `assets/foo.py` resolves both on the
# website (https://ml-theses.org/assets/foo.py) and in the GitHub repo view.
if [[ -d assets ]]; then
  mkdir -p docs/assets
  cp -R assets/. docs/assets/
fi

# The linter README doubles as a nav page (mkdocs.yml: "Thesis Linters").
# Page-scoped style: keep the first (instruction) column of the 3-column
# coverage tables narrow — the long instruction text otherwise dominates the
# layout. The 4-column script table is left alone. docs/ is a build
# artifact, so the committed README stays clean for the GitHub view.
cat >> docs/assets/linters/README.md <<'EOF'

<style>
/* Material renders tables shrink-to-fit with auto layout, so cell width
   hints are ignored; fixed layout + full width makes them stick. */
.md-typeset table:not(:has(th:nth-child(4))) {
  display: table;
  table-layout: fixed;
  width: 100%;
}
.md-typeset table:not(:has(th:nth-child(4))) th:first-child,
.md-typeset table:not(:has(th:nth-child(4))) td:first-child {
  /* extra.css collapses every table's first column to min-content with
     nowrap (for the thesis-number column); undo that here. */
  width: 22%;
  white-space: normal;
}
.md-typeset table:not(:has(th:nth-child(4))) td {
  overflow-wrap: break-word;
}
</style>
EOF

# Publish full topic proposal PDFs at the same relative path they live in the
# repo, so a catalog `url` like `topics/<slug>/proposal.pdf` resolves both on
# the website and in the GitHub view of Topics.md.
shopt -s nullglob
for pdf in topics/*/proposal.pdf; do
  mkdir -p "docs/$(dirname "$pdf")"
  cp "$pdf" "docs/$pdf"
done
shopt -u nullglob

if [[ "${1:-}" == "serve" ]]; then
  echo "==> Serving live preview (Ctrl-C to stop)"
  exec $MKDOCS serve
fi

echo "==> Building static site into site/"
$MKDOCS build --strict

echo "==> Done. Static site is in ./site/"
