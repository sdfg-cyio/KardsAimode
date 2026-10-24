# 打法：英国 + 澳新 流星（指挥部 突尼斯城；所有总部无特效）
# 思路：大量过牌（土地女孩/护送航运/计划/雷达）反复抽回流星，每次攻击按当时攻防 ×2 洗回牌库；
# AANS/澳新军团精神加槽回血，甜心随抽牌回血；前进观察员/高潮迭起/Z 队/击退进攻/军司令部解场；
# 反制（拦截/ULTRA/雷达警报）有闲费就挂，不同反制可同时挂多张；
# 后期女王直属卡梅伦高地人团（闪击奋战 7/7，部署把挡路的单位放回牌库顶）压场斩杀
# 卡牌效果在 cards_britain.py（部分在 cards_usa / cards_neutral）；这里只放“这套卡组看重什么”
from cards_britain import meteor_value

NAME = 'britain_meteor'
# 2026-10-15 用户卡组，两张第 2 西非旅换成雷达警报（原本配合研发牌，研发删了后鸡肋）
DECK_CODE = '%%2a|0B0i0mgvoooysQsTtVw8yJ;0l1VDJ0rqYy7ycyH;DLtTwbyd;'
HQ = 'card_location_tunis_city'
TITLE = '英澳流星'                      # 用户这次没给新名，沿用
COMMANDER = '阿尔托莉雅·潘德拉贡'
AVATAR = 'avatar_ats'                   # 本土辅助服务团
MAIN, ALLY = 'Britain', 'anzac'

# 过牌控制卡组：自保略重于打脸（靠回血和清场拖到流星够大）。
# 前线要抢：1 费突击队/溃兵上前线就能挡住对面占前线（用户指出），所以前线权重不低
W = {'my_hq': 1.1, 'en_hq': 1.0, 'threat': 1.2, 'front': 1.6, 'board': 1.0}
FRONT_PRESSURE = 0.45     # 我方前线单位下回合打总部的威胁：每点攻击（不超过对面总部血量）值多少分
# 加槽：AANS ×3 + 澳新军团精神 ×2，对局拖得长
SLOT_R, SLOT_V = 12, 1.4
HOLD_FRAC = 0.5
DANGER_DMG = 7
METEOR_V = 0.5            # 牌库里流星的价值系数（cards_britain.meteor_value 用）
# 爆牌一张的代价（默认 1.0）：这套靠反复抽回流星，丢掉的可能就是流星（实测 9 张满手时爆掉了流星）
BURN_V = 3.0
CORPS_V = 2.5             # 手牌上一个军司令部标记（打出时随机消灭一个敌方单位）的价值

E_, U_ = 'card_event_', 'card_unit_'
METEOR = U_ + 'meteor'


def _e(side):
    return 'left' if side == 'right' else 'right'


def _r(ctx, n=5):
    return min(ctx.get('R', 6), n)


def danger(ctx):
    """敌方下回合能打到总部 >= 7 点，或足以斩杀"""
    return ctx.get('T', 0) >= DANGER_DMG or ctx.get('T', 0) >= ctx.get('H', 20)


def _en_units(sim, side):
    return sim.units(_e(side))


def _in_hand(sim, side, name):
    return any(h.name == name for h in sim.side[side]['hand'])


def _sweep_hold(base, per=0.6):
    """清场指令：对面单位越多越值得留到合适时机（搜索会在单位多、能多杀时才打）"""
    return lambda sim, c, ctx: base + per * len(_en_units(sim, c.side))


def _forward_observers(sim, c, ctx):
    # 上回合没部署英国步兵时打出就少抽一张：多留一回合（先下个 1 费步兵）更值
    return _sweep_hold(1.0)(sim, c, ctx) + (0.0 if sim.memo.get('brit_last') else 0.8)


def _corps_command(sim, c, ctx):
    # 标记只有在对面有单位时才杀得到人：对面单位越多，越值得留到能标上两张好牌时打
    return 1.5 + 0.4 * min(4, len(_en_units(sim, c.side)))


def _chain(sim, c, ctx):
    import research_v
    return research_v.chain_hold(sim, c, ctx, card_hold, allow_option)


def _bletchley(sim, c, ctx):
    # 12 费：对面 5 费以下的单位全部回牌库顶 + 手牌里的小牌也回去
    cheap = sum(1 for u in _en_units(sim, c.side) if (u.cost or 0) <= 5)
    return 3.0 + 1.0 * cheap


