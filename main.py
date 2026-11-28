import os
import re
import json
import uuid
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta
import requests
import telebot
from telebot import types

# ==================== ENVIRONMENT VARIABLES ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8909534863:AAG9F4ZwZRaT0RYovkaEKauvEtzM91-j2qk")
OWNER_ID = int(os.getenv("OWNER_ID", "8415289516"))
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "-1004448651266"))
SUPPORT_TOPIC_ID = int(os.getenv("SUPPORT_TOPIC_ID", "99"))  # User တွေရဲ့စာကိုဖြေကြားရန် topic ID

WEBHOOK_URL = os.getenv(
    "WEBHOOK_URL",
    "https://aykrecaptool.lovable.app/api/public/subscription/update"
)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "OSv2efvHvWGB6b4l6jGsr87IZvyYLhMcH5V2YHuHgvSWKpJt")
PORT = int(os.getenv("PORT", "10000"))

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ==================== DATA PERSISTENCE ====================
DATA_FILE = "bot_data.json"

DEFAULT_DATA = {
    "settings": {
        "kpay_phone": "09965376292",
        "kpay_name": "Ko Myo Min Naing",
        "wave_phone": "09780695452",
        "wave_name": "Khin Myo Nwe",
        "pro_price": "3,000 Ks / 1 Month",
        "vip_price": "5,000 Ks / 1 Month",
        "ref_rate": "250 Ks / ယောက်",
        "pro_ref_target": "12 ယောက်",
        "vip_ref_target": "20 ယောက်",
        "support_username": "boostmmowner"
    },
    "notifications": {
        "welcome_msg": "👋 မင်္ဂလာပါ <b>{first_name}</b>!\n\nAYK Recap Bot မှ ကြိုဆိုပါသည်။ အောက်ပါ Menu မှတစ်ဆင့် အသုံးပြုနိုင်ပါပြီ။",
        "support_prompt": "💬 Admin ထံ ဆက်သွယ်လိုသော မက်ဆေ့ခ်ျကို ရိုက်ပို့ပေးပါ။",
        "plan_update_msg": "✨ Plan Update: သင့် Plan အခြေအနေ ပြောင်းလဲသွားပါပြီ။"
    },
    "known_users": {},   # { str(user_id): {"name": ..., "username": ..., "last_seen": ...} }
    "banned_users": [],  # [ int(user_id), ... ]
    "referrals": {}      # { str(user_id): str(referrer_id) }
}

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "settings": {**DEFAULT_DATA["settings"], **data.get("settings", {})},
                    "notifications": {**DEFAULT_DATA["notifications"], **data.get("notifications", {})},
                    "known_users": data.get("known_users", {}),
                    "banned_users": [int(x) for x in data.get("banned_users", [])],
                    "referrals": data.get("referrals", {})
                }
        except Exception:
            return json.loads(json.dumps(DEFAULT_DATA))
    return json.loads(json.dumps(DEFAULT_DATA))

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")

bot_data = load_data()
user_states = {}      # { user_id: {"step": ..., ...} }
pending_requests = {} # { req_id: {"user_id": ..., "email": ..., "name": ..., "username": ...} }
support_threads = {}  # { group_msg_id: user_id }

def track_user(user):
    if not user:
        return
    uid_str = str(user.id)
    bot_data["known_users"][uid_str] = {
        "name": user.full_name or user.first_name or "Unknown",
        "username": user.username or "",
        "last_seen": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    }
    save_data(bot_data)

def is_banned(user_id: int) -> bool:
    return int(user_id) in bot_data.get("banned_users", [])

# ==================== WEBHOOK INTEGRATION ====================
def call_subscription_webhook(email: str, plan: str, duration_days: int = 30):
    """App Backend သို့ Webhook ပို့၍ Plan ဖွင့်ပေးခြင်း"""
    if not WEBHOOK_SECRET:
        return {"success": False, "error": "WEBHOOK_SECRET is not configured"}

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Secret": WEBHOOK_SECRET,
    }
    now_utc = datetime.now(timezone.utc)
    approval_time = now_utc.isoformat()
    calculated_expiry = (now_utc + timedelta(days=duration_days)).isoformat()

    payload = {
        "email": email.strip().lower(),
        "plan": plan.upper(),
        "status": "ACTIVE",
        "startDate": approval_time,
        "durationDays": duration_days
    }

    try:
        res = requests.post(WEBHOOK_URL, headers=headers, json=payload, timeout=20)
        data = res.json() if res.content else {}
        if res.status_code == 200 and data.get("ok", True):
            expiry = data.get("expiryDate") or data.get("expiresAt") or calculated_expiry
            return {"success": True, "data": data, "expiry": expiry}
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
        types.KeyboardButton("💬 Chat with Admin")
    )
    if user_id == OWNER_ID:
        markup.add(types.KeyboardButton("⚙️ Owner Menu"))
    return markup

