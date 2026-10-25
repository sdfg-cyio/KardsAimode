# 英+澳新流星卡组（含皇家研发链衍生牌）
# 结算细则（2026-10-15 用户确认）：新抽到/新生成的牌在手牌最右；流星发动攻击那一刻按当时攻防（含本回合加成）×2
# 复制一张随机洗进牌库，费用不变；“所有敌人”含总部，“所有敌方单位”不含
# 军情五处、甜心、米德尔塞克斯团、驻军、爆破、生产、计划已在 cards_usa / cards_neutral
import sim_rules as R
from sim import other
from effects import P, U, card, on, gain, buff, rand_kill, unit_or_hq, research, enemy_targets, all_units

GROUND = ('infantry', 'tank', 'artillery')


def _enemies(sim, c, lines=('support', 'front')):
    return enemy_targets(sim, c.side, lines, smoke_ok=True, by_order=True)


def _targets(sim, c):
    return [(i, 0) for i in _enemies(sim, c)]


def _plan(sim):
    return (sim.ctx or {}).get('plan')


def _bounce_value(u):
    """敌方单位回到手牌/牌库顶：对方还能再打出来，按单位价值的一半估（同 cards_germany）"""
    return 0.25 * ((u.atk or 0) + (u.df or 0)) + 0.2 * (u.cost or 0)


def meteor_value(sim, side, atk, df):
    """牌库里一张 atk/df 的流星值多少分：以后抽到它就是一次 atk 点的闪击打脸（攻击超过敌方总部血量的部分不算），
    还要等抽到（折扣 0.5）。卡组可用 METEOR_V 调整系数"""
    hq = sim.side[other(side)]['hq'].df
    k = getattr(_plan(sim), 'METEOR_V', 0.5)
    return k * (min(atk, hq + 4) + 0.3 * df)


def _all_enemy_units(sim, c, n):
    for u in list(sim.units(other(c.side))):
        R.damage(sim, u, n, c.side)


# ---------- 指令 ----------
@on('play', P + 'anzac_spirit')
def _anzac_spirit(sim, c, t, k):
    e = other(c.side)
    for u in list(sim.units(e)) + [sim.side[e]['hq']]:      # 所有敌人：含总部
        R.damage(sim, u, 2, c.side)
    R.draw(sim, c.side, 2)
    R.gain_slot(sim, c.side, 2)


@on('play', P + 'aans')
def _aans(sim, c, t, k):
    sim.side[c.side]['hq'].df += 3
    R.gain_slot(sim, c.side, 1)


@on('play', P + 'z_special_unit')
def _z_special(sim, c, t, k):
    x = sim.find(t)
    if x is not None:
        R.damage(sim, x, 4, c.side)
    if sim.play_left:
        sim.side[c.side]['hq'].df += 5


@on('play', P + 'repel_the_attack')
def _repel(sim, c, t, k):
    # 只有前线单位能撤退（支援线满则移除）；不在最右边打出会结束回合——打法层只允许最右边打（allow）
    for u in list(sim.side[other(c.side)]['front']):
        R.retreat(sim, u)
    if not sim.play_right:
        sim.turn_over = True                 # 不在最右边打出：回合结束，之后不能再行动


@on('play', P + 'forward_observers')
def _forward_observers(sim, c, t, k):
    _all_enemy_units(sim, c, 2)
    if sim.memo.get('brit_last'):
        R.draw(sim, c.side, 1)


@on('play', P + 'wave_after_wave')
def _wave(sim, c, t, k):
    _all_enemy_units(sim, c, 4 if sim.played == 2 else 2)    # sim.played 已含这一张


@on('play', P + 'corps_command')
def _corps(sim, c, t, k):
    # 打完后手牌最左、最右两张获得“打出时随机消灭一个敌方单位”（只剩一张就只标一次）
    h = sim.side[c.side]['hand']
    for x in {id(h[0]): h[0], id(h[-1]): h[-1]}.values() if h else ():
        x.corps = (getattr(x, 'corps', 0) or 0) + 1


