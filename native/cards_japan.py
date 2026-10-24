# 日本 + 波兰 “汝即军团”（含帝国研发链、天气牌、军团/4TP/偷袭等衍生牌）
# 结算细则（2026-10-15 用户确认）：
#   预报 = 先三选一天气（晴/雨/风暴），再从该天气池三选一 2/4/6 费牌；
#   延长战线算情报牌（空场打出：新军团吃到自己这次触发，成 3/3）；
#   京都联队离场时被移除的单位回到支援线，支援线满则彻底消失；摧枯拉朽的同名单位包括我方
# 情报：打出时看对方 N 张没看过的牌；“若是明牌/若知道对方手牌”按累计情报等级估（sim.known_enemy）
import sim_rules as R
import effects
from sim import SC, other
from effects import (P, U, card, on, gain, buff, temp_atk, once, rand_damage, rand_kill, unit_or_hq, research,
                     enemy_targets, all_units, spawn, forecast, on_intel, convert, converted)

LEGION = U + 'legion_pol'


def _enemies(sim, c, lines=('support', 'front')):
    return enemy_targets(sim, c.side, lines, smoke_ok=True, by_order=True)


def _value(u):
    """单位粗估价值（攻防和 + 词条），用于“移除/回手”类效果的收益"""
    return 0.5 * ((u.atk or 0) + max(0, u.df or 0)) + (1.0 if u.guard else 0) + 0.2 * (u.cost or 0)


def _known_draw(sim, side):
    """“若是明牌/若知道对方手牌则抽 1”：按看过的比例估抽牌期望（我方才模拟）"""
    e = sim.side[other(side)]['hand']
    if side != sim.me or not e:
        return
    p = sim.known_enemy() / len(e)
    if p >= 0.999:
        R.draw(sim, side, 1)
    elif p > 0:
        gain(sim, side, p * R.DRAW_V)


# ---------- 指令 ----------
@on('play', P + 'stretch_the_line')
def _stretch(sim, c, t, k):
    # 加一个军团到支援线，然后“情报 N”（N = 友方军团数）：看 N 张牌，但只算一次“使用情报牌”
    # （实测：场上 2 个军团时打出，每个军团只 +1+1，塔尔努夫只送 1 个军团）
    spawn(sim, c.side, LEGION)
    on_intel(sim, c.side, c, max(1, sim.count(c.side, LEGION)))


@on('play', P + 'punish')
def _punish(sim, c, t, k):
    h = sim.side[other(c.side)]['hand']
    if not h:
        return
    p = sim.known_enemy() / len(h) if c.side == sim.me else 0
    h.remove(next((x for x in h if x.name == '?'), h[0]))
    gain(sim, c.side, 1.5 + p * R.DRAW_V)    # 对方少一张牌；弃的是明牌就抽 1（按看过的比例估）


@on('play', P + 'overpower')
def _overpower(sim, c, t, k):
    x = sim.find(t)
    if x is None:
        return
    for u in [u for u in all_units(sim) if u.name == x.name]:
        R.destroy(sim, u)                      # 场上所有同名单位，包括我方（用户确认）


@on('play', P + 'ferocious_assault')
def _ferocious(sim, c, t, k):
    x = sim.find(t)
    if x is None:
        return
    lose = (x.atk or 0) > sim.side[c.side]['max_kredits']
    R.destroy(sim, x)
    if lose:
        R.gain_slot(sim, c.side, -1)


@on('play', P + 'desperate_measures')
def _desperate(sim, c, t, k):
    e = other(c.side)
    for u in list(sim.units(e)) + [sim.side[e]['hq']]:
        R.damage(sim, u, 2, c.side)
    R.gain_slot(sim, c.side, -1)


@on('play', P + 'anders_army')
def _anders(sim, c, t, k):
    R.draw(sim, c.side, 2)
    R.damage(sim, sim.side[c.side]['hq'], 2, other(c.side))


@on('play', P + 'island_fighting')
def _island(sim, c, t, k):
    hq = sim.side[c.side]['hq']
    if hq.df <= 10:
        R.draw(sim, c.side, 1)
    hq.df += 8


