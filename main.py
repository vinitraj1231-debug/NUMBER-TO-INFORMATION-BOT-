#!/usr/bin/env python3
"""
Advanced "Number → Info" Telegram Bot
- Uses aiohttp + python-telegram-bot (async)
- SQLite stores query history
- In-memory caching with TTL, per-user rate-limiting
- Inline query support, admin broadcast/stats
"""

import os
import re
import json
import time
import logging
import asyncio
from datetime import datetime, timedelta
import aiosqlite
import aiohttp

from typing import Optional, Dict, Any, Tuple

from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    InlineQueryHandler,
    filters,
)

# ----------------- CONFIG -----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Set BOT_TOKEN environment variable before running.")

# By default using admin id from your earlier context; change if needed
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "7524032836"))

API_BASE = "https://encore.sahilraz9265.workers.dev/numbr?num="

DB_PATH = os.getenv("DB_PATH", "bot_history.db")

# Rate limit: tokens per window and window seconds
RATE_LIMIT_TOKENS = int(os.getenv("RATE_LIMIT_TOKENS", "5"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # seconds

# Cache TTL in seconds
CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))

# Telegram message max length
TG_MAX_LEN = 4000

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ----------------- GLOBALS -----------------
session: Optional[aiohttp.ClientSession] = None

# cache: number -> (expiry_ts, formatted_text)
cache: Dict[str, Tuple[float, str]] = {}

# rate limiting: user_id -> (tokens_left, window_reset_ts)
rate_table: Dict[int, Tuple[int, float]] = {}

# sqlite connection will be opened in async init
# ----------------- UTILITIES -----------------


def normalize_number(text: str) -> Optional[str]:
    # Accept digits, +, spaces, hyphens. Extract first reasonable sequence of 7-15 digits.
    digits = re.findall(r"\d{7,15}", text)
    return digits[0] if digits else None


