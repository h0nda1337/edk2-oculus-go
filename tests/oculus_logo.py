"""Independent pixel oracle for the private stock splash. SPDX-License-Identifier: BSD-2-Clause-Patent"""

import hashlib
import struct

LOGO_W, LOGO_H = 68, 42
STOCK_HASH = "d8ba4434e87f8bfc55f33091c2d78401fcea22a068105942285edb2da6869d4a"


def stock_frame(path):
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == STOCK_HASH
    assert struct.unpack_from("<8s4I", data) == (b"SPLASH!!", 1440, 2560, 0, 0)
    return data[512 : 512 + 1440 * 2560 * 3]


def stock_mark(frame, first_row=558):
    # Sample in worn coordinates. Keep the stock antialiasing by averaging each cell.
    values = bytearray()
    for y in range(LOGO_H):
        for x in range(LOGO_W):
            total = 0
            for u in range(3):
                pos = 3 * ((first_row + 3 * x + u) * 1440 + 783 - 3 * (y + 1))
                total += sum(frame[pos : pos + 9])
            gray = total // 27
            values.append(gray if gray > 8 else 0)
    return bytes(values)


def matches_tile(rgb, mark):
    # Dark stock-background pixels are transparent over the intro's blue gradient.
    for y in range(LOGO_H):
        for x in range(LOGO_W):
            u, v = (352 - LOGO_W) // 2 + x, 355 + y
            value = mark[y * LOGO_W + x]
            light = max(0, 27000 - (u - 176) ** 2 - (v - 200) ** 2)
            expected = (
                bytes([value]) * 3
                if value
                else bytes((light // 9400, light // 3400, light // 1270))
            )
            pos = (v * 352 + u) * 3
            if rgb[pos : pos + 3] != expected:
                return False
    return True


def check_center_mark(frame, mark):
    top = (1440 - LOGO_H) // 2
    # Verify every channel of both marks, then mask only their exact rectangle so
    # the usual Shell oracle can still reject any other pixels in the margins.
    masked = bytearray(frame)
    for eye in range(2):
        for x in range(LOGO_W):
            for y in range(LOGO_H):
                offset = 3 * (
                    (eye * 1280 + (1280 - LOGO_W) // 2 + x) * 1440 + 1439 - top - y
                )
                assert (
                    frame[offset : offset + 3] == bytes([mark[y * LOGO_W + x]]) * 3
                ), "Centered Shell emblem differs"
                masked[offset : offset + 3] = bytes(3)
    return masked
