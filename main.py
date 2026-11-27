import os
import re
import json
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone
import requests
import telebot
from telebot import types

# ==================== ENVIRONMENT VARIABLES ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8909534863:AAG9F4ZwZRaT0RYovkaEKauvEtzM91-j2qk")
OWNER_ID = int(os.getenv("OWNER_ID", "8415289516"))
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "-1004448651266"))

WEBHOOK_URL = os.getenv(
    "WEBHOOK_URL",
    "https://aykrecaptool.lovable.app/api/public/subscription/update"
)
WEBHOOK_SECRET = os.getenv(
    "WEBHOOK_SECRET",
    "OSv2efvHvWGB6b4l6jGsr87IZvyYLhMcH5V2YHuHgvSWKpJt"
)
PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing! Set BOT_TOKEN in Render Environment Variables.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ==================== DATA PERSISTENCE ====================
DATA_FILE = "bot_data.json"

DEFAULT_MESSAGES = {
    "welcome": (
        "👋 မင်္ဂလာပါ <b>{first_name}</b>!\n\n"
        "AYK Recap Bot မှ ကြိုဆိုပါသည်။ အောက်ပါ Menu မှတစ်ဆင့် အသုံးပြုနိုင်ပါပြီ။"
    ),
    "referral_info": (
        "👥 <b>သင့် Referral Link:</b>\n\n"
        "<code>{ref_link}</code>\n\n"
        "📊 ဖိတ်ခေါ်ထားသူ စုစုပေါင်း: <b>{ref_count}</b> ယောက်\n"
        "💸 ရရှိထားသော Plan လျှော့ဈေး: <b>{discount_amount:,}</b> (တစ်ယောက်လျှင် <b>{per_ref:,}</b> လျှော့ဈေး)\n"
        "မိတ်ဆွေများကို မျှဝေ၍ ဖိတ်ခေါ်ပြီး Plan ဝယ်ယူရာတွင် လျှော့ဈေးရယူနိုင်ပါသည်။"
    ),
    "referral_notify": (
        "🎉 <b>Referral အသစ် ဝင်ရောက်လာပါသည်!</b>\n\n"
        "• ဖိတ်ခေါ်ခံရသူ: <b>{invited_name}</b> (<code>{invited_id}</code>)\n"
        "• သင့် Referral စုစုပေါင်း: <b>{ref_count}</b> ယောက်\n"
        "• လက်ရှိ လျှော့ဈေး စုစုပေါင်း: <b>{discount_amount:,}</b>"
    ),
    "approve_user": (
        "🎉 <b>ဂုဏ်ယူပါသည်!</b>\n\n"
        "သင့်အကောင့် (<code>{email}</code>) ကို <b>{plan} Plan</b> အဖြစ် အောင်မြင်စွာ အတည်ပြုဖွင့်လှစ်ပေးလိုက်ပါပြီ။\n"
        "သက်တမ်း: <code>{expiry}</code> ထိ အသုံးပြုနိုင်ပါသည်။"
    ),
    "reject_insuf": (
        "❌ သင်ပေးပို့သော ငွေလွှဲစလစ်သည် ပမာဏမလုံလောက်ပါ သို့မဟုတ် မှားယွင်းနေပါသည်။ Support သို့ ဆက်သွယ်ပါ။"
    ),
    "slip_submitted": (
        "✅ သင့်ငွေလွှဲစလစ်ကို Admin ထံ တင်ပြထားပါပြီ။ စစ်ဆေးပြီးပါက Bot မှတစ်ဆင့် အကြောင်းကြားပေးပါမည်။"
    )
}

