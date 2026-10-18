# 芬兰（盟国）的牌
# 结算细则（用户确认 2026-10-16）：洛塔组织只影响打出时在场的单位，永久，行动费最低 0；
# 长久围困只弃这 4 张，弃牌在“下个友方回合结束时”（本回合打 -> 敌方回合 -> 我方回合结束时弃）
import sim_rules as R
from effects import P, on, buff


@on('play', P + 'lotta_svard')
def _lotta(sim, c, t, k):
    for u in sim.units(c.side):
        buff(u, 0, 1)
        if u.op:
            u.op -= 1


@on('play', P + 'prolonged_siege')
def _siege(sim, c, t, k):
    """抽 4 张，这两回合（本回合剩下的 + 下回合）打不出去的会被弃掉。
    模拟里抽到的是未知牌、本回合打不了，按“两回合的指挥点能打出几张”折算：打不出的那几张不算抽牌价值。
    卡组平均每张牌的花费给 SIEGE_AVG（缺省 2.5）"""
    my = sim.side[c.side]
    R.draw(sim, c.side, 4)
    if c.side != sim.me:
        return
    avg = getattr(sim.ctx.get('plan'), 'SIEGE_AVG', 2.5)
    # 手里已知的牌也要花指挥点：先扣掉，剩下的才轮到这 4 张
    known = sum(h.cost or 0 for h in my['hand'] if h.name != R.UNKNOWN and h.cost is not None and h.cost < 20)
    budget = max(0, my['kredits'] + min(24, my['max_kredits'] + 1) - known)
    usable = max(0.0, min(4.0, budget / max(0.5, avg)))
    sim.bonus -= R.DRAW_V * (4 - usable)
