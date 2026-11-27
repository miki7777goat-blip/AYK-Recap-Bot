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

    caption = (
        f"📩 <b>ငွေလွှဲစလစ် အသစ်ရောက်ရှိပါသည်</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"• User: {message.from_user.full_name} (@{message.from_user.username or 'none'})\n"
        f"• Telegram ID: <code>{user_id}</code>\n"
        f"• App Email: <code>{email}</code>{discount_info}\n"
        f"• Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )

    if ADMIN_GROUP_ID != 0:
        bot.send_photo(ADMIN_GROUP_ID, photo_id, caption=caption, reply_markup=markup)
        slip_reply = format_msg("slip_submitted", email=email, user_id=user_id, discount_amount=applied_discount)
        bot.reply_to(message, slip_reply, reply_markup=main_menu_keyboard(user_id))
    else:
        bot.reply_to(message, "⚠️ Admin Group ID မသတ်မှတ်ရသေးပါ။ Owner ထံ ဆက်သွယ်ပါ။", reply_markup=main_menu_keyboard(user_id))

    user_states.pop(user_id, None)

# ==================== ADMIN ACTIONS CALLBACK ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith(("app|", "rej|")))
def handle_admin_callback(call):
    data = call.data.split("|", 3)
    action = data[0]

    if action == "app":
        plan = data[1]
        uid = int(data[2])
        email = data[3]

        bot.answer_callback_query(call.id, f"Updating {plan} in App...")

        res = call_subscription_webhook(email=email, telegram_id=uid, plan=plan, duration_days=30)

        if res["success"]:
            consume_referral_discounts(uid)
            resp_data = res.get("data", {})
            expiry = resp_data.get("expiryDate") or resp_data.get("expiry_date") or "30 Days"
            admin_name = call.from_user.username or call.from_user.first_name
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=f"{call.message.caption}\n\n✅ <b>APPROVED ({plan}) by @{admin_name}</b>\nExpiry: {expiry}",
                reply_markup=None
            )
            try:
                user_notify_text = format_msg(
                    "approve_user",
                    email=email,
                    plan=plan,
                    expiry=expiry,
                    user_id=uid
                )
                bot.send_message(uid, user_notify_text, reply_markup=main_menu_keyboard(uid))
            except Exception as e:
                print(f"Error notifying user {uid}: {e}")
        else:
            bot.send_message(call.message.chat.id, f"⚠️ Webhook Error: {res.get('error')}")

    elif action == "rej":
        reason = data[1]
        uid = int(data[2])
        admin_name = call.from_user.username or call.from_user.first_name

        if reason == "insuf":
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=f"{call.message.caption}\n\n❌ <b>REJECTED (ငွေမလုံလောက်) by @{admin_name}</b>",
                reply_markup=None
            )
            try:
                reject_text = format_msg("reject_insuf", user_id=uid)
                bot.send_message(uid, reject_text, reply_markup=main_menu_keyboard(uid))
            except Exception:
                pass
        elif reason == "spam":
            if uid not in bot_data["banned_users"]:
                bot_data["banned_users"].append(uid)
                save_data(bot_data)
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=f"{call.message.caption}\n\n🚫 <b>USER BANNED (Spam/Fake) by @{admin_name}</b>",
                reply_markup=None
            )

