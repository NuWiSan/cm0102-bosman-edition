"""The tables of the data that the editor edits: one layout per table, and the model that reads and writes them.

A layout is the list of fields of a row: offset, kind, range and, for a link, the table it points to. The page draws
every record from its layout, and every change goes through Field.write, so a table needs no code of its own.

Sources of the layouts (docs/specs/2026-11-17-editor-and-new-nations-spec.md has the table per table):
- the links (which offsets hold ids of which table): the load's id pass, ported in src/cm3/database.c (club_fields,
  nation_fields, ... with the FUN_ addresses of the original);
- the order and names of the plain fields: the field names of the original editor (strings of cm0102ed.exe, in the
  order of the rows), the value ranges of the 3.9.68 data, and the reads named per field below.
"""
import datetime
import struct

import cmdb
import cmdb1

NONE = -2                  # an empty link in most tables of the data
NONE1 = -1                 # an empty link in the histories, the club staff lists and the person's player rows

# The jobs, from database_get_job_name 0x53ad00 (jump table 0x53b384); 14 has no name there.
JOBS = {0: "Unemployed", 1: "Chairman", 2: "Managing Director", 3: "General Manager", 4: "Director Of Football",
        5: "Manager", 6: "Assistant Manager", 7: "Reserve Team Manager", 8: "Coach", 9: "Scout", 10: "Physio",
        11: "Player", 12: "Player/Manager", 13: "Player/Assistant Manager", 14: "(job 14)", 15: "Player/Coach",
        16: "Retired Player", 17: "Media Pundit"}
STATUSES = {0: "Unknown", 1: "Professional", 2: "Semi-Professional", 3: "Amateur"}
DAYS = {-1: "None", 0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday",
        6: "Sunday"}


class Field:
    """One field of a row. kind: text, int, float, ref, name, enum, flag, date, colour, staff (a link to a person)."""

    def __init__(self, key, label, off, kind="int", fmt="B", size=0, lo=None, hi=None, ref=None, choices=None,
                 none=NONE, row="main", note="", on=1, readonly=False, lock=None):
        self.key, self.label, self.off, self.kind, self.fmt, self.size = key, label, off, kind, fmt, size
        self.lo, self.hi, self.ref, self.choices, self.none, self.row = lo, hi, ref, choices, none, row
        self.note, self.on, self.readonly, self.lock = note, on, readonly, lock
        if kind in ("ref", "name", "colour", "staff"):
            self.fmt = "<i"
        if kind == "float":
            self.fmt = "<d"

    def read(self, r):
        if self.kind == "text":
            return cmdb.cstr(r, self.off, self.size)
        if self.kind == "date":
            d = cmdb1.to_date(*struct.unpack_from("<hH", r, self.off))
            return d.isoformat() if d else ""
        if self.kind == "flag":
            return struct.unpack_from(self.fmt, r, self.off)[0] != 0
        return struct.unpack_from(self.fmt, r, self.off)[0]

    def write(self, r, value, model):
        """Writes value (as the page sends it). Returns an error text or None. A link that is not changed stays as it
        is: the data holds ids of records that it lacks, which the game skips."""
        if self.readonly:
            return f"{self.label} cannot change"
        if self.kind == "text":
            b = str(value).encode("latin-1", "replace") if isinstance(value, str) else b""
            if str(value).encode("latin-1", "ignore") != b:
                return f"{self.label}: a letter that the game cannot show"
            if len(b) >= self.size:
                return f"{self.label}: at most {self.size - 1} letters"
            r[self.off:self.off + self.size] = b + bytes(self.size - len(b))
            return None
        if self.kind == "date":
            try:
                d = datetime.date.fromisoformat(value) if value else None
            except ValueError:
                return f"{self.label}: not a date"
            cmdb1.put_date(r, self.off, d)
            return None
        if self.kind == "flag":
            struct.pack_into(self.fmt, r, self.off, self.on if value else 0)
            return None
        if self.kind == "float":
            v = float(value)
            if (self.lo is not None and v < self.lo) or (self.hi is not None and v > self.hi):
                return f"{self.label} must be {self.lo} to {self.hi}"
            struct.pack_into("<d", r, self.off, v)
            return None
        v = int(value)
        if self.kind in ("ref", "name", "colour", "staff"):
            if v == struct.unpack_from("<i", r, self.off)[0]:
                return None
            if v < 0:
                v = self.none
            elif not model.exists(self.ref, v):
                return f"{self.label}: no such record"
        elif self.kind == "enum":
            if v not in self.choices:
                return f"{self.label}: no such value"
        else:
            lo, hi = self.range()
            if not lo <= v <= hi:
                return f"{self.label} must be {lo} to {hi}"
        struct.pack_into(self.fmt, r, self.off, v)
        return None

    def range(self):
        lo, hi = {"B": (0, 255), "b": (-128, 127), "<h": (-32768, 32767), "<H": (0, 65535),
                  "<i": (-2 ** 31, 2 ** 31 - 1)}[self.fmt]
        return (lo if self.lo is None else self.lo), (hi if self.hi is None else self.hi)


def F(*a, **k):
    return Field(*a, **k)


