import json
import os
import threading
import flask
import requests
import telebot
from telebot import types

BOT_TOKEN = "8909534863:AAG9F4ZwZRaT0RYovkaEKauvEtzM91-j2qk"
OWNER_ID = 8415289516
ADMIN_GROUP_ID = -1004448651266
WEBHOOK_URL = "https://aykrecaptool.lovable.app/api/public/telegram/webhook"
WEBHOOK_SECRET = "MKivv5WQl1i5RhdumjWjcad6Pk7YqgRG96v1q72RQ4Qwwvad"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)
app = flask.Flask(__name__)
DATA_FILE = "bot_data.json"

user_states = {}
pending_requests = {}


def load_data():
    default_data = {
        "kpay_name": "U Aye",
        "kpay_no": "09123456789",
        "wave_name": "U Aye",
        "wave_no": "09123456789",
        "pro_price": "15,000 MMK",
        "vip_price": "30,000 MMK",
        "support": "@mikef07",
        "referral_link": "https://t.me/your_bot?start=",
        "welcome_msg": "မင်္ဂလာပါ။ အောက်ပါ ခလုတ်များမှ တစ်ဆင့် အသုံးပြုလိုရာကို ရွေးချယ်ပါ။",
        "request_noti": (
            "🧾 **ငွေပေးချေမှု တောင်းဆိုချက် အသစ်**\n"
            "👤 အသုံးပြုသူ: `{first_name}` (`{user_id}`)\n"
            "📧 အီးမေးလ်: `{email}`\n"
            "💎 Plan: **{plan}**"
        ),
        "approved_noti": (
            "🎉 `{email}` အတွက် **{plan}** Plan ({days} ရက်) ကို အတည်ပြုပေးပြီးပါပြီ။ "
            "Web App ကို Refresh လုပ်ပြီး ပြန်အသုံးပြုနိုင်ပါပြီ။"
        ),
        "rejected_noti": "❌ သင့်ရဲ့ ငွေပေးချေမှု တောင်းဆိုချက်ကို ပယ်ချလိုက်ပါသည်။ Support ကို ဆက်သွယ်မေးမြန်းနိုင်ပါတယ်။",
        "spam_noti": "⚠️ သင့်အကောင့်ကို Spam အဖြစ် သတ်မှတ်လိုက်ပါသည်။",
        "banned_noti": "🚫 သင်သည် ဤ Bot ကို အသုံးပြုခွင့် ပိတ်ပင်ခံထားရပါသည်။",
        "banned_users": [],
        "spam_users": [],
        "referrals": {},
    }
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    default_data.update(loaded)
                return default_data
        except Exception as e:
            print(f"Data load error: {e}")
    return default_data


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update_web_subscription(email, plan, duration_days=30):
    payload = {
        "email": email.strip().lower(),
        "plan": plan.strip().upper(),
        "status": "ACTIVE",
        "durationDays": duration_days,
        "customDailyQuota": None,
        "customCharLimit": None,
    }
    headers = {"Content-Type": "application/json"}
    if WEBHOOK_SECRET:
        headers["x-webhook-secret"] = WEBHOOK_SECRET
        headers["Authorization"] = f"Bearer {WEBHOOK_SECRET}"
    try:
        res = requests.post(WEBHOOK_URL, json=payload, headers=headers, timeout=15)
        print(f"Webhook Status: {res.status_code} | Response: {res.text}")
        return res.status_code in (200, 201), res.text
    except Exception as e:
        print(f"Webhook error: {e}")
        return False, str(e)


def get_main_menu(user_id=None):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💎 Buy PRO", callback_data="buy_PRO"),
        types.InlineKeyboardButton("👑 Buy VIP", callback_data="buy_VIP"),
        types.InlineKeyboardButton("🎁 Referral", callback_data="menu_ref"),
        types.InlineKeyboardButton("💬 Support", callback_data="menu_support"),
    )
    if user_id == OWNER_ID:
        markup.add(types.InlineKeyboardButton("⚙️ Owner Menu", callback_data="owner_menu"))
    return markup


