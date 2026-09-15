"""User-supplied brand assets embedded in offline views without remote requests."""

import base64
from functools import lru_cache
from importlib.resources import files


@lru_cache(maxsize=2)
def logo_uri(*, dark=False):
    name = "logo-dark.png" if dark else "logo-light.png"
    raw = files("forkit_radar").joinpath("assets", name).read_bytes()
    return "data:image/png;base64," + base64.b64encode(raw).decode("ascii")


def card_logo():
    # Crop only the transparent canvas in the SVG viewport; keep the supplied
    # image bytes intact. This embeds the artwork in exported SVG/PNG too.
    return ('<svg x="945" y="39" width="180" height="52" viewBox="20 180 1640 590">'
            f'<image width="1672" height="941" href="{logo_uri(dark=True)}"/></svg>')
