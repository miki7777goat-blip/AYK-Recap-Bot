import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone
import requests
import telebot
from telebot import types
import json
import os
from supabase import create_client, Client

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

FIELD_MAP = {
    "edit_welcome": "welcome_message",
    "edit_ref_info": "ref_info_msg",
    "edit_ref_notify": "ref_notify_msg",
    "edit_approve_msg": "approve_msg",
    "edit_reject_msg": "reject_msg",
    "edit_slip_msg": "slip_msg",
    "edit_custom_notices": "custom_notices",
}


def get_main_config() -> dict:
    """bot_config table ထဲက main_config row ရဲ့ data ကို dict အဖြစ် ပြန်ထုတ်ပေးသည်။"""
    res = (
        supabase.table("bot_config")
        .select("data")
        .eq("id", "main_config")
        .single()
        .execute()
    )
    raw = res.data.get("data") if res.data else {}

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


def update_main_config_field(field_key: str, new_value: str) -> dict:
    """Bot မှာ edit လုပ်လိုက်တဲ့ value ကို main_config ရဲ့ data ထဲမှာ update လုပ်သည်။"""
    current_data = get_main_config()
    current_data[field_key] = new_value

    # data column က text ဖြစ်နေရင် JSON string အဖြစ် သိမ်းပြီး၊ jsonb ဖြစ်ရင် dict အတိုင်း သိမ်းသည်
    res = (
        supabase.table("bot_config")
        .select("data")
        .eq("id", "main_config")
        .single()
        .execute()
    )
    existing_raw = res.data.get("data") if res.data else None
    payload_value = json.dumps(current_data, ensure_ascii=False) if isinstance(existing_raw, str) else current_data

    supabase.table("bot_config").update({"data": payload_value}).eq("id", "main_config").execute()
    return current_data
    
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
# ==================== BOT HANDLERS ====================
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.from_user.id
    if user_id in bot_data.get("banned_users", []):
        bot.reply_to(message, "❌ You are banned from using this bot.")
        return

    register_known_user(user_id)
    user_states.pop(user_id, None)

    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        referrer_str = args[1].replace("ref_", "").strip()
        if referrer_str.isdigit() and referrer_str != str(user_id):
            referrer_id = int(referrer_str)
            if str(user_id) not in bot_data["referrals"]:
                bot_data["referrals"][str(user_id)] = referrer_str
                current_cnt = get_referral_count(referrer_id) + 1
                bot_data["referral_counts"][referrer_str] = current_cnt
                save_data(bot_data)

                discount_per = get_referral_discount_per_user()
                total_discount = current_cnt * discount_per
                req_cnt = get_required_referrals_for_free_pro()
                
                tmpl = bot_data["messages"].get("referral_notify", DEFAULT_MESSAGES["referral_notify"])
                notify_txt = tmpl.format(
                    invited_name=message.from_user.full_name,
                    ref_count=current_cnt
                )
                if req_cnt > 0:
                    notify_txt += f" / <b>{req_cnt}</b> ယောက် (Free PRO အတွက်)"
                notify_txt += f"\n• လက်ရှိ လျှော့စျေးတန်ဖိုး: <b>{total_discount:,} Ks</b> ({discount_per:,} Ks / ယောက်)"

                try:
                    bot.send_message(referrer_id, notify_txt)
                except Exception:
                    pass

    tmpl = bot_data["messages"].get("welcome", DEFAULT_MESSAGES["welcome"])
    welcome_text = tmpl.format(
        first_name=message.from_user.first_name,
        full_name=message.from_user.full_name
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=main_menu_keyboard(user_id))

@bot.message_handler(func=lambda msg: msg.text == "👤 Profile")
def handle_profile(message):
    uid = message.from_user.id
    register_known_user(uid)
    ref_cnt = get_referral_count(uid)
    discount_per = get_referral_discount_per_user()
    discount_val = ref_cnt * discount_per
    req_cnt = get_required_referrals_for_free_pro()

    txt = (
        f"👤 <b>သင့် Profile အချက်အလက်</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"• Telegram ID: <code>{uid}</code>\n"
        f"• Name: {message.from_user.full_name}\n"
        f"• Username: @{message.from_user.username or 'မရှိပါ'}\n"
        f"• Referral Count: <b>{ref_cnt}</b> ယောက်"
    )
    if req_cnt > 0:
        txt += f" / <b>{req_cnt}</b> ယောက် (Free PRO)"
    txt += (
        f"\n• လက်ရှိ Discount တန်ဖိုး: <b>{discount_val:,} Ks</b>\n\n"
        f"<i>မှတ်ချက် - Web App ပေါ်တွင် Plan အခြေအနေကို စစ်ဆေးနိုင်ပါသည်။</i>"
    )
    bot.send_message(message.chat.id, txt)

