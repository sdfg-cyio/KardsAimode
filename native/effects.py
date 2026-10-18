# 卡牌效果引擎：每张牌按“时机”挂钩子，规则代码（sim_rules）只在各个时机点调用这里
# 卡牌本身写在 cards_*.py（按卡组分文件）；新卡组只要新建一个 cards_xxx.py 并在文末导入
#
# 钩子一览（f 的参数见右侧）：
#   打出指令    play(sim, c, t, k)               t = 目标 id（0 无目标），k = 抉择序号
#   指令选项    options(sim, c) -> [(t, k)]      缺省：choose_one 的牌 [(0,0),(0,1)]，其余 [(0,0)]
#   抉择牌      choose_one = True                0 = 卡面第一个选项
#   部署效果    deploy(sim, c, t)
#   部署目标    deploy_targets(sim, c) -> [id]   缺省 [0]（无目标）
#   亡计        destroyed(sim, u)
#   被敌方效果指向  targeted(sim, u)
#   被攻击      attacked(sim, u, a) -> True      返回 True = 这次攻击不结算（如 BM-13N 撤回手牌）
#   战斗伤害加成  dmg_bonus(sim, u, t) -> int
#   造成战斗伤害后  dealt(sim, u, t, n)
#   冲击后不失去冲击  keeps_shock = True
# 光环类（单位在场上时对别的东西生效）：
#   减伤        reduce(sim, u, t, src_side, by_unit) -> int   u 一方的 t 受到伤害时减少的点数
#   总部保底    hq_floor(sim, u) -> bool          为 True 时 u 一方指挥部不低于 1
#   友方阵亡    ally_destroyed(sim, u, dead)     u 一方的其他单位被消灭后
#   友方抽牌    ally_draw(sim, u)                u 一方每抽 1 张
#   敌方抽牌    enemy_draw(sim, u)               u 的对方每抽 1 张
#   手牌中：敌方抽牌  hand_enemy_draw(sim, c)     c 在手里、对方每抽 1 张
#   友方部署    ally_deployed(sim, u, new)       u 一方部署了另一个单位 new 之后（第 96 步兵团自毁）
#   敌方阵亡    enemy_destroyed(sim, u, dead)    u 的对方有单位被消灭后（第 158 补给营）
#   友方行动后  ally_operated(sim, u, x, paid)   u 一方的单位 x 移动/攻击、付了 paid 点行动费之后（蓝色军团）
#   动态加成    stat_bonus(sim, u) -> (攻, 防)   随场面变化的加成（三号坦克 L 型）；每个动作后重算
#   发起攻击时  attacking(sim, u, t)              战斗结算之前（流星：按当时攻防复制进牌库）
#   攻击后移出  gone_after_attack = True          攻击结算后移出场（不算消灭）
#   友方下指令  ally_order(sim, u)                u 一方每打出一张指令后（卡梅伦团：第二张指令抽 2）
#   敌方下指令  enemy_order(sim, u)               u 的对方每打出一张指令后（169 掷弹兵：对方随机弃一张）
#   友方情报    ally_intel(sim, u)              u 一方使用情报牌后（军团 +1+1、塔尔努夫送军团抽牌、雷兵团）
#                intel_spawns = True              标记“送单位”类（后结算，新送来的军团不吃这一次）
#   友方预报    ally_forecast(sim, u)             u 一方预报后（H8K 抽 1）
#   攻击力被提升  atk_raised(sim, u, n)           u 的攻击力被别的牌提升了 n 点后（Sd Kfz 10 PaK 38：再 +1 到回合结束）
#                只有传了 sim 的 buff/temp_atk 才触发；src 是 u 自己时不触发（蓝图：instigatorID != 自己）
#   部署二选一  deploy_choose_one = True          deploy 钩子收 (sim, c, t, k)，k = 0 卡面第一个选项（第 5 游骑兵营）
#   打出费用    cost(sim, c) -> int               随场面变化的费用（B-24D）
#   部署之后    after_deploy(sim, u, new)        u 一方部署了另一个单位 new、部署效果结算完之后（散兵团/骇人/工兵）
#   进入战场    ally_entered(sim, u, new)        u 一方有另一个单位进入战场（部署或刷出）后（永先者团）
#   友方光环    aura(sim, u, x) -> (攻, 防)        u 在场时给同一方的其他单位 x 的加成（岚兵团），每个动作后重算
#   费用变化    cost 钩子也用于洛林十字（敌方手牌越多越便宜）
import sim_rules as R
import card_rules
from sim import SC, other

