# 打法：日本 + 法国 “手牌爆炸”（指挥部 碧瑶）
# 思路（2026-10-17 与用户讨论）：拖延 + 大规模解场。不停让双方抽牌，把对面手牌塞满（上限 9，再抽就爆），
# 对面爆牌比我方快就赚；对面牌库抽空后再抽按等差数列扣血（协力的疲惫伤害共用计数）。
# 贪婪地等：先压住对面（竭尽全力、气球炸弹、久留米断回合），对面会一直往场上下牌，场面足够大再万岁冲锋/至死方休/最后一搏。
# 洛林十字（萨尔攻势第一张指令送）、纵深防御吃对面手牌数；最后的仪式/橘花往自己牌库塞神风特攻队收尾。
# 卡牌效果在 cards_japan.py / cards_france.py；这里只放这套卡组的用法和估值
import sim_rules as R

NAME = 'japan_burst'
DECK_CODE = '%%36|2h5C5U5x637xE8gQimjjlfmcqtrkx9zn;2l5OfcgJjOmap9rQ;qz;oG'
HQ = 'card_location_baguio'           # 用户指定（2026-10-17）：特鲁克没有正式版
COMMANDER = '福田'                      # 我起的
AVATAR = 'avatar_samurai'
MAIN, ALLY = 'Japan', 'france'

# 控制：自保重于打脸
W = {'my_hq': 1.2, 'en_hq': 0.8, 'threat': 1.3, 'front': 0.8, 'board': 1.0}
SLOT_R, SLOT_V = 10, 1.0
HOLD_FRAC = 0.5
DANGER_DMG = 7
BURN_V = 1.5              # 我方爆牌
ENEMY_DRAW_V = 1.5        # 对方抽到一张（R.draw）：给对方牌是代价
ENEMY_BURN_V = 1.8        # 对方爆掉一张：白丢一张牌，还离牌库抽空更近
NEXT_BURN_V = 1.6         # 回合结束时对方手牌已满：他下回合开始抽的那张必爆
FATIGUE_V = 1.2           # 牌库空了，每回合自然抽牌要扣血：每点按这么多分
KAMIKAZE_V = 1.2          # 牌库里一张神风特攻队（1 费：总部 1 点 + 抽 1）

E_, U_ = 'card_event_', 'card_unit_'
WIPES = {E_ + 'banzai_charge', E_ + 'to_the_last_man', E_ + 'last_ditch_force'}


def _e(side):
    return 'left' if side == 'right' else 'right'


def _r(ctx, n=4):
    return min(ctx.get('R', 6), n)


def danger(ctx):
    return ctx.get('T', 0) >= DANGER_DMG or ctx.get('T', 0) >= ctx.get('H', 20)


def _en(sim, side):
    return sim.units(_e(side))


def _board(sim, side):
    return sum((u.atk or 0) + max(0, u.df or 0) for u in sim.units(side))


def _rv():
    import research_v
    return research_v


def _chain(sim, c, ctx):
    return _rv().chain_hold(sim, c, ctx, hold, allow_option)


def _en_hand(sim, side):
    return len(sim.side[_e(side)]['hand'])


