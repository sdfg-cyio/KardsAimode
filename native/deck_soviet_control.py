# 打法：苏联 + 意大利 控制（指挥部 布良斯克）
# 思路：低费守护挡线、站住前线；清场对己方伤害小（我方多为高防御/多词条单位，小兵阵亡有亡计）；
# 216 团/以剑之名/雅克补牌，329/G.50/进攻殖民地回血抵消自伤；方面军、近卫 4 团、KV-1 1941、小国成员收尾
NAME = 'soviet_control'
DECK_CODE = '%%47|8C919bDZg6h3jWmtpkppqLqTrjvewqxmyX;9a9xfrfXhGjMmToYwowSz0;;'
HQ = 'card_location_bryansk_waw'
TITLE = '苏意控'
COMMANDER = '喀秋莎'
AVATAR = 'avatar_to_arms'               # 拿起武器
MAIN, ALLY = 'Soviet', 'italy'

# 控制卡组：自保 > 打脸；守得住时尽量站住前线（防止对方前线单位打支援线和总部）
W = {'my_hq': 1.2, 'en_hq': 0.8, 'threat': 1.3, 'front': 2.5, 'board': 1.0}
HOLD_FRAC = 0.5
EPHEMERAL = {'card_unit_t_34eot'}   # 方面军送的 T-34：回合结束被消灭，留着没价值，每回合都该打出去
DANGER_DMG = 7

E_, U_ = 'card_event_', 'card_unit_'


def _r(ctx, n=5):
    return min(ctx.get('R', 6), n)


def danger(ctx):
    """敌方下回合能打到总部 >= 7 点，或足以斩杀"""
    return ctx.get('T', 0) >= DANGER_DMG or ctx.get('T', 0) >= ctx.get('H', 20)


def _big_enemy(sim, side):
    """敌方有需要处理的强单位（倾斜装甲的打出条件）"""
    e = 'left' if side == 'right' else 'right'
    return any((u.atk or 0) >= 5 or (u.atk or 0) + (u.df or 0) >= 11 for u in sim.units(e))


def _en(sim, side):
    return sim.units('left' if side == 'right' else 'right')


def _small_ground(sim, side):
    return sum(1 for u in _en(sim, side) if u.type in ('infantry', 'tank', 'artillery') and (u.df or 0) <= 2)


def _standard_ammo(sim, c, ctx):
    """手牌和牌库里的单位部署、行动都 -1：手里的单位全算，牌库里的按这局还能抽到的比例"""
    hand = sum(1 for h in sim.side[c.side]['hand'] if h.type not in ('order', 'location'))
    return 0.6 * (hand + 0.4 * ctx.get('deck_units', 6))


def _sloped_armor(sim, c, ctx):
    """0 费召一辆斯大林重坦（12/12 量级）打指定敌方单位，回合结束回手、下回合还能用：
    按“现在场上最值得杀的那个”估，再加一点“以后还能再用”的价值"""
    # 空场时也有价值（对面迟早会下大单位，它每回合都能回手再用）：保底 2.5
    best = max((0.5 * ((u.atk or 0) + (u.df or 0)) + 0.3 * (u.atk or 0) for u in _en(sim, c.side)), default=0)
    return max(2.5, 1.5 + 0.6 * best)


def _chain(sim, c, ctx):
    import research_v
    return research_v.chain_hold(sim, c, ctx, hold, allow_option)


HOLD = {
    E_ + 'monastyr': 5.0,
    E_ + 'winter_offensive': 4.5,
    E_ + 'strategic_focus': 4.5,
    E_ + 'dagger_has_struck': 3.0,
    E_ + 'attack_in_the_colonies': 2.5,
    E_ + 'minority_recruits': 5.0,
    E_ + 'by_the_sword': 2.0,
    E_ + 'front_formation': 4.0,
    # 研发链：每层的留牌价值 = 往下最终能换到的产物价值 - 还要花的研发费用（research_v.chain_hold）。
    # 原来扩展研发/高级研发都是固定 6.0，推一层评分不变，AI 从不推；危险时扩展研发 -6 还让它在危险时最想推（bug）
    E_ + 'soviet_military_research': _chain,
    E_ + 'expanded_soviet_research': _chain,
    E_ + 'advanced_soviet_research': _chain,
    # 研发产物：按场面估
    E_ + 'aerosani': lambda sim, c, ctx: 1.0 + 0.5 * min(3, _small_ground(sim, c.side)),
    E_ + 'standard_ammo': _standard_ammo,
    E_ + 'sloped_armor': _sloped_armor,
    # 三张一起来：第一张值满，后面的打折（手牌位置有限，一回合也打不了几张 4 费）
    # 对面总部 <= 12 时三张 24 点随机伤害有斩杀机会，再加
    E_ + 'stalin_organ': lambda sim, c, ctx: 0.75 * (1.5 + 0.6 * min(5, len(_en(sim, c.side)))) + (
        1.5 if ctx['E'] <= 12 else 0.0),
    U_ + 'la_decima': 3.0,              # 部署效果是解场，要等对面支援线有值得杀的目标
}