P, U = 'card_event_', 'card_unit_'
HOOKS = {'play', 'options', 'choose_one', 'deploy', 'deploy_targets', 'destroyed', 'targeted', 'attacked',
         'dmg_bonus', 'dealt', 'keeps_shock', 'reduce', 'hq_floor', 'ally_destroyed', 'ally_draw', 'enemy_draw',
         'hand_enemy_draw', 'ally_deployed', 'enemy_destroyed', 'ally_operated', 'stat_bonus',
         'attacking', 'gone_after_attack', 'ally_order', 'enemy_order', 'ally_intel', 'intel_spawns', 'ally_forecast',
         'shield_hq', 'atk_raised', 'deploy_choose_one', 'cost', 'after_deploy', 'ally_entered', 'aura'}
CARDS = {}             # 卡名 -> {钩子名: 函数或标记}


def card(name, **hooks):
    """注册（或补充）一张牌的钩子"""
    bad = set(hooks) - HOOKS
    assert not bad, f'{name}: 未知钩子 {bad}'
    CARDS.setdefault(name, {}).update(hooks)


def on(hook, *names):
    """装饰器写法：@on('play', P + 'xxx')"""
    def reg(f):
        for n in names:
            card(n, **{hook: f})
        return f
    return reg


def hook(name, h):
    return CARDS.get(name, {}).get(h)


def uhook(sim, u, h):
    """场上单位 u 的钩子：被抑制的单位没有特效"""
    return None if u.id in sim.silenced else hook(u.name, h)


def _holders(sim, side, h):
    """side 一方场上带钩子 h 的单位（被抑制的单位特效没了，不算）"""
    return [(u, CARDS[u.name][h]) for u in sim.units(side) if h in CARDS.get(u.name, ())
            and u.id not in sim.silenced]


def suppress(sim, x, src_side):
    """抑制（Kards规则.txt）：抹除词条特效和状态变化——数值回到卡面（受的伤保留），词条去掉，单位特效不再触发。
    不是压制（压制 = pinned，下回合不能移动/攻击）"""
    if x is None:
        return
    base = SC.new(x.name, x.side, x.id, x.loc)
    x.atk = min(x.atk or 0, base.atk or 0) if x.side == src_side else base.atk
    x.df = min(x.df or 0, base.df or 0)
    x.op = base.op
    x.guard = x.ambush = x.shock = x.fury = x.smoke = x.blitz = False
    x.armor = 0
    sim.temp.pop(x.id, None)
    sim.temp_op.pop(x.id, None)
    sim.silenced = sim.silenced | {x.id}


# ---------- 卡牌共用的小工具 ----------
def gain(sim, side, v):
    """附加收益记账：我方 +v，敌方 -v（用于模拟不了的跨回合收益）"""
    sim.bonus += v if side == sim.me else -v


def all_units(sim):
    return list(sim.units('left')) + list(sim.units('right'))


def buff(u, a, d, sim=None, src=None):
    """u +a+d。传了 sim 时攻击力提升会触发 u 的“攻击力被提升”（src = 造成提升的卡，是 u 自己则不触发）"""
    if u is not None:
        u.atk = (u.atk or 0) + a
        u.df = (u.df or 0) + d
        if sim is not None and a > 0:
            _atk_raised(sim, u, a, src)


