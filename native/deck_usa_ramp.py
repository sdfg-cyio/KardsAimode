# 打法：美国 + 英国 加费控制（指挥部 华盛顿）
# 思路：前期加费、过牌、低费单位守支援线；中期用解场压住对面；后期大单位/曼哈顿收尾
# 这里只放“这套卡组看重什么”的数值；规则在 sim_rules.py，卡牌效果在 cards_*.py（引擎 effects.py）
NAME = 'usa_ramp'
DECK_CODE = '%%52|bCbEbncpcPcZdkfGmPtYv6vXwdyv;0lbIbPbqcWv7w8081w;1V;bK'
HQ = 'card_location_washington_waw'
COMMANDER = '凯伊'                      # 对局里 AI 的玩家名
AVATAR = 'avatar_rosie'                 # 头像（游戏自带的 avatar_* 物品 id）：铆工罗茜
MAIN, ALLY = 'USA', 'britain'

# 评分权重：控制卡组，自保比打脸重要
W = {'my_hq': 1.2, 'en_hq': 0.8, 'threat': 1.3, 'front': 1.0, 'board': 1.0}
# 加槽估值：加费卡组对局拖得长，按 12 回合算，1 个指挥点值 1.5 分（第 1~2 回合的战争机器应优先于低费单位）
SLOT_R, SLOT_V = 12, 1.5
HOLD_FRAC = 0.5        # 手里的单位按“上场后价值”的这个比例算保留价值：早下只赚节奏，不是白赚整张牌

E_ = 'card_event_'
U_ = 'card_unit_'


def _r(ctx, n=5):
    return min(ctx.get('R', 6), n)


# 手牌保留价值：打出这张牌的收益必须超过它，才会打。指令按“留着以后用”的价值估
HOLD = {
    E_ + 'the_war_machine': 0.0,          # 加槽价值由 slot_value 算：12 槽以下越早越值，10~11 槽几乎没用，12 以上又有用
    E_ + 'war_bonds': 1.5,
    # 研发链：每层的留牌价值 = 往下最终能换到的产物价值 - 还要花的研发费用（research_v.chain_hold）。
    # 原来扩展研发危险时 -6，等于危险时最想推研发（和本意相反）；第一层危险时选深水炸弹改在 allow_option
    E_ + 'us_military_research': lambda sim, c, ctx: _chain(sim, c, ctx),
    E_ + 'expanded_us_research': lambda sim, c, ctx: _chain(sim, c, ctx),
    # 高级研发：也走研发链（青霉素 / 两张曼哈顿取较大者 - 9 费折扣）；
    # 原来固定 3.0（只在对面 <= 14 血时 +4），一直比增压舱低，AI 几乎不开后期（用户指出）
    E_ + 'advanced_us_research': lambda sim, c, ctx: _chain(sim, c, ctx),
    # 深水炸弹是保命牌：只在危险时才允许打（见 allow），平时留在手里的价值 = 以后救命一次
    E_ + 'depth_charges': 3.0,
    # 增压舱：0 费，给一张 B-29（6 点随机分配）+ 随机消灭一个敌方单位
    E_ + 'pressurized_cabin': lambda sim, c, ctx: 2.5 + (1.5 if sim.units('left' if c.side == 'right' else 'right') else 0),
    # 青霉素：手牌少/总部低时更值；曼哈顿：按能打死的敌方单位数和斩杀线加权（research_v）
    E_ + 'penicillin': lambda sim, c, ctx: _rv().penicillin_v(sim, c.side, ctx),
    E_ + 'manhattan_project': lambda sim, c, ctx: _rv().manhattan_v(sim, c.side, ctx),
    E_ + 'for_freedom': 0.8,
    E_ + 'convoy_175': 1.5,
    E_ + 'mi_5': 1.5,
    E_ + 'supply_shipment': 1.0,
    E_ + 'combined_chiefs_of_staff': 2.5,
    E_ + 'uss_missouri': 3.0,
    E_ + 'death_from_above': 2.5,
    E_ + 'strategic_bombing': 3.0,
    E_ + 'naval_battle': 4.0,
    E_ + 'seaborne_invasion': 3.5,
    # 中立衍生/发现牌
    E_ + 'blast': 0.6,                    # 0 费 1 点伤害：能补刀、拆残血或配合换子时才用
    E_ + 'production': 0.6,               # 0 费 +1 指挥点：只有多出的这 1 点能用掉时才打
    E_ + 'plan': 1.2,                     # 2 费抽 1 张
    U_ + 'the_professionals': 1.0,        # 越早打出越好：亡计让牌库单位变强
    U_ + 'b_29_super_fortress': 3.0,
    U_ + 'm26_pershing': 3.0,
    U_ + 'lancaster': 2.0,
}


