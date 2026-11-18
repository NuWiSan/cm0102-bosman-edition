#!/usr/bin/env python3
"""The database editor of the fork NuWiSan (spec docs/specs/2026-11-17-editor-and-new-nations-spec.md).

A small local web app: this server reads a data folder and serves a page for the browser. It runs the same on
Linux, Mac and Windows with Python 3 alone.

    python3 tools/editor/editor.py <data folder> [--user <user folder>] [--port 8102]

<data folder> is a game's Data folder (index.dat and the .dat files). --user is the game's user folder, the one
with the saves and the settings.txt; the badges and faces live in its folders badges/ and faces/. The
server listens on 127.0.0.1 only and opens the page in the browser.

It edits every table that the original editor edits (records.py has the layouts): clubs, people (person, contract,
national team, personal and player attributes, non-player attributes, likes and dislikes, career history), nations,
club competitions and their history, awards and their history, stadiums, cities, continents, colours, officials and
the name tables. It manages the pictures: each club's badge and person's face, the file name that the game looks
for, a picture (PNG, made by the page from PNG, SVG, WebP or JPEG) saved under that name; on the Pictures page it
converts the picture files that are not PNG and renames the PNG files whose name matches no record. It never
deletes a file.

The changes stay in memory until Save, which writes the whole data set into a new folder
<user folder>/Databases/<name>, which the game plays as a custom database. The opened data folder is never written.
"""
import argparse
import difflib
import http.server
import json
import os
import struct
import sys
import threading
import urllib.parse
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "seasons", "own_db"))
import cmdb  # noqa: E402
import cmdb1  # noqa: E402
import backgrounds  # noqa: E402
import key_names  # noqa: E402
import records  # noqa: E402

PICTURE_FOLDERS = {"badge": "badges", "face": "faces"}
MAX_PICTURE = 8 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PAGE_SIZE = 200
KEY_CHAINS = ("club", "nation", "club_comp", "staff_comp", "colour", "continent")


def file_name(text):
    """A name of the game (Latin-1 text) as the game makes a picture file name (pictures.c put_name): '_' for a
    character that a file name cannot hold."""
    return "".join("_" if c in '/\\:*?"<>|' or ord(c) < 0x20 else c for c in text)


class Data:
    """A data folder: the model of its tables, and the picture names of its clubs and people."""

    def __init__(self, path, user=""):
        fmt = cmdb1.staff_format(path)
        self.folder = cmdb1.open_folder(path) if fmt == 1 else cmdb.Folder(path)
        exe = os.path.join(os.path.dirname(os.path.abspath(path)), "cm0102.exe")
        keys = {c: key_names.load(exe, c) for c in KEY_CHAINS} if os.path.exists(exe) else None
        self.model = records.Model(self.folder, fmt, keys)
        self.backgrounds = backgrounds.Backgrounds(os.path.join(os.path.dirname(os.path.abspath(path)), "Pictures"),
                                                   os.path.join(user, "Pictures") if user else None)

    def picture(self, kind, i):
        """(picture kind, file name) of a record, or None."""
        m = self.model
        if kind == "club" and m.exists("club", i):
            return "badge", file_name(m.name("club", i))
        if kind == "person" and m.exists("person", i):
            return "face", self.face_name(i)
        return None

    def birth(self, pid):
        """(first name, second name, day, month, year) of a person, the date as the game's date functions give it
        from the stored day of the year (the common-year table, also in a leap year) and year."""
        m, r = self.model, self.model.rows["person"][pid]
        first, second = (m.name(t, struct.unpack_from("<i", r, o)[0]) for t, o in (("first", 4), ("second", 8)))
        day, year = struct.unpack_from("<hH", r, 0x10)
        day = min(max(day, 0), 364)
        mo = max(i for i in range(12) if cmdb1.CUM[i] <= day)
        return first, second, day - cmdb1.CUM[mo] + 1, mo + 1, year

    def background_key(self, kind, i):
        """The pics.cfg key of a record: its name, or for a person "first second d/m/yyyy" with "*" for a missing
        name (0x41cf74)."""
        if kind == "person":
            first, second, d, mo, y = self.birth(i)
            return f"{first or '*'} {second or '*'} {d}/{mo}/{y}"
        return self.model.name(kind, i)

    def background_keys(self, section):
        kind = next(k for k, s in backgrounds.RECORD_SECTIONS.items() if s == section)
        return {self.background_key(kind, i).lower(): self.background_key(kind, i) for i in self.model.rows[kind]}

    def face_name(self, pid):
        """The game's key (pictures_person_name): first and second name, '_' for a missing one, and the birth date
        d-m-yyyy as the game's date functions give it from the stored day of the year (the common-year table, also
        in a leap year: "Ashley Cole 20-12-1980") and year, also for a person with no date."""
        first, second, d, mo, y = self.birth(pid)
        return file_name(f"{first or '_'} {second or '_'} {d}-{mo}-{y}")

    def picture_names(self, kind):
        if kind == "badge":
            return {file_name(self.model.name("club", i)) for i in self.model.rows["club"]}
        return {self.face_name(i) for i in self.model.rows["person"]}

    def save(self, folder):
        def write(files, path):
            os.makedirs(path)
            for name, b in sorted(files.items()):
                with open(os.path.join(path, name), "wb") as f:
                    f.write(b)
        self.model.write(folder, write)
        self.model.changed.clear()