def _atk_raised(sim, u, n, src):
    f = uhook(sim, u, 'atk_raised')
    if f and src is not u and u in sim.units(u.side):
        f(sim, u, n)


def rand_kill(sim, side):
    """随机消灭 side 的一个敌方单位"""
    us = sim.units(other(side))
    if us:
        sim.random_used = True
        R.destroy(sim, sim.rng.choice(us))


def rand_damage(sim, side, times):
    """对 side 的敌方所有目标（含指挥部）随机分配 times 次 1 点伤害"""
    e = other(side)
    for _ in range(times):
        cand = sim.units(e) + [sim.side[e]['hq']]
        sim.random_used = True
        R.damage(sim, sim.rng.choice(cand), 1, side)


def unit_or_hq(sim, side, t):
    """目标 id -> side 的敌方指挥部或场上单位"""
    hq = sim.side[other(side)]['hq']
    return hq if t == hq.id else sim.find(t)


def spawn(sim, side, name, line='support'):
    """把单位放到战线上（满了就不放）；返回新单位或 None"""
    d = sim.side[side]
    room = (R.SUPPORT_MAX - len(d['support']) - (sim.extra_sup if side == sim.me else 0)) if line == 'support' \
        else (R.FRONT_MAX - len(sim.side['left']['front']) - len(sim.side['right']['front']))
    if room <= 0:
        return None
    u = SC.new(name, side, sim.new_id(), line)
    R.place(sim, side, u, line)
    sim.deployed.add(u.id)                 # 刚上场：当回合不能行动（闪击除外）
    on_enter(sim, u)
    return u


def temp_atk(sim, u, n, src=None):
    """本回合内有效的攻击加成（老兔子、闪电战）：记在 sim.temp，估值时扣掉，免得当成永久加成"""
    if u is not None:
        u.atk = (u.atk or 0) + n
        sim.temp[u.id] = sim.temp.get(u.id, 0) + n
        if n > 0:
            _atk_raised(sim, u, n, src)


def temp_op(sim, u, n):
    """本回合内的行动费变化（闪电战 -1）：记在 sim.temp_op，卡组估值时区分永久减费"""
    if u is not None and u.op is not None:
        d = max(-u.op, n)
        u.op += d
        sim.temp_op[u.id] = sim.temp_op.get(u.id, 0) + d


def once(sim, key):
    """每回合一次的效果：第一次返回 True 并记下（跨步骤由 TurnLog.once 带过来）"""
    if key in sim.once:
        return False
    sim.once.add(key)
    return True


def research(a, b, n_b=1):
    """研发类抉择：0 -> 手牌加 a；1 -> 手牌加 n_b 张 b"""
    def f(sim, c, t, k):
        for _ in range(1 if k == 0 else n_b):
            R.add_hand(sim, c.side, a if k == 0 else b)
    f.products = ((a, 1), (b, n_b))           # 研发链估值用（research_v.chain_hold）
    return f


def enemy_targets(sim, side, lines, smoke_ok=False, by_order=False):
    """可被效果指向的敌方单位：隐蔽单位无法被指向；烟幕只挡单位攻击，指令可以指向（smoke_ok）。
    部署效果能否指向烟幕单位未确认，保守排除。by_order = 指令的目标：排除“不能被敌方指令指向”的单位"""
    e = other(side)
    return [u.id for line in lines for u in sim.side[e][line] if not u.covert and (smoke_ok or not u.smoke)
            and not (by_order and card_rules.order_immune(u.name))]


# ---------- 规则在各时机点调用的入口 ----------
def deploy_targets(sim, c):
    """部署效果的目标选项（目标 id 列表；0 = 无目标）"""
    f = hook(c.name, 'deploy_targets')
    return (f(sim, c) or [0]) if f else [0]


