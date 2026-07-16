from bale import Bot, Message
from deep_translator import GoogleTranslator
from deep_translator.exceptions import NotValidPayload, NotValidLength
import json
import os
import logging
from concurrent.futures import ThreadPoolExecutor
import asyncio
from datetime import datetime
import re
from flask import Flask
import threading
import time

# تنظیم لاگینگ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== تنظیمات اولیه ==========
TOKEN = os.getenv('BALE_TOKEN', '643390345:_RraKmp0R1jrJhE4z_JQhBh7oeOZMY03kXE')

bot = Bot(TOKEN)

# ========== کلاس مترجم امن با deep-translator ==========
class SafeTranslator:
    def __init__(self):
        self.cache = {}
        self.last_request_time = 0
        self.min_interval = 0.5  # نیم ثانیه بین درخواست‌ها
        
    def detect_language(self, text):
        """تشخیص زبان با استفاده از deep-translator"""
        try:
            # بررسی کش
            cache_key = f"detect_{text[:50]}"
            if cache_key in self.cache:
                return self.cache[cache_key]
            
            # محدود کردن نرخ درخواست
            current_time = time.time()
            if current_time - self.last_request_time < self.min_interval:
                time.sleep(self.min_interval - (current_time - self.last_request_time))
            
            # تشخیص زبان
            detector = GoogleTranslator(target='en')
            detected = detector.detect(text)
            
            self.last_request_time = time.time()
            self.cache[cache_key] = detected
            return detected
            
        except Exception as e:
            logger.warning(f"خطا در تشخیص زبان: {e}")
            return 'en'  # پیش‌فرض انگلیسی
    
    def translate_text(self, text, source='auto', target='fa'):
        """ترجمه متن با deep-translator و تلاش مجدد"""
        try:
            # بررسی کش
            cache_key = f"trans_{source}_{target}_{text[:100]}"
            if cache_key in self.cache:
                return self.cache[cache_key]
            
            # محدود کردن نرخ درخواست
            current_time = time.time()
            if current_time - self.last_request_time < self.min_interval:
                time.sleep(self.min_interval - (current_time - self.last_request_time))
            
            # تلاش برای ترجمه با حداکثر ۳ بار تکرار
            for attempt in range(3):
                try:
                    # استفاده از GoogleTranslator
                    translator = GoogleTranslator(source=source, target=target)
                    translated = translator.translate(text)
                    
                    self.last_request_time = time.time()
                    
                    # ذخیره در کش
                    self.cache[cache_key] = translated
                    return translated
                    
                except (NotValidPayload, NotValidLength) as e:
                    # این خطاها مربوط به ورودی نامعتبر هستن
                    logger.warning(f"ورودی نامعتبر برای ترجمه: {e}")
                    return f"⚠️ خطا: متن ورودی معتبر نیست. لطفاً متن دیگری بفرستید."
                    
                except Exception as e:
                    logger.warning(f"تلاش {attempt+1} برای ترجمه ناموفق: {e}")
                    if attempt < 2:
                        wait_time = 2 ** attempt  # تاخیر نمایی: 1, 2 ثانیه
                        time.sleep(wait_time)
                    else:
                        # همه تلاش‌ها ناموفق
                        return f"❌ خطا در ترجمه! لطفاً دوباره تلاش کنید.\n\nمتن اصلی:\n{text}"
            
            return None
            
        except Exception as e:
            logger.error(f"خطا در ترجمه: {e}")
            return f"❌ خطا در ترجمه! لطفاً دوباره تلاش کنید.\n\nمتن اصلی:\n{text}"

# ایجاد نمونه از مترجم امن
safe_translator = SafeTranslator()

# Thread pool برای پردازش همزمان
executor = ThreadPoolExecutor(max_workers=4)

# فایل تنظیمات
SETTINGS_FILE = 'user_settings.json'
STATS_FILE = 'bot_stats.json'

# ========== لیست زبان‌ها با اطلاعات کامل ==========
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
    'el': {'name': 'یونانی', 'emoji': '🇬🇷', 'native': 'Ελληνικά'},
    'he': {'name': 'عبری', 'emoji': '🇮🇱', 'native': 'עברית'},
    'pl': {'name': 'لهستانی', 'emoji': '🇵🇱', 'native': 'Polski'},
    'vi': {'name': 'ویتنامی', 'emoji': '🇻🇳', 'native': 'Tiếng Việt'},
    'th': {'name': 'تایلندی', 'emoji': '🇹🇭', 'native': 'ไทย'},
    'id': {'name': 'اندونزیایی', 'emoji': '🇮🇩', 'native': 'Bahasa Indonesia'},
}