def owner_inline_keyboard():
    st = bot_data["settings"]
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💳 Edit KPay", callback_data="owner_set_kpay"),
        types.InlineKeyboardButton("🌊 Edit Wave", callback_data="owner_set_wave"),
        types.InlineKeyboardButton("💰 Edit Pro Price", callback_data="owner_set_pro_price"),
        types.InlineKeyboardButton("👑 Edit VIP Price", callback_data="owner_set_vip_price"),
        types.InlineKeyboardButton(f"🎯 Ref Rate ({st.get('ref_rate')})", callback_data="owner_set_ref_rate"),
        types.InlineKeyboardButton(f"🏆 Pro/VIP Ref ({st.get('pro_ref_target')}/{st.get('vip_ref_target')})", callback_data="owner_set_ref_targets"),
        types.InlineKeyboardButton("👥 User Control", callback_data="uc_menu"),
        types.InlineKeyboardButton("🔔 Notification Mgmt", callback_data="notif_menu"),
        types.InlineKeyboardButton("📢 Send Broadcast", callback_data="owner_broadcast"),
        types.InlineKeyboardButton("📞 Edit Support", callback_data="owner_set_support"),
        types.InlineKeyboardButton("📋 View Settings", callback_data="owner_view_settings"),
        types.InlineKeyboardButton("🏠 Main Menu", callback_data="owner_main_menu")
    )
    return markup

def notification_mgmt_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("👋 Edit Welcome Msg", callback_data="notif_edit_welcome_msg"),
        types.InlineKeyboardButton("💬 Edit Support Prompt", callback_data="notif_edit_support_prompt"),
        types.InlineKeyboardButton("✨ Edit Plan Update Msg", callback_data="notif_edit_plan_update_msg"),
        types.InlineKeyboardButton("⬅️ Back to Owner Panel", callback_data="owner_back_main")
    )
    return markup

def user_control_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🔍 Lookup User ID", callback_data="uc_lookup"),
        types.InlineKeyboardButton("🚫 Ban User ID", callback_data="uc_ban"),
        types.InlineKeyboardButton("✅ Unban User ID", callback_data="uc_unban"),
        types.InlineKeyboardButton("📋 Banned List", callback_data="uc_banned_list"),
        types.InlineKeyboardButton("⬅️ Back to Owner Panel", callback_data="owner_back_main")
    )
    return markup

def build_owner_panel_text():
    st = bot_data["settings"]
    known_count = len(bot_data.get("known_users", {}))
    banned_count = len(bot_data.get("banned_users", []))
    return (
        "⚙️ <b>Owner Control Panel</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"• KPay: <code>{st.get('kpay_phone')}</code> ({st.get('kpay_name')})\n"
        f"• Wave: <code>{st.get('wave_phone')}</code> ({st.get('wave_name')})\n"
        f"• Pro Price: {st.get('pro_price')}\n"
        f"• VIP Price: {st.get('vip_price')}\n"
        f"• Ref Rate: {st.get('ref_rate')}\n"
        f"• Pro Ref Target: {st.get('pro_ref_target')} | VIP Ref Target: {st.get('vip_ref_target')}\n"
        f"• Support: @{st.get('support_username')}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"👥 Known Users: <b>{known_count}</b> ယောက် | 🚫 Banned: <b>{banned_count}</b> ယောက်"
    )

def build_notification_summary():
    nf = bot_data["notifications"]
    return (
        "🔔 <b>Notification Management</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"<b>1. Welcome Msg:</b>\n{nf.get('welcome_msg')}\n\n"
        f"<b>2. Support Prompt:</b>\n{nf.get('support_prompt')}\n\n"
        f"<b>3. Plan Update Msg:</b>\n{nf.get('plan_update_msg')}\n\n"
        "ပြင်ဆင်လိုသော မက်ဆေ့ခ်ျကို ရွေးချယ်ပါ-"
    )

