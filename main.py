import os
import json
import logging
import telebot
from telebot import types
from supabase import create_client, Client

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

CONFIG_TABLE = "bot_config"
CONFIG_ROW_ID = "main_config"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

DEFAULT_CONFIG = {
    "kpay": "09xxxxxxxxx (Owner Name)",
    "wave": "09xxxxxxxxx (Owner Name)",
    "pro_price": "3,000 Ks / 1 Month",
    "vip_price": "5,000 Ks / 1 Month",
    "ref_rate_ks": 250,
    "pro_ref_target": 12,
    "vip_ref_target": 20,
    "support": "@mikef07",
    "known_users": 1,
    "banned_users": 0,
    "users": {},
    "notifications": {
        "welcome": "🎉 မင်္ဂလာပါ! <b>AYK Recap Bot</b> မှ နွေးထွေးစွာ ကြိုဆိုပါတယ်။",
        "support_prompt": "💬 Admin ထံ ဆက်သွယ်လိုသော မက်ဆေ့ခ်ျကို ရိုက်ပို့ပေးပါ။",
        "plan_update": "✨ သင့် Plan အခြေအနေ ပြောင်းလဲသွားပါပြီ။",
    },
}

EDITABLE_FIELDS = {
    "kpay": {
        "title": "💳 KPay အချက်အလက်",
        "format_hint": "<code>ဖုန်းနံပါတ် (ပိုင်ရှင်အမည်)</code>",
        "example": "09965376292 (Ko Myo Min Naing)",
        "type": "str",
    },
    "wave": {
        "title": "🌊 Wave အချက်အလက်",
        "format_hint": "<code>ဖုန်းနံပါတ် (ပိုင်ရှင်အမည်)</code>",
        "example": "09965376292 (Ko Myo Min Naing)",
        "type": "str",
    },
    "pro_price": {
        "title": "💎 Pro Plan ဈေးနှုန်း",
        "format_hint": "<code>ဈေးနှုန်း / ကာလ</code>",
        "example": "3,000 Ks / 1 Month",
        "type": "str",
    },
    "vip_price": {
        "title": "👑 VIP Plan ဈေးနှုန်း",
        "format_hint": "<code>ဈေးနှုန်း / ကာလ</code>",
        "example": "5,000 Ks / 1 Month",
        "type": "str",
    },
    "ref_rate_ks": {
        "title": "🎁 Referral Rate (Ks)",
        "format_hint": "ဂဏန်းသီးသန့် ဥပမာ - <code>250</code>",
        "example": "250",
        "type": "int",
    },
    "pro_ref_target": {
        "title": "🎯 Pro Referral Target",
        "format_hint": "ဂဏန်းသီးသန့် ဥပမာ - <code>12</code>",
        "example": "12",
        "type": "int",
    },
    "vip_ref_target": {
        "title": "🏆 VIP Referral Target",
        "format_hint": "ဂဏန်းသီးသန့် ဥပမာ - <code>20</code>",
        "example": "20",
        "type": "int",
    },
    "support": {
        "title": "🛟 Support Username",
        "format_hint": "<code>@username</code> ပုံစံဖြင့် ရိုက်ထည့်ပါ",
        "example": "@mikef07",
        "type": "str",
    },
}
def _default_user_record(user_id: int, username: str = "", full_name: str = "") -> dict:
    return {
        "user_id": int(user_id),
        "username": username or "",
        "full_name": full_name or "",
        "plan": "free",
        "app_linked": False,
        "app_account_id": "",
        "banned": False,
        "referrals": 0,
        "invited_by": None,
    }


def _sync_user_counts(cfg: dict) -> None:
    users = cfg.get("users")
    if not isinstance(users, dict):
        cfg["users"] = {}
        users = cfg["users"]

    if users:
        cfg["known_users"] = len(users)
        cfg["banned_users"] = sum(
            1 for u in users.values() if isinstance(u, dict) and u.get("banned")
        )
    else:
        cfg["known_users"] = max(int(cfg.get("known_users", 0) or 0), 0)
        cfg["banned_users"] = max(int(cfg.get("banned_users", 0) or 0), 0)


def get_config() -> dict:
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        resp = (
            supabase.table(CONFIG_TABLE)
            .select("data")
            .eq("id", CONFIG_ROW_ID)
            .limit(1)
            .execute()
        )
        rows = resp.data or []
        if rows and isinstance(rows[0].get("data"), dict):
            db_data = rows[0]["data"]
            for k, v in db_data.items():
                if k == "notifications" and isinstance(v, dict):
                    merged["notifications"].update(v)
                elif k == "users" and isinstance(v, dict):
                    merged["users"] = v
                else:
                    merged[k] = v
    except Exception as e:
        logger.error(f"get_config error: {e}")

    _sync_user_counts(merged)
    return merged


