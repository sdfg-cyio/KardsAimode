# 打法：日本 + 美国 加费空军（指挥部 马尼拉，2026-10-25 用户卡组“日本卡组 2”）
# 思路（用户）：前期守住（久留米/第六十一联队守护、侦察队铺身子、战争机器/南进计划/战争债券加费）；
# 后期一次性给大量强化斩杀，或者飞机一次性扣对方大血。最好的飞机是 N1K-J 紫电（伏击闪击奋战），其次 Ki-61-I 丁。
# 激励部队（+行动费攻防、行动费 0）/火力爆发（+1 攻和奋战到回合结束）都留到爆发回合；
# 万岁冲锋/如日方升清场（自己的 5 攻飞机不吃万岁）；胁迫抑制对方的严重效果单位或斩杀前的守护；
# 帝国之力弃掉反制（对面是德/美/英/芬这些带防御反制的国家时更值）；Ki-61 改留 7 点在对方回合结束时自己上场
# 卡牌效果在 cards_japan.py / cards_usa.py；这里只放这套卡组的用法和估值
import sim_rules as R

NAME = 'japan_air'
DECK_CODE = '%%35|5C5R5x6B6Y6Z7bimjjlfmanPqtrkzn;5z667sjOohp9x3;bPgL;bK'
HQ = 'card_location_manila'           # 用户指定（2026-10-25）：特鲁克没有正式版
TITLE = '日美飞燕'
COMMANDER = '信浓'                     # 用户指定（2026-10-25）
AVATAR = 'avatar_warrior_sky'           # 头像我选的：天空武士（空军卡组）
MAIN, ALLY = 'Japan', 'usa'

# 前期守住，后期爆发：自保略重，对方总部低时 planner 的斩杀会自己算出来
W = {'my_hq': 1.1, 'en_hq': 1.0, 'threat': 1.2, 'front': 1.0, 'board': 1.0}
SLOT_R, SLOT_V = 10, 1.2              # 加费卡组：对局按 10 回合算
HOLD_FRAC = 0.5
DANGER_DMG = 7
TONY_KR = 7                           # Ki-61 改：我方回合结束时剩这么多点才会在对方回合结束时上场
TONY_V = 6.0                          # 免费上场一架 5/4 闪击战斗机的价值
COUNTER_NATIONS = ('Germany', 'USA', 'Britain', 'Finland')   # 用户：这些国家常带防御性反制

E_, U_ = 'card_event_', 'card_unit_'
SHIDEN, TEI, TONY = U_ + 'shiden', U_ + 'ki_61_i_tei', U_ + 'ki_61_tony'
BOLSTER, BURST, DURESS = E_ + 'bolster_the_ranks', E_ + 'burst_of_fire', E_ + 'duress'
BANZAI, ASCEND = E_ + 'banzai_charge', E_ + 'on_the_ascend'
# 飞机排名（用户）：紫电 > 一型丁 > 其他；强化优先给排名高的
ACE = {SHIDEN: 2.0, TEI: 1.0}


def _e(side):
    return 'left' if side == 'right' else 'right'


def _r(ctx, n=4):
    return min(ctx.get('R', 6), n)


def danger(ctx):
    return ctx.get('T', 0) >= DANGER_DMG or ctx.get('T', 0) >= ctx.get('H', 20)


def _en(sim, side):
    return sim.units(_e(side))


def _hand(sim, side):
    return [h for h in sim.side[side]['hand'] if h.name != '?']


def _rv():
    import research_v
    return research_v


def _chain(sim, c, ctx):
    return _rv().chain_hold(sim, c, ctx, hold, allow_option)


def _value(u):
    return (u.atk or 0) + max(0, u.df or 0)


def _counter_nation(sim, side):
    """对面是不是常带防御反制的国家（看场上/看过的手牌）"""
    e = _e(side)
    cards = sim.units(e) + [h for h in sim.side[e]['hand'] if h.name != '?']
    return any(getattr(x, 'faction', None) in COUNTER_NATIONS for x in cards)