# ==================== CUSTOM NOTICES HANDLERS ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith(("notice_", "ntx|")))
def handle_notice_callbacks(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "Unauthorized", show_alert=True)
        return

    bot_data.setdefault("custom_notices", {})
    notices = bot_data["custom_notices"]

    if call.data == "notice_back":
        bot.edit_message_text(
            "⚙️ <b>Owner Control Panel</b>\nအောက်ပါ ဆက်တင်များ နဲ့ Message များကို ပြင်ဆင်နိုင်ပါသည်-",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=owner_inline_keyboard()
        )
        bot.answer_callback_query(call.id)
        return

    if call.data in ("notice_menu", "notice_list"):
        if not notices:
            bot.send_message(
                call.message.chat.id,
                "📢 <b>Custom Notices</b>\nသိမ်းထားသော အကြောင်းကြားချက်အသစ် မရှိသေးပါ။ <b>➕ Add New Notice</b> နှိပ်ပြီး ထည့်နိုင်ပါသည်။",
                reply_markup=custom_notices_keyboard()
            )
            bot.answer_callback_query(call.id)
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        for nid, item in notices.items():
            title = item.get("title", nid)
            markup.add(types.InlineKeyboardButton(f"📌 {title}", callback_data=f"notice_open_{nid}"))
        markup.add(
            types.InlineKeyboardButton("➕ Add New Notice", callback_data="notice_add"),
            types.InlineKeyboardButton("⬅️ Back to Owner", callback_data="notice_back")
        )
        bot.send_message(
            call.message.chat.id,
            f"📋 <b>သိမ်းထားသော Custom Notices ({len(notices)} ခု)</b>\nအသုံးပြုရန် သို့မဟုတ် ပြင်ဆင်ရန် တစ်ခုကို ရွေးပါ-",
            reply_markup=markup
        )
        bot.answer_callback_query(call.id)
        return

    if call.data == "notice_add":
        user_states[OWNER_ID] = {"step": "ADD_NOTICE_TITLE"}
        bot.send_message(
            call.message.chat.id,
            "📝 <b>အကြောင်းကြားချက်အသစ် ခေါင်းစဉ်/နာမည်</b> ကို ရိုက်ထည့်ပေးပါ\n(ဥပမာ: <code>Server Update</code> သို့မဟုတ် <code>Promo News</code>):"
        )
        bot.answer_callback_query(call.id)
        return

    if call.data.startswith("notice_open_"):
        nid = call.data.replace("notice_open_", "")
        item = notices.get(nid)
        if not item:
            bot.answer_callback_query(call.id, "Notice not found", show_alert=True)
            return
        txt = (
            f"📌 <b>Notice: {item.get('title')}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"{item.get('text')}"
        )
        bot.send_message(call.message.chat.id, txt, reply_markup=notice_actions_keyboard(nid))
        bot.answer_callback_query(call.id)
        return

    if call.data.startswith("ntx|"):
        parts = call.data.split("|", 2)
        sub_action = parts[1]
        nid = parts[2]
        item = notices.get(nid)
        if not item:
            bot.answer_callback_query(call.id, "Notice not found", show_alert=True)
            return

        if sub_action == "all":
            users = [u for u in bot_data.get("users", []) if u not in bot_data.get("banned_users", [])]
            sent_count = 0
            failed_count = 0
            for uid in users:
                try:
                    bot.send_message(uid, item.get("text", ""), reply_markup=main_menu_keyboard(uid))
                    sent_count += 1
                    time.sleep(0.05)
                except Exception:
                    failed_count += 1
            bot.send_message(
                call.message.chat.id,
                f"📤 <b>Broadcast ပြီးစီးပါပြီ</b>\n• ပို့ပြီး: <code>{sent_count}</code> ယောက်\n• မရောက်: <code>{failed_count}</code> ယောက်"
            )
            bot.answer_callback_query(call.id, "Broadcast sent!")

        elif sub_action == "one":
            user_states[OWNER_ID] = {"step": "SEND_NOTICE_ONE_USER", "notice_id": nid}
            bot.send_message(
                call.message.chat.id,
                f"📩 <b>{item.get('title')}</b> ကို ပို့လိုသော User ရဲ့ <b>Telegram ID</b> (ဂဏန်း) ကို ရိုက်ထည့်ပေးပါ:"
            )
            bot.answer_callback_query(call.id)

        elif sub_action == "grp":
            if ADMIN_GROUP_ID != 0:
                try:
                    bot.send_message(ADMIN_GROUP_ID, item.get("text", ""))
                    bot.send_message(call.message.chat.id, "✅ Admin Group ထဲသို့ အကြောင်းကြားချက် ပို့ပြီးပါပြီ။")
                except Exception as e:
                    bot.send_message(call.message.chat.id, f"⚠️ Admin Group သို့ ပို့ရာတွင် Error ဖြစ်ပါသည်: {e}")
            else:
                bot.send_message(call.message.chat.id, "⚠️ ADMIN_GROUP_ID မသတ်မှတ်ရသေးပါ။")
            bot.answer_callback_query(call.id)

        elif sub_action == "edt":
            user_states[OWNER_ID] = {"step": "EDIT_NOTICE_TEXT", "notice_id": nid}
            bot.send_message(
                call.message.chat.id,
                f"✏️ <b>{item.get('title')}</b> အတွက် အကြောင်းကြားချက် စာသားအသစ်ကို ရိုက်ထည့်ပေးပါ:"
            )
            bot.answer_callback_query(call.id)

        elif sub_action == "del":
            notices.pop(nid, None)
            save_data(bot_data)
            bot.send_message(call.message.chat.id, "🗑 အကြောင်းကြားချက်ကို ဖျက်ပြီးပါပြီ။", reply_markup=custom_notices_keyboard())
            bot.answer_callback_query(call.id, "Deleted")

