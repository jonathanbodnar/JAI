#!/usr/bin/env bash
# Render PNG fallbacks from apps/web/public/icon.svg.
# Requires `rsvg-convert` (brew install librsvg) or ImageMagick `magick`.
set -e
cd "$(dirname "$0")/.."

SVG="apps/web/public/icon.svg"
OUT="apps/web/public"

render() {
  local size=$1
  local out=$2
  if command -v rsvg-convert >/dev/null; then
    rsvg-convert -w "$size" -h "$size" "$SVG" -o "$out"
  elif command -v magick >/dev/null; then
    magick -density 600 -background none "$SVG" -resize "${size}x${size}" "$out"
  elif command -v convert >/dev/null; then
    convert -density 600 -background none "$SVG" -resize "${size}x${size}" "$out"
  else
    echo "install librsvg (brew install librsvg) or imagemagick first" >&2
    exit 1
  fi
  echo "  → $out"
}

render 192 "$OUT/icon-192.png"
render 512 "$OUT/icon-512.png"
render 1024 "$OUT/icon-1024.png"
# Apple touch icon
render 180 "$OUT/apple-touch-icon.png"

echo "done."
