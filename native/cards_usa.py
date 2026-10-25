# 美+英加费控制卡组（含衍生牌）
# 结算细则以用户确认为准（2026-10-14）：海战含己方单位；海鹰减少所有敌方伤害；战略轰炸打到敌方总部；
# 101 空降可打总部；探路者只能打单位；专家步兵团协力国家 = 美国
import sim_rules as R
from sim import SC, other
from effects import P, U, card, on, gain, buff, rand_kill, rand_damage, unit_or_hq, research, enemy_targets

B29 = U + 'b_29_super_fortress'


# ---------- 指令 ----------
@on('play', P + 'advanced_us_research')
def _advanced(sim, c, t, k):
    if k == 0:
        R.add_hand(sim, c.side, P + 'penicillin')
    else:
        R.add_hand(sim, c.side, P + 'manhattan_project')
        R.add_hand(sim, c.side, P + 'manhattan_project')


_advanced.products = ((P + 'penicillin', 1), (P + 'manhattan_project', 2))   # 研发链估值用（research_v.chain_hold）


@on('play', P + 'depth_charges')
def _depth(sim, c, t, k):
    R.gain_slot(sim, c.side, 1)
    sim.side[c.side]['hq'].smoke = True        # 指挥部烟幕到我方下回合开始


@on('play', P + 'pressurized_cabin')
def _cabin(sim, c, t, k):
    R.add_hand(sim, c.side, B29)
    rand_kill(sim, c.side)


@on('play', P + 'penicillin')
def _penicillin(sim, c, t, k):
    for u in sim.units(c.side) + [sim.side[c.side]['hq']]:
        u.df += 6
    R.draw(sim, c.side, 4)


@on('play', P + 'manhattan_project')
def _manhattan(sim, c, t, k):
    e = other(c.side)
    for u in list(sim.units(e)) + [sim.side[e]['hq']]:
        R.damage(sim, u, 6, c.side)


@on('play', P + 'mi_5')
def _mi5(sim, c, t, k):
    # 对方随机一张手牌放回牌库顶：下回合它会把这张抽回来，等于少抽一张新牌
    h = sim.side[other(c.side)]['hand']
    if h:
        sim.bonus += 1.5 if c.side == sim.me else -1.5
        # 手牌真的少一张（实测预测偏差：对方手牌每次预测多 1 张）；不知道是哪张，先拿未知牌
        h.remove(next((x for x in h if x.name == '?'), h[0]))
    R.draw(sim, c.side, 1)


@on('play', P + 'uss_missouri')
def _missouri(sim, c, t, k):
    x = sim.find(t)
    if x is None or x not in sim.side[x.side]['front']:
        return
    line = sorted(sim.side[x.side]['front'], key=lambda u: u.slot)
    i = line.index(x)
    adj = [line[j] for j in (i - 1, i + 1) if 0 <= j < len(line)]
    R.destroy(sim, x)
    for u in adj:
        R.retreat(sim, u)


@on('play', P + 'strategic_bombing')
def _bombing(sim, c, t, k):
    e = other(c.side)
    for u in list(sim.side[e]['support']) + [sim.side[e]['hq']]:
        R.damage(sim, u, 3, c.side)
    R.gain_slot(sim, e, -1)


@on('play', P + 'naval_battle')
def _naval(sim, c, t, k):
    parity = 1 if k == 0 else 0                 # 0 = 奇数花费，1 = 偶数花费
    for u in list(sim.units('left')) + list(sim.units('right')):
        if (u.cost or 0) % 2 == parity:
            R.destroy(sim, u)


@on('play', P + 'seaborne_invasion')
def _invasion(sim, c, t, k):
    e, me = other(c.side), c.side
    for u in list(sim.side[e]['front']):
        R.retreat(sim, u)
    # 刷出 2 个攻击和为 6 的美国步兵：池子不可控，按两个 3/3 估
    for _ in range(2):
        if len(sim.side[me]['front']) < R.FRONT_MAX:
            u = SC.new(U + 'seaborne_token', me, sim.new_id(), 'front')
            u.type, u.atk, u.df, u.op, u.cost, u.faction = 'infantry', 3, 3, 1, 3, 'USA'
            R.place(sim, me, u, 'front')
            sim.deployed.add(u.id)


