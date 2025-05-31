import os
import sys
from pathlib import Path
from datetime import datetime

def debug_write(message):
    """Write a debug message directly to a file."""
    try:
        debug_dir = Path.cwd()
        debug_file = debug_dir / "debug.log"
        
        with open(debug_file, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.now()} - {message}\n")
    except Exception as e:
        # If we can't write to the file, try to print to stdout
        print(f"DEBUG ERROR: {e}")
        print(f"DEBUG MESSAGE: {message}")

# Write initial debug message
debug_write(f"Debug module loaded. Python version: {sys.version}")
debug_write(f"Current working directory: {os.getcwd()}")
debug_write(f"Files in current directory: {os.listdir('.')}")