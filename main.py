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
OWNER_ID = int(os.getenv("OWNER_ID", "8415289516"))
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "-1004448651266"))
SUPPORT_TOPIC_ID = int(os.getenv("SUPPORT_TOPIC_ID", "99"))

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

WEBHOOK_URL = os.getenv(
    "WEBHOOK_URL",
    "https://aykrecaptool.lovable.app/api/public/subscription/update"
)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "OSv2efvHvWGB6b4l6jGsr87IZvyYLhMcH5V2YHuHgvSWKpJt")
PORT = int(os.getenv("PORT", "10000"))

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ==================== SUPABASE DATA PERSISTENCE ====================
DEFAULT_SETTINGS = {
    "kpay_phone": "09xxxxxxxxx",
    "kpay_name": "Owner Name",
    "wave_phone": "09xxxxxxxxx",
    "wave_name": "Owner Name",
    "pro_price": "3,000 Ks / 1 Month",
    "vip_price": "25,000 Ks / 1 Month",
    "support_username": "mikef07",
    "referral_discount": 250
}

DEFAULT_MESSAGES = {
    "welcome": "👋 မင်္ဂလာပါ <b>{first_name}</b>!\n\nAYK Recap Bot မှ ကြိုဆိုပါသည်။ အောက်ပါ Menu မှတစ်ဆင့် အသုံးပြုနိုင်ပါပြီ။",
    "referral_notify": "🎉 <b>Referral အသစ် ဝင်ရောက်လာပါသည်!</b>\n━━━━━━━━━━━━━━━━━━━\n• ဖိတ်ခံရသူ: {invited_name}\n• လက်ရှိ Referral Count: <b>{ref_count}</b> ယောက်",
    "approve_user": "🎉 <b>ဂုဏ်ယူပါသည်!</b>\n\nသင့်အကောင့် (<code>{email}</code>) ကို <b>{plan} Plan</b> အဖြစ် အောင်မြင်စွာ အတည်ပြုဖွင့်လှစ်ပေးလိုက်ပါပြီ။\nသက်တမ်း: <code>{expiry}</code> ထိ အသုံးပြုနိုင်ပါသည်။",
    "reject_user": "င့်ငွေလွှဲစလစ်ကို ပယ်ချလိုက်ပါသည်။ Support သို့ ဆက်သွယ်ပါ။",
    "slip_submitted": "✅ သင့်ငွေလွှဲစလစ်ကို Admin ထံ တင်ပြထားပါပြီ။ စစ်ဆေးပြီးပါက App မှတစ်ဆင့် အကြောင်းကြားပေးပါမည်。"
}

DEFAULT_DATA = {
    "settings": DEFAULT_SETTINGS,
    "messages": DEFAULT_MESSAGES,
    "banned_users": [],
    "known_users": [],
    "referrals": {},
    "referral_counts": {}
}

def load_data():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Supabase credentials missing, using default data.")
        return DEFAULT_DATA
    
    url = f"{SUPABASE_URL}/rest/v1/bot_state?id=eq.main_config&select=data"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Prefer": "return=representation"
    }
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200 and res.json():
            loaded_data = res.json()[0]["data"]
            # Ensure messages dict exists for backward compatibility
            if "messages" not in loaded_data:
                loaded_data["messages"] = DEFAULT_MESSAGES.copy()
            else:
                for k, v in DEFAULT_MESSAGES.items():
                    if k not in loaded_data["messages"]:
                        loaded_data["messages"][k] = v
            return loaded_data
    except Exception as e:
        print(f"Error loading from Supabase: {e}")
    return DEFAULT_DATA

def save_data(data):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    
    url = f"{SUPABASE_URL}/rest/v1/bot_state?id=eq.main_config"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates"
    }
    payload = {"id": "main_config", "data": data}
    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print(f"Error saving to Supabase: {e}")

bot_data = load_data()
user_states = {}

def parse_amount_ks(price_str: str, fallback: int = 3000) -> int:
    digits = "".join(ch for ch in str(price_str) if ch.isdigit())
    return int(digits) if digits else fallback

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

# ==================== WEBHOOK INTEGRATION ====================
def call_subscription_webhook(email: str, plan: str, duration_days: int = 30):
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
        types.InlineKeyboardButton("💬 Edit Welcome Msg", callback_data="owner_edit_welcome"),
        types.InlineKeyboardButton("💬 Edit Ref Notify Msg", callback_data="owner_edit_ref_notify"),
        types.InlineKeyboardButton("💬 Edit Approve Msg", callback_data="owner_edit_approve"),
        types.InlineKeyboardButton("💬 Edit Reject Msg", callback_data="owner_edit_reject"),
        types.InlineKeyboardButton("💬 Edit Slip Msg", callback_data="owner_edit_slip"),
        types.InlineKeyboardButton("📢 Send Broadcast", callback_data="owner_broadcast"),
        types.InlineKeyboardButton("📋 View Settings", callback_data="owner_view_settings")
    )
    return markup
