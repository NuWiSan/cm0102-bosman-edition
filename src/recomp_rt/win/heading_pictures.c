/* Faces and club badges on the staff profile and the club screen (fork NuWiSan, spec
 * 2026-11-17-badges-and-faces). The pictures themselves: pictures.c.
 *
 * - Staff profile: with player_faces = frame and a face file, a portrait frame at the top left; with
 *   club_badges = on and a badge file of the person's club, the badge just before the name in place of
 *   the club's name in brackets, with the club link that the name had.
 * - Club screen: the badge just before the club's name in the heading, and in the General Info view of
 *   the info tab, where the Spanish edition put its badges.
 * Without the files, or with the options off, the screens are the original's.
 *
 * Facts (read in the 3.9.68 code, see the spec):
 * - staff_screens_build_profile_screen 0x870700 (cdecl, no arguments) takes the person from slot 0 of the
 *   screen node (0x8707ba, 0x7ff010) and adds the heading area (100, 10)-(790, 70) and the name area with
 *   Display::add_area 0x55fba0, and in it the name as a text with links (Text::set_string 0x4ae660,
 *   comp_text 0x4aeaf0) of the format 0xa85654 "<%s - player> ({}<%s - club>{})". The tabs and the
 *   Action drop-down lie above y 120. The person's club is at staff +0x39 (0x41c790).
 * - club_screen_build 0x454900 takes the club from slot 0 and adds the heading with
 *   ScreenManager::add_screen_title 0x803f30: one widget of flags 1 over (100, 10)-(790, 70), font 7,
 *   the centred club name.
 * - club_screen_draw_info_tab 0x460590 asks 0x460450 (cdecl (club, char *out), 1 when found) for the
 *   Spanish badge and, on a hit, adds an area from x 638 to 780 with the picture item (0x460c49).
 *
 * Decided (Nuno, 2026-11-17):
 * - the frame: a portrait of 4:5 in screen pixels from the top of the heading (y 10) to the bottom of the
 *   tabs (y 116), its left edge on the panels below (x 110). The heading and the tabs move and narrow
 *   from x 100..790 to new_left..790, one tab gap right of the frame;
 * - the heading badge: y 17 to 62 (the bar less a margin), a gap of 8 before the name, the badge and the
 *   name centred together;
 * - the info tab badge: from the top of the Nation row to the bottom of the Training Ground row, centred
 *   in x 638..780. */
#include "win.h"
#include "options.h"
#include "pictures.h"
#include "display_scale.h"

#include <stdio.h>
#include <string.h>

#define SCREENS 0xb74450u           /* the screen stack */
#define NODE_SLOT 0x7ff010u         /* thiscall on the stack (slot): a slot of the current screen node */
#define STAFF_CLUB 0x39u
#define TEXT_WIDTH 0x5e5ad0u        /* font_text_width, cdecl (font, text): screen pixels for the runtime */
#define TITLE_FONT 7u

#define LEFT 100u                   /* the heading: x 100..790, y 10..70 */
#define RIGHT 790u
#define HEAD_Y1 10u
#define HEAD_Y2 70u
#define TOP_PART 120u               /* the heading, the tabs and the Action drop-down lie above it */
#define FRAME_X1 110u
#define FRAME_Y2 116u
#define GAP 2u                      /* the gap between two tabs */
#define BADGE_Y1 17u
#define BADGE_Y2 62u
#define BADGE_GAP 8u
#define INFO_X1 638u                /* the Spanish badge's area (0x460c77, 0x460c6e) */
#define INFO_X2 780u
#define INFO_TOP 13u                /* from its top to the top of the Nation row */
#define INFO_HIGH 118u              /* from the top of the Nation row to the bottom of Training Ground */

static Picture face, badge, info;
static int building;                /* a heading with a picture is being built */
static int club_screen;             /* ... on the club screen (else the staff profile) */
static int cut_club;                /* the next name text loses its club part */
static int in_name;                 /* comp_text is making the widgets of the name */
static int info_next;               /* the next area from x 638 to 780 holds the info tab's badge */
static uint32_t new_left = LEFT;    /* the heading's left edge, classic */
static uint32_t frame_x2;           /* the frame's right edge, classic */
static uint32_t badge_room;         /* classic pixels for the badge and its gap */
static int32_t name_left;           /* the name's left edge on the screen */

#define sx pictures_sx
#define sy pictures_sy

static uint32_t slot0(void)
{
    uint32_t slot[1] = {0};
    return pictures_call_this(NODE_SLOT, SCREENS, 1, slot);
}

static int find_badge(Picture *p, uint32_t club, const char *tag)
{
    char name[300];
    if (!club || !options_bool(OPT_CLUB_BADGES)) return p->on = 0;
    pictures_club_name(club, name, sizeof name);
    return pictures_find(p, PICTURE_BADGE, "badges", name, tag);
}

