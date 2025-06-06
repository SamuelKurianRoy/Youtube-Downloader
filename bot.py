# Main modules
import os
import sys
import json
import re
import time
import asyncio
import logging
import zipfile
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Union, Tuple, Callable, Awaitable
from urllib.parse import urlparse

# Third-party libraries
try:
    import yt_dlp
except ImportError:
    debug_write("ERROR: yt_dlp not installed")
    
try:
    import openai
except ImportError:
    debug_write("ERROR: openai not installed")
    
try:
    import requests
except ImportError:
    debug_write("ERROR: requests not installed")
    
try:
    from telegram import Bot, Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
    from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
    from telegram.constants import ParseMode, ChatAction
except ImportError:
    debug_write("ERROR: python-telegram-bot not installed")
    
try:
    from dotenv import load_dotenv
except ImportError:
    debug_write("ERROR: python-dotenv not installed")
    
    # Simple replacement for load_dotenv
    def load_dotenv():
        debug_write("Using simple replacement for load_dotenv")
        env_file = Path.cwd() / ".env"
        if env_file.exists():
            with open(env_file, "r") as f:
                for line in f:
                    if "=" in line and not line.startswith("#"):
                        key, value = line.strip().split("=", 1)
                        os.environ[key] = value
                        debug_write(f"Set environment variable from .env file: {key}")

# Replace with new logging configuration
import logging.handlers
import subprocess
import signal
try:
    from debug import debug_write
except ImportError:
    # Create a simple debug_write function if the module doesn't exist
    def debug_write(message):
        print(f"DEBUG: {message}")

# Add this at the start of the script
debug_write("Bot module loaded")

# Update the setup_logging function
def setup_logging():
    """Configure logging with file output and filters."""
    debug_write("Setting up logging")
    
    # Create logs directory if it doesn't exist
    base_dir = Path.cwd()
    log_dir = base_dir / "logs"
    
    try:
        log_dir.mkdir(exist_ok=True)
        debug_write(f"Log directory created/verified at {log_dir}")
    except Exception as e:
        debug_write(f"Failed to create log directory: {e}")
        # Fallback to a temporary directory
        import tempfile
        log_dir = Path(tempfile.gettempdir()) / "telegram-ytdl-logs"
        log_dir.mkdir(exist_ok=True)
        debug_write(f"Using fallback log directory: {log_dir}")
    
    # Create formatters
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Setup bot log handler with rotation (for errors and system messages)
    bot_log_path = log_dir / "bot.log"
    try:
        # First try to create the file if it doesn't exist
        if not bot_log_path.exists():
            with open(bot_log_path, 'w') as f:
                f.write("")
            debug_write(f"Created bot log file at {bot_log_path}")
            
        bot_handler = logging.handlers.RotatingFileHandler(
            bot_log_path,
            maxBytes=1024 * 1024,  # 1MB
            backupCount=5,
            encoding='utf-8'
        )
        bot_handler.setFormatter(file_formatter)
        bot_handler.setLevel(logging.INFO)
        debug_write("Bot log handler created successfully")
    except Exception as e:
        debug_write(f"Failed to create bot log handler: {e}")
        # Use a stream handler as fallback
        bot_handler = logging.StreamHandler()
        bot_handler.setFormatter(console_formatter)
        bot_handler.setLevel(logging.INFO)
    
    # Setup user log handler with rotation (for user activity)
    user_log_path = log_dir / "user.log"
    try:
        # First try to create the file if it doesn't exist
        if not user_log_path.exists():
            with open(user_log_path, 'w') as f:
                f.write("")
            print(f"Created user log file at {user_log_path}")
            
        user_handler = logging.handlers.RotatingFileHandler(
            user_log_path,
            maxBytes=1024 * 1024,  # 1MB
            backupCount=5,
            encoding='utf-8'
        )
        user_handler.setFormatter(file_formatter)
        user_handler.setLevel(logging.INFO)
    except Exception as e:
        print(f"Failed to create user log handler: {e}")
        # Use a stream handler as fallback
        user_handler = logging.StreamHandler()
        user_handler.setFormatter(console_formatter)
        user_handler.setLevel(logging.INFO)
    
    # Setup console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO)
    
    # Create loggers
    bot_logger = logging.getLogger(__name__)
    bot_logger.setLevel(logging.INFO)
    
    user_logger = logging.getLogger("user_activity")
    user_logger.setLevel(logging.INFO)
    
    # Remove existing handlers
    bot_logger.handlers.clear()
    user_logger.handlers.clear()
    
    # Add our handlers
    bot_logger.addHandler(bot_handler)
    bot_logger.addHandler(console_handler)
    
    user_logger.addHandler(user_handler)
    
    # Set httpx logger to WARNING level to suppress request logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    # Write initial log entries to verify logging is working
    bot_logger.info("Logging initialized")
    user_logger.info("User activity logging initialized")
    
    print(f"Logging setup complete. Bot log: {bot_log_path}, User log: {user_log_path}")
    
    return bot_logger, user_logger

# Initialize logging
logger, user_logger = setup_logging()

# Load environment variables
# First try to load from .env file
try:
    load_dotenv()
except Exception as e:
    logger.warning(f"Could not load .env file: {e}")

# Environment variables
class Environment:
    def __init__(self):
        debug_write("Initializing Environment class")
        
        # Try to load from .env file
        try:
            load_dotenv()
            debug_write("Loaded .env file")
        except Exception as e:
            debug_write(f"Could not load .env file: {e}")
        
        # Try to load from Streamlit secrets
        try:
            import streamlit as st
            for key in st.secrets:
                if isinstance(st.secrets[key], dict):
                    # Handle nested secrets
                    for subkey, value in st.secrets[key].items():
                        full_key = f"{key}_{subkey}".upper()
                        os.environ[full_key] = str(value)
                        debug_write(f"Set environment variable from Streamlit secrets: {full_key}")
                else:
                    os.environ[key] = str(st.secrets[key])
                    debug_write(f"Set environment variable from Streamlit secrets: {key}")
            debug_write("Loaded Streamlit secrets")
        except Exception as e:
            debug_write(f"Could not load Streamlit secrets: {e}")
        
        # Bot token is required
        self.BOT_TOKEN = self.get_variable("TELEGRAM_BOT_TOKEN", "")
        debug_write(f"Bot token: {'Set' if self.BOT_TOKEN else 'Not set'}")

        # Handle webhook settings - completely ignore them to prevent issues
        self.WEBHOOK_PORT = None
        self.WEBHOOK_URL = ""
        self.API_ROOT = self.get_variable("TELEGRAM_API_ROOT", "")
        if self.API_ROOT and not self.API_ROOT.startswith(("http://", "https://")):
            debug_write(f"Invalid API_ROOT: {self.API_ROOT}, setting to default")
            self.API_ROOT = "https://api.telegram.org"
            os.environ["TELEGRAM_API_ROOT"] = self.API_ROOT
        
        # Admin and whitelist settings
        admin_id = self.get_variable("ADMIN_ID", "")
        self.ADMIN_ID = int(admin_id) if admin_id.strip() and admin_id.strip().isdigit() else None
        
        # Whitelisted IDs
        whitelist_str = self.get_variable("WHITELISTED_IDS", "")
        self.WHITELISTED_IDS = []
        if whitelist_str.strip():
            try:
                # Try to parse as JSON array first
                self.WHITELISTED_IDS = json.loads(whitelist_str)
            except:
                # Fall back to comma-separated list
                self.WHITELISTED_IDS = [int(id.strip()) for id in whitelist_str.split(",") if id.strip().isdigit()]
        
        # Add admin to whitelist if set
        if self.ADMIN_ID and self.ADMIN_ID not in self.WHITELISTED_IDS:
            self.WHITELISTED_IDS.append(self.ADMIN_ID)
        
        self.ALLOW_GROUPS = self.get_variable("ALLOW_GROUPS", "false").lower() != "false"

        # YT-DLP settings
        self.YTDL_AUTOUPDATE = self.get_variable("YTDL_AUTOUPDATE", "true").lower() == "true"

        # API keys
        self.OPENAI_API_KEY = self.get_variable("OPENAI_API_KEY", "")
        self.COBALT_INSTANCE_URL = self.get_variable("COBALT_INSTANCE_URL", "")
        
        # Paths
        self.BASE_DIR = Path.cwd()
        self.STORAGE_DIR = self.BASE_DIR / "storage"
        self.COOKIE_FILE = self.STORAGE_DIR / "cookies.txt"
        self.TRANSLATIONS_FILE = self.STORAGE_DIR / "saved-translations.json"
        self.USER_PREFS_FILE = self.STORAGE_DIR / "user-preferences.json"

        # Create storage directory if it doesn't exist
        self.STORAGE_DIR.mkdir(exist_ok=True)
        debug_write(f"Storage directory: {self.STORAGE_DIR}")

        debug_write("Environment initialized")

    def get_variable(self, name, default=""):
        """Get an environment variable."""
        value = os.environ.get(name, default)
        return value

    def get_cookie_args(self) -> List[str]:
        if self.COOKIE_FILE.exists() and self.COOKIE_FILE.is_file():
            return ["--cookies", str(self.COOKIE_FILE)]
        return []

