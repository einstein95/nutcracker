import struct
import io
import itertools

from .base import UINT16LE, wrap_uint16le, unwrap_uint16le

BG = 39


def decode_line(line, width, bg):
    with io.BytesIO(line) as stream, io.BytesIO() as ostr:
        while ostr.tell() < width:
            off = UINT16LE.unpack(stream.read(2))[0]
            if ostr.tell() + off > width:
                break
            ostr.write(bytes([bg for _ in range(off)]))
            w = UINT16LE.unpack(stream.read(2))[0] + 1
            ostr.write(stream.read(w))
        ostr.write(bytes([bg for _ in range(width - ostr.tell())]))
        return list(ostr.getvalue())[:width]


def unidecoder(width, height, f):
    with io.BytesIO(f) as stream:
        lines = [
            decode_line(unwrap_uint16le(stream), width, BG) for _ in range(height + 1)
        ][:height]
        tail = stream.read()
        assert tail in {b'', b'\00'}, tail
        return lines


def join_segments(segments):
    return b''.join(
        (
            struct.pack('<H', off)
            + (struct.pack('<H', len(lst) - 1) + lst if lst else b'')
        )
        for off, lst in segments
    )


def split_segments_44(line, bg):
    off = 0
    width = len(line)
    pos = 0
    for is_bg, group in itertools.groupby(line, key=lambda val: val == bg):
        lst = bytes(group)
        pos += len(lst)
        if not is_bg:
            yield off, lst + (b'' if pos < width else b'\x00')
        off = len(lst)
    assert pos >= width
    if is_bg:
        yield off, b'\x00'


def encode_line_44(width, line, bg):
    assert width == len(line)
    return join_segments(split_segments_44(line, bg))


def codec44(width, height, out):
    assert height == len(out)
    buf = b''.join(
        wrap_uint16le(encode_line_44(width, line, BG))
        for line in out + [[0 for _ in range(width)]]
    )
    return buf + b'\x00' * (len(buf) % 2)


def split_segments_21(line, bg):
    off = 0
    lst = b''
    for is_bg, group in itertools.groupby(line, key=lambda val: val == bg):
        lst = bytes(group)
        if not is_bg:
            yield off, lst
        off = len(lst)
        if not is_bg:
            lst = b''
    yield len(lst) + 1, b''


def encode_line_21(width, line, bg):
    assert width == len(line)
    return join_segments(split_segments_21(line, bg))


def codec21(width, height, out):
    assert height == len(out)
    buf = b''.join(
        wrap_uint16le(encode_line_21(width, line, BG))
        for line in out + [[BG for _ in range(width)]]
    )
    return buf + b'\x00' * (len(buf) % 2)
