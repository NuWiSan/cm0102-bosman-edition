/* Our PNG pictures (faces, club badges) drawn with the original's picture items (pictures.c). */
#ifndef PICTURES_H
#define PICTURES_H

#include <stddef.h>
#include <stdint.h>

#define PICTURE_PATH 1100u

typedef enum {
    PICTURE_FRAME,                  /* a face in a frame: a thin line, the face covers the inside, opaque */
    PICTURE_BADGE                   /* a badge: the whole picture in the box, transparent where it is */
} PictureKind;

typedef struct {
    int on;
    PictureKind kind;
    char path[PICTURE_PATH];        /* the file on the host */
    char key[PICTURE_PATH];         /* the text of the picture item: the path and a tag, one per size */
    uint32_t text;                  /* game memory for the key */
    uint32_t w, h;                  /* screen pixels */
} Picture;

/* The file names, as the keys of pics.cfg: a club by its name, a person by "first second d-m-yyyy". */
void pictures_club_name(uint32_t club, char *out, size_t room);
void pictures_person_name(uint32_t person, char *out, size_t room);

/* 1 when <user folder>/<folder>/<name>.png exists; sets p->path and p->key (path and tag). */
int pictures_find(Picture *p, PictureKind kind, const char *folder, const char *name, const char *tag);

/* A badge's size: box_h high (screen pixels), the width by its shape, at most max_w wide. */
int pictures_badge_size(Picture *p, uint32_t box_h, uint32_t max_w);

/* Adds the picture item at x1 (screen pixels), y1..y2 (classic): in an area of its own (returns the
 * area), or outside any area (area < 0: returns -1), as the screen title is. */
int16_t pictures_add(Picture *p, uint32_t x1, uint32_t y1, uint32_t y2, int in_area);

/* Over the area of a picture, the link to a club (the club name link of comp_text). */
void pictures_add_club_link(int16_t area, uint32_t club);

/* 1 when the badges folder holds any file (looked at once a session). */
int pictures_any_badge(void);

/* The badge of a club, h screen pixels high, as RGBA pixels (kept for the session), or NULL when the club
 * has no badge file; its width in *w. */
const uint8_t *pictures_club_badge(uint32_t club, uint32_t h, uint32_t *w);

/* Mixes w x h RGBA pixels onto the draw surface at (x, y), inside the clip y1..y2. */
void pictures_blend(const uint8_t *rgba, uint32_t w, uint32_t h, int32_t x, int32_t y, int32_t clip_y1, int32_t clip_y2);

/* From the picture load wrap of display.c: 1 when the path is one of ours (then cpu.eax is the picture). */
int pictures_load(void);

/* Classic coordinates on the screen. */
uint32_t pictures_sx(uint32_t v, int far);
uint32_t pictures_sy(uint32_t v, int far);

uint32_t pictures_call_this(uint32_t fn, uint32_t self, int n, const uint32_t *args);

#endif