# Initialize environment
env = Environment()

# Check for required environment variables
if not env.BOT_TOKEN:
    logger.error("TELEGRAM_BOT_TOKEN is not set. Bot cannot start.")
    exit(1)

# Constants
class Text:
    DENIED_MESSAGE = (
        "<b>This bot is private.</b>\n\n"
        "If you want to use this bot, please contact the administrator."
    )

# Callback data prefixes (simplified for audio only)
class CallbackPrefix:
    AUDIO_QUALITY = "aq:"  # aq:high, aq:medium, aq:low
    CANCEL = "cancel"

# Audio quality options
class AudioQuality:
    HIGH = "high"     # 320kbps
    MEDIUM = "medium" # 192kbps
    LOW = "low"       # 128kbps

# User preferences
class UserPreferences:
    def __init__(self, prefs_file: Path):
        self.prefs_file = prefs_file
        self.preferences = self.load_preferences()
    
    def load_preferences(self) -> Dict:
        """Load saved user preferences from file."""
        if self.prefs_file.exists():
            with open(self.prefs_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    async def save_preferences(self):
        """Save user preferences to file."""
        with open(self.prefs_file, 'w', encoding='utf-8') as f:
            json.dump(self.preferences, f, indent=2)
    
    def get_user_preference(self, user_id: int, key: str, default=None):
        """Get a specific preference for a user."""
        user_id_str = str(user_id)
        if user_id_str in self.preferences and key in self.preferences[user_id_str]:
            return self.preferences[user_id_str][key]
        return default
    
    async def set_user_preference(self, user_id: int, key: str, value):
        """Set a specific preference for a user."""
        user_id_str = str(user_id)
        if user_id_str not in self.preferences:
            self.preferences[user_id_str] = {}
        self.preferences[user_id_str][key] = value
        await self.save_preferences()

# HTML formatting helpers
def bold(text: str) -> str:
    return f"<b>{text}</b>"

def italic(text: str) -> str:
    return f"<i>{text}</i>"

def code(text: str) -> str:
    return f"<code>{escape_code(text)}</code>"

def pre(text: str) -> str:
    return f"<pre>{escape_code(text)}</pre>"

def underline(text: str) -> str:
    return f"<u>{text}</u>"

def strikethrough(text: str) -> str:
    return f"<s>{text}</s>"

def link(text: str, url: str) -> str:
    return f"<a href=\"{url}\">{text}</a>"

def quote(text: str) -> str:
    return f"<blockquote>{text}</blockquote>"

def mention(text: str, user_id: int) -> str:
    return f"<a href=\"tg://user?id={user_id}\">{text}</a>"

# Escape code for HTML
def escape_code(text: str) -> str:
    replacements = {
        '`': '\\`',
        '\\': '\\\\',
        '<': '&lt;',
        '>': '&gt;',
        '&': '&amp;',
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text

# Utility functions
def remove_hashtags_mentions(text: str) -> str:
    if not text:
        return text
    return re.sub(r'[#@]\S+', '', text).strip()

def chunk_array(array: List, chunk_size: int) -> List[List]:
    """Split an array into chunks of specified size."""
    return [array[i:i + chunk_size] for i in range(0, len(array), chunk_size)]

def cutoff_with_notice(text: str) -> str:
    """Cut off text if it exceeds Telegram's limit and add a notice."""
    if len(text) > 4000 - len(Text.CUTOFF_NOTICE):
        return text[:4000 - len(Text.CUTOFF_NOTICE)] + Text.CUTOFF_NOTICE
    return text

def url_matcher(url: str, matcher: str) -> bool:
    """Check if URL matches a specific domain."""
    parsed = urlparse(url)
    return parsed.netloc.endswith(matcher)

def detect_platform(url: str) -> str:
    """Detect the platform from URL."""
    url_lower = url.lower()

    # YouTube
    if any(domain in url_lower for domain in ['youtube.com', 'youtu.be', 'music.youtube.com']):
        return 'YouTube'

    # Instagram
    elif any(domain in url_lower for domain in ['instagram.com', 'instagr.am']):
        return 'Instagram'

    # Spotify
    elif 'spotify.com' in url_lower:
        return 'Spotify'

    # TikTok
    elif 'tiktok.com' in url_lower:
        return 'TikTok'

    # Twitter/X
    elif any(domain in url_lower for domain in ['twitter.com', 'x.com']):
        return 'Twitter/X'

    # SoundCloud
    elif 'soundcloud.com' in url_lower:
        return 'SoundCloud'

    # Facebook
    elif any(domain in url_lower for domain in ['facebook.com', 'fb.watch']):
        return 'Facebook'

    # Default
    else:
        return 'Unknown Platform'

def is_supported_url(url: str) -> bool:
    """Check if the URL is from a supported platform."""
    # Platforms that actually work well with yt-dlp without authentication
    supported_domains = [
        'youtube.com', 'youtu.be', 'music.youtube.com',
        'spotify.com',  # Now supported via spotdl
        'tiktok.com',
        'twitter.com', 'x.com',
        'soundcloud.com',
        'facebook.com', 'fb.watch',
        'vimeo.com',
        'dailymotion.com',
        'twitch.tv'
    ]

    url_lower = url.lower()
    return any(domain in url_lower for domain in supported_domains)

def is_limited_support_url(url: str) -> bool:
    """Check if the URL is from a platform with limited/conditional support."""
    limited_domains = [
        'instagram.com', 'instagr.am',  # Requires authentication
    ]

    url_lower = url.lower()
    return any(domain in url_lower for domain in limited_domains)

def is_spotify_url(url: str) -> bool:
    """Check if the URL is from Spotify."""
    return 'spotify.com' in url.lower()

def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

# Queue implementation for processing downloads
class Queue:
    def __init__(self):
        self.queue = []
        self.running = False
        self.lock = asyncio.Lock()
    
    async def run(self, executor):
        try:
            await executor()
        except Exception as e:
            logger.error(f"Error in queue executor: {e}")
    
    async def bump(self):
        async with self.lock:
            if self.running:
                return
            self.running = True
        
        try:
            while self.queue:
                next_up = self.queue.pop(0)
                if next_up:
                    await self.run(next_up)
        finally:
            async with self.lock:
                self.running = False
    
    def add(self, executor):
        self.queue.append(executor)
        asyncio.create_task(self.bump())

# Translation service
class TranslationService:
    def __init__(self, api_key: str, translations_file: Path):
        self.api_key = api_key
        self.translations_file = translations_file
        self.saved_translations = self.load_translations()
    
    def load_translations(self) -> Dict:
        """Load saved translations from file."""
        if self.translations_file.exists():
            with open(self.translations_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    async def save_translations(self):
        """Save translations to file."""
        with open(self.translations_file, 'w', encoding='utf-8') as f:
            json.dump(self.saved_translations, f, indent=2)
    
    async def translate_text(self, text: str, lang: str) -> str:
        """Translate text to the specified language."""
        if not self.api_key:
            return text
        
        # Check if we already have this translation
        if text in self.saved_translations and lang in self.saved_translations[text]:
            return self.saved_translations[text][lang]
        
        try:
            client = openai.OpenAI(api_key=self.api_key)
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": f"Translate text to the following IETF language tag: {lang}. "
                                  f"Keep the HTML formatting. Do not add any other text or explanations"
                    },
                    {"role": "user", "content": text}
                ],
                temperature=0.2,
                max_tokens=256
            )
            
            translated = response.choices[0].message.content
            
            if not translated:
                return text
            
            # Save the translation
            if text not in self.saved_translations:
                self.saved_translations[text] = {}
            self.saved_translations[text][lang] = translated
            
            await self.save_translations()
            return translated
            
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return text

