# Caption fonts of the Studio

Taken unchanged from Debian (trixie) font packages; each keeps its own licence.

| id | file | package | licence |
|---|---|---|---|
| classic | DejaVuSans-Bold.ttf | fonts-dejavu-core | Bitstream Vera / DejaVu (free) |
| serif | DejaVuSerif-Bold.ttf | fonts-dejavu-core | Bitstream Vera / DejaVu (free) |
| montserrat | Montserrat-ExtraBold.ttf | fonts-montserrat | SIL Open Font License 1.1 |
| roboto | Roboto-Bold.ttf | fonts-roboto-unhinted | Apache License 2.0 |
| condensed | RobotoCondensed-Bold.ttf | fonts-roboto-unhinted | Apache License 2.0 |
| opensans | OpenSans-Bold.ttf | fonts-open-sans | Apache License 2.0 |
| lato | Lato-Black.ttf | fonts-lato | SIL Open Font License 1.1 |
| bebas | BebasNeue-Bold.otf | fonts-bebas-neue | SIL Open Font License 1.1 |

## Added 2026-10-06 (bot36: "so good fonts, attractive, modern")

Again unchanged from Debian (trixie) font packages (`apt-get download`, `dpkg-deb -x`); each keeps its own licence.

| id | file | package | licence |
|---|---|---|---|
| spartan | LeagueSpartan-Bold.otf | fonts-league-spartan | SIL Open Font License 1.1 |
| sora | Sora-ExtraBold.otf | fonts-sora | SIL Open Font License 1.1 |
| manrope | Manrope-ExtraBold.ttf | fonts-manrope | SIL Open Font License 1.1 |
| inter | InterDisplay-Black.otf | fonts-inter | SIL Open Font License 1.1 |
| black | Montserrat-Black.otf | fonts-montserrat | SIL Open Font License 1.1 |
| cabin | Cabin-Bold.otf | fonts-cabin | SIL Open Font License 1.1 |
| kaffeesatz | YanoneKaffeesatz-Bold.otf | fonts-yanone-kaffeesatz | SIL Open Font License 1.1 |
| slab | RobotoSlab-Bold.otf | fonts-roboto-slab | Apache License 2.0 |
| quicksand | Quicksand-Bold.ttf | fonts-quicksand | SIL Open Font License 1.1 |
| comfortaa | Comfortaa-Bold.ttf | fonts-comfortaa | SIL Open Font License 1.1 |
| lobster | lobster.otf | fonts-lobster | SIL Open Font License 1.1 |
| dancing | DancingScript-Bold.otf | fonts-dancingscript | SIL Open Font License 1.1 |

The Studio gives the page each font's line pitch (`branding.caption_line_height`): the font's own line height, which
is what the render (ffmpeg drawtext) uses from one line of a caption to the next.
