import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

import aiohttp
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
    ReplyKeyboardRemove,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AYK-Recap-Bot")

# ==========================================
# PART 1: CONFIG, SUPABASE & WEBHOOK HELPER
# ==========================================

BOT_TOKEN: str = os.getenv(
    "BOT_TOKEN", "8909534863:AAEck21ljGacrRR_e4mUZQmGKqeH4tVAqwU"
)
OWNER_ID: int = int(os.getenv("OWNER_ID", "8415289516"))
ADMIN_GROUP_ID: int = int(os.getenv("ADMIN_GROUP_ID", "-100448651266"))
WEBHOOK_URL: str = os.getenv(
    "WEBHOOK_URL",
    "https://aykrecaptool.lovable.app/api/public/subscription/update",
)
WEBHOOK_SECRET: str = os.getenv("WEBHOOK_SECRET", "")
PORT: int = int(os.getenv("PORT", "8080"))

# Supabase Bot Data Persistence (Optional Env Vars)
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")
SUPABASE_TABLE: str = os.getenv("SUPABASE_BOT_TABLE", "bot_data")
SUPABASE_ROW_ID: str = os.getenv("SUPABASE_BOT_ROW_ID", "ayk_recap_bot")
LOCAL_FALLBACK_FILE: str = "bot_data.json"


def default_bot_data() -> Dict[str, Any]:
    return {
        "settings": {
            "pro_price": "10,000 Ks / 1 Month",
            "vip_price": "25,000 Ks / 1 Month",
        },
        "users": {},
        "referrals": {},
        "banned_users": [],
    }


class SubscriptionStates(StatesGroup):
    waiting_for_email = State()
    waiting_for_plan = State()
    waiting_for_proof = State()


router = Router()


def get_utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _supabase_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _supabase_headers() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }


def _load_local_fallback() -> Dict[str, Any]:
    if os.path.exists(LOCAL_FALLBACK_FILE):
        try:
            with open(LOCAL_FALLBACK_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    base = default_bot_data()
                    base.update(data)
                    return base
        except Exception as exc:
            logger.warning("Local fallback load failed: %s", exc)
    return default_bot_data()


def _save_local_fallback(data: Dict[str, Any]) -> None:
    try:
        with open(LOCAL_FALLBACK_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning("Local fallback save failed: %s", exc)


async def load_bot_data() -> Dict[str, Any]:
    data = _load_local_fallback()
    if not _supabase_enabled():
        return data

    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?id=eq.{SUPABASE_ROW_ID}&select=payload"
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=_supabase_headers()) as resp:
                if 200 <= resp.status < 300:
                    rows = await resp.json()
                    if isinstance(rows, list) and rows:
                        payload = rows[0].get("payload")
                        if isinstance(payload, dict):
                            merged = default_bot_data()
                            merged.update(payload)
                            _save_local_fallback(merged)
                            return merged
                else:
                    logger.warning("Supabase GET status %s: %s", resp.status, await resp.text())
    except Exception as exc:
        logger.warning("Supabase GET error: %s", exc)

    return data


async def save_bot_data(data: Dict[str, Any]) -> None:
    _save_local_fallback(data)
    if not _supabase_enabled():
        return

    url = f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}?on_conflict=id"
    body = [{"id": SUPABASE_ROW_ID, "payload": data, "updated_at": get_utc_now_iso()}]
    timeout = aiohttp.ClientTimeout(total=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=body, headers=_supabase_headers()) as resp:
                if not (200 <= resp.status < 300):
                    logger.warning("Supabase UPSERT status %s: %s", resp.status, await resp.text())
    except Exception as exc:
        logger.warning("Supabase UPSERT error: %s", exc)


async def post_subscription_update(payload: Dict[str, Any]) -> Dict[str, Any]:
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if WEBHOOK_SECRET:
        headers["X-Webhook-Secret"] = WEBHOOK_SECRET

    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(WEBHOOK_URL, json=payload, headers=headers) as resp:
            text_body = await resp.text()
            try:
                parsed = await resp.json()
            except Exception:
                parsed = text_body
            return {
                "ok": 200 <= resp.status < 300,
                "status": resp.status,
                "data": parsed,
}