def get_owner_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💳 Set KPay", callback_data="set_kpay"),
        types.InlineKeyboardButton("🌊 Set WavePay", callback_data="set_wave"),
        types.InlineKeyboardButton("💎 Set Pro Price", callback_data="set_pro"),
        types.InlineKeyboardButton("👑 Set VIP Price", callback_data="set_vip"),
        types.InlineKeyboardButton("💬 Set Support", callback_data="set_support"),
        types.InlineKeyboardButton("👋 Set Welcome Msg", callback_data="set_welcome"),
        types.InlineKeyboardButton("📩 Set Request Noti", callback_data="set_req_noti"),
        types.InlineKeyboardButton("✅ Set Approved Noti", callback_data="set_app_noti"),
        types.InlineKeyboardButton("❌ Set Rejected Noti", callback_data="set_rej_noti"),
        types.InlineKeyboardButton("⚠️ Set Spam Noti", callback_data="set_spm_noti"),
        types.InlineKeyboardButton("🚫 Set Banned Noti", callback_data="set_ban_noti"),
        types.InlineKeyboardButton("🚫 Ban User", callback_data="set_ban"),
        types.InlineKeyboardButton("✅ Unban User", callback_data="set_unban"),
        types.InlineKeyboardButton("📊 View Settings", callback_data="view_settings"),
        types.InlineKeyboardButton("🏠 Main Menu", callback_data="go_home"),
    )
    return markup


@bot.message_handler(commands=["start"])
def handle_start(message):
    user_id = message.from_user.id
    data = load_data()

    if user_id in data.get("banned_users", []):
        bot.send_message(message.chat.id, data.get("banned_noti", "🚫 သင်သည် ဤ Bot ကို အသုံးပြုခွင့် ပိတ်ပင်ခံထားရပါသည်။"))
        return

    user_states[user_id] = {}

    args = message.text.split()
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1].replace("ref_", "", 1))
            if referrer_id != user_id:
                refs = data.setdefault("referrals", {})
                user_refs = refs.setdefault(str(referrer_id), [])
                if user_id not in user_refs:
                    user_refs.append(user_id)
                    save_data(data)
        except ValueError:
            pass

    welcome_text = data.get("welcome_msg", "မင်္ဂလာပါ။ အောက်ပါ ခလုတ်များမှ တစ်ဆင့် အသုံးပြုလိုရာကို ရွေးချယ်ပါ။")
    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=get_main_menu(user_id),
    )


@bot.callback_query_handler(func=lambda call: call.data in {"go_home", "menu_ref", "menu_support"})
def general_menu_cb(call):
    user_id = call.from_user.id
    data = load_data()

    if user_id in data.get("banned_users", []):
        bot.answer_callback_query(call.id, data.get("banned_noti", "အသုံးပြုခွင့် ပိတ်ပင်ခံထားရပါသည်။"), show_alert=True)
        return

    try:
        if call.data == "go_home":
            welcome_text = data.get("welcome_msg", "မင်္ဂလာပါ။ အောက်ပါ ခလုတ်များမှ တစ်ဆင့် အသုံးပြုလိုရာကို ရွေးချယ်ပါ။")
            bot.edit_message_text(
                welcome_text,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=get_main_menu(user_id),
            )
        elif call.data == "menu_ref":
            ref_count = sum(1 for v in data.get("referrals", {}).values() if user_id in v)
            ref_link = f"{data.get('referral_link', '')}ref_{user_id}"
            txt = (
                "🎁 **သင့် Referral Link**\n"
                f"`{ref_link}`\n\n"
                f"👥 ဖိတ်ခေါ်ထားသူ စုစုပေါင်း: **{ref_count}**"
            )
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🏠 Main Menu", callback_data="go_home"))
            bot.edit_message_text(
                txt,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup,
                parse_mode="Markdown",
            )
        elif call.data == "menu_support":
            support_handle = data.get("support", "@mikef07")
            txt = f"💬 **Support**\nဆက်သွယ်ရန်: {support_handle}"
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🏠 Main Menu", callback_data="go_home"))
            bot.edit_message_text(
                txt,
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup,
                parse_mode="Markdown",
            )
    except Exception as e:
        print(f"general_menu_cb error: {e}")

    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "owner_menu")