# YT-DLP Updater
class Updater:
    def __init__(self, enabled: bool):
        self.enabled = enabled
        self.updating = False
        self._scheduled_update = None
        
        logger.info(f"Auto-update is {'enabled' if self.enabled else 'disabled'}")
        
        if self.enabled:
            # Schedule update at 4:20 AM daily
            self._schedule_next_update()
    
    def _schedule_next_update(self):
        """Schedule the next update."""
        now = datetime.now()
        target_hour, target_minute = 4, 20
        
        # Calculate seconds until next 4:20 AM
        if now.hour > target_hour or (now.hour == target_hour and now.minute >= target_minute):
            # Next day
            seconds = ((24 - now.hour + target_hour) * 3600 + 
                      (target_minute - now.minute) * 60 - 
                      now.second)
        else:
            # Same day
            seconds = ((target_hour - now.hour) * 3600 + 
                      (target_minute - now.minute) * 60 - 
                      now.second)
        
        logger.info(f"Next update scheduled in {seconds} seconds")
        self._scheduled_update = asyncio.get_event_loop().call_later(
            seconds, lambda: asyncio.create_task(self.update())
        )
    
    async def update(self):
        """Update yt-dlp."""
        if self.updating:
            return
            
        self.updating = True
        try:
            logger.info("Updating yt-dlp")
            
            # Run yt-dlp update command
            process = await asyncio.create_subprocess_exec(
                "pip", "install", "--upgrade", "yt-dlp",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info(f"yt-dlp updated: {stdout.decode()}")
            else:
                logger.error(f"yt-dlp update failed: {stderr.decode()}")
                
        except Exception as e:
            logger.error(f"Error updating yt-dlp: {e}")
        finally:
            self.updating = False
            self._schedule_next_update()

# Cobalt API Integration
class CobaltAPI:
    def __init__(self, instance_url: str):
        self.instance_url = instance_url
        self.instance_info = None
        
        # Initialize regexes for matching URLs
        self.cobalt_regexes = [
            # TikTok photo slides
            re.compile(r'^(?:https:\/\/)?(?:www\.)?tiktok\.com\/@\w+\/photo\/\d+.*'),
            # Add more regexes as needed
        ]
    
    async def check_instance(self) -> bool:
        """Check if the Cobalt instance is valid and available."""
        if not self.instance_url:
            return False
            
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(self.instance_url, timeout=5)
            )
            
            if response.status_code != 200:
                logger.warning("Invalid Cobalt instance URL")
                return False
                
            self.instance_info = response.json()
            logger.info(f"Cobalt instance found, version {self.instance_info['cobalt']['version']}")
            return True
            
        except Exception as e:
            logger.error(f"Error checking Cobalt instance: {e}")
            return False
    
    def matches_url(self, url: str) -> bool:
        """Check if URL can be processed by Cobalt."""
        if not self.instance_info:
            return False
            
        return any(regex.match(url) for regex in self.cobalt_regexes)
    
    async def resolve_url(self, url: str) -> Dict:
        """Resolve a URL using Cobalt API."""
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, 
                lambda: requests.post(
                    self.instance_url,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    json={"url": url},
                    timeout=10
                )
            )
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Error resolving URL with Cobalt: {e}")
            return {"status": "error", "error": {"code": "request_failed", "message": str(e)}}

# Media utilities
def get_thumbnail(thumbnails: List[Dict]) -> Optional[str]:
    """Get a suitable thumbnail URL within Telegram's size limits."""
    if not thumbnails:
        return None
        
    MAX_SIZE = 320
    
    # Reverse to get largest to smallest
    reversed_thumbnails = thumbnails[::-1]
    
    for thumbnail in reversed_thumbnails:
        width = thumbnail.get('width')
        height = thumbnail.get('height')
        
        if width and height and width <= MAX_SIZE and height <= MAX_SIZE:
            return thumbnail['url']
            
        resolution = thumbnail.get('resolution')
        if resolution:
            try:
                w, h = map(int, resolution.split('x'))
                if w <= MAX_SIZE and h <= MAX_SIZE:
                    return thumbnail['url']
            except (ValueError, IndexError):
                pass
                
    # If no suitable thumbnail found, return the smallest one
    if thumbnails:
        return thumbnails[0]['url']
    
    return None

