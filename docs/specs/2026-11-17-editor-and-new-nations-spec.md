# Editor for every system, and new playable nations (fork NuWiSan)

Status: editor slices 1, 2, 2b and 2c done (`tools/editor/`); the rest is research. Fork `NuWiSan/cm0102-bosman-edition`.

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
### 2. Editor: every table of the original editor
Done. The editor edits the tables that the original editor (`Editor/cm0102ed.exe`) edits: clubs, people, nations, club competitions (club and nation comps), awards (staff comps), stadiums, cities, continents, colours, officials, the three name tables, and the histories (club comp and nation comp history on the competition page, the career on the person page, the award winners on the award page). The changes stay in memory; Save as writes the whole data set into `<user folder>/Databases/<name>` (a new folder, `cmdb1.write_folder` with every file's length checked), which the game plays as a custom database. Opened and saved with no change, the folder equals the original byte for byte; one change changes only its bytes.

`tools/editor/records.py` holds one layout per table (offset, kind, range, and for a link its table), and the page draws every record from it. Sources of the layouts:
- The links: the load's id pass, ported in `src/cm3/database.c` (`club_fields`, `nation_fields` and the others, with the `FUN_` addresses of the original). It names every offset that holds an id, and its table.
- The order and names of the other fields: the field names of the original editor (strings of `cm0102ed.exe`), which follow the order of the row, and the values of the 3.9.68 data. The reads named below confirm the order where the game shows the field.
- The ids equal the rows in every table (club and nation comp ids, and national team ids, follow on from the first table). Name ids are at 0x33 of the name rows.

| Table (file) | Row | Fields |
|---|---|---|
| Club (`club.dat`, `nat_club.dat`) | 581 | name 4 (51), short name 0x38 (26), nation 0x53, division 0x57, last division 0x5b, last position 0x5f, reserve division 0x60, status 0x64, bank balance 0x65, stadium 0x69, owns the stadium 0x6d, reserve stadium 0x6e, match day 0x72, attendances 0x73/0x77/0x7b, training facilities 0x7f, reputation 0x80, PLC 0x82, six colours 0x83, favourite and disliked people 0x9b/0xa7, rivals 0xb3, chairman 0xbf, directors 0xc3, manager 0xcf, assistant 0xd3, squad 0xd7 (50), coaches 0x19f (5), scouts 0x1b3 (7), physios 0x1cf (3) |
| Person (`staff.dat`, table 6) | 157 | names 4/8/0xc (name ids), born 0x10, year of birth 0x18, nation 0x1a, second nation 0x1e, caps 0x22, goals 0x23, national team 0x24, its job 0x28, joined 0x29, expires 0x31, club 0x39, job 0x3d, joined 0x3e, expires 0x46, wage 0x4e, value 0x52, personal attributes 0x56..0x5d, kind of row 0x5f (2 player, 1 non-player), favourite and disliked clubs 0x61/0x6d, favourite and disliked people 0x79/0x85, player row 0x91, non-player row 0x99 |
| Player (`staff.dat`, table 10) | 70 | squad number 4, current and potential ability 5/7, home, current and world reputation 9/0xb/0xd, 12 positions 0xf, 42 attributes 0x1b..0x44 |
| Non-player (`staff.dat`, table 9) | 68 | current and potential ability 4/6, three reputations 8/0xa/0xc, 21 attributes 0xe..0x22, preferred formation 0x43 |
| Nation (`nation.dat`) | 290 | name 4, short name 0x38, three letter name 0x53, nationality 0x57, continent 0x71, region 0x75, actual region 0x76, three languages 0x77, capital 0x7a, state of development 0x7e, group membership 0x7f, national stadium 0x80, game importance 0x84, league standard 0x85, number of clubs 0x86, of staff 0x88, reputation 0x8e, six colours 0x90, FIFA coefficients 0xa8..0xd8, UEFA coefficients 0xe0..0x108, rivals 0x110 |
| Club and nation comp (`club_comp.dat`, `nation_comp.dat`) | 107 | name 4, short name 0x38, three letter name 0x53, continent 0x59, nation 0x5d, two colours 0x61, reputation 0x69 |
| Award (`staff_comp.dat`) | 101 | name 4, short name 0x38, continent 0x53, nation 0x57, two colours 0x5b, reputation 0x63 |
| Stadium (`stadium.dat`) | 78 | name 4, city 0x38, capacity 0x3c, seating 0x40, expansion 0x44, nearby stadium 0x48, covered 0x4c, under-soil heating 0x4d |
| City (`city.dat`) | 56 | name 4 (26), nation 0x1f, latitude 0x23, longitude 0x2b (doubles), attraction 0x33, weather 0x34 (a row of `weather.cfg`) |
| Continent (`continent.dat`) | 198 | name 4 (26), three letter name 0x1f, continentality 0x23, federation 0x3d (101), its short name 0xa3, regional strength 0xbe (double) |
| Colour (`colour.dat`) | 58 | name 4, red, green, blue 0x37..0x39 |
| Official (`officials.dat`) | 43 | names 4/8, born 0xc, nation 0x16, city 0x1a, current and potential ability 0x1e/0x20, reputation 0x22, seven attributes 0x24..0x2a |
| Name (`first_names.dat` and the others) | 60 | name 0, id 0x33, nation 0x37, count 0x3b |
| Comp history (`club_comp_history.dat`, `nation_comp_history.dat`) | 26 | comp 4, year 8, winners 0xa, runners-up 0xe, third 0x12, host 0x16 |
| Career (`staff_history.dat`) | 17 | person 4, year 8, club 0xa, on loan 0xe, apps 0xf, goals 0x10 |
| Award history (`staff_comp_history.dat`) | 58 | award 4, year 8, then winner, second and third: first name, second name, person and a value each, from 0xa, 0x1a and 0x2a |

Reads that confirm the plain fields:
- Club: status (the info tab `0x460ec6`; `Finance::init_for_club` makes an amateur club of a division that the game plays semi-professional, `0x596280`), balance (`0x5961d0`), attendances (the crowd estimate `0x85d52c`), training facilities (the info tab's Training Ground text `0x461506`).
- Player: the attributes that the profile shows (`staff_compute_player_attribute` `0x543540`, jump table `0x543a94`; names `0x5428a0`); the profile shows some relative to the current ability after a new game (`0x543689`), as with the original editor. In the data 0 means random (the original editor's hint "0 (random) - 20 (best)").
- Personal attributes: adaptability and determination (`0x543fd0`), ambition (deserved squad status `0x4ca4ee`), loyalty and temperament (`staff_fade_staff_relationships` `0x547fb0`, `0x548016`), professionalism (`game_check_players_missing_training` `0x5d6b7e`, `AWOL::daily_update` `0x4191fc`).
- Non-player: the 12 attributes that the game shows (`staff_compute_non_player_attribute` `0x543fd0`, jump table `0x5442b4`; names `0x543b10`) are at the offsets of the alphabetical order.
- The jobs 0 to 17: `database_get_job_name` `0x53ad00` (jump table `0x53b384`).

Rules that the editor keeps:
- Key names: at the load the game finds some clubs, nations, comps, awards, colours and continents by name (`match_club_key_id` `0x6146b0` for the clubs, `_stricmp` `0x951c50`) and keeps their rows in key ids; a key id that stays unset stops the load with the box "index.cpp 5809" (`report_missing_key_id` `0x60d780`). So the name of such a record cannot change, and no record takes such a name. The editor reads the names from the player's `cm0102.exe` next to the Data folder, through `src/cm3/key_ids_table.c`; with no exe, these names cannot change.
- The club's staff lists are the master at a new game (create_game sets the person's club from them, `docs/research/2026-10-19-club-table-users.md`). When a person's club, national team or job changes, the editor takes the person out of the old club's lists and puts them in the new club's lists of the job, as `database_leave_club` `0x53c190` (jump table `0x53c54c`) and `database_add_staff_to_club` `0x53bd10` do: 1 chairman, 2 to 4 directors, 5 manager, 6 and 7 assistant, 8 coaches, 9 scouts, 10 physios, 11 squad, 12 manager and squad, 13 assistant and squad, 15 coaches and squad. A full list refuses the change.
- A link that is not changed keeps its id: the data holds ids of records that the data set lacks. An emptied link gets the data's empty value (-2, or -1 in the histories and the person lists).
- Not edited: the kind of a person's row (it needs a player or non-player row), staff byte 0x5e (flags: `0x4842b6` tests the value 2, `0x487b46` the value 4), player byte 0x45 (2 in every row of the data), the non-player links 0x23 (eight person ids), and the club fields that the game sets at a new game (0x1db, 0x1df, 0x1e0, 0x230, 0x244).

Checked in a new game on saved data sets:
- Thierry Henry: Finishing 15, Determination 7, Left Foot 1 (Preferred Foot "Right Only"), wage 25,000, expires 30.6.2006, 40 caps, all shown. Moved to Chelsea: he is in Chelsea's squad and not in Arsenal's.
- Arsenal: Amateur (shown Semi-Professional, as above), stadium Wembley (Wembley, London, 78000), training facilities 3 (Awful facilities), balance -5,000,000 (Finances Ok), home background colour Blue 1 (the club heading is blue). Renaming Aston Villa stops the load at index.cpp 5809, so the editor refuses it.
- The city London renamed: the info tab shows "Highbury, London Test". France's nationality renamed: the profile of a French player shows it. The English Premier Division's short name renamed: the club screen's button shows it.

### 2b. Editor: background pictures (pics.cfg)
Done. The page of a club, nation, competition, award, stadium and person shows its background pictures (its line in `pics.cfg`): each picture, or "No file" when the game finds no file for the name. A new one comes from any picture file: the page makes it an 800x600 RGN (the picture fills the screen, cut to fit), the editor saves it in `<user folder>/Pictures` under a name made from the key, and adds it to the record's line. For a competition the pictures shown when it is won (`{}`) have their own list. Remove takes a name out of the line; the file stays. The Pictures page lists the keys that match no record (with up to three close record names to change the key to; a key that another line already holds is merged into that line), the names that no file has, and the picture files that are not RGN, with a button that converts one and puts the RGN's name in its place in `pics.cfg`. The editor reads `pics.cfg` again before each use, so a change made by hand stays.

How the game reads them (`tools/editor/backgrounds.py`; port `src/cm3/background.c` with the original's addresses):
- Sections nations, clubs, stadiums, comps, awards, staff and the screens training, boardroom, trophy, transfer, si (`setup_background_system` `0x41b3d0`). A line is `key: name, name, {name}`; `#` starts a comment; spaces inside a name are dropped.
- The key is the record's English name, compared without case (`_stricmp` `0x951c50`; `club_get_english_name` `0x545880` and the others); a person is `first second d/m/yyyy` with `*` for a missing name (`0x41cf74`, format `0x989ac8`). A key that matches no record is not used; only the switch `-verifypics` reports it (`verify_background_config` `0x41bc20`, called at `0x82830c`).
- A name opens as `Pictures/<name>`, `Pictures/stadium/<name>` or `Pictures/old/<name>`, then the same with `_` in front; a name that no file has is dropped (`background_add_picture` `0x41b8c0`).
- RGN: a 48-byte header (width, height, byte size of the pixels, then the fixed values 0x01684c14, 32, 64, 0, 16 and the RGB565 masks 0xf800, 0x7e0, 0x1f, 0) and RGB565 pixels from the top row (`gui_load_rgn_picture` `0x5e40d0`). The backgrounds are 800x600.
- The game reads a file of the user folder before the game folder's (`src/recomp_rt/win/files.c`), so `pics.cfg` and the new pictures go to `<user folder>/Pictures`; the game folder does not change. `pics.cfg` belongs to every data set: a record renamed in a data set keeps the old key there, which the Pictures page then lists.

Checked: a picture added to Arsenal on its page shows behind Arsenal's club screen in a new game (Background Changes on).

### 2c. Editor: new records
Done. New copy, on the page of a club, person, stadium, city, official or name, makes a new record with the values of that one and opens it. The new row goes after the table's rows, with the next id, and Save as writes each table followed by its new rows and `index.dat` with the new counts and offsets (the tables of `staff.dat` move with the rows before them). The game takes the counts and offsets from `index.dat`.
- A person gets new player and non-player rows (copies) when the original has them, no club, no national team and job 0; the clubs' lists follow when the club and job are set.
- A club gets no people and no division, last division or reserve division. The ids equal the rows, and the national teams follow the clubs in the same id range, so a new club takes the first national team's id and the national teams move up by one, with every link to them: the club links of the load's id pass (club rivals, person club and national team, favourite and disliked clubs, career, comp history).
- A new name (first, second or common) is the way to give a person a name that the tables lack.
- Not supported: new nations and competitions (they need the custom league work, slices 3 to 6), and deleting records (other records link to the ids).

Checked: a new club in Switzerland and two new copies of Thierry Henry, one with a new second name "Henrytest" in Arsenal's squad; a new game loads the data set, and Arsenal's squad shows "Henrytest, T".

### 3. Read the original for B (Q1, Q2)
Blocked by: the build files.
### 4. Custom league with one division
Blocked by: 3.
### 5. Switzerland: Super League, Challenge League, play-off, cup
Blocked by: 4.
### 6. European places for custom nations
Blocked by: 5.