def owner_menu_cb(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "Owner သာ အသုံးပြုနိုင်ပါသည်။", show_alert=True)
        return

    try:
        bot.edit_message_text(
            "⚙️ **Owner Control Panel**",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=get_owner_menu(),
            parse_mode="Markdown",
        )
    except Exception as e:
        print(f"owner_menu_cb error: {e}")

    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "view_settings")
def view_settings_cb(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "Owner သာ အသုံးပြုနိုင်ပါသည်။", show_alert=True)
        return

    data = load_data()
    txt = (
        "⚙️ **လက်ရှိ Settings များ**\n"
        f"• KPay: `{data['kpay_name']}` - `{data['kpay_no']}`\n"
        f"• Wave: `{data['wave_name']}` - `{data['wave_no']}`\n"
        f"• Pro Price: `{data['pro_price']}`\n"
        f"• VIP Price: `{data['vip_price']}`\n"
        f"• Support: `{data['support']}`\n"
        f"• Banned Users: `{len(data.get('banned_users', []))}`\n"
        f"• Welcome Msg: `{data.get('welcome_msg', '')[:50]}`\n"
        f"• Webhook: `{WEBHOOK_URL}`"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="owner_menu"))

    try:
        bot.edit_message_text(
            txt,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown",
        )
    except Exception as e:
        print(f"view_settings_cb error: {e}")

    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("set_"))
