import os
import requests
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, filters
from dotenv import load_dotenv

# Logging सेटअप करें ताकि हम कंसोल में errors देख सकें
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# .env फ़ाइल लोड करें
load_dotenv()

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL", "https://freeapi.frappeash.workers.dev/")
ADMIN_ID = int(os.getenv("ADMIN_ID")) # Admin ID को यहाँ से लेंगे (इसे .env में सेट करें!)
DAILY_CREDITS_LIMIT = 3
REFERRAL_CREDITS = 3
# ---------------------

# डेटाबेस: बड़े स्केल के लिए, इसकी जगह Redis/PostgreSQL का उपयोग करें!
USER_CREDITS = {} 
USERS = set() # सभी यूनिक यूजर्स को स्टोर करने के लिए

def get_credits(user_id: int) -> int:
    """यूजर के क्रेडिट्स प्राप्त करता है, अगर पहली बार है तो डिफ़ॉल्ट देता है।"""
    # अगर यूजर मौजूद नहीं है, या क्रेडिट 0 है (दैनिक रीसेट के लिए सरल लॉजिक)
    if user_id not in USER_CREDITS or USER_CREDITS.get(user_id, 0) == 0:
        USER_CREDITS[user_id] = DAILY_CREDITS_LIMIT
    
    return USER_CREDITS.get(user_id, DAILY_CREDITS_LIMIT)

def get_referral_link(bot_username: str, user_id: int) -> str:
    """यूजर के लिए रेफरल लिंक बनाता है।"""
    return f"https://t.me/{bot_username}?start=ref_{user_id}"

