# 难度加成：调用客户端自带的开发者作弊函数（BP_OnlineMatch.PlayerDevCheat*）给 AI 加 buff。
# 实测（COMET 4.0.1，375423）：客户端直接结算，并自己发一条 XActionCheat 给服务器，本地人机局照常记录。
# 只能在本地人机局里用（live_driver 只在 LocalMatch 里跑，PvP 不经过这里）。
import struct, time

OM = '/Game/Blueprints/Logic/BP_OnlineMatch.BP_OnlineMatch_C'
CF = '/Game/Blueprints/Cards/BP_CardFunctions.BP_CardFunctions_C'
SIDE = {'left': 1, 'right': 2}                        # ESideEnum
HAND = {'left': 3, 'right': 4}                        # ECardLocationEnum: Hand_Left / Hand_Right

# 难度档（替换不叠加）。kredit_from = 从 AI 自己第几个回合起每回合 +1 指挥点（0 = 不加）
LEVELS = {
    'normal':  {'title': '普通', 'opening': False, 'hq': 0,  'kredit_from': 0, 'draw_below': 0, 'print_below': 0},
    'veteran': {'title': '老兵', 'opening': True,  'hq': 5,  'kredit_from': 0, 'draw_below': 0, 'print_below': 0},
    'elite':   {'title': '精英', 'opening': True,  'hq': 10, 'kredit_from': 6, 'draw_below': 4, 'print_below': 0},
    'hell':    {'title': '地狱', 'opening': True,  'hq': 20, 'kredit_from': 1, 'draw_below': 0, 'print_below': 4},
}
ALIAS = {'普通': 'normal', '老兵': 'veteran', '精英': 'elite', '地狱': 'hell',
         'vet': 'veteran', 'hard': 'elite', 'nightmare': 'hell'}
PRINT_MAX = 1                                         # 地狱：每张核心牌最多打印 1 次（用户 2026-10-23 由 2 改 1）
PRODUCTION = 'card_event_production'                  # 生产：0 费，本回合 +1 指挥点（每回合 +1 指挥点就送这张）
GIFT_BELOW = 9                                        # 补完牌后手牌 < 9 张（还有空位）就送生产（用户 2026-10-24 由 8 改 9）
GIFT_DELAY = 1.5                                      # 送生产前等一下（回合开始抽牌的动画播完）


def level(key):
    key = ALIAS.get(key, key)
    return key if key in LEVELS else 'normal'


def current():
    """本次启动选的难度（start.sh 写进环境变量 KARDS_LEVEL）"""
    import os
    return level(os.environ.get('KARDS_LEVEL', 'normal'))


def opening(cards, plan, rng, n=5):
    """老兵及以上的起手：从卡组里属于 plan.OPENING 的牌中随机挑 n 张（同名尽量不重复），其余洗成牌库。
    返回新的牌序（前 n 张是起手）；没有候选池时原样返回。先手时最后一张会被放回牌库顶，所以 n 按后手 5 张给"""
    pool = set(getattr(plan, 'OPENING', ()) or ())
    if not pool:
        return list(cards)
    rest = list(cards)
    rng.shuffle(rest)
    cand = [c for c in rest if c in pool]
    hand, used = [], set()
    for c in cand:                       # 先挑不同名的
        if len(hand) < n and c not in used:
            hand.append(c)
            used.add(c)
    for c in cand:                       # 不够再允许同名
        if len(hand) < n and hand.count(c) < cand.count(c):
            hand.append(c)
    for c in hand:
        rest.remove(c)
    while len(hand) < n and rest:        # 候选池里的牌太少：用牌库补
        hand.append(rest.pop())
    return hand + rest


