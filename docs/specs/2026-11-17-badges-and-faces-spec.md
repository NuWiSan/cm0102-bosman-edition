# Club badges and player faces (fork NuWiSan)

Status: in progress. Done: faces and badges on the staff profile and the club screen. Next: small badges in lists and tables.

Upstream lists club badges and faces as "not planned" (`2026-11-12-features-0.8.0-spec.md`, Out of scope). This is a fork feature. It follows the upstream rules: no game decision changes, a line in `settings.txt` for each option, hooks only through `tools/recomp`.

## What the player gets

- **Face**: a portrait frame at the top left of the staff profile, on every tab.
- **Badge on the staff profile**: the badge of the person's club just before the name, in place of the club's name in brackets. A click on it opens the club, as the name did.
- **Badge on the club screen**: just before the club's name in the heading, and large in the General Info view of the Finances & Info tab.
- Without the files, or with the options off, every screen is the original's, byte for byte.

## Files

- PNG in the user folder (beside the saves): `badges/<club name>.png` and `faces/<first name> <second name> <d-m-yyyy>.png`, for example `badges/Arsenal.png` and `faces/Thierry Henry 17-8-1977.png`.
- The names are the keys of the original's `pics.cfg` (a club by its name, `0x41cad0`; a person by `"%s %s %d/%d/%d"`, `0x41cf74`), with `-` for `/`, in UTF-8; a character that a file name cannot hold becomes `_`. Not ids: the ids change between data sets and in a game.
- The game reads PNG only. The editor takes PNG, SVG and WebP and saves PNG with the right name. The community can make packs already named, ready to copy into the folders.
- A transparent picture: a badge shows what lies under it; a face shows a dark blue.

## Options (`settings.txt`)

- `player_faces = frame | background`: `frame` shows the face frame; `background` keeps only the original's background pictures of `pics.cfg`.
- `club_badges = on | off`.

## Layout

All values classic (800x600); widescreen uses the same places, scaled.

- Face frame: a portrait of 4:5 in screen pixels, from the top of the heading (y 10) to the bottom of the tabs (y 116), its left edge on the left edge of the panels below (x 110), a line of one pixel. The heading, the tabs and the Action drop-down move and narrow from x 100..790 to start one tab gap (2 pixels) right of the frame.
- Heading badge (staff profile and club screen): y 17 to 62, the width by the picture's shape, 8 pixels before the name; the badge and the name are centred together in the heading.
- Info tab badge: from the top of the Nation row to the bottom of the Training Ground row, the width by its shape, centred in x 638..780 (the place of the Spanish edition's badges).

## How it works

Code: `src/recomp_rt/win/pictures.c` (files, PNG, drawing) and `heading_pictures.c` (the screens); hooks in the create wraps of `display.c`. Addresses are of `cm0102.exe` 3.9.68.

- Pictures are the original's picture item: style `0x400`, the text a path, as `0x460c55..0x460cc6` adds the Spanish badges. Its draw loads the text with `0x5e40d0`: the wrap answers our keys with a picture made at its screen size (`stb_image.h`, public domain, `src/third_party/`). The draw keeps one picture per text, so each size has its own key (the path and a tag). The blit `0x5e3fd0` (cdecl (x, y, picture)) is wrapped so that a badge mixes with what lies under it; `0x5e42b0` frees a picture.
- Staff profile, `staff_screens_build_profile_screen` `0x870700`: the person is slot 0 of the screen node (`0x8707ba`, `0x7ff010`), the club `staff+0x39` (`0x41c790`). The name is a text with links (`Text::set_string` `0x4ae660`, `comp_text` `0x4aeaf0`, format `0xa85654` `"<%s - player> ({}<%s - club>{})"`); with a badge the text loses its last `" ("`, and over the badge lies the club link item that `comp_text` made for the name (flags 2, font 7, action `0x7d5`, the club as data).
- Club screen, `club_screen_build` `0x454900`: the club is slot 0. The heading is one widget of `ScreenManager::add_screen_title` `0x803f30` (the bar and its centred text, font 7), so the text gets spaces in front as wide as the badge and its gap; the badge item lies outside any area, as the heading does, so that it draws after it.
- Info tab: `club_screen_draw_info_tab` `0x460590` asks `0x460450` (cdecl (club, out); the Spanish badge table at `0x98dedc`, 40 clubs, `.BDG` files that the free release does not ship) and adds an area at x 638..780 with the picture (`0x460c49`). The wrap of `0x460450` answers for every club with a badge file, and the area gets the badge's box.
- The original's person picture order (`0x41c790`), kept as it is: the person's own picture, his club's (`0x41cad0`), his nation's (`0x41c9d0`), the default (`0x41ced0`), a random one (`0x41bfb0`).

## Tests

- Classic and widescreen screenshots of the staff profile (Profile and Contract tabs), the club screen and its General Info view, with test files.
- Without files, the three screens equal the original's byte for byte.
- A click on the profile's badge opens the club screen.
- Same save: the same steps with the options on and off give the same save; only `national_teams.dat` may differ, by a heap address that the original writes into the save (a part of `smoke_run.LAYOUT_PARTS`).
- `tests/options` knows both options. `tests/fixtures/fixtures.py`: `FIXTURES_USER_FILES` copies a folder (for example `faces/`, `badges/`) into the user folder of a play.

## Next

Small badges in every list and table. Club names there are link widgets with id `0x7d5` and the club as data (`2026-10-14-clickable-names-inventory.md`): one hook where such a widget is made gives the club's place on every screen. To check: whether a row is high enough for a badge and whether names must move right.
