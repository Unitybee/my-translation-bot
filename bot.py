from bale import Bot, Message
from deep_translator import GoogleTranslator
from deep_translator.exceptions import NotValidPayload, NotValidLength
import json
import os
import logging
from concurrent.futures import ThreadPoolExecutor
import asyncio
from datetime import datetime
from flask import Flask
import threading
import time
from langdetect import detect, DetectorFactory
from langdetect.lang_detect_exception import LangDetectException

# تنظیم seed برای تشخیص دقیق‌تر زبان
DetectorFactory.seed = 0

# تنظیم لاگینگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== تنظیمات اولیه ==========
TOKEN = os.getenv('BALE_TOKEN', '643390345:qpmMhzvaLfpMDBvugEW5NJQz1DD1KGohbP4')

bot = Bot(TOKEN)

# ========== کلاس مترجم امن ==========
class SafeTranslator:
    def __init__(self):
        self.cache = {}
        self.last_request_time = 0
        self.min_interval = 0.5
        self.detector_cache = {}
        
    def detect_language(self, text):
        try:
            cache_key = f"detect_{text[:50]}"
            if cache_key in self.detector_cache:
                return self.detector_cache[cache_key]
            
            detected_lang = detect(text)
            self.detector_cache[cache_key] = detected_lang
            return detected_lang
            
        except:
            return 'en'
    
    def translate_text(self, text, source='auto', target='fa'):
        try:
            cache_key = f"trans_{source}_{target}_{text[:100]}"
            if cache_key in self.cache:
                return self.cache[cache_key]
            
            current_time = time.time()
            if current_time - self.last_request_time < self.min_interval:
                time.sleep(self.min_interval - (current_time - self.last_request_time))
            
            for attempt in range(3):
                try:
                    translator = GoogleTranslator(source=source, target=target)
                    translated = translator.translate(text)
                    self.last_request_time = time.time()
                    self.cache[cache_key] = translated
                    return translated
                    
                except Exception as e:
                    if attempt < 2:
                        time.sleep(2 ** attempt)
                    else:
                        return None
            
            return None
            
        except Exception as e:
            logger.error(f"خطا در ترجمه: {e}")
            return None

safe_translator = SafeTranslator()
executor = ThreadPoolExecutor(max_workers=4)

# ========== فایل‌های تنظیمات ==========
SETTINGS_FILE = 'user_settings.json'
STATS_FILE = 'bot_stats.json'

# ========== لیست زبان‌ها ==========
LANGUAGES = {
    'fa': {'name': 'فارسی', 'emoji': '🇮🇷', 'native': 'فارسی'},
    'en': {'name': 'انگلیسی', 'emoji': '🇺🇸', 'native': 'English'},
    'ar': {'name': 'عربی', 'emoji': '🇸🇦', 'native': 'العربية'},
    'tr': {'name': 'ترکی استانبولی', 'emoji': '🇹🇷', 'native': 'Türkçe'},
    'de': {'name': 'آلمانی', 'emoji': '🇩🇪', 'native': 'Deutsch'},
    'fr': {'name': 'فرانسوی', 'emoji': '🇫🇷', 'native': 'Français'},
    'es': {'name': 'اسپانیایی', 'emoji': '🇪🇸', 'native': 'Español'},
    'ru': {'name': 'روسی', 'emoji': '🇷🇺', 'native': 'Русский'},
    'ur': {'name': 'اردو', 'emoji': '🇵🇰', 'native': 'اردو'},
    'hi': {'name': 'هندی', 'emoji': '🇮🇳', 'native': 'हिन्दी'},
    'zh-cn': {'name': 'چینی ساده', 'emoji': '🇨🇳', 'native': '简体中文'},
    'ja': {'name': 'ژاپنی', 'emoji': '🇯🇵', 'native': '日本語'},
    'ko': {'name': 'کره‌ای', 'emoji': '🇰🇷', 'native': '한국어'},
    'it': {'name': 'ایتالیایی', 'emoji': '🇮🇹', 'native': 'Italiano'},
    'pt': {'name': 'پرتغالی', 'emoji': '🇵🇹', 'native': 'Português'},
    'nl': {'name': 'هلندی', 'emoji': '🇳🇱', 'native': 'Nederlands'},
}

# ========== توابع کمکی ==========
def load_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except:
        return False

