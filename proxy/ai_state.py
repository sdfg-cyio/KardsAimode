# 对局状态的简化模型：由双方 XAction 推演手牌、牌库、指挥点和战线
# 只做 AI 决策需要的近似；卡牌特效不模拟，偏差靠保守决策兜住
import re
import card_db

LINE_MAX = 5  # 每条战线最多单位数


class Unit:
    def __init__(self, cid, name, side, turn):
        info = card_db.get(name) or {}
        self.id, self.name, self.side = cid, name, side
        self.type = info.get('type')
        self.attack = info.get('attack', 0)
        self.defense = info.get('defense', 0)
        self.op = info.get('op', 0)
        self.attrs = set(info.get('attrs', ()))
        self.deployed_turn = turn
        self.acted_turn = -1  # 本回合已移动或攻击

    def __repr__(self):
        return f'{self.name[10:]}#{self.id}({self.attack}/{self.defense})'


class State:
    def __init__(self, sd):
        self.hand = {s: [(c['card_id'], c['name']) for c in sd[f'starting_hand_{s}']] for s in ('left', 'right')}
        self.deck = {s: [(c['card_id'], c['name']) for c in sorted(sd[f'deck_{s}'], key=lambda c: c['location_number'])]
                     for s in ('left', 'right')}
        self.hq = {s: sd[f'location_card_{s}']['card_id'] for s in ('left', 'right')}
        self.hq_def = {'left': 20, 'right': 20}
        self.support = {'left': [], 'right': []}  # Board_HQLeft / Board_HQRight
        self.front = []                           # Board_Frontline（同一时间只属于一方）
        self.max_kredits = {'left': 0, 'right': 0}
        self.kredits = {'left': 0, 'right': 0}
        self.turn = 0

    # ---------- 查询 ----------
    def front_owner(self):
        return self.front[0].side if self.front else None

    def units(self, side):
        return [u for u in self.support[side] + self.front if u.side == side]

    def find(self, cid):
        for line in (self.support['left'], self.support['right'], self.front):
            for u in line:
                if u.id == cid:
                    return u, line
        return None, None

    # ---------- 从动作推演 ----------
    def apply(self, rec):
        """rec 为服务器侧动作记录（双方的都走这里）"""
        at, ad = rec.get('action_type'), rec.get('action_data') or {}
        try:
            if at == 'XActionStartOfTurn':
                self.start_turn(ad['side'])
            elif at == 'XActionPlayCardFromHand':
                side = 'left' if ad['location'] in ('Board_HQLeft',) else (
                    'right' if ad['location'] == 'Board_HQRight' else self._side_of_hand(int(ad['cardID'])))
                self.play(side, int(ad['cardID']), ad['location'], int(ad.get('locationNumber', 0)),
                          ad.get('card_name'))
                self.order_effect(side, ad.get('card_name', ''), int(ad.get('targetCardID') or 0))
            elif at == 'XActionMoveCardToLine':
                self.move(int(ad['cardID']), int(ad.get('locationNumber', 0)))
            elif at == 'XActionAttackCard':
                self.attack(int(ad['attackerCardID']), int(ad['defenderCardID']))
        except (KeyError, ValueError):
            pass

    # ---------- 用客户端结算结果校正 ----------
    def _remove(self, cid):
        u, line = self.find(cid)
        if u:
            line.remove(u)
            return 1
        return 0

    def apply_subactions(self, subs):
        """sub_actions 字段格式尚未完全确认，按常见字段名宽松处理；返回校正次数"""
        n = 0
        for s in subs:
            if isinstance(s, str):
                try:
                    import json
                    s = json.loads(s)
                except Exception:
                    continue
            if not isinstance(s, dict):
                continue
            t = str(s.get('action_type') or s.get('type') or s.get('name') or '')
            d = s.get('action_data') or s.get('data') or s
            if 'Destroy' in t or 'RemoveCardFromBoard' in t:
                ids = d.get('cardsToDestroy') or d.get('cardIDs') or [d.get('cardID') or d.get('targetCardID')]
                for cid in ids if isinstance(ids, list) else [ids]:
                    if cid is not None:
                        n += self._remove(int(cid))
            elif 'Damage' in t or 'SetDefense' in t or 'GainDefense' in t or 'LoseDefense' in t:
                cid = d.get('cardID') or d.get('targetCardID')
                val = d.get('newDefenseValue', d.get('defense', d.get('newDefense')))
                if cid is not None and val is not None:
                    if int(cid) in self.hq.values():
                        side = 'left' if self.hq['left'] == int(cid) else 'right'
                        self.hq_def[side] = int(val)
                        n += 1
                    else:
                        u, _ = self.find(int(cid))
                        if u:
                            u.defense = int(val)
                            n += 1
                            if u.defense <= 0:
                                self._remove(u.id)
            elif 'GainAttack' in t or 'LoseAttack' in t:
                u, _ = self.find(int(d.get('cardID', -1)))
                val = d.get('newAttackValue')
                if u and val is not None:
                    u.attack = int(val)
                    n += 1
            elif 'ChangeKredits' in t:
                side = d.get('side')
                if side in self.kredits and d.get('newKredits') is not None:
                    self.kredits[side] = int(d['newKredits'])
                    if d.get('newMaxKredits') is not None:
                        self.max_kredits[side] = int(d['newMaxKredits'])
                    n += 1
        return n

    def sanity(self, me):
        """规则约束兜底：前线同一时间只属于一方。玩家单位进了前线，说明 AI 的前线单位已不存在"""
        if any(u.side == me for u in self.front):
            gone = [u for u in self.front if u.side != me]
            for u in gone:
                self.front.remove(u)
            return len(gone)
        return 0

    def _side_of_hand(self, cid):
        return 'left' if any(c[0] == cid for c in self.hand['left']) else 'right'

    # ---------- 常见指令效果（按卡面英文文本粗略匹配） ----------
    def _damage(self, u, n):
        u.defense -= n
        if u.defense <= 0:
            self._remove(u.id)

    def order_effect(self, side, name, target):
        info = card_db.get(name) or {}
        if info.get('type') not in ('order', 'countermeasure'):
            return
        t = info.get('text', '').lower()
        foe = 'right' if side == 'left' else 'left'
        foes = [u for u in self.support[foe] + self.front if u.side == foe]
        m = re.search(r'deal (\d+) damage to all enem(y units|ies)', t)
        if m:
            for u in list(foes):
                self._damage(u, int(m.group(1)))
            if m.group(2) == 'ies':
                self.hq_def[foe] -= int(m.group(1))
        m = re.search(r'deal (\d+) damage to (an? |target )?(enemy )?(unit|target)', t)
        if m and target:
            u, _ = self.find(target)
            if u:
                self._damage(u, int(m.group(1)))
        if re.search(r'destroy (a |target )?(enemy )?unit', t) and target:
            self._remove(target)
        if 'swap the attack and operation cost' in t and target:
            u, _ = self.find(target)
            if u:
                u.attack, u.op = u.op, u.attack
        if 'all enemy units retreat' in t:
            for u in [u for u in self.front if u.side == foe]:
                self.front.remove(u)
                if len(self.support[foe]) < LINE_MAX:
                    self.support[foe].append(u)

    # ---------- 状态推演 ----------
    def start_turn(self, side):
        self.turn += 1
        self.max_kredits[side] = min(self.max_kredits[side] + 1, 12)
        self.kredits[side] = self.max_kredits[side]
        # 先手方第一回合不抽牌（实机验证：按“每回合都抽”推算，AI 会打出客户端认为还在牌库里的卡，
        # 客户端报 "Visual card not found in PlayFromHand"，之后动作队列卡死）
        if self.turn == 1:
            return
        if self.deck[side]:
            self.hand[side].append(self.deck[side].pop(0))

    def play(self, side, cid, location, loc_num, name=None):
        card = next((c for c in self.hand[side] if c[0] == cid), None)
        if card is not None:
            self.hand[side].remove(card)
            name = card[1]
        elif not name:
            return
        # 不在模型手牌里的（特效生成，如 Middlesex 部署时给的 Garrison）：按动作里的卡名照样上场
        self.kredits[side] -= (card_db.get(name) or {}).get('kredits', 0)
        if card_db.is_unit(name):
            u = Unit(cid, name, side, self.turn)
            line = self.front if location == 'Board_Frontline' else self.support[side]
            line.insert(min(loc_num, len(line)), u)

    def move(self, cid, loc_num):
        u, line = self.find(cid)
        if not u:
            return
        line.remove(u)
        self.front.insert(min(loc_num, len(self.front)), u)
        self.kredits[u.side] -= u.op
        u.acted_turn = self.turn

    def attack(self, att_id, def_id):
        a, _ = self.find(att_id)
        if not a:
            return
        a.acted_turn = self.turn
        self.kredits[a.side] -= a.op
        if def_id in self.hq.values():
            side = 'left' if self.hq['left'] == def_id else 'right'
            self.hq_def[side] -= a.attack
            return
        d, dline = self.find(def_id)
        if not d:
            return
        d.defense -= a.attack
        # 反击：火炮、轰炸机攻击不受反击；被攻击的火炮/轰炸机不反击（简化）
        if a.type not in ('artillery', 'bomber') and d.type not in ('artillery', 'bomber'):
            a.defense -= d.attack
        for u in (a, d):
            if u.defense <= 0:
                _, ln = self.find(u.id)
                if ln is not None:
                    ln.remove(u)
