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
WEBHOOK_URL = "https://aykrecaptool.lovable.app/api/public/subscription/update"
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
        bot.send_message(message.chat.id, "🚫 You are banned from using this bot.")
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

    bot.send_message(
        message.chat.id,
        "Welcome! Choose an option below:",
        reply_markup=get_main_menu(user_id),
    )


@bot.callback_query_handler(func=lambda call: call.data in ["go_home", "menu_ref", "menu_support"])
def general_menu_cb(call):
    user_id = call.from_user.id
    data = load_data()

    if user_id in data.get("banned_users", []):
        bot.answer_callback_query(call.id, "You are banned.", show_alert=True)
        return

    if call.data == "go_home":
        bot.edit_message_text(
            "Welcome! Choose an option below:",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=get_main_menu(user_id),
        )
    elif call.data == "menu_ref":
        ref_count = sum(1 for v in data.get("referrals", {}).values() if user_id in v)
        ref_link = f"{data.get('referral_link', '')}ref_{user_id}"
        txt = (
            "🎁 **Your Referral Link**\n"
            f"`{ref_link}`\n\n"
            f"👥 Total Referrals: **{ref_count}**"
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
        txt = f"💬 **Support**\nContact: {support_handle}"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🏠 Main Menu", callback_data="go_home"))
        bot.edit_message_text(
            txt,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown",
        )

    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "owner_menu")
