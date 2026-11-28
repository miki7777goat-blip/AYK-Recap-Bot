# --- အပိုင်း (၁): Imports, Config & Supabase Setup ---
import os
import json
import logging
import telebot
from telebot import types
from supabase import create_client, Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
OWNER_ID = int(os.getenv("OWNER_ID", "0"))

SUPABASE_URL = os.getenv("SUPABASE_URL", "YOUR_SUPABASE_URL_HERE")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "YOUR_SUPABASE_KEY_HERE")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

CONFIG_TABLE = "bot_config"
CONFIG_ROW_ID = "main_config"

DEFAULT_CONFIG = {
    "kpay": "09xxxxxxxxx (Owner Name)",
    "wave": "09xxxxxxxxx (Owner Name)",
    "pro_price": "3,000 Ks / 1 Month",
    "vip_price": "5,000 Ks / 1 Month",
    "ref_rate_ks": 250,
    "pro_ref_target": 12,   # 3,000 / 250 = 12 ယောက်
    "vip_ref_target": 20,   # 5,000 / 250 = 20 ယောက်
    "support": "@mikef07",
    "known_users": 1,
    "banned_users": 0,
    "users": {},
    "notifications": {
        "welcome": "မင်္ဂလာပါ! Bot မှ ကြိုဆိုပါတယ်။",
        "support_prompt": "Admin ထံ ဆက်သွယ်ရန် မက်ဆေ့ချ် ရိုက်ပို့ပေးပါ။",
        "plan_update": "သင့် Plan အခြေအနေ ပြောင်းလဲသွားပါပြီ။",
    },
}