@bot.message_handler(func=lambda msg: msg.text == "📞 Support")
def handle_support(message):
    register_known_user(message.from_user.id)
    support_user = bot_data["settings"].get("support_username", "mikef07")
    bot.send_message(message.chat.id, f"💬 အကူအညီလိုအပ်ပါက Owner/Support ဖြစ်သော @{support_user} သို့ တိုက်ရိုက် ဆက်သွယ်နိုင်ပါသည်။")

@bot.message_handler(func=lambda msg: msg.text == "👥 Referral")
def handle_referral(message):
    uid = message.from_user.id
    register_known_user(uid)
    bot_info = bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref_{uid}"

    ref_cnt = get_referral_count(uid)
    discount_per = get_referral_discount_per_user()
    pro_ks = get_pro_price_ks()
    req_cnt = get_required_referrals_for_free_pro()
    current_discount = min(pro_ks, ref_cnt * discount_per)
    remaining_ks = max(0, pro_ks - current_discount)

    txt = (
        f"👥 <b>သင့် Referral အချက်အလက်</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"• Link: <code>{ref_link}</code>\n"
        f"• ဖိတ်ခေါ်သူတစ်ဦးလျှင် လျှော့စျေး: <b>{discount_per:,} Ks</b>\n"
        f"• Pro Plan စျေးနှုန်း: <b>{pro_ks:,} Ks</b>\n"
        f"• လက်ရှိ ဖိတ်ထားသူ: <b>{ref_cnt}</b> ယောက်"
    )
    if req_cnt > 0:
        txt += f" (Free PRO အတွက် <b>{req_cnt}</b> ယောက်လိုအပ်ပါသည်)"
    txt += (
        f"\n• လက်ရှိ လျှော့စျေး: <b>{current_discount:,} Ks</b>\n"
        f"• Pro Plan အတွက် ကျန်ငွေ: <b>{remaining_ks:,} Ks</b>"
    )

    markup = None
    if req_cnt > 0 and ref_cnt >= req_cnt:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🎁 Claim Free PRO", callback_data=f"claim_free_pro_{uid}"))
        txt += "\n\n🎉 <b>Free PRO ရရှိရန် သတ်မှတ်အရေအတွက် ပြည့်မီပါပြီ! အောက်ပါခလုတ်ဖြင့် တောင်းဆိုနိုင်ပါသည်။</b>"

    bot.send_message(message.chat.id, txt, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("claim_free_pro_"))