def owner_menu_cb(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "Owner only!", show_alert=True)
        return

    bot.edit_message_text(
        "⚙️ **Owner Control Panel**",
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=get_owner_menu(),
        parse_mode="Markdown",
    )
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data == "view_settings")
def view_settings_cb(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "Owner only!", show_alert=True)
        return

    data = load_data()
    txt = (
        "⚙️ **Current Settings**\n"
        f"• KPay: `{data['kpay_name']}` - `{data['kpay_no']}`\n"
        f"• Wave: `{data['wave_name']}` - `{data['wave_no']}`\n"
        f"• Pro Price: `{data['pro_price']}`\n"
        f"• VIP Price: `{data['vip_price']}`\n"
        f"• Support: `{data['support']}`\n"
        f"• Banned Users: `{len(data.get('banned_users', []))}`\n"
        f"• Webhook: `{WEBHOOK_URL}`"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="owner_menu"))
    bot.edit_message_text(
        txt,
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup,
        parse_mode="Markdown",
    )
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda call: call.data.startswith("set_"))
def handle_setting_start(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "Owner only!", show_alert=True)
        return

    action = call.data
    user_states[call.from_user.id] = {"step": action}
    prompts = {
        "set_kpay": "Send KPay Name and Number (e.g. `U Aye 09123456789`):",
        "set_wave": "Send WavePay Name and Number (e.g. `U Aye 09123456789`):",
        "set_pro": "Send new Pro price (e.g. `15,000 MMK`):",
        "set_vip": "Send new VIP price (e.g. `30,000 MMK`):",
        "set_support": "Send new Support handle (e.g. `@mikef07`):",
        "set_ban": "Send Telegram User ID to ban:",
        "set_unban": "Send Telegram User ID to unban:",
    }
    bot.answer_callback_query(call.id, "Enter value...", show_alert=False)
    bot.send_message(
        call.message.chat.id,
        prompts.get(action, "Send new value:"),
        parse_mode="Markdown",
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def handle_buy_plan(call):
    user_id = call.from_user.id
    data = load_data()

    if user_id in data.get("banned_users", []):
        bot.answer_callback_query(call.id, "You are banned.", show_alert=True)
        return

    plan = call.data.split("_", 1)[1]
    price = data["pro_price"] if plan == "PRO" else data["vip_price"]
    user_states[user_id] = {"step": "awaiting_email", "plan": plan}
    txt = (
        f"💎 **{plan} Plan** ({price})\n\n"
        f"💳 KPay: `{data['kpay_name']}` (`{data['kpay_no']}`)\n"
        f"🌊 WavePay: `{data['wave_name']}` (`{data['wave_no']}`)\n\n"
        "Please send your **Email address** first:"
    )
    bot.send_message(call.message.chat.id, txt, parse_mode="Markdown")
    bot.answer_callback_query(call.id)


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
                bot.send_message(message.chat.id, "❌ Format: `Name 09xxxxxxxxx`", parse_mode="Markdown")
                return
            data["kpay_name"], data["kpay_no"] = " ".join(parts[:-1]), parts[-1]
        elif step == "set_wave":
            parts = val.split()
            if len(parts) < 2:
                bot.send_message(message.chat.id, "❌ Format: `Name 09xxxxxxxxx`", parse_mode="Markdown")
                return
            data["wave_name"], data["wave_no"] = " ".join(parts[:-1]), parts[-1]
        elif step == "set_pro":
            if not val:
                bot.send_message(message.chat.id, "❌ Please enter a valid Pro price.")
                return
            data["pro_price"] = val
        elif step == "set_vip":
            if not val:
                bot.send_message(message.chat.id, "❌ Please enter a valid VIP price.")
                return
            data["vip_price"] = val
        elif step == "set_support":
            if not val:
                bot.send_message(message.chat.id, "❌ Please enter a valid Support handle.")
                return
            data["support"] = val
        elif step == "set_ban":
            try:
                uid = int(val)
                banned = data.setdefault("banned_users", [])
                if uid not in banned:
                    banned.append(uid)
            except ValueError:
                bot.send_message(message.chat.id, "❌ Invalid User ID.")
                return
        elif step == "set_unban":
            try:
                uid = int(val)
                banned = data.setdefault("banned_users", [])
                if uid in banned:
                    banned.remove(uid)
            except ValueError:
                bot.send_message(message.chat.id, "❌ Invalid User ID.")
                return

        save_data(data)
        user_states[user_id] = {}
        bot.send_message(message.chat.id, "✅ Updated!", reply_markup=get_main_menu(user_id))
        return

    if state.get("step") == "awaiting_email" and message.text:
        email = message.text.strip().lower()
        if "@" not in email or "." not in email.split("@")[-1]:
            bot.send_message(message.chat.id, "❌ Please enter a valid email address.")
            return
        state["email"] = email
        state["step"] = "awaiting_slip"
        user_states[user_id] = state
        bot.send_message(
            message.chat.id,
            "✅ Email saved! Now send a **screenshot/photo** of your payment slip:",
            parse_mode="Markdown",
        )
        return

    if state.get("step") == "awaiting_slip" and message.photo:
        file_id = message.photo[-1].file_id
        plan = state.get("plan", "PRO")
        email = state.get("email", "")
        req_id = f"{user_id}_{message.message_id}"
        pending_requests[req_id] = {
            "user_id": user_id,
            "plan": plan,
            "email": email,
        }

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ Approve", callback_data=f"app_{req_id}"),
            types.InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user_id}"),
        )
        markup.add(types.InlineKeyboardButton("⚠️ Spam", callback_data=f"spm_{user_id}"))

        first_name = message.from_user.first_name or "User"
        caption = (
            "🧾 **New Payment Request**\n"
            f"👤 User: `{first_name}` (`{user_id}`)\n"
            f"📧 Email: `{email}`\n"
            f"💎 Plan: **{plan}**"
        )
        bot.send_photo(
            ADMIN_GROUP_ID,
            file_id,
            caption=caption,
            reply_markup=markup,
            parse_mode="Markdown",
        )
        user_states[user_id] = {}
        bot.send_message(
            message.chat.id,
            "✅ Payment slip sent to admin. Please wait for approval.",
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith(("app_", "rej_", "spm_")))
def admin_actions(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "Admin only!", show_alert=True)
        return

    data = load_data()

    if call.data.startswith("app_"):
        req_id = call.data.split("_", 1)[1]
        req_info = pending_requests.get(req_id)
        if not req_info:
            bot.answer_callback_query(call.id, "Request expired or not found.", show_alert=True)
            return

        target_user = req_info["user_id"]
        plan = req_info["plan"]
        email = req_info["email"]

        ok, resp_text = update_web_subscription(email, plan, duration_days=30)
        if ok:
            pending_requests.pop(req_id, None)
            try:
                bot.send_message(
                    target_user,
                    f"🎉 Your **{plan}** plan (30 days) is approved for `{email}`! Please refresh the web app.",
                    parse_mode="Markdown",
                )
            except Exception as e:
                print(f"Notify user error: {e}")
            try:
                bot.edit_message_caption(
                    caption=(call.message.caption or "") + "\n\n✅ **APPROVED BY ADMIN**",
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    parse_mode="Markdown",
                )
            except Exception:
                pass
            bot.answer_callback_query(call.id, "Approved & Synced!")
        else:
            bot.send_message(
                call.message.chat.id,
                f"⚠️ **Web App Sync Failed!**\nEmail: `{email}` | Plan: `{plan}`\nError: `{resp_text[:300]}`",
                parse_mode="Markdown",
            )
            bot.answer_callback_query(call.id, "Web Sync Error!", show_alert=True)

    elif call.data.startswith("rej_"):
        try:
            target_user = int(call.data.split("_", 1)[1])
        except ValueError:
            bot.answer_callback_query(call.id, "Invalid user", show_alert=True)
            return
        try:
            bot.send_message(target_user, "❌ Your payment request was rejected. Contact support.")
        except Exception:
            pass
        try:
            bot.edit_message_caption(
                caption=(call.message.caption or "") + "\n\n❌ **REJECTED**",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="Markdown",
            )
        except Exception:
            pass
        bot.answer_callback_query(call.id, "Rejected")

    elif call.data.startswith("spm_"):
        try:
            target_user = int(call.data.split("_", 1)[1])
        except ValueError:
            bot.answer_callback_query(call.id, "Invalid user", show_alert=True)
            return
        spam_list = data.setdefault("spam_users", [])
        if target_user not in spam_list:
            spam_list.append(target_user)
            save_data(data)
        try:
            bot.send_message(target_user, "⚠️ You have been marked as spam.")
        except Exception:
            pass
        try:
            bot.edit_message_caption(
                caption=(call.message.caption or "") + "\n\n⚠️ **MARKED AS SPAM**",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="Markdown",
            )
        except Exception:
            pass
        bot.answer_callback_query(call.id, "Marked as spam")


@app.route("/api/public/subscription/update", methods=["POST"])
def subscription_webhook():
    if WEBHOOK_SECRET:
        provided_secret = flask.request.headers.get("x-webhook-secret", "")
        auth_header = flask.request.headers.get("Authorization", "")
        if not ((provided_secret == WEBHOOK_SECRET) or (auth_header == f"Bearer {WEBHOOK_SECRET}")):
            return flask.jsonify({"ok": False, "error": "Unauthorized"}), 401
    payload = flask.request.get_json(silent=True) or {}
    threading.Thread(target=handle_incoming_webhook_payload, args=(payload,), daemon=True).start()
    return flask.jsonify({"ok": True, "received": True}), 200


def handle_incoming_webhook_payload(payload):
    print("Received incoming webhook payload:", payload)


def run_flask():
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False,
        use_reloader=False,
    )


if __name__ == "__main__":
    print("Starting Flask webhook server...")
    threading.Thread(target=run_flask, daemon=True).start()
    print("Starting Telegram bot...")
    print(f"Target Webhook: {WEBHOOK_URL}")
    bot.infinity_polling(skip_pending=True, timeout=25, long_polling_timeout=20)
                
