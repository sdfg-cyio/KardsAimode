# 打法：德国 + 美国 加费（指挥部 阿登）
# 思路：前期战争机器/债券加槽、嗡嗡炸弹/Ar 196/恩尼格玛过牌、低费单位守线；中期研发、狼群/Hs 129 解场；
# 后期一触即溃 + 鼠式清场打脸、利奥波德全场回手、俾斯麦斩杀
# 卡牌效果在 cards_germany.py；这里只放“这套卡组看重什么”的数值
NAME = 'germany_ramp'
# 2026-10-15 用户改版：-三号坦克 -1 老兔子 -1 战争机器，+第 22 步兵团 +前线与家乡 +1 恩尼格玛（缓解缺牌）
DECK_CODE = '%%15|2Q2S313b3N3Q4F4zbJeYoTqftctgwCwL;2Z3j3Xbqv7vhzd;bKbPq8;'
HQ = 'card_location_ardennes_waw'   # 用户指定（2026-10-15）；总部都没有特效
TITLE = '德美跳'
COMMANDER = '逸见艾丽卡'
AVATAR = 'avatar_blitzmadel'            # 闪电女孩
MAIN, ALLY = 'Germany', 'usa'

# 加费卡组：前期自保，后期靠大牌收尾
W = {'my_hq': 1.1, 'en_hq': 0.9, 'threat': 1.2, 'front': 1.2, 'board': 1.0}
SLOT_R, SLOT_V = 12, 1.5
HOLD_FRAC = 0.5
DANGER_DMG = 7
ARADO_DRAW_BONUS = 1.5    # 阿拉多触发抽牌时额外加分（见 HOLD 里阿拉多的说明）

E_, U_ = 'card_event_', 'card_unit_'


def _r(ctx, n=5):
    return min(ctx.get('R', 6), n)


def _e(side):
    return 'left' if side == 'right' else 'right'


def danger(ctx):
    """敌方下回合能打到总部 >= 7 点，或足以斩杀"""
    return ctx.get('T', 0) >= DANGER_DMG or ctx.get('T', 0) >= ctx.get('H', 20)


def _en_units(sim, side):
    return sim.units(_e(side))


def _en_value(sim, side):
    """敌方场面总价值（攻防和）"""
    return sum((u.atk or 0) + max(0, u.df or 0) for u in _en_units(sim, side))


def _bismarck_now(sim, side, ctx):
    """俾斯麦现在打出去的价值：对方总部掉 8 点（按 planner 的总部估值曲线）"""
    import planner
    e = sim.side[_e(side)]['hq'].df
    return W['en_hq'] * (planner.hq_value(e) - planner.hq_value(e - 8))


def _big_in_hand(sim, side):
    return sum(1 for h in sim.side[side]['hand'] if (h.cost or 0) >= 9 and h.name != '?')


def _chain(sim, c, ctx):
    import research_v
    return research_v.chain_hold(sim, c, ctx, hold, allow_option)


HOLD = {
    E_ + 'the_war_machine': 0.0,          # 加槽价值由 slot_value 算
    E_ + 'war_bonds': 1.5,
    E_ + 'for_freedom': 0.8,
    E_ + 'buzz_bomb': 0.6,                # 打总部 = 过一张牌，有闲费就打
    E_ + 'from_the_deep': 1.5,
    # 老兔子/闪电战：加攻只到回合结束，不攻击就没收益；保留价值调低，
    # 有像样的攻击就用（实测原来 3/4 分时两张一直捏在手里，几回合剩 6~9 点指挥点）
    E_ + 'old_hares': 1.5,
    E_ + 'blitzkrieg': 2.0,
    # 前线与家乡：越早打牌库里剩的奇数费牌越多（收益在 cards_germany 里算）
    E_ + 'front_and_homeland': 1.0,
    # 恩尼格玛：手牌差 >= 2 才值得（抽 1 张 2 分）
    E_ + 'enigma': 2.5,
    E_ + 'sky_barons': 2.5,
    E_ + 'wolfpack': 3.0,
    E_ + 'the_alliance': lambda sim, c, ctx: 2.0 + 0.8 * sum(
        1 for u in sim.units(c.side) if u.faction != 'USA'),
    # 俾斯麦：8 点打总部早打晚打一样，捏着只会浪费指挥点（实测一局捏了 6 回合、每回合剩 7~14 点）。
    # 保留价值 = 现在打出去的价值 × 0.85：有闲费就打，费用紧时让给更要紧的牌
    E_ + 'bismarck': lambda sim, c, ctx: 0.85 * _bismarck_now(sim, c.side, ctx),
    E_ + 'capitulation': 6.0,
    # 研发链：每层的留牌价值 = 往下最终能换到的产物价值 - 还要花的研发费用（research_v.chain_hold）。
    # 原来扩展研发危险时 -4，等于危险时最想推研发（和本意相反）；各层固定值也让推进没有收益
    E_ + 'reich_research': lambda sim, c, ctx: _chain(sim, c, ctx),
    E_ + 'expanded_reich_research': lambda sim, c, ctx: _chain(sim, c, ctx),
    E_ + 'advanced_reich_research': lambda sim, c, ctx: _chain(sim, c, ctx),
    # 研发产物：按场面估
    E_ + 'v1_flying_bomb': lambda sim, c, ctx: 1.0 + 0.5 * max(
        [0.5 * ((u.atk or 0) + (u.df or 0)) for u in _en_units(sim, c.side) if (u.cost or 0) <= 3] or [0]),
    E_ + 'synthetic_oil': lambda sim, c, ctx: 1.0 + 2.0 * min(2, _big_in_hand(sim, c.side)),
    E_ + 'type_xxi_boat': lambda sim, c, ctx: 2.5 + 0.5 * max(
        [0.5 * ((u.atk or 0) + (u.df or 0)) for u in _en_units(sim, c.side)] or [0]),
    E_ + 'uranium_club': lambda sim, c, ctx: 3.0 + 0.8 * len(_en_units(sim, c.side)),   # 空场也保底：后期清场王牌
    # 阿拉多：1/2 身板不值钱，价值在抽牌。保留价值压高（3.5 盖过身板 + 蓝色军团联动），
    # 满足"友方单位数不大于敌方"时再加 ARADO_DRAW_BONUS，抽牌那一下才值得放（实测曾 4 对 0 空放）
    U_ + 'arado_ar_196': 3.5,
    U_ + 'maus': 6.0,
    U_ + 'railway_gun_leopold': 5.0,
    U_ + 'tiger_i_e': 3.5,
}