def name_index(ue, name):
    """卡名 -> FName 编号（扫一遍名字表，结果缓存在 ue 上）"""
    cache = ue.__dict__.setdefault('_name_idx', {})
    if not cache:
        i = 0
        while True:
            data = ue.block_data(i)
            if not data:
                break
            off = 0
            while off + 2 <= len(data):
                h = struct.unpack_from('<H', data, off)[0]
                wide, ln = h & 1, h >> 6
                if ln == 0:
                    break
                size = 2 + ln * (2 if wide else 1)
                if not wide and data[off + 2:off + 7] == b'card_':
                    cache[data[off + 2:off + size].decode('latin-1')] = (i << 16) | (off // 2)
                off += (size + 1) & ~1
            i += 1
    return cache.get(name)


class Cheat:
    def __init__(self, ue):
        self.ue = ue
        self.om = ue.instances('BP_OnlineMatch_C')[0]

    def _call(self, fn, **args):
        return self.ue.call(self.om, self.ue.find_func(OM, fn), **args)

    def change_defense(self, card_id, n):
        return self._call('PlayerDevCheatChangeDefense', cardToChange=card_id, AmountToChange=n)

    def set_kredits(self, side, n):
        return self._call('PlayerDevCheatSetKredits', sideToSet=SIDE[side], kreditToSet=n)

    def draw(self, side):
        return self._call('PlayerDevCheatDrawCard', sidetodraw=SIDE[side])

    def spawn_in_hand(self, side, name):
        idx = name_index(self.ue, name)
        if idx is None:
            return None
        return self._call('PlayerDevCheatSpawnCard', sideToSpawn=SIDE[side], cardNameToSpawn=(idx, 0),
                          locationToSpawn=HAND[side], numberToSpawn=1)


def plan_turn(lv, st, side, memo, plan, rng):
    """本 AI 回合开始时该加哪些 buff（纯函数，不碰客户端，方便测试）。
    st = 真实场面快照；memo = 驱动的跨回合记忆（记 hq_done / prints / ai_turn / deck_n）。
    返回 [(种类, 参数)]：('hq', n) ('gift', 生产) ('draw', 1) ('print', 核心牌名)"""
    cfg = LEVELS[lv]
    out = []
    my = st['side'][side]
    if cfg['hq'] and not memo.get('buff_hq_done'):
        out.append(('hq', cfg['hq']))
    turn = memo.get('ai_turn', 1)
    n_hand = len(my['hand'])                 # 实际占手牌位置的张数（上限 9）
    n_real = sum(1 for c in my['hand'] if c.name != PRODUCTION)   # “手牌少于 N 张”按真牌算，不算送的生产
    # 先补牌（摸牌 / 打印核心牌），最后才送生产（用户要求的顺序）
    if cfg['draw_below'] and n_real < cfg['draw_below'] and n_hand < 9 and \
            (memo.get('deck_n') or {}).get(side, 1) > 0:
        out.append(('draw', 1))              # 牌库空了不摸（只会吃疲惫伤害）
        n_hand += 1
        n_real += 1
    core = list(getattr(plan, 'CORE', ()) or ())
    if cfg['print_below'] and n_real < cfg['print_below'] and n_hand < 9 and core:
        prints = memo.get('buff_prints', {})
        left = [c for c in core if prints.get(c, 0) < PRINT_MAX]
        if left:
            out.append(('print', rng.choice(left)))
            n_hand += 1
            n_real += 1
    if cfg['kredit_from'] and turn >= cfg['kredit_from'] and n_hand < GIFT_BELOW:
        # +1 指挥点 = 往手牌打印一张“生产”（0 费，本回合 +1），由 AI 自己打出：客户端走正常出牌，界面和动作记录都对。
        # 直接改指挥点（GiveKreditsBySide / SetKreditsAndKreditSlots）实测 431028 数值对但界面不刷新（用户反馈）。
        # 手里有上回合没用的生产也照送（用户 2026-10-24：只要补完牌手牌 < 9 就送）
        out.append(('gift', PRODUCTION))
    return out


def apply(cheat, cf, st, side, todo, memo, log):
    """按 plan_turn 的结果调用作弊函数；返回实际给总部加的防御（驱动同步给 local_match 的总部值）"""
    hq_add = 0
    my = st['side'][side]
    for kind, arg in todo:
        try:
            if kind == 'hq':
                cheat.change_defense(my['hq'].id, arg)
                memo['buff_hq_done'] = True
                hq_add += arg
            elif kind == 'draw':
                cheat.draw(side)
            elif kind in ('print', 'gift'):
                if kind == 'gift':
                    time.sleep(GIFT_DELAY)   # 稍等再送（用户：先抽牌再发生产，发生产要有点延迟）
                if cheat.spawn_in_hand(side, arg) is None:
                    log(f'[难度] 名字表里找不到 {arg}，不打印')
                    continue
                if kind == 'print':          # 核心牌记次数；送的“生产”不算
                    p = memo.setdefault('buff_prints', {})
                    p[arg] = p.get(arg, 0) + 1
            log(f'[难度] {kind} {arg if not isinstance(arg, str) else arg[5:]}')
        except Exception as e:
            log(f'[难度] {kind} 失败 {e!r}')
    return hq_add
