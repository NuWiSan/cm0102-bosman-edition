/* Our PNG pictures: faces and club badges (fork NuWiSan, spec 2026-11-17-badges-and-faces).
 *
 * The files are PNG in the user folder, named as the keys of pics.cfg (0x41cad0, 0x41cf74): a club by its
 * name, a person by "first second d-m-yyyy", in UTF-8. Not by id: the ids change between data sets and in
 * a game.
 *
 * They are drawn with the original's picture item: an item with style 0x400 and a path as its text, as
 * 0x460c55..0x460cc6 adds the badges of the Spanish edition. Its draw loads the text with 0x5e40d0, which
 * pictures_load answers for our keys with a picture made at its screen size (header as an RGN file), and
 * blits it with 0x5e3fd0 (cdecl (x, y, picture)), whose wrap below draws a badge with its transparency on
 * what lies under it. 0x5e42b0 frees a picture. The draw keeps one picture per text (0x5ee5f0..0x5ee6c5),
 * so each size of a picture gets its own key (the path and a tag). */
#include "win.h"
#include "pictures.h"
#include "display_scale.h"
#include "host.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define STB_IMAGE_IMPLEMENTATION
#define STBI_ONLY_PNG
#define STBI_NO_STDIO_WRITE
#include "../../third_party/stb_image.h"

#define STAFF_FIRST 0x4u            /* staff +4, +8: the first and second name, char * or 0 (0x41cf35..0x41cf41) */
#define STAFF_SECOND 0x8u
#define STAFF_BIRTH 0x10u           /* staff +0x10: the birth date; its year is the u16 at +0x12 */
#define CLUB_NAME 0x4u              /* club +4: the name */
#define DAY_OF 0x54cf70u            /* Date::get_day_of_month, thiscall */
#define MONTH_OF 0x54cfb0u          /* Date::get_month, thiscall: 0 for January */
#define DISPLAYS 0xb74c4cu          /* the Display of a screen: [DISPLAYS + 0x300 * (s16 [CURRENT])] */
#define CURRENT 0xb77c7au
#define ADD_AREA 0x55fba0u          /* Display::add_area, thiscall, 11 arguments */
#define ADD_ITEM 0x55f990u          /* Display::add_item, thiscall, 18 arguments */
#define CALLOC 0x945501u            /* the original's calloc */
#define DRAW_SURFACE 0xaebde4u      /* the surface that the draw functions draw on (ddraw.c) */
#define S_W 8u
#define S_H 0xcu
#define S_PITCH 0x10u
#define S_PIXELS 0x14u
#define PICTURE_STYLE 0x400u
#define LINK_STYLE 2u               /* the link button of a name text (comp_text): flags 2, font 7 */
#define CLUB_LINK 0x7d5u            /* the action of a club name link; its data is the club */

static const uint32_t frame_ground[3] = {16, 0, 74};   /* dark blue behind a transparent face (Nuno) */

#define ACTIVE_MAX 8
static Picture *active[ACTIVE_MAX];  /* the pictures that pictures_find found */

#define ALPHA_MAX 8
static struct {
    uint32_t pic, pixels, w, h;
    uint8_t *rgba;                  /* host memory: w x h, 4 bytes a pixel */
} alpha[ALPHA_MAX];                 /* the badges made by pictures_load, for the blit */

uint32_t pictures_call_this(uint32_t fn, uint32_t self, int n, const uint32_t *args)
{
    Cpu saved = cpu;
    cpu.ecx = self;
    uint32_t r = rt_callback(fn, n, args);
    cpu = saved;
    return r;
}

uint32_t pictures_sx(uint32_t v, int far) { return ds_screen(v, rt_screen_w, 800, far); }
uint32_t pictures_sy(uint32_t v, int far) { return ds_screen(v, rt_screen_h, 600, far); }