def load_stats():
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {'total_translations': 0, 'users': {}}

def save_stats(stats):
    try:
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        return True
    except:
        return False

user_settings = load_settings()
bot_stats = load_stats()

def get_lang_info(lang_code):
    return LANGUAGES.get(lang_code, {'name': lang_code, 'emoji': '🌐', 'native': lang_code})

def get_lang_display(lang_code):
    info = get_lang_info(lang_code)
    return f"{info['emoji']} {info['name']}"

def format_number(num):
    return f"{num:,}".replace(',', '٬')

class UserManager:
    def __init__(self):
        self.settings = user_settings
        self.stats = bot_stats
    
    def get_target_lang(self, user_id):
        return self.settings.get(user_id, {}).get('target_lang', 'fa')
    
    def set_target_lang(self, user_id, lang_code):
        if user_id not in self.settings:
            self.settings[user_id] = {}
        self.settings[user_id]['target_lang'] = lang_code
        return save_settings(self.settings)
    
    def get_user_stats(self, user_id):
        return self.stats['users'].get(user_id, {'count': 0, 'last_use': None})
    
    def increment_translation(self, user_id):
        if user_id not in self.stats['users']:
            self.stats['users'][user_id] = {'count': 0, 'last_use': None}
        self.stats['users'][user_id]['count'] += 1
        self.stats['users'][user_id]['last_use'] = datetime.now().isoformat()
        self.stats['total_translations'] += 1
        save_stats(self.stats)

user_manager = UserManager()
user_states = {}

