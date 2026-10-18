# 数据目录：手机部署包里是 ./data，电脑开发环境是 ../work
import os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
if not os.path.isdir(DATA):
    DATA = os.path.join(HERE, '..', 'work')
if DATA not in sys.path:
    sys.path.insert(0, DATA)  # kards_codec.py 在这里