/* Appends the Latin-1 text s to out as UTF-8, with '_' for a character that a file name cannot hold. */
static void put_name(char *out, size_t room, const char *s)
{
    size_t n = strlen(out);
    for (; *s && n + 3 < room; s++) {
        unsigned char c = (unsigned char)*s;
        if (strchr("/\\:*?\"<>|", c) || c < 0x20) out[n++] = '_';
        else if (c < 0x80) out[n++] = (char)c;
        else {
            out[n++] = (char)(0xc0 | c >> 6);
            out[n++] = (char)(0x80 | (c & 0x3f));
        }
    }
    out[n] = 0;
}

void pictures_club_name(uint32_t club, char *out, size_t room)
{
    out[0] = 0;
    put_name(out, room, win_str(club + CLUB_NAME));
}

void pictures_person_name(uint32_t person, char *out, size_t room)
{
    uint32_t first = rd32(g_mem, person + STAFF_FIRST), second = rd32(g_mem, person + STAFF_SECOND);
    out[0] = 0;
    put_name(out, room, first ? win_str(first) : "_");
    put_name(out, room, " ");
    put_name(out, room, second ? win_str(second) : "_");
    uint32_t day = pictures_call_this(DAY_OF, person + STAFF_BIRTH, 0, NULL);
    uint32_t month = pictures_call_this(MONTH_OF, person + STAFF_BIRTH, 0, NULL);
    char date[40];
    snprintf(date, sizeof date, " %d-%d-%u", (int16_t)day, (int8_t)month + 1, rd16(g_mem, person + STAFF_BIRTH + 2));
    put_name(out, room, date);
}

int pictures_find(Picture *p, PictureKind kind, const char *folder, const char *name, const char *tag)
{
    p->on = 0;
    p->kind = kind;
    snprintf(p->path, sizeof p->path, "%s/%s/%s.png", win_user_dir, folder, name);
    snprintf(p->key, sizeof p->key, "%s%s", p->path, tag);
    FILE *f = fopen(p->path, "rb");
    if (!f) return 0;
    fclose(f);
    int i;
    for (i = 0; i < ACTIVE_MAX && active[i] && active[i] != p; i++) {}
    if (i < ACTIVE_MAX) active[i] = p;
    return p->on = 1;
}

int pictures_badge_size(Picture *p, uint32_t box_h, uint32_t max_w)
{
    int w = 0, h = 0, comp = 0;
    if (!stbi_info(p->path, &w, &h, &comp) || w <= 0 || h <= 0) return p->on = 0;
    p->h = box_h;
    p->w = (uint32_t)(((uint64_t)box_h * (uint32_t)w + (uint32_t)h / 2) / (uint32_t)h);
    if (p->w > max_w) {
        p->w = max_w;
        p->h = (uint32_t)(((uint64_t)max_w * (uint32_t)h + (uint32_t)w / 2) / (uint32_t)w);
    }
    return p->on = p->w > 0 && p->h > 0;
}

static uint32_t display(void)
{
    return rd32(g_mem, DISPLAYS + 0x300u * (uint32_t)(int32_t)(int16_t)rd16(g_mem, CURRENT));
}

int16_t pictures_add(Picture *p, uint32_t x1, uint32_t y1, uint32_t y2, int in_area)
{
    if (!p->text) p->text = win_static_alloc(PICTURE_PATH);
    win_put_str(p->text, p->key, PICTURE_PATH);
    /* The create wraps of display.c scale classic x values: give those that land on x1 .. x1 + w - 1. */
    uint32_t cx1 = ds_classic(x1, rt_screen_w, 800, 0), cx2 = ds_classic(x1 + p->w - 1, rt_screen_w, 800, 1);
    if (!in_area) {
        uint32_t args[18] = {PICTURE_STYLE, cx1, y1, cx2, y2, 0, 0, 1, 0, 0, 0xc, 1, 0, p->text, 0, 0, 0, 0xffffffffu};
        pictures_call_this(ADD_ITEM, display(), 18, args);
        return -1;
    }
    uint32_t area_args[11] = {cx1, y1, cx2, y2, 1, 0, 1, 0, 1, 0, 0xffffffffu};
    uint32_t area = pictures_call_this(ADD_AREA, display(), 11, area_args);
    if ((int16_t)area < 0) return -1;
    uint32_t item_args[18] = {PICTURE_STYLE, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0xc, 1, 0, p->text, 0, 0, 0, area};
    pictures_call_this(ADD_ITEM, display(), 18, item_args);
    return (int16_t)area;
}

