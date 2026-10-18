# KARDS 对局 action 串编解码（还原自 libUnreal.so FUN_07541334）
# 格式：%02d 密钥长度表索引 | %06d 明文UTF-8字节数 | b64(3字节: key[0..2] ^ 会话key) | key(随机base64字符) | b64(明文 ^ key)
import base64, json, random

B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'

def _b64len(n):
    return 4 * ((n + 2) // 3)

def decode(s):
    """返回 (明文字符串, 会话key, 索引)"""
    idx = int(s[:2])
    n = int(s[2:8])
    body = s[8:]
    clen = _b64len(n)
    keylen = len(body) - 4 - clen
    hdr = base64.b64decode(body[:4])
    key = body[4:4 + keylen].encode()
    cipher = base64.b64decode(body[4 + keylen:])
    plain = bytes(c ^ key[i % keylen] for i, c in enumerate(cipher))
    sess = ((hdr[0] ^ key[0]) << 16) | ((hdr[1] ^ key[1 % keylen]) << 8) | (hdr[2] ^ key[2 % keylen])
    return plain.decode('utf-8'), sess, idx

def encode(text, sess_key, idx=0, keylen=None):
    """按客户端相同格式编码；keylen 需与客户端长度表 table[idx] 一致（若客户端校验）"""
    data = text.encode('utf-8')
    if keylen is None:
        keylen = random.randint(60, 120)
    key = ''.join(random.choice(B64) for _ in range(keylen)).encode()
    k = sess_key % 0xffffff
    hdr = bytes([key[0] ^ (k >> 16) & 0xff, key[1 % keylen] ^ (k >> 8) & 0xff, key[2 % keylen] ^ k & 0xff])
    cipher = bytes(c ^ key[i % keylen] for i, c in enumerate(data))
    return '%02d%06d' % (idx, len(data)) + base64.b64encode(hdr).decode() + key.decode() + base64.b64encode(cipher).decode()

if __name__ == '__main__':
    import sys
    for s in json.load(open(sys.argv[1])):
        p, k, i = decode(s)
        print(f'[idx={i} key={k}] {p}')