# ==================== OWNER PANEL ====================
@bot.message_handler(func=lambda msg: msg.text == "⚙️ Owner Menu")
def handle_owner_menu(message):
    if message.from_user.id != OWNER_ID:
        return
    user_states.pop(OWNER_ID, None)
    register_user(message.from_user.id)
    bot.send_message(
        message.chat.id,
        "⚙️ <b>Owner Control Panel</b>\nအောက်ပါ ဆက်တင်များ နဲ့ Message များကို ပြင်ဆင်နိုင်ပါသည်-",
        reply_markup=owner_inline_keyboard()
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("owner_"))
def handle_owner_actions(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "Unauthorized", show_alert=True)
        return

    action = call.data.replace("owner_", "")
    st = bot_data["settings"]
    msgs = bot_data.get("messages", DEFAULT_MESSAGES)
    notices = bot_data.get("custom_notices", {})

    if action == "notices_menu":
        bot.send_message(
            call.message.chat.id,
            f"📢 <b>Custom Notices Manager</b>\nလက်ရှိ သိမ်းထားသော Notice အရေအတွက်: <b>{len(notices)}</b> ခု\n\nအကြောင်းကြားချက်အသစ် ထပ်ထည့်ခြင်း၊ ပြင်ခြင်း သို့မဟုတ် User များထံ ပို့ခြင်း ပြုလုပ်နိုင်ပါသည်။",
            reply_markup=custom_notices_keyboard()
        )
        bot.answer_callback_query(call.id)
        return

    if action == "view_settings":
        txt = (
            "⚙️ <b>လက်ရှိ ဆက်တင်များ</b>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"• KPay: {st.get('kpay_phone')} ({st.get('kpay_name')})\n"
            f"• Wave: {st.get('wave_phone')} ({st.get('wave_name')})\n"
            f"• Pro Price: {st.get('pro_price')}\n"
            f"• VIP Price: {st.get('vip_price')}\n"
            f"• Ref Discount / Person: <b>{get_per_referral_discount():,}</b>\n"
            f"• Support: @{st.get('support_username')}\n"
            f"• Total Users: {len(bot_data.get('users', []))} ယောက်\n"
            f"• Total Referrals: {len(bot_data.get('referrals', {}))} ခု\n"
            f"• Banned Users: {len(bot_data.get('banned_users', []))} ယောက်\n"
            f"• Custom Notices: {len(notices)} ခု\n\n"
            "📝 <b>လက်ရှိ Notification / Welcome / Referral စာသားများ</b>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>Welcome:</b>\n{msgs.get('welcome')}\n\n"
            f"• <b>Referral Info:</b>\n{msgs.get('referral_info')}\n\n"
            f"• <b>Referral Notify:</b>\n{msgs.get('referral_notify')}\n\n"
            f"• <b>Approve User:</b>\n{msgs.get('approve_user')}\n\n"
            f"• <b>Reject (Insufficient):</b>\n{msgs.get('reject_insuf')}\n\n"
            f"• <b>Slip Submitted:</b>\n{msgs.get('slip_submitted')}"
        )
        bot.send_message(call.message.chat.id, txt)
        bot.answer_callback_query(call.id)
    else:
        field_map = {
            "set_kpay": ("KPay (ဖုန်းနံပါတ် နှင့် အမည်)", "kpay", "ဥပမာ: 09123456789 U Aye"),
            "set_wave": ("Wave (ဖုန်းနံပါတ် နှင့် အမည်)", "wave", "ဥပမာ: 09123456789 U Aye"),
            "set_pro_price": ("Pro Plan စျေးနှုန်း", "pro_price", "ဥပမာ: 15,000 MMK"),
            "set_vip_price": ("VIP Plan စျေးနှုန်း", "vip_price", "ဥပမာ: 30,000 MMK"),
            "set_ref_discount": ("တစ်ယောက်ဖိတ်ခေါ်ရင် လျှော့ဈေးပမာဏ (ဂဏန်းသီးသန့်)", "ref_discount", "ဥပမာ: 250"),
            "set_support": ("Support Telegram Username (without @)", "support_username", None),
            "set_welcome": ("Welcome Message (သုံးနိုင်သော tag များ: {first_name}, {full_name}, {username}, {user_id}, {ref_count}, {discount_amount})", "welcome", "Variables သုံးလို့ရပါသည်။"),
            "set_referral_info": ("Referral Info Message (သုံးနိုင်သော tag များ: {ref_link}, {ref_count}, {avail_ref_count}, {discount_amount}, {per_ref}, {user_id}, {first_name})", "referral_info", "User က Referral နှိပ်ချိန် ပြမည့်စာ ဖြစ်ပါသည်။"),
            "set_referral_notify": ("Referral Notify Message (သုံးနိုင်သော tag များ: {invited_name}, {invited_id}, {ref_count}, {avail_ref_count}, {discount_amount}, {per_ref}, {referrer_id})", "referral_notify", "ဖိတ်ခေါ်လင့်နဲ့ User အသစ်ဝင်လာချိန် ဖိတ်ခေါ်သူဆီ ပို့မည့်စာ ဖြစ်ပါသည်။"),
            "set_approve_msg": ("Approve Notification Message (သုံးနိုင်သော tag များ: {email}, {plan}, {expiry}, {user_id})", "approve_user", "Plan ဖွင့်ပြီးချိန် User ဆီ ပို့မည့်စာ ဖြစ်ပါသည်။"),
            "set_reject_msg": ("Reject Notification Message (သုံးနိုင်သော tag: {user_id})", "reject_insuf", "ငွေမလုံလောက်ဟု Reject လုပ်ချိန် User ဆီ ပို့မည့်စာ ဖြစ်ပါသည်။"),
            "set_slip_msg": ("Slip Submitted Notification Message (သုံးနိုင်သော tag များ: {email}, {user_id}, {discount_amount})", "slip_submitted", "User က စလစ်ပို့ပြီးချိန် ပြန်ပြမည့်စာ ဖြစ်ပါသည်။")
        }
        if action in field_map:
            label, key, hint = field_map[action]
            user_states[OWNER_ID] = {"step": f"EDIT_{key}"}
            extra = f"\n<i>{hint}</i>" if hint else ""
            bot.send_message(call.message.chat.id, f"📝 <b>{label}</b> အသစ်ကို ရိုက်ထည့်ပေးပါ:{extra}")
            bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda msg: msg.from_user.id == OWNER_ID and OWNER_ID in user_states and msg.content_type == "text")
