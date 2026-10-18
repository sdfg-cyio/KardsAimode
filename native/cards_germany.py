# 德+美加费卡组（含研发链衍生牌）
# 结算细则（2026-10-15）：但泽与柏林没有区别；鼠式“每消灭一个造成 2 点伤害”可指向目标
# 让对方弃牌的效果（狼群战术、XXI 型潜艇、第 169 掷弹兵团）由客户端本地随机结算，这里只按张数估
import sim_rules as R
from sim import SC, other
from effects import (P, U, card, on, gain, buff, temp_atk, temp_op, once, unit_or_hq, research, enemy_targets,
                     all_units, rand_discard, suppress)

GROUND = ('infantry', 'tank', 'artillery')
NON_TANK = ('infantry', 'artillery', 'fighter', 'bomber')


def _enemies(sim, c, lines=('support', 'front')):
    """指令的敌方单位目标（排除隐蔽、不能被敌方指令指向的；烟幕挡不住指令）"""
    return enemy_targets(sim, c.side, lines, smoke_ok=True, by_order=True)


def _targets(sim, c, pred=None):
    return [(i, 0) for i in _enemies(sim, c) if pred is None or pred(sim.find(i))]


def _discard(sim, side, n):
    """side 随机弃 n 张：按张数结算（先丢未知牌，模拟里不分是哪张）"""
    h = sim.side[side]['hand']
    for _ in range(min(n, len(h))):
        h.sort(key=lambda c: c.name != '?')
        h.pop(0)
        gain(sim, other(side), 1.5)


def _bounce_value(u):
    """敌方单位回手：对方要再花费用和一回合重新部署，按单位价值的一半估（模拟里看不到对方手牌价值）"""
    return 0.25 * ((u.atk or 0) + (u.df or 0)) + 0.2 * (u.cost or 0)


def _can_act(sim, u):
    """本回合还能攻击（老兔子/闪电战只给能打的单位才有用）"""
    return (not u.pinned and not u.cant_attack and (u.id not in sim.deployed or u.blitz)
            and sim.attacks.get(u.id, 0) < (2 if u.fury else 1))


# ---------- 指令 ----------
@on('play', P + 'buzz_bomb')
def _buzz(sim, c, t, k):
    x = unit_or_hq(sim, c.side, t)
    if x is None:
        return
    R.damage(sim, x, 1, c.side)
    if x.type == 'location':
        R.draw(sim, c.side, 1)


@on('play', P + 'enigma')
def _enigma(sim, c, t, k):
    n = len(sim.side[other(c.side)]['hand']) - len(sim.side[c.side]['hand'])
    if n > 0:
        R.draw(sim, c.side, n)


@on('play', P + 'sky_barons')
def _sky_barons(sim, c, t, k):
    x = sim.find(t)
    if x is not None:
        R.destroy(sim, x)
    R.draw(sim, c.side, 1)


@on('play', P + 'wolfpack')
def _wolfpack(sim, c, t, k):
    x = sim.find(t)
    if x is None:
        return
    e = x.side
    full = len(sim.side[e]['hand']) >= R.HAND_MAX
    R.to_hand(sim, x)
    if not full:
        gain(sim, c.side, -_bounce_value(x))   # 回手不是消灭：对方还能再打出来（手牌满则直接爆掉）
    _discard(sim, e, 1)


@on('play', P + 'blitzkrieg')
def _blitzkrieg(sim, c, t, k):
    # 前线友方 +3 攻、-1 行动费，都到回合结束
    for u in sim.side[c.side]['front']:
        temp_atk(sim, u, 3, c)
        temp_op(sim, u, -1)


def _german_tanks(sim, side):
    return [u for u in sim.units(side) if u.type == 'tank' and u.faction == 'Germany']


