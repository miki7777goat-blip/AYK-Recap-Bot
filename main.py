import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone
import requests
import telebot
from telebot import types

# ==================== ENVIRONMENT VARIABLES ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))  # Owner ၏ Telegram Chat ID (ဂဏန်းသီးသန့်)
ADMIN_GROUP_ID = int(os.getenv("ADMIN_GROUP_ID", "0"))  # Admin Group ID (ဥပမာ: -100xxxxxxxxxx)

WEBHOOK_URL = os.getenv(
    "WEBHOOK_URL", 
    "https://aykrecaptool.lovable.app/api/public/subscription/update"
)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
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
        "pro_price": "10,000 Ks / 1 Month",
        "vip_price": "25,000 Ks / 1 Month",
        "support_username": "mikef07"
    },
    "banned_users": [],
    "referrals": {}  # { user_id: referrer_id }
}

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return DEFAULT_DATA
    return DEFAULT_DATA

def save_data(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving data: {e}")

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
        types.InlineKeyboardButton("📞 Edit Support", callback_data="owner_set_support"),
        types.InlineKeyboardButton("📋 View Settings", callback_data="owner_view_settings")
    )
    return markup

# ==================== BOT HANDLERS ====================
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    if user_id in bot_data.get("banned_users", []):
        bot.reply_to(message, "❌ You are banned from using this bot.")
        return

    # Referral checking
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        referrer = args[1].replace("ref_", "")
        if str(user_id) not in bot_data["referrals"] and referrer != str(user_id):
            bot_data["referrals"][str(user_id)] = referrer
            save_data(bot_data)

    welcome_text = (
        f"👋 မင်္ဂလာပါ <b>{message.from_user.first_name}</b>!\n\n"
        "AYK Recap Bot မှ ကြိုဆိုပါသည်။ အောက်ပါ Menu မှတစ်ဆင့် အသုံးပြုနိုင်ပါပြီ။"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=main_menu_keyboard(user_id))

@bot.message_handler(func=lambda msg: msg.text == "👤 Profile")
def handle_profile(message):
    uid = message.from_user.id
    txt = (
        f"👤 <b>သင့် Profile အချက်အလက်</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"• Telegram ID: <code>{uid}</code>\n"
        f"• Name: {message.from_user.full_name}\n"
        f"• Username: @{message.from_user.username or 'မရှိပါ'}\n\n"
        f"<i>မှတ်ချက် - Web App ပေါ်တွင် Plan အခြေအနေကို စစ်ဆေးနိုင်ပါသည်။</i>"
    )
    bot.send_message(message.chat.id, txt)

@bot.message_handler(func=lambda msg: msg.text == "💬 Support")
def handle_support(message):
    support_user = bot_data["settings"].get("support_username", "mikef07")
    bot.send_message(message.chat.id, f"💬 အကူအညီလိုအပ်ပါက Owner/Support ဖြစ်သော @{support_user} သို့ တိုက်ရိုက် ဆက်သွယ်နိုင်ပါသည်။")

@bot.message_handler(func=lambda msg: msg.text == "👥 Referral")
def handle_referral(message):
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{message.from_user.id}"
    bot.send_message(message.chat.id, f"👥 <b>သင့် Referral Link:</b>\n\n<code>{ref_link}</code>\n\nမိတ်ဆွေများကို မျှဝေ၍ ဖိတ်ခေါ်နိုင်ပါသည်။")

# ==================== PLAN PURCHASE FLOW ====================
@bot.message_handler(func=lambda msg: msg.text == "💎 Buy Plan")
def handle_buy_plan(message):
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
        "ငွေလွှဲပြီးပါက App ထဲတွင် ဖွင့်ထားသော <b>သင့်အကောင့် Email</b> ကို အောက်တွင် ရိုက်ထည့်ပေးပါ-"
    )
    user_states[message.from_user.id] = {"step": "WAITING_EMAIL"}
    bot.send_message(message.chat.id, msg_text)

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id, {}).get("step") == "WAITING_EMAIL")
def handle_user_email(message):
    email = message.text.strip()
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

