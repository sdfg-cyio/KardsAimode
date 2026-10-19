# 新 AI 决策：输入真实场面（live.Live.snapshot() 的结果），输出一个动作；纯函数，可离线测试
# 原则：宁可少做，不做非法动作。拿不准的一律不做（最坏只是结束回合）。
import card_rules
GROUND = ('infantry', 'tank', 'antitank', 'tankdestroyer', 'antiair')  # 能上前线、按战线规则攻击
RANGED = ('artillery', 'bomber', 'fighter')                         # 可攻击任意战线
AIR = ('fighter', 'bomber')
NO_COUNTER = ('artillery', 'bomber')   # 攻击方为这些时不吃反击；被攻击的这些也不反击
SUPPORT_MAX = 4                         # 支援线单位上限（指挥部占 1 格，共 5 格）
OP_WEIGHT = 0.6                         # 每点行动费用折算的分数代价
FRONT_MAX = 5


def other(s):
    return 'right' if s == 'left' else 'left'


def value(c):
    """单位价值：攻防 + 费用"""
    return (c.atk or 0) * 1.0 + (c.df or 0) * 0.8 + (c.cost or 0) * 0.5


def ready(c, turn):
    """本回合能否行动（移动/攻击）：交给客户端的判断，再加本地保守条件"""
    if c.pinned or c.cant_attack is None:
        return False
    return True


IGNORE_GUARD = ('artillery', 'bomber')   # 火炮、轰炸机无视守护


def guarded(line, hq=None):
    """返回该战线上被守护的目标集合（卡对象 id()；'HQ' 表示指挥部）
    规则：守护单位只守护左右相邻的格子；指挥部在支援线上占一格，只有守护单位紧挨着它时才被守护；
    守护单位自身不被守护。按格子号排序判断相邻；格子号缺失或重复（读数不可靠）时保守处理：
    整条线的非守护单位和指挥部都算被守护（最坏少打一次，不会违规）。"""
    guards = [c for c in line if c.guard]
    if not guards:
        return set()
    cells = list(line) + ([hq] if hq is not None else [])
    slots = [getattr(c, 'slot', None) for c in cells]
    if None in slots or len(set(slots)) != len(slots):
        out = {id(c) for c in line if not c.guard}
        return out | ({'HQ'} if hq is not None else set())
    order = sorted(cells, key=lambda c: c.slot)
    out = set()
    for i, c in enumerate(order):
        if c is hq or not c.guard:
            continue
        for j in (i - 1, i + 1):
            if 0 <= j < len(order) and not getattr(order[j], 'guard', False):
                out.add('HQ' if order[j] is hq else id(order[j]))
    return out


# 规则上能打、但 AI 不该打的目标：BM-13N 被攻击时撤退回手牌，打它只是白交一次攻击
DONT_ATTACK = {'card_unit_bm_13n_us6'}


def worth_attacking(t):
    return t is None or t.name not in DONT_ATTACK


def attack_targets(st, me, a):
    """攻击者 a 的合法目标：[(目标卡 或 None=敌方指挥部)]"""
    en = st['side'][other(me)]
    e_front = [c for c in en['front'] if not c.smoke]
    e_sup = [c for c in en['support'] if not c.smoke]
    in_front = a.loc == 'front'
    # 可打的战线
    lines = []   # [(该线可选目标, 是否含指挥部)]
    if a.type in RANGED:
        lines = [(e_front, False), (e_sup, True)]
    elif in_front:
        lines = [(e_sup, True)]
    else:
        lines = [(e_front, False)]
    out = []
    hq_smoke = bool(en['hq'] is not None and getattr(en['hq'], 'smoke', False))   # 指挥部烟幕（深水炸弹）
    for cards, has_hq in lines:
        # 原始（含烟幕）战线用于判断守护相邻关系
        raw = en['support'] if has_hq else en['front']
        cand = list(cards) + ([None] if has_hq and not hq_smoke else [])
        if a.type not in IGNORE_GUARD:
            g = guarded(raw, en['hq'] if has_hq else None)
            cand = [t for t in cand if ('HQ' if t is None else id(t)) not in g]
        if a.type == 'bomber':
            # 轰炸机：该战线有敌方战斗机时只能选战斗机
            fighters = [c for c in cards if c.type == 'fighter']
            if fighters:
                cand = fighters
        out += cand
    return out


