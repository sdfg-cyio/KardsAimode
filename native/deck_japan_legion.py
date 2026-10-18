# 打法：日本 + 波兰 “汝即军团”（指挥部 马尼拉）
# 思路：情报引擎——塔尔努夫（每张情报牌送军团 + 抽 1）、军团（每张情报牌 +1+1）、雷兵团（每回合一次全体 +2+2）；
# 13 张情报牌（搜索第七联队/E14Y/京都联队/严惩/延长战线）同一回合先下引擎、再连打情报，让全场一起长；
# 低费单位守线、偷袭/摧枯拉朽/猛袭/挺进团/京都/第 15 狼解场；Ki-30、4TP、亡命之计、Ki-61 打脸收尾
# 卡牌效果在 cards_japan.py；这里只放“这套卡组看重什么”
import sim_rules as R
from effects import is_weather
from live_ai import guarded

NAME = 'japan_legion'
DECK_CODE = '%%38|5C6BhHphqDrks0tyuywXx3znzv;E7iDmatGzizs;7etK;E9pg'
HQ = 'card_location_manila'
TITLE = '日波军团'
COMMANDER = '玛莉亚·临光'
AVATAR = 'avatar_cadet_nurse'           # 学员护士
MAIN, ALLY = 'Japan', 'poland'

# 铺场卡组：场面最重要；前线要抢（军团、塔尔努夫都是步兵，站前线才能打总部）
W = {'my_hq': 1.0, 'en_hq': 1.0, 'threat': 1.2, 'front': 1.8, 'board': 1.1}
SLOT_R, SLOT_V = 10, 1.2
HOLD_FRAC = 0.5
DANGER_DMG = 7
EPHEMERAL = {'card_unit_4tp'}            # 达努塔送的 4TP：回合结束被消灭，每回合都该用掉
FRONT_PRESSURE = 0.35                    # 前线地面单位下回合打总部的威胁（每点攻击）

E_, U_ = 'card_event_', 'card_unit_'
TARNOW, THUNDER, LEGION = U_ + '16th_tarnow_regiment', U_ + 'thunder_division', U_ + 'legion_pol'
STRETCH = E_ + 'stretch_the_line'


def _e(side):
    return 'left' if side == 'right' else 'right'


def _r(ctx, n=5):
    return min(ctx.get('R', 6), n)


def danger(ctx):
    return ctx.get('T', 0) >= DANGER_DMG or ctx.get('T', 0) >= ctx.get('H', 20)


def _en_units(sim, side):
    return sim.units(_e(side))


def _intel_in_hand(sim, side):
    """手里还有几张情报牌（延长战线也算）：引擎单位的持续价值随它上升"""
    return sum(1 for h in sim.side[side]['hand'] if getattr(h, 'intel', 0) or h.name == STRETCH)


def _rv():
    import research_v
    return research_v


def _chain(sim, c, ctx):
    return _rv().chain_hold(sim, c, ctx, hold, allow_option)


def _long_lance_v(sim, c, ctx):
    """氧气鱼雷留牌价值：平时 1.0；有马上能打总部的大单位时按场上最值得杀的目标加"""
    if not _rv().big_hitter(sim, c.side):
        return 1.0
    return 1.5 + 0.5 * max([0.5 * ((u.atk or 0) + (u.df or 0)) for u in _en_units(sim, c.side)] or [0])


def _sup_full(sim, side):
    return len(sim.side[side]['support']) + (sim.extra_sup if side == sim.me else 0) >= 4


# ---------- 预报：先选天气（0 晴 / 1 雨 / 2 风暴），再选 2/4/6 费（0/1/2） ----------
# 用户确认：选中的天气牌下回合抽完牌后才进手牌；每回合只能打一张天气牌；预报必须选，但两次选择都由我们定。
# 做法：每种天气每一档有 3 种变体（共 27 张），各按“下回合拿到它值多少”估分；选档时按 3 种变体的平均值，挑最高的
WEATHER_DISCOUNT = 0.7     # 下回合才拿到、局面会变：打折