@bot.message_handler(content_types=['photo'], func=lambda msg: user_states.get(msg.from_user.id, {}).get("step") == "WAITING_SLIP")
def handle_user_slip(message):
    user_id = message.from_user.id
    email = user_states[user_id]["email"]
    photo_id = message.photo[-1].file_id

    # Admin Group သို့ Forward လုပ်မည့် Keyboard
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Approve PRO", callback_data=f"app_PRO_{user_id}_{email}"),
        types.InlineKeyboardButton("🌟 Approve VIP", callback_data=f"app_VIP_{user_id}_{email}"),
        types.InlineKeyboardButton("❌ ငွေမလုံလောက်", callback_data=f"rej_insuf_{user_id}"),
        types.InlineKeyboardButton("🚫 Spam/Fake", callback_data=f"rej_spam_{user_id}")
    )

    caption = (
        f"📩 <b>ငွေလွှဲစလစ် အသစ်ရောက်ရှိပါသည်</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"• User: {message.from_user.full_name} (@{message.from_user.username or 'none'})\n"
        f"• Telegram ID: <code>{user_id}</code>\n"
        f"• App Email: <code>{email}</code>\n"
        f"• Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
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
    data = call.data.split("_")
    action = data[0]

    if action == "app":
        plan = data[1]       # PRO သို့မဟုတ် VIP
        uid = int(data[2])
        email = data[3]

        bot.answer_callback_query(call.id, f"Updating {plan} in App...")
        
        # Webhook ခေါ်ယူပြီး App Database တွင် Plan ဖွင့်ခြင်း
        res = call_subscription_webhook(email=email, plan=plan, duration_days=30)
        
        if res["success"]:
            expiry = res["data"].get("expiryDate", "30 Days")
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=f"{call.message.caption}\n\n✅ <b>APPROVED ({plan}) by @{call.from_user.username}</b>\nExpiry: {expiry}",
                reply_markup=None
            )
            # User ထံ အကြောင်းကြားစာ ပို့ခြင်း
            try:
                bot.send_message(
                    uid,
                    f"🎉 <b>ဂုဏ်ယူပါသည်!</b>\n\nသင့်အကောင့် (<code>{email}</code>) ကို <b>{plan} Plan</b> အဖြစ် အောင်မြင်စွာ အတည်ပြုဖွင့်လှစ်ပေးလိုက်ပါပြီ။\nသက်တမ်း: <code>{expiry}</code> ထိ အသုံးပြုနိုင်ပါသည်။"
                )
            except Exception:
                pass
        else:
            bot.send_message(call.message.chat.id, f"⚠️ Webhook Error: {res.get('error')}")

    elif action == "rej":
        reason = data[1]
        uid = int(data[2])
        
        if reason == "insuf":
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=f"{call.message.caption}\n\n❌ <b>REJECTED (ငွေမလုံလောက်) by @{call.from_user.username}</b>",
                reply_markup=None
            )
            try:
                bot.send_message(uid, "❌ သင်ပေးပို့သော ငွေလွှဲစလစ်သည် ပမာဏမလုံလောက်ပါ သို့မဟုတ် မှားယွင်းနေပါသည်။ Support သို့ ဆက်သွယ်ပါ။")
            except Exception:
                pass
        elif reason == "spam":
            if uid not in bot_data["banned_users"]:
                bot_data["banned_users"].append(uid)
                save_data(bot_data)
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=f"{call.message.caption}\n\n🚫 <b>USER BANNED (Spam/Fake) by @{call.from_user.username}</b>",
                reply_markup=None
            )

# ==================== OWNER PANEL ====================
@bot.message_handler(func=lambda msg: msg.text == "⚙️ Owner Menu")
def handle_owner_menu(message):
    if message.from_user.id != OWNER_ID:
        return
    bot.send_message(message.chat.id, "⚙️ <b>Owner Control Panel</b>\nအောက်ပါ ဆက်တင်များကို ပြင်ဆင်နိုင်ပါသည်-", reply_markup=owner_inline_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith("owner_"))
def handle_owner_actions(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "Unauthorized", show_alert=True)
        return

    action = call.data.replace("owner_", "")
    st = bot_data["settings"]

    if action == "view_settings":
        txt = (
            "⚙️ <b>လက်ရှိ ဆက်တင်များ</b>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"• KPay: {st.get('kpay_phone')} ({st.get('kpay_name')})\n"
            f"• Wave: {st.get('wave_phone')} ({st.get('wave_name')})\n"
            f"• Pro Price: {st.get('pro_price')}\n"
            f"• VIP Price: {st.get('vip_price')}\n"
            f"• Support: @{st.get('support_username')}\n"
            f"• Banned Users: {len(bot_data.get('banned_users', []))} ယောက်"
        )
        bot.send_message(call.message.chat.id, txt)
        bot.answer_callback_query(call.id)
    else:
        field_map = {
            "set_kpay": ("KPay (ဖုန်းနံပါတ် နှင့် အမည်)", "kpay"),
            "set_wave": ("Wave (ဖုန်းနံပါတ် နှင့် အမည်)", "wave"),
            "set_pro_price": ("Pro Plan စျေးနှုန်း", "pro_price"),
            "set_vip_price": ("VIP Plan စျေးနှုန်း", "vip_price"),
            "set_support": ("Support Telegram Username (without @)", "support_username")
        }
        if action in field_map:
            label, key = field_map[action]
            user_states[OWNER_ID] = {"step": f"EDIT_{key}"}
            bot.send_message(call.message.chat.id, f"📝 <b>{label}</b> အသစ်ကို ရိုက်ထည့်ပေးပါ:")
            bot.answer_callback_query(call.id)

@bot.message_handler(func=lambda msg: msg.from_user.id == OWNER_ID and user_states.get(OWNER_ID, {}).get("step", "").startswith("EDIT_"))
def handle_owner_input(message):
    step = user_states[OWNER_ID]["step"].replace("EDIT_", "")
    text = message.text.strip()
    st = bot_data["settings"]

    if step == "kpay":
        parts = text.split()
        st["kpay_phone"] = parts[0]
        st["kpay_name"] = " ".join(parts[1:]) if len(parts) > 1 else ""
    elif step == "wave":
        parts = text.split()
        st["wave_phone"] = parts[0]
        st["wave_name"] = " ".join(parts[1:]) if len(parts) > 1 else ""
    elif step == "pro_price":
        st["pro_price"] = text
    elif step == "vip_price":
        st["vip_price"] = text
    elif step == "support_username":
        st["support_username"] = text.replace("@", "")

    save_data(bot_data)
    user_states.pop(OWNER_ID, None)
    bot.reply_to(message, f"✅ <b>{step}</b> ဆက်တင်ကို အောင်မြင်စွာ ပြောင်းလဲသိမ်းဆည်းပြီးပါပြီ။")

# ==================== RENDER HEALTH CHECK SERVER ====================
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
    print("Starting Render Health Server...")
    # Background Thread ဖြင့် Port ဖွင့်ပေးထားခြင်း (Render Web Service မကျစေရန်)
    threading.Thread(target=run_health_server, daemon=True).start()

    print("Starting Telegram Bot Polling...")
    bot.infinity_polling(skip_pending=True)
    
