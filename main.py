import asyncio
from datetime import datetime, timezone
import json
import os
from typing import Any, Dict, Optional
from aiohttp import web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

# ==============================================================================
# 1. CONFIGURATION (Hardcoded Topic ID 99)
# ==============================================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8909534863:AAEck21ljGacrRR_e4mUZQmGKqeH4tVAqwU").strip()
if not BOT_TOKEN:
  raise RuntimeError("BOT_TOKEN environment variable is required.")


def _parse_int(env_name: str, default: int) -> int:
  raw = os.getenv(env_name, str(default)).strip()
  try:
    return int(raw)
  except ValueError:
    return default


OWNER_ID = _parse_int("OWNER_ID", 8415289516)
ADMIN_GROUP_ID = _parse_int("ADMIN_GROUP_ID", -1004448651266)

# Hardcoded Topic ID as requested
ADMIN_TOPIC_ID = 99

REFERRAL_DISCOUNT_AMOUNT = _parse_int("REFERRAL_DISCOUNT_AMOUNT", 250)
PORT = _parse_int("PORT", 8080)
DATA_FILE = os.getenv("DATA_FILE", "bot_data.json").strip() or "bot_data.json"
WEBAPP_URL = os.getenv("WEBAPP_URL", "").strip()
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()

BTN_PROFILE = "👤 Profile"
BTN_BUY_PLAN = "💎 Buy Plan"
BTN_REFERRAL = "👥 Referral"
BTN_SUPPORT = "💬 Support"
BTN_ADMIN_MSG = "✉️ Admin Group သို့ စာပို့မည်"

DEFAULT_PLANS: Dict[str, Dict[str, Any]] = {
    "plan_1m": {
        "id": "plan_1m",
        "name": "1 Month Plan",
        "price": 5000,
        "duration_days": 30,
        "description": "30 days access",
    },
    "plan_3m": {
        "id": "plan_3m",
        "name": "3 Months Plan",
        "price": 13500,
        "duration_days": 90,
        "description": "90 days access",
    },
}

DEFAULT_TEMPLATES: Dict[str, str] = {
    "welcome": (
        "မင်္ဂလာပါ {name}! 👋\n"
        "အောက်ပါ Menu ခလုတ်များကို နှိပ်၍ အသုံးပြုနိုင်ပါသည်။"
    ),
    "menu_prompt": "အောက်ပါ Menu ခလုတ်များကို နှိပ်၍ အသုံးပြုနိုင်ပါသည်။",
    "support": (
        "💬 **Support**\n"
        "Admin Group သို့ စာပို့လိုပါက **✉️ Admin Group သို့ စာပို့မည်**"
        " ခလုတ်ကို နှိပ်၍ ပို့နိုင်ပါသည်။"
    ),
    "admin_prompt": (
        "✉️ **Admin Group သို့ စာပို့မည်**\n"
        "Admin Group သို့ ပို့လိုသော စာကို ရိုက်ထည့်ပေးပါ။\n"
        "(ပယ်ဖျက်လိုပါက `/cancel` ဟု ရိုက်ပါ)"
    ),
    "admin_sent": "✅ သင့်စာကို Admin Group သို့ ပို့ပေးပြီးပါပြီ။",
    "admin_cancelled": "❌ Admin Group သို့ စာပို့ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီ။",
    "admin_not_configured": (
        "⚠️ Admin Group ID (`ADMIN_GROUP_ID`) မသတ်မှတ်ရသေးပါ။"
    ),
    "admin_send_failed": (
        "⚠️ Admin Group သို့ စာပို့ရာတွင် အမှားအယွင်း ဖြစ်သွားပါသည်: {error}"
    ),
}


# ==============================================================================
# 2. DATA PERSISTENCE (bot_data.json)
# ==============================================================================
def _default_store() -> Dict[str, Any]:
  return {
      "users": {},
      "referrals": {},
      "redeemed_referrals": [],
      "plans": dict(DEFAULT_PLANS),
      "templates": dict(DEFAULT_TEMPLATES),
      "orders": [],
  }