def combat(a, t):
    """确定性战斗结算：返回 (目标受到伤害, 攻击方受到伤害, 攻击方是否被伏击先手消灭)"""
    dmg_t = max(0, (a.atk or 0) - (getattr(t, 'armor', 0) or 0))
    if t.type == 'location':      # 指挥部不反击
        return dmg_t, 0, False
    counter = t.atk or 0
    if a.type == 'artillery':
        counter = 0               # 火炮主动进攻不被反击
    elif a.type == 'bomber' and t.type != 'fighter':
        counter = 0               # 轰炸机主动进攻不被反击（打战斗机除外）
    if t.type == 'bomber':
        counter = 0               # 轰炸机被进攻时不反击
    if getattr(a, 'shock', False):
        counter = 0               # 冲击：攻击时己方不受伤害
    dmg_a = max(0, counter - (getattr(a, 'armor', 0) or 0))
    # 伏击：被攻击时先出手，若能消灭攻击方，则自己不掉血
    if getattr(t, 'ambush', False) and counter > 0 and dmg_a >= (a.df or 0):
        return 0, dmg_a, True
    return dmg_t, dmg_a, False


class TurnLog:
    """本回合 AI 自己做过的事（客户端的 HasAttackLeft/HasMovementLeft 不含“部署当回合不能行动”
    和“移动后不能攻击”这两条规则，实测会放行，所以由 AI 自己记账）"""

    def __init__(self, st=None, me=None):
        self.deployed, self.moved, self.attacked = set(), set(), set()
        self.attacks = {}   # 单位 id -> 本回合攻击次数
        # 回合开始时两条线的单位数；之后的“占用数”= 开始数 + 本回合自己放上去的数
        # （快照里刚部署/推进的单位有时还没出现，实测导致连续往同一格部署、支援线超员）
        my = st['side'][me] if st else None
        self.base_sup = len(my['support']) if my else 0
        self.base_front = len(my['front']) if my else 0
        self.n_deploy, self.n_move = 0, 0
        self.played = 0            # 本回合下过的指令数（第 60 骑兵团：每回合只能下一个）
        self.no_deploy = False     # 对方上回合打了提尔皮茨/U-99：本回合不能部署（由驱动设置）
        self.temp = {}             # 单位 id -> 本回合内有效的攻击加成（老兔子、闪电战），估值时扣掉
        self.temp_op = {}          # 单位 id -> 本回合内的行动费变化（闪电战 -1）
        self.free = set()          # 本回合可免费行动一次的单位（永先者团）
        self.deploys = 0           # 本回合部署过的单位数（第 5 胸甲骑兵团：第一个部署）
        self.once = set()          # 本回合已触发过的“每回合一次”效果（第 158 补给营加费）
        self.gone = set()          # 本回合已打出的手牌 id（快照里可能还在手牌列表，如埋下的反制卡）
        self.cm_names = set()      # 本回合埋下的反制卡名
        self.extra_draw = 0        # 下回合开始额外多抽几张（战争债券）
        self.intel_seen = 0        # 本回合打情报牌看过的对方牌数
        self.forecasts = []        # 本回合预报的选择 [(天气, 档位)]
        self.weather_played = False  # 本回合已打过天气牌
        self.firewalled = set()      # 被防火墙贴过的单位 id（同步进 memo['firewalled']）
        self.neutralized = set()     # 被防火墙/两难困境处理过的单位 id（同步进 memo['neutralized']）
        self.memo = {}             # 跨回合的对局记忆（驱动每回合传入同一个 dict）：corps / brit_last

    def carry(self, sim):
        """执行完一步后，从这一步的模拟结果里带走跨步骤的状态（临时加成、每回合一次、军司令部标记）"""
        if sim is not None:
            self.temp = dict(sim.temp)
            self.temp_op = dict(getattr(sim, 'temp_op', {}))
            self.free = set(getattr(sim, 'free', ()))
            self.deploys = getattr(sim, 'deploys', self.deploys)
            if getattr(sim, 'fatigue', None):
                self.memo['fatigue'] = dict(sim.fatigue)     # 疲惫伤害次数（等差数列）
            for s, n in (getattr(sim, 'deck_add', None) or {}).items():
                da = self.memo.setdefault('deck_added', {})
                da[s] = da.get(s, 0) + n                      # 往牌库塞的牌：驱动下回合并入牌库张数
            for s, n in (getattr(sim, 'burned', None) or {}).items():
                bd = self.memo.setdefault('burned', {})
                bd[s] = bd.get(s, 0) + n                      # 爆掉的牌看不到：驱动从牌库估算里扣掉
            if getattr(sim, 'silenced', None):
                self.memo['silenced'] = set(sim.silenced)    # 抑制永久：跨回合关掉它的特效
            if getattr(sim, 'op_count', None):
                self.memo['op_count'] = dict(sim.op_count)   # 累计行动次数：跨步骤、跨回合
            self.once = set(sim.once)
            self.cm_names = set(getattr(sim, 'cm_names', ()))
            self.extra_draw = getattr(sim, 'extra_draw', 0)
            self.intel_seen = getattr(sim, 'intel_seen', 0)
            self.forecasts = list(getattr(sim, 'forecasts', ()))
            self.weather_played = getattr(sim, 'weather_played', False)
            fw = getattr(sim, 'firewalled', frozenset())
            if fw:
                self.firewalled = set(fw)
                self.memo['firewalled'] = set(fw)   # 防火墙永久生效：跨回合记住
            nz = getattr(sim, 'neutralized', frozenset())
            if nz:
                self.neutralized = set(nz)
                self.memo['neutralized'] = set(nz)
            corps = {c.id: c.corps for c in sim.side[sim.me]['hand'] if getattr(c, 'corps', 0)}
            if corps or self.memo.get('corps'):
                self.memo['corps'] = corps

    def sup_count(self, my):
        return max(len(my['support']), self.base_sup + self.n_deploy - self.n_move)

    def front_count(self, my):
        return max(len(my['front']), self.base_front + self.n_move)

    def rebase(self, st, me):
        """打出指令后（可能消灭/撤退/刷出单位）按最新快照重新计数"""
        my = st['side'][me]
        self.base_sup, self.base_front = len(my['support']), len(my['front'])
        self.n_deploy = self.n_move = 0


