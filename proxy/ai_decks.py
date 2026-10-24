# 给人机局的 AI 换一套套牌（私服默认直接复制玩家所选套牌）
# 套牌来源：登录响应里玩家自己的套牌列表；用 deckCodeIDsTable2 把套牌码解成卡名
import json, os, random, sys
import ai_deckgen
import card_db

from paths import DATA as W
_raw = json.load(open(os.path.join(W, 'deck_codes_all.json'), encoding='utf-8'))
# 同一代码可能对应多张（*_bal 平衡版），优先非 _bal
CODE2NAME = {c: sorted(ns, key=lambda n: n.endswith('_bal'))[0] for c, ns in _raw.items()}

DECKS = {}              # player_id -> [deck header]
last_lobby_deck = None  # 进入人机时选的 deck_id
AI_NAMES = ['训练官 Bob', '沙盘推演', '演习指挥部', '模拟对手']


def remember(pid, headers):
    DECKS[pid] = headers or []


def parse_deck_code(code):
    """'%%XY|g1;g2;g3;g4~...|loc..' -> (卡名列表[含重复], 指挥部卡名)。第 n 组每张 n 份"""
    parts = code.split('|')
    body = parts[1].split('~')[0]
    cards = []
    for n, grp in enumerate(body.split(';'), 1):
        for i in range(0, len(grp), 2):
            cards += [CODE2NAME[grp[i:i + 2]]] * n
    loc = CODE2NAME.get(parts[2][:2]) if len(parts) > 2 else None
    return cards, loc


HQ_BY_FACTION = {'Germany': 'card_location_berlin', 'Britain': 'card_location_london',
                 'Soviet': 'card_location_moscow', 'Japan': 'card_location_changchun',
                 'USA': 'card_location_supply_train_neutral'}
ALLY_DEFAULT = {'Germany': 'italy', 'Britain': 'usa', 'Soviet': 'usa', 'Japan': 'germany', 'USA': 'britain'}


MIX_AVOID = 2           # 随机对手：最近 2 局用过的不再选（连续 3 局不重复）
_HIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ai_mix_history.json')


def _mix_pick(keys):
    """从已登记的打法里随机挑一个，避开最近 MIX_AVOID 局用过的；记录存文件，代理重启后也接着算"""
    try:
        hist = json.load(open(_HIST, encoding='utf-8'))
    except Exception:
        hist = []
    pool = [k for k in keys if k not in hist[-MIX_AVOID:]] or keys
    key = random.choice(pool)
    try:
        json.dump((hist + [key])[-10:], open(_HIST, 'w', encoding='utf-8'))
    except Exception:
        pass
    return key


def _plan():
    """当前选用的 AI 打法：环境变量 KARDS_AI_DECK=mix（默认，每局从已登记的打法里随机选）/
    usa_ramp / soviet_control / random（随机生成的单位卡组）"""
    key = os.environ.get('KARDS_AI_DECK', 'mix')
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'native'))
        import decks
        if key == 'mix':
            key = _mix_pick(sorted(decks.PLANS))
        decks.activate(key)          # 不认识的名字（如 random）-> 通用打法
        return decks.load(key)
    except Exception:
        return None


def _mulligan(hand, rest, keep, log=None):
    """AI 起手调度：不想留的牌与牌库随机一张互换（与玩家调度规则相同，只换一次）。
    在开局数据发给客户端之前就换好，所以游戏画面里看不到 AI 换牌的过程"""
    swaps = []
    for i, n in enumerate(hand):
        if not keep(n, (card_db.get(n) or {}).get('kredits')) and rest:
            j = random.randrange(len(rest))
            hand[i], rest[j] = rest[j], n
            swaps.append(f'{n[5:]}->{hand[i][5:]}')
    if log:
        log(f'[ai_decks] AI 起手调度：' + ('、'.join(swaps) if swaps else '全部保留'))
    return hand, rest


def replace_ai_deck(j, log):
    """AI 套牌：有专门打法时用该打法的固定卡组和指挥部；否则程序生成（只含单位卡），国家随机"""
    sd = j['match_and_starting_data']['starting_data']
    ai = 'right' if sd['player_id_right'] >= 900000000 else 'left'
    plan = _plan()
    nhand = len(sd[f'starting_hand_{ai}'])
    if plan is not None:
        cards, _ = parse_deck_code(plan.DECK_CODE)
        random.shuffle(cards)
        faction, loc = plan.MAIN, plan.HQ
        deck = {'name': f'AI-{plan.NAME}', 'main_faction': faction, 'ally_faction': plan.ALLY,
                'card_back': sd[f'card_back_{ai}']}
        import buffs                     # native/（_plan 已把路径加进 sys.path）
        lv = buffs.current()
        if buffs.LEVELS[lv]['opening'] and getattr(plan, 'OPENING', None):
            # 老兵及以上：起手从卡组的候选池里随机挑 5 张（不再调度）；先手时 LocalMatch 会把最后一张放回牌库顶
            cards = buffs.opening(cards, plan, random)
            log(f'[ai_decks] 难度 {buffs.LEVELS[lv]["title"]}：起手候选池 -> ' + '、'.join(n[5:] for n in cards[:5]))
        else:
            # 起手按 5 张调度（后手的数量）；先手时 LocalMatch 会把最后一张放回牌库顶
            hand, rest = _mulligan(cards[:5], cards[5:], plan.keep, log)
            cards = hand + rest
    else:
        faction, cards = ai_deckgen.build()
        random.shuffle(cards)
        loc = HQ_BY_FACTION[faction]
        deck = {'name': f'AI-{faction}', 'main_faction': faction, 'ally_faction': ALLY_DEFAULT[faction],
                'card_back': sd[f'card_back_{ai}']}
    base = sd[f'location_card_{ai}']['card_id']  # 指挥部卡 id（左 1 / 右 41），其余顺延
    hand, rest = cards[:nhand], cards[nhand:]
    sd[f'starting_hand_{ai}'] = [
        {'card_id': base + 1 + i, 'is_gold': False, 'location': f'hand_{ai}', 'location_number': i, 'name': n}
        for i, n in enumerate(hand)]
    sd[f'deck_{ai}'] = [
        {'card_id': base + 1 + nhand + i, 'is_gold': False, 'location': f'deck_{ai}',
         'location_number': nhand + i, 'name': n} for i, n in enumerate(rest)]
    if loc:
        sd[f'location_card_{ai}'] = dict(sd[f'location_card_{ai}'], name=loc,
                                         faction=deck.get('main_faction', sd[f'location_card_{ai}'].get('faction')))
    sd[f'ally_faction_{ai}'] = (deck.get('ally_faction') or sd[f'ally_faction_{ai}']).lower()
    sd[f'card_back_{ai}'] = deck.get('card_back') or sd[f'card_back_{ai}']
    sd[f'{ai}_player_name'] = getattr(plan, 'COMMANDER', None) or random.choice(AI_NAMES)
    if getattr(plan, 'AVATAR', None):
        # 头像在 equipment_{side} 里（avatar_* 物品 id）；表情等其余装备保留
        eq = [x for x in sd.get(f'equipment_{ai}') or [] if not str(x).startswith('avatar_')]
        sd[f'equipment_{ai}'] = [plan.AVATAR] + eq
    log(f'[ai_decks] AI 使用套牌「{deck.get("name")}」{deck.get("main_faction")}+{deck.get("ally_faction")} '
        f'{len(cards)} 张，指挥部 {loc}')
