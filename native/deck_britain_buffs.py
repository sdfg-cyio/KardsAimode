# 打法：英国 + 美国 米色团快攻（指挥部 阿拉姆哈勒法，2026-10-24 用户卡组）
# 思路（用户）：核心是米色团开局快攻——1 费步兵铺场抢前线，奎宁/为了自由/沙利文兄弟号/威尔士卫队往米色团身上堆
# （被指令或部署指向时额外 +1+1）；出其不意的是边防团/第 70 步兵旅这类高防单位偷偷上前线，
# 再用本土链/HMS 可畏号把攻击力变成防御力，清掉挡路的单位后打总部斩杀。
# 土地女孩/西非旅/70 旅/桑德兰补牌；区域轰炸的兰开斯特（7 攻闪击）后期补斩杀
# 卡牌效果在 cards_britain.py / cards_usa.py；这里只放这套卡组的用法和估值
NAME = 'britain_buffs'
DECK_CODE = '%%25|030i19gE;bqpWsDtVyP;pUwbyw;1TDRsUvS'
HQ = 'card_location_alam_el_halfa'    # 用户指定（2026-10-24）
TITLE = '英美米色团'
COMMANDER = '千户'                     # 用户指定（2026-10-25）
AVATAR = 'avatar_monty'                 # 头像我选的：蒙蒂（北非第 8 集团军，配阿拉姆哈勒法）
MAIN, ALLY = 'Britain', 'usa'

# 快攻：前线和对方总部看得重
W = {'my_hq': 0.9, 'en_hq': 1.2, 'threat': 1.0, 'front': 2.5, 'board': 1.0}
SLOT_R, SLOT_V = 6, 0.8
HOLD_FRAC = 0.5
DANGER_DMG = 7
FRONT_PRESSURE = 0.4      # 前线地面单位下回合打总部的威胁：每点攻击值多少分（同德芬车）
SWAP_PRESSURE = 0.25      # 前线高防单位 + 手里有本土链/可畏号：下回合攻击变防御打脸的威胁（每点防御）
SWAP_DF = 5               # 防御 >= 这个才值得用本土链/可畏号（攻击 = 防御）

E_, U_ = 'card_event_', 'card_unit_'
BUFFS = U_ + 'buffs'
CHAIN, FORMIDABLE = E_ + 'chain_home', E_ + 'hms_formidable'
LANCASTER = U_ + 'lancaster'
EPHEMERAL = {LANCASTER}   # 回合结束洗回牌库：留在场上没价值
# 只给友方的增益（卡面能给敌方，但这套没理由给；少一些搜索分支）
FRIENDLY_ONLY = {E_ + 'quinine', E_ + 'uss_sullivans', U_ + 'welsh_guards', E_ + 'for_freedom'}
SWAPS = (CHAIN, FORMIDABLE)


def _e(side):
    return 'left' if side == 'right' else 'right'


def _r(ctx, n=4):
    return min(ctx.get('R', 6), n)


def danger(ctx):
    return ctx.get('T', 0) >= DANGER_DMG or ctx.get('T', 0) >= ctx.get('H', 20)


def _en(sim, side):
    return sim.units(_e(side))


def _hand(sim, side):
    return [h for h in sim.side[side]['hand'] if h.name != '?']


def _swaps_in_hand(sim, side):
    return sum(1 for h in _hand(sim, side) if h.name in SWAPS)


def _formidable_hold(sim, c, ctx):
    """可畏号：对面单位越多越值得留着等一次大清场"""
    return 2.5 + 0.5 * min(4, len(_en(sim, c.side)))


HOLD = {
    E_ + 'the_land_girls': 1.2,
    E_ + 'for_freedom': 0.8,
    E_ + 'quinine': 0.8,
    E_ + 'uss_sullivans': 1.0,
    CHAIN: 2.0,
    FORMIDABLE: _formidable_hold,
    E_ + 'area_bombardment': 3.0,
    E_ + 'interception': 0.8,
    E_ + 'aerial_reconaissance': 0.6,
}