# नया फ़ंक्शन: हर इंटरेक्शन पर यूजर को सेव करें
def save_user(user_id: int) -> None:
    """यूजर ID को USERS सेट में जोड़ता है।"""
    USERS.add(user_id)
    # आप यहाँ इस सेट को किसी फ़ाइल या डेटाबेस में सेव कर सकते हैं ताकि बॉट रीस्टार्ट होने पर डेटा न खोए।

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start कमांड पर जवाब देता है, रेफरल हैंडलिंग सहित।"""
    user_id = update.effective_user.id
    username = update.effective_user.first_name or "friend"
    
    save_user(user_id) # यूजर को सेव करें

    # 1. रेफरल लॉजिक हैंडल करें (पहले जैसा)
    if context.args and context.args[0].startswith('ref_'):
        try:
            referrer_id = int(context.args[0].split('_')[1])
            
            if referrer_id != user_id and user_id not in context.user_data.get('referred_by', []):
                # सुनिश्चित करें कि रेफरर को केवल एक बार क्रेडिट मिले (context.user_data का उपयोग करके)
                context.user_data['referred_by'] = [referrer_id]
                
                current_credits = get_credits(referrer_id)
                USER_CREDITS[referrer_id] = current_credits + REFERRAL_CREDITS
                
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=f"🥳 **बधाई हो!** `{username}` ने आपके रेफरल लिंक से बॉट शुरू किया है।\n"
                         f"आपको {REFERRAL_CREDITS} अतिरिक्त क्रेडिट मिले हैं। आपके कुल क्रेडिट: {USER_CREDITS[referrer_id]}",
                    parse_mode='Markdown'
                )
                await update.message.reply_text(f"धन्यवाद! आपने रेफरल के ज़रिए बॉट शुरू किया है। आपको {DAILY_CREDITS_LIMIT} क्रेडिट मिले हैं।")
            elif referrer_id == user_id:
                 await update.message.reply_text("आप खुद को रेफर नहीं कर सकते, दोस्त!")

        except Exception as e:
            logger.error(f"Referral Error: {e}")
            pass 

    # 2. सामान्य वेलकम मैसेज (पहले जैसा)
    current_credits = get_credits(user_id)
    bot_username = context.bot.username

    keyboard = [
        [
            InlineKeyboardButton("🔍 जानकारी खोजें", switch_inline_query_current_chat="/search "),
            InlineKeyboardButton(f"🎁 {REFERRAL_CREDITS} क्रेडिट कमाएँ", url=get_referral_link(bot_username, user_id))
        ],
        [
            InlineKeyboardButton(f"💰 मेरे क्रेडिट्स ({current_credits})", callback_data='show_credits')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_message = (
        f"🤖 **नमस्ते {username}! मैं आपका उन्नत नंबर सर्च बॉट हूँ।**\n\n"
        f"आज आपको **{DAILY_CREDITS_LIMIT}** मुफ़्त सर्च क्रेडिट्स मिले हैं।\n"
        f"आप अभी **{current_credits}** क्रेडिट्स का उपयोग कर सकते हैं।\n\n"
        "✨ **कैसे काम करता है:**\n"
        "1. `/search <नंबर>` टाइप करें।\n"
        "2. हर सर्च में 1 क्रेडिट का उपयोग होता है।\n"
        f"3. जब क्रेडिट खत्म हो जाएँ, तो **'क्रेडिट कमाएँ'** बटन का उपयोग करके किसी दोस्त को रेफर करें और **{REFERRAL_CREDITS}** अतिरिक्त क्रेडिट्स पाएँ!"
    )

    await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='Markdown')

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/search <number> कमांड को हैंडल करता है (पहले जैसा, क्रेडिट चेक सहित)"""
    user_id = update.effective_user.id
    save_user(user_id) # यूजर को सेव करें

    current_credits = get_credits(user_id)
    if current_credits <= 0:
        bot_username = context.bot.username
        keyboard = [[InlineKeyboardButton(f"🎁 {REFERRAL_CREDITS} क्रेडिट कमाएँ", url=get_referral_link(bot_username, user_id))]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🛑 **क्रेडिट खत्म!** आपके पास अभी 0 क्रेडिट हैं। और सर्च करने के लिए, दोस्त को रेफर करें!",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return

    if not context.args:
        await update.message.reply_text("⚠️ कृपया `/search` के बाद एक नंबर दें। उदाहरण: `/search 9798423774`")
        return

    num = context.args[0]
    api_url = f"{API_BASE_URL}?num={{{num}}}"
    
    await update.message.reply_text(f"🔍 `{num}` के लिए जानकारी खोज रहा हूँ... (1 क्रेडिट लगेगा)", parse_mode='Markdown')

    try:
        # API कॉल
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # क्रेडिट घटाएँ
        USER_CREDITS[user_id] -= 1
        
        # डेटा प्रोसेस करें (JSON parsing और formatting)
        if 'result' in data and isinstance(data['result'], list) and len(data['result']) > 0:
            user_data = data['result'][0]
            if 'Api_owner' in user_data:
                del user_data['Api_owner']
                
            response_message = "✅ **जानकारी प्राप्त हुई:**\n\n"
            for key, value in user_data.items():
                clean_key = key.replace('_', ' ').title()
                response_message += f"**{clean_key}:** `{value}`\n"
            
            remaining_credits = USER_CREDITS[user_id]
            response_message += f"\n💰 **क्रेडिट्स बाकी:** {remaining_credits}"
            
            await update.message.reply_text(response_message, parse_mode='Markdown')

        else:
            remaining_credits = USER_CREDITS[user_id]
            await update.message.reply_text(f"❌ इस नंबर (`{num}`) के लिए कोई जानकारी नहीं मिली।\n"
                                            f"💰 **क्रेडिट्स बाकी:** {remaining_credits}", parse_mode='Markdown')

    except requests.exceptions.RequestException as e:
        USER_CREDITS[user_id] += 1 # क्रेडिट वापस करें
        logger.error(f"API Request Error: {e}")
        await update.message.reply_text("🛑 बाहरी सर्विस से कनेक्ट करने में कोई समस्या आई। आपका क्रेडिट वापस कर दिया गया है।")
        
    except Exception as e:
        logger.error(f"Unexpected Error: {e}")
        await update.message.reply_text("❌ कोई अनपेक्षित गलती हुई।")

# --- नया ब्रॉडकास्ट कमांड ---
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """एडमिन द्वारा चलाए जाने पर सभी यूजर्स को मैसेज भेजता है।"""
    user_id = update.effective_user.id
    
    # 1. एडमिन चेक
    if user_id != ADMIN_ID:
        await update.message.reply_text("⚠️ **अस्वीकृत!** यह कमांड केवल एडमिन के लिए है।")
        return

    # 2. ब्रॉडकास्ट मैसेज प्राप्त करें
    if not context.args:
        await update.message.reply_text("📣 कृपया ब्रॉडकास्ट करने के लिए मैसेज लिखें।\nउदाहरण: `/broadcast Bot में नया फीचर आ गया है!`")
        return

    broadcast_message = " ".join(context.args)
    success_count = 0
    failure_count = 0
    
    await update.message.reply_text(f"⏳ **ब्रॉडकास्ट शुरू हो रहा है**... {len(USERS)} यूजर्स को मैसेज भेजा जाएगा।")

    # 3. सभी यूजर्स को मैसेज भेजें
    for chat_id in USERS:
        try:
            # यहाँ हम try-except ब्लॉक का उपयोग करते हैं क्योंकि कुछ यूजर्स ने बॉट को ब्लॉक कर दिया होगा
            await context.bot.send_message(chat_id=chat_id, text=broadcast_message, parse_mode='Markdown')
            success_count += 1
        except Exception as e:
            # अगर यूजर ने बॉट को ब्लॉक कर दिया है (Block by user), तो उसे नोट करें
            if 'bot was blocked by the user' in str(e):
                 logger.info(f"User {chat_id} blocked the bot.")
                 # आप चाहें तो यहाँ से यूजर को USERS सेट से हटा सकते हैं
            else:
                logger.error(f"Could not send message to {chat_id}: {e}")
            failure_count += 1
            
    # 4. एडमिन को परिणाम भेजें
    await update.message.reply_text(
        f"✅ **ब्रॉडकास्ट पूरा हुआ!**\n"
        f"सफलतापूर्वक भेजे गए: **{success_count}**\n"
        f"विफल (Failed): **{failure_count}**"
    )
# -----------------------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline बटन क्लिक को हैंडल करता है (पहले जैसा)।"""
    query = update.callback_query
    await query.answer()

    if query.data == 'show_credits':
        user_id = query.from_user.id
        save_user(user_id) # यूजर को सेव करें
        current_credits = get_credits(user_id)
        
        bot_username = context.bot.username
        keyboard = [
            [InlineKeyboardButton(f"🎁 {REFERRAL_CREDITS} क्रेडिट कमाएँ", url=get_referral_link(bot_username, user_id))]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"💰 आपके पास **{current_credits}** सर्च क्रेडिट्स बाकी हैं।", 
            reply_markup=reply_markup, 
            parse_mode='Markdown'
        )

def main() -> None:
    """Bot को शुरू करने का मुख्य फ़ंक्शन।"""
    if not BOT_TOKEN or not ADMIN_ID:
        print("ERROR: BOT_TOKEN or ADMIN_ID is not set in environment variables.")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    # कमांड हैंडलर्स जोड़ें
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command)) # नया ब्रॉडकास्ट कमांड

    # बटन हैंडलर
    from telegram.ext import CallbackQueryHandler
    application.add_handler(CallbackQueryHandler(button_handler))

    print(f"Advanced Bot is running. Admin ID: {ADMIN_ID}")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
