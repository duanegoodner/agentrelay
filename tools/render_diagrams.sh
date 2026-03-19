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

# ── Per-variant overrides (uncomment to customize) ──────────────────
# STANDARD_RENDER_SCALE=0.4
# STANDARD_D2_FONT_SIZE=55
# NO_IMPL_RENDER_SCALE=0.35

# ── Helper: resolve per-variant value or fall back to default ───────
variant_val() {
  local variant_upper="${1^^}"       # e.g. "standard" -> "STANDARD"
  variant_upper="${variant_upper//-/_}" # e.g. "NO-PRIVATE" -> "NO_PRIVATE"
  local param="$2"                   # e.g. "RENDER_SCALE"
  local default="$3"
  local varname="${variant_upper}_${param}"
  echo "${!varname:-$default}"
}

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

# ── Generate filtered D2 variants with style preamble ────────────────
# Convert the multi-line preamble into --preamble args (one per line).
preamble_args=()
while IFS= read -r line; do
  preamble_args+=(--preamble "$line")
done < <(build_preamble)

python -m tools.generate_diagrams "${preamble_args[@]}"

# ── Render all SVGs ──────────────────────────────────────────────────
for variant in detailed no-private no-impl standard; do
  scale=$(variant_val "$variant" RENDER_SCALE "$RENDER_SCALE")
  pad=$(variant_val "$variant" RENDER_PAD "$RENDER_PAD")
  layout=$(variant_val "$variant" RENDER_LAYOUT "$RENDER_LAYOUT")

  if [ "$variant" = "detailed" ]; then
    # Detailed diagram is the source — prepend preamble directly for rendering.
    {
      build_preamble
      echo ""
      cat "docs/diagrams/uml/diagram-detailed.d2"
    } | d2 --layout "$layout" --scale "$scale" --pad "$pad" - "docs/diagrams/uml/diagram-detailed.svg"
  else
    d2 --layout "$layout" --scale "$scale" --pad "$pad" \
      "docs/diagrams/uml/diagram-${variant}.d2" "docs/diagrams/uml/diagram-${variant}.svg"
  fi
done