def hp_trade(sim, u, x):
    """可畏号/本土链的“与敌方单位战斗”（用户确认 2026-10-24）：双方按攻击力互相扣血，
    无视任何条件（火炮/轰炸机不反击、伏击先手、冲击、重甲、被攻击时撤退都不管）；减伤光环照算"""
    a, b = max(0, u.atk or 0), max(0, x.atk or 0)
    for src, dst, n in ((u, x, a), (x, u, b)):
        if n:
            R.damage(sim, dst, n, src.side, by_unit=True, pierce=True)


@on('play', P + 'hms_formidable')
def _formidable(sim, c, t, k):
    u = sim.find(t)
    if u is None:
        return
    u.atk = u.df                         # 永久：之后还是这个攻击力
    foes = list(sim.units(other(c.side)))
    sim.random_used = sim.random_used or len(foes) > 1
    sim.rng.shuffle(foes)
    for x in foes:
        if u not in sim.units(u.side):
            break
        if x in sim.units(x.side):
            hp_trade(sim, u, x)


@on('play', P + 'chain_home')
def _chain_home(sim, c, t, k):
    u = sim.find(t)
    if u is None:
        return
    u.atk = u.df
    foes = list(sim.units(other(c.side)))
    if foes:
        sim.random_used = sim.random_used or len(foes) > 1
        hp_trade(sim, u, sim.rng.choice(foes))


@on('play', P + 'monty')
def _monty(sim, c, t, k):
    x = sim.find(t)
    if x is not None:
        line = sorted(sim.side[x.side]['support' if x in sim.side[x.side]['support'] else 'front'],
                      key=lambda u: u.slot)
        i = line.index(x)
        for u in line[max(0, i - 1):i + 2]:
            u.pinned = True
    R.draw(sim, c.side, 1)


@on('play', P + 'synthetic_rubber')
def _rubber(sim, c, t, k):
    u = sim.find(t)
    if u is not None:
        u.df += 4
        u.atk = u.df


@on('play', P + 'active_sonar')
def _sonar(sim, c, t, k):
    e = other(c.side)
    for u in sim.units(e):
        u.pinned = True
    gain(sim, c.side, 0.8 * len(sim.side[e]['hand']))      # 对方手牌全部 +3 费


@on('play', P + 'bletchley_park')
def _bletchley(sim, c, t, k):
    e = other(c.side)
    for u in [u for u in sim.units(e) if (u.cost or 0) <= 5]:
        R.destroy(sim, u, removed=True)
        gain(sim, c.side, -_bounce_value(u) + 1.0)
    gain(sim, c.side, 1.2 * len(sim.side[e]['hand']))


def _counter(v):
    """反制：埋下后在对方回合生效，按固定价值估（卡组的 HOLD 决定什么时候值得埋）"""
    return lambda sim, c, t, k: gain(sim, c.side, v(sim, c) if callable(v) else v)


card(P + 'interception', play=_counter(1.5))                    # 反制指向我方的敌方指令
card(P + 'ultra', play=_counter(lambda sim, c: 2.5 + 0.8 * R.DRAW_V))   # 反制任意指令并抽 1
card(P + 'radar_alert',                                         # 对方部署单位时给一张同费英国飞机
     play=_counter(lambda sim, c: 1.0 + 0.25 * min(10, sim.side[other(c.side)]['max_kredits'])))
card(P + 'the_land_girls', play=lambda sim, c, t, k: R.draw(sim, c.side, 2))
card(P + 'protected_convoy', play=lambda sim, c, t, k: (R.add_hand(sim, c.side, P + 'production'),
                                                         R.add_hand(sim, c.side, P + 'plan')))
card(P + 'radar', play=lambda sim, c, t, k: (R.draw(sim, c.side, 1),
                                             setattr(sim.side[c.side]['hq'], 'df', sim.side[c.side]['hq'].df + 4)))
card(P + 'royal_research', choose_one=True, play=research(P + 'radar', P + 'expanded_royal_research'))
card(P + 'expanded_royal_research', choose_one=True,
     play=research(P + 'synthetic_rubber', P + 'advanced_royal_research'))
