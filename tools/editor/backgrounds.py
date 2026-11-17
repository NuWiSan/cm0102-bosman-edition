"""The background pictures of the game: Pictures/pics.cfg and its RGN files.

How the game reads them (port: src/cm3/background.c, with the original's addresses):
- pics.cfg has sections [NATIONS], [CLUBS], [STADIUMS], [COMPS], [AWARDS], [STAFF] and the screens [TRAINING],
  [BOARDROOM], [TROPHY], [TRANSFER], [SI] (setup_background_system 0x41b3d0). A line is "key: name, name, {name}";
  "#" starts a comment; spaces inside a name are dropped; a name in {} is a picture of a won competition.
- The key is the record's name, compared without case (_stricmp 0x951c50): a club, nation, stadium, comp or award
  by its English name (0x545880 and the others), a person as "first second d/m/yyyy" with "*" for a missing name
  (0x41cf74, format 0x989ac8). A key that matches no record is unused; only the switch -verifypics reports it
  (verify_background_config 0x41bc20, called at 0x82830c).
- A name opens as Pictures/<name>, Pictures/stadium/<name> or Pictures/old/<name>, then the same with "_" in front;
  a name that no file has is dropped (background_add_picture 0x41b8c0).
- The files are RGN: a 48-byte header (width, height, byte size of the pixels, then fixed values) and 16-bit RGB565
  pixels, rows from the top (gui_load_rgn_picture 0x5e40d0). The backgrounds are 800x600.

The game reads a file of the user folder before the game folder's (src/recomp_rt/win/files.c), so the editor writes
pics.cfg and new pictures into <user folder>/Pictures and never changes the game folder.
"""
import os
import struct
import zlib

SECTIONS = ["nations", "clubs", "stadiums", "comps", "awards", "staff", "training", "boardroom", "trophy",
            "transfer", "si"]
RECORD_SECTIONS = {"nation": "nations", "club": "clubs", "stadium": "stadiums", "comp": "comps",
                   "staff_comp": "awards", "person": "staff"}
RGN_HEADER = struct.pack("<9I", 0x01684C14, 32, 64, 0, 16, 0xF800, 0x07E0, 0x1F, 0)
WIDTH, HEIGHT = 800, 600
BAD_IN_NAME = set(' ,{}:#\\/"*?<>|')


def find_ci(folder, name):
    """The path of name in folder, matched without case as the game matches it, or None."""
    if not folder or not os.path.isdir(folder):
        return None
    low = name.lower()
    for f in os.listdir(folder):
        if f.lower() == low:
            return os.path.join(folder, f)
    return None


def is_rgn(b):
    if len(b) < 48:
        return False
    w, h, n = struct.unpack_from("<3I", b)
    return 0 < w <= 4096 and 0 < h <= 4096 and n == w * h * 2 and len(b) == 48 + n


def rgn_to_png(b, scale=1):
    """A PNG of an RGN picture, every scale-th pixel."""
    w, h, _ = struct.unpack_from("<3I", b)
    out = bytearray()
    for y in range(0, h, scale):
        out.append(0)
        row = struct.unpack_from(f"<{w}H", b, 48 + 2 * w * y)
        for p in row[::scale]:
            out += bytes(((p >> 11) << 3, ((p >> 5) & 63) << 2, (p & 31) << 3))
    w2, h2 = len(range(0, w, scale)), len(range(0, h, scale))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w2, h2, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(out), 6)) + chunk(b"IEND", b""))


class Entry:
    def __init__(self, section, key, names, won):
        self.section, self.key, self.names, self.won = section, key, names, won

    def line(self):
        return f"{self.key}: " + ", ".join(self.names + [f"{{{n}}}" for n in self.won])


