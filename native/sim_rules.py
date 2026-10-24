# 模拟器规则：合法动作、动作结算、伤害/消灭/撤退/抽牌等基本操作
# 规则与 live_ai.gen_actions / combat 保持一致（测试会核对两边生成的动作）
from sim import SC, HAND_MAX, UNKNOWN, slot_value, other, SUPPORT_MAX, FRONT_MAX
from live_ai import GROUND, RANGED, attack_targets, worth_attacking
import effects
import card_rules

UNIT_TYPES = GROUND + RANGED
DRAW_V = 2.0           # 抽 1 张牌的价值（手牌不超上限时）


# ---------- 基本操作 ----------
def place(sim, side, u, line):
    """把单位放到 side 的 line（'support' / 'front'），格子号取该线最大号 + 1"""
    d = sim.side[side]
    cells = d[line] + ([d['hq']] if line == 'support' else [])
    u.slot = max([c.slot for c in cells if c.slot is not None] or [-1]) + 1
    u.loc = 'front' if line == 'front' else 'support_' + side
    u.side = side
    d[line].append(u)


def damage(sim, t, n, src_side, by_unit=False, pierce=False):
    """对 t（单位或指挥部）造成 n 点伤害；减伤（海鹰、通信连、重甲）和总部保底（潘兴）走卡牌钩子。
    pierce=True：卡牌效果触发的战斗，无视重甲（用户确认）"""
    n = max(0, n - effects.damage_reduction(sim, t, src_side, by_unit, pierce))
    if n == 0:
        return 0
    if t.type == 'location':
        # 皇家阿尔斯特步枪兵团：友方总部受到的伤害改由它承受（它死了多出来的不回到总部）
        s = next((u for u in sim.units(t.side) if effects.uhook(sim, u, 'shield_hq')), None)
        if s is not None:
            s.df -= n
            if s.df <= 0:
                destroy(sim, s)
            return n
    t.df -= n
    if t.type == 'location':
        if t.df < 1 and effects.hq_floor(sim, t.side):
            t.df = 1
    elif t.df <= 0:
        destroy(sim, t)
    return n


def destroy(sim, u, removed=False):
    """消灭（removed=True 为“移除”：不算消灭，不触发亡计）"""
    d = sim.side[u.side]
    for line in ('support', 'front'):
        if u in d[line]:
            d[line].remove(u)
            if not removed:
                effects.on_destroy(sim, u)
            return True
    return False


def retreat(sim, u):
    """前线单位撤退到支援线；支援线满则回到拥有者手牌（实测 765012：拖延战术把 3 个单位退回玩家手牌，
    原来按“移除”算，模拟以为对面单位没了；手牌也满则丢弃）。回手 = 状态全部刷新（防火墙/两难困境白贴），
    对方还能重新打出来：给拥有者记一半单位价值（同 cards_germany._bounce_value）"""
    d = sim.side[u.side]
    if u not in d['front']:
        return
    d['front'].remove(u)
    room = SUPPORT_MAX - len(d['support']) - (sim.extra_sup if u.side == sim.me else 0)
    if room > 0:
        place(sim, u.side, u, 'support')
        return
    sim.temp.pop(u.id, None)
    h = add_hand(sim, u.side, u.name, cid=u.id)
    if h is not None:
        # 按卡面数值算（场上被两难困境换成 0 攻的，回手后攻击也恢复了）
        effects.gain(sim, u.side, 0.25 * ((h.atk or 0) + (h.df or 0)) + 0.2 * (h.cost or 0))
    else:
        effects.on_removed(sim, u)


def hand_room(sim, side):
    """side 手牌还能放几张。实测：埋下没触发的反制卡仍占手牌位置（快照里滤掉了，记在 sim.hand_extra）"""
    return HAND_MAX - len(sim.side[side]['hand']) - (sim.hand_extra if side == sim.me else 0)


def fatigue(sim, side):
    """疲惫伤害（Kards规则.txt）：牌库空了还要抽 / 协力不满足时受到，1、2、3……等差递增，两者共用一个计数"""
    k = sim.fatigue.get(side, 0) + 1
    sim.fatigue = dict(sim.fatigue, **{side: k})
    hq = sim.side[side]['hq']
    hq.df -= k
    if hq.df < 1 and effects.hq_floor(sim, side):
        hq.df = 1
    return k


