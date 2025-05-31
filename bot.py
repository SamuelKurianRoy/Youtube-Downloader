# Main modules
import os
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
import yt_dlp
import openai
import requests
from telegram import Bot, Update, InputFile, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode, ChatAction
from dotenv import load_dotenv 

# Replace with new logging configuration
import logging.handlers
import subprocess
import signal
print("Running Bot code")
def setup_logging():
    """Configure logging with file output and filters."""
    # Create logs directory if it doesn't exist
    base_dir = Path.cwd()
    log_dir = base_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # Create formatters
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Setup bot log handler with rotation (for errors and system messages)
    bot_handler = logging.handlers.RotatingFileHandler(
        log_dir / "bot.log",
        maxBytes=1024 * 1024,  # 1MB
        backupCount=5,
        encoding='utf-8'
    )
    bot_handler.setFormatter(file_formatter)
    bot_handler.setLevel(logging.INFO)
    
    # Setup user log handler with rotation (for user activity)
    user_handler = logging.handlers.RotatingFileHandler(
        log_dir / "user.log",
        maxBytes=1024 * 1024,  # 1MB
        backupCount=5,
        encoding='utf-8'
    )
    user_handler.setFormatter(file_formatter)
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
        self.YTDL_AUTOUPDATE = self.get_variable("YTDL_AUTOUPDATE", "true").lower() != "false"
        
        # Handle webhook settings
        webhook_port = self.get_variable("TELEGRAM_WEBHOOK_PORT", "")
        self.WEBHOOK_PORT = int(webhook_port) if webhook_port.strip() and webhook_port.strip().isdigit() else None
        self.WEBHOOK_URL = self.get_variable("TELEGRAM_WEBHOOK_URL", "")
        self.API_ROOT = self.get_variable("TELEGRAM_API_ROOT", "")
        
        # Bot token is required
        self.BOT_TOKEN = self.get_variable("TELEGRAM_BOT_TOKEN", "")
        
        # Admin and whitelist settings
        admin_id = self.get_variable("ADMIN_ID", "")
        self.ADMIN_ID = int(admin_id) if admin_id.strip() and admin_id.strip().isdigit() else None
        
        # Handle whitelist IDs
        whitelist_str = self.get_variable("WHITELISTED_IDS", "")
        self.WHITELISTED_IDS = []
        if whitelist_str.strip():
            for id_str in whitelist_str.split(","):
                if id_str.strip() and id_str.strip().isdigit():
                    self.WHITELISTED_IDS.append(int(id_str.strip()))
        
        self.ALLOW_GROUPS = self.get_variable("ALLOW_GROUPS", "false").lower() != "false"
        
        # API keys
        self.OPENAI_API_KEY = self.get_variable("OPENAI_API_KEY", "")
        self.COBALT_INSTANCE_URL = self.get_variable("COBALT_INSTANCE_URL", "")
        
        # Paths - adjusted for Streamlit Cloud
        self.BASE_DIR = Path.cwd()
        
        # For Streamlit Cloud, use a persistent directory if available
        # Check if we're running in Streamlit Cloud by looking for STREAMLIT_SHARING_MODE env var
        self.is_streamlit_cloud = os.environ.get("STREAMLIT_SHARING_MODE") is not None
        
        if self.is_streamlit_cloud:
            logger.info("Running in Streamlit Cloud environment")
            # In Streamlit Cloud, we need to use directories that persist
            # The current working directory should be writable
            self.STORAGE_DIR = self.BASE_DIR / "storage"
        else:
            # Local environment
            self.STORAGE_DIR = self.BASE_DIR / "storage"
            
        logger.info(f"Storage directory set to: {self.STORAGE_DIR}")
        
        self.COOKIE_FILE = self.STORAGE_DIR / "cookies.txt"
        self.TRANSLATIONS_FILE = self.STORAGE_DIR / "saved-translations.json"
        self.USER_PREFS_FILE = self.STORAGE_DIR / "user-preferences.json"
        
        # Create storage directory if it doesn't exist
        try:
            self.STORAGE_DIR.mkdir(exist_ok=True)
            logger.info(f"Storage directory created/verified at {self.STORAGE_DIR}")
        except Exception as e:
            logger.error(f"Failed to create storage directory: {e}")
            # Fallback to a temporary directory
            import tempfile
            self.STORAGE_DIR = Path(tempfile.gettempdir()) / "telegram-ytdl"
            self.STORAGE_DIR.mkdir(exist_ok=True)
            logger.info(f"Using fallback storage directory: {self.STORAGE_DIR}")
            
            # Update paths with new storage dir
            self.COOKIE_FILE = self.STORAGE_DIR / "cookies.txt"
            self.TRANSLATIONS_FILE = self.STORAGE_DIR / "saved-translations.json"
            self.USER_PREFS_FILE = self.STORAGE_DIR / "user-preferences.json"
        
        # Create translations file if it doesn't exist
        if not self.TRANSLATIONS_FILE.exists():
            with open(self.TRANSLATIONS_FILE, 'w') as f:
                f.write("{}")
                
        # Create user preferences file if it doesn't exist
        if not self.USER_PREFS_FILE.exists():
            with open(self.USER_PREFS_FILE, 'w') as f:
                f.write("{}")
        
        # Log configuration
        logger.info(f"Bot configuration loaded:")
        logger.info(f"- Auto-update: {self.YTDL_AUTOUPDATE}")
        logger.info(f"- Webhook URL: {'Set' if self.WEBHOOK_URL else 'Not set'}")
        logger.info(f"- API Root: {'Set' if self.API_ROOT else 'Not set'}")
        logger.info(f"- Bot Token: {'Set' if self.BOT_TOKEN else 'Not set'}")
        logger.info(f"- Admin ID: {self.ADMIN_ID}")
        logger.info(f"- Whitelisted IDs: {len(self.WHITELISTED_IDS)} IDs set")
        logger.info(f"- Allow Groups: {self.ALLOW_GROUPS}")
        logger.info(f"- OpenAI API Key: {'Set' if self.OPENAI_API_KEY else 'Not set'}")
        logger.info(f"- Cobalt Instance URL: {'Set' if self.COBALT_INSTANCE_URL else 'Not set'}")

    def get_variable(self, key: str, default: str = None) -> str:
        """Get environment variable with fallback to Streamlit secrets."""
        # First try regular environment variables
        value = os.environ.get(key)
        
        # Then try Streamlit secrets
        if value is None:
            try:
                import streamlit as st
                # This is the correct way to access Streamlit secrets
                # Access as dictionary items, not as a method call
                value = st.secrets[key]
            except (ImportError, KeyError):
                value = None
        
        # Use default if still None
        if value is None and default is not None:
            logger.info(f"Environment variable {key} not found, using default value")
            return default
        
        # Return empty string if all else fails
        if value is None:
            logger.warning(f"Environment variable {key} is not set, using empty string")
            return ""
        
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
    URL_REMINDER = "You need to send an URL to download stuff."
    MAINTENANCE_NOTICE = "<b>Bot is currently under maintenance, it'll return shortly.</b>"
    PROCESSING = "<b>Processing...</b>"
    DENIED_MESSAGE = (
        "<b>This bot is private.</b>\n\n"
        "It costs money to run this and unfortunately it doesn't grow on trees.\n"
        f"This bot is open source, so you can always <a href=\"https://github.com/vaaski/telegram-ytdl#hosting\">host it yourself</a>.\n\n"
        f"<b>As an alternative I recommend checking out <a href=\"https://github.com/yt-dlp/yt-dlp\">yt-dlp</a>, "
        f"the command line tool that powers this bot or <a href=\"https://cobalt.tools\">cobalt</a>, "
        f"a web-based social media content downloader (not affiliated with this bot).</b>\n\n"
    )

