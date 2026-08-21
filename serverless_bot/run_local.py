import os
import asyncio
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

from serverless_bot.handlers.bot_handlers import create_application

async def main():
    app = create_application()
    
    print("Bot dang chay local (polling mode)...")
    print("Nhan Ctrl+C de dung")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=[])
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\nDang dung bot...")
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())