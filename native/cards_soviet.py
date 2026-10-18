# 苏+意控制卡组（含衍生牌）
# 结算细则以用户确认为准（2026-10-14）：修道院行动的词条数含闪击不含协力；冬季攻势/战略重心双方都打；
# 单刀直入在全场比攻击力；小国成员偷来的单位当回合可移动可攻击；BM-13N 被攻击时撤退回手牌
import sim_rules as R
import card_rules
from sim import other
from effects import (P, U, card, on, gain, all_units, rand_damage, unit_or_hq, spawn, research, enemy_targets)

KW = ('guard', 'fury', 'shock', 'armor', 'smoke', 'ambush', 'blitz')   # 对战词条（协力不算）
GROUND = ('infantry', 'tank', 'artillery')


def _kw(u):
    return sum(1 for k in KW if (getattr(u, k, 0) or 0))


def _enemies(sim, c, lines=('support', 'front')):
    """指令的敌方单位目标（排除隐蔽、不能被敌方指令指向的）"""
    return enemy_targets(sim, c.side, lines, smoke_ok=True, by_order=True)


def _targets(sim, c):
    return [(i, 0) for i in _enemies(sim, c)]


# ---------- 指令 ----------
@on('play', P + 'monastyr')
def _monastyr(sim, c, t, k):
    for u in all_units(sim):
        if _kw(u) <= 1:
            R.destroy(sim, u)


@on('play', P + 'winter_offensive')
def _winter(sim, c, t, k):
    for u in all_units(sim):
        R.damage(sim, u, 4, c.side)
    for s in ('left', 'right'):
        R.damage(sim, sim.side[s]['hq'], 4, c.side)


@on('play', P + 'strategic_focus')
def _focus(sim, c, t, k):
    kinds = GROUND if k == 0 else R.AIR    # 0 = 陆军，1 = 空军
    for u in all_units(sim):
        if u.type in kinds:
            R.damage(sim, u, 5, c.side)


@on('play', P + 'dagger_has_struck')
def _dagger(sim, c, t, k):
    x = sim.find(t)
    if x is None:
        return
    x.pinned = True
    others = [u.atk or 0 for u in all_units(sim) if u is not x]
    if (x.atk or 0) > max(others or [-1]):
        R.destroy(sim, x)


@on('play', P + 'attack_in_the_colonies')
def _colonies(sim, c, t, k):
    x = unit_or_hq(sim, c.side, t)
    if x is not None:
        R.damage(sim, x, 3, c.side)
    sim.side[c.side]['hq'].df += 5


@on('play', P + 'minority_recruits')
def _minority(sim, c, t, k):
    """控制敌方单位：原在支援线 -> 我方支援线（满了白控制）；原在前线且前线只有它 -> 原地归我；
    前线还有别的敌方单位 -> 我方支援线。当回合可以移动、攻击"""
    x = sim.find(t)
    if x is None:
        return
    me, e = c.side, other(c.side)
    was_front = x in sim.side[e]['front']
    if was_front and len(sim.side[e]['front']) == 1:
        sim.side[e]['front'].remove(x)
        R.place(sim, me, x, 'front')
        return
    if R.SUPPORT_MAX - len(sim.side[me]['support']) - (sim.extra_sup if me == sim.me else 0) <= 0:
        return
    sim.side[e]['front' if was_front else 'support'].remove(x)
    R.place(sim, me, x, 'support')


@on('play', P + 'front_formation')
def _front_formation(sim, c, t, k):
    # 永久：每个友方回合开始指挥部 -1，送一辆当回合有效的 5/5 闪击 T-34。按剩余回合估值
    gain(sim, c.side, 4.0 * min(sim.ctx.get('R', 6), 6))


@on('play', P + 'aerosani')
def _aerosani(sim, c, t, k):
    e = other(c.side)
    hq = sim.side[e]['hq']
    x = unit_or_hq(sim, c.side, t)
    if x is None:
        return
    line = sim.side[e]['support'] + [hq] if (x is hq or x in sim.side[e]['support']) else sim.side[e]['front']
    line = sorted(line, key=lambda u: u.slot if u.slot is not None else -1)
    i = line.index(x)
    for u in [x] + [line[j] for j in (i - 1, i + 1) if 0 <= j < len(line)]:
        R.damage(sim, u, 2, c.side)


@on('play', P + 'standard_ammo')
def _standard_ammo(sim, c, t, k):
    for h in sim.side[c.side]['hand']:
        if h.type in R.UNIT_TYPES:
            h.cost = max(0, (h.cost or 0) - 1)
            h.op = max(0, (h.op or 0) - 1)
    gain(sim, c.side, 1.0 * sim.ctx.get('deck_units', 8))     # 牌库里的单位也 -1 费


@on('play', P + 'sloped_armor')
def _sloped_armor(sim, c, t, k):
    u = spawn(sim, c.side, U + 'is_i')
    x = sim.find(t)
    if u is None or x is None:
        return
    u.returns = True                       # 回合结束回手（回手时再复制一个上支援线）
    R.fight(sim, u, x, effect=True)        # 效果战斗无视重甲


card(P + 'by_the_sword', play=lambda sim, c, t, k: R.draw(sim, c.side, len(sim.units(other(c.side)))))
card(P + 'stalin_organ', play=lambda sim, c, t, k: rand_damage(sim, c.side, 8))
card(P + 'soviet_military_research', choose_one=True,
     play=research(P + 'aerosani', P + 'expanded_soviet_research'))
