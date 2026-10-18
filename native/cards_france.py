# 法国（盟国）的牌
# 抑制 ≠ 压制（Kards规则.txt）：出动对步兵是抑制（effects.suppress），对坦克是压制
import sim_rules as R
from sim import other
from effects import P, U, card, on, gain, enemy_targets, suppress

RES_V = 1.2       # 塞进对方牌库的 1 张抵抗：对方抽到自动打出，-1 指挥点、总部 -1、压制自己一个单位、再抽 1


def _order_targets(sim, c):
    return [(i, 0) for i in enemy_targets(sim, c.side, ('support', 'front'), smoke_ok=True, by_order=True)]


@on('play', P + 'sally')
def _sally(sim, c, t, k):
    x = sim.find(t)
    if x is None:
        return
    if x.type == 'tank':
        x.pinned = True
    elif x.type == 'infantry':
        suppress(sim, x, c.side)
    elif x.type == 'artillery':
        R.destroy(sim, x)
    elif x.type in R.AIR:
        R.retreat(sim, x)                       # 支援线上的空军撤退不了（retreat 只动前线）


@on('play', P + 'liberation')
def _liberation(sim, c, t, k):
    sim.side[c.side]['hq'].df += 6
    R.add_deck(sim, other(c.side), 3)
    gain(sim, c.side, 3 * RES_V)


@on('play', P + 'arming_resistance')
def _arming(sim, c, t, k):
    # 5 点伤害，溢出几点就往对方牌库塞几张抵抗
    x = sim.find(t)
    if x is None:
        return
    before = max(0, x.df or 0)
    dealt = R.damage(sim, x, 5, c.side)
    excess = max(0, dealt - before) if x not in sim.units(x.side) else 0
    if excess:
        R.add_deck(sim, other(c.side), excess)
        gain(sim, c.side, excess * RES_V)


@on('play', P + 'saar_probe')
def _saar(sim, c, t, k):
    R.damage(sim, sim.find(t), 7, c.side) if sim.find(t) else None
    if sim.played == 1:                         # 本回合第一张指令：送洛林十字
        R.add_hand(sim, c.side, P + 'cross_of_lorraine')


@on('play', P + 'cross_of_lorraine')
def _lorraine(sim, c, t, k):
    from effects import unit_or_hq
    x = unit_or_hq(sim, c.side, t)
    if x is not None:
        R.damage(sim, x, 3, c.side)


def _lorraine_cost(sim, c):
    import card_db
    base = (card_db.get(c.name) or {}).get('kredits', 9)
    return max(0, base - len(sim.side[other(c.side)]['hand']))   # 敌方每有一张手牌 -1 费


@on('play', P + 'defend_in_depth')
def _defend(sim, c, t, k):
    x = sim.find(t)
    if x is not None:
        R.damage(sim, x, len(sim.side[other(c.side)]['hand']), c.side)


@on('play', P + 'phoney_war')
def _phoney(sim, c, t, k):
    # 双方各抽“离 8 张差几张”（用户确认）。对方抽牌的估值走 R.draw 的 ENEMY_DRAW_V（卡组给）
    for s in (c.side, other(c.side)):
        R.draw(sim, s, max(0, 8 - len(sim.side[s]['hand']) - (sim.hand_extra if s == sim.me else 0)))


@on('deploy', U + '5e_cuirassier')
def _cuirassier(sim, c, t):
    if sim.deploys == 1:                        # 本回合第一个部署的单位
        R.add_hand(sim, c.side, U + '18e_regiment')


@on('after_deploy', U + '8e_tirailleurs_marocains')
def _tirailleurs(sim, u, new):
    sim.side[u.side]['hq'].df += max(0, new.op or 0)


card(P + 'sally', options=_order_targets)
card(P + 'defend_in_depth', options=_order_targets)
card(P + 'arming_resistance', options=_order_targets)
card(P + 'saar_probe', options=_order_targets)
card(P + 'cross_of_lorraine', cost=_lorraine_cost,
     options=lambda sim, c: _order_targets(sim, c) + [(sim.side[other(c.side)]['hq'].id, 0)])
card(U + '18e_regiment')       # 回合结束若是本回合唯一部署的单位，行动费变 0：卡组按 eval 估
