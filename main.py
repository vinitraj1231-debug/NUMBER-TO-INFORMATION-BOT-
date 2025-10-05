import os
import requests
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, filters
from dotenv import load_dotenv

# Logging सेटअप करें
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# .env फ़ाइल लोड करें
load_dotenv()

# --- CONFIGURATION ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
# **परिवर्तित API URL**
API_BASE_URL = os.getenv("API_BASE_URL", "https://taitan.mastimusicboxabd01.workers.dev/?mobile=") 
try:
    ADMIN_ID = int(os.getenv("ADMIN_ID"))
except (TypeError, ValueError):
    ADMIN_ID = None
    logger.error("ADMIN_ID is missing or invalid in .env file. Broadcast command will not work.")

DAILY_CREDITS_LIMIT = 3
REFERRAL_CREDITS = 3
SUPPORT_CHANNEL_LINK = "https://t.me/narzoxbot" 
# ---------------------

# --- GLOBAL STORAGE (Persistence के लिए डेटाबेस का उपयोग करें) ---
USER_CREDITS = {} 
USERS = set() 
REFERRED_TRACKER = set() 
# -----------------------------------------------------------------

def get_credits(user_id: int) -> int:
    """यूजर के वर्तमान क्रेडिट्स प्राप्त करता है। नया यूजर होने पर डिफॉल्ट क्रेडिट देता है।"""
    if user_id not in USER_CREDITS:
        USER_CREDITS[user_id] = DAILY_CREDITS_LIMIT
    
    return USER_CREDITS.get(user_id, 0) 

def get_referral_link(bot_username: str, user_id: int) -> str:
    """यूजर के लिए रेफरल लिंक बनाता है।"""
    return f"https://t.me/{bot_username}?start=ref_{user_id}"