USER_STATES = {}
# --- အပိုင်း (၂): Database Load, Save, User Control, Referral & Notification Helpers ---
def _default_user_record(user_id: int, username: str = "", full_name: str = "") -> dict:
    return {
        "user_id": int(user_id),
        "username": username or "",
        "full_name": full_name or "",
        "plan": "free",               # "free" | "pro" | "vip"
        "app_linked": False,          # App နဲ့ ချိတ်ဆက်ထားလား
        "app_account_id": "",         # ချိတ်ဆက်ထားတဲ့ App / Account ID
        "banned": False,              # Ban / Unban အခြေအနေ
        "referrals": 0,               # ဖိတ်ခေါ်နိုင်ခဲ့တဲ့ အရေအတွက်
        "invited_by": None,           # ဖိတ်ခေါ်ခဲ့သူ user_id
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
    """Supabase `bot_config` table ထဲက `main_config` row ရဲ့ `data` ကို ဖတ်ယူပြီး default နှင့် ပေါင်းစပ်ပေးသည်။"""
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
    """Configuration dictionary တစ်ခုလုံးကို Supabase `bot_config` (`main_config`) ထဲတွင် သိမ်းဆည်းသည်။"""
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
    """Key တစ်ခုတည်းကို အမြန် update လုပ်ပြီး Supabase ထဲ သိမ်းဆည်းသည်။"""
    cfg = get_config()
    cfg[key] = value
    return save_config(cfg)


def register_or_update_user(
    user_id: int,
    username: str = "",
    full_name: str = "",
    invited_by: int | None = None,
) -> dict:
    """User ကို မှတ်တမ်းတင်ပြီး referral ရှိပါက ဖိတ်ခေါ်သူရဲ့ count ကို တိုးပေးသည်။"""
    cfg = get_config()
    users = cfg.setdefault("users", {})
    uid_str = str(int(user_id))

    is_new = uid_str not in users
    rec = _default_user_record(user_id, username, full_name)
    if not is_new and isinstance(users[uid_str], dict):
        rec.update(users[uid_str])
    if username:
        rec["username"] = username
    if full_name:
        rec["full_name"] = full_name

    if (
        is_new
        and invited_by is not None
        and int(invited_by) != int(user_id)
        and not rec.get("invited_by")
    ):
        inv_str = str(int(invited_by))
        if inv_str not in users:
            users[inv_str] = _default_user_record(int(invited_by))
        users[inv_str]["referrals"] = int(users[inv_str].get("referrals", 0) or 0) + 1
        rec["invited_by"] = int(invited_by)

    users[uid_str] = rec
    save_config(cfg)
    return rec


def set_user_ban(user_id: int, banned: bool) -> tuple[bool, dict]:
    """User တစ်ယောက်ကို Ban / Unban လုပ်သည်။"""
    cfg = get_config()
    users = cfg.setdefault("users", {})
    uid_str = str(int(user_id))
    rec = _default_user_record(user_id)
    if isinstance(users.get(uid_str), dict):
        rec.update(users[uid_str])
    rec["banned"] = bool(banned)
    users[uid_str] = rec
    ok = save_config(cfg)
    return ok, rec


def set_user_plan(user_id: int, plan: str) -> tuple[bool, dict]:
    """User ရဲ့ Plan ကို 'free', 'pro', 'vip' သတ်မှတ်သည်။"""
    plan_clean = (plan or "free").strip().lower()
    if plan_clean not in ("free", "pro", "vip"):
        plan_clean = "free"
    cfg = get_config()
    users = cfg.setdefault("users", {})
    uid_str = str(int(user_id))
    rec = _default_user_record(user_id)
    if isinstance(users.get(uid_str), dict):
        rec.update(users[uid_str])
    rec["plan"] = plan_clean
    users[uid_str] = rec
    ok = save_config(cfg)
    return ok, rec


def set_user_app_link(user_id: int, linked: bool, app_account_id: str = "") -> tuple[bool, dict]:
    """User ရဲ့ App ချိတ်ဆက်မှု အခြေအနေ (linked / unlinked + account ID) ကို သိမ်းဆည်းသည်။"""
    cfg = get_config()
    users = cfg.setdefault("users", {})
    uid_str = str(int(user_id))
    rec = _default_user_record(user_id)
    if isinstance(users.get(uid_str), dict):
        rec.update(users[uid_str])
    rec["app_linked"] = bool(linked)
    rec["app_account_id"] = (app_account_id or "").strip() if linked else ""
    users[uid_str] = rec
    ok = save_config(cfg)
    return ok, rec


def calculate_referral_status(cfg: dict, referrals_count: int) -> dict:
    """ဥပမာ- 250 Ks/ယောက် -> Pro (3,000 = 12 ယောက်), VIP (5,000 = 20 ယောက်) အတိုင်း တွက်ချက်သည်။"""
    rate = max(int(cfg.get("ref_rate_ks", 250) or 250), 1)
    pro_target = max(int(cfg.get("pro_ref_target", 12) or 12), 1)
    vip_target = max(int(cfg.get("vip_ref_target", 20) or 20), 1)
    refs = max(int(referrals_count or 0), 0)

    earned_ks = refs * rate
    pro_unlocked = refs // pro_target
    vip_unlocked = refs // vip_target
    to_next_pro = 0 if refs >= pro_target else (pro_target - refs)
    to_next_vip = 0 if refs >= vip_target else (vip_target - refs)

    return {
        "rate_ks": rate,
        "earned_ks": earned_ks,
        "pro_target": pro_target,
        "vip_target": vip_target,
        "pro_unlocked": pro_unlocked,
        "vip_unlocked": vip_unlocked,
        "to_next_pro": to_next_pro,
        "to_next_vip": to_next_vip,
    }


def format_user_detail(cfg: dict, user_id: int) -> str:
    """User တစ်ယောက်ရဲ့ Plan၊ App Link၊ Ban Status နဲ့ Referral တွက်ချက်မှုကို စာသားအဖြစ် ဖွဲ့စည်းသည်။"""
    users = cfg.get("users") or {}
    rec = _default_user_record(user_id)
    if isinstance(users.get(str(int(user_id))), dict):
        rec.update(users[str(int(user_id))])

    plan_label = {
        "free": "Free Plan",
        "pro": "Pro Plan",
        "vip": "VIP Plan",
    }.get(str(rec.get("plan", "free")).lower(), "Free Plan")

    if rec.get("app_linked"):
        acc_id = rec.get("app_account_id") or "ချိတ်ဆက်ထားသည်"
        app_status = f"✅ ချိတ်ဆက်ထားပါသည် (<code>{acc_id}</code>)"
    else:
        app_status = "❌ မချိတ်ဆက်ရသေးပါ"

    ban_status = "🚫 Banned" if rec.get("banned") else "✅ Active (Ban မခံရပါ)"
    ref_info = calculate_referral_status(cfg, rec.get("referrals", 0))

    uname = f"@{rec['username']}" if rec.get("username") else "မရှိပါ"
    return (
        f"👤 <b>User အချက်အလက်:</b> <code>{rec['user_id']}</code>\n"
        f"• Name: <code>{rec.get('full_name') or '-'}</code> ({uname})\n"
        f"• Plan: <b>{plan_label}</b>\n"
        f"• App Link: {app_status}\n"
        f"• Status: <b>{ban_status}</b>\n"
        f"• Referrals: <code>{rec.get('referrals', 0)}</code> ယောက် "
        f"(စုစုပေါင်း <code>{ref_info['earned_ks']:,} Ks</code>)\n"
        f"• Pro Target ({ref_info['pro_target']} ယောက်): "
        f"<code>{ref_info['pro_unlocked']}</code> ကြိမ်ရရှိ / လိုသေး: <code>{ref_info['to_next_pro']}</code> ယောက်\n"
        f"• VIP Target ({ref_info['vip_target']} ယောက်): "
        f"<code>{ref_info['vip_unlocked']}</code> ကြိမ်ရရှိ / လိုသေး: <code>{ref_info['to_next_vip']}</code> ယောက်"
    )


def format_settings_summary(cfg: dict) -> str:
    """Owner Control Panel အောက်မှာ ပြသမည့် လက်ရှိ ဆက်တင်အနှစ်ချုပ် စာသားကို တည်ဆောက်သည်။"""
    _sync_user_counts(cfg)
    users = cfg.get("users") or {}
    free_cnt = sum(1 for u in users.values() if isinstance(u, dict) and u.get("plan", "free") == "free")
    pro_cnt = sum(1 for u in users.values() if isinstance(u, dict) and u.get("plan") == "pro")
    vip_cnt = sum(1 for u in users.values() if isinstance(u, dict) and u.get("plan") == "vip")
    linked_cnt = sum(1 for u in users.values() if isinstance(u, dict) and u.get("app_linked"))

    return (
        "⚙️ <b>လက်ရှိ ဆက်တင်များ:</b>\n"
        f"• KPay: <code>{cfg.get('kpay', '')}</code>\n"
        f"• Wave: <code>{cfg.get('wave', '')}</code>\n"
        f"• Pro Price: <code>{cfg.get('pro_price', '')}</code>\n"
        f"• VIP Price: <code>{cfg.get('vip_price', '')}</code>\n"
        f"• Referral Rate: <code>{cfg.get('ref_rate_ks', 250)} Ks / ယောက်</code>\n"
        f"• Pro Ref Target: <code>{cfg.get('pro_ref_target', 12)} ယောက်</code> | "
        f"VIP Ref Target: <code>{cfg.get('vip_ref_target', 20)} ယောက်</code>\n"
        f"• Support: <code>{cfg.get('support', '')}</code>\n"
        f"• Known Users: <code>{cfg.get('known_users', 0)}</code> ယောက် "
        f"(Free: <code>{free_cnt}</code>, Pro: <code>{pro_cnt}</code>, VIP: <code>{vip_cnt}</code>)\n"
        f"• App Linked Users: <code>{linked_cnt}</code> ယောက် | "
        f"Banned Users: <code>{cfg.get('banned_users', 0)}</code> ယောက်"
        )
# --- အပိုင်း (၃): Keyboards, User Control, Referral & Notification Menu Builders ---
def build_main_menu_keyboard(user_id: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("👤 My Profile / Plan", callback_data="user_profile"),
        types.InlineKeyboardButton("🔗 Link App Account", callback_data="user_link_app"),
    )
    kb.add(
        types.InlineKeyboardButton("🎁 Referral (Pro / VIP)", callback_data="user_referral"),
        types.InlineKeyboardButton("💳 Buy Plan (KPay / Wave)", callback_data="user_buy_plan"),
    )
    kb.add(
        types.InlineKeyboardButton("📩 Notifications", callback_data="user_notifications"),
        types.InlineKeyboardButton("🛟 Support", callback_data="user_support"),
    )
    if int(user_id) == OWNER_ID and OWNER_ID != 0:
        kb.add(
            types.InlineKeyboardButton("👑 Owner Control Panel", callback_data="owner_panel")
        )
    return kb


def build_owner_panel_keyboard(cfg: dict) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✏️ Edit KPay", callback_data="edit_kpay"),
        types.InlineKeyboardButton("✏️ Edit Wave", callback_data="edit_wave"),
    )
    kb.add(
        types.InlineKeyboardButton("💎 Edit Pro Price", callback_data="edit_pro_price"),
        types.InlineKeyboardButton("👑 Edit VIP Price", callback_data="edit_vip_price"),
    )
    kb.add(
        types.InlineKeyboardButton(
            f"🎁 Ref Rate ({cfg.get('ref_rate_ks', 250)} Ks)",
            callback_data="edit_ref_rate_ks",
        ),
        types.InlineKeyboardButton(
            f"🎯 Pro/VIP Ref ({cfg.get('pro_ref_target', 12)}/{cfg.get('vip_ref_target', 20)})",
            callback_data="menu_ref_targets",
        ),
    )
    kb.add(
        types.InlineKeyboardButton("👥 User Control", callback_data="menu_user_control"),
        types.InlineKeyboardButton("🔔 Notification Mgmt", callback_data="menu_notifications"),
    )
    kb.add(
        types.InlineKeyboardButton("📢 Send Broadcast", callback_data="start_broadcast"),
        types.InlineKeyboardButton("🛟 Edit Support", callback_data="edit_support"),
    )
    kb.add(
        types.InlineKeyboardButton("📊 View Settings", callback_data="view_settings"),
        types.InlineKeyboardButton("🏠 Main Menu", callback_data="back_main"),
    )
    return kb


