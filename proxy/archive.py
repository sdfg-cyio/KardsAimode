# 单机保留地·第一阶段：把私服的回应原样录下来（私服随时可能关，关了就再也录不到）
# 代理每转发一次私服请求，就把“请求 + 回应”存成一个 JSON 文件。以后离线模式用这些文件冒充私服。
#
# 存放位置：环境变量 KARDS_ARCHIVE_DIR（start.sh 设为 /sdcard/Download/kardsai_archive），
# 不放在 ~/kardsai 里，因为重新安装会清空那个目录。
# 文件名 = 方法 + 路径（数字 id 换成 {id}），同一个接口只留最新一份；
# 开局数据这类“每次都不一样、离线要照着生成”的接口额外留几份样本。
import os, json, re, time, threading

DIR = os.environ.get('KARDS_ARCHIVE_DIR') or os.path.join(os.path.dirname(os.path.abspath(__file__)), 'archive')
SAMPLES = {'GET /matches/v2/': 5, 'POST /singleplayerlobby': 3, 'GET /matches/v2/reconnect': 3,
           'POST /players/{id}/decks': 3, 'PUT /players/{id}/decks/{id}': 3}
THROTTLE = 60            # 频繁轮询的接口 60 秒内只写一次
# 只有这些接口限频（2026-10-20 教训：原来所有接口都限频，登录前后两次 GET / 间隔 1 秒，
# 登录后那份（带 current_user）被限掉了没录到，离线时客户端拿到未登录的那份就卡住进不去）
NOISY = re.compile(r'^(PUT /players/\{id\}/heartbeat|GET /players/notifications/\{id\}|PUT /players/\{id\}|'
                   r'GET /store/v2/txn|GET /matches/v2/reconnect)$')
SKIP = re.compile(r'^/matches/v2/\d+/')   # PvP 对局里的动作/调度：量大、带对手数据，离线用不上
SECRET_KEYS = ('password',)               # 登录请求里的密码不存

_lock = threading.Lock()
_last = {}               # 接口 -> 上次写入时间
_seen = None             # 已录过的接口（第一次录到时打一行日志）
_cnt = {}                # 接口 -> 本次运行录了几份样本


def key_of(method, path, auth=False):
    p = path.split('?')[0]
    p = re.sub(r'/\d+(?=/|$)', '/{id}', p)
    # GET / 登录前后回应不同（登录后带 current_user 和 my_* 地址）：分开存
    return f'{method} {p}' + (' (auth)' if auth and p == '/' else '')


def _fname(key, n=None):
    s = re.sub(r'[^A-Za-z0-9_.-]+', '_', key.replace('{id}', 'ID')).strip('_')
    return s + (f'.{n}' if n is not None else '') + '.json'


def _text(b):
    if b is None:
        return None
    try:
        return json.loads(b)                 # JSON 存成结构，方便以后读
    except Exception:
        try:
            return {'_text': b.decode('utf-8')}
        except Exception:
            return {'_hex': b.hex()}


def _scrub(obj):
    if isinstance(obj, dict):
        return {k: ('***' if k.lower() in SECRET_KEYS else _scrub(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


def record(method, path, req_body, status, headers, body, log=None, auth=False):
    """记一次私服往返（auth = 请求带了登录凭证）。出任何错都吞掉：录档不能影响正常游戏"""
    global _seen
    try:
        if SKIP.match(path.split('?')[0]):
            return
        key = key_of(method, path, auth)
        now = time.time()
        with _lock:
            if _seen is None:
                os.makedirs(DIR, exist_ok=True)
                _seen = {f for f in os.listdir(DIR)}
            n_keep = SAMPLES.get(key)
            if NOISY.match(key) and now - _last.get(key, 0) < THROTTLE:
                return
            _last[key] = now
            rec = {'key': key, 'method': method, 'path': path, 'time': time.strftime('%Y-%m-%d %H:%M:%S'),
                   'request': _scrub(_text(req_body)), 'status': status,
                   'headers': {k: v for k, v in headers}, 'body': _text(body)}
            name = _fname(key)
            first = name not in _seen
            _write(name, rec)
            if n_keep:
                # 样本轮流覆盖 .0 ~ .n-1（代理重启后从 .0 重新轮）
                i = _cnt.get(key, 0) % n_keep
                _cnt[key] = i + 1
                _write(_fname(key, i), rec)
                _seen.add(_fname(key, i))
            _seen.add(name)
        if first and log:
            log(f'[archive] 新录到接口 {key}（{status}）')
    except Exception as e:
        if log:
            log('[archive] 录档出错（不影响游戏）', e)


def _write(name, rec):
    p = os.path.join(DIR, name)
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(rec, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)                        # 先写临时文件再改名：写到一半被杀不会留下坏文件


def summary():
    """已录到哪些接口（kards_proxy 启动时打印）"""
    try:
        fs = [f for f in os.listdir(DIR) if f.endswith('.json') and not re.search(r'\.\d+\.json$', f)]
    except OSError:
        return 0
    return len(fs)