def draw(sim, side, n=1):
    """抽 n 张未知牌；超过手牌上限的丢弃。每抽 1 张都触发抽牌联动（甜心、KV-1 1941、近卫 4 团等）。
    牌库张数已知（sim.deck_n，驱动估算）且抽空时改为受疲惫伤害。
    卡组可给对方抽牌估值：ENEMY_DRAW_V（对方抽到一张）、ENEMY_BURN_V（对方爆掉一张）；缺省都是 0（旧行为）"""
    d = sim.side[side]
    plan = sim.ctx.get('plan')
    for _ in range(n):
        left = sim.deck_n.get(side)
        if left is not None:
            if left <= 0:
                fatigue(sim, side)
                continue
            sim.deck_n = dict(sim.deck_n, **{side: left - 1})
        effects.on_draw(sim, side)
        if hand_room(sim, side) <= 0:
            sim.burned = dict(sim.burned, **{side: sim.burned.get(side, 0) + 1})
            if side == sim.me:
                # 爆牌：白白丢一张。卡组可用 BURN_V 加重（流星卡组：丢掉的可能就是流星）
                sim.bonus -= getattr(plan, 'BURN_V', 1.0)
            else:
                sim.bonus += getattr(plan, 'ENEMY_BURN_V', 0.0)
            continue
        d['hand'].append(SC.new(UNKNOWN, side, sim.new_id(), 'hand_' + side))
        if side == sim.me:
            sim.bonus += DRAW_V
        else:
            sim.bonus -= getattr(plan, 'ENEMY_DRAW_V', 0.0)


def add_deck(sim, side, n):
    """往 side 的牌库塞 n 张牌（最后的仪式、解放的抵抗……）：牌库张数已知时跟着加，驱动跨回合累计"""
    if sim.deck_n.get(side) is not None:
        sim.deck_n = dict(sim.deck_n, **{side: sim.deck_n[side] + n})
    sim.deck_add = dict(sim.deck_add, **{side: sim.deck_add.get(side, 0) + n})


def to_hand(sim, u):
    """场上单位回到拥有者手牌（同一张牌，数值按卡面重置；手牌满则丢弃）。不算消灭，不触发亡计"""
    d = sim.side[u.side]
    for line in ('support', 'front'):
        if u in d[line]:
            d[line].remove(u)
            sim.temp.pop(u.id, None)
            return add_hand(sim, u.side, u.name, cid=u.id)
    return None


def add_hand(sim, side, name, cid=None):
    """手牌加一张牌（满了就丢弃）；cid = 回手的原卡 id（不给则是新生成的牌）"""
    d = sim.side[side]
    if hand_room(sim, side) <= 0:
        if side == sim.me:
            # 我方手牌满了还往手里加牌（护航给的生产/计划等）：这张直接丢掉。
            # 原来不计代价，满手时打护航之类的牌看起来“白赚”（用户 2026-10-19：英国卡组满手还打护航）
            plan = sim.ctx.get('plan')
            sim.bonus -= getattr(plan, 'BURN_V', 1.0)
        return None
    c = SC.new(name, side, sim.new_id() if cid is None else cid, 'hand_' + side)
    d['hand'].append(c)
    return c


def gain_slot(sim, side, n=1):
    d = sim.side[side]
    S = d['max_kredits']
    d['max_kredits'] = max(0, min(24, S + n))
    v = slot_value(S, n, sim.ctx.get('R_slot', 8), sim.ctx.get('slot_v', 0.8))
    sim.bonus += v if side == sim.me else -v