HOLD = {
    E_ + 'honorable_death': 1.0,
    E_ + 'desperate_measures': lambda sim, c, ctx: 1.5 + 0.4 * len(_en(sim, c.side)),
    E_ + 'seize_the_initiative': 0.8,
    E_ + 'take_initiative': 0.8,
    E_ + 'last_rites': 1.5,               # 价值（8 张神风）在 eval_extra 里按牌库估，留牌价值低：早打
    E_ + 'kamikaze': 0.6,
    E_ + 'imperial_research': lambda sim, c, ctx: _chain(sim, c, ctx),
    E_ + 'expanded_imperial_rnd': lambda sim, c, ctx: _chain(sim, c, ctx),
    E_ + 'advanced_imperial_rnd': lambda sim, c, ctx: _chain(sim, c, ctx),
    E_ + 'balloon_bombs': lambda sim, c, ctx: 1.0 + 0.6 * min(4, len(_en(sim, c.side))),
    # 氧气鱼雷：权重压低，除非有马上能对总部打出大伤害的单位（用户）
    E_ + 'long_lance': lambda sim, c, ctx: 2.5 if _rv().big_hitter(sim, c.side) else 1.0,
    E_ + '7075_aluminium': 4.0,
    E_ + 'imperial_weapon_no_2': 7.0,         # 四张 0 费橘花：后期连续四回合免费大飞机
    E_ + 'island_fighting': lambda sim, c, ctx: 3.0 if not danger(ctx) else 1.0,
    E_ + 'audacity': 1.5,
    E_ + 'bombing_raid': 2.0,
    E_ + 'exhaust_all_options': 2.5,
    E_ + 'southern_plan': 1.0,
    E_ + 'compromise': 1.5,
    E_ + 'liberation': 2.5,
    E_ + 'defend_in_depth': lambda sim, c, ctx: 0.8 + 0.3 * _en_hand(sim, c.side),
    E_ + 'arming_resistance': 2.0,
    E_ + 'phoney_war': 2.0,
    E_ + 'saar_probe': 2.5,
    E_ + 'cross_of_lorraine': 2.5,
    # 清场：留着等对面场面足够大（贪婪地等）；要打出的局面分超过这些才打
    E_ + 'banzai_charge': 5.0,
    E_ + 'to_the_last_man': 8.0,
    E_ + 'last_ditch_force': 8.0,
}


def hold(sim, c, ctx):
    n = c.name
    h = HOLD.get(n)
    if h is not None:
        return h(sim, c, ctx) if callable(h) else h
    if c.type == 'order':
        return 0.3 * (c.cost or 0)
    v = 0.5 * (c.atk or 0) + 0.5 * (c.df or 0) + (1.0 if c.guard else 0) + (c.armor or 0) + persist(sim, c, ctx)
    return HOLD_FRAC * v


def persist(sim, u, ctx):
    n = u.name
    if n == U_ + 'ki_83':
        # 我方回合开始：我抽 1、对面抽 2。对面手牌快满时那 2 张多半爆掉
        room = R.HAND_MAX - _en_hand(sim, u.side)
        burn = max(0, 2 - max(0, room))
        return _r(ctx, 3) * (0.8 * R.DRAW_V - (2 - burn) * ENEMY_DRAW_V * 0.5 + burn * ENEMY_BURN_V * 0.8)
    if n == U_ + '388th_independent':
        return -0.5 * ENEMY_DRAW_V        # 死了对面抽 1
    if n == U_ + 'kurume_regiment':
        return 1.5                        # 守护 + 对面在自己回合打死它就断回合
    if n == U_ + 'kokuras_sword':
        return 2.5                        # 敌方回合被消灭时送一个日本地面单位，一直传下去
    if n == U_ + 'kikka_jet':
        return 1.0                        # 死了往牌库塞 4 张神风
    if n == U_ + 'storm_division':
        return 1.0
    return 0.0


def eval_extra(sim, ctx):
    """手牌爆炸的局面项：对面手牌已满 -> 他下回合开始那张必爆；牌库抽空后自然抽牌扣血；我方牌库里的神风"""
    me, e = sim.me, _e(sim.me)
    v = 0.0
    if R.hand_room(sim, e) <= 0:
        v += NEXT_BURN_V
    for s, sign in ((e, 1), (me, -1)):
        left = sim.deck_n.get(s)
        if left is not None and left <= 0:
            v += sign * FATIGUE_V * (sim.fatigue.get(s, 0) + 1)   # 下回合自然抽牌的那一下疲惫伤害
    v += KAMIKAZE_V * sim.deck_add.get(me, 0) * 0.5     # 本回合塞进自己牌库的神风（按以后抽到一半估）
    return v


