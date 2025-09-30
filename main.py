import os
import logging
import json
import aiohttp
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)
from pymongo import MongoClient

# --- Load env ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URL = os.getenv("MONGO_URL")

# --- DB setup ---
client = MongoClient(MONGO_URL)
db = client["numinfo_bot"]
users = db["users"]

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

API_TEMPLATE = "https://freeapi.frappeash.workers.dev/?num={num}"
FREE_CREDIT = 1

# --- Helpers ---
def get_user(user_id: int):
    user = users.find_one({"_id": user_id})
    if not user:
        user = {"_id": user_id, "credits": FREE_CREDIT, "referrals": 0}
        users.insert_one(user)
    return user

def update_credits(user_id: int, amount: int):
    users.update_one({"_id": user_id}, {"$inc": {"credits": amount}})

async def fetch_num_info(number: str):
    url = API_TEMPLATE.format(num=number)
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()

def strip_owner_fields(data: dict) -> dict:
    data.pop("footer", None)
    data.pop("Api_owner", None)
    if isinstance(data.get("result"), list):
        for item in data["result"]:
            if isinstance(item, dict):
                item.pop("Api_owner", None)
    return data

def format_result_for_user(data: dict) -> str:
    res = data.get("result")
    if not res:
        return "Koi result nahi mila."
    item = res[0] if isinstance(res, list) else res
    parts = []
    for k in ("name", "mobile", "alt_mobile", "father_name", "address", "circle", "id_number", "email"):
        v = item.get(k)
        if v:
            pretty_key = {
                "name":"Name",
                "mobile":"Mobile",
                "alt_mobile":"Alt mobile",
                "father_name":"Father name",
                "address":"Address",
                "circle":"Circle",
                "id_number":"ID number",
                "email":"Email"
            }.get(k, k)
            parts.append(f"*{pretty_key}*: {v}")
    return "\n".join(parts) if parts else "Kuch bhi dikhane layak nahi mila."

# --- Commands ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # referral handling
    if context.args:
        try:
            ref_id = int(context.args[0])
            if ref_id != user_id:
                ref_user = get_user(ref_id)
                update_credits(ref_id, 1)
                users.update_one({"_id": ref_id}, {"$inc": {"referrals": 1}})
                await context.bot.send_message(
                    chat_id=ref_id,
                    text=f"🎉 Aapko 1 extra credit mila! (Referral se)\nTotal credits: {get_user(ref_id)['credits']}"
                )
        except:
            pass  # ignore invalid args

    user = get_user(user_id)
    await update.message.reply_text(
        f"👋 Welcome {update.effective_user.first_name}!\n\n"
        f"Aapke paas {user['credits']} free credit hai.\n"
        f"Har /num search me 1 credit lagega.\n\n"
        f"Apna referral link:\n"
        f"https://t.me/{context.bot.username}?start={user_id}"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 *Available Commands:*\n\n"
        "/start - Welcome + referral link\n"
        "/help - Show this help menu\n"
        "/num <number> - Get number info (1 credit)\n"
        "/credits - Check your credits",
        parse_mode="Markdown"
    )

async def credits(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    await update.message.reply_text(
        f"💰 Aapke paas {user['credits']} credits hai.\n"
        f"Referrals: {user['referrals']}"
    )

async def num(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if user["credits"] <= 0:
        await update.message.reply_text(
            "❌ Aapke paas koi credit nahi bacha.\n\n"
            "➡️ Refer friends to earn free credits!\n"
            f"Referral link: https://t.me/{context.bot.username}?start={user_id}"
        )
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ Usage: /num <number>\nExample: `/num 919876543210`", parse_mode="Markdown"
        )
        return

    number = context.args[0]
    msg = await update.message.reply_text("🔎 Fetching info...")

    try:
        data = await fetch_num_info(number)
        clean = strip_owner_fields(data)
        clean_text = format_result_for_user(clean)
        update_credits(user_id, -1)
        await msg.edit_text(clean_text, parse_mode="Markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error fetching API: {e}")

# --- Main ---
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("credits", credits))
    app.add_handler(CommandHandler("num", num))
    logger.info("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