def _attackers(sim, side):
    """下回合大概能攻击的我方单位（本回合在场的，加 1 个下回合新下的）"""
    return [u for u in sim.units(side) if (u.atk or 0) > 0 and not u.cant_attack] + [None]


def _weather_values(sim, side):
    """[天气][档位] -> 下回合拿到这张天气牌的粗估价值（已扣它的费用）"""
    my, en = sim.side[side], sim.side[_e(side)]
    mine, foes = sim.units(side), sim.units(_e(side))
    H, E = my['hq'].df, en['hq'].df
    T = (sim.ctx or {}).get('T', 0)
    # 总部加防的价值：按总部估值曲线（10 血以下每点 1 分），被斩杀威胁时再加倍
    low = (1.0 if H <= 10 else 0.5) * (2.0 if T >= H - 2 else 1.0)
    att = _attackers(sim, side)
    n_air = sum(1 for u in mine if u.type in ('fighter', 'bomber'))
    hand_units = [h for h in my['hand'] if h.type in ('infantry', 'tank', 'artillery', 'fighter', 'bomber')]
    room = max(0, 4 - len(my['support']))
    small = sum(1 for u in foes if 0 < (u.df or 0) <= 2)
    top2 = lambda us: sum(sorted(((u.cost or 0) for u in us), reverse=True)[:2])
    kr = 0.4                                            # 每点费用的机会成本
    hit = min(1.0, 0.25 * len(foes))                    # 单位加防只在会被打时有用（对面空场时几乎不值）
    inf = [u for u in mine if u.type == 'infantry']
    foe_v = sum(0.5 * ((u.atk or 0) + (u.df or 0)) for u in foes)
    big_foe = max([0.5 * ((u.atk or 0) + (u.df or 0)) + 0.2 * (u.cost or 0) for u in foes] or [0])
    # 每档 3 种变体（用户指出：同名天气牌效果各不相同；文字取自客户端 Game.locres）。
    # 每次攻击多打的伤害按 0.6 分算（不是每下都打总部）；对面同样吃到的加成按对面单位数扣
    sunny = [
        [0.6 * (2 * len(att) + n_air) - 1.0 * len(foes),                       # 全体 +2 攻（空军 +3）
         0.6 * len(att) + 0.8 * len(mine),                                     # 友方 +1 攻、-1 行动花费
         0.6 * 2 * 2 * min(2, len(hand_units))],                               # 本回合部署时随机打攻击力点
        [0.6 * 3 * len(att) - 1.2 * len(foes) - 0.5 * len(att),                # 全体 +3 攻，没攻击的友方被压制
         max([0.5 * ((u.atk or 0) + (u.df or 0)) for u in mine] or [0]),       # 复制 1 个友方单位
         0.6 * 2 * min(2, len(hand_units)) + 1.0 * min(2, len(hand_units))],   # 新上场 +2 攻和闪击
        [sum(0.5 * ((h.atk or 0) + (h.df or 0)) for h in hand_units[:room]) * 0.6,   # 手里单位全部上场
         2.5 * len(mine),                                                      # 友方全体 +3+2
         0.6 * sum((u.atk or 0) for u in mine if u.type in ('fighter', 'bomber'))]]   # 空军打谁都打总部
    rain = [
        [6 * 0.5 * low + 0.3 * min(len(mine), 3),                              # 6 点防御随机分配
         0.6 * len(foes) * hit + 0.3 * len(foes),                              # 敌方单位 -1 攻
         0.5 * big_foe + R.DRAW_V],                                            # 抑制 1 个单位 + 抽 1
        [3 * low + 0.5 * hit * sum(3 if u.type == 'infantry' else 2 for u in mine) + (3.0 if H <= 6 else 0),
         0.8 * sum((u.atk or 0) for u in foes) * 0.5 + (2.0 if T >= H - 2 else 0),   # 压制全部敌方单位
         -9.0],                                       # 抽 3 选 1 弃：选弃牌的动作代理不会发，不选
        [(top2(foes) - top2(mine)) * 0.6,                                      # 双方移除 2 张最贵（会带走引擎）
         0.6 * (foe_v - 2 * len(foes)) - 0.6 * (sum(0.5 * ((u.atk or 0) + (u.df or 0)) for u in mine)
                                                - 2 * len(mine)),             # 全体变 2/2
         2.0 * len(inf) + 0.6 * 2 * len(inf)]]                                 # 友方步兵 +2+2 并能再次行动
    storm = [
        [3 * 0.8 + 1.0 * min(small, 3) + (4.0 if E <= 3 else 0),               # 随机 3 点（可能斩杀）
         0.6 + 0.8,                                                            # 敌方手牌 +1 费，友方 -1 费
         (2.5 if foes else 0) + 1.0 * sum(1 for u in foes if (u.df or 0) <= 5)],   # 随机 1 个敌方单位 5 点
        [0.8 * (len(en['hand']) - len(my['hand'])),                            # 双方手牌拉平
         (big_foe + 1.0) if foes else 0,                                       # 撤退 1 个 + 随机消灭 1 个
         3 * 0.8 + 0.8 * min(2, len(foes)) * 1.5 + (3.0 if E <= 3 else 0)],    # 3 + 2 + 1 点
        [3 * 1.5 - 0.8 * (len(my['hand']) + 3) * low,                          # 抽 3，总部扣手牌数
         1.5 * len(en['front']) - 1.5 * len(my['front']),                      # 所有单位撤退（双方）
         (big_foe + 1.0) if foes else 0]]                                      # 6 点 + 相邻 2 点
    cost = (2 * kr, 4 * kr, 6 * kr)
    return [[[x - cost[k] for x in pool[k]] for k in range(3)] for pool in (sunny, rain, storm)]