DEFAULT_DATA = {
    "settings": {
        "kpay_phone": "09xxxxxxxxx",
        "kpay_name": "Owner Name",
        "wave_phone": "09xxxxxxxxx",
        "wave_name": "Owner Name",
        "pro_price": "15,000 MMK",
        "vip_price": "30,000 MMK",
        "support_username": "mikef07",
        "referral_discount_per_person": 250
    },
    "messages": DEFAULT_MESSAGES.copy(),
    "custom_notices": {},        # { notice_key: {"title": "...", "text": "..."} }
    "users": [],                 # Bot သုံးဖူးသော user_id များ
    "banned_users": [],
    "referrals": {},             # { invited_user_id_str: referrer_user_id_str }
    "redeemed_referrals": {}     # { referrer_user_id_str: redeemed_count }
}

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    return json.loads(json.dumps(DEFAULT_DATA))

                if "settings" not in data or not isinstance(data["settings"], dict):
                    data["settings"] = DEFAULT_DATA["settings"].copy()
                else:
                    for k, v in DEFAULT_DATA["settings"].items():
                        data["settings"].setdefault(k, v)

                if "messages" not in data or not isinstance(data["messages"], dict):
                    data["messages"] = DEFAULT_MESSAGES.copy()
                else:
                    for k, v in DEFAULT_MESSAGES.items():
                        data["messages"].setdefault(k, v)

                if "custom_notices" not in data or not isinstance(data["custom_notices"], dict):
                    data["custom_notices"] = {}
                if "users" not in data or not isinstance(data["users"], list):
                    data["users"] = []
                if "banned_users" not in data or not isinstance(data["banned_users"], list):
                    data["banned_users"] = []
                if "referrals" not in data or not isinstance(data["referrals"], dict):
                    data["referrals"] = {}
                if "redeemed_referrals" not in data or not isinstance(data["redeemed_referrals"], dict):
                    data["redeemed_referrals"] = {}
                return data
        except Exception as e:
            print(f"Error loading data: {e}")
            return json.loads(json.dumps(DEFAULT_DATA))
    return json.loads(json.dumps(DEFAULT_DATA))

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")

bot_data = load_data()
user_states = {}  # In-memory user state handling

def register_user(user_id: int):
    bot_data.setdefault("users", [])
    if user_id not in bot_data["users"]:
        bot_data["users"].append(user_id)
        save_data(bot_data)

def get_referral_count(user_id: int) -> int:
    uid_str = str(user_id)
    refs = bot_data.get("referrals", {})
    return sum(1 for _, inviter in refs.items() if str(inviter) == uid_str)

def get_available_referral_count(user_id: int) -> int:
    uid_str = str(user_id)
    total_refs = get_referral_count(user_id)
    redeemed = int(bot_data.get("redeemed_referrals", {}).get(uid_str, 0))
    return max(0, total_refs - redeemed)

def get_per_referral_discount() -> int:
    try:
        return int(bot_data.get("settings", {}).get("referral_discount_per_person", 250))
    except Exception:
        return 250

def get_referral_discount_amount(user_id: int, only_available: bool = True) -> int:
    per_ref = get_per_referral_discount()
    count = get_available_referral_count(user_id) if only_available else get_referral_count(user_id)
    return count * per_ref

def consume_referral_discounts(user_id: int):
    uid_str = str(user_id)
    total_refs = get_referral_count(user_id)
    bot_data.setdefault("redeemed_referrals", {})
    bot_data["redeemed_referrals"][uid_str] = total_refs
    save_data(bot_data)

def format_discounted_price(price_str: str, discount_amount: int) -> str:
    if discount_amount <= 0 or not price_str:
        return price_str
    match = re.search(r"(\d[\d,]*)", price_str)
    if not match:
        return f"{price_str} (-{discount_amount:,} လျှော့ဈေး)"
    raw_num_str = match.group(1).replace(",", "")
    try:
        base_price = int(raw_num_str)
        final_price = max(0, base_price - discount_amount)
        formatted_final = f"{final_price:,}"
        replaced = price_str[:match.start(1)] + formatted_final + price_str[match.end(1):]
        return f"<s>{price_str}</s> ➜ <b>{replaced}</b> (-{discount_amount:,})"
    except Exception:
        return f"{price_str} (-{discount_amount:,} လျှော့ဈေး)"

def format_msg(template_key: str, **kwargs):
    template = bot_data.get("messages", {}).get(template_key) or DEFAULT_MESSAGES.get(template_key, "")
    try:
        return template.format(**kwargs)
    except Exception:
        return template