@on('play', P + 'surprise_attack')
def _surprise(sim, c, t, k):
    x = sim.find(t)
    if x is None:
        return
    if x.pinned:
        R.destroy(sim, x)
    else:
        x.pinned = True


@on('play', P + 'balloon_bombs')
def _balloon(sim, c, t, k):
    for u in sim.units(other(c.side)):
        u.pinned = True


@on('play', P + 'long_lance')
def _long_lance(sim, c, t, k):
    x = sim.find(t)
    if x is None:
        return
    small = (x.atk or 0) <= 3
    R.destroy(sim, x)
    if small:
        R.draw(sim, c.side, 2)


@on('play', P + '7075_aluminium')
def _aluminium(sim, c, t, k):
    for _ in range(3):
        z = R.add_hand(sim, c.side, U + 'zero')
        if z is not None:
            z.cost = 0                         # 0 费零战（亡计再给一张 0 费复制：不模拟）
    gain(sim, c.side, 1.5)


# ---------- 天气牌（预报得到）：每档 3 种变体效果各不相同（基础版 / *2 / *3） ----------
def _heatwave(sim, c, t, k):
    for u in all_units(sim):
        temp_atk(sim, u, 3 if u.type in R.AIR else 2)


def _jungle_fever(sim, c, t, k):
    # 所有单位本回合 +3 攻；不攻击的友方单位被压制（下回合不能动：按每个 -0.5 估）
    for u in all_units(sim):
        temp_atk(sim, u, 3)
    gain(sim, c.side, -0.5 * len([u for u in sim.units(c.side) if sim.attacks.get(u.id, 0) == 0]))


def _scorching_sun(sim, c, t, k):
    d = sim.side[c.side]
    for h in [h for h in d['hand'] if h.type in R.UNIT_TYPES]:
        if len(d['support']) + (sim.extra_sup if c.side == sim.me else 0) >= R.SUPPORT_MAX:
            break
        d['hand'].remove(h)
        R.place(sim, c.side, h, 'support')
        sim.deployed.add(h.id)
        h.pinned = True


def _deluge(sim, c, t, k):
    cand = sim.units(c.side) + [sim.side[c.side]['hq']]
    sim.random_used = True
    for _ in range(6):
        sim.rng.choice(cand).df += 1


def _torrential(sim, c, t, k):
    sim.side[c.side]['hq'].df += 3
    for u in sim.units(c.side):
        u.df += 3 if u.type == 'infantry' else 2


def _monsoon(sim, c, t, k):
    # 双方移除手牌和/或场上 2 张最贵的牌（不触发亡计）
    for s in ('left', 'right'):
        d = sim.side[s]
        pool = sorted([(x.cost or 0, 0, x) for x in d['hand'] if x.name != '?'] +
                      [(x.cost or 0, 1, x) for x in sim.units(s)], key=lambda p: -p[0])[:2]
        for _, onboard, x in pool:
            if onboard:
                R.destroy(sim, x, removed=True)
                gain(sim, other(s), _value(x))
            else:
                d['hand'].remove(x)
                gain(sim, other(s), 0.3 * (x.cost or 0))


def _thunderstorm(sim, c, t, k):
    rand_damage(sim, c.side, 3)


def _tropical(sim, c, t, k):
    # 双方手牌洗回，按洗回最多的一方张数重抽：手牌数拉平
    n = max(len(sim.side[s]['hand']) for s in ('left', 'right'))
    for s in ('left', 'right'):
        d = sim.side[s]
        d['hand'] = [SC.new('?', s, sim.new_id(), 'hand_' + s) for _ in range(n)]
    gain(sim, c.side, 0.0)


def _cyclone(sim, c, t, k):
    R.draw(sim, c.side, 3)
    R.damage(sim, sim.side[c.side]['hq'], len(sim.side[c.side]['hand']), other(c.side))


# --- 变体（用户指出：同名天气牌有 3 种不同效果；文字取自客户端 Game.locres） ---
def _heatwave2(sim, c, t, k):
    # 友方单位 +1 攻击、-1 行动花费，直到回合结束
    for u in sim.units(c.side):
        temp_atk(sim, u, 1)
        if u.op:
            u.op -= 1