@on('play', P + 'tank_wedge')
def _tank_wedge(sim, c, t, k):
    """目标德国坦克和同一战线上相邻的单位 +1+1（相邻按格子号排序；支援线的指挥部不算单位）"""
    x = sim.find(t)
    if x is None:
        return
    d = sim.side[x.side]
    line = sorted(d['front'] if x in d['front'] else d['support'], key=lambda u: u.slot if u.slot is not None else 99)
    i = line.index(x)
    for u in [x] + [line[j] for j in (i - 1, i + 1) if 0 <= j < len(line)]:
        buff(u, 1, 1, sim, c)


@on('play', P + 'suppression_fire')
def _suppression(sim, c, t, k):
    # 抑制 ≠ 压制：抹除词条和数值变化、特效失效（Kards规则.txt）
    suppress(sim, sim.find(t), c.side)
    if any(u.type in R.AIR for u in sim.units(c.side)):
        R.draw(sim, c.side, 1)


@on('play', P + 'capitulation')
def _capitulation(sim, c, t, k):
    """敌方全部单位变成溃兵（1/1 步兵、无词条）：不算消灭（不触发亡语）。
    实测客户端是移除原卡、在同一位置换成新编号的溃兵，所以这里也换新 id"""
    e = other(c.side)
    for line in ('support', 'front'):
        row = sim.side[e][line]
        for i, u in enumerate(row):
            n = SC.new(U + 'routed_troops', e, sim.new_id(), line)
            n.slot = u.slot
            row[i] = n
            sim.temp.pop(u.id, None)


@on('play', P + 'type_xxi_boat')
def _xxi(sim, c, t, k):
    x = sim.find(t)
    if x is not None:
        R.destroy(sim, x)
    _discard(sim, other(c.side), 2)


@on('play', P + 'uranium_club')
def _uranium(sim, c, t, k):
    n = 0
    for u in list(sim.units(other(c.side))):
        if R.destroy(sim, u):
            n += 1
    sim.side[c.side]['kredits'] += n


@on('play', P + 'synthetic_oil')
def _synthetic_oil(sim, c, t, k):
    # 下回合多 10 点指挥点并多抽 1 张：只有手里有大牌时多出的指挥点才用得上
    hand = [h for h in sim.side[c.side]['hand'] if h.name != '?']
    big = sum(1 for h in hand if (h.cost or 0) >= 6)
    first = once(sim, 'synthetic_oil')       # 同一回合打第二张：多出的 10 点基本花不完，只算抽牌
    gain(sim, c.side, 0.8 * R.DRAW_V + (min(10, 3.0 * big) if first else 0))


@on('play', P + 'from_the_deep')
def _from_the_deep(sim, c, t, k):
    # 反制：敌方下一个部署的单位直接被消灭。对方指挥点越多，越可能是大单位
    gain(sim, c.side, 1.0 + 0.4 * min(10, sim.side[other(c.side)]['max_kredits']))


card(P + 'buzz_bomb', options=lambda sim, c: _targets(sim, c) + [(sim.side[other(c.side)]['hq'].id, 0)])
card(P + 'old_hares',                  # 友方步兵/坦克本回合 +5 攻（只给还能攻击的）
     play=lambda sim, c, t, k: temp_atk(sim, sim.find(t), 5, c),
     options=lambda sim, c: [(u.id, 0) for u in sim.units(c.side) if u.type in ('infantry', 'tank') and _can_act(sim, u)])
card(P + 'sky_barons', options=lambda sim, c: _targets(sim, c, lambda u: u.type in R.AIR))
card(P + 'wolfpack', options=_targets)
card(P + 'the_alliance', play=lambda sim, c, t, k: [buff(u, 2, 2) for u in sim.units(c.side) if u.faction != 'USA'])
card(P + 'bismarck', play=lambda sim, c, t, k: R.damage(sim, sim.side[other(c.side)]['hq'], 8, c.side),
     options=lambda sim, c: [(sim.side[other(c.side)]['hq'].id, 0)])