# Telegram Bot
class TelegramYTDLBot:
    def __init__(self):
        debug_write("Initializing TelegramYTDLBot")
        
        # Initialize application
        self.application = None
        self.bot = None
        
        # Initialize other components
        self.queue = None  # Will be initialized later
        self.updater = None  # Will be initialized later
        self.translation = None  # Will be initialized later
        self.cobalt = None  # Will be initialized later
        self.user_prefs = None  # Will be initialized later
        
        # TikTok special arguments
        self.tiktok_args = [
            "--extractor-args",
            "tiktok:api_hostname=api16-normal-c-useast1a.tiktokv.com;app_info=7355728856979392262"
        ]
        
        # FFmpeg path
        self.ffmpeg_path = None
        
        # Flag to check if bot should be running
        self.should_run = True
        
        debug_write("TelegramYTDLBot initialized")

    def _validate_bot_token(self, token):
        """Validate that the bot token has the correct format."""
        if not token:
            return False

        # Bot tokens should have the format: <bot_id>:<bot_secret>
        # bot_id should be numeric, bot_secret should be alphanumeric
        if ":" not in token:
            debug_write("Bot token missing colon separator")
            return False

        parts = token.split(":", 1)
        if len(parts) != 2:
            debug_write("Bot token has incorrect format")
            return False

        bot_id, bot_secret = parts

        # Bot ID should be numeric
        if not bot_id.isdigit():
            debug_write("Bot ID is not numeric")
            return False

        # Bot secret should be at least 20 characters
        if len(bot_secret) < 20:
            debug_write("Bot secret is too short")
            return False

        # Bot secret should be alphanumeric with some special characters
        import re
        if not re.match(r'^[A-Za-z0-9_-]+$', bot_secret):
            debug_write("Bot secret contains invalid characters")
            return False

        debug_write("Bot token validation passed")
        return True

    async def initialize(self):
        """Initialize the bot and its components."""
        try:
            debug_write("Initializing bot components")

            # Check for required environment variables
            if not env.BOT_TOKEN:
                debug_write("ERROR: TELEGRAM_BOT_TOKEN is not set. Bot cannot start.")
                return False

            # Validate bot token format
            if not self._validate_bot_token(env.BOT_TOKEN):
                debug_write("ERROR: Invalid bot token format. Bot cannot start.")
                return False

            # Clear all webhook settings to prevent URL issues
            clear_webhook_settings()

            # Fix environment variables that might be causing issues
            self._fix_environment_variables()

            # Initialize application with simplified approach
            debug_write("Building application with direct token")

            # Create a clean environment for the bot
            clean_token = env.BOT_TOKEN.strip()
            debug_write(f"Using token: {clean_token[:5]}...")

            # Create the application directly without using environment variables
            from telegram.ext import ApplicationBuilder

            # Create a completely new application builder with minimal configuration
            builder = ApplicationBuilder()
            builder.token(clean_token)

            # DO NOT set base_url - let it use the default
            # This avoids URL parsing issues that were causing the port error
            debug_write("Using default Telegram API configuration")

            # Build the application
            self.application = builder.build()
            debug_write("Application built successfully")

            # Initialize the application
            debug_write("Initializing application")
            await self.application.initialize()
            debug_write("Application initialized")
            
            # Get bot instance
            self.bot = self.application.bot
            debug_write("Bot instance retrieved")
            
            # Initialize other components (using classes defined in this file)
            self.queue = Queue()
            self.updater = Updater(env.YTDL_AUTOUPDATE)
            self.translation = TranslationService(env.OPENAI_API_KEY, env.TRANSLATIONS_FILE)
            self.cobalt = CobaltAPI(env.COBALT_INSTANCE_URL)
            self.user_prefs = UserPreferences(env.USER_PREFS_FILE)
            
            # Set up handlers
            self.setup_handlers()
            debug_write("Handlers set up")
            
            # Setup FFmpeg
            await self.setup_ffmpeg()
            
            debug_write("Bot initialized successfully")
            return True
            
        except Exception as e:
            debug_write(f"ERROR: Error initializing bot: {e}")
            import traceback
            debug_write(f"Traceback: {traceback.format_exc()}")
            return False

    def _fix_environment_variables(self):
        """Fix environment variables that might be causing issues"""
        debug_write("Fixing environment variables")

        # Clear all webhook-related variables to prevent URL parsing issues
        webhook_vars = ["TELEGRAM_WEBHOOK_PORT", "TELEGRAM_WEBHOOK_URL", "TELEGRAM_API_ROOT"]
        for var in webhook_vars:
            if var in os.environ:
                old_value = os.environ[var]
                os.environ[var] = ""
                debug_write(f"Cleared {var}: {old_value[:10] if old_value else 'empty'}...")

        # Ensure the bot token is in the right place and properly formatted
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if bot_token:
            # Clean the token of any extra whitespace or quotes
            bot_token = bot_token.strip('"\'')
            os.environ["TELEGRAM_BOT_TOKEN"] = bot_token
            debug_write(f"Cleaned bot token: {bot_token[:5]}...")

        debug_write("Environment variables fixed")

    async def setup_ffmpeg(self):
        """Setup FFmpeg and add it to PATH."""
        try:
            self.ffmpeg_path = await download_ffmpeg()
            if self.ffmpeg_path:
                # Add FFmpeg directory to PATH
                current_path = os.environ.get("PATH", "")
                if self.ffmpeg_path not in current_path:
                    os.environ["PATH"] = self.ffmpeg_path + os.pathsep + current_path
                logger.info(f"FFmpeg set up at: {self.ffmpeg_path}")
            else:
                logger.warning("FFmpeg not available - some audio conversions may not work")
                logger.info("Bot will try to download audio in native formats when possible")
            return self.ffmpeg_path
        except Exception as e:
            logger.error(f"Error setting up FFmpeg: {e}")
            logger.info("Continuing without FFmpeg - some features may be limited")
            return None

    async def start(self):
        """Start the bot with proper initialization."""
        try:
            debug_write("Starting bot")
            
            # Initialize bot components
            debug_write("Initializing bot components")
            success = await self.initialize()
            if not success:
                debug_write("ERROR: Failed to initialize bot. Exiting.")
                return
            
            debug_write("Bot initialized successfully, starting polling")
            
            # Check for Streamlit Cloud flag file
            flag_file = Path.cwd() / "bot_running.flag"
            debug_write(f"Flag file path: {flag_file}, exists: {flag_file.exists()}")
            
            # Start polling
            debug_write("Starting bot in polling mode")
            
            await self.application.start()
            debug_write("Application started")
            
            await self.application.updater.start_polling()
            debug_write("Polling started")
            
            debug_write("Bot is now running")
            
            # Set a flag to track if we should continue running
            self.should_run = True
            
            # Block until we receive a stop signal or flag file is removed
            while self.should_run:
                # In Streamlit Cloud, check if the flag file exists
                if not flag_file.exists():
                    debug_write("Stop flag detected. Stopping bot.")
                    self.should_run = False
                    break
                
                await asyncio.sleep(5)  # Check every 5 seconds
        
        except Exception as e:
            debug_write(f"ERROR: Error running bot: {e}")
            import traceback
            debug_write(f"Traceback: {traceback.format_exc()}")
            raise
        finally:
            # Ensure proper cleanup
            if hasattr(self, 'application') and self.application:
                debug_write("Shutting down bot...")
                try:
                    if hasattr(self.application, 'updater') and self.application.updater:
                        await self.application.updater.stop()
                        debug_write("Updater stopped")
                except Exception as e:
                    debug_write(f"Error stopping updater: {e}")
                
                try:
                    await self.application.stop()
                    debug_write("Application stopped")
                except Exception as e:
                    debug_write(f"Error stopping application: {e}")
                
                try:
                    await self.application.shutdown()
                    debug_write("Application shutdown complete")
                except Exception as e:
                    debug_write(f"Error shutting down application: {e}")
                
                debug_write("Bot shutdown complete")

    @classmethod
    async def create_and_run(cls):
        """Create and run the bot."""
        try:
            debug_write("Creating bot instance")
            bot = cls()
            debug_write("Starting bot")
            await bot.start()
        except Exception as e:
            debug_write(f"ERROR: Error in create_and_run: {e}")
            import traceback
            debug_write(f"Traceback: {traceback.format_exc()}")

    @classmethod
    def run_bot(cls):
        """Run the bot with proper async handling."""
        try:
            debug_write("Starting run_bot method")
            # Create new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            debug_write("Created event loop")
            
            # Run the bot
            debug_write("Running create_and_run")
            loop.run_until_complete(cls.create_and_run())
            debug_write("create_and_run completed")
        except KeyboardInterrupt:
            debug_write("Bot stopped by user")
        except Exception as e:
            debug_write(f"ERROR: Error running bot: {e}")
            import traceback
            debug_write(f"Traceback: {traceback.format_exc()}")
        finally:
            # Clean up
            try:
                debug_write("Closing event loop")
                loop.close()
                debug_write("Event loop closed")
            except Exception as e:
                debug_write(f"ERROR: Error closing event loop: {e}")

    async def is_whitelisted(self, update: Update) -> bool:
        """Check if user is whitelisted."""
        # If no whitelist is configured, allow all users
        if len(env.WHITELISTED_IDS) == 0:
            return True
            
        # Check if user is in whitelist
        return update.effective_user.id in env.WHITELISTED_IDS

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command."""
        debug_write(f"Received /start command from user {update.effective_user.id}")
        await update.message.reply_text("🎵 Hello! Send me a link from YouTube, Spotify, TikTok, Twitter, SoundCloud and more - I'll download the audio for you!")

    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /help command."""
        debug_write(f"Received /help command from user {update.effective_user.id}")
        help_text = """🎵 *Audio Downloader Bot*

Send me a link and I'll extract the audio for you!

*✅ Fully Supported Platforms:*
• 🎥 YouTube & YouTube Music
• 🎬 TikTok
• � Twitter/X
• 🎧 SoundCloud
• 📺 Vimeo, Dailymotion, Twitch
• 📘 Facebook (public videos)

*⚠️ Limited Support:*
• 📸 Instagram (requires login/cookies)
• � Spotify (DRM protected - not downloadable)

*Audio Quality Options:*
• High (320kbps) • Medium (192kbps) • Low (128kbps)

Just send me a link to get started! 🎧"""
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages without URLs."""
        debug_write(f"Received text message from user {update.effective_user.id}")
        await update.message.reply_text("🎵 Please send me a link from YouTube, TikTok, Twitter, SoundCloud or other supported platforms to download audio.")

    async def handle_url_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle messages with URLs."""
        debug_write(f"Received URL message from user {update.effective_user.id}")

        # Check if user is whitelisted
        if not await self.is_whitelisted(update):
            await self.handle_denied_user(update, context)
            return

        # Extract URL from message
        url = None
        for entity in update.message.entities:
            if entity.type == "url":
                url = update.message.text[entity.offset:entity.offset + entity.length]
                break

        if not url:
            await update.message.reply_text("❌ No valid URL found in your message.")
            return

        # Validate URL and detect platform
        platform = detect_platform(url)

        if is_limited_support_url(url):
            # Handle platforms with limited support
            if platform == 'Instagram':
                await update.message.reply_text(
                    f"📸 *Instagram Support Limited*\n\n"
                    f"❌ Instagram requires login/cookies for most content.\n\n"
                    f"💡 *Alternatives:*\n"
                    f"• Use a browser extension to download\n"
                    f"• Try screen recording for stories\n"
                    f"• Use Instagram's built-in save feature\n\n"
                    f"✅ *Try these platforms instead:*\n"
                    f"• YouTube, TikTok, Twitter, SoundCloud",
                    parse_mode=ParseMode.MARKDOWN
                )

            return
        elif not is_supported_url(url):
            await update.message.reply_text(
                f"❌ Sorry, {platform} is not supported.\n\n"
                f"✅ *Supported platforms:*\n"
                f"• YouTube & YouTube Music\n"
                f"• Spotify (tracks, albums, playlists)\n"
                f"• TikTok, Twitter/X\n"
                f"• SoundCloud, Vimeo\n"
                f"• Facebook, Dailymotion, Twitch"
            )
            return

        # Start audio download process
        await self.start_audio_download(update, url)

    async def start_audio_download(self, update: Update, url: str):
        """Start the audio download process."""
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name or "Unknown"
        platform = detect_platform(url)

        # Log the download request with platform info
        user_logger.info(f"DOWNLOAD REQUEST | User: {username} ({user_id}) | Platform: {platform} | URL: {url}")
        debug_write(f"Starting audio download for {platform} - {url}")

        # Send initial processing message with platform info
        processing_msg = await update.message.reply_text(f"🎵 Processing {platform} link...")

        try:
            # Extract audio info
            debug_write(f"Extracting audio info for {platform}")
            info = await self.extract_audio_info(url)
            debug_write(f"Audio info extracted: {info}")

            if not info:
                debug_write(f"No info extracted for {platform} URL: {url}")
                platform_specific_msg = self.get_platform_error_message(platform)
                await processing_msg.edit_text(f"❌ Could not extract information from this {platform} link.\n\n{platform_specific_msg}")
                return

            # For Spotify, auto-download with high quality to improve user experience
            if platform == 'Spotify':
                debug_write(f"Auto-downloading Spotify with high quality")
                await processing_msg.edit_text("🎵 Starting Spotify download with high quality...")

                # Get user info for logging
                user_id = update.effective_user.id
                username = update.effective_user.username or update.effective_user.first_name or "Unknown"

                # Log auto-selection
                user_logger.info(f"AUDIO QUALITY SELECTED | User: {username} ({user_id}) | Platform: {platform} | Quality: high (auto) | URL: {url}")

                # Create a mock query object for the download function
                class MockQuery:
                    def __init__(self, message):
                        self.message = message

                    async def edit_message_text(self, text):
                        await self.message.edit_text(text)

                mock_query = MockQuery(processing_msg)
                await self.download_spotify_audio(mock_query, url, "high", username, user_id)
            else:
                # Show audio quality options for other platforms
                debug_write(f"Showing quality options for {platform}")
                await self.show_audio_quality_options(update, processing_msg, url, info)

        except Exception as e:
            debug_write(f"Error in start_audio_download for {platform}: {e}")
            platform_specific_msg = self.get_platform_error_message(platform)
            await processing_msg.edit_text(f"❌ An error occurred while processing your {platform} request.\n\n{platform_specific_msg}")

    def get_platform_error_message(self, platform: str) -> str:
        """Get platform-specific error message and tips."""
        messages = {
            'Instagram': "❌ Instagram requires login/cookies. This platform has limited support.\n💡 Try using YouTube or TikTok instead.",
            'Spotify': "💡 Tips for Spotify:\n• Make sure the track/playlist is public\n• Bot searches for tracks on YouTube\n• Some region-locked content may not be available",
            'YouTube': "💡 Tips for YouTube:\n• Check if the video is public\n• Age-restricted content may not work\n• Live streams are not supported",
            'TikTok': "💡 Tips for TikTok:\n• Make sure the video is public\n• Private accounts may not work",
            'Twitter/X': "💡 Tips for Twitter/X:\n• Make sure the tweet is public\n• Protected accounts may not work",
            'SoundCloud': "💡 Tips for SoundCloud:\n• Make sure the track is public\n• Private tracks may not work",
            'Vimeo': "💡 Tips for Vimeo:\n• Check if the video is public\n• Password-protected videos won't work",
            'Facebook': "💡 Tips for Facebook:\n• Make sure the video is public\n• Private posts may not work"
        }
        return messages.get(platform, "💡 Please check if the link is valid and publicly accessible.")

    async def extract_audio_info(self, url: str):
        """Extract basic info from the URL with platform-specific handling."""
        try:
            import yt_dlp
            platform = detect_platform(url)

            # Platform-specific options
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }

            # Add platform-specific configurations
            if platform == 'Instagram':
                ydl_opts.update({
                    'extractor_args': {
                        'instagram': {
                            'include_stories': True,
                        }
                    }
                })
            elif platform == 'Spotify':
                # For Spotify, we'll extract metadata using our custom function
                return await self.extract_spotify_info_for_display(url)
            elif platform == 'TikTok':
                ydl_opts.update({
                    'extractor_args': {
                        'tiktok': {
                            'api_hostname': 'api16-normal-c-useast1a.tiktokv.com',
                        }
                    }
                })

            # Add cookie file if available
            if env.COOKIE_FILE.exists():
                ydl_opts['cookiefile'] = str(env.COOKIE_FILE)

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # Add timeout for info extraction
                    info = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, lambda: ydl.extract_info(url, download=False)
                        ),
                        timeout=60  # 1 minute timeout for info extraction
                    )
            except asyncio.TimeoutError:
                raise Exception("Info extraction timed out after 1 minute")

            # Extract platform-specific information
            title = info.get('title', 'Unknown Title')
            uploader = info.get('uploader', info.get('channel', info.get('artist', 'Unknown')))
            duration = info.get('duration', 0)

            # For Spotify, try to get additional metadata
            if platform == 'Spotify':
                title = info.get('track', info.get('title', title))
                uploader = info.get('artist', info.get('uploader', uploader))

            return {
                'title': title,
                'duration': duration,
                'uploader': uploader,
                'platform': platform,
                'url': url
            }

        except Exception as e:
            debug_write(f"Error extracting info from {detect_platform(url)}: {e}")
            return None

    async def extract_spotify_info_for_display(self, url: str):
        """Extract Spotify info for display purposes only."""
        try:
            debug_write(f"Extracting Spotify info for display: {url}")
            track_id = self.extract_spotify_track_id(url)
            debug_write(f"Extracted track ID: {track_id}")

            if not track_id:
                debug_write("No track ID found, returning default info")
                return {
                    'title': 'Spotify Track',
                    'duration': 0,
                    'uploader': 'Spotify',
                    'platform': 'Spotify',
                    'url': url
                }

            # Try to get metadata for display
            debug_write(f"Getting metadata for track ID: {track_id}")
            metadata = await self.get_spotify_track_metadata(track_id)
            debug_write(f"Metadata result: {metadata}")

            if metadata:
                result = {
                    'title': metadata['title'],
                    'duration': 0,  # We don't have duration info
                    'uploader': metadata['artist'],
                    'platform': 'Spotify',
                    'url': url
                }
                debug_write(f"Returning metadata result: {result}")
                return result
            else:
                debug_write("No metadata found, returning default info")
                return {
                    'title': 'Spotify Track',
                    'duration': 0,
                    'uploader': 'Unknown Artist',
                    'platform': 'Spotify',
                    'url': url
                }
        except Exception as e:
            debug_write(f"Error extracting Spotify info for display: {e}")
            return {
                'title': 'Spotify Track',
                'duration': 0,
                'uploader': 'Spotify',
                'platform': 'Spotify',
                'url': url
            }

    async def show_audio_quality_options(self, update: Update, message, url: str, info: dict):
        """Show audio quality selection buttons."""
        title = info['title']
        platform = info.get('platform', 'Unknown Platform')
        uploader = info.get('uploader', 'Unknown')
        duration = info.get('duration', 0)

        if duration and isinstance(duration, (int, float)):
            duration = int(duration)  # Convert to int to avoid float formatting issues
            duration_str = f"{duration // 60}:{duration % 60:02d}"
        else:
            duration_str = "Unknown"

        # Platform emoji mapping
        platform_emojis = {
            'YouTube': '🎥',
            'Instagram': '📸',
            'Spotify': '🎵',
            'TikTok': '🎬',
            'Twitter/X': '🐦',
            'SoundCloud': '🎧',
            'Facebook': '📘'
        }

        platform_emoji = platform_emojis.get(platform, '🎵')

        text = f"{platform_emoji} *{title}*\n\n👤 {uploader}\n⏱ Duration: {duration_str}\n🌐 Platform: {platform}\n\nChoose audio quality:"

        keyboard = [
            [InlineKeyboardButton("🔊 High Quality (320kbps)", callback_data=f"{CallbackPrefix.AUDIO_QUALITY}high:{url}")],
            [InlineKeyboardButton("🎵 Medium Quality (192kbps)", callback_data=f"{CallbackPrefix.AUDIO_QUALITY}medium:{url}")],
            [InlineKeyboardButton("📻 Low Quality (128kbps)", callback_data=f"{CallbackPrefix.AUDIO_QUALITY}low:{url}")],
            [InlineKeyboardButton("❌ Cancel", callback_data=CallbackPrefix.CANCEL)]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.edit_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline buttons."""
        query = update.callback_query
        await query.answer()

        data = query.data
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name or "Unknown"

        # Log the user's selection
        user_logger.info(f"BUTTON SELECTION | User: {username} ({user_id}) | Selection: {data}")

        # Process different callback types
        if data.startswith(CallbackPrefix.AUDIO_QUALITY):
            # Parse quality and URL from callback data
            parts = data[len(CallbackPrefix.AUDIO_QUALITY):].split(":", 1)
            if len(parts) != 2:
                await query.edit_message_text("❌ Invalid selection. Please try again.")
                return

            quality, url = parts

            # Save quality preference for user
            await self.user_prefs.set_user_preference(user_id, "preferred_audio_quality", quality)

            # Log user preference and start download
            platform = detect_platform(url)
            user_logger.info(f"AUDIO QUALITY SELECTED | User: {username} ({user_id}) | Platform: {platform} | Quality: {quality} | URL: {url}")

            # Start audio download
            await query.answer(f"🎵 Starting {platform} audio download...")
            await self.download_audio(query, url, quality, username, user_id)

        elif data == CallbackPrefix.CANCEL:
            # Cancel download
            await query.answer("Download canceled")
            await query.edit_message_text("❌ Download canceled")
        else:
            await query.answer("Unknown option")

    async def download_audio(self, query, url: str, quality: str, username: str, user_id: int):
        """Download audio from the given URL with platform-specific handling."""
        start_time = time.time()
        platform = detect_platform(url)

        try:
            # Update message to show downloading status
            await query.edit_message_text(f"🎵 Downloading {platform} audio... Please wait.")

            # Create temp directory if it doesn't exist
            temp_dir = env.STORAGE_DIR / "temp"
            temp_dir.mkdir(exist_ok=True)

            # Generate unique filename
            temp_filename = f"audio_{platform.lower().replace('/', '_')}_{int(time.time())}_{user_id}"
            temp_filepath = temp_dir / temp_filename

            # Set quality-specific options
            quality_map = {
                "high": "320",
                "medium": "192",
                "low": "128"
            }

            # Prepare download options for audio only
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f"{str(temp_filepath)}.%(ext)s",
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': quality_map.get(quality, '192'),
                }],
                'quiet': True,
                'no_warnings': True,
                'noprogress': True,
            }

            # Add platform-specific configurations
            if platform == 'Instagram':
                ydl_opts.update({
                    'extractor_args': {
                        'instagram': {
                            'include_stories': True,
                        }
                    }
                })
            elif platform == 'TikTok':
                ydl_opts.update({
                    'extractor_args': {
                        'tiktok': {
                            'api_hostname': 'api16-normal-c-useast1a.tiktokv.com',
                        }
                    }
                })
            elif platform == 'Spotify':
                # For Spotify, we'll use a different approach with spotdl-like functionality
                return await self.download_spotify_audio(query, url, quality, username, user_id)
            elif platform == 'SoundCloud':
                # SoundCloud specific options
                ydl_opts.update({
                    'extractor_args': {
                        'soundcloud': {
                            'client_id': None,  # Let yt-dlp handle this
                        }
                    }
                })

            # Add FFmpeg location if available
            if self.ffmpeg_path:
                ydl_opts['ffmpeg_location'] = self.ffmpeg_path
            else:
                # If no FFmpeg available, try to download audio-only formats that don't need conversion
                logger.warning("No FFmpeg available, trying audio-only formats")
                ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio'
                # Remove post-processors that require FFmpeg
                ydl_opts['postprocessors'] = []

            # Add cookie file if available
            if env.COOKIE_FILE.exists():
                ydl_opts['cookiefile'] = str(env.COOKIE_FILE)

            download_start = time.time()
            logger.info(f"Starting audio download for user {username} ({user_id})")

            # Download the audio with timeout handling
            import yt_dlp
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # Use asyncio.wait_for to add timeout to the download
                    info = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, lambda: ydl.extract_info(url, download=True)
                        ),
                        timeout=300  # 5 minute timeout for downloads
                    )
            except asyncio.TimeoutError:
                raise Exception("Download timed out after 5 minutes")

            download_time = time.time() - download_start

            # Find the downloaded file
            downloaded_files = list(temp_dir.glob(f"{temp_filename}.*"))
            if not downloaded_files:
                raise FileNotFoundError("Download failed - no file found")

            downloaded_file = downloaded_files[0]
            file_size_mb = downloaded_file.stat().st_size / (1024 * 1024)

            # Log successful download
            title = info.get('title', 'Unknown Title')
            user_logger.info(f"DOWNLOAD COMPLETE | User: {username} ({user_id}) | Platform: {platform} | Title: {title} | URL: {url} | Quality: {quality} | Size: {file_size_mb:.2f}MB | Time: {download_time:.1f}s")

            # Send the audio file
            await query.edit_message_text("📤 Uploading audio file...")

            with open(downloaded_file, 'rb') as audio_file:
                await query.message.reply_audio(
                    audio=audio_file,
                    title=title,
                    performer=info.get('uploader', 'Unknown'),
                    duration=info.get('duration'),
                    caption=f"🎵 {title}\n\n📊 Quality: {quality_map.get(quality, '192')}kbps\n📁 Size: {file_size_mb:.1f}MB"
                )

            # Clean up
            downloaded_file.unlink()
            await query.edit_message_text(f"✅ Audio download completed!\n\n🎵 {title}")

            total_time = time.time() - start_time
            logger.info(f"Audio download completed for {username} ({user_id}) in {total_time:.1f}s")

        except Exception as e:
            error_msg = f"❌ {platform} download failed: {str(e)}"
            debug_write(f"Error downloading audio from {platform}: {e}")
            user_logger.error(f"DOWNLOAD FAILED | User: {username} ({user_id}) | Platform: {platform} | URL: {url} | Error: {str(e)}")

            try:
                await query.edit_message_text(error_msg)
            except:
                await query.message.reply_text(error_msg)

    async def download_spotify_audio(self, query, url: str, quality: str, username: str, user_id: int):
        """Download Spotify audio using spotdl command-line tool."""
        start_time = time.time()

        try:
            # Update message to show downloading status
            await query.edit_message_text("🎵 Processing Spotify link...")

            # Create temp directory if it doesn't exist
            temp_dir = env.STORAGE_DIR / "temp"
            temp_dir.mkdir(exist_ok=True)

            # Generate unique output directory for this download
            output_dir = temp_dir / f"spotify_{int(time.time())}_{user_id}"
            output_dir.mkdir(exist_ok=True)

            # Set quality-specific options
            quality_map = {
                "high": "320",
                "medium": "192",
                "low": "128"
            }

            bitrate = quality_map.get(quality, '192')

            # Prepare spotdl command
            spotdl_cmd = [
                "spotdl",
                "--bitrate", f"{bitrate}k",
                "--format", "mp3",
                "--output", str(output_dir),
                url
            ]

            await query.edit_message_text("🎵 Downloading with spotdl...")

            download_start = time.time()
            logger.info(f"Starting spotdl download for user {username} ({user_id})")

            # Run spotdl command
            import subprocess
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    spotdl_cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 minute timeout
                    cwd=str(output_dir)
                )
            )

            download_time = time.time() - download_start

            if result.returncode != 0:
                error_output = result.stderr or result.stdout
                raise Exception(f"spotdl failed: {error_output}")

            # Find the downloaded file
            downloaded_files = list(output_dir.glob("*.mp3"))
            if not downloaded_files:
                raise FileNotFoundError("Download failed - no MP3 file found")

            downloaded_file = downloaded_files[0]
            file_size_mb = downloaded_file.stat().st_size / (1024 * 1024)

            # Extract title and artist from filename or spotdl output
            filename = downloaded_file.stem
            if " - " in filename:
                parts = filename.split(" - ", 1)
                artist = parts[0].strip()
                title = parts[1].strip()
            else:
                title = filename
                artist = "Unknown Artist"

            # Log successful download
            full_title = f"{artist} - {title}"
            user_logger.info(f"DOWNLOAD COMPLETE | User: {username} ({user_id}) | Platform: Spotify | Title: {full_title} | URL: {url} | Quality: {quality} | Size: {file_size_mb:.2f}MB | Time: {download_time:.1f}s")

            # Send the audio file
            await query.edit_message_text("📤 Uploading audio file...")

            with open(downloaded_file, 'rb') as audio_file:
                await query.message.reply_audio(
                    audio=audio_file,
                    title=title,
                    performer=artist,
                    caption=f"🎵 {full_title}\n\n📊 Quality: {bitrate}kbps\n📁 Size: {file_size_mb:.1f}MB\n🎧 Source: Spotify (via spotdl)"
                )

            # Clean up
            import shutil
            shutil.rmtree(output_dir)
            await query.edit_message_text(f"✅ Spotify download completed!\n\n🎵 {full_title}")

            total_time = time.time() - start_time
            logger.info(f"Spotify download completed for {username} ({user_id}) in {total_time:.1f}s")

        except subprocess.TimeoutExpired:
            error_msg = "❌ Spotify download timed out (5 minutes). The track might be too long or there's a network issue."
            debug_write(f"Spotify download timeout for user {username} ({user_id})")
            user_logger.error(f"DOWNLOAD TIMEOUT | User: {username} ({user_id}) | Platform: Spotify | URL: {url}")

            try:
                await query.edit_message_text(error_msg)
            except:
                await query.message.reply_text(error_msg)

        except Exception as e:
            error_msg = f"❌ Spotify download failed: {str(e)}"
            debug_write(f"Error downloading Spotify audio: {e}")
            user_logger.error(f"DOWNLOAD FAILED | User: {username} ({user_id}) | Platform: Spotify | URL: {url} | Error: {str(e)}")

            try:
                await query.edit_message_text(error_msg)
            except:
                await query.message.reply_text(error_msg)

        finally:
            # Clean up output directory if it still exists
            try:
                if 'output_dir' in locals() and output_dir.exists():
                    import shutil
                    shutil.rmtree(output_dir)
            except:
                pass

    async def extract_spotify_metadata(self, url: str):
        """Extract metadata from Spotify URL using web scraping approach."""
        try:
            # First try to get metadata from Spotify's public API endpoint
            track_id = self.extract_spotify_track_id(url)
            if not track_id:
                return self.parse_spotify_url_fallback(url)

            # Try to get metadata from Spotify's public endpoint
            metadata = await self.get_spotify_track_info(track_id)
            if metadata:
                return metadata

            # Fallback: try to parse from URL
            return self.parse_spotify_url_fallback(url)

        except Exception as e:
            debug_write(f"Error extracting Spotify metadata: {e}")
            # Fallback: try to parse from URL
            return self.parse_spotify_url_fallback(url)

    def extract_spotify_track_id(self, url: str):
        """Extract track ID from Spotify URL."""
        try:
            import re
            # Match track URLs
            track_match = re.search(r'/track/([a-zA-Z0-9]+)', url)
            if track_match:
                return track_match.group(1)
            return None
        except Exception as e:
            debug_write(f"Error extracting Spotify track ID: {e}")
            return None

    async def get_spotify_track_metadata(self, track_id: str):
        """Get track metadata using web scraping approach."""
        try:
            import requests
            import re

            # Try to get basic info from Spotify's public page
            track_url = f"https://open.spotify.com/track/{track_id}"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }

            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(track_url, headers=headers, timeout=10)
            )

            if response.status_code == 200:
                html = response.text

                # Try to extract title and artist from meta tags
                # Look for Open Graph tags
                title_match = re.search(r'<meta property="og:title" content="([^"]+)"', html)
                description_match = re.search(r'<meta property="og:description" content="([^"]+)"', html)

                if title_match:
                    title = title_match.group(1)
                    artist = "Unknown Artist"

                    # Try to extract artist from description
                    if description_match:
                        description = description_match.group(1)
                        # Description often contains "Song · Artist · Year"
                        if ' · ' in description:
                            parts = description.split(' · ')
                            if len(parts) >= 2:
                                artist = parts[1]

                    return {
                        'title': title.strip(),
                        'artist': artist.strip(),
                        'duration': 0,
                        'album': '',
                        'url': track_url,
                        'track_id': track_id
                    }

                # Fallback: try to extract from page title
                title_match = re.search(r'<title[^>]*>([^<]+)</title>', html)
                if title_match:
                    title_text = title_match.group(1)
                    # Remove " | Spotify" from the end
                    title_text = title_text.replace(' | Spotify', '')

                    # Try to split by common separators
                    if ' - ' in title_text:
                        parts = title_text.split(' - ', 1)
                        return {
                            'title': parts[0].strip(),
                            'artist': parts[1].strip() if len(parts) > 1 else 'Unknown Artist',
                            'duration': 0,
                            'album': '',
                            'url': track_url,
                            'track_id': track_id
                        }

            return None

        except Exception as e:
            debug_write(f"Error getting Spotify track metadata: {e}")
            return None

    def parse_spotify_url_fallback(self, url: str):
        """Fallback method to parse Spotify URL when API fails."""
        try:
            # Extract track ID from URL
            track_id = self.extract_spotify_track_id(url)
            if track_id:
                # Return basic info that will allow the search to proceed
                return {
                    'title': 'Spotify Track',
                    'artist': 'Unknown Artist',
                    'duration': 0,
                    'album': '',
                    'url': url,
                    'track_id': track_id
                }
        except Exception as e:
            debug_write(f"Error in Spotify URL fallback parsing: {e}")

        return None

    async def search_youtube_for_spotify_track(self, search_query: str):
        """Search YouTube for a Spotify track."""
        try:
            import yt_dlp

            # Search YouTube for the track
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'default_search': 'ytsearch1:',  # Search for 1 result
            }

            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # Add timeout for YouTube search
                    search_results = await asyncio.wait_for(
                        asyncio.get_event_loop().run_in_executor(
                            None, lambda: ydl.extract_info(search_query, download=False)
                        ),
                        timeout=30  # 30 second timeout for search
                    )
            except asyncio.TimeoutError:
                debug_write("YouTube search timed out")
                return None

            # Get the first result
            if search_results and 'entries' in search_results and search_results['entries']:
                first_result = search_results['entries'][0]
                return first_result.get('webpage_url', first_result.get('url'))

            return None

        except Exception as e:
            debug_write(f"Error searching YouTube for Spotify track: {e}")
            return None

    async def handle_denied_user(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle non-whitelisted users."""
        message = await update.message.reply_html(
            Text.DENIED_MESSAGE,
            disable_web_page_preview=True
        )
        
        # Try to translate the message if user has a non-English language code
        if update.effective_user.language_code and update.effective_user.language_code != "en":
            translated = await self.translation.translate_text(
                Text.DENIED_MESSAGE,
                update.effective_user.language_code
            )
            
            if translated != Text.DENIED_MESSAGE:
                await update.get_bot().edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=message.message_id,
                    text=translated,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )
        
        # Forward message to admin
        forwarded = await update.message.forward(
            chat_id=env.ADMIN_ID,
            disable_notification=True
        )
        
        # Add middle finger reaction
        await update.get_bot().set_message_reaction(
            chat_id=forwarded.chat_id,
            message_id=forwarded.message_id,
            reaction=[{"type": "emoji", "emoji": "🖕"}]
        )

    def setup_handlers(self):
        """Set up message handlers."""
        debug_write("Setting up handlers")
        
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.handle_start))
        self.application.add_handler(CommandHandler("help", self.handle_help))
        
        # Main message handler with URL detection
        self.application.add_handler(
            MessageHandler(
                filters.TEXT & filters.Entity("url"), 
                self.handle_url_message
            )
        )
        
        # Fallback handler for text messages without URLs
        self.application.add_handler(
            MessageHandler(
                filters.TEXT, 
                self.handle_text_message
            )
        )
        
        # Callback query handler for inline buttons
        self.application.add_handler(
            CallbackQueryHandler(self.handle_callback_query)
        )
        
        debug_write("Handlers set up successfully")





