# 回合规划：在模拟器里搜索本回合的出牌/行动序列，挑终局评分最高的那条，只返回第一步
# 每走一步 live_driver 都会重读真实场面再规划，所以模拟误差不会累积
import re, time, random
import sim_rules as R
from sim import Sim, other, UNKNOWN, card_db
from live_ai import guarded, GROUND

BEAM = 10              # 每层保留的局面数
DEPTH = 10             # 一回合最多搜几步
SAMPLES = 4            # 随机效果的抽样次数
TIME_LIMIT = 2.5       # 每次规划的时间上限（秒）
MIN_GAIN = 0.3         # 比“直接结束回合”至少好这么多才出手
WIN = 1e6


# ---------- 估值 ----------
# 敌方“特殊单位”：攻防不高但持续起作用（每回合触发、光环、改规则、打乱手牌），
# 模拟器多半不结算这些效果，场面分只按攻防算会低估它们，清场时排不上号（用户指出：169 掷弹兵、
# 各种奋战火炮/飞机、回合开始/结束送牌加攻的单位）。按卡面文字给一个“早清早好”的额外分
_ENGINE_PATS = [
    (2.0, r'after giving an order|discards? a card|must discard'),             # 打乱手牌（下指令就弃牌等）
    (1.5, r'at the (start|end) of (your|each|every) turn'),                   # 每回合持续触发
    (1.5, r'(other )?friendly (units|infantry|tanks|fighters|bombers|artillery)[^.]{0,30}(have|get|gain)'
          r'|your (units|tanks|infantry|orders)[^.]{0,15}(have|get|cost)'),   # 光环
    (1.2, r'when(ever)? (you|your opponent|the enemy) (play|deploy|give|draw)'),  # 随对方出牌触发
    (1.0, r'costs? \d+ less|cost[^.]{0,20}reduc'),                            # 降费
    (1.0, r"can't be targeted|immune|cannot be (attacked|targeted)"),        # 改规则
    (0.8, r'when(ever)? (this unit|a friendly unit)[^.]{0,25}(is damaged|is attacked|destroys|attacks)'),
    (1.0, r'(gets?|gains?) \+\d[^.]{0,40}(when|each time|the first time|for each)|the first (unit|order)[^.]{0,20}each turn'),
    (0.8, r'\bcovert\b|\breveal:'),                                          # 隐蔽/揭示：故意藏着的单位
    # 1 费 0/4 的通信兵/补给兵一类（用户指出：持续增益但每次很小，攻防上看不出来）
    (1.5, r'when (another|a) friendly unit is destroyed|when an enemy unit is destroyed'),
    (1.5, r'damage dealt to your hq is reduced|your hq (gains|gets)'),
    (1.0, r'gain \d+ kredits?|once per turn'),
]
_engine_cache = {}


def enemy_engine_v(u):
    """敌方单位的额外清除价值（不含攻防）：持续效果 + 奋战/无视守护等难挡的输出"""
    v = _engine_cache.get(u.name)
    if v is None:
        t = ((card_db.get(u.name) or {}).get('text') or '').lower()
        v = min(3.5, sum(w for w, p in _ENGINE_PATS if re.search(p, t)))
        _engine_cache[u.name] = v
    atk = max(0, u.atk or 0)
    if u.fury and u.type in ('artillery', 'bomber', 'fighter'):
        v += 0.5 * atk                     # 奋战的火炮/飞机：一回合两次，守护挡不住（火炮/轰炸机）
    elif u.fury and (u.loc or '').startswith('front'):
        v += 0.3 * atk                     # 前线奋战单位
    if u.type == 'artillery' and atk >= 4:
        v += 0.3 * atk                     # 大口径火炮：每回合直接打总部或后排，守护挡不住
    return v


def unit_value(sim, u, plan, ctx):
    if u.side == sim.me and u.name in getattr(plan, 'EPHEMERAL', ()):
        return 0.0                         # 回合结束就会消失的单位（如方面军的 T-34）：留着没价值
    atk = (u.atk or 0) - sim.temp.get(u.id, 0)   # 只到回合结束的攻击加成不算持续价值
    v = 0.5 * atk + 0.5 * max(0, u.df or 0)
    v += (1.0 if u.guard else 0) + (1.0 if u.ambush else 0) + (1.0 if u.smoke else 0)
    v += (u.armor or 0) + (0.5 * atk if u.fury else 0)
    if u.side == sim.me:
        v += plan.persist(sim, u, ctx)
    else:
        v += 0.3 * atk                     # 敌方单位的攻击力是威胁，清掉它额外有价值
        if not u.pinned and u.id not in sim.silenced:
            v += enemy_engine_v(u)         # 被压制的暂时不起作用、被抑制的特效没了，不加
    return v


def hq_value(h):
    """指挥部血量价值：越接近 0 每点越值钱"""
    h = max(0, h)
    return h * 1.0 if h <= 10 else 10 + (h - 10) * 0.5


