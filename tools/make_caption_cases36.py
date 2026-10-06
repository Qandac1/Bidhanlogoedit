"""The shared list of typed captions and what must be stored for each (bot36) -> caption_cases36.json.
The bot's branding.caption_lines (test_bot_studio36.py) and the page's capNorm (driven in a browser) are both
tested with this one list. The expected values are written by hand here, not computed by either function.
Usage: python make_caption_cases36.py <out.json>"""
import json
import sys

CASES = [
    ["UGAAR AH BIDHAAN TV 0619624090", "UGAAR AH BIDHAAN TV 0619624090"],                 # one line, as before
    ["     U GAAR AH\nRASHKA BOY MUSALSAL TV", "     U GAAR AH\nRASHKA BOY MUSALSAL TV"],  # John's own: kept as typed
    ["  Bidhaan   TV \n 0619  ", " Bidhaan   TV\n0619"],        # spaces at line ends go; the indent both lines share (1) goes
    ["\n\n  A\n\n  B  \n\n", "A\n\nB"],                         # empty first / last lines go, the empty line between stays
    ["A\r\nB\rC", "A\nB\nC"],                                   # Windows / old Mac line ends
    ["\tTAB", "TAB"],                                           # one line: its indent cannot be seen
    ["A\n\tB", "A\n    B"],                                     # a tab = 4 spaces
    ["   ONE LINE   ", "ONE LINE"],
    ["A  B", "A  B"],                                           # two spaces stay two
    ["1\n2\n3\n4\n5\n6\n7\n8", "1\n2\n3\n4\n5\n6"],             # at most 6 lines
    ["LINE\n\n\n\n\n\nLATE", "LINE"],                           # ... and no empty lines left at the end after the cut
    ["x" * 500, "x" * 300],                                     # at most 300 characters
    ["a" * 299 + " b", "a" * 299],                              # ... and no space left at the end after the cut
    ["", ""],
    ["   \n  \n", ""],
    [None, ""],
    ["A\u0007B\u0000C", "ABC"],                                 # control characters go
    ["CAASHAQ ❤\n  SOMALI", "CAASHAQ ❤\n  SOMALI"],
    ["   A\n     B\n C", "  A\n    B\nC"],                      # three lines, indents 3 / 5 / 1 -> 2 / 4 / 0
    ["TOP\n      \nBOTTOM", "TOP\n\nBOTTOM"],                   # a line of spaces only is an empty line
]
json.dump(CASES, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=True, indent=0)
print("CAPTION_CASES %d -> %s" % (len(CASES), sys.argv[1]))
