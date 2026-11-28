"""
AYK Recap Bot — aiogram v3 + Supabase (aiohttp REST) backend.

Environment variables (loaded from .env or the process env):
    BOT_TOKEN      — Telegram bot token (required)
    OWNER_ID       — integer Telegram user id of the bot owner (recommended)
    SUPABASE_URL   — Supabase project URL
    SUPABASE_KEY   — Supabase API key (secret / service role)

Falls back to the project defaults only if env vars are missing, so that
the bot boots out-of-the-box for a quick demo. For production, ALWAYS
provide them via environment variables.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
#  Configuration
# --------------------------------------------------------------------------- #
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ayk-bot")

BOT_TOKEN = os.getenv("BOT_TOKEN")

_owner_raw = os.getenv("OWNER_ID", "").strip()
try:
    OWNER_ID: int = int(_owner_raw) if _owner_raw else 0
except ValueError:
    OWNER_ID = 0
    logger.warning("OWNER_ID=%r is not a valid integer; owner features disabled", _owner_raw)

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://tcyqlwzgvocjwtyqbxsp.supabase.co").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

if not BOT_TOKEN:
    logger.critical("BOT_TOKEN is not set. Aborting.")
    sys.exit(1)
if not OWNER_ID:
    logger.warning("OWNER_ID is not set — /admin and admin buttons will be disabled.")

BOT_USERNAME: str = ""  # filled in at startup

# --------------------------------------------------------------------------- #
#  Supabase client (aiohttp REST)
# --------------------------------------------------------------------------- #
class Supabase:
    """Minimal async REST client for Supabase PostgREST."""

    def __init__(self, url: str, key: str) -> None:
        self.base = f"{url}/rest/v1"
        self.key = key
        self._session: aiohttp.ClientSession | None = None

    # -- lifecycle --------------------------------------------------------- #
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "apikey": self.key,
                    "Authorization": f"Bearer {self.key}",
                    "Content-Type": "application/json",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # -- helpers ----------------------------------------------------------- #
    @staticmethod
    def _count_from_headers(headers: Any) -> int:
        content_range = headers.get("Content-Range", "") if headers else ""
        if "/" in content_range:
            try:
                return int(content_range.rsplit("/", 1)[-1])
            except ValueError:
                return 0
        return 0

    # -- queries ----------------------------------------------------------- #
    async def select(self, table: str, params: dict[str, str] | None = None) -> list[dict]:
        try:
            session = await self._get_session()
            async with session.get(f"{self.base}/{table}", params=params or {}) as resp:
                if resp.status >= 400:
                    logger.error("Supabase select [%s] %s → %s", table, resp.status, await resp.text())
                    return []
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.error("Supabase select [%s] network error: %s", table, exc)
            return []

    async def upsert(
        self,
        table: str,
        data: dict | list[dict],
        on_conflict: str | None = None,
    ) -> list[dict]:
        try:
            session = await self._get_session()
            params = {"on_conflict": on_conflict} if on_conflict else {}
            headers = {"Prefer": "resolution=merge-duplicates,return=representation"}
            async with session.post(
                f"{self.base}/{table}", json=data, params=params, headers=headers
            ) as resp:
                if resp.status >= 400:
                    logger.error("Supabase upsert [%s] %s → %s", table, resp.status, await resp.text())
                    return []
                return await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.error("Supabase upsert [%s] network error: %s", table, exc)
            return []

    async def count(self, table: str, params: dict[str, str] | None = None) -> int:
        try:
            session = await self._get_session()
            headers = {"Prefer": "count=exact", "Range": "0-0"}
            q = {"select": "user_id"}
            if params:
                q.update(params)
            async with session.get(f"{self.base}/{table}", params=q, headers=headers) as resp:
                if resp.status >= 400:
                    return 0
                return self._count_from_headers(resp.headers)
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return 0

    # -- domain helpers ---------------------------------------------------- #
    async def get_user(self, user_id: int) -> dict | None:
        rows = await self.select(
            "users", {"user_id": f"eq.{user_id}", "select": "*", "limit": "1"}
        )
        return rows[0] if rows else None

    async def upsert_user(self, user_id: int, **fields: Any) -> dict | None:
        payload = {"user_id": user_id, **fields}
        rows = await self.upsert("users", payload, on_conflict="user_id")
        return rows[0] if rows else None

    async def count_referrals(self, referrer_id: int) -> int:
        return await self.count("users", {"referrer_id": f"eq.{referrer_id}"})

    async def count_users(self) -> int:
        return await self.count("users")

    async def count_active_subs(self) -> int:
        now = datetime.now(timezone.utc).isoformat()
        return await self.count("users", {"subscription_until": f"gt.{now}"})

    async def all_user_ids(self) -> list[int]:
        rows = await self.select("users", {"select": "user_id"})
        return [int(r["user_id"]) for r in rows if "user_id" in r]


db = Supabase(SUPABASE_URL, SUPABASE_KEY)

# --------------------------------------------------------------------------- #
#  Auth helpers
# --------------------------------------------------------------------------- #
def is_owner(user_id: int | None) -> bool:
    return bool(OWNER_ID) and user_id == OWNER_ID


# --------------------------------------------------------------------------- #
#  Keyboards
# --------------------------------------------------------------------------- #
def main_menu_kb(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text="👤 Profile"), KeyboardButton(text="📋 Plans")],
        [KeyboardButton(text="🎁 Referral"), KeyboardButton(text="⚙️ Settings")],
    ]
    if is_admin:
        rows.append([KeyboardButton(text="🔧 Admin Panel")])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Choose an option…",
    )


def plans_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="1 Month — $5", callback_data="sub:1m")],
            [InlineKeyboardButton(text="3 Months — $12", callback_data="sub:3m")],
            [InlineKeyboardButton(text="12 Months — $40", callback_data="sub:12m")],
        ]
    )


def admin_ikb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Stats", callback_data="admin:stats")],
            [InlineKeyboardButton(text="👥 Recent Users", callback_data="admin:users")],
            [InlineKeyboardButton(text="📢 Broadcast", callback_data="admin:broadcast")],
        ]
    )


# --------------------------------------------------------------------------- #
#  FSM states
# --------------------------------------------------------------------------- #
class AdminStates(StatesGroup):
    waiting_broadcast = State()


# --------------------------------------------------------------------------- #
#  Router & utility
# --------------------------------------------------------------------------- #
router = Router()


def fmt_dt(raw: str | None) -> str:
    if not raw:
        return "—"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return raw


async def reply_with_menu(message: Message, text: str) -> None:
    await message.answer(text, reply_markup=main_menu_kb(is_owner(message.from_user.id)))


# --------------------------------------------------------------------------- #
#  Basic commands
# --------------------------------------------------------------------------- #
@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = message.from_user
    if user is None:
        return

    # Referral parsing: /start ref_12345
    referrer_id: int | None = None
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) == 2 and parts[1].startswith("ref_"):
        try:
            candidate = int(parts[1][4:])
            if candidate != user.id and await db.get_user(candidate):
                referrer_id = candidate
        except ValueError:
            pass

    existing = await db.get_user(user.id)
    if existing is None:
        await db.upsert_user(
            user.id,
            username=user.username,
            first_name=user.first_name,
            joined_at=datetime.now(timezone.utc).isoformat(),
            referrer_id=referrer_id,
            plan="free",
        )
    else:
        await db.upsert_user(
            user.id, username=user.username, first_name=user.first_name
        )

    await reply_with_menu(
        message,
        f"👋 Welcome, <b>{user.first_name or 'friend'}</b>!\n\n"
        f"I'm <b>AYK Recap Bot</b>. Use the menu below to get started.",
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await reply_with_menu(message, "🏠 <b>Main menu</b>")


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await reply_with_menu(message, "✅ Action cancelled.")


# --------------------------------------------------------------------------- #
#  Menu handlers
# --------------------------------------------------------------------------- #
@router.message(F.text == "👤 Profile")
async def show_profile(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = message.from_user
    if user is None:
        return
    data = await db.get_user(user.id)
    if not data:
        await reply_with_menu(message, "⚠️ Profile not found. Please send /start.")
        return
    ref_count = await db.count_referrals(user.id)
    text = (
        "👤 <b>Your Profile</b>\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"👤 Name: {user.first_name or '—'}\n"
        f"🔗 Username: @{user.username or '—'}\n"
        f"💼 Plan: <b>{data.get('plan') or 'free'}</b>\n"
        f"📅 Valid until: {fmt_dt(data.get('subscription_until'))}\n"
        f"🎁 Referrals: <b>{ref_count}</b>"
    )
    await reply_with_menu(message, text)


@router.message(F.text == "📋 Plans")
async def show_plans(message: Message, state: FSMContext) -> None:
    await state.clear()
    text = (
        "📋 <b>Available Plans</b>\n\n"
        "• <b>1 Month</b> — $5\n"
        "• <b>3 Months</b> — $12 (save 20%)\n"
        "• <b>12 Months</b> — $40 (best value)\n\n"
        "Choose a plan:"
    )
    await message.answer(text, reply_markup=plans_ikb())
    # Keep the persistent keyboard alive
    await message.answer(
        "Use the menu anytime 👇",
        reply_markup=main_menu_kb(is_owner(message.from_user.id)),
    )


@router.message(F.text == "🎁 Referral")
async def show_referral(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = message.from_user
    if user is None:
        return
    count = await db.count_referrals(user.id)
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{user.id}" if BOT_USERNAME else "—"
    text = (
        "🎁 <b>Referral Program</b>\n\n"
        f"Your invite link:\n<code>{link}</code>\n\n"
        f"👥 Invited friends: <b>{count}</b>"
    )
    await reply_with_menu(message, text)


@router.message(F.text == "⚙️ Settings")
async def show_settings(message: Message, state: FSMContext) -> None:
    await state.clear()
    await reply_with_menu(message, "⚙️ <b>Settings</b>\n\nComing soon.")


# --------------------------------------------------------------------------- #
#  Admin panel
# --------------------------------------------------------------------------- #
@router.message(F.text == "🔧 Admin Panel")
async def show_admin(message: Message, state: FSMContext) -> None:
    await state.clear()
    if not is_owner(message.from_user.id):
        await message.answer("⛔ Access denied.", reply_markup=main_menu_kb(False))
        return
    await message.answer("🔧 <b>Admin Panel</b>", reply_markup=admin_ikb())
    await message.answer("Menu:", reply_markup=main_menu_kb(True))


@router.callback_query(F.data.startswith("admin:"))
async def handle_admin_cb(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    if not is_owner(callback.from_user.id):
        return

    action = callback.data.split(":", 1)[1]
    message = callback.message

    if action == "stats":
        total = await db.count_users()
        active = await db.count_active_subs()
        text = (
            "📊 <b>Bot Statistics</b>\n\n"
            f"👥 Total users: <b>{total}</b>\n"
            f"💎 Active subscribers: <b>{active}</b>"
        )
        if message:
            await message.edit_text(text, reply_markup=admin_ikb())

    elif action == "users":
        rows = await db.select(
            "users",
            {"select": "user_id,first_name,username,plan,joined_at",
             "order": "joined_at.desc.nullslast",
             "limit": "20"},
        )
        if not rows:
            text = "👥 No users yet."
        else:
            lines = ["👥 <b>Recent 20 users</b>\n"]
            for r in rows:
                lines.append(
                    f"• <code>{r['user_id']}</code> — "
                    f"{r.get('first_name') or '—'} "
                    f"(@{r.get('username') or '—'}) · {r.get('plan') or 'free'}"
                )
            text = "\n".join(lines)
        if message:
            await message.edit_text(text, reply_markup=admin_ikb())

    elif action == "broadcast":
        await state.set_state(AdminStates.waiting_broadcast)
        if message:
            await message.answer(
                "📢 <b>Broadcast mode</b>\n\nSend the message you want to deliver "
                "to <i>every</i> user. Any content type is supported.\n\n"
                "Type /cancel to abort."
            )


@router.message(AdminStates.waiting_broadcast)
async def perform_broadcast(message: Message, state: FSMContext, bot: Bot) -> None:
    if not is_owner(message.from_user.id):
        await state.clear()
        return

    if (message.text or "").strip() == "/cancel":
        await state.clear()
        await reply_with_menu(message, "❌ Broadcast cancelled.")
        return

    await state.clear()
    user_ids = await db.all_user_ids()
    sent = failed = 0
    for uid in user_ids:
        try:
            await bot.copy_message(
                chat_id=uid,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
            )
            sent += 1
        except (TelegramBadRequest, Exception) as exc:  # noqa: BLE001
            failed += 1
            logger.debug("Broadcast to %s failed: %s", uid, exc)
        await asyncio.sleep(0.05)  # ~20 msg/s, safe under TG limits

    await reply_with_menu(
        message, f"✅ Broadcast finished.\n\n✔️ Sent: <b>{sent}</b>\n❌ Failed: <b>{failed}</b>"
    )


# --------------------------------------------------------------------------- #
#  Subscription callback
# --------------------------------------------------------------------------- #
@router.callback_query(F.data.startswith("sub:"))
async def handle_sub(callback: CallbackQuery) -> None:
    await callback.answer()
    plan = callback.data.split(":", 1)[1]
    await callback.message.answer(
        f"📦 You selected the <b>{plan}</b> plan.\n\n"
        "💳 Payment integration isn't wired up yet. "
        "Please contact the owner to complete your subscription."
    )


# --------------------------------------------------------------------------- #
#  Fallback (keeps keyboard persistent)
# --------------------------------------------------------------------------- #
@router.message()
async def fallback(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    if current is not None:
        return
    await reply_with_menu(
        message, "🤔 I didn't understand that. Pick an option from the menu 👇"
    )


# --------------------------------------------------------------------------- #
#  Bootstrap
# --------------------------------------------------------------------------- #
async def on_startup(bot: Bot) -> None:
    global BOT_USERNAME
    me = await bot.get_me()
    BOT_USERNAME = me.username or ""
    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Start the bot"),
                BotCommand(command="menu", description="Open main menu"),
            ]
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("set_my_commands failed: %s", exc)

    # Ensure no stale webhook conflicts with long polling
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("delete_webhook failed: %s", exc)

    logger.info("Bot @%s is up (owner_id=%s)", BOT_USERNAME or "?", OWNER_ID or "unset")


async def main() -> None:
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    dp.startup.register(on_startup)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await db.close()
        await bot.session.close()
        logger.info("Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopped by user.")
