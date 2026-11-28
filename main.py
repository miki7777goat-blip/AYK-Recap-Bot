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
