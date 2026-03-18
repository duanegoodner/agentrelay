#!/usr/bin/env bash
set -euo pipefail

# ── Layout parameters (edit these to experiment) ─────────────────────
# Overview diagram
OV_NODE_BETWEEN=10
OV_EDGE_BETWEEN=5
OV_PADDING="[top=10,left=10,bottom=10,right=10]"
OV_SELF_LOOP=20
OV_SCALE=0.5
OV_PAD=20

# Detail diagram
DT_SCALE=0.1
DT_PAD=50

# ── Generate overview D2 source ──────────────────────────────────────
python tools/generate_overview.py

# ── Render overview SVG ──────────────────────────────────────────────
# d2 --layout elk \
#   --elk-nodeNodeBetweenLayers "$OV_NODE_BETWEEN" \
#   --elk-edgeNodeBetweenLayers "$OV_EDGE_BETWEEN" \
#   --elk-padding "$OV_PADDING" \
#   --elk-nodeSelfLoop "$OV_SELF_LOOP" \
#   --scale "$OV_SCALE" \
#   --pad "$OV_PAD" \
#   docs/diagram-overview.d2 docs/diagram-overview.svg

# ── Generate overview HTML (requires overview SVG to exist) ──────────
# python tools/generate_overview.py --html-only

# ── Render detail SVG ────────────────────────────────────────────────
d2 --layout tala \
  --scale "$DT_SCALE" \
  --pad "$DT_PAD" \
  docs/diagram-detailed.d2 docs/diagram-detailed.svg
