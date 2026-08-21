from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from .handlers.bot_handlers import create_application

app = FastAPI(title="Telegram Schedule Bot")

telegram_app = None

@app.on_event("startup")
async def startup():
    global telegram_app
    telegram_app = create_application()
    await telegram_app.initialize()
    logger.info("Bot initialized")

@app.on_event("shutdown")
async def shutdown():
    global telegram_app
    if telegram_app:
        await telegram_app.shutdown()
    logger.info("Bot shutdown")

@app.post("/webhook")
async def webhook(request: Request):
    global telegram_app
    if not telegram_app:
        return JSONResponse({"error": "Bot not initialized"}, status_code=500)
    
    try:
        data = await request.json()
        update = telegram_app.update_queue._create_update(data)
        await telegram_app.process_update(update)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/webhook")
async def webhook_get():
    return JSONResponse({"status": "ok", "message": "Webhook endpoint ready"})

@app.get("/health")
async def health():
    return JSONResponse({"status": "healthy"})

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)