def _deluge2(sim, c, t, k):
    for u in sim.units(other(c.side)):
        if u.atk:
            u.atk -= 1                         # 敌方单位 -1 攻击（永久）


def _deluge3(sim, c, t, k):
    # 抑制 1 个单位（回到卡面数值、去掉词条），抽 1
    effects.suppress(sim, sim.find(t), c.side)
    R.draw(sim, c.side, 1)


def _torrential2(sim, c, t, k):
    for u in sim.units(other(c.side)):
        u.pinned = True


def _monsoon2(sim, c, t, k):
    # 所有单位的攻击、防御、行动花费都变成 2
    for u in all_units(sim):
        u.atk, u.df, u.op = 2, 2, 2
        sim.temp.pop(u.id, None)
        if u.df <= 0:
            R.destroy(sim, u)


def _monsoon3(sim, c, t, k):
    # 友方步兵 +2+2，并能再次行动
    for u in sim.units(c.side):
        if u.type == 'infantry':
            buff(u, 2, 2)
            sim.attacks.pop(u.id, None)
            sim.moved.discard(u.id)
            sim.deployed.discard(u.id)


def _thunderstorm2(sim, c, t, k):
    # 随机 1 张敌方手牌 +1 费，随机 1 张友方卡牌 -1 费
    gain(sim, c.side, 0.6 if sim.side[other(c.side)]['hand'] else 0)
    h = [x for x in sim.side[c.side]['hand'] if (x.cost or 0) > 0]
    if h:
        sim.random_used = True
        x = sim.rng.choice(h)
        x.cost -= 1


def _thunderstorm3(sim, c, t, k):
    us = sim.units(other(c.side))
    if us:
        sim.random_used = True
        R.damage(sim, sim.rng.choice(us), 5, c.side)


def _tropical2(sim, c, t, k):
    # 随机让 1 个敌方单位撤退，然后随机消灭 1 个敌方单位
    e = other(c.side)
    fr = sim.side[e]['front']
    if fr:
        sim.random_used = True
        R.retreat(sim, sim.rng.choice(fr))
    rand_kill(sim, c.side)


def _tropical3(sim, c, t, k):
    # 对 1 个敌方目标 3 点，再随机对敌方单位 2 点、1 点
    x = unit_or_hq(sim, c.side, t)
    if x is not None:
        R.damage(sim, x, 3, c.side)
    for n in (2, 1):
        us = sim.units(other(c.side))
        if us:
            sim.random_used = True
            R.damage(sim, sim.rng.choice(us), n, c.side)


def _cyclone2(sim, c, t, k):
    for s in ('left', 'right'):
        for u in list(sim.side[s]['front']):
            R.retreat(sim, u)                  # 所有单位撤退（双方）


def _cyclone3(sim, c, t, k):
    # 对 1 个敌方单位 6 点，相邻目标 2 点
    x = sim.find(t)
    if x is None:
        return
    line = sorted(sim.side[x.side]['support' if x in sim.side[x.side]['support'] else 'front'], key=lambda u: u.slot)
    i = line.index(x)
    adj = [line[j] for j in (i - 1, i + 1) if 0 <= j < len(line)]
    R.damage(sim, x, 6, c.side)
    for u in adj:
        R.damage(sim, u, 2, c.side)


def _jungle_fever2(sim, c, t, k):
    # 1 个友方单位的复制加入支援线，压制到回合结束（下回合能动）
    x = sim.find(t)
    if x is not None:
        n = spawn(sim, c.side, x.name)
        if n is not None:
            n.atk, n.df = x.atk, x.df


def _flag(name):
    """本回合生效的效果：记在 sim.once（跨步骤由 TurnLog.once 带过来），部署/攻击时查"""
    return lambda sim, c, t, k: sim.once.add(name)


def _scorching_sun2(sim, c, t, k):
    for u in sim.units(c.side):
        buff(u, 3, 2)