def deploy_options(sim, c):
    """部署的 [(目标id, 抉择序号)]：部署时二选一的单位（第 5 游骑兵营）给两个序号"""
    ks = (0, 1) if hook(c.name, 'deploy_choose_one') else (0,)
    return [(t, k) for t in deploy_targets(sim, c) for k in ks]


def cost(sim, c):
    """这张手牌现在打出要花多少（B-24D：控制行动费 >= 3 的单位时 -3）。
    卡面费用按卡牌数据算，免得快照里客户端已经减过一次又减一次"""
    f = hook(c.name, 'cost')
    return f(sim, c) if f else c.cost


def play_options(sim, c):
    """指令的 [(目标id, 抉择序号)]；None = 不认识这张指令，不打"""
    h = CARDS.get(c.name, {})
    if 'play' not in h:
        return None
    if 'options' in h:
        return h['options'](sim, c)
    if h.get('choose_one'):
        return [(0, 0), (0, 1)]
    return [(0, 0)]


def targeted(sim, x, src_side):
    """效果指向单位 x 时调用（如 75 团：被敌方效果指向时复制一个）"""
    if x is not None and x.type != 'location' and x.side != src_side:
        f = uhook(sim, x, 'targeted')
        if f:
            f(sim, x)


def on_play(sim, c, t, k):
    if t:
        targeted(sim, sim.find(t), c.side)
    CARDS[c.name]['play'](sim, c, t, k)


def _bond(sim, c):
    """协力（通用）：场上没有其他同国单位时，受到一次疲惫伤害。
    疲惫次数已知（驱动记了 memo['fatigue']）时按等差数列走、和牌库抽空共用计数（用户确认）；不知道时按 2 点估"""
    if not any(u.faction == c.faction and u is not c for u in sim.units(c.side)):
        if c.side in sim.fatigue:
            R.fatigue(sim, c.side)
        else:
            R.damage(sim, sim.side[c.side]['hq'], 2, c.side)


FROM_THE_DEEP = 'card_event_from_the_deep'
COUNTER_STRIKE = 'card_event_counter_strike'


def enemy_counter(sim, side, name):
    """side 的对方挂着反制 name：触发一次就没了（我方回合里，side = sim.me 时才模拟）"""
    if side == sim.me and name in sim.en_cm:
        sim.en_cm = sim.en_cm - {name}
        return True
    return False


def on_deploy(sim, c, t, k=0):
    if enemy_counter(sim, c.side, FROM_THE_DEEP):
        # 对方埋了“来自深处”：部署的单位直接被消灭，部署效果不结算（实测 662056：剑兵团部署后直接没了）
        R.destroy(sim, c)
        return
    for v, g in _holders(sim, c.side, 'ally_deployed'):
        if v is not c:
            g(sim, v, c)
    if c.bond:
        _bond(sim, c)
    on_enter(sim, c)
    # “被指向时”在效果结算前触发（同 on_play）：75 团被京都联队移除/被消灭前先复制一个。
    # 原来放在部署效果之后，目标已被移走就找不到，复制漏算
    if t:
        targeted(sim, sim.find(t), c.side)
    f = hook(c.name, 'deploy')
    if f:
        if hook(c.name, 'deploy_choose_one'):
            f(sim, c, t, k)
        else:
            f(sim, c, t)
    # 部署效果（含抉择）结算之后才看新单位的行动费（用户确认：游骑兵先选 0 行动费，散兵团加 0）
    if c in sim.units(c.side):
        for v, g in _holders(sim, c.side, 'after_deploy'):
            if v is not c:
                g(sim, v, c)


def on_destroy(sim, u):
    """u 已经离开战线：先结算它自己的亡计，再结算友方的“友方阵亡”、敌方的“敌方阵亡”光环"""
    f = uhook(sim, u, 'destroyed')
    if f:
        f(sim, u)
    for v, g in _holders(sim, u.side, 'ally_destroyed'):
        g(sim, v, u)
    for v, g in _holders(sim, other(u.side), 'enemy_destroyed'):
        g(sim, v, u)
    if u.type in ('infantry', 'tank', 'artillery'):
        sim.last_dead[u.side] = u               # 伊尔-10 亡计用


