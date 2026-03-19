#!/usr/bin/env bash
set -euo pipefail

# ── D2 style defaults (all diagrams) ────────────────────────────────
D2_DIRECTION="right"
D2_FONT_SIZE=50           # **.style.font-size (nested elements)
D2_LABEL_FONT_SIZE=100    # *.style.font-size (top-level container labels)

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

# ── Generate filtered D2 variants with style preamble ────────────────
python -m tools.generate_diagrams \
  --preamble "direction: ${D2_DIRECTION}" \
  --preamble "**.style.font-size: ${D2_FONT_SIZE}" \
  --preamble "*.style.font-size: ${D2_LABEL_FONT_SIZE}"

# ── Render all SVGs ──────────────────────────────────────────────────
for variant in detailed no-private no-impl standard; do
  scale=$(variant_val "$variant" RENDER_SCALE "$RENDER_SCALE")
  pad=$(variant_val "$variant" RENDER_PAD "$RENDER_PAD")
  layout=$(variant_val "$variant" RENDER_LAYOUT "$RENDER_LAYOUT")

  if [ "$variant" = "detailed" ]; then
    # Detailed diagram is the source — prepend preamble directly for rendering.
    {
      echo "direction: ${D2_DIRECTION}"
      echo "**.style.font-size: ${D2_FONT_SIZE}"
      echo "*.style.font-size: ${D2_LABEL_FONT_SIZE}"
      echo ""
      cat "docs/diagram-detailed.d2"
    } | d2 --layout "$layout" --scale "$scale" --pad "$pad" - "docs/diagram-detailed.svg"
  else
    d2 --layout "$layout" --scale "$scale" --pad "$pad" \
      "docs/diagram-${variant}.d2" "docs/diagram-${variant}.svg"
  fi
done
