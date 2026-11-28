import os
import json
import logging
import telebot
from telebot import types
from supabase import create_client, Client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

CONFIG_TABLE = "bot_config"
CONFIG_ROW_ID = "main_config"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

DEFAULT_CONFIG = {
    "kpay": "09xxxxxxxxx (Owner Name)",
    "wave": "09xxxxxxxxx (Owner Name)",
    "pro_price": "3,000 Ks / 1 Month",
    "vip_price": "5,000 Ks / 1 Month",
    "ref_rate_ks": 250,
    "pro_ref_target": 12,
    "vip_ref_target": 20,
    "support": "@mikef07",
    "known_users": 1,
    "banned_users": 0,
    "users": {},
    "notifications": {
        "welcome": "🎉 မင်္ဂလာပါ! <b>AYK Recap Bot</b> မှ နွေးထွေးစွာ ကြိုဆိုပါတယ်။",
        "support_prompt": "💬 Admin ထံ ဆက်သွယ်လိုသော မက်ဆေ့ခ်ျကို ရိုက်ပို့ပေးပါ။",
        "plan_update": "✨ သင့် Plan အခြေအနေ ပြောင်းလဲသွားပါပြီ။",
    },
}

EDITABLE_FIELDS = {
    "kpay": {
        "title": "💳 KPay အချက်အလက်",
        "format_hint": "<code>ဖုန်းနံပါတ် (ပိုင်ရှင်အမည်)</code>",
        "example": "09965376292 (Ko Myo Min Naing)",
        "type": "str",
    },
    "wave": {
        "title": "🌊 Wave အချက်အလက်",
        "format_hint": "<code>ဖုန်းနံပါတ် (ပိုင်ရှင်အမည်)</code>",
        "example": "09965376292 (Ko Myo Min Naing)",
        "type": "str",
    },
    "pro_price": {
        "title": "💎 Pro Plan ဈေးနှုန်း",
        "format_hint": "<code>ဈေးနှုန်း / ကာလ</code>",
        "example": "3,000 Ks / 1 Month",
        "type": "str",
    },
    "vip_price": {
        "title": "👑 VIP Plan ဈေးနှုန်း",
        "format_hint": "<code>ဈေးနှုန်း / ကာလ</code>",
        "example": "5,000 Ks / 1 Month",
        "type": "str",
    },
    "ref_rate_ks": {
        "title": "🎁 Referral Rate (Ks)",
        "format_hint": "ဂဏန်းသီးသန့် ဥပမာ - <code>250</code>",
        "example": "250",
        "type": "int",
    },
    "pro_ref_target": {
        "title": "🎯 Pro Referral Target",
        "format_hint": "ဂဏန်းသီးသန့် ဥပမာ - <code>12</code>",
        "example": "12",
        "type": "int",
    },
    "vip_ref_target": {
        "title": "🏆 VIP Referral Target",
        "format_hint": "ဂဏန်းသီးသန့် ဥပမာ - <code>20</code>",
        "example": "20",
        "type": "int",
    },
    "support": {
        "title": "🛟 Support Username",
        "format_hint": "<code>@username</code> ပုံစံဖြင့် ရိုက်ထည့်ပါ",
        "example": "@mikef07",
        "type": "str",
    },
}
def _default_user_record(user_id: int, username: str = "", full_name: str = "") -> dict:
    return {
        "user_id": int(user_id),
        "username": username or "",
        "full_name": full_name or "",
        "plan": "free",
        "app_linked": False,
        "app_account_id": "",
        "banned": False,
        "referrals": 0,
        "invited_by": None,
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
    cfg = get_config()
    cfg[key] = value
    return save_config(cfg)


def register_or_update_user(user: types.User) -> dict:
    cfg = get_config()
    users = cfg.setdefault("users", {})
    uid_str = str(user.id)
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()

    if uid_str not in users or not isinstance(users[uid_str], dict):
        users[uid_str] = _default_user_record(user.id, user.username or "", full_name)
    else:
        if user.username:
            users[uid_str]["username"] = user.username
        if full_name:
            users[uid_str]["full_name"] = full_name

    _sync_user_counts(cfg)
    save_config(cfg)
    return users[uid_str]