def load_data(path: str = DATA_FILE) -> Dict[str, Any]:
  base = _default_store()
  if not os.path.exists(path):
    save_data(base, path)
    return base
  try:
    with open(path, "r", encoding="utf-8") as f:
      loaded = json.load(f)
    if not isinstance(loaded, dict):
      return base
    for k, v in base.items():
      if k not in loaded or not isinstance(loaded[k], type(v)):
        loaded[k] = v
    merged_templates = dict(DEFAULT_TEMPLATES)
    merged_templates.update(loaded.get("templates", {}))
    loaded["templates"] = merged_templates
    if not loaded.get("plans"):
      loaded["plans"] = dict(DEFAULT_PLANS)
    return loaded
  except Exception:
    return base


def save_data(data: Dict[str, Any], path: str = DATA_FILE) -> None:
  directory = os.path.dirname(os.path.abspath(path))
  if directory and not os.path.exists(directory):
    os.makedirs(directory, exist_ok=True)
  tmp_path = f"{path}.tmp"
  with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
  os.replace(tmp_path, path)


DB: Dict[str, Any] = load_data()


def ensure_user(
    user_id: int,
    first_name: str = "User",
    username: Optional[str] = None,
    referred_by: Optional[int] = None,
) -> Dict[str, Any]:
  uid_str = str(user_id)
  users = DB["users"]
  now_iso = datetime.now(timezone.utc).isoformat()

  if uid_str not in users:
    users[uid_str] = {
        "user_id": user_id,
        "first_name": first_name or "User",
        "username": username or "",
        "discount_balance": 0,
        "subscription": {
            "active": False,
            "plan_name": "None",
            "expires_at": None,
            "source": None,
        },
        "referred_by": None,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
  else:
    users[uid_str]["first_name"] = first_name or users[uid_str].get(
        "first_name", "User"
    )
    if username is not None:
      users[uid_str]["username"] = username
    users[uid_str]["updated_at"] = now_iso

  if referred_by and referred_by != user_id:
    ref_str = str(referred_by)
    redeemed_list = DB["redeemed_referrals"]
    ref_map = DB["referrals"]
    ref_map.setdefault(ref_str, [])

    if (
        user_id not in redeemed_list
        and users[uid_str].get("referred_by") is None
        and ref_str in users
    ):
      users[uid_str]["referred_by"] = referred_by
      redeemed_list.append(user_id)
      if user_id not in ref_map[ref_str]:
        ref_map[ref_str].append(user_id)
      users[ref_str]["discount_balance"] = (
          int(users[ref_str].get("discount_balance", 0))
          + REFERRAL_DISCOUNT_AMOUNT
      )
      users[ref_str]["updated_at"] = now_iso

  save_data(DB)
  return users[uid_str]


def get_referral_count(user_id: int) -> int:
  return len(DB["referrals"].get(str(user_id), []))


def get_discount_balance(user_id: int) -> int:
  u = DB["users"].get(str(user_id))
  if not u:
    return 0
  return int(u.get("discount_balance", 0))


def consume_discount(user_id: int, amount: int) -> int:
  u = DB["users"].get(str(user_id))
  if not u or amount <= 0:
    return 0
  current = int(u.get("discount_balance", 0))
  used = min(current, amount)
  u["discount_balance"] = current - used
  u["updated_at"] = datetime.now(timezone.utc).isoformat()
  save_data(DB)
  return used


def is_owner(user_id: int) -> bool:
  return OWNER_ID != 0 and user_id == OWNER_ID


def render_template(key: str, **kwargs: Any) -> str:
  raw = DB["templates"].get(key) or DEFAULT_TEMPLATES.get(key, "")
  try:
    return raw.format(**kwargs)
  except Exception:
    return raw


def main_menu_keyboard() -> ReplyKeyboardMarkup:
  return ReplyKeyboardMarkup(
      keyboard=[
          [KeyboardButton(text=BTN_PROFILE), KeyboardButton(text=BTN_BUY_PLAN)],
          [KeyboardButton(text=BTN_REFERRAL), KeyboardButton(text=BTN_SUPPORT)],
          [KeyboardButton(text=BTN_ADMIN_MSG)],
      ],
      resize_keyboard=True,
      is_persistent=True,
      input_field_placeholder="Menu ခလုတ်များကို ရွေးချယ်ပါ...",
)
# ==============================================================================
# 3. FSM STATES & ROUTER
# ==============================================================================
router = Router()


class BotStates(StatesGroup):
  waiting_admin_group_message = State()
  waiting_broadcast_message = State()
  waiting_template_value = State()
  waiting_discount_adjust = State()


# ------------------------------------------------------------------------------
# /start, /cancel & Persistent Menu
# ------------------------------------------------------------------------------
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot: Bot) -> None:
  await state.clear()
  user = message.from_user
  if not user:
    return

  referred_by: Optional[int] = None
  parts = (message.text or "").split(maxsplit=1)
  if len(parts) == 2 and parts[1].strip():
    payload = parts[1].strip()
    if payload.startswith("ref_"):
      payload = payload[4:]
    if payload.isdigit():
      referred_by = int(payload)

  record = ensure_user(
      user_id=user.id,
      first_name=user.first_name or "User",
      username=user.username,
      referred_by=referred_by,
  )

  if (
      referred_by
      and referred_by != user.id
      and record.get("referred_by") == referred_by
  ):
    ref_uid_str = str(referred_by)
    if ref_uid_str in DB["users"]:
      try:
        await bot.send_message(
            chat_id=referred_by,
            text=(
                f"🎉 Referral အသစ်ရရှိပါပြီ!\n"
                f"• User: {user.first_name} (`{user.id}`)\n"
                f"• Discount ထပ်တိုး: +{REFERRAL_DISCOUNT_AMOUNT}\n"
                f"• လက်ကျန် Discount: {get_discount_balance(referred_by)}"
            ),
        )
      except Exception:
        pass

  text = render_template(
      "welcome",
      name=user.first_name or "User",
      user_id=user.id,
      discount=get_discount_balance(user.id),
      referrals=get_referral_count(user.id),
  )
  await message.answer(text, reply_markup=main_menu_keyboard())


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
  current_state = await state.get_state()
  await state.clear()
  if current_state == BotStates.waiting_admin_group_message.state:
    await message.answer(
        render_template("admin_cancelled"), reply_markup=main_menu_keyboard()
    )
  else:
    await message.answer(
        "❌ လုပ်ဆောင်ချက်ကို ပယ်ဖျက်လိုက်ပါပြီ။",
        reply_markup=main_menu_keyboard(),
    )


