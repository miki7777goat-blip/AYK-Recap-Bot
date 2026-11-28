# --- အပိုင်း (၁): Imports, Config & Supabase Setup ---
import os
import json
import logging
import telebot
from telebot import types
from supabase import create_client, Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

SUPABASE_URL = os.getenv("SUPABASE_URL", "YOUR_SUPABASE_URL_HERE")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "YOUR_SUPABASE_KEY_HERE")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

CONFIG_TABLE = "bot_config"
CONFIG_ROW_ID = "main_config"

DEFAULT_CONFIG = {
    "kpay": "09xxxxxxxxx (Owner Name)",
    "wave": "09xxxxxxxxx (Owner Name)",
    "pro_price": "3,000 Ks / 1 Month",
    "vip_price": "5,000 Ks / 1 Month",
    "ref_rate_ks": 250,
    "pro_ref_target": 12,   # 3,000 / 250 = 12 ယောက်
    "vip_ref_target": 20,   # 5,000 / 250 = 20 ယောက်
    "support": "@mikef07",
    "known_users": 1,
    "banned_users": 0,
    "users": {},
    "notifications": {
        "welcome": "မင်္ဂလာပါ! Bot မှ ကြိုဆိုပါတယ်။",
        "support_prompt": "Admin ထံ ဆက်သွယ်ရန် မက်ဆေ့ချ် ရိုက်ပို့ပေးပါ။",
        "plan_update": "သင့် Plan အခြေအနေ ပြောင်းလဲသွားပါပြီ။",
    },
}

USER_STATES = {}
# --- အပိုင်း (၂): Database Load, Save, User Control, Referral & Notification Helpers ---
def _default_user_record(user_id: int, username: str = "", full_name: str = "") -> dict:
    return {
        "user_id": int(user_id),
        "username": username or "",
        "full_name": full_name or "",
        "plan": "free",               # "free" | "pro" | "vip"
        "app_linked": False,          # App နဲ့ ချိတ်ဆက်ထားလား
        "app_account_id": "",         # ချိတ်ဆက်ထားတဲ့ App / Account ID
        "banned": False,              # Ban / Unban အခြေအနေ
        "referrals": 0,               # ဖိတ်ခေါ်နိုင်ခဲ့တဲ့ အရေအတွက်
        "invited_by": None,           # ဖိတ်ခေါ်ခဲ့သူ user_id
    }


def _sync_user_counts(cfg: dict) -> None:
    users = cfg.get("users")
    if not isinstance(users, dict):
        cfg["users"] = {}
        users = cfg["users"]
    if users:
        cfg["known_users"] = len(users)
        cfg["banned_users"] = sum(
            1 for u in users.values() if isinstance(u, dict) and u.get("banned")
        )
    else:
        cfg["known_users"] = max(int(cfg.get("known_users", 0) or 0), 0)
        cfg["banned_users"] = max(int(cfg.get("banned_users", 0) or 0), 0)


