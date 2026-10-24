# 打法：苏联 + 波兰 转换（指挥部 莫斯科，2026-10-22 用户卡组）
# 思路：前期 0~2 费闪击步兵、海军步兵铺场；达努塔每回合送 4TP、诺夫哥罗德把每次转换变成一个摩托化步兵；
# 喀尔巴阡把要没的 4TP/小兵转成钢铁师（6/6 守护，回合开始抽牌）；铁锤/气动雪橇解场；
# 后期 T-34、909 团（步兵闪击）、修道院行动/胜利旗帜收场
NAME = 'soviet_convert'
DECK_CODE = '%%48|8CfrjWppqTrjt3tatmu4vewqwyyXz5zi;8Ns0t5tyww;88E5zC;u5'
HQ = 'card_location_moscow'           # 用户指定（2026-10-22）
TITLE = '苏波转换'
COMMANDER = '艾莉莎·米哈伊罗夫纳'
AVATAR = 'avatar_iron_comrade'
MAIN, ALLY = 'Soviet', 'poland'

# 中速：场面和前线优先，自保略重
W = {'my_hq': 1.1, 'en_hq': 0.9, 'threat': 1.2, 'front': 2.0, 'board': 1.0}
HOLD_FRAC = 0.5
DANGER_DMG = 7
LIVE_SURVEIL = False                     # 监视的动作格式（手牌 + 单位两个目标）还没抓包确认：先不打

E_, U_ = 'card_event_', 'card_unit_'
TP4, IRON, NOVGOROD = U_ + '4tp', U_ + 'iron_division', U_ + '312th_novgorod'
# 4TP 回合结束被消灭：本身不算持续价值（persist 里按“能转成钢铁师”另算）
EPHEMERAL = {TP4}
CONVERTERS = {U_ + '3rd_carpathian', U_ + '15th_wolves_regiment', U_ + 'kv_85', E_ + 'victory_banners', E_ + 'surveil'}


def _r(ctx, n=5):
    return min(ctx.get('R', 6), n)


def _e(side):
    return 'left' if side == 'right' else 'right'


def danger(ctx):
    return ctx.get('T', 0) >= DANGER_DMG or ctx.get('T', 0) >= ctx.get('H', 20)


def _en(sim, side):
    return sim.units(_e(side))


def _hand(sim, side):
    return [h for h in sim.side[side]['hand'] if h.name != '?']


def iron_draws_left(sim, u):
    """钢铁师还能在回合开始抽几次：活完整两回合（含出现那一轮），所以刚出现的还剩 2 次（用户确认）。
    驱动在 memo['seen_turn'] 记每个单位第一次出现时是 AI 的第几回合（转换出来的从零算）"""
    seen = (sim.memo.get('seen_turn') or {}).get(u.id)
    now = sim.memo.get('ai_turn', 0)
    age = 0 if seen is None or (isinstance(u.id, int) and u.id < 0) else max(0, now - seen)
    return max(0, 2 - age)


def _small_ground(sim, side):
    return sum(1 for u in _en(sim, side) if u.type in ('infantry', 'tank', 'artillery') and (u.df or 0) <= 2)


def _chain(sim, c, ctx):
    import research_v
    return research_v.chain_hold(sim, c, ctx, hold, allow_option)


def _hammer(sim, c, ctx):
    """铁锤（6 伤单体）：按对面最值得打的陆军估"""
    best = max(((u.atk or 0) + 0.5 * (u.df or 0) for u in _en(sim, c.side)
                if u.type in ('infantry', 'tank', 'artillery') and (u.df or 0) <= 6), default=0)
    return min(5.0, 2.0 + 0.3 * best)


HOLD = {
    E_ + 'monastyr': 5.0,
    E_ + 'victory_banners': 5.0,
    E_ + 'the_hammer': _hammer,
    E_ + 'burning_sky': lambda sim, c, ctx: 2.0 if any(u.type in ('fighter', 'bomber') for u in _en(sim, c.side)) else 1.2,
    E_ + 'arctic_convoy': 2.5,
    E_ + 'by_the_sword': lambda sim, c, ctx: 1.0 + 0.6 * min(5, len(_en(sim, c.side))),
    E_ + 'anders_army': lambda sim, c, ctx: 1.2,
    E_ + 'blast': lambda sim, c, ctx: 0.3 + (0.7 if any((u.df or 0) == 1 for u in _en(sim, c.side)) else 0),
    E_ + 'surveil': 1.0,
    # 研发链：同苏意控（每层 = 往下能换到的产物价值 - 还要花的费用）
    E_ + 'soviet_military_research': _chain,
    E_ + 'expanded_soviet_research': _chain,
    E_ + 'advanced_soviet_research': _chain,
    E_ + 'aerosani': lambda sim, c, ctx: 1.0 + 0.5 * min(3, _small_ground(sim, c.side)),
    E_ + 'standard_ammo': lambda sim, c, ctx: 0.6 * (sum(1 for h in _hand(sim, c.side) if h.type not in ('order', 'location'))
                                                    + 0.4 * ctx.get('deck_units', 6)),
    E_ + 'sloped_armor': 3.0,
    E_ + 'stalin_organ': lambda sim, c, ctx: 0.75 * (1.5 + 0.6 * min(5, len(_en(sim, c.side)))),
}


