# AI 回合决策：部署 -> 推进前线 -> 攻击；边决策边更新状态模型
# 返回 [(action_type, action_data)]，由 LocalMatch 依次发给客户端
import card_db

GROUND = ('infantry', 'tank')
RANGED = ('artillery', 'fighter', 'bomber')  # 可直接打任意目标（简化）


class AIPlayer:
    def __init__(self, state, side, hq_names):
        self.st, self.side = state, side
        self.enemy = 'left' if side == 'right' else 'right'
        self.hq_names = hq_names  # side -> 指挥部卡名
        self.loc = 'Board_HQRight' if side == 'right' else 'Board_HQLeft'

    # ---------- 动作构造（字段格式照抄抓包） ----------
    def _play(self, cid, name, num, x):
        return 'XActionPlayCardFromHand', {
            '0': str(cid), '1': str(num), '2': '0', '3': '0', '4': card_db.code(name), **x,
            'cardID': cid, 'location': self.loc, 'locationNumber': num, 'targetCardID': 0,
            'card_name': name, 'chooseOneIndex': 0}

    def _move(self, u, num, x):
        return 'XActionMoveCardToLine', {
            '0': str(u.id), '1': str(num), '2': card_db.code(u.name), **x,
            'cardID': u.id, 'location': 'Board_Frontline', 'card_name': u.name, 'locationNumber': num}

    def _attack(self, u, did, dname, x):
        return 'XActionAttackCard', {
            '0': str(u.id), '1': str(did), '2': card_db.code(u.name), '3': card_db.code(dname), **x,
            'attackerCardID': u.id, 'defenderCardID': did,
            'attacker_card_name': u.name, 'defender_card_name': dname}

    # ---------- 规则判断（简化） ----------
    def _can_act(self, u):
        if u.acted_turn == self.st.turn:
            return False
        if u.deployed_turn == self.st.turn and 'blitz' not in u.attrs:
            return False
        # 指挥点模型可能有偏差（客户端报过 "pay movement cost ... doesn't have enough kredits"）：
        # 行动费用必须严格在预算内，且预算不能为负
        k = self.st.kredits[self.side]
        return k >= 0 and u.op <= k

    def _targets(self, u, in_front):
        """返回可攻击目标 [(id, name, unit或None)]，None 表示敌方指挥部"""
        st, e = self.st, self.enemy
        e_front = [v for v in st.front if v.side == e]
        e_support = st.support[e]
        guards = [v for v in e_support if 'guard' in v.attrs]
        hq = (st.hq[e], self.hq_names[e], None)
        if u.type in RANGED:
            if guards:
                return [(g.id, g.name, g) for g in guards] + [(v.id, v.name, v) for v in e_front]
            return [hq] + [(v.id, v.name, v) for v in e_front + e_support]
        if in_front:  # 前线地面单位：打敌方支援线或指挥部（受守护限制）
            if guards:
                return [(g.id, g.name, g) for g in guards]
            return [hq] + [(v.id, v.name, v) for v in e_support]
        # 支援线地面单位：只能打敌方前线单位
        return [(v.id, v.name, v) for v in e_front]

    def _score(self, u, t):
        """攻击评分：击杀加分，自己阵亡扣分；打指挥部按伤害计"""
        _, _, v = t
        if v is None:
            return 1.0 + u.attack * 0.6
        if 'smokescreen' in v.attrs:
            return -99
        kill = u.attack >= v.defense
        counter = 0 if (u.type in ('artillery', 'bomber') or v.type in ('artillery', 'bomber')) else v.attack
        die = counter >= u.defense
        s = (3 + card_db.get(v.name).get('kredits', 1) if kill else u.attack * 0.3) - (4 if die else 0)
        return s

    # ---------- 主流程 ----------
    def take_turn(self, x):
        st, me = self.st, self.side
        out = []
        st.start_turn(me)
        # 先用场上已有单位行动（推进/攻击），再用剩下的指挥点部署。
        # 原先先部署会把指挥点花光，导致后期单位全堆在支援线、从不上前线
        self._act(out, x)
        self._deploy(out, x)
        self._act(out, x)  # 新部署的闪击单位可以当回合行动
        return out

    def _deploy(self, out, x):
        st, me = self.st, self.side
        hand = sorted(st.hand[me], key=lambda c: -(card_db.get(c[1]) or {}).get('kredits', 99))
        for cid, name in hand:
            info = card_db.get(name)
            if not info or not card_db.is_unit(name):
                continue
            if info['kredits'] > st.kredits[me] or len(st.support[me]) >= 5:
                continue
            num = len(st.support[me])
            out.append(self._play(cid, name, num, x))
            st.play(me, cid, self.loc, num)

    def _act(self, out, x):
        """行动：远程优先，然后前线单位，最后支援线地面单位"""
        st, me = self.st, self.side
        for _ in range(12):
            acted = False
            units = sorted(st.units(me), key=lambda u: (u.type not in RANGED, u not in st.front))
            for u in units:
                if not self._can_act(u):
                    continue
                in_front = u in st.front
                tg = self._targets(u, in_front)
                best = max(tg, key=lambda t: self._score(u, t)) if tg else None
                if best and self._score(u, best) > 0.5:
                    out.append(self._attack(u, best[0], best[1], x))
                    st.attack(u.id, best[0])
                    acted = True
                    break
                # 没有好目标：地面单位推进到前线（前线空或归我方）
                if (u.type in GROUND and not in_front and st.front_owner() in (None, me)
                        and len(st.front) < 5):
                    num = len(st.front)
                    out.append(self._move(u, num, x))
                    st.move(u.id, num)
                    acted = True
                    break
            if not acted:
                break
        return out