def _severe(u):
    """值得胁迫（抑制）的敌方单位：有特效的引擎单位，或高攻守护/重甲"""
    import planner
    return planner.enemy_engine_v(u) >= 1.0 or (u.guard and (u.atk or 0) + max(0, u.df or 0) >= 8) or (u.armor or 0) >= 2


HOLD = {
    E_ + 'the_war_machine': 0.0,          # 加槽价值由 slot_value 算，前期越早越值
    E_ + 'southern_plan': 1.0,
    E_ + 'war_bonds': 1.5,
    E_ + 'imperial_research': _chain,
    E_ + 'expanded_imperial_rnd': _chain,
    E_ + 'advanced_imperial_rnd': _chain,
    E_ + 'balloon_bombs': lambda sim, c, ctx: 1.0 + 0.6 * min(4, len(_en(sim, c.side))),
    E_ + 'long_lance': lambda sim, c, ctx: 2.5 if _rv().big_hitter(sim, c.side) else 1.0,
    E_ + '7075_aluminium': 4.0,
    E_ + 'imperial_weapon_no_2': 7.0,
    E_ + 'kamikaze': 0.6,
    E_ + 'island_fighting': lambda sim, c, ctx: 3.0 if not danger(ctx) else 1.0,
    E_ + 'audacity': 1.5,
    E_ + 'bombing_raid': 2.0,
    E_ + 'exhaust_all_options': 2.5,
    E_ + 'desperate_measures': lambda sim, c, ctx: 1.5 + 0.4 * len(_en(sim, c.side)),
    E_ + 'scouting_party': 1.0,
    E_ + 'imperial_strength': lambda sim, c, ctx: 1.5 if _counter_nation(sim, c.side) else 1.0,
    # 爆发牌：留到斩杀/大扣血回合（局面分要超过这个才打）
    # 激励部队：对面总部越健康越留着（用户：后期一次性大量强化斩杀/大扣血）；对面低血时门槛下降，斩杀由 planner 直接算
    BOLSTER: lambda sim, c, ctx: 2.0 + 0.4 * max(0, sim.side[_e(c.side)]['hq'].df),
    BURST: lambda sim, c, ctx: 1.0 + 0.15 * max(0, sim.side[_e(c.side)]['hq'].df),
    DURESS: 1.5,
    BANZAI: 5.0,
    ASCEND: 2.5,
    TONY: 4.0,
}


def hold(sim, c, ctx):
    h = HOLD.get(c.name)
    if h is not None:
        return h(sim, c, ctx) if callable(h) else h
    if c.type == 'order':
        return 0.3 * (c.cost or 0)
    v = 0.5 * (c.atk or 0) + 0.5 * (c.df or 0) + (1.0 if c.guard else 0) + (c.armor or 0) + _persist(sim, c, ctx)
    return HOLD_FRAC * v


def persist(sim, u, ctx):
    v = _persist(sim, u, ctx)
    if getattr(u, 'temp_fury', False):
        v -= 0.5 * max(0, u.atk or 0)     # 火力爆发的奋战只到回合结束（unit_value 按永久奋战加过）
    return v


def _persist(sim, u, ctx):
    n = u.name
    if n == SHIDEN:
        return 1.5                        # 伏击 + 奋战：守空、一回合打两次
    if n == TEI:
        return 1.0                        # 亡计：对方总部 2、我方 +2
    if n == U_ + 'kikka_jet':
        return 1.0                        # 亡计：牌库塞 4 张神风
    if n == U_ + 'kurume_regiment':
        return 1.5                        # 守护；对面在自己回合打死它就断回合
    if n == U_ + '61st_infantry_regiment':
        return 1.0                        # 守护，亡计抽 1
    if n == U_ + '33rd_recon':
        return 0.8                        # 受伤抽 1
    if n == U_ + 'ki_30_ann':
        return 0.8 * _r(ctx, 3)           # 每次攻击额外打总部 2
    return 0.0


