# 打法：英国 + 美国 “Firewall” 堡垒（指挥部 伦敦：亚历山大港客户端只有新手版）
# 思路：几乎没有单位，赢法是英联邦（我方总部 >= 30 时对敌方总部 20 点 + 抽 4）。整局三件事：
#   1. 不让对面打到总部：防火墙（永久不能打总部）、两难困境（攻击 <-> 行动费互换，主要给敌方）、
#      自由之地 + 两难困境（先把敌方行动费变 0 再互换 -> 攻击 0）、海军力量/蒙蒂/炮击压制、反制、消防局、阿尔斯特挡伤
#   2. 总部堆到 30：海军力量 +3、防御工事 +7、诚挚问候 +6、雷达 +4
#   3. 槽堆到 12：战争债券、战争需要；HX175/租借法案/诚挚问候过牌找英联邦；流星、空军力量补伤害
# 什么时候贴防火墙/两难困境（用户：这套最考验这个）：
#   早期对面只有 1~3 攻的小兵，挨几下没关系（总部还要靠后面的加防堆上去）；贴一张少一张，
#   留给火炮/轰炸机/高攻单位。留牌价值随对面槽数上升（对面越晚下的单位越大），
#   所以前期只有“威胁够大或总部危险”时才贴，中后期攻击 >= 3 就贴
# 卡牌效果在 cards_britain.py / cards_usa.py；这里只放“这套卡组看重什么”
from cards_britain import meteor_value

NAME = 'britain_firewall'
DECK_CODE = '%%25|0B0d0D0E0j0m0w0z191GbPgvj1lryJ;0n0sbuhDtU;080o;losC'
HQ = 'card_location_london'
TITLE = '英美防火墙'
COMMANDER = '大吉岭'
AVATAR = 'avatar_land_girl'             # 土地女孩
MAIN, ALLY = 'Britain', 'usa'

# 堡垒卡组：总部最重要，场面和前线次要（自己几乎不上单位）
W = {'my_hq': 1.3, 'en_hq': 0.8, 'threat': 1.5, 'front': 0.5, 'board': 0.8}
SLOT_R, SLOT_V = 12, 1.5       # 要攒到 12 槽下英联邦：加槽很值
HOLD_FRAC = 0.5
DANGER_DMG = 6
METEOR_V = 0.5
BURN_V = 2.0
NEUTRAL_R = 3.0                # 防火墙/两难困境：一个敌方单位之后大约还活几回合（cards_britain.neutral_v）
FORT_HQ = 30                   # 英联邦的总部门槛

E_, U_ = 'card_event_', 'card_unit_'
METEOR = U_ + 'meteor'
CW = E_ + 'the_commonwealth'


def _e(side):
    return 'left' if side == 'right' else 'right'


def danger(ctx):
    return ctx.get('T', 0) >= DANGER_DMG or ctx.get('T', 0) >= ctx.get('H', 20)


def _en_units(sim, side):
    return sim.units(_e(side))


def _in_hand(sim, side, name):
    return any(h.name == name for h in sim.side[side]['hand'])


def _en_slots(sim, side):
    return sim.side[_e(side)]['max_kredits']


def _neutralizer_hold(base):
    """防火墙/两难困境留在手里的价值：对面槽越多，以后来的单位越大，越值得留着等大的。
    前期（对面 2~4 槽）约 2.4~3.1：只有 2 攻以上、或总部危险时才贴；中期 6 槽以上约 3.9：要 3 攻以上"""
    return lambda sim, c, ctx: base + 0.35 * min(10, _en_slots(sim, c.side)) - (1.5 if danger(ctx) else 0)


def _cw_hold(sim, c, ctx):
    """英联邦：一局只有一张，20 点要打在“打完能斩杀或接近斩杀”的时候"""
    e = sim.side[_e(c.side)]['hq'].df
    return 6.0 + (4.0 if e <= 26 else 0)


def _chain(sim, c, ctx):
    import research_v
    return research_v.chain_hold(sim, c, ctx, hold, allow_option)


def _sweep(base, per=0.6):
    return lambda sim, c, ctx: base + per * len(_en_units(sim, c.side))


HOLD = {
    # 防敌方单位打总部
    E_ + 'firewall': _neutralizer_hold(1.6),
    E_ + 'dilemma': _neutralizer_hold(1.2),
    E_ + 'land_of_the_free': 0.5,
    E_ + 'naval_power': 1.0,
    E_ + 'monty': 1.0,
    E_ + 'shelling': _sweep(1.5, 0.7),
    E_ + 'delaying_tactics': lambda sim, c, ctx: 1.0 + 0.8 * len(sim.side[_e(c.side)]['front']),
    E_ + 'air_power': 1.5,
    E_ + 'raid': 0.6,
    # 反制：挂上后对方回合生效；消防局的价值体现在 planner.threat（挂上后每次伤害按 1 算）
    E_ + 'hms_spectre': 1.2,
    E_ + 'dowding_system': 1.0,
    E_ + 'ultra': 2.0,
    E_ + 'national_fire_service': 0.8,
    # 回血/过牌/加槽：越早越好
    E_ + 'convoy_175': 0.6,
    E_ + 'lend_lease': 1.0,
    E_ + 'sincerely_yours': 1.0,
    E_ + 'fortification': 1.2,
    # 研发链：留牌价值 = 往下能换到的产物价值 - 还要花的研发费用（research_v.chain_hold）；本卡组固定选雷达
    E_ + 'royal_research': lambda sim, c, ctx: _chain(sim, c, ctx),
    E_ + 'expanded_royal_research': lambda sim, c, ctx: _chain(sim, c, ctx),
    E_ + 'radar': 1.2,
    E_ + 'war_bonds': 0.0,
    E_ + 'in_hour_of_need': 0.0,
    E_ + 'plan': 0.4,
    CW: _cw_hold,
    U_ + '85_pioneer_company': 1.0,
    U_ + 'royal_ulster_rifles': 2.0,
}