card(P + 'the_war_machine', play=lambda sim, c, t, k: R.gain_slot(sim, c.side, 1))
def _war_bonds(sim, c, t, k):
    R.gain_slot(sim, c.side, 2)
    sim.bonus += R.DRAW_V * 0.8                  # 下回合多抽一张的价值（爆不爆由 planner.evaluate 按 extra_draw 算）
    if c.side == sim.me:
        sim.extra_draw = getattr(sim, 'extra_draw', 0) + 1


card(P + 'war_bonds', play=_war_bonds)
card(P + 'us_military_research', choose_one=True,
     play=research(P + 'depth_charges', P + 'expanded_us_research'))
card(P + 'expanded_us_research', choose_one=True,
     play=research(P + 'pressurized_cabin', P + 'advanced_us_research'))
card(P + 'advanced_us_research', choose_one=True)
card(P + 'naval_battle', choose_one=True)
card(P + 'for_freedom',
     play=lambda sim, c, t, k: (buff(sim.find(t), 1, 1), R.draw(sim, c.side, 1)),
     options=lambda sim, c: [(u.id, 0) for u in sim.units(c.side)])
card(P + 'convoy_175', play=lambda sim, c, t, k: R.draw(sim, c.side, 2))
# 英美米色团卡组（2026-10-24）：奎宁只能给步兵；沙利文兄弟号卡组顶那个单位 +1+1 看不到，按半张增益记
card(P + 'quinine',
     play=lambda sim, c, t, k: (buff(sim.find(t), 1, 2),
                                setattr(sim.find(t), 'op', max(0, (sim.find(t).op or 0) - 1)) if sim.find(t) else None),
     options=lambda sim, c: [(u.id, 0) for u in sim.units(c.side) if u.type == 'infantry'] +
     [(i, 0) for i in enemy_targets(sim, c.side, ('support', 'front'), smoke_ok=True, by_order=True)
      if sim.find(i).type == 'infantry'])
card(P + 'uss_sullivans',
     play=lambda sim, c, t, k: (buff(sim.find(t), 1, 1), gain(sim, c.side, 0.8), R.draw(sim, c.side, 1)),
     options=lambda sim, c: [(u.id, 0) for u in sim.units(c.side)] +
     [(i, 0) for i in enemy_targets(sim, c.side, ('support', 'front'), smoke_ok=True, by_order=True)])
card(P + 'supply_shipment',
     play=lambda sim, c, t, k: buff(sim.find(t), 2, 3),
     options=lambda sim, c: [(u.id, 0) for u in sim.side[c.side]['front']])
card(P + 'combined_chiefs_of_staff', play=lambda sim, c, t, k: [
    buff(u, 2, 3) for u in sim.units(c.side) if u.faction in ('Britain', 'USA')])
card(P + 'uss_missouri',
     options=lambda sim, c: [(i, 0) for i in enemy_targets(sim, c.side, ('front',), smoke_ok=True, by_order=True)])
card(P + 'death_from_above', play=lambda sim, c, t, k: rand_kill(sim, c.side))


# ---------- 部署 ----------
@on('deploy', U + '327th_pathfinders')
def _pathfinder(sim, c, t):
    x = sim.find(t)
    if x is not None and x.type != 'location':
        R.damage(sim, x, 2, c.side)
        if x not in sim.units(x.side):
            c.vet, c.blitz = True, True         # 消灭目标 -> 升为老兵（老兵形态带闪击）


@on('deploy', U + '101st_airborne')
def _airborne(sim, c, t):
    x = unit_or_hq(sim, c.side, t)
    if x is not None:
        R.damage(sim, x, 2, c.side)


card(U + 'middlesex_regiment', deploy=lambda sim, c, t: R.add_hand(sim, c.side, U + 'garrison'))
card(U + '327th_pathfinders',           # 探路者只能打单位
     deploy_targets=lambda sim, c: enemy_targets(sim, c.side, ('support', 'front')))
