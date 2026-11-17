/* Small club badges beside club names in lists and tables (fork NuWiSan, spec 2026-11-17-badges-and-faces).
 *
 * A club name in a list is a link widget: action 0x7d5, the club as its data (2026-10-14-clickable-names-
 * inventory.md). Guio::draw 0x5ee590 (thiscall (refresh) ret 4, wrapped in names.c) draws a widget; its
 * fields (0x5ee4a0): the rectangle +0x10..+0x1c, the action +0x08, the data +0x48, the text +0x80. With
 * club_badges = on and any file in the badges folder, every club name gets a square box at its left, as
 * high as the row less a margin, and a gap: the widget is narrowed from the left before the draw, so that
 * the names stay in line whether their club has a badge or not; after the draw its rectangle is put back
 * and the badge, if the club has one, drawn in the box, centred. */
#include "win.h"
#include "options.h"
#include "pictures.h"

#define W_ACTION 0x08u
#define W_X1 0x10u
#define W_Y1 0x14u
#define W_X2 0x18u
#define W_Y2 0x1cu
#define W_DATA 0x48u
#define W_TEXT 0x80u
#define CLUB_LINK 0x7d5u
#define MARGIN 2u                   /* above and below the badge, screen pixels */
#define GAP 4u                      /* between the badge and the name, screen pixels */

static struct {
    uint32_t widget, w, h;
    int32_t x1, y1, y2;
    const uint8_t *badge;
    const char *path;
} drawing[4];                       /* a draw can draw another widget inside it */
static int depth;

/* Before the draw of the widget: 1 when it gets a badge. */
int list_badges_before(uint32_t widget)
{
    if (depth >= 4) return 0;
    drawing[depth].badge = NULL;
    if (rd32(g_mem, widget + W_ACTION) != CLUB_LINK || !rd32(g_mem, widget + W_DATA) || !rd8(g_mem, widget + W_TEXT) ||
        !options_bool(OPT_CLUB_BADGES))
        return 0;
    int32_t x1 = (int32_t)rd32(g_mem, widget + W_X1), y1 = (int32_t)rd32(g_mem, widget + W_Y1);
    int32_t x2 = (int32_t)rd32(g_mem, widget + W_X2), y2 = (int32_t)rd32(g_mem, widget + W_Y2);
    uint32_t h = y2 - y1 + 1 > 2 * (int32_t)MARGIN + 4 ? (uint32_t)(y2 - y1 + 1) - 2 * MARGIN : 0, w = 0;
    if (!h || !pictures_any_badge() || x1 + (int32_t)(h + GAP) >= x2) return 0;
    const char *path = NULL;
    const uint8_t *badge = pictures_club_badge(rd32(g_mem, widget + W_DATA), h, &w, &path);
    if (w > h) badge = NULL;        /* wider than the box: not shown */
    drawing[depth].widget = widget;
    drawing[depth].badge = badge;
    drawing[depth].path = path;
    drawing[depth].w = w;
    drawing[depth].h = h;
    drawing[depth].x1 = x1;
    drawing[depth].y1 = y1;
    drawing[depth].y2 = y2;
    depth++;
    wr32(g_mem, widget + W_X1, (uint32_t)(x1 + (int32_t)(h + GAP)));
    return 1;
}

/* After the draw of a widget that list_badges_before gave a badge. */
void list_badges_after(void)
{
    if (depth <= 0) return;
    depth--;
    wr32(g_mem, drawing[depth].widget + W_X1, (uint32_t)drawing[depth].x1);
    if (!drawing[depth].badge) return;
    int32_t x = drawing[depth].x1 + (int32_t)(drawing[depth].h - drawing[depth].w) / 2;
    int32_t y = drawing[depth].y1 + (int32_t)MARGIN;
    pictures_blend(drawing[depth].badge, drawing[depth].w, drawing[depth].h, x, y, drawing[depth].y1, drawing[depth].y2);
    pictures_sharp_add(PICTURE_BADGE, drawing[depth].path, x, y, drawing[depth].w, drawing[depth].h);
}