_HQ_DMG = re.compile(r'deal (\d+) damage to (?:the )?(?:enemy hq|all enem(?:ies|y targets)|all targets|'
                     r'an? (?:enemy )?target|the enemy headquarters)')


def threat(sim):
    """估计敌方下回合最多能对我方指挥部造成的伤害"""
    me, e = sim.me, other(sim.me)
    my, en = sim.side[me], sim.side[e]
    hq = my['hq']
    unit_ok = not hq.smoke                   # 指挥部烟幕：单位打不到
    hq_guarded = 'HQ' in guarded(my['support'], hq)
    front_free = not my['front']
    red = sim.count(me, 'card_unit_seahawk') + sim.count(me, 'card_unit_us_signal_corps')
    opts = []                                # [(伤害, 指挥点)]
    if unit_ok:
        for u in sim.units(e):
            if u.pinned or u.cant_attack or not u.atk or getattr(u, 'no_hq', False):
                continue                     # no_hq：被防火墙贴过，永久不能攻击指挥部
            if sim.temp.get(u.id):
                # 本回合内的攻击加成（热浪给敌方也加了）下回合就没了：按去掉加成后的攻击算
                u = u.copy()
                u.atk -= sim.temp[u.id]
                if u.atk <= 0:
                    continue
            hits = 2 if u.fury else 1
            if u.type in ('artillery', 'bomber'):
                opts.append((u.atk, u.op or 0, hits))
            elif hq_guarded:
                continue
            elif u.type == 'fighter' or u.loc == 'front':
                opts.append((u.atk, u.op or 0, hits))
            elif u.type in GROUND and front_free and (u.type == 'tank' or u.move_and_attack):
                opts.append((u.atk, 2 * (u.op or 0), hits))
        for c in en['hand']:
            if c.name == UNKNOWN or not c.blitz or not c.atk:
                continue
            if c.type in ('artillery', 'bomber') or (c.type == 'fighter' and not hq_guarded):
                opts.append((c.atk, (c.cost or 0) + (c.op or 0), 1))
            elif c.type == 'tank' and front_free and not hq_guarded:
                opts.append((c.atk, (c.cost or 0) + 2 * (c.op or 0), 1))
    order_opts = []
    for c in en['hand']:
        if c.type == 'order':
            m = _HQ_DMG.search(((card_db.get(c.name) or {}).get('text') or '').lower())
            if m:
                opts.append((int(m.group(1)), c.cost or 0, 1))
                order_opts.append(opts[-1])
    budget = min(24, en['max_kredits'] + (1 if en['max_kredits'] < 12 else 0))
    # 国家消防局（挂着的反制）：对方回合总部每次受到的伤害降到 1
    nfs = 'card_event_national_fire_service' in getattr(sim, 'cm_names', ())
    total, unit_hits = 0, []
    for dmg, cost, hits in sorted(opts, key=lambda x: -x[0] * x[2] / max(1, x[1])):
        if cost <= budget:
            budget -= cost
            d = max(0, dmg - red)
            total += (min(1, d) if nfs else d) * hits
            if (dmg, cost, hits) not in order_opts:
                unit_hits.append(min(1, d) if nfs else d)
    # 反袭（挂着的反制）：第一个打总部的单位在结算前被消灭。对方不知道是哪张反制，按“最小的那一下被吃掉”算
    if 'card_event_counter_strike' in getattr(sim, 'cm_names', ()) and unit_hits:
        total -= min(unit_hits)
    # 皇家阿尔斯特步枪兵团：总部受到的伤害改由它承受，它的防御先挡掉一部分
    shield = sum(max(0, u.df or 0) for u in sim.units(me) if u.name == 'card_unit_royal_ulster_rifles')
    total = max(0, total - shield)
    if any(u.name == 'card_unit_m26_pershing' for u in my['front']):
        total = min(total, max(0, hq.df - 1))
    return total


