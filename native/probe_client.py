# 探针客户端：经 adb forward tcp:23456 连接手机里的 libkardsai.so
import socket, struct


class Probe:
    def __init__(self, host='127.0.0.1', port=23456):
        # 超时不能太长：探针卡住时 AI 回合要能及时放弃（索引全部对象约 1~2 秒，30 秒足够）
        self.s = socket.create_connection((host, port), timeout=30)
        self.s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def _recv(self, n):
        buf = b''
        while len(buf) < n:
            c = self.s.recv(n - len(buf))
            if not c:
                raise ConnectionError('探针断开')
            buf += c
        return buf

    def _reply(self):
        n = struct.unpack('<I', self._recv(4))[0]
        return self._recv(n) if n else b''

    def base(self):
        self.s.sendall(b'B')
        return struct.unpack('<Q', self._reply())[0]

    def read(self, addr, n):
        self.s.sendall(b'R' + struct.pack('<QI', addr, n))
        return self._reply()

    def maps(self):
        self.s.sendall(b'M')
        return self._reply().decode('utf-8', 'replace')

    def scan(self, start, end, pat):
        self.s.sendall(b'S' + struct.pack('<QQI', start, end, len(pat)) + pat)
        d = self._reply()
        return list(struct.unpack('<%dQ' % (len(d) // 8), d))

    def write(self, addr, data):
        self.s.sendall(b'W' + struct.pack('<QI', addr, len(data)) + data)
        return struct.unpack('<I', self._reply())[0]

    # ---------- 游戏线程调用 ----------
    def hook_all(self, pe_obj, pe_actor, objs, num):
        self.s.sendall(b'X' + struct.pack('<QQQI', pe_obj, pe_actor, objs, num))
        return struct.unpack('<II', self._reply())

    def set_game_tid(self, tid):
        self.s.sendall(b'T' + struct.pack('<I', tid))
        return self._reply()

    def status(self):
        """(游戏线程 tid, 钩子命中数, 是否有卡死调用)"""
        self.s.sendall(b'Q')
        return struct.unpack('<iQI', self._reply())

    def call_batch(self, calls):
        """calls=[(obj, func, parms_bytes)]，同一帧内在游戏线程依次执行
        返回 (批状态, [(单个状态, 回写后的参数块)])；批状态 0 成功，2 钩子未就绪，3 卡死，4 已有卡死，6 参数错"""
        ents, blob = b'', bytearray()
        for obj, func, parms in calls:
            off = len(blob)
            blob += parms
            blob += b'\0' * (-len(blob) % 16)  # 对齐
            ents += struct.pack('<QQII', obj, func, off, len(parms))
        self.s.sendall(b'C' + struct.pack('<II', len(calls), len(blob)) + ents + bytes(blob))
        d = self._reply()
        bst = struct.unpack('<I', d[:4])[0]
        if bst != 0:
            return bst, []
        n = len(calls)
        st, data = d[4:4 + n], d[4 + n:]
        out, off = [], 0
        for i, (obj, func, parms) in enumerate(calls):
            out.append((st[i], data[off:off + len(parms)]))
            off += len(parms) + (-(off + len(parms)) % 16)
        return bst, out

    def call(self, obj, func, parms):
        bst, res = self.call_batch([(obj, func, parms)])
        if bst != 0:
            return bst, b''
        return res[0]

    def alloc(self, n):
        self.s.sendall(b'A' + struct.pack('<I', n))
        return struct.unpack('<Q', self._reply())[0]

    def free(self, ptr):
        self.s.sendall(b'F' + struct.pack('<Q', ptr))
        self._reply()

    def threads(self):
        self.s.sendall(b'D')
        out = []
        for l in self._reply().decode('utf-8', 'replace').splitlines():
            t, _, n = l.partition(' ')
            out.append((int(t), n))
        return out

    def obj_heads(self, objs, start, cnt):
        """批量对象头：[(obj, class, nameIdx, nameNum, outer)]"""
        self.s.sendall(b'O' + struct.pack('<QII', objs, start, cnt))
        d = self._reply()
        res = []
        for k in range(len(d) // 32):
            o, c, nm, outer = struct.unpack_from('<QQQQ', d, k * 32)
            res.append((o, c, nm & 0xffffffff, nm >> 32, outer))
        return res

    # 便捷读取
    def u64(self, a):
        d = self.read(a, 8)
        return struct.unpack('<Q', d)[0] if len(d) == 8 else None

    def u32(self, a):
        d = self.read(a, 4)
        return struct.unpack('<I', d)[0] if len(d) == 4 else None

    def i32(self, a):
        d = self.read(a, 4)
        return struct.unpack('<i', d)[0] if len(d) == 4 else None


if __name__ == '__main__':
    p = Probe()
    b = p.base()
    print('libUnreal 基址 0x%x' % b)
    print('ELF 头', p.read(b, 4))
    m = [l for l in p.maps().splitlines() if 'kardsai' in l or 'libUnreal' in l]
    print('\n'.join(m))