def save_config(new_config: dict) -> bool:
    try:
        _sync_user_counts(new_config)
        payload = {
            "id": CONFIG_ROW_ID,
            "data": new_config,
        }
        supabase.table(CONFIG_TABLE).upsert(payload, on_conflict="id").execute()
        return True
    except Exception as e:
        logger.error(f"save_config error: {e}")
        return False


def update_config_key(key: str, value) -> bool:
    cfg = get_config()
    cfg[key] = value
    return save_config(cfg)


def register_or_update_user(user: types.User) -> dict:
    cfg = get_config()
    users = cfg.setdefault("users", {})
    uid_str = str(user.id)
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()

    if uid_str not in users or not isinstance(users[uid_str], dict):
        users[uid_str] = _default_user_record(user.id, user.username or "", full_name)
    else:
        if user.username:
            users[uid_str]["username"] = user.username
        if full_name:
            users[uid_str]["full_name"] = full_name

    _sync_user_counts(cfg)
    save_config(cfg)
    return users[uid_str]
def is_owner(user_id: int) -> bool:
    return OWNER_ID != 0 and int(user_id) == int(OWNER_ID)


def format_settings_summary(cfg: dict) -> str:
    _sync_user_counts(cfg)
    users = cfg.get("users", {})
    free_cnt = sum(
        1 for u in users.values() if isinstance(u, dict) and u.get("plan", "free") == "free"
    )
    pro_cnt = sum(
        1 for u in users.values() if isinstance(u, dict) and u.get("plan") == "pro"
    )
    vip_cnt = sum(
        1 for u in users.values() if isinstance(u, dict) and u.get("plan") == "vip"
    )
    linked_cnt = sum(
        1 for u in users.values() if isinstance(u, dict) and u.get("app_linked")
    )
    banned_cnt = cfg.get("banned_users", 0)
    known_cnt = cfg.get("known_users", 0)

    return (
        "⚙️ <b>လက်ရှိ ဆက်တင်များ</b>\n"
        "────────────────────\n"
        f"💳 <b>KPay:</b> <code>{cfg.get('kpay', '')}</code>\n"
        f"🌊 <b>Wave:</b> <code>{cfg.get('wave', '')}</code>\n"
        f"💎 <b>Pro Price:</b> <code>{cfg.get('pro_price', '')}</code>\n"
        f"👑 <b>VIP Price:</b> <code>{cfg.get('vip_price', '')}</code>\n"
        f"🎁 <b>Referral Rate:</b> <code>{cfg.get('ref_rate_ks', 250)}</code> Ks / ယောက်\n"
        f"🎯 <b>Pro Ref Target:</b> <code>{cfg.get('pro_ref_target', 12)}</code> ယောက် | "
        f"<b>VIP Ref Target:</b> <code>{cfg.get('vip_ref_target', 20)}</code> ယောက်\n"
        f"🛟 <b>Support:</b> <code>{cfg.get('support', '')}</code>\n"
        "────────────────────\n"
        f"👥 <b>Known Users:</b> <code>{known_cnt}</code> ယောက် "
        f"(Free: <code>{free_cnt}</code>, Pro: <code>{pro_cnt}</code>, VIP: <code>{vip_cnt}</code>)\n"
        f"🔗 <b>App Linked Users:</b> <code>{linked_cnt}</code> ယောက် | "
        f"🚫 <b>Banned Users:</b> <code>{banned_cnt}</code> ယောက်"
    )


def format_user_profile(user: types.User, cfg: dict) -> str:
    rec = register_or_update_user(user)
    plan_map = {
        "free": "🆓 Free Plan",
        "pro": "💎 Pro Plan",
        "vip": "👑 VIP Plan",
    }
    plan_label = plan_map.get(str(rec.get("plan", "free")).lower(), "🆓 Free Plan")
    linked_text = (
        f"✅ ချိတ်ဆက်ထားသည် (<code>{rec.get('app_account_id')}</code>)"
        if rec.get("app_linked")
        else "❌ မချိတ်ဆက်ရသေးပါ"
    )
    status_text = "🚫 Banned" if rec.get("banned") else "✅ Active"
    uname = f"@{user.username}" if user.username else "မရှိပါ"

    return (
        "👤 <b>သင့် Profile အချက်အလက်</b>\n"
        "────────────────────\n"
        f"🆔 <b>User ID:</b> <code>{user.id}</code>\n"
        f"📛 <b>Name:</b> <code>{user.first_name or ''} {user.last_name or ''}</code>\n"
        f"🔹 <b>Username:</b> <code>{uname}</code>\n"
        f"📦 <b>Current Plan:</b> <b>{plan_label}</b>\n"
        f"🔗 <b>App Account:</b> {linked_text}\n"
        f"🎁 <b>Referrals:</b> <code>{rec.get('referrals', 0)}</code> ယောက်\n"
        f"📌 <b>Status:</b> <b>{status_text}</b>"
    )