# ==================== BOT HANDLERS ====================
@bot.message_handler(commands=['cancel'])
def handle_cancel(message):
    user_states.pop(message.from_user.id, None)
    bot.reply_to(
        message,
        "✅ လက်ရှိလုပ်ဆောင်ချက်ကို ပယ်ဖျက်လိုက်ပါပြီ။",
        reply_markup=main_menu_keyboard(message.from_user.id)
    )

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    if is_banned(user_id):
        bot.reply_to(message, "❌ You are banned from using this bot.")
        return

    track_user(message.from_user)

    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        referrer = args[1].replace("ref_", "")
        if str(user_id) not in bot_data["referrals"] and referrer != str(user_id):
            bot_data["referrals"][str(user_id)] = referrer
            save_data(bot_data)

    template = bot_data["notifications"].get("welcome_msg", DEFAULT_DATA["notifications"]["welcome_msg"])
    try:
        welcome_text = template.format(
            first_name=message.from_user.first_name or "",
            full_name=message.from_user.full_name or "",
            username=message.from_user.username or "none",
            user_id=user_id
        )
    except Exception:
        welcome_text = template

    bot.send_message(message.chat.id, welcome_text, reply_markup=main_menu_keyboard(user_id))

@bot.message_handler(func=lambda msg: msg.chat.type == "private" and msg.text == "👤 Profile")
def handle_profile(message):
    if is_banned(message.from_user.id):
        bot.reply_to(message, "❌ You are banned from using this bot.")
        return
    track_user(message.from_user)
    uid = message.from_user.id
    ref_count = sum(1 for r in bot_data.get("referrals", {}).values() if str(r) == str(uid))
    txt = (
        f"👤 <b>သင့် Profile အချက်အလက်</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"• Telegram ID: <code>{uid}</code>\n"
        f"• Name: {message.from_user.full_name}\n"
        f"• Username: @{message.from_user.username or 'မရှိပါ'}\n"
        f"• Referrals: <b>{ref_count}</b> ယောက်\n\n"
        f"<i>မှတ်ချက် - Web App ပေါ်တွင် Plan အခြေအနေကို စစ်ဆေးနိုင်ပါသည်။</i>"
    )
    bot.send_message(message.chat.id, txt)

@bot.message_handler(func=lambda msg: msg.chat.type == "private" and msg.text in ("💬 Chat with Admin", "💬 Support"))
def handle_chat_with_admin(message):
    user_id = message.from_user.id
    if is_banned(user_id):
        bot.reply_to(message, "❌ You are banned from using this bot.")
        return
    track_user(message.from_user)
    support_user = bot_data["settings"].get("support_username", "boostmmowner")
    prompt = bot_data["notifications"].get("support_prompt", DEFAULT_DATA["notifications"]["support_prompt"])
    user_states[user_id] = {"step": "WAITING_SUPPORT_MSG"}
    bot.send_message(
        message.chat.id,
        f"💬 <b>Support & Admin Contact</b>\n\n{prompt}\n✉️ Contact: @{support_user}\n<i>(ပယ်ဖျက်ရန် /cancel)</i>"
    )

@bot.message_handler(func=lambda msg: msg.chat.type == "private" and msg.text == "👥 Referral")
def handle_referral(message):
    if is_banned(message.from_user.id):
        bot.reply_to(message, "❌ You are banned from using this bot.")
        return
    track_user(message.from_user)
    st = bot_data["settings"]
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"
    ref_count = sum(1 for r in bot_data.get("referrals", {}).values() if str(r) == str(message.from_user.id))
    txt = (
        f"👥 <b>သင့် Referral အချက်အလက်</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"• ဖိတ်ခေါ်ပြီးသူ: <b>{ref_count}</b> ယောက်\n"
        f"• Ref Rate: {st.get('ref_rate')}\n"
        f"• Pro Target: {st.get('pro_ref_target')} | VIP Target: {st.get('vip_ref_target')}\n\n"
        f"<b>Referral Link:</b>\n<code>{ref_link}</code>"
    )
    bot.send_message(message.chat.id, txt)

