from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from telegram import Update

from .handlers.bot_handlers import create_application

app = FastAPI(title="Telegram Schedule Bot")

telegram_app = None


async def get_application():
    global telegram_app
    if telegram_app is None:
        logger.info("Initializing telegram application (lazy)...")
        telegram_app = create_application()
        await telegram_app.initialize()
        logger.info("Bot initialized (lazy)")
    return telegram_app


@app.on_event("startup")
async def startup():
    # Try eager init, but lazy fallback ensures Vercel serverless still works
    try:
        await get_application()
    except Exception as e:
        logger.warning(f"Startup init failed (will retry lazy): {e}")


@app.on_event("shutdown")
async def shutdown():
    global telegram_app
    if telegram_app:
        try:
            await telegram_app.shutdown()
        except Exception as e:
            logger.warning(f"Shutdown error: {e}")
        logger.info("Bot shutdown")


async def _process_update(request: Request):
    tg_app = await get_application()
    try:
        data = await request.json()
        logger.info(f"Webhook received update: {list(data.keys())}")
        update = Update.de_json(data, tg_app.bot)
        await tg_app.process_update(update)
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.exception(f"Webhook error: {e}")
        # Always return 200 to Telegram to avoid retry storm, but log error
        return JSONResponse({"ok": False, "error": str(e)}, status_code=200)


# Vercel rewrites map /webhook -> /api, but we handle all variants for safety
@app.post("/")
async def webhook_root(request: Request):
    return await _process_update(request)

@app.post("/webhook")
async def webhook(request: Request):
    return await _process_update(request)

@app.post("/api")
async def webhook_api(request: Request):
    return await _process_update(request)

@app.post("/api/webhook")
async def webhook_api_webhook(request: Request):
    return await _process_update(request)


@app.get("/")
async def root():
    return JSONResponse({"status": "ok", "message": "Bot is running. POST /webhook is ready."})

@app.get("/webhook")
async def webhook_get():
    return JSONResponse({"status": "ok", "message": "Webhook endpoint ready. Use POST /webhook"})

@app.get("/api")
async def api_get():
    return JSONResponse({"status": "ok", "message": "API ready"})

@app.get("/api/webhook")
async def api_webhook_get():
    return JSONResponse({"status": "ok", "message": "Webhook endpoint ready"})

@app.get("/health")
async def health():
    return JSONResponse({"status": "healthy"})

@app.get("/api/health")
async def api_health():
    return JSONResponse({"status": "healthy"})


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
