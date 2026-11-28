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
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
  raise RuntimeError("BOT_TOKEN environment variable is required.")


def _parse_int(env_name: str, default: int) -> int:
  raw = os.getenv(env_name, str(default)).strip()
  try:
    return int(raw)
  except ValueError:
    return default


OWNER_ID = _parse_int("OWNER_ID", 0)
ADMIN_GROUP_ID = _parse_int("ADMIN_GROUP_ID", 0)

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
    "admin_cancelled": "❌ Admin Group သို့ စာပို့ခြင်းကို ပယ်ဖျက်လိုက်ပါပြီ.",
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