card(P + 'expanded_soviet_research', choose_one=True,
     play=research(P + 'standard_ammo', P + 'advanced_soviet_research'))
card(P + 'advanced_soviet_research', choose_one=True,
     play=research(P + 'sloped_armor', P + 'stalin_organ', 3))
card(P + 'strategic_focus', choose_one=True)

# 指向目标
card(P + 'dagger_has_struck', options=_targets)
card(P + 'minority_recruits', options=_targets)
card(P + 'attack_in_the_colonies',
     options=lambda sim, c: _targets(sim, c) + [(sim.side[other(c.side)]['hq'].id, 0)])
card(P + 'aerosani',                    # 气动雪橇：敌方陆军或总部（连同相邻目标）
     options=lambda sim, c: [(i, 0) for i in [u.id for line in ('support', 'front')
                                              for u in sim.side[other(c.side)][line]
                                              if u.type in GROUND and not u.covert
                                              and not card_rules.order_immune(u.name)]
                             + [sim.side[other(c.side)]['hq'].id]])
card(P + 'sloped_armor',                # 倾斜装甲：支援线要有空位放 IS-2
     options=lambda sim, c: _targets(sim, c) if sim.sup_count() < R.SUPPORT_MAX else [])


# ---------- 部署 ----------
@on('deploy', U + 'la_decima')
def _la_decima(sim, c, t):
    x = sim.find(t)
    if x is not None and x in sim.side[other(c.side)]['support']:
        R.destroy(sim, x)


card(U + 'la_decima', deploy_targets=lambda sim, c: enemy_targets(sim, c.side, ('support',)))
card(U + '18th_bersaglieri', deploy=lambda sim, c, t: gain(sim, c.side, 1.0))   # 把第 9 神射手洗入卡组


# ---------- 亡计 ----------
@on('destroyed', U + 'ilyushin_10')
def _ilyushin(sim, u):
    last = sim.last_dead.get(u.side)
    if last is not None and spawn(sim, u.side, last.name) is not None:
        return
    gain(sim, u.side, 2.0)                 # 不知道上一个阵亡的陆军是谁（跨回合）：按 2 分估


@on('destroyed', U + '289th_gatchina')
def _gatchina(sim, u):
    R.draw(sim, u.side, 1)
    sim.side[u.side]['hq'].df += u.cost or 2


card(U + '97th_rifles', destroyed=lambda sim, u: (gain(sim, u.side, 2.0), R.draw(sim, u.side, 1)))  # 洗入 414 团 + 抽 1
card(U + '414th_rifles', destroyed=lambda sim, u: (gain(sim, u.side, 1.0), R.draw(sim, u.side, 3),
                                                   R.damage(sim, sim.side[u.side]['hq'], 3, u.side)))
card(U + '178th_guard_rifles', destroyed=lambda sim, u: spawn(sim, u.side, U + '89th_infantry'))
card(U + '55th_rifles', destroyed=lambda sim, u: gain(sim, u.side, 3 * 0.8))          # 下回合 +3 指挥点
card(U + '9th_bersaglieri', destroyed=lambda sim, u: gain(sim, u.side, 2.5))          # 洗入第 18 神射手
card(U + 'yak_9', destroyed=lambda sim, u: R.draw(sim, u.side, 1))


# ---------- 被指向 / 被攻击 / 战斗 ----------
card(U + '75th_rifle_regiment', targeted=lambda sim, u: spawn(sim, u.side, u.name))   # 被敌方效果指向：复制一个


@on('attacked', U + 'bm_13n_us6')
def _bm13(sim, u, a):
    # BM-13N：被攻击时在伤害造成前撤退回手牌（攻击方照样消耗攻击；手牌满则丢弃）
    d = sim.side[u.side]
    for line in ('support', 'front'):
        if u in d[line]:
            d[line].remove(u)
            R.add_hand(sim, u.side, u.name, cid=u.id)   # 回手是同一张牌（id 不变），数值按卡面重置
            break
    return True


card(U + 't_34_85_1945', keeps_shock=True)                               # 冲击后不失去冲击
card(U + 'macchi_c205', dmg_bonus=lambda sim, u, t: 2 if t.type in R.AIR else 0)   # 对空军伤害 +2
card(U + 'fiat_g50',                    # 造成伤害时友方总部获得同等防御
     dealt=lambda sim, u, t, n: setattr(sim.side[u.side]['hq'], 'df', sim.side[u.side]['hq'].df + n))


# ---------- 光环 ----------
card(U + '11th_signal_battalion',       # 329 通信营：其他友方单位被消灭时，友方总部 +2
     ally_destroyed=lambda sim, u, dead: setattr(sim.side[u.side]['hq'], 'df', sim.side[u.side]['hq'].df + 2))
card(U + 'kv_1_1941',                   # KV-1 1941：敌方每抽 1 张，对其总部 2 点
     enemy_draw=lambda sim, u: R.damage(sim, sim.side[other(u.side)]['hq'], 2, u.side))
card(U + '4th_guards_rifles',           # 近卫 4 团在手中：敌方每抽 1 张，-1 花费
     hand_enemy_draw=lambda sim, c: setattr(c, 'cost', c.cost - 1) if c.cost else None)
