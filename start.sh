#!/data/data/com.termux/files/usr/bin/bash
# 在 Termux 里运行人机代理 + AI（不需要电脑）：
#   游戏 -> 127.0.0.1:5233（本代理）-> 私服；AI 经 127.0.0.1:23456 直连游戏里的探针
# 用法：kards            随机对手（所有已登记卡组轮换，连续 3 局不重复）
#       kards japan_legion   固定某一套
#       kards offline [卡组]  离线模式：完全不连私服（要先联网玩过一轮录档）；kards online 强制联网
#       （默认自动：私服连不上且有录档时自动离线）
#       kards comet [offline|online] [卡组]  给 COMET 4.x 客户端用（连 comet 服，端口 5235，录档单独一份）
#       难度：kards comet 老兵|精英|地狱 [卡组]（也可写 veteran/elite/hell；不写 = 普通）
#         老兵：起手候选池 + 总部 +5；精英：老兵 + 第 6 回合起每回合 +1 指挥点 + 总部 +10 + 手牌 <4 摸 1 张；
#         地狱：起手候选池 + 每回合 +1 指挥点 + 总部 +20 + 手牌 <4 打印 1 张核心牌（每张只打印 1 次）
#         “+1 指挥点”= 每回合往 AI 手牌送一张“生产”，AI 自己打出
PORT=5233
ARCH=kardsai_archive
if [ "$1" = "comet" ]; then
    export KARDS_UPSTREAM=comet; PORT=5235; ARCH=kardsai_archive_comet; shift
fi
# 联网方式和难度档位顺序随意：kards comet hell soviet_convert / kards comet offline 精英
while [ $# -gt 0 ]; do
    case "$1" in
        offline) export KARDS_OFFLINE=1; shift ;;
        online)  export KARDS_OFFLINE=0; shift ;;
        normal|普通|veteran|vet|老兵|elite|hard|精英|hell|nightmare|地狱) export KARDS_LEVEL="$1"; shift ;;
        *) break ;;
    esac
done
cd "$HOME/kardsai/proxy"
export KARDS_AI_DECK="${1:-${KARDS_AI_DECK:-mix}}"
export PYTHONIOENCODING=utf-8
# 日志放 sdcard：电脑连上时能 adb pull 取回来看
LOGS=/sdcard/Download/kardsai_logs
if mkdir -p "$LOGS" 2>/dev/null && touch "$LOGS/.w" 2>/dev/null; then
    export KARDS_LOG_DIR="$LOGS"
    # 单机保留地：私服回应录档放 Download（重新安装会清空 ~/kardsai，录档不能放那里）
    export KARDS_ARCHIVE_DIR=/sdcard/Download/$ARCH
else
    LOGS="$HOME/kardsai/proxy"
    export KARDS_ARCHIVE_DIR="$HOME/$ARCH"
    echo "（没有存储权限，日志写在 $LOGS；运行 termux-setup-storage 授权后可放到 Download）"
fi
termux-wake-lock 2>/dev/null || true   # 防止息屏后被系统挂起
echo "KARDS 人机代理启动（${KARDS_UPSTREAM:-wards}，端口 $PORT，对手：$KARDS_AI_DECK，难度：${KARDS_LEVEL:-普通}），保持 Termux 不要关闭；日志 $LOGS/proxy.log"
python -u kards_proxy.py $PORT 2>&1 | tee -a "$LOGS/proxy.log"
echo "代理已退出。若提示端口 $PORT 被占用：电脑上的 adb reverse 还在，拔掉 USB 或让电脑执行 adb reverse --remove tcp:$PORT"