card(P + 'reich_research', choose_one=True,
     play=research(P + 'v1_flying_bomb', P + 'expanded_reich_research'))
card(P + 'expanded_reich_research', choose_one=True,
     play=research(P + 'synthetic_oil', P + 'advanced_reich_research'))
card(P + 'advanced_reich_research', choose_one=True,
     play=research(P + 'type_xxi_boat', P + 'uranium_club'))
card(P + 'v1_flying_bomb', play=lambda sim, c, t, k: R.destroy(sim, sim.find(t)) if sim.find(t) else None,
     options=lambda sim, c: _targets(sim, c, lambda u: (u.cost or 0) <= 3))
card(P + 'type_xxi_boat', options=_targets)
card(P + 'fast_heinz', play=lambda sim, c, t, k: [buff(u, 2, 1, sim, c) for u in _german_tanks(sim, c.side)])
card(P + 'tank_wedge', options=lambda sim, c: [(u.id, 0) for u in _german_tanks(sim, c.side)])
card(P + 'suppression_fire', options=_targets)


# ---------- 部署 ----------
@on('deploy', U + 'arado_ar_196')
def _arado(sim, c, t):
    # 实测：友方单位数包含阿拉多自己（两局都是"不算自己时满足、算上就不满足"而没抽到）
    if len(sim.units(c.side)) <= len(sim.units(other(c.side))):
        R.draw(sim, c.side, 1)               # 抽一张指令（按普通抽牌算）
        if c.side == sim.me:
            # 卡组可以给"触发抽牌"额外加分（德国加费：平时捏着，满足条件才放）
            sim.bonus += getattr((sim.ctx or {}).get('plan'), 'ARADO_DRAW_BONUS', 0)


@on('deploy', U + 'henschel_he_129')
def _hs129(sim, c, t):
    x = sim.find(t)
    if x is not None:
        R.fight(sim, c, x, effect=True)    # 效果战斗无视重甲（用户确认，实测装甲列车 7 防被 6 点打到 1）


@on('deploy', U + 'maus')
def _maus(sim, c, t):
    """消灭所有 3 费及以下的单位（双方），每消灭一个对目标造成 2 点伤害（目标在部署时选定，按同一个目标结算）"""
    n = 0
    for u in [u for u in all_units(sim) if u is not c and (u.cost or 0) <= 3]:
        if R.destroy(sim, u):
            n += 1
    x = unit_or_hq(sim, c.side, t)
    if x is not None and n and (x.type == 'location' or x in sim.units(x.side)):
        R.damage(sim, x, 2 * n, c.side)


@on('deploy', U + 'railway_gun_leopold')
def _leopold(sim, c, t):
    e = other(c.side)
    for u in list(sim.units(e)):
        full = len(sim.side[e]['hand']) >= R.HAND_MAX
        R.to_hand(sim, u)
        if not full:
            gain(sim, c.side, -_bounce_value(u))   # 回手不是消灭：对方还能再打出来


card(U + 'henschel_he_129',             # 部署时与一个敌方单位战斗；对地面目标 +2 攻（实测打总部也 +2）
     deploy_targets=lambda sim, c: enemy_targets(sim, c.side, ('support', 'front')),
     dmg_bonus=lambda sim, u, t: 2 if t.type in GROUND + ('location',) else 0)
card(U + 'maus',                        # 伤害目标：敌方总部或敌方费用 > 3 的单位（3 费及以下的会先被消灭）
     deploy_targets=lambda sim, c: [sim.side[other(c.side)]['hq'].id] + [
         i for i in enemy_targets(sim, c.side, ('support', 'front')) if (sim.find(i).cost or 0) > 3])


# ---------- 光环 / 持续效果 ----------
@on('ally_deployed', U + '96_infantry_regiment')
def _96th(sim, u, new):
    R.destroy(sim, u)                       # 我方再部署任何单位，第 96 步兵团被消灭


