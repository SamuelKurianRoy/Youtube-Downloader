import streamlit as st
import subprocess
import os
import signal
import time
import sys
import requests
from pathlib import Path
from datetime import datetime
import toml
import threading
import re

# Import the debug module
try:
    from debug import debug_write
except ImportError:
    # Create a simple debug_write function if the module doesn't exist
    def debug_write(message):
        print(f"DEBUG: {message}")

# Add this at the start of the script
debug_write("Streamlit app started")

# Set page config
st.set_page_config(
    page_title="Telegram YouTube Downloader Bot",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #FF0000;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.8rem;
        margin-top: 2rem;
    }
    .status-running {
        color: #00CC00;
        font-weight: bold;
    }
    .status-stopped {
        color: #FF0000;
        font-weight: bold;
    }
    .info-box {
        background-color: #f0f2f6;
        padding: 1rem;
        border-radius: 0.5rem;
        margin: 1rem 0;
    }
    .stButton>button {
        width: 100%;    
    }
    .log-container {
        height: 400px;
        overflow-y: auto;
        background-color: #f9f9f9;
        border-radius: 5px;
        padding: 10px;
        font-family: monospace;
    }
</style>
""", unsafe_allow_html=True)

# Define paths - adjusted for Streamlit Cloud
base_dir = Path.cwd()
logs_dir = base_dir / "logs"
bot_log_path = logs_dir / "bot.log"
user_log_path = logs_dir / "user.log"
bot_script_path = base_dir / "bot.py"
flag_file_path = base_dir / "bot_running.flag"

# Create logs directory if it doesn't exist
try:
    logs_dir.mkdir(exist_ok=True)
except Exception as e:
    st.error(f"Failed to create logs directory: {e}")
    # Fallback to a temporary directory
    import tempfile
    logs_dir = Path(tempfile.gettempdir()) / "telegram-ytdl-logs"
    logs_dir.mkdir(exist_ok=True)
    bot_log_path = logs_dir / "bot.log"
    user_log_path = logs_dir / "user.log"
    st.info(f"Using fallback logs directory: {logs_dir}")

# Check if we're running in Streamlit Cloud
is_streamlit_cloud = os.environ.get("STREAMLIT_SHARING_MODE") is not None

# Functions for Streamlit Cloud
def is_bot_running_in_cloud():
    """Check if the bot is running in Streamlit Cloud"""
    return flag_file_path.exists()

def start_bot_in_cloud():
    """Start the bot in Streamlit Cloud using flag file"""
    try:
        debug_write("Attempting to start bot in Streamlit Cloud")
        
        # Fix environment variables first
        fix_environment_variables()
        
        # Create the flag file
        with open(flag_file_path, 'w') as f:
            f.write(str(datetime.now()))
        debug_write(f"Flag file created at {flag_file_path}")
        
        # Verify the flag file was created
        if not flag_file_path.exists():
            debug_write("ERROR: Flag file was not created successfully")
            st.error("Failed to create bot flag file. Check file permissions.")
            return False
            
        debug_write(f"Flag file exists: {flag_file_path.exists()}")
        
        # Log the attempt
        with open(bot_log_path, 'a') as f:
            f.write(f"{datetime.now()} - INFO - Attempting to start bot via Streamlit Cloud\n")
        debug_write("Wrote to bot log about start attempt")
        
        # Always try to run the bot directly first (more reliable)
        success = run_bot_directly()
        if success:
            debug_write("Bot started directly")
            return True

        # If direct method fails, try subprocess method as fallback
        debug_write("Direct method failed, trying subprocess method as fallback")
        
        # In Streamlit Cloud, we need to actually start the process
        # We'll use a thread to avoid blocking the Streamlit app
        def run_bot():
            try:
                debug_write("Starting bot process in thread")
                with open(bot_log_path, 'a') as f:
                    f.write(f"{datetime.now()} - INFO - Starting bot process in thread\n")

                # Run the bot script with subprocess
                debug_write(f"Running: {sys.executable} {bot_script_path}")

                # Use subprocess.Popen for better control with improved pipe handling
                process = subprocess.Popen(
                    [sys.executable, str(bot_script_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,  # Separate stderr to avoid mixing
                    text=True,
                    bufsize=1,  # Line buffered
                    env=os.environ.copy()  # Pass current environment
                )

                # Store process reference for cleanup
                import threading
                current_thread = threading.current_thread()
                current_thread.process = process

                # Read output with timeout and error handling
                try:
                    # Use communicate with timeout to avoid hanging
                    stdout, stderr = process.communicate(timeout=30)  # 30 second timeout for startup

                    if stdout:
                        debug_write(f"BOT STDOUT: {stdout.strip()}")
                    if stderr:
                        debug_write(f"BOT STDERR: {stderr.strip()}")

                    debug_write(f"Bot process exited with code: {process.returncode}")

                except subprocess.TimeoutExpired:
                    debug_write("Bot process startup timeout - process is running in background")
                    # Process is running, don't wait for it to complete

                except Exception as pipe_error:
                    # Handle specific pipe errors
                    error_str = str(pipe_error).lower()
                    if "broken pipe" in error_str or "errno 32" in error_str:
                        debug_write("Broken pipe error detected - bot is running normally")
                    else:
                        debug_write(f"Pipe communication error: {pipe_error}")
                    # These errors are expected when the bot is running normally

            except Exception as e:
                error_msg = f"Failed to run bot: {e}"
                debug_write(f"ERROR: {error_msg}")
                with open(bot_log_path, 'a') as f:
                    f.write(f"{datetime.now()} - ERROR - {error_msg}\n")
        
        # Start the bot in a thread
        bot_thread = threading.Thread(target=run_bot)
        bot_thread.daemon = True  # Allow the thread to be terminated when the app stops
        bot_thread.start()
        debug_write("Bot thread started")
        
        return True
    except Exception as e:
        error_msg = f"Failed to start bot: {e}"
        debug_write(f"ERROR: {error_msg}")
        st.error(error_msg)
        return False

def stop_bot_in_cloud():
    """Stop the bot in Streamlit Cloud by removing flag file"""
    try:
        # Remove the flag file if it exists
        if flag_file_path.exists():
            flag_file_path.unlink()
            
        # Log the attempt
        with open(bot_log_path, 'a') as f:
            f.write(f"{datetime.now()} - INFO - Stopping bot via Streamlit Cloud\n")
            
        return True
    except Exception as e:
        st.error(f"Failed to stop bot: {e}")
        return False

# Global variables
bot_process = None

# Functions
def get_log_content(log_path, max_lines=100):
    """Get the content of a log file"""
    try:
        if os.path.exists(log_path):
            with open(log_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                return "".join(lines[-max_lines:])
        else:
            # If log file doesn't exist, create it with a message
            with open(log_path, 'w', encoding='utf-8') as f:
                message = f"{datetime.now()} - INFO - Log file created\n"
                f.write(message)
            return message
    except Exception as e:
        error_message = f"Error reading log: {str(e)}"
        st.error(error_message)
        # Try to create the log file with the error message
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(f"{datetime.now()} - ERROR - {error_message}\n")
        except:
            pass
        return error_message

def start_bot():
    """Start the bot process"""
    global bot_process
    
    if is_streamlit_cloud:
        # Use cloud-specific method
        success = start_bot_in_cloud()
        if success:
            st.session_state.bot_running = True
        return success
    else:
        # Original method for local deployment
        if bot_process is None or bot_process.poll() is not None:
            try:
                # Start the bot as a subprocess
                bot_process = subprocess.Popen(
                    [sys.executable, str(bot_script_path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                st.session_state.bot_running = True
                return True
            except Exception as e:
                st.error(f"Failed to start bot: {e}")
        return False

def stop_bot():
    """Stop the bot process"""
    global bot_process
    
    if is_streamlit_cloud:
        # Use cloud-specific method
        success = stop_bot_in_cloud()
        if success:
            st.session_state.bot_running = False
        return success
    else:
        # Original method for local deployment
        if bot_process is not None and bot_process.poll() is None:
            try:
                # Send SIGTERM signal to the process
                if os.name == 'nt':  # Windows
                    bot_process.terminate()
                else:  # Unix/Linux
                    os.kill(bot_process.pid, signal.SIGTERM)
                
                # Wait for process to terminate
                try:
                    bot_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate
                    if os.name == 'nt':
                        bot_process.kill()
                    else:
                        os.kill(bot_process.pid, signal.SIGKILL)
                
                bot_process = None
                st.session_state.bot_running = False
                return True
            except Exception as e:
                st.error(f"Failed to stop bot: {e}")
        return False

def get_download_stats():
    """Get download statistics from logs"""
    stats = {
        "total_requests": 0,
        "completed": 0,
        "failed": 0,
        "success_rate": 0,
        "recent_downloads": []
    }
    
    if os.path.exists(user_log_path):
        try:
            with open(user_log_path, 'r', encoding='utf-8') as f:
                logs = f.readlines()
                
            stats["total_requests"] = sum(1 for line in logs if "URL REQUEST" in line)
            stats["completed"] = sum(1 for line in logs if "DOWNLOAD COMPLETE" in line)
            stats["failed"] = sum(1 for line in logs if "DOWNLOAD FAILED" in line)
            
            if stats["completed"] + stats["failed"] > 0:
                stats["success_rate"] = (stats["completed"] / (stats["completed"] + stats["failed"])) * 100
                
            # Get recent downloads
            recent_downloads = []
            for line in reversed(logs):
                if "DOWNLOAD COMPLETE" in line:
                    parts = line.split(" | ")
                    if len(parts) >= 5:
                        try:
                            timestamp = parts[0]
                            title = parts[-1].replace("Title: ", "").strip()
                            format_type = parts[3].replace("Format: ", "").strip()
                            size = parts[4].replace("Size: ", "").replace("MB", "").strip()
                            
                            recent_downloads.append({
                                "timestamp": timestamp,
                                "title": title,
                                "format": format_type,
                                "size": f"{size} MB"
                            })
                            
                            if len(recent_downloads) >= 5:
                                break
                        except:
                            pass
                            
            stats["recent_downloads"] = recent_downloads
                
        except Exception as e:
            st.error(f"Error reading statistics: {e}")
            
    return stats

def check_yt_dlp_version():
    """Check the installed version of yt-dlp"""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", "yt-dlp"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("Version:"):
                    return line.replace("Version:", "").strip()
        
        return "Unknown"
    except:
        return "Unknown"

# Function to check if bot token is configured
def is_bot_configured():
    """Check if the bot token is configured in secrets or environment variables"""
    debug_write("Checking if bot is configured")
    
    # Check environment variables first
    env_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if env_token:
        debug_write("Bot token found in environment variables")
        return True
        
    # Try to read from secrets file directly
    try:
        secrets_path = Path.cwd() / ".streamlit" / "secrets.toml"
        debug_write(f"Looking for secrets file at: {secrets_path}")
        
        if secrets_path.exists():
            debug_write(f"Found secrets file at {secrets_path}")
            try:
                import toml
                secrets_content = toml.load(str(secrets_path))
                debug_write(f"Loaded secrets file, keys: {list(secrets_content.keys())}")
                
                if "TELEGRAM_BOT_TOKEN" in secrets_content:
                    debug_write("Bot token found in secrets file")
                    # Copy to environment variables
                    os.environ["TELEGRAM_BOT_TOKEN"] = secrets_content["TELEGRAM_BOT_TOKEN"]
                    return True
            except Exception as e:
                debug_write(f"Error parsing secrets file: {e}")
    except Exception as e:
        debug_write(f"Error reading secrets file directly: {e}")
    
    # Then check Streamlit secrets as a fallback
    try:
        if hasattr(st, 'secrets'):
            debug_write(f"Checking Streamlit secrets, keys: {list(st.secrets.keys())}")
            if "TELEGRAM_BOT_TOKEN" in st.secrets:
                debug_write("Bot token found in Streamlit secrets")
                # Copy to environment variables for child processes
                os.environ["TELEGRAM_BOT_TOKEN"] = st.secrets["TELEGRAM_BOT_TOKEN"]
                return True
    except Exception as e:
        debug_write(f"Error checking Streamlit secrets: {e}")
    
    debug_write("Bot token not found in any location")
    return False

# Add a function to check bot token
def check_bot_token():
    """Check if the bot token is valid and accessible"""
    try:
        # Check environment variables first
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        
        # Then check Streamlit secrets
        if token is None:
            try:
                token = st.secrets["TELEGRAM_BOT_TOKEN"]
            except:
                pass
        
        if token:
            masked_token = f"{token[:5]}...{token[-5:] if len(token) > 10 else ''}"
            debug_write(f"Bot token found: {masked_token}")
            
            # Set the token in environment variables for child processes
            os.environ["TELEGRAM_BOT_TOKEN"] = token
            debug_write("Bot token set in environment variables")
            
            return True
        else:
            debug_write("ERROR: No bot token found")
            return False
    except Exception as e:
        debug_write(f"ERROR checking bot token: {e}")
        return False

# Define a direct bot runner that doesn't rely on subprocess
def run_bot_directly():
    """Run the bot directly in the same process"""
    try:
        debug_write("Running bot directly in the same process")
        
        # Fix environment variables first
        fix_environment_variables()
        
        # Import the bot module
        from bot import TelegramYTDLBot
        
        # Create and run the bot
        debug_write("Creating bot instance")
        bot = TelegramYTDLBot()
        
        # Run the bot in a separate thread
        def bot_thread_func():
            try:
                debug_write("Starting bot in thread")
                import asyncio
                asyncio.run(bot.start())
            except Exception as e:
                debug_write(f"ERROR: Bot thread failed: {e}")
                import traceback
                debug_write(f"Traceback: {traceback.format_exc()}")
        
        # Start the bot in a thread
        bot_thread = threading.Thread(target=bot_thread_func)
        bot_thread.daemon = True
        bot_thread.start()
        debug_write("Bot thread started")
        
        return True
    except Exception as e:
        debug_write(f"ERROR: Failed to run bot directly: {e}")
        import traceback
        debug_write(f"Traceback: {traceback.format_exc()}")
        return False

# Add a function to create the flag file
def create_flag_file():
    """Create the bot running flag file"""
    try:
        debug_write(f"Creating flag file at {flag_file_path}")
        
        # Ensure the directory exists
        flag_file_path.parent.mkdir(exist_ok=True)
        
        # Create the flag file
        with open(flag_file_path, 'w') as f:
            f.write(str(datetime.now()))
            
        debug_write(f"Flag file created successfully: {flag_file_path.exists()}")
        return True
    except Exception as e:
        debug_write(f"Error creating flag file: {e}")
        return False

# Add a function to check if the flag file exists
def check_flag_file():
    """Check if the flag file exists and create it if needed"""
    if flag_file_path.exists():
        debug_write(f"Flag file already exists at {flag_file_path}")
        return True
    else:
        debug_write(f"Flag file does not exist at {flag_file_path}")
        return create_flag_file()

# Add this function to check and fix environment variables
def fix_environment_variables():
    """Check and fix environment variables that might be causing issues"""
    debug_write("Checking environment variables for issues")
    
    # Check if TELEGRAM_WEBHOOK_PORT contains the bot token (common mistake)
    webhook_port = os.environ.get("TELEGRAM_WEBHOOK_PORT", "")
    if webhook_port and not webhook_port.isdigit() and len(webhook_port) > 20:
        debug_write(f"Found invalid TELEGRAM_WEBHOOK_PORT: {webhook_port[:5]}...")
        # This looks like a token, not a port
        debug_write("Clearing invalid TELEGRAM_WEBHOOK_PORT")
        os.environ["TELEGRAM_WEBHOOK_PORT"] = ""
        
    # Check if TELEGRAM_API_ROOT is valid
    api_root = os.environ.get("TELEGRAM_API_ROOT", "")
    if api_root and not api_root.startswith(("http://", "https://")):
        debug_write(f"Found invalid TELEGRAM_API_ROOT: {api_root}")
        # Set to default
        debug_write("Setting TELEGRAM_API_ROOT to default")
        os.environ["TELEGRAM_API_ROOT"] = "https://api.telegram.org"
    
    # Check if TELEGRAM_WEBHOOK_URL is valid
    webhook_url = os.environ.get("TELEGRAM_WEBHOOK_URL", "")
    if webhook_url and not webhook_url.startswith(("http://", "https://")):
        debug_write(f"Found invalid TELEGRAM_WEBHOOK_URL: {webhook_url}")
        # Clear it
        debug_write("Clearing invalid TELEGRAM_WEBHOOK_URL")
        os.environ["TELEGRAM_WEBHOOK_URL"] = ""
    
    debug_write("Environment variables checked and fixed")

# Initialize session state
if 'bot_running' not in st.session_state:
    # Check if the bot is already running in Streamlit Cloud
    if is_streamlit_cloud:
        st.session_state.bot_running = is_bot_running_in_cloud()
    else:
        st.session_state.bot_running = False
    
if 'auto_refresh' not in st.session_state:
    st.session_state.auto_refresh = False
    
if 'last_refresh' not in st.session_state:
    st.session_state.last_refresh = datetime.now()

# Sidebar
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/0/09/YouTube_full-color_icon_%282017%29.svg/800px-YouTube_full-color_icon_%282017%29.svg.png", width=100)
    st.markdown("<h2 style='text-align: center;'>Bot Controls</h2>", unsafe_allow_html=True)
    
    # Check if bot is configured
    if not is_bot_configured():
        st.error("⚠️ Bot token not configured!")
        st.info("Please set up your bot token in Streamlit secrets or environment variables.")
        
        # Add a secrets configuration section
        with st.expander("Configure Bot Secrets"):
            st.write("Create a file named `.streamlit/secrets.toml` with the following content:")
            
            example_secrets = """
            # Telegram Bot Configuration
            TELEGRAM_BOT_TOKEN = "your_bot_token_here"
            TELEGRAM_WEBHOOK_URL = ""
            TELEGRAM_WEBHOOK_PORT = ""
            TELEGRAM_API_ROOT = ""
            
            # API Keys
            OPENAI_API_KEY = ""
            COBALT_INSTANCE_URL = ""
            
            # Bot Settings
            YTDL_AUTOUPDATE = "true"
            ADMIN_ID = ""
            WHITELISTED_IDS = ""
            ALLOW_GROUPS = "false"
            """
            
            st.code(example_secrets, language="toml")
            
            st.write("Or configure these settings in Streamlit Cloud's secrets management.")
        
        # Separate expander for bot creation instructions
        with st.expander("How to Create a Telegram Bot"):
            st.write("""
            ### Creating a Telegram Bot
            
            1. Open Telegram and search for the "BotFather" (@BotFather)
            2. Start a chat with BotFather and send the command `/newbot`
            3. Follow the instructions to create your bot:
               - Provide a name for your bot
               - Provide a username for your bot (must end with 'bot')
            4. BotFather will give you a token that looks like `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`
            5. Copy this token and use it as your `TELEGRAM_BOT_TOKEN`
            
            ### Setting Up Streamlit Cloud Secrets
            
            1. Go to your Streamlit Cloud dashboard
            2. Select your app
            3. Click on "Settings" in the app menu
            4. Scroll down to "Secrets"
            5. Add your bot token in the following format:
            
            ```toml
            TELEGRAM_BOT_TOKEN = "your_bot_token_here"
            ```
            
            6. Click "Save"
            7. Restart your app
            """)
            
        # Add a form to set the bot token temporarily
        st.write("### Temporary Bot Token Configuration")
        st.write("You can set the bot token temporarily for this session:")
        
        with st.form("bot_token_form"):
            temp_token = st.text_input("Enter your Telegram Bot Token", type="password")
            submit_button = st.form_submit_button("Set Token")
            
            if submit_button and temp_token:
                os.environ["TELEGRAM_BOT_TOKEN"] = temp_token
                st.success("Bot token set for this session!")
                st.info("Note: This setting will be lost when the app restarts. For permanent configuration, use Streamlit secrets.")
                time.sleep(2)
                st.rerun()
    
    status = "🟢 RUNNING" if st.session_state.bot_running else "🔴 STOPPED"
    status_class = "status-running" if st.session_state.bot_running else "status-stopped"
    st.markdown(f"<h3 style='text-align: center;' class='{status_class}'>{status}</h3>", unsafe_allow_html=True)
    
    if st.session_state.bot_running:
        if st.button("Stop Bot"):
            if is_streamlit_cloud:
                if stop_bot_in_cloud():
                    st.success("Bot stopping... Flag file removed.")
                    st.session_state.bot_running = False
                    time.sleep(1)
                    st.rerun()
            else:
                if stop_bot():
                    st.success("Bot stopped.")
                    st.session_state.bot_running = False
                    time.sleep(1)
                    st.rerun()
    else:
        if st.button("Start Bot"):
            if is_streamlit_cloud:
                if start_bot_in_cloud():
                    st.success("Bot starting... Flag file created.")
                    st.session_state.bot_running = True
                    time.sleep(1)
                    st.rerun()
            else:
                if start_bot():
                    st.success("Bot started.")
                    st.session_state.bot_running = True
                    time.sleep(1)
                    st.rerun()
    
    st.divider()
    
    st.markdown("### Auto-Refresh")
    auto_refresh = st.checkbox("Enable auto-refresh", value=st.session_state.auto_refresh)
    
    if auto_refresh != st.session_state.auto_refresh:
        st.session_state.auto_refresh = auto_refresh
        st.rerun()
    
    if st.session_state.auto_refresh:
        refresh_interval = st.slider("Refresh interval (seconds)", 5, 60, 15)
        current_time = datetime.now()
        if (current_time - st.session_state.last_refresh).total_seconds() > refresh_interval:
            st.session_state.last_refresh = current_time
            st.rerun()
            
        st.info(f"Next refresh in {refresh_interval - int((current_time - st.session_state.last_refresh).total_seconds())} seconds")
    
    st.divider()
    
    # System info
    st.markdown("### System Info")
    yt_dlp_version = check_yt_dlp_version()
    st.markdown(f"**yt-dlp version:** {yt_dlp_version}")
    st.markdown(f"**Python version:** {sys.version.split()[0]}")
    
    if st.button("Manual Refresh", use_container_width=True):
        st.session_state.last_refresh = datetime.now()
        st.rerun()

# Main content
st.markdown("<h1 class='main-header'>📥 Telegram YouTube Downloader Bot</h1>", unsafe_allow_html=True)

# Dashboard
st.markdown("<h2 class='sub-header'>📊 Dashboard</h2>", unsafe_allow_html=True)

stats = get_download_stats()
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Total Requests", stats["total_requests"])
    
with col2:
    st.metric("Downloads Completed", stats["completed"])
    
with col3:
    st.metric("Downloads Failed", stats["failed"])
    
with col4:
    st.metric("Success Rate", f"{stats['success_rate']:.1f}%")

# Recent downloads
if stats["recent_downloads"]:
    st.markdown("<h2 class='sub-header'>🔄 Recent Downloads</h2>", unsafe_allow_html=True)
    
    for download in stats["recent_downloads"]:
        with st.container():
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.markdown(f"**{download['title']}**")
            with col2:
                st.markdown(f"Format: {download['format']}")
            with col3:
                st.markdown(f"Size: {download['size']}")
            st.divider()

# Logs section
st.markdown("<h2 class='sub-header'>📜 Logs</h2>", unsafe_allow_html=True)
tab1, tab2 = st.tabs(["Bot Log", "User Activity Log"])

with tab1:
    col1, col2 = st.columns([3, 1])
    
    with col1:
        bot_search = st.text_input("Filter bot logs (case-insensitive):", key="bot_search")
    
    with col2:
        bot_log_level = st.selectbox(
            "Filter by log level:",
            ["All", "INFO", "WARNING", "ERROR", "CRITICAL"],
            key="bot_log_level"
        )
    
    # Get log content
    bot_log_content = get_log_content(bot_log_path, max_lines=500)
    
    # Apply filters
    if bot_search:
        filtered_lines = [line for line in bot_log_content.split('\n') 
                         if bot_search.lower() in line.lower()]
        bot_log_content = '\n'.join(filtered_lines)
    
    if bot_log_level != "All":
        filtered_lines = [line for line in bot_log_content.split('\n') 
                         if f" - {bot_log_level} - " in line]
        bot_log_content = '\n'.join(filtered_lines)
    
    # Display logs
    st.markdown("<div class='log-container'>", unsafe_allow_html=True)
    st.code(bot_log_content, language="text")
    st.markdown("</div>", unsafe_allow_html=True)

with tab2:
    col1, col2 = st.columns([3, 1])
    
    with col1:
        user_search = st.text_input("Filter user logs (case-insensitive):", key="user_search")
    
    with col2:
        user_activity_type = st.selectbox(
            "Filter by activity type:",
            ["All", "URL REQUEST", "VIDEO INFO", "FORMAT PREFERENCE", "DOWNLOAD START", 
             "DOWNLOAD COMPLETE", "DOWNLOAD FAILED", "PROCESSING ERROR"],
            key="user_activity_type"
        )
    
    # Get log content
    user_log_content = get_log_content(user_log_path, max_lines=500)
    
    # Apply filters
    if user_search:
        filtered_lines = [line for line in user_log_content.split('\n') 
                         if user_search.lower() in line.lower()]
        user_log_content = '\n'.join(filtered_lines)
    
    if user_activity_type != "All":
        filtered_lines = [line for line in user_log_content.split('\n') 
                         if f" | {user_activity_type} | " in line]
        user_log_content = '\n'.join(filtered_lines)
    
    # Display logs
    st.markdown("<div class='log-container'>", unsafe_allow_html=True)
    st.code(user_log_content, language="text")
    st.markdown("</div>", unsafe_allow_html=True)

# Bot information
st.markdown("<h2 class='sub-header'>ℹ️ Bot Information</h2>", unsafe_allow_html=True)

with st.expander("About This Bot"):
    st.markdown("""
    ### Telegram YouTube Downloader Bot
    
    This bot allows users to download videos from various platforms through Telegram.
    
    **Supported Platforms:**
    - YouTube
    - TikTok
    - Instagram
    - Twitter/X
    - Facebook
    - And many more!
    
    **Features:**
    - Download videos in different quality options
    - Extract audio from videos
    - Automatic format selection
    - Support for playlists
    - Automatic yt-dlp updates
    
    **Bot Commands:**
    - `/start` - Start the bot
    - `/help` - Show help information
    
    **How It Works:**
    1. User sends a video URL to the bot
    2. Bot extracts video information
    3. User selects format (video/audio) and quality
    4. Bot downloads and sends the file to the user
    """)

with st.expander("Usage Instructions"):
    st.markdown("""
    ### How to Use the Bot
    
    1. **Start the bot** using the START BOT button in the sidebar
    2. **Open Telegram** and search for your bot by username
    3. **Send a URL** to the bot from any supported platform
    4. **Select format** (video or audio) when prompted
    5. **Choose quality** from the available options
    6. **Wait for download** to complete
    7. **Receive the file** directly in your Telegram chat
    
    ### Monitoring
    
    Use this dashboard to:
    - Monitor bot status
    - View download statistics
    - Check logs for errors
    - Track user activity
    
    ### Troubleshooting
    
    If the bot stops responding:
    1. Check the Bot Log for errors
    2. Stop and restart the bot using the sidebar controls
    3. Ensure your system has internet connectivity
    """)

# Add a debug section to the app
with st.expander("Debug Information"):
    st.write("### Log File Paths")
    st.write(f"Bot Log Path: `{bot_log_path}`")
    st.write(f"User Log Path: `{user_log_path}`")
    st.write(f"Flag File Path: `{flag_file_path}`")
    st.write(f"Debug Log Path: `{Path.cwd() / 'debug.log'}`")
    
    st.write("### Directory Structure")
    st.write(f"Current Working Directory: `{os.getcwd()}`")
    st.write(f"Logs Directory: `{logs_dir}`")
    
    # Check for secrets file
    secrets_path = Path.cwd() / ".streamlit" / "secrets.toml"
    st.write(f"Secrets File Path: `{secrets_path}`")
    st.write(f"Secrets File Exists: `{secrets_path.exists()}`")
    
    # Try to read secrets file content
    if secrets_path.exists():
        try:
            with open(secrets_path, 'r') as f:
                secrets_content = f.read()
            st.write("### Secrets File Content (masked)")
            # Mask any tokens in the file
            masked_content = re.sub(r'(["\']\w{5,})[^"\']*(["\'])', r'\1...\2', secrets_content)
            st.code(masked_content, language="toml")
        except Exception as e:
            st.error(f"Error reading secrets file: {e}")
    
    # Check if we can access secrets through Streamlit
    st.write("### Streamlit Secrets Access")
    try:
        # List available secret keys (without showing values)
        secret_keys = list(st.secrets.keys()) if hasattr(st, 'secrets') else []
        st.write(f"Available secret keys: {secret_keys}")
        
        # Check specifically for TELEGRAM_BOT_TOKEN
        has_token = "TELEGRAM_BOT_TOKEN" in st.secrets if hasattr(st, 'secrets') else False
        st.write(f"Has TELEGRAM_BOT_TOKEN in secrets: {has_token}")
    except Exception as e:
        st.error(f"Error accessing Streamlit secrets: {e}")
    
    st.write("### File Existence")
    st.write(f"Logs Directory Exists: `{logs_dir.exists()}`")
    st.write(f"Bot Log Exists: `{Path(bot_log_path).exists()}`")
    st.write(f"User Log Exists: `{Path(user_log_path).exists()}`")
    st.write(f"Flag File Exists: `{Path(flag_file_path).exists()}`")
    st.write(f"Debug Log Exists: `{(Path.cwd() / 'debug.log').exists()}`")
    
    # List files in the current directory
    st.write("### Files in Current Directory")
    try:
        files = os.listdir('.')
        st.write(f"Files: {files}")
    except Exception as e:
        st.error(f"Error listing files: {e}")
    
    # Show debug log if it exists
    debug_log_path = Path.cwd() / "debug.log"
    if debug_log_path.exists():
        st.write("### Debug Log")
        with open(debug_log_path, 'r', encoding='utf-8') as f:
            debug_content = f.read()
        st.code(debug_content, language="text")
    
    if st.button("Create Test Log Entries"):
        try:
            debug_write("Test log entry button clicked")
            
            # Create logs directory if it doesn't exist
            logs_dir.mkdir(exist_ok=True)
            debug_write(f"Logs directory created/verified: {logs_dir}")
            
            # Write test entries to both log files
            with open(bot_log_path, 'a', encoding='utf-8') as f:
                test_message = f"{datetime.now()} - INFO - Test log entry created via debug button\n"
                f.write(test_message)
                debug_write(f"Wrote to bot log: {test_message}")
                
            with open(user_log_path, 'a', encoding='utf-8') as f:
                test_message = f"{datetime.now()} | TEST ENTRY | User: 0 | URL: https://example.com | Title: Test Entry\n"
                f.write(test_message)
                debug_write(f"Wrote to user log: {test_message}")
                
            st.success("Test log entries created successfully!")
            debug_write("Test log entries created successfully")
        except Exception as e:
            error_message = f"Failed to create test log entries: {e}"
            st.error(error_message)
            debug_write(f"ERROR: {error_message}")

# Add this to the sidebar when bot is not configured
if not is_bot_configured():
    if st.button("Check Bot Token Again"):
        if is_bot_configured():
            st.success("Bot token found!")
            time.sleep(1)
            st.rerun()
        else:
            st.error("Still no bot token found. Please check the debug information.")

# Add this to the main UI section
with st.expander("Bot Flag File Status"):
    st.write(f"Flag file path: `{flag_file_path}`")
    flag_exists = flag_file_path.exists()
    st.write(f"Flag file exists: `{flag_exists}`")
    
    if flag_exists:
        try:
            with open(flag_file_path, 'r') as f:
                flag_content = f.read()
            st.write(f"Flag file content: `{flag_content}`")
        except Exception as e:
            st.error(f"Error reading flag file: {e}")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Create Flag File"):
            if create_flag_file():
                st.success("Flag file created successfully!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Failed to create flag file. Check permissions.")
    
    with col2:
        if st.button("Delete Flag File"):
            try:
                if flag_file_path.exists():
                    flag_file_path.unlink()
                    st.success("Flag file deleted successfully!")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.info("Flag file doesn't exist.")
            except Exception as e:
                st.error(f"Error deleting flag file: {e}")
    
    # Add a button to check if the bot can read the flag file
    if st.button("Test Bot Flag File"):
        from bot import should_start_bot
        if should_start_bot():
            st.success("Bot can detect the flag file!")
        else:
            st.error("Bot cannot detect the flag file.")

# Add this to the debug section
def test_secrets_access():
    """Test if the bot can access the secrets file"""
    try:
        # Try to read the secrets file directly
        secrets_path = Path.cwd() / ".streamlit" / "secrets.toml"
        if not secrets_path.exists():
            return False, f"Secrets file not found at {secrets_path}"
        
        # Try to parse the secrets file
        import toml
        secrets_content = toml.load(str(secrets_path))
        
        # Check if the token is in the secrets file
        if "TELEGRAM_BOT_TOKEN" not in secrets_content:
            return False, "TELEGRAM_BOT_TOKEN not found in secrets file"
        
        # Check if the token is valid (not empty)
        token = secrets_content["TELEGRAM_BOT_TOKEN"]
        if not token or len(token) < 10:
            return False, "TELEGRAM_BOT_TOKEN is empty or too short"
        
        # Set the token in environment variables
        os.environ["TELEGRAM_BOT_TOKEN"] = token
        
        return True, f"Successfully read token from secrets file: {token[:5]}...{token[-5:] if len(token) > 10 else ''}"
    except Exception as e:
        return False, f"Error reading secrets file: {e}"

# Add a button to test secrets access
with st.expander("Test Secrets Access"):
    if st.button("Test Secrets File Access"):
        success, message = test_secrets_access()
        if success:
            st.success(message)
        else:
            st.error(message)

# Add this to the main UI section
with st.expander("Environment Variables"):
    st.write("### Current Environment Variables")
    
    # Display current environment variables
    env_vars = {
        "TELEGRAM_BOT_TOKEN": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        "TELEGRAM_WEBHOOK_URL": os.environ.get("TELEGRAM_WEBHOOK_URL", ""),
        "TELEGRAM_WEBHOOK_PORT": os.environ.get("TELEGRAM_WEBHOOK_PORT", ""),
        "TELEGRAM_API_ROOT": os.environ.get("TELEGRAM_API_ROOT", ""),
        "ADMIN_ID": os.environ.get("ADMIN_ID", ""),
        "WHITELISTED_IDS": os.environ.get("WHITELISTED_IDS", ""),
        "ALLOW_GROUPS": os.environ.get("ALLOW_GROUPS", ""),
        "YTDL_AUTOUPDATE": os.environ.get("YTDL_AUTOUPDATE", ""),
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY", ""),
        "COBALT_INSTANCE_URL": os.environ.get("COBALT_INSTANCE_URL", "")
    }
    
    # Display masked values
    for key, value in env_vars.items():
        if key == "TELEGRAM_BOT_TOKEN" or key == "OPENAI_API_KEY":
            # Mask sensitive values
            masked_value = f"{value[:5]}...{value[-5:] if len(value) > 10 else ''}" if value else ""
            st.text_input(key, value=masked_value, disabled=True)
        else:
            st.text_input(key, value=value, disabled=True)
    
    # Add a button to fix environment variables
    if st.button("Fix Environment Variables"):
        fix_environment_variables()
        st.success("Environment variables checked and fixed!")
        time.sleep(1)
        st.rerun()

# Add this to the main UI section
with st.expander("Fix Bot Issues"):
    st.write("### Fix Common Bot Issues")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Check Bot Token"):
            if check_bot_token():
                st.success("Bot token is valid and accessible!")
            else:
                st.error("Bot token is not valid or not accessible.")
    
    with col2:
        if st.button("Fix All Environment Variables"):
            # Fix environment variables
            fix_environment_variables()
            
            # Check if TELEGRAM_WEBHOOK_PORT is a valid port number
            webhook_port = os.environ.get("TELEGRAM_WEBHOOK_PORT", "")
            if webhook_port and not webhook_port.isdigit():
                st.warning(f"Invalid TELEGRAM_WEBHOOK_PORT: {webhook_port[:5]}...")
                os.environ["TELEGRAM_WEBHOOK_PORT"] = ""
                st.info("TELEGRAM_WEBHOOK_PORT has been cleared.")
            
            # Check if TELEGRAM_API_ROOT is valid
            api_root = os.environ.get("TELEGRAM_API_ROOT", "")
            if api_root and not api_root.startswith(("http://", "https://")):
                st.warning(f"Invalid TELEGRAM_API_ROOT: {api_root}")
                os.environ["TELEGRAM_API_ROOT"] = "https://api.telegram.org"
                st.info("TELEGRAM_API_ROOT has been set to default.")
            
            # Check if TELEGRAM_WEBHOOK_URL is valid
            webhook_url = os.environ.get("TELEGRAM_WEBHOOK_URL", "")
            if webhook_url and not webhook_url.startswith(("http://", "https://")):
                st.warning(f"Invalid TELEGRAM_WEBHOOK_URL: {webhook_url}")
                os.environ["TELEGRAM_WEBHOOK_URL"] = ""
                st.info("TELEGRAM_WEBHOOK_URL has been cleared.")
            
            st.success("Environment variables have been fixed!")
            time.sleep(1)
            st.rerun()