def allow(sim, c, ctx):
    n = c.name
    H = sim.side[c.side]['hq'].df
    if n == E_ + 'surveil':
        return LIVE_SURVEIL
    if n == E_ + 'anders_army':
        return H > 8
    if n == E_ + 'by_the_sword':
        return len(_en(sim, c.side)) >= 3
    if n == U_ + 'kv_85':
        # 部署效果把一张手牌变成上一个阵亡的友方单位：没有好单位阵亡时只是 5/5 白身子 + 下回合少 2 费，留着
        last = (getattr(sim, 'last_dead_any', {}) or {}).get(c.side)
        return last is not None and ((last.cost or 0) >= 4 or (last.atk or 0) + (last.df or 0) >= 9)
    return True


def allow_option(sim, c, t, k, ctx):
    """研发第一层：有压力选气动雪橇，没压力往下研发（同苏意控）；740 团开发：默认铁锤，
    手牌少时北极护航队，对面有飞机时燃烧的天空"""
    n = c.name
    if n == E_ + 'soviet_military_research':
        return k == (0 if danger(ctx) else 1)
    if n == E_ + 'expanded_soviet_research':
        units = sum(1 for h in _hand(sim, c.side) if h.type not in ('order', 'location'))
        return k == 1 or (sim.side[c.side]['max_kredits'] < 7 and units >= 3)
    return True


def hold(sim, c, ctx):
    n = c.name
    if n == U_ + '4th_guards_rifles':
        base = HOLD_FRAC * (0.5 * (c.atk or 0) + 0.5 * (c.df or 0) + 1.0)
        return base + (1.5 if (c.cost or 0) > 6 else 0)
    h = HOLD.get(n)
    if h is not None:
        return h(sim, c, ctx) if callable(h) else h
    if c.type == 'order':
        return 0.3 * (c.cost or 0)
    v = 0.5 * (c.atk or 0) + 0.5 * (c.df or 0) + (1.0 if c.guard else 0) + (c.armor or 0) + persist(sim, c, ctx)
    if n in CONVERTERS and sim.count(c.side, NOVGOROD):
        v += 1.0                         # 诺夫哥罗德在场：转换牌多送一个摩托化步兵
    return HOLD_FRAC * v


def persist(sim, u, ctx):
    """我方单位在场上的持续价值（攻防之外）"""
    n = u.name
    mine = [x for x in sim.units(u.side) if x is not u]
    hand = _hand(sim, u.side)
    if n == U_ + 'danuta':
        # 每回合一个 3/3 闪击 4TP；手里有喀尔巴阡/狼团时它还是转换的好材料
        fodder = sum(1 for h in hand if h.name in (U_ + '3rd_carpathian', U_ + '15th_wolves_regiment'))
        return 1.5 * _r(ctx, 4) + 1.0 * min(2, fodder)
    if n == NOVGOROD:
        conv = sum(1 for h in hand if h.name in CONVERTERS)
        return 1.0 + 1.5 * min(3, conv)  # 每次转换送一个 3/3 闪击伏击
    if n == U_ + '909th_roslavl':
        inf = sum(1 for x in mine if x.type == 'infantry') + sum(1 for h in hand if h.type == 'infantry')
        return 0.5 + 0.3 * min(6, inf)   # 步兵闪击；修道院行动时步兵多一个词条
    if n == U_ + '11th_signal_battalion':
        tp = 1.0 if sim.count(u.side, U_ + 'danuta') else 0.0   # 4TP 每回合结束都会死：总部 +2
        return 1.0 + 0.8 * min(4, len(mine)) + 1.5 * tp * _r(ctx, 4) / 2
    if n == IRON:
        left = iron_draws_left(sim, u)
        return 1.6 * left - (1.5 if left <= 1 else 0)   # 回合开始抽牌；快没了的身子不值钱
    if n == TP4:
        return 0.0
    if n == U_ + 'ilyushin_10':
        return 1.5
    if n == U_ + '28th_infantry_regiment':
        return 0.8                       # 对战存活 +1+1
    if n == U_ + '97th_rifles':
        return 1.5                       # 亡计：洗入 414 团 + 抽 1
    if n == U_ + '289th_gatchina':
        return 1.0                       # 亡计：抽 1 + 总部回血
    if n == U_ + '414th_rifles':
        return 2.0 if sim.side[u.side]['hq'].df > 6 else 0.5   # 亡计抽 3 但自伤 3
    return 0.0


KEEP = {U_ + 'danuta', NOVGOROD, U_ + '28th_infantry_regiment', U_ + '554th_rifles', U_ + '3rd_morskoi_pekhoty',
        U_ + '97th_rifles', U_ + '11th_signal_battalion', U_ + '289th_gatchina'}


def keep(name, cost):
    """起手调度：留低费铺场、达努塔、诺夫哥罗德；大单位和指令换掉"""
    return name in KEEP


# 难度加成（native/buffs.py）：OPENING = 老兵及以上的起手候选池（随机挑 4~5 张）；CORE = 地狱档手牌少时打印的核心牌
OPENING = [U_ + 'danuta', NOVGOROD, U_ + '3rd_carpathian', U_ + '28th_infantry_regiment', U_ + '3rd_morskoi_pekhoty',
           U_ + '554th_rifles', U_ + '289th_gatchina', U_ + '44th_silesia']
CORE = [U_ + '3rd_carpathian', NOVGOROD, U_ + 'danuta', U_ + '15th_wolves_regiment', U_ + '909th_roslavl']