def _scorching_sun3(sim, c, t, k):
    sim.once.add('ss3')
    for u in sim.units(c.side):
        if u.type in R.AIR:
            u.op = 0                           # 本回合友方空军行动花费 0


# 名字 -> (效果, 目标选项)；目标：None 无目标 / 'enemy' 敌方单位 / 'enemy_hq' 敌方单位或总部 / 'mine' 友方单位 / 'any'
WEATHER_FX = {
    'sunny2_heatwave': (_heatwave, None), 'sunny2_heatwave2': (_heatwave2, None),
    'sunny2_heatwave3': (_flag('hw3'), None),
    'sunny3_jungle_fever': (_jungle_fever, None), 'sunny3_jungle_fever2': (_jungle_fever2, 'mine'),
    'sunny3_jungle_fever3': (_flag('jf3'), None),
    'sunny4_scorching_sun': (_scorching_sun, None), 'sunny4_scorching_sun2': (_scorching_sun2, None),
    'sunny4_scorching_sun3': (_scorching_sun3, None),
    'rain2_deluge': (_deluge, None), 'rain2_deluge2': (_deluge2, None), 'rain2_deluge3': (_deluge3, 'any'),
    'rain3_torrential_rain': (_torrential, None), 'rain3_torrential_rain2': (_torrential2, None),
    # 骤雨 3（抽 3 选 1 弃）：选择弃牌的动作代理还不会发，不让 AI 打（见 deck 的 allow）
    'rain3_torrential_rain3': (lambda sim, c, t, k: R.draw(sim, c.side, 2), None),
    'rain4_monsoon_rain': (_monsoon, None), 'rain4_monsoon_rain2': (_monsoon2, None),
    'rain4_monsoon_rain3': (_monsoon3, None),
    'storm2_thunderstorm': (_thunderstorm, None), 'storm2_thunderstorm2': (_thunderstorm2, None),
    'storm2_thunderstorm3': (_thunderstorm3, None),
    'storm3_tropical_storm': (_tropical, None), 'storm3_tropical_storm2': (_tropical2, None),
    'storm3_tropical_storm3': (_tropical3, 'enemy_hq'),
    'storm4_cyclone': (_cyclone, None), 'storm4_cyclone2': (_cyclone2, None), 'storm4_cyclone3': (_cyclone3, 'enemy'),
}


def _weather_opts(kind):
    def f(sim, c):
        if kind == 'enemy':
            return [(i, 0) for i in _enemies(sim, c)]
        if kind == 'enemy_hq':
            return [(i, 0) for i in _enemies(sim, c)] + [(sim.side[other(c.side)]['hq'].id, 0)]
        if kind == 'mine':
            return [(u.id, 0) for u in sim.units(c.side)]
        return [(i, 0) for i in _enemies(sim, c)] + [(u.id, 0) for u in sim.units(c.side)]
    return f


for _n, (_f, _kind) in WEATHER_FX.items():
    card(P + _n, play=_f, **({'options': _weather_opts(_kind)} if _kind else {}))


def on_enter(sim, u):
    """友方单位部署/加入战场时（丛林热 3：+2 攻和闪击；热浪 3：随机对敌方目标造成等同攻击的伤害）"""
    if u.side != sim.me:
        return
    if 'jf3' in sim.once:
        u.atk = (u.atk or 0) + 2
        u.blitz = True
    if 'hw3' in sim.once and u.atk:
        e = other(u.side)
        cand = sim.units(e) + [sim.side[e]['hq']]
        sim.random_used = True
        R.damage(sim, sim.rng.choice(cand), u.atk, u.side)
    if 'ss3' in sim.once and u.type in R.AIR:
        u.op = 0


def ss3_attack(sim, u, t):
    """骄阳 3：本回合友方空军攻击单位时也对敌方总部造成伤害"""
    if 'ss3' in sim.once and u.side == sim.me and u.type in R.AIR and t.type != 'location':
        R.damage(sim, sim.side[other(u.side)]['hq'], u.atk or 0, u.side)


effects.ENTER_HOOKS.append(on_enter)
effects.ATTACK_HOOKS.append(ss3_attack)