void pictures_add_club_link(int16_t area, uint32_t club)
{
    uint32_t args[18] = {LINK_STYLE, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 7, 0, 0, 0, CLUB_LINK, club, (uint32_t)area};
    pictures_call_this(ADD_ITEM, display(), 18, args);
}

/* Scales the part cw x ch at (cx, cy) of the source into w x h RGBA pixels: each one the mean of the
 * source pixels under it. */
static void scale_rgba(uint8_t *dst, uint32_t w, uint32_t h, const uint8_t *src, int sw, int sh, uint32_t cx,
                       uint32_t cy, uint32_t cw, uint32_t ch)
{
    for (uint32_t y = 0; y < h; y++)
        for (uint32_t x = 0; x < w; x++) {
            uint32_t x0 = cx + x * cw / w, x1 = cx + (x + 1) * cw / w;
            uint32_t y0 = cy + y * ch / h, y1 = cy + (y + 1) * ch / h;
            if (x1 <= x0) x1 = x0 + 1;
            if (y1 <= y0) y1 = y0 + 1;
            uint64_t acc[4] = {0, 0, 0, 0}, n = 0;
            for (uint32_t yy = y0; yy < y1 && yy < (uint32_t)sh; yy++)
                for (uint32_t xx = x0; xx < x1 && xx < (uint32_t)sw; xx++) {
                    const uint8_t *s = src + ((size_t)yy * (size_t)sw + xx) * 4;
                    for (int c = 0; c < 4; c++) acc[c] += s[c];
                    n++;
                }
            for (int c = 0; c < 4; c++) dst[(y * w + x) * 4 + c] = n ? (uint8_t)(acc[c] / n) : 0;
        }
}

static uint16_t rgb565(uint32_t r, uint32_t g, uint32_t b)
{
    return (uint16_t)((r >> 3) << 11 | (g >> 2) << 5 | (b >> 3));
}

/* The frame: a thin light line; the face covers the inside, cut at the sides (centred) or at the bottom
 * (a portrait keeps the head), on the dark blue. */
static void make_frame(uint8_t *px, uint32_t w, uint32_t h, const uint8_t *src, int sw, int sh)
{
    for (uint32_t y = 0; y < h; y++)
        for (uint32_t x = 0; x < w; x++) {
            int line = x == 0 || y == 0 || x == w - 1 || y == h - 1;
            wr16(px, (y * w + x) * 2, line ? rgb565(200, 200, 210)
                                           : rgb565(frame_ground[0], frame_ground[1], frame_ground[2]));
        }
    if (w <= 2 || h <= 2) return;
    uint32_t iw = w - 2, ih = h - 2, cw = (uint32_t)sw, ch = (uint32_t)sh;
    if ((uint64_t)cw * ih > (uint64_t)ch * iw) cw = (uint32_t)((uint64_t)ch * iw / ih);
    else ch = (uint32_t)((uint64_t)cw * ih / iw);
    if (!cw || !ch) return;
    uint8_t *rgba = malloc((size_t)iw * ih * 4);
    if (!rgba) return;
    scale_rgba(rgba, iw, ih, src, sw, sh, ((uint32_t)sw - cw) / 2, 0, cw, ch);
    for (uint32_t y = 0; y < ih; y++)
        for (uint32_t x = 0; x < iw; x++) {
            const uint8_t *s = rgba + (y * iw + x) * 4;
            uint32_t c[3];
            for (int k = 0; k < 3; k++) c[k] = (s[k] * s[3] + frame_ground[k] * (255u - s[3])) / 255u;
            wr16(px, ((1 + y) * w + 1 + x) * 2, rgb565(c[0], c[1], c[2]));
        }
    free(rgba);
}

