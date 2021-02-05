import io
from typing import Iterable, Iterator, Mapping, Tuple, Type, TypeVar

from nutcracker.utils.funcutils import flatten
from nutcracker.sputm.types import Element
from nutcracker.sputm.script.opcodes import OpTable

from .parser import CString, RefOffset, ScriptArg, Statement


S_Arg = TypeVar('S_Arg', bound=ScriptArg)
ByteCode = Mapping[int, Statement]


def get_argtype(args: Iterable[ScriptArg], argtype: Type[S_Arg]) -> Iterable[S_Arg]:
    for arg in args:
        if isinstance(arg, argtype):
            yield arg


def descumm(data: bytes, opcodes: OpTable) -> ByteCode:
    with io.BytesIO(data) as stream:
        bytecode = {}
        while True:
            next_byte = stream.read(1)
            if not next_byte:
                break
            opcode = ord(next_byte)
            try:
                op = opcodes[opcode](opcode, stream)  # type: ignore
                bytecode[op.offset] = op
                # print(f'0x{op.offset:04x}', op)

            except Exception as e:
                print(f'{type(e)}: {str(e)}')
                print(f'0x{stream.tell():04x}', f'0x{opcode:02x}')
                raise e

        for _off, stat in bytecode.items():
            for arg in get_argtype(stat.args, RefOffset):
                assert arg.abs in bytecode, hex(arg.abs)

        assert to_bytes(bytecode) == data
        assert to_bytes(refresh_offsets(bytecode)) == data, (
            to_bytes(refresh_offsets(bytecode)),
            data,
        )
        return bytecode


def print_bytecode(bytecode: ByteCode) -> None:
    for off, stat in bytecode.items():
        print(f'0x{off:04x}', stat)


def get_strings(bytecode: ByteCode) -> Iterable[CString]:
    for _off, stat in bytecode.items():
        for arg in get_argtype(stat.args, CString):
            if arg.msg:
                yield arg


def update_strings(bytecode: ByteCode, strings: Iterable[bytes]) -> ByteCode:
    for orig, upd in zip(get_strings(bytecode), strings):
        orig.msg = upd
    return refresh_offsets(bytecode)


def refresh_offsets(bytecode: ByteCode) -> ByteCode:
    updated = {}
    off = 0
    for stat in bytecode.values():
        for arg in get_argtype(stat.args, RefOffset):
            arg.endpos += off - stat.offset
        stat.offset = off
        off += len(stat.to_bytes())
    for stat in bytecode.values():
        for arg in get_argtype(stat.args, RefOffset):
            arg.abs = bytecode[arg.abs].offset
        updated[stat.offset] = stat
    return updated


def to_bytes(bytecode: ByteCode) -> bytes:
    with io.BytesIO() as stream:
        for off, stat in bytecode.items():
            assert off == stream.tell()
            stream.write(stat.to_bytes())
        return stream.getvalue()


def global_script(data: bytes) -> Tuple[bytes, bytes]:
    return b'', data


def local_script(data: bytes) -> Tuple[bytes, bytes]:
    return data[:1], data[1:]


def local_script_v7(data: bytes) -> Tuple[bytes, bytes]:
    return data[:2], data[2:]


def local_script_v8(data: bytes) -> Tuple[bytes, bytes]:
    return data[:4], data[4:]


def verb_script(data: bytes) -> Tuple[bytes, bytes]:
    serial = b''
    with io.BytesIO(data) as stream:
        while True:
            key = stream.read(1)
            serial += key
            if key in {b'\0'}:  # , b'\xFF'}:
                break
            serial += stream.read(2)
        return serial, stream.read()


script_map = {
    'SCRP': global_script,
    'LSCR': local_script,
    'VERB': verb_script,
    'ENCD': global_script,
    'EXCD': global_script,
}


def get_scripts(root: Iterable[Element]) -> Iterator[Element]:
    for elem in root:
        if elem.tag in {'LECF', 'LFLF', 'RMDA', 'ROOM', 'OBCD', *script_map}:
            if elem.tag in script_map:
                yield elem
            else:
                yield from get_scripts(elem.children)


if __name__ == '__main__':
    import argparse
    import glob

    from ..preset import sputm
    from nutcracker.utils.fileio import read_file

    from .opcodes import OPCODES_he80

    parser = argparse.ArgumentParser(description='read smush file')
    parser.add_argument('files', nargs='+', help='files to read from')
    parser.add_argument('--chiper-key', default='0x00', type=str, help='xor key')
    args = parser.parse_args()

    files = set(flatten(glob.iglob(r) for r in args.files))
    for filename in files:

        resource = read_file(filename, key=int(args.chiper_key, 16))

        for elem in get_scripts(sputm.map_chunks(resource)):
            _, script_data = script_map[elem.tag](elem.data)
            bytecode = descumm(script_data, OPCODES_he80)
            print_bytecode(bytecode)