def build_ref_targets_keyboard(cfg: dict) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(
            f"💎 Set Pro Ref Target (လက်ရှိ: {cfg.get('pro_ref_target', 12)} ယောက်)",
            callback_data="edit_pro_ref_target",
        ),
        types.InlineKeyboardButton(
            f"👑 Set VIP Ref Target (လက်ရှိ: {cfg.get('vip_ref_target', 20)} ယောက်)",
            callback_data="edit_vip_ref_target",
        ),
        types.InlineKeyboardButton("⬅️ Back to Owner Panel", callback_data="owner_panel"),
    )
    return kb


def build_user_control_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🔍 Inspect User", callback_data="uc_inspect_user"),
        types.InlineKeyboardButton("📋 User List", callback_data="uc_list_users"),
    )
    kb.add(
        types.InlineKeyboardButton("🚫 Ban User", callback_data="uc_ban_user"),
        types.InlineKeyboardButton("✅ Unban User", callback_data="uc_unban_user"),
    )
    kb.add(
        types.InlineKeyboardButton("📦 Set User Plan", callback_data="uc_set_plan"),
        types.InlineKeyboardButton("🔗 Set App Link", callback_data="uc_set_app_link"),
    )
    kb.add(
        types.InlineKeyboardButton("⬅️ Back to Owner Panel", callback_data="owner_panel"),
    )
    return kb


