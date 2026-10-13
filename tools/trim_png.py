# Trim trailing all-black rows from an RGB/RGBA 8-bit PNG (stdlib only).
import sys, zlib, struct
def chunks(d):
    i = 8
    while i < len(d):
        n = struct.unpack(">I", d[i:i+4])[0]; t = d[i+4:i+8]
        yield t, d[i+8:i+8+n]; i += 12 + n
src, dst, pad = sys.argv[1], sys.argv[2], int(sys.argv[3])
d = open(src, "rb").read(); assert d[:8] == b"\x89PNG\r\n\x1a\n"
idat = b""; 
for t, c in chunks(d):
    if t == b"IHDR": w, h, bd, ct = struct.unpack(">IIBB", c[:10])
    if t == b"IDAT": idat += c
assert bd == 8 and ct in (2, 6); bpp = 3 if ct == 2 else 4
raw = zlib.decompress(idat); stride = w * bpp
rows, prev = [], bytearray(stride)
for y in range(h):
    f = raw[y*(stride+1)]; line = bytearray(raw[y*(stride+1)+1:(y+1)*(stride+1)])
    for x in range(stride):
        a = line[x-bpp] if x >= bpp else 0; b = prev[x]; c = prev[x-bpp] if x >= bpp else 0
        if f == 1: line[x] = (line[x] + a) & 255
        elif f == 2: line[x] = (line[x] + b) & 255
        elif f == 3: line[x] = (line[x] + ((a + b) >> 1)) & 255
        elif f == 4:
            p = a + b - c; pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
            line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
    rows.append(bytes(line)); prev = line
def dark(r): return max(r[i] for i in range(len(r)) if (i % bpp) != 3) < 24
last = max(y for y in range(h) if not dark(rows[y]))
nh = min(h, last + 1 + pad)
data = b"".join(b"\x00" + rows[y] for y in range(nh))
def ch(t, c): return struct.pack(">I", len(c)) + t + c + struct.pack(">I", zlib.crc32(t + c) & 0xffffffff)
png = b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", w, nh, 8, ct, 0, 0, 0)) + ch(b"IDAT", zlib.compress(data, 9)) + ch(b"IEND", b"")
open(dst, "wb").write(png); print(f"{w}x{h} -> {w}x{nh}")