def build_main_menu(user_id: int) -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        types.KeyboardButton("👤 Profile"),
        types.KeyboardButton("💎 Buy Plan"),
    )
    kb.add(
        types.KeyboardButton("🎁 Referral"),
        types.KeyboardButton("💬 Chat with Admin"),
    )
    kb.add(types.KeyboardButton("🛟 Support"))
    if is_owner(user_id):
        kb.add(types.KeyboardButton("⚙️ Owner Menu"))
    return kb


def build_owner_menu(cfg: dict) -> types.InlineKeyboardMarkup:
    ref_rate = cfg.get("ref_rate_ks", 250)
    pro_target = cfg.get("pro_ref_target", 12)
    vip_target = cfg.get("vip_ref_target", 20)

    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✏️ Edit KPay", callback_data="edit_cfg:kpay"),
        types.InlineKeyboardButton("✏️ Edit Wave", callback_data="edit_cfg:wave"),
    )
    kb.add(
        types.InlineKeyboardButton("💎 Edit Pro Price", callback_data="edit_cfg:pro_price"),
        types.InlineKeyboardButton("👑 Edit VIP Price", callback_data="edit_cfg:vip_price"),
    )
    kb.add(
        types.InlineKeyboardButton(f"🎁 Ref Rate ({ref_rate} Ks)", callback_data="edit_cfg:ref_rate_ks"),
        types.InlineKeyboardButton(f"🎯 Pro/VIP Ref ({pro_target}/{vip_target})", callback_data="edit_cfg_targets"),
    )
    kb.add(
        types.InlineKeyboardButton("👥 User Control", callback_data="owner_user_ctrl"),
        types.InlineKeyboardButton("🔔 Notification Mgmt", callback_data="owner_notif_mgmt"),
    )
    kb.add(
        types.InlineKeyboardButton("📢 Send Broadcast", callback_data="owner_broadcast"),
        types.InlineKeyboardButton("🛟 Edit Support", callback_data="edit_cfg:support"),
    )
    kb.add(
        types.InlineKeyboardButton("📊 View Settings", callback_data="view_cfg"),
        types.InlineKeyboardButton("🏠 Main Menu", callback_data="owner_main_menu"),
    )
    return kb
def _parse_and_validate(field_key: str, raw_text: str):
    meta = EDITABLE_FIELDS[field_key]
    text = (raw_text or "").strip()

    if not text:
        return False, None, f"စာသား ကွက်လပ် မဖြစ်ရပါ။\n📌 <b>ပုံစံ:</b> {meta['format_hint']}"

    if meta["type"] == "int":
        cleaned = text.replace(",", "").strip()
        if not cleaned.isdigit():
            return False, None, f"ဂဏန်းသီးသန့်သာ ရိုက်ထည့်ရပါမည်။\n📌 <b>ပုံစံ:</b> {meta['format_hint']}"
        val = int(cleaned)
        if val < 0:
            return False, None, "သုည (0) ထက် မငယ်သော ဂဏန်းသာ ထည့်သွင်းပါ။"
        return True, val, ""

    if field_key == "support" and not text.startswith("@"):
        return False, None, f"Support username သည် <code>@</code> ဖြင့် စရပါမည်။\n📌 <b>ပုံစံ:</b> {meta['format_hint']}"

    return True, text, ""