def build_plan_select_keyboard(target_user_id: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("Free", callback_data=f"setplan_{target_user_id}_free"),
        types.InlineKeyboardButton("Pro", callback_data=f"setplan_{target_user_id}_pro"),
        types.InlineKeyboardButton("VIP", callback_data=f"setplan_{target_user_id}_vip"),
    )
    kb.add(
        types.InlineKeyboardButton("⬅️ Cancel", callback_data="menu_user_control"),
    )
    return kb


def build_notifications_menu_keyboard() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("✏️ Edit Welcome Notification", callback_data="edit_notif_welcome"),
        types.InlineKeyboardButton("✏️ Edit Support Prompt", callback_data="edit_notif_support_prompt"),
        types.InlineKeyboardButton("✏️ Edit Plan Update Notice", callback_data="edit_notif_plan_update"),
        types.InlineKeyboardButton("📢 Send Broadcast Now", callback_data="start_broadcast"),
        types.InlineKeyboardButton("⬅️ Back to Owner Panel", callback_data="owner_panel"),
    )
    return kb
# --- အပိုင်း (၄): Callback Handlers, User Flows & Owner Control Handlers ---
def _is_owner(user_id: int) -> bool:
    return OWNER_ID != 0 and int(user_id) == int(OWNER_ID)


def _is_banned(cfg: dict, user_id: int) -> bool:
    if _is_owner(user_id):
        return False
    users = cfg.get("users") or {}
    rec = users.get(str(int(user_id)))
    return bool(isinstance(rec, dict) and rec.get("banned"))


@bot.message_handler(commands=["start"])
def handle_start(message: telebot.types.Message):
    uid = message.from_user.id
    username = message.from_user.username or ""
    full_name = " ".join(
        filter(None, [message.from_user.first_name, message.from_user.last_name])
    )

    invited_by = None
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("ref_"):
        raw_inv = parts[1].replace("ref_", "", 1).strip()
        if raw_inv.isdigit():
            invited_by = int(raw_inv)

    register_or_update_user(uid, username=username, full_name=full_name, invited_by=invited_by)
    cfg = get_config()
    if _is_banned(cfg, uid):
        bot.send_message(message.chat.id, "🚫 သင့်အကောင့်ကို ယာယီပိတ်ပင်ထားပါသည်။")
        return

    welcome_text = cfg.get("notifications", {}).get(
        "welcome", DEFAULT_CONFIG["notifications"]["welcome"]
    )
    bot.send_message(
        message.chat.id,
        f"{welcome_text}\n\n{format_user_detail(cfg, uid)}",
        reply_markup=build_main_menu_keyboard(uid),
    )


@bot.message_handler(commands=["owner"])
def handle_owner_cmd(message: telebot.types.Message):
    uid = message.from_user.id
    if not _is_owner(uid):
        bot.send_message(message.chat.id, "⛔ Owner သာ အသုံးပြုနိုင်ပါသည်။")
        return
    cfg = get_config()
    bot.send_message(
        message.chat.id,
        f"👑 <b>Owner Control Panel</b>\n\n{format_settings_summary(cfg)}",
        reply_markup=build_owner_panel_keyboard(cfg),
    )