def refs(key, labels, off, ref, kind="ref", none=NONE, row="main"):
    return [Field(f"{key}.{i}", lab, off + 4 * i, kind, ref=ref, none=none, row=row) for i, lab in enumerate(labels)]


def numbered(label, n):
    return [f"{label} {i + 1}" for i in range(n)]


def attrs(names, off, row, lo=0, hi=20):
    """Byte attributes in a row, in order from off."""
    return [Field(n.lower().replace(" ", "_"), n, off + i, lo=lo, hi=hi, row=row) for i, n in enumerate(names) if n]


COLOURS6 = ["Home foreground", "Home background", "Away foreground", "Away background", "Third foreground",
            "Third background"]


class Table:
    def __init__(self, key, title, tids, size, sections, columns, picture=None, lock=None, name=None):
        self.key, self.title, self.tids, self.size, self.sections = key, title, tids, size, sections
        self.columns, self.picture, self.lock, self.name = columns, picture, lock, name

    def fields(self):
        return [f for _, fs in self.sections for f in fs]


# The club row (club.dat, nat_club.dat; 581 bytes). Status, balance, attendances, training: see the clubs section of
# the spec (0x460ec6, 0x5961d0, 0x85d52c, 0x461506). The staff lists 0xbf..0x1db follow the people (Model.move).
CLUB = Table("club", "Clubs", (0, 1), 581, [
    ("Club", [F("name", "Name", 4, "text", size=51, lock="club"), F("short", "Short name", 0x38, "text", size=26),
              F("nation", "Nation", 0x53, "ref", ref="nation"),
              F("division", "Division", 0x57, "ref", ref="comp",
                note="A league takes its clubs by this (0x56ecb0): one club more makes that league one club larger."),
              F("last_division", "Last division", 0x5B, "ref", ref="comp"),
              F("last_position", "Last position", 0x5F, hi=30),
              F("reserve_division", "Reserve division", 0x60, "ref", ref="comp"),
              F("status", "Status", 0x64, "enum", choices=STATUSES,
                note="An amateur club in a division that the game plays starts as semi-professional (0x596280)."),
              F("reputation", "Reputation", 0x80, fmt="<h", lo=1, hi=10000),
              F("plc", "PLC", 0x82, "flag", fmt="b", on=-1)]),
    ("Ground and finance", [F("stadium", "Stadium", 0x69, "ref", ref="stadium"),
                            F("owns_stadium", "Owns the stadium", 0x6D, "flag", fmt="b"),
                            F("reserve_stadium", "Reserve stadium", 0x6E, "ref", ref="stadium"),
                            F("match_day", "Match day", 0x72, "enum", fmt="b", choices=DAYS),
                            F("attendance", "Average attendance", 0x73, fmt="<i", lo=0, hi=200000),
                            F("min_attendance", "Minimum attendance", 0x77, fmt="<i", lo=0, hi=200000),
                            F("max_attendance", "Maximum attendance", 0x7B, fmt="<i", lo=0, hi=200000),
                            F("training", "Training facilities", 0x7F, lo=1, hi=20),
                            F("balance", "Bank balance (£)", 0x65, fmt="<i")]),
    ("Colours", [F(f"colours.{i}", lab, 0x83 + 4 * i, "colour", ref="colour") for i, lab in enumerate(COLOURS6)]),
    ("Rivals and people", refs("rivals", numbered("Rival", 3), 0xB3, "club")
     + refs("liked", numbered("Favourite person", 3), 0x9B, "person", "staff", NONE1)
     + refs("disliked", numbered("Disliked person", 3), 0xA7, "person", "staff", NONE1)),
], ["nation", "division", "reputation"], picture="badge", lock="club")

# The club's staff lists (read only: the person page moves people), as database_leave_club 0x53c190 uses them.
CLUB_STAFF = [("Chairman", 0xBF, 1), ("Directors", 0xC3, 3), ("Manager", 0xCF, 1), ("Assistant", 0xD3, 1),
              ("Squad", 0xD7, 50), ("Coaches", 0x19F, 5), ("Scouts", 0x1B3, 7), ("Physios", 0x1CF, 3)]
# The lists of each job (0x53c190, jump table 0x53c54c): 2..4 directors, 6 and 7 the assistant, 12, 13 and 15 a
# player who also holds a staff job.
JOB_LISTS = {1: ["Chairman"], 2: ["Directors"], 3: ["Directors"], 4: ["Directors"], 5: ["Manager"],
             6: ["Assistant"], 7: ["Assistant"], 8: ["Coaches"], 9: ["Scouts"], 10: ["Physios"], 11: ["Squad"],
             12: ["Manager", "Squad"], 13: ["Assistant", "Squad"], 15: ["Coaches", "Squad"]}

