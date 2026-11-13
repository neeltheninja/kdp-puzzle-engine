"""Resolve print fonts on any platform, with ReportLab's bundled fonts as fallback."""
import os
from functools import lru_cache
from pathlib import Path

import reportlab


@lru_cache(maxsize=None)
def font_path(name):
    replacements = {
        "Arial.ttf": ("arial.ttf", "DejaVuSans.ttf", "Vera.ttf"),
        "Arial Bold.ttf": ("arialbd.ttf", "DejaVuSans-Bold.ttf", "VeraBd.ttf"),
        "Georgia Bold.ttf": ("georgiab.ttf", "DejaVuSerif-Bold.ttf", "VeraBd.ttf"),
        "Impact.ttf": ("impact.ttf", "DejaVuSansCondensed-Bold.ttf", "VeraBd.ttf"),
        "Courier New Bold.ttf": ("courbd.ttf", "DejaVuSansMono-Bold.ttf", "VeraBd.ttf"),
    }
    windows, linux, bundled = replacements[name]
    candidates = [
        Path("/System/Library/Fonts/Supplemental") / name,
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / windows,
        Path("/usr/share/fonts/truetype/dejavu") / linux,
        Path(reportlab.__file__).parent / "fonts" / bundled,
    ]
    return str(next(path for path in candidates if path.is_file()))
