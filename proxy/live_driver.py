# 新 AI 回合驱动：每一步都从客户端读真实场面 -> live_ai 决策 -> 发一个动作 -> 等客户端播完 -> 再读
# 读不到场面（探针没连上/出错）时什么都不做，直接结束回合，保证不发非法动作
import os, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'native'))
import card_db  # noqa: E402

try:
    from live import Live  # noqa: E402
    import live_ai  # noqa: E402
    import audit  # noqa: E402
    AVAILABLE = True
except Exception as e:  # 没有探针模块（如 Termux 环境）时退回旧 AI
    AVAILABLE = False
    _IMPORT_ERR = e

MAX_STEPS = 30          # 每回合最多动作数（防止死循环）
HAND_TARGET = {'card_unit_gordon_highlanders'}   # 部署效果选自己手牌的单位（目标用 XActionHandTargetSelected 发）
WAIT_TIMEOUT = 20.0     # 等客户端播完一个动作的最长时间


class LiveDriver:
    def __init__(self, log, factory=None):
        self.log = log
        self.live = None
        self.factory = factory or Live   # 测试时可换成假的场面源
        self.memo = {}                   # 跨回合的对局记忆（军司令部标记、上回合是否部署英国步兵）
        self.seen_ids = set()            # 快照里见过的卡编号（估牌库剩余张数）

    def coverage(self, decks, ai_side, match_id=''):
        """开局：双方卡组里 AI 还不认识效果的牌（只写日志）"""
        try:
            for s in audit.coverage(decks, ai_side, match_id):
                self.log(s)
        except Exception as e:
            self.log(f'[覆盖率] 统计失败 {e!r}')

    def _check_prediction(self, pending, st, step):
        """上一步动作的模拟结果 vs 现在的真实场面"""
        if pending is None:
            return
        (pred, before), desc = pending
        try:
            problems = audit.diff(pred, before, st)
        except Exception as e:
            problems = [f'比较失败 {e!r}']
        if problems:
            audit.record_diff(self.log, step, desc, problems)

    def _connect(self):
        # 每个 AI 回合重新建连接：上一次连接可能已超时/断开（连接异常后状态不可信）
        try:
            if self.live is not None:
                self.live.ue.p.s.close()
        except Exception:
            pass
        self.live = self.factory()
        if not self.live.refresh():
            raise RuntimeError('没找到对局内的 BP_CardFunctions 实例')

    def wait_idle(self, seen_fn, target_id):
        """等客户端拉取到 target_id 号动作，且动作队列连续两次空闲"""
        t0 = time.time()
        while time.time() - t0 < WAIT_TIMEOUT:
            if seen_fn() > target_id:
                break
            time.sleep(0.2)
        idle = 0
        while time.time() - t0 < WAIT_TIMEOUT:
            try:
                idle = idle + 1 if not self.live.busy() else 0
            except Exception:
                return
            if idle >= 2:
                return
            time.sleep(0.25)

    @staticmethod
    def build(act, ai_side, x):
        """把决策转成 XAction（字段格式与抓包一致）"""
        loc = 'Board_HQRight' if ai_side == 'right' else 'Board_HQLeft'
        kind = act[0]
        if kind in ('deploy', 'play'):
            # ('deploy'|'play', 卡, 格子号, 目标id, 抉择序号)；指令的格式与部署相同（抓包：location 为己方支援线）
            c, num = act[1], act[2]
            tid = int(act[3]) if len(act) > 3 and act[3] else 0
            k = int(act[4]) if len(act) > 4 and act[4] else 0
            return 'XActionPlayCardFromHand', {
                '0': str(c.id), '1': str(num), '2': str(tid), '3': '0', '4': card_db.code(c.name), **x,
                'cardID': c.id, 'location': loc, 'locationNumber': num, 'targetCardID': tid,
                'card_name': c.name, 'chooseOneIndex': k}
        if kind == 'move':
            u, num = act[1], act[2]
            return 'XActionMoveCardToLine', {
                '0': str(u.id), '1': str(num), '2': card_db.code(u.name), **x,
                'cardID': u.id, 'location': 'Board_Frontline', 'card_name': u.name, 'locationNumber': num}
        a, t = act[1], act[2]
        return 'XActionAttackCard', {
            '0': str(a.id), '1': str(t.id), '2': card_db.code(a.name), '3': card_db.code(t.name), **x,
            'attackerCardID': a.id, 'defenderCardID': t.id,
            'attacker_card_name': a.name, 'defender_card_name': t.name}

    def play_turn(self, ai_side, append, seen_fn, hq_key, ended_fn=lambda: False, no_deploy=False, turn=0):
        """执行 AI 一整个回合（开始/结束回合由调用方发）
        append(action_type, action_data) -> 记录；seen_fn() -> 客户端已拉取到的最小动作 id；
        ended_fn() -> 对局是否已结束（实测：打掉指挥部后 AI 还在继续部署）；
        no_deploy -> 本回合不能部署（玩家上回合打了提尔皮茨/U-99）"""
        self.turn = turn                 # 对局里的回合数（服务器动作记录的 turn_number；生成牌编号要用）
        self.gen_seen = set()            # 本回合已用掉的客户端生成牌编号
        try:
            self._connect()
        except Exception as e:
            self.log(f'[live] 探针不可用，本回合直接结束：{e!r}')
            return 'unavailable'
        steps = 0
        tlog = None
        pending = None          # 上一步动作的模拟预测，等下一次读场面时比较
        while steps < MAX_STEPS:
            if ended_fn():
                return 'match_ended'
            try:
                st = self.live.snapshot()
            except Exception as e:
                self.log(f'[live] 读场面失败，结束回合：{e!r}')
                return 'error'
            if st['playing'] != ai_side:
                self.log(f'[live] 当前行动方是 {st["playing"]}，不是 AI，停止')
                return 'not_ai_turn'
            if tlog is None:
                self._check_enemy_draw(st, ai_side)
                tlog = live_ai.TurnLog(st, ai_side)
                tlog.no_deploy = no_deploy
                # 跨回合记忆（每局一个 LiveDriver）：上回合是否部署过英国步兵（前进观察员）
                self.memo['brit_last'], self.memo['brit_now'] = self.memo.get('brit_now', False), False
                tlog.memo = self.memo
                # 上回合预报选的天气牌：这回合抽完牌后应该在手里（核对推算的编号对不对）
                for name in self.memo.pop('forecast_pending', []):
                    got = [c.name for c in st['side'][ai_side]['hand'] if c.name.rstrip('23') == name.rstrip('23')]
                    self.log(f'[live] 上回合预报选了 {name.split("_", 2)[-1]}：' +
                             (f'手牌里是 {got[0].split("_", 2)[-1]}' if got else '手牌里没有（第二次选择可能没生效）'))
                # 情报：上回合看过的对方牌数并入累计（“若是明牌/若知道对方手牌”按它估）
                self.memo['intel'] = self.memo.get('intel', 0) + self.memo.pop('intel_turn', 0)
                # 长久围困上回合抽的牌：本回合结束时被弃掉，本回合留着没价值（planner 不算保留价值）
                self.memo['expiring'] = set(self.memo.pop('siege_new', ()))
                if self.memo['expiring']:
                    self.log(f'[live] 长久围困的牌本回合结束弃掉：{sorted(self.memo["expiring"])}')
                # 埋下的反制卡没触发前一直留在快照手牌里（实测拦截被连着两回合重复打出、重复扣费）：
                # 跨回合记住，从手牌里消失（触发了）就忘掉
                ids = {c.id for c in st['side'][ai_side]['hand']}
                self.memo['planted'] = {i: n for i, n in self.memo.get('planted', {}).items() if i in ids}
                tlog.gone |= set(self.memo['planted'])
                if no_deploy:
                    self.log('[live] 对方上回合打了提尔皮茨/U-99：本回合不部署')
            # 见过的卡编号（手牌/场上）：估牌库剩余张数用（local_match._deck_left）
            self.seen_ids |= {c.id for d in st['side'].values() for k in ('hand', 'support', 'front') for c in d[k]}
            # 本回合已打出、但快照里还留在手牌的卡（反制卡埋下后仍在手牌列表里）：从手牌去掉，免得重复打
            st['side'][ai_side]['hand'] = [c for c in st['side'][ai_side]['hand'] if c.id not in tlog.gone]
            self._check_prediction(pending, st, steps)
            pending = None
            act = live_ai.decide(st, ai_side, tlog)
            if act is None:
                # 记下回合结束时对方手牌数：下回合开始时对照“他回合开始有没有抽到牌”（_check_enemy_draw）
                self.memo['en_hand_end'] = len(st['side'][live_ai.other(ai_side)]['hand'])
                self.memo['my_hand_end'] = len(st['side'][ai_side]['hand'])
                # 诊断：结束回合时记下自己每个单位的状态和可选动作分数，便于查“为什么不打”
                my = st['side'][ai_side]
                us = ' '.join(f'{u.name[10:24]}#{u.id}[{u.loc[:3]} 攻{int(bool(u.can_attack))}'
                              f'移{int(bool(u.can_move))} 行{u.op}]' for u in my['support'] + my['front'])
                cand = sorted(((live_ai.score(st, ai_side, a), a) for a in live_ai.gen_actions(st, ai_side, tlog)),
                              key=lambda x: -x[0])[:6]
                self.log(f'[live] 结束回合 指挥点{my["kredits"]} 单位: {us}')
                # 诊断：手牌（名字/费用），用来区分“没得打”和“选择不打”
                self.log(f'[live]   手牌{len(my["hand"])}张: ' + ' '.join(
                    f'{c.name.split("_", 2)[-1][:18]}({c.cost})@{c.slot}' for c in my['hand']))
                # 诊断：敌方支援线格子号（含指挥部），用来核对守护相邻判断用的格子号是否可靠
                en = st['side'][live_ai.other(ai_side)]
                hq = en['hq']
                self.log('[live]   敌支援线格子: ' + ' '.join(
                    f'{c.name[10:22]}@{c.slot}{"守" if c.guard else ""}' for c in en['support'])
                         + (f' 指挥部@{hq.slot}' if hq else ''))
                self.log('[live]   候选: ' + '; '.join(f'{a[0]} #{a[1].id}->{getattr(a[2], "id", "HQ") if len(a) > 2 else ""} '
                                                       f'{s:.1f}' for s, a in cand))
                return 'done'
            my, en = st['side'][ai_side], st['side'][live_ai.other(ai_side)]
            info = live_ai.LAST
            if info.get('error'):
                self.log(f'[live] 规划退回贪心：{info["error"]}')
            n_fc = len(tlog.forecasts)
            hand_before = {c.id for c in st['side'][ai_side]['hand']} | tlog.gone
            try:
                ends_turn = False
                # 记账前先在模拟器里走一遍这一步，下一次读场面时和真实结果比较
                import decks
                sim, before = audit.simulate(st, ai_side, tlog, act, decks.ACTIVE)
                pending = None if sim.random_used else ((sim, before), f'{act[0]} {act[1]!r}')
                tlog.carry(sim)          # 临时攻击加成、每回合一次的效果要跨步骤记住
                ends_turn = sim.turn_over  # 击退进攻不在最右边打出：这一步之后回合就结束了
                self.memo['intel_turn'] = tlog.intel_seen
            except Exception as e:
                self.log(f'[预测偏差] 预测失败 {e!r}')
            picks = tlog.forecasts[n_fc:]   # 这一步触发的预报（E14Y/H8K 部署）：动作发出后要补发两次三选一
            live_ai.record(tlog, act)
            tgt, k = (act[2], act[3]) if len(act) > 3 else (0, 0)
            if act[0] == 'deploy':
                act = ('deploy', act[1], tlog.sup_count(my) - 1, tgt, k)
            elif act[0] == 'play':
                act = ('play', act[1], len(my['support']), tgt, k)
            elif act[0] == 'move':
                act = ('move', act[1], tlog.front_count(my) - 1)
            elif act[0] == 'attack' and act[2] is None:
                act = ('attack', act[1], en['hq'])
            kr_before = my['kredits']        # 发动作前的指挥点（判断是否生效用）
            x = {hq_key: str(my['hq'].df if my['hq'] else 20)}
            hand_tgt = act[0] == 'deploy' and act[1].name in HAND_TARGET and act[3]
            if hand_tgt:
                act = act[:3] + (0,) + act[4:]   # 选手牌的部署效果：目标另发一条（抓包同玩家操作）
            at, ad = self.build(act, ai_side, x)
            rec = append(at, ad)
            if hand_tgt:
                rec = append('XActionHandTargetSelected', {'0': str(act[1].id), '1': str(hand_tgt),
                                                           'cardSelectingTarget': act[1].id, 'targetCard': hand_tgt})
                self.log(f'[live]   手牌目标 #{hand_tgt}')
            if act[0] == 'deploy' and act[1].type == 'infantry' and \
                    (card_db.get(act[1].name) or {}).get('faction') == 'Britain':
                self.memo['brit_now'] = True
            for w, k in picks:
                rec = self._forecast(append, act[1], w, k, ai_side, seen_fn, rec, hand_before) or rec
            extra = f' 目标{act[3]} 抉择{act[4]}' if act[0] in ('deploy', 'play') else ''
            val = info.get('value')
            how = f' [{info.get("via")} {val[0]:.1f}/{val[1]:.1f}]' if val and info.get('via') == 'planner' else ''
            self.log(f'[live] 第{steps + 1}步 {act[0]} {act[1]!r} -> {act[2]!r}{extra} '
                     f'(指挥点 {my["kredits"]}/{my["max_kredits"]}){how}')
            steps += 1
            if act[0] in ('deploy', 'play'):
                tlog.gone.add(act[1].id)
                if (card_db.get(act[1].name) or {}).get('type') == 'countermeasure':
                    self.memo.setdefault('planted', {})[act[1].id] = act[1].name
            self.wait_idle(seen_fn, rec['action_id'])
            if not self.wait_applied(act, ai_side, kr_before):
                # 客户端没反映出这一步：场面不可信，宁可结束回合也不继续出手
                self.log(f'[live] 第{steps}步未在客户端生效（{act[0]} #{act[1].id}），结束回合')
                return 'not_applied'
            if ends_turn:
                self.log(f'[live] {act[1]!r} 不在手牌最右边打出，按卡面结束回合')
                return 'effect_end'
            if act[0] == 'play':
                # 指令可能消灭/撤退/刷出单位：按最新场面重新计数，免得占位数不准
                try:
                    snap = self.live.snapshot()
                    tlog.rebase(snap, ai_side)
                    if act[1].name == 'card_event_prolonged_siege':
                        # 长久围困：记下新抽到的牌，下回合结束时被弃掉
                        new = {c.id for c in snap['side'][ai_side]['hand']} - hand_before
                        self.memo.setdefault('siege_new', set()).update(new)
                        self.log(f'[live]   长久围困抽到 {len(new)} 张：{sorted(new)}')
                except Exception:
                    pass
        return 'max_steps'

    def _check_enemy_draw(self, st, ai_side):
        """对方回合开始有没有抽到牌：上回合结束时他 n 张，他回合里打出 p 张（不含埋反制），
        现在应该是 n - p + 1。少了那 1 张 = 牌库已经空了、他回合开始吃了一次疲惫伤害；n - p 已经 9 张 = 那张爆了。
        （662056：对面早就在吃疲惫伤害，牌库估算还以为有牌，假战/妥协能斩杀却没打）"""
        m = self.memo
        if not m.get('deck_known'):
            return                           # 没有开局牌库信息（测试用的假场面）：不推断
        # AI 自己：上回合结束时 k 张，现在还是 k 张 = 自己牌库空了（对方回合里改动我方手牌的效果少，忽略）
        k = m.pop('my_hand_end', None)
        if k is not None and k < 9 and len(st['side'][ai_side]['hand']) == k:
            m.setdefault('deck_empty', set()).add(ai_side)
            m.setdefault('fatigue', {})[ai_side] = m['fatigue'].get(ai_side, 0) + 1
            self.log(f'[live] AI 回合开始没抽到牌：自己牌库已空，第 {m["fatigue"][ai_side]} 次疲惫伤害')
        for s in m.get('deck_empty', ()):
            m.setdefault('deck_n', {})[s] = 0    # 确认空过的牌库一直是 0（除非之后又塞牌，塞的另算）
        n, p = m.pop('en_hand_end', None), m.pop('en_played', 0)
        if n is None:
            return
        e = live_ai.other(ai_side)
        now = len(st['side'][e]['hand'])
        base = n - p
        deck_n, fat = m.setdefault('deck_n', {}), m.setdefault('fatigue', {})
        if base >= 9:
            b = m.setdefault('burned', {})
            b[e] = b.get(e, 0) + 1
            deck_n[e] = max(0, deck_n.get(e, 1) - 1)
        elif now == base:
            deck_n[e] = 0
            m.setdefault('deck_empty', set()).add(e)
            fat[e] = fat.get(e, 0) + 1
            self.log(f'[live] 对方回合开始没抽到牌（{n}-{p}={base} 张，现在 {now} 张）：牌库已空，第 {fat[e]} 次疲惫伤害')

    def _forecast(self, append, src, w, k, ai_side, seen_fn, rec, hand_before):
        """预报：客户端弹两次三选一，由 AI 一方补发 XActionCardToDrawSelected（格式照玩家抓包）：
        1) 触发者 = 打出的卡，选第一级天气牌（晴/雨/风暴，cardToDraw = 0/1/2）
        2) 触发者 = 刚生成的第一级天气牌（快照里找新 id），选 2/4/6 费（cardToDraw = 0/1/2）"""
        import effects, random
        lv1 = effects.WEATHER[w][0]
        # 每档有 3 种变体（基础版 / *2 / *3，效果各不同）：第二次三选一给的是随机一种，AI 也随机取，不挑
        tier = effects.WEATHER[w][1 + k] + random.choice(('', '2', '3'))
        r1 = append('XActionCardToDrawSelected', {'0': str(src.id), '1': str(w), '2': card_db.code(lv1),
                                                  'cardTriggeringDraw': src.id, 'cardToDraw': w,
                                                  'cardNameToSpawn': lv1})
        self.wait_idle(seen_fn, r1['action_id'])
        # 第一级天气牌不进手牌（实测快照里找不到），选中的天气牌要到下回合抽完牌后才进手牌（用户确认），
        # 所以当场没法核对，只能按客户端规则推算编号发一次：
        # 客户端生成的牌编号 = 回合数 * 1000 + 本回合第几张（抓包：13001、17001、31003…）
        base = self.turn * 1000
        seen = [i for i in self._ids_now(ai_side) | self.gen_seen if base < i < base + 1000]
        guess = max(seen + [base]) + 1
        r = append('XActionCardToDrawSelected', {'0': str(guess), '1': str(k), '2': card_db.code(tier), '3': 1,
                                                 'cardTriggeringDraw': guess, 'cardToDraw': k,
                                                 'cardNameToSpawn': tier})
        self.gen_seen |= {guess, guess + 1}       # 第一级牌 + 它生成的天气牌各占一个编号
        self.memo.setdefault('forecast_pending', []).append(tier)
        self.log(f'[live]   预报：{lv1.split("_", 2)[-1]} -> {tier.split("_", 2)[-1]}（第一级按 #{guess} 选，下回合进手牌）')
        return r

    def _ids_now(self, ai_side):
        """快照里双方手牌/战线上所有卡的编号"""
        try:
            st = self.live.snapshot()
        except Exception:
            return set()
        return {c.id for d in st['side'].values() for k in ('hand', 'support', 'front') for c in d[k]}


    def wait_applied(self, act, ai_side, kr_before=None, timeout=8.0):
        """等到快照里能看到这一步的效果：部署/出牌 -> 卡离开手牌或指挥点扣了费；推进 -> 单位在前线；
        攻击 -> 只看动作队列空闲。
        实测：AI 打出反制卡（来自深处）后卡仍留在手牌列表里，但已生效、指挥点已扣——只看手牌会误判没生效"""
        t0 = time.time()
        cid = act[1].id
        while time.time() - t0 < timeout:
            try:
                st = self.live.snapshot()
            except Exception:
                return False
            my = st['side'][ai_side]
            hand = {c.id for c in my['hand']}
            front = {c.id: c for c in my['front']}
            alive = {c.id: c for c in my['support'] + my['front']}
            if act[0] in ('deploy', 'play') and cid not in hand:
                return True
            cost = act[1].cost or 0
            if act[0] == 'play' and kr_before is not None and cost > 0 and my['kredits'] <= kr_before - cost:
                return True
            if act[0] == 'move' and cid in front:
                return True
            if act[0] == 'attack':
                # 客户端的攻击标记对 AI 单位不可靠（不重置），攻击只依赖动作队列空闲判断
                return True
            time.sleep(0.3)
        return False
