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
    if message.from_user:
        bot_data = await load_bot_data()
        uid_str = str(message.from_user.id)
        users = bot_data.setdefault("users", {})
        users[uid_str] = {
            "id": message.from_user.id,
            "name": message.from_user.full_name,
            "username": message.from_user.username or "",
            "last_seen": get_utc_now_iso(),
        }
        await save_bot_data(bot_data)

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

    if len(parts) != 3:
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
        bot_data = await load_bot_data()
        subscriptions = bot_data.setdefault("subscriptions", {})
        subscriptions[str(buyer_id)] = {
            "email": email,
            "plan": plan,
            "status": "ACTIVE",
            "durationDays": duration_days,
            "updatedAt": get_utc_now_iso(),
        }
        await save_bot_data(bot_data)

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
        raise RuntimeError("BOT_TOKEN is missing.")

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await load_bot_data()
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

             