# ------------------------------------------------------------------------------
# Profile, Buy Plan, Referral & Support (Topic 99 Applied)
# ------------------------------------------------------------------------------
@router.message(F.text == BTN_PROFILE)
async def on_profile(message: Message, state: FSMContext) -> None:
  await state.clear()
  user = message.from_user
  if not user:
    return
  u = ensure_user(user.id, user.first_name or "User", user.username)
  sub = u.get("subscription", {})
  status_txt = "Active ✅" if sub.get("active") else "Inactive ❌"
  plan_txt = sub.get("plan_name", "None")
  exp_txt = sub.get("expires_at") or "-"
  ref_count = get_referral_count(user.id)
  discount = get_discount_balance(user.id)

  lines = [
      "👤 **User Profile**",
      f"• Name: {user.first_name or 'User'}",
      f"• Username: @{user.username}" if user.username else "• Username: -",
      f"• Telegram ID: `{user.id}`",
      f"• Subscription: {status_txt} ({plan_txt})",
      f"• Expires At: `{exp_txt}`",
      f"• Referrals: {ref_count} ယောက်",
      f"• Available Discount: {discount}",
  ]
  if WEBAPP_URL:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="🌐 Open Web App", web_app=WebAppInfo(url=WEBAPP_URL)
            )
        ]]
    )
    await message.answer("\n".join(lines), reply_markup=kb)
  else:
    await message.answer("\n".join(lines), reply_markup=main_menu_keyboard())


