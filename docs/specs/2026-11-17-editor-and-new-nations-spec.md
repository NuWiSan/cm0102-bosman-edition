# Editor for every system, and new playable nations (fork NuWiSan)

Status: editor slices 1 and 2a done (`tools/editor/`); the rest is research. Fork `NuWiSan/cm0102-bosman-edition`.

Two features that depend on each other: a database editor that runs on Linux, Mac and Windows, and new nations in the League table, Switzerland first. Upstream keeps "competition structure changes of any kind" out of 0.8.0, so both are fork work.

## Problem

1. The original's data editor is a separate Windows program. It is not part of this project and does not run on Linux or a Mac without Wine.
2. Switzerland is in the database (clubs, people, the Swiss Cup and National Division A history in the History tables, `docs/research/history-0.6.0/ger-aut-sui-lux.md`), but a new game cannot include a Swiss league. The function by function translation keeps the original's limits.

## Why a nation is not playable (what the research shows)

- The League table holds the 35 leagues that a new game can include (GLOSSARY). It is built in the program, not read from the data: `FUN_00667150`, 35 entries with a "playable" flag at +0x08 (`docs/research/2026-10-14-start-new-game-inventory.md`). The Select League(s) screen lists only those nations (`setup_build_select_leagues_screen` `0x81d010`, `menubar_list_league_nations` `0x7651e0`).
- Each league of the table has its own classes in the program: one source file per division and cup, such as `bel_first.cpp`, `swe_prm.cpp`, `eng_fa_cup.cpp` (`docs/research/function-map/`). They hold the fixtures, the table rules, promotion, relegation, play-offs and cup rounds. There is no `sui_*`, so Switzerland has no code.
- A nation that is not loaded gets no RulingBody (`discipline_rules_init` `0x55d420` builds one only when the nation byte +0x11c is set), and its clubs play only in the simulated groups of `SimulatedStats` `0x84b940`.
- Upstream already changes leagues at run time, but only inside nations that have code: new divisions reuse an existing class with new club counts (`tools/recomp/new_divisions.py`, `league_sizes.py`, `src/recomp_rt/win/season_divisions*.c`).

So a new nation needs: a new League table entry, league and cup objects for it, its RulingBody, and its rules. Data alone is not enough. Each address above is a lead to read before the code relies on it (CLAUDE.md).

## Solution, in three parts

### A. Editor (no game change)

A separate program that opens a database folder, shows and edits clubs, people, nations, competitions and contracts, and saves a new folder. The game already plays such a folder through the Custom database tile (0.6.0, Q254): an edited database is a Custom database (Q271).

- Base: `tools/seasons/own_db/cmdb.py` and `cmdb1.py` already read every table of `index.dat` and write a folder (`cmdb1.write_folder`). Row sizes, offsets and fields are in `docs/research/data-map/`.
- Form: a small local web app (Python server and a page in the browser). It runs the same on Linux, Mac and Windows with only Python.
- Look: retro, in the style of CM 01/02 and of its editor (`Editor/cm0102ed.exe` of the free release is the reference of the layout), cleaner.
- Pictures: the editor shows the pictures of every nation, club, competition, stadium and person: the background pictures of `pics.cfg` (sections nations, clubs, stadiums, comps, staff and the rest) and the fork's badges and faces. It says whether each picture is in the right folder with the right name, so that the game finds it. It takes PNG, SVG and WebP, shows a preview, and saves PNG with the right name for the record (badges, faces: see `2026-11-17-badges-and-faces-spec.md`) or the right `pics.cfg` line (backgrounds). It flags an SVG or WebP put in a picture folder by hand, which the game does not read, and offers to convert it.
- Power: it edits every field the original editor edits, and more, with search, filters, lists of many records at once and checks of the links.
- It never writes into the folder it opened: it saves a copy. It checks every table length and link before it saves, as `cmdb.table` does.

### B. Custom league in the game (the key piece)

One generic league object, configured by a file in the database folder, in place of a hand-written class per division:

- `leagues.txt` (name to agree): nation, divisions, clubs per division, rounds (2, 3 or 4 meetings), points, tie-breaks, promotion and relegation places, play-offs, a split after N rounds, and the cup's rounds.
- The game adds one League table entry per nation in the file, so Select League(s) lists it.
- The generic object is built on the code of an existing league that is close, read from the original, not written from nothing. The fixtures and the table come from that class; the file gives the numbers.
- A match in a custom league is played by the original's match engine. Only the competition frame is new.

### C. Switzerland as the first custom nation

