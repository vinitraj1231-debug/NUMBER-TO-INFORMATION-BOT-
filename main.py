import os
import re
import json
import aiohttp
import asyncio
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters
)

# ---------------- CONFIG ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN", "<YOUR_BOT_TOKEN>")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7524032836"))
API_URL = "https://encore.sahilraz9265.workers.dev/numbr?num="

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- HELPERS ----------------
def extract_number(text: str):
    """Extract first 7–15 digit number from text"""
    match = re.search(r"\b\d{7,15}\b", text)
    return match.group(0) if match else None


async def fetch_info(number: str):
    """Call external API"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(API_URL + number, timeout=10) as resp:
                text = await resp.text()
                try:
                    data = await resp.json()
                    formatted = json.dumps(data, indent=2, ensure_ascii=False)
                    return True, formatted
                except:
                    return True, text
        except Exception as e:
            return False, f"❌ API Error: {e}"


# ---------------- COMMAND HANDLERS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Welcome to Number Info Bot!*\n\n"
        "Send any phone number or use `/info <number>` to get details.\n\n"
        "Example: `/info 9798423774`\n"
        "Data powered by your private API.\n\n"
        "⚠️ Use responsibly. Respect privacy laws."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/info 9798423774`", parse_mode=ParseMode.MARKDOWN)
        return

    num = extract_number(" ".join(context.args))
    if not num:
        await update.message.reply_text("⚠️ No valid number found.")
        return

    await update.message.chat.send_action("typing")
    ok, data = await fetch_info(num)
    if not ok:
        await update.message.reply_text(data)
        return

    msg = f"📞 *Data for {num}:*\n```\n{data}\n```"
    msg = msg[:3900] + "\n...[truncated]" if len(msg) > 4000 else msg

    buttons = [
        [InlineKeyboardButton("🔁 Share", switch_inline_query=num)],
        [InlineKeyboardButton("📤 Send to Admin", callback_data=f"admin|{num}")]
    ]
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons))


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    num = extract_number(text)
    if not num:
        return
    await update.message.chat.send_action("typing")
    ok, data = await fetch_info(num)
    if not ok:
        await update.message.reply_text(data)
        return

    msg = f"📞 *Data for {num}:*\n```\n{data}\n```"
    msg = msg[:3900] + "\n...[truncated]" if len(msg) > 4000 else msg
    buttons = [
        [InlineKeyboardButton("🔁 Share", switch_inline_query=num)],
        [InlineKeyboardButton("📤 Send to Admin", callback_data=f"admin|{num}")]
    ]
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(buttons))


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("admin|"):
        num = data.split("|")[1]
        user = query.from_user
        ok, api_data = await fetch_info(num)
        msg = (
            f"📨 Request from @{user.username or user.full_name} (`{user.id}`)\n"
            f"🔢 Number: `{num}`\n\n"
            f"```\n{api_data}\n```"
        )
        await context.bot.send_message(chat_id=ADMIN_ID, text=msg, parse_mode=ParseMode.MARKDOWN)
        await query.edit_message_text("✅ Data sent to Admin!")


# ---------------- MAIN ----------------
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Bot started successfully 🚀")
    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
