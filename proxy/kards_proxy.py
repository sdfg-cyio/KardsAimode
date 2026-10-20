# KARDS 本地代理：游戏(127.0.0.1:5233 经 adb reverse) -> 本代理 -> 私服
# 第一阶段：透明转发 + 把响应中的私服地址改写成本机地址，保证后续请求都经过代理
# 后续阶段在 handle() 中接管人机对局（singleplayerlobby / matches）
import http.server, http.client, sys, os, datetime, gzip, zlib, json, re, traceback
from local_match import LocalMatch, enc
from kards_codec import decode
import ai_decks
import archive
import offline

MATCH_RE = re.compile(r'^/matches/v2/(\d+)(/.*)?$')
LOCAL = {}  # match_id -> LocalMatch
# 改写下发给客户端的服务器开关。skip_sending_subactions=0：让客户端把本地结算结果(sub_actions)随动作发回，
# AI 据此校正场面。注意 PvP 时这会让对方客户端收到带 sub_actions 的动作，所以 PvP 前可关掉此项
OPTION_OVERRIDES = {'skip_sending_subactions': 0}

UP_HOST, UP_PORT = 'ovo.wards.mom', 5233
# 2026-10-19 私服域名的 DNS 记录被删了（各家 DNS 都返回不存在），但服务器本身还在：
# 直接连 IP、请求头 Host 仍写域名就能用（服务器前面有 CDN，按 Host 分流，不带域名会返回人机验证页）。
# 所以只把“连哪个地址”换成 IP，Host 头照旧。IP 来自抓包；环境变量 KARDS_UP_IP 可改
UP_IP_FALLBACK = '43.199.188.3'


def _pick_up_addr():
    """连接用的地址：域名能解析就用域名（服务器换 IP 时跟着变），解析不了用备用 IP"""
    import os, socket
    env = os.environ.get('KARDS_UP_IP')
    if env:
        return env
    try:
        socket.getaddrinfo(UP_HOST, UP_PORT)
        return UP_HOST
    except OSError:
        return UP_IP_FALLBACK


UP_ADDR = _pick_up_addr()


def _pick_up_proxy():
    """直连私服不通而本机 7897 代理可用时，改走代理；环境变量 KARDS_UP_PROXY=host:port / 'none' 可强制指定"""
    import os, socket
    env = os.environ.get('KARDS_UP_PROXY')
    if env:
        if env.lower() == 'none':
            return None
        h, _, p = env.rpartition(':')
        return h, int(p)
    try:
        socket.create_connection((UP_ADDR, UP_PORT), timeout=5).close()
        return None
    except OSError:
        pass
    try:
        socket.create_connection(('127.0.0.1', 7897), timeout=2).close()
        return '127.0.0.1', 7897
    except OSError:
        return None


UP_PROXY = _pick_up_proxy()


def _pick_offline():
    """单机保留地：KARDS_OFFLINE=1 强制离线（完全不连私服）/ 0 强制联网 / auto（默认）私服连不上且有录档时离线"""
    import os, socket
    env = os.environ.get('KARDS_OFFLINE', 'auto').lower()
    if env in ('1', 'on', 'yes', 'offline'):
        return True
    if env in ('0', 'off', 'no', 'online') or not offline.available() or UP_PROXY:
        return False
    try:
        socket.create_connection((UP_ADDR, UP_PORT), timeout=5).close()
        return False
    except OSError:
        return True


OFFLINE = _pick_offline()
LISTEN_PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 15233
UP_URL = b'http://ovo.wards.mom:5233'
LOCAL_URL = b'http://127.0.0.1:5233'
HOP = {'connection', 'keep-alive', 'transfer-encoding', 'content-length', 'content-encoding', 'host'}

def strip_subactions(body):
    try:
        j = json.loads(body)
        text, key, idx = decode(j['a'])
        obj = json.loads(text)
        if 'sub_actions' not in obj:
            return body
        obj.pop('sub_actions')
        j['a'] = enc(obj, key)
        return json.dumps(j).encode()
    except Exception:
        return body  # 解不开就原样转发