@on('enemy_destroyed', U + '158_nachschub')
def _158(sim, u, dead):
    # 我方回合敌方单位被消灭：+2 指挥点，每回合一次（只模拟我方回合）
    if u.side == sim.me and once(sim, ('158', u.id)):
        sim.side[u.side]['kredits'] += 2


@on('ally_operated', U + 'blue_legion')
def _blue_legion(sim, u, x, paid):
    buff(x, paid, paid, sim, u)              # 行动后每花 1 点行动费 +1+1


# 第 30 步兵团 / 第 3 装甲掷弹兵团：友方德国单位（含自己，用户确认 2026-10-16）行动后，行动费 -1（永久、最低 0）/ +1+1
@on('ally_operated', U + '30_infantry_regiment')
def _30th(sim, u, x, paid):
    if x.faction == 'Germany' and u.op:
        u.op -= 1


@on('ally_operated', U + '3_panzergrenadier')
def _3pzg(sim, u, x, paid):
    if x.faction == 'Germany':
        buff(u, 1, 1, sim, u)


@on('ally_operated', U + 'panther_a_zimm')
def _zimmerit(sim, u, x, paid):
    # 自己行动后，攻防都 +本局累计行动次数（第 1 次 +1、第 2 次 +2……，用户确认只加攻防）
    if x is u:
        n = sim.op_count.get(u.id, 1)
        buff(u, n, n, sim, u)


@on('atk_raised', U + 'sd_kfz_10_38')
def _sdkfz(sim, u, n):
    # 蓝图 OnAfterChangeAttack：别的牌每提升一次攻击力，再 +1 攻到回合结束（自己这 +1 不再触发）
    temp_atk(sim, u, 1, u)


@on('deploy', U + 'panzer_i_a')
def _panzer_ia(sim, c, t):
    if any(u.type == 'infantry' for u in sim.units(c.side) if u is not c):
        R.draw(sim, c.side, 1)


# 169 掷弹兵：对方每下一道指令，随机弃一张手牌。指令结算后还活着才触发（用这道指令打死它就不弃）。
# 原来没模拟（AI 下指令不知道会弃牌）；现在规划时按抽样算弃掉的牌，AI 会先用攻击/部署清掉它再下指令
# 用户确认：这道指令打死它或压制它都不弃
card(U + '169_grenadiers', enemy_order=lambda sim, u: None if u.pinned else rand_discard(sim, other(u.side)))
card(U + '22_infantry')       # 回合结束我方控制前线就抽 1 张：客户端结算，AI 按 persist 估值


@on('play', P + 'front_and_homeland')
def _front_and_homeland(sim, c, t, k):
    # 牌库里奇数费的德国牌全部 -1 费（牌库不模拟，按“剩余张数 × 抽到的比例 × 每张的价值”估）
    # 第四回合自动抽到这张是客户端的事，AI 只管什么时候打。用最大指挥点当进度，越晚打牌库里剩得越少
    # 实测（对局 797458）：原来每张只算 0.5 分，第 5 回合起一直攥在手里，第 13 回合才打，几乎没用上。
    # 张数、过牌量、每张价值随卡组不同，由卡组给（FH_ODD / FH_DRAWS / FH_V）；缺省是德美加费的数
    plan = sim.ctx.get('plan')
    odd, draws, per = getattr(plan, 'FH_ODD', 14), getattr(plan, 'FH_DRAWS', 18), getattr(plan, 'FH_V', 1.3)
    S = min(14, sim.side[c.side]['max_kredits'])
    left = odd * max(0.0, (14 - S) / 11)          # 4 槽时约 0.9 × odd，13 槽时约 0.1 × odd
    drawn = min(1.0, draws / max(1.0, 39 - 5 - S))
    gain(sim, c.side, per * left * drawn)


@on('stat_bonus', U + 'panzer_iii_e')
def _panzer3(sim, u):
    kinds = {x.type for x in sim.units(u.side) if x.type in NON_TANK}
    return len(kinds), 0