# ==================== SUPPORT CHAT FORWARD & ADMIN REPLY ====================
@bot.message_handler(
    func=lambda msg: msg.chat.type == "private"
    and user_states.get(msg.from_user.id, {}).get("step") == "WAITING_SUPPORT_MSG"
)
def handle_user_support_message(message):
    user_id = message.from_user.id
    if is_banned(user_id):
        user_states.pop(user_id, None)
        return

    user_states.pop(user_id, None)
    text_body = (message.text or "").strip()
    uname = f"@{message.from_user.username}" if message.from_user.username else "none"
    admin_msg_txt = (
        "❓ <b>User မေးခွန်း / စကားပြောမှု</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"• Name: {message.from_user.full_name} ({uname})\n"
        f"• UserID: <code>{user_id}</code>\n"
        f"• Message: {text_body}"
    )

    if ADMIN_GROUP_ID != 0:
        sent = bot.send_message(
            ADMIN_GROUP_ID,
            admin_msg_txt,
            message_thread_id=SUPPORT_TOPIC_ID if SUPPORT_TOPIC_ID else None
        )
        support_threads[sent.message_id] = user_id
        bot.reply_to(message, "✅ သင့်မက်ဆေ့ခ်ျကို Admin ထံ ပို့ပြီးပါပြီ။ ပြန်ကြားစာကို ဤနေရာမှ တစ်ဆင့် ရရှိပါမည်။")
    else:
        bot.reply_to(message, "⚠️ Admin Group ID မသတ်မှတ်ရသေးပါ။")

@bot.message_handler(
    func=lambda msg: msg.chat.id == ADMIN_GROUP_ID
    and msg.reply_to_message is not None
    and not (msg.text or "").startswith("/")
)
def handle_admin_group_reply(message):
    replied_id = message.reply_to_message.message_id
    target_uid = support_threads.get(replied_id)

    # Fallback: extract UserID from replied message text if bot restarted
    if not target_uid and message.reply_to_message.text:
        m = re.search(r"UserID:\s*(\d+)", message.reply_to_message.text)
        if m:
            target_uid = int(m.group(1))

    if not target_uid:
        return

    reply_text = (message.text or "").strip()
    if not reply_text:
        return

    try:
        bot.send_message(
            target_uid,
            f"💬 <b>Admin ပြန်ကြားစာ</b>\n━━━━━━━━━━━━━━━━━━━\n{reply_text}"
        )
        bot.reply_to(message, "✅ User ထံ ပြန်ပို့ ပြီးပါပြီ။")
    except Exception as e:
        bot.reply_to(message, f"⚠️ User ထံ ပို့၍မရပါ: <code>{e}</code>")

# ==================== PLAN PURCHASE FLOW ====================
@bot.message_handler(func=lambda msg: msg.chat.type == "private" and msg.text == "💎 Buy Plan")
def handle_buy_plan(message):
    user_id = message.from_user.id
    if is_banned(user_id):
        bot.reply_to(message, "❌ You are banned from using this bot.")
        return

    track_user(message.from_user)
    st = bot_data["settings"]
    msg_text = (
        "💎 <b>Plan များ ဝယ်ယူရန် ငွေလွှဲအကောင့်များ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 <b>Pro Plan:</b> {st.get('pro_price')}\n"
        f"⚡ <b>VIP Plan:</b> {st.get('vip_price')}\n\n"
        "💳 <b>KPay:</b>\n"
        f"• နံပါတ်: <code>{st.get('kpay_phone')}</code>\n"
        f"• အမည်: {st.get('kpay_name')}\n\n"
        "🌊 <b>WavePay:</b>\n"
        f"• နံပါတ်: <code>{st.get('wave_phone')}</code>\n"
        f"• အမည်: {st.get('wave_name')}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "ငွေလွှဲပြီးပါက App ထဲတွင် ဖွင့်ထားသော <b>သင့်အကောင့် Email</b> ကို အောက်တွင် ရိုက်ထည့်ပေးပါ-\n"
        "<i>(ပယ်ဖျက်လိုပါက /cancel ဟု ရိုက်ပါ။)</i>"
    )
    user_states[user_id] = {"step": "WAITING_EMAIL"}
    bot.send_message(message.chat.id, msg_text)