def handle_claim_free_pro_button(call):
    uid = int(call.data.replace("claim_free_pro_", ""))
    if call.from_user.id != uid:
        bot.answer_callback_query(call.id, "သင့်အတွက်သာ ဖြစ်ပါသည်။", show_alert=True)
        return
    if uid in bot_data.get("banned_users", []):
        bot.answer_callback_query(call.id, "Banned user", show_alert=True)
        return

    ref_cnt = get_referral_count(uid)
    req_cnt = get_required_referrals_for_free_pro()
    if req_cnt <= 0 or ref_cnt < req_cnt:
        bot.answer_callback_query(call.id, "Referral အရေအတွက် မပြည့်သေးပါ။", show_alert=True)
        return

    user_states[uid] = {"step": "WAITING_FREE_PRO_EMAIL"}
    bot.answer_callback_query(call.id)
    bot.send_message(
        call.message.chat.id,
        "🎁 <b>Free PRO Plan တောင်းဆိုခြင်း</b>\n\n"
        "Free PRO ဖွင့်ပေးရန် App ထဲတွင် ဖွင့်ထားသော <b>သင့်အကောင့် Email</b> ကို ရိုက်ထည့်ပေးပါ-"
    )

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id, {}).get("step") == "WAITING_FREE_PRO_EMAIL")
def handle_free_pro_email(message):
    uid = message.from_user.id
    email = message.text.strip()
    if "@" not in email or "." not in email:
        bot.reply_to(message, "Email ပုံစံ မှားယွင်းနေပါသည်။ သေချာစွာ ပြန်လည်ရိုက်ထည့်ပေးပါ:")
        return

    ref_cnt = get_referral_count(uid)
    req_cnt = get_required_referrals_for_free_pro()
    if req_cnt <= 0 or ref_cnt < req_cnt:
        user_states.pop(uid, None)
        bot.reply_to(message, "⚠️ သင့် Referral အရေအတွက် မပြည့်မီတော့ပါ။")
        return

    if ADMIN_GROUP_ID == 0:
        user_states.pop(uid, None)
        bot.reply_to(message, "⚠️ Admin Group ID မသတ်မှတ်ရသေးပါ။")
        return

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Approve Free PRO", callback_data=f"freeapp_{uid}_{email}"),
        types.InlineKeyboardButton("❌ Reject", callback_data=f"freerej_{uid}")
    )

    caption = (
        f"🎁 <b>Free PRO Claim Request (Referral Reward)</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"• User: {message.from_user.full_name} (@{message.from_user.username or 'none'})\n"
        f"• Telegram ID: <code>{uid}</code>\n"
        f"• App Email: <code>{email}</code>\n"
        f"• Referral Count: <b>{ref_cnt}</b> / <b>{req_cnt}</b>\n"
        f"• Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )

    bot.send_message(chat_id=ADMIN_GROUP_ID, text=caption, reply_markup=markup)
    user_states.pop(uid, None)
    bot.reply_to(
        message,
        "✅ သင့် Free PRO တောင်းဆိုမှုကို Admin Group သို့ ပို့ပြီးပါပြီ။ အတည်ပြုပြီးပါက အကြောင်းကြားပေးပါမည်။",
        reply_markup=main_menu_keyboard(uid)
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith(("freeapp_", "freerej_")))
def handle_free_pro_admin_callback(call):
    parts = call.data.split("_", 2)
    action = parts[0]

    if action == "freeapp":
        uid = int(parts[1])
        email = parts[2]
        bot.answer_callback_query(call.id, "Activating Free PRO...")

        res = call_subscription_webhook(email=email, plan="PRO", duration_days=30)
        if res["success"]:
            expiry = res["data"].get("expiryDate", "30 Days")
            bot_data["referral_counts"][str(uid)] = 0
            save_data(bot_data)

            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"{call.message.text}\n\n✅ <b>FREE PRO APPROVED by @{call.from_user.username}</b>\n• Referral Count Reset: <b>0</b>\n• Expiry: {expiry}",
                reply_markup=None
            )
            try:
                tmpl = bot_data["messages"].get("approve_user", DEFAULT_MESSAGES["approve_user"])
                approval_msg = tmpl.format(
                    email=email,
                    plan="PRO",
                    expiry=expiry
                )
                bot.send_message(uid, approval_msg)
            except Exception:
                pass
        else:
            bot.send_message(call.message.chat.id, f"⚠️ Webhook Error: {res.get('error')}")

    elif action == "freerej":
        uid = int(parts[1])
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"{call.message.text}\n\n❌ <b>FREE PRO REJECTED by @{call.from_user.username}</b>",
            reply_markup=None
        )
        try:
            tmpl = bot_data["messages"].get("reject_user", DEFAULT_MESSAGES["reject_user"])
            bot.send_message(uid, tmpl)
        except Exception:
            pass

# ==================== USER <-> ADMIN TOPIC CHAT ====================
@bot.message_handler(func=lambda msg: msg.text == "💬 Chat with Admin")
def handle_chat_start(message):
    user_id = message.from_user.id
    if user_id in bot_data.get("banned_users", []):
        bot.reply_to(message, " this bot.")
        return

    register_known_user(user_id)
    user_states[user_id] = {"step": "CHATTING_ADMIN"}
    bot.send_message(
        message.chat.id,
        "💬 <b>Admin Group Topic နှင့် စကားပြောရန် အဆင်သင့်ဖြစ်ပါပြီ።</b>\n\n"
        "သင်မေးလိုသော စာ (သို့မဟုတ် ပုံ) ကို ရိုက်ထည့်ပို့လိုက်ပါ။ Admin ဘက်မှ ပြန်ဖြေလာလျှင် ဒီနေရာမှာ ပြန်မြင်ရပါမည်။\n"
        "ထွက်လိုပါက <b> ကို နှိပ်ပါ။",
        reply_markup=chat_exit_keyboard()
    )