def allow(sim, c, ctx):
    n = c.name
    my = sim.side[c.side]
    if n == E_ + 'area_bombardment':
        # 6 费 + 兰开斯特行动费 3：当回合打不出去就只是白占支援线一格
        return my['kredits'] >= (c.cost or 0) + 3
    if n == E_ + 'aerial_reconaissance':
        return sum(1 for h in _hand(sim, c.side) if h.type == 'order' and (h.cost or 0) >= 2 and h is not c) >= 2
    if n == E_ + 'interception':
        return any((u.df or 0) >= 4 for u in sim.units(c.side))     # 有值得保护的大单位才埋
    if n in SWAPS:
        return any((u.df or 0) >= SWAP_DF for u in sim.units(c.side))
    return True


def allow_option(sim, c, t, k, ctx):
    n = c.name
    if n in FRIENDLY_ONLY:
        u = sim.find(t)
        return u is None or u.side == c.side
    if n in SWAPS:
        u = sim.find(t)
        return u is not None and (u.df or 0) >= SWAP_DF
    return True


def hold(sim, c, ctx):
    h = HOLD.get(c.name)
    if h is not None:
        return h(sim, c, ctx) if callable(h) else h
    if c.type == 'order':
        return 0.3 * (c.cost or 0)
    v = 0.5 * (c.atk or 0) + 0.5 * (c.df or 0) + (1.0 if c.guard else 0) + (c.armor or 0) + _persist(sim, c, ctx)
    if c.name == U_ + 'frontier_force':
        v += 1.0                          # 部署时给一张卫戍
    return HOLD_FRAC * v


def _front_pressure(sim, u):
    if not (u.loc or '').startswith('front') or u.type not in ('infantry', 'tank', 'artillery'):
        return 0.0
    hq = max(0, sim.side[_e(u.side)]['hq'].df)
    atk = max(0, (u.atk or 0) - sim.temp.get(u.id, 0))
    v = FRONT_PRESSURE * min(atk, hq)
    if (u.df or 0) > atk and (u.df or 0) >= SWAP_DF and _swaps_in_hand(sim, u.side):
        # 偷偷上前线的高防单位：下回合本土链/可畏号让它攻击 = 防御，清掉挡路的再打总部
        v += SWAP_PRESSURE * min(u.df - atk, hq)
    return v


def persist(sim, u, ctx):
    return _front_pressure(sim, u) + _persist(sim, u, ctx)


def _persist(sim, u, ctx):
    n = u.name
    if n == BUFFS:
        # 增益吸收器：手里每张能指向它的增益牌多给 +1+1
        k = sum(1 for h in _hand(sim, u.side) if h.name in FRIENDLY_ONLY)
        return 0.5 + 0.4 * min(3, k)
    if n == U_ + '70th_brigade':
        # 没被攻击就每回合抽 1 + 总部 +2：在支援线更难被碰到
        return (1.2 if (u.loc or '').startswith('support') else 0.6) * _r(ctx, 4)
    if n == U_ + 'garrison':
        return 0.3 * _r(ctx)              # 没被攻击时每回合打对面总部 1 点
    if n == U_ + 'short_sunderland':
        return 0.8 * _r(ctx, 4)           # 回合结束抽 1 张海军牌（可畏号/沙利文兄弟号共 6 张）
    if n == U_ + '85_pioneer_company':
        return 0.4 * _r(ctx, 4)           # 每回合第一张指令 -1 费
    return 0.0


def allow_attack(sim, u, t):
    return u.name != U_ + '85_pioneer_company'      # 0 攻


def allow_move(sim, u):
    return u.name != U_ + '85_pioneer_company'


KEEP = {BUFFS, U_ + 'welsh_guards', E_ + 'quinine', E_ + 'for_freedom', U_ + '2nd_west_africa',
        U_ + '85_pioneer_company', E_ + 'uss_sullivans'}


def keep(name, cost):
    """起手调度：留米色团、1 费步兵和便宜增益，大牌换掉"""
    return name in KEEP


# 难度加成（native/buffs.py）：OPENING = 老兵及以上的起手候选池（随机挑 4~5 张）；CORE = 地狱档手牌少时打印的核心牌
OPENING = [BUFFS, U_ + 'welsh_guards', E_ + 'quinine', E_ + 'for_freedom', U_ + '2nd_west_africa',
           E_ + 'uss_sullivans', U_ + '85_pioneer_company']
CORE = [BUFFS, FORMIDABLE, CHAIN, U_ + 'frontier_force', U_ + '70th_brigade']