card(U + '101st_airborne',              # 101 空降可打支援线单位或总部
     deploy_targets=lambda sim, c: enemy_targets(sim, c.side, ('support',)) + [sim.side[other(c.side)]['hq'].id])
card(B29, deploy=lambda sim, c, t: rand_damage(sim, c.side, 6))   # 6 点随机分配到所有敌方目标


# ---------- 亡计 ----------
# 专家步兵团：牌库里所有单位 +2+3 和 1 个随机战斗词条
card(U + 'the_professionals', destroyed=lambda sim, u: gain(sim, u.side, sim.ctx.get('deck_units', 6) * 1.2))


# ---------- 光环 ----------
card(U + 'seahawk',                     # SC 海鹰：受到的所有敌方伤害 -1（可叠加）
     reduce=lambda sim, u, t, src, by_unit: 1 if src != t.side else 0)
card(U + 'us_signal_corps',             # 593 通信连：友方指挥部受到的伤害 -1
     reduce=lambda sim, u, t, src, by_unit: 1 if t.type == 'location' else 0)
card(U + 'm26_pershing',                # 潘兴在前线时，友方指挥部不低于 1
     hq_floor=lambda sim, u: u in sim.side[u.side]['front'])
card(U + 'm3a3_honey_desert',           # 甜心：友方每抽 1 张牌，指挥部 +1
     ally_draw=lambda sim, u: setattr(sim.side[u.side]['hq'], 'df', sim.side[u.side]['hq'].df + 1))


# ---------- 防火墙卡组 ----------
@on('play', P + 'firewall')
def _firewall(sim, c, t, k):
    # 目标永久“不能攻击敌方指挥部”（用户确认）；驱动记在 memo['firewalled']，之后每回合给它挂 no_hq
    u = sim.find(t)
    if u is None:
        return
    if u.side != c.side and not getattr(u, 'no_hq', False):
        from cards_britain import neutral_v
        gain(sim, c.side, neutral_v(sim, c.side, u, u.atk or 0))
    u.no_hq = True
    sim.firewalled = sim.firewalled | {u.id}
    sim.neutralized = sim.neutralized | {u.id}


@on('play', P + 'land_of_the_free')
def _land_of_the_free(sim, c, t, k):
    u = sim.find(t)
    if u is not None:
        u.op = 0                             # 行动费变 0（永久）；给敌方用于配两难困境：攻击 <-> 0


def _order_targets(sim, c):
    return [i for i in enemy_targets(sim, c.side, ('support', 'front'), smoke_ok=True, by_order=True)]


# ---------- 美法“行动费 3+”卡组（2026-10-17） ----------
# 结算细则（用户确认）：永先者团的免费行动照样触发密歇根（按行动费算，不扣指挥点）；“加入的步兵”= 以任何方式进入战场；
# 燃烧弹付完费后剩 >= 2 点才溢出，溢出伤害逐点随机分配；反袭在攻击结算前消灭攻击者；
# 散兵团/骇人/工兵看的是部署效果（游骑兵抉择）结算之后的行动费
HIGH_OP = 3


def _high_op(u):
    return (u.op or 0) >= HIGH_OP


@on('play', P + 'firebomb')
def _firebomb(sim, c, t, k):
    x = sim.find(t)
    if x is None:
        return
    before = max(0, x.df or 0)
    dealt = R.damage(sim, x, 5, c.side)
    excess = dealt - before if x not in sim.units(x.side) else 0
    if excess > 0 and sim.side[c.side]['kredits'] >= 2:
        rand_damage(sim, c.side, excess)        # 溢出伤害随机打敌人（含总部）


@on('play', P + 'victory_march')
def _victory_march(sim, c, t, k):
    # 友方单位行动费变 0（永久），总部加防 = 减掉的总数
    n = 0
    for u in sim.units(c.side):
        n += max(0, u.op or 0)
        u.op = 0
    sim.side[c.side]['hq'].df += n


@on('play', P + 'counter_strike')
def _counter_strike(sim, c, t, k):
    # 反制：敌方单位攻击我方总部时（结算前）消灭它。威胁的扣减在 planner.threat 里；这里记“大概率换掉一个单位”的价值
    att = [(u.atk or 0) + max(0, u.df or 0) for u in sim.units(other(c.side)) if u.atk and not u.pinned]
    gain(sim, c.side, 0.4 * max(att) if att else 0.3)


