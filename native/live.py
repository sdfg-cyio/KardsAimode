# 从客户端内存读取真实对局场面（经探针在游戏线程调用客户端自己的函数）
import struct
from ue import UE

CF = '/Game/Blueprints/Cards/BP_CardFunctions.BP_CardFunctions_C'
PM = '/Game/Blueprints/BP_PlayerMoves.BP_PlayerMoves_C'
CARD = '/Script/kards.BaseCardObject'

# 枚举（实测）
SIDE = {'left': 1, 'right': 2}
LOC = {1: 'deck_left', 2: 'deck_right', 3: 'hand_left', 4: 'hand_right', 5: 'support_left',
       6: 'support_right', 7: 'front', 8: 'discard', 9: 'deck'}
TYPE = {1: 'location', 2: 'order', 3: 'tank', 4: 'fighter', 5: 'bomber', 6: 'infantry', 7: 'artillery',
        8: 'antiair', 9: 'antitank', 10: 'tankdestroyer', 11: 'gotcha', 12: 'wildcard'}

# 每张卡要问客户端的取值函数 -> 结果字段
CARD_Q = [('getTotalAttack', 'atk'), ('getTotalDefense', 'df'), ('getTotalOperationCost', 'op'),
          ('getTotalKreditCost', 'cost'), ('HasAttackLeft', 'can_attack'), ('HasMovementLeft', 'can_move'),
          ('getHasGuard', 'guard'), ('getHasSmokescreen', 'smoke'), ('IsPinned', 'pinned'),
          ('getHasBlitz', 'blitz'), ('CanMoveAndAttackInTheSameTurn', 'move_and_attack'),
          ('HasCantAttack', 'cant_attack'),
          # 战斗词条（规则见 Kards规则.txt）
          ('getHasAmbush', 'ambush'), ('getHasShock', 'shock'), ('getTotalHeavyArmor', 'armor'),
          ('getHasFury', 'fury')]


class Card:
    def __init__(self, obj):
        self.obj = obj

    def __repr__(self):
        return '%s#%d(%d/%d %s)' % (self.name[5:30], self.id, getattr(self, 'atk', 0), getattr(self, 'df', 0),
                                    self.loc)


