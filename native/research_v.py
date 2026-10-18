# 研发链的留牌价值（各国研发通用的算法；每层选什么、产物值多少由各卡组自己的 hold / allow_option 决定）
# 原来每层研发的留牌价值是拍的固定数（如苏联扩展研发 6.0、高级研发 6.0），打出去换下一层评分不变，
# AI 从不往下推研发；终点产物（倾斜装甲、斯大林管风琴……）的实际用处也没进估值。
# 现在：一层研发值 = max(这一层两个选项最终能换到的价值) - 还要再花的研发费用 × β。
#   “还要再花”只算后面几层研发本身（终点产物的费用已在卡组给它的 hold 里体现）；
#   每推进一层都会少一截要花的费用，所以只要终点值得，推进本身就有正收益——
#   但收益不到“花同样指挥点下单位”，所以有闲费时才推，不和正事抢费用
import effects
from sim import SC

BETA = 0.25          # 每 1 点研发费用折掉多少分（研发费用 = 不能拿去下单位的指挥点）
FLOOR = 0.3


def big_hitter(sim, side, need=None):
    """我方有没有“马上就能对敌方总部造成大伤害”的单位（氧气鱼雷这类 0 费解场牌留着就是为了给它清路）：
    本回合还能攻击、攻击 >= need（默认 min(6, 敌方总部血量)）"""
    from sim import other
    e_hq = sim.side[other(side)]['hq'].df
    need = min(6, e_hq) if need is None else need
    kr = sim.side[side]['kredits']
    for u in sim.units(side):
        if u.pinned or u.cant_attack or u.op is None or u.op > kr:
            continue
        if u.id in sim.deployed and not u.blitz:
            continue
        if (u.atk or 0) >= need:
            return True
    return False


def manhattan_v(sim, side, ctx):
    """曼哈顿计划（6 费：所有敌方单位和指挥部受 6 点伤害）一张的留牌价值：
    按能打死的敌方单位数加权（每个 +1.2，最多算 5 个），对面总部 <= 6 一张斩杀、<= 12 两张斩杀再加"""
    from sim import other
    en = sim.units(other(side))
    kills = sum(1 for u in en if not getattr(u, 'immune', False) and (u.df or 0) <= 6)
    hurt = sum(1 for u in en if (u.df or 0) > 6)                    # 打不死的也掉 6 血
    E = ctx['E']
    lethal = 4.0 if E <= 6 else (2.0 if E <= 12 else 0.0)
    return 1.5 + 1.2 * min(5, kills) + 0.4 * min(3, hurt) + lethal


def penicillin_v(sim, side, ctx):
    """青霉素（0 费：我方单位和指挥部 +6 防、抽 4）的留牌价值：手牌越少越值（快没牌时 +3），
    总部 <= 10 再 +2；牌库快空时抽 4 会吃疲惫，按能抽到的张数打折"""
    hand = len(sim.side[side]['hand'])
    v = 1.5 + 0.5 * max(0, 5 - hand) + (3.0 if hand <= 2 else 0.0) + (2.0 if ctx['H'] <= 10 else 0.0)
    n = sim.deck_n.get(side)
    if n is not None and n < 4:
        v -= 1.0 * (4 - n)
    return v


def _tmp(name, side):
    c = SC.new(name, side, 0, 'hand_' + side)
    return c


def chain_hold(sim, c, ctx, hold, allow_option=None, _depth=0):
    """研发牌 c 留在手里的价值。hold = 卡组的 hold(sim, card, ctx)（用来估终点产物）；
    allow_option = 卡组的选项限制（只在允许的选项里取最优）"""
    f = effects.hook(c.name, 'play')
    prods = getattr(f, 'products', None)
    if not prods or _depth > 3:
        return FLOOR
    best = None
    for k, (name, n) in enumerate(prods):
        if allow_option is not None and not allow_option(sim, c, 0, k, ctx):
            continue
        x = _tmp(name, c.side)
        if getattr(effects.hook(name, 'play'), 'products', None):
            v = chain_hold(sim, x, ctx, hold, allow_option, _depth + 1)   # 下一层还是研发
        else:
            v = n * hold(sim, x, ctx)
        best = v if best is None else max(best, v)
    if best is None:
        return FLOOR
    # 留着 = 产物价值 - 把它打出去还要花的费用 × β：打出这一层的收益恰好是 β × 它的费用（> 0），有闲费就推。
    # 不截底（截底会让上一层的“推进收益”消失）；整体很低时，和其他牌比自然排在后面
    return best - BETA * (c.cost or 0)
