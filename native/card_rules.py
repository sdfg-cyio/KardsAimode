# 卡面文字里的“能不能”类限制（合法性层）：AI 发出的动作客户端不校验，这一层必须准
# 只按现役卡（非 reserved）的英文卡面归纳成通用规则，不针对单卡；新卡同样的写法自动生效
# 预测层（打得好不好）的卡牌效果在 cards_*.py，不在这里
import re
from functools import lru_cache

U = 'card_unit_'
IGNORE_NO_HQ = U + 'nara_regiment'           # 奈良团：无视友方单位的“不能攻击敌方指挥部”
NO_BIG_ATTACK = U + 'no_3_commando'          # 第 3 突击队：攻击力 4 以上的单位不能攻击（双方）
ONE_ORDER = U + '60th_cavalry_regiment'      # 第 60 骑兵团：每回合双方都只能下一个指令
FRONT_TWO = U + 'black_prince'               # 黑王子：前线只能容纳 2 个单位
NO_DEPLOY_NEXT = ('card_event_tirpitz', 'card_event_u_99')   # 打出后：对方下回合不能部署


S = r'(?:^|[.:]\s*)'    # 句首：只认“这个单位自己”的限制，不误伤“攻击力 4 以上的单位不能攻击”这类别人的光环


@lru_cache(maxsize=None)
def text(name):
    try:
        import card_db
    except ImportError:                       # card_db 在 proxy/：live_ai 单独使用（测试）时自己加路径
        import os, sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'proxy'))
        import card_db
    i = card_db.get(name) or {}
    return (i.get('text') or '').lower()


def order_immune(name):
    """不能被敌方指令指向（豹式、虎式 E、M4A1、第 141 山地猎兵等）"""
    return bool(re.search(S + r"(cannot|can't) be targeted by enemy orders", text(name)))


def no_hq_attack(name, deploy_turn=False):
    """不能攻击敌方指挥部；fw 200 一类只在部署当回合不能"""
    t = text(name)
    if re.search(r"deployment: (cannot|can't) attack the enemy hq this turn", t):
        return deploy_turn
    return bool(re.search(S + r"(cannot|can't) attack the enemy hq", t))


def cant_move(name):
    """不能移动（如第 190 近卫步兵团、第 38 独立营：“Cannot attack or move”）"""
    return bool(re.search(S + r"(cannot|can't) (attack or )?move", text(name)))


def cant_attack(name):
    """卡面写着不能攻击（不含“不能攻击敌方指挥部”）"""
    return bool(re.search(S + r"(cannot|can't) attack(?! the enemy hq)", text(name)))


def _on_board(st, name):
    return any(u.name == name for d in st['side'].values() for u in d['support'] + d['front'])


def _side_has(st, side, name):
    d = st['side'][side]
    return any(u.name == name for u in d['support'] + d['front'])


def can_attack_hq(st, me, u, deploy_turn=False):
    if _side_has(st, me, IGNORE_NO_HQ):
        return True
    return not no_hq_attack(u.name, deploy_turn)


def attack_blocked(st, u):
    """场上光环让 u 这回合不能攻击"""
    return _on_board(st, NO_BIG_ATTACK) and (u.atk or 0) >= 4


def front_max(st, default):
    return min(default, 2) if _on_board(st, FRONT_TWO) else default


def order_limit_hit(st, n_orders):
    """本回合已下 n_orders 个指令，还能不能再下"""
    return _on_board(st, ONE_ORDER) and n_orders >= 1
