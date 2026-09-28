"""Proves patch_bot_cutsummary inside the bot container on real data:
  pretty_name on John's real file names; make_cut_summary on Half Girlfriend (its approved summary:
  8 places, 'ku dhawaad 10 daqiiqo', the censored place, a picture); a title with no work -> (None,
  None) and the reason recorded (never silent).
Usage: python3 test_bot_cutsummary.py <patched bot dir>     prints CUTSUMMARY_TESTS ALL PASS"""
import asyncio
import importlib.util
import os
import sys

d = sys.argv[1]
spec = importlib.util.spec_from_file_location("jcs", os.path.join(d, "dubsync_job.py"))
m = importlib.util.module_from_spec(spec)
sys.modules["jcs"] = m
sys.path.insert(0, d)
spec.loader.exec_module(m)
ok = True


def check(name, cond, detail=""):
    global ok
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else "  | " + str(detail)[:500]))
    ok &= bool(cond)


for fn, want in [("Half.Girlfriend.2017.1080p.NF.WEB-DL.DDP5.1.x264-AtishMK.mkv", "Half Girlfriend (2017)"),
                 ("Bheemaa.2008.1080p.AHA.WEB-DL.AAC2.0.H.264-PMI.mkv", "Bheemaa (2008)"),
                 ("(DVDWO) Bheema (2008) Tamil 1080p x265 (Hevc) 1.4Gb - Rj.mp4", "Bheema (2008)"),
                 ("Pushpa.2.The.Rule.Reloaded.2024.1080p.10Bit.WEB-DL.Hindi.5.1.mkv", "Pushpa 2 The Rule Reloaded (2024)"),
                 ("@HEVC_Moviesz_Achcham_Yenbadhu_Madamaiyada_2016_Tamil_10.mp4", "Moviesz Achcham Yenbadhu Madamaiyada (2016)")]:
    got = m.pretty_name(fn)
    check("pretty_name %s" % fn[:30], got == want, got)
st = {"hd_intro_s": 11.0}
txt, img = asyncio.run(m.make_cut_summary("halfgirlfriend2017_6a7c28", "Half Girlfriend (2017)", st))
check("summary text made", bool(txt) and "ku dhawaad 10 daqiiqo" in txt and "about 10 minutes" in txt, txt)
check("8 places, censored place named", bool(txt) and "8. 1:54:12-1:54:34" in txt and "faafreebay" in txt, txt)
check("picture made", bool(img) and os.path.getsize(img) > 20000, img)
st2 = {}
t2, i2 = asyncio.run(m.make_cut_summary("no_such_title_xyz", "X", st2))
check("unknown title -> None + reason recorded", t2 is None and i2 is None and st2.get("cut_summary_error"), st2)
print("CUTSUMMARY_TESTS", "ALL PASS" if ok else "FAILED")