HOLD = {
    # 过牌：保留价值低，有闲费就打。爆牌由模拟器自己罚（满 9 张再抽每张 -1，满手再罚）。
    # 原来手牌快满时 +3，结果护送航运/土地女孩越攒越多、手牌越满越不打（实测两局塞满手）
    E_ + 'the_land_girls': 1.2,
    E_ + 'protected_convoy': 0.6,
    E_ + 'production': 0.3,
    # 计划：2 费抽 1，手牌数不变。原来 0.8 时常被费用挤掉、一局攒到 3 张（用户指出），调低让它有闲费就打
    E_ + 'plan': 0.4,
    E_ + 'blast': 0.4,                    # 0 费 1 点：补刀用
    E_ + 'mi_5': 1.8,
    E_ + 'radar': 1.5,
    # 加槽/回血：价值由 slot_value 和总部估值算，越早越好
    E_ + 'aans': 0.0,
    E_ + 'anzac_spirit': 3.0,             # 8 费：清小兵 + 抽 2 + 2 槽，中期的核心回合
    # 皇家研发链
    # 研发链：每层留牌价值 = 往下最终能换到的产物价值 - 还要花的研发费用（research_v.chain_hold）
    # 原来扩展研发危险时 -3，等于危险时更想推研发（和本意相反）
    E_ + 'royal_research': lambda sim, c, ctx: _chain(sim, c, ctx),
    E_ + 'expanded_royal_research': lambda sim, c, ctx: _chain(sim, c, ctx),
    E_ + 'advanced_royal_research': lambda sim, c, ctx: _chain(sim, c, ctx),
    # 合成橡胶：只给能攻击的流星（cards_britain 限制目标）；手里有流星时留着等它
    E_ + 'synthetic_rubber': lambda sim, c, ctx: 2.0 + (3.0 if _in_hand(sim, c.side, METEOR) else 0),
    # 主动声呐：0 费压制全部敌方单位 + 对方手牌 +3 费
    E_ + 'active_sonar': lambda sim, c, ctx: 1.5 + 0.6 * min(4, len(_en_units(sim, c.side))),
    E_ + 'bletchley_park': _bletchley,
    # 解场
    E_ + 'forward_observers': _forward_observers,
    E_ + 'wave_after_wave': _sweep_hold(1.8),
    E_ + 'z_special_unit': 1.8,
    E_ + 'repel_the_attack': lambda sim, c, ctx: 1.5 + 0.8 * len(sim.side[_e(c.side)]['front']),
    E_ + 'corps_command': _corps_command,
    E_ + 'hms_formidable': _sweep_hold(2.0, 0.5),
    E_ + 'monty': 1.0,                    # 压制的价值由 threat 体现（被压制的单位下回合不算威胁）
    # 反制：不同反制可同时挂多张；挂上的收益在 cards_britain 里，有闲费就挂
    E_ + 'interception': 0.8,
    E_ + 'ultra': 2.0,
    E_ + 'radar_alert': 1.2,
    # 大单位
    U_ + 'queens_own': 4.0,               # 斩杀/压场：部署弹走挡路的守护，闪击奋战当回合打两次
    U_ + 'cameronians': 3.5,              # 越早下越好（每回合第二张指令抽 2）
    U_ + 'gordon_highlanders': 3.0,
}


def allow(sim, c, ctx):
    """打法层面禁止的出牌"""
    n = c.name
    my = sim.side[c.side]
    if n == METEOR:
        # 流星只在本回合还能打出去时才下（下了不攻击就是一张脆皮 1/1，美国还有反制战斗机攻击的指令）
        return my['kredits'] >= (c.cost or 0) + (c.op or 0)
    if n == E_ + 'repel_the_attack':
        # 撤退只对前线单位有用；不在最右边打出会结束回合（模拟里 turn_over，搜索会把它排在最后一步）
        return bool(sim.side[_e(c.side)]['front'])
    if n in (E_ + 'forward_observers', E_ + 'wave_after_wave', E_ + 'corps_command', E_ + 'hms_formidable'):
        return bool(_en_units(sim, c.side))
    if n == E_ + 'bletchley_park':
        return any((u.cost or 0) <= 5 for u in _en_units(sim, c.side))
    return True


def allow_attack(sim, u, t):
    """流星每次出场都很难得（要等很久才抽回来），要打总部；只有能一击打死目标时才打单位。
    实测：2/2 流星撞 3/6 守护，伤害白给（用户指出“坠机”）。守护挡着就捏在手里，等清掉守护再出"""
    if u.name != METEOR or t is None:
        return True
    return (u.atk or 0) >= (t.df or 0) + (t.armor or 0)