def _cost_now(st, me, c):
    """随场面变化的费用（B-24D）；快照的 cost 可能已经是减过的，取两者较小"""
    import effects
    f = effects.hook(c.name, 'cost')
    if not f:
        return c.cost
    try:
        return f(_View(st, me), c)
    except Exception:
        return c.cost


class _View:
    """给 cost 钩子用的最小场面视图（只要 units）"""

    def __init__(self, st, me):
        self.side, self.me = st['side'], me

    def units(self, side):
        return self.side[side]['support'] + self.side[side]['front']


def gen_actions(st, me, log=None):
    """生成全部合法动作：('deploy', 卡) / ('move', 卡) / ('attack', 卡, 目标)"""
    log = log or TurnLog()
    my = st['side'][me]
    kr = my['kredits']
    acts = []
    # 部署：单位卡，费用够，支援线有空位（快照可能还没反映刚部署的单位，取两者较大值）
    n_sup = log.sup_count(my)
    if n_sup < SUPPORT_MAX and not log.no_deploy:
        for c in my['hand']:
            if c.type in GROUND + RANGED and c.cost is not None and min(c.cost, _cost_now(st, me, c)) <= kr:
                acts.append(('deploy', c))
    units = my['support'] + my['front']
    en_front = st['side'][other(me)]['front']
    n_front = log.front_count(my)
    f_max = card_rules.front_max(st, FRONT_MAX)
    free = getattr(log, 'free', ())
    for u in units:
        if not ready(u, st['turn']) or u.op is None or (u.op > kr and u.id not in free):
            continue
        # 部署当回合不能行动（闪击除外，永先者团给的免费行动除外）；攻击过的不能再动；移动过的不能攻击
        if u.id in log.deployed and not u.blitz and u.id not in free:
            continue
        # 奋战（fury）一回合可攻击两次；坦克攻击后仍可移动（用户确认），其他单位攻击后不能再动
        n_att = log.attacks.get(u.id, 0)
        att_left = n_att < (2 if getattr(u, 'fury', False) else 1)
        if not att_left and not (u.type == 'tank' and u.id not in log.moved):
            continue
        moved = u.id in log.moved
        # 注意：不用客户端的 can_attack/can_move。实测客户端只给本机玩家的单位每回合重置这两个标记，
        # AI 单位行动过一次后永远是 0，导致 AI 后期整局不动。是否已行动完全以本回合记账为准。
        # 推进：地面单位，在支援线，本回合没移动过，前线没被敌方占且未满；攻击过的只有坦克能推进
        if (not moved and u.loc.startswith('support') and u.type in GROUND and not en_front
                and n_front < f_max and not st['front_full'] and (n_att == 0 or u.type == 'tank')
                and not card_rules.cant_move(u.name)):
            acts.append(('move', u))
        # 坦克天生可以移动后攻击；其他单位要有对应能力；“无法攻击”的单位只能移动
        if att_left and (not moved or u.move_and_attack or u.type == 'tank') and not u.cant_attack \
                and not card_rules.cant_attack(u.name) and not card_rules.attack_blocked(st, u):
            for t in attack_targets(st, me, u):
                if worth_attacking(t) and (t is not None or card_rules.can_attack_hq(st, me, u, u.id in log.deployed)):
                    acts.append(('attack', u, t))
    return acts