async def download_ffmpeg():
    """Setup FFmpeg using local binaries or system installation."""
    try:
        # First, check if ffmpeg is already installed on the system
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info("FFmpeg is already installed on the system")
                return None  # No need to add to PATH
        except:
            logger.info("FFmpeg not found in system PATH, checking local directory")

        # Check for FFmpeg in the local repository directory
        ffmpeg_dir = Path.cwd() / "ffmpeg"

        # Determine platform and appropriate executable name
        import platform
        system = platform.system().lower()

        if system == "windows":
            ffmpeg_names = ["ffmpeg.exe"]
        else:
            ffmpeg_names = ["ffmpeg"]

        # Check if FFmpeg exists in the local directory
        for name in ffmpeg_names:
            ffmpeg_path = ffmpeg_dir / name
            if ffmpeg_path.exists():
                logger.info(f"Found local FFmpeg at: {ffmpeg_path}")
                # Make sure it's executable (Linux/Mac only)
                if system != "windows":
                    try:
                        os.chmod(ffmpeg_path, 0o755)
                    except Exception as chmod_error:
                        logger.warning(f"Could not make FFmpeg executable: {chmod_error}")

                # Test if it works
                try:
                    test_result = subprocess.run([str(ffmpeg_path), "-version"],
                                               capture_output=True, text=True, timeout=10)
                    if test_result.returncode == 0:
                        logger.info("Local FFmpeg is working correctly")
                        return str(ffmpeg_dir)
                    else:
                        logger.warning(f"Local FFmpeg test failed: {test_result.stderr}")
                except Exception as test_error:
                    logger.warning(f"Could not test local FFmpeg: {test_error}")

        # If we're on Linux and only have Windows executables, try to download Linux version
        if system == "linux" and (ffmpeg_dir / "ffmpeg.exe").exists():
            logger.info("Found Windows FFmpeg but running on Linux, downloading Linux version")
            try:
                # Try multiple sources for Linux FFmpeg
                ffmpeg_urls = [
                    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz",
                    "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
                    "https://github.com/eugeneware/ffmpeg-static/releases/download/b4.4/ffmpeg-linux-x64"
                ]

                success = False
                for ffmpeg_url in ffmpeg_urls:
                    try:
                        logger.info(f"Trying to download from: {ffmpeg_url}")
                        response = requests.get(ffmpeg_url, stream=True, timeout=60)
                        response.raise_for_status()

                        # Save the Linux version
                        linux_ffmpeg_path = ffmpeg_dir / "ffmpeg"

                        if ffmpeg_url.endswith('.tar.xz'):
                            # Handle compressed archives
                            import tempfile
                            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                                for chunk in response.iter_content(chunk_size=8192):
                                    tmp_file.write(chunk)
                                tmp_file.flush()

                                # Extract the archive (simplified - just try to find ffmpeg binary)
                                logger.info("Downloaded archive, extracting...")
                                # For now, skip complex extraction and try direct download
                                continue
                        else:
                            # Direct binary download
                            with open(linux_ffmpeg_path, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=8192):
                                    f.write(chunk)

                        # Make it executable
                        os.chmod(linux_ffmpeg_path, 0o755)

                        # Test the downloaded version
                        test_result = subprocess.run([str(linux_ffmpeg_path), "-version"],
                                                   capture_output=True, text=True, timeout=10)
                        if test_result.returncode == 0:
                            logger.info("Downloaded Linux FFmpeg is working correctly")
                            success = True
                            break
                        else:
                            logger.warning("Downloaded FFmpeg is not working, trying next source")
                            linux_ffmpeg_path.unlink(missing_ok=True)

                    except Exception as url_error:
                        logger.warning(f"Failed to download from {ffmpeg_url}: {url_error}")
                        continue

                if success:
                    return str(ffmpeg_dir)
                else:
                    logger.error("All FFmpeg download attempts failed")

            except Exception as download_error:
                logger.error(f"Failed to download Linux FFmpeg: {download_error}")

        # If no working FFmpeg found, create directory and log the issue
        ffmpeg_dir.mkdir(exist_ok=True)
        logger.warning("No working FFmpeg found")
        logger.info("Bot will work with limited functionality - some audio conversions may not be available")
        logger.info("yt-dlp will try to download audio in native formats when possible")

        # Return None to indicate FFmpeg is not available
        return None

    except Exception as e:
        logger.error(f"Error setting up FFmpeg: {e}")
        return None

