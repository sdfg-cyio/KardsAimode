# AI 卡组打法登记：每套卡组一个模块（deck_xxx.py），提供权重、手牌保留价值、单位持续价值、起手调度
# ACTIVE 为当前人机局 AI 使用的打法；没登记专门打法时用 GENERIC
import importlib


class Generic:
    """通用打法：不认识的牌只按攻防估值"""
    NAME = 'generic'
    W = {'my_hq': 1.0, 'en_hq': 1.0, 'threat': 1.0, 'front': 1.5, 'board': 1.0}

    @staticmethod
    def hold(sim, c, ctx):
        return 0.25 * (c.cost or 0)

    @staticmethod
    def persist(sim, u, ctx):
        return 0.0

    @staticmethod
    def keep(name, cost):
        return (cost or 0) <= 4


GENERIC = Generic()
PLANS = {'usa_ramp': 'deck_usa_ramp', 'soviet_control': 'deck_soviet_control', 'germany_ramp': 'deck_germany_ramp',
         'britain_meteor': 'deck_britain_meteor', 'japan_legion': 'deck_japan_legion',
         'britain_firewall': 'deck_britain_firewall', 'germany_panzer': 'deck_germany_panzer',
         'usa_assault': 'deck_usa_assault', 'japan_burst': 'deck_japan_burst'}
ACTIVE = GENERIC


def load(key):
    """按名字加载打法模块；失败返回 None"""
    mod = PLANS.get(key)
    if not mod:
        return None
    try:
        return importlib.import_module(mod)
    except Exception:
        return None


def activate(key):
    global ACTIVE
    ACTIVE = load(key) or GENERIC
    return ACTIVE
