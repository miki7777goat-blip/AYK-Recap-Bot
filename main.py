from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
import threading
from supabase import Client, create_client
import telebot
from telebot import types

# ==========================================
# 1. ENVIRONMENT VARIABLES & SETUP
# ==========================================
BOT_TOKEN = os.environ.get(
    "BOT_TOKEN", "8909534863:AAEcK211jGacRR_e4mUZQmKqxeH4tVAxqWU"
)
OWNER_IDS = {8415289516}
ADMIN_GROUP_ID = int(os.environ.get("ADMIN_GROUP_ID", "-1004448651266"))
SUPPORT_TOPIC_ID = int(os.environ.get("SUPPORT_TOPIC_ID", "99"))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

WEBHOOK_URL = os.environ.get(
    "WEBHOOK_URL",
    "https://aykrecaptool.lovable.app/api/public-bot-webhook",
)
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
PORT = int(os.environ.get("PORT", "10000"))

supabase: Client | None = (
    create_client(SUPABASE_URL, SUPABASE_KEY)
    if SUPABASE_URL and SUPABASE_KEY
    else None
)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# Editing states:
# EDITING_STATE[user_id] = {"target": "main_config" | "settings", "key": "..."}
EDITING_STATE: dict[int, dict[str, str]] = {}
BROADCAST_WAITING: set[int] = set()
SLIP_WAITING: set[int] = set()

# ==========================================
# 2. DEFAULT DATA & SUPABASE CONFIG HELPERS
# ==========================================
DEFAULT_SETTINGS = {
    "kpay_phone": "09xxxxxxxxx",
    "kpay_name": "Owner Name",
    "wave_phone": "09xxxxxxxxx",
    "wave_name": "Owner Name",
    "pro_price": "3,000 Ks / 1 Month",
    "vip_price": "25,000 Ks / 1 Month",
    "support_username": "mikef07",
    "referral_discount": 250,
}

DEFAULT_MESSAGES = {
    "welcome": "👋 မင်္ဂလာပါ {first_name}",
    "ref_info": "👥 Referral အချက်အလက်\nTotal Referrals: {count}",
    "ref_notify": "🔔 Referral အသစ်ဝင်လာပါပြီ: {user}",
    "approve_user": "✅ သင့်အကောင့်ကို အတည်ပြုပြီးပါပြီ။",
    "reject_user": "❌ သင့်တောင်းဆိုချက်ကို ငြင်းပယ်လိုက်ပါသည်။",
    "slip_submitted": "📩 Slip ပေးပို့ပြီးပါပြီ။ Admin မှ စစ်ဆေးပေးပါမည်။",
}

DEFAULT_DATA = {
    "settings": DEFAULT_SETTINGS,
    "messages": DEFAULT_MESSAGES,
    "known_users": [],
    "referrals": {},
    "referral_counts": {},
}

FIELD_MAP = {
    "edit_welcome": "welcome_message",
    "edit_ref_info": "ref_info_msg",
    "edit_ref_notify": "ref_notify_msg",
    "edit_approve_msg": "approve_msg",
    "edit_reject_msg": "reject_msg",
    "edit_slip_msg": "slip_msg",
    "edit_custom_notices": "custom_notices",
}

SETTING_BUTTON_MAP = {
    "edit_kpay": "kpay_phone",
    "edit_wave": "wave_phone",
    "edit_pro_price": "pro_price",
    "edit_vip_price": "vip_price",
    "edit_ref_discount": "referral_discount",
    "edit_support": "support_username",
    "edit_custom_notices": "custom_notices"
}


def get_main_config() -> dict:
    """Fetch 'data' dictionary from 'bot_config' table where id == 'main_config'."""
    if not supabase:
        return {}

    res = (
        supabase.table("bot_config")
        .select("data")
        .eq("id", "main_config")
        .single()
        .execute()
    )
    raw = res.data.get("data") if res.data else None

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


def save_main_config(updated_data: dict) -> dict:
    """Persist full config dictionary to Supabase bot_config (main_config)."""
    if not supabase:
        return updated_data

    res = (
        supabase.table("bot_config")
        .select("data")
        .eq("id", "main_config")
        .single()
        .execute()
    )
    existing_raw = res.data.get("data") if res.data else None
    payload_value = (
        json.dumps(updated_data, ensure_ascii=False)
        if isinstance(existing_raw, str)
        else updated_data
    )

    supabase.table("bot_config").update({"data": payload_value}).eq(
        "id", "main_config"
    ).execute()
    return updated_data


