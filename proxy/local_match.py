# 本地人机对局：代理接管私服建好的 training 局，替 AI 发 XAction
# 私服只负责建局（生成 AI 套牌/起手），之后该局的所有请求都在本地处理，不再发往私服
import json, random, threading, time, sys, os, re

import paths  # noqa: E402,F401  设置数据目录
import card_db  # noqa: E402
from kards_codec import decode, encode  # noqa: E402
from ai_state import State  # noqa: E402
from ai_player import AIPlayer  # noqa: E402
import live_driver  # noqa: E402

# 新 AI：读客户端真实场面决策（需要游戏里的探针 + adb forward tcp:23456）；
# 设环境变量 KARDS_LIVE_AI=0 可退回旧的“猜场面”AI
USE_LIVE = os.environ.get('KARDS_LIVE_AI', '1') != '0'

# 抓包观察到的 索引 -> 密钥长度（客户端内置表），编码时只用这些组合
KEYLEN_BY_IDX = {0: 47, 1: 53, 2: 73, 4: 61, 6: 47, 7: 103, 9: 45, 13: 71, 17: 61, 19: 101,
                 21: 97, 22: 79, 26: 33, 28: 43, 30: 39, 32: 79, 33: 55, 34: 49, 35: 73,
                 36: 83, 38: 59, 39: 69, 41: 39, 43: 37, 44: 41, 48: 49, 49: 45, 50: 33,
                 51: 45, 53: 49, 54: 43, 55: 53, 56: 59, 58: 59, 63: 75, 65: 89, 66: 75,
                 69: 89, 71: 101, 74: 97}

AI_STEP_DELAY = 0.7  # AI 每个动作之间的间隔（秒）；客户端自己会排队播动画，原 1.5 秒叠加后显得卡
NO_DEPLOY_NEXT = ('card_event_tirpitz', 'card_event_u_99')   # 打出后对方下回合不能部署（同 card_rules）


def other(side):
    return 'right' if side == 'left' else 'left'


def enc(obj, key):
    idx = random.choice(list(KEYLEN_BY_IDX))
    return encode(json.dumps(obj, separators=(',', ':'), ensure_ascii=False), key, idx, KEYLEN_BY_IDX[idx])


