# 苏波转换卡组（2026-10-22）：转换、诺夫哥罗德、钢铁师、开发等
# 结算细则（用户确认 2026-10-22）：
#   转换：位置不变、受的伤恢复、不触发部署；当回合不能行动，除非转出来的单位有闪击
#   诺夫哥罗德：每次转换效果送 1 个（不论转了几张）；狼团转敌方单位也算；送来的摩托化步兵不触发部署
#   4TP 转成钢铁师后回合结束不会被消灭；钢铁师活完整两回合（含出现那一轮），转出来/拿回来的从零算
#   修道院行动：闪击算对战词条（909 团给的也算，909 自己也有闪击）；西里西亚 44 团数词条时算它自己
#   336 旅复制的单位不触发部署；监视可以指向敌方单位；KV-85“上一个被消灭的友方单位”含衍生物，只看最后一个
#   胜利旗帜转换我方单位不触发诺夫哥罗德（诺夫哥罗德先被转换）
import sim_rules as R
from sim import SC, other
from effects import (P, U, card, on, gain, spawn, enemy_targets, convert, converted)

GROUND = ('infantry', 'tank', 'artillery')
IRON = U + 'iron_division'
MOTOR = U + '6th_motor_rifles_sov'


def _my_units(sim, c, exclude_self=True):
    return [u.id for u in sim.units(c.side) if not (exclude_self and u is c)]


def _any_units(sim, c):
    """任意单位（敌方排除隐蔽、不能被指令指向的）"""
    return enemy_targets(sim, c.side, ('support', 'front'), smoke_ok=True, by_order=True) + \
        [u.id for u in sim.units(c.side)]


# ---------- 转换 ----------
@on('deploy', U + '3rd_carpathian')
def _carpathian(sim, c, t):
    """部署：把 1 个友方单位转换为钢铁师（COMET 现版本；旧数据写的是乌兰骑兵）"""
    x = sim.find(t)
    if x is None or x.side != c.side or convert(sim, x, IRON, c.side) is None:
        return
    converted(sim, c.side)


card(U + '3rd_carpathian', deploy_targets=lambda sim, c: _my_units(sim, c))


@on('ally_converted', U + '312th_novgorod')
def _novgorod(sim, u, n):
    spawn(sim, u.side, MOTOR)          # 摩托化步兵第 6 团（3/3 闪击伏击），刷出来的不触发部署


@on('play', P + 'victory_banners')
def _banners(sim, c, t, k):
    """指向 1 个单位：把它的所有者场上所有单位（包括它自己）转换为它（卡面数值）。
    实测 132795：目标自己也换了新 id（加成、伤害清掉，当回合不能行动），不是只转其余单位"""
    x = sim.find(t)
    if x is None or x not in sim.units(x.side):
        return
    side = x.side
    name = x.name
    others = list(sim.units(side))
    for u in others:
        convert(sim, u, name, c.side)
    if others and side != c.side:
        converted(sim, c.side)         # 转我方单位时诺夫哥罗德先被转掉，不触发（用户确认）


card(P + 'victory_banners', options=lambda sim, c: [(i, 0) for i in _any_units(sim, c)])


@on('play', P + 'surveil')
def _surveil(sim, c, t, k):
    """选 1 张手牌转换为指向的单位（k = 手牌卡 id；live_driver 另发手牌目标，格式待抓包确认）"""
    x = sim.find(t)
    h = next((y for y in sim.side[c.side]['hand'] if y.id == k), None)
    if x is None or h is None:
        return
    hand = sim.side[c.side]['hand']
    n = SC.new(x.name, c.side, h.id, h.loc)
    n.slot = h.slot
    hand[hand.index(h)] = n
    converted(sim, c.side)


card(P + 'surveil', options=lambda sim, c: [
    (i, h.id) for i in _any_units(sim, c) for h in sim.side[c.side]['hand'] if h is not c and h.name != '?'])


