# 模拟器状态：把真实场面复制成可修改的副本，供 planner 在里面试走动作
# 动作的合法性与结算在 sim_rules.py；卡牌效果在 cards_*.py（引擎 effects.py）
import os, sys, random
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'proxy'))
import card_db  # noqa: E402
from live_ai import other, SUPPORT_MAX, FRONT_MAX  # noqa: E402,F401
import card_rules  # noqa: E402

HAND_MAX = 9           # 手牌上限，超出的抽牌直接丢弃
UNKNOWN = '?'          # 模拟里新抽到的未知牌
ORDER_TYPES = ('countermeasure', 'gotcha')   # 反制卡：出牌方式与指令相同
KREDIT_V = 0.8         # 未来 1 个指挥点折算的分数
DISCOUNT = 0.9         # 未来回合的折扣
FIELDS = ('name', 'type', 'id', 'loc', 'side', 'slot', 'atk', 'df', 'op', 'cost', 'guard', 'smoke', 'pinned',
          'blitz', 'move_and_attack', 'cant_attack', 'ambush', 'shock', 'armor', 'fury', 'covert')


def intel_level(attrs):
    """情报等级（关键词 intel1/intel2/...）；0 = 不是情报牌"""
    return max([int(x[5:]) for x in (attrs or ()) if x.startswith('intel') and x[5:].isdigit()] or [0])


def slot_value(S, delta, R, kv=KREDIT_V):
    """指挥点槽变化 delta 的价值：槽每回合自然 +1 到 12 为止，12 以上的加槽才是永久的（上限 24）。
    比较“有/没有这次变化”在之后 R 个回合里每回合的槽数差，折现求和；kv = 1 个指挥点值多少分"""
    a, b, v = S, max(0, min(24, S + delta)), 0.0
    for t in range(1, int(R) + 1):
        a = a + 1 if a < 12 else a
        b = b + 1 if b < 12 else b
        v += (b - a) * kv * DISCOUNT ** t
    return v


class SC:
    """模拟用卡牌：字段与 live.Card 相同；real 指向真实卡（模拟里新生成的为 None）"""

    def copy(self):
        n = SC.__new__(SC)
        n.__dict__ = dict(self.__dict__)
        return n

    @staticmethod
    def of(c):
        n = SC()
        for f in FIELDS:
            setattr(n, f, getattr(c, f, None))
        n.armor = n.armor or 0
        n.real = c
        i = card_db.get(n.name) or {}
        if n.type in ORDER_TYPES:
            n.type = 'order'                  # 反制卡（客户端枚举不确定）按指令处理
        n.faction = i.get('faction')
        n.bond = 'bond' in (i.get('attrs') or ())
        n.vet = False
        n.counter = i.get('type') == 'countermeasure'
        n.intel = intel_level(i.get('attrs'))
        return n

    @staticmethod
    def new(name, side, cid, loc):
        """按卡牌数据生成新卡（加入手牌的衍生牌、刷出的单位）"""
        i = card_db.get(name) or {}
        a = i.get('attrs') or set()
        n = SC()
        n.name, n.type, n.id, n.loc, n.side, n.slot = name, i.get('type', 'unknown'), cid, loc, side, 99
        if not i and str(name).startswith('card_event_'):
            n.type = 'order'                  # 卡牌数据里没有的指令（天气牌变体 *2/*3）
            base = card_db.get(str(name).rstrip('23')) or {}
            i = {'kredits': base.get('kredits', 99)}   # 变体费用同基础版（第 2/3/4 级 = 2/4/6 费）
        if n.type in ORDER_TYPES:
            n.type = 'order'
        n.atk, n.df, n.op, n.cost = i.get('attack', 0), i.get('defense', 0), i.get('op', 0), i.get('kredits', 99)
        n.guard, n.smoke, n.blitz = 'guard' in a, 'smokescreen' in a, 'blitz' in a
        n.ambush, n.shock, n.fury = 'ambush' in a, 'shock' in a, 'fury' in a
        n.armor = max([int(x[-1]) for x in a if x.startswith('heavyArmor')] or [0])
        n.pinned = n.move_and_attack = n.covert = False
        n.cant_attack = card_rules.cant_attack(name)     # 如 BP-43 装甲列车（真实单位用客户端的 HasCantAttack）
        n.faction, n.vet, n.real = i.get('faction'), False, None
        n.bond = 'bond' in a
        n.counter = i.get('type') == 'countermeasure'
        n.intel = intel_level(a)
        return n

    def __repr__(self):
        return '%s#%s(%s/%s)' % (str(self.name).split('_', 2)[-1][:18], self.id, self.atk, self.df)


