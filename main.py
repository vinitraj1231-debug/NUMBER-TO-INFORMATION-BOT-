import os
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv

# .env फ़ाइल लोड करें
load_dotenv()

# --- CONFIGURATION ---
# BotFather से प्राप्त किया गया Token
BOT_TOKEN = os.getenv("BOT_TOKEN")
# आपकी API का बेस URL
API_BASE_URL = os.getenv("API_BASE_URL", "https://freeapi.frappeash.workers.dev/")
# ---------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start कमांड पर जवाब देता है।"""
    await update.message.reply_text(
        'नमस्ते! मैं नंबर से जानकारी खोज सकता हूँ।\n'
        'जानकारी प्राप्त करने के लिए `/search <नंबर>` टाइप करें।\n'
        'उदाहरण: `/search 9798423774`'
    )

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/search <number> कमांड को हैंडल करता है और API को कॉल करता है।"""
    
    # कमांड के बाद का टेक्स्ट (नंबर) प्राप्त करें।
    # context.args में /search के बाद के सभी शब्द एक लिस्ट के रूप में होते हैं।
    if not context.args:
        await update.message.reply_text("⚠️ कृपया `/search` के बाद एक नंबर दें। उदाहरण: `/search 9798423774`")
        return

    num = context.args[0]
    
    # API URL बनाएं, नंबर को curly braces ({}) में संलग्न करें।
    api_url = f"{API_BASE_URL}?num={{{num}}}"
    
    await update.message.reply_text(f"🔍 `{num}` के लिए जानकारी खोज रहा हूँ...", parse_mode='Markdown')

    try:
        # API को कॉल करें।
        response = requests.get(api_url, timeout=10)
        response.raise_for_status() # HTTP errors के लिए exception उठाएँ।

        data = response.json()
        
        # 'result' array के पहले एलिमेंट से डेटा निकालें।
        if 'result' in data and isinstance(data['result'], list) and len(data['result']) > 0:
            user_data = data['result'][0]
            
            # 'Api_owner' जैसी अनावश्यक keys को हटा दें।
            if 'Api_owner' in user_data:
                del user_data['Api_owner']
                
            # साफ़ डेटा को फ़ॉर्मेट करें।
            response_message = "✅ **जानकारी प्राप्त हुई:**\n\n"
            
            # डेटा को सुंदर फ़ॉर्मेट में दिखाने के लिए लूप करें।
            for key, value in user_data.items():
                # Underscore को हटाकर (जैसे father_name से Father Name)
                clean_key = key.replace('_', ' ').title()
                response_message += f"**{clean_key}:** `{value}`\n"
            
            await update.message.reply_text(response_message, parse_mode='Markdown')

        else:
            await update.message.reply_text(f"❌ इस नंबर (`{num}`) के लिए कोई जानकारी नहीं मिली।", parse_mode='Markdown')

    except requests.exceptions.RequestException as e:
        # API कॉल से संबंधित errors को संभालें।
        print(f"API Request Error: {e}")
        await update.message.reply_text("🛑 बाहरी सर्विस से कनेक्ट करने में कोई समस्या आई। कृपया बाद में प्रयास करें।")
        
    except Exception as e:
        # अन्य सभी errors को संभालें।
        print(f"Unexpected Error: {e}")
        await update.message.reply_text("❌ कोई अनपेक्षित गलती हुई।")


def main() -> None:
    """Bot को शुरू करने का मुख्य फ़ंक्शन।"""
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN is not set in environment variables.")
        return

    # Application Builder का उपयोग करके Bot को सेट करें।
    application = Application.builder().token(BOT_TOKEN).build()

    # कमांड हैंडलर्स जोड़ें
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("search", search_command))

    # Bot को लगातार चलने दें (polling)।
    print("Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
