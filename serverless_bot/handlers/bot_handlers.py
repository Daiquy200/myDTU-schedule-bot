import os
import json
import tempfile
from typing import Dict, List, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.constants import ParseMode

from ..db.database import db
from ..parser.parse_pdf import parse_pdf
from ..parser.parse_text import parse_registration_text

WEEKDAYS_VN = {1: "Thứ 2", 2: "Thứ 3", 3: "Thứ 4", 4: "Thứ 5", 5: "Thứ 6", 6: "Thứ 7", 7: "Chủ nhật"}

pending_pdfs: Dict[int, List[Dict]] = {}

def format_schedule_item(item: Dict) -> str:
    lines = []
    if item.get("start_time") and item.get("end_time"):
        lines.append(f"🕐 {item['start_time']} - {item['end_time']}")
    if item.get("subject"):
        lines.append(f"📚 {item['subject']}")
    if item.get("subject_code"):
        code_parts = [item['subject_code']]
        if item.get('class_code'):
            code_parts.append(item['class_code'])
        lines.append(f"📝 Mã: {' '.join(code_parts)}")
    if item.get("room"):
        lines.append(f"🏫 {item['room']}")
    if item.get("lecturer"):
        lines.append(f"👨‍🏫 {item['lecturer']}")
    if item.get("week_range"):
        lines.append(f"📅 Tuần: {item['week_range']}")
    if item.get("note"):
        lines.append(f"💬 {item['note']}")
    return "\n".join(lines)

def format_schedule_list(items: List[Dict], title: str) -> str:
    if not items:
        return f"{title}\n\n🎉 Không có lịch học."
    
    grouped = {}
    for item in items:
        date = item['date']
        if date not in grouped:
            grouped[date] = []
        grouped[date].append(item)
    
    lines = [title]
    for date in sorted(grouped.keys()):
        day_items = grouped[date]
        try:
            dt = __import__('datetime').datetime.strptime(date, "%Y-%m-%d")
            day_name = WEEKDAYS_VN[dt.isoweekday()]
            date_display = dt.strftime("%d/%m")
        except:
            day_name = ""
            date_display = date
        
        lines.append(f"\n📅 {day_name} ({date_display}):")
        for item in day_items:
            lines.append(format_schedule_item(item))
    
    return "\n".join(lines)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.first_name or "", user.username or "")
    
    text = (
        "👋 Chào bạn!\n"
        "Hãy gửi PDF thời khóa biểu hoặc file CSV/TXT (xuất từ myDTU) để mình phân tích và lưu lịch học.\n\n"
        "📥 TIỆN ÍCH XUẤT LỊCH PDF (myDTU):\n"
        "• MediaFire: https://www.mediafire.com/folder/lnjtg2o3zxsf7/mydtu-schedule-pdf\n"
        "• Google Drive: https://drive.google.com/drive/folders/1E2_epNUd-oeot6CrmUQhX73TcY1pZYK9?usp=drive_link\n"
        "Cài tiện ích -> vào myDTU.duytan.edu.vn -> Thời khóa biểu -> Bấm Xuất PDF -> gửi file cho bot\n\n"
        "Các lệnh:\n"
        "/today - Xem lịch hôm nay\n"
        "/tomorrow - Xem lịch ngày mai\n"
        "/week - Xem lịch tuần này\n"
        "/next - Tiết học tiếp theo\n"
        "/lich - Xem lịch gần nhất\n"
        "/delete - Xóa lịch học\n"
        "/help - Hướng dẫn chi tiết"
    )
    await update.message.reply_text(text)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 HƯỚNG DẪN SỬ DỤNG\n\n"
        "📥 BƯỚC 1 - TẢI TIỆN ÍCH XUẤT LỊCH PDF:\n"
        "• MediaFire: https://www.mediafire.com/folder/lnjtg2o3zxsf7/mydtu-schedule-pdf\n"
        "• Google Drive: https://drive.google.com/drive/folders/1E2_epNUd-oeot6CrmUQhX73TcY1pZYK9?usp=drive_link\n"
        "Cài đặt -> vào myDTU.duytan.edu.vn -> Đăng nhập -> Thời khóa biểu\n"
        "Bấm nút Xuất PDF của tiện ích để tải file\n\n"
        "📄 BƯỚC 2 - GỬI CHO BOT:\n"
        "Gửi file PDF (hoặc CSV/TXT từ trang Đăng ký môn) vào bot\n"
        "Bot sẽ phân tích và hiển thị lịch để bạn xác nhận\n"
        "Chọn:\n"
        "   ✅ Thay thế lịch cũ (mặc định)\n"
        "   ➕ Cộng thêm vào lịch hiện tại\n"
        "   ❌ Hủy\n\n"
        "Lệnh:\n"
        "/today - Lịch hôm nay\n"
        "/tomorrow - Lịch ngày mai\n"
        "/week - Lịch tuần này\n"
        "/next - Tiết học tiếp theo\n"
        "/lich - Lịch gần nhất\n"
        "/delete - Xóa toàn bộ lịch\n"
        "/help - Hiện hướng dẫn này"
    )
    await update.message.reply_text(text)

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    today_str = __import__('datetime').datetime.now().strftime("%Y-%m-%d")
    items = db.get_schedule(user_id, today_str, today_str)
    text = format_schedule_list(items, f"📅 LỊCH HỌC HÔM NAY ({today_str[8:10]}/{today_str[5:7]})")
    await update.message.reply_text(text)