# Add this function at the module level
def clear_webhook_settings():
    """Clear all webhook-related environment variables to prevent URL issues."""
    debug_write("Clearing all webhook-related environment variables")

    # Debug print all environment variables
    debug_print_env_vars()

    # Fix bot token if it's in the wrong place
    fix_bot_token()

    # List of webhook-related variables to clear
    webhook_vars = [
        "TELEGRAM_WEBHOOK_PORT",
        "TELEGRAM_WEBHOOK_URL",
        "TELEGRAM_API_ROOT"
    ]

    # Clear all webhook-related variables
    for var in webhook_vars:
        if var in os.environ:
            old_value = os.environ[var]
            os.environ[var] = ""
            debug_write(f"Cleared {var}: {old_value[:10] if old_value else 'empty'}...")

    # Update env object if it exists
    if 'env' in globals():
        if hasattr(env, 'WEBHOOK_PORT'):
            env.WEBHOOK_PORT = None
        if hasattr(env, 'WEBHOOK_URL'):
            env.WEBHOOK_URL = ""
        if hasattr(env, 'API_ROOT'):
            env.API_ROOT = ""

    # Debug print all environment variables after clearing
    debug_write("Environment variables after clearing:")
    debug_print_env_vars()

    debug_write("Webhook settings cleared")

