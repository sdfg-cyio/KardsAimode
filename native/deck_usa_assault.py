# 打法：美国 + 法国 “行动费 3+” 进攻（指挥部 阿拉库尔）
# 思路（2026-10-17 与用户讨论）：要下单位、积极威胁对方。行动费 >= 3 的步兵串联：
# 第 13 工兵营加槽、骇人步兵团抽牌、第 2 密歇根回 2 费、B-24D 便宜 3 费、散兵团给总部加防；
# 永先者团让新上场的步兵当回合免费行动（照样触发密歇根）；第 116 步兵团给游骑兵/骇人这类同名卡全体 +5+5。
# 解场：俄亥俄第 5、燃烧弹、密苏里、纵深防御、出动、战略轰炸；保命：593 通信连、解放、反袭。
# 卡牌效果在 cards_usa.py / cards_france.py；这里只放这套卡组的用法和估值
import sim_rules as R

NAME = 'usa_assault'
DECK_CODE = '%%56|bEbmDBdkEbfGoaocpCtYv6vc;2lgJgQofq6r6rT;DOlgo7;bK'
HQ = 'card_location_arracourt'        # 用户指定（2026-10-18 由瑟堡改为阿拉库尔，两者都无特效）
TITLE = '美法高油'
COMMANDER = '凯伊'
AVATAR = 'avatar_stars_and_stripes'
MAIN, ALLY = 'USA', 'france'

# 进攻：对方总部和前线看得重
W = {'my_hq': 1.0, 'en_hq': 1.15, 'threat': 1.1, 'front': 2.0, 'board': 1.0}
SLOT_R, SLOT_V = 9, 1.0
HOLD_FRAC = 0.5
DANGER_DMG = 7
FRONT_PRESSURE = 0.35
HIGH_OP = 3
ENEMY_DRAW_V = 2.0        # 对方抽一张 = 我方抽一张的价值（假战双方都抽）

E_, U_ = 'card_event_', 'card_unit_'
ENGINES = {U_ + '13th_engineers_battalion', U_ + 'les_terribles', U_ + '2nd_michigan',
           U_ + '8e_tirailleurs_marocains', U_ + '1st_infantry_regiment_us'}


def _e(side):
    return 'left' if side == 'right' else 'right'


def _r(ctx, n=4):
    return min(ctx.get('R', 6), n)


def danger(ctx):
    return ctx.get('T', 0) >= DANGER_DMG or ctx.get('T', 0) >= ctx.get('H', 20)


def _en(sim, side):
    return sim.units(_e(side))


def _rv():
    import research_v
    return research_v


def _chain(sim, c, ctx):
    return _rv().chain_hold(sim, c, ctx, hold, allow_option)


_DECK = None


def deck_copies(sim, name):
    """牌库里还剩几张同名牌（第 116 步兵团）：卡组里的张数 - 场上/手里看得到的"""
    global _DECK
    if _DECK is None:
        import ai_decks
        cards, _ = ai_decks.parse_deck_code(DECK_CODE)
        _DECK = {n: cards.count(n) for n in set(cards)}
    me = sim.me
    seen = sum(1 for c in sim.side[me]['hand'] + sim.units(me) if c.name == name)
    return max(0, _DECK.get(name, 0) - seen)


def _high_on_board(sim, side):
    return sum(1 for u in sim.units(side) if (u.op or 0) >= HIGH_OP)


HOLD = {
    E_ + 'the_war_machine': 0.0,          # 加槽价值由 slot_value 算
    E_ + 'production_order': 2.5,          # 给一张 B-24（场上有行动费 3+ 的单位时 B-24D 只要 4 费）
    E_ + 'counter_strike': 2.0,
    E_ + 'us_military_research': lambda sim, c, ctx: _chain(sim, c, ctx),
    E_ + 'expanded_us_research': lambda sim, c, ctx: _chain(sim, c, ctx),
    # 高级研发走研发链（青霉素 / 两张曼哈顿取较大者）；青霉素、曼哈顿按局面估（research_v）
    E_ + 'advanced_us_research': lambda sim, c, ctx: _chain(sim, c, ctx),
    E_ + 'depth_charges': 3.0,
    E_ + 'pressurized_cabin': lambda sim, c, ctx: 2.5 + (1.5 if _en(sim, c.side) else 0),
    E_ + 'penicillin': lambda sim, c, ctx: _rv().penicillin_v(sim, c.side, ctx),
    E_ + 'manhattan_project': lambda sim, c, ctx: _rv().manhattan_v(sim, c.side, ctx),
    E_ + 'uss_missouri': 2.5,
    E_ + 'firebomb': 2.0,
    E_ + 'defend_in_depth': lambda sim, c, ctx: 0.8 + 0.25 * len(sim.side[_e(c.side)]['hand']),
    E_ + 'sally': 1.0,
    E_ + 'liberation': 2.5,
    E_ + 'phoney_war': 2.0,
    E_ + 'victory_march': 3.0,
    E_ + 'strategic_bombing': 3.0,
}


