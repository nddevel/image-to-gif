#!/usr/bin/env bash
# Adds "Image to GIF" to the GNOME app grid and to "Open With" for images.
# Only writes to ~/.local/share/applications. Undo with:
#   rm ~/.local/share/applications/io.github.imagetogif.ImageToGif.desktop
set -euo pipefail
DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
TARGET="$HOME/.local/share/applications/io.github.imagetogif.ImageToGif.desktop"
mkdir -p "$(dirname "$TARGET")"
cat > "$TARGET" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Image to GIF
Comment=Convert PNG, JPG, WebP, HEIC, SVG and other images to GIF
Exec="$DIR/run.sh" %F
Icon=image-x-generic
Terminal=false
Categories=Graphics;GTK;GNOME;
MimeType=image/png;image/jpeg;image/gif;image/bmp;image/webp;image/tiff;image/heic;image/heif;image/avif;image/svg+xml;image/x-icon;image/vnd.microsoft.icon;image/x-tga;image/x-portable-pixmap;image/jxl;
StartupNotify=true
DESKTOP
update-desktop-database "$(dirname "$TARGET")" 2>/dev/null || true
echo "Installed: $TARGET"
