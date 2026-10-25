# 卡牌数值库：客户端内部卡名(card_unit_xxx) -> 费用/攻防/类型/关键词
# 数据来源：社区站 data.json（importId 即客户端卡组码），用 deckCodeIDsTable2 映射到内部卡名
import json, os

from paths import DATA as W
UNIT_TYPES = {'infantry', 'tank', 'artillery', 'fighter', 'bomber'}

_codes = json.load(open(os.path.join(W, 'deck_codes_all.json'), encoding='utf-8'))
_data = json.load(open(os.path.join(W, 'kards_cards_data.json'), encoding='utf-8'))['cards']

DB = {}  # 内部卡名 -> dict
for c in _data:
    j = c.get('json') or {}
    names = _codes.get(c.get('importId'), [])
    if not names:
        continue
    info = {
        'type': j.get('type'),
        'kredits': j.get('kredits') or 0,
        'attack': j.get('attack') or 0,
        'defense': j.get('defense') or 0,
        'op': j.get('operationCost') or 0,
        'attrs': set(j.get('attributes') or []),
        'faction': j.get('faction'),
        'text': (j.get('text') or {}).get('en-EN', ''),
        'reserved': c.get('reserved', False),
        'rarity': j.get('rarity') or 'Standard',
    }
    for n in names:
        # 同码多卡：*_bal 是平衡版，同样数值；都登记
        DB.setdefault(n, info)


# 官方改版但社区站 data.json 还没跟上的数值，在这里覆盖（data.json 更新后可删对应条目）
PATCH = {
    'card_unit_238th_regiment': {'defense': 2},   # 2026-10 改版：2/3 -> 2/2
    'card_unit_2nd_west_africa': {'kredits': 2},  # 用户确认 2026-10-24：现为 2 费（社区站仍是 1 费）
}
for _n, _p in PATCH.items():
    if _n in DB:
        DB[_n] = dict(DB[_n], **_p)


# 内部卡名 -> 卡组码（动作里 "4"/"2"/"3" 字段要用）
NAME2CODE = {}
for _c, _ns in _codes.items():
    for _n in _ns:
        NAME2CODE.setdefault(_n, _c)


def code(name):
    return NAME2CODE.get(name, '')


def get(name):
    return DB.get(name)


# 每张卡在一副卡组里的上限（KARDS 规则：标准/限定 4、特殊 2、精英 1）
MAX_COPIES = {'Standard': 4, 'Limited': 4, 'Special': 2, 'Elite': 1}


def max_copies(name):
    i = DB.get(name)
    return MAX_COPIES.get(i['rarity'], 1) if i else 1


def is_unit(name):
    i = DB.get(name)
    return bool(i and i['type'] in UNIT_TYPES)


if __name__ == '__main__':
    print('卡牌数', len(DB))
    for n in ['card_unit_2nd_west_africa', 'card_event_pams', 'card_unit_meteor']:
        print(n, DB.get(n))
