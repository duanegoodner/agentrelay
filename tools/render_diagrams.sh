#!/usr/bin/env bash
set -euo pipefail

# ── Layout parameters ────────────────────────────────────────────────
SCALE=0.3
PAD=50

# ── Generate filtered D2 variants ────────────────────────────────────
python -m tools.generate_diagrams

# ── Render all SVGs with TALA layout ─────────────────────────────────
for variant in detailed no-private no-impl standard; do
  d2 --layout tala \
    --scale "$SCALE" \
    --pad "$PAD" \
    "docs/diagram-${variant}.d2" "docs/diagram-${variant}.svg"
done