def forecast_choice(sim, side):
    """返回 (天气, 档位, 价值)。第二次三选一给的是这一档里随机的一种变体，选档时只能按 3 种变体的平均值估"""
    v = _weather_values(sim, side)
    avg = lambda w, k: sum(v[w][k]) / 3
    w, k = max(((w, k) for w in range(3) for k in range(3)), key=lambda p: avg(*p))
    return w, k, WEATHER_DISCOUNT * max(0.5, avg(w, k))


def _tarnow_v(sim, u, ctx):
    # 塔尔努夫十分珍贵（用户强调）：没了就不能无限招军团。每张剩余情报牌 = 一个军团 + 抽 1
    return 3.0 + 1.6 * min(5, _intel_in_hand(sim, u.side) + 1) * (0.3 if _sup_full(sim, u.side) else 1.0)


def exposure(sim, u, loc=None):
    """u 下个敌方回合被打死的粗估概率（0~1）。loc 可假设它站在哪条线（手里的牌按“下到支援线”估）。
    能打到它的：敌方火炮/轰炸机（无视守护）、战斗机、前线陆军；敌方支援线上的坦克能移动后攻击。
    被相邻守护挡住时只算火炮/轰炸机。另加一点“手里有解场”的风险"""
    side, e = u.side, _e(u.side)
    loc = (loc or u.loc or '').split('_')[0]           # 'support_right' -> 'support'
    line = sim.side[side][loc] if loc in ('support', 'front') else []
    hq = sim.side[side]['hq'] if loc == 'support' else None
    # 线上没有守护单位就谈不上挡（guarded() 遇到新部署、没格子号的牌会保守地全算被守护）
    shielded = not u.guard and u in line and any(x.guard for x in line) and id(u) in guarded(line, hq)
    dmg = 0
    for x in sim.units(e):
        if x.pinned or x.cant_attack or not x.atk:
            continue
        a = (x.atk or 0) - sim.temp.get(x.id, 0)
        if x.type in ('artillery', 'bomber'):
            dmg += a
        elif shielded:
            continue
        elif x.type in ('fighter', 'tank') or (x.loc or '').startswith('front') \
                or (loc == 'front' and x.type == 'infantry'):
            dmg += a
    df = max(1, u.df or 1)
    risk = min(1.0, dmg / df) ** 1.5
    n_hand = len(sim.side[e]['hand'])
    return min(1.0, risk + (0.12 if n_hand >= 3 else 0.05 * n_hand))


