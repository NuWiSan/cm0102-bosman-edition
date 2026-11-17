#!/usr/bin/env python3
"""The database editor of the fork NuWiSan (spec docs/specs/2026-11-17-editor-and-new-nations-spec.md).

A small local web app: this server reads a data folder and serves a page for the browser. It runs the same on
Linux, Mac and Windows with Python 3 alone.

    python3 tools/editor/editor.py <data folder> [--pictures <user folder>] [--port 8102]

<data folder> is a game's Data folder (index.dat and the .dat files). --pictures is the game's user folder, the
one with the saves and the settings.txt; the badges and faces live in its folders badges/ and faces/. The
server listens on 127.0.0.1 only and opens the page in the browser.

This slice reads and shows clubs, nations and people, and manages the pictures: it shows each record's badge or
face, says the file name that the game looks for, and saves a picture (PNG, made by the page from PNG, SVG, WebP
or JPEG) under that name. On the Pictures page it converts the picture files that are not PNG and renames the PNG
files whose name matches no record. It never deletes a file. The data folder is not written.
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

PICTURE_FOLDERS = {"badge": "badges", "face": "faces"}
MAX_PICTURE = 8 * 1024 * 1024
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PAGE_SIZE = 200


def file_name(text):
    """A name of the game (Latin-1 text) as the game makes a picture file name (pictures.c put_name): '_' for a
    character that a file name cannot hold."""
    return "".join("_" if c in '/\\:*?"<>|' or ord(c) < 0x20 else c for c in text)


class Data:
    """The records of a data folder that the editor shows."""

    def __init__(self, path):
        fmt = cmdb1.staff_format(path)
        self.folder = cmdb1.open_folder(path) if fmt == 1 else cmdb.Folder(path)
        F = self.folder
        self.nations = {}
        for r in F.rows(4):
            i = struct.unpack_from("<i", r, 0)[0]
            self.nations[i] = dict(id=i, name=cmdb.cstr(r, 4, 51), short=cmdb.cstr(r, 0x38, 26))
        self.clubs = {}
        for t in (0, 1):
            for r in F.rows(t):
                i, nation = struct.unpack_from("<i", r, 0)[0], struct.unpack_from("<i", r, 0x53)[0]
                self.clubs[i] = dict(id=i, name=cmdb.cstr(r, 4, 51), short=cmdb.cstr(r, 0x38, 26), nation=nation,
                                     national=t == 1)
        staff, _ = (cmdb1 if fmt == 1 else cmdb).staff_view(F)
        self.people = {}
        for s in staff:
            if not (s["first"] or s["second"] or s["common"]):
                continue
            born = cmdb1.to_date(*s["dob"]) if s["dob"][1] > cmdb1.NO_DATE_YEAR else None
            self.people[s["id"]] = dict(id=s["id"], first=s["first"], second=s["second"], common=s["common"],
                                        born=born.isoformat() if born else "", dob=list(s["dob"]),
                                        nation=s["nation"], club=s["club"],
                                        player=bool(s["kind"] & 2), staff=bool(s["kind"] & 1))
        for p in self.people.values():
            p["name"] = p["common"] or f"{p['first']} {p['second']}".strip()

    def badge_name(self, club):
        return file_name(club["name"])

    def face_name(self, person):
        """The game's key (pictures_person_name): first and second name, '_' for a missing one, and the birth date
        d-m-yyyy as the game's date functions give it from the stored day of the year (the common-year table, also
        in a leap year: "Ashley Cole 20-12-1980") and year, also for a person with no date."""
        day, year = person["dob"]
        day = min(max(day, 0), 364)
        m = max(i for i in range(12) if cmdb1.CUM[i] <= day)
        return file_name(f"{person['first'] or '_'} {person['second'] or '_'} {day - cmdb1.CUM[m] + 1}-{m + 1}-{year}")


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


def search(records, q, fields, offset):
    q = q.strip().lower()
    found = [r for r in records if not q or any(q in str(r.get(f, "")).lower() for f in fields)]
    found.sort(key=lambda r: r["name"].lower())
    return dict(total=len(found), offset=offset, rows=found[offset:offset + PAGE_SIZE])


def make_handler(data, pictures):
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

        def club_view(self, c):
            v = dict(c)
            v["nation_name"] = data.nations.get(c["nation"], {}).get("name", "")
            v["picture"] = data.badge_name(c)
            v["has_picture"] = pictures.exists("badge", v["picture"])
            return v

        def person_view(self, p):
            v = dict(p)
            v["nation_name"] = data.nations.get(p["nation"], {}).get("name", "")
            v["club_name"] = data.clubs.get(p["club"], {}).get("name", "")
            v["picture"] = data.face_name(p)
            v["has_picture"] = pictures.exists("face", v["picture"])
            return v

        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(url.query)
            arg = lambda k, d="": q.get(k, [d])[0]  # noqa: E731
            offset = max(0, int(arg("offset", "0") or 0))
            if url.path in ("/", "/index.html"):
                with open(os.path.join(HERE, "index.html"), "rb") as f:
                    return self.send(200, f.read(), "text/html; charset=utf-8")
            if url.path == "/api/info":
                return self.send(200, dict(data=data.folder.path, pictures=pictures.user or "",
                                           clubs=len(data.clubs), nations=len(data.nations),
                                           people=len(data.people)))
            if url.path == "/api/clubs":
                res = search(data.clubs.values(), arg("q"), ("name", "short"), offset)
                res["rows"] = [self.club_view(c) for c in res["rows"]]
                return self.send(200, res)
            if url.path == "/api/nations":
                return self.send(200, search(data.nations.values(), arg("q"), ("name", "short"), offset))
            if url.path == "/api/people":
                res = search(data.people.values(), arg("q"), ("name", "first", "second", "common"), offset)
                res["rows"] = [self.person_view(p) for p in res["rows"]]
                return self.send(200, res)
            if url.path.startswith("/api/club/"):
                c = data.clubs.get(int(url.path.rsplit("/", 1)[1] or -1))
                return self.send(200, self.club_view(c)) if c else self.send(404, {})
            if url.path.startswith("/api/person/"):
                p = data.people.get(int(url.path.rsplit("/", 1)[1] or -1))
                return self.send(200, self.person_view(p)) if p else self.send(404, {})
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
                names = self.names(kind)
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

        def names(self, kind):
            if kind == "badge":
                return {data.badge_name(c) for c in data.clubs.values()}
            return {data.face_name(p) for p in data.people.values()}

        def do_POST(self):
            url = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(url.query)
            if url.path == "/api/rename" and pictures.user:
                return self.rename(q)
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

        def rename(self, q):
            """A PNG file of the folder gets the name of a record. Never over another file."""
            kind, old, new = (q.get(k, [""])[0] for k in ("kind", "file", "name"))
            if kind not in PICTURE_FOLDERS or new not in self.names(kind):
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
    ap.add_argument("--pictures", default="", help="the game's user folder (badges/ and faces/)")
    ap.add_argument("--port", type=int, default=8102)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    data = Data(os.path.abspath(a.data))
    pictures = Pictures(os.path.abspath(a.pictures) if a.pictures else "")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(data, pictures))
    url = f"http://127.0.0.1:{a.port}/"
    print(f"editor: {len(data.clubs)} clubs, {len(data.nations)} nations, {len(data.people)} people; {url}")
    if not a.no_browser:
        threading.Timer(0.5, webbrowser.open, (url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main(sys.argv[1:])