class Live:
    def __init__(self, ue=None):
        self.ue = ue or UE()
        self.ready = False

    def refresh(self):
        """每局开始/每个 AI 回合开始时调用：重建对象索引、装钩子、找到本局的单例对象"""
        ue = self.ue
        ue.index()
        ue.setup_calls()
        self.f = {n: ue.find_func(CF, n) for n in (
            'GetCardsInHandBySide', 'GetCardsInSupportLineBySide', 'GetCardsInFrontlineBySide',
            'GetKreditsBySide', 'GetMaxKreditsBySide', 'DoesSideControlTheFrontline', 'IsLocationFull',
            'GetLocationCardBySide', 'GetTurnNumber', 'GetPlayingSide', 'GetClientSide')}
        self.cf_f = {n: ue.find_func(CARD, n) for n, _ in CARD_Q}
        self.q_running = ue.find_func(PM, 'IsAnyQueueRunning')
        cands = ue.instances('BP_CardFunctions_C')
        pms = ue.instances('BP_PlayerMoves_C')
        # 有多个实例时，选能取到本方手牌/指挥部的那个（属于当前对局关卡）
        self.cf = None
        for c in cands:
            r = ue.call_many([(c, self.f['GetLocationCardBySide'], {'side': 1})])[0]
            if r and r.get('card'):
                self.cf = c
                break
        self.pm = pms[-1] if pms else None
        self.ready = self.cf is not None
        return self.ready

    def busy(self):
        """客户端是否还在播放/结算动作队列"""
        if not self.pm or not self.q_running:
            return False
        r = self.ue.call_many([(self.pm, self.q_running, {})])[0]
        return bool(r and r.get('isIt'))

    def _cards(self, objs):
        """读卡牌原始字段 + 批量调用取值函数"""
        ue = self.ue
        cards = []
        for o in objs:
            d = ue.p.read(o, 0x290)
            if len(d) < 0x290:
                continue
            c = Card(o)
            c.name = ue.name(*struct.unpack_from('<II', d, 0x50))
            c.type = TYPE.get(d[0x68], '?')
            c.id = struct.unpack_from('<i', d, 0x264)[0]
            c.loc = LOC.get(d[0x275], '?')
            c.side = {1: 'left', 2: 'right'}.get(d[0x276], '?')
            c.slot = struct.unpack_from('<i', d, 0x278)[0]
            c.enter_turn = struct.unpack_from('<i', d, 0x270)[0]
            c.covert = bool(d[0x1ea])     # hasCovert：隐蔽单位无法被指向（保守：带隐蔽就不选为效果目标）
            cards.append(c)
        calls = [(c.obj, self.cf_f[n], {}) for c in cards for n, _ in CARD_Q if self.cf_f[n]]
        res = ue.call_many(calls) if calls else []
        i = 0
        for c in cards:
            for n, key in CARD_Q:
                if not self.cf_f[n]:
                    continue
                r = res[i]
                i += 1
                setattr(c, key, list(r.values())[0] if r else None)
        return cards

    def snapshot(self):
        """返回当前真实场面 dict"""
        ue, f, cf = self.ue, self.f, self.cf
        calls = []
        for s in ('left', 'right'):
            v = SIDE[s]
            calls += [(cf, f['GetCardsInHandBySide'], {'side': v}),
                      (cf, f['GetCardsInSupportLineBySide'], {'side': v, 'unitsOnly': 1, 'includeCovertCards': 1}),
                      (cf, f['GetCardsInFrontlineBySide'], {'side': v, 'includeCovertCards': 1}),
                      (cf, f['GetKreditsBySide'], {'side': v}),
                      (cf, f['GetMaxKreditsBySide'], {'side': v}),
                      (cf, f['DoesSideControlTheFrontline'], {'side': v}),
                      (cf, f['GetLocationCardBySide'], {'side': v})]
        calls += [(cf, f['GetTurnNumber'], {}), (cf, f['GetPlayingSide'], {}), (cf, f['GetClientSide'], {}),
                  (cf, f['IsLocationFull'], {'Location': 7})]
        r = ue.call_many(calls)
        if any(x is None for x in r):
            raise RuntimeError('场面读取失败（对象失效，可能对局已结束）')
        st = {'side': {}}
        for k, s in enumerate(('left', 'right')):
            hand, sup, front, kr, mkr, ctrl, hq = r[k * 7:k * 7 + 7]
            st['side'][s] = {
                'hand': self._cards(hand['Cards']),
                'support': self._cards(sup['Cards']),
                'front': self._cards(front['Cards']),
                'kredits': kr['kredits'], 'max_kredits': mkr['maxkredits'],
                'controls_front': ctrl['doesHe'],
                'hq': self._cards([hq['card']])[0] if hq['card'] else None,
            }
        turn, play, client, ffull = r[14:18]
        st['turn'] = turn['TurnNumber']
        st['playing'] = {1: 'left', 2: 'right'}.get(play['OutPlayingSide'], '?')
        st['client'] = {1: 'left', 2: 'right'}.get(client['OutClientSide'], '?')
        st['front_full'] = ffull['isFull']
        return st


def show(st):
    print('回合 %s 行动方 %s 本机 %s 前线满=%s' % (st['turn'], st['playing'], st['client'], st['front_full']))
    for s, d in st['side'].items():
        hq = d['hq']
        print('[%s] 指挥点 %d/%d 控制前线=%s 指挥部=%s' % (s, d['kredits'], d['max_kredits'], d['controls_front'],
                                                    hq.df if hq else '?'))
        for k in ('hand', 'support', 'front'):
            print('   %-7s' % k, ', '.join('%s#%d %s %d/%d 费%s 行%s%s%s%s' % (
                c.name.replace('card_unit_', '').replace('card_event_', '!')[:22], c.id, c.type, c.atk or 0,
                c.df or 0, c.cost, c.op, ' 守' if c.guard else '', ' 可攻' if c.can_attack else '',
                ' 可移' if c.can_move else '') for c in d[k]))


if __name__ == '__main__':
    lv = Live()
    print('就绪', lv.refresh(), '队列忙', lv.busy())
    show(lv.snapshot())