/* The heading badge: the bar's height less the margin, the width by its shape. */
static int heading_badge(uint32_t club)
{
    if (!find_badge(&badge, club, "") ||
        !pictures_badge_size(&badge, sy(BADGE_Y2, 1) - sy(BADGE_Y1, 0) + 1, sx(RIGHT, 1)))
        return 0;
    badge_room = ds_classic(badge.w + sx(BADGE_GAP, 0) - sx(0, 0), rt_screen_w, 800, 0);
    return 1;
}

/* The frame: a 4:5 portrait in screen pixels; the heading starts one tab gap right of it. */
static void frame_layout(void)
{
    face.h = sy(FRAME_Y2, 1) - sy(HEAD_Y1, 0) + 1;
    uint32_t want = sx(FRAME_X1, 0) + (face.h * 4 + 2) / 5 - 1;
    frame_x2 = FRAME_X1;
    while (frame_x2 < 400 && sx(frame_x2 + 1, 1) <= want) frame_x2++;
    face.w = sx(frame_x2, 1) - sx(FRAME_X1, 0) + 1;
    uint32_t gap = sx(LEFT + GAP, 0) - sx(LEFT, 0);
    new_left = frame_x2 + 1;
    while (new_left < 400 && sx(new_left, 0) < sx(frame_x2, 1) + 1 + gap) new_left++;
}

/* x in 100..790 on the narrower heading. */
static uint32_t squeeze_x(uint32_t x)
{
    if (x < LEFT || x > RIGHT) return x;
    return new_left + (x - LEFT) * (RIGHT - new_left) / (RIGHT - LEFT);
}

/* Moves the rectangle of the stack arguments x1, y1, x2, y2 from `a` when it lies in the top part. */
static void move_rect(uint32_t a)
{
    int32_t x1 = (int32_t)rd32(g_mem, a), y1 = (int32_t)rd32(g_mem, a + 4);
    int32_t x2 = (int32_t)rd32(g_mem, a + 8), y2 = (int32_t)rd32(g_mem, a + 12);
    if (x1 < (int32_t)LEFT || y1 < 0 || y2 > (int32_t)TOP_PART || y2 <= 0 || x2 <= x1) return;
    wr32(g_mem, a, squeeze_x((uint32_t)x1));
    wr32(g_mem, a + 8, squeeze_x((uint32_t)x2));
}

/* The info tab's badge area: the box of the badge, centred in x 638..780, from the Nation row. */
static void info_rect(uint32_t a)
{
    uint32_t x1 = sx(INFO_X1, 0), x2 = sx(INFO_X2, 1);
    uint32_t left = x1 + (x2 - x1 + 1 - info.w) / 2;
    uint32_t top = rd32(g_mem, a + 4) + INFO_TOP;
    wr32(g_mem, a, ds_classic(left, rt_screen_w, 800, 0));
    wr32(g_mem, a + 4, top);
    wr32(g_mem, a + 8, ds_classic(left + info.w - 1, rt_screen_w, 800, 1));
    wr32(g_mem, a + 12, top + INFO_HIGH - 1);
}

/* From the area create wrap of display.c, before the widescreen scale: (x1, y1, x2, y2, ...). */
void heading_pictures_area_before(void)
{
    uint32_t a = cpu.esp + 4;
    if (info_next && rd32(g_mem, a) == INFO_X1 && rd32(g_mem, a + 8) == INFO_X2) {
        info_next = 0;
        info_rect(a);
        return;
    }
    if (building && !club_screen) move_rect(a);
}

/* The club screen's heading (0x803f30): (1, 100, 10, 790, 70, .., font 7 as argument 12, .., text as
 * argument 14, ..). The widget is the bar and its centred text: the text gets spaces in front, as wide as
 * the badge and its gap, and the badge goes on them. */
static void title_before(uint32_t a)
{
    if (rd32(g_mem, a) != 1 || rd32(g_mem, a + 4) != LEFT || rd32(g_mem, a + 8) != HEAD_Y1 ||
        rd32(g_mem, a + 12) != RIGHT || rd32(g_mem, a + 16) != HEAD_Y2 || rd32(g_mem, a + 44) != TITLE_FONT)
        return;
    uint32_t text = rd32(g_mem, a + 52);
    char name[0x100], padded[0x200] = "";
    snprintf(name, sizeof name, "%s", win_str(text));
    uint32_t args[2] = {TITLE_FONT, text};
    int32_t width = (int32_t)rt_callback(TEXT_WIDTH, 2, args), pad = 0;
    int32_t room = (int32_t)(sx(badge_room, 0) - sx(0, 0));
    while (pad < room && strlen(padded) + strlen(name) + 2 < sizeof padded) {
        strcat(padded, " ");
        win_put_str(text, padded, 0x200);
        pad = (int32_t)rt_callback(TEXT_WIDTH, 2, args);
    }
    strcat(padded, name);
    win_put_str(text, padded, 0x200);
    name_left = ((int32_t)sx(LEFT, 0) + (int32_t)sx(RIGHT, 1) + 1) / 2 - (pad + width) / 2 + pad;
}