HOLD = {
    # 情报指令
    STRETCH: lambda sim, c, ctx: 1.0 + (3.0 if _sup_full(sim, c.side) else 0),   # 支援线满了就送不出军团
    E_ + 'punish': 1.2,
    # 解场
    E_ + 'surprise_attack': 0.6,
    E_ + 'overpower': 1.5,
    E_ + 'ferocious_assault': lambda sim, c, ctx: 1.5 + (1.0 if sim.side[c.side]['max_kredits'] < 6 else 0),
    E_ + 'desperate_measures': lambda sim, c, ctx: 2.0 + 0.4 * len(_en_units(sim, c.side)),
    E_ + 'balloon_bombs': lambda sim, c, ctx: 1.0 + 0.6 * min(4, len(_en_units(sim, c.side))),   # 压制全部敌方
    # 氧气鱼雷：0 费消灭，攻 <= 3 还抽 2。用户：权重压低，除非有马上能对总部打出大伤害的单位（鱼雷给它清路）
    E_ + 'long_lance': lambda sim, c, ctx: _long_lance_v(sim, c, ctx),
    # 过牌/回血
    E_ + 'anders_army': lambda sim, c, ctx: 0.6 + (3.0 if sim.side[c.side]['hq'].df <= 8 else 0),
    E_ + 'island_fighting': lambda sim, c, ctx: 3.0 if not danger(ctx) else 1.0,   # 危险时才打
    # 研发
    # 研发链：每层留牌价值 = 往下最终能换到的产物价值 - 还要花的研发费用（research_v.chain_hold）
    # 原来扩展研发危险时 -3，等于危险时更想推研发（和本意相反）
    E_ + 'imperial_research': lambda sim, c, ctx: _chain(sim, c, ctx),
    E_ + 'expanded_imperial_rnd': lambda sim, c, ctx: _chain(sim, c, ctx),
    E_ + 'advanced_imperial_rnd': lambda sim, c, ctx: _chain(sim, c, ctx),
    E_ + '7075_aluminium': 4.0,            # 三张 0 费零战，被消灭回手 0 费复制：持续的铺场/换子
    E_ + 'imperial_weapon_no_2': 7.0,      # 牌库顶四张 0 费橘花（部署行动都 0 费）：后期四回合连续出大飞机
    # 天气牌（预报来的）：热浪要在攻击前打；骤雨危险时打
    E_ + 'sunny2_heatwave': 1.2, E_ + 'rain2_deluge': 1.2, E_ + 'storm2_thunderstorm': 1.2,
    E_ + 'sunny3_jungle_fever': 2.0, E_ + 'rain3_torrential_rain': 2.0, E_ + 'storm3_tropical_storm': 1.0,
    E_ + 'sunny4_scorching_sun': 3.0, E_ + 'rain4_monsoon_rain': 3.0, E_ + 'storm4_cyclone': 1.0,
    # 引擎单位：越早下越好（保留价值低）
    # 塔尔努夫留在手里 = 等一个能当回合接情报、有军团挡刀的回合再下（单独空放会被直接打死）
    TARNOW: lambda sim, c, ctx: 0.5 * _tarnow_v(sim, c, ctx),
    THUNDER: 3.0,
    U_ + 'kyoto_regiment': 2.0,            # 部署移除是解场：等有值得移除的大单位
    U_ + '15th_wolves_regiment': 2.5,
    U_ + 'ki_61_i_tei': 3.0,
}


def _intel_cost_min(sim, side, skip=None):
    cs = [h.cost or 0 for h in sim.side[side]['hand'] if h is not skip and (getattr(h, 'intel', 0) or h.name == STRETCH)]
    return min(cs) if cs else None


def allow_attack(sim, u, t):
    """塔尔努夫是引擎不是打手（实测 252771：拿它去撞 5/4 的狙击兵，剩 1 血被打死）：
    只打总部，或者能打死对方、自己还剩一半以上血的目标"""
    if u.name != TARNOW or t is None or t.type == 'location':
        return True
    from live_ai import combat
    dt, da, ambushed = combat(u, t)
    return not ambushed and dt >= (t.df or 0) and (u.df or 0) - da >= 3