def allow(sim, c, ctx):
    n = c.name
    my = sim.side[c.side]
    if n == CW:
        # 总部不到 30 只抽 4（12 费抽 4 不划算）：手牌快空、没别的事做时才这样用
        return my['hq'].df >= FORT_HQ or len(my['hand']) <= 2
    if n == METEOR:
        return my['kredits'] >= (c.cost or 0) + (c.op or 0)
    if n == E_ + 'delaying_tactics':
        return bool(sim.side[_e(c.side)]['front'])
    if n in (E_ + 'shelling', E_ + 'monty'):
        return bool(_en_units(sim, c.side))
    if n == E_ + 'raid':
        return len(sim.side[_e(c.side)]['hand']) >= 3
    return True


def allow_attack(sim, u, t):
    """流星要打总部；只有能一击打死目标时才打单位（同流星卡组）"""
    if u.name != METEOR or t is None:
        return True
    return (u.atk or 0) >= (t.df or 0) + (t.armor or 0)


WAIT_FRONT = ('infantry', 'antitank', 'antiair', 'tankdestroyer')


def _worth_handling(sim, u, ctx):
    """这套卡组处理敌方单位的规矩（用户 2026-10-16，只在本卡组生效）：
    1. 已被防火墙或两难困境处理过的不再处理/压制（行动费已经很高，或已经打不了总部）；已被压制的不再压；
    2. 步兵类在支援线时打不到总部，等它上了前线再处理——处理完它就堵在前线，对面别的单位上不来。
       坦克（能移动后攻击）、火炮/飞机（在支援线就能打总部）不用等；总部危险时也不等"""
    if u is None or u.type == 'location' or u.id in sim.neutralized:
        return False
    if u.pinned:
        return False                 # 已被压制（本回合压的或对面回合还压着）：同一单位不叠两种处理
    if u.type in WAIT_FRONT and not (u.loc or '').startswith('front') and not danger(ctx):
        return False
    return True


def allow_option(sim, c, t, k, ctx):
    n = c.name
    if n == E_ + 'royal_research':
        return k == 0                         # 雷达：抽 1 + 总部 +4，正好堆总部
    if n == E_ + 'expanded_royal_research':
        return k == 0
    u = sim.find(t) if t else None
    mine = u is not None and u.side == c.side
    if n == E_ + 'dilemma':
        # 主要给敌方（用户）：换完至少少 2 攻才值一张
        return not mine and _worth_handling(sim, u, ctx) and (u.atk or 0) - (u.op or 0) >= 2
    if n == E_ + 'firewall':
        return not mine and _worth_handling(sim, u, ctx) and not getattr(u, 'no_hq', False) and (u.atk or 0) > 0
    if n == E_ + 'land_of_the_free':
        if mine:
            return (u.op or 0) > 0             # 自己的流星/阿尔斯特：行动费变 0
        # 给敌方：只为同回合接两难困境（行动费 0 再互换 -> 攻击 0）
        return (_in_hand(sim, c.side, E_ + 'dilemma') and _worth_handling(sim, u, ctx)
                and (u.atk or 0) >= 2 and (u.op or 0) > 0)
    if n in (E_ + 'naval_power', E_ + 'monty'):
        # 别重复压制（用户）：处理过的、已压制的、还在支援线的步兵不压；没合适目标就留着
        return _worth_handling(sim, u, ctx) and not u.pinned
    if n == E_ + 'air_power' and k == 1:
        u = sim.find(t)
        # 2 点：打得死的单位，或者对面总部（补刀）
        return u is None or u.type == 'location' or (u.df or 0) <= 2
    return True


def eval_extra(sim, ctx):
    """总部堆到 30 的进度：20 以上每点额外 +0.3；到 30 且手里有英联邦再 +6（没有也 +2，抽到就能用）"""
    me = sim.me
    h = sim.side[me]['hq'].df
    v = 0.3 * max(0, min(h, FORT_HQ) - 20)
    if h >= FORT_HQ:
        v += 6.0 if _in_hand(sim, me, CW) else 2.0
    return v


def hold(sim, c, ctx):
    n = c.name
    if n == METEOR:
        return 0.5 * meteor_value(sim, c.side, 2 * (c.atk or 0), 2 * (c.df or 0)) + 0.3 * (c.atk or 0)
    h = HOLD.get(n)
    if h is not None:
        return h(sim, c, ctx) if callable(h) else h
    if c.type == 'order':
        return 0.3 * (c.cost or 0)
    return HOLD_FRAC * (0.5 * (c.atk or 0) + 0.5 * (c.df or 0) + persist(sim, c, ctx))


def persist(sim, u, ctx):
    n = u.name
    if n == METEOR:
        return -0.5 * ((u.atk or 0) + (u.df or 0)) - 1.0
    if n == U_ + '85_pioneer_company':
        return 0.8 * min(ctx.get('R', 6), 4)     # 这套全是指令：每回合省 1 费
    if n == U_ + 'royal_ulster_rifles':
        return 0.5 * max(0, u.df or 0)           # 替总部挡伤：防御就是总部的“备用血”
    return 0.0


KEEP = {E_ + 'naval_power', E_ + 'dilemma', E_ + 'firewall', E_ + 'convoy_175', U_ + '85_pioneer_company',
        E_ + 'war_bonds', E_ + 'in_hour_of_need', U_ + 'royal_ulster_rifles', E_ + 'raid'}


def keep(name, cost):
    """起手调度：留 1~2 费的防守牌、过牌、加槽、先锋连和阿尔斯特；英联邦和大牌换掉"""
    return name in KEEP
