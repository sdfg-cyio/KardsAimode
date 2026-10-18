# UE5 内存读取基础：名字表、对象表、对象名/类名/路径
import struct, re
from probe_client import Probe

NAME_BLOCKS_OFF = 0xa187ec0      # FNamePool.Blocks（so 偏移，本版 libUnreal 固定）
OBJ_ITEM_SIZE = 24               # FUObjectItem 大小
OBJ_CHUNK = 64 * 1024            # 每块元素数

# UObjectBase 字段偏移
UO_CLASS = 0x10
UO_NAME = 0x18
UO_OUTER = 0x20


class UE:
    def __init__(self, probe=None):
        self.p = probe or Probe()
        self.base = self.p.base()
        self.blocks_addr = self.base + NAME_BLOCKS_OFF
        self.blocks = {}
        self.name_cache = {}
        self.objarr = None  # (Objects 指针, NumElements)

    # ---------- 名字 ----------
    def block_data(self, i):
        """整块读取名字表块（128KB），本地解析；最后一块可能仍在增长，每次都刷新"""
        bd = self.__dict__.setdefault('_bdata', {})
        if i not in bd:
            b = self.block(i)
            if not b:
                return None
            bd[i] = self.p.read(b, 0x20000)
        return bd[i]

    def block(self, i):
        if i not in self.blocks:
            self.blocks[i] = self.p.u64(self.blocks_addr + i * 8)
        return self.blocks[i]

    def name(self, idx, number=0):
        key = idx
        if key not in self.name_cache:
            blk, off = idx >> 16, (idx & 0xffff) * 2
            data = self.block_data(blk)
            if not data or off + 2 > len(data):
                return '<badname %x>' % idx
            h = struct.unpack_from('<H', data, off)[0]
            wide, ln = h & 1, h >> 6
            raw = data[off + 2: off + 2 + ln * (2 if wide else 1)]
            s = raw.decode('utf-16-le' if wide else 'latin-1', 'replace')
            self.name_cache[key] = s
        s = self.name_cache[key]
        return s if number == 0 else '%s_%d' % (s, number - 1)

    def fname_at(self, addr):
        d = self.p.read(addr, 8)
        if len(d) < 8:
            return None
        i, n = struct.unpack('<II', d)
        return self.name(i, n)

    # ---------- 对象表 ----------
    def find_objarray(self):
        """在 .data/.bss 中按 FChunkedFixedUObjectArray 字段一致性定位对象表"""
        maps = []
        for l in self.p.maps().splitlines():
            m = re.match(r'([0-9a-f]+)-([0-9a-f]+) (\S+) (\S+) \S+ \S+\s*(.*)', l)
            if m:
                maps.append((int(m[1], 16), int(m[2], 16), m[3], m[5]))
        un = [x for x in maps if 'libUnreal' in x[3]]
        glob = [(un[-1][0], un[-1][1])]
        for a, b, perm, name in maps:
            if a == glob[-1][1] and perm.startswith('rw') and name in ('', '[anon:.bss]'):
                glob.append((a, b))
        res = []
        for ga, gb in glob:
            data = b''
            a = ga
            while a < gb:
                data += self.p.read(a, min(gb - a, 4 << 20))
                a += 4 << 20
            for off in range(0, len(data) - 32, 8):
                objs, pre, mx, num, mxc, nc = struct.unpack_from('<QQiiii', data, off)
                if not objs or num < 10000 or num > mx or mx > 0x4000000:
                    continue
                if mxc != (mx + OBJ_CHUNK - 1) // OBJ_CHUNK or nc != (num + OBJ_CHUNK - 1) // OBJ_CHUNK:
                    continue
                res.append((ga + off, objs, num))
        return res

    OBJARR_OFF = 0xa1e1e50   # FChunkedFixedUObjectArray（so 偏移，本版固定）

    def init_objects(self):
        # 优先用已知偏移，避免扫描 .bss 时误读到 Java 堆（ART GC 压缩期间会让读取卡死）
        addr = self.base + self.OBJARR_OFF
        objs, pre, mx, num = struct.unpack('<QQii', self.p.read(addr, 24))
        if objs and 0 < num <= mx:
            self.objarr = (objs, num, addr)
            o = self.obj(0)
            if o and self.p.u32(o + 0xC) == 0:
                return addr
        cands = self.find_objarray()
        for addr, objs, num in cands:
            self.objarr = (objs, num, addr)
            o = self.obj(0)
            if o and self.p.u32(o + 0xC) == 0:
                return addr
        raise RuntimeError('没找到对象表 %r' % cands)

    def num_objects(self):
        objs, num, addr = self.objarr
        return self.p.i32(addr + 20)

    def obj(self, i):
        objs = self.objarr[0]
        chunk = self.p.u64(objs + (i // OBJ_CHUNK) * 8)
        if not chunk:
            return 0
        return self.p.u64(chunk + (i % OBJ_CHUNK) * OBJ_ITEM_SIZE)

    def chunk_items(self, ci):
        """一次读一整块对象项，返回对象指针列表"""
        objs = self.objarr[0]
        chunk = self.p.u64(objs + ci * 8)
        if not chunk:
            return []
        data = self.p.read(chunk, OBJ_CHUNK * OBJ_ITEM_SIZE)
        return [struct.unpack_from('<Q', data, k * OBJ_ITEM_SIZE)[0] for k in range(len(data) // OBJ_ITEM_SIZE)]

    # ---------- 对象信息 ----------
    def obj_name(self, o):
        return self.fname_at(o + UO_NAME)

    def obj_class(self, o):
        return self.p.u64(o + UO_CLASS)

    def obj_outer(self, o):
        return self.p.u64(o + UO_OUTER)

    def obj_path(self, o):
        if getattr(self, 'heads', None) and o in self.heads:
            return self.path(o)
        parts = []
        while o and len(parts) < 16:
            parts.append(self.obj_name(o))
            o = self.obj_outer(o)
        return '.'.join(reversed(parts))

    # ---------- 快速对象索引（原生批量读取对象头） ----------
    def index(self):
        if not self.objarr:
            self.init_objects()
        n = self.num_objects()
        self.heads = {}
        for st in range(0, n, 0x10000):
            for o, c, ni, nn, outer in self.p.obj_heads(self.objarr[0], st, min(0x10000, n - st)):
                if o:
                    self.heads[o] = (c, ni, nn, outer)
        self._paths = {}
        self.by_path = {}
        for o in self.heads:
            self.by_path[self.path(o)] = o
        return len(self.heads)

    def nm(self, o):
        h = self.heads.get(o)
        return self.name(h[1], h[2]) if h else '?'

    def path(self, o):
        if o in self._paths:
            return self._paths[o]
        h = self.heads.get(o)
        if not h:
            return '?'
        s = self.path(h[3]) + '.' + self.nm(o) if h[3] else self.nm(o)
        self._paths[o] = s
        return s

    def cls_of(self, o):
        return self.heads.get(o, (0,))[0]

    def instances(self, cls_name):
        """某类（按类名）的全部非 CDO 实例"""
        return [o for o, h in self.heads.items()
                if self.nm(h[0]) == cls_name and not self.nm(o).startswith('Default__')]

    def find_func(self, cls_path, fname):
        return self.by_path.get(cls_path + '.' + fname)

    # ---------- 反射：属性与函数参数 ----------
    def fields(self, struct_addr):
        """[(名, 类型, 偏移, 大小, 标志)]，按 FField 链"""
        out = []
        f = self.p.u64(struct_addr + 0x50)
        while f and len(out) < 4000:
            d = self.p.read(f, 0x48)
            fc, nxt = struct.unpack_from('<Q', d, 0x08)[0], struct.unpack_from('<Q', d, 0x18)[0]
            ni, nn = struct.unpack_from('<II', d, 0x20)
            esz = struct.unpack_from('<i', d, 0x30)[0]
            flags = struct.unpack_from('<Q', d, 0x38)[0]
            off = struct.unpack_from('<i', d, 0x44)[0]
            t = self.fname_at(fc) if fc else '?'
            out.append((self.name(ni, nn), t, off, esz, flags, f))
            f = nxt
        return out

    def props_all(self, cls):
        """类及所有父类的属性 {名: (类型, 偏移, 大小, FField)}"""
        res = {}
        c = cls
        while c:
            for nm, t, off, esz, fl, f in self.fields(c):
                res.setdefault(nm, (t, off, esz, f))
            c = self.p.u64(c + 0x40)
        return res

    def func_info(self, func):
        """(参数块大小, 参数列表)，按函数缓存"""
        fc = self.__dict__.setdefault('_finfo', {})
        if func not in fc:
            size = self.p.i32(func + 0x58)
            fc[func] = (max(size, 1), [x for x in self.fields(func) if x[4] & 0x80])  # CPF_Parm
        return fc[func]

    def call(self, obj, func, **args):
        """调用 UFunction；简单类型按名传参，返回 {参数名: 值}"""
        return self.call_many([(obj, func, args)])[0]

    def call_many(self, calls):
        """calls=[(obj, func, {参数})]，同一帧内执行；返回每个调用的结果字典（对象失效时为 None）"""
        packed = []
        for obj, func, args in calls:
            packed.append((obj, func, self._pack(func, args)))
        bst, res = self.p.call_batch(packed)
        if bst != 0:
            raise RuntimeError('调用失败 状态 %d（1=超时 2=钩子未就绪 3=卡死 4=之前已卡死）' % bst)
        out = []
        for (obj, func, args), (st, data) in zip(calls, res):
            out.append(None if st != 0 else self._unpack(func, data))
        return out

    def _pack(self, func, args):
        size, params = self.func_info(func)
        buf = bytearray(size)
        for nm, t, off, esz, fl, f in params:
            if nm in args:
                v = args[nm]
                if t in ('IntProperty',):
                    struct.pack_into('<i', buf, off, v)
                elif t in ('BoolProperty', 'ByteProperty', 'EnumProperty'):
                    struct.pack_into('<B', buf, off, int(v))
                elif t in ('ObjectProperty', 'ClassProperty'):
                    struct.pack_into('<Q', buf, off, v)
                elif t == 'DoubleProperty':
                    struct.pack_into('<d', buf, off, v)
                elif t == 'FloatProperty':
                    struct.pack_into('<f', buf, off, v)
                elif t == 'NameProperty':
                    struct.pack_into('<II', buf, off, *v)
                else:
                    buf[off:off + esz] = v
        return bytes(buf)

    def _unpack(self, func, out):
        size, params = self.func_info(func)
        res = {}
        for nm, t, off, esz, fl, f in params:
            raw = out[off:off + esz]
            if t == 'IntProperty':
                res[nm] = struct.unpack('<i', raw)[0]
            elif t in ('BoolProperty',):
                res[nm] = raw[0] != 0
            elif t in ('ByteProperty', 'EnumProperty'):
                res[nm] = raw[0]
            elif t in ('ObjectProperty', 'ClassProperty'):
                res[nm] = struct.unpack('<Q', raw)[0]
            elif t == 'DoubleProperty':
                res[nm] = struct.unpack('<d', raw)[0]
            elif t == 'FloatProperty':
                res[nm] = struct.unpack('<f', raw)[0]
            elif t == 'NameProperty':
                res[nm] = self.name(*struct.unpack('<II', raw))
            elif t in ('StrProperty',):
                ptr, num = struct.unpack('<Qi', raw[:12])
                res[nm] = self.p.read(ptr, num * 2).decode('utf-16-le', 'replace').rstrip('\0') if ptr and num > 0 else ''
            elif t == 'ArrayProperty':
                # 数组按元素 8 字节（对象指针数组）读出；其他元素类型由调用方自行解析 (ptr, num)
                ptr, num = struct.unpack('<Qi', raw[:12])
                if ptr and 0 < num < 4096:
                    d = self.p.read(ptr, num * 8)
                    res[nm] = list(struct.unpack('<%dQ' % (len(d) // 8), d))
                    res[nm + '#raw'] = (ptr, num)
                else:
                    res[nm] = []
            else:
                res[nm] = raw
        return res

    # ---------- 钩子 ----------
    PE_OBJ_OFF = 0x3d32cc8     # UObject::ProcessEvent（so 偏移）
    PE_ACTOR_OFF = 0x5fcbfa8   # AActor::ProcessEvent

    def setup_calls(self):
        if not self.objarr:
            self.init_objects()
        nv, ok = self.p.hook_all(self.base + self.PE_OBJ_OFF, self.base + self.PE_ACTOR_OFF,
                                 self.objarr[0], self.num_objects())
        # 主线程即游戏线程（Android UE 的 GameThread 名为 "GameThread"）
        tid = [t for t, n in self.p.threads() if n.strip() == 'GameThread']
        if tid:
            self.p.set_game_tid(tid[0])
        return nv, ok, tid