NATION = Table("nation", "Nations", (4,), 290, [
    ("Nation", [F("name", "Name", 4, "text", size=51, lock="nation"),
                F("short", "Short name", 0x38, "text", size=26,
                  note="The sort key of the nation lists."),
                F("code", "Three letter name", 0x53, "text", size=4),
                F("nationality", "Nationality", 0x57, "text", size=26),
                F("continent", "Continent", 0x71, "ref", ref="continent"),
                F("capital", "Capital city", 0x7A, "ref", ref="city"),
                F("stadium", "National stadium", 0x80, "ref", ref="stadium"),
                F("reputation", "Reputation", 0x8E, fmt="<h", lo=0, hi=10000)]),
    ("Football", [F("region", "Region", 0x75, fmt="b", lo=0), F("actual_region", "Actual region", 0x76, fmt="b", lo=0),
                  F("development", "State of development", 0x7E, fmt="b", lo=0, hi=3),
                  F("group", "Group membership", 0x7F, fmt="b", lo=0, hi=2),
                  F("importance", "Game importance", 0x84, fmt="b", lo=0, hi=4),
                  F("standard", "League standard", 0x85, fmt="b", lo=0, hi=20),
                  F("clubs", "Number of clubs", 0x86, fmt="<h", lo=0), F("staff", "Number of staff", 0x88, fmt="<i", lo=0),
                  F("language1", "First language", 0x77, fmt="b", lo=0),
                  F("language2", "Second language", 0x78, fmt="b", lo=0),
                  F("language3", "Third language", 0x79, fmt="b", lo=0)]),
    ("Colours", [F(f"colours.{i}", lab, 0x90 + 4 * i, "colour", ref="colour") for i, lab in enumerate(COLOURS6)]),
    ("Coefficients and rivals", [F("fifa", "FIFA coefficient", 0xA8, "float", lo=0)]
     + [F(f"fifa.{y}", f"FIFA coefficient {y}", 0xB0 + 8 * k, "float", lo=0) for k, y in enumerate(range(1991, 1997))]
     + [F(f"uefa.{y}", f"UEFA coefficient {y}", 0xE0 + 8 * k, "float", lo=0) for k, y in enumerate(range(1991, 1997))]
     + refs("rivals", numbered("Rival", 3), 0x110, "nation")),
], ["continent", "reputation"], lock="nation")

CONTINENT = Table("continent", "Continents", (3,), 198, [
    ("Continent", [F("name", "Name", 4, "text", size=26, lock="continent"),
                   F("code", "Three letter name", 0x1F, "text", size=4),
                   F("adjective", "Continentality", 0x23, "text", size=26),
                   F("federation", "Federation", 0x3D, "text", size=101),
                   F("federation_short", "Federation short name", 0xA3, "text", size=26),
                   F("strength", "Regional strength", 0xBE, "float", lo=0, hi=1)]),
], ["code", "federation_short"], lock="continent")

CITY = Table("city", "Cities", (21,), 56, [
    ("City", [F("name", "Name", 4, "text", size=26), F("nation", "Nation", 0x1F, "ref", ref="nation"),
              F("latitude", "Latitude", 0x23, "float", lo=-90, hi=90),
              F("longitude", "Longitude", 0x2B, "float", lo=-180, hi=180),
              F("attraction", "Attraction", 0x33, fmt="b", lo=0, hi=20),
              F("weather", "Weather (row of weather.cfg)", 0x34, fmt="<i", lo=-2)]),
], ["nation", "attraction"])

STADIUM = Table("stadium", "Stadiums", (5,), 78, [
    ("Stadium", [F("name", "Name", 4, "text", size=51), F("city", "City", 0x38, "ref", ref="city"),
                 F("capacity", "Capacity", 0x3C, fmt="<i", lo=0, hi=200000),
                 F("seating", "Seating capacity", 0x40, fmt="<i", lo=0, hi=200000),
                 F("expansion", "Expansion capacity", 0x44, fmt="<i", lo=0, hi=200000),
                 F("nearby", "Nearby stadium", 0x48, "ref", ref="stadium"),
                 F("covered", "Covered", 0x4C, "flag", fmt="b", on=-1),
                 F("heating", "Under-soil heating", 0x4D, "flag", fmt="b", on=-1)]),
], ["city", "capacity"])

COLOUR = Table("colour", "Colours", (2,), 58, [
    ("Colour", [F("name", "Name", 4, "text", size=51, lock="colour"), F("red", "Red", 0x37), F("green", "Green", 0x38),
                F("blue", "Blue", 0x39)]),
], ["red", "green", "blue"], lock="colour")

OFFICIAL = Table("official", "Officials", (7,), 43, [
    ("Official", [F("first", "First name", 4, "name", ref="first"), F("second", "Second name", 8, "name", ref="second"),
                  F("born", "Born", 0xC, "date"), F("nation", "Nation", 0x16, "ref", ref="nation"),
                  F("city", "City", 0x1A, "ref", ref="city"),
                  F("ca", "Current ability", 0x1E, fmt="<h", lo=0, hi=200),
                  F("pa", "Potential ability", 0x20, fmt="<h", lo=0, hi=200),
                  F("reputation", "Reputation", 0x22, fmt="<h", lo=0, hi=200)]),
    ("Attributes (0 to 20)", attrs(["Allowing Flow", "Discipline", "Important Matches", "Pressure", "Refereeing",
                                    "Running The Line", "Time Keeping"], 0x24, "main")),
], ["nation", "ca"])