@bot.message_handler(
    func=lambda msg: msg.chat.type == "private"
    and user_states.get(msg.from_user.id, {}).get("step") == "WAITING_EMAIL"
)
def handle_user_email(message):
    if is_banned(message.from_user.id):
        user_states.pop(message.from_user.id, None)
        return
    email = (message.text or "").strip()
    if "@" not in email or "." not in email:
        bot.reply_to(message, "❌ အီးမေးလ်ပုံစံ မှားယွင်းနေပါသည်။ သေချာစွာ ပြန်လည်ရိုက်ထည့်ပေးပါ:")
        return

    user_states[message.from_user.id] = {
        "step": "WAITING_SLIP",
        "email": email
    }
    bot.send_message(
        message.chat.id,
        f"✅ အီးမေးလ် <code>{email}</code> ကို မှတ်သားထားပါသည်။\n\nကျေးဇူးပြု၍ <b>ငွေလွှဲပြေစာ (Screenshot/Photo)</b> ကို ပို့ပေးပါ-"
    )

@bot.message_handler(
    content_types=['photo'],
    func=lambda msg: msg.chat.type == "private"
    and user_states.get(msg.from_user.id, {}).get("step") == "WAITING_SLIP"
)
def handle_user_slip(message):
    user_id = message.from_user.id
    if is_banned(user_id):
        user_states.pop(user_id, None)
        return

    email = user_states[user_id]["email"]
    photo_id = message.photo[-1].file_id

    req_id = uuid.uuid4().hex[:10]
    pending_requests[req_id] = {
        "user_id": user_id,
        "email": email,
        "name": message.from_user.full_name,
        "username": message.from_user.username or "none"
    }

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Approve PRO", callback_data=f"app_PRO_{req_id}"),
        types.InlineKeyboardButton("🌟 Approve VIP", callback_data=f"app_VIP_{req_id}"),
        types.InlineKeyboardButton("❌ ငွေမလုံလောက်", callback_data=f"rej_insuf_{req_id}"),
        types.InlineKeyboardButton("🚫 Spam/Fake", callback_data=f"rej_spam_{req_id}")
    )

    now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    caption = (
        f"📩 <b>ငွေလွှဲစလစ် အသစ်ရောက်ရှိပါသည်</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"• User: {message.from_user.full_name} (@{message.from_user.username or 'none'})\n"
        f"• Telegram ID: <code>{user_id}</code>\n"
        f"• App Email: <code>{email}</code>\n"
        f"• Time: <code>{now_str}</code>"
    )

    if ADMIN_GROUP_ID != 0:
        bot.send_photo(ADMIN_GROUP_ID, photo_id, caption=caption, reply_markup=markup)
        bot.reply_to(message, "✅ သင့်ငွေလွှဲစလစ်ကို Admin ထံ တင်ပြထားပါပြီ။ စစ်ဆေးပြီးပါက Bot မှတစ်ဆင့် အကြောင်းကြားပေးပါမည်။")
    else:
        bot.reply_to(message, "⚠️ Admin Group ID မသတ်မှတ်ရသေးပါ။ Owner ထံ ဆက်သွယ်ပါ။")

    user_states.pop(user_id, None)