@router.message(F.text == BTN_BUY_PLAN)
async def on_buy_plan(message: Message, state: FSMContext) -> None:
  await state.clear()
  user = message.from_user
  if not user:
    return
  ensure_user(user.id, user.first_name or "User", user.username)
  discount = get_discount_balance(user.id)

  rows = []
  detail_lines = [
      "💎 **Subscription Plans**",
      f"• သင့် Discount Balance: **{discount}**",
      "",
  ]
  for plan_id, plan in DB["plans"].items():
    base_price = int(plan.get("price", 0))
    final_price = max(0, base_price - discount)
    p_name = plan.get("name", plan_id)
    detail_lines.append(
        f"• **{p_name}**: {base_price} → **{final_price}**"
        f" ({plan.get('duration_days', 30)}d)"
    )
    rows.append([
        InlineKeyboardButton(
            text=f"Buy {p_name} ({final_price})",
            callback_data=f"buy_plan:{plan_id}",
        )
    ])

  await message.answer(
      "\n".join(detail_lines),
      reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
  )


@router.callback_query(F.data.startswith("buy_plan:"))
async def cb_buy_plan(callback: CallbackQuery, bot: Bot) -> None:
  await callback.answer()
  user = callback.from_user
  if not user or not callback.message:
    return
  plan_id = (callback.data or "").split(":", 1)[1]
  plan = DB["plans"].get(plan_id)
  if not plan:
    await callback.message.answer("⚠️ Plan မတွေ့ပါ။")
    return

  ensure_user(user.id, user.first_name or "User", user.username)
  base_price = int(plan.get("price", 0))
  available_disc = get_discount_balance(user.id)
  used_disc = consume_discount(user.id, base_price)
  final_price = max(0, base_price - used_disc)

  order = {
      "order_id": f"ORD-{user.id}-{int(datetime.now(timezone.utc).timestamp())}",
      "user_id": user.id,
      "username": user.username or "",
      "plan_id": plan_id,
      "plan_name": plan.get("name", plan_id),
      "base_price": base_price,
      "discount_used": used_disc,
      "final_price": final_price,
      "status": "pending",
      "created_at": datetime.now(timezone.utc).isoformat(),
  }
  DB["orders"].append(order)
  save_data(DB)

  await callback.message.answer(
      f"🛒 **Order Created**\n"
      f"• Order ID: `{order['order_id']}`\n"
      f"• Plan: {order['plan_name']}\n"
      f"• Original Price: {base_price}\n"
      f"• Discount Applied: -{used_disc}"
      f" (Remaining: {available_disc - used_disc})\n"
      f"• Total Payable: **{final_price}**\n\n"
      "Payment အတည်ပြုရန် **✉️ Admin Group သို့ စာပို့မည်** ခလုတ်မှ"
      " Order ID ကို ပို့ပေးပါ။"
  )

  # Hardcoded Topic 99 applied here
  if ADMIN_GROUP_ID != 0:
    try:
      uname = f"@{user.username}" if user.username else "No username"
      await bot.send_message(
          chat_id=ADMIN_GROUP_ID,
          text=(
              "🆕 **New Plan Order**\n"
              f"• Order ID: `{order['order_id']}`\n"
              f"• User: {user.first_name} ({uname}) / `{user.id}`\n"
              f"• Plan: {order['plan_name']}\n"
              f"• Discount Used: {used_disc}\n"
              f"• Final Amount: {final_price}"
          ),
          message_thread_id=ADMIN_TOPIC_ID,
      )
    except Exception:
      pass


