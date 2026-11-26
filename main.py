import json
import os
import threading
import flask
import requests
import telebot
from telebot import types

# ===== CONFIGURATION =====
BOT_TOKEN = "8909534863:AAG9F4ZwZRaT0RYovkaEKauvEtzM91-j2qk"
OWNER_ID = 8909534863
ADMIN_GROUP_ID = -1004448651266

WEBHOOK_URL = "https://aykrecaptool.lovable.app/api/public/subscription/update;"
WEBHOOK_SECRET = "MKivv5WQl1i5RhdumjWjcad6Pk7YqgRG96v1q72RQ4Qwwvad"

bot = telebot.TeleBot(BOT_TOKEN)
app = flask.Flask(__name__)

DATA_FILE = "bot_data.json"
user_states = {}  # { user_id: {'step': ..., 'plan': ..., 'email': ...} }


# ===== DATA STORAGE =====
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
                default_data.update(loaded)
                return default_data
        except Exception as e:
            print(f"Data load error: {e}")
    return default_data


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ===== WEBHOOK SUBSCRIPTION SYNC =====
def update_web_subscription(email, plan, duration_days=30):
    payload = {
        "email": email.strip().lower(),
        "plan": plan.strip().upper(),  # "PRO" or "VIP"
        "status": "ACTIVE",
        "durationDays": duration_days,
        "customDailyQuota": None,
        "customCharLimit": None,
    }
    headers = {
        "Content-Type": "application/json",
    }
    if WEBHOOK_SECRET:
        headers["x-webhook-secret"] = WEBHOOK_SECRET
        headers["Authorization"] = f"Bearer {WEBHOOK_SECRET}"

    try:
        res = requests.post(WEBHOOK_URL, json=payload, headers=headers, timeout=15)
        print(f"Webhook Status: {res.status_code} | Response: {res.text}")
        ok = res.status_code in (200, 201)
        return ok, res.text
    except Exception as e:
        print(f"Webhook error: {e}")
        return False, str(e)


# ===== MENUS =====
def get_main_menu(user_id=None):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("💎 Buy PRO", callback_data="buy_PRO"),
        types.InlineKeyboardButton("👑 Buy VIP", callback_data="buy_VIP"),
        types.InlineKeyboardButton("🎁 Referral", callback_data="menu_ref"),
        types.InlineKeyboardButton("💬 Support", callback_data="menu_support"),
    )
    if user_id == OWNER_ID:
        markup.add(
            types.InlineKeyboardButton("⚙️ Owner Menu", callback_data="owner_menu")
        )
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
    )
    return markup


# ===== START & BASIC HANDLERS =====
@bot.message_handler(commands=["start"])
def handle_start(message):
    user_id = message.from_user.id
    data = load_data()
    if user_id in data.get("banned_users", []):
        bot.send_message(message.chat.id, "🚫 You are banned from using this bot.")
        return

    args = message.text.split()
    if len(args) > 1:
        ref_code = args[1]
        if ref_code.startswith("ref_"):
            try:
                referrer_id = int(ref_code.replace("ref_", ""))
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


@bot.callback_query_handler(
    func=lambda call: call.data in ["go_home", "menu_ref", "menu_support"]
)
def general_menu_cb(call):
    user_id = call.from_user.id
    data = load_data()

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
            f"🎁 **Your Referral Link**\n"
            f"`{ref_link}`\n\n"
            f"👥 Total Referrals: **{ref_count}**"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("🏠 Main Menu", callback_data="go_home")
        )
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
        markup.add(
            types.InlineKeyboardButton("🏠 Main Menu", callback_data="go_home")
        )
        bot.edit_message_text(
            txt,
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown",
        )
    bot.answer_callback_query(call.id)


# ===== OWNER MENU & SETTINGS =====
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
        return
    data = load_data()
    txt = (
        f"⚙️ **Current Settings**\n"
        f"• KPay: `{data['kpay_name']}` - `{data['kpay_no']}`\n"
        f"• Wave: `{data['wave_name']}` - `{data['wave_no']}`\n"
        f"• Pro Price: `{data['pro_price']}`\n"
        f"• VIP Price: `{data['vip_price']}`\n"
        f"• Support: `{data['support']}`\n"
        f"• Banned Users: `{len(data.get('banned_users', []))}`\n"
        f"• Webhook: `{WEBHOOK_URL}`"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("⬅️ Back", callback_data="owner_menu")
    )
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
        return
    bot.answer_callback_query(call.id, "Enter value...", show_alert=False)
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
    bot.send_message(
        call.message.chat.id,
        prompts.get(action, "Send new value:"),
        parse_mode="Markdown",
    )


# ===== BUY FLOW & TEXT/PHOTO HANDLERS =====
@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def handle_buy_plan(call):
    plan = call.data.split("_", 1)[1]  # "PRO" or "VIP"
    data = load_data()
    price = data["pro_price"] if plan == "PRO" else data["vip_price"]
    user_states[call.from_user.id] = {"step": "awaiting_email", "plan": plan}

    txt = (
        f"💎 **{plan} Plan** ({price})\n\n"
        f"💳 KPay: `{data['kpay_name']}` (`{data['kpay_no']}`)\n"
        f"🌊 WavePay: `{data['wave_name']}` (`{data['wave_no']}`)\n\n"
        f"Please send your **Email address** first:"
    )
    bot.send_message(call.message.chat.id, txt, parse_mode="Markdown")
    bot.answer_callback_query(call.id)