def _pathfinder_can_kill(sim, side):
    """327 探路者部署时 2 点伤害能否消灭一个敌方单位（对方海鹰每张 -1）"""
    e = 'left' if side == 'right' else 'right'
    dmg = 2 - sim.count(e, U_ + 'seahawk')
    return any(not u.covert and not u.smoke and 0 < (u.df or 0) <= dmg for u in sim.units(e))


DANGER_DMG = 7        # 玩家经验：对方下回合至少能打总部 7~8 点时才开深水炸弹


def danger(ctx):
    """回合开始时的危险判断：敌方下回合能打到总部的伤害 >= 7，或足以斩杀"""
    return ctx.get('T', 0) >= DANGER_DMG or ctx.get('T', 0) >= ctx.get('H', 20)


def allow(sim, c, ctx):
    """打法层面禁止的出牌（规则上合法，但这套卡组不该这么用）"""
    if c.name == E_ + 'depth_charges':
        return danger(ctx)
    return True


FREEDOM_MAX_OP = 2       # 为了自由不给行动费 3 以上的单位（593 通信连 0/4 行动费 4 这种，+1+1 没意义）


def allow_option(sim, c, t, k, ctx):
    """研发第一层：危险时选深水炸弹（当回合烟幕 + 加槽），否则往下研发；其余按产物价值选。
    为了自由：不给行动费高的单位"""
    n = c.name
    if n == E_ + 'us_military_research':
        return k == (0 if danger(ctx) else 1)
    if n == E_ + 'expanded_us_research':
        # 增压舱只在有压力、或还没到 9 槽（高级研发 9 费下回合也打不出）时选；后期没压力就开高级研发
        return k == 1 or danger(ctx) or sim.side[c.side]['max_kredits'] < 8
    if n == E_ + 'for_freedom':
        u = sim.find(t)
        return u is None or (u.op or 0) <= FREEDOM_MAX_OP
    return True


def _rv():
    import research_v
    return research_v


def _chain(sim, c, ctx):
    return _rv().chain_hold(sim, c, ctx, hold, allow_option)


def hold(sim, c, ctx):
    if c.name == U_ + '327th_pathfinders':
        # 只有这一次升老兵的机会：打不死人时留着（保留价值高），能打死时保留价值低、倾向立刻用
        base = HOLD_FRAC * (0.5 * (c.atk or 0) + 0.5 * (c.df or 0))
        return base + (0.0 if _pathfinder_can_kill(sim, c.side) else 5.0)
    h = HOLD.get(c.name)
    if h is not None:
        return h(sim, c, ctx) if callable(h) else h
    if c.type == 'order':
        return 0.3 * (c.cost or 0)
    # 单位：上场后价值（攻防 + 关键词 + 持续价值）的一部分
    v = 0.5 * (c.atk or 0) + 0.5 * (c.df or 0) + (1.0 if c.guard else 0) + (c.armor or 0) + persist(sim, c, ctx)
    if c.name == U_ + 'middlesex_regiment':
        v += 2.0                          # 部署时给一张卫戍
    return HOLD_FRAC * v


def persist(sim, u, ctx):
    """我方单位在场上的持续价值（攻防之外）"""
    n = u.name
    en = [x for x in sim.units('left' if u.side == 'right' else 'right') if x.atk]
    if n == U_ + 'm3a3_honey_desert':
        return 0.4 * _r(ctx)              # 每抽 1 张牌指挥部 +1
    if n == U_ + 'garrison':
        return 0.3 * _r(ctx)              # 没被攻击时每回合打对面指挥部 1 点（常被攻击，打折）
    if n == U_ + 'middlesex_regiment':
        return 0.5
    if n == U_ + 'us_signal_corps':
        return 0.2 * _r(ctx) * max(1, len(en))
    if n == U_ + 'seahawk':
        bombers = any(x.type == 'bomber' for x in en)
        return 0.2 * _r(ctx) * max(1, len(en)) + (2.0 if bombers else 0)
    if n == U_ + 'tigercat':
        room = len(sim.side[u.side]['support']) < 4
        return 2.5 * min(ctx.get('R', 6), 3) * (1.0 if room else 0.2)   # 每回合刷一架 SBD 无畏
    if n == U_ + 'm26_pershing' and u.loc == 'front':
        return 3.0                        # 在前线时我方指挥部不会降到 1 以下
    if n == U_ + 'm18_hellcat':
        tanks = any(x.type == 'tank' for x in en)
        return 1.5 if tanks else 0
    if getattr(u, 'vet', False) or n == U_ + '327th_pathfinders_vet':
        return 3.5                        # 老兵探路者：闪击，且每回合开始随机让一个敌方单位撤退
    return 0.0


KEEP = {E_ + 'the_war_machine', E_ + 'us_military_research', U_ + 'middlesex_regiment',
        U_ + 'm3a3_honey_desert', U_ + 'us_signal_corps', U_ + 'seahawk', E_ + 'for_freedom'}


def keep(name, cost):
    """起手调度：留低费加费/守线牌，大单位和解场换掉"""
    return name in KEEP or (cost or 0) <= 2