# ==================== ADMIN ACTIONS CALLBACK ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith(("app_", "rej_")))
def handle_admin_callback(call):
    parts = call.data.split("_")
    if len(parts) < 3:
        bot.answer_callback_query(call.id, "Invalid action", show_alert=True)
        return

    action = parts[0]
    sub_type = parts[1]
    req_id = "_".join(parts[2:])

    req_data = pending_requests.get(req_id)
    if not req_data:
        bot.answer_callback_query(call.id, "Request expired or already processed.", show_alert=True)
        return

    uid = req_data["user_id"]
    email = req_data["email"]
    admin_tag = f"@{call.from_user.username}" if call.from_user.username else call.from_user.full_name
    plan_notice = bot_data["notifications"].get("plan_update_msg", DEFAULT_DATA["notifications"]["plan_update_msg"])

    if action == "app":
        plan = sub_type
        bot.answer_callback_query(call.id, f"Updating {plan} in App...")

        res = call_subscription_webhook(email=email, plan=plan, duration_days=30)
        if res["success"]:
            expiry = res["expiry"]
            pending_requests.pop(req_id, None)
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=f"{call.message.caption}\n\n✅ <b>APPROVED ({plan}) by {admin_tag}</b>\nExpiry: <code>{expiry}</code>",
                reply_markup=None
            )
            try:
                bot.send_message(
                    uid,
                    f"🎉 <b>ဂုဏ်ယူပါသည်!</b>\n\n{plan_notice}\n\nသင့်အကောင့် (<code>{email}</code>) ကို <b>{plan} Plan</b> အဖြစ် အတည်ပြုဖွင့်လှစ်ပေးလိုက်ပါပြီ။\nသက်တမ်း: <code>{expiry}</code> ထိ အသုံးပြုနိုင်ပါသည်။"
                )
            except Exception:
                pass
        else:
            bot.send_message(call.message.chat.id, f"⚠️ Webhook Error: <code>{res.get('error')}</code>")

    elif action == "rej":
        pending_requests.pop(req_id, None)
        if sub_type == "insuf":
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=f"{call.message.caption}\n\n❌ <b>REJECTED (ငွေမလုံလောက်) by {admin_tag}</b>",
                reply_markup=None
            )
            try:
                bot.send_message(uid, "❌ သင်ပေးပို့သော ငွေလွှဲစလစ်သည် ပမာဏမလုံလောက်ပါ သို့မဟုတ် မှားယွင်းနေပါသည်။ Support သို့ ဆက်သွယ်ပါ။")
            except Exception:
                pass
        elif sub_type == "spam":
            if uid not in bot_data["banned_users"]:
                bot_data["banned_users"].append(uid)
                save_data(bot_data)
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=f"{call.message.caption}\n\n🚫 <b>USER BANNED (Spam/Fake) by {admin_tag}</b>",
                reply_markup=None
            )

# ==================== OWNER PANEL, NOTIFICATION MGMT & USER CONTROL ====================
@bot.message_handler(func=lambda msg: msg.chat.type == "private" and msg.text == "⚙️ Owner Menu")
def handle_owner_menu(message):
    if message.from_user.id != OWNER_ID:
        return
    bot.send_message(message.chat.id, build_owner_panel_text(), reply_markup=owner_inline_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith(("owner_", "notif_", "uc_")))
