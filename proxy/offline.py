# 单机保留地·第二阶段：离线模式，代理自己冒充私服，完全不连私服服务器
# 数据来源：
#   1. 录档（archive.py 录下的私服回应）：登录、收藏、商店、成就等原样回放；
#   2. 本地状态 offline_state.json（和录档放在一起）：卡组增删改、装备的表情/物品；
#   3. 训练局开局数据：照录档里的开局样本，用玩家所选卡组自己洗牌发牌，AI 套牌照常由 ai_decks 替换。
# 对局本身（调度、动作、结束）一直是 LocalMatch 在本地处理，离线时不用改。
import os, json, re, copy, random, datetime, threading
import archive
import ai_decks

STATE = os.path.join(archive.DIR, 'offline_state.json')
# 客户端连的本机地址（1.58 是 5233，COMET 是 5235），由 kards_proxy 按上游设置
LOCAL = os.environ.get('KARDS_LOCAL_URL', 'http://127.0.0.1:5233')
_lock = threading.RLock()
_state = None
_pending = {}            # player_id -> 进入训练时选的 deck_id（POST /singleplayerlobby 之后、开局之前）
_missing = set()         # 录档里没有的接口（每个只打一次日志）


def available():
    """有录档（至少录到登录和开局样本）才能离线"""
    return all(os.path.exists(os.path.join(archive.DIR, archive._fname(k)))
               for k in ('GET /', 'POST /session', 'GET /matches/v2/'))


def _rec(key):
    p = os.path.join(archive.DIR, archive._fname(key))
    if not os.path.exists(p):
        return None
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def _body_bytes(b):
    if b is None:
        return b'null'
    if isinstance(b, dict) and set(b) == {'_text'}:
        return b['_text'].encode('utf-8')
    if isinstance(b, dict) and set(b) == {'_hex'}:
        return bytes.fromhex(b['_hex'])
    return json.dumps(b, ensure_ascii=False).encode('utf-8')


def _now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') + '000Z'


def _load():
    """本地状态：第一次离线时用录档里登录回应的卡组列表初始化"""
    global _state
    if _state is None:
        if os.path.exists(STATE):
            with open(STATE, encoding='utf-8') as f:
                _state = json.load(f)
        else:
            s = (_rec('POST /session') or {}).get('body') or {}
            _state = {'decks': copy.deepcopy((s.get('decks') or {}).get('headers') or []), 'equipped': None}
    return _state


def _save():
    tmp = STATE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(_state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE)


def _json(status, obj):
    return status, [('Content-Type', 'application/json')], json.dumps(obj, ensure_ascii=False).encode('utf-8')


def _not_found(method, path):
    return _json(404, {'message': f'Cannot {method} {path.split("?")[0]}', 'error': 'Not Found', 'statusCode': 404})


def handle(method, path, body, log, auth=False):
    """离线回应一个请求：返回 (状态码, 响应头列表, 响应体字节)。auth = 请求带了登录凭证（Authorization 头）"""
    with _lock:
        try:
            req = json.loads(body) if body else None
        except Exception:
            req = None
        p = path.split('?')[0]
        st = _load()
        if method == 'POST' and p == '/session':
            return _session()
        if method == 'GET' and p == '/' and auth:
            return _root_auth()
        if method == 'POST' and p == '/singleplayerlobby':
            pid = (req or {}).get('player_id')
            _pending[pid] = (req or {}).get('deck_id')
            return 201, [('Content-Type', 'text/html')], b'OK'
        if method == 'DELETE' and p == '/singleplayerlobby':
            _pending.clear()
            return 200, [('Content-Type', 'text/html')], b'OK'
        if method == 'GET' and p == '/matches/v2/':
            if not _pending:
                return 200, [('Content-Type', 'text/html')], b'null'     # 实测：还没匹配到时私服回 null
            pid, deck_id = _pending.popitem()
            return _json(200, _new_match(deck_id, log))
        if method == 'GET' and p == '/matches/v2/reconnect':
            return 200, [('Content-Type', 'text/html')], b'null'         # 进行中的本地局由 kards_proxy 先处理
        m = re.match(r'^/players/(\d+)/decks(?:/(\d+))?$', p)
        if m:
            return _decks(method, int(m.group(1)), m.group(2) and int(m.group(2)), req)
        m = re.match(r'^/items/(\d+)$', p)
        if m:
            return _items(method, req)
        if method == 'PUT' and re.match(r'^/players/\d+/heartbeat$', p):
            return _json(200, {})
        if method == 'POST' and re.match(r'^/players/notifications/\d+$', p):
            return _json(201, {})
        # 其余接口：录档里有就原样回放（收藏、商店、成就、好友……）
        r = _rec(archive.key_of(method, path))
        if r is not None:
            hdrs = [(k, v) for k, v in (r.get('headers') or {}).items() if k.lower() in ('content-type',)]
            return r['status'], hdrs, _body_bytes(r.get('body'))
        if method in ('PUT', 'POST') and re.match(r'^/players/\d+$', p):
            s = (_rec('POST /session') or {}).get('body') or {}
            return _json(200, {'player_name': s.get('player_name'), 'player_tag': s.get('player_tag')})
        key = archive.key_of(method, path)
        if key not in _missing:
            _missing.add(key)
            log(f'[offline] 录档里没有 {key}，回 404（游戏如果因此出问题，联网时补录这个接口）')
        return _not_found(method, path)


