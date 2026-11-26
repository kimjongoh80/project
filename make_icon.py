"""외부 라이브러리 없이 Wi-Fi 모양 아이콘(icon.ico)을 생성한다."""
import math
import struct
import zlib


def render(size):
    px = bytearray()
    cx, cy = size * 0.5, size * 0.78
    r_bg = size * 0.22
    for y in range(size):
        px.append(0)  # PNG filter: none
        for x in range(size):
            # 둥근 사각형 배경
            dx = max(abs(x + 0.5 - size / 2) - (size / 2 - r_bg), 0)
            dy = max(abs(y + 0.5 - size / 2) - (size / 2 - r_bg), 0)
            inside = math.hypot(dx, dy) <= r_bg
            if not inside:
                px += b"\0\0\0\0"
                continue
            r, g, b = 14, 18, 23
            d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
            ang = math.degrees(math.atan2(cy - (y + 0.5), x + 0.5 - cx))
            on = False
            if d <= size * 0.075:
                on = True
            elif 45 <= ang <= 135:
                for rad in (0.22, 0.38, 0.54):
                    if abs(d - size * rad) <= size * 0.045:
                        on = True
            if on:
                r, g, b = 63, 167, 255
            px += bytes((r, g, b, 255))
    return bytes(px)


def png(size):
    def chunk(t, data):
        c = struct.pack(">I", len(data)) + t + data
        return c + struct.pack(">I", zlib.crc32(t + data) & 0xFFFFFFFF)
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(render(size), 9)) + chunk(b"IEND", b""))


def main(path="icon.ico"):
    sizes = [16, 32, 48, 256]
    imgs = [png(s) for s in sizes]
    out = struct.pack("<HHH", 0, 1, len(sizes))
    off = 6 + 16 * len(sizes)
    for s, data in zip(sizes, imgs):
        out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), off)
        off += len(data)
    with open(path, "wb") as f:
        f.write(out + b"".join(imgs))
    print("wrote", path)


def iconset(folder):
    """macOS용 .iconset 폴더 생성 (iconutil -c icns 로 .icns 변환)."""
    import os
    os.makedirs(folder, exist_ok=True)
    cache = {}
    for base in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            px = base * scale
            if px not in cache:
                cache[px] = png(px)
            name = f"icon_{base}x{base}{'@2x' if scale == 2 else ''}.png"
            with open(os.path.join(folder, name), "wb") as f:
                f.write(cache[px])
    print("wrote", folder)


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3 and sys.argv[1] == "--iconset":
        iconset(sys.argv[2])
    else:
        main()