def allow(sim, c, ctx):
    """打法层面禁止的出牌"""
    n = c.name
    if n == E_ + 'capitulation':
        return len(_en_units(sim, c.side)) >= 2      # 对方场上至少 2 个单位才投
    if n == U_ + 'railway_gun_leopold':
        return len(_en_units(sim, c.side)) >= 2
    if n == E_ + 'enigma':
        return len(sim.side[_e(c.side)]['hand']) - (len(sim.side[c.side]['hand']) - 1) >= 2
    if n == E_ + 'from_the_deep':
        return sim.side[_e(c.side)]['max_kredits'] >= 5   # 对方前期都是小单位，不值得埋
    return True


FREEDOM_MAX_OP = 2       # 为了自由不给行动费 3 以上的单位（用户：鼠式这种行动费极高的，+1+1 没意义）


def allow_option(sim, c, t, k, ctx):
    """研发：第一层危险且 V-1 有目标时选 V-1，否则往下研发；第二层手里有大牌才可能选合成燃料，
    其余按产物价值选。为了自由：不给行动费高的单位"""
    n = c.name
    if n == E_ + 'reich_research':
        v1_target = any((u.cost or 0) <= 3 for u in _en_units(sim, c.side))
        return k == (0 if danger(ctx) and v1_target else 1)
    if n == E_ + 'expanded_reich_research':
        return k == 1 or _big_in_hand(sim, c.side) >= 1
    if n == E_ + 'for_freedom':
        u = sim.find(t)
        return u is None or (u.op or 0) <= FREEDOM_MAX_OP
    return True


def hold(sim, c, ctx):
    n = c.name
    h = HOLD.get(n)
    if h is not None:
        return h(sim, c, ctx) if callable(h) else h
    if c.type == 'order':
        return 0.3 * (c.cost or 0)
    v = 0.5 * (c.atk or 0) + 0.5 * (c.df or 0) + (1.0 if c.guard else 0) + (c.armor or 0) + persist(sim, c, ctx)
    return HOLD_FRAC * v


def persist(sim, u, ctx):
    """我方单位在场上的持续价值（攻防之外）"""
    n = u.name
    mine = [x for x in sim.units(u.side) if x is not u]
    if n == U_ + '158_nachschub':
        return 0.8 * _r(ctx, 4)          # 每回合杀一个敌方单位就 +2 指挥点
    if n == U_ + 'blue_legion':
        return 0.6 * _r(ctx, 4) * max(1, min(3, len(mine)))   # 每次行动给行动单位 +1+1/点
    if n == U_ + '96_infantry_regiment':
        return -2.5                      # 下次部署单位它就没了，攻防不是持续价值
    if n == U_ + '169_grenadiers':
        return 1.5                       # 对方每下一张指令随机弃一张
    if n == U_ + '22_infantry':
        # 回合结束我方控制前线就抽 1 张：本回合结束能抽算 0.8 张，之后每回合按一半机会算
        front = bool(sim.side[u.side]['front'])
        return (0.8 * 2.0 if front else 0) + 0.5 * min(3, _r(ctx, 3))
    if n == U_ + 'seahawk':
        en = [x for x in sim.units(_e(u.side)) if x.atk]
        bombers = any(x.type == 'bomber' for x in en)
        return 0.2 * _r(ctx) * max(1, len(en)) + (2.0 if bombers else 0)
    if n == U_ + 'tiger_i_e':
        return 1.0                       # 不能被敌方指令指向
    return 0.0


KEEP = {E_ + 'the_war_machine', U_ + '158_nachschub', U_ + 'arado_ar_196', E_ + 'buzz_bomb',
        E_ + 'for_freedom', U_ + '96_infantry_regiment', E_ + 'reich_research', U_ + '22_infantry'}


def keep(name, cost):
    """起手调度：留加费、过牌和低费单位，大牌换掉。
    前线与家乡不在 KEEP 里：起手拿到就换回牌库，让它第四回合额外抽出来"""
    return name in KEEP


# 难度加成（native/buffs.py）：OPENING = 老兵及以上的起手候选池（随机挑 4~5 张）；CORE = 地狱档手牌少时打印的核心牌
OPENING = [E_ + 'the_war_machine', E_ + 'buzz_bomb', U_ + '158_nachschub', U_ + 'arado_ar_196', E_ + 'for_freedom',
           U_ + '22_infantry', U_ + '96_infantry_regiment', E_ + 'reich_research']
CORE = [E_ + 'capitulation', U_ + 'maus', E_ + 'bismarck', U_ + 'railway_gun_leopold', U_ + 'henschel_he_129']