@on('deploy', U + 'b_24_j')
def _b24j(sim, c, t):
    x = sim.find(t)
    if x is None:
        return
    import effects
    line = sorted(sim.side[x.side]['front'] if x in sim.side[x.side]['front'] else sim.side[x.side]['support'],
                  key=lambda u: u.slot if u.slot is not None else 99)
    i = line.index(x)
    for u in [x] + [line[j] for j in (i - 1, i + 1) if 0 <= j < len(line)]:
        effects.suppress(sim, u, c.side)


@on('deploy', U + 'fifth_ohio')
def _fifth_ohio(sim, c, t):
    x = sim.find(t)
    if x is not None:
        R.destroy(sim, x)


@on('deploy', U + '5th_rangers')
def _rangers(sim, c, t, k):
    if k == 0:
        c.op = 0                                # 卡面第一个选项：行动费 0
    else:
        buff(c, 4, 4)


@on('deploy', U + '116th_infantry_regiment')
def _116th(sim, c, t):
    x = sim.find(t)
    if x is None:
        return
    buff(x, 5, 5, sim, c)
    for h in sim.side[c.side]['hand']:
        if h.name == x.name:
            buff(h, 5, 5)                       # 手里同名的也 +5+5
    # 牌库里同名的：牌库不模拟，张数由卡组给（plan.deck_copies），每张按 +5+5 一半价值估
    f = getattr(sim.ctx.get('plan'), 'deck_copies', None)
    if f:
        gain(sim, c.side, 2.5 * f(sim, x.name))


@on('after_deploy', U + '13th_engineers_battalion')
def _13th(sim, u, new):
    if _high_op(new):
        R.gain_slot(sim, u.side, 1)


@on('after_deploy', U + 'les_terribles')
def _terribles(sim, u, new):
    if _high_op(new):
        R.draw(sim, u.side, 1)


@on('ally_entered', U + '1st_infantry_regiment_us')
def _1st(sim, u, new):
    if new.type == 'infantry':
        sim.free = sim.free | {new.id}          # 本回合免费行动一次（不受部署当回合限制）


@on('ally_operated', U + '2nd_michigan')
def _michigan(sim, u, x, paid):
    if _high_op(x):
        sim.side[u.side]['kredits'] += 2        # 含自己；免费行动也算（按行动费，用户确认）


def _b24d_cost(sim, c):
    import card_db
    base = (card_db.get(c.name) or {}).get('kredits', c.cost)
    return max(0, base - 3) if any(_high_op(u) for u in sim.units(c.side)) else base


card(P + 'production_order', choose_one=True, play=research(U + 'b_24_d', U + 'b_24_j'))
card(U + 'b_24_d', cost=_b24d_cost)
card(U + 'b_24_j', deploy_targets=lambda sim, c: enemy_targets(sim, c.side, ('support', 'front')))
card(U + 'fifth_ohio', deploy_targets=lambda sim, c: [
    i for i in enemy_targets(sim, c.side, ('support', 'front'))
    if (sim.find(i).atk or 0) + max(0, sim.find(i).df or 0) <= 6])
card(U + '5th_rangers', deploy_choose_one=True)
card(U + '116th_infantry_regiment',
     deploy_targets=lambda sim, c: [u.id for u in sim.units(c.side) if u.type == 'infantry'])
card(P + 'firebomb', options=lambda sim, c: [(i, 0) for i in enemy_targets(sim, c.side, ('support', 'front'),
                                                                           smoke_ok=True, by_order=True)])
card(U + 'tigercat')           # 回合结束送一架 SBD 无畏：客户端结算，卡组按 persist 估值


# 只写卡面允许的目标；“给谁、什么时候给”是卡组的事（deck_britain_firewall.allow_option）
card(P + 'firewall', options=lambda sim, c: [(i, 0) for i in _order_targets(sim, c)])
card(P + 'land_of_the_free', options=lambda sim, c: [(u.id, 0) for u in sim.units(c.side)] +
     [(i, 0) for i in _order_targets(sim, c)])
