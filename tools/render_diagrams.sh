#!/usr/bin/env bash
set -euo pipefail

# ── D2 style defaults (all diagrams) ────────────────────────────────
D2_DIRECTION="right"
D2_FONT_SIZE=50           # **.style.font-size (nested elements)
D2_LABEL_FONT_SIZE=100    # *.style.font-size (top-level container labels)

# ── Connector style defaults ────────────────────────────────────────
D2_CONNECTOR_STROKE_WIDTH=12
D2_CONNECTOR_FONT_SIZE=55
D2_SOLID_STROKE_COLOR="#333333"

# ── Render defaults (all diagrams) ──────────────────────────────────
RENDER_LAYOUT="tala"
RENDER_SCALE=0.3
RENDER_PAD=50

# Seeds that produce layouts within TALA's dimension limits for the
# detailed diagram (~80+ classes). TALA runs all seeds in parallel and
# picks the best result.  Re-scan if the diagram grows significantly:
#   for s in $(seq 0 20); do ... --tala-seeds "$s" ... ; done
DETAILED_TALA_SEEDS="4,6,11,13,14"

# ── Build the D2 preamble (globals + style classes) ──────────────────
build_preamble() {
  cat <<PREAMBLE
direction: ${D2_DIRECTION}
**.style.font-size: ${D2_FONT_SIZE}
*.style.font-size: ${D2_LABEL_FONT_SIZE}

classes: {
  composition: {
    # NOTE: source-arrowhead.shape: diamond doesn't propagate via classes (D2 limitation)
    style.stroke: "${D2_SOLID_STROKE_COLOR}"
    style.stroke-width: ${D2_CONNECTOR_STROKE_WIDTH}
    style.font-size: ${D2_CONNECTOR_FONT_SIZE}
  }
  dependency: {
    target-arrowhead: {
      shape: arrow
      style.filled: false
    }
    style.stroke-dash: 3
    style.stroke-width: ${D2_CONNECTOR_STROKE_WIDTH}
    style.font-size: ${D2_CONNECTOR_FONT_SIZE}
  }
  inheritance: {
    target-arrowhead: {
      shape: triangle
      style.filled: false
    }
    style.stroke: "${D2_SOLID_STROKE_COLOR}"
    style.stroke-width: ${D2_CONNECTOR_STROKE_WIDTH}
    style.font-size: ${D2_CONNECTOR_FONT_SIZE}
  }
  implementation: {
    target-arrowhead: {
      shape: triangle
      style.filled: false
    }
    style.stroke-dash: 3
    style.stroke-width: ${D2_CONNECTOR_STROKE_WIDTH}
    style.font-size: ${D2_CONNECTOR_FONT_SIZE}
  }
}
PREAMBLE
}

# ── Generate per-module diagrams from detailed source ─────────────────
# Convert the multi-line preamble into --preamble args (one per line).
preamble_args=()
while IFS= read -r line; do
  preamble_args+=(--preamble "$line")
done < <(build_preamble)

python -m tools.generate_module_diagrams "${preamble_args[@]}"

# ── Render diagram-detailed SVG ──────────────────────────────────────
{
  build_preamble
  echo ""
  cat "docs/diagrams/uml/diagram-detailed.d2"
} | d2 --layout "$RENDER_LAYOUT" --scale "$RENDER_SCALE" --pad "$RENDER_PAD" \
    --tala-seeds "$DETAILED_TALA_SEEDS" \
    - "docs/diagrams/uml/diagram-detailed.svg"

# ── Render per-module SVGs ───────────────────────────────────────────
MODULE_DIR="docs/diagrams/uml/modules"
if [ -d "$MODULE_DIR" ]; then
  for d2_file in "$MODULE_DIR"/diagram-*.d2; do
    [ -f "$d2_file" ] || continue
    svg_file="${d2_file%.d2}.svg"
    d2 --layout "$RENDER_LAYOUT" --scale "$RENDER_SCALE" --pad "$RENDER_PAD" \
      "$d2_file" "$svg_file"
  done
fi

# ── Render module-overview SVG ───────────────────────────────────────
OVERVIEW="docs/diagrams/uml/diagram-modules.d2"
if [ -f "$OVERVIEW" ]; then
  d2 --layout "$RENDER_LAYOUT" --scale 0.5 --pad "$RENDER_PAD" \
    "$OVERVIEW" "${OVERVIEW%.d2}.svg"
fi