COMP_FIELDS = [
    ("Competition", [F("name", "Name", 4, "text", size=51, lock="club_comp"),
                     F("short", "Short name", 0x38, "text", size=26), F("code", "Three letter name", 0x53, "text", size=4),
                     F("continent", "Continent", 0x59, "ref", ref="continent"),
                     F("nation", "Nation", 0x5D, "ref", ref="nation"),
                     F("reputation", "Reputation", 0x69, fmt="<h", lo=0, hi=20),
                     F("foreground", "Foreground colour", 0x61, "colour", ref="colour"),
                     F("background", "Background colour", 0x65, "colour", ref="colour")]),
]
COMP = Table("comp", "Club competitions", (12, 16), 107, COMP_FIELDS, ["nation", "continent", "reputation"],
             lock="club_comp")

STAFF_COMP = Table("staff_comp", "Awards", (11,), 101, [
    ("Award", [F("name", "Name", 4, "text", size=51, lock="staff_comp"), F("short", "Short name", 0x38, "text", size=26),
               F("continent", "Continent", 0x53, "ref", ref="continent"), F("nation", "Nation", 0x57, "ref", ref="nation"),
               F("reputation", "Reputation", 0x63, fmt="<h", lo=0, hi=20),
               F("foreground", "Foreground colour", 0x5B, "colour", ref="colour"),
               F("background", "Background colour", 0x5F, "colour", ref="colour")]),
], ["nation", "continent"], lock="staff_comp")

# The name tables (first_names.dat, second_names.dat, common_names.dat; 60 bytes): the text at 0, the id at 0x33.
NAME_SECTIONS = [("Name", [F("name", "Name", 0, "text", size=51), F("nation", "Nation", 0x37, "ref", ref="nation"),
                           F("count", "Count", 0x3B, readonly=True)])]
FIRST = Table("first", "First names", (13,), 60, NAME_SECTIONS, ["nation", "count"])
SECOND = Table("second", "Second names", (14,), 60, NAME_SECTIONS, ["nation", "count"])
COMMON = Table("common", "Common names", (15,), 60, NAME_SECTIONS, ["nation", "count"])

# The person: the staff row (table 6), and its player row (table 10) and non-player row (table 9) when it has them.
POSITIONS = ["Goalkeeper", "Sweeper", "Defender", "Defensive Midfielder", "Midfielder", "Attacking Midfielder",
             "Attacker", "Wing Back", "Right Side", "Left Side", "Centre", "Free Role"]
# Player attribute bytes 0x1b..0x44, in the order of the original editor's field names; the game's names where it
# shows them (0x5428a0): Creativity is Vision, Influence Leadership, Off The Ball Movement, Set Pieces Free Kicks.
PLAYER_ATTRIBUTES = ["Acceleration", "Aggression", "Agility", "Anticipation", "Balance", "Bravery", "Consistency",
                     "Corners", "Crossing", "Decisions", "Dirtiness", "Dribbling", "Finishing", "Flair", "Set Pieces",
                     "Handling", "Heading", "Important Matches", "Injury Proneness", "Jumping", "Influence",
                     "Left Foot", "Long Shots", "Marking", "Off The Ball", "Natural Fitness", "One On Ones", "Pace",
                     "Passing", "Penalties", "Positioning", "Reflexes", "Right Foot", "Stamina", "Strength",
                     "Tackling", "Teamwork", "Technique", "Throw Ins", "Versatility", "Creativity", "Work Rate"]
HIDDEN = {"Consistency", "Corners", "Dirtiness", "Important Matches", "Injury Proneness", "Left Foot",
          "Natural Fitness", "One On Ones", "Penalties", "Right Foot", "Throw Ins", "Versatility"}
# Non-player bytes 0x0e..0x22 in the order of the original editor's field names; the game reads the 12 it shows at
# these offsets (staff_compute_non_player_attribute 0x543fd0, jump table 0x5442b4; names 0x543b10).
NON_PLAYER_ATTRIBUTES = ["Attacking", "Business", "Coaching", "Coaching Goalkeepers", "Coaching Technique",
                         "Directness", "Discipline", "Free Roles", "Interference", "Judgement", "Judging Potential",
                         "Man Management", "Marking", "Motivating", "Offside", "Patience", "Physiotherapy", "Pressing",
                         "Resources", "Tactics", "Youngsters"]
FORMATIONS = {k: f"Formation {k}" for k in range(0, 9)}