def _root_auth():
    """登录后的 GET /：带 current_user（登录凭证里的身份）和 my_* 地址。
    客户端登录后会再要一次，拿到未登录那份（current_user 为空）就卡在登录界面（2026-10-20 实测）。
    录到了就用录档，没录到就照抓包里的格式拼（未登录那份 + 登录回应里的账号）"""
    r = _rec('GET / (auth)')
    if r is not None:
        return r['status'], [('Content-Type', 'application/json')], _body_bytes(r.get('body'))
    root = copy.deepcopy(_rec('GET /')['body'])
    sess = _rec('POST /session') or {}
    s, q = sess.get('body') or {}, sess.get('request') or {}
    pid = s.get('player_id')
    now = int(datetime.datetime.now().timestamp())
    root['current_user'] = {
        'client_id': s.get('client_id', pid), 'exp': now + 30 * 86400, 'external_id': q.get('username', ''),
        'iat': now, 'identity_id': s.get('user_id', pid), 'iss': 'fyserver', 'jti': s.get('jti', ''),
        'language': q.get('language', 'zh-Hans'), 'payment': 'notavailable', 'player_id': str(pid),
        'provider': q.get('provider', 'device_id'), 'roles': [], 'tier': 'LIVE', 'user_id': s.get('user_id', pid),
        'user_name': q.get('username', '')}
    ep = root.get('endpoints') or {}
    base = ep.get('root', LOCAL)
    ep.update(my_draft=f'{base}/draft/{pid}', my_items=f'{base}/items/{pid}', my_player=f'{base}/players/{pid}')
    return _json(200, root)


def _session():
    r = _rec('POST /session')
    s = copy.deepcopy(r['body'])
    s['decks'] = {'headers': copy.deepcopy(_load()['decks'])}
    s['server_time'] = datetime.datetime.now(datetime.timezone.utc).strftime('%Y.%m.%d-%H.%M.%S')
    s['last_logon_date'] = _now_iso()
    if isinstance(s.get('server_options'), str):
        so = json.loads(s['server_options'])
        # 通知用的 WebSocket 长连接：离线时指向本机一个没人监听的端口，连不上就算了；关掉断线弹窗
        so['websocketurl'] = 'ws://127.0.0.1:5239'
        so['feature_socketerror_popup_enabled'] = 0
        s['server_options'] = json.dumps(so, ensure_ascii=False)
    return _json(200, s)


def _decks(method, pid, did, req):
    st = _load()
    decks = st['decks']
    if method == 'GET' and did is None:
        return _json(200, decks)
    if method == 'GET':
        d = next((x for x in decks if x.get('id') == did), None)
        return _json(200, d) if d else _not_found(method, f'/players/{pid}/decks/{did}')
    # 格式按 2026-10-20 录到的真实回应：新建回 201 + 完整卡组（没给卡背时用阵营新手卡背）；
    # 修改是 {"action": "fill", "deck_code": ...}，删除和修改都回 200 空内容
    empty = (200, [], b'')
    if method == 'POST':
        d = dict(req or {})
        now = _now_iso()
        d.setdefault('card_back', f'cardback_starter_{str(d.get("main_faction", "")).lower()}')
        d.setdefault('deck_code', '')
        d.update(favorite=False, id=max([x.get('id', 0) for x in decks] + [100000]) + random.randint(1, 999),
                 player_id=pid, last_played=now, create_date=now, modify_date=now)
        decks.append(d)
        _save()
        return _json(201, d)
    if method == 'PUT' and did is not None:
        d = next((x for x in decks if x.get('id') == did), None)
        if d is None:
            return _not_found(method, f'/players/{pid}/decks/{did}')
        d.update({k: v for k, v in (req or {}).items() if k not in ('id', 'player_id', 'action')})
        d['modify_date'] = _now_iso()
        _save()
        return empty
    if method == 'PUT':
        return empty                             # PUT /players/{id}/decks（整体保存）
    if method == 'DELETE' and did is not None:
        st['decks'] = [x for x in decks if x.get('id') != did]
        _save()
        return empty
    return _not_found(method, f'/players/{pid}/decks')