card(P + 'imperial_research', choose_one=True, play=research(P + 'balloon_bombs', P + 'expanded_imperial_rnd'))
card(P + 'expanded_imperial_rnd', choose_one=True, play=research(P + 'long_lance', P + 'advanced_imperial_rnd'))
card(P + 'advanced_imperial_rnd', choose_one=True, play=research(P + '7075_aluminium', P + 'imperial_weapon_no_2'))
card(P + 'imperial_weapon_no_2', play=lambda sim, c, t, k: gain(sim, c.side, 12.0))   # 四张 0 费橘花放牌库顶
card(P + 'surprise_attack', options=lambda sim, c: [(i, 0) for i in _enemies(sim, c)])
card(P + 'long_lance', options=lambda sim, c: [(i, 0) for i in _enemies(sim, c)])
card(P + 'overpower', options=lambda sim, c: [(i, 0) for i in _enemies(sim, c) if (sim.find(i).atk or 0) <= 2])
card(P + 'ferocious_assault',
     options=lambda sim, c: [(i, 0) for i in _enemies(sim, c) if sim.find(i).type == 'infantry'])


# ---------- 单位 ----------
@on('deploy', U + 'kyoto_regiment')
def _kyoto(sim, c, t):
    # 移除 1 个敌方单位，直到京都联队离场（离场时回到支援线；满则消失）
    x = sim.find(t)
    if x is None or x not in sim.units(x.side):
        return
    R.destroy(sim, x, removed=True)
    c.held = x
    gain(sim, c.side, -0.25 * _value(x))     # 对面打掉京都联队就能把它要回来：按 1/4 的回来概率扣


@on('destroyed', U + 'kyoto_regiment')
def _kyoto_gone(sim, u):
    x = getattr(u, 'held', None)
    if x is None:
        return
    d = sim.side[x.side]
    if len(d['support']) < R.SUPPORT_MAX:
        R.place(sim, x.side, x.copy(), 'support')   # 复制一份：held 在各模拟副本间共享，不能就地改
    u.held = None


@on('deploy', U + '2nd_raiding_brigade')
def _raiding(sim, c, t):
    x = sim.find(t)
    if x is not None and (x.atk or 0) <= 2:
        R.destroy(sim, x)


@on('deploy', U + 'yokosuka_e14y')
def _e14y(sim, c, t):
    forecast(sim, c.side)
    if sim.side[c.side]['kredits'] == 0:
        R.draw(sim, c.side, 1)


@on('deploy', U + '15th_wolves_regiment')
def _wolves(sim, c, t):
    x = sim.find(t)
    if x is None or x not in sim.units(x.side):
        return
    friendly = x.side == c.side
    convert(sim, x, U + 'routed_troops', c.side)   # 通用转换：原位、按卡面数值、当回合不能行动
    converted(sim, c.side)                         # 转敌方单位也算友方转换（用户确认：诺夫哥罗德触发）
    if friendly:
        R.draw(sim, c.side, 2)


@on('dealt', U + '77th_regiment')
def _77th(sim, u, t, n):
    if t.type != 'location' and t not in sim.units(t.side):
        spawn(sim, u.side, U + '20th_infantry_regiment')


@on('attacking', U + 'ki_30_ann')
def _ki30(sim, u, t):
    R.damage(sim, sim.side[other(u.side)]['hq'], 2, u.side)


@on('destroyed', U + 'ki_61_i_tei')
def _ki61(sim, u):
    R.damage(sim, sim.side[other(u.side)]['hq'], 2, u.side)
    sim.side[u.side]['hq'].df += 2


@on('ally_intel', LEGION)
def _legion(sim, u):
    buff(u, 1, 1)


@on('ally_intel', U + '16th_tarnow_regiment')
def _tarnow(sim, u):
    spawn(sim, u.side, LEGION)
    R.draw(sim, u.side, 1)


@on('ally_intel', U + 'thunder_division')
def _thunder(sim, u):
    if once(sim, ('thunder', u.id)):
        for x in sim.units(u.side):
            if x is not u:
                buff(x, 2, 2)