@bot.message_handler(func=lambda msg: msg.text == "❌ Exit Chat")
def handle_chat_exit(message):
    user_states.pop(message.from_user.id, None)
    bot.send_message(
        message.chat.id,
        "✅ Admin နှင့် စကားပြောခြင်းမှ ထွက်လိုက်ပါပြီ။",
        reply_markup=main_menu_keyboard(message.from_user.id)
    )

@bot.message_handler(
    content_types=['text', 'photo'],
    func=lambda msg: msg.chat.type == "private" and user_states.get(msg.from_user.id, {}).get("step") == "CHATTING_ADMIN"
)
def forward_user_question_to_topic(message):
    user = message.from_user
    if ADMIN_GROUP_ID == 0:
        bot.reply_to(message, "⚠️ Admin Group ID မသတ်မှတ်ရသေးပါ။")
        return

    header = (
        f"❓ <b>User မေးခွန်း / စကားပြောမှု</b>\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"• Name: {user.full_name} (@{user.username or 'none'})\n"
        f"• UserID: <code>{user.id}</code>\n"
    )

    try:
        if message.content_type == "photo":
            caption = header + (f"• Message: {message.caption}" if message.caption else "")
            bot.send_photo(
                chat_id=ADMIN_GROUP_ID,
                photo=message.photo[-1].file_id,
                caption=caption,
                message_thread_id=SUPPORT_TOPIC_ID
            )
        else:
            body = header + f"• Message: {message.text}"
            bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                text=body,
                message_thread_id=SUPPORT_TOPIC_ID
            )
        bot.reply_to(message, "✅ သင့်စာကို Admin Topic ထဲသို့ ပို့ပြီးပါပြီ။ ပြန်ကြားချက်ကို စောင့်ဆိုင်းပေးပါ။")
    except Exception as e:
        bot.reply_to(message, f"⚠️ ပို့ရာတွင် အခက်အခဲရှိပါသည်: {e}")

@bot.message_handler(
    func=lambda msg: (
        msg.chat.id == ADMIN_GROUP_ID
        and msg.message_thread_id == SUPPORT_TOPIC_ID
        and msg.reply_to_message is not None
        and msg.from_user is not None
        and not msg.from_user.is_bot
    )
)
def reply_from_topic_to_user(message):
    original_text = message.reply_to_message.text or message.reply_to_message.caption or ""
    target_user_id = None

    for line in original_text.splitlines():
        if "UserID:" in line:
            digits = "".join(ch for ch in line.split("UserID:")[-1] if ch.isdigit())
            if digits:
                target_user_id = int(digits)
                break

    if not target_user_id:
        return

    try:
        admin_name = message.from_user.first_name or "Admin"
        bot.send_message(
            target_user_id,
            f"📩 <b>{admin_name} မှ ပြန်ကြားချက်:</b>\n\n{message.text}"
        )
        bot.reply_to(message, "✅ User ထံ ပြန်ပို့ပြီးပါပြီ။")
    except Exception as e:
        bot.reply_to(message, f"⚠️ User ထံ ပို့မရပါ: {e}")    
# ==================== PLAN PURCHASE FLOW ====================
@bot.message_handler(func=lambda msg: msg.text == "💎 Buy Plan")
def handle_buy_plan(message):
    uid = message.from_user.id
    register_known_user(uid)
    st = bot_data["settings"]

    pro_ks = get_pro_price_ks()
    ref_cnt = get_referral_count(uid)
    discount_per = get_referral_discount_per_user()
    discount_ks = min(pro_ks, ref_cnt * discount_per)
    final_pro_ks = max(0, pro_ks - discount_ks)

    pro_line = f"{st.get('pro_price')}"
    if discount_ks > 0:
        pro_line += f"\n   ↳ 🎁 Referral Discount: <b>-{discount_ks:,} Ks</b> ({ref_cnt} ယောက်) → <b>{final_pro_ks:,} Ks</b>"

    msg_text = (
        "💎 <b>Plan များ ဝယ်ယူရန် ငွေလွှဲအကောင့်များ</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👑 <b>Pro Plan:</b> {pro_line}\n"
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
    user_states[uid] = {"step": "WAITING_EMAIL"}
    bot.send_message(message.chat.id, msg_text)

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id, {}).get("step") == "WAITING_EMAIL")
def handle_user_email(message):
    email = message.text.strip()
    if "@" not in email or "." not in email:
        bot.reply_to(message, "Email ပုံစံ မှားယွင်းနေပါသည်။ သေချာစွာ ပြန်လည်ရိုက်ထည့်ပေးပါ:")
        return

    user_states[message.from_user.id] = {
        "step": "WAITING_SLIP",
        "email": email
    }
    bot.send_message(
        message.chat.id,
        f"✅ Email <code>{email}</code> ကို မှတ်သားထားပါသည်။\n\nကျေးဇူးပြု၍ <b>ငွေလွှဲပြေစာ (Screenshot/Photo)</b> ကို ပို့ပေးပါ-"
    )