# ========== توابع کمکی ==========
def load_settings() -> dict:
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"خطا در بارگذاری تنظیمات: {e}")
    return {}

def save_settings(settings: dict) -> bool:
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"خطا در ذخیره تنظیمات: {e}")
        return False

def load_stats() -> dict:
    try:
        if os.path.exists(STATS_FILE):
            with open(STATS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {'total_translations': 0, 'users': {}}

def save_stats(stats: dict) -> bool:
    try:
        with open(STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        return True
    except:
        return False

# بارگذاری داده‌ها
user_settings = load_settings()
bot_stats = load_stats()

def get_lang_info(lang_code: str) -> dict:
    return LANGUAGES.get(lang_code, {'name': lang_code, 'emoji': '🌐', 'native': lang_code})

def get_lang_display(lang_code: str) -> str:
    info = get_lang_info(lang_code)
    return f"{info['emoji']} {info['name']}"

def format_number(num: int) -> str:
    return f"{num:,}".replace(',', '٬')

# ========== کلاس مدیریت کاربر ==========
class UserManager:
    def __init__(self):
        self.settings = user_settings
        self.stats = bot_stats
    
    def get_target_lang(self, user_id: str) -> str:
        return self.settings.get(user_id, {}).get('target_lang', 'fa')
    
    def set_target_lang(self, user_id: str, lang_code: str) -> bool:
        if user_id not in self.settings:
            self.settings[user_id] = {}
        self.settings[user_id]['target_lang'] = lang_code
        return save_settings(self.settings)
    
    def get_user_stats(self, user_id: str) -> dict:
        return self.stats['users'].get(user_id, {'count': 0, 'last_use': None})
    
    def increment_translation(self, user_id: str):
        if user_id not in self.stats['users']:
            self.stats['users'][user_id] = {'count': 0, 'last_use': None}
        self.stats['users'][user_id]['count'] += 1
        self.stats['users'][user_id]['last_use'] = datetime.now().isoformat()
        self.stats['total_translations'] += 1
        save_stats(self.stats)

user_manager = UserManager()

# ========== وضعیت‌های کاربران ==========
user_states = {}

# ========== مدیریت پیام‌ها ==========
@bot.event
async def on_message(message: Message):
    if message.text is None:
        return
    
    user_id = str(message.chat.id)
    user_text = message.text.strip()
    
    # ========== دستورات اصلی ==========
    
    # start
    if user_text in ['/start', '/s']:
        target_lang = user_manager.get_target_lang(user_id)
        lang_display = get_lang_display(target_lang)
        
        welcome = f"""
🤖 **ربات ترجمه حرفه‌ای**

سلام! من یک ربات ترجمه قدرتمند هستم که می‌توانم متون شما را به بیش از ۲۰ زبان زنده دنیا ترجمه کنم.

**✨ ویژگی‌ها:**
• 🚀 ترجمه سریع و دقیق
• 🌍 پشتیبانی از ۲۲ زبان
• 💾 ذخیره تنظیمات شخصی
• 📊 آمار ترجمه‌ها

**⚡ دستورات سریع:**
/s یا /start - شروع
/l یا /languages - لیست زبان‌ها
/sl یا /setlang - تنظیم زبان
/st یا /status - وضعیت فعلی
/h یا /help - راهنما
/stats - آمار ربات

**🌐 زبان فعلی شما:** {lang_display}

📝 **نحوه استفاده:**
1. با /setlang زبان مقصد را انتخاب کنید
2. هر متنی بفرستید تا ترجمه شود
3. برای تغییر سریع، کد زبان را مستقیم بفرستید
        """
        await message.reply(welcome)
        return
    
    # لیست زبان‌ها
    if user_text in ['/languages', '/l']:
        lang_list = []
        for code, info in LANGUAGES.items():
            lang_list.append(f"{info['emoji']} `{code}` → {info['name']}")
        
        popular = ['fa', 'en', 'ar', 'tr', 'de', 'fr', 'es', 'ru']
        popular_langs = [f"{LANGUAGES[code]['emoji']} `{code}` → {LANGUAGES[code]['name']}" 
                        for code in popular if code in LANGUAGES]
        other_langs = [lang for lang in lang_list 
                      if not any(code in lang for code in popular)]
        
        reply = f"""
🌍 **زبان‌های قابل ترجمه**

**📌 پرکاربردترین:**
{chr(10).join(popular_langs)}

**📌 سایر زبان‌ها:**
{chr(10).join(other_langs[:15])}

💡 **نکته:** برای تغییر زبان، کد آن را مستقیم بفرستید
مثال: `en` برای انگلیسی، `fa` برای فارسی
        """
        await message.reply(reply)
        return
    
    # تنظیم زبان
    if user_text in ['/setlang', '/sl']:
        popular_codes = ['fa', 'en', 'ar', 'tr', 'de', 'fr', 'es']
        popular_list = "\n".join([f"{LANGUAGES[code]['emoji']} `{code}` → {LANGUAGES[code]['name']}" 
                                 for code in popular_codes if code in LANGUAGES])
        
        reply = f"""
🗣 **تنظیم زبان مقصد**

کد زبان مورد نظر را وارد کنید.

**زبان‌های پرکاربرد:**
{popular_list}

**برای مشاهده همه زبان‌ها:** /languages

📝 **مثال:** کد `en` را بفرستید تا زبان مقصد انگلیسی شود.
        """
        user_states[user_id] = 'waiting_for_lang'
        await message.reply(reply)
        return
    
    # وضعیت کاربر
    if user_text in ['/status', '/st']:
        target_lang = user_manager.get_target_lang(user_id)
        lang_display = get_lang_display(target_lang)
        user_stats = user_manager.get_user_stats(user_id)
        
        reply = f"""
📊 **وضعیت شما**

👤 **شناسه:** `{user_id[:8]}...`

🌐 **زبان مقصد:** {lang_display}

📝 **تعداد ترجمه:** {format_number(user_stats['count'])} 

⏱️ **آخرین ترجمه:** {user_stats['last_use'][:10] if user_stats['last_use'] else 'ندارد'}

💡 **تغییر زبان:** /setlang یا کد زبان را مستقیم بفرستید
        """
        await message.reply(reply)
        return
    
    # آمار ربات
    if user_text in ['/stats']:
        total = bot_stats.get('total_translations', 0)
        users_count = len(bot_stats.get('users', {}))
        
        active_users = sorted(
            bot_stats.get('users', {}).items(),
            key=lambda x: x[1].get('count', 0),
            reverse=True
        )[:5]
        
        top_users = ""
        for i, (uid, data) in enumerate(active_users, 1):
            count = data.get('count', 0)
            top_users += f"{i}. کاربر `{uid[:8]}...` → {format_number(count)} ترجمه\n"
        
        reply = f"""
📊 **آمار کلی ربات**

📝 **کل ترجمه‌ها:** {format_number(total)}
👥 **کاربران فعال:** {format_number(users_count)}

**🏆 کاربران برتر:**
{top_users if top_users else 'هنوز کاربری ثبت نشده'}

⚡ **وضعیت:** آنلاین ✅
        """
        await message.reply(reply)
        return
    
    # راهنما
    if user_text in ['/help', '/h']:
        reply = """
📖 **راهنمای کامل ربات**

**⚡ دستورات سریع:**
• `/s` - شروع مجدد
• `/l` - لیست زبان‌ها
• `/sl` - تنظیم زبان مقصد
• `/st` - وضعیت فعلی
• `/stats` - آمار ربات
• `/h` - این راهنما

**🌐 تغییر زبان سریع:**
فقط کد زبان را بفرستید:
`en` → انگلیسی
`fa` → فارسی
`ar` → عربی

**📝 ترجمه متن:**
• هر متنی بفرستید، ترجمه می‌شود
• تشخیص خودکار زبان مبدأ
• پشتیبانی از متون طولانی

**💡 نکات:**
• تنظیمات شما ذخیره می‌شود
• ترجمه‌های تکراری کش می‌شوند
• آمار ترجمه‌ها نگهداری می‌شود
        """
        await message.reply(reply)
        return
    
    # ========== تغییر سریع زبان با کد مستقیم ==========
    if len(user_text) <= 5 and user_text.lower() in LANGUAGES:
        lang_code = user_text.lower()
        lang_info = get_lang_info(lang_code)
        
        if user_manager.set_target_lang(user_id, lang_code):
            await message.reply(f"""
✅ **زبان تغییر کرد!**

🌐 زبان مقصد: {lang_info['emoji']} **{lang_info['name']}** (`{lang_code}`)

⚡ حالا هر متنی بفرستید به {lang_info['name']} ترجمه می‌شود.
            """)
        else:
            await message.reply("❌ خطا در ذخیره تنظیمات!")
        return
    
    # ========== مدیریت انتخاب زبان ==========
    if user_id in user_states and user_states[user_id] == 'waiting_for_lang':
        lang_code = user_text.lower()
        
        if lang_code in LANGUAGES:
            if user_manager.set_target_lang(user_id, lang_code):
                del user_states[user_id]
                lang_info = get_lang_info(lang_code)
                await message.reply(f"""
✅ **زبان با موفقیت تنظیم شد!**

🌐 زبان مقصد: {lang_info['emoji']} **{lang_info['name']}** (`{lang_code}`)

✨ حالا هر متنی بفرستید به {lang_info['name']} ترجمه می‌شود.
                """)
            else:
                await message.reply("❌ خطا در ذخیره تنظیمات!")
        else:
            suggestions = [code for code in LANGUAGES.keys() if code.startswith(lang_code[:2])]
            suggest_text = f"\n\n💡 شاید منظور شما: {', '.join([f'`{code}`' for code in suggestions[:3]])}" if suggestions else ""
            
            await message.reply(f"""
❌ **کد زبان نامعتبر!**

کد `{user_text}` در لیست وجود ندارد.

📋 برای مشاهده لیست کامل: /languages
{suggest_text}
            """)
        return
    
    # ========== ترجمه متن با deep-translator ==========
    if len(user_text) < 2:
        await message.reply("📝 لطفاً متن معتبری برای ترجمه بفرستید.")
        return
    
    try:
        # ارسال پیام در حال پردازش
        status_msg = await message.reply("⏳ در حال ترجمه...")
        
        # دریافت زبان مقصد
        target_lang = user_manager.get_target_lang(user_id)
        target_info = get_lang_info(target_lang)
        
        # تشخیص زبان مبدأ
        try:
            loop = asyncio.get_event_loop()
            detected_lang = await loop.run_in_executor(
                executor,
                safe_translator.detect_language,
                user_text
            )
        except Exception as e:
            logger.error(f"خطا در تشخیص زبان: {e}")
            detected_lang = 'en'
        
        # اگر زبان مبدأ و مقصد یکی بود
        if detected_lang == target_lang:
            await status_msg.edit(f"ℹ️ متن شما به {target_info['emoji']} **{target_info['name']}** است. نیازی به ترجمه نیست!")
            return
        
        # ترجمه با deep-translator
        try:
            # ترجمه در thread جداگانه
            translated_text = await loop.run_in_executor(
                executor,
                safe_translator.translate_text,
                user_text,
                detected_lang,
                target_lang
            )
            
            # بررسی نتیجه
            if translated_text is None:
                await status_msg.edit("❌ خطا در ترجمه! لطفاً دوباره تلاش کنید یا زبان مقصد را تغییر دهید.")
                return
            
            # اگر خطا بود
            if translated_text.startswith("⚠️") or translated_text.startswith("❌"):
                await status_msg.edit(translated_text)
                return
            
            # افزایش آمار
            user_manager.increment_translation(user_id)
            
            # اطلاعات زبان‌ها
            src_info = get_lang_info(detected_lang)
            
            # نمایش نتیجه
            reply_text = f"""
{src_info['emoji']} **{src_info['name']}** → {target_info['emoji']} **{target_info['name']}**

📝 **متن اصلی:**
_{user_text[:200]}{'...' if len(user_text) > 200 else ''}_

✅ **ترجمه:**
{translated_text}
            """
            
            if len(user_text) > 200:
                reply_text += f"\n\n📊 **طول متن:** {len(user_text)} کاراکتر"
            
            await status_msg.edit(reply_text)
            
        except Exception as e:
            logger.error(f"خطا در ترجمه: {e}")
            await status_msg.edit("❌ خطا در ترجمه! لطفاً دوباره تلاش کنید یا زبان مقصد را تغییر دهید.")
            
    except Exception as e:
        logger.error(f"خطای عمومی: {e}")
        await message.reply("❌ خطای غیرمنتظره! لطفاً دوباره تلاش کنید.")

# ========== Flask App برای Render ==========
app = Flask(__name__)

@app.route('/')
@app.route('/health')
def health_check():
    return "🤖 ربات ترجمه در حال اجراست!", 200

def run_bot():
    """اجرای ربات در یک ترد جداگانه"""
    print("=" * 50)
    print("🤖 ربات ترجمه حرفه‌ای با deep-translator")
    print("=" * 50)
    print(f"📊 {len(user_settings)} کاربر تنظیمات ذخیره شده دارند.")
    print(f"🌍 {len(LANGUAGES)} زبان پشتیبانی می‌شود.")
    print(f"📝 {bot_stats.get('total_translations', 0)} ترجمه انجام شده.")
    print("=" * 50)
    print("✅ ربات آماده به کار است!")
    print("=" * 50)
    
    try:
        bot.run()
    except Exception as e:
        print(f"❌ خطا در اجرای ربات: {e}")

# ========== شروع برنامه ==========
if __name__ == "__main__":
    # ربات را در یک ترد جداگانه اجرا کن
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # وب سرور Flask را برای Render اجرا کن
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 وب سرور روی پورت {port} در حال اجراست...")
    app.run(host='0.0.0.0', port=port)