card(P + 'advanced_royal_research', choose_one=True, play=research(P + 'active_sonar', P + 'bletchley_park'))
def _z_options(sim, c):
    """Z 队“对一个单位造成 4 点伤害”：敌方单位；在手牌最左时也可以打自己的高防守护单位，只为总部 +5"""
    opts = _targets(sim, c)
    h = sim.side[c.side]['hand']
    if h and h[0] is c:
        opts += [(u.id, 0) for u in sim.units(c.side) if (u.df or 0) > 4 and u.name != U + 'meteor']
    return opts


card(P + 'z_special_unit', options=_z_options)
card(P + 'monty', options=_targets)
card(P + 'hms_formidable', options=lambda sim, c: [(u.id, 0) for u in sim.units(c.side)])
card(P + 'chain_home', options=lambda sim, c: [(u.id, 0) for u in sim.units(c.side)])
# 合成橡胶只给本回合还能攻击的流星（实测给了没意义的驻军，用户指出）：+4 后攻击，复制出来翻倍
card(P + 'synthetic_rubber', options=lambda sim, c: [
    (u.id, 0) for u in sim.units(c.side)
    if u.name == U + 'meteor' and not u.pinned and sim.attacks.get(u.id, 0) == 0])


# ---------- 防火墙卡组（英美“Firewall”，2026-10-16） ----------
# 用户确认：两难困境/防火墙/自由之地的效果是永久的；两难困境主要给敌方；自由之地也可以给敌方
# （先自由之地把行动费变 0，再两难困境互换 -> 攻击 0）；HMS 权杖号把指令变成计划还给对方；
# 英联邦打出时检查我方总部 >= 30，20 点会被减伤挡（概率不大）
def neutral_v(sim, side, u, atk_cut, hq_only=False):
    """敌方单位 u 以后每回合少打 atk_cut 点总部的价值：按它大概还能活几回合（攻高的会被对面留着用）
    折算；本回合的威胁已在 planner.threat 里体现，这里只算之后的回合"""
    plan = _plan(sim)
    rounds = getattr(plan, 'NEUTRAL_R', 3.0)
    fn = getattr(plan, 'neutral_rounds', None)
    if fn is not None:
        rounds = fn(sim, u, rounds)           # 卡组按“这个单位已经打过几次总部”等修正还能打几回合
    # 这套几乎没有单位：敌方单位的攻击基本都打在总部上
    v = 0.6 * max(0, atk_cut) * rounds
    if u.type in ('artillery', 'bomber'):
        v *= 1.2                              # 火炮/轰炸机无视守护，最难挡
    return v


@on('play', P + 'dilemma')
def _dilemma(sim, c, t, k):
    u = sim.find(t)
    if u is None:
        return
    a, o = u.atk or 0, u.op or 0
    u.atk, u.op = o, a
    if u.side != c.side:
        gain(sim, c.side, neutral_v(sim, c.side, u, a - o))
        sim.neutralized = sim.neutralized | {u.id}   # 记录事实（处理过哪些单位）；怎么用由卡组决定


@on('play', P + 'naval_power')
def _naval_power(sim, c, t, k):
    u = sim.find(t)
    if u is not None:
        u.pinned = True
    sim.side[c.side]['hq'].df += 3


@on('play', P + 'raid')
def _raid(sim, c, t, k):
    # 对方手牌下回合全部 +2 费：按对方手牌数和槽数估（槽少时更伤）
    e = sim.side[other(c.side)]
    gain(sim, c.side, 0.5 * min(5, len(e['hand'])) * (1.3 if e['max_kredits'] <= 6 else 1.0))


@on('play', P + 'delaying_tactics')
def _delaying(sim, c, t, k):
    for s in ('left', 'right'):              # 前线所有单位撤退（双方）
        for u in list(sim.side[s]['front']):
            R.retreat(sim, u)


