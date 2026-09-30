#!/bin/bash
# Remove Al-Aqsa: the background service, the Omarchy bar widget (if added), the
# `al-aqsa` command, the launcher entry and the icon.
# Your settings and prayer log are kept unless you pass --purge.
set -uo pipefail

cd "$(dirname "$0")"

if [[ -x .venv/bin/al-aqsa ]] && command -v omarchy >/dev/null; then
  .venv/bin/al-aqsa --omarchy-bar remove >/dev/null 2>&1 || true
fi

systemctl --user disable --now al-aqsa-notify.service >/dev/null 2>&1 || true
rm -f ~/.config/systemd/user/al-aqsa-notify.service
systemctl --user daemon-reload >/dev/null 2>&1 || true

rm -f ~/.local/bin/al-aqsa ~/.local/share/applications/Al-Aqsa.desktop
rm -f ~/.local/share/icons/hicolor/*/apps/al-aqsa.png ~/.local/share/icons/hicolor/scalable/apps/al-aqsa.svg
update-desktop-database ~/.local/share/applications >/dev/null 2>&1 || true
gtk-update-icon-cache -f -t ~/.local/share/icons/hicolor >/dev/null 2>&1 || true

if [[ ${1:-} == --purge ]]; then
  rm -rf ~/.config/al-aqsa ~/.local/share/al-aqsa
  echo "Removed Al-Aqsa and your settings and prayer log."
else
  echo "Removed Al-Aqsa. Your settings and prayer log are still in ~/.config/al-aqsa and ~/.local/share/al-aqsa"
  echo "(run ./uninstall.sh --purge to delete them too)."
fi
echo "You can now delete this folder."