@bot.message_handler(content_types=['photo'], func=lambda msg: user_states.get(msg.from_user.id, {}).get("step") == "WAITING_SLIP")
def handle_user_slip(message):
    user_id = message.from_user.id
    email = user_states[user_id]["email"]
    photo_id = message.photo[-1].file_id

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
        bot.send_photo(
            chat_id=ADMIN_GROUP_ID,
            photo=photo_id,
            caption=caption,
            reply_markup=markup
        )
        tmpl = bot_data["messages"].get("slip_submitted", DEFAULT_MESSAGES["slip_submitted"])
        bot.reply_to(message, tmpl, reply_markup=main_menu_keyboard(user_id))
    else:
        bot.reply_to(message, "⚠️ Admin Group ID မသတ်မှတ်ရသေးပါ။ Owner ထံ ဆက်သွယ်ပါ။")

    user_states.pop(user_id, None)

# ==================== ADMIN ACTIONS CALLBACK ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith(("app_", "rej_")))
def handle_admin_callback(call):
    data = call.data.split("_")
    action = data[0]

    if action == "app":
        plan = data[1]
        uid = int(data[2])
        email = data[3]

        bot.answer_callback_query(call.id, f"Updating {plan} in App...")

        res = call_subscription_webhook(email=email, plan=plan, duration_days=30)

        if res["success"]:
            expiry = res["data"].get("expiryDate", "30 Days")
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=f"{call.message.caption}\n\n✅ <b>APPROVED ({plan}) by @{call.from_user.username}</b>\nExpiry: {expiry}",
                reply_markup=None
            )
            try:
                tmpl = bot_data["messages"].get("approve_user", DEFAULT_MESSAGES["approve_user"])
                approval_msg = tmpl.format(
                    email=email,
                    plan=plan,
                    expiry=expiry
                )
                bot.send_message(uid, approval_msg)
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
                tmpl = bot_data["messages"].get("reject_user", DEFAULT_MESSAGES["reject_user"])
                bot.send_message(uid, tmpl)
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
    register_known_user(message.from_user.id)
    bot.send_message(message.chat.id, "⚙️ <b>Owner Control Panel</b>\nအောက်ပါ ဆက်တင်များကို ပြင်ဆင်နိုင်ပါသည်-", reply_markup=owner_inline_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith("owner_"))