@router.message(F.text == BTN_REFERRAL)
async def on_referral(message: Message, state: FSMContext, bot: Bot) -> None:
  await state.clear()
  user = message.from_user
  if not user:
    return
  ensure_user(user.id, user.first_name or "User", user.username)
  me = await bot.get_me()
  bot_username = me.username or ""
  ref_link = (
      f"https://t.me/{bot_username}?start=ref_{user.id}"
      if bot_username
      else f"/start ref_{user.id}"
  )
  ref_count = get_referral_count(user.id)
  discount = get_discount_balance(user.id)

  await message.answer(
      f"👥 **Referral Program**\n"
      f"• ဖိတ်ခေါ်သူတစ်ဦးလျှင် Discount: **+{REFERRAL_DISCOUNT_AMOUNT}**\n"
      f"• သင့် Referral အရေအတွက်: **{ref_count}** ယောက်\n"
      f"• လက်ကျန် Discount: **{discount}**\n\n"
      f"🔗 သင့် Referral Link:\n`{ref_link}`",
      reply_markup=main_menu_keyboard(),
  )


@router.message(F.text == BTN_SUPPORT)
async def on_support(message: Message, state: FSMContext) -> None:
  await state.clear()
  user = message.from_user
  if user:
    ensure_user(user.id, user.first_name or "User", user.username)
  await message.answer(
      render_template("support"), reply_markup=main_menu_keyboard()
  )


# ------------------------------------------------------------------------------
# Admin Group Only Message Button Flow (Hardcoded Topic 99 Targeted)
# ------------------------------------------------------------------------------
@router.message(F.text == BTN_ADMIN_MSG)
async def on_admin_group_button(message: Message, state: FSMContext) -> None:
  user = message.from_user
  if not user:
    return
  ensure_user(user.id, user.first_name or "User", user.username)
  if ADMIN_GROUP_ID == 0:
    await message.answer(
        render_template("admin_not_configured"),
        reply_markup=main_menu_keyboard(),
    )
    return
  await state.set_state(BotStates.waiting_admin_group_message)
  await message.answer(
      render_template("admin_prompt"), reply_markup=main_menu_keyboard()
  )


@router.message(BotStates.waiting_admin_group_message, F.text)
async def send_to_admin_group_only(
    message: Message, state: FSMContext, bot: Bot
) -> None:
  user = message.from_user
  if not user:
    return
  raw_text = (message.text or "").strip()
  if raw_text.lower() == "/cancel":
    await state.clear()
    await message.answer(
        render_template("admin_cancelled"), reply_markup=main_menu_keyboard()
    )
    return

  if ADMIN_GROUP_ID == 0:
    await state.clear()
    await message.answer(
        render_template("admin_not_configured"),
        reply_markup=main_menu_keyboard(),
    )
    return

  uname = f"@{user.username}" if user.username else "No username"
  payload_text = (
      "📨 **Message to Admin Group**\n"
      f"• **From:** {user.first_name or 'User'} ({uname})\n"
      f"• **User ID:** `{user.id}`\n"
      "━━━━━━━━━━━━━━\n"
      f"{raw_text}"
  )

  try:
    # Strictly targets Topic 99 inside ADMIN_GROUP_ID
    await bot.send_message(
        chat_id=ADMIN_GROUP_ID,
        text=payload_text,
        message_thread_id=ADMIN_TOPIC_ID,
    )
    await state.clear()
    await message.answer(
        render_template("admin_sent"), reply_markup=main_menu_keyboard()
    )
  except Exception as exc:
    await state.clear()
    await message.answer(
        render_template("admin_send_failed", error=str(exc)),
        reply_markup=main_menu_keyboard(),
    )


# ------------------------------------------------------------------------------
# Owner Control Panel (/admin) & Dynamic Templates
# ------------------------------------------------------------------------------
def owner_panel_keyboard() -> InlineKeyboardMarkup:
  return InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="📊 Stats", callback_data="owner:stats"
              ),
              InlineKeyboardButton(
                  text="📢 Broadcast", callback_data="owner:broadcast"
              ),
          ],
          [
              InlineKeyboardButton(
                  text="📝 Edit Welcome Msg",
                  callback_data="owner:tpl:welcome",
              ),
              InlineKeyboardButton(
                  text="📝 Edit Support Msg",
                  callback_data="owner:tpl:support",
              ),
          ],
          [
              InlineKeyboardButton(
                  text="💰 Set User Discount",
                  callback_data="owner:set_discount",
              )
          ],
      ]
  )


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext) -> None:
  await state.clear()
  if not message.from_user or not is_owner(message.from_user.id):
    return
  await message.answer(
      "🛠 **Owner Control Panel**", reply_markup=owner_panel_keyboard()
  )