def person_sections(fmt):
    prefs = [] if fmt != 1 else [("Likes and dislikes",
                                  refs("fav_clubs", numbered("Favourite club", 3), 0x61, "club")
                                  + refs("dis_clubs", numbered("Disliked club", 3), 0x6D, "club")
                                  + refs("fav_staff", numbered("Favourite person", 3), 0x79, "person", "staff")
                                  + refs("dis_staff", numbered("Disliked person", 3), 0x85, "person", "staff"))]
    return [
        ("Person", [F("first", "First name", 4, "name", ref="first"), F("second", "Second name", 8, "name", ref="second"),
                    F("common", "Common name", 0xC, "name", ref="common"), F("born", "Born", 0x10, "date"),
                    F("year", "Year of birth (no date)", 0x18, fmt="<H"),
                    F("nation", "Nation", 0x1A, "ref", ref="nation"),
                    F("nation2", "Second nation", 0x1E, "ref", ref="nation")]),
        ("Contract", [F("club", "Club", 0x39, "ref", ref="club", none=NONE1), F("job", "Job", 0x3D, "enum", choices=JOBS),
                      F("joined", "Joined", 0x3E, "date"), F("expires", "Expires", 0x46, "date"),
                      F("wage", "Wage (£ a week)", 0x4E, fmt="<i", lo=0),
                      F("value", "Value (£)", 0x52, fmt="<i", lo=0)]),
        ("International", [F("nat_club", "National team", 0x24, "ref", ref="club"),
                           F("nat_job", "Job", 0x28, "enum", choices=JOBS),
                           F("nat_joined", "Joined", 0x29, "date"), F("nat_expires", "Expires", 0x31, "date"),
                           F("caps", "Caps", 0x22), F("goals", "Goals", 0x23)]),
        ("Personal (0 to 20)", attrs(["Adaptability", "Ambition", "Determination", "Loyalty", "Pressure",
                                      "Professionalism", "Sportsmanship", "Temperament"], 0x56, "main")),
    ] + prefs + [
        ("Player", [F("squad_number", "Squad number", 4, hi=99, row="player"),
                    F("ca", "Current ability", 5, fmt="<h", lo=0, hi=200, row="player"),
                    F("pa", "Potential ability", 7, fmt="<h", lo=-10, hi=200, row="player",
                      note="-1, -2, -9 and -10 ask the game for a random potential."),
                    F("home_rep", "Home reputation", 9, fmt="<h", lo=0, hi=10000, row="player"),
                    F("current_rep", "Current reputation", 0xB, fmt="<h", lo=0, hi=10000, row="player"),
                    F("world_rep", "World reputation", 0xD, fmt="<h", lo=0, hi=10000, row="player")]),
        ("Positions (1 to 20)", attrs(POSITIONS, 0xF, "player", lo=1)),
        ("Attributes (0 to 20; 0 is random)", attrs([n if n not in HIDDEN else "" for n in PLAYER_ATTRIBUTES], 0x1B,
                                                    "player")),
        ("Hidden attributes (0 to 20)", attrs([n if n in HIDDEN else "" for n in PLAYER_ATTRIBUTES], 0x1B, "player")),
        ("Non-player", [F("np_ca", "Current ability", 4, fmt="<h", lo=-1, hi=200, row="np"),
                        F("np_pa", "Potential ability", 6, fmt="<h", lo=-10, hi=200, row="np"),
                        F("np_home_rep", "Home reputation", 8, fmt="<h", lo=0, hi=10000, row="np"),
                        F("np_current_rep", "Current reputation", 0xA, fmt="<h", lo=-1, hi=10000, row="np"),
                        F("np_world_rep", "World reputation", 0xC, fmt="<h", lo=-1, hi=10000, row="np"),
                        F("formation", "Preferred formation", 0x43, lo=0, hi=8, row="np")]),
        ("Non-player attributes (0 to 20)", attrs(NON_PLAYER_ATTRIBUTES, 0xE, "np")),
    ]


def person_table(fmt):
    return Table("person", "People", (6,), None, person_sections(fmt), ["born", "nation", "club"], picture="face")


# Histories: rows that belong to a record, edited on its page. (table, its tables, size, the field that names the
# owner, the fields)
HISTORIES = {
    "comp": ("History", (19, 20), 26, 4, [F("year", "Year", 8, fmt="<h", lo=0, hi=9999),
                                          F("winners", "Winners", 0xA, "ref", ref="club", none=NONE1),
                                          F("runners_up", "Runners-up", 0xE, "ref", ref="club", none=NONE1),
                                          F("third", "Third", 0x12, "ref", ref="club", none=NONE1),
                                          F("host", "Host", 0x16, "ref", ref="club", none=NONE1)]),
    "person": ("Career", (17,), 17, 4, [F("year", "Year", 8, fmt="<h", lo=0, hi=9999),
                                        F("club", "Club", 0xA, "ref", ref="club", none=NONE1),
                                        F("loan", "On loan", 0xE, "flag", fmt="b", on=-1),
                                        F("apps", "Apps", 0xF, lo=0, hi=127), F("goals", "Goals", 0x10, lo=0, hi=127)]),
    "staff_comp": ("History", (18,), 58, 4, [F("year", "Year", 8, fmt="<h", lo=0, hi=9999)]
                   + [F(f"{p}_{k}", f"{lab} {what}", o + 4 * j, "ref" if k == "staff" else "name",
                        ref={"first": "first", "second": "second", "staff": "person"}[k], none=NONE1)
                      for p, lab, o in (("winner", "Winner", 0xA), ("second", "Second", 0x1A), ("third", "Third", 0x2A))
                      for j, (k, what) in enumerate((("first", "first name"), ("second", "second name"),
                                                      ("staff", "person")))]),
}

TABLES = [CLUB, NATION, COMP, STAFF_COMP, STADIUM, CITY, CONTINENT, COLOUR, OFFICIAL, FIRST, SECOND, COMMON]


