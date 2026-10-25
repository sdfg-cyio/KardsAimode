# KardsAimode：KARDS 私服人机对战

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
git clone https://github.com/sdfg-cyio/KardsAimode ~/KardsAimode
bash ~/KardsAimode/install.sh
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

| 名称 | 卡组 | 指挥官 | 总部 |
|---|---|---|---|
| usa_ramp | 美英跳 | 生盐诺亚 | 华盛顿 |
| usa_assault | 美法高油 | 凯伊 | 阿拉库尔 |
| germany_ramp | 德美跳 | 逸见艾丽卡 | 阿登 |
| germany_panzer | 德芬车 | 艾拉·伊尔玛塔 | 维莱博卡日 |
| soviet_control | 苏意控 | 喀秋莎 | 布良斯克 |
| japan_legion | 日波军团 | 玛莉亚·临光 | 马尼拉 |
| japan_burst | 日法爆牌 | 押田流歌 | 碧瑶 |
| britain_meteor | 英澳流星 | 阿尔托莉雅·潘德拉贡 | 突尼斯城 |
| britain_firewall | 英美防火墙 | 大吉岭 | 伦敦 |
| soviet_convert | 苏波转换 | 艾莉莎·米哈伊罗夫纳 | 莫斯科 |
| britain_buffs | 英美米色团 | 千户 | 阿拉姆哈勒法 |
| japan_air | 日美飞燕 | 信浓 | 马尼拉 |

难度（只在本地人机局里生效；写在卡组名前面，不写 = 普通）：

```bash
kards comet 地狱 soviet_convert   # 也可写 veteran / elite / hell
```

| 档位 | 加成 |
|---|---|
| 普通 | 无 |
| 老兵 | 起手从卡组的候选池里随机挑；总部 +5 |
| 精英 | 老兵 + 从第 6 回合起每回合 +1 指挥点；总部 +10；手牌少于 4 张时从牌库摸 1 张 |
| 地狱 | 起手候选池 + 每回合 +1 指挥点；总部 +20；手牌少于 4 张时凭空打印 1 张核心牌（每张只打印 1 次） |

“+1 指挥点”是每回合往 AI 手牌送一张“生产”（0 费，本回合 +1 指挥点），由 AI 自己打出，对局里看得见。
加成用的是客户端自带的开发者作弊函数（目前只在 COMET 4.x 上验证过）。

## 单机模式（私服关了也能打人机）

代理会自动把私服的回应录到 `/sdcard/Download/kardsai_archive/`（密码不存）。
**趁私服还在，先联网正常玩一轮**：登录、看看收藏/商店、改一次卡组、打一局训练。之后：

```bash
kards offline              # 完全不连私服；也可以 kards offline usa_ramp 指定对手
```

- 私服连不上时，`kards` 会自动进入离线模式（启动时会显示“离线模式”）。
- 离线时：登录、收藏、卡组、训练局全在本机；卡组的增删改存在录档目录的 `offline_state.json`，不会同步回私服。
- 离线时 PvP 不可用。
- 建议把 `kardsai_archive` 整个备份到电脑。

## 更新

```bash
cd ~/KardsAimode && git pull && bash install.sh
```

## 注意

- 修改版 apk 的所有请求都经过本机代理：**不开 `kards` 时游戏连不上服务器**（会提示 Network error），PvP 也要先启动 `kards`。
  代理中途退出会导致正在进行的对局断线。只想打 PvP、不想开 Termux 的话，继续用原版私服 apk。
- 部分手机会在后台杀掉 Termux：请在系统设置里允许 Termux 后台运行、关闭电池优化。
- 提示端口 5233 被占用：说明已有一个代理在运行（或电脑上的 `adb reverse` 没删），先关掉旧的。
- 反馈问题时请附上 `/sdcard/Download/kardsai_logs/` 里的 `proxy.log` 和 `ai_audit.log`。