# Callback data prefixes
class CallbackPrefix:
    FORMAT = "format:"  # format:video, format:audio
    VIDEO_QUALITY = "vq:"  # vq:high, vq:medium, vq:low
    AUDIO_QUALITY = "aq:"  # aq:high, aq:medium, aq:low
    CANCEL = "cancel"

# Format quality options
class VideoQuality:
    HIGH = "high"     # Best available
    MEDIUM = "medium" # 720p
    LOW = "low"       # 480p

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

# Handle URL download context
class DownloadContext:
    def __init__(self):
        self.url = None
        self.info = None
        self.processing_message = None
        self.chat_id = None
        self.user_id = None
        self.message_id = None
        self.title = None
        self.is_tiktok = False
        self.is_youtube_music = False
        self.has_video = False
        self.has_audio = False
        self.formats = {}  # Will store available formats
        
    def clear(self):
        """Clear all context data."""
        self.__init__()
        
    def update_from_info(self, info):
        """Update context with extracted info."""
        try:
            self.info = info
            self.title = remove_hashtags_mentions(info.get('title', 'Untitled'))
            self.has_video = info.get('vcodec') != 'none'
            self.has_audio = info.get('acodec') != 'none'
            
            # Extract available formats
            if 'formats' in info:
                self.process_formats(info['formats'])
            else:
                raise ValueError("No format information available")
                
        except Exception as e:
            logger.error(f"Error updating from info: {e}")
            raise ValueError(f"Failed to process video information: {str(e)}")
    
    def process_formats(self, formats):
        """Process and categorize available formats."""
        video_formats = []
        audio_formats = []
        
        for fmt in formats:
            try:
                if fmt.get('vcodec', 'none') != 'none' and fmt.get('acodec', 'none') != 'none':
                    # This is a format with both video and audio
                    height = fmt.get('height', 0)
                    file_size = fmt.get('filesize') or fmt.get('filesize_approx', 0)
                    tbr = fmt.get('tbr', 0)  # Total bitrate
                    format_id = fmt.get('format_id', '')
                    format_note = fmt.get('format_note', '')
                    ext = fmt.get('ext', 'mp4')
                    
                    # Only add if we have valid height and reasonable bitrate
                    if height and tbr > 0:
                        video_formats.append({
                            'format_id': format_id,
                            'ext': ext,
                            'height': int(height),  # Ensure height is an integer
                            'file_size': int(file_size) if file_size else 0,
                            'tbr': float(tbr) if tbr else 0,
                            'format_note': format_note
                        })
                    
                elif fmt.get('acodec', 'none') != 'none' and fmt.get('vcodec', 'none') == 'none':
                    # This is an audio-only format
                    file_size = fmt.get('filesize') or fmt.get('filesize_approx', 0)
                    abr = fmt.get('abr', 0)  # Audio bitrate
                    format_id = fmt.get('format_id', '')
                    
                    if abr:  # Only add if we have valid audio bitrate
                        audio_formats.append({
                            'format_id': format_id,
                            'ext': fmt.get('ext', 'mp3'),
                            'abr': float(abr) if abr else 0,
                            'file_size': int(file_size) if file_size else 0
                        })
            except Exception as e:
                logger.error(f"Error processing format: {e}")
                continue
        
        if not video_formats and not audio_formats:
            logger.error("No valid formats found")
            raise ValueError("No valid formats found for this video")
        
        # Sort video formats by resolution and bitrate
        video_formats.sort(key=lambda x: (x['height'], x['tbr']), reverse=True)
        
        # Sort audio formats by bitrate
        audio_formats.sort(key=lambda x: x['abr'], reverse=True)
        
        # Initialize format dictionaries
        self.formats = {
            'video': {'high': None, 'medium': None, 'low': None},
            'audio': {'high': None, 'medium': None, 'low': None}
        }
        
        # Categorize video formats based on resolution
        if video_formats:
            try:
                # High quality: 1080p or best available
                self.formats['video']['high'] = next(
                    (f for f in video_formats if f['height'] >= 1080),
                    next(
                        (f for f in video_formats if f['height'] >= 720),
                        video_formats[0] if video_formats else None
                    )
                )
                
                # Medium quality: 720p or closest below
                self.formats['video']['medium'] = next(
                    (f for f in video_formats if f['height'] <= 720),
                    next(
                        (f for f in video_formats if f['height'] <= 1080),
                        video_formats[-1] if video_formats else None
                    )
                )
                
                # Low quality: 480p or closest below
                self.formats['video']['low'] = next(
                    (f for f in video_formats if f['height'] <= 480),
                    next(
                        (f for f in video_formats if f['height'] <= 720),
                        video_formats[-1] if video_formats else None
                    )
                )
            except Exception as e:
                logger.error(f"Error categorizing video formats: {e}")
                # Fallback to simple categorization
                if len(video_formats) >= 3:
                    self.formats['video']['high'] = video_formats[0]
                    self.formats['video']['medium'] = video_formats[len(video_formats)//2]
                    self.formats['video']['low'] = video_formats[-1]
                elif len(video_formats) == 2:
                    self.formats['video']['high'] = video_formats[0]
                    self.formats['video']['medium'] = self.formats['video']['low'] = video_formats[1]
                elif len(video_formats) == 1:
                    self.formats['video']['high'] = self.formats['video']['medium'] = self.formats['video']['low'] = video_formats[0]
        
        # Categorize audio formats based on bitrate
        if audio_formats:
            try:
                # High quality: 256kbps or best available
                self.formats['audio']['high'] = next(
                    (f for f in audio_formats if f['abr'] >= 256),
                    audio_formats[0] if audio_formats else None
                )
                
                # Medium quality: 192kbps or closest available
                self.formats['audio']['medium'] = next(
                    (f for f in audio_formats if 128 <= f['abr'] < 256),
                    self.formats['audio']['high']
                )
                
                # Low quality: 128kbps or lowest available
                self.formats['audio']['low'] = next(
                    (f for f in audio_formats if f['abr'] <= 128),
                    self.formats['audio']['medium']
                )
            except Exception as e:
                logger.error(f"Error categorizing audio formats: {e}")
                # Fallback to simple categorization
                if len(audio_formats) >= 3:
                    self.formats['audio']['high'] = audio_formats[0]
                    self.formats['audio']['medium'] = audio_formats[len(audio_formats)//2]
                    self.formats['audio']['low'] = audio_formats[-1]
                elif len(audio_formats) == 2:
                    self.formats['audio']['high'] = audio_formats[0]
                    self.formats['audio']['medium'] = self.formats['audio']['low'] = audio_formats[1]
                elif len(audio_formats) == 1:
                    self.formats['audio']['high'] = self.formats['audio']['medium'] = self.formats['audio']['low'] = audio_formats[0]
        
        # Log available formats
        logger.info("Available video formats:")
        for quality, fmt in self.formats['video'].items():
            if fmt:
                logger.info(f"{quality}: {fmt['height']}p ({format_file_size(fmt['file_size'])})")
        
        logger.info("Available audio formats:")
        for quality, fmt in self.formats['audio'].items():
            if fmt:
                logger.info(f"{quality}: {fmt['abr']}kbps ({format_file_size(fmt['file_size'])})")

# Telegram Bot
class TelegramYTDLBot:
    def __init__(self):
        # Initialize application
        self.application = None
        self.bot = None
        
        # Initialize other components
        self.queue = None  # Will be initialized later
        self.updater = None  # Will be initialized later
        self.translation = None  # Will be initialized later
        self.cobalt = None  # Will be initialized later
        self.user_prefs = None  # Will be initialized later
        
        # Download contexts for active downloads - keyed by user_id
        self.download_contexts = {}
        
        # TikTok special arguments
        self.tiktok_args = [
            "--extractor-args",
            "tiktok:api_hostname=api16-normal-c-useast1a.tiktokv.com;app_info=7355728856979392262"
        ]
        
        # FFmpeg path
        self.ffmpeg_path = None
        
        # Flag to check if bot should be running
        self.should_run = True

    async def initialize(self):
        """Initialize the bot and its components."""
        try:
            # Initialize application
            application_builder = Application.builder().token(env.BOT_TOKEN)
            
            # Set custom API endpoint if provided
            if env.API_ROOT:
                application_builder.base_url(env.API_ROOT)
                
            self.application = application_builder.build()
            
            # Initialize the application
            await self.application.initialize()
            
            # Get bot instance
            self.bot = self.application.bot
            
            # Initialize other components
            from queue_manager import Queue
            from updater import Updater
            from translation import TranslationService
            from cobalt_api import CobaltAPI
            from user_preferences import UserPreferences
            
            self.queue = Queue()
            self.updater = Updater(env.YTDL_AUTOUPDATE)
            self.translation = TranslationService(env.OPENAI_API_KEY, env.TRANSLATIONS_FILE)
            self.cobalt = CobaltAPI(env.COBALT_INSTANCE_URL)
            self.user_prefs = UserPreferences(env.USER_PREFS_FILE)
            
            # Set up handlers
            self.setup_handlers()
            
            # Setup FFmpeg
            await self.setup_ffmpeg()
            
            logger.info("Bot initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing bot: {e}")
            return False

    async def setup_ffmpeg(self):
        """Setup FFmpeg and add it to PATH."""
        try:
            self.ffmpeg_path = await download_ffmpeg()
            if self.ffmpeg_path:
                os.environ["PATH"] = self.ffmpeg_path + os.pathsep + os.environ["PATH"]
                logger.info(f"FFmpeg set up at: {self.ffmpeg_path}")
            return self.ffmpeg_path
        except Exception as e:
            logger.error(f"Error setting up FFmpeg: {e}")
            return None

    async def start(self):
        """Start the bot with proper initialization."""
        try:
            # Initialize bot components
            success = await self.initialize()
            if not success:
                logger.error("Failed to initialize bot. Exiting.")
                return
            
            # Check for Streamlit Cloud flag file
            flag_file = Path.cwd() / "bot_running.flag"
            
            # Start polling
            logger.info("Starting bot in polling mode")
            await self.application.start()
            await self.application.updater.start_polling()
            
            # Block until we receive a stop signal or flag file is removed
            while self.should_run:
                # In Streamlit Cloud, check if the flag file exists
                if not flag_file.exists():
                    logger.info("Stop flag detected. Stopping bot.")
                    self.should_run = False
                    break
                
                await asyncio.sleep(5)  # Check every 5 seconds
            
        except Exception as e:
            logger.error(f"Error running bot: {e}")
            raise
        finally:
            # Ensure proper cleanup
            if self.application:
                logger.info("Shutting down bot...")
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                logger.info("Bot shutdown complete")

    @classmethod
    async def create_and_run(cls):
        """Create and run the bot."""
        bot = cls()
        await bot.start()

    @classmethod
    def run_bot(cls):
        """Run the bot with proper async handling."""
        try:
            # Create new event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # Run the bot
            loop.run_until_complete(cls.create_and_run())
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Error: {e}")
        finally:
            # Clean up
            try:
                loop.close()
            except:
                pass

    async def is_whitelisted(self, update: Update) -> bool:
        """Check if user is whitelisted."""
        # If no whitelist is configured, allow all users
        if len(env.WHITELISTED_IDS) == 0:
            return True
            
        # Check if user is in whitelist
        return update.effective_user.id in env.WHITELISTED_IDS

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /start command."""
        if not await self.is_whitelisted(update):
            # Get user info
            user = update.effective_user
            # Notify admin but do NOT block user
            await context.bot.send_message(
                chat_id=env.ADMIN_ID,
                text=(
                    f"⚠️ <b>Unauthorized user accessed /start</b>\n\n"
                    f"<b>Name:</b> {user.full_name}\n"
                    f"<b>Username:</b> @{user.username}\n"
                    f"<b>User ID:</b> <code>{user.id}</code>"
                ),
                parse_mode="HTML"
            )
            await self.handle_denied_user(update, context)
            return
        
        welcome_message = (
            f"<b>Welcome to YouTube Downloader Bot!</b>\n\n"
            f"Send me a URL from YouTube, TikTok, or other supported platforms to download content.\n\n"
            f"I'll give you options to download it as video or audio, in different quality levels."
        )
        
        await update.message.reply_html(welcome_message)
    
    async def handle_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /help command."""
        # Check if the user is whitelisted
        if not await self.is_whitelisted(update):
            await self.handle_denied_user(update, context)
            return
            
        help_message = (
            f"<b>How to use this bot:</b>\n\n"
            f"1. Send a link to a video from YouTube, TikTok, or other supported sites\n"
            f"2. Choose whether you want to download it as video or audio\n"
            f"3. Select the quality you prefer\n"
            f"4. Wait for the download to complete\n\n"
            f"<b>Supported Sites:</b>\n"
            f"• YouTube\n"
            f"• TikTok\n"
            f"• Instagram\n"
            f"• Twitter/X\n"
            f"• Facebook\n"
            f"• And many more!\n\n"
            f"<b>File Size Limits:</b>\n"
            f"• Videos: up to 50MB\n"
            f"• Audio: up to 50MB\n\n"
            f"Your preferences will be remembered for future downloads."
        )
        
        await update.message.reply_html(help_message)

    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages without URLs."""
        # Check if the user is whitelisted
        if not await self.is_whitelisted(update):
            await self.handle_denied_user(update, context)
            return
        
        # Reply with URL reminder
        message = await update.message.reply_html(Text.URL_REMINDER)
        
        # Try to translate the message if user has a non-English language code
        if update.effective_user.language_code and update.effective_user.language_code != "en":
            translated = await self.translation.translate_text(
                Text.URL_REMINDER,
                update.effective_user.language_code
            )
            
            if translated != Text.URL_REMINDER:
                await update.get_bot().edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=message.message_id,
                    text=translated,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True
                )

    async def handle_url_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle messages containing URLs."""
        # Check if the user is whitelisted
        if not await self.is_whitelisted(update):
            await self.handle_denied_user(update, context)
            return
        
        # Extract URL from the message
        entities = update.message.entities
        url = None
        
        for entity in entities:
            if entity.type == "url":
                offset = entity.offset
                length = entity.length
                url = update.message.text[offset:offset + length]
                break
                
        if not url:
            await update.message.reply_html(Text.URL_REMINDER)
            return
        
        # Send "processing" message
        processing_message = await update.message.reply_html(
            Text.PROCESSING,
            reply_to_message_id=update.message.message_id
        )
        
        # Create download context for this user
        user_id = update.effective_user.id
        self.download_contexts[user_id] = DownloadContext()
        context = self.download_contexts[user_id]
        context.url = url
        context.processing_message = processing_message
        context.chat_id = update.effective_chat.id
        context.user_id = user_id
        context.message_id = processing_message.message_id
        context.is_tiktok = "tiktok.com" in url
        context.is_youtube_music = "music.youtube.com" in url
        
        # Add the task to queue
        self.queue.add(lambda: self.process_url(url, context))

    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle callback queries from inline buttons."""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        user_id = update.effective_user.id
        
        # Log the user's selection
        user_logger.info(
            f"BUTTON SELECTION | User: {user_id} | "
            f"Selection: {data}"
        )
        
        # Check if we have a download context for this user
        if user_id not in self.download_contexts:
            await query.edit_message_text(
                text="Your session has expired. Please send the URL again."
            )
            return
            
        download_context = self.download_contexts[user_id]
        
        # Process different callback types
        if data.startswith(CallbackPrefix.FORMAT):
            format_type = data[len(CallbackPrefix.FORMAT):]
            
            if format_type == "back":
                # Go back to format selection
                await self.show_format_options(download_context)
            elif format_type in ["video", "audio"]:
                # Save format preference for user
                await self.user_prefs.set_user_preference(user_id, "preferred_format", format_type)
                
                # Log user preference
                user_logger.info(
                    f"FORMAT PREFERENCE | User: {user_id} | "
                    f"Preferred Format: {format_type}"
                )
                
                # Show quality options for selected format
                await self.show_quality_options(download_context, format_type)
                
        elif data.startswith(CallbackPrefix.VIDEO_QUALITY):
            quality = data[len(CallbackPrefix.VIDEO_QUALITY):]
            
            # Save quality preference for user
            await self.user_prefs.set_user_preference(user_id, "preferred_video_quality", quality)
            
            # Download video with selected quality
            await query.answer("Starting download...")
            await self.download_media(download_context, "video", quality)
            
        elif data.startswith(CallbackPrefix.AUDIO_QUALITY):
            quality = data[len(CallbackPrefix.AUDIO_QUALITY):]
            
            # Save quality preference for user
            await self.user_prefs.set_user_preference(user_id, "preferred_audio_quality", quality)
            
            # Download audio with selected quality
            await query.answer("Starting download...")
            await self.download_media(download_context, "audio", quality)
            
        elif data == CallbackPrefix.CANCEL:
            # Cancel download
            await query.answer("Download canceled")
            
            await self.bot.edit_message_text(
                chat_id=download_context.chat_id,
                message_id=download_context.message_id,
                text="<b>Download canceled</b>",
                parse_mode=ParseMode.HTML
            )
            
            # Clear the download context
            del self.download_contexts[user_id]
        else:
            await query.answer("Unknown option")

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

    async def download_media(self, context: DownloadContext, format_type: str, quality: str):
        """Download media in the specified format and quality."""
        start_time = time.time()
        
        try:
            # Log download start
            user_logger.info(
                f"DOWNLOAD START | User: {context.user_id} | "
                f"URL: {context.url} | "
                f"Format: {format_type} | "
                f"Quality: {quality} | "
                f"Title: {context.title}"
            )
            
            # Update message to show downloading status
            await self.bot.edit_message_text(
                chat_id=context.chat_id,
                message_id=context.message_id,
                text=f"<b>{context.title}</b>\n\n{Text.DOWNLOADING}",
                parse_mode=ParseMode.HTML
            )
            
            # Create temp directory if it doesn't exist
            temp_dir = env.STORAGE_DIR / "temp"
            temp_dir.mkdir(exist_ok=True)
            
            # Generate unique filenames
            temp_filename = f"{int(time.time())}_{context.user_id}"
            temp_filepath = temp_dir / temp_filename
            
            # Prepare download options
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'noprogress': True,
                'outtmpl': f"{str(temp_filepath)}.%(ext)s",
            }
            
            # Add FFmpeg location if available
            if self.ffmpeg_path:
                ydl_opts['ffmpeg_location'] = self.ffmpeg_path
            
            # Get format ID for selected quality
            format_id = None
            if format_type in context.formats and quality in context.formats[format_type]:
                format_data = context.formats[format_type][quality]
                if format_data:
                    format_id = format_data.get('format_id')
                    
            if not format_id and format_type == "video":
                # Fallback to default format
                format_id = "18"  # 360p MP4
                
            # Configure format-specific options
            if format_type == "video":
                ydl_opts.update({
                    'format': f"{format_id}+bestaudio/best",  # Try to get best audio with video
                    'merge_output_format': 'mp4',  # Force MP4 output
                })
                
            else:  # audio
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                })
            
            # Add cookie file if available
            if env.COOKIE_FILE.exists():
                ydl_opts['cookiefile'] = str(env.COOKIE_FILE)
                
            download_start = time.time()
            logger.info(f"Starting download with options: {ydl_opts}")
            
            # Download the file
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                await asyncio.get_event_loop().run_in_executor(
                    None, lambda: ydl.download([context.url])
                )
            download_time = time.time() - download_start
            
            # Find the downloaded file
            downloaded_files = list(temp_dir.glob(f"{temp_filename}.*"))
            if not downloaded_files:
                raise FileNotFoundError("Download failed - no file found")
            
            downloaded_file = downloaded_files[0]
            file_extension = downloaded_file.suffix.lower()
            
            # Log file details
            logger.info(f"File exists: {downloaded_file.exists()}")
            logger.info(f"File size: {downloaded_file.stat().st_size} bytes")
            logger.info(f"File path: {downloaded_file}")
            logger.info(f"File extension: {file_extension}")
            
            # Log successful download to user log
            file_size_mb = downloaded_file.stat().st_size / (1024 * 1024)
            user_logger.info(
                f"DOWNLOAD COMPLETE | User: {context.user_id} | "
                f"URL: {context.url} | "
                f"Format: {format_type} | "
                f"Quality: {quality} | "
                f"Size: {file_size_mb:.2f}MB | "
                f"Duration: {download_time:.2f}s | "
                f"Title: {context.title}"
            )
            
            # Verify file size and content
            if downloaded_file.stat().st_size < 1024:  # Less than 1KB
                raise ValueError(f"Downloaded file is too small: {downloaded_file.stat().st_size} bytes")
            
            upload_start = time.time()
            
            # Read file into memory for upload
            with open(downloaded_file, 'rb') as file:
                file_data = file.read()
                
            if format_type == "video":
                # Ensure we have a valid video file
                if file_extension not in ['.mp4', '.mkv', '.avi', '.mov']:
                    raise ValueError(f"Invalid video file format: {file_extension}")
                
                # Send as video
                await self.bot.send_video(
                    chat_id=context.chat_id,
                    video=InputFile(file_data, filename=f"{context.title}.mp4"),
                    caption=f"{context.title}\n\nProcessing time: {time.time() - start_time:.1f}s (Download: {download_time:.1f}s, Upload: {time.time() - upload_start:.1f}s)",
                    supports_streaming=True,
                    reply_to_message_id=context.message_id
                )
            else:  # audio
                # Try to send as audio first
                try:
                    await self.bot.send_audio(
                        chat_id=context.chat_id,
                        audio=InputFile(file_data, filename=f"{context.title}.mp3"),
                        title=context.title,
                        performer="YouTube",  # You might want to extract this from metadata
                        caption=f"Processing time: {time.time() - start_time:.1f}s (Download: {download_time:.1f}s, Upload: {time.time() - upload_start:.1f}s)",
                        reply_to_message_id=context.message_id
                    )
                except Exception as e:
                    logger.error(f"Error sending as audio, trying as document: {e}")
                    # Fallback to document if audio fails
                    await self.bot.send_document(
                        chat_id=context.chat_id,
                        document=InputFile(file_data, filename=f"{context.title}.mp3"),
                        caption=f"Processing time: {time.time() - start_time:.1f}s (Download: {download_time:.1f}s, Upload: {time.time() - upload_start:.1f}s)",
                        reply_to_message_id=context.message_id
                    )
                
            # Delete the processing message
            await self.bot.delete_message(
                chat_id=context.chat_id,
                message_id=context.message_id
            )
                
        except Exception as e:
            logger.error(f"Error downloading media: {e}")
            # Log the full error details
            import traceback
            logger.error(f"Full error: {traceback.format_exc()}")
            
            # Log failed download to user log
            user_logger.error(
                f"DOWNLOAD FAILED | User: {context.user_id} | "
                f"URL: {context.url} | "
                f"Format: {format_type} | "
                f"Quality: {quality} | "
                f"Error: {str(e)}"
            )
            
            await self.bot.edit_message_text(
                chat_id=context.chat_id,
                message_id=context.message_id,
                text=f"<b>{context.title}</b>\n\n{Text.DOWNLOAD_FAILED}\n\nError: {str(e)}",
                parse_mode=ParseMode.HTML
            )
        finally:
            # Clean up files
            try:
                if downloaded_file and downloaded_file.exists():
                    downloaded_file.unlink()
                
                # Clean up any remaining temp files
                temp_dir = env.STORAGE_DIR / "temp"
                for temp_file in temp_dir.glob(f"{temp_filename}.*"):
                    try:
                        temp_file.unlink()
                    except:
                        pass
                        
                # Clear the download context
                del self.download_contexts[context.user_id]
            except Exception as cleanup_error:
                logger.error(f"Error during cleanup: {cleanup_error}")

    async def process_url(self, url: str, context: DownloadContext):
        """Process a URL to extract video information."""
        try:
            logger.info(f"Starting to process URL: {url}")
            # Check if we should use Cobalt API for this URL
            if self.cobalt and self.cobalt.matches_url(url):
                logger.info("Using Cobalt API for processing")
                # Process with Cobalt
                info = await self.cobalt.resolve_url(url)
                if info.get("status") != "error":
                    # TODO: Process Cobalt response
                    pass
                
            # Extract info with yt-dlp
            args = ["--no-playlist", "--dump-json"]
            logger.info("Extracting video info with yt-dlp")
            
            # Add cookie file if available
            args.extend(env.get_cookie_args())
            
            # Add special args for TikTok
            if context.is_tiktok:
                args.extend(self.tiktok_args)
            
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                logger.info("Starting yt-dlp extraction")
                info = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: ydl.extract_info(url, download=False)
                )
                logger.info("Video info extraction completed")
                
            # Update context with extracted info
            context.update_from_info(info)
            logger.info("Context updated with video info")
            
            # Log video information to user log
            user_logger.info(
                f"VIDEO INFO | User: {context.user_id} | "
                f"Title: {context.title} | "
                f"URL: {url} | "
                f"Has Video: {context.has_video} | "
                f"Has Audio: {context.has_audio}"
            )
            
            # Show format selection buttons
            await self.show_format_options(context)
            logger.info("Format options displayed to user")
            
        except Exception as e:
            logger.error(f"Error processing URL: {e}")
            user_logger.error(
                f"PROCESSING ERROR | User: {context.user_id} | "
                f"URL: {url} | Error: {str(e)}"
            )
            
            if context.processing_message:
                await self.bot.edit_message_text(
                    chat_id=context.chat_id,
                    message_id=context.message_id,
                    text=f"<b>Error processing URL:</b>\n{str(e)}",
                    parse_mode=ParseMode.HTML
                )

    async def show_format_options(self, context: DownloadContext):
        """Show available format options to the user."""
        # Get user's preferred format
        preferred_format = self.user_prefs.get_user_preference(context.user_id, "preferred_format")
        
        # Create format selection buttons
        keyboard = []
        
        # Video button if video formats are available
        if context.has_video:
            keyboard.append([
                InlineKeyboardButton(
                    "🎥 Video" + (" (Preferred)" if preferred_format == "video" else ""),
                    callback_data=f"{CallbackPrefix.FORMAT}video"
                )
            ])
            
        # Audio button if audio formats are available
        if context.has_audio:
            keyboard.append([
                InlineKeyboardButton(
                    "🎵 Audio" + (" (Preferred)" if preferred_format == "audio" else ""),
                    callback_data=f"{CallbackPrefix.FORMAT}audio"
                )
            ])
            
        # Cancel button
        keyboard.append([
            InlineKeyboardButton("❌ Cancel", callback_data=CallbackPrefix.CANCEL)
        ])
        
        # Update the processing message with format selection
        await self.bot.edit_message_text(
            chat_id=context.chat_id,
            message_id=context.message_id,
            text=f"<b>{context.title}</b>\n\n{Text.SELECT_FORMAT}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

    async def show_quality_options(self, context: DownloadContext, format_type: str):
        """Show available quality options for the selected format."""
        keyboard = []
        prefix = CallbackPrefix.VIDEO_QUALITY if format_type == "video" else CallbackPrefix.AUDIO_QUALITY
        
        # Get user's preferred quality
        pref_key = "preferred_video_quality" if format_type == "video" else "preferred_audio_quality"
        preferred_quality = self.user_prefs.get_user_preference(context.user_id, pref_key)
        
        # Quality labels with resolution/bitrate info
        quality_labels = {
            'video': {
                'high': lambda f: f"High Quality ({f['height']}p)" if f else "High Quality",
                'medium': lambda f: f"Medium Quality ({f['height']}p)" if f else "Medium Quality",
                'low': lambda f: f"Low Quality ({f['height']}p)" if f else "Low Quality"
            },
            'audio': {
                'high': lambda f: f"High Quality ({f['abr']}kbps)" if f else "High Quality",
                'medium': lambda f: f"Medium Quality ({f['abr']}kbps)" if f else "Medium Quality",
                'low': lambda f: f"Low Quality ({f['abr']}kbps)" if f else "Low Quality"
            }
        }
        
        # Add quality buttons if formats are available
        for quality in ['high', 'medium', 'low']:
            fmt = context.formats[format_type][quality]
            if fmt:
                # Get base label with quality info
                base_label = quality_labels[format_type][quality](fmt)
                
                # Add preferred indicator if applicable
                if preferred_quality == quality:
                    base_label += " (Preferred)"
                
                # Add size if available
                size = fmt.get('file_size', 0)
                size_str = f" [{format_file_size(size)}]" if size else ""
                
                # Create button
                keyboard.append([
                    InlineKeyboardButton(
                        f"{'🎥' if format_type == 'video' else '🎵'} {base_label}{size_str}",
                        callback_data=f"{prefix}{quality}"
                    )
                ])
        
        # Back and Cancel buttons
        keyboard.append([
            InlineKeyboardButton("⬅️ Back", callback_data=f"{CallbackPrefix.FORMAT}back"),
            InlineKeyboardButton("❌ Cancel", callback_data=CallbackPrefix.CANCEL)
        ])
        
        # Update message with quality selection
        await self.bot.edit_message_text(
            chat_id=context.chat_id,
            message_id=context.message_id,
            text=f"<b>{context.title}</b>\n\n{Text.SELECT_QUALITY}",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.HTML
        )

async def download_ffmpeg():
    """Download FFmpeg for the current platform."""
    try:
        # For Streamlit Cloud, we'll use a simpler approach
        # Check if ffmpeg is already installed
        try:
            result = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
            if result.returncode == 0:
                logger.info("FFmpeg is already installed on the system")
                return None  # No need to add to PATH
        except:
            logger.info("FFmpeg not found in system PATH, will download")
        
        # Create ffmpeg directory
        ffmpeg_dir = Path.cwd() / "ffmpeg"
        ffmpeg_dir.mkdir(exist_ok=True)
        
        # Check if we already have ffmpeg in our directory
        if (ffmpeg_dir / "ffmpeg").exists() or (ffmpeg_dir / "ffmpeg.exe").exists():
            logger.info("Using previously downloaded FFmpeg")
            return str(ffmpeg_dir)
        
        # Download FFmpeg (simplified for Streamlit Cloud)
        logger.info("Downloading FFmpeg...")
        
        # For Streamlit Cloud, we'll use a pre-built static binary
        ffmpeg_url = "https://github.com/eugeneware/ffmpeg-static/releases/download/b4.4/ffmpeg-linux-x64"
        
        # Download the file
        response = requests.get(ffmpeg_url, stream=True)
        response.raise_for_status()
        
        # Save the file
        ffmpeg_path = ffmpeg_dir / "ffmpeg"
        with open(ffmpeg_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Make it executable
        os.chmod(ffmpeg_path, 0o755)
        
        logger.info("FFmpeg setup complete")
        return str(ffmpeg_dir)
        
    except Exception as e:
        logger.error(f"Error downloading FFmpeg: {e}")
        return None

# Check for Streamlit Cloud flag file
def should_start_bot():
    flag_file = Path.cwd() / "bot_running.flag"
    return flag_file.exists()

if __name__ == "__main__":
    # Only start the bot if the flag file exists (for Streamlit Cloud)
    if should_start_bot():
        logger.info("Bot flag file found, starting bot")
        TelegramYTDLBot.run_bot()
    else:
        logger.info("Bot flag file not found, not starting bot")