def update_main_config_field(field_key: str, new_value) -> dict:
    """Update a top-level key in 'main_config'."""
    current_data = get_main_config()
    current_data[field_key] = new_value
    return save_main_config(current_data)


def update_nested_setting(setting_key: str, new_value) -> dict:
    """Update a key inside data['settings'] in 'main_config'."""
    current_data = get_main_config()
    settings = current_data.get("settings")
    if not isinstance(settings, dict):
        settings = dict(DEFAULT_SETTINGS)
    if setting_key == "referral_discount":
        try:
            new_value = int(str(new_value).strip())
        except ValueError:
            pass
    settings[setting_key] = new_value
    current_data["settings"] = settings
    return save_main_config(current_data)


def load_data() -> dict:
    """Load merged data combining defaults and Supabase main_config."""
    cfg = get_main_config()
    merged = json.loads(json.dumps(DEFAULT_DATA))
    if isinstance(cfg, dict):
        if isinstance(cfg.get("settings"), dict):
            merged["settings"].update(cfg["settings"])
        if isinstance(cfg.get("messages"), dict):
            merged["messages"].update(cfg["messages"])
        for key in ("known_users", "referrals", "referral_counts"):
            if key in cfg:
                merged[key] = cfg[key]
    return merged


def register_user_and_referral(user_id: int, start_payload: str = ""):
    """Track known users and optional referral ID."""
    cfg = get_main_config()
    known_users = cfg.get("known_users")
    if not isinstance(known_users, list):
        known_users = []

    is_new_user = user_id not in known_users
    if is_new_user:
        known_users.append(user_id)
        cfg["known_users"] = known_users

    referrals = cfg.get("referrals")
    if not isinstance(referrals, dict):
        referrals = {}

    ref_counts = cfg.get("referral_counts")
    if not isinstance(ref_counts, dict):
        ref_counts = {}

    notified_referrer_id = None
    if start_payload and start_payload.isdigit():
        referrer_id = int(start_payload)
        str_uid = str(user_id)
        str_ref = str(referrer_id)
        if referrer_id != user_id and str_uid not in referrals:
            referrals[str_uid] = referrer_id
            ref_counts[str_ref] = int(ref_counts.get(str_ref, 0)) + 1
            cfg["referrals"] = referrals
            cfg["referral_counts"] = ref_counts
            notified_referrer_id = referrer_id

    if is_new_user or notified_referrer_id:
        save_main_config(cfg)

    return notified_referrer_id
# ==========================================
# 3. OWNER MENU KEYBOARD BUILDER
# ==========================================
def get_extra_owner_rows() -> list[list[types.InlineKeyboardButton]]:
    """Return additional inline keyboard rows for Owner Menu."""
    return [
        [
            types.InlineKeyboardButton(
                "👋 Edit Welcome", callback_data="edit_welcome"
            ),
            types.InlineKeyboardButton(
                "👥 Edit Ref Info Msg", callback_data="edit_ref_info"
            ),
        ],
        [
            types.InlineKeyboardButton(
                "🔔 Edit Ref Notify", callback_data="edit_ref_notify"
            ),
            types.InlineKeyboardButton(
                "✅ Edit Approve Msg", callback_data="edit_approve_msg"
            ),
        ],
        [
            types.InlineKeyboardButton(
                "❌ Edit Reject Msg", callback_data="edit_reject_msg"
            ),
            types.InlineKeyboardButton(
                "📩 Edit Slip Msg", callback_data="edit_slip_msg"
            ),
        ],
        [
            types.InlineKeyboardButton(
                "📢 Custom Notices", callback_data="edit_custom_notices"
            ),
        ],
    ]

            

def build_owner_keyboard(
    existing_rows: list[list[types.InlineKeyboardButton]] | None = None,
) -> types.InlineKeyboardMarkup:
    """Merge existing owner menu rows with extra Supabase config rows."""
    markup = types.InlineKeyboardMarkup()
    if existing_rows:
        for row in existing_rows:
            markup.row(*row)
    for row in get_extra_owner_rows():
        markup.row(*row)
    return markup