def handle_setting_start(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "Owner သာ အသုံးပြုနိုင်ပါသည်။", show_alert=True)
        return

    action = call.data
    user_states[call.from_user.id] = {"step": action}
    prompts = {
        "set_kpay": "KPay အမည် နှင့် ဖုန်းနံပါတ် ပို့ပေးပါ (ဥပမာ - `U Aye 09123456789`):",
        "set_wave": "WavePay အမည် နှင့် ဖုန်းနံပါတ် ပို့ပေးပါ (ဥပမာ - `U Aye 09123456789`):",
        "set_pro": "Pro Plan ဈေးနှုန်းအသစ် ပို့ပေးပါ (ဥပမာ - `15,000 MMK`):",
        "set_vip": "VIP Plan ဈေးနှုန်းအသစ် ပို့ပေးပါ (ဥပမာ - `30,000 MMK`):",
        "set_support": "Support Account အသစ် ပို့ပေးပါ (ဥပမာ - `@mikef07`):",
        "set_welcome": "Welcome Message အသစ်ကို ရေးပို့ပေးပါ:",
        "set_req_noti": (
            "Payment Request Notification စာသားအသစ် ပို့ပေးပါ။\n"
            "သုံးနိုင်သော စာသားများ - `{first_name}`, `{user_id}`, `{email}`, `{plan}`"
        ),
        "set_app_noti": (
            "Approved Notification စာသားအသစ် ပို့ပေးပါ။\n"
            "သုံးနိုင်သော စာသားများ - `{plan}`, `{email}`, `{days}`"
        ),
        "set_rej_noti": "Rejected Notification စာသားအသစ် ပို့ပေးပါ:",
        "set_spm_noti": "Spam Notification စာသားအသစ် ပို့ပေးပါ:",
        "set_ban_noti": "Banned User Notification စာသားအသစ် ပို့ပေးပါ:",
        "set_ban": "Ban လုပ်လိုသော Telegram User ID ကို ပို့ပေးပါ:",
        "set_unban": "Unban လုပ်လိုသော Telegram User ID ကို ပို့ပေးပါ:",
    }
    bot.answer_callback_query(call.id, "တန်ဖိုးအသစ်ကို ရိုက်ပို့ပေးပါ...", show_alert=False)
    bot.send_message(
        call.message.chat.id,
        prompts.get(action, "တန်ဖိုးအသစ်ကို ပို့ပေးပါ:"),
        parse_mode="Markdown",
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def handle_buy_plan(call):
    user_id = call.from_user.id
    data = load_data()

    if user_id in data.get("banned_users", []):
        bot.answer_callback_query(call.id, data.get("banned_noti", "အသုံးပြုခွင့် ပိတ်ပင်ခံထားရပါသည်။"), show_alert=True)
        return

    plan = call.data.split("_", 1)[1]
    price = data["pro_price"] if plan == "PRO" else data["vip_price"]
    user_states[user_id] = {"step": "awaiting_email", "plan": plan}
    txt = (
        f"💎 **{plan} Plan** ({price})\n\n"
        f"💳 KPay: `{data['kpay_name']}` (`{data['kpay_no']}`)\n"
        f"🌊 WavePay: `{data['wave_name']}` (`{data['wave_no']}`)\n\n"
        "အရင်ဆုံး သင့်ရဲ့ **Email လိပ်စာ** ကို ပို့ပေးပါ:"
    )
    bot.send_message(call.message.chat.id, txt, parse_mode="Markdown")
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith(("app_", "rej_", "spm_")))
def admin_actions(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "Admin သာ လုပ်ဆောင်နိုင်ပါသည်။", show_alert=True)
        return

    data = load_data()

    if call.data.startswith("app_"):
        req_id = call.data.split("_", 1)[1]
        req_info = pending_requests.get(req_id)
        if not req_info:
            bot.answer_callback_query(call.id, "တောင်းဆိုချက် သက်တမ်းကုန်သွားပါပြီ သို့မဟုတ် မတွေ့ပါ။", show_alert=True)
            return

        target_user = req_info["user_id"]
        plan = req_info["plan"]
        email = req_info["email"]
        days = 30

        ok, resp_text = update_web_subscription(email, plan, duration_days=days)
        if ok:
            pending_requests.pop(req_id, None)
            app_template = data.get(
                "approved_noti",
                "🎉 `{email}` အတွက် **{plan}** Plan ({days} ရက်) ကို အတည်ပြုပေးပြီးပါပြီ။",
            )
            try:
                msg_txt = app_template.format(email=email, plan=plan, days=days)
            except Exception:
                msg_txt = app_template
            try:
                bot.send_message(target_user, msg_txt, parse_mode="Markdown")
            except Exception as e:
                print(f"Notify user error: {e}")
            try:
                bot.edit_message_caption(
                    caption=(call.message.caption or "") + "\n\n✅ **ADMIN မှ အတည်ပြုပြီး**",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode="Markdown",
                )
            except Exception:
                pass
            bot.answer_callback_query(call.id, "အတည်ပြုပြီး Web နှင့် ချိတ်ဆက်ပြီးပါပြီ။")
        else:
            bot.send_message(
                call.message.chat.id,
                f"⚠️ **Web App ချိတ်ဆက်မှု မအောင်မြင်ပါ!**\nEmail: `{email}` | Plan: `{plan}`\nError: `{resp_text[:300]}`",
                parse_mode="Markdown",
            )
            bot.answer_callback_query(call.id, "Web Sync Error!", show_alert=True)

    elif call.data.startswith("rej_"):
        try:
            target_user = int(call.data.split("_", 1)[1])
        except ValueError:
            bot.answer_callback_query(call.id, "User ID မမှန်ကန်ပါ။", show_alert=True)
            return
        try:
            bot.send_message(
                target_user,
                data.get("rejected_noti", "❌ သင့်ရဲ့ ငွေပေးချေမှု တောင်းဆိုချက်ကို ပယ်ချလိုက်ပါသည်။"),
            )
        except Exception:
            pass
        try:
            bot.edit_message_caption(
                caption=(call.message.caption or "") + "\n\n❌ **ပယ်ချပြီး**",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="Markdown",
            )
        except Exception:
            pass
        bot.answer_callback_query(call.id, "ပယ်ချလိုက်ပါပြီ။")

    elif call.data.startswith("spm_"):
        try:
            target_user = int(call.data.split("_", 1)[1])
        except ValueError:
            bot.answer_callback_query(call.id, "User ID မမှန်ကန်ပါ။", show_alert=True)
            return
        spam_list = data.setdefault("spam_users", [])
        if target_user not in spam_list:
            spam_list.append(target_user)
            save_data(data)
        try:
            bot.send_message(
                target_user,
                data.get("spam_noti", "⚠️ သင့်အကောင့်ကို Spam အဖြစ် သတ်မှတ်လိုက်ပါသည်။"),
            )
        except Exception:
            pass
        try:
            bot.edit_message_caption(
                caption=(call.message.caption or "") + "\n\n⚠️ **SPAM အဖြစ် သတ်မှတ်ပြီး**",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="Markdown",
            )
        except Exception:
            pass
        bot.answer_callback_query(call.id, "Spam အဖြစ် သတ်မှတ်ပြီးပါပြီ။")