def _send_edit_instruction(chat_id: int, field_key: str, cfg: dict):
    meta = EDITABLE_FIELDS[field_key]
    current_val = cfg.get(field_key, "")
    instruction = (
        f"{meta['title']} <b>ပြင်ဆင်ရန် ညွှန်ကြားချက်</b>\n"
        "────────────────────\n"
        f"📌 <b>လက်ရှိ တန်ဖိုး:</b> <code>{current_val}</code>\n"
        f"✅ <b>မှန်ကန်သော ပုံစံ:</b> {meta['format_hint']}\n"
        f"💡 <b>ဥပမာ:</b> <code>{meta['example']}</code>\n"
        "────────────────────\n"
        "အထက်ပါ ပုံစံအတိုင်း အချက်အလက်အသစ်ကို ရိုက်ပို့ပေးပါ။\n"
        "🚫 ပယ်ဖျက်လိုပါက <code>/cancel</code> ဟု ရိုက်ပါ။"
    )
    msg = bot.send_message(chat_id, instruction)
    bot.register_next_step_handler(msg, _handle_field_input, field_key)


def _handle_field_input(message: types.Message, field_key: str):
    if not is_owner(message.from_user.id):
        return

    raw_text = message.text or ""
    cfg = get_config()

    if raw_text.strip().lower() == "/cancel":
        bot.send_message(
            message.chat.id,
            "🚫 <b>ပြင်ဆင်မှုကို ပယ်ဖျက်လိုက်ပါပြီ။</b>",
            reply_markup=build_owner_menu(cfg),
        )
        return

    ok, parsed_value, err_msg = _parse_and_validate(field_key, raw_text)
    if not ok:
        retry_msg = bot.send_message(
            message.chat.id,
            f"⚠️ <b>Format မှားယွင်းနေပါသည်</b>\n"
            "────────────────────\n"
            f"{err_msg}\n\n"
            "🔁 ပုံစံမှန်ဖြင့် ထပ်မံ ရိုက်ထည့်ပါ သို့မဟုတ် <code>/cancel</code> ဖြင့် ပယ်ဖျက်ပါ။",
        )
        bot.register_next_step_handler(retry_msg, _handle_field_input, field_key)
        return

    saved = update_config_key(field_key, parsed_value)
    updated_cfg = get_config()
    if saved:
        bot.send_message(
            message.chat.id,
            f"✅ <b>{EDITABLE_FIELDS[field_key]['title']}</b> ကို အောင်မြင်စွာ Update လုပ်ပြီးပါပြီ!\n\n"
            f"{format_settings_summary(updated_cfg)}",
            reply_markup=build_owner_menu(updated_cfg),
        )
    else:
        bot.send_message(
            message.chat.id,
            "❌ <b>Supabase ထဲ သိမ်းဆည်းရာတွင် အမှားဖြစ်ပွားပါသည်။</b>\n"
            "<code>bot_config</code> table structure (<code>id</code> primary key / <code>data</code> jsonb) နှင့် Server Log ကို စစ်ဆေးပါ။",
            reply_markup=build_owner_menu(updated_cfg),
        )


@bot.message_handler(commands=["start"])
def cmd_start(message: types.Message):
    register_or_update_user(message.from_user)
    cfg = get_config()
    welcome_text = cfg.get("notifications", {}).get(
        "welcome",
        "🎉 မင်္ဂလာပါ! <b>AYK Recap Bot</b> မှ ကြိုဆိုပါတယ်။",
    )
    bot.send_message(
        message.chat.id,
        f"{welcome_text}\n\n👇 အောက်ပါ Menu မှ လိုအပ်သော လုပ်ဆောင်ချက်ကို ရွေးချယ်ပါ။",
        reply_markup=build_main_menu(message.from_user.id),
    )


@bot.message_handler(commands=["owner", "settings"])
@bot.message_handler(func=lambda m: m.text == "⚙️ Owner Menu")
def cmd_owner_menu(message: types.Message):
    if not is_owner(message.from_user.id):
        bot.send_message(message.chat.id, "⛔ ဤ Menu ကို Owner သာ အသုံးပြုနိုင်ပါသည်။")
        return
    cfg = get_config()
    bot.send_message(
        message.chat.id,
        f"👑 <b>Owner Control Panel</b>\n\n{format_settings_summary(cfg)}",
        reply_markup=build_owner_menu(cfg),
    )