def handle_owner_panel_callbacks(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "Unauthorized", show_alert=True)
        return

    data = call.data

    if data == "owner_main_menu":
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "🏠 Main Menu", reply_markup=main_menu_keyboard(OWNER_ID))

    elif data == "owner_back_main":
        bot.edit_message_text(
            build_owner_panel_text(),
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=owner_inline_keyboard()
        )
        bot.answer_callback_query(call.id)

    elif data == "owner_view_settings":
        bot.send_message(call.message.chat.id, build_owner_panel_text())
        bot.answer_callback_query(call.id)

    elif data == "owner_broadcast":
        user_states[OWNER_ID] = {"step": "BROADCAST_MSG"}
        bot.send_message(call.message.chat.id, "📢 User များအားလုံးထံ ပို့လိုသော Broadcast မက်ဆေ့ခ်ျကို ရိုက်ထည့်ပေးပါ (ပယ်ဖျက်ရန် /cancel):")
        bot.answer_callback_query(call.id)

    elif data.startswith("owner_set_"):
        action = data.replace("owner_", "")
        field_map = {
            "set_kpay": ("KPay (ဖုန်းနံပါတ် နှင့် အမည်)", "kpay"),
            "set_wave": ("Wave (ဖုန်းနံပါတ် နှင့် အမည်)", "wave"),
            "set_pro_price": ("Pro Plan စျေးနှုန်း", "pro_price"),
            "set_vip_price": ("VIP Plan စျေးနှုန်း", "vip_price"),
            "set_ref_rate": ("Referral Rate", "ref_rate"),
            "set_ref_targets": ("Pro Target နှင့် VIP Target (ဥပမာ: 12 20)", "ref_targets"),
            "set_support": ("Support Telegram Username (without @)", "support_username")
        }
        if action in field_map:
            label, key = field_map[action]
            user_states[OWNER_ID] = {"step": f"EDIT_{key}"}
            bot.send_message(call.message.chat.id, f"📝 <b>{label}</b> အသစ်ကို ရိုက်ထည့်ပေးပါ:")
            bot.answer_callback_query(call.id)

    elif data == "notif_menu":
        bot.edit_message_text(
            build_notification_summary(),
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=notification_mgmt_keyboard()
        )
        bot.answer_callback_query(call.id)

    elif data.startswith("notif_edit_"):
        notif_key = data.replace("notif_edit_", "")
        labels = {
            "welcome_msg": "Welcome Message (<code>{first_name}</code>, <code>{full_name}</code>, <code>{username}</code>, <code>{user_id}</code> သုံးနိုင်ပါသည်)",
            "support_prompt": "Support Prompt Message",
            "plan_update_msg": "Plan Update Message"
        }
        if notif_key in labels:
            current_val = bot_data["notifications"].get(notif_key, "")
            user_states[OWNER_ID] = {"step": f"EDIT_NOTIF_{notif_key}"}
            bot.send_message(
                call.message.chat.id,
                f"📝 <b>{labels[notif_key]}</b> အသစ်ကို ရိုက်ထည့်ပေးပါ-\n\n<b>လက်ရှိစာသား:</b>\n{current_val}"
            )
            bot.answer_callback_query(call.id)

    elif data == "uc_menu":
        txt = (
            "👥 <b>User Control Panel</b>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"• Known Users: <b>{len(bot_data.get('known_users', {}))}</b> ယောက်\n"
            f"• Banned Users: <b>{len(bot_data.get('banned_users', []))}</b> ယောက်\n\n"
            "လုပ်ဆောင်လိုသော ခလုတ်ကို ရွေးချယ်ပါ-"
        )
        bot.edit_message_text(
            txt,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=user_control_keyboard()
        )
        bot.answer_callback_query(call.id)

    elif data == "uc_lookup":
        user_states[OWNER_ID] = {"step": "UC_LOOKUP"}
        bot.send_message(call.message.chat.id, "🔍 ကြည့်ရှုလိုသော User ရဲ့ <b>Telegram ID</b> ကို ရိုက်ထည့်ပေးပါ:")
        bot.answer_callback_query(call.id)

    elif data == "uc_ban":
        user_states[OWNER_ID] = {"step": "UC_BAN"}
        bot.send_message(call.message.chat.id, "🚫 Ban ပြုလုပ်လိုသော User ရဲ့ <b>Telegram ID</b> ကို ရိုက်ထည့်ပေးပါ:")
        bot.answer_callback_query(call.id)

    elif data == "uc_unban":
        user_states[OWNER_ID] = {"step": "UC_UNBAN"}
        bot.send_message(call.message.chat.id, "✅ Unban ပြုလုပ်လိုသော User ရဲ့ <b>Telegram ID</b> ကို ရိုက်ထည့်ပေးပါ:")
        bot.answer_callback_query(call.id)

    elif data == "uc_banned_list":
        banned = bot_data.get("banned_users", [])
        if not banned:
            bot.send_message(call.message.chat.id, "📋 Ban စာရင်းထဲတွင် User မရှိသေးပါ။")
        else:
            lines = ["📋 <b>Banned Users List</b>\n━━━━━━━━━━━━━━━━━━━"]
            for uid in banned:
                u_info = bot_data.get("known_users", {}).get(str(uid), {})
                uname = f"@{u_info['username']}" if u_info.get("username") else "none"
                lines.append(f"• <code>{uid}</code> — {u_info.get('name', 'Unknown')} ({uname})")
            bot.send_message(call.message.chat.id, "\n".join(lines))
        bot.answer_callback_query(call.id)