/* Remembers the RGBA pixels of a badge picture for the blit. */
static void keep_alpha(uint32_t pic, uint32_t pixels, uint32_t w, uint32_t h, uint8_t *rgba)
{
    static int next;
    int i;
    for (i = 0; i < ALPHA_MAX && alpha[i].pic; i++) {}
    if (i == ALPHA_MAX) i = next++ % ALPHA_MAX;
    free(alpha[i].rgba);
    alpha[i].pic = pic;
    alpha[i].pixels = pixels;
    alpha[i].w = w;
    alpha[i].h = h;
    alpha[i].rgba = rgba;
}

int pictures_load(void)
{
    uint32_t path = rd32(g_mem, cpu.esp + 4);
    Picture *p = NULL;
    for (int i = 0; path && i < ACTIVE_MAX && active[i]; i++)
        if (active[i]->on && !strcmp(win_str(path), active[i]->key)) p = active[i];
    if (!p) return 0;
    int sw = 0, sh = 0, comp = 0;
    uint8_t *src = stbi_load(p->path, &sw, &sh, &comp, 4);
    cpu.eax = 0;
    if (!src) return 1;
    uint32_t size = p->w * p->h * 2;
    uint32_t a1[2] = {1, 0x30}, a2[2] = {1, size};
    uint32_t pic = rt_callback(CALLOC, 2, a1);
    uint32_t pixels = pic ? rt_callback(CALLOC, 2, a2) : 0;
    if (pixels) {
        if (p->kind == PICTURE_FRAME) make_frame(g_mem + pixels, p->w, p->h, src, sw, sh);
        else {
            uint8_t *rgba = malloc((size_t)p->w * p->h * 4);
            if (rgba) {
                scale_rgba(rgba, p->w, p->h, src, sw, sh, 0, 0, (uint32_t)sw, (uint32_t)sh);
                keep_alpha(pic, pixels, p->w, p->h, rgba);
            }
        }
        const uint32_t head[12] = {p->w, p->h, size, pixels, 32, 64, 0, 16, 0xf800, 0x07e0, 0x001f, 0};
        for (int i = 0; i < 12; i++) wr32(g_mem, pic + 4u * (uint32_t)i, head[i]);
        cpu.eax = pic;
    }
    stbi_image_free(src);
    return 1;
}

void pictures_blend(const uint8_t *rgba, uint32_t w, uint32_t h, int32_t x, int32_t y, int32_t clip_y1, int32_t clip_y2)
{
    uint32_t surf = rd32(g_mem, DRAW_SURFACE);
    if (!surf || !rgba) return;
    uint32_t sw = rd32(g_mem, surf + S_W), sh = rd32(g_mem, surf + S_H), pitch = rd32(g_mem, surf + S_PITCH);
    uint8_t *dst = g_mem + rd32(g_mem, surf + S_PIXELS);
    for (uint32_t r = 0; r < h; r++)
        for (uint32_t c = 0; c < w; c++) {
            int32_t dx = x + (int32_t)c, dy = y + (int32_t)r;
            if (dx < 0 || dy < 0 || dx >= (int32_t)sw || dy >= (int32_t)sh || dy < clip_y1 || dy > clip_y2) continue;
            const uint8_t *s = rgba + (r * w + c) * 4;
            if (!s[3]) continue;
            uint32_t at = (uint32_t)dy * pitch + (uint32_t)dx * 2;
            uint16_t d = (uint16_t)rd16(dst, at);
            uint32_t under[3] = {(d >> 11) * 255u / 31u, ((d >> 5) & 63u) * 255u / 63u, (d & 31u) * 255u / 31u};
            uint32_t m[3];
            for (int k = 0; k < 3; k++) m[k] = (s[k] * s[3] + under[k] * (255u - s[3])) / 255u;
            wr16(dst, at, rgb565(m[0], m[1], m[2]));
        }
}

