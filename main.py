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