@bot.message_handler(func=lambda m: m.text in [
    "👤 Profile",
    "💎 Buy Plan",
    "🎁 Referral",
    "💬 Chat with Admin",
    "🛟 Support",
])
def handle_user_menu_buttons(message: types.Message):
    cfg = get_config()
    text = message.text

    if text == "👤 Profile":
        bot.send_message(
            message.chat.id,
            format_user_profile(message.from_user, cfg),
            reply_markup=build_main_menu(message.from_user.id),
        )
    elif text == "💎 Buy Plan":
        msg = (
            "💎 <b>Plan ဝယ်ယူရန် ငွေပေးချေမှု အချက်အလက်များ</b>\n"
            "────────────────────\n"
            f"🔹 <b>Pro Plan:</b> <code>{cfg.get('pro_price', '')}</code>\n"
            f"👑 <b>VIP Plan:</b> <code>{cfg.get('vip_price', '')}</code>\n"
            "────────────────────\n"
            f"💳 <b>KPay:</b> <code>{cfg.get('kpay', '')}</code>\n"
            f"🌊 <b>Wave:</b> <code>{cfg.get('wave', '')}</code>\n"
            "────────────────────\n"
            "📸 ငွေလွှဲပြီးပါက Screenshot နှင့် User ID ကို Admin ထံ ပေးပို့ပါ။"
        )
        bot.send_message(message.chat.id, msg, reply_markup=build_main_menu(message.from_user.id))
    elif text == "🎁 Referral":
        bot_username = bot.get_me().username or "YourBotUsername"
        ref_link = f"https://t.me/{bot_username}?start=ref_{message.from_user.id}"
        msg = (
            "🎁 <b>Referral အစီအစဉ်</b>\n"
            "────────────────────\n"
            f"💰 <b>Referral Rate:</b> <code>{cfg.get('ref_rate_ks', 250)}</code> Ks / ယောက်\n"
            f"🎯 <b>Pro Target:</b> <code>{cfg.get('pro_ref_target', 12)}</code> ယောက်\n"
            f"🏆 <b>VIP Target:</b> <code>{cfg.get('vip_ref_target', 20)}</code> ယောက်\n"
            "────────────────────\n"
            f"🔗 <b>သင့် Referral Link:</b>\n<code>{ref_link}</code>"
        )
        bot.send_message(message.chat.id, msg, reply_markup=build_main_menu(message.from_user.id))
    elif text in ["💬 Chat with Admin", "🛟 Support"]:
        support_handle = cfg.get("support", "@mikef07")
        prompt_text = cfg.get("notifications", {}).get(
            "support_prompt",
            "💬 Admin ထံ ဆက်သွယ်ရန် မက်ဆေ့ခ်ျ ပို့ပေးပါ။",
        )
        bot.send_message(
            message.chat.id,
            f"🛟 <b>Support & Admin Contact</b>\n"
            "────────────────────\n"
            f"{prompt_text}\n"
            f"📩 <b>Contact:</b> <code>{support_handle}</code>",
            reply_markup=build_main_menu(message.from_user.id),
        )


@bot.callback_query_handler(func=lambda call: call.data == "view_cfg")
def cb_view_cfg(call: types.CallbackQuery):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Owner သာ အသုံးပြုနိုင်ပါသည်။", show_alert=True)
        return
    cfg = get_config()
    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"👑 <b>Owner Control Panel</b>\n\n{format_settings_summary(cfg)}",
        reply_markup=build_owner_menu(cfg),
    )


@bot.callback_query_handler(func=lambda call: call.data == "owner_main_menu")
def cb_owner_main_menu(call: types.CallbackQuery):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Owner သာ အသုံးပြုနိုင်ပါသည်။", show_alert=True)
        return
    bot.answer_callback_query(call.id, "🏠 Main Menu သို့ ပြောင်းလဲလိုက်ပါပြီ။")
    bot.send_message(
        call.message.chat.id,
        "🏠 <b>Main Menu</b>",
        reply_markup=build_main_menu(call.from_user.id),
    )