@on('ally_forecast', U + 'kawanishi_h8k')
def _h8k_draw(sim, u):
    R.draw(sim, u.side, 1)


card(U + '16th_tarnow_regiment', intel_spawns=True)
card(U + 'kawanishi_h8k', deploy=lambda sim, c, t: forecast(sim, c.side))
card(U + 'type94_tk', deploy=lambda sim, c, t: R.add_hand(sim, c.side, P + 'surprise_attack'))
card(U + 'dinah_iii', deploy=lambda sim, c, t: R.draw(sim, c.side, 2))   # 从牌库抽两张 1 费单位（按两次抽牌算）
card(U + '1st_recon', destroyed=lambda sim, u: _known_draw(sim, u.side))
card(U + '238th_regiment',                # 我方指挥点槽 <= 3 时造成双倍伤害
     dmg_bonus=lambda sim, u, t: (u.atk or 0) if sim.side[u.side]['max_kredits'] <= 3 else 0)
card(U + '4tp', gone_after_attack=lambda sim, u, t: t.type == 'location')   # 攻击敌方总部后消灭
card(U + 'danuta')                        # 回合开始送 4TP：客户端结算，按 persist 估值
card(U + 'kyoto_regiment',
     deploy_targets=lambda sim, c: enemy_targets(sim, c.side, ('support', 'front')))
card(U + '2nd_raiding_brigade', deploy_targets=lambda sim, c: [
    i for i in enemy_targets(sim, c.side, ('support', 'front')) if (sim.find(i).atk or 0) <= 2])
card(U + '15th_wolves_regiment', deploy_targets=lambda sim, c: (
    enemy_targets(sim, c.side, ('support', 'front')) + [u.id for u in sim.units(c.side) if u is not c]))


# ---------- 日法“手牌爆炸”（2026-10-17） ----------
# 结算细则（用户确认）：先发制人给对面的那张所有数值 +1，对面打了再给回来一张 +1 的，一直加下去；
# 妥协“双方各来两次” = 双方各抽 2、各 +6 防；剑兵团送出来的单位也带这个能力（没被抑制就一直传）；
# 最后一搏的“牌库里的单位 +3 攻”双方都加；竭尽全力“下回合部署或加入的单位”包括刷出来的
TAKE = P + 'take_initiative'


def _initiative(sim, c, t, k):
    """先发制人 / 对面拿到的那张：抽 (费用 - 1) 张，给对面一张费用 +1 的（卡牌数据里没有升级版，按费用推等级）"""
    R.draw(sim, c.side, max(1, (c.cost or 2) - 1))
    n = R.add_hand(sim, other(c.side), TAKE)
    if n is not None:
        n.type, n.cost = 'order', (c.cost or 2) + 1


@on('play', P + 'honorable_death')
def _honorable(sim, c, t, k):
    x = sim.find(t)
    if x is not None:
        R.destroy(sim, x)
        R.draw(sim, x.side, 1)                 # 单位的主人抽 1


@on('play', P + 'last_rites')
def _last_rites(sim, c, t, k):
    R.add_deck(sim, c.side, 8)                 # 8 张神风特攻队洗进牌库（价值由卡组按“之后能抽到几张”估）


@on('play', P + 'kamikaze')
def _kamikaze(sim, c, t, k):
    R.damage(sim, sim.side[other(c.side)]['hq'], 1, c.side)
    R.draw(sim, c.side, 1)


@on('play', P + 'audacity')
def _audacity(sim, c, t, k):
    a = spawn(sim, c.side, U + 'aichi_d3a')
    effects.refresh_stats(sim)
    us = sim.units(other(c.side))
    if a is not None and us:
        sim.random_used = True
        R.damage(sim, sim.rng.choice(us), a.atk or 0, c.side)


@on('play', P + 'bombing_raid')
def _bombing_raid(sim, c, t, k):
    """目标 3 点，同一战线相邻的目标 2 点（支援线里指挥部也算目标）"""
    e = sim.side[other(c.side)]
    x = unit_or_hq(sim, c.side, t)
    if x is None:
        return
    line = e['front'] if x in e['front'] else e['support'] + [e['hq']]
    line = sorted(line, key=lambda u: u.slot if u.slot is not None else 99)
    i = line.index(x)
    adj = [line[j] for j in (i - 1, i + 1) if 0 <= j < len(line)]
    R.damage(sim, x, 3, c.side)
    for u in adj:
        R.damage(sim, u, 2, c.side)


