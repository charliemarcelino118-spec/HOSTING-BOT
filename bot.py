import sys
import telebot
import requests
import json
import uuid
import re
import time
import os
import threading
import queue
import html
import shutil
import functools
import random
import sqlite3
import signal
import zipfile
import io
import urllib3
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from enum import Enum

from DRAKVEX_ML import (
    probe_device,
    fetch_info_by_device,
    DEVICE_ID_RE,
    map_rank,
    map_collector,
)

if 'imghdr' not in sys.modules:
    class DummyImghdr:
        def what(self, *a, **k):
            return 'jpeg'
    sys.modules['imghdr'] = DummyImghdr()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
telebot.apihelper.RETRY_ON_ERROR = True
telebot.apihelper.MAX_RETRIES = 5

BOT_TOKEN = "8638173787:AAHmwq8loNlIsKWsC6CUSRDEEFMubuMUAs4"
OWNER_ID = "8829599064"
BRAND = "MLBB BOT CEK"
OWNER_USERNAME = "RYUSIN"
SUPPORT_HANDLE = "RYUSIN"
SUPPORT_URL = "https://t.me/RAX1ELA"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML')
bot_start_time = time.time()
BOT_RUNNING = True
banned_users = []
shutdown_flag = False

DEFAULT_THREADS_FREE = 100
DEFAULT_THREADS_BASIC = 150
DEFAULT_THREADS_SEMI_VIP = 200
DEFAULT_THREADS_VIP = 250  # [DRAKVEX_SPEED]
CUSTOM_THREADS = {
    "free": DEFAULT_THREADS_FREE,
    "basic": DEFAULT_THREADS_BASIC,
    "semi_vip": DEFAULT_THREADS_SEMI_VIP,
    "vip": DEFAULT_THREADS_VIP,
    "daily_reward_max": 25,
}

try:
    BOT_USERNAME = bot.get_me().username
except Exception:
    BOT_USERNAME = "@Dev_id_checker_v2_bot"

SQLITE_DB = 'bot_database.db'
BACKUP_FILE = 'bot_backup.db'
DB_FILE = 'users_db'
FORCE_DB = 'force_subscriptions'
BANNED_DB = 'banned_users'
db_lock = threading.Lock()


class MembershipStatus(Enum):
    FREE = "🆓 FREE"
    BASIC = "⭐ BASIC"
    SEMI_VIP = "💠 SEMI VIP"
    VIP = "👑 VIP"


class RateLimiter:
    def __init__(self, max_calls=40, period=1):
        self.max_calls = max_calls
        self.period = period
        self.calls = []
        self.lock = threading.Lock()

    def wait_if_needed(self):
        with self.lock:
            now = time.time()
            self.calls = [t for t in self.calls if now - t < self.period]
            if len(self.calls) >= self.max_calls:
                st = self.period - (now - self.calls[0])
                if st > 0:
                    time.sleep(st)
            self.calls.append(time.time())


rate_limiter = RateLimiter(max_calls=60, period=1)  # [DRAKVEX_SPEED]


def send_with_retry(func, *args, max_retries=5, **kwargs):
    for attempt in range(max_retries):
        try:
            rate_limiter.wait_if_needed()
            return func(*args, **kwargs)
        except telebot.apihelper.ApiTelegramException as e:
            s = str(e)
            if "429" in s:
                time.sleep(2 * (attempt + 1) + random.uniform(0, 1))
                continue
            if any(x in s for x in ("400", "403", "404")):
                return None
            raise
        except Exception:
            if attempt == max_retries - 1:
                return None
            time.sleep(1)
    return None