def truncate(s: str, max_len: int = TG_MAX_LEN) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 15] + "\n\n...[truncated]"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS queries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                number TEXT,
                response TEXT,
                created_at TEXT
            )"""
        )
        await db.commit()


async def log_query(user_id: int, username: str, number: str, response_text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO queries (user_id, username, number, response, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, username or "", number, response_text, datetime.utcnow().isoformat()),
        )
        await db.commit()


def check_rate_limit(user_id: int) -> Tuple[bool, str]:
    now = time.time()
    tokens, reset = rate_table.get(user_id, (RATE_LIMIT_TOKENS, now + RATE_LIMIT_WINDOW))
    if now >= reset:
        # reset window
        tokens = RATE_LIMIT_TOKENS
        reset = now + RATE_LIMIT_WINDOW
    if tokens <= 0:
        retry_secs = int(reset - now)
        return False, f"Rate limit exceeded. Try again in {retry_secs} seconds."
    # consume a token
    rate_table[user_id] = (tokens - 1, reset)
    return True, ""


async def fetch_number_data(number: str) -> Tuple[bool, str]:
    # Check cache
    now = time.time()
    if number in cache:
        expiry, formatted = cache[number]
        if now < expiry:
            logger.debug("Cache hit for %s", number)
            return True, formatted
        else:
            cache.pop(number, None)

    url = API_BASE + number
    try:
        async with session.get(url, timeout=10) as resp:
            text = await resp.text()
            try:
                data = await resp.json()
                pretty = json.dumps(data, indent=2, ensure_ascii=False)
                message = f"<b>Data for {number}:</b>\n<pre>{pretty}</pre>"
            except Exception:
                # not JSON
                message = f"<b>Data for {number}:</b>\n<pre>{text}</pre>"
            message = truncate(message)
            # store in cache
            cache[number] = (now + CACHE_TTL, message)
            return True, message
    except Exception as e:
        logger.exception("API fetch error")
        return False, f"Failed to fetch data for {number}: {e}"


# ----------------- HANDLERS -----------------


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "👋 *Number→Info Bot*\n\n"
        "Use /info <number> to look up a number.\n"
        "You can also just send a message containing the number and I'll auto-detect it.\n\n"
        "Examples:\n"
        "`/info 9798423774`\n\n"
        "Note: Respect privacy and laws when using this bot."
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Commands:\n"
        "/info <number> - Lookup a number\n"
        "/history - (admin only) show recent queries\n"
        "/stats - (admin only) usage stats\n"
        "/broadcast <msg> - (admin only) send message to admin only (for demo)\n"
    )


async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    ok, reason = check_rate_limit(user_id)
    if not ok:
        await update.message.reply_text(reason)
        return

    if context.args:
        num_raw = " ".join(context.args)
        num = normalize_number(num_raw)
        if not num:
            await update.message.reply_text("No valid number found in your input.")
            return
    else:
        await update.message.reply_text("Usage: /info <number>")
        return

    await update.message.chat.send_action("typing")
    success, message = await fetch_number_data(num)
    if success:
        # reply with inline buttons
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Share", switch_inline_query= num)],]
        )
        sent_msg = await update.message.reply_text(message, parse_mode=ParseMode.HTML, reply_markup=kb)
        # log
        await log_query(user_id, user.username or "", num, message)
    else:
        await update.message.reply_text(message)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Auto-detect number in plain messages
    if not update.message or not update.message.text:
        return
    user = update.effective_user
    user_id = user.id
    text = update.message.text.strip()

    num = normalize_number(text)
    if not num:
        # ignore or you could add help message
        return

    ok, reason = check_rate_limit(user_id)
    if not ok:
        await update.message.reply_text(reason)
        return

    await update.message.chat.send_action("typing")
    success, message = await fetch_number_data(num)
    if success:
        kb = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Share", switch_inline_query=num),
                    InlineKeyboardButton("Send to Admin", callback_data=f"sendadm|{num}"),
                ]
            ]
        )
        await update.message.reply_text(message, parse_mode=ParseMode.HTML, reply_markup=kb)
        await log_query(user_id, user.username or "", num, message)
    else:
        await update.message.reply_text(message)


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    if data.startswith("sendadm|"):
        num = data.split("|", 1)[1]
        user = query.from_user
        msg = f"User @{user.username or user.full_name} ({user.id}) requested info for <b>{num}</b>."
        ok, message = await fetch_number_data(num)
        if ok:
            await context.bot.send_message(chat_id=ADMIN_USER_ID, text=msg + "\n\n" + message, parse_mode=ParseMode.HTML)
            await query.edit_message_text("Sent to admin ✅", parse_mode=ParseMode.HTML)
        else:
            await query.edit_message_text("Failed to fetch data to send to admin.")


async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query.strip()
    if not query:
        return
    num = normalize_number(query)
    if not num:
        # offer help item
        result = InlineQueryResultArticle(
            id="no-number",
            title="Enter a phone number (7-15 digits)",
            input_message_content=InputTextMessageContent("Please provide a number like `9798423774`."),
        )
        await update.inline_query.answer([result], cache_time=1)
        return

    success, message = await fetch_number_data(num)
    if not success:
        message = f"Failed to fetch data for {num}."

    content = message
    result = InlineQueryResultArticle(
        id=num,
        title=f"Info for {num}",
        input_message_content=InputTextMessageContent(content, parse_mode=ParseMode.HTML),
        description="Tap to send number info into chat",
    )
    await update.inline_query.answer([result], cache_time=10)


# --------- Admin commands ----------
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("Unauthorized.")
        return
    # simple stats from DB
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM queries")
        total = (await cursor.fetchone())[0]
        cursor = await db.execute("SELECT number, COUNT(*) as c FROM queries GROUP BY number ORDER BY c DESC LIMIT 10")
        top = await cursor.fetchall()
    text = f"Total queries: {total}\nTop numbers:\n"
    for row in top:
        text += f"- {row[0]} ({row[1]})\n"
    await update.message.reply_text(text)


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Example: admin can send a small message to ADMIN only or do mass broadcast (careful!)
    user = update.effective_user
    if user.id != ADMIN_USER_ID:
        await update.message.reply_text("Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    msg = " ".join(context.args)
    # For demo: send back to admin and return
    await context.bot.send_message(chat_id=ADMIN_USER_ID, text=f"[Broadcast preview]\n{msg}")
    await update.message.reply_text("Broadcast preview sent to admin.")


# ----------------- APP SETUP -----------------


async def main():
    global session
    await init_db()
    session = aiohttp.ClientSession()

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("info", info_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))

    application.add_handler(CallbackQueryHandler(callback_query_handler))
    application.add_handler(InlineQueryHandler(inline_query_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # start the bot (polling)
    logger.info("Starting bot (polling)...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()  # runs the poller
    await application.idle()

    # cleanup
    await session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user")