@bot.message_handler(content_types=["text", "photo"])
def handle_messages(message):
    user_id = message.from_user.id
    state = user_states.get(user_id, {})
    data = load_data()

    if user_id in data.get("banned_users", []) or user_id in data.get(
        "spam_users", []
    ):
        return

    # Owner setting updates
    if user_id == OWNER_ID and state.get("step", "").startswith("set_"):
        step = state["step"]
        val = (message.text or "").strip()
        if step == "set_kpay":
            parts = val.split()
            if len(parts) < 2:
                bot.send_message(
                    message.chat.id, "❌ Format: `Name 09xxxxxxxxx`", parse_mode="Markdown"
                )
                return
            data["kpay_name"] = " ".join(parts[:-1])
            data["kpay_no"] = parts[-1]
        elif step == "set_wave":
            parts = val.split()
            if len(parts) < 2:
                bot.send_message(
                    message.chat.id, "❌ Format: `Name 09xxxxxxxxx`", parse_mode="Markdown"
                )
                return
            data["wave_name"] = " ".join(parts[:-1])
            data["wave_no"] = parts[-1]
        elif step == "set_pro":
            data["pro_price"] = val
        elif step == "set_vip":
            data["vip_price"] = val
        elif step == "set_support":
            data["support"] = val
        elif step == "set_ban":
            try:
                uid = int(val)
                if uid not in data["banned_users"]:
                    data["banned_users"].append(uid)
            except ValueError:
                bot.send_message(message.chat.id, "❌ Invalid User ID.")
                return
        elif step == "set_unban":
            try:
                uid = int(val)
                if uid in data["banned_users"]:
                    data["banned_users"].remove(uid)
            except ValueError:
                bot.send_message(message.chat.id, "❌ Invalid User ID.")
                return

        save_data(data)
        user_states[user_id] = {}
        bot.send_message(
            message.chat.id,
            "✅ Updated!",
            reply_markup=get_main_menu(user_id),
        )
        return

    # Step 1: Awaiting email
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

    # Step 2: Awaiting payment slip photo
    if state.get("step") == "awaiting_slip" and message.photo:
        file_id = message.photo[-1].file_id
        plan = state.get("plan", "PRO")
        email = state.get("email", "")

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton(
                "✅ Approve", callback_data=f"app_{plan}_{user_id}_{email}"
            ),
            types.InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user_id}"),
        )
        markup.add(
            types.InlineKeyboardButton("⚠️ Spam", callback_data=f"spm_{user_id}")
        )

        first_name = message.from_user.first_name or "User"
        caption = (
            f"🧾 **New Payment Request**\n"
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
        return


# ===== ADMIN GROUP CALLBACKS =====
@bot.callback_query_handler(
    func=lambda call: call.data.startswith(("app_", "rej_", "spm_"))
)
def admin_actions(call):
    if call.from_user.id != OWNER_ID:
        bot.answer_callback_query(call.id, "Admin only!", show_alert=True)
        return

    data = load_data()

    if call.data.startswith("app_"):
        parts = call.data.split("_", 3)
        if len(parts) < 4:
            bot.answer_callback_query(call.id, "Invalid data", show_alert=True)
            return
        _, plan, target_str, email = parts
        target_user = int(target_str)

        ok, resp_text = update_web_subscription(email, plan, duration_days=30)
        if ok:
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
        target_user = int(call.data.split("_", 1)[1])
        try:
            bot.send_message(
                target_user, "❌ Your payment request was rejected. Contact support."
            )
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
        target_user = int(call.data.split("_", 1)[1])
        if target_user not in data.get("spam_users", []):
            data.setdefault("spam_users", []).append(target_user)
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


# ===== FLASK WEBHOOK ENDPOINT =====
@app.route("/api/public/subscription/update", methods=["POST"])
def subscription_webhook():
    if WEBHOOK_SECRET:
        provided_secret = flask.request.headers.get("x-webhook-secret", "")
        auth_header = flask.request.headers.get("Authorization", "")
        valid = (provided_secret == WEBHOOK_SECRET) or (
            auth_header == f"Bearer {WEBHOOK_SECRET}"
        )
        if not valid:
            return flask.jsonify({"ok": False, "error": "Unauthorized"}), 401

    payload = flask.request.get_json(silent=True) or {}
    # Acknowledge immediately so the sender never times out; run heavy work in background
    threading.Thread(
        target=handle_incoming_webhook_payload, args=(payload,), daemon=True
    ).start()
    return flask.jsonify({"ok": True, "received": True}), 200


def handle_incoming_webhook_payload(payload):
    print("Received incoming webhook payload:", payload)


def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


# ===== BOT RUNNING =====
if __name__ == "__main__":
    print("Starting Flask webhook server...")
    threading.Thread(target=run_flask, daemon=True).start()
    print("Starting Telegram bot...")
    print(f"Target Webhook: {WEBHOOK_URL}")
    bot.infinity_polling(skip_pending=True)