@on('play', P + 'air_power')
def _air_power(sim, c, t, k):
    x = unit_or_hq(sim, c.side, t)
    if x is None:
        return
    if k == 0:
        if x.type == 'tank':
            R.destroy(sim, x)
    else:
        R.damage(sim, x, 2, c.side)


@on('play', P + 'shelling')
def _shelling(sim, c, t, k):
    e = other(c.side)
    for u in list(sim.units(e)):
        R.damage(sim, u, 1, c.side)
        if u in sim.units(e):
            u.pinned = True
    R.gain_slot(sim, e, -1)


@on('play', P + 'the_commonwealth')
def _commonwealth(sim, c, t, k):
    if sim.side[c.side]['hq'].df >= 30:
        R.damage(sim, sim.side[other(c.side)]['hq'], 20, c.side)
    R.draw(sim, c.side, 4)


def _air_power_options(sim, c):
    e = sim.side[other(c.side)]
    ids = _enemies(sim, c)
    tanks = [(i, 0) for i in ids if sim.find(i).type == 'tank']
    return tanks + [(i, 1) for i in ids] + [(e['hq'].id, 1)]


# 只写卡面允许的目标；“给谁、什么时候给”是卡组的事（deck_britain_firewall.allow_option）
card(P + 'dilemma', options=_targets)
card(P + 'naval_power', options=_targets)
card(P + 'air_power', options=_air_power_options)
card(P + 'fortification', play=lambda sim, c, t, k: setattr(sim.side[c.side]['hq'], 'df',
                                                            sim.side[c.side]['hq'].df + 7))
card(P + 'sincerely_yours', play=lambda sim, c, t, k: (
    setattr(sim.side[c.side]['hq'], 'df', sim.side[c.side]['hq'].df + 6), R.draw(sim, c.side, 2)))
card(P + 'lend_lease', play=lambda sim, c, t, k: R.draw(sim, c.side, 4))
card(P + 'in_hour_of_need', play=lambda sim, c, t, k: R.gain_slot(sim, c.side, 2))
# 反制：权杖号反制任意指令（对面拿回一张计划），道丁只反制 4 费以上的
card(P + 'hms_spectre', play=_counter(lambda sim, c: 2.0))
card(P + 'dowding_system', play=_counter(lambda sim, c: 1.0 + 0.2 * min(10, sim.side[other(c.side)]['max_kredits'])))
# 国家消防局：对方回合总部每次受伤降到 1——价值由 planner.threat 体现（挂上后威胁按次数算）
card(P + 'national_fire_service', play=_counter(lambda sim, c: 0.0))


# ---------- 单位 ----------
@on('attacking', U + 'meteor')
def _meteor(sim, u, t):
    # 发动攻击那一刻：按当时攻防 ×2 复制进牌库（随机位置）；攻击后自己移出场（gone_after_attack）
    gain(sim, u.side, meteor_value(sim, u.side, 2 * (u.atk or 0), 2 * max(1, u.df or 0)))


@on('deploy', U + 'queens_own')
def _queens_own(sim, c, t):
    x = sim.find(t)
    if x is None or x.type == 'location' or x not in sim.units(x.side):
        return
    R.destroy(sim, x, removed=True)          # 放回拥有者牌库顶：不算消灭
    if x.side != c.side:
        gain(sim, c.side, -_bounce_value(x) + 1.0)   # 对方下回合抽回它，等于少抽一张新牌


@on('deploy', U + 'gordon_highlanders')
def _gordon(sim, c, t):
    # 选一张手里的指令：费用变 0、放回牌库顶（下回合抽回）。驱动另发 XActionHandTargetSelected
    x = next((h for h in sim.side[c.side]['hand'] if h.id == t), None)
    if x is None:
        return
    plan = _plan(sim)
    # 牌库里的牌不带军司令部标记：只按牌本身的保留价值算
    h = getattr(plan, 'card_hold', None) or getattr(plan, 'hold', None)
    keep = h(sim, x, sim.ctx) if h is not None else 0.25 * (x.cost or 0)
    sim.side[c.side]['hand'].remove(x)       # 离手：评估里自然少了它的保留价值
    # 换来：下回合抽回它（保留价值打九折）且 0 费，但少抽一张新牌
    gain(sim, c.side, 0.9 * keep + 0.8 * (x.cost or 0) - R.DRAW_V)