def _items(method, req):
    st = _load()
    r = _rec('GET /items/{id}')
    base = copy.deepcopy(r['body']) if r else {'equipped_items': [], 'items': []}
    if st.get('equipped') is None:
        st['equipped'] = base.get('equipped_items') or []
    if method == 'POST' and req:
        # 同一阵营同一格子只能装一个：替换
        st['equipped'] = [e for e in st['equipped']
                          if not (e.get('slot') == req.get('slot') and e.get('faction') == req.get('faction'))]
        st['equipped'].append({k: req.get(k) for k in ('item_id', 'slot', 'faction')})
        _save()
        return _json(201, req)
    base['equipped_items'] = st['equipped']
    return _json(200, base)


def _usable(d):
    try:
        return bool(ai_decks.parse_deck_code(d.get('deck_code') or '')[0])
    except KeyError:
        return False                             # 卡组码里有不认识的卡


def _template():
    """开局样本：优先本录档目录里录到的，没有就用随包带的脱敏样本（COMET 服训练模式被关，录不到）"""
    r = _rec('GET /matches/v2/')
    if r is not None:
        return copy.deepcopy(r['body'])
    with open(os.path.join(ai_decks.W, 'match_template.json'), encoding='utf-8') as f:
        return json.load(f)


def _new_match(deck_id, log):
    """离线：照录档里的开局样本，用本地保存的卡组生成一局训练"""
    s = (_rec('POST /session') or {}).get('body') or {}
    return build_match(_load()['decks'], deck_id, s, log)


def build_match(decks, deck_id, s, log):
    """用玩家所选卡组生成一局训练（AI 那一半随后由 ai_decks.replace_ai_deck 换掉）。
    decks = 玩家卡组列表，s = 登录回应（取玩家 id、名字）"""
    tpl = _template()
    md = tpl['match_and_starting_data']
    m, sd = md['match'], md['starting_data']
    decks = [d for d in decks if _usable(d)]
    deck = next((d for d in decks if d.get('id') == deck_id), None) or (decks[0] if decks else None)
    if deck is None:
        raise RuntimeError('没有可用的卡组')
    cards, loc = ai_decks.parse_deck_code(deck['deck_code'])
    me = 'left' if sd['player_id_left'] < 900000000 else 'right'
    ai = 'right' if me == 'left' else 'left'
    mid = random.randint(100000, 999999)
    base_id = {'left': sd['location_card_left']['card_id'], 'right': sd['location_card_right']['card_id']}
    n_hand = {x: len(sd[f'starting_hand_{x}']) for x in ('left', 'right')}
    for side in ('left', 'right'):
        names = list(cards)                      # AI 先拿玩家卡组占位（私服也是这样），随后被替换
        random.shuffle(names)
        ids = list(range(base_id[side] + 1, base_id[side] + 1 + len(names)))
        hand, rest = names[:n_hand[side]], names[n_hand[side]:]
        sd[f'starting_hand_{side}'] = [
            {'card_id': ids[i], 'is_gold': False, 'location': f'hand_{side}', 'location_number': i, 'name': n}
            for i, n in enumerate(hand)]
        sd[f'deck_{side}'] = [
            {'card_id': ids[len(hand) + i], 'is_gold': False, 'location': f'deck_{side}',
             'location_number': len(hand) + i, 'name': n} for i, n in enumerate(rest)]
        sd[f'location_card_{side}'] = dict(sd[f'location_card_{side}'],
                                           name=loc or ai_decks.HQ_BY_FACTION.get(deck['main_faction']),
                                           faction=deck['main_faction'])
        sd[f'ally_faction_{side}'] = (deck.get('ally_faction') or '').lower()
        sd[f'card_back_{side}'] = deck.get('card_back') or sd[f'card_back_{side}']
    sd[f'{me}_player_name'] = s.get('player_name') or sd[f'{me}_player_name']
    sd[f'{me}_player_tag'] = s.get('player_tag') or sd[f'{me}_player_tag']
    pid = s.get('player_id')
    if pid:                                      # 样本可能来自别的账号/服务器：玩家 id 换成当前登录的
        sd[f'player_id_{me}'] = m[f'player_id_{me}'] = pid
        if m.get('action_side') == me:
            m['action_player_id'] = pid
    m.update(match_id=mid, current_action_id=0, current_turn=1, actions=[], notifications=[], status='pending',
             winner_id=0, winner_side='', modify_date=json.dumps(_now_iso()),
             match_url=f'{LOCAL}/matches/v2/{mid}',
             actions_url=f'{LOCAL}/matches/v2/{mid}/actions')
    m[f'deck_id_{me}'] = deck.get('id')
    m[f'deck_id_{ai}'] = 0
    m[f'player_status_{me}'], m[f'player_status_{ai}'] = 'not_done', 'mulligan_done'
    log(f'[offline] 生成训练局 {mid}：玩家卡组「{deck.get("name")}」{len(cards)} 张')
    return tpl
