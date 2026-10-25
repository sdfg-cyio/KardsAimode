# 打法：德国 + 芬兰 “车车”（指挥部 维莱博卡日）
# 思路（2026-10-16 与用户讨论）：从开局就抢前线。1 费小坦克/步兵铺场，一回合里多次行动叠增益
# （第 30 步兵团减行动费、第 3 装甲掷弹兵团/蓝色军团 +1+1、豹式防磁装甲型越动越大），
# 古德里安/装甲楔形阵/闪电战加攻（Sd Kfz 10 吃每次加攻再 +1），前线与家乡第 4 回合打出后奇数费牌全 -1 费，
# 恩尼格玛/长久围困/Ar 196/一号坦克/抑制补牌。
# 卡牌效果在 cards_germany.py / cards_finland.py；这里只放这套卡组的用法和估值
import sim_rules as R

NAME = 'germany_panzer'
DECK_CODE = '%%19|2S303NE1wC;2Z3XrKzd;3f4vE4nlxoza;uxxp'
HQ = 'card_location_villers_bocage'   # 用户指定（2026-10-16）
TITLE = '德芬车'
COMMANDER = '艾拉·伊尔玛塔'
AVATAR = 'avatar_blitzkrieg'
MAIN, ALLY = 'Germany', 'finland'

# 快攻：前线和对方总部看得重，自己总部看得轻一些
W = {'my_hq': 0.9, 'en_hq': 1.2, 'threat': 1.0, 'front': 2.5, 'board': 1.0}
SLOT_R, SLOT_V = 6, 0.8
HOLD_FRAC = 0.5
DANGER_DMG = 7
FRONT_PRESSURE = 0.4      # 前线地面单位下回合打总部的威胁：每点攻击（不超过对面总部血量）值多少分
OP_SAVE_V = 0.4           # 永久减掉的 1 点行动费（洛塔组织、第 30 步兵团）每回合值多少分
ARADO_DRAW_BONUS = 1.5    # 阿拉多触发抽牌时额外加分（平时捏着，满足“友方单位不多于敌方”才放）
# 前线与家乡（cards_germany）：这套 31 张奇数费德国牌（1 费 24 张 + 3 费 7 张），过牌多，1 费变 0 费
FH_ODD, FH_DRAWS, FH_V = 30, 22, 1.0
SIEGE_AVG = 1.5           # 长久围困（cards_finland）：这套平均每张牌花费（前线与家乡之后大多 0~2 费）

E_, U_ = 'card_event_', 'card_unit_'
SUPPRESS = E_ + 'suppression_fire'


def _e(side):
    return 'left' if side == 'right' else 'right'


def _r(ctx, n=4):
    return min(ctx.get('R', 6), n)


def danger(ctx):
    return ctx.get('T', 0) >= DANGER_DMG or ctx.get('T', 0) >= ctx.get('H', 20)


def _german(sim, side, u=None):
    return [x for x in sim.units(side) if x.faction == 'Germany' and x is not u]


def _tanks(sim, side):
    return [x for x in sim.units(side) if x.type == 'tank' and x.faction == 'Germany']


def _hand_diff(sim, side):
    """敌方手牌数 - 我方手牌数（不含正要打出的这张）"""
    return len(sim.side[_e(side)]['hand']) - (len(sim.side[side]['hand']) - 1)


HOLD = {
    # 恩尼格玛：手牌差 >= 2 才打（allow），差得越多越值，留着等差距拉大
    E_ + 'enigma': 3.0,
    # 长久围困：抽牌价值在 cards_finland 里按两回合打得出几张折算；留牌价值低，有费有空就打
    E_ + 'prolonged_siege': 2.0,
    E_ + 'front_and_homeland': 1.0,       # 第 4 回合就打（收益在 cards_germany 里算，远大于这个）
    SUPPRESS: 1.2,
    E_ + 'tank_wedge': 1.0,               # 三个单位各 +1+1 = 3 分以上才打
    E_ + 'blitzkrieg': 2.5,               # 只到回合结束：要能打出伤害才值
    E_ + 'lotta_svard': 2.0,
    U_ + 'arado_ar_196': 3.0,
}


def _heinz_hold(sim, c, ctx):
    """古德里安：场上德国坦克越少越该留着（手里还有能下的坦克就等）"""
    my = sim.side[c.side]
    on = len(_tanks(sim, c.side))
    coming = sum(1 for h in my['hand'] if h.type == 'tank' and h.cost is not None and h.cost <= my['kredits'])
    return 1.5 + 0.8 * min(2, coming) if on < 3 else 1.0


