#!/usr/bin/env bash
# 一键构建：网页单文件 → 图标 → macOS App
# 用法：./build.sh          构建 build/架构刷题.app
#      ./build.sh web      只生成 app/index.html
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

APP_NAME="架构刷题"
EXEC_NAME="ArchQuiz"
BUNDLE_ID="local.jiagou.shuati"
BUILD="build"
OUT_APP="$BUILD/$APP_NAME.app"

need() { command -v "$1" >/dev/null 2>&1 || { echo "缺少 $1，请先安装：$2"; exit 1; }; }

echo "==> [1/3] 注入题库，生成 app/index.html"
need python3 "brew install python3"
python3 tools/build.py

[ "${1:-}" = "web" ] && { echo "完成：$ROOT/app/index.html"; exit 0; }

echo "==> [2/3] 生成 AppIcon.icns"
need sips "系统自带，缺失请检查 Xcode 命令行工具"
need iconutil "系统自带，缺失请检查 Xcode 命令行工具"
ICONSET="$BUILD/AppIcon.iconset"
rm -rf "$ICONSET" && mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z "$s" "$s" app/src/icon.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  d=$((s * 2))
  sips -z "$d" "$d" app/src/icon.png --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$BUILD/AppIcon.icns"
rm -rf "$ICONSET"

echo "==> [3/3] 编译并打包 $APP_NAME.app"
need swiftc "xcode-select --install"
rm -rf "$OUT_APP"
mkdir -p "$OUT_APP/Contents/MacOS" "$OUT_APP/Contents/Resources"
swiftc -O app/src/main.swift app/src/docx.swift -o "$OUT_APP/Contents/MacOS/$EXEC_NAME"
cp app/index.html "$OUT_APP/Contents/Resources/app.html"
cp "$BUILD/AppIcon.icns" "$OUT_APP/Contents/Resources/AppIcon.icns"

cat > "$OUT_APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>$APP_NAME</string>
  <key>CFBundleDisplayName</key><string>$APP_NAME</string>
  <key>CFBundleExecutable</key><string>$EXEC_NAME</string>
  <key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
  <key>CFBundleVersion</key><string>1.2</string>
  <key>CFBundleShortVersionString</key><string>1.2</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>LSApplicationCategoryType</key><string>public.app-category.education</string>
</dict></plist>
PLIST

# 本地 ad-hoc 签名：避免每次打开都被 Gatekeeper 拦
codesign --force --deep --sign - "$OUT_APP" >/dev/null 2>&1 || \
  echo "    （ad-hoc 签名失败，可忽略；首次打开右键 → 打开）"

echo
echo "完成：$ROOT/$OUT_APP"
echo "安装：cp -R \"$OUT_APP\" /Applications/"
