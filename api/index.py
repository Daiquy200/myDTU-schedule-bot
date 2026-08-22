import sys
import os

# api/index.py -> parent is project root, where serverless_bot/ lives
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from serverless_bot.main import app