def save_user(user_id: int) -> None:
    """यूजर ID को USERS सेट में जोड़ता है।"""
    USERS.add(user_id)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start कमांड पर जवाब देता है, एडवांस रेफरल हैंडलिंग सहित।"""
    user_id = update.effective_user.id
    username = update.effective_user.first_name or "friend"
    bot_username = context.bot.username
    
    save_user(user_id)

    # 1. एडवांस रेफरल लॉजिक हैंडल करें
    if context.args and context.args[0].startswith('ref_'):
        try:
            referrer_id = int(context.args[0].split('_')[1])
            referral_key = (referrer_id, user_id)
            
            if referrer_id != user_id and referral_key not in REFERRED_TRACKER:
                
                if referrer_id in USER_CREDITS:
                    USER_CREDITS[referrer_id] += REFERRAL_CREDITS
                    REFERRED_TRACKER.add(referral_key) 
                    
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=f"🥳 **बधाई हो!** `{username}` ने आपके रेफरल लिंक से बॉट शुरू किया है।\n"
                            f"आपको {REFERRAL_CREDITS} अतिरिक्त क्रेडिट मिले हैं। आपके कुल क्रेडिट: {USER_CREDITS[referrer_id]}",
                        parse_mode='Markdown'
                    )
                    
                    await update.message.reply_text(f"धन्यवाद! आपने रेफरल के ज़रिए बॉट शुरू किया है। आपको {DAILY_CREDITS_LIMIT} शुरुआती क्रेडिट मिले हैं।")
                else:
                     await update.message.reply_text(f"धन्यवाद! आपने बॉट शुरू किया है। आपको {DAILY_CREDITS_LIMIT} शुरुआती क्रेडिट मिले हैं।")
            
            elif referral_key in REFERRED_TRACKER:
                 await update.message.reply_text("आपने पहले ही इस रेफरल के ज़रिए बॉट शुरू कर दिया है। कोई अतिरिक्त क्रेडिट नहीं मिला।")

        except Exception as e:
            logger.error(f"Referral Error: {e}")
            pass 

    # 2. सामान्य वेलकम मैसेज और बटन
    current_credits = get_credits(user_id) 

    keyboard = [
        [
            InlineKeyboardButton("🔍 जानकारी खोजें", switch_inline_query_current_chat="/search "),
            InlineKeyboardButton(f"🎁 {REFERRAL_CREDITS} क्रेडिट कमाएँ", callback_data='get_referral_link') 
        ],
        [
            InlineKeyboardButton("💰 मेरे क्रेडिट्स", callback_data='show_credits'),
            InlineKeyboardButton("📢 Support Channel", url=SUPPORT_CHANNEL_LINK)
        ],
        [
            InlineKeyboardButton("➕ Add Me to Group", url=f"https://t.me/{bot_username}?startgroup=start")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_message = (
        f"🤖 **नमस्ते {username}! मैं आपका उन्नत नंबर सर्च बॉट हूँ।**\n\n"
        f"आपको **{DAILY_CREDITS_LIMIT}** शुरुआती सर्च क्रेडिट्स मिले हैं।\n"
        f"आपके पास अभी **{current_credits}** क्रेडिट्स हैं।\n\n"
        "✨ **क्रेडिट सिस्टम:**\n"
        "1. हर सर्च में 1 क्रेडिट का उपयोग होता है।\n"
        "2. क्रेडिट खत्म होने के बाद, आपको दोस्त को रेफर करके ही **नए क्रेडिट** मिलेंगे!\n"
        "🚀 **शुरुआत करने के लिए:** `/search <नंबर>` टाइप करें।"
    )

    await update.message.reply_text(welcome_message, reply_markup=reply_markup, parse_mode='Markdown')

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/search <number> कमांड को हैंडल करता है और क्रेडिट्स को सख्ती से लागू करता है।"""
    user_id = update.effective_user.id
    save_user(user_id)

    current_credits = get_credits(user_id)
    bot_username = context.bot.username

    # **सख्त क्रेडिट चेक: 0 क्रेडिट होने पर सर्च नहीं होगा**
    if current_credits <= 0:
        keyboard = [[InlineKeyboardButton(f"🎁 {REFERRAL_CREDITS} क्रेडिट कमाएँ", callback_data='get_referral_link')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "🛑 **क्रेडिट खत्म!**\nआपके पास अभी 0 क्रेडिट हैं। और सर्च करने के लिए, किसी दोस्त को रेफर करें!",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return 

    if not context.args:
        await update.message.reply_text("⚠️ कृपया `/search` के बाद एक नंबर दें। उदाहरण: `/search 9798423774`")
        return

    num = context.args[0]
    # **API URL को नए फॉर्मेट के लिए अपडेट किया गया**
    api_url = f"{API_BASE_URL}{num}" 
    
    await update.message.reply_text(f"🔍 `{num}` के लिए जानकारी खोज रहा हूँ... (1 क्रेडिट लगेगा)", parse_mode='Markdown')

    try:
        # API कॉल
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # क्रेडिट घटाएँ (सफलतापूर्वक कॉल होने पर)
        USER_CREDITS[user_id] -= 1
        
        response_message = "✅ **जानकारी प्राप्त हुई:**\n\n"
        user_data = None

        # API से JSON डेटा को प्रोसेस करने का प्रयास करें
        if 'result' in data and isinstance(data['result'], list) and len(data['result']) > 0:
            user_data = data['result'][0]
        elif isinstance(data, dict) and any(data.values()): 
            user_data = data
        
        if user_data:
            if 'Api_owner' in user_data:
                del user_data['Api_owner']
                
            for key, value in user_data.items():
                if value: # खाली/None वैल्यू को छोड़ दें
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
        await update.message.reply_text("❌ कोई अनपेक्षित गलती हुई है।")

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """एडमिन द्वारा चलाए जाने पर सभी यूजर्स को मैसेज भेजता है।"""
    user_id = update.effective_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("⚠️ **अस्वीकृत!** यह कमांड केवल एडमिन के लिए है।")
        return

    if not context.args:
        await update.message.reply_text("📣 कृपया ब्रॉडकास्ट करने के लिए मैसेज लिखें।\nउदाहरण: `/broadcast Bot में नया फीचर आ गया है!`")
        return

    broadcast_message = " ".join(context.args)
    success_count = 0
    failure_count = 0
    
    await update.message.reply_text(f"⏳ **ब्रॉडकास्ट शुरू हो रहा है**... {len(USERS)} यूजर्स को मैसेज भेजा जाएगा।")

    for chat_id in USERS:
        try:
            await context.bot.send_message(chat_id=chat_id, text=broadcast_message, parse_mode='Markdown')
            success_count += 1
        except Exception as e:
            if 'bot was blocked by the user' in str(e):
                 logger.info(f"User {chat_id} blocked the bot.")
            failure_count += 1
            
    await update.message.reply_text(
        f"✅ **ब्रॉडकास्ट पूरा हुआ!**\n"
        f"सफलतापूर्वक भेजे गए: **{success_count}**\n"
        f"विफल (Failed): **{failure_count}**"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline बटन क्लिक को हैंडल करता है।"""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    save_user(user_id) 
    bot_username = context.bot.username

    if query.data == 'show_credits':
        current_credits = get_credits(user_id)
        
        keyboard = [
            [InlineKeyboardButton(f"🎁 {REFERRAL_CREDITS} क्रेडिट कमाएँ", callback_data='get_referral_link')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"💰 आपके पास **{current_credits}** सर्च क्रेडिट्स बाकी हैं।", 
            reply_markup=reply_markup, 
            parse_mode='Markdown'
        )

    elif query.data == 'get_referral_link':
        # लॉजिक: रेफरल लिंक भेजें
        referral_link = get_referral_link(bot_username, user_id)
        current_credits = get_credits(user_id)
        
        referral_message = (
            "🔗 **आपका रेफरल लिंक यहाँ है:**\n"
            f"`{referral_link}`\n\n"
            f"यह लिंक किसी दोस्त को भेजें। जब वे बॉट शुरू करेंगे, तो आपको **{REFERRAL_CREDITS}** अतिरिक्त क्रेडिट मिलेंगे!\n"
            f"आपके पास वर्तमान में: **{current_credits}** क्रेडिट्स हैं।"
        )

        keyboard = [[InlineKeyboardButton("🔙 वापस जाएँ", callback_data='show_credits')]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            referral_message, 
            reply_markup=reply_markup, 
            parse_mode='Markdown'
        )


def main() -> None:
    if not BOT_TOKEN or ADMIN_ID is None:
        print("ERROR: BOT_TOKEN or ADMIN_ID is not set correctly in environment variables.")
        return

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    
    application.add_handler(CallbackQueryHandler(button_handler))

    print(f"Final Advanced Bot is running. Admin ID: {ADMIN_ID}")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