def log(*a):
    print(datetime.datetime.now().strftime('%H:%M:%S'), *a, flush=True)

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, *a):
        pass

    def _reply(self, status, data, ctype='application/json; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _forward(self):
        n = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(n) if n else None
        # 客户端日志上报：私服没有这个接口(404)，改为本地记录，便于排查卡顿/不同步
        if self.command == 'POST' and self.path.split('?')[0].endswith('/logger'):
            try:
                text = (body or b'').decode('utf-8', 'replace')
                with open('client_logger.txt', 'a', encoding='utf-8') as f:
                    f.write(datetime.datetime.now().strftime('%H:%M:%S ') + text + '\n')
                err = json.loads(text).get('error', '')
                for lm in LOCAL.values():
                    lm.client_report(err)
            except Exception:
                pass
            return self._reply(200, b'{}')
        # 本地接管的人机局：不发往私服
        m = MATCH_RE.match(self.path.split('?')[0])
        if m and int(m.group(1)) in LOCAL:
            lm = LOCAL[int(m.group(1))]
            was = lm.match_status
            try:
                st, data = lm.handle(self.command, m.group(2) or '', body)
            except Exception:
                log('ERR local', self.command, self.path, traceback.format_exc())
                st, data = 500, b'{}'
            if was != 'finished' and lm.match_status == 'finished' and self.command == 'PUT' and body and not OFFLINE:
                # 客户端发的结束请求（投降/拆总部）也给私服一份；要带上客户端的登录头，否则私服回“用户不存在”
                _tell_upstream_end(self.path, body, {k: v for k, v in self.headers.items() if k.lower() not in HOP})
            if (m.group(2) or '') not in ('/actions', ''):  # 轮询太频繁，不记录
                log('LOCAL', self.command, self.path, st, len(data))
            return self._reply(st, data)
        # 发往私服的 PvP 动作：去掉 sub_actions，保证联机流量与未改开关时一致
        if m and self.command == 'POST' and m.group(2) == '/actions' and body and OPTION_OVERRIDES:
            body = strip_subactions(body)
        p0 = self.path.split('?')[0]
        if OFFLINE and self.command == 'GET' and p0 == '/matches/v2/reconnect':
            # 离线断线重连：本地还在进行的人机局给本地局面，否则“没有可重连的对局”
            run = [lm for lm in LOCAL.values() if lm.match_status != 'finished']
            data = json.dumps(run[-1].reconnect_payload(), ensure_ascii=False).encode() if run else b'null'
            if run:
                log(f'[local {run[-1].id}] 客户端断线重连，返回本地局面（离线）')
            return self._reply(200, data)
        conn = None
        try:
            if OFFLINE:
                # 单机保留地：不连私服，由 offline 模块按录档和本地状态回应
                status, rheaders, data = offline.handle(self.command, self.path, body, log)
                reason = ''
            else:
                hdrs = {k: v for k, v in self.headers.items() if k.lower() not in HOP}
                hdrs['Host'] = f'{UP_HOST}:{UP_PORT}'
                hdrs['Accept-Encoding'] = 'identity'  # 便于改写响应
                # 电脑直连私服不通时，经本机的 HTTP 代理（如 Clash 127.0.0.1:7897）转发；UP_PROXY 为空则直连
                if UP_PROXY:
                    ph, pp = UP_PROXY
                    conn = http.client.HTTPConnection(ph, pp, timeout=30)
                    target = f'http://{UP_ADDR}:{UP_PORT}{self.path}'
                else:
                    conn = http.client.HTTPConnection(UP_ADDR, UP_PORT, timeout=30)
                    target = self.path
                conn.request(self.command, target, body=body, headers=hdrs)
                r = conn.getresponse()
                status, reason = r.status, r.reason
                rheaders = [(k, v) for k, v in r.getheaders() if k.lower() not in HOP]
                data = r.read()
                enc = (r.getheader('Content-Encoding') or '').lower()
                if 'gzip' in enc:
                    data = gzip.decompress(data)
                elif 'deflate' in enc:
                    data = zlib.decompress(data)
                data = data.replace(UP_URL, LOCAL_URL)
                # 单机保留地：录下私服原样回应（地址已换成本机，还没做人机改写），离线模式照着回
                archive.record(self.command, self.path, body, status, rheaders, data, log)
            # 登录响应：记下玩家套牌；按 OPTION_OVERRIDES 改写服务器开关（只影响本机客户端）
            if self.command == 'POST' and self.path.split('?')[0] == '/session' and status == 200:
                try:
                    s = json.loads(data)
                    ai_decks.remember(s.get('player_id'), s['decks']['headers'])
                    if OPTION_OVERRIDES and isinstance(s.get('server_options'), str):
                        so = json.loads(s['server_options'])
                        for k, v in OPTION_OVERRIDES.items():
                            log(f'[options] {k}: {so.get(k)} -> {v}')
                            so[k] = v
                        s['server_options'] = json.dumps(so, ensure_ascii=False)
                        data = json.dumps(s, ensure_ascii=False).encode()
                except Exception:
                    log('ERR parse session', traceback.format_exc())
            # 记下进入人机时选的套牌，AI 尽量换一套
            if self.command == 'POST' and self.path.split('?')[0] == '/singleplayerlobby' and body:
                try:
                    ai_decks.last_lobby_deck = json.loads(body).get('deck_id')
                except Exception:
                    pass
            # 私服建好的人机局：登记为本地接管，并替换 AI 套牌
            if self.command == 'GET' and p0 in ('/matches/v2/', '/matches/v2/reconnect') and status == 200:
                try:
                    j = json.loads(data)
                    if p0.endswith('reconnect') and isinstance(j, dict) and 'match_and_starting_data' not in j:
                        data = _reconnect_flat(j, data)
                        j = None                   # 已处理，下面不再按开局格式解析
                    if j and j['match_and_starting_data']['starting_data'].get('is_ai_match'):
                        mid = j['match_and_starting_data']['match']['match_id']
                        if mid in LOCAL and p0.endswith('reconnect'):
                            # 断线重连：私服那份不含本地记录的 AI 动作，必须用本地局的数据，
                            # 否则客户端按私服的旧局面重放，立刻不同步（实测：指挥点不足、无效卡牌、被判投降）
                            data = json.dumps(LOCAL[mid].reconnect_payload(), ensure_ascii=False).encode()
                            log(f'[local {mid}] 客户端断线重连，返回本地局面')
                        elif mid in LOCAL and LOCAL[mid].match_status == 'finished':
                            # 私服还当这局在进行（实测：本地打完后开新局，私服连着几次返回刚结束的那局）：
                            # 不再把它当新局发给客户端，回“还没匹配到”，客户端会接着轮询
                            log(f'[local {mid}] 私服又返回已结束的本地局，当作还在等新局')
                            data = b'null'
                        else:
                            if mid not in LOCAL:
                                ai_decks.replace_ai_deck(j, log)
                                LOCAL[mid] = LocalMatch(j, log)
                            data = json.dumps(LOCAL[mid].raw, ensure_ascii=False).encode()
                except Exception:
                    log('ERR parse match', traceback.format_exc())
            self.send_response(status, reason or None)
            for k, v in rheaders:
                self.send_header(k, v)
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            log('OFFLINE' if OFFLINE else '', self.command, self.path, status, len(data))
        except Exception as e:
            log('ERR', self.command, self.path, e if not OFFLINE else traceback.format_exc())
            try:
                self.send_error(502)
            except OSError:
                pass                                 # 客户端已经断开
        finally:
            if conn is not None:
                conn.close()

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _forward

def _reconnect_flat(j, data):
    """重连响应（实测外层是 match / starting_data / actions / mulligan_left/right…，不是开局的 match_and_starting_data）。
    私服不知道本地接管局里发生了什么：本地局已结束、或代理重启后不认识的旧人机局，私服仍当它“进行中”，
    客户端会进到私服那份（原版 AI 的局面，没有我们的 AI 动作）-> 和原版人机抢控制权、被判投降（用户实测）。
    处理：人机局一律不让客户端重连私服那份——本地局还在进行就换成本地局面，否则回“没有可重连的对局”"""
    sd, m = j.get('starting_data') or {}, j.get('match') or {}
    if not sd.get('is_ai_match'):
        return data                                # PvP 重连：原样透传
    mid = m.get('match_id')
    lm = LOCAL.get(mid)
    if lm is None or lm.match_status == 'finished':
        log(f'[local] 重连：人机局 {mid} {"已在本地结束" if lm else "不是本次代理接管的"}，不让客户端进私服那份')
        return b'null'
    p = lm.reconnect_payload()
    md = p['match_and_starting_data']
    flat = dict(j)
    flat['match'], flat['starting_data'] = md['match'], md['starting_data']
    flat['actions'] = []                           # 客户端随后从 min_action_id=1 轮询本地记录的动作
    for s in ('left', 'right'):
        res = getattr(lm, '_mull_res', {}).get(s)
        flat[f'mulligan_{s}'] = res if res else flat.get(f'mulligan_{s}')
    log(f'[local {mid}] 客户端断线重连，返回本地局面')
    return json.dumps(flat, ensure_ascii=False).encode()


def _tell_upstream_end(path, body, hdrs=None):
    """本地局结束后把客户端的结束请求也发给私服（原样），让私服把那局关掉。
    不发的话私服一直当它在进行：下一局建局要等它超时，客户端重新登录后还会被拉回原版人机的那局"""
    import threading

    def go():
        try:
            if UP_PROXY:
                conn = http.client.HTTPConnection(*UP_PROXY, timeout=15)
                target = f'http://{UP_ADDR}:{UP_PORT}{path}'
            else:
                conn = http.client.HTTPConnection(UP_ADDR, UP_PORT, timeout=15)
                target = path
            h = dict(hdrs or {'Content-Type': 'application/json'})
            h['Host'] = f'{UP_HOST}:{UP_PORT}'
            conn.request('PUT', target, body=body, headers=h)
            r = conn.getresponse()
            log(f'[local] 结束请求已转给私服 {path}：{r.status} {r.read()[:60]!r}')
            conn.close()
        except Exception as e:
            log(f'[local] 结束请求转给私服失败 {path}：{e!r}')
    threading.Thread(target=go, daemon=True).start()


if __name__ == '__main__':
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', LISTEN_PORT), Handler)
    log('kards proxy listening', LISTEN_PORT, '->', UP_HOST, UP_PORT,
        '' if UP_ADDR == UP_HOST else f'（域名解析不了，直连 {UP_ADDR}）')
    log(f'[archive] 私服回应录档目录 {archive.DIR}，已录 {archive.summary()} 个接口')
    if OFFLINE:
        log('[offline] ===== 离线模式：不连私服，登录/收藏/卡组/训练局全部本机回应（PvP 不可用）=====')
        if not offline.available():
            log('[offline] 警告：录档不全（缺登录或开局样本），游戏可能进不去。联网时正常玩一轮补录')
    else:
        log('[offline] 联网模式（私服连不上时会自动离线；强制离线：kards offline）')
    srv.serve_forever()