def handle_owner_input(message):
    state = user_states.get(OWNER_ID, {})
    step = state.get("step", "")
    text = message.text.strip()
    st = bot_data["settings"]
    bot_data.setdefault("messages", DEFAULT_MESSAGES.copy())
    bot_data.setdefault("custom_notices", {})

    if step == "ADD_NOTICE_TITLE":
        user_states[OWNER_ID] = {"step": "ADD_NOTICE_TEXT", "title": text}
        bot.reply_to(message, f"✅ ခေါင်းစဉ် <b>{text}</b> ကို မှတ်သားထားပါပြီ။\nအခု <b>အကြောင်းကြားချက် စာသား</b> ကို ရိုက်ထည့်ပေးပါ:")
        return

    if step == "ADD_NOTICE_TEXT":
        title = state.get("title", "Notice")
        nid = f"n_{int(time.time())}"
        bot_data["custom_notices"][nid] = {"title": title, "text": text}
        save_data(bot_data)
        user_states.pop(OWNER_ID, None)
        bot.reply_to(message, f"✅ အကြောင်းကြားချက်အသစ် <b>{title}</b> ကို သိမ်းဆည်းပြီးပါပြီ။", reply_markup=notice_actions_keyboard(nid))
        return

    if step == "EDIT_NOTICE_TEXT":
        nid = state.get("notice_id")
        if nid in bot_data["custom_notices"]:
            bot_data["custom_notices"][nid]["text"] = text
            save_data(bot_data)
            bot.reply_to(message, "✅ အကြောင်းကြားချက် စာသားကို ပြင်ဆင်သိမ်းဆည်းပြီးပါပြီ။", reply_markup=notice_actions_keyboard(nid))
        user_states.pop(OWNER_ID, None)
        return

    if step == "SEND_NOTICE_ONE_USER":
        nid = state.get("notice_id")
        item = bot_data["custom_notices"].get(nid)
        try:
            target_uid = int(text)
            if item:
                bot.send_message(target_uid, item.get("text", ""), reply_markup=main_menu_keyboard(target_uid))
                bot.reply_to(message, f"✅ User ID <code>{target_uid}</code> ဆီသို့ အကြောင်းကြားချက် ပို့ပြီးပါပြီ။")
        except ValueError:
            bot.reply_to(message, "❌ Telegram ID သည် ဂဏန်းဖြစ်ရပါမည်။ ပြန်ရိုက်ထည့်ပေးပါ:")
            return
        except Exception as e:
            bot.reply_to(message, f"⚠️ ပို့ရာတွင် Error ဖြစ်ပါသည်: {e}")
        user_states.pop(OWNER_ID, None)
        return

    if step.startswith("EDIT_"):
        field = step.replace("EDIT_", "")
        if field == "kpay":
            parts = text.split()
            st["kpay_phone"] = parts[0]
            st["kpay_name"] = " ".join(parts[1:]) if len(parts) > 1 else ""
        elif field == "wave":
            parts = text.split()
            st["wave_phone"] = parts[0]
            st["wave_name"] = " ".join(parts[1:]) if len(parts) > 1 else ""
        elif field == "pro_price":
            st["pro_price"] = text
        elif field == "vip_price":
            st["vip_price"] = text
        elif field == "ref_discount":
            clean_num = text.replace(",", "").strip()
            if not clean_num.isdigit():
                bot.reply_to(message, "❌ လျှော့ဈေးပမာဏကို ဂဏန်းသက်သက် ရိုက်ထည့်ပေးပါ (ဥပမာ: 250):")
                return
            st["referral_discount_per_person"] = int(clean_num)
        elif field == "support_username":
            st["support_username"] = text.replace("@", "")
        elif field in ("welcome", "referral_info", "referral_notify", "approve_user", "reject_insuf", "slip_submitted"):
            bot_data["messages"][field] = text

        save_data(bot_data)
        user_states.pop(OWNER_ID, None)
        bot.reply_to(message, f"✅ <b>{field}</b> ဆက်တင်ကို အောင်မြင်စွာ ပြောင်းလဲသိမ်းဆည်းပြီးပါပြီ။", reply_markup=main_menu_keyboard(OWNER_ID))