async def tomorrow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    tomorrow_dt = __import__('datetime').datetime.now() + __import__('datetime').timedelta(days=1)
    tomorrow_str = tomorrow_dt.strftime("%Y-%m-%d")
    items = db.get_schedule(user_id, tomorrow_str, tomorrow_str)
    text = format_schedule_list(items, f"📅 LỊCH HỌC NGÀY MAI ({tomorrow_str[8:10]}/{tomorrow_str[5:7]})")
    await update.message.reply_text(text)

async def week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = __import__('datetime').datetime.now()
    week_start = now - __import__('datetime').timedelta(days=now.weekday())
    week_end = week_start + __import__('datetime').timedelta(days=6)
    items = db.get_schedule(user_id, week_start.strftime("%Y-%m-%d"), week_end.strftime("%Y-%m-%d"))
    text = format_schedule_list(items, f"📅 LỊCH TUẦN ({week_start.strftime('%d/%m')} - {week_end.strftime('%d/%m')})")
    await update.message.reply_text(text)

async def next_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    item = db.get_next_class(user_id)
    if not item:
        await update.message.reply_text("🎉 Không có tiết học nào sắp tới.")
        return
    text = "⏰ TIẾT HỌC TIẾP THEO:\n\n" + format_schedule_item(item)
    await update.message.reply_text(text)

async def lich(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = __import__('datetime').datetime.now()
    week_start = now - __import__('datetime').timedelta(days=now.weekday())
    week_end = week_start + __import__('datetime').timedelta(days=13)
    items = db.get_schedule(user_id, week_start.strftime("%Y-%m-%d"), week_end.strftime("%Y-%m-%d"))
    text = format_schedule_list(items, "📅 LỊCH HỌC GẦN NHẤT (2 tuần)")
    await update.message.reply_text(text)

async def delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("✅ Xác nhận xóa", callback_data="delete_confirm"),
            InlineKeyboardButton("❌ Hủy", callback_data="delete_cancel")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "⚠️ Bạn có chắc muốn xóa TOÀN BỘ lịch học của mình?\nHành động này không thể hoàn tác.",
        reply_markup=reply_markup
    )

