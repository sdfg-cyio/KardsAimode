# 为 AI 生成套牌：只选“状态模型能准确跟踪”的单位卡
# 排除会改动牌库/手牌/费用/造成额外伤害的特效卡，保证 AI 对自己局面的推演不跑偏
import random, re
import card_db

SAFE_ATTRS = {'blitz', 'guard', 'smokescreen', 'fury', 'ambush', 'mobilize', 'heavyArmor', 'alpine', 'shock'}
BAD_TEXT = re.compile(r'(?i)(deck|draw|hand|cost|kredit|damage|destroy|discard|spawn|develop|return|copy|'
                      r'gain|lose|each|all|random|enemy|friendly|when|whenever|deploy|turn|frontline)')
FACTIONS = ['Germany', 'Britain', 'Soviet', 'USA', 'Japan']


def safe_units(faction):
    out = []
    for name, i in card_db.DB.items():
        if name.endswith('_bal') or not name.startswith('card_unit_') or i['reserved']:
            continue
        if i['faction'] != faction or i['type'] not in card_db.UNIT_TYPES:
            continue
        if not i['attrs'] <= SAFE_ATTRS or (i['text'] and BAD_TEXT.search(i['text'])):
            continue
        if i['defense'] <= 0:
            continue
        out.append(name)
    return out


def build(faction=None, size=39):
    """返回 (国家, 卡名列表)；按费用曲线挑，每张最多 3 份"""
    if faction is None:
        # 只在能凑满且符合数量上限的国家里随机（美国可选单位太少，凑不满 39 张）
        ok = [f for f in FACTIONS if sum(card_db.max_copies(n) for n in safe_units(f)) >= size]
        faction = random.choice(ok)
    pool = safe_units(faction)
    by_cost = {}
    for n in pool:
        by_cost.setdefault(min(card_db.get(n)['kredits'], 7), []).append(n)
    curve = {1: 9, 2: 9, 3: 8, 4: 6, 5: 4, 6: 2, 7: 1}  # 期望张数
    cards = []
    for cost, want in curve.items():
        cands = by_cost.get(cost, [])
        random.shuffle(cands)
        for n in cands:
            if want <= 0:
                break
            k = min(3, want, card_db.max_copies(n))
            cards += [n] * k
            want -= k
    # 不足则用低费卡补满，同样遵守每张卡的数量上限（精英 1、特殊 2、其他 4）
    low = sorted(pool, key=lambda n: card_db.get(n)['kredits'])
    for n in low:
        while len(cards) < size and cards.count(n) < card_db.max_copies(n):
            cards.append(n)
        if len(cards) >= size:
            break
    return faction, cards[:size]


def valid(cards):
    """检查卡组是否符合数量上限"""
    return all(cards.count(n) <= card_db.max_copies(n) for n in set(cards))


if __name__ == '__main__':
    for f in FACTIONS:
        fac, cs = build(f)
        print(f, len(safe_units(f)), '张可选 ->', len(cs),
              sorted({(card_db.get(n)['kredits'], n[10:]) for n in cs})[:8])