@on('play', P + 'exhaust_all_options')
def _exhaust(sim, c, t, k):
    x = sim.find(t)
    if x is None:
        return
    d = sim.side[x.side]
    line = sorted(d['front'] if x in d['front'] else d['support'], key=lambda u: u.slot if u.slot is not None else 99)
    i = line.index(x)
    for u in [x] + [line[j] for j in (i - 1, i + 1) if 0 <= j < len(line)]:
        u.pinned = True
    # 对面下回合部署/加入的单位也被压制：对面指挥点越多越值（下回合在模拟之外）
    gain(sim, c.side, 0.25 * min(10, sim.side[other(c.side)]['max_kredits']))


@on('play', P + 'southern_plan')
def _southern(sim, c, t, k):
    R.gain_slot(sim, c.side, 1)
    R.gain_slot(sim, other(c.side), -1)


@on('play', P + 'compromise')
def _compromise(sim, c, t, k):
    sides = (c.side,) if k == 0 else (c.side, other(c.side))
    for _ in range(1 if k == 0 else 2):
        for s in sides:
            R.draw(sim, s, 1)
            sim.side[s]['hq'].df += 3


@on('play', P + 'banzai_charge')
def _banzai(sim, c, t, k):
    for u in [u for u in all_units(sim) if (u.atk or 0) <= 4]:
        R.destroy(sim, u)
    sim.turn_over = True


@on('play', P + 'to_the_last_man')
def _last_man(sim, c, t, k):
    for u in list(all_units(sim)):
        R.destroy(sim, u)


@on('play', P + 'last_ditch_force')
def _last_ditch(sim, c, t, k):
    for u in list(all_units(sim)):
        R.destroy(sim, u)
    R.gain_slot(sim, c.side, -6)
    R.gain_slot(sim, other(c.side), -6)       # 牌库单位 +3 攻双方都加，互相抵消，不记


def _kurume_dead(sim, u):
    sim.turn_over = True                       # 被消灭时结束回合（模拟的是我方回合：我方这回合就结束了）


card(P + 'seize_the_initiative', play=_initiative)
card(TAKE, play=_initiative)
card(P + 'honorable_death', options=lambda sim, c: [
    (u.id, 0) for u in all_units(sim) if (u.atk or 0) <= 3 and
    (u.side == c.side or u.id in enemy_targets(sim, c.side, ('support', 'front'), smoke_ok=True, by_order=True))])
card(P + 'bombing_raid', options=lambda sim, c: [(i, 0) for i in enemy_targets(
    sim, c.side, ('support', 'front'), smoke_ok=True, by_order=True)] + [(sim.side[other(c.side)]['hq'].id, 0)])
card(P + 'exhaust_all_options', options=lambda sim, c: [(i, 0) for i in enemy_targets(
    sim, c.side, ('support', 'front'), smoke_ok=True, by_order=True)])
card(P + 'compromise', choose_one=True)
card(U + 'kurume_regiment', destroyed=_kurume_dead)
card(U + '388th_independent', destroyed=lambda sim, u: R.draw(sim, other(u.side), 1))
card(U + 'kikka_jet', destroyed=lambda sim, u: R.add_deck(sim, u.side, 4))
card(U + 'storm_division', aura=lambda sim, u, x: (2, 0) if x.faction == 'Japan' else (0, 0))
card(U + 'aichi_d3a', stat_bonus=lambda sim, u: (2 * sum(1 for x in sim.units(u.side)
                                                         if x is not u and x.name == u.name), 0))
card(U + 'ki_83')              # 我方回合开始时我抽 1、对面抽 2：在模拟之外，卡组按 persist 估
card(U + 'kokuras_sword')      # 敌方回合被消灭时送一个日本地面单位：在模拟之外，卡组按 persist 估