@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call: telebot.types.CallbackQuery):
    uid = call.from_user.id
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    data = call.data or ""

    username = call.from_user.username or ""
    full_name = " ".join(
        filter(None, [call.from_user.first_name, call.from_user.last_name])
    )
    register_or_update_user(uid, username=username, full_name=full_name)
    cfg = get_config()

    if _is_banned(cfg, uid):
        bot.answer_callback_query(call.id, "🚫 သင့်အကောင့် ပိတ်ပင်ခံထားရပါသည်။", show_alert=True)
        return

    bot.answer_callback_query(call.id)

    # --- User Menus ---
    if data == "back_main":
        USER_STATES.pop(uid, None)
        bot.edit_message_text(
            f"🏠 <b>Main Menu</b>\n\n{format_user_detail(cfg, uid)}",
            chat_id,
            msg_id,
            reply_markup=build_main_menu_keyboard(uid),
        )
        return

    if data == "user_profile":
        bot.edit_message_text(
            format_user_detail(cfg, uid),
            chat_id,
            msg_id,
            reply_markup=build_main_menu_keyboard(uid),
        )
        return

    if data == "user_link_app":
        USER_STATES[uid] = {"action": "user_link_app_input"}
        bot.send_message(
            chat_id,
            "🔗 သင့် App Account ID ကို ရိုက်ထည့်ပေးပါ (ချိတ်ဆက်မှု ဖြုတ်လိုပါက <code>unlink</code> ဟု ရိုက်ပါ၊ ပယ်ဖျက်ရန် <code>/cancel</code>):",
        )
        return

    if data == "user_referral":
        users = cfg.get("users") or {}
        rec = users.get(str(uid), {})
        refs = int(rec.get("referrals", 0) or 0)
        info = calculate_referral_status(cfg, refs)
        bot_info = bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{uid}" if bot_info.username else f"ref_{uid}"
        text = (
            "🎁 <b>Referral အစီအစဉ် (Pro & VIP)</b>\n"
            f"• ဖိတ်ခေါ်မှု နှုန်းထား: <code>{info['rate_ks']:,} Ks / ယောက်</code>\n"
            f"• Pro Plan Target: <code>{info['pro_target']} ယောက်</code> (3,000 Ks တန်ဖိုး)\n"
            f"• VIP Plan Target: <code>{info['vip_target']} ယောက်</code> (5,000 Ks တန်ဖိုး)\n"
            "────────────────────\n"
            f"• သင့် Referral အရေအတွက်: <code>{refs}</code> ယောက် (<code>{info['earned_ks']:,} Ks</code>)\n"
            f"• Pro ရရှိပြီး/လိုသေး: <code>{info['pro_unlocked']}</code> ကြိမ် / လိုသေး <code>{info['to_next_pro']}</code> ယောက်\n"
            f"• VIP ရရှိပြီး/လိုသေး: <code>{info['vip_unlocked']}</code> ကြိမ် / လိုသေး <code>{info['to_next_vip']}</code> ယောက်\n\n"
            f"🔗 သင့် Invite Link:\n<code>{ref_link}</code>"
        )
        bot.edit_message_text(
            text, chat_id, msg_id, reply_markup=build_main_menu_keyboard(uid)
        )
        return

    if data == "user_buy_plan":
        text = (
            "💳 <b>Plan ဝယ်ယူရန် အချက်အလက်များ</b>\n"
            f"• Pro Price: <code>{cfg.get('pro_price', '')}</code>\n"
            f"• VIP Price: <code>{cfg.get('vip_price', '')}</code>\n"
            f"• KPay: <code>{cfg.get('kpay', '')}</code>\n"
            f"• Wave: <code>{cfg.get('wave', '')}</code>\n"
            f"• Support: <code>{cfg.get('support', '')}</code>"
        )
        bot.edit_message_text(
            text, chat_id, msg_id, reply_markup=build_main_menu_keyboard(uid)
        )
        return

    if data == "user_notifications":
        notifs = cfg.get("notifications") or {}
        text = (
            "📩 <b>Notification Messages</b>\n"
            f"• Welcome: {notifs.get('welcome', '')}\n"
            f"• Plan Update: {notifs.get('plan_update', '')}"
        )
        bot.edit_message_text(
            text, chat_id, msg_id, reply_markup=build_main_menu_keyboard(uid)
        )
        return

    if data == "user_support":
        prompt_txt = cfg.get("notifications", {}).get(
            "support_prompt", DEFAULT_CONFIG["notifications"]["support_prompt"]
        )
        USER_STATES[uid] = {"action": "user_support_msg"}
        bot.send_message(
            chat_id,
            f"🛟 <b>Support</b> ({cfg.get('support', '')})\n{prompt_txt}\n\n(ပယ်ဖျက်ရန် <code>/cancel</code> ရိုက်ပါ)",
        )
        return

    # --- Owner Panel ---
    if not _is_owner(uid):
        bot.send_message(chat_id, "⛔ Owner သာ လုပ်ဆောင်နိုင်ပါသည်။")
        return

    if data == "owner_panel":
        USER_STATES.pop(uid, None)
        bot.edit_message_text(
            f"👑 <b>Owner Control Panel</b>\n\n{format_settings_summary(cfg)}",
            chat_id,
            msg_id,
            reply_markup=build_owner_panel_keyboard(cfg),
        )
        return

    if data == "view_settings":
        bot.edit_message_text(
            format_settings_summary(cfg),
            chat_id,
            msg_id,
            reply_markup=build_owner_panel_keyboard(cfg),
        )
        return

    if data == "menu_ref_targets":
        bot.edit_message_text(
            "🎯 <b>Pro & VIP Referral Target ဆက်တင်များ</b>\n"
            f"• တစ်ယောက်ဖိတ်ခေါ် နှုန်းထား: <code>{cfg.get('ref_rate_ks', 250)} Ks</code>\n"
            f"• Pro Target: <code>{cfg.get('pro_ref_target', 12)} ယောက်</code>\n"
            f"• VIP Target: <code>{cfg.get('vip_ref_target', 20)} ယောက်</code>",
            chat_id,
            msg_id,
            reply_markup=build_ref_targets_keyboard(cfg),
        )
        return

    if data == "menu_user_control":
        USER_STATES.pop(uid, None)
        bot.edit_message_text(
            "👥 <b>User Control Panel</b>\nUser များကို စစ်ဆေးခြင်း၊ Ban/Unban လုပ်ခြင်း၊ Plan (Free/Pro/VIP) သတ်မှတ်ခြင်းနှင့် App ချိတ်ဆက်မှု စီမံနိုင်ပါသည်။",
            chat_id,
            msg_id,
            reply_markup=build_user_control_keyboard(),
        )
        return

    if data == "uc_list_users":
        users = cfg.get("users") or {}
        if not users:
            bot.edit_message_text(
                "📋 User မှတ်တမ်း မရှိသေးပါ။",
                chat_id,
                msg_id,
                reply_markup=build_user_control_keyboard(),
            )
            return
        lines = ["📋 <b>User စာရင်း (နောက်ဆုံး ၁၅ ယောက်):</b>"]
        for u_key, u_val in list(users.items())[-15:]:
            if not isinstance(u_val, dict):
                continue
            p = str(u_val.get("plan", "free")).upper()
            app_flg = "🔗App" if u_val.get("app_linked") else "NoApp"
            ban_flg = "🚫Ban" if u_val.get("banned") else "OK"
            r_cnt = u_val.get("referrals", 0)
            lines.append(f"• <code>{u_key}</code> | <b>{p}</b> | {app_flg} | {ban_flg} | Ref:{r_cnt}")
        bot.edit_message_text(
            "\n".join(lines),
            chat_id,
            msg_id,
            reply_markup=build_user_control_keyboard(),
        )
        return

    if data == "menu_notifications":
        USER_STATES.pop(uid, None)
        notifs = cfg.get("notifications") or {}
        text = (
            "🔔 <b>Notification Message စီမံခန့်ခွဲမှု</b>\n"
            f"• Welcome: <code>{notifs.get('welcome', '')}</code>\n"
            f"• Support Prompt: <code>{notifs.get('support_prompt', '')}</code>\n"
            f"• Plan Update: <code>{notifs.get('plan_update', '')}</code>"
        )
        bot.edit_message_text(
            text,
            chat_id,
            msg_id,
            reply_markup=build_notifications_menu_keyboard(),
        )
        return

    if data.startswith("setplan_"):
        parts = data.split("_")
        if len(parts) == 3 and parts[1].isdigit():
            target_uid = int(parts[1])
            chosen_plan = parts[2]
            ok, _ = set_user_plan(target_uid, chosen_plan)
            if ok:
                plan_notice = cfg.get("notifications", {}).get(
                    "plan_update", DEFAULT_CONFIG["notifications"]["plan_update"]
                )
                try:
                    bot.send_message(
                        target_uid,
                        f"🔔 {plan_notice}\n• လက်ရှိ Plan: <b>{chosen_plan.upper()}</b>",
                    )
                except Exception:
                    pass
                bot.edit_message_text(
                    f"✅ User <code>{target_uid}</code> ရဲ့ Plan ကို <b>{chosen_plan.upper()}</b> ပြောင်းလဲပြီးပါပြီ။\n\n{format_user_detail(get_config(), target_uid)}",
                    chat_id,
                    msg_id,
                    reply_markup=build_user_control_keyboard(),
                )
            else:
                bot.send_message(chat_id, "❌ Plan သိမ်းဆည်းရာတွင် အမှားဖြစ်ပွားပါသည်။")
        return

    prompt_map = {
        "edit_kpay": ("edit_config_key", "kpay", "KPay အချက်အလက်အသစ် ရိုက်ထည့်ပါ:"),
        "edit_wave": ("edit_config_key", "wave", "Wave အချက်အလက်အသစ် ရိုက်ထည့်ပါ:"),
        "edit_pro_price": ("edit_config_key", "pro_price", "Pro Price အသစ် ရိုက်ထည့်ပါ:"),
        "edit_vip_price": ("edit_config_key", "vip_price", "VIP Price အသစ် ရိုက်ထည့်ပါ:"),
        "edit_support": ("edit_config_key", "support", "Support username/link အသစ် ရိုက်ထည့်ပါ:"),
        "edit_ref_rate_ks": ("edit_int_key", "ref_rate_ks", "တစ်ယောက်ဖိတ်ခေါ် Ks နှုန်းထား ရိုက်ထည့်ပါ (ဥပမာ- 250):"),
        "edit_pro_ref_target": ("edit_int_key", "pro_ref_target", "Pro Plan အတွက် လိုအပ်မည့် ဖိတ်ခေါ်သူ အရေအတွက် ရိုက်ထည့်ပါ (ဥပမာ- 12):"),
        "edit_vip_ref_target": ("edit_int_key", "vip_ref_target", "VIP Plan အတွက် လိုအပ်မည့် ဖိတ်ခေါ်သူ အရေအတွက် ရိုက်ထည့်ပါ (ဥပမာ- 20):"),
        "edit_notif_welcome": ("edit_notif_key", "welcome", "Welcome Notification စာသားအသစ် ရိုက်ထည့်ပါ:"),
        "edit_notif_support_prompt": ("edit_notif_key", "support_prompt", "Support Prompt စာသားအသစ် ရိုက်ထည့်ပါ:"),
        "edit_notif_plan_update": ("edit_notif_key", "plan_update", "Plan Update Notification စာသားအသစ် ရိုက်ထည့်ပါ:"),
        "start_broadcast": ("broadcast_msg", None, "📢 User များထံ ပို့လိုသော Notification / Broadcast မက်ဆေ့ချ် ရိုက်ထည့်ပါ:"),
        "uc_inspect_user": ("uc_inspect", None, "🔍 စစ်ဆေးလိုသော User ID ကို ရိုက်ထည့်ပါ:"),
        "uc_ban_user": ("uc_ban", None, "🚫 Ban လုပ်လိုသော User ID ကို ရိုက်ထည့်ပါ:"),
        "uc_unban_user": ("uc_unban", None, "✅ Unban လုပ်လိုသော User ID ကို ရိုက်ထည့်ပါ:"),
        "uc_set_plan": ("uc_pick_plan", None, "📦 Plan ပြောင်းလဲလိုသော User ID ကို ရိုက်ထည့်ပါ:"),
        "uc_set_app_link": ("uc_app_link", None, "🔗 App Link သတ်မှတ်ရန် <code>USER_ID APP_ACCOUNT_ID</code> (သို့မဟုတ် <code>USER_ID unlink</code>) ပုံစံဖြင့် ရိုက်ထည့်ပါ:"),
    }

    if data in prompt_map:
        action, key, prompt_msg = prompt_map[data]
        USER_STATES[uid] = {"action": action, "key": key}
        bot.send_message(chat_id, f"{prompt_msg}\n\n(ပယ်ဖျက်ရန် <code>/cancel</code> ရိုက်ပါ)")