# ==========================================
# 4. BOT HANDLERS (USER, SLIP & ADMIN)
# ==========================================
@bot.message_handler(commands=["start"])
def handle_start(message: types.Message):
    parts = message.text.split(maxsplit=1)
    payload = parts[1].strip() if len(parts) > 1 else ""
    referrer_id = register_user_and_referral(message.from_user.id, payload)

    cfg = get_main_config()
    data = load_data()
    first_name = message.from_user.first_name or ""

    if referrer_id:
        notify_template = cfg.get("ref_notify_msg") or data["messages"].get(
            "ref_notify", "🔔 Referral အသစ်ဝင်လာပါပြီ: {user}"
        )
        try:
            bot.send_message(
                referrer_id,
                notify_template.format(
                    user=first_name or str(message.from_user.id),
                    first_name=first_name,
                ),
            )
        except Exception:
            pass

    custom_welcome = cfg.get("welcome_message")
    if custom_welcome:
        text = (
            custom_welcome.format(first_name=first_name)
            if "{first_name}" in custom_welcome
            else custom_welcome
        )
    else:
        default_welcome = data["messages"].get(
            "welcome", "👋 မင်္ဂလာပါ {first_name}"
        )
        text = default_welcome.format(first_name=first_name)

    custom_notices = cfg.get("custom_notices")
    if custom_notices:
        text = f"{text}\n\n📢 <b>Notice:</b>\n{custom_notices}"

    bot.reply_to(message, text)


@bot.message_handler(commands=["ref"])
def handle_ref_info(message: types.Message):
    cfg = get_main_config()
    data = load_data()
    uid_str = str(message.from_user.id)
    count = int(data.get("referral_counts", {}).get(uid_str, 0))
    discount = data["settings"].get("referral_discount", 250)
    bot_username = bot.get_me().username or ""
    ref_link = f"https://t.me/{bot_username}?start={message.from_user.id}"

    template = cfg.get("ref_info_msg") or data["messages"].get(
        "ref_info", "👥 Referral အချက်အလက်\nTotal Referrals: {count}"
    )
    msg = template.format(
        count=count, discount=discount, link=ref_link, user_id=message.from_user.id
    )
    if "{link}" not in template:
        msg = f"{msg}\n🔗 Link: <code>{ref_link}</code>\n🎁 Discount: {discount} Ks"
    bot.reply_to(message, msg)


@bot.message_handler(commands=["slip"])
def handle_slip_command(message: types.Message):
    SLIP_WAITING.add(message.from_user.id)
    data = load_data()
    s = data["settings"]
    bot.reply_to(
        message,
        f"💳 <b>Payment Info</b>\n"
        f"• KPay: <code>{s.get('kpay_phone')}</code> ({s.get('kpay_name')})\n"
        f"• Wave: <code>{s.get('wave_phone')}</code> ({s.get('wave_name')})\n"
        f"• Pro: {s.get('pro_price')} | VIP: {s.get('vip_price')}\n\n"
        f"📸 Slip ပုံ (သို့မဟုတ် စာသား) ပို့ပေးပါ။ (/cancel ဖြင့် ပယ်ဖျက်နိုင်သည်)",
    )


@bot.message_handler(
    func=lambda m: m.from_user.id in SLIP_WAITING,
    content_types=["photo", "text", "document"],
)
def handle_slip_submission(message: types.Message):
    if message.text and message.text.strip() == "/cancel":
        SLIP_WAITING.discard(message.from_user.id)
        bot.reply_to(message, "❌ Slip ပေးပို့ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီ။")
        return

    SLIP_WAITING.discard(message.from_user.id)
    cfg = get_main_config()
    data = load_data()

    slip_reply = cfg.get("slip_msg") or data["messages"].get(
        "slip_submitted", "📩 Slip ပေးပို့ပြီးပါပြီ။ Admin မှ စစ်ဆေးပေးပါမည်။"
    )
    bot.reply_to(message, slip_reply)

    user = message.from_user
    user_line = f"• User: {user.first_name or ''} (<code>{user.id}</code>)"
    if user.username:
        user_line += f"\n• Username: @{user.username}"
    caption = f"🧾 <b>New Payment Slip</b>\n{user_line}"

    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton(
            "✅ Approve", callback_data=f"approve_user:{user.id}"
        ),
        types.InlineKeyboardButton(
            "❌ Reject", callback_data=f"reject_user:{user.id}"
        ),
    )

    try:
        if message.photo:
            file_id = message.photo[-1].file_id
            bot.send_photo(
                ADMIN_GROUP_ID,
                file_id,
                caption=caption,
                message_thread_id=SUPPORT_TOPIC_ID,
                reply_markup=markup,
            )
        else:
            extra_text = message.text or "[Attachment]"
            bot.send_message(
                ADMIN_GROUP_ID,
                f"{caption}\n• Detail: {extra_text}",
                message_thread_id=SUPPORT_TOPIC_ID,
                reply_markup=markup,
            )
    except Exception as e:
        print("Error forwarding slip to admin group:", e)