# ==================== WEBHOOK INTEGRATION ====================
def call_subscription_webhook(email: str = None, telegram_id=None, plan: str = "PRO", duration_days: int = 30):
    """Lovable / App Backend သို့ Webhook ပို့၍ Plan ဖွင့်ပေးခြင်း"""
    if not WEBHOOK_URL:
        return {"success": False, "error": "WEBHOOK_URL is not configured"}
    if not WEBHOOK_SECRET:
        return {"success": False, "error": "WEBHOOK_SECRET is not configured"}

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Secret": WEBHOOK_SECRET,
    }
    approval_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {
        "plan": plan.upper(),
        "status": "ACTIVE",
        "startDate": approval_time,
        "durationDays": int(duration_days)
    }
    if email:
        payload["email"] = email.strip().lower()
    if telegram_id is not None:
        payload["telegramId"] = str(telegram_id)

    try:
        res = requests.post(WEBHOOK_URL, headers=headers, json=payload, timeout=20)
        try:
            data = res.json()
        except ValueError:
            data = {"raw": res.text}

        if res.status_code == 200 and (isinstance(data, dict) and data.get("ok", True)):
            return {"success": True, "data": data if isinstance(data, dict) else {}}

        err_msg = data.get("error") if isinstance(data, dict) else res.text
        return {"success": False, "error": err_msg or f"HTTP {res.status_code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ==================== KEYBOARDS ====================
def main_menu_keyboard(user_id: int):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2, is_persistent=True)
    markup.add(
        types.KeyboardButton("👤 Profile"),
        types.KeyboardButton("💎 Buy Plan"),
        types.KeyboardButton("👥 Referral"),
        types.KeyboardButton("💬 Support")
    )
    if user_id == OWNER_ID:
        markup.add(types.KeyboardButton("⚙️ Owner Menu"))
    return markup

def owner_inline_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💳 Edit KPay", callback_data="owner_set_kpay"),
        types.InlineKeyboardButton("🌊 Edit Wave", callback_data="owner_set_wave"),
        types.InlineKeyboardButton("💰 Edit Pro Price", callback_data="owner_set_pro_price"),
        types.InlineKeyboardButton("👑 Edit VIP Price", callback_data="owner_set_vip_price"),
        types.InlineKeyboardButton("💸 Edit Ref Discount", callback_data="owner_set_ref_discount"),
        types.InlineKeyboardButton("📞 Edit Support", callback_data="owner_set_support"),
        types.InlineKeyboardButton("👋 Edit Welcome", callback_data="owner_set_welcome"),
        types.InlineKeyboardButton("👥 Edit Ref Info Msg", callback_data="owner_set_referral_info"),
        types.InlineKeyboardButton("🔔 Edit Ref Notify", callback_data="owner_set_referral_notify"),
        types.InlineKeyboardButton("✅ Edit Approve Msg", callback_data="owner_set_approve_msg"),
        types.InlineKeyboardButton("❌ Edit Reject Msg", callback_data="owner_set_reject_msg"),
        types.InlineKeyboardButton("📩 Edit Slip Msg", callback_data="owner_set_slip_msg"),
        types.InlineKeyboardButton("📢 Custom Notices", callback_data="owner_notices_menu"),
        types.InlineKeyboardButton("📋 View Settings", callback_data="owner_view_settings")
    )
    return markup

def custom_notices_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Add New Notice", callback_data="notice_add"),
        types.InlineKeyboardButton("📋 List / Manage", callback_data="notice_list"),
        types.InlineKeyboardButton("⬅️ Back to Owner", callback_data="notice_back")
    )
    return markup

def notice_actions_keyboard(notice_id: str):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📤 Send All Users", callback_data=f"ntx|all|{notice_id}"),
        types.InlineKeyboardButton("📩 Send 1 User", callback_data=f"ntx|one|{notice_id}"),
        types.InlineKeyboardButton("👥 Send Admin Group", callback_data=f"ntx|grp|{notice_id}"),
        types.InlineKeyboardButton("✏️ Edit Text", callback_data=f"ntx|edt|{notice_id}"),
        types.InlineKeyboardButton("🗑 Delete", callback_data=f"ntx|del|{notice_id}"),
        types.InlineKeyboardButton("⬅️ Back", callback_data="notice_list")
    )
    return markup