def retry_on_error(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return send_with_retry(func, *args, **kwargs)
        except Exception:
            return None
    return wrapper


def init_db(db_path=None):
    if db_path is None:
        db_path = SQLITE_DB
    try:
        conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        conn.execute("PRAGMA cache_size=10000;")
        conn.execute("PRAGMA mmap_size=268435456;")
        conn.execute("PRAGMA foreign_keys=ON;")
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY,registered_date TEXT,total_scans INTEGER DEFAULT 0,total_hits INTEGER DEFAULT 0,today_scans INTEGER DEFAULT 0,last_scan_date TEXT,referrals INTEGER DEFAULT 0,referred_by TEXT,base_limit INTEGER DEFAULT 5000,username TEXT,first_name TEXT,membership TEXT,membership_expiry TEXT,user_threads INTEGER DEFAULT 50,total_files INTEGER DEFAULT 0,last_scan_time TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS force_subs (sub_data TEXT PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS banned_users (user_id TEXT PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS threads_config (key TEXT PRIMARY KEY,value INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS rewards_data (user_id TEXT PRIMARY KEY,last_daily TEXT,claimed_codes TEXT,temp_lines INTEGER DEFAULT 0,temp_lines_expiry TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS gift_codes (code TEXT PRIMARY KEY,reward_type TEXT,reward_value TEXT,max_uses INTEGER DEFAULT 1,current_uses INTEGER DEFAULT 0)''')
        c.execute('''CREATE TABLE IF NOT EXISTS license_keys (key TEXT PRIMARY KEY,plan TEXT,duration TEXT,created_at TEXT,created_by TEXT,used_by TEXT,used_at TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS payment_requests (req_id TEXT PRIMARY KEY,user_id TEXT,username TEXT,plan TEXT,amount TEXT,receipt_id TEXT,status TEXT,created_at TEXT,decided_at TEXT)''')
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def init_db_with_fallback():
    if not init_db(SQLITE_DB):
        if os.path.exists(BACKUP_FILE):
            try:
                shutil.copyfile(BACKUP_FILE, SQLITE_DB)
                init_db(SQLITE_DB)
            except Exception:
                init_db(SQLITE_DB)
        else:
            init_db(SQLITE_DB)


def save_db_users(data):
    with db_lock:
        try:
            conn = sqlite3.connect(SQLITE_DB, check_same_thread=False, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            c = conn.cursor()
            c.execute("BEGIN TRANSACTION")
            for uid, u in data.items():
                c.execute('''INSERT OR REPLACE INTO users (user_id,registered_date,total_scans,total_hits,today_scans,last_scan_date,referrals,referred_by,base_limit,username,first_name,membership,membership_expiry,user_threads,total_files,last_scan_time) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                    uid,
                    u.get('registered_date'),
                    u.get('total_scans', 0),
                    u.get('total_hits', 0),
                    u.get('today_scans', 0),
                    u.get('last_scan_date'),
                    u.get('referrals', 0),
                    u.get('referred_by'),
                    u.get('base_limit', 5000),
                    u.get('username'),
                    u.get('first_name'),
                    u.get('membership'),
                    u.get('membership_expiry'),
                    u.get('user_threads', 50),
                    u.get('total_files', 0),
                    u.get('last_scan_time'),
                ))
            conn.commit()
            conn.close()
        except Exception:
            pass


def save_db_rewards():
    with db_lock:
        try:
            conn = sqlite3.connect(SQLITE_DB, check_same_thread=False, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            c = conn.cursor()
            c.execute("BEGIN TRANSACTION")
            for u, rd in rewards_db.items():
                c.execute("INSERT OR REPLACE INTO rewards_data (user_id, last_daily, claimed_codes, temp_lines, temp_lines_expiry) VALUES (?,?,?,?,?)", (
                    u, rd.get("last_daily"), json.dumps(rd.get("claimed_codes", [])),
                    rd.get("temp_lines", 0), rd.get("temp_lines_expiry"),
                ))
            conn.commit()
            conn.close()
        except Exception:
            pass


def save_db_gift_codes():
    with db_lock:
        try:
            conn = sqlite3.connect(SQLITE_DB, check_same_thread=False, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            c = conn.cursor()
            c.execute("DELETE FROM gift_codes")
            for code, cd in gift_codes_db.items():
                c.execute("INSERT INTO gift_codes (code, reward_type, reward_value, max_uses, current_uses) VALUES (?,?,?,?,?)", (
                    code, cd['type'], cd['value'], cd['max'], cd['curr'],
                ))
            conn.commit()
            conn.close()
        except Exception:
            pass


def save_db_force_subs(data):
    with db_lock:
        try:
            conn = sqlite3.connect(SQLITE_DB, check_same_thread=False, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            c = conn.cursor()
            c.execute("DELETE FROM force_subs")
            for s in data:
                c.execute("INSERT INTO force_subs (sub_data) VALUES (?)", (s,))
            conn.commit()
            conn.close()
        except Exception:
            pass


def save_db_banned_users(data):
    with db_lock:
        try:
            conn = sqlite3.connect(SQLITE_DB, check_same_thread=False, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            c = conn.cursor()
            c.execute("DELETE FROM banned_users")
            for uid in data:
                c.execute("INSERT INTO banned_users (user_id) VALUES (?)", (uid,))
            conn.commit()
            conn.close()
        except Exception:
            pass


def save_threads_config():
    with db_lock:
        try:
            conn = sqlite3.connect(SQLITE_DB, check_same_thread=False, timeout=30)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            c = conn.cursor()
            c.execute("DELETE FROM threads_config")
            for k, v in CUSTOM_THREADS.items():
                c.execute("INSERT INTO threads_config (key,value) VALUES (?,?)", (k, v))
            conn.commit()
            conn.close()
        except Exception:
            pass


def save_license_keys():
    with db_lock:
        try:
            conn = sqlite3.connect(SQLITE_DB, check_same_thread=False, timeout=30)
            c = conn.cursor()
            c.execute("DELETE FROM license_keys")
            for k, d in license_keys_db.items():
                c.execute("INSERT INTO license_keys (key,plan,duration,created_at,created_by,used_by,used_at) VALUES (?,?,?,?,?,?,?)", (
                    k, d["plan"], d["duration"], d["created_at"], d["created_by"], d["used_by"], d["used_at"],
                ))
            conn.commit()
            conn.close()
        except Exception:
            pass


def save_payment_requests():
    with db_lock:
        try:
            conn = sqlite3.connect(SQLITE_DB, check_same_thread=False, timeout=30)
            c = conn.cursor()
            c.execute("DELETE FROM payment_requests")
            for r in payment_requests_db.values():
                c.execute("INSERT INTO payment_requests (req_id,user_id,username,plan,amount,receipt_id,status,created_at,decided_at) VALUES (?,?,?,?,?,?,?,?,?)", (
                    r["req_id"], r["user_id"], r["username"], r["plan"], r["amount"],
                    r["receipt_id"], r["status"], r["created_at"], r["decided_at"],
                ))
            conn.commit()
            conn.close()
        except Exception:
            pass


def save_db(data, db_file):
    if db_file == DB_FILE:
        save_db_users(data)
    elif db_file == FORCE_DB:
        save_db_force_subs(data)
    elif db_file == BANNED_DB:
        save_db_banned_users(data)


def migrate_json_to_sqlite():
    init_db()
    for fname, fn in [
        ('users_db.json', lambda d: save_db_users(d)),
        ('banned_users.json', lambda d: save_db_banned_users(d)),
        ('force_subscriptions.json', lambda d: save_db_force_subs(list(d.keys()) if isinstance(d, dict) else d)),
    ]:
        if os.path.exists(fname):
            try:
                with open(fname, 'r', encoding='utf-8') as f:
                    fn(json.load(f))
                os.rename(fname, fname + '.bak')
            except Exception:
                pass
    if os.path.exists('threads_config.json'):
        try:
            with open('threads_config.json', 'r', encoding='utf-8') as f:
                CUSTOM_THREADS.update(json.load(f))
                save_threads_config()
            os.rename('threads_config.json', 'threads_config.json.bak')
        except Exception:
            pass


def load_db_sqlite():
    try:
        conn = sqlite3.connect(SQLITE_DB, check_same_thread=False, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM users")
        db_dict = {}
        for row in c.fetchall():
            db_dict[row['user_id']] = {
                "registered_date": row['registered_date'],
                "total_scans": row['total_scans'],
                "total_hits": row['total_hits'],
                "today_scans": row['today_scans'],
                "last_scan_date": row['last_scan_date'],
                "referrals": row['referrals'],
                "referred_by": row['referred_by'],
                "base_limit": row['base_limit'],
                "username": row['username'],
                "first_name": row['first_name'],
                "membership": row['membership'],
                "membership_expiry": row['membership_expiry'],
                "user_threads": row['user_threads'] if row['user_threads'] is not None else 50,
                "total_files": row['total_files'] if row['total_files'] is not None else 0,
                "last_scan_time": row['last_scan_time'],
            }
        c.execute("SELECT sub_data FROM force_subs")
        fs = [row['sub_data'] for row in c.fetchall()]
        c.execute("SELECT user_id FROM banned_users")
        bu = [row['user_id'] for row in c.fetchall()]
        c.execute("SELECT key,value FROM threads_config")
        tc = {row['key']: row['value'] for row in c.fetchall()}
        c.execute("SELECT * FROM rewards_data")
        rd = {}
        for row in c.fetchall():
            tl = row['temp_lines'] if row['temp_lines'] is not None else 0
            rd[row['user_id']] = {
                "last_daily": row['last_daily'],
                "claimed_codes": json.loads(row['claimed_codes']) if row['claimed_codes'] else [],
                "temp_lines": tl,
                "temp_lines_expiry": row['temp_lines_expiry'],
            }
        c.execute("SELECT * FROM gift_codes")
        gd = {}
        for row in c.fetchall():
            gd[row['code']] = {
                "type": row['reward_type'], "value": row['reward_value'],
                "max": row['max_uses'], "curr": row['current_uses'],
            }
        lk = {}
        try:
            c.execute("SELECT * FROM license_keys")
            for row in c.fetchall():
                lk[row["key"]] = {
                    "key": row["key"], "plan": row["plan"], "duration": row["duration"],
                    "created_at": row["created_at"], "created_by": row["created_by"],
                    "used_by": row["used_by"], "used_at": row["used_at"],
                }
        except Exception:
            pass
        pr = {}
        try:
            c.execute("SELECT * FROM payment_requests")
            for row in c.fetchall():
                pr[row["req_id"]] = {
                    "req_id": row["req_id"], "user_id": row["user_id"],
                    "username": row["username"], "plan": row["plan"], "amount": row["amount"],
                    "receipt_id": row["receipt_id"], "status": row["status"],
                    "created_at": row["created_at"], "decided_at": row["decided_at"],
                }
        except Exception:
            pass
        conn.close()
        return db_dict, fs, bu, tc, rd, gd, lk, pr
    except Exception:
        return {}, [], [], {}, {}, {}, {}, {}


migrate_json_to_sqlite()
init_db_with_fallback()
db, force_subs, banned_users, loaded_threads_config, rewards_db, gift_codes_db, license_keys_db, payment_requests_db = load_db_sqlite()
CUSTOM_THREADS.update(loaded_threads_config)


def _plan_disp(pt):
    return {
        "basic": "⭐ BASIC",
        "semi_vip": "💠 SEMI VIP",
        "vip": "👑 VIP",
    }.get(pt, "⭐ BASIC")


def gen_license_key():
    return "MLBB-" + ''.join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=16))


def get_today_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_user(user_id):
    user_id, today = str(user_id), get_today_utc()
    if user_id not in db:
        db[user_id] = {
            "registered_date": today,
            "total_scans": 0,
            "total_hits": 0,
            "today_scans": 0,
            "last_scan_date": today,
            "referrals": 0,
            "referred_by": None,
            "base_limit": 5000,
            "username": None,
            "first_name": None,
            "membership": MembershipStatus.FREE.value,
            "membership_expiry": None,
            "user_threads": 100,  # [DRAKVEX_SPEED]
            "total_files": 0,
            "last_scan_time": None,
        }
        save_db(db, DB_FILE)
        return db[user_id], True
    if db[user_id]["last_scan_date"] != today:
        db[user_id]["today_scans"] = 0
        db[user_id]["last_scan_date"] = today
        save_db(db, DB_FILE)
    if db[user_id].get("membership_expiry"):
        try:
            if datetime.now(timezone.utc) > datetime.fromisoformat(db[user_id]["membership_expiry"]):
                db[user_id]["membership"] = MembershipStatus.FREE.value
                db[user_id]["membership_expiry"] = None
                mf = CUSTOM_THREADS.get("free", 50)
                if db[user_id].get("user_threads", 50) > mf:
                    db[user_id]["user_threads"] = mf
                save_db(db, DB_FILE)
        except Exception:
            pass
    return db[user_id], False


def update_user_info(user_id, from_user):
    try:
        user_id = str(user_id)
        username = from_user.username if from_user.username else "No username"
        first_name = from_user.first_name if from_user.first_name else "Unknown"
        if user_id in db:
            u = False
            if db[user_id].get("username") != username:
                db[user_id]["username"] = username
                u = True
            if db[user_id].get("first_name") != first_name:
                db[user_id]["first_name"] = first_name
                u = True
            if u:
                save_db(db, DB_FILE)
    except Exception:
        pass


def get_user_daily_limit(user_id):
    try:
        ud, _ = get_user(user_id)
        m = ud.get("membership")
        if str(user_id) == OWNER_ID:
            return float('inf')
        if m in (MembershipStatus.BASIC.value, MembershipStatus.SEMI_VIP.value, MembershipStatus.VIP.value):
            return float('inf')
        refs = ud.get("referrals", 0)
        base = 150 + (refs * 50)
        rd = rewards_db.get(str(user_id), {})
        tl = rd.get("temp_lines", 0)
        exp = rd.get("temp_lines_expiry")
        if tl > 0 and exp:
            try:
                if datetime.now(timezone.utc) > datetime.fromisoformat(exp):
                    rd["temp_lines"] = 0
                    rd["temp_lines_expiry"] = None
                    tl = 0
                    save_db_rewards()
            except Exception:
                pass
        return base + tl
    except Exception:
        return 5000


def get_file_max_lines(user_id):
    try:
        ud, _ = get_user(user_id)
        m = ud.get("membership")
        if str(user_id) == OWNER_ID:
            return float('inf')
        if m in (MembershipStatus.BASIC.value, MembershipStatus.SEMI_VIP.value, MembershipStatus.VIP.value):
            return float('inf')
        return 150
    except Exception:
        return 2500


def get_max_threads_for_user(user_data):
    try:
        m = user_data.get("membership")
        if str(user_data.get("user_id")) == OWNER_ID:
            return 300
        if m == MembershipStatus.BASIC.value:
            return CUSTOM_THREADS.get("basic", 150)
        if m == MembershipStatus.SEMI_VIP.value:
            return CUSTOM_THREADS.get("semi_vip", 200)
        if m == MembershipStatus.VIP.value:
            return CUSTOM_THREADS.get("vip", 250)
        return CUSTOM_THREADS.get("free", 100)  # [DRAKVEX_SPEED]
    except Exception:
        return 50


def get_user_thread_count(user_data):
    try:
        ut = user_data.get("user_threads", 100)  # [DRAKVEX_SPEED]
        ma = get_max_threads_for_user(user_data)
        if ut > ma:
            ut = ma
            user_data["user_threads"] = ut
            save_db(db, DB_FILE)
        return ut
    except Exception:
        return 50


class Job:
    def __init__(self, chat_id, file_name, combos, priority=False):
        self.job_id = str(uuid.uuid4())
        self.chat_id = str(chat_id)
        self.file_name = html.escape(file_name)
        self.combos = combos
        self.total = len(combos)
        self.checked = 0
        self.hits = 0
        self.bad = 0
        self.error = 0
        self.cpm = 0
        self.start_time = None
        self.status = 'Queued'
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.stop_flag = False
        self.hits_data = []
        self.bad_data = []
        self.msg_id = None
        self.processed_lines = 0
        self.priority = priority
        self.max_workers = 50


job_queue, current_jobs, jobs_lock = queue.Queue(), [], threading.Lock()


def is_user_busy(chat_id, user_data):
    try:
        chat_id = str(chat_id)
        m = user_data.get("membership")
        with jobs_lock:
            total = sum(1 for j in current_jobs if j.chat_id == chat_id and j.status in ['Running', 'Paused']) + sum(1 for j in list(job_queue.queue) if j.chat_id == chat_id)
            if chat_id == OWNER_ID:
                return total >= 5
            if m in [MembershipStatus.VIP.value, MembershipStatus.BASIC.value]:
                return total >= 3
            return total >= 1
    except Exception:
        return True


def get_active_jobs_count_free_only():
    c = 0
    try:
        with jobs_lock:
            for j in current_jobs:
                if j.status in ['Running', 'Paused']:
                    ud, _ = get_user(j.chat_id)
                    if ud.get("membership") == MembershipStatus.FREE.value and j.chat_id != OWNER_ID:
                        c += 1
    except Exception:
        pass
    return c


def trunc_name(fname):
    return fname[:15] + "...." if len(fname) > 15 else fname


def extract_ids(text):
    if not text:
        return []
    seen, out = set(), []
    for line in text.splitlines():
        line = line.strip().strip('"').strip("'")
        if not line or line.startswith('#') or line.startswith('//'):
            continue
        if DEVICE_ID_RE.fullmatch(line):
            key = line
        elif line.startswith(('and_', 'ios_')):
            key = line
        else:
            for m in DEVICE_ID_RE.findall(line):
                if m not in seen:
                    seen.add(m)
                    out.append(m)
            continue
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def check_id(line):
    line = str(line).strip()
    if not line:
        return False
    if DEVICE_ID_RE.fullmatch(line):
        return True
    if line.startswith(('and_', 'ios_')):
        return True
    return False


_hit_lock = threading.Lock()
_hit_counter = [0]


def _next_hit_idx():
    with _hit_lock:
        _hit_counter[0] += 1
        return _hit_counter[0]


def _fmt_n(v):
    try:
        return "{:,}".format(int(v))
    except Exception:
        return str(v)


def _v(x, d="-"):
    if x is None:
        return d
    s = str(x).strip()
    return s if s else d


def _field(k, v, kw=14):
    return "  " + str(k).ljust(kw) + str(v)


def _fmt_kda(lm):
    k = lm.get("kills", 0)
    d = lm.get("deaths", 0)
    a = lm.get("assists", 0)
    r = lm.get("kda_ratio", 0)
    return "%s/%s/%s  (%s)" % (k, d, a, r)


def format_hit_card(device_id, res, player):
    idx = _next_hit_idx()
    sb = player.get("skin_breakdown") or {}
    lm = player.get("last_match") or {}
    hh = player.get("hero_history") or []
    lhb = player.get("last_heroes_purchase") or []
    sh = player.get("skin_history") or []
    em = player.get("emblem_levels") or []
    top = "\u2501" * 48
    bot = "\u2500" * 48
    o = []
    o.append(top)
    o.append("  MLBB HIT  #%04d" % idx)
    o.append(top)
    o.append("")

    o.append("  ACCOUNT")
    o.append(_field("nick", _v(player.get("nickname"))))
    o.append(_field("account", _v(res.get("account_id"), "0")))
    o.append(_field("zone", _v(res.get("zone_id"), "0")))
    srv = player.get("server", 0)
    if srv:
        o.append(_field("server", srv))
    o.append(_field("level", _v(player.get("level"), "0")))
    o.append(_field("region", _v(player.get("region_country"))))
    if player.get("location"):
        o.append(_field("location", player.get("location")))
    o.append(_field("registered", _v(player.get("last_login_country"))))
    o.append("")

    o.append("  RANK")
    o.append(_field("current", _v(player.get("current_rank"), "Unranked")))
    o.append(_field("peak", _v(player.get("high_rank"), "Unranked")))
    ach = player.get("achievement_points", 0)
    if ach:
        o.append(_field("ach pts", _fmt_n(ach)))
    mcl = player.get("mcl_champion_wins", 0)
    if mcl:
        o.append(_field("mcl wins", _fmt_n(mcl)))
    o.append("")

    o.append("  COLLECTOR")
    o.append(_field("tier", _v(player.get("collector_tier"), "No Tier")))
    o.append(_field("points", _fmt_n(player.get("collector_point", 0))))
    o.append("")

    o.append("  PROGRESS")
    o.append(_field("battles", _fmt_n(player.get("total_battles", 0))))
    o.append(_field("matches", _fmt_n(player.get("matches", 0))))
    o.append(_field("win rate", _v(player.get("win_rate"))))
    rs = player.get("rating_score", 0)
    if rs:
        o.append(_field("rating", _fmt_n(rs)))
    o.append("")

    o.append("  WALLET")
    o.append(_field("diamonds", _fmt_n(player.get("diamonds", 0))))
    o.append(_field("battle pts", _fmt_n(player.get("battle_points", 0))))
    o.append(_field("tickets", _fmt_n(player.get("tickets", 0))))
    if player.get("credits_score"):
        o.append(_field("credits", player.get("credits_score")))
    o.append("")

    o.append("  INVENTORY")
    o.append(_field("heroes", _fmt_n(player.get("hero_count", 0))))
    o.append(_field("skins", _fmt_n(player.get("skin_count", 0))))
    o.append(_field("supreme", sb.get("Supreme Skins", 0)))
    o.append(_field("grand", sb.get("Grand Skins", 0)))
    o.append(_field("exquisite", sb.get("Exquisite Skins", 0)))
    o.append(_field("deluxe", sb.get("Deluxe Skins", 0)))
    o.append(_field("exceptional", sb.get("Exceptional Skins", 0)))
    o.append(_field("common", sb.get("Common Skins", 0)))
    o.append("")

    o.append("  DATES")
    o.append(_field("created", _v(player.get("creation_date"))))
    o.append(_field("age", _v(player.get("account_age"))))
    o.append(_field("last login", _v(player.get("last_login"))))
    ldp = player.get("last_diamond_purchase")
    if ldp:
        o.append(_field("last dia buy", ldp))
    o.append("")

    o.append("  SOCIAL")
    o.append(_field("followers", _fmt_n(player.get("followers", 0))))
    o.append(_field("likes", _fmt_n(player.get("likes", 0))))
    o.append(_field("affinity", _v(player.get("affinity"), "none")))
    o.append(_field("squad", _v(player.get("squad"))))
    if player.get("squad_motto"):
        o.append(_field("motto", player.get("squad_motto")))
    o.append("")

    o.append("  STATUS")
    o.append(_field("v2l", _v(player.get("v2l_status"), "Unknown")))
    o.append(_field("starlight", _v(player.get("starlight_user"), "No")))
    if player.get("starlight_expiry"):
        o.append(_field("sl expiry", player.get("starlight_expiry")))
    slm = player.get("starlight_months", 0)
    if slm:
        o.append(_field("sl months", slm))
    o.append(_field("restriction", _v(player.get("restriction_flags"), "None")))
    o.append("")

    if hh:
        o.append("  HERO HISTORY")
        o.append("    " + "  \u00b7  ".join(hh[:15]))
        o.append("")

    if lhb:
        o.append("  RECENT HEROES")
        o.append("    " + "  \u00b7  ".join(lhb))
        o.append("")

    if sh:
        o.append("  SKIN HISTORY")
        for entry in sh[:10]:
            o.append("    " + entry)
        o.append("")

    if em:
        o.append("  EMBLEMS")
        o.append("    " + "  \u00b7  ".join(em))
        o.append("")

    if lm:
        o.append("  LAST MATCH")
        o.append(_field("hero", _v(lm.get("hero"))))
        o.append(_field("kda", _fmt_kda(lm)))
        o.append(_field("result", _v(lm.get("result"))))
        o.append(_field("mode", _v(lm.get("mode"))))
        o.append(_field("duration", _v(lm.get("duration"))))
        if lm.get("gold"):
            o.append(_field("gold", _fmt_n(lm.get("gold"))))
        o.append(_field("mvp", "Yes" if lm.get("mvp") else "No"))
        if lm.get("played_at"):
            o.append(_field("played at", lm.get("played_at")))
        o.append("")

    if player.get("latest_skin_id"):
        o.append("  LATEST SKIN")
        o.append(_field("id", player.get("latest_skin_id")))
        if player.get("latest_skin_date"):
            o.append(_field("date", player.get("latest_skin_date")))
        o.append("")

    o.append("  DEVICE")
    o.append("    " + str(device_id))
    o.append("")
    o.append(bot)
    return "\n".join(o)


def format_banned_card(device_id, res, player):
    idx = _next_hit_idx()
    top = "\u2501" * 48
    bot = "\u2500" * 48
    o = []
    o.append(top)
    o.append("  BANNED  #%04d" % idx)
    o.append(top)
    o.append("")
    o.append("  ACCOUNT")
    o.append(_field("nick", _v(player.get("nickname"))))
    o.append(_field("account", _v(res.get("account_id"), "0")))
    o.append(_field("zone", _v(res.get("zone_id"), "0")))
    o.append(_field("level", _v(player.get("level"), "0")))
    o.append("")
    o.append("  BAN INFO")
    o.append(_field("reason", _v(player.get("ban_reason"))))
    o.append(_field("code", _v(player.get("ban_code"))))
    o.append(_field("duration", _v(player.get("ban_duration"))))
    o.append("")
    o.append("  DEVICE")
    o.append("    " + str(device_id))
    o.append("")
    o.append(bot)
    return "\n".join(o)


class MLBBChecker:
    def check_account(self, device_id):
        device_id = str(device_id).strip()
        if not check_id(device_id):
            return "BAD", []
        try:
            res = fetch_info_by_device(device_id)
        except Exception:
            return "ERROR", []
        st = res.get("status")
        if st != "success":
            return "BAD", []
        player = res.get("player") or {}
        if player.get("ban_status") == "BANNED":
            return "BANNED", [format_banned_card(device_id, res, player)]
        return "PREMIUM", [format_hit_card(device_id, res, player)]


def get_mode_description():
    return ("🎮 MLBB Mode\n"
            "✅ Device-ID based login\n"
            "✅ Shows account, zone, level, rank\n"
            "✅ Shows collector tier\n"
            "✅ Detects banned accounts\n"
            "✅ Powered by DRAKVEX engine")


def get_stats_text(job):
    mins, secs = divmod(int(time.time() - job.start_time) if job.start_time else 0, 60)
    if job.status == 'Paused':
        status_text = 'Scan Paused ⏸ (Auto-resume in 30s)'
    elif job.status in ['Stopped', 'Completed']:
        status_text = f'Scan {job.status} ✅'
    else:
        status_text = 'Scan In Progress 🔄'
    return (f"𖠵 <b>📊 {status_text}</b> 𖥻\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"➪ <b>📁 File:</b> <code>{trunc_name(job.file_name)}</code>\n"
            f"➪ <b>📊 Processed:</b> <code>{job.checked}/{job.total}</code>\n"
            f"➪ <b>🧵 Threads:</b> <code>{job.max_workers}</code>\n"
            f"➪ <b>📡 Mode:</b> 🎮 MLBB Checker\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ <b>HITS:</b> <code>{job.hits}</code>\n"
            f"🔴 <b>BANNED:</b> <code>{job.bad}</code>\n"
            f"⚠️ <b>ERROR:</b> <code>{job.error}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ <b>Elapsed:</b> <code>{f'{mins} min' if mins>0 else f'{secs} sec'}</code>\n"
            f"⚡ <b>CPM:</b> <code>{job.cpm}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"☰ <b>— Controls:</b>\n"
            f"︙ /pause - Pause\n"
            f"︙ /resume - Resume\n"
            f"︙ /stop - Stop and send results\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def get_job_markup(job):
    m = InlineKeyboardMarkup()
    if job.status == 'Running':
        m.row(InlineKeyboardButton("⏸ Pause", callback_data=f"job_pause_{job.job_id}", style="danger"))
    elif job.status == 'Paused':
        m.row(InlineKeyboardButton("▶️ Resume", callback_data=f"job_resume_{job.job_id}", style="success"))
    if job.status in ['Running', 'Paused']:
        m.row(InlineKeyboardButton("⏹ Stop", callback_data=f"job_stop_{job.job_id}", style="danger"))
    return m


def get_main_markup(message):
    m = InlineKeyboardMarkup(row_width=2)
    m.add(
        InlineKeyboardButton("📊 My Stats", callback_data="my_stats", style="primary"),
        InlineKeyboardButton("🔗 My Referrals", callback_data="referral_sys", style="primary"),
        InlineKeyboardButton("🎁 Rewards & Gifts", callback_data="rewards_menu", style="primary"),
        InlineKeyboardButton("💎 Membership", callback_data="membership_plans", style="primary"),
        InlineKeyboardButton("💳 Buy Plan", callback_data="buy_menu", style="success"),
        InlineKeyboardButton("📞 Support", callback_data="support_contact", style="primary"),
        InlineKeyboardButton("⚙️ Settings", callback_data="user_settings", style="primary"),
    )
    if str(message.chat.id) == OWNER_ID:
        m.add(InlineKeyboardButton("👑 Owner Panel", callback_data="owner_panel", style="danger"))
    return m


def pin_scan_message(chat_id, message_id):
    try:
        send_with_retry(bot.pin_chat_message, chat_id, message_id, disable_notification=True)
    except Exception:
        pass


def unpin_scan_message(chat_id, message_id):
    try:
        send_with_retry(bot.unpin_chat_message, chat_id, message_id)
    except Exception:
        pass


def auto_resume_job(job):
    time.sleep(30)
    if job.status == 'Paused':
        job.status = 'Running'
        job.pause_event.set()
        try:
            send_with_retry(bot.edit_message_text, get_stats_text(job), job.chat_id, job.msg_id, reply_markup=get_job_markup(job))
            send_with_retry(bot.send_message, job.chat_id, "▶️ <b>Scan Auto-Resumed</b>\n\n30 seconds have passed, scanning continues...")
        except Exception:
            pass


def update_ui_thread(job):
    last = ""
    while job.status in ['Running', 'Paused']:
        try:
            cur = get_stats_text(job)
            if cur != last:
                send_with_retry(bot.edit_message_text, cur, job.chat_id, job.msg_id, reply_markup=get_job_markup(job))
                last = cur
        except Exception:
            pass
        time.sleep(2)  # [DRAKVEX_SPEED]


def get_balanced_thread_count(chat_id, total_threads):
    try:
        with jobs_lock:
            active = sum(1 for j in current_jobs if j.chat_id == str(chat_id) and j.status in ['Running', 'Paused'])
        per = max(1, total_threads // max(active, 1))
        return per
    except Exception:
        return max(1, total_threads)


def run_job(job):
    try:
        job.status, job.start_time = 'Running', time.time()
        pin_scan_message(job.chat_id, job.msg_id)
        threading.Thread(target=update_ui_thread, args=(job,), daemon=True).start()
        user_data, _ = get_user(job.chat_id)
        total_threads = get_user_thread_count(user_data)
        job.max_workers = get_balanced_thread_count(job.chat_id, total_threads)
        _hit_counter[0] = 0
        chk = MLBBChecker()

        def process_combo(line):
            if job.stop_flag:
                return
            job.pause_event.wait()
            try:
                st, hits = chk.check_account(line)
                if st == "PREMIUM":
                    job.hits += 1
                    job.hits_data.extend(hits)
                elif st == "BANNED":
                    job.bad += 1
                    job.bad_data.append(hits[0] if hits else line)
                elif st == "BAD":
                    job.bad += 1
                else:
                    job.error += 1
                job.checked += 1
                job.processed_lines += 1
                el = time.time() - job.start_time
                if el > 0:
                    job.cpm = int((job.checked / el) * 60)
            except Exception:
                job.error += 1
                job.checked += 1

        with ThreadPoolExecutor(max_workers=job.max_workers) as ex:
            list(ex.map(process_combo, job.combos))

        if job.status != 'Stopped':
            job.status = 'Completed'
        try:
            send_with_retry(bot.edit_message_text, get_stats_text(job), job.chat_id, job.msg_id)
        except Exception:
            pass
        unpin_scan_message(job.chat_id, job.msg_id)
        user, _ = get_user(job.chat_id)
        user["total_hits"] += job.hits
        user["today_scans"] += job.processed_lines
        user["total_scans"] += job.processed_lines
        user["total_files"] = user.get("total_files", 0) + 1
        user["last_scan_time"] = datetime.now(timezone.utc).isoformat()
        save_db(db, DB_FILE)

        all_cards = job.hits_data + job.bad_data
        if all_cards:
            try:
                send_with_retry(bot.send_document, job.chat_id, document=("MLBB-Results.txt", "\n\n".join(all_cards).encode('utf-8')), caption=f"✅ <b>MLBB Scan Completed!</b>\n🎯 Hits: <code>{job.hits}</code>\n🔴 Banned: <code>{job.bad}</code>\n⚠️ Errors: <code>{job.error}</code>")
            except Exception:
                send_with_retry(bot.send_message, job.chat_id, f"✅ <b>MLBB Scan Completed!</b>\n🎯 Hits: <code>{job.hits}</code>\n🔴 Banned: <code>{job.bad}</code>")
        else:
            send_with_retry(bot.send_message, job.chat_id, f"✅ <b>Scan Completed for:</b> <code>{trunc_name(job.file_name)}</code>\n⚠️ No working accounts were found.")
    except Exception:
        pass


def worker_queue_processor():
    while not shutdown_flag:
        try:
            job = job_queue.get(timeout=1)
            with jobs_lock:
                current_jobs.append(job)
            try:
                run_job(job)
            except Exception:
                pass
            with jobs_lock:
                if job in current_jobs:
                    current_jobs.remove(job)
            job_queue.task_done()
        except queue.Empty:
            continue
        except Exception:
            time.sleep(1)


threading.Thread(target=worker_queue_processor, daemon=True).start()


def check_subscription(user_id):
    if not force_subs:
        return True
    for sub in force_subs:
        try:
            if bot.get_chat_member(sub.split('|')[0], user_id).status not in ['member', 'administrator', 'creator']:
                return False
        except Exception:
            return False
    return True


def get_ping():
    start = time.time()
    try:
        requests.get("https://api.telegram.org", timeout=3)
        return int((time.time() - start) * 1000)
    except Exception:
        return 0


def parse_time_duration(d):
    m = re.match(r'^(\d+)([hdm])$', d.lower().strip())
    if not m:
        return None
    v, u = int(m.group(1)), m.group(2)
    if u == 'h':
        return timedelta(hours=v)
    if u == 'd':
        return timedelta(days=v)
    if u == 'm':
        return timedelta(days=v * 30)
    return None


def create_backup():
    shutil.copyfile(SQLITE_DB, BACKUP_FILE)
    return BACKUP_FILE


def restore_backup(bf):
    global db, force_subs, banned_users, CUSTOM_THREADS, rewards_db, gift_codes_db, license_keys_db, payment_requests_db
    try:
        shutil.copyfile(bf, SQLITE_DB)
        d, f, b, t, rd, gd, lk, pr = load_db_sqlite()
        db.clear()
        db.update(d)
        force_subs.clear()
        force_subs.extend(f)
        banned_users.clear()
        banned_users.extend(b)
        CUSTOM_THREADS.update(t)
        rewards_db.clear()
        rewards_db.update(rd)
        gift_codes_db.clear()
        gift_codes_db.update(gd)
        license_keys_db.clear()
        license_keys_db.update(lk)
        payment_requests_db.clear()
        payment_requests_db.update(pr)
        return True
    except Exception:
        return False


def signal_handler(sig, frame):
    global shutdown_flag
    shutdown_flag = True
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


@bot.message_handler(content_types=['pinned_message'])
@retry_on_error
def delete_pinned_service_message(m):
    try:
        send_with_retry(bot.delete_message, m.chat.id, m.message_id)
    except Exception:
        pass


def cancel_current_operation(m):
    try:
        bot.clear_step_handler_by_chat_id(m.chat.id)
    except Exception:
        pass
    send_with_retry(bot.send_message, m.chat.id, "✅ Operation cancelled.")
    send_welcome(m)


@bot.my_chat_member_handler()
@retry_on_error
def handle_bot_block(message):
    if message.new_chat_member.status == 'kicked':
        try:
            send_with_retry(bot.send_message, OWNER_ID, f"⚠️ <b>User Blocked Bot!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🆔 ID: <code>{message.chat.id}</code>\n👤 Name: {message.chat.first_name}\n🔗 Username: @{message.chat.username or 'No username'}\n⏰ Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception:
            pass


@bot.message_handler(commands=['start'])
@retry_on_error
def send_welcome(m):
    user_id = str(m.chat.id)
    if user_id in banned_users:
        bot.reply_to(m, "🚫 <b>You have been banned from using this bot.</b>\n\nIf you think this is a mistake, contact the bot owner.")
        return
    user, is_new = get_user(user_id)
    update_user_info(user_id, m.from_user)
    if force_subs and not check_subscription(m.chat.id) and user_id != OWNER_ID:
        mk = InlineKeyboardMarkup()
        for sub in force_subs:
            try:
                cid = sub.split('|')[0]
                clink = sub.split('|')[1] if '|' in sub else None
                ch = bot.get_chat(cid)
                mk.add(InlineKeyboardButton(f"📢 {ch.title}", url=clink if clink else f"https://t.me/{ch.username}" if ch.username else f"https://t.me/c/{str(cid)[4:]}", style="primary"))
            except Exception:
                mk.add(InlineKeyboardButton("📢 Join Channel", url="https://t.me/", style="primary"))
        mk.add(InlineKeyboardButton("✅ Check Membership", callback_data="check_sub", style="success"))
        bot.reply_to(m, "<b>🔒 CHANNEL MEMBERSHIP REQUIRED</b>\n\nTo use this bot, you must join our channel first!\n\n👇 Click the button below to join, then press <b>✅ Check Membership.</b>", reply_markup=mk)
        return
    parts = m.text.split()
    if len(parts) > 1 and parts[1] != user_id and parts[1] in db and user["referred_by"] is None and is_new:
        user["referred_by"] = parts[1]
        db[parts[1]]["referrals"] += 1
        save_db(db, DB_FILE)
        send_with_retry(bot.send_message, parts[1], f"🎉 <b>Congratulations!</b>\nA new user joined via your link.\n🎁 Your Daily Limit increased by <b>+50 lines!</b>")
        send_with_retry(bot.send_message, m.chat.id, f"🎁 <b>Welcome!</b>\nYou joined via {parts[1]}'s referral link.\nYou have been added to the system successfully!")
        if parts[1] == OWNER_ID:
            send_with_retry(bot.send_message, OWNER_ID, f"🔔 <b>New User Joined!</b>\n\n👤 New User: @{m.from_user.username or 'No username'} (ID: {user_id})\n📅 Joined via owner link!")
    if user_id != OWNER_ID and is_new:
        send_with_retry(bot.send_message, OWNER_ID, f"<b>👤 New User Joined!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🆔 ID: <code>{user_id}</code>\n👤 Username: @{m.from_user.username or 'No username'}\n📅 Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    dl = get_user_daily_limit(user_id)
    rem = dl - user.get("today_scans", 0) if dl != float('inf') else "∞"
    dld = dl if dl != float('inf') else "∞"
    mem = user.get("membership", MembershipStatus.FREE.value)
    exp = user.get("membership_expiry")
    dl_left = " - "
    if exp:
        try:
            dl_left = f"{(datetime.fromisoformat(exp) - datetime.now(timezone.utc)).days} days"
        except Exception:
            pass
    ut = get_user_thread_count(user)
    mt = get_max_threads_for_user(user)
    bot.reply_to(m, f"𖠵 <b>WELCOME TO {BRAND}</b> 𖥻\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n➪ <b>📤 Send your MLBB device id list (.txt file)</b>\n︙ <i>Format: one device id per line</i>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n☰ <b>📊 Your Dashboard:</b>\n⌯ 🧵 Threads: <code>{ut} / {mt}</code>\n⌯ 👑 Plan: <code>{mem}</code>\n⌯ 📅 Days Left: <code>{dl_left}</code>\n⌯ 📈 Daily Limit: <code>{rem} / {dld} lines</code>\n⌯ 📡 Mode: <code>🎮 MLBB Checker</code>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n⦿ <b>Select an option from the menu below:</b>", reply_markup=get_main_markup(m))


@bot.message_handler(commands=['pause', 'resume', 'stop'])
@retry_on_error
def handle_scan_commands(m):
    user_id, cmd = str(m.chat.id), m.text[1:].lower()
    with jobs_lock:
        uj = next((job for job in current_jobs if job.chat_id == user_id and job.status in ['Running', 'Paused']), None)
    if not uj:
        bot.reply_to(m, "⚠️ <b>No active scan found.</b>\n\nPlease start a scan by sending a device id file first.")
        return
    if cmd == 'pause':
        if uj.status == 'Running':
            uj.status = 'Paused'
            uj.pause_event.clear()
            threading.Thread(target=auto_resume_job, args=(uj,), daemon=True).start()
            bot.reply_to(m, "⏸ <b>Scan Paused</b>\n\nScan will auto-resume after 30 seconds.\nUse /resume to resume immediately.")
        else:
            bot.reply_to(m, f"⚠️ <b>Scan is not running.</b>\nCurrent status: <code>{uj.status}</code>")
    elif cmd == 'resume':
        if uj.status == 'Paused':
            uj.status = 'Running'
            uj.pause_event.set()
            bot.reply_to(m, "▶️ <b>Scan Resumed</b>\n\nScanning continues...")
        else:
            bot.reply_to(m, f"⚠️ <b>No paused scan found.</b>\nCurrent status: <code>{uj.status}</code>")
    elif cmd == 'stop':
        if uj.status in ['Running', 'Paused']:
            uj.status = 'Stopped'
            uj.stop_flag = True
            uj.pause_event.set()
            unpin_scan_message(uj.chat_id, uj.msg_id)
            bot.reply_to(m, "⏹ <b>Scan Stopped</b>\n\nResults will be sent shortly.")


@bot.message_handler(content_types=['document'])
@retry_on_error
def handle_document(m):
    user_id = str(m.chat.id)
    is_owner = user_id == OWNER_ID
    if user_id in banned_users:
        bot.reply_to(m, "🚫 <b>You have been banned from using this bot.</b>")
        return
    if not BOT_RUNNING and not is_owner:
        bot.reply_to(m, "⚠️ <b>Bot is currently under maintenance.</b>\nPlease try again later.")
        return
    if force_subs and not check_subscription(m.chat.id) and not is_owner:
        mk = InlineKeyboardMarkup()
        for sub in force_subs:
            try:
                cid = sub.split('|')[0]
                clink = sub.split('|')[1] if '|' in sub else None
                ch = bot.get_chat(cid)
                mk.add(InlineKeyboardButton(f"📢 {ch.title}", url=clink if clink else f"https://t.me/{ch.username}" if ch.username else f"https://t.me/c/{str(cid)[4:]}", style="primary"))
            except Exception:
                mk.add(InlineKeyboardButton("📢 Join Channel", url="https://t.me/", style="primary"))
        mk.add(InlineKeyboardButton("✅ Check Membership", callback_data="check_sub", style="success"))
        bot.reply_to(m, "<b>🔒 CHANNEL MEMBERSHIP REQUIRED</b>\n\nTo join our channel, press the button below, then <b>✅ Check Membership.</b>", reply_markup=mk)
        return
    try:
        if m.document.file_size > 5 * 1024 * 1024:
            bot.reply_to(m, "❌ <b>Error!</b> The file size exceeds the 5MB maximum limit.")
            return
        user, _ = get_user(user_id)
        update_user_info(user_id, m.from_user)
        mem = user.get("membership")
        is_mem = mem != MembershipStatus.FREE.value
        if not is_owner and is_user_busy(user_id, user):
            bot.reply_to(m, "⚠️ <b>Warning!</b> You already have 3 files in progress. Please wait." if mem in [MembershipStatus.VIP.value, MembershipStatus.BASIC.value] else "⚠️ <b>Warning!</b> You already have a file in progress or queue.")
            return
        raw = bot.download_file(bot.get_file(m.document.file_id).file_path)
        try:
            text = raw.decode('utf-8', 'ignore')
        except Exception:
            text = raw.decode('latin-1', 'ignore')
        vc = extract_ids(text)
        if not vc:
            bot.reply_to(m, "❌ <b>Error!</b> The file does not contain valid <code>MLBB device IDs</code>.")
            return
        fml = get_file_max_lines(user_id)
        if not is_owner and len(vc) > fml:
            bot.reply_to(m, f"❌ <b>Error!</b> Maximum allowed lines per file for your plan is <code>{fml}</code>. Your file contains <code>{len(vc)}</code> lines.")
            return
        dl = get_user_daily_limit(user_id)
        if not is_owner and dl != float('inf'):
            rl = dl - user["today_scans"]
            if rl <= 0:
                bot.reply_to(m, f"🚫 <b>Daily Limit Exceeded!</b>\nYou have reached your max limit of <code>{dl}</code> lines today.\n\n💡 <i>Invite friends to get +500 lines!</i>", reply_markup=get_main_markup(m))
                return
            if len(vc) > rl:
                send_with_retry(bot.send_message, m.chat.id, f"⚠️ <b>Notice:</b> Your file contains <code>{len(vc)}</code> lines, but you only have <code>{rl}</code> left.\n✂️ <i>Processing only {rl} lines.</i>")
                vc = vc[:rl]
        nj = Job(m.chat.id, m.document.file_name, vc, is_mem or is_owner)
        msg = send_with_retry(bot.send_message, m.chat.id, "⏳ <i>Adding file to the queue...</i>")
        nj.msg_id = msg.message_id
        if is_mem or is_owner:
            send_with_retry(bot.edit_message_text, "✅ <b>File accepted! Starting scan now (Priority Mode) using MLBB Checker...</b>", m.chat.id, msg.message_id)
            with jobs_lock:
                current_jobs.append(nj)
            threading.Thread(target=run_job, args=(nj,), daemon=True).start()
        else:
            job_queue.put(nj)
            send_with_retry(bot.edit_message_text, f"✅ <b>File accepted!</b>\nYour position in queue: <code>{job_queue.qsize()}</code>\nMode: 🎮 MLBB Checker", m.chat.id, msg.message_id)
        if not is_owner:
            send_with_retry(bot.send_message, OWNER_ID, f"<b>👤 User Started Scan!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🆔 ID: <code>{user_id}</code>\n👤 Username: @{m.from_user.username or 'No username'}\n📁 File: {m.document.file_name}\n📊 Lines: {len(vc)}\n👑 Membership: {user.get('membership','FREE')}\n🔍 Mode: 🎮 MLBB\n⏰ Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception as e:
        bot.reply_to(m, f"❌ <b>An error occurred:</b> <code>{str(e)}</code>")


@bot.callback_query_handler(func=lambda call: True)
@retry_on_error
def handle_query(c):
    global BOT_RUNNING
    d, uid = c.data, str(c.message.chat.id)
    if uid in banned_users:
        bot.answer_callback_query(c.id, "You are banned.")
        return
    user, _ = get_user(uid)
    update_user_info(uid, c.from_user)

    if d == "check_sub":
        bot.answer_callback_query(c.id, "Checking...", show_alert=False)
        if check_subscription(c.message.chat.id):
            bot.answer_callback_query(c.id, "✅ Verification successful!", show_alert=True)
            dl = get_user_daily_limit(uid)
            dld = dl if dl != float('inf') else "∞"
            rem = dl - user.get("today_scans", 0) if dl != float('inf') else "∞"
            mem = user.get("membership", MembershipStatus.FREE.value)
            exp = user.get("membership_expiry")
            dlt = " - "
            if exp:
                try:
                    dlt = f"{(datetime.fromisoformat(exp) - datetime.now(timezone.utc)).days} days"
                except Exception:
                    pass
            ut = get_user_thread_count(user)
            mt = get_max_threads_for_user(user)
            try:
                send_with_retry(bot.edit_message_text, f"𖠵 <b>WELCOME TO {BRAND}</b> 𖥻\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n➪ <b>📤 Send your MLBB device id list (.txt file)</b>\n︙ <i>Format: one device id per line</i>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n☰ <b>📊 Your Dashboard:</b>\n⌯ 🧵 Threads: <code>{ut} / {mt}</code>\n⌯ 👑 Plan: <code>{mem}</code>\n⌯ 📅 Days Left: <code>{dlt}</code>\n⌯ 📈 Daily Limit: <code>{rem} / {dld} lines</code>\n⌯ 📡 Mode: <code>🎮 MLBB Checker</code>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n⦿ <b>Select an option from the menu below:</b>", c.message.chat.id, c.message.message_id, reply_markup=get_main_markup(c.message))
            except Exception:
                pass
        else:
            mk = InlineKeyboardMarkup()
            for sub in force_subs:
                try:
                    cid = sub.split('|')[0]
                    clink = sub.split('|')[1] if '|' in sub else None
                    ch = bot.get_chat(cid)
                    mk.add(InlineKeyboardButton(f"📢 {ch.title}", url=clink if clink else f"https://t.me/{ch.username}" if ch.username else f"https://t.me/c/{str(cid)[4:]}", style="primary"))
                except Exception:
                    mk.add(InlineKeyboardButton("📢 Join Channel", url="https://t.me/", style="primary"))
            mk.add(InlineKeyboardButton("✅ Check Membership", callback_data="check_sub", style="success"))
            try:
                send_with_retry(bot.edit_message_text, "<b>🔒 CHANNEL MEMBERSHIP REQUIRED</b>\n\nTo use this bot, you must join our channel first!\n\n👇 Click the button below to join, then press ✅ Check Membership.", c.message.chat.id, c.message.message_id, reply_markup=mk)
            except Exception:
                pass
            bot.answer_callback_query(c.id, "❌ You are not subscribed to all required channels.")
        return

    if d == "buy_menu":
        bot.answer_callback_query(c.id)
        txt = ("💳 PURCHASE MEMBERSHIP\n\n"
               "💠 Payment Method: GCash\n"
               "👤 Name: JO****E D.\n"
               "📱 Number: 09301319429\n\n"
               "⚠️ After paying, send a photo of your receipt.\n"
               "Admin will review and send your license key.\n\n"
               "⭐ BASIC - 100 pesos / 3 days unlimited\n"
               "💠 SEMI VIP - 200 pesos / 7 days unlimited\n"
               "👑 VIP - 300 pesos / lifetime unlimited")
        mk = InlineKeyboardMarkup(row_width=1)
        mk.add(InlineKeyboardButton("⭐ Buy BASIC - 100", callback_data="buy_basic", style="success"))
        mk.add(InlineKeyboardButton("💠 Buy SEMI VIP - 200", callback_data="buy_semi_vip", style="success"))
        mk.add(InlineKeyboardButton("👑 Buy VIP - 300", callback_data="buy_vip", style="success"))
        mk.add(InlineKeyboardButton("🔑 Redeem License Key", callback_data="redeem_key_prompt", style="primary"))
        mk.add(InlineKeyboardButton("🔙 Back", callback_data="back_home", style="danger"))
        try:
            send_with_retry(bot.edit_message_text, txt, c.message.chat.id, c.message.message_id, reply_markup=mk)
        except Exception:
            pass
        return

    if d == "buy_basic":
        bot.answer_callback_query(c.id)
        msg = send_with_retry(bot.send_message, c.message.chat.id, "⭐ BASIC - 100 pesos (3 Days Unlimited)\n\nSend a photo of your GCash receipt now.\n\nSend /cancel to abort.")
        if msg:
            bot.register_next_step_handler(msg, process_payment_receipt, "basic")
        return

    if d == "buy_semi_vip":
        bot.answer_callback_query(c.id)
        msg = send_with_retry(bot.send_message, c.message.chat.id, "💠 SEMI VIP - 200 pesos (7 Days Unlimited)\n\nSend a photo of your GCash receipt now.\n\nSend /cancel to abort.")
        if msg:
            bot.register_next_step_handler(msg, process_payment_receipt, "semi_vip")
        return

    if d == "buy_vip":
        bot.answer_callback_query(c.id)
        msg = send_with_retry(bot.send_message, c.message.chat.id, "👑 VIP - 300 pesos (LIFETIME Unlimited)\n\nSend a photo of your GCash receipt now.\n\nSend /cancel to abort.")
        if msg:
            bot.register_next_step_handler(msg, process_payment_receipt, "vip")
        return

    if d == "redeem_key_prompt":
        bot.answer_callback_query(c.id)
        msg = send_with_retry(bot.send_message, c.message.chat.id, "Redeem License Key\n\nSend your key now.\n\nSend /cancel to abort.")
        if msg:
            bot.register_next_step_handler(msg, process_redeem_key)
        return

    if d.startswith("pay_approve_"):
        bot.answer_callback_query(c.id, "Approved.")
        process_admin_approve(c, d.replace("pay_approve_", ""))
        return

    if d.startswith("pay_reject_"):
        bot.answer_callback_query(c.id, "Rejected.")
        process_admin_reject(c, d.replace("pay_reject_", ""))
        return

    if d == "manage_keys":
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        mk = InlineKeyboardMarkup(row_width=1)
        mk.add(InlineKeyboardButton("Generate BASIC Key", callback_data="keygen_basic", style="success"))
        mk.add(InlineKeyboardButton("Generate SEMI VIP Key", callback_data="keygen_semi_vip", style="success"))
        mk.add(InlineKeyboardButton("Generate VIP Key", callback_data="keygen_vip", style="success"))
        mk.add(InlineKeyboardButton("🔧 Custom Key Generator", callback_data="keygen_custom", style="success"))
        mk.add(InlineKeyboardButton("List Active Keys", callback_data="list_keys", style="primary"))
        mk.add(InlineKeyboardButton("Back", callback_data="owner_panel", style="danger"))
        try:
            send_with_retry(bot.edit_message_text, "License Key Manager\n\nGenerate, list, and manage keys below.", c.message.chat.id, c.message.message_id, reply_markup=mk)
        except Exception:
            pass
        return

    if d == "keygen_custom":
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        mk = InlineKeyboardMarkup(row_width=1)
        mk.add(
            InlineKeyboardButton("⭐ BASIC", callback_data="custkey_basic", style="success"),
            InlineKeyboardButton("💠 SEMI VIP", callback_data="custkey_semi_vip", style="success"),
            InlineKeyboardButton("👑 VIP", callback_data="custkey_vip", style="success"),
            InlineKeyboardButton("🔙 Cancel", callback_data="manage_keys", style="danger"),
        )
        try:
            send_with_retry(bot.edit_message_text, "🔧 <b>Custom Key Generator</b>\n\nStep 1/3 — Choose a plan for the keys:", c.message.chat.id, c.message.message_id, reply_markup=mk)
        except Exception:
            pass
        return

    if d in ("custkey_basic", "custkey_semi_vip", "custkey_vip"):
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        plan = d.replace("custkey_", "")
        msg = send_with_retry(bot.send_message, c.message.chat.id,
            f"🔧 <b>Custom Key Generator</b>\n\nPlan: <code>{plan.upper()}</code>\n\nStep 2/3 — Send the duration (e.g. <code>1h</code>, <code>3d</code>, <code>7d</code>, <code>30d</code>, <code>36500d</code>):\n\nSend /cancel to abort.")
        if msg:
            bot.register_next_step_handler(msg, process_custom_key_duration, plan)
        return

    if d.startswith("keygen_"):
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        plan = d.replace("keygen_", "")
        duration = {"basic": "3d", "semi_vip": "7d", "vip": "36500d"}.get(plan, "3d")
        key = gen_license_key()
        license_keys_db[key] = {"key": key, "plan": plan, "duration": duration, "created_at": datetime.now(timezone.utc).isoformat(), "created_by": OWNER_ID, "used_by": None, "used_at": None}
        save_license_keys()
        send_with_retry(bot.send_message, c.message.chat.id, "Key Generated\n\n" + key + "\nPlan: " + plan.upper() + "\nDuration: " + duration)
        return

    if d == "list_keys":
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        active = [k for k, v in license_keys_db.items() if not v["used_by"]]
        used = [k for k, v in license_keys_db.items() if v["used_by"]]
        txt = "License Keys\n\nActive: " + str(len(active)) + "\nUsed: " + str(len(used)) + "\n\n"
        for k in active[:25]:
            v = license_keys_db[k]
            txt += k + " - " + v["plan"].upper() + " (" + v["duration"] + ")\n"
        if len(active) > 25:
            txt += "and " + str(len(active) - 25) + " more\n"
        try:
            send_with_retry(bot.edit_message_text, txt, c.message.chat.id, c.message.message_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("Back", callback_data="manage_keys", style="danger")))
        except Exception:
            pass
        return

    if d == "rewards_menu":
        bot.answer_callback_query(c.id)
        now = datetime.now(timezone.utc)
        rd = rewards_db.get(uid, {"last_daily": None, "claimed_codes": [], "temp_lines": 0, "temp_lines_expiry": None})
        last_daily = rd.get("last_daily")
        ready = True
        time_str = "🟢 Ready to Claim!"
        if last_daily:
            last_date = datetime.fromisoformat(last_daily)
            diff = (now - last_date).total_seconds()
            if diff < 86400:
                ready = False
                rem = int(86400 - diff)
                h, r = divmod(rem, 3600)
                m, s = divmod(r, 60)
                time_str = f"⏳ {h:02d}:{m:02d}:{s:02d}"
        txt = f"𖠵 <b>🎁 Rewards & Gifts Hub</b> 𖥻\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\nClaim your daily free lines or redeem premium gift codes provided by the admin.\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n☰ <b>📊 Your Daily Statistics:</b>\n⌯ Next Reward In: <code>{time_str}</code>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        mk = InlineKeyboardMarkup(row_width=1)
        if ready:
            mk.add(InlineKeyboardButton("🎁 Claim Daily Reward", callback_data="claim_daily"))
        else:
            mk.add(InlineKeyboardButton(f"⏳ Unlocks in: {time_str}", callback_data="none"))
        mk.add(InlineKeyboardButton("🎟 REDEEM GIFT CODE", callback_data="redeem_code_prompt"), InlineKeyboardButton("🔙 Back", callback_data="back_home"))
        try:
            send_with_retry(bot.edit_message_text, txt, c.message.chat.id, c.message.message_id, reply_markup=mk)
        except Exception:
            pass
        return

    if d == "cancel_to_rewards":
        bot.answer_callback_query(c.id)
        try:
            bot.clear_step_handler_by_chat_id(c.message.chat.id)
        except Exception:
            pass
        now = datetime.now(timezone.utc)
        rd = rewards_db.get(uid, {"last_daily": None, "claimed_codes": [], "temp_lines": 0, "temp_lines_expiry": None})
        last_daily = rd.get("last_daily")
        ready = True
        time_str = "🟢 Ready to Claim!"
        if last_daily:
            last_date = datetime.fromisoformat(last_daily)
            diff = (now - last_date).total_seconds()
            if diff < 86400:
                ready = False
                rem = int(86400 - diff)
                h, r = divmod(rem, 3600)
                m, s = divmod(r, 60)
                time_str = f"⏳ {h:02d}:{m:02d}:{s:02d}"
        txt = f"𖠵 <b>🎁 Rewards & Gifts Hub</b> 𖥻\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\nClaim your daily free lines or redeem premium gift codes provided by the admin.\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n☰ <b>📊 Your Daily Statistics:</b>\n⌯ Next Reward In: <code>{time_str}</code>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        mk = InlineKeyboardMarkup(row_width=1)
        if ready:
            mk.add(InlineKeyboardButton("🎁 Claim Daily Reward", callback_data="claim_daily"))
        else:
            mk.add(InlineKeyboardButton(f"⏳ Unlocks in: {time_str}", callback_data="none"))
        mk.add(InlineKeyboardButton("🎟 REDEEM GIFT CODE", callback_data="redeem_code_prompt"), InlineKeyboardButton("🔙 Back", callback_data="back_home"))
        try:
            send_with_retry(bot.edit_message_text, txt, c.message.chat.id, c.message.message_id, reply_markup=mk)
        except Exception:
            pass
        return

    if d == "cancel_to_settings":
        bot.answer_callback_query(c.id)
        try:
            bot.clear_step_handler_by_chat_id(c.message.chat.id)
        except Exception:
            pass
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(InlineKeyboardButton("🧵 Set Threads", callback_data="set_threads", style="primary"), InlineKeyboardButton("🔙 Back", callback_data="back_home", style="danger"))
        try:
            send_with_retry(bot.edit_message_text, f"𖠵 <b>⚙️ Settings Menu</b> 𖥻\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n➪ <b>🧵 Threads:</b> Control scan speed\n︙ Current: <code>{get_user_thread_count(user)}</code> threads\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n<i>Click a button to configure:</i>", c.message.chat.id, c.message.message_id, reply_markup=mk)
        except Exception:
            pass
        return

    if d == "claim_daily":
        now = datetime.now(timezone.utc)
        rd = rewards_db.get(uid, {"last_daily": None, "claimed_codes": [], "temp_lines": 0, "temp_lines_expiry": None})
        last_daily = rd.get("last_daily")
        if last_daily:
            last_date = datetime.fromisoformat(last_daily)
            if (now - last_date).total_seconds() < 86400:
                bot.answer_callback_query(c.id, "⚠️ You already claimed your daily reward today! Come back tomorrow.", show_alert=True)
                return
        reward_amount = 25
        current_temp = rd.get("temp_lines", 0)
        exp = rd.get("temp_lines_expiry")
        if exp and now > datetime.fromisoformat(exp):
            current_temp = 0
        rd["temp_lines"] = current_temp + reward_amount
        rd["temp_lines_expiry"] = (now + timedelta(days=1)).isoformat()
        rd["last_daily"] = now.isoformat()
        rewards_db[uid] = rd
        save_db_rewards()
        bot.answer_callback_query(c.id, f"🎉 Congratulations! You received +{reward_amount} lines (Valid for 24H).", show_alert=True)
        time_str = "⏳ 23:59:59"
        txt = f"𖠵 <b>🎁 Rewards & Gifts Hub</b> 𖥻\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\nClaim your daily free lines or redeem premium gift codes provided by the admin.\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n☰ <b>📊 Your Daily Statistics:</b>\n⌯ Next Reward In: <code>{time_str}</code>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        mk = InlineKeyboardMarkup(row_width=1)
        mk.add(InlineKeyboardButton(f"⏳ Unlocks in: {time_str}", callback_data="none"))
        mk.add(InlineKeyboardButton("🎟 REDEEM GIFT CODE", callback_data="redeem_code_prompt"), InlineKeyboardButton("🔙 Back", callback_data="back_home"))
        try:
            send_with_retry(bot.edit_message_text, txt, c.message.chat.id, c.message.message_id, reply_markup=mk)
        except Exception:
            pass
        try:
            send_with_retry(bot.send_message, OWNER_ID, f"🎁 <b>Daily Reward Claimed!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n👤 User ID: <code>{uid}</code>\n🔗 Username: @{user.get('username') or 'None'}\n📈 Reward: <b>+{reward_amount} lines</b>\n⏰ Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception:
            pass
        return

    if d == "redeem_code_prompt":
        bot.answer_callback_query(c.id)
        txt = "🎟 <b>GIFT CODE REDEMPTION</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\nPlease enter the gift code you received to claim your reward.\n\n📌 <b>Format:</b> GIF-XXXXXXXX\n\n💬 Send the code now.\n• or send /cancel to abort."
        mk = InlineKeyboardMarkup(row_width=1).add(InlineKeyboardButton("🔙 Back", callback_data="cancel_to_rewards"))
        msg = send_with_retry(bot.edit_message_text, txt, c.message.chat.id, c.message.message_id, reply_markup=mk)
        if msg:
            try:
                bot.clear_step_handler_by_chat_id(c.message.chat.id)
            except Exception:
                pass
            bot.register_next_step_handler(msg, process_redeem_code)
        return

    if d == "manage_gifts":
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        txt = "<b>🎁 Generate Gift Code</b>\n\nSelect what type of gift you want to create:"
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(InlineKeyboardButton("⭐ BASIC Sub", callback_data="gen_code_basic"), InlineKeyboardButton("💠 SEMI VIP Sub", callback_data="gen_code_semi_vip"))
        mk.add(InlineKeyboardButton("👑 VIP Sub", callback_data="gen_code_vip"), InlineKeyboardButton("📈 Extra Lines", callback_data="gen_code_lines"))
        mk.add(InlineKeyboardButton("🛑 Revoke All Codes", callback_data="revoke_all_codes"), InlineKeyboardButton("🔙 Back", callback_data="owner_panel"))
        try:
            send_with_retry(bot.edit_message_text, txt, c.message.chat.id, c.message.message_id, reply_markup=mk)
        except Exception:
            pass
        return

    if d.startswith("gen_code_"):
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        rtype = d[len("gen_code_"):]
        txt = "<b>⚙️ CODE GENERATION (Step 1/2)</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n👥 <b>Usage Limit Setup</b>\n\n<i>How many users should be able to redeem this specific code?</i>\n\n💬 <b>Action:</b> Send a number (e.g., <code>1</code>, <code>5</code>, <code>100</code>) or /cancel"
        msg = send_with_retry(bot.send_message, c.message.chat.id, txt)
        bot.register_next_step_handler(msg, process_gen_code_step1, rtype)
        return

    if d == "revoke_all_codes":
        if uid != OWNER_ID:
            return
        gift_codes_db.clear()
        save_db_gift_codes()
        bot.answer_callback_query(c.id, "🛑 All gift codes deactivated!", show_alert=True)
        return

    if d == "membership_plans":
        bot.answer_callback_query(c.id)
        txt = (f"𝗥 <b>👑 MEMBERSHIP PLANS</b> 𝗧\n"
               f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
               f"➪ <b>🆓 FREE PLAN</b>\n"
               f"︙ Daily Limit: 150 lines\n"
               f"︙ +50 lines per referral\n"
               f"︙ Max Threads: 1-{CUSTOM_THREADS.get('free',50)}\n"
               f"︙ Single scan at a time\n"
               f"︙ Queue Waiting System\n"
               f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
               f"➪ <b>⭐ BASIC PLAN (3 DAYS)</b>\n"
               f"︙ Duration: 3 Days\n"
               f"︙ Unlimited lines\n"
               f"︙ Max Threads: 1-{CUSTOM_THREADS.get('basic',75)}\n"
               f"︙ No Queue Waiting\n"
               f"<b>— Price: 100 pesos</b>\n"
               f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
               f"➪ <b>💠 SEMI VIP PLAN (7 DAYS)</b>\n"
               f"︙ Duration: 7 Days\n"
               f"︙ Unlimited lines\n"
               f"︙ Max Threads: 1-{CUSTOM_THREADS.get('semi_vip',100)}\n"
               f"︙ No Queue Waiting\n"
               f"<b>— Price: 200 pesos</b>\n"
               f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
               f"➪ <b>👑 VIP PLAN (LIFETIME)</b>\n"
               f"︙ Duration: Lifetime\n"
               f"︙ Unlimited lines\n"
               f"︙ Max Threads: 1-{CUSTOM_THREADS.get('vip',125)}\n"
               f"︙ No Queue Waiting\n"
               f"<b>— Price: 300 pesos</b>\n"
               f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
               f"⦿ <b>Your Current Plan:</b> <code>{user.get('membership',MembershipStatus.FREE.value)}</code>\n\n"
               f"💳 <b>PAYMENT METHOD (GCash)</b>\n"
               f"︙ Name: <b>JO****E D.</b>\n"
               f"︙ Number: <code>09301319429</code>\n\n"
               f"📌 <b>How to purchase:</b>\n"
               f"︙ Send payment via GCash to the number above\n"
               f"︙ Take a screenshot of your receipt\n"
               f"︙ Click Buy Plan and choose your plan\n"
               f"︙ Send the receipt photo to the bot\n"
               f"︙ Wait for admin approval\n"
               f"︙ Redeem your license key\n")
        mk = InlineKeyboardMarkup(row_width=1)
        mk.add(InlineKeyboardButton("💳 Buy Plan", callback_data="buy_menu", style="success"))
        mk.add(InlineKeyboardButton("🔙 Back", callback_data="back_home", style="danger"))
        try:
            send_with_retry(bot.edit_message_text, txt, c.message.chat.id, c.message.message_id, reply_markup=mk)
        except Exception:
            pass
        return

    if d == "support_contact":
        bot.answer_callback_query(c.id)
        try:
            send_with_retry(bot.edit_message_text, f"𖠵 <b>📞 Support & Contact</b> 𖥻\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n<i>Need help or want to upgrade?</i>\n\n➪ Contact: <a href=\"{SUPPORT_URL}\">@{SUPPORT_HANDLE}</a>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n", c.message.chat.id, c.message.message_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Back", callback_data="back_home", style="danger")))
        except Exception:
            pass
        return

    if d == "my_stats":
        bot.answer_callback_query(c.id)
        dl = get_user_daily_limit(uid)
        dld = dl if dl != float('inf') else "∞ (Owner/VIP)"
        rem = dl - user["today_scans"] if dl != float('inf') else "∞"
        sr = f"{(user['total_hits']/user['total_scans']*100):.2f}" if user['total_scans'] > 0 else "0.00"
        mem = user.get("membership", MembershipStatus.FREE.value)
        exp = user.get("membership_expiry", None)
        expt = "N/A"
        if exp:
            try:
                expt = datetime.fromisoformat(exp).strftime("%Y-%m-%d")
            except Exception:
                expt = "Invalid"
        rd = rewards_db.get(uid, {})
        claimed_codes_count = len(rd.get("claimed_codes", []))
        now = datetime.now(timezone.utc)
        used_today = "No"
        last_d = rd.get("last_daily")
        if last_d and (now - datetime.fromisoformat(last_d)).total_seconds() < 86400:
            used_today = "Yes"
        valid_temp = 0
        if rd.get("temp_lines", 0) > 0 and rd.get("temp_lines_expiry"):
            if now < datetime.fromisoformat(rd["temp_lines_expiry"]):
                valid_temp = rd["temp_lines"]
        base_plan_limit = 25000 if user.get("membership") == MembershipStatus.BASIC.value else (float('inf') if user.get("membership") == MembershipStatus.VIP.value else 5000)
        ref_lines = user.get('referrals', 0) * 50
        txt = f"""𖠵 <b>📊 Your Statistics</b> 𖥻
━━━━━━━━━━━━━━━━━━━━━━━━━━━
➪ <b>👤 User ID:</b> <code>{uid}</code>
➪ <b>📅 Registered:</b> <code>{user['registered_date']}</code>
➪ <b>👑 Plan:</b> {mem}
➪ <b>📅 Expires:</b> {expt}
➪ <b>📡 Mode:</b> 🎮 MLBB
━━━━━━━━━━━━━━━━━━━━━━━━━━━
➪ <b>🧵 Threads:</b> <code>{get_user_thread_count(user)} / {get_max_threads_for_user(user)}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━━
☰ <b>📈 General Statistics:</b>
⌯ ✅ Total Scans: <code>{user['total_scans']}</code>
⌯ 💎 Total Hits: <code>{user['total_hits']}</code>
⌯ 🎯 Success Rate: <code>{sr}%</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━━
☰ <b>📊 Today's Statistics:</b>
⌯ 📊 Scans Used: <code>{user['today_scans']}</code>
⌯ ⏳ Remaining: <code>{rem} / {dld}</code>
⌯ 👥 Referrals: <code>{user.get('referrals', 0)}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━━
☰ <b>🎁 Rewards & Limits Details:</b>
⌯ 🎟 Claimed Codes: <code>{claimed_codes_count}</code>
⌯ 🎁 Daily Reward Claimed Today: <code>{used_today}</code>
⌯ ✨ Daily Reward Lines (Active): <code>{valid_temp}</code>
⌯ 👥 Referral Bonus Lines: <code>+{ref_lines}</code>
⌯ 📦 Base Plan Limit: <code>{base_plan_limit if base_plan_limit!=float('inf') else 'Unlimited'}</code>"""
        try:
            send_with_retry(bot.edit_message_text, txt, c.message.chat.id, c.message.message_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Back", callback_data="back_home", style="danger")))
        except Exception:
            pass
        return

    if d == "referral_sys":
        bot.answer_callback_query(c.id)
        dl = get_user_daily_limit(uid)
        bl = 150
        bn = user["referrals"] * 50
        ml = bl + bn if dl != float('inf') else "∞"
        rlink = f"https://t.me/{BOT_USERNAME}?start={uid}"
        txt = f"𖠵 <b>🔗 My Referrals</b> 𖥻\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n☰ <b>📊 Your Statistics:</b>\n⌯ <b>✅ Referral Count:</b> <code>{user['referrals']}</code>\n⌯ <b>📈 Your Daily Limit:</b> <code>{ml} lines</code>\n⌯ <b>💰 Bonus:</b> <code>+{bn} lines</code>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n🎁 <b>Earn +50 lines for each referral!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n➪ <b>🔗 Your Referral Link:</b>\n{rlink}\n━━━━━━━━━━━━━━━━━━━━━━━━━━\n📤 <i>Share this link with your friends!</i>\n\n<b>💡 Example:</b>\n︙ 0 referrals = {bl} lines/day\n︙ 1 referral = {bl+50} lines/day\n︙ 5 referrals = {bl+250} lines/day"
        try:
            send_with_retry(bot.edit_message_text, txt, c.message.chat.id, c.message.message_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Back", callback_data="back_home", style="danger")))
        except Exception:
            pass
        return

    if d == "back_home":
        bot.answer_callback_query(c.id)
        dl = get_user_daily_limit(uid)
        rem = dl - user.get("today_scans", 0) if dl != float('inf') else "∞"
        dld = dl if dl != float('inf') else "∞"
        mem = user.get("membership", MembershipStatus.FREE.value)
        exp = user.get("membership_expiry")
        dl_left = " - "
        if exp:
            try:
                dl_left = f"{(datetime.fromisoformat(exp) - datetime.now(timezone.utc)).days} days"
            except Exception:
                pass
        ut = get_user_thread_count(user)
        mt = get_max_threads_for_user(user)
        try:
            send_with_retry(bot.edit_message_text, f"𖠵 <b>WELCOME TO {BRAND}</b> 𖥻\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n➪ <b>📤 Send your MLBB device id list (.txt file)</b>\n︙ <i>Format: one device id per line</i>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n☰ <b>📊 Your Dashboard:</b>\n⌯ 🧵 Threads: <code>{ut} / {mt}</code>\n⌯ 👑 Plan: <code>{mem}</code>\n⌯ 📅 Days Left: <code>{dl_left}</code>\n⌯ 📈 Daily Limit: <code>{rem} / {dld} lines</code>\n⌯ 📡 Mode: <code>🎮 MLBB Checker</code>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n⦿ <b>Select an option from the menu below:</b>", c.message.chat.id, c.message.message_id, reply_markup=get_main_markup(c.message))
        except Exception:
            pass
        return

    if d == "user_settings":
        bot.answer_callback_query(c.id)
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(InlineKeyboardButton("🧵 Set Threads", callback_data="set_threads", style="primary"), InlineKeyboardButton("🔙 Back", callback_data="back_home", style="danger"))
        try:
            send_with_retry(bot.edit_message_text, f"𖠵 <b>⚙️ Settings Menu</b> 𖥻\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n➪ <b>🧵 Threads:</b> Control scan speed\n︙ Current: <code>{get_user_thread_count(user)}</code> threads\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n<i>Click a button to configure:</i>", c.message.chat.id, c.message.message_id, reply_markup=mk)
        except Exception:
            pass
        return

    if d == "set_threads":
        bot.answer_callback_query(c.id)
        mem = user.get("membership", MembershipStatus.FREE.value)
        lh = CUSTOM_THREADS.get("basic", 75) if mem == MembershipStatus.BASIC.value else CUSTOM_THREADS.get("vip", 125) if mem == MembershipStatus.VIP.value else CUSTOM_THREADS.get("free", 50)
        txt = f"𖠵 <b>🧵 Set Thread Count</b> 𖥻\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\nLimits by plan:\n🆓 FREE: 1-{CUSTOM_THREADS.get('free',50)}\n⭐ BASIC: 1-{CUSTOM_THREADS.get('basic',75)}\n👑 VIP: 1-{CUSTOM_THREADS.get('vip',125)}\n\nYour plan ({mem}) allows 1-{lh} threads.\n\nCurrent threads: {get_user_thread_count(user)}\n\nSend a number between 1 and {lh} to set your thread count."
        mk = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Back", callback_data="cancel_to_settings"))
        msg = send_with_retry(bot.edit_message_text, txt, c.message.chat.id, c.message.message_id, reply_markup=mk)
        if msg:
            try:
                bot.clear_step_handler_by_chat_id(c.message.chat.id)
            except Exception:
                pass
            bot.register_next_step_handler(msg, process_set_user_threads)
        return

    if d == "owner_panel":
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            bot.answer_callback_query(c.id, "⛔ This panel is for the bot owner only.")
            return
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(
            InlineKeyboardButton("⚙️ Settings", callback_data="owner_settings", style="primary"),
            InlineKeyboardButton("📢 Broadcast", callback_data="owner_broadcast", style="primary"),
            InlineKeyboardButton("🔗 Force Subscribe", callback_data="owner_forcesub", style="primary"),
            InlineKeyboardButton("📊 Full Statistics", callback_data="full_stats", style="primary"),
            InlineKeyboardButton("👥 Users List", callback_data="users_list", style="primary"),
            InlineKeyboardButton("⚡ Threads Config", callback_data="threads_config", style="primary"),
            InlineKeyboardButton("🎁 Manage Gifts", callback_data="manage_gifts", style="success"),
            InlineKeyboardButton("🔑 Manage Keys", callback_data="manage_keys", style="success"),
            InlineKeyboardButton("🔙 Back", callback_data="back_home", style="danger"),
        )
        try:
            send_with_retry(bot.edit_message_text, "𖠵 <b>👑 Owner Control Panel</b> 𖥻\n\nSelect an option:", c.message.chat.id, c.message.message_id, reply_markup=mk)
        except Exception:
            pass
        return

    if d == "full_stats":
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        act_today = ts_today = th = ts_all = bc = vc = free_c = 0
        for u, udata in db.items():
            if udata.get("last_scan_date") == get_today_utc():
                act_today += 1
                ts_today += udata.get("today_scans", 0)
            th += udata.get("total_hits", 0)
            ts_all += udata.get("total_scans", 0)
            if udata.get("membership") == MembershipStatus.BASIC.value:
                bc += 1
            elif udata.get("membership") == MembershipStatus.VIP.value:
                vc += 1
            else:
                free_c += 1
        daily_rewards_today = sum(1 for rd in rewards_db.values() if rd.get("last_daily") and rd.get("last_daily")[:10] == get_today_utc())
        total_codes = len(gift_codes_db)
        active_codes = sum(1 for cd in gift_codes_db.values() if cd['curr'] < cd['max'])
        active_keys = sum(1 for k in license_keys_db.values() if not k["used_by"])
        used_keys = sum(1 for k in license_keys_db.values() if k["used_by"])
        pending_pay = sum(1 for r in payment_requests_db.values() if r["status"] == "pending")
        uptime_str = str(timedelta(seconds=int(time.time() - bot_start_time))).split('.')[0]
        txt = f"""𖠵 <b>📊 FULL SYSTEM STATISTICS</b> 𖥻
━━━━━━━━━━━━━━━━━━━━━━━━━━━
☰ <b>👥 USERS OVERVIEW</b>
⌯ Total Users: <code>{len(db)}</code>
⌯ Active Today: <code>{act_today}</code>
⌯ 👑 VIP Users: <code>{vc}</code>
⌯ ⭐ BASIC Users: <code>{bc}</code>
⌯ 🆓 FREE Users: <code>{free_c}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━━
☰ <b>📈 SCANNING METRICS</b>
⌯ Total Scans: <code>{ts_all}</code>
⌯ Scans Today: <code>{ts_today}</code>
⌯ Total Hits: <code>{th}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━━
☰ <b>🎁 REWARDS & CODES</b>
⌯ Daily Rewards Today: <code>{daily_rewards_today}</code>
⌯ Total Gift Codes: <code>{total_codes}</code>
⌯ Active Gift Codes: <code>{active_codes}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━━
☰ <b>🔑 LICENSE KEYS</b>
⌯ Active Keys: <code>{active_keys}</code>
⌯ Used Keys: <code>{used_keys}</code>
⌯ Pending Payments: <code>{pending_pay}</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━━
☰ <b>⚙️ SYSTEM & PERFORMANCE</b>
⌯ Active Scan Jobs: <code>{get_active_jobs_count_free_only()}</code>
⌯ Queue Size: <code>{job_queue.qsize()}</code>
⌯ Ping / Latency: <code>{get_ping()} ms</code>
⌯ Uptime: <code>{uptime_str}</code>
⌯ Bot Status: <code>{'🟢 Running' if BOT_RUNNING else '🔴 Stopped'}</code>
⌯ Auto-Backup: <code>🟢 Active (12H)</code>
━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 <b>Date:</b> <code>{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}</code>"""
        try:
            send_with_retry(bot.edit_message_text, txt, c.message.chat.id, c.message.message_id, reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 Back", callback_data="owner_panel", style="danger")))
        except Exception:
            pass
        return

    if d == "users_list":
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        show_users_list(c.message.chat.id, 0, c.message.message_id)
        return

    if d == "owner_settings":
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(
            InlineKeyboardButton("🟢 Start Bot" if not BOT_RUNNING else "🔴 Stop Bot", callback_data="toggle_bot", style="success" if not BOT_RUNNING else "danger"),
            InlineKeyboardButton("💾 Backup Data", callback_data="backup_data", style="primary"),
            InlineKeyboardButton("📂 Restore Backup", callback_data="restore_backup", style="primary"),
            InlineKeyboardButton("🔙 Back", callback_data="owner_panel", style="danger"),
        )
        try:
            send_with_retry(bot.edit_message_text, f"<b>⚙️ Bot Settings</b>\n\nCurrent Status: {'🟢 Running' if BOT_RUNNING else '🔴 Stopped'}\n\nUse the buttons below to manage the bot.", c.message.chat.id, c.message.message_id, reply_markup=mk)
        except Exception:
            pass
        return

    if d == "backup_data":
        if uid != OWNER_ID:
            return
        try:
            bf = create_backup()
            with open(bf, 'rb') as f:
                send_with_retry(bot.send_document, c.message.chat.id, f, caption=f"✅ <b>Backup Created Successfully!</b>\n\n📅 Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}\n\n⚠️ Keep this .db file safe!")
            bot.answer_callback_query(c.id, "✅ Backup created successfully!")
        except Exception as e:
            bot.answer_callback_query(c.id, f"❌ Backup failed: {str(e)}")
        return

    if d == "restore_backup":
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        msg = send_with_retry(bot.send_message, c.message.chat.id, "📂 <b>Restore Backup</b>\n\nPlease send the SQLite backup database file (.db) you want to restore.\n\n<i>Send /cancel to abort.</i>")
        bot.register_next_step_handler(msg, process_restore_backup, c.message.message_id)
        try:
            send_with_retry(bot.edit_message_text, "📂 <b>Restore Backup Mode</b>\n\nWaiting for backup file...", c.message.chat.id, c.message.message_id)
        except Exception:
            pass
        return

    if d == "toggle_bot":
        if uid != OWNER_ID:
            return
        BOT_RUNNING = not BOT_RUNNING
        st = '🟢 Running' if BOT_RUNNING else '🔴 Stopped'
        bot.answer_callback_query(c.id, f"Bot is now {st}.")
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(
            InlineKeyboardButton("🟢 Start Bot" if not BOT_RUNNING else "🔴 Stop Bot", callback_data="toggle_bot", style="success" if not BOT_RUNNING else "danger"),
            InlineKeyboardButton("💾 Backup Data", callback_data="backup_data", style="primary"),
            InlineKeyboardButton("📂 Restore Backup", callback_data="restore_backup", style="primary"),
            InlineKeyboardButton("🔙 Back", callback_data="owner_panel", style="danger"),
        )
        try:
            send_with_retry(bot.edit_message_text, f"<b>⚙️ Bot Settings</b>\n\nCurrent Status: {st}\n\nUse the buttons below to manage the bot.", c.message.chat.id, c.message.message_id, reply_markup=mk)
        except Exception:
            pass
        return

    if d == "owner_broadcast":
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        msg = send_with_retry(bot.send_message, c.message.chat.id, "📢 <b>Send me the message you want to broadcast to all users.</b>\n\n<i>Note: The broadcast system will copy your message exactly.</i>\n\nSend /cancel to cancel.")
        bot.register_next_step_handler(msg, broadcast_message)
        try:
            send_with_retry(bot.edit_message_text, "📢 <b>Broadcast Mode</b>\n\nWaiting for message...", c.message.chat.id, c.message.message_id)
        except Exception:
            pass
        return

    if d == "owner_forcesub":
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        mk = InlineKeyboardMarkup(row_width=1)
        for sub in force_subs:
            try:
                mk.add(InlineKeyboardButton(f"❌ {bot.get_chat(sub.split('|')[0]).title}", callback_data=f"remove_channel_{sub.split('|')[0]}", style="danger"))
            except Exception:
                mk.add(InlineKeyboardButton(f"❌ {sub}", callback_data=f"remove_channel_{sub}", style="danger"))
        mk.add(InlineKeyboardButton("➕ Add Channel", callback_data="add_sub_channel", style="success"), InlineKeyboardButton("🔙 Back", callback_data="owner_panel", style="danger"))
        try:
            send_with_retry(bot.edit_message_text, f"<b>🔗 Force Subscribe Channels</b>\n\nCurrent Channels ({len(force_subs)}):\n" + ("\n".join([f"• {s.split('|')[0]}" for s in force_subs]) if force_subs else "No channels set yet."), c.message.chat.id, c.message.message_id, reply_markup=mk)
        except Exception:
            pass
        return

    if d == "threads_config" or d.startswith("threads_"):
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        if d == "threads_free_inc" and CUSTOM_THREADS.get('free', 50) < 100:
            CUSTOM_THREADS['free'] += 1; save_threads_config()
        elif d == "threads_free_dec" and CUSTOM_THREADS.get('free', 50) > 1:
            CUSTOM_THREADS['free'] -= 1; save_threads_config()
        elif d == "threads_basic_inc" and CUSTOM_THREADS.get('basic', 75) < 200:
            CUSTOM_THREADS['basic'] += 1; save_threads_config()
        elif d == "threads_basic_dec" and CUSTOM_THREADS.get('basic', 75) > 1:
            CUSTOM_THREADS['basic'] -= 1; save_threads_config()
        elif d == "threads_semi_vip_inc" and CUSTOM_THREADS.get('semi_vip', 100) < 250:
            CUSTOM_THREADS['semi_vip'] += 1; save_threads_config()
        elif d == "threads_semi_vip_dec" and CUSTOM_THREADS.get('semi_vip', 100) > 1:
            CUSTOM_THREADS['semi_vip'] -= 1; save_threads_config()
        elif d == "threads_vip_inc" and CUSTOM_THREADS.get('vip', 125) < 300:
            CUSTOM_THREADS['vip'] += 1; save_threads_config()
        elif d == "threads_vip_dec" and CUSTOM_THREADS.get('vip', 125) > 1:
            CUSTOM_THREADS['vip'] -= 1; save_threads_config()
        elif d == "threads_reward_inc":
            CUSTOM_THREADS['daily_reward_max'] = CUSTOM_THREADS.get('daily_reward_max', 1000) + 100; save_threads_config()
        elif d == "threads_reward_dec":
            CUSTOM_THREADS['daily_reward_max'] = max(100, CUSTOM_THREADS.get('daily_reward_max', 1000) - 100); save_threads_config()
        refresh_threads_config(c.message.chat.id, c.message.message_id)
        return

    if d.startswith("user_page_"):
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        show_users_list(c.message.chat.id, int(d.split("_")[-1]), c.message.message_id)
        return

    if d.startswith("select_user_"):
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        tu = d.replace("select_user_", "")
        if tu in db:
            show_user_controls(c.message.chat.id, tu, c.message.message_id)
        else:
            bot.answer_callback_query(c.id, "User not found.")
        return

    if d.startswith("ban_user_"):
        if uid != OWNER_ID:
            return
        tu = d.replace("ban_user_", "")
        if tu not in banned_users:
            banned_users.append(tu)
            save_db(banned_users, BANNED_DB)
            bot.answer_callback_query(c.id, f"User {tu} banned.")
        else:
            bot.answer_callback_query(c.id, "User is already banned.")
        show_user_controls(c.message.chat.id, tu, c.message.message_id)
        return

    if d.startswith("unban_user_"):
        if uid != OWNER_ID:
            return
        tu = d.replace("unban_user_", "")
        if tu in banned_users:
            banned_users.remove(tu)
            save_db(banned_users, BANNED_DB)
            bot.answer_callback_query(c.id, f"User {tu} unbanned.")
        else:
            bot.answer_callback_query(c.id, "User is not banned.")
        show_user_controls(c.message.chat.id, tu, c.message.message_id)
        return

    if d.startswith("set_membership_basic_") or d.startswith("set_membership_vip_") or d.startswith("set_membership_semi_vip_"):
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        if "semi_vip" in d:
            plan = "semi_vip"
        elif "basic" in d:
            plan = "basic"
        else:
            plan = "vip"
        tu = d.replace(f"set_membership_{plan}_", "")
        msg = send_with_retry(bot.send_message, c.message.chat.id, f"Set {plan.upper()} plan duration for user {tu}\n\nEnter duration (e.g., 1h, 1d, 1m):\n\n<i>Send /cancel to cancel.</i>")
        bot.register_next_step_handler(msg, process_set_membership, tu, c.message.message_id, plan)
        return

    if d.startswith("remove_membership_"):
        if uid != OWNER_ID:
            return
        tu = d.replace("remove_membership_", "")
        if tu in db:
            db[tu]["membership"] = MembershipStatus.FREE.value
            db[tu]["membership_expiry"] = None
            if db[tu].get("user_threads", 50) > CUSTOM_THREADS.get("free", 50):
                db[tu]["user_threads"] = CUSTOM_THREADS.get("free", 50)
            save_db(db, DB_FILE)
            bot.answer_callback_query(c.id, f"Membership removed from user {tu}.")
        else:
            bot.answer_callback_query(c.id, "User not found.")
        show_user_controls(c.message.chat.id, tu, c.message.message_id)
        return

    if d.startswith("add_bonus_") or d.startswith("remove_bonus_") or d.startswith("adjust_limit_"):
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        action = "add_bonus" if "add" in d else "remove_bonus" if "remove" in d else "adjust_limit"
        tu = d.replace(f"{action}_", "")
        txt = f"Add bonus lines to user {tu}" if action == "add_bonus" else f"Remove bonus lines from user {tu}" if action == "remove_bonus" else f"Adjust remaining daily limit for user {tu}"
        msg = send_with_retry(bot.send_message, c.message.chat.id, f"{txt}\n\nEnter amount:\n\n<i>Send /cancel to cancel.</i>")
        bot.register_next_step_handler(msg, process_add_bonus if action == "add_bonus" else process_remove_bonus if action == "remove_bonus" else process_adjust_limit, tu, c.message.message_id)
        return

    if d == "add_sub_channel":
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        msg = send_with_retry(bot.send_message, c.message.chat.id, "<b>➕ Add Force Subscribe Channel</b>\n\nPlease forward a message from the channel you want to add.\n\n<i>Send /cancel to cancel.</i>")
        bot.register_next_step_handler(msg, get_forwarded_message)
        try:
            send_with_retry(bot.edit_message_text, "➕ <b>Add Force Subscribe Channel</b>\n\nWaiting for forwarded message...", c.message.chat.id, c.message.message_id)
        except Exception:
            pass
        return

    if d.startswith("remove_channel_"):
        bot.answer_callback_query(c.id)
        if uid != OWNER_ID:
            return
        cid = d.replace("remove_channel_", "")
        tr = next((s for s in force_subs if s.startswith(cid)), None)
        if tr:
            force_subs.remove(tr)
            save_db(force_subs, FORCE_DB)
            bot.answer_callback_query(c.id, "Channel removed successfully.")
        else:
            bot.answer_callback_query(c.id, "Channel not found.")
        mk = InlineKeyboardMarkup(row_width=1)
        for sub in force_subs:
            try:
                mk.add(InlineKeyboardButton(f"❌ {bot.get_chat(sub.split('|')[0]).title}", callback_data=f"remove_channel_{sub.split('|')[0]}", style="danger"))
            except Exception:
                mk.add(InlineKeyboardButton(f"❌ {sub}", callback_data=f"remove_channel_{sub}", style="danger"))
        mk.add(InlineKeyboardButton("➕ Add Channel", callback_data="add_sub_channel", style="success"), InlineKeyboardButton("🔙 Back", callback_data="owner_panel", style="danger"))
        try:
            send_with_retry(bot.edit_message_text, f"<b>🔗 Force Subscribe Channels</b>\n\nCurrent Channels ({len(force_subs)}):\n" + ("\n".join([f"• {s.split('|')[0]}" for s in force_subs]) if force_subs else "No channels set yet."), c.message.chat.id, c.message.message_id, reply_markup=mk)
        except Exception:
            pass
        return

    if d.startswith("job_pause_") or d.startswith("job_resume_") or d.startswith("job_stop_"):
        jid = d.split("_")[-1]
        tj = next((job for job in current_jobs if job.job_id == jid and job.chat_id == uid), None)
        if tj:
            if "pause" in d and tj.status == 'Running':
                tj.status = 'Paused'
                tj.pause_event.clear()
                threading.Thread(target=auto_resume_job, args=(tj,), daemon=True).start()
                bot.answer_callback_query(c.id, "⏸ Scan Paused (Auto-resume in 30s)")
            elif "resume" in d and tj.status == 'Paused':
                tj.status = 'Running'
                tj.pause_event.set()
                bot.answer_callback_query(c.id, "▶️ Scan Resumed")
            elif "stop" in d and tj.status in ['Running', 'Paused']:
                tj.status = 'Stopped'
                tj.stop_flag = True
                tj.pause_event.set()
                unpin_scan_message(tj.chat_id, tj.msg_id)
                bot.answer_callback_query(c.id, "⏹ Scan Stopped")
        else:
            bot.answer_callback_query(c.id, "⚠️ No active scan found.")
        return


def refresh_threads_config(chat_id, message_id):
    mk = InlineKeyboardMarkup(row_width=3)
    mk.add(InlineKeyboardButton("FREE -", callback_data="threads_free_dec", style="danger"), InlineKeyboardButton(f"{CUSTOM_THREADS.get('free',50)}", callback_data="none", style="primary"), InlineKeyboardButton("FREE +", callback_data="threads_free_inc", style="success"))
    mk.add(InlineKeyboardButton("BASIC -", callback_data="threads_basic_dec", style="danger"), InlineKeyboardButton(f"{CUSTOM_THREADS.get('basic',75)}", callback_data="none", style="primary"), InlineKeyboardButton("BASIC +", callback_data="threads_basic_inc", style="success"))
    mk.add(InlineKeyboardButton("SEMI VIP -", callback_data="threads_semi_vip_dec", style="danger"), InlineKeyboardButton(f"{CUSTOM_THREADS.get('semi_vip',100)}", callback_data="none", style="primary"), InlineKeyboardButton("SEMI VIP +", callback_data="threads_semi_vip_inc", style="success"))
    mk.add(InlineKeyboardButton("VIP -", callback_data="threads_vip_dec", style="danger"), InlineKeyboardButton(f"{CUSTOM_THREADS.get('vip',125)}", callback_data="none", style="primary"), InlineKeyboardButton("VIP +", callback_data="threads_vip_inc", style="success"))
    mk.add(InlineKeyboardButton("Reward Max -", callback_data="threads_reward_dec", style="danger"), InlineKeyboardButton(f"{CUSTOM_THREADS.get('daily_reward_max',1000)}", callback_data="none", style="primary"), InlineKeyboardButton("Reward Max +", callback_data="threads_reward_inc", style="success"))
    mk.add(InlineKeyboardButton("🔙 Back to Panel", callback_data="owner_panel", style="danger"))
    try:
        send_with_retry(bot.edit_message_text, f"<b>⚙️ Threads & Rewards Configuration</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n<b>FREE Max Threads:</b> <code>{CUSTOM_THREADS.get('free',50)}</code>\n<b>BASIC Max Threads:</b> <code>{CUSTOM_THREADS.get('basic',75)}</code>\n<b>VIP Max Threads:</b> <code>{CUSTOM_THREADS.get('vip',125)}</code>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n<b>Max Daily Reward Amount:</b> <code>{CUSTOM_THREADS.get('daily_reward_max',1000)} lines</code>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━", chat_id, message_id, reply_markup=mk)
    except Exception:
        pass


def process_payment_receipt(m, plan):
    try:
        bot.clear_step_handler_by_chat_id(m.chat.id)
    except Exception:
        pass
    if not m.photo:
        send_with_retry(bot.send_message, m.chat.id, "Please send a photo of your receipt.")
        return
    uid = str(m.chat.id)
    file_id = m.photo[-1].file_id
    req_id = uuid.uuid4().hex[:12].upper()
    price_map = {"basic": "100", "semi_vip": "200", "vip": "300"}
    amount = price_map.get(plan, "100")
    now = datetime.now(timezone.utc).isoformat()
    payment_requests_db[req_id] = {"req_id": req_id, "user_id": uid, "username": m.from_user.username or "", "plan": plan, "amount": amount, "receipt_id": file_id, "status": "pending", "created_at": now, "decided_at": None}
    save_payment_requests()
    cap = "Payment Request\n\nID: " + req_id + "\nUser: " + uid + "\nHandle: @" + (m.from_user.username or "None") + "\nPlan: " + plan.upper() + "\nAmount: " + amount + " Stars\nTime: " + now
    mk = InlineKeyboardMarkup(row_width=2)
    mk.add(InlineKeyboardButton("Approve", callback_data="pay_approve_" + req_id, style="success"), InlineKeyboardButton("Reject", callback_data="pay_reject_" + req_id, style="danger"))
    try:
        send_with_retry(bot.send_photo, OWNER_ID, file_id, caption=cap, reply_markup=mk)
        send_with_retry(bot.send_message, m.chat.id, "Receipt received. Request " + req_id + " is pending admin review.")
    except Exception:
        send_with_retry(bot.send_message, m.chat.id, "Failed to submit receipt. Try again later.")


def process_redeem_key(m):
    try:
        bot.clear_step_handler_by_chat_id(m.chat.id)
    except Exception:
        pass
    if not m.text:
        return
    key = m.text.strip().upper()
    entry = license_keys_db.get(key)
    if not entry:
        send_with_retry(bot.send_message, m.chat.id, "Invalid license key.")
        return
    if entry["used_by"]:
        send_with_retry(bot.send_message, m.chat.id, "This key has already been used.")
        return
    uid = str(m.chat.id)
    plan = entry["plan"]
    dur = parse_time_duration(entry["duration"])
    if not dur:
        return
    expiry = datetime.now(timezone.utc) + dur
    plan_map = {"basic": MembershipStatus.BASIC.value, "semi_vip": MembershipStatus.SEMI_VIP.value, "vip": MembershipStatus.VIP.value}
    db[uid]["membership"] = plan_map.get(plan, MembershipStatus.BASIC.value)
    db[uid]["membership_expiry"] = expiry.isoformat()
    if db[uid].get("user_threads", 50) > get_max_threads_for_user(db[uid]):
        db[uid]["user_threads"] = get_max_threads_for_user(db[uid])
    save_db(db, DB_FILE)
    entry["used_by"] = uid
    entry["used_at"] = datetime.now(timezone.utc).isoformat()
    save_license_keys()
    send_with_retry(bot.send_message, m.chat.id, "Key redeemed. Plan " + plan.upper() + " is active until " + expiry.strftime("%Y-%m-%d %H:%M") + ".")


def process_admin_approve(c, req_id):
    if str(c.message.chat.id) != OWNER_ID:
        return
    req = payment_requests_db.get(req_id)
    if not req or req["status"] != "pending":
        send_with_retry(bot.answer_callback_query, c.id, "Request not found or already handled.")
        return
    plan = req["plan"]
    duration_map = {"basic": "3d", "semi_vip": "7d", "vip": "36500d"}
    duration = duration_map.get(plan, "3d")
    key = gen_license_key()
    license_keys_db[key] = {"key": key, "plan": plan, "duration": duration, "created_at": datetime.now(timezone.utc).isoformat(), "created_by": OWNER_ID, "used_by": None, "used_at": None}
    save_license_keys()
    req["status"] = "approved"
    req["decided_at"] = datetime.now(timezone.utc).isoformat()
    save_payment_requests()
    send_with_retry(bot.send_message, req["user_id"], "Payment approved.\n\nPlan: " + plan.upper() + "\nKey:\n" + key + "\n\nRedeem from Buy Plan menu to activate.")
    send_with_retry(bot.send_message, OWNER_ID, "Key delivered to " + req["user_id"] + ": " + key)


def process_admin_reject(c, req_id):
    if str(c.message.chat.id) != OWNER_ID:
        return
    req = payment_requests_db.get(req_id)
    if not req or req["status"] != "pending":
        return
    req["status"] = "rejected"
    req["decided_at"] = datetime.now(timezone.utc).isoformat()
    save_payment_requests()
    send_with_retry(bot.send_message, req["user_id"], "Payment rejected. Receipt could not be verified. Contact support.")
    send_with_retry(bot.send_message, OWNER_ID, "Rejected request " + req_id + ".")


def process_redeem_code(m):
    try:
        bot.clear_step_handler_by_chat_id(m.chat.id)
    except Exception:
        pass
    if m.text and (m.text.startswith('/') or m.text.lower() == "/cancel"):
        cancel_current_operation(m)
        return
    code = m.text.strip().upper()
    if code not in gift_codes_db:
        send_with_retry(bot.send_message, m.chat.id, "❌ <b>Invalid or expired code!</b>")
        return
    cdata = gift_codes_db[code]
    if cdata['curr'] >= cdata['max']:
        send_with_retry(bot.send_message, m.chat.id, "❌ <b>This code has reached its maximum usage limit!</b>")
        return
    uid = str(m.chat.id)
    rd = rewards_db.get(uid, {"last_daily": None, "claimed_codes": [], "temp_lines": 0, "temp_lines_expiry": None})
    if code in rd["claimed_codes"]:
        send_with_retry(bot.send_message, m.chat.id, "⚠️ <b>You have already redeemed this code!</b>")
        return
    rtype, rval = cdata['type'], cdata['value']
    if rtype == "lines":
        now = datetime.now(timezone.utc)
        ct = rd.get("temp_lines", 0)
        exp = rd.get("temp_lines_expiry")
        if exp and now > datetime.fromisoformat(exp):
            ct = 0
        rd["temp_lines"] = ct + int(rval)
        rd["temp_lines_expiry"] = (now + timedelta(days=1)).isoformat()
        msg_text = f"✅ <b>Code Redeemed!</b>\nYou received <b>+{rval} temporary lines</b> (Valid for 24H)."
    elif rtype in ["basic", "vip"]:
        dur = parse_time_duration(rval)
        if not dur:
            send_with_retry(bot.send_message, m.chat.id, "❌ <b>Error in code duration!</b>")
            return
        ed = datetime.now(timezone.utc) + dur
        plan_map = {"basic": MembershipStatus.BASIC.value, "semi_vip": MembershipStatus.SEMI_VIP.value, "vip": MembershipStatus.VIP.value}
        db[uid]["membership"] = plan_map.get(rtype, MembershipStatus.BASIC.value)
        db[uid]["membership_expiry"] = ed.isoformat()
        db[uid]["today_scans"] = 0
        db[uid]["last_scan_date"] = get_today_utc()
        if db[uid].get("user_threads", 50) > get_max_threads_for_user(db[uid]):
            db[uid]["user_threads"] = get_max_threads_for_user(db[uid])
        plan_name = {"basic": "⭐ BASIC", "semi_vip": "💠 SEMI VIP", "vip": "👑 VIP"}.get(rtype, "⭐ BASIC")
        msg_text = f"✅ <b>Code Redeemed!</b>\nYour account has been upgraded to <b>{plan_name}</b> for {rval}!"
    else:
        return
    cdata['curr'] += 1
    rd["claimed_codes"].append(code)
    rewards_db[uid] = rd
    save_db(db, DB_FILE)
    save_db_rewards()
    save_db_gift_codes()
    send_with_retry(bot.send_message, m.chat.id, msg_text)
    user, _ = get_user(m.chat.id)
    try:
        send_with_retry(bot.send_message, OWNER_ID, f"🎟 <b>Gift Code Redeemed!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n👤 User ID: <code>{uid}</code>\n🔗 Username: @{user.get('username') or 'None'}\n🎟 Code: <code>{code}</code>\n🎁 Reward: <b>{rval} ({rtype})</b>\n⏰ Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    except Exception:
        pass


def process_gen_code_step1(m, rtype):
    try:
        bot.clear_step_handler_by_chat_id(m.chat.id)
    except Exception:
        pass
    if m.text and (m.text.startswith('/') or m.text.lower() == "/cancel"):
        cancel_current_operation(m)
        return
    try:
        uses = int(m.text.strip())
        if uses < 1:
            raise ValueError
    except Exception:
        send_with_retry(bot.send_message, m.chat.id, "❌ Invalid number. Operation cancelled.")
        return
    if rtype == "lines":
        txt = "<b>⚙️ CODE GENERATION (Step 2/2)</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📈 <b>Reward Amount Setup</b>\n\n<i>Enter the amount of extra lines to gift (Valid for 24H).</i>\n📌 <b>Example:</b> <code>5000</code>\n\n💬 <b>Action:</b> Send amount or /cancel"
    else:
        txt = "<b>⚙️ CODE GENERATION (Step 2/2)</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n⏱ <b>Duration Setup</b>\n\n<i>Enter the duration for this subscription gift.</i>\n📌 <b>Format:</b> <code>1h</code> (Hour), <code>1d</code> (Day), <code>1m</code> (Month)\n\n💬 <b>Action:</b> Send duration or /cancel"
    msg = send_with_retry(bot.send_message, m.chat.id, txt)
    bot.register_next_step_handler(msg, process_gen_code_step2, rtype, uses)


def process_gen_code_step2(m, rtype, uses):
    try:
        bot.clear_step_handler_by_chat_id(m.chat.id)
    except Exception:
        pass
    if m.text and (m.text.startswith('/') or m.text.lower() == "/cancel"):
        cancel_current_operation(m)
        return
    rval = m.text.strip()
    if rtype in ["basic", "vip"] and not parse_time_duration(rval):
        send_with_retry(bot.send_message, m.chat.id, "❌ Invalid duration format.")
        return
    if rtype == "lines" and not rval.isdigit():
        send_with_retry(bot.send_message, m.chat.id, "❌ Invalid lines amount.")
        return
    code = "GIF-" + ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=8))
    gift_codes_db[code] = {"type": rtype, "value": rval, "max": uses, "curr": 0}
    save_db_gift_codes()
    plan_name = {"lines": "Extra Lines (24H)", "basic": "⭐ BASIC", "semi_vip": "💠 SEMI VIP", "vip": "👑 VIP"}.get(rtype, "⭐ BASIC")
    res_msg = f"✅ <b>Gift Code Generated!</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n🎟 <b>Code:</b> <code>{code}</code>\n🎁 <b>Reward:</b> {plan_name} ({rval})\n👥 <b>Max Uses:</b> {uses}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n➪ <b>How to use:</b>\n︙ <i>Go to Bot settings or Rewards menu.</i>\n︙ <i>Click \"Redeem Gift Code\".</i>\n︙ <i>Send the code exactly as shown above.</i>\n\n🌐 <b>Bot Link:</b> @{BOT_USERNAME}\n━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    send_with_retry(bot.send_message, m.chat.id, res_msg)


def process_custom_key_duration(m, plan):
    try:
        bot.clear_step_handler_by_chat_id(m.chat.id)
    except Exception:
        pass
    if not m.text:
        send_with_retry(bot.send_message, m.chat.id, "❌ Invalid input.")
        return
    if m.text.startswith("/") or m.text.lower() == "/cancel":
        cancel_current_operation(m)
        return
    dur_text = m.text.strip().lower()
    if not parse_time_duration(dur_text):
        send_with_retry(bot.send_message, m.chat.id, "❌ Invalid duration. Use <code>1h</code>, <code>3d</code>, <code>7d</code>, <code>30d</code>, or <code>36500d</code>.")
        return
    msg = send_with_retry(bot.send_message, m.chat.id,
        f"🔧 <b>Custom Key Generator</b>\n\nPlan: <code>{plan.upper()}</code>\nDuration: <code>{dur_text}</code>\n\nStep 3/3 — How many keys should be generated? (1-100):\n\nSend /cancel to abort.")
    if msg:
        bot.register_next_step_handler(msg, process_custom_key_qty, plan, dur_text)


def process_custom_key_qty(m, plan, dur_text):
    try:
        bot.clear_step_handler_by_chat_id(m.chat.id)
    except Exception:
        pass
    if not m.text:
        send_with_retry(bot.send_message, m.chat.id, "❌ Invalid input.")
        return
    if m.text.startswith("/") or m.text.lower() == "/cancel":
        cancel_current_operation(m)
        return
    try:
        qty = int(m.text.strip())
        if qty < 1 or qty > 100:
            raise ValueError
    except Exception:
        send_with_retry(bot.send_message, m.chat.id, "❌ Enter a number between 1 and 100.")
        return
    keys = []
    now = datetime.now(timezone.utc).isoformat()
    for _ in range(qty):
        k = gen_license_key()
        license_keys_db[k] = {
            "key": k,
            "plan": plan,
            "duration": dur_text,
            "created_at": now,
            "created_by": OWNER_ID,
            "used_by": None,
            "used_at": None,
        }
        keys.append(k)
    save_license_keys()
    body = "\n".join(keys)
    header = f"🔧 <b>Custom Keys Generated</b>\n\nPlan: <code>{plan.upper()}</code>\nDuration: <code>{dur_text}</code>\nQuantity: <code>{qty}</code>\n"
    try:
        send_with_retry(bot.send_document, m.chat.id, document=("custom_keys.txt", body.encode("utf-8")), caption=header)
    except Exception:
        send_with_retry(bot.send_message, m.chat.id, header + "\n<code>" + body + "</code>")


def process_set_user_threads(m):
    try:
        bot.clear_step_handler_by_chat_id(m.chat.id)
    except Exception:
        pass
    if m.text and (m.text.startswith('/') or m.text.lower() == "/cancel"):
        cancel_current_operation(m)
        return
    user, _ = get_user(m.chat.id)
    mem = user.get("membership", MembershipStatus.FREE.value)
    ma = CUSTOM_THREADS.get("basic", 75) if mem == MembershipStatus.BASIC.value else CUSTOM_THREADS.get("vip", 125) if mem == MembershipStatus.VIP.value else CUSTOM_THREADS.get("free", 50)
    try:
        nt = int(m.text.strip())
        if nt < 1 or nt > ma:
            send_with_retry(bot.send_message, m.chat.id, "❌ Thread count must be at least 1." if nt < 1 else f"❌ Your plan ({mem}) allows a maximum of {ma} threads.")
        else:
            user["user_threads"] = nt
            save_db(db, DB_FILE)
            send_with_retry(bot.send_message, m.chat.id, f"✅ Thread count updated to <code>{nt}</code> for your account.")
            send_welcome(m)
    except ValueError:
        send_with_retry(bot.send_message, m.chat.id, "❌ Invalid number. Please enter a valid number.")


def show_users_list(chat_id, page, message_id=None):
    users = sorted(db.items(), key=lambda it: (it[1].get('last_scan_date', '1970-01-01'), it[1].get('today_scans', 0), it[1].get('total_scans', 0)), reverse=True)
    tp = max(1, (len(users) + 9) // 10)
    page = max(0, min(page, tp - 1))
    cu = users[page * 10:(page + 1) * 10]
    txt = f"<b>👥 Users List | Page {page+1}/{tp}</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for uid, udata in cu:
        un = udata.get('username')
        un_str = f"@{un}" if un and un not in ['None', 'Unknown'] else "No Username"
        plan = udata.get('membership', MembershipStatus.FREE.value).split()[0]
        hits = udata.get('total_hits', 0)
        scans = udata.get('total_scans', 0)
        last = udata.get('last_scan_date', 'Unknown')
        status = '🔴 Ban' if uid in banned_users else '🟢 Act'
        txt += f"👤 <b>{uid}</b> | {un_str}\n"
        txt += f"└ {status} | 👑 {plan} | 💎 Hits: {hits} | 📊 Scans: {scans} | 📅 Last: {last}\n\n"
    mk = InlineKeyboardMarkup(row_width=2)
    user_btns = []
    for uid, udata in cu:
        un = udata.get('username', 'No username')
        btn_text = f"👤 {un if un not in [None, 'None', 'Unknown'] else uid[:8]}"
        user_btns.append(InlineKeyboardButton(btn_text, callback_data=f"select_user_{uid}", style="primary"))
    for i in range(0, len(user_btns), 2):
        if i + 1 < len(user_btns):
            mk.row(user_btns[i], user_btns[i + 1])
        else:
            mk.row(user_btns[i])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ Prev", callback_data=f"user_page_{page-1}", style="primary"))
    nav.append(InlineKeyboardButton(f"{page+1}/{tp}", callback_data="none", style="primary"))
    if page < tp - 1:
        nav.append(InlineKeyboardButton("Next ▶️", callback_data=f"user_page_{page+1}", style="primary"))
    if nav:
        mk.row(*nav)
    mk.add(InlineKeyboardButton("🔙 Back to Panel", callback_data="owner_panel", style="danger"))
    if message_id:
        try:
            send_with_retry(bot.edit_message_text, txt, chat_id, message_id, reply_markup=mk)
        except Exception:
            pass
    else:
        send_with_retry(bot.send_message, chat_id, txt, reply_markup=mk)


def show_user_controls(chat_id, tu, msg_id):
    udata, dl = db.get(tu, {}), get_user_daily_limit(tu)
    ib = tu in banned_users
    mem = udata.get("membership", MembershipStatus.FREE.value)
    exp = udata.get("membership_expiry", None)
    expt = "N/A"
    if exp:
        try:
            expt = datetime.fromisoformat(exp).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            expt = "Invalid"
    last_scan_str = "Not yet examined"
    lst = udata.get("last_scan_time")
    if lst:
        try:
            lst_dt = datetime.fromisoformat(lst)
            if lst_dt.tzinfo is None:
                lst_dt = lst_dt.replace(tzinfo=timezone.utc)
            diff = datetime.now(timezone.utc) - lst_dt
            total_mins = int(diff.total_seconds() // 60)
            if total_mins < 60:
                last_scan_str = f"{total_mins} minutes ago"
            elif total_mins < 1440:
                last_scan_str = f"{total_mins//60} hours ago"
            else:
                last_scan_str = f"{total_mins//1440} days ago"
        except Exception:
            last_scan_str = udata.get("last_scan_date", "Unknown")
    total_files = udata.get("total_files", 0)
    cur_threads = udata.get("user_threads", 50)
    txt = (
        f"<b>👤 User Control Panel</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>🆔 ID:</b> <code>{tu}</code>\n"
        f"<b>👤 Name:</b> {udata.get('first_name','Unknown')}\n"
        f"<b>🔗 Username:</b> @{udata.get('username','No username') if udata.get('username') not in [None,'None'] else 'No username'}\n"
        f"<b>📅 Registered:</b> {udata.get('registered_date','Unknown')}\n"
        f"<b>👑 Plan:</b> {mem}\n"
        f"<b>📅 Expires:</b> {expt}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>📁 Files Scanned:</b> <code>{total_files}</code>\n"
        f"<b>📊 Total Lines:</b> <code>{udata.get('total_scans',0)}</code>\n"
        f"<b>⏰ Last Scan:</b> <code>{last_scan_str}</code>\n"
        f"<b>🧵 Threads Set:</b> <code>{cur_threads}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>🎯 Stats:</b>\n"
        f"⌯ 💎 Total Hits: <code>{udata.get('total_hits',0)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>👥 Referrals:</b> <code>{udata.get('referrals',0)}</code>\n"
        f"<b>📊 Daily Limit:</b> <code>{dl if dl!=float('inf') else 'Unlimited'}</code>\n"
        f"<b>⏳ Remaining Today:</b> <code>{dl-udata.get('today_scans',0) if dl!=float('inf') else 'Unlimited'}</code>\n"
        f"<b>⚡ Status:</b> {'🔴 Banned' if ib else '🟢 Active'}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    mk = InlineKeyboardMarkup(row_width=2)
    mk.add(InlineKeyboardButton("✅ Unban User" if ib else "🚫 Ban User", callback_data=f"{'unban' if ib else 'ban'}_user_{tu}", style="success" if ib else "danger"))
    if mem != MembershipStatus.FREE.value:
        mk.add(InlineKeyboardButton("❌ Remove Plan", callback_data=f"remove_membership_{tu}", style="danger"))
    else:
        mk.add(InlineKeyboardButton("⭐ Set BASIC", callback_data=f"set_membership_basic_{tu}", style="success"))
        mk.add(InlineKeyboardButton("💠 Set SEMI VIP", callback_data=f"set_membership_semi_vip_{tu}", style="success"), InlineKeyboardButton("👑 Set VIP", callback_data=f"set_membership_vip_{tu}", style="success"))
    mk.add(InlineKeyboardButton("➕ Add Bonus (+500)", callback_data=f"add_bonus_{tu}", style="success"), InlineKeyboardButton("➖ Remove Bonus (-500)", callback_data=f"remove_bonus_{tu}", style="danger"), InlineKeyboardButton("📊 Adjust Remaining", callback_data=f"adjust_limit_{tu}", style="primary"), InlineKeyboardButton("🔙 Back to Users List", callback_data=f"user_page_0", style="danger"))
    try:
        send_with_retry(bot.edit_message_text, txt, chat_id, msg_id, reply_markup=mk)
    except Exception:
        pass


def process_set_membership(m, tu, orig_id, pt):
    try:
        bot.clear_step_handler_by_chat_id(m.chat.id)
    except Exception:
        pass
    if m.text and (m.text.startswith('/') or m.text.lower() == "/cancel"):
        cancel_current_operation(m)
        return
    try:
        dur = parse_time_duration(m.text.strip())
        if not dur:
            send_with_retry(bot.send_message, m.chat.id, "❌ Invalid format.")
            return
        if tu in db:
            ed = datetime.now(timezone.utc) + dur
            plan_map = {"basic": MembershipStatus.BASIC.value, "semi_vip": MembershipStatus.SEMI_VIP.value, "vip": MembershipStatus.VIP.value}
            db[tu]["membership"] = plan_map.get(pt, MembershipStatus.BASIC.value)
            db[tu]["membership_expiry"] = ed.isoformat()
            db[tu]["today_scans"] = 0
            db[tu]["last_scan_date"] = get_today_utc()
            if db[tu].get("user_threads", 50) > get_max_threads_for_user(db[tu]):
                db[tu]["user_threads"] = get_max_threads_for_user(db[tu])
            save_db(db, DB_FILE)
            send_with_retry(bot.send_message, m.chat.id, f"✅ User {tu} has been upgraded to {_plan_disp(pt)} for {m.text.strip()}.")
            try:
                send_with_retry(bot.send_message, tu, f"🎉 <b>Congratulations! 🎉</b>\n\n<b>Your account has been upgraded to {_plan_disp(pt)}!</b>\n\n<b>✨ Plan Benefits:</b>\n• Daily limit: Unlimited lines\n• No queue waiting\n• Max threads: 1-{CUSTOM_THREADS.get(pt, 75)} (configurable)\n• Multi-Scan: Up to {'3' if pt=='basic' else '5'} files\n• Priority Support\n\n<b>⏰ Expires:</b> <code>{ed.strftime('%Y-%m-%d %H:%M:%S')}</code>\n\nEnjoy the premium experience! 🚀")
            except Exception:
                pass
            show_user_controls(m.chat.id, tu, orig_id)
    except Exception as e:
        send_with_retry(bot.send_message, m.chat.id, f"❌ Error: {str(e)}")


def process_add_bonus(m, tu, orig_id):
    try:
        bot.clear_step_handler_by_chat_id(m.chat.id)
    except Exception:
        pass
    if m.text and (m.text.startswith('/') or m.text.lower() == "/cancel"):
        cancel_current_operation(m)
        return
    try:
        amt = int(m.text.strip())
        if amt <= 0:
            send_with_retry(bot.send_message, m.chat.id, "Amount must be positive.")
            return
        if tu in db:
            db[tu]["base_limit"] = db[tu].get("base_limit", 5000) + amt
            save_db(db, DB_FILE)
            send_with_retry(bot.send_message, m.chat.id, f"✅ Added {amt} bonus lines to user {tu}.")
            show_user_controls(m.chat.id, tu, orig_id)
    except Exception:
        send_with_retry(bot.send_message, m.chat.id, "❌ Invalid amount.")


def process_remove_bonus(m, tu, orig_id):
    try:
        bot.clear_step_handler_by_chat_id(m.chat.id)
    except Exception:
        pass
    if m.text and (m.text.startswith('/') or m.text.lower() == "/cancel"):
        cancel_current_operation(m)
        return
    try:
        amt = int(m.text.strip())
        if amt <= 0:
            send_with_retry(bot.send_message, m.chat.id, "Amount must be positive.")
            return
        if tu in db:
            db[tu]["base_limit"] = max(0, db[tu].get("base_limit", 5000) - amt)
            save_db(db, DB_FILE)
            send_with_retry(bot.send_message, m.chat.id, f"✅ Removed {amt} bonus lines from user {tu}.")
            show_user_controls(m.chat.id, tu, orig_id)
    except Exception:
        send_with_retry(bot.send_message, m.chat.id, "❌ Invalid amount.")


def process_adjust_limit(m, tu, orig_id):
    try:
        bot.clear_step_handler_by_chat_id(m.chat.id)
    except Exception:
        pass
    if m.text and (m.text.startswith('/') or m.text.lower() == "/cancel"):
        cancel_current_operation(m)
        return
    try:
        nr = int(m.text.strip())
        if nr < 0:
            send_with_retry(bot.send_message, m.chat.id, "Amount cannot be negative.")
            return
        if tu in db:
            if db[tu]["last_scan_date"] != get_today_utc():
                db[tu]["today_scans"] = 0
                db[tu]["last_scan_date"] = get_today_utc()
            dl = get_user_daily_limit(tu)
            if dl != float('inf'):
                db[tu]["today_scans"] = max(0, dl - nr)
            save_db(db, DB_FILE)
            send_with_retry(bot.send_message, m.chat.id, f"✅ Adjusted remaining limit for user {tu} to {nr}.")
            show_user_controls(m.chat.id, tu, orig_id)
    except Exception:
        send_with_retry(bot.send_message, m.chat.id, "❌ Invalid amount.")


def process_restore_backup(m, orig_id):
    try:
        bot.clear_step_handler_by_chat_id(m.chat.id)
    except Exception:
        pass
    if m.text and (m.text.startswith('/') or m.text.lower() == "/cancel"):
        cancel_current_operation(m)
        return
    if not m.document or not m.document.file_name.endswith('.db'):
        send_with_retry(bot.send_message, m.chat.id, "❌ Please send a valid SQLite database (.db) backup file.")
        return
    try:
        tf = f"temp_backup_{uuid.uuid4()}.db"
        with open(tf, 'wb') as f:
            f.write(bot.download_file(bot.get_file(m.document.file_id).file_path))
        send_with_retry(bot.send_message, m.chat.id, "✅ <b>Backup restored successfully!</b>" if restore_backup(tf) else "❌ <b>Restore failed!</b>")
        os.remove(tf)
        mk = InlineKeyboardMarkup(row_width=2)
        mk.add(
            InlineKeyboardButton("⚙️ Settings", callback_data="owner_settings", style="primary"),
            InlineKeyboardButton("📢 Broadcast", callback_data="owner_broadcast", style="primary"),
            InlineKeyboardButton("🔗 Force Subscribe", callback_data="owner_forcesub", style="primary"),
            InlineKeyboardButton("📊 Full Statistics", callback_data="full_stats", style="primary"),
            InlineKeyboardButton("👥 Users List", callback_data="users_list", style="primary"),
            InlineKeyboardButton("⚡ Threads Config", callback_data="threads_config", style="primary"),
            InlineKeyboardButton("🎁 Manage Gifts", callback_data="manage_gifts", style="success"),
            InlineKeyboardButton("🔑 Manage Keys", callback_data="manage_keys", style="success"),
            InlineKeyboardButton("🔙 Back", callback_data="back_home", style="danger"),
        )
        try:
            send_with_retry(bot.edit_message_text, "<b>👑 Owner Control Panel</b>\n\nSelect an option:", m.chat.id, orig_id, reply_markup=mk)
        except Exception:
            pass
    except Exception as e:
        send_with_retry(bot.send_message, m.chat.id, f"❌ Error restoring backup: {str(e)}")


def get_forwarded_message(m):
    try:
        bot.clear_step_handler_by_chat_id(m.chat.id)
    except Exception:
        pass
    if m.text and (m.text.startswith('/') or m.text.lower() == "/cancel"):
        cancel_current_operation(m)
        return
    if not m.forward_from_chat:
        send_with_retry(bot.send_message, m.chat.id, "❌ Please forward a message from the channel.")
        return
    msg = send_with_retry(bot.send_message, m.chat.id, f"✅ Channel detected: <b>{m.forward_from_chat.title}</b>\n\n<b>Step 2:</b> Now send the channel invite link\n\n<i>Send /cancel to abort.</i>")
    bot.register_next_step_handler(msg, get_channel_link, str(m.forward_from_chat.id), m.forward_from_chat.title)


def get_channel_link(m, cid, ctitle):
    try:
        bot.clear_step_handler_by_chat_id(m.chat.id)
    except Exception:
        pass
    if m.text and (m.text.startswith('/') or m.text.lower() == "/cancel"):
        cancel_current_operation(m)
        return
    clink = m.text.strip()
    if not clink.startswith("https://t.me/"):
        send_with_retry(bot.send_message, m.chat.id, "❌ Invalid link.")
        return
    if f"{cid}|{clink}" in force_subs:
        send_with_retry(bot.send_message, m.chat.id, "❌ This channel is already in the list.")
        return
    force_subs.append(f"{cid}|{clink}")
    save_db(force_subs, FORCE_DB)
    send_with_retry(bot.send_message, m.chat.id, f"✅ Successfully added channel: <b>{ctitle}</b>\n🔗 Link: {clink}")
    mk = InlineKeyboardMarkup(row_width=1)
    for sub in force_subs:
        try:
            mk.add(InlineKeyboardButton(f"❌ {bot.get_chat(sub.split('|')[0]).title}", callback_data=f"remove_channel_{sub.split('|')[0]}", style="danger"))
        except Exception:
            mk.add(InlineKeyboardButton(f"❌ {sub}", callback_data=f"remove_channel_{sub}", style="danger"))
    mk.add(InlineKeyboardButton("➕ Add Channel", callback_data="add_sub_channel", style="success"), InlineKeyboardButton("🔙 Back", callback_data="owner_panel", style="danger"))
    send_with_retry(bot.send_message, m.chat.id, f"<b>🔗 Force Subscribe Channels</b>\n\nCurrent Channels ({len(force_subs)}):\n" + ("\n".join([f"• {s.split('|')[0]}" for s in force_subs]) if force_subs else "No channels set yet."), reply_markup=mk)


def broadcast_message(m):
    try:
        bot.clear_step_handler_by_chat_id(m.chat.id)
    except Exception:
        pass
    if m.text and (m.text.startswith('/') or m.text.lower() == "/cancel"):
        cancel_current_operation(m)
        return
    send_with_retry(bot.send_message, m.chat.id, "📢 Starting broadcast...")
    count = 0
    for uid in list(db.keys()):
        if str(uid) in banned_users:
            continue
        try:
            send_with_retry(bot.copy_message, uid, m.chat.id, m.message_id)
            count += 1
            time.sleep(0.05)
        except Exception:
            pass
    send_with_retry(bot.send_message, m.chat.id, f"✅ Broadcast finished!\nSent to <code>{count}</code> users.")


def auto_backup_loop():
    while not shutdown_flag:
        for _ in range(12 * 3600):
            if shutdown_flag:
                return
            time.sleep(1)
        try:
            bf = create_backup()
            with open(bf, 'rb') as f:
                send_with_retry(bot.send_document, OWNER_ID, f, caption=f"🔄 <b>Auto-Backup (12H)</b>\n━━━━━━━━━━━━━━━━━━━━━━━━━━━\n📅 Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}\n✅ Database successfully backed up.")
        except Exception:
            pass


threading.Thread(target=auto_backup_loop, daemon=True).start()

print(f"🤖 {BRAND} is Running...")
print(f"   Owner ID: {OWNER_ID}")
print(f"   Bot: @{BOT_USERNAME.replace('@','')}")
print(f"   Support: @{SUPPORT_HANDLE}")
print()

while BOT_RUNNING:
    try:
        bot.polling(none_stop=True, timeout=60, long_polling_timeout=60)
    except Exception:
        time.sleep(3)