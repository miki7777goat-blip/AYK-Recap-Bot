from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import threading
from supabase import Client, create_client
import telebot
from telebot import types

# ==========================================
# 1. ENVIRONMENT VARIABLES & SETUP
# ==========================================
BOT_TOKEN = os.environ.get(
    "BOT_TOKEN", "8909534863:AAEcK211jGacRR_e4mUZQmKqxeH4tVAxqWU"
)
OWNER_IDS = {8415289516}
ADMIN_GROUP_ID = int(os.environ.get("ADMIN_GROUP_ID", "-1004448651266"))
SUPPORT_TOPIC_ID = int(os.environ.get("SUPPORT_TOPIC_ID", "99"))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

WEBHOOK_URL = os.environ.get(
    "WEBHOOK_URL",
    "https://aykrecaptool.lovable.app/api/public-bot-webhook",
)
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
PORT = int(os.environ.get("PORT", "10000"))

supabase: Client | None = (
    create_client(SUPABASE_URL, SUPABASE_KEY)
    if SUPABASE_URL and SUPABASE_KEY
    else None
)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# Editing states:
# EDITING_STATE[user_id] = {"target": "main_config" | "settings", "key": "..."}
EDITING_STATE: dict[int, dict[str, str]] = {}
BROADCAST_WAITING: set[int] = set()
SLIP_WAITING: set[int] = set()

# ==========================================
# 2. DEFAULT DATA & SUPABASE CONFIG HELPERS
# ==========================================
DEFAULT_SETTINGS = {
    "kpay_phone": "09xxxxxxxxx",
    "kpay_name": "Owner Name",
    "wave_phone": "09xxxxxxxxx",
    "wave_name": "Owner Name",
    "pro_price": "3,000 Ks / 1 Month",
    "vip_price": "25,000 Ks / 1 Month",
    "support_username": "mikef07",
    "referral_discount": 250,
}

DEFAULT_MESSAGES = {
    "welcome": "👋 မင်္ဂလာပါ {first_name}",
    "ref_info": "👥 Referral အချက်အလက်\nTotal Referrals: {count}",
    "ref_notify": "🔔 Referral အသစ်ဝင်လာပါပြီ: {user}",
    "approve_user": "✅ သင့်အကောင့်ကို အတည်ပြုပြီးပါပြီ။",
    "reject_user": "❌ သင့်တောင်းဆိုချက်ကို ငြင်းပယ်လိုက်ပါသည်။",
    "slip_submitted": "📩 Slip ပေးပို့ပြီးပါပြီ။ Admin မှ စစ်ဆေးပေးပါမည်။",
}

DEFAULT_DATA = {
    "settings": DEFAULT_SETTINGS,
    "messages": DEFAULT_MESSAGES,
    "known_users": [],
    "referrals": {},
    "referral_counts": {},
}

FIELD_MAP = {
    "edit_welcome": "welcome_message",
    "edit_ref_info": "ref_info_msg",
    "edit_ref_notify": "ref_notify_msg",
    "edit_approve_msg": "approve_msg",
    "edit_reject_msg": "reject_msg",
    "edit_slip_msg": "slip_msg",
    "edit_custom_notices": "custom_notices",
}

SETTING_BUTTON_MAP = {
    "edit_kpay": "kpay_phone",
    "edit_wave": "wave_phone",
    "edit_pro_price": "pro_price",
    "edit_vip_price": "vip_price",
    "edit_ref_discount": "referral_discount",
    "edit_support": "support_username",
}


def get_main_config() -> dict:
    """Fetch 'data' dictionary from 'bot_config' table where id == 'main_config'."""
    if not supabase:
        return {}

    res = (
        supabase.table("bot_config")
        .select("data")
        .eq("id", "main_config")
        .single()
        .execute()
    )
    raw = res.data.get("data") if res.data else None

    if raw is None or raw == "":
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def save_main_config(updated_data: dict) -> dict:
    """Persist full config dictionary to Supabase bot_config (main_config)."""
    if not supabase:
        return updated_data

    res = (
        supabase.table("bot_config")
        .select("data")
        .eq("id", "main_config")
        .single()
        .execute()
    )
    existing_raw = res.data.get("data") if res.data else None
    payload_value = (
        json.dumps(updated_data, ensure_ascii=False)
        if isinstance(existing_raw, str)
        else updated_data
    )

    supabase.table("bot_config").update({"data": payload_value}).eq(
        "id", "main_config"
    ).execute()
    return updated_data


def update_main_config_field(field_key: str, new_value) -> dict:
    """Update a top-level key in 'main_config'."""
    current_data = get_main_config()
    current_data[field_key] = new_value
    return save_main_config(current_data)


def update_nested_setting(setting_key: str, new_value) -> dict:
    """Update a key inside data['settings'] in 'main_config'."""
    current_data = get_main_config()
    settings = current_data.get("settings")
    if not isinstance(settings, dict):
        settings = dict(DEFAULT_SETTINGS)
    if setting_key == "referral_discount":
        try:
            new_value = int(str(new_value).strip())
        except ValueError:
            pass
    settings[setting_key] = new_value
    current_data["settings"] = settings
    return save_main_config(current_data)


def load_data() -> dict:
    """Load merged data combining defaults and Supabase main_config."""
    cfg = get_main_config()
    merged = json.loads(json.dumps(DEFAULT_DATA))
    if isinstance(cfg, dict):
        if isinstance(cfg.get("settings"), dict):
            merged["settings"].update(cfg["settings"])
        if isinstance(cfg.get("messages"), dict):
            merged["messages"].update(cfg["messages"])
        for key in ("known_users", "referrals", "referral_counts"):
            if key in cfg:
                merged[key] = cfg[key]
    return merged


def register_user_and_referral(user_id: int, start_payload: str = ""):
    """Track known users and optional referral ID."""
    cfg = get_main_config()
    known_users = cfg.get("known_users")
    if not isinstance(known_users, list):
        known_users = []

    is_new_user = user_id not in known_users
    if is_new_user:
        known_users.append(user_id)
        cfg["known_users"] = known_users

    referrals = cfg.get("referrals")
    if not isinstance(referrals, dict):
        referrals = {}

    ref_counts = cfg.get("referral_counts")
    if not isinstance(ref_counts, dict):
        ref_counts = {}

    notified_referrer_id = None
    if start_payload and start_payload.isdigit():
        referrer_id = int(start_payload)
        str_uid = str(user_id)
        str_ref = str(referrer_id)
        if referrer_id != user_id and str_uid not in referrals:
            referrals[str_uid] = referrer_id
            ref_counts[str_ref] = int(ref_counts.get(str_ref, 0)) + 1
            cfg["referrals"] = referrals
            cfg["referral_counts"] = ref_counts
            notified_referrer_id = referrer_id

    if is_new_user or notified_referrer_id:
        save_main_config(cfg)

    return notified_referrer_id