def score(st, me, act):
    """动作评分：模拟确定性的战斗结果，按场面价值变化打分；<= 0 的动作不做"""
    kind = act[0]
    en = st['side'][other(me)]
    if kind == 'attack':
        a, t = act[1], act[2]
        op_cost = (a.op or 0) * OP_WEIGHT   # 行动费用是代价（实测：0 攻击单位也会花 4 点去打指挥部）
        if (a.atk or 0) <= 0:
            return -1.0   # 打不出伤害的攻击不做
        if t is None:  # 打指挥部
            hq = en['hq'].df if en['hq'] else 99
            if (a.atk or 0) >= hq:
                return 1000.0  # 斩杀
            return 2.0 + (a.atk or 0) * 1.2 - op_cost
        dmg_t, dmg_a, ambushed = combat(a, t)
        kill = dmg_t >= (t.df or 0)
        die = dmg_a >= (a.df or 0)
        if ambushed:
            return -value(a) * 2   # 撞上伏击直接送死
        if kill:
            s = 2.0 + value(t) * 1.5
        else:
            # 磨血：造成的伤害有价值，自己挨的反击是代价（原先这里分太低，守护单位挡着时前线单位干站着不打）
            s = 1.0 + dmg_t * 0.8 - dmg_a * 0.5
        if die:
            s -= value(a) * 1.3
        if t.guard:
            s += 2.0 if kill else 1.0  # 拆守护打开指挥部
        return s - op_cost
    if kind == 'deploy':
        c = act[1]
        return 3.0 + (c.cost or 0) * 0.8 + value(c) * 0.2
    if kind == 'move':
        u = act[1]
        # 抢前线有价值，但别把脆弱单位送上去挨打
        s = 2.5
        if not st['side'][me]['front']:
            s += 1.5  # 夺取前线控制
        s -= 1.0 if (u.df or 0) <= 1 else 0
        return s - (u.op or 0) * OP_WEIGHT
    return 0.0