def hold(sim, c, ctx):
    n = c.name
    if n == E_ + 'fast_heinz':
        return _heinz_hold(sim, c, ctx)
    h = HOLD.get(n)
    if h is not None:
        return h(sim, c, ctx) if callable(h) else h
    if c.type == 'order':
        return 0.3 * (c.cost or 0)
    v = 0.5 * (c.atk or 0) + 0.5 * (c.df or 0) + (1.0 if c.guard else 0) + (c.armor or 0) + _persist(sim, c, ctx)
    return HOLD_FRAC * v


def _front_pressure(sim, u):
    if not (u.loc or '').startswith('front') or not u.atk or u.type not in ('infantry', 'tank', 'artillery'):
        return 0.0
    atk = u.atk - sim.temp.get(u.id, 0)
    return FRONT_PRESSURE * min(max(0, atk), max(0, sim.side[_e(u.side)]['hq'].df))


def _op_saved(sim, u):
    """比卡面少掉的永久行动费（本回合闪电战的临时 -1 不算）"""
    import card_db
    base = (card_db.get(u.name) or {}).get('op')
    if base is None or u.op is None:
        return 0
    return max(0, base - (u.op - sim.temp_op.get(u.id, 0)))


def persist(sim, u, ctx):
    return _front_pressure(sim, u) + _persist(sim, u, ctx) + OP_SAVE_V * _r(ctx, 3) * _op_saved(sim, u)


def _persist(sim, u, ctx):
    n = u.name
    if n == U_ + '158_nachschub':
        return 0.8 * _r(ctx, 4)          # 每回合杀一个敌方单位就 +2 指挥点
    if n == U_ + 'blue_legion':
        return 0.6 * _r(ctx, 4) * max(1, min(3, len(sim.units(u.side)) - 1))
    if n == U_ + '3_panzergrenadier':
        # 每有一个“其他”德国单位行动 +1+1（2026-10 改版不含自己）：按每回合约 min(3, 其他德国单位数) 次、容易被集火打个折
        others = sum(1 for x in _german(sim, u.side) if x is not u)
        return 0.4 * _r(ctx, 3) * min(3, others)
    if n == U_ + 'panther_a_zimm':
        k = sim.op_count.get(u.id, 0) if u.id is not None else 0
        return 0.5 * (k + 1) * min(2, _r(ctx, 2))   # 下次行动攻防各 +(k+1)，行动费 0 每回合都能动
    return 0.0


def allow(sim, c, ctx):
    n = c.name
    if n == E_ + 'enigma':
        return _hand_diff(sim, c.side) >= 2
    if n == E_ + 'fast_heinz':
        return len(_tanks(sim, c.side)) >= 2
    if n == E_ + 'prolonged_siege':
        return R.hand_room(sim, c.side) >= 4 + 1       # 抽 4 张别爆牌（打出这张腾出 1 格）
    return True


def allow_option(sim, c, t, k, ctx):
    if c.name == SUPPRESS:
        u = sim.find(t)
        return u is not None and u.id not in sim.silenced   # 已经抑制过的不再抑制
    return True


def allow_attack(sim, u, t):
    return u.name != U_ + '158_nachschub'          # 0 攻，打什么都白打，留在支援线加费


def allow_move(sim, u):
    return u.name != U_ + '158_nachschub'


KEEP = {U_ + '30_infantry_regiment', U_ + 'panzer_ii_a', U_ + 'panzer_i_a', U_ + 'sd_kfz_10_38',
        U_ + '3_panzergrenadier', U_ + 'panther_a_zimm', U_ + 'arado_ar_196', U_ + '158_nachschub',
        U_ + 'blue_legion', E_ + 'tank_wedge'}


def keep(name, cost):
    """起手调度：留 1~3 费单位和装甲楔形阵；前线与家乡换回牌库，让它第四回合额外抽出来"""
    return name in KEEP


# 难度加成（native/buffs.py）：OPENING = 老兵及以上的起手候选池（随机挑 4~5 张）；CORE = 地狱档手牌少时打印的核心牌
# 前线与家乡不进起手池（第四回合额外抽出来才划算）
OPENING = [U_ + '30_infantry_regiment', U_ + 'panzer_ii_a', U_ + 'panzer_i_a', U_ + 'sd_kfz_10_38', E_ + 'tank_wedge',
           U_ + 'panther_a_zimm', U_ + 'blue_legion', U_ + '3_panzergrenadier', U_ + 'arado_ar_196']
CORE = [U_ + 'panther_a_zimm', U_ + 'blue_legion', U_ + '3_panzergrenadier', E_ + 'tank_wedge', U_ + '30_infantry_regiment']