class LocalMatch:
    def __init__(self, data, log):
        self.log = log
        self.raw = data  # 发给客户端的开局数据（AI 套牌已替换），重复请求时原样返回
        md = data['match_and_starting_data']
        self.m, self.sd = md['match'], md['starting_data']
        self.id = self.m['match_id']
        self.ai_side = 'right' if self.sd['player_id_right'] >= 900000000 else 'left'
        self.me_side = other(self.ai_side)
        self.pid = {s: self.sd[f'player_id_{s}'] for s in ('left', 'right')}
        self.status = {s: self.m[f'player_status_{s}'] for s in ('left', 'right')}
        self.match_status = 'running'
        # 先手：私服人机局总是 AI 先手。KARDS_FIRST=random(默认)/ai/me
        mode = os.environ.get('KARDS_FIRST', 'random')
        first = {'ai': self.ai_side, 'me': self.me_side}.get(mode) or random.choice((self.ai_side, self.me_side))
        self.m['action_side'], self.m['action_player_id'] = first, self.pid[first]
        self.first_side = first
        # 私服给的 start_side 和实际先手(action_side)不一致，客户端会报 "active side not matching starting turn"
        self.m['start_side'] = self.first_side
        self._fix_hand_sizes()
        self.hand = {s: list(self.sd[f'starting_hand_{s}']) for s in ('left', 'right')}
        self.deck = {s: list(self.sd[f'deck_{s}']) for s in ('left', 'right')}
        self.actions = []        # [(release_time, record_dict, encoded_str)]
        self.turn = 0
        # 动作里的数字键 = 行动方自己指挥部当前防御（客户端校验用，键名每局不同，如 "38"/"23"/"54"）
        self.hq_key = '38'
        self.ai_hq_client = None  # 客户端日志里报出的 AI 指挥部真实防御（最可靠）
        self.winner = None
        self.lock = threading.RLock()
        self.ai_turn_scheduled = False
        self.state, self.ai = None, None
        self.client_min_id = 0   # 客户端轮询时带的 min_action_id（= 已拉取到的下一个 id）
        self.live = live_driver.LiveDriver(log) if USE_LIVE and live_driver.AVAILABLE else None
        self.ai_no_deploy = False   # 玩家上回合打了提尔皮茨/U-99
        self.seen_ids = set()       # 动作记录里出现过的卡编号（估牌库剩余张数用）
        self.en_planted = {}        # 玩家本回合埋下的反制 {卡id: 卡名}
        if self.live is not None:
            # 覆盖率：双方卡组里 AI 还不认识效果的牌（开局写一次日志）
            self.live.coverage({s: [c.get('name') for c in self.sd[f'starting_hand_{s}'] + self.sd[f'deck_{s}']]
                                for s in ('left', 'right')}, self.ai_side, self.id)
        self.log(f'[local] 接管人机局 {self.id}: 我方 {self.me_side}({self.pid[self.me_side]}) '
                 f'AI {self.ai_side}({self.pid[self.ai_side]}) 先手 {self.first_side}')

    def _fix_hand_sizes(self):
        """起手牌数按先后手改正：先手 4 张（第 1 回合不抽），后手 5 张。
        私服总是给 left 4 张、right 5 张，不管谁先手；AI(right) 先手时就变成先手 5 张、后手 4 张。
        多的一张放回牌库顶，少的一方从牌库顶补一张，然后重排 location_number"""
        first, second = self.first_side, other(self.first_side)
        sd = self.sd
        moved = False
        sd[f'deck_{first}'] = sorted(sd[f'deck_{first}'], key=lambda c: c['location_number'])
        while len(sd[f'starting_hand_{first}']) > 4:
            c = sd[f'starting_hand_{first}'].pop()
            sd[f'deck_{first}'].insert(0, c)
            moved = True
        while len(sd[f'starting_hand_{second}']) < 5 and sd[f'deck_{second}']:
            deck = sorted(sd[f'deck_{second}'], key=lambda c: c['location_number'])
            c = deck[0]
            sd[f'deck_{second}'].remove(c)
            sd[f'starting_hand_{second}'].append(c)
            moved = True
        if not moved:
            return
        for s in (first, second):
            hand = sd[f'starting_hand_{s}']
            deck = sd[f'deck_{s}'] if s == first else sorted(sd[f'deck_{s}'], key=lambda c: c['location_number'])
            sd[f'deck_{s}'] = deck
            for i, c in enumerate(hand):
                c.update(location=f'hand_{s}', location_number=i)
            for i, c in enumerate(deck):
                c.update(location=f'deck_{s}', location_number=len(hand) + i)
        self.log(f'[local] 起手牌数改正：先手 {first} {len(sd[f"starting_hand_{first}"])} 张，'
                 f'后手 {second} {len(sd[f"starting_hand_{second}"])} 张')

    # ---------- 动作记录 ----------
    def _append(self, action_type, player_id, action_data, delay=0.0, key=None, extra=None):
        """按私服格式追加一条服务器侧动作记录；delay>0 时延迟对客户端可见"""
        with self.lock:
            if action_type == 'XActionStartOfTurn':
                self.turn += 1
            rec = {'action_id': len(self.actions) + 1, 'action_type': action_type,
                   'player_id': player_id, 'action_data': action_data, 'sub_actions': [],
                   'turn_number': max(self.turn, 1), 'action': '', 'value': None,
                   'send_action_id': self.id if key is None else key}
            if extra:
                rec.update(extra)
            if action_type.startswith('XAction'):
                rec['local_subactions'] = 1
            base = self.actions[-1][0] if self.actions else time.time()
            release = max(time.time(), base) + delay
            self.actions.append((release, rec, enc(rec, self.id if key is None else key)))
            self.log(f'[local {self.id}] +#{rec["action_id"]} {action_type or rec["action"]} '
                     f'by {player_id} t{rec["turn_number"]}')
            return rec

    def _released(self, min_id):
        now = time.time()
        vis = [a for a in self.actions if a[0] <= now]
        return vis, [a[2] for a in vis if a[1]['action_id'] >= min_id]

    # ---------- AI ----------
    def _ensure_state(self):
        """双方起手调度后，按最终手牌/牌库建状态模型"""
        if self.state is None:
            sd = dict(self.sd)
            for s in ('left', 'right'):
                sd[f'starting_hand_{s}'], sd[f'deck_{s}'] = self.hand[s], self.deck[s]
            self.state = State(sd)
            hq = {s: self.sd[f'location_card_{s}']['name'] for s in ('left', 'right')}
            self.ai = AIPlayer(self.state, self.ai_side, hq)
        return self.state

    def _ai_turn(self):
        if self.live is not None:
            # 新 AI 每一步都要等客户端播完，不能占着 HTTP 线程：放到后台线程
            threading.Thread(target=self._live_turn, daemon=True).start()
            return
        self._guess_turn()

    def _deck_left(self):
        """双方牌库剩余张数（估算）：开局牌库里“从没见过的牌”数，再用“至少自然抽了几张”封顶。
        见过 = 出现在动作记录里的卡编号（玩家打出、AI 快照里看到的由驱动另记）；爆牌/没打出的牌看不到，
        所以再按“起手后每个己方回合抽 1 张”取较小值。塞进牌库的牌（神风、抵抗）由驱动加回去"""
        out = {}
        for s in ('left', 'right'):
            ids = {c['card_id'] for c in self.deck[s]}
            seen = ids & (self.seen_ids | (self.live.seen_ids if self.live else set()))
            # 第 n 个全局回合：先手方已开始 ceil(n/2) 个回合，后手 floor(n/2)；先手第 1 回合不抽
            n = max(1, self.turn)
            mine = (n + 1) // 2 if s == self.first_side else n // 2
            drawn = max(0, mine - (1 if s == self.first_side else 0))
            out[s] = max(0, min(len(ids) - len(seen), len(ids) - drawn))
        return out

    def _live_turn(self):
        """新 AI 回合：开始 -> 逐步（读真实场面 -> 决策 -> 发动作 -> 等播完）-> 结束"""
        ai = self.pid[self.ai_side]
        st = self._ensure_state()
        hqv = self.ai_hq_client if self.ai_hq_client is not None else st.hq_def[self.ai_side]
        x = {self.hq_key: str(hqv)}
        rec = self._append('XActionStartOfTurn', ai, {**x, 'side': self.ai_side}, delay=AI_STEP_DELAY)
        self.live.wait_idle(lambda: self.client_min_id, rec['action_id'])
        result = 'error'
        try:
            # 牌库张数（手牌爆炸卡组要算对方抽空；先打出 AI 自己回合开始的那一张，所以 self.turn 已经 +1）
            left = self._deck_left()
            add = self.live.memo.get('deck_added', {})
            burned = self.live.memo.get('burned', {})
            mem = self.live.memo
            mem['deck_n'] = {s: 0 if s in mem.get('deck_empty', ()) else max(0, left[s] + add.get(s, 0) - burned.get(s, 0))
                             for s in left}
            mem.setdefault('fatigue', {'left': 0, 'right': 0})
            mem['deck_known'] = True
            mem['en_planted'] = dict(self.en_planted)
            self.log(f'[local {self.id}] 牌库估算 {mem["deck_n"]}（塞入 {add}，爆掉 {burned}）疲惫 {mem["fatigue"]}'
                     + (f' 对方挂着反制 {sorted(set(self.en_planted.values()))}' if self.en_planted else ''))
        except Exception as e:
            self.log(f'[local {self.id}] 牌库张数估算失败 {e!r}')
        try:
            no_dep, self.ai_no_deploy = self.ai_no_deploy, False
            result = self.live.play_turn(self.ai_side, lambda at, ad: self._append(at, ai, ad),
                                         lambda: self.client_min_id, self.hq_key,
                                         lambda: self.match_status == 'finished', no_deploy=no_dep,
                                         turn=self.turn)
        except Exception as e:  # 任何异常都只结束回合，不发可能非法的动作
            self.log(f'[local {self.id}] 新 AI 出错 {e!r}')
        self.log(f'[local {self.id}] 新 AI 回合结束：{result}')
        if self.match_status == 'finished':
            return   # 对局已结束，不再发结束回合
        self._append('XActionEndOfTurn', ai, {**x, 'side': self.ai_side, 'reason': 'endTurnButton'},
                     delay=AI_STEP_DELAY)

    def _guess_turn(self):
        """旧 AI 回合（猜场面）：开始 -> 部署/推进/攻击 -> 结束"""
        ai = self.pid[self.ai_side]
        st = self._ensure_state()
        if self.ai_hq_client is not None:
            st.hq_def[self.ai_side] = self.ai_hq_client
        x = {self.hq_key: str(st.hq_def[self.ai_side])}
        self._append('XActionStartOfTurn', ai, {**x, 'side': self.ai_side}, delay=AI_STEP_DELAY)
        try:
            acts = self.ai.take_turn(x)
        except Exception as e:  # AI 出错也要结束回合，避免卡死
            self.log(f'[local {self.id}] AI 出错 {e!r}')
            acts = []
        for at, ad in acts:
            self._append(at, ai, ad, delay=AI_STEP_DELAY)
        self.log(f'[local {self.id}] AI 回合后 指挥点 {st.kredits[self.ai_side]}/{st.max_kredits[self.ai_side]} '
                 f'前线 {st.front} AI支援 {st.support[self.ai_side]} 玩家支援 {st.support[self.me_side]} '
                 f'HQ {st.hq_def}')
        self._append('XActionEndOfTurn', ai, {**x, 'side': self.ai_side, 'reason': 'endTurnButton'},
                     delay=AI_STEP_DELAY)

    def _maybe_start(self):
        """双方都完成起手调度后，若 AI 先手则让 AI 走第一回合"""
        if self.ai_turn_scheduled:
            return
        if all(v == 'mulligan_done' for v in self.status.values()) and self.first_side == self.ai_side:
            self.ai_turn_scheduled = True
            self._ai_turn()

    # ---------- 起手调度 ----------
    def reconnect_payload(self):
        """断线重连时返回的开局数据：起手/牌库为调度后的实际结果，状态为进行中；
        客户端随后从 min_action_id=1 轮询，按本地记录的动作重放到当前局面"""
        import copy
        d = copy.deepcopy(self.raw)
        md = d['match_and_starting_data']
        for s in ('left', 'right'):
            md['starting_data'][f'starting_hand_{s}'] = self.hand[s]
            md['starting_data'][f'deck_{s}'] = self.deck[s]
            md['match'][f'player_status_{s}'] = self.status[s]
        md['match']['status'] = self.match_status
        return d

    def _mulligan(self, side, discarded):
        """被换掉的手牌与牌库中随机一张互换位置（与抓包中私服行为一致）
        同一方只调度一次：重连后客户端会再发一次，原样返回第一次的结果，避免手牌被二次洗换"""
        if self.status.get(side) == 'mulligan_done' and getattr(self, '_mull_res', {}).get(side):
            return self._mull_res[side]
        res = self._mulligan_once(side, discarded)
        self.__dict__.setdefault('_mull_res', {})[side] = res
        return res

    def _mulligan_once(self, side, discarded):
        repl = []
        for cid in discarded:
            hi = next((i for i, c in enumerate(self.hand[side]) if c['card_id'] == cid), None)
            if hi is None or not self.deck[side]:
                continue
            di = random.randrange(len(self.deck[side]))
            h, d = self.hand[side][hi], self.deck[side][di]
            nh = dict(d, location=f'hand_{side}', location_number=h['location_number'])
            nd = dict(h, location=f'deck_{side}', location_number=d['location_number'])
            self.hand[side][hi], self.deck[side][di] = nh, nd
            repl.append(nh)
        self.status[side] = 'mulligan_done'
        return {'deck': self.deck[side], 'replacement_cards': repl}

    # ---------- 结束对局 ----------
    def _end(self, sender_pid, value):
        if self.winner is not None:
            return
        win_side = value.get('winner_side') or ''
        lose_side = other(win_side) if win_side in ('left', 'right') else None
        self.winner = win_side
        self._append('ActionEndMatch', sender_pid,
                     {'reason': value.get('result', ''), 'winner_side': win_side})
        if lose_side:
            hq = self.sd[f'location_card_{lose_side}']['card_id']
            self._append('XActionCheat', sender_pid,
                         {'0': 'DamageCard', '1': str(hq), '2': '99', 'playerID': sender_pid}, key=0)
        rec = self._append('', None, None)
        rec.update(action='end-match', value=value)
        rec.pop('local_subactions', None)
        # 重新编码（rec 已被修改）
        self.actions[-1] = (self.actions[-1][0], rec, enc(rec, self.id))
        self.match_status = 'finished'
        self.log(f'[local {self.id}] 对局结束 winner={win_side} result={value.get("result")}')

    def client_report(self, err):
        """客户端日志上报：'HQ defense not matching ... >>M:{id} - i1: {值}' 里的值是 AI 指挥部的真实防御"""
        m = re.search(r'HQ defense not matching.*>>M:(\d+).*i1: (-?\d+)', err)
        if m and int(m.group(1)) == self.id:
            with self.lock:
                self.ai_hq_client = int(m.group(2))

    # ---------- 玩家提交的动作 ----------
    def _player_action(self, obj):
        at = obj.get('action_type', '')
        ad = obj.get('action_data') or {}
        if at in ('XActionStartOfTurn', 'XActionEndOfTurn'):
            ex = {k: v for k, v in ad.items() if k.isdigit()}
            if ex:
                # 这个数字字段是“行动方自己指挥部的当前防御”，客户端会校验；键名每局不同
                self.hq_key = next(iter(ex))
                try:
                    self._ensure_state().hq_def[self.me_side] = int(ex[self.hq_key])
                except ValueError:
                    pass
        self.log(f'[local {self.id}] 玩家 {at} {json.dumps(ad, ensure_ascii=False)[:160]}')
        if at == 'XActionPlayCardFromHand' and ad.get('card_name') in NO_DEPLOY_NEXT:
            self.ai_no_deploy = True     # 提尔皮茨/U-99：AI 下回合不能部署
        for key in ('cardID', 'attackerCardID', 'defenderCardID', 'targetCardID'):
            if isinstance(ad.get(key), int):
                self.seen_ids.add(ad[key])     # 打出/行动过的牌：已经不在牌库里（估牌库剩余用）
        if at == 'XActionStartOfTurn':
            self.en_planted = {}               # 反制没触发到自己回合就失效，要重新花费激活（Kards规则.txt）
            if self.live is not None:
                self.live.memo['en_played'] = 0
        elif at == 'XActionPlayCardFromHand' and str(ad.get('location', '')).startswith('Hand') and \
                (card_db.get(ad.get('card_name')) or {}).get('type') == 'countermeasure':
            # 玩家埋反制：location 是自己手牌（实测“来自深处”）。AI 回合里卡还在玩家手牌就算挂着
            self.en_planted[ad.get('cardID')] = ad.get('card_name')
            self.log(f'[local {self.id}] 玩家埋下反制 {ad.get("card_name")}#{ad.get("cardID")}')
        elif at == 'XActionPlayCardFromHand' and self.live is not None:
            # 玩家本回合打出的牌数（埋下的反制还留在手牌里，不算）：用来判断他回合开始有没有抽到牌
            self.live.memo['en_played'] = self.live.memo.get('en_played', 0) + 1
        rec = self._append(at, obj.get('player_id', self.pid[self.me_side]), ad)
        st = self._ensure_state()
        st.apply(rec)
        subs = obj.get('sub_actions') or []
        if subs:
            # 客户端回传的真实结算结果：存档供分析，并用来校正场面
            with open(os.path.join(os.path.dirname(__file__), 'subactions_log.jsonl'), 'a', encoding='utf-8') as f:
                f.write(json.dumps({'match': self.id, 'action': at, 'action_data': ad, 'sub_actions': subs},
                                   ensure_ascii=False) + '\n')
            n = st.apply_subactions(subs)
            self.log(f'[local {self.id}] 收到 {len(subs)} 条结算结果，校正 {n} 处')
        st.sanity(self.me_side)
        if at == 'XActionEndOfTurn':
            self._ai_turn()

    # ---------- HTTP 入口 ----------
    def handle(self, method, sub, body):
        """sub 为 /matches/v2/{id} 之后的路径；返回 (状态码, 字节串)"""
        with self.lock:
            j = {}
            if body:
                try:
                    j = json.loads(body)
                except Exception:
                    j = {}
            if method == 'GET' and sub == '':
                return 200, self.match_status.encode()
            if method == 'PUT' and sub == '':
                if j.get('action') == 'lvl-loaded':
                    return 200, b'{"otherPlayerReady":1}'
                if 'a' in j:
                    obj = json.loads(decode(j['a'])[0])
                    if obj.get('action') == 'end-match':
                        self._end(self.pid[self.me_side], obj.get('value') or {})
                    else:
                        self.log(f'[local {self.id}] 未知 PUT 动作 {obj}')
                    return 200, b'OK'
                self.log(f'[local {self.id}] 未知 PUT {j}')
                return 200, b'OK'
            if sub.startswith('/mulligan'):
                if method == 'POST':
                    res = self._mulligan(self.me_side, j.get('discarded_card_ids') or [])
                    self._maybe_start()
                    return 201, json.dumps(res, ensure_ascii=False).encode()
                side = sub.rsplit('/', 1)[-1]
                if side == self.ai_side and self.status[side] != 'mulligan_done':
                    self.status[side] = 'mulligan_done'
                res = {'deck': self.deck[side], 'replacement_cards': []}
                self._maybe_start()
                return 200, json.dumps(res, ensure_ascii=False).encode()
            if sub == '/actions':
                if method == 'POST':
                    self._player_action(json.loads(decode(j['a'])[0]))
                    return 201, b'OK'
                self.client_min_id = max(self.client_min_id, int(j.get('min_action_id', 1)))
                vis, new = self._released(int(j.get('min_action_id', 1)))
                res = {'actions': new,
                       'match': {'player_status_left': self.status['left'],
                                 'player_status_right': self.status['right'],
                                 'status': self.match_status},
                       'opponent_polling': True,
                       'current_action_id': len(vis) + 1, 'total_actions': len(vis)}
                return 200, json.dumps(res).encode()
            if sub == '/post':
                me = self.me_side
                fac = self.sd[f'location_card_{me}'].get('faction', '')
                return 200, json.dumps({'faction': fac, 'winner': self.winner == me}).encode()
            self.log(f'[local {self.id}] 未处理 {method} {sub} {body[:200] if body else b""}')
            return 200, b'OK'