@bot.message_handler(commands=["admin", "owner"])
def handle_owner_menu(message: types.Message):
    if message.from_user.id not in OWNER_IDS:
        return

    existing_rows = [
        [
            types.InlineKeyboardButton("Edit KPay", callback_data="edit_kpay"),
            types.InlineKeyboardButton("Edit Wave", callback_data="edit_wave"),
        ],
        [
            types.InlineKeyboardButton(
                "Edit Pro Price", callback_data="edit_pro_price"
            ),
            types.InlineKeyboardButton(
                "Edit VIP Price", callback_data="edit_vip_price"
            ),
        ],
        [
            types.InlineKeyboardButton(
                "Edit Ref Discount", callback_data="edit_ref_discount"
            ),
            types.InlineKeyboardButton(
                "Edit Support", callback_data="edit_support"
            ),
        ],
        [
            types.InlineKeyboardButton(
                "📢 Broadcast", callback_data="send_broadcast"
            ),
            types.InlineKeyboardButton(
                "View Settings", callback_data="view_settings"
            ),
        ],
    ]

    markup = build_owner_keyboard(existing_rows)
    bot.send_message(
        message.chat.id,
        "⚙️ <b>Owner Control Panel</b>",
        reply_markup=markup,
    )
# ==========================================
# 5. CALLBACKS, BROADCAST & TEXT INPUT
# ==========================================
@bot.callback_query_handler(
    func=lambda call: call.data.startswith(("approve_user:", "reject_user:"))
    and call.from_user.id in OWNER_IDS
)
def handle_approve_reject_callback(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    action, target_uid_str = call.data.split(":", 1)
    target_uid = int(target_uid_str)

    cfg = get_main_config()
    data = load_data()

    if action == "approve_user":
        msg_to_user = cfg.get("approve_msg") or data["messages"].get(
            "approve_user", "✅ သင့်အကောင့်ကို အတည်ပြုပြီးပါပြီ။"
        )
        status_label = "✅ Approved"
    else:
        msg_to_user = cfg.get("reject_msg") or data["messages"].get(
            "reject_user", "❌ သင့်တောင်းဆိုချက်ကို ငြင်းပယ်လိုက်ပါသည်။"
        )
        status_label = "❌ Rejected"

    try:
        bot.send_message(target_uid, msg_to_user)
    except Exception:
        pass

    try:
        bot.edit_message_reply_markup(
            call.message.chat.id, call.message.message_id, reply_markup=None
        )
        bot.send_message(
            call.message.chat.id,
            f"{status_label} for user <code>{target_uid}</code>",
            message_thread_id=call.message.message_thread_id,
        )
    except Exception:
        pass


@bot.callback_query_handler(
    func=lambda call: call.data in FIELD_MAP and call.from_user.id in OWNER_IDS
)
def handle_extra_owner_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    field_key = FIELD_MAP[call.data]

    EDITING_STATE[user_id] = {"target": "main_config", "key": field_key}
    bot.answer_callback_query(call.id)

    cfg = get_main_config()
    current_val = cfg.get(field_key, "(သတ်မှတ်ထားခြင်း မရှိသေးပါ)")

    bot.send_message(
        call.message.chat.id,
        f"✏️ <b>{field_key}</b> ကို ပြင်ဆင်ရန် စာသားအသစ် ရိုက်ပို့ပေးပါ။\n"
        f"(ပယ်ဖျက်လိုပါက /cancel ဟု ပို့ပါ)\n\n"
        f"<b>လက်ရှိ စာသား:</b>\n{current_val}",
    )


@bot.callback_query_handler(
    func=lambda call: call.data in SETTING_BUTTON_MAP
    and call.from_user.id in OWNER_IDS
)
def handle_setting_edit_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    setting_key = SETTING_BUTTON_MAP[call.data]
    EDITING_STATE[user_id] = {"target": "settings", "key": setting_key}
    bot.answer_callback_query(call.id)

    data = load_data()
    current_val = data["settings"].get(setting_key, "")
    bot.send_message(
        call.message.chat.id,
        f"⚙️ <b>{setting_key}</b> အတွက် တန်ဖိုးအသစ် ရိုက်ပို့ပေးပါ။\n"
        f"(ပယ်ဖျက်လိုပါက /cancel ဟု ပို့ပါ)\n\n"
        f"<b>လက်ရှိ တန်ဖိုး:</b> <code>{current_val}</code>",
    )


@bot.callback_query_handler(
    func=lambda call: call.data in ("send_broadcast", "view_settings")
    and call.from_user.id in OWNER_IDS
)
def handle_other_owner_callbacks(call: types.CallbackQuery):
    bot.answer_callback_query(call.id)
    if call.data == "send_broadcast":
        BROADCAST_WAITING.add(call.from_user.id)
        bot.send_message(
            call.message.chat.id,
            "📢 User များအားလုံးထံ ပို့လိုသော Broadcast စာသား ရိုက်ပို့ပေးပါ။\n"
            "(ပယ်ဖျက်လိုပါက /cancel ဟု ပို့ပါ)",
        )
    elif call.data == "view_settings":
        cfg = get_main_config()
        merged = load_data()
        bot.send_message(
            call.message.chat.id,
            f"📋 <b>Current Merged Config:</b>\n"
            f"<pre>{json.dumps({'settings': merged['settings'], 'main_config': cfg}, ensure_ascii=False, indent=2)}</pre>",
        )


@bot.message_handler(
    commands=["cancel"],
    func=lambda m: m.from_user.id in EDITING_STATE
    or m.from_user.id in BROADCAST_WAITING
    or m.from_user.id in SLIP_WAITING,
)
def handle_cancel_any(message: types.Message):
    uid = message.from_user.id
    EDITING_STATE.pop(uid, None)
    BROADCAST_WAITING.discard(uid)
    SLIP_WAITING.discard(uid)
    bot.reply_to(message, "❌ လုပ်ဆောင်ချက်ကို ပယ်ဖျက်လိုက်ပါပြီ။")


@bot.message_handler(
    func=lambda m: m.from_user.id in OWNER_IDS
    and m.from_user.id in BROADCAST_WAITING,
    content_types=["text"],
)
def handle_broadcast_send(message: types.Message):
    BROADCAST_WAITING.discard(message.from_user.id)
    data = load_data()
    users = data.get("known_users", [])
    sent_count = 0
    failed_count = 0

    for uid in users:
        try:
            bot.send_message(int(uid), message.text)
            sent_count += 1
        except Exception:
            failed_count += 1

    bot.reply_to(
        message,
        f"📢 Broadcast ပြီးပါပြီ။\n• Sent: {sent_count}\n• Failed: {failed_count}",
    )


@bot.message_handler(
    func=lambda m: m.from_user.id in OWNER_IDS
    and m.from_user.id in EDITING_STATE,
    content_types=["text"],
)
def handle_owner_text_input(message: types.Message):
    user_id = message.from_user.id
    state = EDITING_STATE.pop(user_id, None)
    if not state:
        return

    target = state["target"]
    key = state["key"]
    new_text = message.text

    if target == "settings":
        update_nested_setting(key, new_text)
    else:
        update_main_config_field(key, new_text)

    bot.reply_to(
        message,
        f"✅ <b>{key}</b> ({target}) ကို Database ထဲတွင် အောင်မြင်စွာ Update လုပ်ပြီးပါပြီ။\n\n"
        f"<b>စာသားအသစ်:</b>\n{new_text}",
    )


# ==========================================
# 6. HEALTH / HTTP SERVER & RUNNER
# ==========================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        payload = {
            "status": "ok",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def log_message(self, format, *args):
        return


def start_http_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthCheckHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()


if __name__ == "__main__":
    start_http_server()
    print(f"Bot & HTTP health server running on port {PORT}...")
    bot.infinity_polling(skip_pending=True)