async def handle_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data == "delete_confirm":
        db.clear_schedule(user_id)
        await query.edit_message_text("✅ Đã xóa toàn bộ lịch học của bạn.")
    else:
        await query.edit_message_text("❌ Đã hủy xóa lịch.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    doc = update.message.document
    
    if not doc:
        return
    
    file_name = (doc.file_name or "").lower()
    is_pdf = doc.mime_type == "application/pdf" or file_name.endswith(".pdf")
    is_text = file_name.endswith(".txt") or file_name.endswith(".csv") or file_name.endswith(".tsv")
    
    if not (is_pdf or is_text):
        await update.message.reply_text("Vui lòng gửi file PDF, TXT hoặc CSV.")
        return
    
    file_type = "PDF" if is_pdf else "CSV/TXT"
    msg = await update.message.reply_text(f"📄 Đã nhận file {file_type}. Đang phân tích...")
    
    try:
        tg_file = await doc.get_file()
        
        if is_pdf:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                await tg_file.download_to_drive(tmp.name)
                tmp_path = tmp.name
            result = parse_pdf(tmp_path)
            os.unlink(tmp_path)
            items = result.get("items", [])
            source = "pdf"
        else:
            # Text/CSV file - download as bytes and decode
            file_bytes = await tg_file.download_as_bytearray()
            text_content = file_bytes.decode('utf-8-sig')  # Handle BOM
            items = parse_registration_text(text_content)
            source = "text"
        
        if not items:
            await msg.edit_text(f"❌ Không trích xuất được lịch từ {file_type} này.")
            return
        
        pending_pdfs[user_id] = items
        
        preview = f"✅ Phân tích xong! Tìm thấy {len(items)} buổi học.\n\n"
        preview += format_schedule_list(items[:5], "📋 Xem trước:")
        if len(items) > 5:
            preview += f"\n... và {len(items) - 5} buổi khác."
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Thay thế lịch cũ", callback_data=f"{source}_replace"),
                InlineKeyboardButton("➕ Cộng thêm", callback_data=f"{source}_append")
            ],
            [InlineKeyboardButton("❌ Hủy", callback_data=f"{source}_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await msg.edit_text(preview, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        await msg.edit_text(f"❌ Lỗi khi phân tích {file_type}:\n{str(e)}")

async def handle_file_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if user_id not in pending_pdfs:
        await query.edit_message_text("❌ Phiên làm việc đã hết hạn. Vui lòng gửi file lại.")
        return
    
    items = pending_pdfs[user_id]
    action = query.data.split('_')[1]  # replace, append, cancel
    
    if action == "cancel":
        del pending_pdfs[user_id]
        await query.edit_message_text("❌ Đã hủy lưu lịch.")
        return
    
    if action == "replace":
        db.clear_schedule(user_id)
        db.add_schedule_items(user_id, items)
        del pending_pdfs[user_id]
        await query.edit_message_text(f"✅ Đã lưu lịch mới ({len(items)} buổi học).")
        return
    
    if action == "append":
        db.add_schedule_items(user_id, items)
        del pending_pdfs[user_id]
        await query.edit_message_text(f"✅ Đã cộng thêm {len(items)} buổi học vào lịch hiện tại.")
        return

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").lower().strip()
    if not text:
        return
    
    if text in ["hôm nay", "hom nay", "today"]:
        await today(update, context)
    elif text in ["ngày mai", "ngay mai", "mai", "tomorrow"]:
        await tomorrow(update, context)
    elif text in ["tuần này", "tuan nay", "tuần", "tuan", "week"]:
        await week(update, context)
    elif text in ["tiết tiếp", "tiet tiep", "next"]:
        await next_class(update, context)
    elif text.startswith("thứ") or text.startswith("thu"):
        await handle_weekday_text(update, context, text)
    else:
        await update.message.reply_text(
            "Bạn có thể hỏi: \"hôm nay\", \"ngày mai\", \"tuần này\", \"thứ 2\", \"thứ 7\", \"CN\"...\n"
            "Hoặc dùng lệnh: /today, /tomorrow, /week, /next, /lich, /help"
        )

async def handle_weekday_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user_id = update.effective_user.id
    now = __import__('datetime').datetime.now()
    
    wd_map = {
        "2": 1, "hai": 1, "thứ 2": 1, "thu 2": 1,
        "3": 2, "ba": 2, "thứ 3": 2, "thu 3": 2,
        "4": 3, "tư": 3, "tu": 3, "thứ 4": 3, "thu 4": 3,
        "5": 4, "năm": 4, "nam": 4, "thứ 5": 4, "thu 5": 4,
        "6": 5, "sáu": 5, "sau": 5, "thứ 6": 5, "thu 6": 5,
        "7": 6, "bảy": 6, "bay": 6, "thứ 7": 6, "thu 7": 6,
        "cn": 7, "chủ nhật": 7, "chu nhat": 7, "chủ nhật": 7
    }
    
    wd = None
    for key, val in wd_map.items():
        if key in text:
            wd = val
            break
    
    if not wd:
        await update.message.reply_text("Không hiểu thứ. Thử: \"thứ 2\", \"thứ 7\", \"CN\"...")
        return
    
    days_ahead = (wd - now.isoweekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    target_date = now + __import__('datetime').timedelta(days=days_ahead)
    date_str = target_date.strftime("%Y-%m-%d")
    
    items = db.get_schedule(user_id, date_str, date_str)
    day_name = WEEKDAYS_VN[wd]
    text_out = format_schedule_list(items, f"📅 {day_name} ({target_date.strftime('%d/%m')})")
    await update.message.reply_text(text_out)

def create_application() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")
    
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("tomorrow", tomorrow))
    app.add_handler(CommandHandler("week", week))
    app.add_handler(CommandHandler("next", next_class))
    app.add_handler(CommandHandler("lich", lich))
    app.add_handler(CommandHandler("delete", delete_confirm))
    
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_delete_callback, pattern="^delete_"))
    app.add_handler(CallbackQueryHandler(handle_file_callback, pattern="^(pdf|text)_(replace|append|cancel)$"))
    
    return app