@router.callback_query(F.data.startswith("owner:"))
async def cb_owner_panel(callback: CallbackQuery, state: FSMContext) -> None:
  if not callback.from_user or not is_owner(callback.from_user.id):
    await callback.answer("Owner only.", show_alert=True)
    return
  await callba
# ==========================================
# PART 2: KEYBOARDS & BOT HANDLERS
# ==========================================


def build_main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Plan ဝယ်ယူရန်"), KeyboardButton(text="👤 Profile")],
            [KeyboardButton(text="ℹ️ အကူအညီ")],
        ],
        resize_keyboard=True,
    )


def build_plan_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Pro Plan (30 Days)", callback_data="plan:PRO:30"),
                InlineKeyboardButton(text="VIP Plan (30 Days)", callback_data="plan:VIP:30"),
            ],
            [InlineKeyboardButton(text="❌ ပယ်ဖျက်မည်", callback_data="plan:cancel")],
        ]
    )


def build_admin_review_keyboard(user_id: int, email: str, plan: str, days: int) -> InlineKeyboardMarkup:
    safe_token = f"{user_id}|{email}|{plan}|{days}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Approve", callback_data=f"adm_ok:{safe_token}"),
                InlineKeyboardButton(text="❌ Reject", callback_data=f"adm_no:{safe_token}"),
            ]
        ]
    )


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "မင်္ဂလာပါ <b>AYK Recap Bot</b> မှ ကြိုဆိုပါတယ်ခင်ဗျာ။\n"
        "အောက်ပါ Menu မှတစ်ဆင့် Plan ဝယ်ယူခြင်းနှင့် အခြားဝန်ဆောင်မှုများကို အသုံးပြုနိုင်ပါတယ်။",
        reply_markup=build_main_menu(),
    )


@router.message(Command("cancel"))
@router.message(F.text == "❌ ပယ်ဖျက်မည်")
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("လုပ်ဆောင်ချက်ကို ပယ်ဖျက်လိုက်ပါပြီ။", reply_markup=build_main_menu())


@router.message(F.text == "👤 Profile")
async def handle_profile(message: Message) -> None:
    user = message.from_user
    username_display = f"@{user.username}" if user and user.username else "မရှိပါ"
    await message.answer(
        f"👤 <b>User Profile</b>\n"
        f"• Name: {user.full_name if user else 'Unknown'}\n"
        f"• Telegram ID: <code>{user.id if user else 0}</code>\n"
        f"• Username: {username_display}",
        reply_markup=build_main_menu(),
    )


@router.message(F.text == "ℹ️ အကူအညီ")
async def handle_help(message: Message) -> None:
    await message.answer(
        "📌 <b>အသုံးပြုပုံ လမ်းညွှန်</b>\n"
        "1. <b>📦 Plan ဝယ်ယူရန်</b> ကို နှိပ်ပါ။\n"
        "2. App တွင် မှတ်ပုံတင်ထားသော <b>Email</b> ကို ထည့်ပါ။\n"
        "3. လိုချင်သော <b>Plan</b> ကို ရွေးချယ်ပြီး <b>ငွေလွှဲပြေစာ (Photo)</b> ပို့ပါ။\n"
        "4. Admin အတည်ပြုပြီးသည်နှင့် Plan အလိုအလျောက် Update ဖြစ်ပါမည်။",
        reply_markup=build_main_menu(),
    )