# ==================== BOT HANDLERS ====================
@bot.message_handler(commands=['start', 'menu'])
def handle_start(message):
    user_id = message.from_user.id
    if user_id in bot_data.get("banned_users", []):
        bot.reply_to(message, "❌ You are banned from using this bot.")
        return

    user_states.pop(user_id, None)
    register_user(user_id)

    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        referrer = args[1].replace("ref_", "").strip()
        if referrer.isdigit() and str(user_id) not in bot_data["referrals"] and referrer != str(user_id):
            bot_data["referrals"][str(user_id)] = referrer
            save_data(bot_data)

            ref_id_int = int(referrer)
            ref_count = get_referral_count(ref_id_int)
            avail_discount = get_referral_discount_amount(ref_id_int, only_available=True)
            try:
                notify_txt = format_msg(
                    "referral_notify",
                    invited_name=message.from_user.full_name or message.from_user.first_name or "User",
                    invited_id=user_id,
                    ref_count=ref_count,
                    avail_ref_count=get_available_referral_count(ref_id_int),
                    discount_amount=avail_discount,
                    per_ref=get_per_referral_discount(),
                    referrer_id=referrer
                )
                bot.send_message(ref_id_int, notify_txt, reply_markup=main_menu_keyboard(ref_id_int))
            except Exception as e:
                print(f"Error sending referral notification to {referrer}: {e}")

    welcome_text = format_msg(
        "welcome",
        first_name=message.from_user.first_name or "",
        full_name=message.from_user.full_name or "",
        username=message.from_user.username or "",
        user_id=user_id,
        ref_count=get_referral_count(user_id),
        discount_amount=get_referral_discount_amount(user_id, only_available=True)
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=main_menu_keyboard(user_id))

@bot.message_handler(func=lambda msg: msg.text == "👤 Profile")
def handle_profile(message):
    uid = message.from_user.id
    if uid in bot_data.get("banned_users", []):
        return
    user_states.pop(uid, None)
    register_user(uid)
    ref_count = get_referral_count(uid)
    avail_discount = get_referral_discount_amount(uid, only_available=True)
    txt = (
        f"👤 <b>သင့် Profile အချက်အလက်</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"• Telegram ID: <code>{uid}</code>\n"
        f"• Name: {message.from_user.full_name}\n"
        f"• Username: @{message.from_user.username or 'မရှိပါ'}\n"
        f"• Referrals: <b>{ref_count}</b> ယောက်\n"
        f"• Available Discount: <b>{avail_discount:,}</b>\n\n"
        f"<i>မှတ်ချက် - Web App ပေါ်တွင် Plan အခြေအနေကို စစ်ဆေးနိုင်ပါသည်။</i>"
    )
    bot.send_message(message.chat.id, txt, reply_markup=main_menu_keyboard(uid))

@bot.message_handler(func=lambda msg: msg.text == "💬 Support")
def handle_support(message):
    uid = message.from_user.id
    if uid in bot_data.get("banned_users", []):
        return
    user_states.pop(uid, None)
    register_user(uid)
    support_user = bot_data["settings"].get("support_username", "mikef07")
    bot.send_message(
        message.chat.id,
        f"💬 အကူအညီလိုအပ်ပါက Owner/Support ဖြစ်သော @{support_user} သို့ တိုက်ရိုက် ဆက်သွယ်နိုင်ပါသည်။",
        reply_markup=main_menu_keyboard(uid)
    )

@bot.message_handler(func=lambda msg: msg.text == "👥 Referral")
def handle_referral(message):
    uid = message.from_user.id
    if uid in bot_data.get("banned_users", []):
        return
    user_states.pop(uid, None)
    register_user(uid)
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{uid}"
    ref_count = get_referral_count(uid)
    avail_refs = get_available_referral_count(uid)
    per_ref = get_per_referral_discount()
    discount_amount = avail_refs * per_ref

    ref_text = format_msg(
        "referral_info",
        ref_link=ref_link,
        ref_count=ref_count,
        avail_ref_count=avail_refs,
        discount_amount=discount_amount,
        per_ref=per_ref,
        user_id=uid,
        first_name=message.from_user.first_name or ""
    )
    bot.send_message(message.chat.id, ref_text, reply_markup=main_menu_keyboard(uid))