@on('deploy', U + 'kv_85')
def _kv85(sim, c, t):
    """把 1 张手牌转换为上 1 个被消灭的友方单位；下个友方回合开始少 2 个指挥点"""
    gain(sim, c.side, -2 * 0.8)
    last = (getattr(sim, 'last_dead_any', {}) or {}).get(c.side)
    hand = sim.side[c.side]['hand']
    h = next((y for y in hand if y.id == t), None)
    if last is None or h is None:
        return
    n = SC.new(last.name, c.side, h.id, h.loc)
    n.slot = h.slot
    hand[hand.index(h)] = n
    converted(sim, c.side)


card(U + 'kv_85', deploy_targets=lambda sim, c: [h.id for h in sim.side[c.side]['hand']
                                                 if h is not c and h.name != '?'] or [0])


# ---------- 部署 ----------
@on('deploy', U + '3rd_morskoi_pekhoty')
def _morskoi(sim, c, t):
    spawn(sim, c.side, U + 'light_infantry')
    R.add_hand(sim, c.side, P + 'blast')


@on('deploy', U + '44th_silesia')
def _silesia(sim, c, t):
    import cards_soviet
    R.draw(sim, c.side, sum(1 for u in sim.units(c.side) if cards_soviet._kw(u) >= 2))


@on('deploy', U + '336th_guards_naval')
def _naval336(sim, c, t):
    """手里 1 张花费 <= 3 的单位：复制一个上支援线（不触发部署）。驱动另发手牌目标"""
    h = next((y for y in sim.side[c.side]['hand'] if y.id == t), None)
    if h is not None:
        spawn(sim, c.side, h.name)


card(U + '336th_guards_naval', deploy_targets=lambda sim, c: [
    h.id for h in sim.side[c.side]['hand'] if h is not c and h.type in R.UNIT_TYPES and (h.cost or 0) <= 3] or [0])

DEVELOP_740 = (P + 'arctic_convoy', P + 'burning_sky', P + 'the_hammer')


@on('deploy', U + '740th_rifle_regiment')
def _740th(sim, c, t, k):
    R.add_hand(sim, c.side, DEVELOP_740[k])   # 开发：三选一（驱动补发 XActionCardToDrawSelected）


card(U + '740th_rifle_regiment', deploy_choose_one=3)


@on('deploy', MOTOR)
def _motor(sim, c, t):
    R.draw(sim, c.side, 1)
    gain(sim, c.side, 1.0)             # 卡组里 2 张牌变成它（之后抽到的更好）


# ---------- 指令 ----------
@on('play', P + 'the_hammer')
def _hammer(sim, c, t, k):
    x = sim.find(t)
    if x is not None:
        R.damage(sim, x, 6, c.side)


card(P + 'the_hammer', options=lambda sim, c: [(i, 0) for i in _any_units(sim, c)
                                              if (sim.find(i).type in GROUND)])


@on('play', P + 'burning_sky')
def _burning_sky(sim, c, t, k):
    x = sim.find(t)
    if x is not None:
        R.damage(sim, x, 4, c.side)


card(P + 'burning_sky', options=lambda sim, c: [(i, 0) for i in enemy_targets(
    sim, c.side, ('support', 'front'), smoke_ok=True, by_order=True) if sim.find(i).type in R.AIR])


@on('play', P + 'arctic_convoy')
def _arctic(sim, c, t, k):
    R.draw(sim, c.side, 2)             # 抽 2 张单位（模拟里按未知牌）


# ---------- 光环 / 回合触发 ----------
card(U + '909th_roslavl',                # 友方步兵具有闪击
     kw_aura=lambda sim, u, x: {'blitz': True} if x.type == 'infantry' else None)
card(U + '28th_infantry_regiment',       # 对战存活后 +1+1
     survived=lambda sim, u, t: (setattr(u, 'atk', (u.atk or 0) + 1), setattr(u, 'df', (u.df or 0) + 1)))
card(IRON)                               # 回合开始抽 1，第三次后消灭：对方回合后结算，按 persist 估值
card(U + '312th_novgorod')
card(U + '24th_uhlan')                   # 旧版喀尔巴阡的产物（COMET 已改为钢铁师）
