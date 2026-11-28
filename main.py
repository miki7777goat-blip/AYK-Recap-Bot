import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone
import requests
import telebot
from telebot import types

# ==================== ENVIRONMENT VARIABLES ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8909534863:AAEck21ljGacrRR_e4mUZQmGKqeH4tVAqwU")
OWNER_ID = int(os.getenv("OWNER_ID", "8415289516"))  # Owner ၏ Telegram Chat ID (ဂဏန်းသီးသန့်)
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "-1004448651266"))  # အဓိက Admin Group ID
SUPPORT_TOPIC_ID = int(os.getenv("SUPPORT_TOPIC_ID", "99"))  # User များနှင့် အမေးအဖြေလုပ်မည့် Topic ID

WEBHOOK_URL = os.getenv(
    "WEBHOOK_URL",
    "https://aykrecaptool.lovable.app/api/public/subscription/update"
)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "OSv2efvHvWGB6b4l6jGsr87IZvyYLhMcH5V2YHuHgvSWKpJt")
PORT = int(os.getenv("PORT", "10000"))  # Render အတွက် Port

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ==================== DATA PERSISTENCE ====================
DATA_FILE = "bot_data.json"

DEFAULT_DATA = {
    "settings": {
        "kpay_phone": "09xxxxxxxxx",
        "kpay_name": "Owner Name",
        "wave_phone": "09xxxxxxxxx",
        "wave_name": "Owner Name",
        "pro_price": "3,000 Ks / 1 Month",
        "vip_price": "25,000 Ks / 1 Month",
        "support_username": "mikef07",
        "referral_discount": 250  # ဖိတ်ခေါ်သူတစ်ဦးလျှင် လျှော့ပေးမည့် ပမာဏ (Ks)
    },
    "banned_users": [],
    "known_users": [],     # Broadcast ပို့ရန် မှတ်သားထားသော User ID များ
    "referrals": {},       # { referred_user_id: referrer_user_id }
    "referral_counts": {}  # { referrer_user_id: active_count }
}


def parse_amount_ks(price_str: str, fallback: int = 3000) -> int:
    digits = "".join(ch for ch in str(price_str) if ch.isdigit())
    return int(digits) if digits else fallback


def load_data():
    data = json.loads(json.dumps(DEFAULT_DATA))
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data["settings"].update(loaded.get("settings", {}))
                data["banned_users"] = loaded.get("banned_users", [])
                data["known_users"] = loaded.get("known_users", [])
                data["referrals"] = loaded.get("referrals", {})
                data["referral_counts"] = loaded.get("referral_counts", {})
        except Exception:
            pass
    return data


def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")


def register_known_user(user_id: int):
    uid_int = int(user_id)
    if uid_int not in bot_data["known_users"]:
        bot_data["known_users"].append(uid_int)
        save_data(bot_data)


def get_referral_count(user_id: int) -> int:
    return int(bot_data["referral_counts"].get(str(user_id), 0))


def get_referral_discount_per_user() -> int:
    try:
        return max(0, int(bot_data["settings"].get("referral_discount", 250)))
    except Exception:
        return 250


def get_pro_price_ks() -> int:
    return parse_amount_ks(bot_data["settings"].get("pro_price", "3,000 Ks / 1 Month"), 3000)


def get_required_referrals_for_free_pro() -> int:
    discount_per = get_referral_discount_per_user()
    if discount_per <= 0:
        return 0
    pro_ks = get_pro_price_ks()
    return (pro_ks + discount_per - 1) // discount_per


bot_data = load_data()
user_states = {}  # In-memory user state handling


# ==================== WEBHOOK INTEGRATION ====================
def call_subscription_webhook(email: str, plan: str, duration_days: int = 30):
    """App Backend သို့ Webhook ပို့၍ Plan ဖွင့်ပေးခြင်း"""
    if not WEBHOOK_SECRET:
        return {"success": False, "error": "WEBHOOK_SECRET is not configured"}

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Secret": WEBHOOK_SECRET,
    }
    approval_time = datetime.now(timezone.utc).isoformat()
    payload = {
        "email": email.strip().lower(),
        "plan": plan.upper(),
        "status": "ACTIVE",
        "startDate": approval_time,
        "durationDays": duration_days
    }

    try:
        res = requests.post(WEBHOOK_URL, headers=headers, json=payload, timeout=20)
        data = res.json()
        if res.status_code == 200 and data.get("ok"):
            return {"success": True, "data": data}
        return {"success": False, "error": data.get("error", f"HTTP {res.status_code}")}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ==================== KEYBOARDS ====================
def main_menu_keyboard(user_id: int):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("👤 Profile"),
        types.KeyboardButton("💎 Buy Plan"),
        types.KeyboardButton("👥 Referral"),
        types.KeyboardButton("💬 Chat with Admin"),
        types.KeyboardButton("📞 Support")
    )
    if user_id == OWNER_ID:
        markup.add(types.KeyboardButton("⚙️ Owner Menu"))
    return markup


def chat_exit_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("❌ Exit Chat"))
    return markup


def owner_inline_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💳 Edit KPay", callback_data="owner_set_kpay"),
        types.InlineKeyboardButton("🌊 Edit Wave", callback_data="owner_set_wave"),
        types.InlineKeyboardButton("💰 Edit Pro Price", callback_data="owner_set_pro_price"),
        types.InlineKeyboardButton("👑 Edit VIP Price", callback_data="owner_set_vip_price"),
        types.InlineKeyboardButton("🎁 Edit Ref Discount", callback_data="owner_set_ref_discount"),
        types.InlineKeyboardButton("📞 Edit Support", callback_data="owner_set_support"),
        types.InlineKeyboardButton("📢 Send Broadcast", callback_data="owner_broadcast"),
        types.InlineKeyboardButton("📋 View Settings", callback_data="owner_view_settings")
    )
    return markup
