#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
APP_NAME="Code Browser.app"
INSTALL_DIR=${CODE_BROWSER_MAC_APP_DIR:-"$HOME/Applications"}
APP_PATH="$INSTALL_DIR/$APP_NAME"
ICON_SOURCE="$REPO_DIR/static/icons/code-browser-512.png"
ICON_NAME="CodeBrowser"
TMP_DIR=$(mktemp -d "${TMPDIR:-/tmp}/code-browser-icon.XXXXXX")
ICONSET_DIR="$TMP_DIR/$ICON_NAME.iconset"

cleanup() { rm -rf "$TMP_DIR"; }
trap cleanup EXIT INT TERM

if [ ! -f "$ICON_SOURCE" ]; then
    echo "Icon source not found: $ICON_SOURCE" >&2
    exit 1
fi

mkdir -p "$INSTALL_DIR" "$ICONSET_DIR"
for spec in \
    "16 16x16" "32 16x16@2x" \
    "32 32x32" "64 32x32@2x" \
    "128 128x128" "256 128x128@2x" \
    "256 256x256" "512 256x256@2x" \
    "512 512x512" "1024 512x512@2x"; do
    size=${spec%% *}
    name=${spec#* }
    /usr/bin/sips -s format png -z "$size" "$size" "$ICON_SOURCE" --out "$ICONSET_DIR/icon_${name}.png" >/dev/null
done
/usr/bin/iconutil -c icns "$ICONSET_DIR" -o "$TMP_DIR/$ICON_NAME.icns"

if [ -e "$APP_PATH" ]; then /bin/rm -rf "$APP_PATH"; fi

sed "s|__REPO_DIR__|$REPO_DIR|g" "$SCRIPT_DIR/code_browser_launcher.applescript" > "$TMP_DIR/launcher.applescript"
/usr/bin/osacompile -o "$APP_PATH" "$TMP_DIR/launcher.applescript"
/bin/cp "$TMP_DIR/$ICON_NAME.icns" "$APP_PATH/Contents/Resources/$ICON_NAME.icns"
/usr/bin/plutil -replace CFBundleDisplayName -string "Code Browser" "$APP_PATH/Contents/Info.plist"
/usr/bin/plutil -replace CFBundleName -string "Code Browser" "$APP_PATH/Contents/Info.plist"
/usr/bin/plutil -replace CFBundleIconName -string "$ICON_NAME" "$APP_PATH/Contents/Info.plist"
/usr/bin/plutil -insert CFBundleIconFile -string "$ICON_NAME" "$APP_PATH/Contents/Info.plist" 2>/dev/null || \
    /usr/bin/plutil -replace CFBundleIconFile -string "$ICON_NAME" "$APP_PATH/Contents/Info.plist"
/usr/bin/touch "$APP_PATH"

echo "Installed: $APP_PATH"
echo "Launch it, choose a project folder, and Code Browser will open in your default browser."