def allow(sim, c, ctx):
    """打法层面禁止的出牌"""
    n = c.name
    H = sim.side[c.side]['hq'].df
    if n == E_ + 'front_formation':
        return H >= 10                  # 每回合自伤 1 点，血少时不开
    if n == U_ + '216th_guards':
        return H >= 12                  # 每回合自伤 2 点
    if n == E_ + 'winter_offensive':
        return H > 4 or sim.side['left' if c.side == 'right' else 'right']['hq'].df <= 4
    return True


def allow_option(sim, c, t, k, ctx):
    """研发第一层（用户经验）：有压力时选气动雪橇当回合解场，没压力往下研发；
    第二、三层两个都允许，按产物价值选（标准弹药看手里/牌库的单位数，倾斜装甲看场上最值得杀的目标）"""
    n = c.name
    if n == E_ + 'soviet_military_research':
        return k == (0 if danger(ctx) else 1)
    if n == E_ + 'expanded_soviet_research':
        # 标准弹药只在前期（7 槽前）且手里有 3 张以上单位时选（后面越来越多回合吃到 -1）；
        # 否则开高级研发（倾斜装甲 / 管风琴）。原来按值比较，前期空场标准弹药总赢，后期一直没见过管风琴（用户）
        units = sum(1 for h in sim.side[c.side]['hand'] if h.type not in ('order', 'location'))
        return k == 1 or (sim.side[c.side]['max_kredits'] < 7 and units >= 3)
    return True


def hold(sim, c, ctx):
    n = c.name
    if n == U_ + '4th_guards_rifles':
        # 在手里会随对面抽牌降费：费用高时等一等更值
        base = HOLD_FRAC * (0.5 * (c.atk or 0) + 0.5 * (c.df or 0) + 1.0)
        return base + (1.5 if (c.cost or 0) > 6 else 0)
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
    if n == U_ + '216th_guards':
        H = sim.side[u.side]['hq'].df
        if H <= 8:
            return -3.0                 # 血少时每回合自伤是负担
        return 0.5 * _r(ctx) + 1.2 * min(4, len(mine) + 1)   # 每回合抽 1 张；第二次触发升老兵 +3 防御
    if n == U_ + 'kv_1_1941':
        return 1.2 * _r(ctx)            # 敌方每抽 1 张，打其总部 2 点
    if n == U_ + 'armored_train':
        return 1.5 * _r(ctx, 4)         # 每回合送 1 个轻步兵
    if n == U_ + '11th_signal_battalion':
        return 1.0 + 0.8 * min(4, len(mine))   # 其他友方阵亡时总部 +2
    if n == U_ + '75th_rifle_regiment':
        return 1.5                      # 被敌方效果指向会复制，对面单体解场打它亏
    if n == U_ + 'bm_13n_us6':
        return 1.0                      # 被攻击时撤退回手牌，对面打它只能换掉一次攻击
    if n == U_ + 'fiat_g50':
        return 0.5 * _r(ctx, 4)         # 造成伤害时总部回血
    if n == U_ + 'ilyushin_10':
        return 1.5                      # 亡计复活上一个阵亡的陆军
    if n == U_ + 'is_i' and getattr(u, 'returns', False):
        return 3.0                      # 倾斜装甲的 IS-2：回合末回手，同时再复制一个上支援线
    return 0.0


KEEP = {U_ + '97th_rifles', U_ + '178th_guard_rifles', U_ + '55th_rifles', U_ + '289th_gatchina',
        U_ + 'fiat_g50', U_ + '11th_signal_battalion', E_ + 'soviet_military_research', U_ + 'bm_13n_us6'}


def keep(name, cost):
    """起手调度：留低费守线牌，清场和大单位换掉"""
    return name in KEEP or ((cost or 0) <= 3 and not name.startswith(E_))