def on_operated(sim, x, paid):
    """x 移动/攻击完（x 可能已阵亡：阵亡的不再触发）"""
    sim.op_count[x.id] = sim.op_count.get(x.id, 0) + 1   # 本局累计行动次数（豹式防磁装甲型）
    if x not in sim.units(x.side):
        return
    for v, g in _holders(sim, x.side, 'ally_operated'):
        g(sim, v, x, paid)


def _bonus(sim, u):
    f = uhook(sim, u, 'stat_bonus')
    a, d = f(sim, u) if f else (0, 0)
    for v, g in _holders(sim, u.side, 'aura'):
        if v is not u:
            x, y = g(sim, v, u)                  # 岚兵团：其他日本单位 +2 攻
            a, d = a + x, d + y
    return a, d


def _dyn(sim, u, auras):
    return auras or uhook(sim, u, 'stat_bonus') or getattr(u, 'stat_b', (0, 0)) != (0, 0)


def init_stats(sim):
    """开局（快照里的数值已含当前加成）：记下每个动态加成单位当前的加成量"""
    for s in ('left', 'right'):
        auras = bool(_holders(sim, s, 'aura'))
        for u in sim.units(s):
            if _dyn(sim, u, auras):
                u.stat_b = _bonus(sim, u)


def refresh_stats(sim):
    """每个动作后：动态加成单位（自身 stat_bonus、友方光环 aura）按新场面调整数值（只加减变化量）"""
    for s in ('left', 'right'):
        auras = bool(_holders(sim, s, 'aura'))
        for u in list(sim.units(s)):
            if not _dyn(sim, u, auras):
                continue
            old = getattr(u, 'stat_b', (0, 0))
            new = _bonus(sim, u)
            if new != old:
                u.atk = (u.atk or 0) + new[0] - old[0]
                u.df = (u.df or 0) + new[1] - old[1]
                u.stat_b = new
                if u.df <= 0:
                    R.destroy(sim, u)


def on_removed(sim, u):
    """被移除（不算消灭）：不触发亡计"""


def damage_reduction(sim, t, src_side, by_unit, pierce=False):
    """t 这次受伤要减掉的点数：t 一方场上的减伤光环 + 单位自身重甲（只减单位造成的伤害；效果战斗无视重甲）"""
    n = sum(f(sim, u, t, src_side, by_unit) for u, f in _holders(sim, t.side, 'reduce'))
    if t.type != 'location' and by_unit and not pierce:
        n += t.armor or 0
    return n


def hq_floor(sim, side):
    """side 的指挥部是否不低于 1（如潘兴在前线）"""
    return any(f(sim, u) for u, f in _holders(sim, side, 'hq_floor'))


def on_draw(sim, side):
    """side 抽 1 张牌时（不论手牌满没满）的联动"""
    e = other(side)
    for u, f in _holders(sim, side, 'ally_draw'):
        f(sim, u)
    for u, f in _holders(sim, e, 'enemy_draw'):
        f(sim, u)
    for c in list(sim.side[e]['hand']):
        f = hook(c.name, 'hand_enemy_draw')
        if f:
            f(sim, c)


def on_attacked(sim, t, a):
    """a 攻击单位 t 之前；返回 True = 这次攻击不结算"""
    f = uhook(sim, t, 'attacked')
    return bool(f and f(sim, t, a))


def on_attacking(sim, u, t):
    f = uhook(sim, u, 'attacking')
    if f:
        f(sim, u, t)
    for g in ATTACK_HOOKS:
        g(sim, u, t)


# 本回合生效的全局效果（天气牌：丛林热 3、热浪 3、骄阳 3）：卡牌文件往这里登记，部署/加入战场/攻击时调用
ENTER_HOOKS, ATTACK_HOOKS = [], []