# ==================== PLAN PURCHASE FLOW ====================
@bot.message_handler(func=lambda msg: msg.text == "💎 Buy Plan")
def handle_buy_plan(message):
    uid = message.from_user.id
    if uid in bot_data.get("banned_users", []):
        return
    register_user(uid)
    st = bot_data["settings"]

    avail_refs = get_available_referral_count(uid)
    per_ref = get_per_referral_discount()
    discount_amount = avail_refs * per_ref

    pro_display = format_discounted_price(st.get("pro_price", ""), discount_amount)
    vip_display = format_discounted_price(st.get("vip_price", ""), discount_amount)

    discount_line = ""
    if discount_amount > 0:
        discount_line = f"🎁 <b>သင့် Referral လျှော့ဈေး:</b> <b>-{discount_amount:,}</b> ({avail_refs} ယောက် × {per_ref:,})\n\n"

    msg_text = (
        "💎 <b>Plan များ ဝယ်ယူရန် ငွေလွှဲအကောင့်များ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 <b>Pro Plan:</b> {pro_display}\n"
        f"⚡ <b>VIP Plan:</b> {vip_display}\n"
        f"{discount_line}"
        "💳 <b>KPay:</b>\n"
        f"• နံပါတ်: <code>{st.get('kpay_phone')}</code>\n"
        f"• အမည်: {st.get('kpay_name')}\n\n"
        "🌊 <b>WavePay:</b>\n"
        f"• နံပါတ်: <code>{st.get('wave_phone')}</code>\n"
        f"• အမည်: {st.get('wave_name')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "ငွေလွှဲပြီးပါက App ထဲတွင် ဖွင့်ထားသော <b>သင့်အကောင့် Email</b> ကို အောက်တွင် ရိုက်ထည့်ပေးပါ-"
    )
    user_states[uid] = {
        "step": "WAITING_EMAIL",
        "applied_discount": discount_amount,
        "applied_ref_count": avail_refs
    }
    bot.send_message(message.chat.id, msg_text, reply_markup=main_menu_keyboard(uid))

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id, {}).get("step") == "WAITING_EMAIL" and msg.content_type == "text")
def handle_user_email(message):
    uid = message.from_user.id
    email = message.text.strip()
    if "@" not in email or "." not in email:
        bot.reply_to(message, "❌ အီးမေးလ်ပုံစံ မှားယွင်းနေပါသည်။ သေချာစွာ ပြန်လည်ရိုက်ထည့်ပေးပါ:")
        return

    prev_state = user_states.get(uid, {})
    user_states[uid] = {
        "step": "WAITING_SLIP",
        "email": email,
        "applied_discount": prev_state.get("applied_discount", 0),
        "applied_ref_count": prev_state.get("applied_ref_count", 0)
    }
    bot.send_message(
        message.chat.id,
        f"✅ အီးမေးလ် <code>{email}</code> ကို မှတ်သားထားပါသည်။\n\nကျေးဇူးပြု၍ <b>ငွေလွှဲပြေစာ (Screenshot/Photo)</b> ကို ပို့ပေးပါ-",
        reply_markup=main_menu_keyboard(uid)
    )

@bot.message_handler(content_types=['photo'], func=lambda msg: user_states.get(msg.from_user.id, {}).get("step") == "WAITING_SLIP")
def handle_user_slip(message):
    user_id = message.from_user.id
    st_data = user_states.get(user_id, {})
    email = st_data.get("email", "")
    applied_discount = int(st_data.get("applied_discount", 0))
    applied_ref_count = int(st_data.get("applied_ref_count", 0))
    photo_id = message.photo[-1].file_id

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Approve PRO", callback_data=f"app|PRO|{user_id}|{email}"),
        types.InlineKeyboardButton("🌟 Approve VIP", callback_data=f"app|VIP|{user_id}|{email}"),
        types.InlineKeyboardButton("❌ ငွေမလုံလောက်", callback_data=f"rej|insuf|{user_id}"),
        types.InlineKeyboardButton("🚫 Spam/Fake", callback_data=f"rej|spam|{user_id}")
    )

    discount_info = ""
    if applied_discount > 0:
        discount_info = f"\n• Ref Discount: <b>-{applied_discount:,}</b> ({applied_ref_count} refs)"

    capt
