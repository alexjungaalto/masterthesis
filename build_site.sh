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

echo "==> Regenerating theses.md from theses.csv"
python3 compile_theses.py --markdown

echo "==> Assembling docs/ from source files"
rm -rf docs site
mkdir -p docs

# README is the landing page; its internal links to Topics.md / theses.md /
# material/* resolve unchanged once those files sit alongside it.
cp README.md   docs/index.md
cp Topics.md   docs/Topics.md
cp theses.md   docs/theses.md
cp datagvat.png docs/datagvat.png
cp -R material docs/material

# Strip files that should not be published with the materials.
rm -f docs/material/.DS_Store docs/material/creategraphtex.py

if [[ "${1:-}" == "serve" ]]; then
  echo "==> Serving live preview (Ctrl-C to stop)"
  exec mkdocs serve
fi

echo "==> Building static site into site/"
mkdocs build --strict

echo "==> Done. Static site is in ./site/"