# ========== مدیریت پیام‌ها ==========
@bot.event
async def on_message(message: Message):
    if message.text is None:
        return
    
    user_id = str(message.chat.id)
    user_text = message.text.strip()
    
    # ========== دستورات (همه با / شروع میشن) ==========
    
    # /start یا /s
    if user_text in ['/start', '/s']:
        target_lang = user_manager.get_target_lang(user_id)
        lang_display = get_lang_display(target_lang)
        welcome = f"""
🤖 **ربات ترجمه حرفه‌ای**

سلام! من یک ربات ترجمه هستم.

**⚡ دستورات:**
/s یا /start - شروع
/l یا /languages - لیست زبان‌ها
/sl یا /setlang - **تغییر زبان** ← فقط با این دستور زبان عوض میشه
/st یا /status - وضعیت فعلی
/h یا /help - راهنما
/stats - آمار ربات

**🌐 زبان فعلی شما:** {lang_display}

📝 **نحوه استفاده:**
1. با /setlang زبان مقصد رو انتخاب کن
2. هر متنی بفرست تا ترجمه بشه
        """
        await message.reply(welcome)
        return
    
    # /languages یا /l
    if user_text in ['/languages', '/l']:
        lang_list = []
        for code, info in LANGUAGES.items():
            lang_list.append(f"{info['emoji']} `{code}` → {info['name']}")
        
        reply = f"""
🌍 **زبان‌های قابل ترجمه**

{chr(10).join(lang_list)}

💡 برای تغییر زبان از /setlang استفاده کن
        """
        await message.reply(reply)
        return
    
    # /setlang یا /sl (تنها راه تغییر زبان)
    if user_text in ['/setlang', '/sl']:
        popular_codes = ['fa', 'en', 'ar', 'tr', 'de', 'fr', 'es']
        popular_list = "\n".join([f"{LANGUAGES[code]['emoji']} `{code}` → {LANGUAGES[code]['name']}" 
                                 for code in popular_codes if code in LANGUAGES])
        
        reply = f"""
🗣 **تنظیم زبان مقصد**

کد زبان رو وارد کن:

{popular_list}

📝 مثال: `en` برای انگلیسی، `fa` برای فارسی
        """
        user_states[user_id] = 'waiting_for_lang'
        await message.reply(reply)
        return
    
    # /status یا /st
    if user_text in ['/status', '/st']:
        target_lang = user_manager.get_target_lang(user_id)
        lang_display = get_lang_display(target_lang)
        user_stats = user_manager.get_user_stats(user_id)
        
        reply = f"""
📊 **وضعیت شما**

🌐 **زبان مقصد:** {lang_display}

📝 **تعداد ترجمه:** {format_number(user_stats['count'])} 

💡 برای تغییر زبان: /setlang
        """
        await message.reply(reply)
        return
    
    # /stats
    if user_text in ['/stats']:
        total = bot_stats.get('total_translations', 0)
        users_count = len(bot_stats.get('users', {}))
        
        reply = f"""
📊 **آمار کلی ربات**

📝 **کل ترجمه‌ها:** {format_number(total)}
👥 **کاربران فعال:** {format_number(users_count)}
⚡ **وضعیت:** آنلاین ✅
        """
        await message.reply(reply)
        return
    
    # /help یا /h
    if user_text in ['/help', '/h']:
        reply = """
📖 **راهنما:**

⚡ **دستورات:**
/s - شروع
/l - لیست زبان‌ها
/sl - **تغییر زبان** (فقط با این دستور)
/st - وضعیت
/stats - آمار
/h - راهنما

📝 **ترجمه:**
هر متنی بفرستی، ترجمه میشه.

💡 **نکته:** دیگه با فرستادن `en` یا `fa` زبان عوض نمیشه. فقط با /setlang
        """
        await message.reply(reply)
        return
    
    # ========== مدیریت انتخاب زبان (از /setlang) ==========
    if user_id in user_states and user_states[user_id] == 'waiting_for_lang':
        lang_code = user_text.lower()
        
        if lang_code in LANGUAGES:
            if user_manager.set_target_lang(user_id, lang_code):
                del user_states[user_id]
                lang_info = get_lang_info(lang_code)
                await message.reply(f"""
✅ **زبان تنظیم شد!**

🌐 زبان مقصد: {lang_info['emoji']} **{lang_info['name']}** (`{lang_code}`)

✨ حالا هر متنی بفرستی به {lang_info['name']} ترجمه میشه.
                """)
            else:
                await message.reply("❌ خطا در ذخیره تنظیمات!")
        else:
            await message.reply(f"""
❌ کد `{user_text}` معتبر نیست.

📋 برای مشاهده لیست: /languages
            """)
        return
    
    # ========== ترجمه ==========
    if len(user_text) < 1:
        await message.reply("📝 لطفاً متن معتبری بفرست.")
        return
    
    try:
        status_msg = await message.reply("⏳ در حال ترجمه...")
        
        target_lang = user_manager.get_target_lang(user_id)
        target_info = get_lang_info(target_lang)
        
        # تشخیص زبان
        try:
            loop = asyncio.get_event_loop()
            detected_lang = await loop.run_in_executor(
                executor,
                safe_translator.detect_language,
                user_text
            )
            if detected_lang not in LANGUAGES:
                detected_lang = 'en'
        except:
            detected_lang = 'en'
        
        # اگه زبان یکی بود
        if detected_lang == target_lang:
            await status_msg.edit(f"ℹ️ متن به {target_info['emoji']} **{target_info['name']}** هست. نیازی به ترجمه نیست!")
            return
        
        # ترجمه
        translated_text = await loop.run_in_executor(
            executor,
            safe_translator.translate_text,
            user_text,
            detected_lang,
            target_lang
        )
        
        if not translated_text:
            await status_msg.edit("❌ خطا در ترجمه! دوباره تلاش کن.")
            return
        
        user_manager.increment_translation(user_id)
        src_info = get_lang_info(detected_lang)
        
        reply_text = f"""
{src_info['emoji']} **{src_info['name']}** → {target_info['emoji']} **{target_info['name']}**

📝 {user_text}

✅ {translated_text}
        """
        
        await status_msg.edit(reply_text)
        
    except Exception as e:
        logger.error(f"خطا: {e}")
        await message.reply("❌ خطا! دوباره تلاش کن.")

# ========== Flask ==========
app = Flask(__name__)

@app.route('/')
@app.route('/health')
def health_check():
    return "🤖 ربات ترجمه در حال اجراست!", 200

def run_bot():
    print("=" * 50)
    print("🤖 ربات ترجمه - نسخه جدا شده")
    print("=" * 50)
    print(f"🌍 {len(LANGUAGES)} زبان پشتیبانی میشه.")
    print(f"📝 {bot_stats.get('total_translations', 0)} ترجمه انجام شده.")
    print("✅ ربات آماده است!")
    print("=" * 50)
    try:
        bot.run()
    except Exception as e:
        print(f"❌ خطا: {e}")

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
