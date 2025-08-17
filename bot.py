import os
import os, hashlib, sys
import logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# Увеличим детализацию для модулей, которые нам важны
logging.getLogger("telegram").setLevel(logging.DEBUG)
logging.getLogger("telegram.ext").setLevel(logging.DEBUG)
logging.getLogger("httpx").setLevel(logging.DEBUG)
logging.getLogger("urllib3").setLevel(logging.DEBUG)
# --- DEBUG: показываем в логах маску токена и его sha256 (без раскрытия самого токена) ---
TOKEN = os.environ.get("TOKEN")
if not TOKEN:
    print("DEBUG: TOKEN env variable is NOT SET")
    sys.stdout.flush()
else:
    TOKEN = TOKEN.strip()
    preview = TOKEN[:6] + "..." + TOKEN[-6:] if len(TOKEN) > 12 else TOKEN
    print(f"DEBUG: TOKEN present. len={len(TOKEN)} preview={preview}")
    sha = hashlib.sha256(TOKEN.encode()).hexdigest()
    print(f"DEBUG: TOKEN sha256={sha}")
    sys.stdout.flush()
#
import sqlite3
from pathlib import Path
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
# --- QUICK CHECK: посылаем прямой запрос к /getMe через httpx и логируем ответ ---
try:
    import httpx
    check_url = f"https://api.telegram.org/bot{TOKEN}/getMe"
    print("DEBUG: Performing direct HTTP check to Telegram getMe...")
    sys.stdout.flush()
    try:
        resp = httpx.get(check_url, timeout=15.0)
        print("DEBUG: httpx status:", resp.status_code)
        # печатаем тело (безопасно, там нет токена)
        text = resp.text
        if len(text) > 1000:
            text = text[:1000] + "...(truncated)"
        print("DEBUG: httpx body:", text)
        sys.stdout.flush()
    except Exception as e:
        print("DEBUG: httpx request failed:", repr(e))
        sys.stdout.flush()
except Exception as e:
    print("DEBUG: httpx import/exec failed:", repr(e))
    sys.stdout.flush()
#
# Путь к папке проекта
BASE_DIR = Path(__file__).parent

# Параметры: замените на свои
TOKEN = "8495777142:AAG_r2MmFsS1s7YEpOf5fXTAXWLUGMD52WU"  # Ваш токен
ADMIN_ID = 461827961  # Ваш Telegram ID

# Папка с PDF-файлами и база данных
PDF_DIR = BASE_DIR / "pdfs"
DB_PATH = BASE_DIR / "codes.db"

# Инициализация SQLite
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS codes (
        keyword TEXT PRIMARY KEY,
        filename TEXT NOT NULL
    )
    """
)
cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS subscribers (
        chat_id INTEGER PRIMARY KEY
    )
    """
)
conn.commit()

# Работа с БД
def add_code(keyword: str, filename: str) -> None:
    cursor.execute(
        "INSERT OR REPLACE INTO codes(keyword, filename) VALUES (?, ?)",
        (keyword.upper(), filename)
    )
    conn.commit()


def get_filename(keyword: str) -> str | None:
    cursor.execute(
        "SELECT filename FROM codes WHERE keyword = ?", (keyword.upper(),)
    )
    row = cursor.fetchone()
    return row[0] if row else None


def add_subscriber(chat_id: int) -> None:
    cursor.execute(
        "INSERT OR IGNORE INTO subscribers(chat_id) VALUES (?)", (chat_id,)
    )
    conn.commit()

# Обработчики
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    add_subscriber(update.effective_chat.id)
    await update.message.reply_text(
        "Привет! Напиши своё кодовое слово, и я пришлю соответствующий файл."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    help_text = (
        "Доступные команды:\n"
        "/addcode <СЛОВО> <файл.pdf> — привязать кодовое слово к файлу (только админ)\n"
        "/broadcast <текст> — отправить сообщение всем подписчикам (только админ)\n"
        "/stats — узнать число пользователей (только админ)\n"
        "/help — показать это сообщение\n\n"
        "Просто напишите ваше кодовое слово для получения PDF."
    )
    await update.message.reply_text(help_text)

async def addcode_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    if len(context.args) != 2:
        await update.message.reply_text(
            "Использование: /addcode <СЛОВО> <имя_файла.pdf>"
        )
        return
    keyword, filename = context.args
    file_path = PDF_DIR / filename
    if not file_path.exists():
        await update.message.reply_text("Файл не найден в папке pdfs.")
        return
    add_code(keyword, filename)
    await update.message.reply_text(
        f"Кодовое слово '{keyword.upper()}' привязано к '{filename}'."
    )

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    message = ' '.join(context.args)
    cursor.execute("SELECT chat_id FROM subscribers")
    for (chat_id,) in cursor.fetchall():
        try:
            await context.bot.send_message(chat_id=chat_id, text=message)
        except Exception:
            pass
    await update.message.reply_text("Рассылка завершена.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_ID:
        return
    cursor.execute("SELECT COUNT(*) FROM subscribers")
    count = cursor.fetchone()[0]
    await update.message.reply_text(f"Зарегистрировано пользователей: {count}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Игнорируем сообщения бота
    if update.message.from_user and update.message.from_user.is_bot:
        return
    add_subscriber(update.effective_chat.id)
    text = update.message.text.strip().upper()
    filename = get_filename(text)
    if filename:
        file_path = PDF_DIR / filename
        if file_path.exists():
            with open(file_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=filename,
                    caption=f"Ваш файл для кода '{text}'"
                )
        else:
            await update.message.reply_text("Файл не найден на сервере.")
    else:
        await update.message.reply_text(
            "Кодовое слово не распознано. Напиши /help для списка команд."
        )

# Точка входа
if __name__ == "__main__":
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("addcode", addcode_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("Бот запущен. Нажми Ctrl+C, чтобы остановить.")
    app.run_polling(drop_pending_updates=True, timeout=60)