- Super League: 12 clubs, 33 rounds, then a split into two groups of 6 for 5 more rounds (format since 2023/24, to confirm against the league's regulations). The Scottish Premier Division of the original also has 12 clubs and a split, so its classes are the first candidate to read as the base of B.
- Challenge League: 10 clubs, 4 meetings. The relegation play-off between the Super League's 11th and the Challenge League's 2nd. Direct promotion of the Challenge League's 1st and relegation of its 10th.
- Swiss Cup. Promotion League and lower tiers later, as background leagues first.
- Data: the Update Team databases hold Swiss clubs and players. The Helvetia Football data is a source for the Swiss divisions, through the editor.

## User stories

1. As a player on Linux or a Mac, I want to edit a database without Wine.
2. As a player, I want the editor to save a new folder that the Custom database tile plays.
3. As a player, I want to choose Switzerland in Select League(s) and manage a Swiss club with real promotion and relegation.
4. As a player, I want to add another nation with only a file and the editor.
5. As a player who does not choose a custom nation, I want the game to play as before, byte for byte.

## Proposals (not decided yet)

1. Order: A first (no game risk, useful at once), then B with Switzerland as its test (C).
2. The editor is a local web app in `tools/editor/`. An editor inside the game is not planned: the game's screens are 800x600 with the original's widgets, and every screen would be new code.
3. A custom league changes no rule of the 35 original leagues. With no `leagues.txt` the game is the original.
4. The fork may break the upstream rule "no change may alter the game's decisions" for custom nations only, because they are new. Saves with a custom nation say so in the save name.

## Open questions

- Q1: Which original class is the best base for B: Scotland (split) or another? (read the code)
- Q2: Can the League table grow past 35 without moving other tables in memory? (read `FUN_00667150` and its users)
- Q3: How do the European cups give places to a nation that the original's UEFA table does not hold? Proposed first step: a custom nation gets no European places; later from the coefficients file.

## Testing

- Editor: open, save with no change, and the saved folder equals the original byte for byte; edit one field and only that field changes; a broken link is refused.
- Custom league: the same-save runs and the smoke runs with no `leagues.txt` match main. A long test game with Switzerland to 2100: every season ends, the counts of clubs hold, promotion and relegation follow the file.

## Slices

### 1. Editor: read and show (clubs, people, nations), pictures
Done. `python3 tools/editor/editor.py <Data folder> --pictures <the game's user folder>` serves the page on `127.0.0.1:8102` and opens it. Clubs, people and nations with search; a record page per club and person; the pictures: each record's badge or face at the game's sizes, the file name that the game looks for (the game's own key: `Ashley Cole 20-12-1980`, checked against the game, also in a leap year), and a new picture from PNG, SVG, WebP or JPEG, made into a PNG by the page and saved under that name. The Pictures page counts the files that the game shows; a PNG file whose name matches no record gets up to three close record names to rename it to (never over another file); a file that is not PNG gets a button that converts it to a PNG of the same name (the original stays, marked as converted). The editor never deletes a file. Format 1 (3.9.68) and format 2 staff tables. The data folder is not written.
### 2a. Editor: edit people, save a new data set
Done. A person's page edits the first, second and common name (picked from the name tables), the birth date, the nation, the second nation and the club, and for a player the current and potential ability, the three reputations, the 12 position ratings, the 31 attributes and the other bytes of the player data that are not named yet. The changes stay in memory; Save as writes the whole data set into `<user folder>/Databases/<name>` (a new folder, `cmdb1.write_folder` with every file's length checked), which the game plays as a custom database. Checked: Finishing of Thierry Henry set from 19 to 15 and saved; a new game on that data set shows Finishing 15.

The player data, as the game reads it (`staff_compute_player_attribute` `0x543540`, jump table `0x543a94`; names `database_get_player_attribute_name` `0x5428a0`, table `0x543158`): current ability i16 at 5, potential at 7, three reputations i16 from 9, position ratings 0x0f to 0x1a (goalkeeper, sweeper, defender, defensive midfielder, midfielder, attacking midfielder, attacker, wing back, right, left, centre, free role), and the attributes 1 to 31: Acceleration 0x1b, Aggression 0x1c, Agility 0x1d, Anticipation 0x1e, Balance 0x1f, Bravery 0x20, Creativity 0x43, Crossing 0x23, Decisions 0x24, Determination (staff row 0x58), Dribbling 0x26, Finishing 0x27, Flair 0x28, Handling 0x2a, Heading 0x2b, Influence 0x2f, Jumping 0x2e, Long Shots 0x31, Marking 0x32, Off The Ball 0x33, Pace 0x36, Passing 0x37, Positioning 0x39, Reflexes 0x3a, Set Pieces 0x29, Stamina 0x3c, Strength 0x3d, Tackling 0x3e, Teamwork 0x3f, Technique 0x40, Work Rate 0x44. The data stores them as 1 to 20. A new game turns some into values relative to the current ability, and the game shows those from the current ability again (`0x543689`: v = (2 * raw + CA) / 20 + 10, shown (v + v * v / 10) / 3 + 0.5, from 1 to 20; a tenth of the CA for some goalkeeper cases), so its numbers can differ from the data's, as with the original editor. Not named yet: 0x21, 0x22, 0x25, 0x2c, 0x2d, 0x30, 0x34, 0x35, 0x38, 0x3b, 0x41, 0x42, 0x45.

### 2b. Editor: contracts, then clubs
Blocked by: 2a. The fields to find in the code first.
### 3. Read the original for B (Q1, Q2)
Blocked by: the build files.
### 4. Custom league with one division
Blocked by: 3.
### 5. Switzerland: Super League, Challenge League, play-off, cup
Blocked by: 4.
### 6. European places for custom nations
Blocked by: 5.
