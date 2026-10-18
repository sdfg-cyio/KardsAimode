#!/data/data/com.termux/files/usr/bin/bash
# 在 Termux 里运行人机代理 + AI（不需要电脑）：
#   游戏 -> 127.0.0.1:5233（本代理）-> 私服；AI 经 127.0.0.1:23456 直连游戏里的探针
# 用法：kards            随机对手（所有已登记卡组轮换，连续 3 局不重复）
#       kards japan_legion   固定某一套
cd "$HOME/kardsai/proxy"
export KARDS_AI_DECK="${1:-${KARDS_AI_DECK:-mix}}"
export PYTHONIOENCODING=utf-8
# 日志放 sdcard：电脑连上时能 adb pull 取回来看
LOGS=/sdcard/Download/kardsai_logs
if mkdir -p "$LOGS" 2>/dev/null && touch "$LOGS/.w" 2>/dev/null; then
    export KARDS_LOG_DIR="$LOGS"
else
    LOGS="$HOME/kardsai/proxy"
    echo "（没有存储权限，日志写在 $LOGS；运行 termux-setup-storage 授权后可放到 Download）"
fi
termux-wake-lock 2>/dev/null || true   # 防止息屏后被系统挂起
echo "KARDS 人机代理启动（对手：$KARDS_AI_DECK），保持 Termux 不要关闭；日志 $LOGS/proxy.log"
python -u kards_proxy.py 5233 2>&1 | tee -a "$LOGS/proxy.log"
echo "代理已退出。若提示端口 5233 被占用：电脑上的 adb reverse 还在，拔掉 USB 或让电脑执行 adb reverse --remove tcp:5233"