# ==================== FALLBACK TEXT HANDLER ====================
@bot.message_handler(func=lambda msg: True, content_types=['text'])
def handle_unknown_text(message):
    uid = message.from_user.id
    if uid in bot_data.get("banned_users", []):
        return
    register_user(uid)
    bot.send_message(
        message.chat.id,
        "အောက်ပါ Menu ခလုတ်များကို နှိပ်၍ အသုံးပြုနိုင်ပါသည်-",
        reply_markup=main_menu_keyboard(uid)
    )

# ==================== RENDER HEALTH CHECK SERVER ====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"AYK Bot is alive!")

    def log_message(self, format, *args):
        return

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
    print(f"Health server started on port {PORT}")
    server.serve_forever()

# ==================== MAIN EXECUTION ====================
if __name__ == "__main__":
    print("Starting Render Health Server...")
    threading.Thread(target=run_health_server, daemon=True).start()

    try:
        bot.remove_webhook()
    except Exception as e:
        print(f"Warning removing webhook: {e}")

    try:
        bot.set_my_commands([
            types.BotCommand("start", "Bot ကို စတင်ရန် / Menu ဖွင့်ရန်"),
            types.BotCommand("menu", "Menu ခလုတ်များ ပြန်ဖော်ရန်")
        ])
    except Exception as e:
        print(f"Warning setting bot commands: {e}")

    print("Starting Telegram Bot Polling...")
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)
        except Exception as e:
            print(f"Polling error: {e} — retrying in 5 seconds...")
            time.sleep(5)