# --- အပိုင်း (၅): Text Input, Broadcast, Commands & Bot Polling Runner ---
@bot.message_handler(commands=["cancel"])
def handle_cancel(message: telebot.types.Message):
    uid = message.from_user.id
    USER_STATES.pop(uid, None)
    bot.send_message(
        message.chat.id,
        "❌ လုပ်ဆောင်ချက်ကို ပယ်ဖျက်လိုက်ပါပြီ။",
        reply_markup=build_main_menu_keyboard(uid),
    )


@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text_input(message: telebot.types.Message):
    uid = message.from_user.id
    chat_id = message.chat.id
    text_in = (message.text or "").strip()

    username = message.from_user.username or ""
    full_name = " ".join(
        filter(None, [message.from_user.first_name, message.from_user.last_name])
    )
    register_or_update_user(uid, username=username, full_name=full_name)
    cfg = get_config()

    if _is_banned(cfg, uid):
        bot.send_message(chat_id, "🚫 သင့်အကောင့်ကို ပိတ်ပင်ထားပါသည်။")
        return

    state = USER_STATES.get(uid)
    if not state:
        bot.send_message(
            chat_id,
            "Menu ကို ဖွင့်ရန် <code>/start</code> (သို့မဟုတ်) ခလုတ်များကို အသုံးပြုပါ။",
            reply_markup=build_main_menu_keyboard(uid),
        )
        return

    action = state.get("action")
    key = state.get("key")

    # --- User Flows ---
    if action == "user_link_app_input":
        USER_STATES.pop(uid, None)
        if text_in.lower() == "unlink":
            ok, _ = set_user_app_link(uid, False, "")
            msg = "✅ App ချိတ်ဆက်မှုကို ဖြုတ်လိုက်ပါပြီ။" if ok else "❌ သိမ်းဆည်းရာတွင် အမှားဖြစ်ပွားပါသည်။"
        else:
            ok, _ = set_user_app_link(uid, True, text_in)
            msg = (
                f"✅ App Account ID <code>{text_in}</code> နှင့် ချိတ်ဆက်ပြီးပါပြီ။"
                if ok
                else "❌ သိမ်းဆည်းရာတွင် အမှားဖြစ်ပွားပါသည်။"
            )
        bot.send_message(chat_id, msg, reply_markup=build_main_menu_keyboard(uid))
        return

    if action == "user_support_msg":
        USER_STATES.pop(uid, None)
        if OWNER_ID != 0:
            try:
                uname_str = f"@{username}" if username else "no_username"
                bot.send_message(
                    OWNER_ID,
                    f"📩 <b>Support Message</b>\n• From: <code>{uid}</code> ({uname_str})\n• Name: <code>{full_name}</code>\n\n{text_in}",
                )
            except Exception as e:
                logger.error(f"Forward support msg failed: {e}")
        bot.send_message(
            chat_id,
            "✅ သင့်မက်ဆေ့ချ်ကို Admin ထံ ပေးပို့ပြီးပါပြီ။",
            reply_markup=build_main_menu_keyboard(uid),
        )
        return

    # --- Owner Only Flows ---
    if not _is_owner(uid):
        USER_STATES.pop(uid, None)
        bot.send_message(chat_id, "⛔ Owner သာ လုပ်ဆောင်နိုင်ပါသည်။")
        return

    if action == "edit_config_key" and key:
        USER_STATES.pop(uid, None)
        if update_config_key(key, text_in):
            bot.send_message(
                chat_id,
                f"✅ <code>{key}</code> ကို အောင်မြင်စွာ ပြင်ဆင်သိမ်းဆည်းပြီးပါပြီ။",
                reply_markup=build_owner_panel_keyboard(get_config()),
            )
        else:
            bot.send_message(chat_id, "❌ Supabase ထဲ သိမ်းဆည်းရာတွင် အမှားဖြစ်ပွားပါသည်။")
        return

    if action == "edit_int_key" and key:
        if not text_in.isdigit() or int(text_in) <= 0:
            bot.send_message(chat_id, "⚠️ 0 ထက်ကြီးသော ဂဏန်းသက်သက် ရိုက်ထည့်ပေးပါ။")
            return
        USER_STATES.pop(uid, None)
        val = int(text_in)
        if update_config_key(key, val):
            bot.send_message(
                chat_id,
                f"✅ <code>{key}</code> ကို <code>{val}</code> ဟု ပြင်ဆင်ပြီးပါပြီ။",
                reply_markup=build_owner_panel_keyboard(get_config()),
            )
        else:
            bot.send_message(chat_id, "❌ Supabase ထဲ သိမ်းဆည်းရာတွင် အမှားဖြစ်ပွားပါသည်။")
        return

    if action == "edit_notif_key" and key:
        USER_STATES.pop(uid, None)
        notifs = cfg.setdefault("notifications", {})
        notifs[key] = text_in
        if save_config(cfg):
            bot.send_message(
                chat_id,
                f"✅ Notification (<code>{key}</code>) ကို သိမ်းဆည်းပြီးပါပြီ။",
                reply_markup=build_notifications_menu_keyboard(),
            )
        else:
            bot.send_message(chat_id, "❌ Notification သိမ်းဆည်းရာတွင် အမှားဖြစ်ပွားပါသည်။")
        return

    if action == "broadcast_msg":
        USER_STATES.pop(uid, None)
        users = cfg.get("users") or {}
        sent_ok = 0
        sent_fail = 0
        for u_key, u_val in users.items():
            if not u_key.isdigit():
                continue
            target_id = int(u_key)
            if isinstance(u_val, dict) and u_val.get("banned"):
                continue
            try:
                bot.send_message(target_id, f"📢 <b>Notification</b>\n\n{text_in}")
                sent_ok += 1
            except Exception:
                sent_fail += 1
        bot.send_message(
            chat_id,
            f"📢 Broadcast ပြီးစီးပါပြီ။\n• ပို့ပြီး: <code>{sent_ok}</code> ယောက်\n• မရောက်သေး/ပိတ်ထား: <code>{sent_fail}</code> ယောက်",
            reply_markup=build_owner_panel_keyboard(get_config()),
        )
        return

    if action in ("uc_inspect", "uc_ban", "uc_unban", "uc_pick_plan"):
        if not text_in.isdigit():
            bot.send_message(chat_id, "⚠️ မှန်ကန်သော User ID (ဂဏန်း) ရိုက်ထည့်ပေးပါ။")
            return
        target_uid = int(text_in)
        USER_STATES.pop(uid, None)

        if action == "uc_inspect":
            bot.send_message(
                chat_id,
                format_user_detail(cfg, target_uid),
                reply_markup=build_user_control_keyboard(),
            )
        elif action == "uc_ban":
            ok, _ = set_user_ban(target_uid, True)
            bot.send_message(
                chat_id,
                f"🚫 User <code>{target_uid}</code> ကို Ban လုပ်ပြီးပါပြီ။" if ok else "❌ Ban လုပ်ရာတွင် အမှားဖြစ်ပွားပါသည်။",
                reply_markup=build_user_control_keyboard(),
            )
        elif action == "uc_unban":
            ok, _ = set_user_ban(target_uid, False)
            bot.send_message(
                chat_id,
                f"✅ User <code>{target_uid}</code> ကို Unban ပြန်ဖွင့်ပြီးပါပြီ။" if ok else "❌ Unban လုပ်ရာတွင် အမှားဖြစ်ပွားပါသည်။",
                reply_markup=build_user_control_keyboard(),
            )
        elif action == "uc_pick_plan":
            bot.send_message(
                chat_id,
                f"📦 User <code>{target_uid}</code> အတွက် Plan ရွေးချယ်ပါ:\n\n{format_user_detail(cfg, target_uid)}",
                reply_markup=build_plan_select_keyboard(target_uid),
            )
        return

    if action == "uc_app_link":
        parts = text_in.split(maxsplit=1)
        if len(parts) < 2 or not parts[0].isdigit():
            bot.send_message(
                chat_id,
                "⚠️ ပုံစံမှန် ရိုက်ထည့်ပါ — ဥပမာ: <code>123456789 APP_ID_01</code> သို့မဟုတ် <code>123456789 unlink</code>",
            )
            return
        target_uid = int(parts[0])
        arg2 = parts[1].strip()
        USER_STATES.pop(uid, None)

        if arg2.lower() == "unlink":
            ok, _ = set_user_app_link(target_uid, False, "")
            status_txt = f"🔗 User <code>{target_uid}</code> ရဲ့ App ချိတ်ဆက်မှု ဖြုတ်ပြီးပါပြီ။"
        else:
            ok, _ = set_user_app_link(target_uid, True, arg2)
            status_txt = f"🔗 User <code>{target_uid}</code> ကို App Account <code>{arg2}</code> နှင့် ချိတ်ဆက်ပြီးပါပြီ။"

        bot.send_message(
            chat_id,
            (status_txt if ok else "❌ App Link သိမ်းဆည်းရာတွင် အမှားဖြစ်ပွားပါသည်။")
            + f"\n\n{format_user_detail(get_config(), target_uid)}",
            reply_markup=build_user_control_keyboard(),
        )
        return


def main():
    logger.info("Bot is starting with Supabase config...")
    bot.infinity_polling(skip_pending=True)


if __name__ == "__main__":
    main()