/* From the widget create wrap of display.c, before the widescreen scale: (flags, x1, y1, x2, y2, ...).
 * comp_text: the x values are screen pixels already; a widget of the name gives the name's left edge. */
void heading_pictures_widget_before(int comp_text)
{
    if (!building) return;
    uint32_t a = cpu.esp + 4;
    if (club_screen) {
        if (!comp_text) title_before(a);
        return;
    }
    if (!comp_text) move_rect(a + 4);
    else if (in_name && (name_left < 0 || (int32_t)rd32(g_mem, a + 4) < name_left))
        name_left = (int32_t)rd32(g_mem, a + 4);
}

/* From the comp_text wrap of display.c, before the widescreen scale: (area, x1, x2, ...), classic. The
 * name follows the heading; with a badge it starts badge_room further right. */
void heading_pictures_comp_text_before(void)
{
    if (!building || club_screen) return;
    uint32_t a = cpu.esp + 8;
    if (rd32(g_mem, a) != LEFT || rd32(g_mem, a + 4) != RIGHT) return;
    wr32(g_mem, a, squeeze_x(LEFT) + (badge.on ? badge_room : 0));
    wr32(g_mem, a + 4, squeeze_x(RIGHT));
    in_name = 1;
}

void heading_pictures_comp_text_after(void)
{
    in_name = 0;
}

/* Text::set_string 0x4ae660, thiscall (source): the name text, already plain ("14. Thierry Henry
 * (Arsenal)"), loses its last " (..." when the badge stands in for the club's name. */
void o_004ae660(void);

RT_WRAP(004ae660, text_set_string)
{
    if (cut_club) {
        char *s = win_str(rd32(g_mem, cpu.esp + 4)), *club = NULL;
        for (char *f = strstr(s, " ("); f; f = strstr(f + 1, " (")) club = f;
        if (club) {
            *club = 0;
            cut_club = 0;
        }
    }
    o_004ae660();
}

static int32_t badge_x(void)
{
    return name_left - (int32_t)(sx(BADGE_GAP, 0) - sx(0, 0)) - (int32_t)badge.w;
}

void o_00870700(void);

RT_WRAP(00870700, staff_profile_build)
{
    uint32_t person = slot0(), club = person ? rd32(g_mem, person + STAFF_CLUB) : 0;
    char name[300];
    face.on = 0;
    if (person && options_enum(OPT_PLAYER_FACES) == FACES_FRAME) {
        pictures_person_name(person, name, sizeof name);
        pictures_find(&face, PICTURE_FRAME, "faces", name, "");
    }
    heading_badge(club);
    new_left = LEFT;
    if (face.on) frame_layout();
    building = face.on || badge.on;
    cut_club = badge.on;
    name_left = -1;

    o_00870700();
    building = cut_club = 0;
    if (rt_unwinding) return;
    if (face.on) pictures_add(&face, sx(FRAME_X1, 0), HEAD_Y1, FRAME_Y2, 1);
    if (badge.on && name_left >= 0) {
        int16_t area = pictures_add(&badge, (uint32_t)badge_x(), BADGE_Y1, BADGE_Y2, 1);
        if (area >= 0) pictures_add_club_link(area, club);
    }
}

void o_00454900(void);

RT_WRAP(00454900, club_screen_build)
{
    building = club_screen = heading_badge(slot0());
    name_left = -1;
    o_00454900();
    building = club_screen = 0;
    if (rt_unwinding || !badge.on || name_left < 0) return;
    /* Outside any area, as the heading is, so that it draws after the heading and not under it. */
    pictures_add(&badge, (uint32_t)badge_x(), BADGE_Y1, BADGE_Y2, 0);
}

/* 0x460450, cdecl (club, char *out): our badge for any club, at the size of the info tab's box. */
void o_00460450(void);

RT_WRAP(00460450, info_badge)
{
    uint32_t club = rd32(g_mem, cpu.esp + 4), out = rd32(g_mem, cpu.esp + 8);
    if (out && find_badge(&info, club, "#info") && strlen(info.key) < 260 &&
        pictures_badge_size(&info, sy(INFO_HIGH, 1) - sy(0, 0), sx(INFO_X2, 1) - sx(INFO_X1, 0) + 1)) {
        win_put_str(out, info.key, 260);
        info_next = 1;
        rt_ret_cdecl(1);
        return;
    }
    o_00460450();
}