class Backgrounds:
    def __init__(self, game_pictures, user_pictures):
        self.game, self.user = game_pictures, user_pictures      # user is None without --user
        self.load()

    def cfg_path(self):
        for folder in (self.user, self.game):
            p = find_ci(folder, "pics.cfg")
            if p:
                return p
        return None

    def load(self):
        """lines: the file's lines, each a text or an Entry."""
        self.lines = []
        p = self.cfg_path()
        text = open(p, "rb").read().decode("latin-1") if p else ""
        section = None
        for raw in text.replace("\r\n", "\n").split("\n"):
            s = raw.split("#", 1)[0].strip()
            if s.startswith("["):
                name = s[1:].split("]", 1)[0].strip().lower()
                section = name if name in SECTIONS else None
                self.lines.append(raw)
            elif s and section and ":" in s:
                key, rest = s.split(":", 1)
                names, won, cur, inside = [], [], "", False
                for c in rest + ",":            # as read_names: "{" marks the next name, which ends at "," or "}"
                    if c in ",{}":
                        if c == "{":
                            inside = True
                        if cur:
                            (won if inside else names).append(cur)
                            inside = False
                        cur = ""
                    elif c not in " \t":
                        cur += c
                self.lines.append(Entry(section, key, names, won))
            else:
                self.lines.append(raw)
        while self.lines and self.lines[-1] == "":
            self.lines.pop()

    def entries(self, section=None):
        return [e for e in self.lines if isinstance(e, Entry) and (section is None or e.section == section)]

    def entry(self, section, key):
        for e in self.entries(section):
            if e.key.lower() == key.lower():
                return e
        return None

    def set(self, section, key, names, won):
        """Changes the line of the key (a new line at the end of its section; no line when it has no picture)."""
        e = self.entry(section, key)
        if e is None and (names or won):
            e = Entry(section, key, [], [])
            at = None                               # the last line of the section that is not empty
            current = None
            for i, x in enumerate(self.lines):
                if isinstance(x, str) and x.split("#", 1)[0].strip().startswith("["):
                    current = x.split("#", 1)[0].strip()[1:].split("]", 1)[0].strip().lower()
                if current == section and (isinstance(x, Entry) or x.strip()):
                    at = i
            if at is None:
                self.lines += ["", f"[{section.upper()}]"]
                at = len(self.lines) - 1
            self.lines.insert(at + 1, e)
        if e is None:
            return
        e.names, e.won = list(names), list(won)
        if not names and not won:
            self.lines.remove(e)

    def save(self):
        os.makedirs(self.user, exist_ok=True)
        text = "\r\n".join(x.line() if isinstance(x, Entry) else x for x in self.lines) + "\r\n"
        path = find_ci(self.user, "pics.cfg") or os.path.join(self.user, "pics.cfg")
        with open(path + ".part", "wb") as f:
            f.write(text.encode("latin-1", "replace"))
        os.replace(path + ".part", path)

    def file(self, name):
        """The file that the game opens for a name (the tries of 0x41b8c0, the user folder first), or None."""
        for n in (name, "_" + name):
            for sub in ("", "stadium", "old"):
                for folder in (self.user, self.game):
                    d = folder if not sub else (find_ci(folder, sub) if folder else None)
                    p = find_ci(d, n) if d else None
                    if p and os.path.isfile(p):
                        return p
        return None

    def files(self):
        """{lower-case file name: path} of the pictures folders (user first), with stadium/ and old/."""
        out = {}
        for folder in (self.game, self.user):
            for sub in ("", "stadium", "old"):
                d = folder if not sub else (find_ci(folder, sub) if folder else None)
                if d and os.path.isdir(d):
                    for f in os.listdir(d):
                        if os.path.isfile(os.path.join(d, f)) and f.lower() != "pics.cfg":
                            out[f.lower()] = os.path.join(d, f)
        return out

    def new_name(self, key):
        """A file name for a new picture of a key: no character that pics.cfg cannot hold, and no file of it."""
        base = "".join("_" if c in BAD_IN_NAME or ord(c) < 0x21 or ord(c) > 0x7E else c for c in key).strip("_.")
        base = base or "picture"
        have = self.files()
        for n in range(1, 1000):
            name = f"{base}_{n}.rgn"
            if name.lower() not in have and ("_" + name).lower() not in have:
                return name
        raise ValueError("no free name")

    def write_file(self, name, body):
        if not is_rgn(body) or set(name) & BAD_IN_NAME or not name.lower().endswith(".rgn"):
            raise ValueError("not an RGN picture")
        os.makedirs(self.user, exist_ok=True)
        path = os.path.join(self.user, name)
        with open(path + ".part", "wb") as f:
            f.write(body)
        os.replace(path + ".part", path)
