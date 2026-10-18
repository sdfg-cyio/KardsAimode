#!/data/data/com.termux/files/usr/bin/bash
# 安装/更新：在 Termux 里运行包里的这个脚本，例如
#   bash ~/WardsAimode/install.sh            （git clone 下来的）
#   bash /sdcard/Download/kardsai/install.sh （电脑 adb push 过来的）
# 会把包复制到 ~/kardsai（在 Termux 自己的目录里跑，比直接在 sdcard 上快、不受存储权限影响）
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
DST="$HOME/kardsai"
# 下面会先删掉 ~/kardsai 再复制：源目录就是它的话会把自己删掉
if [ "$SRC" = "$(cd "$DST" 2>/dev/null && pwd)" ]; then
    echo "不要把包放在 $DST 里安装（会被清空）。请 clone 到别的目录，例如 ~/WardsAimode"
    exit 1
fi
command -v python >/dev/null || pkg install -y python
# 保留上次的随机对手记录
HIST="$DST/proxy/ai_mix_history.json"
[ -f "$HIST" ] && cp "$HIST" "$HOME/.ai_mix_history.json"
rm -rf "$DST"
mkdir -p "$DST"
cp -r "$SRC/proxy" "$SRC/native" "$SRC/work" "$SRC/start.sh" "$DST/"
[ -f "$HOME/.ai_mix_history.json" ] && mv "$HOME/.ai_mix_history.json" "$HIST"
chmod +x "$DST/start.sh"
# 快捷命令：以后在 Termux 里输入 kards 就启动
mkdir -p "$PREFIX/bin"
printf '#!/data/data/com.termux/files/usr/bin/bash\nexec "$HOME/kardsai/start.sh" "$@"\n' > "$PREFIX/bin/kards"
chmod +x "$PREFIX/bin/kards"
echo "安装完成：$(python --version)。输入 kards 启动"