def on_enter(sim, u):
    """单位进入战场（部署或刷出）"""
    for g in ENTER_HOOKS:
        g(sim, u)
    for v, g in _holders(sim, u.side, 'ally_entered'):
        if v is not u:
            g(sim, v, u)


def on_intel(sim, side, c, level=None):
    """side 使用了情报牌 c（含延长战线触发的情报）：看对方的牌，触发场上“友方使用情报牌时”。
    level = 情报等级（看几张牌）；不管等级多少，“使用情报牌”只触发一次"""
    if side == sim.me:
        sim.intel_seen += level or getattr(c, 'intel', 1) or 1
    # 先结算自身加成（军团 +1+1），再结算送军团/抽牌（塔尔努夫）：新送来的军团不吃这一次
    hs = _holders(sim, side, 'ally_intel')
    for u, f in sorted(hs, key=lambda x: hook(x[0].name, 'intel_spawns') is True):
        if u in sim.units(side):
            f(sim, u)


def forecast(sim, side):
    """预报：选一种天气，再从该天气池里选 2/4/6 费中的一张（卡组的 forecast_choice 决定）。
    用户确认：选中的天气牌在下回合开始抽完牌后才进手牌，所以本回合不加手牌，只按“下回合拿到它”的价值记账。
    选择记在 sim.forecasts，驱动按它补发两条 XActionCardToDrawSelected"""
    plan = sim.ctx.get('plan')
    pick = getattr(plan, 'forecast_choice', None)
    w, k, v = pick(sim, side) if pick else (2, 0, 1.0)
    if side == sim.me:
        sim.forecasts.append((w, k))
    gain(sim, side, v)
    for u, f in _holders(sim, side, 'ally_forecast'):
        f(sim, u)


def is_weather(name):
    """天气牌（含客户端带 2/3 后缀的变体）：每回合只能打一张（用户确认）"""
    return name.rstrip('23') in WEATHER_NAMES


# 天气池：0 晴天 / 1 降雨 / 2 风暴（第一次三选一的序号）；每种 [第一级, 2 费, 4 费, 6 费]（第二次三选一的序号 0/1/2）
WEATHER = [
    [P + 'sunny1_blue_sky', P + 'sunny2_heatwave', P + 'sunny3_jungle_fever', P + 'sunny4_scorching_sun'],
    [P + 'rain1_mist', P + 'rain2_deluge', P + 'rain3_torrential_rain', P + 'rain4_monsoon_rain'],
    [P + 'storm1_gale', P + 'storm2_thunderstorm', P + 'storm3_tropical_storm', P + 'storm4_cyclone'],
]
WEATHER_NAMES = {n for row in WEATHER for n in row[1:]}


def on_ally_order(sim, side):
    for u, f in _holders(sim, side, 'ally_order'):
        f(sim, u)
    for u, f in _holders(sim, other(side), 'enemy_order'):
        f(sim, u)


def rand_discard(sim, side):
    """side 随机弃一张手牌（规划时按抽样结算，多个抽样取平均）"""
    h = sim.side[side]['hand']
    if h:
        sim.random_used = True
        h.remove(sim.rng.choice(h))


def keeps_shock(u):
    return bool(hook(u.name, 'keeps_shock'))


def dmg_bonus(sim, u, t):
    f = uhook(sim, u, 'dmg_bonus')
    return f(sim, u, t) if f else 0


def on_dealt(sim, u, t, n):
    f = uhook(sim, u, 'dealt')
    if f and n:
        f(sim, u, t, n)


# 各卡组的牌（导入即注册）
import cards_neutral  # noqa: E402,F401
import cards_usa  # noqa: E402,F401
import cards_soviet  # noqa: E402,F401
import cards_germany  # noqa: E402,F401
import cards_britain  # noqa: E402,F401
import cards_japan  # noqa: E402,F401
import cards_finland  # noqa: E402,F401
import cards_france  # noqa: E402,F401