def hold(sim, c, ctx):
    n = c.name
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


def persist(sim, u, ctx):
    return _front_pressure(sim, u) + _persist(sim, u, ctx)


def _persist(sim, u, ctx):
    n = u.name
    hi = _high_on_board(sim, u.side)
    if n == U_ + '13th_engineers_battalion':
        return 1.0 * min(2, _r(ctx, 3))            # 之后每下一个行动费 3+ 单位 +1 槽
    if n == U_ + 'les_terribles':
        return 0.8 * min(2, _r(ctx, 3))            # 之后每下一个行动费 3+ 单位抽 1
    if n == U_ + '2nd_michigan':
        return 0.8 * _r(ctx, 3) * max(1, min(3, hi))   # 每次行动费 3+ 的单位行动回 2 费
    if n == U_ + '8e_tirailleurs_marocains':
        return 0.6 * _r(ctx, 3)                     # 之后部署单位总部加防
    if n == U_ + '1st_infantry_regiment_us':
        return 0.6 * _r(ctx, 3)                     # 之后上场的步兵免费行动
    if n == U_ + 'us_signal_corps':
        en = [x for x in _en(sim, u.side) if x.atk]
        return 0.3 * _r(ctx) * max(1, len(en))
    if n == U_ + 'tigercat':
        room = len(sim.side[u.side]['support']) < 4
        return 2.5 * min(ctx.get('R', 6), 3) * (1.0 if room else 0.2)   # 每回合送一架 SBD 无畏
    if n == U_ + '18e_regiment':
        return 1.0 if sim.deploys <= 1 else 0.0    # 回合结束若只部署了它，行动费变 0
    return 0.0


def allow(sim, c, ctx):
    n = c.name
    if n == E_ + 'depth_charges':
        return danger(ctx)
    if n == E_ + 'counter_strike':
        return any(u.atk and not u.pinned for u in _en(sim, c.side))   # 对面有能打总部的单位才埋
    if n == E_ + 'phoney_war':
        my = len(sim.side[c.side]['hand']) - 1
        return my <= 4 and 8 - my >= 8 - len(sim.side[_e(c.side)]['hand']) + 2   # 我方多抽 2 张以上
    if n == E_ + 'victory_march':
        return _high_on_board(sim, c.side) >= 2
    return True


def allow_option(sim, c, t, k, ctx):
    n = c.name
    if n == E_ + 'us_military_research':
        return k == (0 if danger(ctx) else 1)
    if n == E_ + 'expanded_us_research':
        # 增压舱只在有压力或 8 槽前选；后期没压力开高级研发（曼哈顿/青霉素）
        return k == 1 or danger(ctx) or sim.side[c.side]['max_kredits'] < 8
    if n == E_ + 'production_order':
        # 场上或手里有行动费 3+ 的单位就选 B-24D（4 费 6/5 闪击），否则 B-24J（抑制一片）
        hi = _high_on_board(sim, c.side) or any(
            h.type in R.UNIT_TYPES and (h.op or 0) >= HIGH_OP for h in sim.side[c.side]['hand'] if h is not c)
        return k == (0 if hi else 1)
    if n == E_ + 'sally':
        u = sim.find(t)
        return u is not None and u.id not in sim.silenced and not (u.type == 'tank' and u.pinned)
    return True


def allow_attack(sim, u, t):
    return u.name != U_ + 'us_signal_corps'


def allow_move(sim, u):
    return u.name not in (U_ + 'us_signal_corps', U_ + '13th_engineers_battalion')


KEEP = {E_ + 'the_war_machine', U_ + '13th_engineers_battalion', U_ + 'les_terribles', U_ + 'us_signal_corps',
        U_ + '5e_cuirassier', U_ + '1st_infantry_regiment_us', U_ + 'fifth_ohio', E_ + 'production_order'}


def keep(name, cost):
    """起手调度：留加槽、引擎和 2~3 费单位"""
    return name in KEEP


# 难度加成（native/buffs.py）：OPENING = 老兵及以上的起手候选池（随机挑 4~5 张）；CORE = 地狱档手牌少时打印的核心牌
OPENING = [E_ + 'the_war_machine', U_ + '13th_engineers_battalion', U_ + 'les_terribles', U_ + 'us_signal_corps',
           U_ + '5e_cuirassier', U_ + '1st_infantry_regiment_us', U_ + 'fifth_ohio', E_ + 'production_order']
CORE = [U_ + '116th_infantry_regiment', U_ + '2nd_michigan', U_ + 'les_terribles', U_ + '5th_rangers',
        U_ + '1st_infantry_regiment_us']