# Check for Streamlit Cloud flag file
def should_start_bot():
    flag_file = Path.cwd() / "bot_running.flag"
    debug_write(f"Checking for flag file at {flag_file}")
    exists = flag_file.exists()
    debug_write(f"Flag file exists: {exists}")
    return exists

def debug_print_env_vars():
    """Print all environment variables for debugging."""
    debug_write("Current environment variables:")
    for key, value in os.environ.items():
        if key.startswith("TELEGRAM_"):
            # Mask sensitive values
            if key == "TELEGRAM_BOT_TOKEN" and value:
                masked = f"{value[:5]}...{value[-5:] if len(value) > 10 else ''}"
                debug_write(f"  {key}: {masked}")
            else:
                debug_write(f"  {key}: {value}")

def check_bot_token():
    """Check if the bot token is valid."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        debug_write("ERROR: TELEGRAM_BOT_TOKEN is not set")
        return False
    
    # Check if the token looks valid
    if ":" not in token or len(token) < 20:
        debug_write(f"ERROR: Invalid bot token format: {token[:5]}...")
        return False
    
    debug_write(f"Bot token looks valid: {token[:5]}...")
    return True

def create_direct_bot():
    """Create a bot directly without using environment variables."""
    debug_write("Creating bot directly")
    
    # Get the bot token
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        debug_write("ERROR: TELEGRAM_BOT_TOKEN is not set")
        return None
    
    # Create a bot instance directly
    from telegram import Bot
    from telegram.ext import Application, ApplicationBuilder
    
    try:
        debug_write(f"Creating bot with token: {token[:5]}...")
        
        # Create a completely new application builder
        builder = ApplicationBuilder()
        builder.token(token)
        
        # Set base URL explicitly
        builder.base_url("https://api.telegram.org/bot")
        
        # Build the application
        app = builder.build()
        debug_write("Application built successfully")
        
        return app
    except Exception as e:
        debug_write(f"ERROR: Failed to create bot: {e}")
        import traceback
        debug_write(f"Traceback: {traceback.format_exc()}")
        return None

def fix_bot_token():
    """Check if the bot token is in the wrong environment variable and fix it."""
    debug_write("Checking for bot token in wrong environment variables")
    
    # Check if the bot token is in the right place
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if token and ":" in token and len(token) > 20:
        debug_write(f"Bot token is in the right place: {token[:5]}...")
        return True
    
    # Check if the bot token is in the wrong place
    for key, value in os.environ.items():
        if key.startswith("TELEGRAM_") and key != "TELEGRAM_BOT_TOKEN":
            if value and ":" in value and len(value) > 20:
                debug_write(f"Found potential bot token in {key}: {value[:5]}...")
                # This might be a bot token in the wrong place
                os.environ["TELEGRAM_BOT_TOKEN"] = value
                os.environ[key] = ""
                debug_write(f"Moved token from {key} to TELEGRAM_BOT_TOKEN")
                return True
    
    debug_write("Bot token not found in any environment variable")
    return False

if __name__ == "__main__":
    debug_write("Bot script started directly")
    
    # Clear webhook settings immediately
    clear_webhook_settings()
    
    # Only start the bot if the flag file exists (for Streamlit Cloud)
    if should_start_bot():
        logger.info("Bot flag file found, starting bot")
        debug_write("Starting bot via run_bot method")
        try:
            # Make sure TELEGRAM_WEBHOOK_PORT and TELEGRAM_WEBHOOK_URL are empty
            os.environ["TELEGRAM_WEBHOOK_PORT"] = ""
            os.environ["TELEGRAM_WEBHOOK_URL"] = ""
            os.environ["TELEGRAM_API_ROOT"] = "https://api.telegram.org"
            
            # Start the bot
            TelegramYTDLBot.run_bot()
            debug_write("Bot run_bot method completed")
        except Exception as e:
            debug_write(f"ERROR: Exception in run_bot: {e}")
            import traceback
            debug_write(f"Traceback: {traceback.format_exc()}")
    else:
        logger.info("Bot flag file not found, not starting bot")
        debug_write("Bot flag file not found, not starting bot")
