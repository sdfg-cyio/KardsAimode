# 中立衍生/发现牌（溃军 card_unit_routed_troops 是 1/1 白板步兵，按普通单位部署即可，不用注册）
import sim_rules as R
from effects import P, card, enemy_targets

card(P + 'blast',                       # 爆破：对一个敌方单位 1 点
     play=lambda sim, c, t, k: R.damage(sim, sim.find(t), 1, c.side) if sim.find(t) else None,
     options=lambda sim, c: [(i, 0) for i in enemy_targets(sim, c.side, ('support', 'front'),
                                                           smoke_ok=True, by_order=True)])
card(P + 'production',                  # 生产：本回合 +1 指挥点
     play=lambda sim, c, t, k: sim.side[c.side].__setitem__('kredits', sim.side[c.side]['kredits'] + 1))
card(P + 'plan',                        # 计划：抽 1
     play=lambda sim, c, t, k: R.draw(sim, c.side, 1))