@bot.message_handler(
    func=lambda msg: msg.chat.type == "private"
    and msg.from_user.id == OWNER_ID
    and user_states.get(OWNER_ID, {}).get("step") is not None
)
def handle_owner_input(message):
    step = user_states[OWNER_ID]["step"]
    text = (message.text or "").strip()
    st = bot_data["settings"]

    if step == "BROADCAST_MSG":
        user_states.pop(OWNER_ID, None)
        sent_ok = 0
        sent_fail = 0
        for uid_str in list(bot_data.get("known_users", {}).keys()):
            if int(uid_str) in bot_data.get("banned_users", []):
                continue
            try:
                bot.send_message(int(uid_str), text)
                sent_ok += 1
            except Exception:
                sent_fail += 1
        bot.reply_to(message, f"📢 Broadcast ပြီးစီးပါပြီ။\n• ပို့ပြီး: <b>{sent_ok}</b> | မရောက်: <b>{sent_fail}</b>")
        return

    if step.startswith("EDIT_NOTIF_"):
        notif_key = step.replace("EDIT_NOTIF_", "")
        bot_data["notifications"][notif_key] = text
        save_data(bot_data)
        user_states.pop(OWNER_ID, None)
        bot.reply_to(
            message,
            f"✅ <b>{notif_key}</b> ကို အောင်မြင်စွာ ပြင်ဆင်သိမ်းဆည်းပြီးပါပြီ။",
            reply_markup=notification_mgmt_keyboard()
        )
        return

    if step.startswith("EDIT_"):
        key = step.replace("EDIT_", "")
        if key == "kpay":
            parts = text.split()
            st["kpay_phone"] = parts[0] if parts else ""
            st["kpay_name"] = " ".join(parts[1:]) if len(parts) > 1 else ""
        elif key == "wave":
            parts = text.split()
            st["wave_phone"] = parts[0] if parts else ""
            st["wave_name"] = " ".join(parts[1:]) if len(parts) > 1 else ""
        elif key == "pro_price":
            st["pro_price"] = text
        elif key == "vip_price":
            st["vip_price"] = text
        elif key == "ref_rate":
            st["ref_rate"] = text
        elif key == "ref_targets":
            parts = text.split()
            if len(parts) >= 2:
                st["pro_ref_target"] = f"{parts[0]} ယောက်"
                st["vip_ref_target"] = f"{parts[1]} ယောက်"
            else:
                st["pro_ref_target"] = text
        elif key == "support_username":
            st["support_username"] = text.replace("@", "")

        save_data(bot_data)
        user_states.pop(OWNER_ID, None)
        bot.reply_to(message, f"✅ <b>{key}</b> ဆက်တင်ကို အောင်မြင်စွာ ပြောင်းလဲသိမ်းဆည်းပြီးပါပြီ။")
        return

    if step in ("UC_LOOKUP", "UC_BAN", "UC_UNBAN"):
        if not text.isdigit():
            bot.reply_to(message, "❌ Telegram ID သည် ဂဏန်းသီးသန့် ဖြစ်ရပါမည်။ ပြန်ရိုက်ထည့်ပေးပါ:")
            return

        target_id = int(text)
        user_states.pop(OWNER_ID, None)
        u_info = bot_data.get("known_users", {}).get(str(target_id), {})
        u_name = u_info.get("name", "Unknown")
        u_user = f"@{u_info['username']}" if u_info.get("username") else "none"
        u_seen = u_info.get("last_seen", "N/A")
        banned_now = target_id in bot_data.get("banned_users", [])

        if step == "UC_LOOKUP":
            info_txt = (
                "👤 <b>User Details</b>\n"
                "━━━━━━━━━━━━━━━━━━━\n"
                f"• ID: <code>{target_id}</code>\n"
                f"• Name: {u_name}\n"
                f"• Username: {u_user}\n"
                f"• Last Seen: <code>{u_seen}</code>\n"
                f"• Status: {'🚫 Banned' if banned_now else '✅ Active'}"
            )
            bot.reply_to(message, info_txt, reply_markup=user_control_keyboard())

        elif step == "UC_BAN":
            if target_id == OWNER_ID:
                bot.reply_to(message, "⚠️ Owner ID ကို Ban လုပ်၍ မရပါ။")
                return
            if not banned_now:
                bot_data["banned_users"].append(target_id)
                save_data(bot_data)
            bot.reply_to(message, f"🚫 User <code>{target_id}</code> ({u_name}) ကို Ban ပြုလုပ်ပြီးပါပြီ။", reply_markup=user_control_keyboard())

        elif step == "UC_UNBAN":
            if banned_now:
                bot_data["banned_users"] = [x for x in bot_data["banned_users"] if x != target_id]
                save_data(bot_data)
            bot.reply_to(message, f"✅ User <code>{target_id}</code> ({u_name}) ကို Unban ပြုလုပ်ပြီးပါပြီ။", reply_markup=user_control_keyboard())

# ==================== HEALTH CHECK SERVER ====================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"AYK Bot is alive!")

def run_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
    print(f"Health server started on port {PORT}")
    server.serve_forever()

# ==================== MAIN EXECUTION ====================
if __name__ == "__main__":
    print("Starting Health Server...")
    threading.Thread(target=run_health_server, daemon=True).start()

    print("Starting Telegram Bot Polling...")
    bot.infinity_polling(skip_pending=True)
       
