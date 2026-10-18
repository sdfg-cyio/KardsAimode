# WardsAimode：KARDS 私服人机对战

给 KARDS 私服客户端加回“训练（人机）”模式。代理和 AI 全部跑在手机的 Termux 里，不需要电脑。

- 人机局由本地代理接管，AI 直接读取游戏里的真实场面并只做合法操作；
- PvP 照常：登录、匹配、对战请求由代理原样转发给私服。

## 需要准备

1. **修改版私服 apk**（不在本仓库里，请向分享者索取）：服务器地址改成了本机 `127.0.0.1:5233`，并带有 AI 读取场面用的探针。
   原版私服 apk 和它签名不同，需要先卸载原版再安装；账号在服务器上，重新登录即可，卡组不会丢。
2. **Termux**：建议从 F-Droid 或 GitHub 安装最新版（应用商店里的旧版无法更新软件包）。

## 安装

在 Termux 里依次执行：

```bash
pkg update -y
pkg install -y git python
git clone https://github.com/sdfg-cyio/WardsAimode ~/WardsAimode
bash ~/WardsAimode/install.sh
```

可选：执行 `termux-setup-storage` 授权存储，日志会写到 `/sdcard/Download/kardsai_logs/`，方便取出来反馈问题。

> 不要 clone 到 `~/kardsai`：那是安装目录，每次安装都会被清空。

## 使用

1. 打开 Termux，输入 `kards` 启动代理，**保持 Termux 不要关闭**（可以切到后台）。
2. 打开游戏登录，进入训练模式开局，对手就是本地 AI。
3. 打完后在 Termux 里按 `Ctrl+C` 退出代理。

指定对手卡组：

```bash
kards                 # 默认：从所有卡组中随机，连续 3 局不重复
kards usa_ramp        # 固定某一套
```

| 名称 | 卡组 |
|---|---|
| usa_ramp | 美英加费控制 |
| usa_assault | 美法“行动费 3+”进攻 |
| germany_ramp | 德美加费 |
| germany_panzer | 德芬“车车” |
| soviet_control | 苏意控制 |
| japan_legion | 日波汝即军团 |
| japan_burst | 日法“手牌爆炸” |
| britain_meteor | 英澳流星 |
| britain_firewall | 英美 Firewall 堡垒 |

## 更新

```bash
cd ~/WardsAimode && git pull && bash install.sh
```

## 注意

- 修改版 apk 的所有请求都经过本机代理：**不开 `kards` 时游戏连不上服务器**（会提示 Network error），PvP 也要先启动 `kards`。
  代理中途退出会导致正在进行的对局断线。只想打 PvP、不想开 Termux 的话，继续用原版私服 apk。
- 部分手机会在后台杀掉 Termux：请在系统设置里允许 Termux 后台运行、关闭电池优化。
- 提示端口 5233 被占用：说明已有一个代理在运行（或电脑上的 `adb reverse` 没删），先关掉旧的。
- 反馈问题时请附上 `/sdcard/Download/kardsai_logs/` 里的 `proxy.log` 和 `ai_audit.log`。
