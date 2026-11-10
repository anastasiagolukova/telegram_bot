from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler 
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
import os
import random
import textwrap
import sqlite3
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Загрузка токена
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# База данных
def init_db():
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            name TEXT,
            score INTEGER DEFAULT 0
        )
    """)
    # Таблица подписчиков
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscribers (
            user_id INTEGER PRIMARY KEY
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL,
            tag TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            option1 TEXT,
            option2 TEXT,
            option3 TEXT,
            option4 TEXT,
            answer TEXT
        )
    """)
    conn.commit()
    conn.close()

# Функция обновить счет (когда игрок правильно отвечает на вопросы викторины)
def update_score(user_id, name, points):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) #Выбери все из таблицы users, но только там, где колонка user_id = тому числу, которое я тебе сейчас передам (?), (user_id - само число)
    result = cursor.fetchone() # Выводит первый найденный результат в виде кортежа, например (1, 12345, "Настя", 10)

    if result:
        cursor.execute("UPDATE users SET score = score + ? WHERE user_id = ?", (points, user_id)) #Если результат найден - Обнови таблицу users, сделай так, чтобы очки стали равны старым очкам + новые (points)
    else:
        cursor.execute("INSERT INTO users (user_id, name, score) VALUES (?, ?, ?)", (user_id, name, points)) #Если игрок зашел впервые (результат не найден), Вставь новую строчку в таблицу users в эти колонки в (), значения (VALUES) - ???

    conn.commit()
    conn.close()

def get_top_players(limit=5):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()

    cursor.execute("SELECT name, score FROM users ORDER BY score DESC LIMIT ?", (limit,))
    top = cursor.fetchall()

    conn.close()
    return top

# Сохранить подписчика
def add_subscriber(user_id):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO subscribers (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def add_question(q_text, options, correct):
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO questions (question, option1, option2, option3, option4, answer)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (q_text, *options, correct))

    conn.commit()
    conn.close()

def get_random_question():
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM questions ORDER BY RANDOM() LIMIT 1")
    row = cursor.fetchone()

    conn.close()

    if row:
        return {
            "id": row[0],
            "question": row[1],
            "options": [row[2], row[3], row[4], row[5]],
            "answer": row[6]
        }
    else:
        return None


# Отправка мема дня
async def send_daily_meme():
    print("Запускается ежедневная рассылка...")
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM subscribers")
    users = cursor.fetchall()
    conn.close()

    meme_folder = "memes"
    meme_list = os.listdir(meme_folder)

    if not meme_list:
        print("Нет мемов для рассылки.")
        return
    meme_file = random.choice(meme_list)

    for (user_id,) in users:
        try:
            await app.bot.send_photo(
                chat_id=user_id,
                photo=open(os.path.join(meme_folder, meme_file), "rb"),
                caption="Вот твой мем дня!"
            )
        except Exception as e:
            print(f"Ошибка при отправке мема пользователю {user_id}: {e}") 

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    add_subscriber(user_id)
    await update.message.reply_text("Привет! Я бот: создаю мемы и провожу викторины")

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/menu - открыть меню\n/start - перезапуск\n/top - таблица лидеров")   

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    top_players = get_top_players()
    if not top_players:
        await update.message.reply_text("Пока никто не набрал очков")
        return

    text = "Топ игроков:\n\n"
    for i, (name, score) in enumerate(top_players, start=1):
        text += f"{i}. {name} - {score} очков\n"
    await update.message.reply_text(text)



async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    if "привет" in text:
        await update.message.reply_text("Привет! Рад тебя видеть") 
    else:
        await update.message.reply_text(update.message.text)

#Главное меню с кнопками
keyboard = [
    [InlineKeyboardButton("Случайный Мем", callback_data="random_meme")],
    [InlineKeyboardButton("Создать Мем", callback_data="create_meme")],
    [InlineKeyboardButton("Викторина", callback_data="quiz")],
    [InlineKeyboardButton("Топ Игроков", callback_data="top")]
]

menu = InlineKeyboardMarkup(keyboard)

# /menu
async def menu_hundler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выберидействие:", reply_markup=menu)