def allow(sim, c, ctx):
    n = c.name
    en, my = _en(sim, c.side), sim.units(c.side)
    if n == E_ + 'banzai_charge':
        # 贪婪地等：对面攻击 <= 4 的场面明显比我方大才清（或者危险时）
        gain = sum((u.atk or 0) + max(0, u.df or 0) for u in en if (u.atk or 0) <= 4)
        lose = sum((u.atk or 0) + max(0, u.df or 0) for u in my if (u.atk or 0) <= 4)
        return danger(ctx) or (len(en) >= 3 and gain - lose >= 12)
    if n in (E_ + 'to_the_last_man', E_ + 'last_ditch_force'):
        return danger(ctx) or (len(en) >= 3 and _board(sim, _e(c.side)) - _board(sim, c.side) >= 15)
    if n == E_ + 'island_fighting':
        return danger(ctx) or sim.side[c.side]['hq'].df <= 10
    if n == E_ + 'desperate_measures':
        e = sim.side[_e(c.side)]['hq'].df
        return e <= 2 or sum(1 for u in en if (u.df or 0) <= 2) >= 2
    if n == E_ + 'phoney_war':
        # 双方各抽“离 8 张差几张”：我方抽得比对面多，或者对面一抽就快满（之后再塞就爆），
        # 或者对面牌库不够他抽（每张抽不到的都是疲惫伤害，越抽越疼）——这时交给模拟算，常常就是斩杀
        mine = max(0, 8 - (len(sim.side[c.side]['hand']) - 1))
        theirs = max(0, 8 - _en_hand(sim, c.side))
        return mine >= theirs + 1 or _en_hand(sim, c.side) >= 6 or _en_fatigued(sim, c.side, theirs)
    return True


def _en_fatigued(sim, side, draws):
    """对面牌库不够这次抽 draws 张：抽不到的每张都按等差数列扣血"""
    left = sim.deck_n.get(_e(side))
    return left is not None and left < draws


def allow_option(sim, c, t, k, ctx):
    n = c.name
    S = sim.side[c.side]['max_kredits']
    if n == E_ + 'compromise':
        # 双方各来两次：对面手牌 >= 7 时多半爆掉（用户：对面 8 张时妥协至少爆两张，开局还要再抽一张）；
        # 对面牌库抽不够 2 张时也选双方（疲惫伤害，模拟里算得出是不是斩杀）；
        # 我方牌库快空、对面还没空时别给自己抽
        mine = sim.deck_n.get(c.side)
        theirs = sim.deck_n.get(_e(c.side))
        if _en_fatigued(sim, c.side, 2) and (mine is None or theirs is None or mine >= theirs):
            return True
        if mine is not None and theirs is not None and mine <= 2 and theirs > mine:
            return k == 0
        return k == (1 if _en_hand(sim, c.side) >= 7 else 0)
    if n == E_ + 'honorable_death':
        x = sim.find(t)
        return x is not None and x.side != c.side         # 只拿来清对面（对面抽 1 正好塞手牌）
    if n == E_ + 'imperial_research':
        return k == (0 if danger(ctx) else 1)
    if n == E_ + 'expanded_imperial_rnd':
        # 氧气鱼雷只在有压力或有大单位等着清路时选，否则开高级研发
        return k == 1 or danger(ctx) or _rv().big_hitter(sim, c.side)
    if n == E_ + 'advanced_imperial_rnd':
        return k == 0 or S >= 10
    return True


def allow_attack(sim, u, t):
    return True


KEEP = {E_ + 'honorable_death', U_ + 'kurume_regiment', E_ + 'seize_the_initiative', E_ + 'last_rites',
        E_ + 'southern_plan', E_ + 'imperial_research', E_ + 'liberation'}


def keep(name, cost):
    """起手调度：留低费解场、久留米、先发制人、最后的仪式和南进计划；大清场换掉"""
    return name in KEEP