class Pictures:
    """The badges/ and faces/ folders of the game's user folder."""

    def __init__(self, user):
        self.user = user

    def folder(self, kind):
        return os.path.join(self.user, PICTURE_FOLDERS[kind]) if self.user else None

    def path(self, kind, name):
        folder = self.folder(kind)
        if not folder or not name or name in (".", "..") or "/" in name or "\\" in name:
            return None
        return os.path.join(folder, name + ".png")

    def exists(self, kind, name):
        p = self.path(kind, name)
        return bool(p and os.path.isfile(p))

    def file(self, kind, name):
        """A file of the folder by its full name, or None."""
        folder = self.folder(kind)
        if not folder or not name or name in (".", "..") or "/" in name or "\\" in name:
            return None
        p = os.path.join(folder, name)
        return p if os.path.isfile(p) else None

    def files(self, kind):
        folder = self.folder(kind)
        if not folder or not os.path.isdir(folder):
            return []
        return sorted(f for f in os.listdir(folder) if not f.startswith("."))


def make_handler(data, pictures):
    model = data.model
    bg = data.backgrounds

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def send(self, code, body, kind="application/json"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            elif isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def body(self):
            return json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0") or 0)) or b"{}")

        def with_picture(self, kind, i, out):
            p = data.picture(kind, i)
            if p:
                out["picture"] = dict(kind=p[0], name=p[1], has=pictures.exists(*p))
            return out

        def with_backgrounds(self, kind, i, out):
            section = backgrounds.RECORD_SECTIONS.get(kind)
            if section and out:
                bg.load()                       # pics.cfg as it is now: a person may change it by hand
                key = data.background_key(kind, i)
                e = bg.entry(section, key)
                item = lambda n: dict(name=n, found=bool(bg.file(n)))  # noqa: E731
                out["backgrounds"] = dict(section=section, key=key, names=[item(n) for n in (e.names if e else [])],
                                          won=[item(n) for n in (e.won if e else [])], can_save=bool(bg.user))
            return out

        def bg_check(self):
            """pics.cfg against the data and the files: keys that match no record, names that no file has, picture
            files that are not RGN (the game reads RGN only)."""
            bg.load()
            unknown, missing = [], []
            keys = {}
            for e in bg.entries():
                if e.section in backgrounds.RECORD_SECTIONS.values():
                    if e.section not in keys:
                        keys[e.section] = data.background_keys(e.section)
                    if e.key.lower() not in keys[e.section]:
                        like = difflib.get_close_matches(e.key, list(keys[e.section].values()), 3, 0.7) \
                            if e.section != "staff" else []
                        unknown.append(dict(section=e.section, key=e.key, like=like))
                for n in e.names + e.won:
                    if not bg.file(n):
                        missing.append(dict(section=e.section, key=e.key, name=n))
            other = [dict(file=os.path.basename(p), converted=bool(bg.file(os.path.splitext(os.path.basename(p))[0] + ".rgn")))
                     for f, p in sorted(bg.files().items())
                     if os.path.splitext(f)[1] in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg")]
            return dict(cfg=bg.cfg_path() or "", user=bg.user or "", unknown=unknown, missing=missing, other=other,
                        entries=sum(1 for _ in bg.entries()))

        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(url.query)
            arg = lambda k, d="": q.get(k, [d])[0]  # noqa: E731
            parts = url.path.strip("/").split("/")
            if url.path in ("/", "/index.html"):
                with open(os.path.join(HERE, "index.html"), "rb") as f:
                    return self.send(200, f.read(), "text/html; charset=utf-8")
            if url.path == "/api/info":
                return self.send(200, dict(data=data.folder.path, pictures=pictures.user or "",
                                           changed=len(model.changed), keys=model.keys is not None,
                                           tables=[dict(key=t.key, title=t.title) for t in model.tables.values()]))
            if parts[:2] == ["api", "list"] and len(parts) == 3 and parts[2] in model.tables:
                res = model.search(parts[2], arg("q"), max(0, int(arg("offset", "0") or 0)), PAGE_SIZE)
                for r in res["rows"]:
                    self.with_picture(parts[2], r["id"], r)
                return self.send(200, res)
            if parts[:2] == ["api", "pick"] and len(parts) == 3:
                return self.send(200, model.pick(parts[2], arg("q")))
            if parts[:2] == ["api", "rec"] and len(parts) == 4 and parts[2] in model.tables:
                i = int(parts[3]) if parts[3].lstrip("-").isdigit() else -1
                rec = model.record(parts[2], i)
                if not rec:
                    return self.send(404, {})
                return self.send(200, self.with_backgrounds(parts[2], i, self.with_picture(parts[2], i, rec)))
            if url.path == "/api/bg/picture":
                p = bg.file(arg("name"))
                if not p:
                    return self.send(404, {})
                b = open(p, "rb").read()
                if backgrounds.is_rgn(b):
                    return self.send(200, backgrounds.rgn_to_png(b, int(arg("scale", "2") or 2)), "image/png")
                return self.send(415, {})
            if url.path == "/api/bg/raw":
                p = bg.files().get(arg("file").lower())
                if not p:
                    return self.send(404, {})
                types = {".svg": "image/svg+xml", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                         ".png": "image/png", ".gif": "image/gif", ".bmp": "image/bmp"}
                return self.send(200, open(p, "rb").read(), types.get(os.path.splitext(p)[1].lower(), ""))
            if url.path == "/api/bg/check":
                return self.send(200, self.bg_check())
            if url.path == "/api/picture":
                p = pictures.path(arg("kind"), arg("name")) if arg("kind") in PICTURE_FOLDERS else None
                if not p or not os.path.isfile(p):
                    return self.send(404, {})
                with open(p, "rb") as f:
                    return self.send(200, f.read(), "image/png")
            if url.path == "/api/file":
                p = pictures.file(arg("kind"), arg("file")) if arg("kind") in PICTURE_FOLDERS else None
                if not p:
                    return self.send(404, {})
                types = {".svg": "image/svg+xml", ".webp": "image/webp", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                         ".png": "image/png", ".gif": "image/gif", ".bmp": "image/bmp"}
                with open(p, "rb") as f:
                    return self.send(200, f.read(), types.get(os.path.splitext(p)[1].lower(), "application/octet-stream"))
            if url.path == "/api/check":
                return self.send(200, self.check())
            return self.send(404, {})

        def check(self):
            """The files of badges/ and faces/: those the game shows, those that match no record, and those that
            are not PNG (the game reads PNG only)."""
            out = {}
            for kind in PICTURE_FOLDERS:
                names = data.picture_names(kind)
                files = pictures.files(kind)
                pngs = {os.path.splitext(f)[0] for f in files if f.lower().endswith(".png")}
                shown, unknown, other = 0, [], []
                for f in files:
                    base, ext = os.path.splitext(f)
                    if ext.lower() != ".png":
                        other.append(dict(file=f, converted=base in pngs))
                    elif base in names:
                        shown += 1
                    else:
                        unknown.append(dict(file=f, like=difflib.get_close_matches(base, names, 3, 0.6)))
                out[kind] = dict(folder=pictures.folder(kind) or "", shown=shown, unknown=unknown, other=other)
            return out

        def do_POST(self):
            url = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(url.query)
            parts = url.path.strip("/").split("/")
            if url.path == "/api/rename" and pictures.user:
                return self.rename(q)
            if parts[:2] == ["api", "bg"] and bg.user:
                return self.bg_post(parts[2] if len(parts) > 2 else "", q)
            if parts[:2] == ["api", "new"] and len(parts) == 4:
                try:
                    if parts[3] == "blank":
                        b = self.body()
                        i, err = model.add(parts[2], None, str(b.get("name", "")), str(b.get("second", "")),
                                           str(b.get("role", "player")))
                    else:
                        i, err = model.add(parts[2], int(parts[3]) if parts[3].isdigit() else -1)
                except ValueError as e:
                    i, err = None, str(e)
                return self.send(400, dict(error=err)) if err else self.send(200, dict(id=i))
            if parts[:2] in (["api", "rec"], ["api", "history"]) and len(parts) == 4:
                i = int(parts[3]) if parts[3].lstrip("-").isdigit() else -1
                try:
                    ch = self.body()
                except ValueError:
                    return self.send(400, dict(error="bad request"))
                if parts[1] == "rec":
                    err = model.apply(parts[2], i, ch)
                    return self.send(400, dict(error=err)) if err else self.send(200, dict(ok=True))
                err = model.apply_history(parts[2], i, ch)
                return self.send(400, dict(error=err)) if err else self.send(200, dict(ok=True))
            if url.path == "/api/save" and pictures.user:
                name = self.body().get("name", "")
                if not name or name.strip() != name or any(c in name for c in '/\\:*?"<>|') or name in (".", ".."):
                    return self.send(400, dict(error="give the new data set a name without / \\ : * ? \" < > |"))
                folder = os.path.join(pictures.user, "Databases", name)
                if os.path.exists(folder):
                    return self.send(409, dict(error="a data set of that name exists: give another name"))
                os.makedirs(os.path.dirname(folder), exist_ok=True)
                data.save(folder)
                return self.send(200, dict(saved=folder))
            if url.path != "/api/picture" or not pictures.user:
                return self.send(404, {})
            kind, name = q.get("kind", [""])[0], q.get("name", [""])[0]
            path = pictures.path(kind, name) if kind in PICTURE_FOLDERS else None
            size = int(self.headers.get("Content-Length", "0") or 0)
            if not path or size <= 0 or size > MAX_PICTURE:
                return self.send(400, dict(error="bad picture"))
            body = self.rfile.read(size)
            if not body.startswith(PNG_SIGNATURE):
                return self.send(400, dict(error="not a PNG"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path + ".part", "wb") as f:
                f.write(body)
            os.replace(path + ".part", path)
            return self.send(200, dict(saved=os.path.basename(path)))

        def bg_post(self, what, q):
            """add: a new picture (RGN body) for a record; remove: a name out of a record's line (the file stays);
            convert: an RGN made from a picture file that is not RGN, put in place of its name in pics.cfg;
            rekey: a key that matches no record gets the name of one."""
            arg = lambda k: q.get(k, [""])[0]  # noqa: E731
            bg.load()
            try:
                if what in ("add", "remove"):
                    kind, i = arg("kind"), int(arg("id") or -1)
                    section = backgrounds.RECORD_SECTIONS.get(kind)
                    if not section or not model.exists(kind, i):
                        return self.send(400, dict(error="no such record"))
                    key = data.background_key(kind, i)
                    e = bg.entry(section, key)
                    names, won = (list(e.names), list(e.won)) if e else ([], [])
                    target = won if arg("won") == "1" else names
                    if what == "add":
                        size = int(self.headers.get("Content-Length", "0") or 0)
                        if not 0 < size <= MAX_PICTURE:
                            return self.send(400, dict(error="bad picture"))
                        name = bg.new_name(key)
                        bg.write_file(name, self.rfile.read(size))
                        target.append(name)
                    elif arg("name") in target:
                        target.remove(arg("name"))
                    bg.set(section, e.key if e else key, names, won)
                    bg.save()
                    return self.send(200, dict(ok=True))
                if what == "convert":
                    old = arg("file")
                    size = int(self.headers.get("Content-Length", "0") or 0)
                    if not old or not 0 < size <= MAX_PICTURE:
                        return self.send(400, dict(error="bad picture"))
                    new = os.path.splitext(old)[0] + ".rgn"
                    if bg.file(new):
                        return self.send(409, dict(error="an RGN of that name exists"))
                    bg.write_file(new, self.rfile.read(size))
                    for e in bg.entries():
                        e.names = [new if n.lower() == old.lower() else n for n in e.names]
                        e.won = [new if n.lower() == old.lower() else n for n in e.won]
                    bg.save()
                    return self.send(200, dict(saved=new))
                if what == "rekey":
                    e = bg.entry(arg("section"), arg("key"))
                    if not e or arg("to").lower() not in data.background_keys(e.section):
                        return self.send(400, dict(error="no such record"))
                    into = bg.entry(e.section, arg("to"))
                    if into:                    # one line per key: the game takes the first that matches
                        bg.set(e.section, into.key, into.names + e.names, into.won + e.won)
                        bg.lines.remove(e)
                    else:
                        e.key = arg("to")
                    bg.save()
                    return self.send(200, dict(ok=True))
            except ValueError as err:
                return self.send(400, dict(error=str(err)))
            return self.send(404, {})

        def rename(self, q):
            """A PNG file of the folder gets the name of a record. Never over another file."""
            kind, old, new = (q.get(k, [""])[0] for k in ("kind", "file", "name"))
            if kind not in PICTURE_FOLDERS or new not in data.picture_names(kind):
                return self.send(400, dict(error="no such record"))
            src, dst = pictures.file(kind, old), pictures.path(kind, new)
            if not src or not src.lower().endswith(".png") or not dst:
                return self.send(400, dict(error="bad file"))
            if os.path.exists(dst):
                return self.send(409, dict(error="a file with that name exists"))
            os.rename(src, dst)
            return self.send(200, dict(saved=os.path.basename(dst)))

    return Handler


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("data", help="the game's Data folder")
    ap.add_argument("--user", "--pictures", dest="user", default="",
                    help="the game's user folder (saves, settings.txt, badges/, faces/, Databases/)")
    ap.add_argument("--port", type=int, default=8102)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    data = Data(os.path.abspath(a.data), os.path.abspath(a.user) if a.user else "")
    pictures = Pictures(os.path.abspath(a.user) if a.user else "")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(data, pictures))
    url = f"http://127.0.0.1:{a.port}/"
    print(f"editor: {data.folder.path}; {url}")
    if not a.no_browser:
        threading.Timer(0.5, webbrowser.open, (url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main(sys.argv[1:])