def allow_move(sim, u):
    """塔尔努夫不上前线（前线什么都打得到它）；对方总部快死、上去能打脸收尾时例外"""
    if u.name != TARNOW:
        return True
    return sim.side[_e(u.side)]['hq'].df <= (u.atk or 0)


def allow(sim, c, ctx):
    n = c.name
    en = _en_units(sim, c.side)
    if n == TARNOW and sim.side[c.side]['max_kredits'] < 8:
        # 用户：塔尔努夫下得太早，下了也空着、下回合被直接打死。
        # 8 槽之前要当回合接得上至少一张情报牌（下了马上送军团挡刀、抽牌）才下；手里没情报牌就等
        k = _intel_cost_min(sim, c.side, skip=c)
        if k is None or sim.side[c.side]['kredits'] < (c.cost or 0) + k:
            return False
    if n == STRETCH:
        return not _sup_full(sim, c.side)
    if n == E_ + 'rain3_torrential_rain3':
        return False                          # 抽 3 选 1 弃：选弃牌的动作代理还不会发，打了会卡住
    if n == E_ + 'island_fighting':
        return danger(ctx) or sim.side[c.side]['hq'].df <= 10
    if n == E_ + 'anders_army':
        return sim.side[c.side]['hq'].df > 6
    if n == E_ + 'desperate_measures':
        # 少一个槽：只在能多杀或斩杀时打
        e = sim.side[_e(c.side)]['hq'].df
        return e <= 2 or sum(1 for u in en if (u.df or 0) <= 2) >= 2
    return True


def allow_option(sim, c, t, k, ctx):
    n = c.name
    S = sim.side[c.side]['max_kredits']
    if n == E_ + 'imperial_research':
        return k == (0 if danger(ctx) else 1)      # 危险时选气球炸弹（压制全部），否则扩展研发
    if n == E_ + 'expanded_imperial_rnd':
        # 氧气鱼雷只在有压力、或有大单位等着它清路打总部时选；否则往高级研发走（原来 10 槽前只能选鱼雷）
        return k == 1 or danger(ctx) or _rv().big_hitter(sim, c.side)
    if n == E_ + 'advanced_imperial_rnd':
        return k == 0 or S >= 10                   # 二号兵器 12 费：10 槽起就可以先拿着
    if n == E_ + 'ferocious_assault':
        x = sim.find(t)
        # 会掉槽（目标攻击 > 槽数）时只打值得的目标
        return x is None or (x.atk or 0) <= S or (x.atk or 0) + (x.df or 0) >= 9
    if n == E_ + 'overpower':
        x = sim.find(t)
        return x is None or not any(u.name == x.name for u in sim.units(c.side))   # 别连带消灭自己的同名单位
    if n == U_ + '15th_wolves_regiment':
        x = sim.find(t)
        if x is not None and x.side == c.side:
            # 变自己的单位：只变要没的（4TP）或不值钱的，换抽 2
            return x.name == U_ + '4tp' or (x.atk or 0) + (x.df or 0) <= 3
        return x is None or (x.atk or 0) + (x.df or 0) >= 7
    return True


def hold(sim, c, ctx):
    return _hold(sim, c, ctx) + _intel_hold(sim, c)


def _hold(sim, c, ctx):
    n = c.name
    h = HOLD.get(n)
    if h is not None:
        return h(sim, c, ctx) if callable(h) else h
    if is_weather(n) and n not in HOLD:
        return 0.3 * (c.cost if c.cost and c.cost < 20 else 2)   # 天气牌变体（*2/*3）：每回合只能打一张，有闲费就打
    if c.type == 'order':
        return 0.3 * (c.cost or 0)
    v = 0.5 * (c.atk or 0) + 0.5 * (c.df or 0) + (1.0 if c.guard else 0) + (c.armor or 0) + persist(sim, c, ctx)
    if n == U_ + 'type94_tk':
        v += 1.0                               # 部署给一张偷袭
    return HOLD_FRAC * v