/* The picture blit 0x5e3fd0, cdecl (x, y, picture): a badge mixes with what is under it. */
void o_005e3fd0(void);

RT_WRAP(005e3fd0, picture_blit)
{
    uint32_t pic = rd32(g_mem, cpu.esp + 12);
    int i;
    for (i = 0; i < ALPHA_MAX; i++)
        if (pic && alpha[i].pic == pic && alpha[i].pixels == rd32(g_mem, pic + 0xc)) break;
    if (i == ALPHA_MAX) {
        o_005e3fd0();
        return;
    }
    pictures_blend(alpha[i].rgba, alpha[i].w, alpha[i].h, (int32_t)rd32(g_mem, cpu.esp + 4),
                   (int32_t)rd32(g_mem, cpu.esp + 8), 0, 0x7fffffff);
    rt_ret_cdecl(0);
}

#define BADGES_MAX 256
static struct {
    uint32_t club, h, w;
    char name[64];                  /* the club's name, to see that the record is still that club */
    uint8_t *rgba;                  /* NULL: no badge file */
} badges[BADGES_MAX];               /* the small badges of the lists (list_badges.c), for the session */

int pictures_any_badge(void)
{
    static int any = -1;
    if (any < 0) {
        char path[PICTURE_PATH];
        snprintf(path, sizeof path, "%s/badges", win_user_dir);
        any = 0;
        HostDir *d = host_opendir(path);
        if (d) {
            for (const char *e; !any && (e = host_readdir(d));) any = e[0] != '.';
            host_closedir(d);
        }
    }
    return any;
}

const uint8_t *pictures_club_badge(uint32_t club, uint32_t h, uint32_t *w)
{
    static int next;
    const char *club_name = win_str(club + CLUB_NAME);
    for (int i = 0; i < BADGES_MAX; i++)
        if (badges[i].club == club && badges[i].h == h && !strncmp(badges[i].name, club_name, sizeof badges[i].name - 1)) {
            *w = badges[i].w;
            return badges[i].rgba;
        }
    int i = next++ % BADGES_MAX;
    free(badges[i].rgba);
    memset(&badges[i], 0, sizeof badges[i]);
    badges[i].club = club;
    badges[i].h = h;
    snprintf(badges[i].name, sizeof badges[i].name, "%s", club_name);
    char name[300], path[PICTURE_PATH];
    pictures_club_name(club, name, sizeof name);
    snprintf(path, sizeof path, "%s/badges/%s.png", win_user_dir, name);
    int sw = 0, sh = 0, comp = 0;
    uint8_t *src = stbi_load(path, &sw, &sh, &comp, 4);
    if (!src || sw <= 0 || sh <= 0) {
        stbi_image_free(src);
        return NULL;
    }
    badges[i].w = (uint32_t)(((uint64_t)h * (uint32_t)sw + (uint32_t)sh / 2) / (uint32_t)sh);
    if (!badges[i].w) badges[i].w = 1;
    badges[i].rgba = malloc((size_t)badges[i].w * h * 4);
    if (badges[i].rgba) scale_rgba(badges[i].rgba, badges[i].w, h, src, sw, sh, 0, 0, (uint32_t)sw, (uint32_t)sh);
    stbi_image_free(src);
    *w = badges[i].w;
    return badges[i].rgba;
}

/* The picture free 0x5e42b0, cdecl (picture): forgets a badge's RGBA pixels. */
void o_005e42b0(void);

RT_WRAP(005e42b0, picture_free)
{
    uint32_t pic = rd32(g_mem, cpu.esp + 4);
    for (int i = 0; pic && i < ALPHA_MAX; i++)
        if (alpha[i].pic == pic) {
            free(alpha[i].rgba);
            memset(&alpha[i], 0, sizeof alpha[i]);
        }
    o_005e42b0();
}