def evaluate(sim, plan, ctx):
    """局面评分（站在 me 一方，假设此刻结束回合）"""
    me, e = sim.me, other(sim.me)
    my, en = sim.side[me], sim.side[e]
    if en['hq'].df <= 0:
        return WIN - sim.n_actions
    if my['hq'].df <= 0:
        return -WIN
    W = plan.W
    v = W['board'] * (sum(unit_value(sim, u, plan, ctx) for u in sim.units(me))
                      - sum(unit_value(sim, u, plan, ctx) for u in sim.units(e)))
    v += W['my_hq'] * hq_value(my['hq'].df) - W['en_hq'] * hq_value(en['hq'].df)
    H, T = my['hq'].df, threat(sim)
    left = H - T                                # 敌方下回合打完后我方指挥部剩多少
    if left <= 0:
        v -= W['threat'] * (30 + 2 * (T - H))   # 下回合可能被斩杀
    else:
        # 打完后血越少罚得越狠：剩 1 血约 -13，剩 5 血约 -3，剩 10 血以上几乎不罚
        v -= W['threat'] * (T / H * 2 + 12 / (left + 1) ** 1.2 * min(1, T / 4))
    # 本回合结束就会被弃掉的手牌（长久围困抽的牌，到期那回合）：留着没价值，能打就打
    v += sum(plan.hold(sim, c, ctx) for c in my['hand'] if c.name != UNKNOWN and c.id not in sim.expiring)
    # 下回合开始要抽几张：自然抽 1 + 战争债券这类额外抽牌（原来只按 1 张算，满 8 张打债券看不出下回合会爆）
    over = 1 + getattr(sim, 'extra_draw', 0) - R.hand_room(sim, me)
    if over > 0:
        # 每爆一张：白丢一张牌（DRAW_V）再加一点余量，
        # 让 AI 在满手还剩指挥点时，倾向于先打掉一张留着价值最低的便宜牌
        v -= over * (R.DRAW_V + 0.5 + getattr(plan, 'BURN_V', 1.0))
    v += W['front'] * ((1 if my['front'] else 0) - (1 if en['front'] else 0))
    extra = getattr(plan, 'eval_extra', None)   # 卡组自己的局面项（如防火墙卡组：总部堆到 30 才能英联邦）
    if extra is not None:
        v += extra(sim, ctx)
    return v + sim.bonus - 0.05 * sim.n_actions


def make_ctx(sim, plan):
    my, en = sim.side[sim.me], sim.side[other(sim.me)]
    H, E = my['hq'].df, en['hq'].df
    R_ = max(3, min(10, min(H, E) / 2.5))
    ctx = {'H': H, 'E': E, 'S': my['max_kredits'], 'R': R_, 'deck_units': 6,
           # 加槽估值：卡组可以给更长的时间跨度（加费卡组对局拖得长）和更高的指挥点价值
           # 时间跨度随对局进程缩短（用槽数当进度：6 槽以后每多 1 槽少算 1 回合），
           # 否则后期 12 槽以上的“永久加槽”会被高估（实测：后期没压力时研发选了深水炸弹）
           'R_slot': max(3, getattr(plan, 'SLOT_R', 8) - max(0, my['max_kredits'] - 6)),
           'slot_v': getattr(plan, 'SLOT_V', 0.8)}
    sim.ctx = ctx
    ctx['plan'] = plan
    ctx['T'] = threat(sim)
    ctx['P'] = ctx['T'] / max(1, H)
    return ctx


# ---------- 搜索 ----------
def _outcomes(node, act):
    c = node.clone()
    R.apply(c, act)
    if not c.random_used:
        return [c], False
    outs = [c]
    for s in range(1, SAMPLES):
        c2 = node.clone(random.Random(s))
        R.apply(c2, act)
        outs.append(c2)
    return outs, True


def _greedy(sim, plan, ctx, steps=2):
    """随机效果之后的局面：贪心再走几步估值（不再展开随机分支）"""
    val = evaluate(sim, plan, ctx)
    for _ in range(steps):
        best = None
        for a in R.legal(sim):
            c = sim.clone(random.Random(7))
            R.apply(c, a)
            v = evaluate(c, plan, ctx)
            if v > val + 1e-9:
                best, val = c, v
        if best is None:
            break
        sim = best
    return val


def _sig(sim):
    us = tuple(sorted((u.id, u.atk, u.df, u.loc, u.smoke, u.id in sim.moved, sim.attacks.get(u.id, 0))
                      for s in ('left', 'right') for u in sim.units(s)))
    return (us, tuple(sorted(c.name for c in sim.side[sim.me]['hand'])),
            sim.side['left']['hq'].df, sim.side['right']['hq'].df, sim.side[sim.me]['kredits'], round(sim.bonus, 2))


def search(root, plan, ctx, deadline):
    """返回 (最佳第一步 或 None, 最佳评分, 直接结束回合的评分)"""
    base = evaluate(root, plan, ctx)
    best_v, best_a = base + MIN_GAIN, None
    frontier = [(base, root, None)]
    for depth in range(DEPTH):
        nxt = {}
        for _, node, first in frontier:
            for a in R.legal(node):
                if depth > 0 and time.time() > deadline:
                    break
                outs, rnd = _outcomes(node, a)
                fa = first or a
                if rnd:
                    v = sum(_greedy(o, plan, ctx) for o in outs) / len(outs)
                    if v > best_v:
                        best_v, best_a = v, fa
                    continue
                c = outs[0]
                v = evaluate(c, plan, ctx)
                if v > best_v:
                    best_v, best_a = v, fa
                k = _sig(c)
                if k not in nxt or nxt[k][0] < v:
                    nxt[k] = (v, c, fa)
        if not nxt or time.time() > deadline:
            break
        frontier = sorted(nxt.values(), key=lambda x: -x[0])[:BEAM]
    return best_a, best_v, base


def plan_turn(st, me, tlog, plan, time_limit=TIME_LIMIT):
    sim = Sim(st, me, tlog)
    ctx = make_ctx(sim, plan)
    return search(sim, plan, ctx, time.time() + time_limit) + (ctx,)
