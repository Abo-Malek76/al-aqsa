#!/bin/bash
# Install Al-Aqsa for the current user: a private Python environment, the `al-aqsa`
# command, a launcher entry and the icon. On Omarchy the app adds its bar widget
# and starts its background service the first time it runs.
set -euo pipefail

cd "$(dirname "$0")"
here="$(pwd)"

python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e .

mkdir -p ~/.local/bin ~/.local/share/applications
ln -sf "$here/.venv/bin/al-aqsa" ~/.local/bin/al-aqsa

for size in 32 48 64 128 256 512; do
  dir=~/.local/share/icons/hicolor/${size}x${size}/apps
  mkdir -p "$dir"
  if command -v rsvg-convert >/dev/null; then
    rsvg-convert -w "$size" -h "$size" assets/al-aqsa.svg -o "$dir/al-aqsa.png"
  fi
done
mkdir -p ~/.local/share/icons/hicolor/scalable/apps
cp assets/al-aqsa.svg ~/.local/share/icons/hicolor/scalable/apps/al-aqsa.svg
gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor >/dev/null 2>&1 || true

if command -v omarchy-launch-or-focus-tui >/dev/null; then
  exec_line="omarchy-launch-or-focus-tui al-aqsa"
  terminal=false
else
  exec_line="al-aqsa"
  terminal=true
fi
cat > ~/.local/share/applications/Al-Aqsa.desktop <<DESKTOP
[Desktop Entry]
Version=1.0
Name=Al-Aqsa
GenericName=Prayer Times
Comment=Prayer times from your mosque, countdown and prayer tracker
Keywords=prayer;salah;salat;namaz;mosque;islam;adhan;aqsa;
Exec=$exec_line
Terminal=$terminal
Type=Application
Icon=al-aqsa
Categories=Utility;
StartupNotify=true
DESKTOP
update-desktop-database ~/.local/share/applications >/dev/null 2>&1 || true

echo "Installed. Run 'al-aqsa' or pick Al-Aqsa from your app launcher."