def handle_owner_actions(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "Unauthorized", show_alert=True)
        return

    action = call.data.replace("owner_", "")
    st = bot_data["settings"]

    if action == "view_settings":
        req_cnt = get_required_referrals_for_free_pro()
        txt = (
            "⚙️ <b>လက်ရှိ ဆက်တင်များ</b>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"• KPay: {st.get('kpay_phone')} ({st.get('kpay_name')})\n"
            f"• Wave: {st.get('wave_phone')} ({st.get('wave_name')})\n"
            f"• Pro Price: {st.get('pro_price')}\n"
            f"• VIP Price: {st.get('vip_price')}\n"
            f"• Referral Discount: <b>{get_referral_discount_per_user():,} Ks</b> / ယောက် (Free PRO = {req_cnt} ယောက်)\n"
            f"• Support: @{st.get('support_username')}\n"
            f"• Known Users: {len(bot_data.get('known_users', []))} ယောက်\n"
            f"• Banned Users: {len(bot_data.get('banned_users', []))} ယောက်"
        )
        bot.send_message(call.message.chat.id, txt)
        bot.answer_callback_query(call.id)
    elif action == "broadcast":
        user_states[OWNER_ID] = {"step": "OWNER_BROADCAST"}
        bot.send_message(call.message.chat.id, "📢 User အားလုံးဆီ ပို့မည့် <b>အသိပေးချက် မက်ဆေ့ခ်ျ</b> ကို ရိုက်ထည့်ပေးပါ:")
        bot.answer_callback_query(call.id)
    else:
        field_map = {
            "set_kpay": ("KPay (ဖုန်းနံပါတ် နှင့် အမည်)", "kpay"),
            "set_wave": ("Wave (ဖုန်းနံပါတ် နှင့် အမည်)", "wave"),
            "set_pro_price": ("Pro Plan ဈေးနှုန်း (ဥပမာ: 3,000 Ks / 1 Month)", "pro_price"),
            "set_vip_price": ("VIP Plan ဈေးနှုန်း", "vip_price"),
            "set_ref_discount": ("ဖိတ်ခေါ်သူတစ်ဦးလျှင် လျှော့ပေးမည့် ပမာဏ (ဂဏန်းသီးသန့်၊ ဥပမာ: 250)", "ref_discount"),
            "set_support": ("Support Telegram Username (without @)", "support_username"),
            "edit_welcome": ("Welcome Message\nVariables များ: {first_name}, {full_name}", "welcome"),
            "edit_ref_notify": ("Referral Notify Message\nVariables များ: {invited_name}, {ref_count}", "referral_notify"),
            "edit_approve": ("Approve Message\nVariables များ: {email}, {plan}, {expiry}", "approve_user"),
            "edit_reject": ("Reject Message", "reject_user"),
            "edit_slip": ("Slip Submitted Message", "slip_submitted")
        }
        if action in field_map:
            label, key = field_map[action]
            user_states[OWNER_ID] = {"step": f"EDIT_{key}"}
            bot.send_message(call.message.chat.id, f"📝 <b>{label}</b> အသစ်ကို ရိုက်ထည့်ပေးပါ:")
            bot.answer_callback_query(call.id)

@bot.message_handler(
    func=lambda msg: msg.from_user.id == OWNER_ID
    and (
        user_states.get(OWNER_ID, {}).get("step", "").startswith("EDIT_")
        or user_states.get(OWNER_ID, {}).get("step") == "OWNER_BROADCAST"
    )
)
def handle_owner_input(message):
    step = user_states[OWNER_ID]["step"]
    text = message.text.strip()
    st = bot_data["settings"]

    if step == "OWNER_BROADCAST":
        user_states.pop(OWNER_ID, None)
        sent_ok = 0
        failed = 0
        banned_set = set(bot_data.get("banned_users", []))
        for uid in list(bot_data.get("known_users", [])):
            if int(uid) in banned_set:
                continue
            try:
                bot.send_message(
                    int(uid),
                    f"📢 <b>အသိပေးချက်အသစ်</b>\n━━━━━━━━━━━━━━━━━━━\n{message.text}"
                )
                sent_ok += 1
            except Exception:
                failed += 1
        bot.reply_to(message, f"✅ Broadcast ပို့ပြီးပါပြီ။\n• အောင်မြင်: <b>{sent_ok}</b> ယောက်\n• မအောင်မြင်: <b>{failed}</b> ယောက်")
        return

    if step.startswith("EDIT_"):
        field = step.replace("EDIT_", "")
        if field in DEFAULT_SETTINGS:
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
            elif field == "referral_discount":
                digits = "".join(ch for ch in text if ch.isdigit())
                if not digits:
                    bot.reply_to(message, "ဂဏန်းသီးသန့် ရိုက်ထည့်ပေးပါ (ဥပမာ: 250)။")
                    return
                st["referral_discount"] = int(digits)
            elif field == "support_username":
                st["support_username"] = text.replace("@", "")
            save_data(bot_data)
            user_states.pop(OWNER_ID, None)
            bot.reply_to(message, f"✅ <b>{field}</b> ဆက်တင်ကို အောင်မြင်စွာ ပြောင်းလဲသိမ်းဆည်းပြီးပါပြီ။")
            return
        
        elif field in DEFAULT_MESSAGES:
            bot_data["messages"][field] = text
            save_data(bot_data)
            user_states.pop(OWNER_ID, None)
            bot.reply_to(message, f"✅ <b>{field}</b> မက်ဆေ့ခ်ျ ပုံစံအသစ်ကို သိမ်းဆည်းပြီးပါပြီ။")
            return

# ==================== RENDER HELPER SERVER ====================
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
