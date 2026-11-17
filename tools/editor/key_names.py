"""The key names: the names by which the game finds some records of the data.

At the load, FUN_00601a40 (index.cpp) compares the name of every club, nation, club comp, staff comp and colour
with fixed lists of names (match_club_key_id 0x6146b0 for the clubs, through _stricmp 0x951c50) and keeps the row of
each one it finds in a key id. Rules of the game use these key ids (the English, Argentinian or MLS rules, say).
A key id that stays unset at the end gives the box "index.cpp 5809" (report_missing_key_id 0x60d780) and the data
does not load. So the editor keeps these names: a record with a key name keeps it, and no record takes one.

src/cm3/key_ids_table.c holds the lists as addresses of the names in cm0102.exe (tools/research/gen_key_ids.py
made it); the names are read from the player's own file, as the port does.
"""
import os
import re
import struct

TABLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src", "cm3", "key_ids_table.c")


def _strings(exe):
    data = open(exe, "rb").read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    optional = struct.unpack_from("<H", data, pe + 20)[0]
    base = struct.unpack_from("<I", data, pe + 24 + 28)[0]
    sections = [struct.unpack_from("<IIII", data, pe + 24 + optional + i * 40 + 8) for i in range(count)]

    def c_string(address):
        rva = address - base
        for _vsize, va, rsize, rptr in sections:
            if va <= rva < va + rsize:
                start = rptr + rva - va
                return data[start:data.index(b"\0", start)].decode("latin-1")
        raise ValueError(f"{address:#x} is not in {exe}")
    return c_string


def load(exe, chain):
    """{lower-case name: True when the data must hold it} for one chain of the table ("club", "nation", ...)."""
    text = open(TABLE).read()
    reported = [int(m.group(1)) for m in re.finditer(r"\{0x[0-9a-f]+, -?\d+, \d, (\d)\}", text)]
    body = re.search(r"g_key_%s_chain\[\] = \{(.*?)\n\};" % chain, text, re.S).group(1)
    c_string = _strings(exe)
    names = {}
    for m in re.finditer(r"\{(0x[0-9a-f]+), (-?\d+), (-?\d+), \d+\}", body):
        name = c_string(int(m.group(1), 16)).lower()
        must = any(int(s) >= 0 and reported[int(s)] for s in m.group(2, 3))
        names[name] = names.get(name, False) or must
    return names