class Sim:
    """一方（me）回合中的局面副本。st['side'] 等键与真实快照一致，live_ai 的规则函数可直接用"""

    def __init__(self, st, me, tlog=None):
        self.me, self.turn = me, st['turn']
        self.side = {}
        for k, d in st['side'].items():
            if d['hq'] is None:
                raise ValueError('快照缺指挥部')
            self.side[k] = {'hand': [SC.of(c) for c in d['hand']], 'support': [SC.of(c) for c in d['support']],
                            'front': [SC.of(c) for c in d['front']], 'kredits': d['kredits'],
                            'max_kredits': d['max_kredits'], 'hq': SC.of(d['hq'])}
        my = st['side'][me]
        # 快照可能还没反映刚部署/推进的单位：按 AI 自己记账补上占位
        self.extra_sup = max(0, tlog.sup_count(my) - len(my['support'])) if tlog else 0
        self.extra_front = max(0, tlog.front_count(my) - len(my['front'])) if tlog else 0
        self.deployed = set(tlog.deployed) if tlog else set()
        self.moved = set(tlog.moved) if tlog else set()
        self.attacks = dict(tlog.attacks) if tlog else {}
        self.played = getattr(tlog, 'played', 0)          # 本回合已下的指令数
        self.no_deploy = getattr(tlog, 'no_deploy', False)  # 本回合不能部署（提尔皮茨/U-99）
        # 模拟里新生成的卡用负数 id，从现有最小 id 往下排，避免撞号
        ids = [c.id for d in self.side.values() for k in ('hand', 'support', 'front') for c in d[k]
               if isinstance(c.id, int)]
        self.bonus, self.next_id, self.n_actions = 0.0, min(ids + [0]) - 1, 0
        self.rng, self.random_used, self.ctx = random.Random(0), False, {}
        self.last_dead = {'left': None, 'right': None}   # 每方上一个被消灭的陆军（伊尔-10 亡计）
        self.temp = dict(getattr(tlog, 'temp', {}) or {})  # 单位 id -> 本回合内有效的攻击加成（回合结束失效）
        self.temp_op = dict(getattr(tlog, 'temp_op', {}) or {})  # 单位 id -> 本回合内的行动费变化（闪电战）
        self.once = set(getattr(tlog, 'once', ()) or ())   # 本回合已触发过的“每回合一次”效果
        # 跨回合的对局记忆（驱动维护，模拟里只读）：军司令部标记、上回合是否部署过英国步兵
        self.memo = getattr(tlog, 'memo', None) or {}
        # 单位 id -> 本局累计行动次数（豹式防磁装甲型）：memo['op_count'] 由 TurnLog.carry 每步写回
        self.op_count = dict(self.memo.get('op_count', {}))
        # 下回合结束会被弃掉的手牌 id（长久围困抽的牌）：留着没价值。驱动记在 memo['expiring']
        self.expiring = frozenset(self.memo.get('expiring', ()))
        # 被抑制的单位 id（特效没了；快照数值已回到卡面，但钩子要靠这里关掉）：memo['silenced'] 跨回合
        self.silenced = frozenset(self.memo.get('silenced', ()))
        self.free = frozenset(getattr(tlog, 'free', ()) or ())   # 本回合可免费行动一次的单位（永先者团）
        self.deploys = getattr(tlog, 'deploys', 0) or 0          # 本回合已部署的单位数（不含刷出的）
        # 牌库剩余张数 {side: n}（驱动按开局牌库和见过的牌估算；没有则不模拟抽空）、已受过几次疲惫伤害
        self.deck_n = dict(self.memo.get('deck_n', {}))
        self.fatigue = dict(self.memo.get('fatigue', {}))
        self.deck_add = {}                                      # 本步往牌库塞了几张（驱动累计）
        self.burned = {}                                        # 本步爆掉几张（驱动从牌库估算里扣掉）
        # 我方下回合开始额外多抽几张（战争债券）：本回合内跨步骤记在 TurnLog，结束回合时算爆牌要用
        self.extra_draw = getattr(tlog, 'extra_draw', 0) or 0
        # 对方埋下、还挂着的反制卡名（驱动记 memo['en_planted'] = {卡id: 卡名}；卡还在对方手牌里才算挂着）
        e_ids = {c.id for c in self.side[other(me)]['hand']}
        self.en_cm = {n for i, n in (self.memo.get('en_planted') or {}).items() if i in e_ids}
        # 手牌按格子号排成显示顺序（实测快照列表顺序 != 显示顺序，slot 0 = 最左；Z 队、军司令部、击退进攻要用）
        self.side[me]['hand'].sort(key=lambda c: c.slot if isinstance(c.slot, int) else 99)
        corps = self.memo.get('corps', {})
        for c in self.side[me]['hand']:
            if corps.get(c.id):
                c.corps = corps[c.id]                     # 打出时随机消灭敌方单位的次数
        # 正在生效的反制卡名（本回合埋的 + 之前埋了还没触发的）：不同反制可以同时挂多张，同名的不重复埋（用户确认）
        self.cm_names = set(getattr(tlog, 'cm_names', ()) or ()) | set(self.memo.get('planted', {}).values())
        # 埋下没触发的反制卡仍占手牌位置（实测：挂着 1 张雷达警报时抽牌预测 9 张、实际 8 张，多抽的那张爆掉了）
        self.hand_extra = len(self.memo.get('planted', {}))
        self.play_left = self.play_right = False          # 刚打出的牌是否在手牌最左/最右（Z 队、击退进攻）
        self.turn_over = False                            # 效果结束了本回合（击退进攻不在最右边打出）
        # 情报：本局我方累计看过对方几张牌（驱动跨回合记在 memo['intel']）；本回合新增记在 intel_seen
        self.intel_seen = getattr(tlog, 'intel_seen', 0) or 0
        self.forecasts = list(getattr(tlog, 'forecasts', ()) or ())   # 本回合预报选了什么（驱动补发选择用）
        self.weather_played = getattr(tlog, 'weather_played', False)   # 本回合已打过天气牌（每回合限一张）
        # 被防火墙贴过的单位（永久不能攻击敌方指挥部）：客户端没有对应的取值函数，驱动跨回合记在 memo
        self.firewalled = frozenset(self.memo.get('firewalled', ())) | frozenset(getattr(tlog, 'firewalled', ()) or ())
        # 已经被防火墙或两难困境处理过的敌方单位（用户：做过一次就别再给它贴/压制了，行动费都那么高了）
        self.neutralized = (frozenset(self.memo.get('neutralized', ())) | frozenset(getattr(tlog, 'neutralized', ()) or ())
                            | self.firewalled)
        for d in self.side.values():
            for u in d['support'] + d['front']:
                u.no_hq = u.id in self.firewalled
        import effects                                    # 运行时导入（effects 依赖本模块）
        effects.init_stats(self)

    def __getitem__(self, k):
        if k == 'front_full':
            return len(self.side['left']['front']) + len(self.side['right']['front']) >= FRONT_MAX
        return getattr(self, k)

    def clone(self, rng=None):
        n = Sim.__new__(Sim)
        n.__dict__ = dict(self.__dict__)
        n.side = {k: {'hand': [c.copy() for c in d['hand']], 'support': [c.copy() for c in d['support']],
                      'front': [c.copy() for c in d['front']], 'kredits': d['kredits'],
                      'max_kredits': d['max_kredits'], 'hq': d['hq'].copy()} for k, d in self.side.items()}
        n.deployed, n.moved, n.attacks = set(self.deployed), set(self.moved), dict(self.attacks)
        n.last_dead = dict(self.last_dead)
        n.temp, n.once = dict(self.temp), set(self.once)
        n.temp_op, n.op_count = dict(self.temp_op), dict(self.op_count)
        n.en_cm = set(self.en_cm)
        n.cm_names = set(self.cm_names)
        n.forecasts = list(self.forecasts)
        n.rng, n.random_used = rng or random.Random(0), False
        return n

    # ---------- 查询 ----------
    def units(self, side):
        d = self.side[side]
        return d['support'] + d['front']

    def count(self, side, name):
        return sum(1 for u in self.units(side) if u.name == name)

    def find(self, cid):
        for d in self.side.values():
            for key in ('hand', 'support', 'front'):
                for c in d[key]:
                    if c.id == cid:
                        return c
        return None

    def known_enemy(self):
        """对方手牌里我们看过的张数（按累计情报等级估，不超过对方手牌数）"""
        return min(len(self.side[other(self.me)]['hand']), self.memo.get('intel', 0) + self.intel_seen)

    def sup_count(self):
        return len(self.side[self.me]['support']) + self.extra_sup

    def new_id(self):
        self.next_id -= 1
        return self.next_id + 1
