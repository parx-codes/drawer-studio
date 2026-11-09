#!/bin/sh
# Installa il bundle Linux già costruito e aggiorna il collegamento sulla Scrivania.
set -eu

bundle=${1:?Indica la cartella del bundle DrawER Studio}
version=${2:?Indica la versione del bundle}
case "$version" in
    *[!0-9.]*|.*|*.) printf 'Versione non valida: %s\n' "$version" >&2; exit 1 ;;
esac
test -x "$bundle/DrawER Studio"
test -d "$bundle/_internal"

install_root="$HOME/.local/opt/DrawER Studio"
desktop_dir=$(xdg-user-dir DESKTOP)
launcher="$desktop_dir/DrawER Studio.desktop"
if [ -e "$launcher" ] && ! grep -qx 'X-DrawER-Managed=true' "$launcher"; then
    printf 'Esiste già un collegamento diverso: %s\n' "$launcher" >&2
    exit 1
fi

mkdir -p "$install_root/versions"
version_dir="$install_root/versions/$version"
if [ ! -e "$version_dir" ]; then
    staged=$(mktemp -d "$install_root/versions/.install.XXXXXX")
    cp -a "$bundle/." "$staged/"
    mv -T "$staged" "$version_dir"
fi
test -x "$version_dir/DrawER Studio"
staged=$(mktemp -d "$install_root/.link.XXXXXX")
ln -s "versions/$version" "$staged/current"
mv -Tf "$staged/current" "$install_root/current"
rmdir "$staged"

cat > "$launcher" <<DESKTOP
[Desktop Entry]
Type=Application
Name=DrawER Studio
Comment=Editor di diagrammi Entità–Relazione
Exec="$install_root/current/DrawER Studio" %f
Icon=applications-graphics
Terminal=false
Categories=Graphics;Education;
X-DrawER-Managed=true
DESKTOP
chmod +x "$launcher"
if command -v gio >/dev/null 2>&1; then
    gio set "$launcher" metadata::trusted true 2>/dev/null || true
fi
printf '%s\n' "$launcher"