# Обработка кнопок
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "random_meme":
        meme_folder = "memes"
        if not os.path.exists(meme_folder) or not os.listdir(meme_folder):
            await query.edit_message_text("Ой папка с мемами пуста! Добавь туда картинки.")
            return
        
        meme_list = os.listdir(meme_folder)
        random_meme = random.choice(meme_list)
        meme_path = os.path.join(meme_folder, random_meme)

        await query.message.reply_photo(
            photo=open(meme_path, "rb"),
            caption="Вот твой случайный мем!"
        )
        await query.delete_message()
        
    elif data == "create_meme":
        await query.edit_message_text("Пришли мне фото для мема")
        context.user_data["wait_for_photo"] = True
    elif data == "quiz":
        await send_quiz(update, context)
    elif data == "top":
        top_players = get_top_players()
        if not top_players:
            await query.edit_message_text("Пока никто не набрал очков")
            return
        text = "Топ игроков:\n\n"
        for i, (name, score) in enumerate(top_players, start=1):
            text += f"{i}. {name} - {score} очков\n"
        await query.edit_message_text(text) 
    elif data.startswith("answer_"):
        await check_answer(update, context, data)
    
# Обработка фото
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("wait_for_photo"):
        return
    photo = update.message.photo[-1]
    file = await photo.get_file()
    os.makedirs("temp", exist_ok=True)
    await file.download_to_drive("temp/meme.jpg")
    context.user_data["wait_for_photo"] = False
    context.user_data["wait_for_text"] = True
    await update.message.reply_text("Теперь пришли текст для мема!")

# Обработка текста для мема
async def handle_meme_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("wait_for_text"):
        return
    text = update.message.text
    image_path = "temp/meme.jpg"
    output_path = "temp/meme_result.jpg"

    # Открываем изображение
    img = Image.open(image_path)
    draw = ImageDraw.Draw(img)

    # Загружаем шрифт
    font_path = "arial.ttf"
    try:
        font = ImageFont.truetype(font_path, size=40)
    except:
        font = ImageFont.load_default()

    # Координаты и размеры
    width, height = img.size
    margin = 20

    # 1. Разбиваем длинный текст на короткие строки (по 25 символов)
    lines = textwrap.wrap(text, width=25) 

    # 2. Задаем начальную высоту
    y_offset = height - 60

    # 3. Запускаем цикл по строкам (переворачиваем список, чтобы рисовать снизу вверх)
    for line in lines[::-1]:
        
        # Тут мы берем твою старую строчку, но вместо height-60 используем y_offset
        text_position = (margin, y_offset)
        
        outline_range = 2
        for dx in range(-outline_range, outline_range + 1):
            for dy in range(-outline_range, outline_range + 1):
                draw.text((text_position[0] + dx, text_position[1] + dy), line, font=font, fill="black")
                
        # 4. Сдвигаем курсор вверх для следующей строки
        draw.text(text_position, line, font=font, fill="white")
        y_offset -= 40

    # Сохраняем и отправляем
    img.save("temp/final_meme.jpg")

    # Сохраняем путь к мему в базу
    conn = sqlite3.connect("bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO memes (path, tag) VALUES (?, ?)", ("temp/final_meme.jpg", "user"))
    conn.commit()
    conn.close()
    
    await update.message.reply_photo(photo=open("temp/final_meme.jpg", "rb"))
    context.user_data["wait_for_text"] = False

# Викторина
async def send_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    q = get_random_question()

    if not q:
        await query.edit_message_text("Вопросов пока нет в базе.")
        return
    
    context.user_data["correct_answer"] = q["answer"]

    buttons = [
        InlineKeyboardButton(opt, callback_data=f"answer_{opt}")
        for opt in q["options"]
    ]
    markup = InlineKeyboardMarkup.from_column(buttons)

    await query.message.reply_text(q["question"], reply_markup=markup)

# Проверка ответа
async def check_answer(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str):
    query = update.callback_query
    selected = data.replace("answer_", "")
    correct = context.user_data.get("correct_answer")

    if selected == correct:
        await query.edit_message_text(f"Верно! Это {correct}.")
        user_id = query.from_user.id
        user_name = query.from_user.first_name
        update_score(user_id, user_name, 1)
    else:
        await query.edit_message_text(f"Неверно. Правильный ответ: {correct}.")
    await query.message.reply_text("Хочешь еще вопрос? Нажми /menu и выбери 'Викторина'!")

# Запуск приложения
init_db()

#Блок для добавления вопросов в викторину
add_question("Что делает print?", 
             ["Печатает текст", "Удаляет файл", "Очищает память", "Закрывает окно"], 
             "Печатает текст")

add_question("Какой язык мы учим?", 
             ["Java", "Python", "C++", "PHP"], 
             "Python")

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("help", help))
app.add_handler(CommandHandler("menu", menu_hundler))
app.add_handler(CommandHandler("top", top))
app.add_handler(CallbackQueryHandler(handle_buttons))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_meme_text))
app.add_handler(MessageHandler(filters.TEXT, echo))

app.run_polling()