@bot.message_handler(content_types=["text", "photo"])
def handle_messages(message):
    user_id = message.from_user.id
    state = user_states.get(user_id, {})
    data = load_data()

    if user_id in data.get("banned_users", []) or user_id in data.get("spam_users", []):
        return

    if user_id == OWNER_ID and state.get("step", "").startswith("set_"):
        step = state["step"]
        val = (message.text or "").strip()

        if step == "set_kpay":
            parts = val.split()
            if len(parts) < 2:
                bot.send_message(message.chat.id, "❌ ပုံစံမှန်ရန် - `Name 09xxxxxxxxx`", parse_mode="Markdown")
                return
            data["kpay_name"], data["kpay_no"] = " ".join(parts[:-1]), parts[-1]
        elif step == "set_wave":
            parts = val.split()
            if len(parts) < 2:
                bot.send_message(message.chat.id, "❌ ပုံစံမှန်ရန် - `Name 09xxxxxxxxx`", parse_mode="Markdown")
                return
            data["wave_name"], data["wave_no"] = " ".join(parts[:-1]), parts[-1]
        elif step == "set_pro":
            if not val:
                bot.send_message(message.chat.id, "❌ Pro ဈေးနှုန်း မှန်ကန်စွာ ထည့်ပါ။")
                return
            data["pro_price"] = val
        elif step == "set_vip":
            if not val:
                bot.send_message(message.chat.id, "❌ VIP ဈေးနှုန်း မှန်ကန်စွာ ထည့်ပါ။")
                return
            data["vip_price"] = val
        elif step == "set_support":
            if not val:
                bot.send_message(message.chat.id, "❌ Support handle မှန်ကန်စွာ ထည့်ပါ။")
                return
            data["support"] = val
        elif step == "set_welcome":
            if not val:
                bot.send_message(message.chat.id, "❌ Welcome Message စာသား ထည့်ပါ။")
                return
            data["welcome_msg"] = val
        elif step == "set_req_noti":
            if not val:
                bot.send_message(message.chat.id, "❌ Notification စာသား ထည့်ပါ။")
                return
            data["request_noti"] = val
        elif step == "set_app_noti":
            if not val:
                bot.send_message(message.chat.id, "❌ Notification စာသား ထည့်ပါ။")
                return
            data["approved_noti"] = val
        elif step == "set_rej_noti":
            if not val:
                bot.send_message(message.chat.id, "❌ Notification စာသား ထည့်ပါ။")
                return
            data["rejected_noti"] = val
        elif step == "set_spm_noti":
            if not val:
                bot.send_message(message.chat.id, "❌ Notification စာသား ထည့်ပါ။")
                return
            data["spam_noti"] = val
        elif step == "set_ban_noti":
            if not val:
                bot.send_message(message.chat.id, "❌ Notification စာသား ထည့်ပါ။")
                return
            data["banned_noti"] = val
        elif step == "set_ban":
            try:
                uid = int(val)
                banned = data.setdefault("banned_users", [])
                if uid not in banned:
                    banned.append(uid)
            except ValueError:
                bot.send_message(message.chat.id, "❌ User ID မမှန်ကန်ပါ။")
 