def _front_pressure(sim, u):
    if u.loc != 'front' or not u.atk or u.type not in ('infantry', 'tank', 'artillery'):
        return 0.0
    return FRONT_PRESSURE * min(u.atk, max(0, sim.side[_e(u.side)]['hq'].df))


def persist(sim, u, ctx):
    return _front_pressure(sim, u) + _persist(sim, u, ctx)


def _body(u):
    return 0.5 * (u.atk or 0) + 0.5 * max(0, u.df or 0) + (1.0 if u.guard else 0)


ENGINES = (TARNOW, THUNDER)


def _engine_pending(sim, side):
    """手里有塔尔努夫/雷兵团、场上还没有、且槽数快够下了：这时情报牌留着和引擎一起爆发"""
    my = sim.side[side]
    if any(u.name in ENGINES for u in sim.units(side)):
        return 0
    S = my['max_kredits']
    return sum(1 for h in my['hand'] if h.name in ENGINES and (h.cost or 0) <= S + 1)


def _intel_hold(sim, c):
    """情报牌的保留加成：引擎快下场时留着（一张情报配塔尔努夫 = 军团 + 抽 1 + 全军团 +1+1）；
    手牌快满或已经在场上有引擎时不加（那时就该打）"""
    if not (getattr(c, 'intel', 0) or c.name == STRETCH):
        return 0.0
    k = _engine_pending(sim, c.side)
    if not k or R.hand_room(sim, c.side) <= 1:
        return 0.0
    return 1.5 + 0.5 * (k - 1)


def _thunder_v(sim, u):
    mine = len([x for x in sim.units(u.side) if x is not u])
    return 1.0 + 0.8 * min(4, mine) * min(2, _intel_in_hand(sim, u.side))


def _persist(sim, u, ctx):
    n = u.name
    # 引擎单位的长期价值要“活到下回合”才拿得到：按被打死的概率打折。
    # 这样单独空放塔尔努夫（没军团挡、对面有能打到它的单位）不如留在手里，等能当回合接情报牌时再下
    # 本体被打死也要扣（场面分只按当前攻防算，不管它活不活得过下回合）
    if n == TARNOW:
        p = exposure(sim, u)
        return _tarnow_v(sim, u, ctx) * (1 - 0.8 * p) - 0.7 * p * _body(u)
    if n == THUNDER:
        p = exposure(sim, u)
        return _thunder_v(sim, u) * (1 - 0.6 * p) - 0.5 * p * _body(u)
    if n == LEGION:
        return 0.5 * min(4, _intel_in_hand(sim, u.side))       # 每张情报牌 +1+1
    if n == U_ + 'danuta':
        return 1.5 * _r(ctx, 4)                                # 每回合一个 3/3 闪击 4TP
    if n == U_ + 'kyoto_regiment':
        x = getattr(u, 'held', None)
        return 1.0 + (0.5 * (0.5 * ((x.atk or 0) + (x.df or 0))) if x is not None else 0)   # 活着才压住对方单位
    if n == U_ + '1st_recon':
        return 0.5                                             # 伏击 + 亡计可能抽牌
    if n == U_ + '238th_regiment':
        return 1.0 if sim.side[u.side]['max_kredits'] <= 3 else 0.0
    if n == U_ + 'ki_61_i_tei':
        return 1.5                                             # 亡计：对方总部 2、我方 +2
    if n == U_ + 'kawanishi_h8k':
        return 0.8 * min(2, sum(1 for h in sim.side[u.side]['hand'] if h.name == U_ + 'yokosuka_e14y'))
    if n == U_ + '20th_infantry_regiment':
        return 0.0
    return 0.0


KEEP = {U_ + '1st_recon', U_ + 'type94_tk', U_ + '238th_regiment', STRETCH, U_ + 'dinah_iii', TARNOW,
        U_ + 'danuta', U_ + '2nd_raiding_brigade'}


def keep(name, cost):
    """起手调度：留低费守线、延长战线、塔尔努夫（第 4 回合起引擎），大单位/回血牌换掉"""
    return name in KEEP