@bot.callback_query_handler(func=lambda call: call.data == "edit_cfg_targets")
def cb_edit_targets_menu(call: types.CallbackQuery):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Owner သာ အသုံးပြုနိုင်ပါသည်။", show_alert=True)
        return
    cfg = get_config()
    bot.answer_callback_query(call.id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"🎯 Pro ({cfg.get('pro_ref_target', 12)})", callback_data="edit_cfg:pro_ref_target"),
        types.InlineKeyboardButton(f"🏆 VIP ({cfg.get('vip_ref_target', 20)})", callback_data="edit_cfg:vip_ref_target"),
    )
    kb.add(types.InlineKeyboardButton("⬅️ Back", callback_data="view_cfg"))
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="🎯 <b>ပြင်ဆင်လိုသော Referral Target ကို ရွေးချယ်ပါ</b>\n────────────────────",
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_cfg:"))
def cb_start_edit_field(call: types.CallbackQuery):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Owner သာ အသုံးပြုနိုင်ပါသည်။", show_alert=True)
        return
    field_key = call.data.split(":", 1)[1]
    if field_key not in EDITABLE_FIELDS:
        bot.answer_callback_query(call.id, "⚠️ Invalid setting.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    cfg = get_config()
    _send_edit_instruction(call.message.chat.id, field_key, cfg)


@bot.callback_query_handler(func=lambda call: call.data == "owner_user_ctrl")
def cb_owner_user_ctrl(call: types.CallbackQuery):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Owner သာ အသုံးပြုနိုင်ပါသည်။", show_alert=True)
        return
    cfg = get_config()
    users = cfg.get("users", {})
    bot.answer_callback_query(call.id)
    msg = (
        "👥 <b>User Control Overview</b>\n"
        "────────────────────\n"
        f"📊 <b>Total Known Users:</b> <code>{len(users)}</code> ယောက်\n"
        f"🚫 <b>Banned Users:</b> <code>{cfg.get('banned_users', 0)}</code> ယောက်\n\n"
        "💡 User Plan / Ban / App Link function များကို ဤနေရာမှ ဆက်လက်ချိတ်ဆက်နိုင်ပါသည်။"
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⬅️ Back to Owner Panel", callback_data="view_cfg"))
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=msg,
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda call: call.data == "owner_notif_mgmt")
def cb_owner_notif_mgmt(call: types.CallbackQuery):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Owner သာ အသုံးပြုနိုင်ပါသည်။", show_alert=True)
        return
    cfg = get_config()
    notifs = cfg.get("notifications", {})
    bot.answer_callback_query(call.id)
    msg = (
        "🔔 <b>Notification Management</b>\n"
        "────────────────────\n"
        f"👋 <b>Welcome:</b> {notifs.get('welcome', '')}\n"
        f"💬 <b>Support Prompt:</b> {notifs.get('support_prompt', '')}\n"
        f"✨ <b>Plan Update:</b> {notifs.get('plan_update', '')}"
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⬅️ Back to Owner Panel", callback_data="view_cfg"))
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=msg,
        reply_markup=kb,
    )


@bot.callback_query_handler(func=lambda call: call.data == "owner_broadcast")
def cb_owner_broadcast(call: types.CallbackQuery):
    if not is_owner(call.from_user.id):
        bot.answer_callback_query(call.id, "⛔ Owner သာ အသုံးပြုနိုင်ပါသည်။", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    msg = bot.send_message(
        call.message.chat.id,
        "📢 <b>Send Broadcast</b>\n"
        "────────────────────\n"
        "အသုံးပြုသူအားလုံးထံ ပို့လိုသော စာသားကို ရိုက်ပို့ပေးပါ။\n"
        "🚫 ပယ်ဖျက်လိုပါက <code>/cancel</code> ဟု ရိုက်ပါ။",
    )
    bot.register_next_step_handler(msg, _handle_broadcast_text)


def _handle_broadcast_text(message: types.Message):
    if not is_owner(message.from_user.id):
        return
    cfg = get_config()
    text = (message.text or "").strip()
    if text.lower() == "/cancel":
        bot.send_message(
            message.chat.id,
            "🚫 Broadcast ပို့ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီ။",
            reply_markup=build_owner_menu(cfg),
        )
        return
    if not text:
        retry = bot.send_message(
            message.chat.id,
            "⚠️ စာသား ကွက်လပ် မဖြစ်ရပါ။ Broadcast စာသား ထပ်ရိုက်ပါ သို့မဟုတ် <code>/cancel</code> ရိုက်ပါ။",
        )
        bot.register_next_step_handler(retry, _handle_broadcast_text)
        return

    users = cfg.get("users", {})
    sent_count = 0
    failed_count = 0
    for uid_str, u_data in users.items():
        if isinstance(u_data, dict) and u_data.get("banned"):
            continue
        try:
            bot.send_message(int(uid_str), f"📢 <b>ကြေညာချက်</b>\n────────────────────\n{text}")
            sent_count += 1
        except Exception:
            failed_count += 1

    bot.send_message(
        message.chat.id,
        f"✅ <b>Broadcast ပြီးစီးပါပြီ!</b>\n"
        f"• ✉️ ပို့ပြီး: <code>{sent_count}</code> ယောက်\n"
        f"• ⚠️ မအောင်မြင်: <code>{failed_count}</code> ယောက်",
        reply_markup=build_owner_menu(cfg),
    )
def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is missing.")
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_URL or SUPABASE_KEY environment variable is missing.")

    logger.info("AYK Recap Bot started successfully.")
    bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=20)


if __name__ == "__main__":
    main()