class Model:
    """The rows of a data folder, by table and id, and the changes made to them."""

    def __init__(self, folder, fmt, keys):
        """folder: cmdb1/cmdb Folder; fmt: the staff format (1 or 2); keys: {chain: {lower-case name: must}} of the key
        names (key_names.load), or None when the game file is not there."""
        self.folder, self.format, self.keys = folder, fmt, keys
        self.tables = {t.key: t for t in TABLES + [person_table(fmt)]}
        self.rows = {}
        for t in self.tables.values():
            idx = 0x33 if t.key in ("first", "second", "common") else 0
            self.rows[t.key] = {struct.unpack_from("<i", r, idx)[0]: r for tid in t.tids for r in folder.rows(tid)}
        self.links = {"player": (folder.rows(10), 0x91 if fmt == 1 else 0x61),
                      "np": (folder.rows(9), 0x99 if fmt == 1 else 0x69)}
        self.added = {}                    # table id: the rows added after the file's rows (Model.add)
        self.history_rows = {k: [r for tid in h[1] for r in folder.rows(tid)] for k, h in HISTORIES.items()}
        self.history_index = {}
        self.changed = set()
        self.names = {}                    # (kind, id): name, until the next change

    # ---- reading

    def exists(self, kind, i):
        return i in self.rows.get(kind, {})

    def row(self, kind, i, role="main"):
        r = self.rows[kind].get(i)
        if r is None or role == "main":
            return r
        if kind != "person":
            return None
        kind_bits = r[0x5F]
        if (role == "player" and not kind_bits & 2) or (role == "np" and not kind_bits & 1):
            return None
        rows, off = self.links[role]
        j = struct.unpack_from("<i", r, off)[0]
        return rows[j] if 0 <= j < len(rows) else None

    def name(self, kind, i):
        n = self.names.get((kind, i))
        if n is None:
            n = self.names[(kind, i)] = self.make_name(kind, i)
        return n

    def make_name(self, kind, i):
        r = self.rows.get(kind, {}).get(i)
        if r is None:
            return ""
        if kind in ("first", "second", "common"):
            return cmdb.cstr(r, 0, 51)
        if kind == "person":
            n = [self.name(t, struct.unpack_from("<i", r, o)[0]) for t, o in (("first", 4), ("second", 8), ("common", 0xC))]
            return n[2] or f"{n[0]} {n[1]}".strip()
        if kind == "official":
            return " ".join(self.name(t, struct.unpack_from("<i", r, o)[0]) for t, o in (("first", 4), ("second", 8)))
        t = self.tables[kind]
        f = next(f for f in t.fields() if f.key == "name")
        return f.read(r)

    def value(self, kind, i, f):
        """{value, text} of a field: text is what the page shows for a link, a list value or a colour."""
        r = self.row(kind, i, f.row)
        if r is None:
            return None
        v = f.read(r)
        out = dict(value=v)
        if f.kind in ("ref", "name", "staff"):
            out["text"] = self.name(f.ref, v)
        elif f.kind == "colour":
            c = self.rows["colour"].get(v)
            out["text"] = self.name("colour", v)
            out["rgb"] = "#%02x%02x%02x" % tuple(c[0x37:0x3A]) if c is not None else ""
        elif f.kind == "enum":
            out["text"] = f.choices.get(v, str(v))
        return out

    def locked(self, kind, i):
        """Why the name of the record cannot change, or None (see key_names)."""
        t = self.tables[kind]
        if not t.lock:
            return None
        if self.keys is None:
            return "the name cannot change: cm0102.exe is not next to the Data folder, so the key names are unknown"
        if self.name(kind, i).lower() in self.keys[t.lock]:
            return "the game finds this record by its name, so the name stays"
        return None

    def record(self, kind, i):
        t = self.tables[kind]
        if not self.exists(kind, i):
            return None
        sections = []
        for title, fields in t.sections:
            items = []
            for f in fields:
                v = self.value(kind, i, f)
                if v is None:
                    continue
                v.update(key=f.key, label=f.label, kind=f.kind, ref=f.ref, note=f.note,
                         readonly=f.readonly or bool(f.lock and self.locked(kind, i)))
                if f.kind == "enum":
                    v["choices"] = [[k, n] for k, n in f.choices.items()]
                if f.kind in ("int", "float"):
                    v["range"] = list(f.range()) if f.kind == "int" else [f.lo, f.hi]
                if f.kind == "text":
                    v["size"] = f.size - 1
                items.append(v)
            if items:
                sections.append(dict(title=title, fields=items))
        out = dict(kind=kind, id=i, name=self.name(kind, i), sections=sections, locked=self.locked(kind, i),
                   history=self.history(kind, i))
        if kind == "club":
            r = self.rows["club"][i]
            out["staff"] = [dict(title=title, people=[dict(id=p, name=self.name("person", p)) for p in
                                                       struct.unpack_from(f"<{n}i", r, o) if p >= 0])
                            for title, o, n in CLUB_STAFF]
        if kind == "colour":
            r = self.rows["colour"][i]
            out["rgb"] = "#%02x%02x%02x" % tuple(r[0x37:0x3A])
        return out

    def history(self, kind, i):
        if kind not in HISTORIES:
            return None
        title, _, _, owner, fields = HISTORIES[kind]
        if kind not in self.history_index:
            idx = {}
            for n, r in enumerate(self.history_rows[kind]):
                idx.setdefault(struct.unpack_from("<i", r, owner)[0], []).append(n)
            self.history_index[kind] = idx
        rows = []
        for n in self.history_index[kind].get(i, []):
            r = self.history_rows[kind][n]
            cells = []
            for f in fields:
                v = dict(value=f.read(r), key=f.key, kind=f.kind, ref=f.ref)
                if f.kind in ("ref", "name"):
                    v["text"] = self.name(f.ref, v["value"])
                cells.append(v)
            rows.append(dict(row=n, cells=cells))
        rows.sort(key=lambda x: -x["cells"][0]["value"])
        return dict(title=title, columns=[f.label for f in fields], rows=rows)

    def search(self, kind, q, offset, size):
        t = self.tables[kind]
        q = q.strip().lower()
        found = []
        for i in self.rows[kind]:
            n = self.name(kind, i)
            if n and (not q or q in n.lower()):
                found.append((n.lower(), i, n))
        found.sort()
        fields = {f.key: f for f in t.fields()}
        rows = []
        for _, i, n in found[offset:offset + size]:
            cols = []
            for c in t.columns:
                v = self.value(kind, i, fields[c])
                cols.append("" if v is None else v.get("text", v["value"]))
            rows.append(dict(id=i, name=n, cols=cols))
        return dict(total=len(found), offset=offset, rows=rows,
                    head=[fields[c].label for c in t.columns])

    def pick(self, kind, q, limit=50):
        """Records whose name starts with q, then those that hold it, for a link field."""
        q = q.strip().lower()
        if not q:
            return []
        first, rest = [], []
        for i in self.rows.get(kind, {}):
            n = self.name(kind, i)
            low = n.lower()
            if low.startswith(q):
                first.append((low, i, n))
            elif q in low and len(rest) < 500:
                rest.append((low, i, n))
        return [dict(id=i, name=n) for _, i, n in (sorted(first) + sorted(rest))[:limit]]

    # ---- writing

    def apply(self, kind, i, changes):
        """Writes {field key: value} into the record. Returns an error text or None; on an error nothing is
        written."""
        t = self.tables.get(kind)
        if t is None or not self.exists(kind, i):
            return "no such record"
        fields = {f.key: f for f in t.fields()}
        rows = {role: self.row(kind, i, role) for role in ("main", "player", "np")}
        saved = {role: bytes(r) for role, r in rows.items() if r is not None}
        before = self.staff_jobs(i) if kind == "person" else None
        for key, v in changes.items():
            f = fields.get(key)
            if f is None or rows.get(f.row) is None:
                return self.undo(rows, saved, f"no field {key}")
            if f.key == "name" and str(v) != f.read(rows["main"]):
                if err := self.locked(kind, i):
                    return self.undo(rows, saved, err)
                if t.lock and str(v).lower() in self.keys[t.lock]:
                    return self.undo(rows, saved, "the game finds a record by that name: pick another name")
            try:
                err = f.write(rows[f.row], v, self)
            except (TypeError, ValueError):
                err = f"{f.label}: not a value"
            if err:
                return self.undo(rows, saved, err)
        if kind == "person" and (err := self.move(i, before)):
            return self.undo(rows, saved, err)
        self.changed.add((kind, i))
        self.names.clear()
        return None

    def undo(self, rows, saved, err):
        for role, b in saved.items():
            rows[role][:] = b
        return err

    def apply_history(self, kind, n, changes):
        if kind not in HISTORIES or not 0 <= n < len(self.history_rows[kind]):
            return "no such row"
        r = self.history_rows[kind][n]
        saved = bytes(r)
        fields = {f.key: f for f in HISTORIES[kind][4]}
        for key, v in changes.items():
            f = fields.get(key)
            err = f"no field {key}" if f is None else None
            if not err:
                try:
                    err = f.write(r, v, self)
                except (TypeError, ValueError):
                    err = f"{f.label}: not a value"
            if err:
                r[:] = saved
                return err
        self.changed.add((kind + "_history", n))
        self.names.clear()
        return None

    # ---- the club staff lists follow the people

    def staff_jobs(self, pid):
        r = self.rows["person"][pid]
        return [(struct.unpack_from("<i", r, 0x39)[0], r[0x3D]), (struct.unpack_from("<i", r, 0x24)[0], r[0x28])]

    def move(self, pid, before):
        """After a change of club, national team or job: takes the person out of the lists of the old club and puts
        them in the lists of the new one, as database_leave_club 0x53c190 and database_add_staff_to_club 0x53bd10
        keep them (the club's lists are the master at a new game: create_game sets the person's club from them)."""
        clubs = self.rows["club"]
        touched = {c for pair in zip(before, self.staff_jobs(pid)) for c, _ in pair if c in clubs}
        saved = {c: bytes(clubs[c]) for c in touched}
        for (old_club, old_job), (club, job) in zip(before, self.staff_jobs(pid)):
            if (old_club, old_job) == (club, job):
                continue
            if old_club in clubs:
                self.leave(clubs[old_club], pid)
            if club in clubs and (err := self.join(clubs[club], pid, job)):
                for c, b in saved.items():
                    clubs[c][:] = b
                return err
        return None

    def leave(self, r, pid):
        for _, o, n in CLUB_STAFF:
            for k in range(n):
                if struct.unpack_from("<i", r, o + 4 * k)[0] == pid:
                    struct.pack_into("<i", r, o + 4 * k, NONE1)

    def join(self, r, pid, job):
        self.leave(r, pid)
        lists = {title: (o, n) for title, o, n in CLUB_STAFF}
        for title in JOB_LISTS.get(job, []):
            o, n = lists[title]
            slots = [k for k in range(n) if struct.unpack_from("<i", r, o + 4 * k)[0] < 0]
            if not slots:
                return f"the club has no free place in its {title.lower()} list ({n})" if n > 1 else f"the club already has a {title.lower()}"
            struct.pack_into("<i", r, o + 4 * slots[0], pid)
        return None


    # ---- new records (beyond the original editor)

    def count(self, tid):
        return self.folder.idx[tid]["count"] + len(self.added.get(tid, []))

    def append(self, tid, row):
        self.added.setdefault(tid, []).append(row)
        return row

    def add(self, kind, template):
        """A new record, a copy of the record template with the next id. Returns (id, None) or (None, error).
        The ids equal the rows, so a new club takes the first national team's id and the national teams move up
        by one, with every link to them (the club links of the load's id pass: club rivals, person club and
        national team, likes, career and comp history)."""
        t = self.tables.get(kind)
        if t is None or not self.exists(kind, template):
            return None, "no such record"
        if kind not in ("club", "person", "stadium", "city", "official", "first", "second", "common"):
            return None, "new records of this table are not supported"
        src = self.rows[kind][template]
        if kind == "club" and template >= self.folder.idx[0]["count"] + len(self.added.get(0, [])):
            return None, "a new national team needs a new nation"
        row = bytearray(src)
        if kind == "club":
            i = self.count(0)
            self.shift_national_teams(i)
            struct.pack_into("<i", row, 0, i)
            for _, o, n in CLUB_STAFF:                      # a new club has no people yet
                struct.pack_into(f"<{n}i", row, o, *([NONE1] * n))
            for o in (0x57, 0x5B, 0x60):                     # and plays in no division: a league takes its clubs
                struct.pack_into("<i", row, o, NONE)          # by the division (0x56ecb0)
            self.append(0, row)
        elif kind == "person":
            i = self.count(6)
            struct.pack_into("<i", row, 0, i)
            struct.pack_into("<i", row, 0x39, NONE1)
            struct.pack_into("<i", row, 0x24, NONE)
            row[0x3D] = 0
            row[0x28] = 0
            for role, tid in (("player", 10), ("np", 9)):
                r = self.row(kind, template, role)
                off = self.links[role][1]
                if r is None:
                    struct.pack_into("<i", row, off, NONE1)
                    continue
                j = self.count(tid)
                link = bytearray(r)
                struct.pack_into("<i", link, 0, j)
                self.links[role][0].append(self.append(tid, link))
                struct.pack_into("<i", row, off, j)
            self.append(6, row)
        else:
            tid = t.tids[0]
            i = self.count(tid)
            struct.pack_into("<i", row, 0x33 if kind in ("first", "second", "common") else 0, i)
            self.append(tid, row)
        self.rows[kind][i] = row
        if kind not in ("person", "first", "second", "common"):
            name = next(f for f in t.fields() if f.key == "name")
            text = (name.read(row) + " (new)")[:name.size - 1]
            row[name.off:name.off + name.size] = text.encode("latin-1") + bytes(name.size - len(text))
        self.changed.add((kind, i))
        self.names.clear()
        return i, None

    def shift_national_teams(self, first):
        """The national teams (ids from first) move up by one id, and every club link to them."""
        clubs = self.rows["club"]
        moved = {i: r for i, r in clubs.items() if i >= first}
        for i in sorted(moved, reverse=True):
            del clubs[i]
        for i, r in moved.items():
            struct.pack_into("<i", r, 0, i + 1)
            clubs[i + 1] = r
        fix = lambda r, o: struct.pack_into("<i", r, o, struct.unpack_from("<i", r, o)[0] + 1) \
            if struct.unpack_from("<i", r, o)[0] >= first else None  # noqa: E731
        for kind, t in self.tables.items():
            for f in t.fields():
                if f.ref == "club" and f.row == "main":
                    for r in self.rows[kind].values():
                        fix(r, f.off)
        for kind, (_, _, _, _, fields) in HISTORIES.items():
            for f in fields:
                if f.ref == "club":
                    for r in self.history_rows[kind]:
                        fix(r, f.off)
        self.history_index.clear()

    def write(self, path, write_folder):
        """Writes the data set into the new folder path: the files, each table followed by its added rows, and
        index.dat with the new counts and offsets."""
        F = self.folder
        files = {}
        idx = bytearray(F.raw["index.dat"])
        for name, b in F.raw.items():
            if name == "index.dat":
                continue
            tables = sorted((e["off"], tid) for tid, e in F.idx.items() if e["file"] == name)
            out, at = bytearray(), 0
            for off, tid in tables:
                e = F.idx[tid]
                size = len(F.rows(tid)[0]) if e["count"] else (157 if tid == 6 and self.format == 1 else 0)
                end = off + e["count"] * size if e["count"] else off
                out += b[at:off]
                struct.pack_into("<i", idx, e["pos"] + 0x3B, len(out))
                out += b[off:end]
                for r in self.added.get(tid, []):
                    out += r
                struct.pack_into("<i", idx, e["pos"] + 0x37, e["count"] + len(self.added.get(tid, [])))
                at = end
            out += b[at:]
            files[name] = out
        files["index.dat"] = idx
        write_folder(files, path)