def eval_extra(sim, ctx):
    """Ki-61 改：手里有它、回合结束剩 >= 7 点 -> 敌方回合结束时免费上场一架 5/4 闪击"""
    me = sim.me
    if any(h.name == TONY for h in sim.side[me]['hand']) and sim.side[me]['kredits'] >= TONY_KR \
            and len(sim.side[me]['support']) < R.SUPPORT_MAX:
        return TONY_V
    return 0.0


def allow(sim, c, ctx):
    n = c.name
    my = sim.side[c.side]
    en, mine = _en(sim, c.side), sim.units(c.side)
    if n == TONY:
        return my['max_kredits'] < TONY_KR      # 7 槽以上留 7 点让它自己上场，不从手里打
    if n == BANZAI:
        gain = sum(_value(u) for u in en if (u.atk or 0) <= 4)
        lose = sum(_value(u) for u in mine if (u.atk or 0) <= 4)
        return danger(ctx) or (len(en) >= 2 and gain - lose >= 8)
    if n == ASCEND:
        us = en + mine
        if not us:
            return False
        low = min((u.atk or 0) for u in us)
        gain = sum(_value(u) for u in en if (u.atk or 0) == low)
        lose = sum(_value(u) for u in mine if (u.atk or 0) == low)
        return gain > 0 and gain >= lose + 2
    if n == E_ + 'island_fighting':
        return danger(ctx) or my['hq'].df <= 10
    if n == E_ + 'desperate_measures':
        e = sim.side[_e(c.side)]['hq'].df
        return e <= 2 or sum(1 for u in en if (u.df or 0) <= 2) >= 2
    if n == BURST:
        return any(u.type == 'fighter' for u in mine)
    return True


def allow_option(sim, c, t, k, ctx):
    n = c.name
    S = sim.side[c.side]['max_kredits']
    if n == BOLSTER:
        u = sim.find(t)
        return u is not None and u.side == c.side and (u.op or 0) >= 2     # 只给友方、行动费高的（飞机 3）
    if n == BURST:
        u = sim.find(t)
        return u is not None and sim.attacks.get(u.id, 0) == 0 and not u.pinned   # 本回合还没打过的飞机
    if n == DURESS:
        u = sim.find(t)
        # 主要给敌方的严重效果单位或斩杀前挡路的守护；自己的久留米在我方回合要拿去换的时候也行
        if u is None:
            return False
        if u.side != c.side:
            return _severe(u) or u.guard
        return u.name == U_ + 'kurume_regiment'
    if n == E_ + 'imperial_research':
        return k == (0 if danger(ctx) else 1)
    if n == E_ + 'expanded_imperial_rnd':
        return k == 1 or danger(ctx) or _rv().big_hitter(sim, c.side)
    if n == E_ + 'advanced_imperial_rnd':
        return k == 0 or S >= 10
    return True


KEEP = {U_ + 'kurume_regiment', E_ + 'the_war_machine', E_ + 'southern_plan', E_ + 'scouting_party',
        U_ + '2nd_raiding_brigade', E_ + 'imperial_research'}


def keep(name, cost):
    """起手调度：留守线和加费，大飞机和爆发牌换掉"""
    return name in KEEP


# 难度加成（native/buffs.py）：OPENING = 老兵及以上的起手候选池（随机挑 4~5 张）；CORE = 地狱档手牌少时打印的核心牌
OPENING = [U_ + 'kurume_regiment', E_ + 'the_war_machine', E_ + 'southern_plan', E_ + 'scouting_party',
           U_ + '2nd_raiding_brigade', E_ + 'imperial_research', U_ + '61st_infantry_regiment']
CORE = [SHIDEN, TEI, BOLSTER, BANZAI, E_ + 'war_bonds']