def get_config() -> dict:
    """Supabase `bot_config` table ထဲက `main_config` row ရဲ့ `data` ကို ဖတ်ယူပြီး default နှင့် ပေါင်းစပ်ပေးသည်။"""
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        resp = (
            supabase.table(CONFIG_TABLE)
            .select("data")
            .eq("id", CONFIG_ROW_ID)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if rows and isinstance(rows[0].get("data"), dict):
            db_data = rows[0]["data"]
            for k, v in db_data.items():
                if k == "notifications" and isinstance(v, dict):
                    merged["notifications"].update(v)
                elif k == "users" and isinstance(v, dict):
                    merged["users"] = v
                else:
                    merged[k] = v
    except Exception as e:
        logger.error(f"get_config error: {e}")
    _sync_user_counts(merged)
    return merged


def save_config(new_config: dict) -> bool:
    """Configuration dictionary တစ်ခုလုံးကို Supabase `bot_config` (`main_config`) ထဲတွင် သိမ်းဆည်းသည်။"""
    try:
        _sync_user_counts(new_config)
        payload = {
            "id": CONFIG_ROW_ID,
            "data": new_config,
        }
        supabase.table(CONFIG_TABLE).upsert(payload, on_conflict="id").execute()
        return True
    except Exception as e:
        logger.error(f"save_config error: {e}")
        return False


def update_config_key(key: str, value) -> bool:
    """Key တစ်ခုတည်းကို အမြန် update လုပ်ပြီး Supabase ထဲ သိမ်းဆည်းသည်။"""
    cfg = get_config()
    cfg[key] = value
    return save_config(cfg)


def register_or_update_user(
    user_id: int,
    username: str = "",
    full_name: str = "",
    invited_by: int | None = None,
) -> dict:
    """User ကို မှတ်တမ်းတင်ပြီး referral ရှိပါက ဖိတ်ခေါ်သူရဲ့ count ကို တိုးပေးသည်။"""
    cfg = get_config()
    users = cfg.setdefault("users", {})
    uid_str = str(int(user_id))

    is_new = uid_str not in users
    rec = _default_user_record(user_id, username, full_name)
    if not is_new and isinstance(users[uid_str], dict):
        rec.update(users[uid_str])
    if username:
        rec["username"] = username
    if full_name:
        rec["full_name"] = full_name

    if (
        is_new
        and invited_by is not None
        and int(invited_by) != int(user_id)
        and not rec.get("invited_by")
    ):
        inv_str = str(int(invited_by))
        if inv_str not in users:
            users[inv_str] = _default_user_record(int(invited_by))
        users[inv_str]["referrals"] = int(users[inv_str].get("referrals", 0) or 0) + 1
        rec["invited_by"] = int(invited_by)

    users[uid_str] = rec
    save_config(cfg)
    return rec


def set_user_ban(user_id: int, banned: bool) -> tuple[bool, dict]:
    """User တစ်ယောက်ကို Ban / Unban လုပ်သည်။"""
    cfg = get_config()
    users = cfg.setdefault("users", {})
    uid_str = str(int(user_id))
    rec = _default_user_record(user_id)
    if isinstance(users.get(uid_str), dict):
        rec.update(users[uid_str])
    rec["banned"] = bool(banned)
    users[uid_str] = rec
    ok = save_config(cfg)
    return ok, rec


def set_user_plan(user_id: int, plan: str) -> tuple[bool, dict]:
    """User ရဲ့ Plan ကို 'free', 'pro', 'vip' သတ်မှတ်သည်။"""
    plan_clean = (plan or "free").strip().lower()
    if plan_clean not in ("free", "pro", "vip"):
        plan_clean = "free"
    cfg = get_config()
    users = cfg.setdefault("users", {})
    uid_str = str(int(user_id))
    rec = _default_user_record(user_id)
    if isinstance(users.get(uid_str), dict):
        rec.update(users[uid_str])
    rec["plan"] = plan_clean
    users[uid_str] = rec
    ok = save_config(cfg)
    return ok, rec


def set_user_app_link(user_id: int, linked: bool, app_account_id: str = "") -> tuple[bool, dict]:
    """User ရဲ့ App ချိတ်ဆက်မှု အခြေအနေ (linked / unlinked + account ID) ကို သိမ်းဆည်းသည်။"""
    cfg = get_config()
    users = cfg.setdefault("users", {})
    uid_str = str(int(user_id))
    rec = _default_user_record(user_id)
    if isinstance(users.get(uid_str), dict):
        rec.update(users[uid_str])
    rec["app_linked"] = bool(linked)
    rec["app_account_id"] = (app_account_id or "").strip() if linked else ""
    users[uid_str] = rec
    ok = save_config(cfg)
    return ok, rec


def calculate_referral_status(cfg: dict, referrals_count: int) -> dict:
    """ဥပမာ- 250 Ks/ယောက် -> Pro (3,000 = 12 ယောက်), VIP (5,000 = 20 ယောက်) အတိုင်း တွက်ချက်သည်။"""
    rate = max(int(cfg.get("ref_rate_ks", 250) or 250), 1)
    pro_target = max(int(cfg.get("pro_ref_target", 12) or 12), 1)
    vip_target = max(int(cfg.get("vip_ref_target", 20) or 20), 1)
    refs = max(int(referrals_count or 0), 0)

    earned_ks = refs * rate
    pro_unlocked = refs // pro_target
    vip_unlocked = refs // vip_target
    to_next_pro = 0 if refs >= pro_target else (pro_target - refs)
    to_next_vip = 0 if refs >= vip_target else (vip_target - refs)

    return {
        "rate_ks": rate,
        "earned_ks": earned_ks,
        "pro_target": pro_target,
        "vip_target": vip_target,
        "pro_unlocked": pro_unlocked,
        "vip_unlocked": vip_unlocked,
        "to_next_pro": to_next_pro,
        "to_next_vip": to_next_vip,
    }


def format_user_detail(cfg: dict, user_id: int) -> str:
    """User တစ်ယောက်ရဲ့ Plan၊ App Link၊ Ban Status နဲ့ Referral တွက်ချက်မှုကို စာသားအဖြစ် ဖွဲ့စည်းသည်။"""
    users = cfg.get("users") or {}
    rec = _default_user_record(user_id)
    if isinstance(users.get(str(int(user_id))), dict):
        rec.update(users[str(int(user_id))])

    plan_label = {
        "free": "Free Plan",
        "pro": "Pro Plan",
        "vip": "VIP Plan",
    }.get(str(rec.get("plan", "free")).lower(), "Free Plan")

    if rec.get("app_linked"):
        acc_id = rec.get("app_account_id") or "ချိတ်ဆက်ထားသည်"
        app_status = f"✅ ချိတ်ဆက်ထားပါသည် (<code>{acc_id}</code>)"
    else:
        app_status = "❌ မချိတ်ဆက်ရသေးပါ"

    ban_status = "🚫 Banned" if rec.get("banned") else "✅ Active (Ban မခံရပါ)"
    ref_info = calculate_referral_status(cfg, rec.get("referrals", 0))

    uname = f"@{rec['username']}" if rec.get("username") else "မရှိပါ"
    return (
        f"👤 <b>User အချက်အလက်:</b> <code>{rec['user_id']}</code>\n"
        f"• Name: <code>{rec.get('full_name') or '-'}</code> ({uname})\n"
        f"• Plan: <b>{plan_label}</b>\n"
        f"• App Link: {app_status}\n"
        f"• Status: <b>{ban_status}</b>\n"
        f"• Referrals: <code>{rec.get('referrals', 0)}</code> ယောက် "
        f"(စုစုပေါင်း <code>{ref_info['earned_ks']:,} Ks</code>)\n"
        f"• Pro Target ({ref_info['pro_target']} ယောက်): "
        f"<code>{ref_info['pro_unlocked']}</code> ကြိမ်ရရှိ / လိုသေး: <code>{ref_info['to_next_pro']}</code> ယောက်\n"
        f"• VIP Target ({ref_info['vip_target']} ယောက်): "
        f"<code>{ref_info['vip_unlocked']}</code> ကြိမ်ရရှိ / လိုသေး: <code>{ref_info['to_next_vip']}</code> ယောက်"
    )


def format_settings_summary(cfg: dict) -> str:
    """Owner Control Panel အောက်မှာ ပြသမည့် လက်ရှိ ဆက်တင်အနှစ်ချုပ် စာသားကို တည်ဆောက်သည်။"""
    _sync_user_counts(cfg)
    users = cfg.get("users") or {}
    free_cnt = sum(1 for u in users.values() if isinstance(u, dict) and u.get("plan", "free") == "free")
    pro_cnt = sum(1 for u in users.values() if isinstance(u, dict) and u.get("plan") == "pro")
    vip_cnt = sum(1 for u in users.values() if isinstance(u, dict) and u.get("plan") == "vip")
    linked_cnt = sum(1 for u in users.values() if isinstance(u, dict) and u.get("app_linked"))

    return (
        "⚙️ <b>လက်ရှိ ဆက်တင်များ:</b>\n"
        f"• KPay: <code>{cfg.get('kpay', '')}</code>\n"
        f"• Wave: <code>{cfg.get('wave', '')}</code>\n"
        f"• Pro Price: <code>{cfg.get('pro_price', '')}</code>\n"
        f"• VIP Price: <code>{cfg.get('vip_price', '')}</code>\n"
        f"• Referral Rate: <code>{cfg.get('ref_rate_ks', 250)} Ks / ယောက်</code>\n"
        f"• Pro Ref Target: <code>{cfg.get('pro_ref_target', 12)} ယောက်</code> | "
        f"VIP Ref Target: <code>{cfg.get('vip_ref_target', 20)} ယောက်</code>\n"
        f"• Support: <code>{cfg.get('support', '')}</code>\n"
        f"• Known Users: <code>{cfg.get('known_users', 0)}</code> ယောက် "
        f"(Free: <code>{free_cnt}</code>, Pro: <code>{pro_cnt}</code>, VIP: <code>{vip_cnt}</code>)\n"
        f"• App Linked Users: <code>{linked_cnt}</code> ယောက် | "
        f"Banned Users: <code>{cfg.get('banned_users', 0)}</code> ယောက်"
        )