def record(log, act):
    """执行动作后记账"""
    if act[0] == 'deploy':
        log.deployed.add(act[1].id)
        log.n_deploy += 1
        log.deploys = max(log.deploys, len(log.deployed))
    elif act[0] == 'play':
        log.played += 1
    elif act[0] == 'move':
        log.moved.add(act[1].id)
        log.n_move += 1
    elif act[0] == 'attack':
        log.attacked.add(act[1].id)
        log.attacks[act[1].id] = log.attacks.get(act[1].id, 0) + 1


LAST = {'error': None, 'value': None, 'via': None}   # 上一次决策的诊断信息（driver 写日志用）


def decide(st, me, log=None):
    """返回本步动作或 None（结束回合）。
    优先用回合规划（planner：模拟器里搜索出牌/行动序列）；规划出错或给出的动作没通过合法性复核时，
    退回下面的逐步贪心"""
    log = log or TurnLog(st, me)
    try:
        import planner, decks
        a, v, base, _ = planner.plan_turn(st, me, log, decks.ACTIVE)
        LAST.update(error=None, value=(v, base), via='planner')
        if a is None:
            return None
        real = to_real(a)
        if check(st, me, log, real):
            return real
        LAST.update(error=f'规划动作未通过复核 {real!r}')
    except Exception as e:
        LAST.update(error=repr(e))
    LAST['via'] = 'greedy'
    return decide_greedy(st, me, log)


def to_real(a):
    """模拟器动作 -> 真实卡对象的动作：('deploy'|'play', 卡, 目标id, 抉择序号) / ('move', 卡) / ('attack', 卡, 目标或None)"""
    if a[0] in ('deploy', 'play'):
        return (a[0], a[1].real, a[2], a[3])
    if a[0] == 'move':
        return ('move', a[1].real)
    return ('attack', a[1].real, a[2].real if a[2] is not None else None)


def check(st, me, log, act):
    """对规划给出的动作再做一次合法性复核（以真实快照为准）"""
    my = st['side'][me]
    if act[1] is None:
        return False
    if act[0] in ('deploy', 'play'):
        c = act[1]
        if c not in my['hand'] or c.cost is None or min(c.cost, _cost_now(st, me, c)) > my['kredits']:
            return False
        if act[0] == 'deploy':
            return c.type in GROUND + RANGED and log.sup_count(my) < SUPPORT_MAX and not log.no_deploy
        if c.type not in ('order', 'countermeasure', 'gotcha'):
            return False
        if card_rules.order_limit_hit(st, log.played):
            return False                 # 第 60 骑兵团在场：每回合只能下一个指令
        if act[2]:
            # 目标可以是场上单位或指挥部（进攻殖民地、气动雪橇可以打总部）
            ids = {u.id for s in st['side'].values() for u in s['support'] + s['front']}
            ids |= {s['hq'].id for s in st['side'].values() if s['hq'] is not None}
            # 敌方的隐蔽单位、不能被敌方指令指向的单位不能当指令目标
            en = st['side'][other(me)]
            bad = {u.id for u in en['support'] + en['front']
                   if getattr(u, 'covert', False) or card_rules.order_immune(u.name)}
            return act[2] in ids and act[2] not in bad
        return True
    for g in gen_actions(st, me, log):
        if g[0] == act[0] and g[1] is act[1] and (act[0] == 'move' or g[2] is act[2]):
            return True
    return False


def decide_greedy(st, me, log=None):
    """返回本步最佳动作，或 None（结束回合）
    顺序策略：先攻击（拆掉威胁），再推进，最后部署；同类里按分数取最高"""
    acts = gen_actions(st, me, log)
    if not acts:
        return None
    scored = [(score(st, me, a), a) for a in acts]
    lethal = [x for x in scored if x[0] >= 1000]
    if lethal:
        return lethal[0][1]
    order = {'attack': 0, 'move': 1, 'deploy': 2}
    good = [x for x in scored if x[0] > 0.5]
    if not good:
        return None
    good.sort(key=lambda x: (order[x[1][0]], -x[0]))
    return good[0][1]
