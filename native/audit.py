# 第三层：让漏掉的效果自己暴露出来（只写日志，不影响决策）
#   覆盖率：每局开始列出双方卡组里 AI 还不认识效果的牌
#   预测偏差：AI 每走一步，比较“模拟以为会发生什么”和“客户端真实场面”，对不上就记一条
# 偏差 = 有没模拟的效果，或者模拟是估算的（如协力疲惫按 2 点估）。日志同时写到 proxy/ai_audit.log
import os, re, time, random
import effects, card_rules, planner, sim_rules as R
from sim import Sim, card_db

# 手机上跑时 start.sh 设 KARDS_LOG_DIR=/sdcard/...，日志放到电脑能用 adb pull 取到的地方
LOG = os.path.join(os.environ.get('KARDS_LOG_DIR') or
                   os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'proxy'), 'ai_audit.log')
# 卡面里这些说法已经有通用规则处理（合法性层），剩下的文字才算“没模拟”
GENERIC = [r"(cannot|can't) be targeted by enemy orders\.?", r"(deployment: )?(cannot|can't) attack the enemy hq( this turn)?\.?",
           r"(cannot|can't) attack or move\.?", r"(cannot|can't) attack\.?",
           r"retreat this unit before damage is applied when it is attacked\.?"]
RULE_CARDS = {card_rules.NO_BIG_ATTACK, card_rules.ONE_ORDER, card_rules.FRONT_TWO, *card_rules.NO_DEPLOY_NEXT}


def _short(name):
    return str(name).split('_', 2)[-1][:20]


def _write(lines):
    try:
        with open(LOG, 'a', encoding='utf-8') as f:
            for s in lines:
                f.write(time.strftime('%m-%d %H:%M:%S ') + s + '\n')
    except OSError:
        pass


def modeled(name):
    """AI 是否认识这张牌的效果：注册了钩子 / 由通用规则处理 / 卡面没有特殊文字"""
    if name in effects.CARDS or name in RULE_CARDS:
        return True
    t = card_rules.text(name)
    for p in GENERIC:
        t = re.sub(p, '', t)
    return not t.strip(' .')


def coverage(decks, ai_side, match_id=''):
    """decks: {side: [卡名...]}；返回给控制台的摘要行，详细文字写进审计日志"""
    out, detail = [], []
    for side, names in decks.items():
        who = 'AI' if side == ai_side else '玩家'
        miss = {}
        for n in names:
            if n and card_db.get(n) and not modeled(n):
                miss[n] = miss.get(n, 0) + 1
        out.append(f'[覆盖率] {who}卡组 {len(names)} 张，{len(miss)} 种效果没模拟：'
                   + '、'.join(f'{_short(n)}x{k}' for n, k in sorted(miss.items())))
        detail += [f'  {who} {n}: {card_rules.text(n)[:160]}' for n in sorted(miss)]
    _write([f'== 对局 {match_id} 覆盖率'] + out + detail)
    return out


# ---------- 预测偏差 ----------
def simulate(st, me, tlog, act, plan):
    """在模拟器里执行 act，返回 (预测局面, 动作前已有的卡 id)"""
    sim = Sim(st, me, tlog)
    sim.rng = random.Random(0)
    planner.make_ctx(sim, plan)
    before = {c.id for d in sim.side.values() for k in ('hand', 'support', 'front') for c in d[k]}
    R.apply(sim, act)
    return sim, before


def predict(st, me, tlog, act, plan):
    """同 simulate；涉及随机效果的不比（返回 None）"""
    sim, before = simulate(st, me, tlog, act, plan)
    return None if sim.random_used else (sim, before)


def _index(side_map):
    out = {}
    for s, d in side_map.items():
        for k in ('hand', 'support', 'front'):
            for c in d[k]:
                out[c.id] = (s, 'hand' if k == 'hand' else k[:3], c.atk, c.df, bool(getattr(c, 'covert', False)),
                             c.name)
    return out


def diff(pred, before, real):
    """预测局面 vs 真实快照，返回差异描述列表（空 = 一致）"""
    P, Rl = _index(pred.side), _index(real['side'])
    out = []
    for s in ('left', 'right'):
        ph, rh = pred.side[s]['hq'], real['side'][s]['hq']
        if rh is not None and ph.df != rh.df:
            out.append(f'{s}总部 预测{ph.df} 实际{rh.df}')
        if s == pred.me and pred.side[s]['kredits'] != real['side'][s]['kredits']:
            out.append(f'{s}指挥点 预测{pred.side[s]["kredits"]} 实际{real["side"][s]["kredits"]}')
        np_, nr = len(pred.side[s]['hand']), len(real['side'][s]['hand'])
        if np_ != nr:
            out.append(f'{s}手牌 预测{np_}张 实际{nr}张')
    for cid, p in P.items():
        if cid < 0 or p[1] == 'hand':
            continue                         # 模拟里新刷出的单位单独按数量比
        r = Rl.get(cid)
        if r is None:
            out.append(f'{_short(p[5])}#{cid} 预测活着 实际没了')
        elif r[1] == 'hand':
            out.append(f'{_short(p[5])}#{cid} 预测在场上 实际回了手牌')
        elif (r[0], r[1]) != (p[0], p[1]):
            out.append(f'{_short(p[5])}#{cid} 预测在{p[0]}{p[1]} 实际在{r[0]}{r[1]}')
        elif not (p[4] or r[4]) and (p[2], p[3]) != (r[2], r[3]):
            out.append(f'{_short(p[5])}#{cid} 预测{p[2]}/{p[3]} 实际{r[2]}/{r[3]}')
    for cid, r in Rl.items():
        if r[1] != 'hand' and cid in before and cid not in P:
            out.append(f'{_short(r[5])}#{cid} 预测没了 实际还在')
    for s in ('left', 'right'):
        for line in ('sup', 'fro'):
            np_ = sum(1 for cid, p in P.items() if cid < 0 and (p[0], p[1]) == (s, line))
            nr = sum(1 for cid, r in Rl.items() if cid not in before and (r[0], r[1]) == (s, line))
            if np_ != nr:
                out.append(f'{s}{line} 新上场 预测{np_}个 实际{nr}个')
    return out


def record_diff(log, step, act_desc, problems):
    """写一条预测偏差（控制台 + 审计日志）"""
    s = f'[预测偏差] 第{step}步 {act_desc}：' + '；'.join(problems[:8])
    log(s)
    _write([s])