def allow_option(sim, c, t, k, ctx):
    """研发：前期/有压力选雷达（抽 1 + 总部 +4），后期没压力才往下研发；
    扩展研发手里有流星或槽多时才选合成橡胶以外的高级研发；布莱切利园 12 费，槽不够就选主动声呐"""
    n = c.name
    S = sim.side[c.side]['max_kredits']
    if n == E_ + 'royal_research':
        # 雷达（抽 1 + 总部 +4）是保命用的：没威胁、总部健康时走扩展研发（合成橡胶配流星）
        # 实测：开局没威胁就选了雷达（用户指出）
        safe = not danger(ctx) and sim.side[c.side]['hq'].df >= 14
        return k == (1 if safe else 0)
    if n == E_ + 'expanded_royal_research':
        return k == 0 or (S >= 10 and not danger(ctx) and not _in_hand(sim, c.side, METEOR))
    if n == E_ + 'advanced_royal_research':
        return k == 0 or S >= 12
    if n == E_ + 'hms_formidable':
        u = sim.find(t)
        return u is not None and (u.df or 0) >= 5          # 防御够高才值得变成攻击去打全场
    if n == E_ + 'z_special_unit':
        u = sim.find(t)
        # 打自己的单位只为最左边的总部 +5：危险时、或总部不满时才值得
        return u is None or u.side != c.side or danger(ctx) or sim.side[c.side]['hq'].df <= 14
    return True


def card_hold(sim, c, ctx):
    """一张牌本身的保留价值（不含军司令部标记）"""
    n = c.name
    if n == METEOR:
        # 手里的流星：下回合才能用（折扣），比打出去攻击（复制翻倍）的价值低，搜索会选择当回合打
        return 0.5 * meteor_value(sim, c.side, 2 * (c.atk or 0), 2 * (c.df or 0)) + 0.3 * (c.atk or 0)
    h = HOLD.get(n)
    if h is not None:
        return h(sim, c, ctx) if callable(h) else h
    if c.type == 'order':
        return 0.3 * (c.cost or 0)
    v = 0.5 * (c.atk or 0) + 0.5 * (c.df or 0) + (1.0 if c.guard else 0) + (c.armor or 0) + persist(sim, c, ctx)
    if n == U_ + 'middlesex_regiment':
        v += 1.5                          # 部署时给一张驻军
    elif n == U_ + 'no_46_commando':
        v += 1.2                          # 部署时给爆破 + 计划
    return HOLD_FRAC * v


def hold(sim, c, ctx):
    v = card_hold(sim, c, ctx)
    marks = getattr(c, 'corps', 0) or 0
    if marks:
        # 标记的价值：对面有单位才杀得到；打出这张牌本身越便宜，越快兑现
        v += marks * CORPS_V * (1.0 if _en_units(sim, c.side) else 0.6) * (1.0 if (c.cost or 0) <= 4 else 0.8)
    return v


def _front_pressure(sim, u):
    """在前线的地面单位下回合能打对面总部：步兵在支援线打不到总部，要先上前线（推进当回合不能攻击）。
    实测：可畏号后戈登 10/4 在支援线站了 3 回合，对面空场、每回合剩 11 点指挥点也没推进（用户指出）"""
    if u.loc != 'front' or not u.atk or u.type not in ('infantry', 'tank', 'artillery'):
        return 0.0
    return FRONT_PRESSURE * min(u.atk, max(0, sim.side[_e(u.side)]['hq'].df))


def persist(sim, u, ctx):
    """我方单位在场上的持续价值（攻防之外）"""
    n = u.name
    if n == METEOR:
        return -0.5 * ((u.atk or 0) + (u.df or 0)) - 1.0   # 留在场上极脆弱，攻击才有价值
    return _front_pressure(sim, u) + _persist(sim, u, ctx)


def _persist(sim, u, ctx):
    n = u.name
    if n == U_ + 'm3a3_honey_desert':
        return 0.5 * _r(ctx, 4) * 1.5                      # 这套每回合抽 2~3 张，每张总部 +1
    if n == U_ + 'cameronians':
        return 0.6 * _r(ctx, 3) * 2.0                      # 每回合第二张指令抽 2
    if n == U_ + 'garrison':
        return 0.4 * _r(ctx, 3)                            # 回合开始没被攻击就打总部 1 点（常被打，打折）
    if n == U_ + 'queens_own':
        return 1.0                                         # 奋战：每回合可攻击两次
    return 0.0


KEEP = {E_ + 'protected_convoy', E_ + 'the_land_girls', U_ + 'm3a3_honey_desert', E_ + 'aans',
        U_ + 'no_46_commando', U_ + 'middlesex_regiment', METEOR}


def keep(name, cost):
    """起手调度：留过牌、加槽、甜心、低费单位和流星（越早开始翻倍越好），其余换掉"""
    return name in KEEP


# 难度加成（native/buffs.py）：OPENING = 老兵及以上的起手候选池（随机挑 4~5 张）；CORE = 地狱档手牌少时打印的核心牌
OPENING = [E_ + 'protected_convoy', E_ + 'the_land_girls', U_ + 'm3a3_honey_desert', E_ + 'aans', U_ + 'meteor',
           U_ + 'no_46_commando', U_ + 'middlesex_regiment', E_ + 'radar_alert']
CORE = [U_ + 'meteor', E_ + 'the_land_girls', E_ + 'aans', U_ + 'cameronians', U_ + 'queens_own']