# ---------- 合法动作 ----------
def legal(sim):
    """me 方当前可做的全部动作：
    ('deploy', 卡, 目标id, 0) / ('play', 卡, 目标id, 抉择序号) / ('move', 单位) / ('attack', 单位, 目标或None)"""
    me = sim.me
    my = sim.side[me]
    kr = my['kredits']
    acts = []
    if sim.turn_over:
        return acts                      # 回合已被效果结束
    plan = sim.ctx.get('plan')
    for c in my['hand']:
        if c.name == UNKNOWN or c.cost is None or effects.cost(sim, c) > kr:
            continue
        if c.type in UNIT_TYPES:
            if plan is not None and hasattr(plan, 'allow') and not plan.allow(sim, c, sim.ctx):
                continue
            if sim.sup_count() < SUPPORT_MAX and not sim.no_deploy:
                # 部署二选一的单位（游骑兵）才过卡组的 allow_option；其余部署照旧（别的卡组的 allow_option 没写部署）
                opt_ok = getattr(plan, 'allow_option', None) if effects.hook(c.name, 'deploy_choose_one') else None
                for t, k in effects.deploy_options(sim, c):
                    if opt_ok is None or opt_ok(sim, c, t, k, sim.ctx):
                        acts.append(('deploy', c, t, k))
        elif c.type == 'order':          # 反制卡在 SC 里已归为 order
            if plan is not None and hasattr(plan, 'allow') and not plan.allow(sim, c, sim.ctx):
                continue
            if card_rules.order_limit_hit(sim, sim.played):
                continue                         # 第 60 骑兵团：每回合只能下一个指令
            if getattr(c, 'counter', False) and c.name in sim.cm_names:
                continue                         # 同名反制已经挂着：不重复埋（不同反制可以同时挂）
            if sim.weather_played and effects.is_weather(c.name):
                continue                         # 每回合只能打一张天气牌（用户确认）
            opt_ok = getattr(plan, 'allow_option', None)
            for t, k in effects.play_options(sim, c) or ():
                if opt_ok is None or opt_ok(sim, c, t, k, sim.ctx):
                    acts.append(('play', c, t, k))
    en_front = sim.side[other(me)]['front']
    n_front = len(my['front']) + sim.extra_front
    f_max = card_rules.front_max(sim, FRONT_MAX)
    for u in my['support'] + my['front']:
        free = u.id in sim.free                  # 永先者团：本回合免费行动一次（不花行动费、不受部署限制）
        if u.pinned or u.cant_attack is None or u.op is None or (u.op > kr and not free):
            continue
        if u.id in sim.deployed and not u.blitz and not free:
            continue
        # 规则同 live_ai.gen_actions：坦克攻击后仍可移动，其他单位攻击后不能再动
        n_att = sim.attacks.get(u.id, 0)
        att_left = n_att < (2 if u.fury else 1)
        if not att_left and not (u.type == 'tank' and u.id not in sim.moved):
            continue
        moved = u.id in sim.moved
        if (not moved and u.loc.startswith('support') and u.type in GROUND and not en_front
                and n_front < f_max and not sim['front_full'] and (n_att == 0 or u.type == 'tank')
                and not card_rules.cant_move(u.name)):
            am = getattr(plan, 'allow_move', None)
            if am is None or am(sim, u):         # 打法层禁止的上前线（如引擎单位不去前线送死）
                acts.append(('move', u))
        if att_left and (not moved or u.move_and_attack or u.type == 'tank') and not u.cant_attack \
                and not card_rules.cant_attack(u.name) and not card_rules.attack_blocked(sim, u):
            aa = getattr(plan, 'allow_attack', None)
            for t in attack_targets(sim, me, u):
                # 不打 BM-13N 这类打了白打的目标；卡面写着不能攻击敌方指挥部的不打指挥部
                if aa is not None and not aa(sim, u, t):
                    continue                     # 打法层禁止的攻击（如流星不去撞打不死的单位）
                if worth_attacking(t) and (t is not None or (card_rules.can_attack_hq(sim, me, u, u.id in sim.deployed)
                                                             and not getattr(u, 'no_hq', False))):
                    acts.append(('attack', u, t))
    return acts