@on('ally_order', U + 'cameronians')
def _cameronians(sim, u):
    if sim.played == 2 and u.side == sim.me:
        R.draw(sim, u.side, 2)


card(U + 'meteor', gone_after_attack=True)
card(U + 'queens_own',
     deploy_targets=lambda sim, c: enemy_targets(sim, c.side, ('support', 'front')))
card(U + 'gordon_highlanders',
     deploy_targets=lambda sim, c: [h.id for h in sim.side[c.side]['hand']
                                    if h is not c and h.type == 'order' and h.name != '?' and (h.cost or 0) > 0])
card(U + 'no_46_commando', deploy=lambda sim, c, t: (R.add_hand(sim, c.side, P + 'blast'),
                                                      R.add_hand(sim, c.side, P + 'plan')))
card(U + 'garrison')                     # 回合开始没被攻击过就打总部 1 点：在对方回合后结算，按 persist 估值
card(U + '85_pioneer_company')            # 每回合第一张指令 -1 费：sim_rules 里打出第一张后把手里指令费用加回去
card(U + 'royal_ulster_rifles',          # 友方总部受到伤害时改由它承受：sim_rules.damage 里转移
     shield_hq=True)


# ---------- 英美米色团卡组（2026-10-24） ----------
# 用户确认：西非旅 2 费（card_db.PATCH）；可畏号/本土链的战斗是纯血量交换；威尔士卫队/沙利文兄弟号可指向敌方；
# 区域轰炸的兰开斯特当回合闪击能打，回合结束还活着就洗回牌库；桑德兰的海军牌 = 可畏号、沙利文兄弟号
LANCASTER = U + 'lancaster'
NAVAL = (P + 'hms_formidable', P + 'uss_sullivans')


def _any_units(sim, c, lines=('support', 'front')):
    """卡面“1 个目标/1 个单位”：我方单位 + 能被指向的敌方单位"""
    return [u.id for u in sim.units(c.side) if u is not c] + enemy_targets(sim, c.side, lines)


@on('play', P + 'area_bombardment')
def _area_bombardment(sim, c, t, k):
    from effects import spawn
    u = spawn(sim, c.side, LANCASTER)
    if u is not None:
        u.blitz = True                       # 兰开斯特 Mk I 自带闪击：当回合就能打
        gain(sim, c.side, 1.0)               # 回合结束洗回牌库：以后还能再抽到一次（8 费，打折）


card(U + 'buffs', pointed=lambda sim, u, src: buff(u, 1, 1, sim, u))   # 被指令或部署指向时 +1+1（敌我都算）
card(U + 'welsh_guards', deploy=lambda sim, c, t: buff(sim.find(t), 0, 1),
     deploy_targets=lambda sim, c: _any_units(sim, c))
card(U + 'frontier_force', deploy=lambda sim, c, t: R.add_hand(sim, c.side, U + 'garrison'))
card(U + '2nd_west_africa', deploy=lambda sim, c, t: R.draw(sim, c.side, 1))   # 抽费用最低的指令（这套只有构筑内的牌，不重复）
card(U + '70th_brigade')                 # 回合开始没被攻击过：抽 1 + 总部 +2，客户端结算，卡组按 persist 估值
card(U + 'short_sunderland')             # 回合结束抽 1 张海军牌：客户端结算，卡组按 persist 估值
card(P + 'aerial_reconaissance',         # 反制：对方部署单位时手里指令 -1 费（最低 1），价值看手里有几张 2 费以上指令
     play=_counter(lambda sim, c: 0.6 * min(3, sum(1 for h in sim.side[c.side]['hand']
                                                  if h.type == 'order' and (h.cost or 0) >= 2 and h is not c))))
card(P + 'area_bombardment')