@router.message(F.text == "📦 Plan ဝယ်ယူရန်")
async def handle_buy_plan_start(message: Message, state: FSMContext) -> None:
    await state.set_state(SubscriptionStates.waiting_for_email)
    await message.answer(
        "ကျေးဇူးပြု၍ သင့် App Account တွင် အသုံးပြုထားသော <b>Email</b> လိပ်စာကို ရိုက်ထည့်ပေးပါ။\n"
        "(ပယ်ဖျက်လိုပါက /cancel သို့မဟုတ် ❌ ပယ်ဖျက်မည် ကို နှိပ်ပါ)",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(SubscriptionStates.waiting_for_email, F.text)
async def handle_email_input(message: Message, state: FSMContext) -> None:
    email = (message.text or "").strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        await message.answer("⚠️ Email ဖော်မက် မှားယွင်းနေပါသည်။ မှန်ကန်သော Email ကို ထပ်မံရိုက်ထည့်ပေးပါ။")
        return

    await state.update_data(email=email)
    await state.set_state(SubscriptionStates.waiting_for_plan)
    await message.answer(
        f"✅ Email: <code>{email}</code>\n\nကျေးဇူးပြု၍ ဝယ်ယူလိုသော Plan ကို ရွေးချယ်ပါ။",
        reply_markup=build_plan_keyboard(),
    )


@router.callback_query(SubscriptionStates.waiting_for_plan, F.data.startswith("plan:"))
async def handle_plan_selection(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data or not callback.message:
        return

    parts = callback.data.split(":")
    if len(parts) == 2 and parts[1] == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ Plan ဝယ်ယူမှုကို ပယ်ဖျက်လိုက်ပါပြီ။")
        await callback.message.answer("ပင်မ Menu သို့ ပြန်ရောက်ပါပြီ။", reply_markup=build_main_menu())
        await callback.answer()
        return

    if len(parts) != 4:
        await callback.answer("Invalid plan data.", show_alert=True)
        return

    _, plan_code, days_str = parts
    try:
        days = int(days_str)
    except ValueError:
        await callback.answer("Invalid duration.", show_alert=True)
        return

    await state.update_data(plan=plan_code.upper(), duration_days=days)
    await state.set_state(SubscriptionStates.waiting_for_proof)
    await callback.message.edit_text(
        f"📦 ရွေးချယ်ထားသော Plan: <b>{plan_code.upper()}</b> ({days} ရက်)\n\n"
        "ငွေလွှဲပြီးကြောင်း <b>Screenshot / ပြေစာ ဓာတ်ပုံ (Photo)</b> တစ်ပုံ ပို့ပေးပါ။"
    )
    await callback.answer()


@router.message(SubscriptionStates.waiting_for_proof, F.photo)
async def handle_payment_proof(message: Message, state: FSMContext, bot: Bot) -> None:
    user_data = await state.get_data()
    email = user_data.get("email")
    plan = user_data.get("plan")
    duration_days = user_data.get("duration_days", 30)

    if not email or not plan or not message.from_user or not message.photo:
        await message.answer("⚠️ အချက်အလက် မပြည့်စုံပါ။ /start ဖြင့် ပြန်လည်စတင်ပါ။", reply_markup=build_main_menu())
        await state.clear()
        return

    photo_file_id = message.photo[-1].file_id
    buyer = message.from_user
    buyer_mention = f"@{buyer.username}" if buyer.username else buyer.full_name

    caption = (
        "🧾 <b>New Subscription Payment Request</b>\n"
        f"• Buyer: {buyer_mention} (<code>{buyer.id}</code>)\n"
        f"• Email: <code>{email}</code>\n"
        f"• Plan: <b>{plan}</b> ({duration_days} days)\n"
        f"• Time: <code>{get_utc_now_iso()}</code>"
    )

    try:
        await bot.send_photo(
            chat_id=ADMIN_GROUP_ID,
            photo=photo_file_id,
            caption=caption,
            reply_markup=build_admin_review_keyboard(buyer.id, email, plan, int(duration_days)),
        )
        await state.clear()
        await message.answer(
            "✅ သင့်ငွေလွှဲပြေစာကို Admin ထံ ပို့ပြီးပါပြီ။ အတည်ပြုပြီးသည်နှင့် အကြောင်းကြားပေးပါမည်။",
            reply_markup=build_main_menu(),
        )
    except Exception as exc:
        await message.answer(
            f"⚠️ Admin Group သို့ ပို့ရာတွင် အခက်အခဲ ရှိနေပါသည်: <code>{exc}</code>",
            reply_markup=build_main_menu(),
        )


@router.message(SubscriptionStates.waiting_for_proof)
async def handle_non_photo_proof(message: Message) -> None:
    await message.answer("⚠️ ကျေးဇူးပြု၍ ငွေလွှဲပြေစာကို <b>ဓာတ်ပုံ (Photo)</b> အနေဖြင့်သာ ပို့ပေးပါ။")


@router.callback_query(F.data.startswith(("adm_ok:", "adm_no:")))
async def handle_admin_decision(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.data or not callback.message or not callback.from_user:
        return

    actor_id = callback.from_user.id
    if actor_id != OWNER_ID and callback.message.chat.id != ADMIN_GROUP_ID:
        await callback.answer("⛔ ခွင့်ပြုချက် မရှိပါ။", show_alert=True)
        return

    action, raw_payload = callback.data.split(":", 1)
    parts = raw_payload.split("|")
    if len(parts) != 4:
        await callback.answer("Invalid callback payload.", show_alert=True)
        return

    buyer_id_str, email, plan, days_str = parts
    try:
        buyer_id = int(buyer_id_str)
        duration_days = int(days_str)
    except ValueError:
        await callback.answer("Invalid numeric fields.", show_alert=True)
        return

    old_caption = callback.message.caption or ""

    if action == "adm_no":
        try:
            await callback.message.edit_caption(
                caption=f"{old_caption}\n\n❌ <b>Rejected</b> by <code>{actor_id}</code>"
            )
        except Exception:
            pass
        try:
            await bot.send_message(
                chat_id=buyer_id,
                text=f"❌ သင့် <b>{plan}</b> Plan ဝယ်ယူမှုကို ပယ်ချလိုက်ပါသည်။ အသေးစိတ်သိလိုပါက Support ကို ဆက်သွယ်ပါ။",
            )
        except Exception:
            pass
        await callback.answer("Rejected.")
        return

    payload: Dict[str, Any] = {
        "email": email,
        "plan": plan,
        "status": "ACTIVE",
        "startDate": get_utc_now_iso(),
        "durationDays": duration_days,
        "telegramUserId": buyer_id,
    }

    result = await post_subscription_update(payload)
    if result["ok"]:
        try:
            await callback.message.edit_caption(
                caption=f"{old_caption}\n\n✅ <b>Approved & Synced</b> (HTTP {result['status']}) by <code>{actor_id}</code>"
            )
        except Exception:
            pass
        try:
            await bot.send_message(
                chat_id=buyer_id,
                text=(
                    f"🎉 ဂုဏ်ယူပါတယ်! သင့် <b>{plan}</b> Plan ({duration_days} ရက်) ကို "
                    f"<code>{email}</code> အတွက် အောင်မြင်စွာ Activate လုပ်ပြီးပါပြီ။"
                ),
            )
        except Exception:
            pass
        await callback.answer("✅ Approved & Webhook updated!")
    else:
        err_detail = result["data"]
        try:
            await callback.message.edit_caption(
                caption=(
                    f"{old_caption}\n\n⚠️ <b>Webhook Failed</b> (HTTP {result['status']}) by <code>{actor_id}</code>\n"
                    f"<code>{err_detail}</code>"
                )
            )
        except Exception:
            pass
        await callback.answer(f"Webhook error ({result['status']})", show_alert=True)
        # ==========================================
# PART 3: HEALTH SERVER & MAIN ENTRYPOINT
# ==========================================


async def health_handler(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok", "service": "AYK-Recap-Bot"})


async def start_health_server() -> web.AppRunner:
    app = web.Application()
    app.router.add_get("/", health_handler)
    app.router.add_get("/health", health_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
    await site.start()
    return runner


async def main() -> None:
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        raise RuntimeError("BOT_TOKEN is missing. Set BOT_TOKEN env var or hardcode it in Part 1.")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    runner = await start_health_server()
    try:
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
    
            