# ---------- 结算 ----------
def apply(sim, act):
    """在 sim 上就地执行动作（act 里的卡可以来自别的副本，按 id 找回本副本里的卡）"""
    me, kind = sim.me, act[0]
    my = sim.side[me]
    c = sim.find(act[1].id)
    sim.n_actions += 1
    if kind in ('deploy', 'play'):
        i = my['hand'].index(c)
        sim.play_left, sim.play_right = i == 0, i == len(my['hand']) - 1   # 手牌顺序 = 快照顺序，新牌在最右
        cost = effects.cost(sim, c)
        my['hand'].remove(c)
        my['kredits'] -= cost
        if kind == 'deploy':
            place(sim, me, c, 'support')
            sim.deployed.add(c.id)
            sim.deploys += 1             # 本回合第几个部署的单位（第 5 胸甲骑兵团）
            c.stat_b = (0, 0)            # 手里的卡面数值不含场上加成
            effects.on_deploy(sim, c, act[2], act[3] if len(act) > 3 else 0)
        else:
            sim.played += 1
            if sim.played == 1 and sim.count(me, 'card_unit_85_pioneer_company'):
                # 第 85 先锋连：本回合第一张指令 -1 费。快照里手牌指令的费用已含这 -1（未实机核对），
                # 第一张打出后其余指令恢复原价
                for h in my['hand']:
                    if h.type == 'order' and h.cost is not None and h.cost < 20:
                        h.cost += 1
            if getattr(c, 'counter', False):
                sim.cm_names.add(c.name)
                sim.hand_extra += 1      # 埋下的反制卡在触发前仍占手牌位置
            if effects.is_weather(c.name):
                sim.weather_played = True
            effects.on_play(sim, c, act[2], act[3])
            effects.on_ally_order(sim, me)
        if getattr(c, 'intel', 0):
            effects.on_intel(sim, me, c)   # 情报牌：效果结算后触发“友方使用情报牌时”（军团/塔尔努夫/雷兵团）
        for _ in range(getattr(c, 'corps', 0) or 0):
            effects.rand_kill(sim, me)   # 军司令部附加的“打出时随机消灭一个敌方单位”
        effects.refresh_stats(sim)
        return
    paid = c.op or 0
    if c.id in sim.free:
        sim.free = sim.free - {c.id}     # 免费行动一次：不扣指挥点（paid 仍按行动费算，密歇根照样触发，用户确认）
    else:
        my['kredits'] -= paid
    c.smoke = False                      # 移动或战斗后失去烟幕
    if kind == 'move':
        my['support'].remove(c)
        place(sim, me, c, 'front')
        sim.moved.add(c.id)
    else:
        t = act[2]
        t = sim.side[other(me)]['hq'] if t is None else sim.find(t.id)
        sim.attacks[c.id] = sim.attacks.get(c.id, 0) + 1
        if t is not None and t.type == 'location' and effects.enemy_counter(sim, me, effects.COUNTER_STRIKE):
            destroy(sim, c)              # 对方埋了反袭：打总部的单位在结算前被消灭（用户确认）
            effects.refresh_stats(sim)
            return
        if t is not None:
            effects.on_attacking(sim, c, t)
            fight(sim, c, t)
            g = effects.hook(c.name, 'gone_after_attack')
            if g and (g is True or g(sim, c, t)):
                # 流星：攻击后移出场；4TP：打总部后消灭（都按移除算，不触发亡计）
                destroy(sim, c, removed=True)
    effects.on_operated(sim, c, paid)
    effects.refresh_stats(sim)


def fight(sim, a, t, effect=False):
    """单位战斗：规则同 live_ai.combat，伤害走 damage()（含海鹰减伤、重甲）。
    effect=True：卡牌效果触发的"与目标战斗"（Hs129 部署、倾斜装甲），双方都无视重甲"""
    if t.type == 'location':
        _hit(sim, a, t, a.atk or 0, effect)
        return
    if effects.on_attacked(sim, t, a):
        return                           # 如 BM-13N：被攻击时撤退回手牌，这次攻击不结算
    _fight(sim, a, t, effect)
    for u, o in ((a, t), (t, a)):        # 对战后还活着（第 28 步兵团 +1+1）
        effects.on_survived(sim, u, o)


def _fight(sim, a, t, effect):
    counter = t.atk or 0
    if a.type == 'artillery' or (a.type == 'bomber' and t.type != 'fighter') or t.type == 'bomber' or a.shock:
        counter = 0
    if not effects.keeps_shock(a):
        a.shock = False                  # 冲击后失去冲击（T-34-85 不会失去冲击）
    t.smoke = False
    if t.ambush and counter > 0:
        # 伏击：先手反击，能消灭攻击方就不掉血
        _hit(sim, t, a, counter, effect)
        if a.df <= 0 or a not in sim.units(a.side):
            return
        _hit(sim, a, t, a.atk or 0, effect)
        return
    _hit(sim, a, t, a.atk or 0, effect)
    if counter > 0:
        _hit(sim, t, a, counter, effect)


AIR = ('fighter', 'bomber')


def _hit(sim, src, t, n, pierce=False):
    """单位 src 对 t 造成 n 点战斗伤害（伤害加成、造成伤害后的特效走卡牌钩子）"""
    dealt = damage(sim, t, n + effects.dmg_bonus(sim, src, t), src.side, by_unit=True, pierce=pierce)
    effects.on_dealt(sim, src, t, dealt)

