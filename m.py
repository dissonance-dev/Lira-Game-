import uuid
import datetime
import asyncio
import random
import sqlite3
import pytz
import warnings
from datetime import datetime # это тоже понадобится для команды "время"
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage


warnings.filterwarnings("ignore", category=UserWarning, module='pkg_resources')

# --- КОНФИГУРАЦИЯ ---
TOKEN = "7913689244:AAGFfGKzRSCu7Jbfh7sY4w2KCJqROUNROYs"
ADMIN_ID = [8049948727, 377252380]
X50_CHAT_ID = -1003855200325

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- БАЗА ДАННЫХ ---
conn = sqlite3.connect("lira_ultimate_v2.db", check_same_thread=False)
cur = conn.cursor()


# Таблица чатов (для рассылки чатам)
cur.execute('''
CREATE TABLE IF NOT EXISTS chats (
    chat_id INTEGER PRIMARY KEY,
    name TEXT
)
''')

conn.commit()



# 1. Создаем основную таблицу пользователей
cur.execute('''CREATE TABLE IF NOT EXISTS users (
    uid INTEGER PRIMARY KEY, 
    name TEXT, 
    bal INTEGER DEFAULT 10000, 
    played INTEGER DEFAULT 0, 
    won INTEGER DEFAULT 0, 
    daily INTEGER DEFAULT 0,
    reg TEXT, 
    bonus TEXT, 
    last_x50_bet TEXT,
    level INTEGER DEFAULT 1,      -- Добавлено для уровней
    used_limit INTEGER DEFAULT 0   -- Добавлено для суточных лимитов
)''')

# 2. ПРОВЕРКА И ДОБАВЛЕНИЕ КОЛОНОК (если таблица уже была создана ранее без них)
# Этот блок исправит ошибки "no such column"
try:
    cur.execute("ALTER TABLE users ADD COLUMN level INTEGER DEFAULT 1")
except: pass

try:
    cur.execute("ALTER TABLE users ADD COLUMN used_limit INTEGER DEFAULT 0")
except: pass

# 3. Таблица админов
cur.execute('''CREATE TABLE IF NOT EXISTS admins (uid INTEGER PRIMARY KEY)''')

# 4. Остальные таблицы
cur.execute('''CREATE TABLE IF NOT EXISTS promo (code TEXT PRIMARY KEY, amount INTEGER, uses INTEGER)''')
cur.execute('''CREATE TABLE IF NOT EXISTS promo_history (uid INTEGER, code TEXT)''')
cur.execute('''CREATE TABLE IF NOT EXISTS x50_history (id INTEGER PRIMARY KEY AUTOINCREMENT, res TEXT)''')

# 5. Казна
cur.execute('''CREATE TABLE IF NOT EXISTS treasury (
    id INTEGER PRIMARY KEY, 
    balance INTEGER DEFAULT 0, 
    reward_per_user INTEGER DEFAULT 100)''')
cur.execute("INSERT OR IGNORE INTO treasury (id, balance, reward_per_user) VALUES (1, 0, 100)")

# 6. История игр
cur.execute("""
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid INTEGER,
    game_name TEXT,
    bet INTEGER,
    win_amount INTEGER,
    coef REAL,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# --- ШАГ 1: Создание таблицы (обязательно в начале) ---
cur.execute("""
CREATE TABLE IF NOT EXISTS game_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    user_name TEXT,
    game_name TEXT,
    coef REAL,
    amount INTEGER,
    is_win INTEGER,
    time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

cur.execute("""
CREATE TABLE IF NOT EXISTS game_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    user_id INTEGER,
    game_name TEXT,
    result TEXT, -- "win" или "lose"
    amount INTEGER,
    timestamp INTEGER
)
""")
conn.commit() #stata

# --- ШАГ 2: Сама функция записи (Она должна быть ВЫШЕ всех игр) ---
def log_game_db(uid, name, game, coef, amount, is_win):
    try:
        cur.execute(
            "INSERT INTO game_logs (user_id, user_name, game_name, coef, amount, is_win) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, str(name), game, float(coef), int(amount), int(is_win))
        )
        conn.commit()
    except Exception as e:
        print(f"Ошибка логирования в БД: {e}")

cur.execute("""
CREATE TABLE IF NOT EXISTS joined_users (
    chat_id INTEGER,
    user_id INTEGER,
    PRIMARY KEY (chat_id, user_id)
)
""")
conn.commit()

# Функция записи логов (ОБЯЗАТЕЛЬНО ВЫШЕ ИГР)
def log_game_db(uid, name, game, coef, amount, is_win):
    try:
        cur.execute(
            "INSERT INTO game_logs (user_id, user_name, game_name, coef, amount, is_win) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, str(name), game, float(coef), int(amount), int(is_win))
        )
        conn.commit()
    except Exception as e:
        print(f"Ошибка логирования: {e}")


try:
    cur.execute("ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0")
    conn.commit()
except: pass
# --- ЭТОТ БЛОК ИСПРАВИТ ОШИБКУ ---
try:
    cur.execute("ALTER TABLE users ADD COLUMN username TEXT")
    conn.commit()
    print("Колонка username успешно добавлена!")
except Exception as e:
    print(f"Заметка: {e}") # Если она уже есть, просто пойдет дальше
# ---------------------------------

# Добавляем новые колонки
for col in [
    ("bank", "INTEGER DEFAULT 0"), 
    ("reputation", "INTEGER DEFAULT 0"), 
    ("bio", "TEXT DEFAULT 'Пока пусто'"),
    ("hide_bal", "INTEGER DEFAULT 0"),  # 0 - открыт, 1 - скрыт
    ("hide_bank", "INTEGER DEFAULT 0")  # 0 - открыт, 1 - скрыт
]:
    try:
        cur.execute(f"ALTER TABLE users ADD COLUMN {col[0]} {col[1]}")
    except: pass
conn.commit()

cur.execute('''CREATE TABLE IF NOT EXISTS logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uid INTEGER,
    game TEXT,
    amount INTEGER,
    result TEXT,
    date DATETIME DEFAULT CURRENT_TIMESTAMP
)''')
conn.commit()


# Удаляем старую таблицу (ВНИМАНИЕ: старые логи удалятся)
cur.execute("DROP TABLE IF EXISTS logs")

import json
import time
import random
import asyncio
from aiogram import types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ====================== БАЗА ДАННЫХ ======================
# Создаём таблицу активных игр (для Хило, X50 и др.)
cur.execute("""
CREATE TABLE IF NOT EXISTS active_games (
    user_id INTEGER PRIMARY KEY,
    game_type TEXT NOT NULL,
    game_state TEXT NOT NULL,
    updated_at INTEGER NOT NULL
)
""")
conn.commit()

# Сохраняем активную игру
def save_active_game(user_id, game_type, game_dict):
    cur.execute(
        """
        INSERT INTO active_games (user_id, game_type, game_state, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            game_type = excluded.game_type,
            game_state = excluded.game_state,
            updated_at = excluded.updated_at
        """,
        (user_id, game_type, json.dumps(game_dict), int(time.time()))
    )
    conn.commit()

# Загружаем все активные игры определённого типа
def load_active_games(game_type):
    cur.execute("SELECT user_id, game_state FROM active_games WHERE game_type = ?", (game_type,))
    rows = cur.fetchall()
    return {row[0]: json.loads(row[1]) for row in rows}

# Удаляем игру после окончания
def delete_active_game(user_id):
    cur.execute("DELETE FROM active_games WHERE user_id = ?", (user_id,))
    conn.commit()

# ====================== ХИЛО ======================
active_hilo_games = load_active_games("hilo")
hl_cooldowns = {}



# --- СОСТОЯНИЯ ---
class AdminStates(StatesGroup):
    # Для выдачи
    give_id = State()
    give_amount = State()
    # Для промо
    promo_name = State()
    promo_sum = State()
    promo_uses = State()
    # Для рассылки
    mailing_text = State()
    # Для ФК и Викторины
    fast_amount = State()
    vik_amount = State()
    vik_question = State()
    vik_answer = State()
# ... твои старые состояния ...
    user_control = State() # Для ввода ID пользователя

from aiogram import types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import asyncio
import re

# ===== FSM для рассылки =====
from aiogram.fsm.state import StatesGroup, State

class AdminMailStates(StatesGroup):
    waiting_text = State()
    waiting_url_choice = State()
    waiting_url_link = State()
    waiting_url_name = State()
    waiting_type_choice = State()
# ====== Автосохранение чатов ======
@dp.message()
async def save_chat(message: types.Message):
    chat_id = message.chat.id
    chat_name = message.chat.title or message.chat.full_name or "Без названия"
    cur.execute("INSERT OR IGNORE INTO chats(chat_id, name) VALUES (?, ?)", (chat_id, chat_name))
    conn.commit()

class SupportStates(StatesGroup):
    waiting_for_report = State()  # Ожидание обращения от юзера
    waiting_for_admin_answer = State()  # Ожидание текста ответа от админа


# Убедись, что этот класс добавлен в твои состояния
class VilinStates(StatesGroup):
    confirm = State()

class GameStates(StatesGroup):
    toad = State()   # Состояние для Жабы
    mines = State()  # Состояние для Мин
    tower = State()  # <--- ДОБАВЬ ЭТУ СТРОКУ
    # ... другие твои состояния

class CreateCheck(StatesGroup):
    amount = State()
    activations = State()
    password = State()    

from aiogram.fsm.state import State, StatesGroup


#m
from aiogram import BaseMiddleware
from aiogram.types import Message
from typing import Callable, Dict, Any, Awaitable

class BanMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # 1. Проверка на наличие пользователя в сообщении
        if not event.from_user:
            return await handler(event, data)

        # 2. ИСПРАВЛЕННЫЙ ЗАПРОС (Проверь название колонки в БД!)
        # Попробуй заменить "uid" на "user_id", если ошибка останется
        try:
            cur.execute("SELECT banned FROM users WHERE uid = ?", (event.from_user.id,))
            res = cur.fetchone()
        except sqlite3.OperationalError:
            # Если uid не найден, пробуем через user_id
            cur.execute("SELECT banned FROM users WHERE user_id = ?", (event.from_user.id,))
            res = cur.fetchone()
        
        if res and res[0] == 1:
            return await event.answer(
                "❌ <b>Доступ заблокирован!</b>\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\nВы были забанены за нарушение правил.",
                parse_mode="HTML"
            )
        
        return await handler(event, data)

#cd
import asyncio
import random
import sqlite3
import time
from aiogram import types, F, BaseMiddleware, Dispatcher
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

# --- УЛУЧШЕННЫЙ КД (ТОЛЬКО ДЛЯ КОМАНД БОТА) ---
class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, time_limit: int = 2):
        self.last_messages = {}
        self.limit = time_limit
        
        # Твой список команд (очищенный и удобный для чтения)
        commands = [
    'х50',
    'мины',
    'башня',
    'хл',
    'охота',
    'флип',
    'баскетбол',
    'футбол',
    'боулинг',
    'спин',
    'рул',
    'джекпот',
    'оверго',
    'пират',
    'колесо',
    'вилин',
    'бж',
    'мосты',
    'б',
    'банк',
    'дать',
    'топ',
    'чд',
    'казна',
    'профиль',
    'дроп',
    'лог',
    'скрыть',
    'время',

    '👤 профиль',
    '🎁 бонус',
    '🏆 чемпионы дня',
    '📍 помощь',
    '➕ добавить',

    '/start',
    'го',
    'бот',
    'шар',
    'шанс',
    'помощь',
    'промо'
]
        # Сохраняем всё в нижнем регистре для точного сравнения
        self.game_commands = [c.lower() for c in commands]

    async def __call__(self, handler, event, data):
        if not isinstance(event, types.Message) or not event.text:
            return await handler(event, data)

        uid = event.from_user.id
        text = event.text.lower()
        
        # Проверяем, начинается ли сообщение с какой-либо команды из списка
        is_command = any(text.startswith(cmd) for cmd in self.game_commands)

        # Если это НЕ команда из списка — пропускаем без КД
        if not is_command:
            return await handler(event, data)

        # Если это команда — проверяем время
        curr = time.time()
        if uid in self.last_messages:
            if curr - self.last_messages[uid] < self.limit:
                return # Игнорируем спам

        self.last_messages[uid] = curr
        return await handler(event, data)

#
def get_game_stats(cursor, chat_id, game_name):
    cursor.execute(
        """
        SELECT 
            COUNT(*),
            SUM(win),
            SUM(amount)
        FROM game_logs
        WHERE chat_id=? AND game_name=?
        """,
        (chat_id, game_name)
    )
    result = cursor.fetchone()
    total_games = result[0] or 0
    total_wins = result[1] or 0
    total_amount = result[2] or 0
    win_rate = round((total_wins / total_games) * 100, 2) if total_games > 0 else 0
    return total_games, total_wins, win_rate, total_amount

# Функция логирования (должна быть выше игр)
def log_game_db(uid, name, game, coef, amount, is_win):
    try:
        cur.execute(
            "INSERT INTO game_logs (user_id, user_name, game_name, coef, amount, is_win) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, str(name), game, float(coef), int(amount), int(is_win))
        )
        conn.commit()
    except Exception as e:
        print(f"Ошибка логирования: {e}")

# --- ИНИЦИАЛИЗАЦИЯ ДИСПЕТЧЕРА ---
dp = Dispatcher()
# Включаем КД на все сообщения (1 секунда)
dp.message.middleware(ThrottlingMiddleware(time_limit=2))

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_u(uid, name, username=None):
    cur.execute("SELECT * FROM users WHERE uid = ?", (uid,))
    res = cur.fetchone()
    if not res:
        from datetime import datetime
        reg_date = datetime.now().strftime("%d.%m.%Y")
        
        # Если юзернейма нет (бывает в ЛС), ставим "None"
        uname = username.replace("@", "") if username else "None"
        
        # ВНИМАНИЕ: Убедись, что количество колонок (uid, name...) 
        # совпадает с количеством знаков ? (их тут 6)
        try:
            cur.execute("""INSERT INTO users (uid, name, reg, level, used_limit, username) 
                           VALUES (?, ?, ?, ?, ?, ?)""", 
                        (uid, name, reg_date, 1, 0, uname))
            conn.commit()
        except Exception as e:
            print(f"Ошибка при регистрации: {e}")
            
        cur.execute("SELECT * FROM users WHERE uid = ?", (uid,))
        return cur.fetchone()
    return res


import sqlite3
import time
import re
from aiogram import types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- ФУНКЦИЯ РАБОТЫ С БАЗОЙ ДАННЫХ ---
def db_query(query, params=(), commit=False, fetchone=False):
    conn = sqlite3.connect("lira_ultimate_v2.db")
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        if commit:
            conn.commit()
        if fetchone:
            return cur.fetchone()
        return cur.fetchall()
    finally:
        conn.close()

# Создание таблицы казны, если её нет
db_query("""
CREATE TABLE IF NOT EXISTS kazna (
    chat_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    reward INTEGER DEFAULT 0
)""", commit=True)


#rtp
def is_win_allowed(user_id, bet_amount):
    """
    Умный RTP: возвращает True, если выигрыш разрешен, 
    и False, если система решила слить игрока.
    """
    # 1. Получаем баланс игрока
    cur.execute("SELECT balance FROM users WHERE uid = ?", (user_id,))
    res = cur.fetchone()
    balance = res[0] if res else 0

    # 2. Базовый шанс (в процентах). 100 - всегда победа, 0 - всегда проигрыш.
    # Для честной игры обычно ставят 45-48%
    chance = 47 

    # --- ЛОГИКА ПОДКУРУТКИ ---
    
    # Если баланс игрока больше 5 млн, шанс падает
    if balance > 5000000:
        chance -= 10 
    
    # Если баланс больше 20 млн, шанс падает до минимума
    if balance > 20000000:
        chance -= 20

    # Если ставка слишком большая (например, > 1 млн)
    if bet_amount > 1000000:
        chance -= 15

    # Финальный расчет
    roll = random.randint(1, 100)
    
    # Игрок побеждает только если roll попал в диапазон шанса
    return roll <= max(chance, 5) # Шанс не может быть ниже 5%


# Функции для казны
def get_kazna(chat_id):
    res = db_query("SELECT balance, reward FROM kazna WHERE chat_id = ?", (chat_id,), fetchone=True)
    if not res:
        db_query("INSERT INTO kazna (chat_id, balance, reward) VALUES (?, 0, 0)", (chat_id,), commit=True)
        return (0, 0)
    return res

def update_kazna_balance(chat_id, amount):
    db_query("UPDATE kazna SET balance = balance + ? WHERE chat_id = ?", (amount, chat_id), commit=True)

def set_kazna_reward(chat_id, amount):
    db_query("UPDATE kazna SET reward = ? WHERE chat_id = ?", (amount, chat_id), commit=True)
    
def b_num(number):
    """Превращает число в жирный текст с разделителями"""
    return f"<b>{number:,}</b>"

def upd_bal(uid, am):
    cur.execute("UPDATE users SET bal = bal + ?, daily = daily + ? WHERE uid = ?", (am, am if am > 0 else 0, uid))
    conn.commit()

def is_admin(uid):
    cur.execute("SELECT uid FROM admins WHERE uid = ?", (uid,))
    return cur.fetchone() is not None

def get_all_admins():
    cur.execute("SELECT uid FROM admins")
    return [row[0] for row in cur.fetchall()]

def log_game(uid, game_name, bet, win_amount, coef):
    conn = sqlite3.connect("lira_ultimate_v2.db")
    cur = conn.cursor()
    cur.execute("INSERT INTO history (uid, game_name, bet, win_amount, coef) VALUES (?, ?, ?, ?, ?)",
                (uid, game_name, bet, win_amount, coef))
    conn.commit()
    conn.close()

def parse_bet(val, user_bal):
    val = str(val).lower().strip().replace("кк", "000000").replace("к", "000")
    if val == "все": return user_bal
    try:
        res = int(val)
        return res if 100 <= res <= user_bal else -1
    except: return -2

def get_link(u):
    return f"[{u[1]}](tg://user?id={u[0]})"

def add_log(uid, l_type, action, amount, result):
    import datetime
    now = datetime.datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    # Записываем только ОДНО значение amount
    cur.execute("INSERT INTO logs (uid, type, action, amount, result, date) VALUES (?, ?, ?, ?, ?, ?)",
                (uid, l_type, action, int(amount), result, now))
    conn.commit()

# --- КЛАВИАТУРЫ ---
def main_kb():
    kb = ReplyKeyboardBuilder()
    kb.row(types.KeyboardButton(text="👤 Профиль"), types.KeyboardButton(text="🎁 Бонус"))
    kb.row(types.KeyboardButton(text="🏆 Чемпионы дня"))
    kb.row(types.KeyboardButton(text="📍 Помощь"), types.KeyboardButton(text="➕ Добавить"))
    return kb.as_markup(resize_keyboard=True)

#
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import types

# --- КОМАНДА СТАРТ (ТОЛЬКО В ЛС) ---
@dp.message(Command("start"), F.chat.type == "private")
async def start(m: types.Message):
    # регистрация пользователя
    get_u(m.from_user.id, m.from_user.full_name)

    text = (
        "✨ <b>Добро пожаловать в LIRA</b>\n\n"
        "🎮 Здесь ты можешь играть, рисковать и\n"
        "зарабатывать игровую валюту — лиры.\n\n"
        "💰 Стартовый баланс уже зачислен.\n"
        "Используй его и испытывай удачу!\n\n"
        "⚙️ Бот поддерживает игры как в ЛС,\n"
        "так и в групповых чатах.\n\n"
        "📜 Запуская бота, ты принимаешь\n"
        "пользовательское соглашение.\n\n"
        "🖤 <i>Удачной игры!</i>"
    )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📜 Пользовательское соглашение",
                    url="https://telegra.ph/LiraGame-Bot-01-15"
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ Добавить в чат",
                    url="https://t.me/LiraGame_Bot?startgroup=0"
                )
            ]
        ]
    )

    await m.answer(
        text,
        reply_markup=kb,
        parse_mode="HTML"
    )


# --- НИКИ И БАЛАНС ---
@dp.message(F.text.lower().startswith("+ник "))
async def set_new_nick(m: types.Message):
    new_nick = m.text[5:].strip().replace("[", "").replace("]", "")
    if len(new_nick) > 20 or len(new_nick) < 2:
        return await m.reply("❌ Ник от 2 до 20 символов!")
    cur.execute("UPDATE users SET name = ? WHERE uid = ?", (new_nick, m.from_user.id))
    conn.commit()
    await m.reply(f"✅ Ваш ник изменен на: {get_link([m.from_user.id, new_nick])}", parse_mode="Markdown")

@dp.message(F.text.lower() == "ник")
async def show_nick(m: types.Message):
    target = m.reply_to_message.from_user if m.reply_to_message else m.from_user
    u = get_u(target.id, target.full_name)
    await m.reply(f"👤 Ник: {get_link(u)}", parse_mode="Markdown")

@dp.message(F.text.lower() == "б")
async def show_my_balance(m: types.Message):
    # Пытаемся получить баланс
    cur.execute("SELECT bal FROM users WHERE uid = ?", (m.from_user.id,))
    res = cur.fetchone()
    
    if res is None:
        # Если пользователя нет, регистрируем его «на лету»
        # Передаем id, имя и юзернейм
        u = get_u(m.from_user.id, m.from_user.full_name, m.from_user.username)
        balance = u[2] # 10000 по умолчанию
    else:
        balance = res[0]

    # Отправляем баланс жирным через HTML
    await m.reply(f"💸 Баланс: <b>{balance:,}</b> лир", parse_mode="HTML")
    
# --- ПЕРЕДАЧА И ВЫДАЧА ---
@dp.message(F.text.lower().startswith("дать "))
async def transfer(m: types.Message):
    if not m.reply_to_message:
        return await m.reply("❌ <b>Ответь на сообщение игрока</b>", parse_mode="HTML")

    u = get_u(m.from_user.id, m.from_user.full_name)
    t_raw = m.reply_to_message.from_user
    t = get_u(t_raw.id, t_raw.full_name)

    if t_raw.is_bot or t[0] == u[0]:
        return await m.reply("❌ <b>Боту нельзя передать</b>", parse_mode="HTML")

    try:
        bet = parse_bet(m.text.split()[1], u[2])
    except:
        return await m.reply("❌ <b>Укажи сумму</b>", parse_mode="HTML")

    if bet < 100:
        return await m.reply("❌ <b>Минимум — 100 лир</b>", parse_mode="HTML")

    cur.execute("SELECT level, used_limit, bal FROM users WHERE uid = ?", (u[0],))
    row = cur.fetchone()
    if not row:
        return await m.reply("❌ <b>Ошибка профиля</b>", parse_mode="HTML")

    u_lv, u_used, u_bal = row

    if bet > u_bal:
        return await m.reply("❌ <b>Недостаточно лир</b>", parse_mode="HTML")

    limit = LEVELS[u_lv]["limit"]

    if u_used + bet > limit:
        remaining_limit = max(0, limit - u_used)
        return await m.reply(
            "⚠️ <b>Лимит исчерпан</b>\n"
            f"Осталось: <b>{remaining_limit:,}</b>\n\n"
            "━━━━━━━━━━━━━━\n"
            "🕛 Лимиты будут обнуляться по времени <b>Almaty / Astana</b> в <b>00:00</b>\n"
            "⬆️ Повысить лимит / уровень — <b>куровень</b>",
            parse_mode="HTML"
        )

    # --- ЕСЛИ ЛИМИТ НЕ ПРЕВЫШЕН, ТУТ ИДЕТ ПЕРЕДАЧА ---
    upd_bal(u[0], -bet)
    upd_bal(t[0], bet)

    cur.execute(
        "UPDATE users SET used_limit = used_limit + ? WHERE uid = ?",
        (bet, u[0])
    )
    conn.commit()

    await m.reply(
        f"✅ <b>Перевод выполнен</b>\n"
        f"💸 Вы передали <b>{bet:,}</b> лир игроку {get_mention(t[0], t_raw.full_name)}",
        parse_mode="HTML"
    )
    
# --- 1. КОМАНДА ВЫДАТЬ (через реплай) ---
@dp.message(F.text.lower().startswith("выдать "))
async def adm_give_fast(m: types.Message):
    # Проверка доступа
    if m.from_user.id not in ADMIN_ID: 
        return 
    
    # Проверка на наличие реплая
    if not m.reply_to_message: 
        return await m.reply("❌ <b>Ответьте на сообщение игрока (реплай)!</b>", parse_mode="HTML")
    
    args = m.text.split()
    if len(args) < 2:
        return await m.reply("❌ <b>Введите сумму!</b>\nПример: <code>выдать 10к</code>", parse_mode="HTML")

    # 1. Пробуем получить сумму
    try:
        summ_raw = args[1].lower().replace("к", "000").replace("k", "000").replace("м", "000000")
        summ = int(summ_raw)
    except ValueError:
        return await m.reply("❌ <b>Ошибка!</b> Введите сумму числом.\nПример: <code>выдать 50к</code>", parse_mode="HTML")

    # 2. Если сумма верна, выполняем выдачу
    target_id = m.reply_to_message.from_user.id
    target_name = m.reply_to_message.from_user.first_name

    upd_bal(target_id, summ)

    # Красивый текст с использованием цитаты (blockquote)
    report = (
        f"👑 <b>АДМИНИСТРАЦИЯ</b>\n\n"
        f"<blockquote>"
        f"💰 Выдано: <b>{summ:,}</b> лир\n"
        f"👤 Получатель: {get_mention(target_id, target_name)}\n"
        f"✅ Транзакция завершена успешно!"
        f"</blockquote>"
    )

    await m.reply(report, parse_mode="HTML")
    
import random
import asyncio
import time
import json
import os
from aiogram import F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

# -------------------- Настройки --------------------
import random
import time
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================= СЛОВАРИ =================
active_mines_games = {}   # Игры в памяти
mines_cooldowns = {}      # КД на ходы
mines_game_counter = 1    # Счётчик игр

# ================= БАЗА =================
cur.execute("""
CREATE TABLE IF NOT EXISTS mines_games (
    user_id INTEGER PRIMARY KEY,
    bet INTEGER,
    mines_cnt INTEGER,
    field TEXT,
    opened INTEGER,
    opened_indices TEXT,
    coef REAL,
    last_index INTEGER,
    finished INTEGER,
    user_name TEXT,
    game_id INTEGER
)
""")
conn.commit()

# --- ВОССТАНОВЛЕНИЕ ИГР ПРИ СТАРТЕ ---
cur.execute("SELECT * FROM mines_games WHERE finished = 0")
for row in cur.fetchall():
    user_id = row[0]
    active_mines_games[user_id] = {
        "bet": row[1],
        "mines_cnt": row[2],
        "field": list(map(int, row[3].split(","))),
        "opened": row[4],
        "opened_indices": list(map(int, row[5].split(","))) if row[5] else [],
        "coef": row[6],
        "last_index": row[7],
        "finished": False,
        "user_name": row[9],
        "game_id": row[10]
    }

# ================= ФУНКЦИИ =================
def get_mines_coef(mines_count: int, opened: int) -> float:
    total = 25
    if mines_count >= total or opened <= 0: return 1.0
    safe = total - mines_count
    prob = 1.0
    for i in range(opened):
        prob *= (safe - i) / (total - i)
    coef = (1.0 / prob) * 0.96
    return round(coef, 2)

def update_mines_db(user_id, game):
    cur.execute("""
        INSERT OR REPLACE INTO mines_games 
        (user_id, bet, mines_cnt, field, opened, opened_indices, coef, last_index, finished, user_name, game_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        game['bet'],
        game['mines_cnt'],
        ",".join(map(str, game['field'])),
        game['opened'],
        ",".join(map(str, game['opened_indices'])),
        game['coef'],
        game['last_index'],
        int(game.get('finished', 0)),
        game['user_name'],
        game['game_id']
    ))
    conn.commit()

# ================= ОТРИСОВКА =================
async def mines_render(m, d, finished=False, is_win=False, prefix=""):
    kb = InlineKeyboardBuilder()
    for i in range(25):
        if finished:
            if d['field'][i] == 1:
                txt = "💥" if i == d['last_index'] and not is_win else "💣"
            else:
                txt = "💎" if i in d['opened_indices'] else "☁️"
            kb.button(text=txt, callback_data="none")
        else:
            txt = "💎" if i in d['opened_indices'] else "❓"
            kb.button(text=txt, callback_data=f"mine_step_{i}")
    kb.adjust(5)
    if not finished:
        kb.row(types.InlineKeyboardButton(text="🎯 Автовыбор", callback_data="mine_auto"))
        if d['opened'] > 0:
            kb.row(types.InlineKeyboardButton(
                text=f"💰 ЗАБРАТЬ {int(d['bet'] * d['coef']):,} лир", 
                callback_data="mine_stop"
            ))

    if finished:
        header = f"🎉 <b>ИГРА #{d['game_id']} ЗАВЕРШЕНА</b>" if is_win else f"💀 <b>ИГРА #{d['game_id']} — ВЗРЫВ</b>"
        status = f"✅ Выигрыш: <b>{int(d['bet'] * d['coef']):,}</b> лир" if is_win else f"📉 Убыток: <b>{d['bet']:,}</b> лир"
    else:
        header = f"✨ <b>ИГРА «МИНЫ» #{d['game_id']}</b>"
        status = f"📈 Множитель: <b>x{d['coef']}</b>"

    text = (
        f"{prefix}"
        f"{header}\n\n"
        f"<blockquote>"
        f"👤 Игрок: <b>{d['user_name']}</b>\n"
        f"💵 Ставка: <b>{d['bet']:,}</b>\n"
        f"{status}\n"
        f"━━━━━━━━━━━━━━\n"
        f"💣 Мины: <b>{d['mines_cnt']}</b> | 💎 Открыто: <b>{d['opened']}</b>"
        f"</blockquote>"
    )

    if hasattr(m, "message"):
        try: await m.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        except: pass
    else:
        await m.reply(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# ================= СТАРТ ИГРЫ =================
@dp.message(F.text.lower().startswith("мины"))
async def mines_start(m: types.Message):
    global mines_game_counter
    user_id = m.from_user.id

    if user_id in active_mines_games and not active_mines_games[user_id].get("finished", False):
        game = active_mines_games[user_id]
        await mines_render(m, game, prefix="#Активная_игра\n")
        return

    u = get_u(user_id, m.from_user.full_name)
    args = m.text.split()
    try:
        bet = parse_bet(args[1], u[2])
        mines_cnt = int(args[2]) if len(args) > 2 else 3
    except:
        return await m.reply("📖 <b>Формат:</b> <code>мины [ставка] [мины]</code>", parse_mode="HTML")

    if bet < 100: return await m.reply("❌ Ставка от 100 лир!")
    if not (1 <= mines_cnt <= 24): return await m.reply("❌ Мин может быть от 1 до 24!")
    if u[2] < bet: return await m.reply("❌ Недостаточно лир!")

    field = [1] * mines_cnt + [0] * (25 - mines_cnt)
    random.shuffle(field)
    upd_bal(user_id, -bet)

    current_game_id = mines_game_counter
    mines_game_counter += 1

    game = {
        "bet": bet,
        "mines_cnt": mines_cnt,
        "field": field,
        "opened": 0,
        "opened_indices": [],
        "coef": 1.0,
        "last_index": -1,
        "finished": False,
        "user_name": m.from_user.first_name,
        "game_id": current_game_id
    }

    active_mines_games[user_id] = game
    update_mines_db(user_id, game)
    await mines_render(m, game)

# ================= ОБРАБОТЧИК КНОПОК =================
@dp.callback_query(F.data.startswith("mine_step_"))
@dp.callback_query(F.data == "mine_auto")
async def mine_logic(call: types.CallbackQuery):
    user_id = call.from_user.id
    now = time.time()
    if user_id in mines_cooldowns and now - mines_cooldowns[user_id] < 1.5:
        return await call.answer("⏳ Не спеши!", show_alert=False)
    mines_cooldowns[user_id] = now

    if user_id not in active_mines_games: return await call.answer()
    d = active_mines_games[user_id]

    if call.data == "mine_auto":
        available = [i for i in range(25) if i not in d['opened_indices']]
        idx = random.choice(available)
    else:
        idx = int(call.data.split("_")[2])

    if idx in d['opened_indices']: return await call.answer()
    d['last_index'] = idx

    if d['field'][idx] == 1:
        await mines_render(call, d, finished=True, is_win=False)
        d['finished'] = True
        update_mines_db(user_id, d)
        active_mines_games.pop(user_id, None)
    else:
        d['opened'] += 1
        d['opened_indices'].append(idx)
        d['coef'] = get_mines_coef(d['mines_cnt'], d['opened'])
        update_mines_db(user_id, d)
        if d['opened'] == (25 - d['mines_cnt']):
            upd_bal(user_id, int(d['bet'] * d['coef']))
            await mines_render(call, d, finished=True, is_win=True)
            d['finished'] = True
            update_mines_db(user_id, d)
            active_mines_games.pop(user_id, None)
        else:
            await mines_render(call, d)
    await call.answer()

@dp.callback_query(F.data == "mine_stop")
async def mine_stop(call: types.CallbackQuery):
    user_id = call.from_user.id
    if user_id not in active_mines_games: return await call.answer()
    d = active_mines_games[user_id]

    win_sum = int(d['bet'] * d['coef'])
    upd_bal(user_id, win_sum)
    log_game_db(user_id, call.from_user.first_name, "Mines", d['coef'], win_sum, 1)

    d['finished'] = True
    update_mines_db(user_id, d)
    active_mines_games.pop(user_id, None)
    await mines_render(call, d, finished=True, is_win=True)
    await call.answer("💰 Выигрыш зачислен!")


    
import random
import time
import asyncio
from aiogram import types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder



CARDS_VALUES = {
    'A': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7,
    '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13
}
CARDS_NAMES = list(CARDS_VALUES.keys())
CARD_SUITS = ['♥️', '♦️', '♠️', '♣️']

async def hl_render_game(m, game, finished=False, is_reminder=False, prefix=""):
    card = game['last']
    suit = game['suit']
    coef = game['coef']
    bet = game['bet']
    val = CARDS_VALUES[card]
    user_name = game.get('user_name', 'Игрок')

    prob_up = (13 - val + 0.5) / 13
    prob_down = (val - 0.5) / 13
    step_up = max(round((1 / prob_up) * 0.92, 2), 1.1)
    step_down = max(round((1 / prob_down) * 0.92, 2), 1.1)
    k_same = 11.50

    kb = InlineKeyboardBuilder()
    if not finished:
        if card == 'K':
            kb.row(
                types.InlineKeyboardButton(text=f"⏺️ Та же [x{round(coef * k_same,2)}]", callback_data=f"hl:same:{k_same}"),
                types.InlineKeyboardButton(text=f"⬇️ Ниже [x{round(coef * step_down,2)}]", callback_data=f"hl:down:{step_down}")
            )
        elif card == 'A':
            kb.row(
                types.InlineKeyboardButton(text=f"⬆️ Выше [x{round(coef * step_up,2)}]", callback_data=f"hl:up:{step_up}"),
                types.InlineKeyboardButton(text=f"⏺️ Та же [x{round(coef * k_same,2)}]", callback_data=f"hl:same:{k_same}")
            )
        else:
            kb.row(
                types.InlineKeyboardButton(text=f"⬆️ Выше [x{round(coef * step_up,2)}]", callback_data=f"hl:up:{step_up}"),
                types.InlineKeyboardButton(text=f"⬇️ Ниже [x{round(coef * step_down,2)}]", callback_data=f"hl:down:{step_down}")
            )
        if coef > 1.0:
            kb.row(types.InlineKeyboardButton(text=f"💰 ЗАБРАТЬ {int(bet*coef):,} 💎", callback_data="hl:collect"))

    if not finished:
        header = "🃏 <b>Карточная игра: HI-LO</b>"
        footer = f"🎴 Карта: <b>{card}{suit}</b>"
    elif game.get('result') == "win":
        header = "🎉 <b>ПОБЕДА!</b>"
        footer = f"✅ Выигрыш зачислен! Карта: <b>{card}{suit}</b>"
    else:
        header = "💀 <b>ПРОИГРЫШ</b>"
        footer = f"📉 Ставка утеряна. Карта: <b>{card}{suit}</b>"

    text = (
        f"{prefix}{header}\n\n<blockquote>"
        f"👤 Игрок: <b>{user_name}</b>\n"
        f"💵 Ставка: <b>{bet:,}</b>\n"
        f"📈 Множитель: <b>x{coef}</b>\n"
        f"💰 Выигрыш: <b>{int(bet*coef):,}</b>\n"
        f"━━━━━━━━━━━━━━\n{footer}</blockquote>"
    )

    markup = kb.as_markup() if not finished else None
    if isinstance(m, types.Message):
        await m.reply(text, reply_markup=markup, parse_mode="HTML")
    else:
        try:
            await m.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        except: pass

# Команда старта Хило
@dp.message(F.text.lower().startswith("хл"))
async def hl_start(m: types.Message):
    user_id = m.from_user.id
    u = get_u(user_id, m.from_user.full_name)
    args = m.text.split()

    if user_id in active_hilo_games and not active_hilo_games[user_id].get("finished", False):
        game = active_hilo_games[user_id]
        await hl_render_game(m, game, is_reminder=True, prefix="#Активная_игра\n")
        return

    bet = parse_bet(args[1] if len(args)>1 else "0", u[2])
    if bet < 100: return await m.reply("❌ Минимум 100 лир.")
    if u[2] < bet: return await m.reply("❌ Недостаточно лир.")

    upd_bal(user_id, -bet)
    game = {
        "bet": bet,
        "last": random.choice(['3','4','5','6','7','8','9','10','J']),
        "suit": random.choice(CARD_SUITS),
        "coef": 1.0,
        "finished": False,
        "user_name": m.from_user.first_name
    }
    active_hilo_games[user_id] = game
    save_active_game(user_id, "hilo", game)  # 💾 сохраняем в БД
    await hl_render_game(m, game)


# --- ОБРАБОТЧИК КНОПОК ---
@dp.callback_query(F.data.startswith("hl:"))
async def hl_callback(call: types.CallbackQuery):
    await call.answer()  # 🔴 КРИТИЧЕСКИ ВАЖНО (фикс залипания кнопок)

    user_id = call.from_user.id

    if user_id not in active_hilo_games:
        return

    game = active_hilo_games[user_id]
    now = time.time()

    if now - hl_cooldowns.get(user_id, 0) < 1.5:
        return

    hl_cooldowns[user_id] = now

    # ─── ЗАБРАТЬ ─────────────────────────────
    if call.data == "hl:collect":
        win_amount = int(game['bet'] * game['coef'])
        upd_bal(user_id, win_amount)

        game.update({"finished": True, "result": "win"})
        log_game_db(user_id, call.from_user.first_name, "Хило", game['coef'], win_amount, 1)

        try:
            await hl_render_game(call, game, finished=True)
        except:
            pass

        active_hilo_games.pop(user_id, None)
        delete_active_game(user_id)
        hl_cooldowns.pop(user_id, None)
        return

    # ─── РАЗБОР CALLBACK (ЗАЩИТА) ────────────
    try:
        _, action, step_k = call.data.split(":")
        step_k = float(step_k)
    except:
        return  # 🔴 если Telegram прислал мусор — не ломаем игру

    new_card = random.choice(CARDS_NAMES)
    new_suit = random.choice(CARD_SUITS)

    old_val = CARDS_VALUES[game['last']]
    new_val = CARDS_VALUES[new_card]

    is_win = (
        (action == "same" and new_val == old_val) or
        (action == "up" and new_val > old_val) or
        (action == "down" and new_val < old_val)
    )

    # ─── ВЫИГРЫШ ─────────────────────────────
    if is_win:
        game['coef'] = round(game['coef'] * step_k, 2)
        game['last'] = new_card
        game['suit'] = new_suit

        save_active_game(user_id, "hilo", game)

        try:
            await hl_render_game(call, game)
        except:
            pass

    # ─── ПРОИГРЫШ ────────────────────────────
    else:
        game.update({
            "finished": True,
            "result": "lose",
            "last": new_card,
            "suit": new_suit
        })

        try:
            await hl_render_game(call, game, finished=True)
        except:
            pass

        active_hilo_games.pop(user_id, None)
        delete_active_game(user_id)
        hl_cooldowns.pop(user_id, None)

# --- ЭМОДЗИ ИГРЫ (🎯⚽️🏀🎳🎰) ---
@dp.message(F.text.lower().startswith(("футбол", "баскетбол", "боулинг", "спин")))
async def emoji_games(m: types.Message):
    u = get_u(m.from_user.id, m.from_user.full_name)
    args = m.text.split()
    cmd = args[0].lower()
    
    bet = parse_bet(args[1] if len(args) > 1 else "0", u[2])
    if bet < 100: 
        return await m.reply("❌ Минимум 100 лир.")
    if u[2] < bet:
        return await m.reply("❌ Недостаточно лир.")

    target = args[2].lower() if cmd == "дарт" and len(args) > 2 else None
    if cmd == "дартс" and not target: 
        return await m.reply("📖 Пример: `дартс 100 ц`")

    upd_bal(u[0], -bet)
    emo_map = {"футбол":"⚽️", "баскетбол":"🏀", "боулинг":"🎳", "спин":"🎰"}

    # Создаем стартовую пустую кнопку, чтобы она уже была под эмодзи
    kb = InlineKeyboardBuilder()
    kb.button(text="⏳ Ожидание...", callback_data="none")

    # 1. Отправляем эмодзи СРАЗУ с кнопкой
    dice_msg = await m.answer_dice(
        emoji=emo_map[cmd], 
        reply_markup=kb.as_markup(),
        reply_to_message_id=m.message_id
    )
    
    # 2. Ждем анимацию
    await asyncio.sleep(3.5)

    val = dice_msg.dice.value
    win = 0
    # Расчет результата (логика остается прежней)
    if cmd == "дарт":
        res = {1:'м', 2:'б', 3:'к', 4:'б', 5:'к', 6:'ц'}.get(val, 'м')
        if target == res: win = bet * (3 if target in ['ц', 'м'] else 2)
    elif cmd == "футбол" and val >= 3: win = int(bet * 1.6)
    elif cmd == "баскетбол" and val >= 4: win = int(bet * 1.8)
    elif cmd == "боулинг" and val == 6: win = int(bet * 2.2)
    elif cmd == "спин" and val in [1, 22, 43, 64]: win = bet * 10

    # 3. ОБНОВЛЯЕМ КНОПКУ прямо под этим же эмодзи (без нового сообщения)
    res_kb = InlineKeyboardBuilder()
    if win > 0:
        upd_bal(u[0], win)
        res_kb.button(text=f"✅ {win:,} лир", callback_data="none")
    else:
        res_kb.button(text=f"❌ {bet:,} лир", callback_data="none")

    # Используем edit_message_reply_markup для изменения кнопки под кубиком
    try:
        await dice_msg.edit_reply_markup(reply_markup=res_kb.as_markup())
    except Exception:
        # Если Telegram не дает редактировать кубик в этом типе чата, 
        # используем старый метод (ответ на кубик), но в большинстве случаев сработает
        pass

# Чтобы при нажатии на кнопку не было иконки часов (загрузки)
@dp.callback_query(F.data == "none")
async def none_callback(call: types.CallbackQuery):
    await call.answer()

# ====================== X50 ======================

# --- X50 ---

@dp.message(F.text.lower() == "дроп")
async def show_drop(m: types.Message):
    if m.chat.id != X50_CHAT_ID:
        return await m.reply("❌ Игра Х50 доступна только в официальном чате! @Lirachatik")
    # Получаем историю последних 10 игр
    cur.execute("SELECT res FROM x50_history ORDER BY id DESC LIMIT 10")
    h = cur.fetchall()
    
    # Формируем текст
    if not h:
        txt = "📜 <b>История X50 пока пуста.</b>"
    else:
        # Делаем заголовок и каждый результат жирным
        txt = "📜 <b>История X50:</b>\n\n" + "\n".join([f"• <b>{x[0]}</b>" for x in h])
    
    # Используем m.reply вместо m.answer для ответа на сообщение
    await m.reply(txt, parse_mode="HTML")

# --- Лобби X50 ---
import asyncio
import random
from aiogram import F, types
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- Лобби X50 ---
x50_lobby = {
    "active": False,
    "bets": [],
    "timer_task": None,
    "round_closed": False,
    "round_id": 0  # 🔑 ID текущего раунда
}

# --- Ставка ---
@dp.message(F.text.lower().startswith("х50"))
async def x50_start(m: types.Message):
    if m.chat.id != X50_CHAT_ID:
        return await m.reply("❌ Игра Х50 доступна только в официальном чате! @Lirachatik")

    # ❗ закрыто только если ЭТОТ раунд реально закрыт
    if x50_lobby["active"] and x50_lobby["round_closed"]:
        return await m.reply("⛔ Ставки на этот раунд уже закрыты.")

    args = m.text.split()
    u = get_u(m.from_user.id, m.from_user.full_name)

    if len(args) < 3:
        return await m.reply("📖 Формат: <code>х50 [сумма] [ч/ф/к/з]</code>", parse_mode="HTML")

    bet = parse_bet(args[1], u[2])
    col = args[2].lower()
    cmap = {'ч': ('black','⚫',2), 'ф': ('purple','🟣',3), 'к': ('red','🔴',5), 'з': ('green','🟢',50)}

    if col not in cmap or bet <= 0:
        return await m.reply("❌ Ошибка в ставке или цвете!")
    if u[2] < bet:
        return await m.reply("❌ Недостаточно лир!")

    upd_bal(u[0], -bet)
    cur.execute("UPDATE users SET last_x50_bet=? WHERE uid=?", (f"{col}:{bet}", u[0]))

    x50_lobby["bets"].append({
        "uid": u[0],
        "name": u[1],
        "bet": bet,
        "col": cmap[col][0]
    })

    await m.reply(
        f"{cmap[col][1]} <b>{u[1]}</b> поставил <b>{bet:,}</b> лир на <b>x{cmap[col][2]}</b>",
        parse_mode="HTML"
    )

    # ▶️ запуск раунда, если ещё не активен
    if not x50_lobby["active"]:
        x50_lobby["active"] = True
        x50_lobby["round_closed"] = False
        x50_lobby["round_id"] += 1
        rid = x50_lobby["round_id"]
        x50_lobby["timer_task"] = asyncio.create_task(x50_timer(m.chat.id, rid))

# --- Таймер раунда ---
async def x50_timer(chat_id, rid):
    try:
        await asyncio.sleep(13)

        if not x50_lobby["active"] or x50_lobby["round_id"] != rid:
            return

        x50_lobby["round_closed"] = True
        await asyncio.sleep(2)

        if not x50_lobby["active"] or x50_lobby["round_id"] != rid:
            return

        await run_x50(chat_id, rid)

    except asyncio.CancelledError:
        return

# --- Результат ---
async def run_x50(cid, rid):
    if x50_lobby["round_id"] != rid:
        return

    res_k = random.choices(
        ['black','purple','red','green'],
        weights=[45,35,19,1]
    )[0]

    rmap = {
        'black': ('⚫ x2', 2),
        'purple': ('🟣 x3', 3),
        'red': ('🔴 x5', 5),
        'green': ('🟢 x50', 50)
    }

    # запись результата в БД
    cur.execute("INSERT INTO x50_history (res) VALUES (?)", (rmap[res_k][0],))
    conn.commit()

    text = (
    f"🎡 <b>Результат X50:</b> "
    f"{rmap[res_k][0].replace('x', '<b>x') + '</b>'}\n"
    + "⎯" * 13 + "\n"
)
    any_bets = False

    color_groups = [('black','⚫',2),('purple','🟣',3),('red','🔴',5),('green','🟢',50)]
    for name, emoji, mult in color_groups:
        bets = [b for b in x50_lobby["bets"] if b["col"] == name]
        if not bets:
            continue
        any_bets = True
        text += f"{emoji} <b>Ставки на x{mult}:</b>\n"
        for b in bets:
            uid_link = f"<a href='tg://user?id={b['uid']}'>{b['name']}</a>"
            if b["col"] == res_k:
                win = b["bet"] * mult
                if asyncio.iscoroutinefunction(upd_bal):
                    await upd_bal(b["uid"], win)
                else:
                    upd_bal(b["uid"], win)
                text += f"💸 {uid_link} — ставка <b>{b['bet']:,}</b> → <b>{win:,}</b>\n"
            else:
                text += f"❌ {uid_link} — ставка <b>{b['bet']:,}</b> → <b>0</b>\n"
        text += "⎯" * 13 + "\n"

    if not any_bets:
        text += "<i>Ставок не было.</i>\n" + "⎯"*25

    # кнопка повторить ставку
    builder = InlineKeyboardBuilder()
    builder.button(text="🔁 Повторить ставку", callback_data="x50_re")

    # Отправка, безопасно для длинного текста
    MAX_LEN = 4000
    if len(text) > MAX_LEN:
        for i in range(0, len(text), MAX_LEN):
            await bot.send_message(cid, text[i:i+MAX_LEN], parse_mode="HTML", disable_web_page_preview=True)
        await bot.send_message(cid, "🔁 Повторить ставку", reply_markup=builder.as_markup())
    else:
        await bot.send_message(
            cid,
            text,
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
            disable_web_page_preview=True
        )

    # 🧹 очистка
    if x50_lobby["timer_task"]:
        x50_lobby["timer_task"].cancel()

    x50_lobby.update({
        "active": False,
        "round_closed": False,
        "bets": [],
        "timer_task": None
    })

# --- Повтор последней ставки ---
@dp.callback_query(F.data == "x50_re")
async def x50_repeat_callback(call: types.CallbackQuery):
    user_id = call.from_user.id
    u = get_u(user_id, call.from_user.full_name)
    
    cur.execute("SELECT last_x50_bet FROM users WHERE uid=?", (user_id,))
    row = cur.fetchone()
    if not row or not row[0]:
        return await call.answer("❌ У вас не было последней ставки!", show_alert=True)
    
    try:
        last_col, last_bet = row[0].split(":")
        last_bet = int(last_bet)
    except:
        return await call.answer("❌ Ошибка при восстановлении ставки!", show_alert=True)
    
    if u[2] < last_bet:
        return await call.answer(f"❌ Недостаточно лир! Нужно <b>{last_bet:,}</b>", show_alert=True)
    
    cmap = {'ч': ('black','⚫',2), 'ф': ('purple','🟣',3), 'к': ('red','🔴',5), 'з': ('green','🟢',50)}
    upd_bal(user_id, -last_bet)
    x50_lobby["bets"].append({"uid": user_id, "name": call.from_user.first_name, "bet": last_bet, "col": cmap[last_col][0]})
    
    await call.message.answer(f"{cmap[last_col][1]} <b>{call.from_user.first_name}</b> повторил ставку <b>{last_bet:,}</b> лир", parse_mode="HTML")
    await call.answer("✅ Ставка повторена!")

    if not x50_lobby["active"]:
        x50_lobby["active"] = True
        x50_lobby["round_closed"] = False
        x50_lobby["timer_task"] = asyncio.create_task(x50_timer(call.message.chat.id, x50_lobby["round_id"]))

#jackpot
import asyncio # Проверь, что это есть в самом верху файла!

# --- JACKPOT CONFIG ---
jackpot_lobby = {"active": False, "bets": []}

@dp.message(F.text.lower().startswith("джекпот"))
async def jackpot_start(m: types.Message):
    # Убедись, что переменная X50_CHAT_ID определена в начале твоего кода
    if m.chat.id != X50_CHAT_ID: 
        return await m.reply("❌ Игра доступна только в официальном чате!")
    
    u = get_u(m.from_user.id, m.from_user.full_name)
    args = m.text.split()
    
    if len(args) < 2:
        return await m.reply("📖 Формат: <code>джекпот [сумма]</code>", parse_mode="HTML")
    
    bet = parse_bet(args[1], u[2])
    
    if bet < 100: 
        return await m.reply("❌ Минимальная ставка — <b>100</b> лир!", parse_mode="HTML")
    
    if u[2] < bet:
        return await m.reply("❌ Недостаточно лир!")

    # Списываем ставку и добавляем в лобби
    upd_bal(u[0], -bet)
    jackpot_lobby["bets"].append({"uid": u[0], "name": u[1], "bet": bet})
    
    total_bank = sum(b['bet'] for b in jackpot_lobby["bets"])
    
    await m.reply(
        f"🎟 <b>{u[1]}</b> внес в банк <b>{bet:,}</b> лир!\n"
        f"💰 Общий банк: <b>{total_bank:,}</b> лир", 
        parse_mode="HTML"
    )
    
    # Запуск таймера только ОДИН раз (для первой ставки)
    if not jackpot_lobby["active"]:
        jackpot_lobby["active"] = True
        # Мы используем create_task, чтобы код не "зависал" на 30 секундах и принимал другие ставки
        asyncio.create_task(start_jackpot_timer(m.chat.id))

async def start_jackpot_timer(cid):
    await asyncio.sleep(30) # Ждем 30 секунд для сбора всех ставок
    await run_jackpot(cid)


async def run_jackpot(cid):
    # Добавляем явное указание, что мы используем глобальный модуль random
    global random 
    
    bets = jackpot_lobby["bets"].copy()
    if not bets:
        jackpot_lobby["active"] = False
        return

    total_bank = sum(b['bet'] for b in bets)
    
    # Выбираем победителя
    # Ошибка была здесь — Python не видел модуль random
    winner = random.choices(bets, weights=[b['bet'] for b in bets], k=1)[0]
    
    win_chance = round((winner['bet'] / total_bank) * 100, 1)
    
    # Начисляем выигрыш
    upd_bal(winner['uid'], total_bank)
    
    # Оформление (Жирный шрифт и линии как на скринах)
    text = f"🎰 <b>ИТОГИ ДЖЕКПОТА</b>\n"
    text += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    text += f"🏆 Победитель: <b>{winner['name']}</b>\n"
    text += f"💰 Выигрыш: <b>{total_bank:,}</b> лир\n"
    text += f"📈 Шанс победы: <b>{win_chance}%</b>\n"
    text += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    text += "<b>Участники раунда:</b>\n"
    
    for b in bets:
        chance = round((b['bet'] / total_bank) * 100, 1)
        text += f"• <b>{b['name']}</b> — <b>{b['bet']:,}</b> (<i>{chance}%</i>)\n"
    
    text += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"

    # Сбрасываем лобби ПЕРЕД отправкой сообщения
    jackpot_lobby["active"] = False
    jackpot_lobby["bets"] = []

    await bot.send_message(cid, text, parse_mode="HTML")

    



# --- ФЛИП И ОХОТА ---

@dp.message(F.text.lower().startswith("флип"))
async def flip_start(m: types.Message, state: FSMContext):
    data = await state.get_data()
    
    # 🔴 Активная игра — отправляем реплай с хэштегом
    if data.get("type") == "flip" and not data.get("resolved"):
        await m.reply(
            "#Активная_игра\n\n" + data["text"],
            reply_markup=data["kb"],
            parse_mode="HTML",
            reply_to_message_id=m.message_id
        )
        return

    u = get_u(m.from_user.id, m.from_user.full_name)
    args = m.text.split()
    bet = parse_bet(args[1] if len(args) > 1 else "0", u[2])

    if bet < 100:
        return await m.reply("❌ Ставка от <b>100</b> лир!", parse_mode="HTML")
    if u[2] < bet:
        return await m.reply("❌ У вас недостаточно лир!", parse_mode="HTML")

    upd_bal(u[0], -bet)

    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="🪙 Орел", callback_data=f"flip:1:{bet}:{m.from_user.id}"),
        types.InlineKeyboardButton(text="🦅 Решка", callback_data=f"flip:2:{bet}:{m.from_user.id}")
    )
    kb.row(types.InlineKeyboardButton(text="🔄 Автовыбор", callback_data=f"flip:3:{bet}:{m.from_user.id}"))

    text = (
        "🪙 <b>Игра в Монетку!</b>\n\n"
        "<blockquote>"
        f"💰 Ставка: <b>{bet:,}</b> лир\n"
        "📈 Коэффициент: <b>x1.9</b>\n"
        "</blockquote>\n"
        "Выберите сторону:"
    )

    msg = await m.reply(text, reply_markup=kb.as_markup(), parse_mode="HTML", reply_to_message_id=m.message_id)

    await state.set_data({
        "type": "flip",
        "bet": bet,
        "user_id": m.from_user.id,
        "text": text,
        "kb": kb.as_markup(),
        "resolved": False
    })



@dp.callback_query(F.data.startswith("flip:"))
async def flip_cb(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    if not data or data.get("type") != "flip" or data.get("resolved"):
        return await call.answer("⏳ Игра уже завершена", show_alert=False)

    _, choice, bet, user_id = call.data.split(":")
    bet = int(bet)
    user_id = int(user_id)

    # Проверка владельца
    if call.from_user.id != user_id:
        return await call.answer("Это не твоя игра! 🪙", show_alert=True)

    await state.update_data(resolved=True)
    await call.answer()

    result = random.choice(["1", "2"])
    user_choice = choice if choice != "3" else random.choice(["1", "2"])
    win = user_choice == result
    res_name = "🪙 Орел" if result == "1" else "🦅 Решка"

    if win:
        win_total = int(bet * 1.9)
        upd_bal(user_id, win_total)
        text = (
            f"✅ <b>Победа!</b>\n\n"
            f"<blockquote>🎰 Выпало: <b>{res_name}</b>\n"
            f"🏆 Ваш выигрыш: <b>{win_total:,}</b> лир</blockquote>"
        )
    else:
        text = (
            f"❌ <b>Проигрыш</b>\n\n"
            f"<blockquote>🎰 Выпало: <b>{res_name}</b>\n"
            f"📉 Вы потеряли: <b>{bet:,}</b> лир</blockquote>"
        )

    await call.message.edit_text(text, reply_markup=None, parse_mode="HTML")
    await state.clear()
    
import random
import asyncio

@dp.message(F.text.lower().startswith("охота"))
async def hunt(m: types.Message):
    user_id = m.from_user.id
    user_name = m.from_user.first_name
    u = get_u(user_id, m.from_user.full_name)
    args = m.text.split()
    
    # 1. Проверка ставки
    bet = parse_bet(args[1] if len(args) > 1 else "0", u[2])

    if bet < 100:
        return await m.reply("❌ Минимальная ставка — <b>100</b> лир.", parse_mode="HTML")
    if u[2] < bet:
        return await m.reply("❌ У вас недостаточно лир!", parse_mode="HTML")

    # 2. Списываем ставку перед началом
    upd_bal(user_id, -bet)

    # Красивый жирный текст ожидания с включенным HTML
    msg = await m.answer(
        "🏹 <b>Вы затаили дыхание и спустили тетиву...</b>\n"
        "<i>Стрела летит точно в цель, подождите результат!</i>",
        reply_to_message_id=m.message_id,
        parse_mode="HTML"  # ЭТО ОБЯЗАТЕЛЬНО, чтобы теги заработали
    )
    await asyncio.sleep(2)

    win_texts = [
        "💥🦅 Ястреб высоко в небе, но ваш выстрел был безупречен! Он рухнул вниз.",
        "🔥🐺 Волк завыл, но его крик оборвался — стрела нашла цель.",
        "⚡🦌 Олень замер, и этого мига хватило. Ваш выстрел — точен, добыча — ваша!",
        "🌪️🐗 Кабан метался в зарослях, но ловушка сработала.",
        "💀🦉 Сова пыталась скрыться в ночи, но попала в ваши сети.",
        "🔥🐍 Змея скользила по траве, но вы были быстрее.",
        "⚔️🐻 Медведь пал после яростной схватки. Ваша сила непоколебима.",
        "🌌🦊 Лиса хитро петляла, но вы всё же настигли её.",
        "🏹🦌 Стрела свистнула — и цель пала. Сегодня удача с вами.",
        "🔥🦅 Орёл бросился вниз, но был встречен вашим выстрелом.",
        "🌪️🐺 Бой был напряжённым, но зверь пал к вашим ногам.",
        "⚡🦊 Быстрая, как ветер, но не быстрее вас. Лиса повержена.",
        "💥🐇 Заяц прыгнул в последний миг, но не избежал судьбы.",
        "🔥🦌 Рёв леса смолк — ваш выстрел был решающим.",
        "🌑🐗 Ловушка щёлкнула, и охота завершилась вашей победой."
    ]

    lose_texts = [
         "🌑🦊 Лиса обманула вас хитростью и скрылась в тумане. Добычи нет.",
        "🥀🦌 Олень сорвался с места, оставив вас с пустыми руками.",
        "🕳️🐇 Заяц исчез в своей норе быстрее, чем вы успели выстрелить.",
        "🌲🐻 Медведь оказался сильнее и прогнал вас прочь. Вы потеряли шанс на трофей.",
        "⚡🦅 Орёл поднялся выше облаков, и стрела не достала его. Вы остались ни с чем.",
        "🌌🐺 Волк ускользнул в темноту, оставив вас без добычи.",
        "💨🦉 Сова вспорхнула в ночное небо, и вы промахнулись.",
        "🌑🐗 Кабан прорвал ловушку и исчез в чаще. Сегодня не ваш день."
    ]

    if random.random() < 0.4:
        # ✅ ПОБЕДА
        win_amount = int(bet * 2)
        upd_bal(user_id, win_amount) # Зачисление на баланс
        
        cur.execute("UPDATE users SET daily = daily + ? WHERE uid = ?", (win_amount, user_id))
        conn.commit()
        log_game_db(user_id, user_name, "Охота", 2.0, win_amount, 1)
        
        txt = random.choice(win_texts)
        # Оформление результата в цитату
        result_text = (
            f"🎯 <b>Охота завершена успешно!</b>\n\n"
            f"<blockquote>"
            f"{txt}\n\n"
            f"📈 Коэффициент: <b>x2</b>\n"
            f"💰 Награда: <b>{win_amount:,}</b> лир"
            f"</blockquote>"
        )
    else:
        # 💥 ПОРАЖЕНИЕ
        log_game_db(user_id, user_name, "Охота", 0, bet, 0)
        
        txt = random.choice(lose_texts)
        # Оформление результата в цитату
        result_text = (
            f"💨 <b>Удача ускользнула от вас...</b>\n\n"
            f"<blockquote>"
            f"{txt}\n\n"
            f"❌ Убыток: <b>{bet:,}</b> лир"
            f"</blockquote>"
        )

    await msg.edit_text(result_text, parse_mode="HTML")
    


# --- ПРОМОКОДЫ ---
@dp.message(F.text.lower().startswith(("промо", "/promo")))
async def promo_act(m: types.Message):
    u = get_u(m.from_user.id, m.from_user.full_name); args = m.text.split()
    if len(args) < 2: return await m.reply("📖 `промо [код]`")
    code = args[1].upper()
    cur.execute("SELECT amount, uses FROM promo WHERE code=?", (code,))
    p = cur.fetchone()
    if not p: return await m.reply("❌ Нет такого промо!")
    cur.execute("SELECT * FROM promo_history WHERE uid=? AND code=?", (u[0], code))
    if cur.fetchone(): return await m.reply("⚠️ Уже активирован!")
    if p[1] <= 0: return await m.reply("❌ Активации закончились!")
    upd_bal(u[0], p[0]); cur.execute("UPDATE promo SET uses=uses-1 WHERE code=?", (code,))
    cur.execute("INSERT INTO promo_history VALUES (?,?)", (u[0], code)); conn.commit()
    await m.reply(f"✅ Промо Активирован! Вам зачислен {p[0]:,} лир.")

@dp.message(Command("admin"))
async def adm_panel(m: types.Message):
    if m.from_user.id not in ADMIN_ID: return
    
    kb = InlineKeyboardBuilder()
    kb.button(text="💰 Выдать", callback_data="adm_give")
    kb.button(text="👥 Юзеры", callback_data="adm_users") # Новая кнопка
    kb.button(text="🎁 Промо", callback_data="adm_promo")
    kb.button(text="📢 Рассылка", callback_data="adm_mail")
    kb.button(text="⚡️ Фаст", callback_data="adm_fast")
    kb.button(text="❓ Викторина", callback_data="adm_vik")
    kb.button(text="♻️ Сброс ТОП", callback_data="adm_reset_top")
    kb.adjust(2)
    await m.answer("⚙️ **ПАНЕЛЬ УПРАВЛЕНИЯ**", reply_markup=kb.as_markup(), parse_mode="Markdown")

# --- ЛОГИКА ВЫДАЧИ (Исправлено по запросу) ---
@dp.callback_query(F.data == "adm_give")
async def adm_give_1(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("👤 Введите ID пользователя, которому хотите выдать лиры:")
    await state.set_state(AdminStates.give_id)

@dp.message(AdminStates.give_id)
async def adm_give_2(m: types.Message, state: FSMContext):
    if not m.text.isdigit():
        return await m.reply("❌ Введите корректный числовой ID!")
    await state.update_data(target_id=int(m.text))
    await m.answer("💰 Теперь введите сумму:")
    await state.set_state(AdminStates.give_amount)

@dp.message(AdminStates.give_amount)
async def adm_give_3(m: types.Message, state: FSMContext):
    summ_text = m.text.lower().replace("к", "000").replace("k", "000")
    if not summ_text.isdigit():
        return await m.reply("❌ Введите число!")
    
    data = await state.get_data()
    target_id = data['target_id']
    amount = int(summ_text)
    
    try:
        upd_bal(target_id, amount)
        await m.answer(f"✅ Успешно выдано {amount:,} лир пользователю `{target_id}`")
        await bot.send_message(target_id, f"💳 Администратор выдал вам {amount:,} лир!")
    except Exception as e:
        await m.answer(f"❌ Ошибка: {e}")
    await state.clear()

# --- ЛОГИКА ПРОМОКОДОВ ---
@dp.callback_query(F.data == "adm_promo")
async def adm_p1(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("📝 Введите название промокода:")
    await state.set_state(AdminStates.promo_name)

@dp.message(AdminStates.promo_name)
async def adm_p2(m: types.Message, state: FSMContext):
    await state.update_data(p_n=m.text.upper())
    await m.answer("💰 Сумма активации:")
    await state.set_state(AdminStates.promo_sum)

@dp.message(AdminStates.promo_sum)
async def adm_p3(m: types.Message, state: FSMContext):
    if not m.text.isdigit(): return await m.reply("❌ Введите число")
    await state.update_data(p_s=int(m.text))
    await m.answer("👥 Количество использований:")
    await state.set_state(AdminStates.promo_uses)

@dp.message(AdminStates.promo_uses)
async def adm_p4(m: types.Message, state: FSMContext):
    if not m.text.isdigit(): 
        return await m.reply("❌ Введите число")
    
    d = await state.get_data()
    n, s, u = d['p_n'], d['p_s'], int(m.text)
    
    cur.execute("INSERT INTO promo VALUES (?,?,?)", (n, s, u))
    conn.commit()
    
    await m.answer(f"✅ Промокод `{n}` создан!")
    
    # Текст сообщения для чата
    # Используем `Промо {n}`, чтобы при клике копировалась сразу команда с кодом
    chat_text = (
        f"🎁 <b>НОВЫЙ ПРОМОКОД!</b>\n\n"
        f"🎫 Нажми на код, чтобы скопировать:\n"
        f"<code>Промо {n}</code>\n\n"
        f"💰 Сумма: <b>{s:,}</b> лир\n"
        f"👤 Активаций: <b>{u}</b>"
    )
    
    await bot.send_message(
        X50_CHAT_ID, 
        chat_text, 
        parse_mode="HTML"
    )
    await state.clear()
    
# --- ЛОГИКА РАССЫЛКИ ---
@dp.callback_query(F.data == "adm_mail")
async def adm_m1(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("📨 Введите текст рассылки для всех пользователей:")
    await state.set_state(AdminStates.mailing_text)

@dp.message(AdminStates.mailing_text)
async def adm_m2(m: types.Message, state: FSMContext):
    cur.execute("SELECT uid FROM users")
    users = cur.fetchall()
    count = 0
    await m.answer(f"🚀 Рассылка запущена на {len(users)} чел...")
    for u in users:
        try:
            await bot.send_message(u[0], m.text)
            count += 1
            await asyncio.sleep(0.05)
        except: continue
    await m.answer(f"✅ Рассылка завершена! Получили: {count} чел.")
    await state.clear()

# --- ЛОГИКА ФАСТ КОНКУРСА (ФК) ---
@dp.callback_query(F.data == "adm_fast")
async def adm_f1(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("💰 <b>Введите сумму для ФАСТ КОНКУРСА:</b>\n(Например: 50000 или 50к)", parse_mode="HTML")
    await state.set_state(AdminStates.fast_amount)

@dp.message(AdminStates.fast_amount)
async def fast_publish(m: types.Message, state: FSMContext):
    # Убираем "к" или "k", если ввели текстом
    summ_text = m.text.lower().replace("к", "000").replace("k", "000").strip()
    
    if not summ_text.isdigit():
        return await m.reply("❌ <b>Введите число!</b>", parse_mode="HTML")
    
    amount = int(summ_text)
    await state.clear() # Очищаем состояние ПЕРЕД публикацией
    
    kb = InlineKeyboardBuilder()
    kb.button(text="💝 ЗАБРАТЬ", callback_data=f"take_fc_{amount}")
    
    await bot.send_message(
        X50_CHAT_ID,
        f"🎁 <b>ФАСТ КОНКУРС</b>\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"УСПЕЙ ПЕРВЫМ НАЖАТЬ НА КНОПКУ!\n\n"
        f"💰 Сумма: <b>{amount:,}</b> лир\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )
    await m.answer(f"✅ <b>ФК на {amount:,} лир запущен!</b>", parse_mode="HTML")

# --- ОБРАБОТКА КНОПКИ ФК ---
@dp.callback_query(F.data.startswith("take_fc_"))
async def take_fast_contest(call: types.CallbackQuery):
    # Извлекаем сумму
    try:
        amount = int(call.data.split("_")[2])
    except:
        return await call.answer("❌ Ошибка данных конкурса")

    # Проверка: не завершен ли конкурс (смотрим на текст сообщения)
    if "ЗАВЕРШЕН" in (call.message.text or ""):
        return await call.answer("❌ Этот приз уже забрали!", show_alert=True)

    try:
        # Сразу отвечаем пользователю, чтобы кнопка не "зависала"
        await call.answer("🎉 Проверка...")

        # Получаем пользователя и обновляем баланс (используем ваши функции)
        u = get_u(call.from_user.id, call.from_user.full_name)
        upd_bal(u[0], amount)
        
        # РЕДАКТИРУЕМ СООБЩЕНИЕ (Ставим флаг ЗАВЕРШЕН первым делом)
        await call.message.edit_text(
            f"✅ <b>ФАСТ КОНКУРС ЗАВЕРШЕН</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"👤 Победитель: <b>{call.from_user.full_name}</b>\n"
            f"💰 Сумма: <b>{amount:,}</b> лир\n"
            f"━━━━━━━━━━━━━━\n"
            f"Лиры зачислены на баланс!",
            parse_mode="HTML"
        )
        
    except Exception as e:
        print(f"Ошибка в ФК: {e}")
        await call.answer("❌ Произошла ошибка или вы не успели!", show_alert=False)
        
# --- ЛОГИКА ВИКТОРИНЫ ---
@dp.callback_query(F.data == "adm_vik")
async def adm_v1(c: types.CallbackQuery, state: FSMContext):
    await c.message.answer("💰 <b>Шаг [1/3]:</b> Введите сумму приза:")
    await state.set_state(AdminStates.vik_amount)

@dp.message(AdminStates.vik_amount)
async def vik_get_amount(m: types.Message, state: FSMContext):
    summ_text = m.text.lower().replace("к", "000").replace("k", "000").strip()
    if not summ_text.isdigit():
        return await m.reply("❌ <b>Введите число!</b>")
    
    await state.update_data(amount=int(summ_text))
    await m.answer("❓ <b>Шаг [2/3]:</b> Введите ВОПРОС викторины:")
    await state.set_state(AdminStates.vik_question)

@dp.message(AdminStates.vik_question)
async def vik_get_question(m: types.Message, state: FSMContext):
    await state.update_data(question=m.text)
    await m.answer("📝 <b>Шаг [3/3]:</b> Введите ПРАВИЛЬНЫЙ ОТВЕТ:")
    await state.set_state(AdminStates.vik_answer)

@dp.message(AdminStates.vik_answer)
async def vik_get_answer(m: types.Message, state: FSMContext):
    data = await state.get_data()
    
    # Записываем в глобальный словарь (убедись, что active_vik создан в начале кода)
    active_vik["amount"] = data['amount']
    active_vik["question"] = data['question']
    active_vik["answer"] = m.text.lower().strip()
    active_vik["is_active"] = True
    
    await bot.send_message(
        X50_CHAT_ID, 
        f"🎁 <b>ВИКТОРИНА!</b>\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"❓ Вопрос: <b>{active_vik['question']}</b>\n\n"
        f"💰 Приз: <b>{active_vik['amount']:,}</b> лир\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"Кто первым напишет правильный ответ?",
        parse_mode="HTML"
    )
    await m.answer("✅ <b>Викторина запущена!</b>")
    await state.clear()
    
# --- СБРОС ТОПА ---
@dp.callback_query(F.data == "adm_reset_top")
async def adm_reset_top(c: types.CallbackQuery):
    # Получаем топ-5 игроков по дневной прибыли
    rows = cur.execute("SELECT name, daily, uid FROM users WHERE daily > 0 ORDER BY daily DESC LIMIT 5").fetchall()
    
    if not rows:
        await c.message.reply("❌ Нет игроков в топе для выдачи призов.", reply=False)
        await c.answer()
        return

    # Призы по местам
    prizes = [100_000, 80_000, 60_000, 40_000, 20_000]

    report_text = "🎉 <b>Топ-5 игроков за сегодня!</b>\n\n"

    for i, row in enumerate(rows):
        name, profit, uid = row
        prize = prizes[i]

        # Начисляем на баланс
        cur.execute("UPDATE users SET bal = bal + ? WHERE uid = ?", (prize, uid))

        # Отправка ЛС игроку
        try:
            await bot.send_message(
                uid,
                f"🏆 <b>Поздравляем!</b>\n\n"
                f"Вы вошли в топ игроков за сегодня!\n"
                f"Ваше место: <b>{i+1}</b>\n"
                f"Ваша награда: <b>{prize:,} лир</b>",
                parse_mode="HTML"
            )
        except:
            # Игрок мог закрыть ЛС
            pass

        # Добавляем игрока в отчёт как цитату с ссылкой
        profile_link = f"http://t.me/@id{uid}"
        report_text += f'“{i+1} <a href="{profile_link}"><b>{name}</b></a> | <b>{prize:,} лир</b>”\n\n'

    # Обнуляем дневной топ
    cur.execute("UPDATE users SET daily = 0")
    conn.commit()

    # Внизу отчёта добавляем цитату с призами
    prizes_text = (
        '“<b>🥇 1 место — 100,000 лир</b>\n'
        '<b>🥈 2 место — 80,000 лир</b>\n'
        '<b>🥉 3 место — 60,000 лир</b>\n'
        '<b>4️⃣ 4 место — 40,000 лир</b>\n'
        '<b>5️⃣ 5 место — 20,000 лир</b>”\n'
    )
    report_text += prizes_text

    # Реплай админу
    await c.message.reply(report_text, parse_mode="HTML", disable_web_page_preview=True)
    await c.answer()


# --- ПРОВЕРКА ОТВЕТА ВИКТОРИНЫ ---
@dp.message(lambda m: active_vik.get("is_active") == True)
async def check_vik_answer(m: types.Message):
    # Проверяем, что ответ в нужном чате
    if m.chat.id != X50_CHAT_ID: 
        return

    # Если текста нет (например, прислали стикер) — игнорим
    if not m.text:
        return

    user_answer = m.text.lower().strip()
    correct_answer = str(active_vik["answer"]).lower().strip()

    if user_answer == correct_answer:
        # Мгновенно выключаем активность, чтобы не было 2-х победителей
        active_vik["is_active"] = False 
        
        try:
            u = get_u(m.from_user.id, m.from_user.full_name)
            upd_bal(u[0], active_vik["amount"])
            
            await m.reply(
                f"🎊 <b>ЕСТЬ ПОБЕДИТЕЛЬ!</b>\n"
                f"━━━━━━━━━━━━━━\n"
                f"👤 <b>{m.from_user.full_name}</b> ответил правильно: <code>{active_vik['answer']}</code>\n"
                f"💰 Приз <b>{active_vik['amount']:,}</b> лир зачислен!\n"
                f"━━━━━━━━━━━━━━",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Ошибка в выдаче викторины: {e}")

# Нажали "Юзеры" -> просим ID
# Количество игроков на одной странице
USERS_PER_PAGE = 10

@dp.callback_query(F.data.startswith("adm_users"))
async def adm_users_list(call: types.CallbackQuery):
    # Определяем текущую страницу
    data = call.data.split("_")
    page = int(data[2]) if len(data) > 2 else 0
    offset = page * USERS_PER_PAGE

    # Получаем срез игроков из БД
    cur.execute("SELECT uid, name FROM users LIMIT ? OFFSET ?", (USERS_PER_PAGE, offset))
    users = cur.fetchall()

    # Считаем общее количество для навигации
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]

    kb = InlineKeyboardBuilder()

    # Создаем кнопки для каждого игрока
    for uid, name in users:
        kb.button(text=f"👤 {name} (ID: {uid})", callback_data=f"u_control_{uid}")
    
    kb.adjust(1) # Список в одну колонку

    # Кнопки управления страницами
    nav_buttons = []
    if page > 0:
        nav_buttons.append(types.InlineKeyboardButton(text="⏪ Назад", callback_data=f"adm_users_{page-1}"))
    
    # Кнопка текущей страницы
    nav_buttons.append(types.InlineKeyboardButton(text=f"📄 {page+1}", callback_data="none"))
    
    if offset + USERS_PER_PAGE < total_users:
        nav_buttons.append(types.InlineKeyboardButton(text="⏩ Вперед", callback_data=f"adm_users_{page+1}"))
    
    kb.row(*nav_buttons)
    kb.row(types.InlineKeyboardButton(text="🔙 В админку", callback_data="admin_main"))

    text = f"👥 <b>СПИСОК ИГРОКОВ</b>\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\nВсего в базе: <b>{total_users}</b>"
    
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    
        
@dp.callback_query(F.data.startswith("u_control_"))
async def adm_user_manage(call: types.CallbackQuery):
    target_id = int(call.data.split("_")[2])
    # Получаем данные: [1]-имя, [2]-бал, [10]-бан, [11]-банк
    user = get_u(target_id, "Игрок") 
    
    if not user:
        return await call.answer("❌ Игрок не найден!", show_alert=True)

    bal = user[2]
    bank = user[11] if len(user) > 11 else 0
    is_banned = "🔴 ЗАБАНЕН" if user[10] == 1 else "🟢 Активен"
    
    text = (
        f"👤 <b>УПРАВЛЕНИЕ ИГРОКОМ</b>\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"🆔 ID: <code>{target_id}</code>\n"
        f"📝 Ник: <b>{user[1]}</b>\n"
        f"💰 Баланс: <b>{bal:,}</b>\n"
        f"🏦 В банке: <b>{bank:,}</b>\n"
        f"📊 Статус: {is_banned}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="🧹 Обнулить всё", callback_data=f"u_reset_{target_id}")
    kb.button(text="📜 Логи", callback_data=f"u_logs_{target_id}")
    kb.button(text="🚫 Бан/Разбан", callback_data=f"u_ban_{target_id}")
    kb.button(text="💰 Выдать", callback_data=f"u_give_{target_id}")
    kb.button(text="🔙 Назад к списку", callback_data="adm_users_0")
    kb.adjust(1)

    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# ИСПРАВЛЕННЫЙ БЛОК ДЕЙСТВИЙ (без SyntaxError)
@dp.callback_query(F.data.startswith("u_"))
async def adm_u_actions(call: types.CallbackQuery, state: FSMContext):
    data = call.data.split("_")
    action = data[1]
    tid = int(data[2])

    if action == "reset":
        cur.execute("UPDATE users SET bal = 0, bank = 0, daily = 0 WHERE uid = ?", (tid,))
        conn.commit()
        await call.answer("🧹 Баланс и банк обнулены!", show_alert=True)
        await adm_user_manage(call) # Обновляем карточку игрока

    elif action == "ban":
        cur.execute("SELECT banned FROM users WHERE uid = ?", (tid,))
        res = cur.fetchone()
        new_status = 1 if res[0] == 0 else 0
        cur.execute("UPDATE users SET banned = ? WHERE uid = ?", (new_status, tid))
        conn.commit()
        await call.answer("✅ Статус изменен!", show_alert=True)
        await adm_user_manage(call) # Обновляем карточку игрока

    elif action == "give":
        await state.update_data(target_id=tid)
        await call.message.answer(f"💰 Введите сумму для <b>{tid}</b> (можно с 'к'):", parse_mode="HTML")
        await state.set_state(AdminStates.give_amount)
#
@dp.callback_query(F.data.startswith("u_logs_"))
async def adm_view_logs(call: types.CallbackQuery):
    tid = int(call.data.split("_")[2])
    
    # Обязательно отвечаем на колбэк в самом начале, чтобы кнопка не лагала
    await call.answer()

    cur.execute("SELECT game, amount, result, date FROM logs WHERE uid = ? ORDER BY id DESC LIMIT 10", (tid,))
    rows = cur.fetchall()
    
    if not rows:
        return await call.message.answer(f"📜 У игрока {tid} пока нет истории игр.")
    
    text = f"📜 <b>ИСТОРИЯ ОПЕРАЦИЙ (ID: {tid})</b>\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    for r in rows:
        date_str = r[3][5:16].replace("-", ".") 
        text += f"📅 <code>{date_str}</code> | <b>{r[0]}</b>\n💰 {r[1]:,} | {r[2]}\n\n"
    
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад", callback_data=f"u_control_{tid}")
    
    try:
        await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except TelegramBadRequest:
        pass # Если логи не изменились, ничего не делаем    



        
@dp.message((F.text == "👤 Профиль") | (F.text.lower() == "профиль"))
async def profile_handler(m: types.Message):
    target = m.reply_to_message.from_user if m.reply_to_message else m.from_user
    
    cur.execute("""SELECT uid, name, bal, reg, level, used_limit, bank, reputation, bio, hide_bal, hide_bank 
                   FROM users WHERE uid = ?""", (target.id,))
    u = cur.fetchone()
    
    if not u: 
        return await m.reply("❌ <b>Игрок еще не зарегистрирован в боте.</b>", parse_mode="HTML")

    uid, name, bal, reg, lv, used, bank, rep, bio, h_bal, h_bank = u
    
    is_owner = m.from_user.id == uid
    bal_display = f"<b>{bal:,}</b> лир" if (h_bal == 0 or is_owner) else "<b>🔒 Скрыто</b>"
    bank_display = f"<b>{bank:,}</b> лир" if (h_bank == 0 or is_owner) else "<b>🔒 Скрыто</b>"
    
    max_l = LEVELS[lv]["limit"]
    remains = max(0, max_l - used)
    limit_val = f"<b>{remains:,}</b>" if lv < 10 else "<b>Безлимит</b>"

    text = (
        f"👤 <b>ПРОФИЛЬ ИГРОКА</b>\n\n"
        f"🎭 Ник: <b>{name}</b>\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"📝 Описание: <b>{bio}</b>\n\n"
        f"💰 <b>ФИНАНСЫ</b>\n"
        f"├ 💰 Баланс: {bal_display}\n"
        f"├ 🏦 Банк: {bank_display}\n"
        f"├ ⭐ LVL лимита: <b>{lv}</b>\n"
        f"├ 💳 Лимит: {limit_val} лир\n"
        f"└ 🔒 Кошелёк: <b>{'Закрыт' if h_bal == 1 else 'Открыт'}</b>\n\n"
        f"📈 <b>ПРОГРЕСС</b>\n"
        f"└ 🫡 Репутация: <b>{rep}</b>\n\n"
        f"📅 Регистрация: <b>{reg}</b>"
    )
    await m.reply(text, parse_mode="HTML")
    

# Изменить описание
@dp.message(F.text.lower().startswith("+описание "))
async def set_bio(m: types.Message):
    new_bio = m.text[10:].strip()
    if len(new_bio) > 100: return await m.reply("❌ Описание слишком длинное (макс 100 симв.)")
    cur.execute("UPDATE users SET bio = ? WHERE uid = ?", (new_bio, m.from_user.id))
    conn.commit()
    await m.reply("✅ Описание успешно обновлено!")

# Скрыть/Показать баланс или банк
@dp.message(F.text.lower().startswith("скрыть "))
async def hide_info(m: types.Message):
    what = m.text.lower().split()[1]
    col = "hide_bal" if what == "б" else "hide_bank" if what == "банк" else None
    if not col: return
    
    cur.execute(f"UPDATE users SET {col} = 1 WHERE uid = ?", (m.from_user.id,))
    conn.commit()
    await m.reply(f"🔒 Вы скрыли свой {what} в профиле!")

@dp.message(F.text.lower().startswith("открыть ")) # Доп. функция для возврата
async def show_info(m: types.Message):
    what = m.text.lower().split()[1]
    col = "hide_bal" if what == "б" else "hide_bank" if what == "банк" else None
    if not col: return
    
    cur.execute(f"UPDATE users SET {col} = 0 WHERE uid = ?", (m.from_user.id,))
    conn.commit()
    await m.reply(f"🔓 Ваш {what} снова виден всем!")

@dp.message((F.text.lower().startswith("+реп")) | (F.text.lower().startswith("-реп")))
async def change_rep(m: types.Message):
    if not m.reply_to_message: return await m.reply("❌ Ответьте на сообщение игрока!")
    if m.reply_to_message.from_user.id == m.from_user.id: return await m.reply("❌ Нельзя менять репутацию себе!")
    
    try:
        val = int(m.text.split()[1])
        if val < 1 or val > 150: return await m.reply("❌ Сумма репутации должна быть от 1 до 150!")
    except: return await m.reply("❌ Формат: `+реп 50` или `-реп 50`")

    sign = 1 if "+реп" in m.text.lower() else -1
    total_change = val * sign
    
    cur.execute("UPDATE users SET reputation = reputation + ? WHERE uid = ?", (total_change, m.reply_to_message.from_user.id))
    conn.commit()
    
    status = "повысил" if sign > 0 else "понизил"
    await m.answer(f"🫡 Вы {status} репутацию игроку на **{val}**!")

import re

# Вспомогательная функция (оставляем без изменений, она работает хорошо)
def parse_amount(text, user_bal):
    text = text.lower().replace('к', '000').replace('k', '000').replace(',', '').replace(' ', '')
    if text in ["все", "всё", "all"]:
        return user_bal
    if text.endswith('%'):
        try:
            pct = int(text.replace('%', ''))
            return int(user_bal * pct / 100)
        except:
            return 0
    try:
        return int(text)
    except:
        return -1

@dp.message(F.text.lower().startswith("банк"))
async def bank_handler(m: types.Message):
    u = get_u(m.from_user.id, m.from_user.full_name)
    uid = u[0]
    user_balance = u[2]
    
    cur.execute("SELECT bank FROM users WHERE uid = ?", (uid,))
    user_bank = cur.fetchone()[0]

    args = m.text.split()

    # 1. Просто команда "банк" — показываем баланс
    if len(args) == 1:
        return await m.reply(
            f"🏦 <b>Ваш банковский счёт</b>\n\n"
            f"💰 В хранилище: <b>{user_bank:,}</b> лир\n\n"
            f"ℹ️ Чтобы положить: <code>банк положить [сумма]</code>\n"
            f"ℹ️ Чтобы снять: <code>банк снять [сумма]</code>",
            parse_mode="HTML"
        )

    # Проверяем, что есть действие и сумма
    if len(args) < 3:
        return await m.reply("❌ <b>Используйте:</b> <code>банк положить/снять [сумма]</code>", parse_mode="HTML")

    action = args[1].lower()
    amount_raw = args[2]

    try:
        limit = user_balance if action in ["положить", "внести", "депозит"] else user_bank
        amount = parse_amount(amount_raw, limit)
        
        if amount == -1:
            return await m.reply("❌ <b>Ошибка! Введите сумму числом или напишите 'все'.</b>", parse_mode="HTML")
        if amount <= 0:
            return await m.reply("❌ <b>Сумма должна быть больше 0!</b>", parse_mode="HTML")
    except:
        return await m.reply("❌ <b>Произошла ошибка при расчете суммы.</b>", parse_mode="HTML")

    # 2. Логика "банк положить"
    if action in ["положить", "внести", "депозит"]:
        if user_balance < amount:
            return await m.reply(f"❌ У вас на руках только <b>{user_balance:,}</b> лир.", parse_mode="HTML")
        
        upd_bal(uid, -amount)
        cur.execute("UPDATE users SET bank = bank + ? WHERE uid = ?", (amount, uid))
        conn.commit()
        
        await m.reply(f"✅ Вы успешно положили в банк <b>{amount:,}</b> лир.", parse_mode="HTML")

    # 3. Логика "банк снять"
    elif action in ["снять", "вывести"]:
        if user_bank < amount:
            return await m.reply(f"❌ В банке недостаточно средств (у вас там <b>{user_bank:,}</b> лир).", parse_mode="HTML")
        
        cur.execute("UPDATE users SET bank = bank - ? WHERE uid = ?", (amount, uid))
        upd_bal(uid, amount)
        conn.commit()
        
        await m.reply(f"✅ Вы успешно сняли из банка <b>{amount:,}</b> лир.", parse_mode="HTML")
    
    else:
        await m.reply("❌ <b>Неизвестная операция. Используйте 'положить' или 'снять'.</b>", parse_mode="HTML")
        
@dp.message((F.text == "🏆 Чемпионы дня") | (F.text.lower() == "чд"))
async def top_champions_day(m: types.Message):
    user_id = m.from_user.id

    # Проверка колонок
    columns_info = db_query("PRAGMA table_info(users)")
    column_names = [col[1] for col in columns_info]
    id_col = next((c for c in ['user_id', 'id', 'uid'] if c in column_names), 'id')

    # Получаем ТОП-5 по чистой прибыли
    rows = db_query(
        f"SELECT name, daily, {id_col} FROM users WHERE daily > 0 ORDER BY daily DESC LIMIT 5"
    )

    text = "✨ <b>СУПЕР ЛИДЕРЫ ДНЯ</b> ✨\n\n"

    if not rows:
        text += "<i>📊 Сегодня прибыли ещё не было...</i>\n"
    else:
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, row in enumerate(rows):
            name, profit, uid = row
            # Ссылка на аккаунт через http://t.me/@id<uid>
            profile_link = f"http://t.me/@id{uid}"
            text += f'“{medals[i]} <a href="{profile_link}"><b>{name}</b></a> | <b>+{profit:,} лир</b>”\n\n'

    # Призы внизу как цитата
    prizes_text = (
        '“<b>🥇 1 место — 100,000 лир</b>\n'
        '<b>🥈 2 место — 80,000 лир</b>\n'
        '<b>🥉 3 место — 60,000 лир</b>\n'
        '<b>4️⃣ 4 место — 40,000 лир</b>\n'
        '<b>5️⃣ 5 место — 20,000 лир</b>”\n'
    )

    text += prizes_text

    # Отправляем реплаем к сообщению
    await m.reply(text, parse_mode="HTML", disable_web_page_preview=False)
    
from aiogram import types
from aiogram.utils.keyboard import InlineKeyboardBuilder
import random
from datetime import datetime, timedelta
import asyncio

from datetime import datetime, timedelta

from aiogram.utils.keyboard import InlineKeyboardBuilder
import random
from datetime import datetime, timedelta

FRUITS = ["🍏","🍎","🍐","🍊","🍋","🥭","🍍","🥥","🥝",
          "🍅","🍆","🥑","🥦","🥬","🥒","🌶️","🫑","🌽",
          "🍌","🍉","🍇","🍓","🫐","🍈","🍒","🍑"]

@dp.message(lambda m: m.text and m.text.lower() in ["🎁 бонус", "бонус"])
async def bonus_cmd(m: types.Message):
    if m.chat.type != "private":
        kb = InlineKeyboardBuilder()
        kb.button(text="Перейти в ЛС бота", url=f"https://t.me/{(await bot.me()).username}")
        kb.adjust(1)
        return await m.reply(
            "📛 Бонус можно получить только в ЛС бота!",
            reply_markup=kb.as_markup()
        )

    u = get_u(m.from_user.id, m.from_user.full_name)
    now = datetime.now()
    
    # Проверка на КД 24 часа
    if u[7]:
        last_bonus_time = datetime.strptime(u[7], "%Y-%m-%d %H:%M:%S")
        if last_bonus_time + timedelta(hours=24) > now:
            remaining = (last_bonus_time + timedelta(hours=24)) - now
            hours = remaining.seconds // 3600
            minutes = (remaining.seconds // 60) % 60
            return await m.reply(f"❌ Вы уже забирали бонус!\nПриходите через **{hours}ч. {minutes}мин.**")

    # --- Создаём поле 5x5 ---
    kb = InlineKeyboardBuilder()
    selected_symbols = random.choices(FRUITS, k=25)
    for i, sym in enumerate(selected_symbols):
        kb.button(text=sym, callback_data=f"play_bonus:{m.from_user.id}")
    kb.adjust(5)

    await m.reply(
        "🎁 Ваш ежедневный бонус готов!\nВыберите любую кнопку на поле 5x5:",
        reply_markup=kb.as_markup()
    )


@dp.callback_query(lambda c: c.data.startswith("play_bonus"))
async def play_bonus_cb(c: types.CallbackQuery):
    user_id = int(c.data.split(":")[1])
    
    # Проверяем, что тот же пользователь нажал
    if c.from_user.id != user_id:
        return await c.answer("❌ Это не ваш бонус!", show_alert=True)

    u = get_u(c.from_user.id, c.from_user.full_name)
    now = datetime.now()

    # --- Проверка на КД ещё раз ---
    if u[7]:
        last_bonus_time = datetime.strptime(u[7], "%Y-%m-%d %H:%M:%S")
        if last_bonus_time + timedelta(hours=24) > now:
            return await c.answer("❌ Вы уже забрали бонус!", show_alert=True)

    # Генерируем бонус
    gift = random.randint(3000, 25000)
    upd_bal(u[0], gift)

    # Обновляем БД
    cur.execute("UPDATE users SET bonus = ? WHERE uid = ?", (now.strftime("%Y-%m-%d %H:%M:%S"), u[0]))
    conn.commit()

    # Редактируем сообщение красиво с цитатой
    text = (
        "<blockquote>"
        f"🎁 {get_link(u)}, вы получили ежедневный бонус <b>{gift:,}</b> лир!\n"
        "</blockquote>"
        "✅ Бонус успешно получен!"
    )
    await c.message.edit_text(text, parse_mode="HTML")
    await c.answer()

import time
from aiogram import types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- КОМАНДА ПОМОЩЬ ---
@dp.message(F.text.lower().in_(["📍 помощь", "помощь"]))
async def help_cmd(m: types.Message):
    user_id = m.from_user.id
    user_name = m.from_user.first_name
    
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(text="🕹️ Игровой зал", callback_data=f"lira_help_games_{user_id}"))
    kb.row(types.InlineKeyboardButton(text="💎 Базовые команды", callback_data=f"lira_help_base_{user_id}"))
    kb.row(types.InlineKeyboardButton(text="📞 Связь с нами", callback_data=f"lira_help_contact_{user_id}"))

    help_text = (
        f"<b>🆘 Меню помощи — Lira Game</b>\n\n"
        f"Привет, <b>{user_name}</b>! Чтобы не запутаться в командах, выбери нужный раздел с помощью кнопок ниже 👇"
    )
    
    await m.reply(help_text, reply_markup=kb.as_markup(), parse_mode="HTML")

# --- ОБРАБОТЧИК КНОПОК ПОМОЩИ ---
@dp.callback_query(F.data.startswith("lira_help_"))
async def help_callback(call: types.CallbackQuery):
    data_parts = call.data.split("_")
    if len(data_parts) < 4: return
        
    section = data_parts[2]
    owner_id = int(data_parts[3])

    if call.from_user.id != owner_id:
        return await call.answer("❌ Это не ваше меню! Введите «помощь», чтобы открыть своё.", show_alert=True)

    kb = InlineKeyboardBuilder()
    back_btn = types.InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=f"lira_help_back_{owner_id}")
    text = ""

    if section == "games":
        text = (
    "🕹️ <b>Игровой зал</b>\n"
    "<i>Играй и зарабатывай лиры:</i>\n\n"
    "<blockquote>"
    "🎡 <b>Х50</b> — Ставки на множители\n"
    "💣 <b>Мины</b> — Не подорвись на поле\n"
    "🗼 <b>Башня</b> — Не падай мину\n"
    "🧮 <b>Хл</b> — Угадай карту выше/ниже\n"
    "🐊 <b>Охота</b> — Добывай трофеи\n"
    "🪙 <b>Флип</b> — Орел или решка\n"
    "🏀 <b>Баскетбол</b> — Игра с смайлик\n"
    "⚽️ <b>Футбол</b> — Игра с смайлик\n"
    "🎳 <b>Боулинг</b> — Игра с смайлик\n"
    "🎰 <b>Спин</b> — Игра с смайлик\n"
    "🔫 <b>Рул</b> — Классический азарт\n"
    "🧩 <b>Джекпот</b> — Куш для счастливчика\n"
    "🎢 <b>Оверго</b> — Игра с коэффициент\n"
    "🏴‍☠️ <b>Пират</b> — Угадай безопасный\n"
    "🧧 <b>Колесо</b> — Рискуй\n"
    "⚠️ <b>Вилин</b> — Все или ничего\n"
    "🃏 <b>Блэкджек</b> — Играй с диллером\n"
    "🌉 <b>Мосты</b> — Сделай безопасный шаг"
    "</blockquote>"
)
    
    elif section == "base":
          text = (
        "<blockquote>"
        "💎 <b>Базовые команды</b>\n"
        "Основные возможности аккаунта и чата\n\n"

        "💰 <b>Б</b> — Твой баланс\n"
        "🏦 <b>Банк</b> — Баланс в хранилище\n"
        "🤝 <b>Дать [сумма]</b> — Перевод (на ответ игрока)\n"
        "🏆 <b>Чд</b> — Лидеры дня\n\n"

        "🏛 <b>Казна</b> — Баланс казны чата\n"
        "📥 <b>Казна пополнить [сумма]</b> — Взнос в казну\n"
        "🎁 <b>Казна приз [сумма]</b> — Сменить награду\n\n"

        "👤 <b>Профиль</b> — Твоя карточка\n"
        "🎡 <b>Дроп</b> — История игры X50\n"
        "🎰 <b>Лог</b> — История игры Рулетка\n\n"

        "🙈 <b>Скрыть б</b> — Скрыть баланс от других\n"
        "🙉 <b>Скрыть банк</b> — Скрыть банк от других\n\n"

        "✏️ <b>+Ник [текст]</b> — Добавить ник в боте\n"
        "🪪 <b>Ник</b> — Показ ника\n"
        "🎟 <b>Промо [код]</b> — Активировать промокод\n"
        "📝 <b>+Описание [текст]</b> — Описание профиля\n\n"

        "👍 <b>+Реп</b> — Дать репутацию (на ответ)\n"
        "👎 <b>-Реп</b> — Снять репутацию (на ответ)\n"
        "👑 <b>Чд</b> — Чемпионы дня\n\n"
        
        "💝 <b>Халява</b> — Ежедневный розыгрыш\n"
        "🎁 <b>Бонус</b> — Забрать бонус\n"
        "🔮 <b>Шар [текст]</b> — Рандомный ответ\n"
        "🎲 <b>Шанс [текст]</b> — Рандомный шанс\n"
        "⚖️ <b>Выбери [текст] или [текст]</b> — Рандомный выбор\n\n"

        "⏰ <b>Время</b> — Время в 5 странах\n"
        "📈 <b>Уровень</b> — Ваш уровень\n"
        "🛒 <b>КУровень</b> — Купить уровень\n"
        "🤖 <b>Бот</b> — Проверка работы бота\n\n"

        "⭐ <b>Донат [сумма]</b> — Донат звёздами (ЛС бота)\n"
        "💵 <b>Крипто [сумма]</b> — Донат в $ (ЛС бота)"
        "</blockquote>"
    )

    elif section == "contact":
        text = (
            "📞 <b>Связь с нами</b>\n\n"
            "📢 <b>Новости:</b> @LiraGameNews\n"
            "👥 <b>Игровой чат:</b> @Lirachatik\n"
            "👨‍💻 <b>Разработчик:</b> @ren1ved\n"
        )

    elif section == "back":
        kb.row(types.InlineKeyboardButton(text="🕹️ Игровой зал", callback_data=f"lira_help_games_{owner_id}"))
        kb.row(types.InlineKeyboardButton(text="💎 Базовые команды", callback_data=f"lira_help_base_{owner_id}"))
        kb.row(types.InlineKeyboardButton(text="📞 Связь с нами", callback_data=f"lira_help_contact_{owner_id}"))
        
        await call.message.edit_text(
            f"<b>🆘 Меню помощи — Lira Game</b>\n\nВыбери раздел:", 
            reply_markup=kb.as_markup(), 
            parse_mode="HTML"
        )
        return await call.answer()

    kb.row(back_btn)
    try:
        await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except Exception:
        pass
    
    await call.answer()

@dp.message(F.text == "➕ Добавить")
async def add_bot_to_chat(m: types.Message):
    # Создаем инлайн-кнопку со ссылкой
    kb = InlineKeyboardBuilder()
    kb.row(types.InlineKeyboardButton(
        text="➕ Добавить в чат", 
        url="https://t.me/LiraGame_Bot?startgroup=0")
    )
    
    # Отправляем сообщение
    await m.answer(
        "🤖 **Добавьте бота в чат!**\n\n"

             "Чтобы начать играть с друзьями, нажмите кнопку ниже и выберите свою группу. "
        "Не забудьте выдать боту права администратора.",
        reply_markup=kb.as_markup(),
        parse_mode="Markdown"
    )

# --- ЛОГИКА ОВЕРГО (ОБЛЕГЧЕННАЯ ВЕРСИЯ) ---

import random
import asyncio

@dp.message(F.text.lower().startswith("оверго"))
async def game_overgo(m: types.Message):
    user_id = m.from_user.id
    user_name = m.from_user.first_name
    u = get_u(user_id, m.from_user.full_name)
    args = m.text.split()
    
    # Проверка аргументов
    if len(args) < 3:
        return await m.reply(
            "📖 <b>Формат:</b> Оверго [ставка] [коэф]\n"
            "Пример: <code>Оверго 100 2.5</code>", 
            parse_mode="HTML"
        )
    
    bet = parse_bet(args[1], u[2])
    try:
        target_coef = float(args[2].replace(",", "."))
    except ValueError:
        return await m.reply("❌ Укажите корректный <b>коэффициент</b>!", parse_mode="HTML")

    if bet < 100: 
        return await m.reply("❌ Минимальная ставка — <b>100</b> лир!", parse_mode="HTML")
    if u[2] < bet:
        return await m.reply("❌ У вас недостаточно лир!", parse_mode="HTML")
    if target_coef <= 1.0: 
        return await m.reply("❌ Коэффициент должен быть выше <b>1.0</b>!", parse_mode="HTML")

    # --- СБАЛАНСИРОВАННЫЙ ШАНС (RTP) ---
    if random.random() < 0.05:  # 5% шанс на быстрый слив
        crash_point = round(random.uniform(1.01, 1.10), 2)
    else:
        r = random.random()
        if r == 0: r = 0.01 
        crash_point = round(0.96 / r, 2)
        
        if crash_point > 50: 
            crash_point = round(random.uniform(10, 50), 2)

    # Эффект ожидания
    await m.bot.send_chat_action(m.chat.id, "typing")
    await asyncio.sleep(2.0) 

    if crash_point >= target_coef:
        # ✅ ПОБЕДА
        win_total = int(bet * target_coef)
        
        # Начисляем чистый выигрыш (win_total - bet), так как ставку мы не списывали заранее
        upd_bal(user_id, win_total - bet)
        
        # Обновляем ежедневную статистику выигрышей
        cur.execute("UPDATE users SET daily = daily + ? WHERE uid = ?", (win_total, user_id))
        conn.commit()
        
        # Запись в глобальные логи (is_win = 1)
        log_game_db(user_id, user_name, "ОверГо", target_coef, win_total, 1)
        
        status = "✅ <b>Победа!</b>"
        result_val = f"💰 Вы выиграли: <b>{win_total:,}</b> лир"
    else:
        # 💥 ПОРАЖЕНИЕ
        upd_bal(user_id, -bet)
        
        # Запись в глобальные логи (is_win = 0)
        log_game_db(user_id, user_name, "ОверГо", 0, bet, 0)
        
        status = "💥 <b>Поражение</b>"
        result_val = f"📉 Вы проиграли: <b>{bet:,}</b> лир"

    text = (
        f"🎢 <b>Игра: ОверГо</b>\n\n"
        f"<blockquote>"
        f"📈 Ваш прогноз: <b>x{target_coef}</b>\n"
        f"📉 График упал на: <b>x{crash_point}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"{status}\n"
        f"{result_val}"
        f"</blockquote>"
    )

    await m.reply(text, parse_mode="HTML") 

    
# Глобальная переменная для хранения активной викторины
active_vik = {
    "is_active": False,
    "amount": 0,
    "question": "",
    "answer": ""
}

# --- ИГРА ПИРАТ ---
@dp.message(F.text.lower().startswith("пират"))
async def pirate_start(m: types.Message, state: FSMContext):
    data = await state.get_data()

    # 🔴 Активная игра — отправляем реплай с хэштегом
    if data.get("type") == "pirate" and not data.get("finished"):
        await m.reply(
            "#Активная_игра\n" + data["text"],
            reply_markup=data["kb"],
            parse_mode="HTML",
            reply_to_message_id=m.message_id
        )
        return

    u = get_u(m.from_user.id, m.from_user.full_name)
    args = m.text.split()
    bet = parse_bet(args[1] if len(args) > 1 else "0", u[2])

    if bet < 100:
        return await m.reply("❌ Ставка от <b>100</b> лир!", parse_mode="HTML")
    if u[2] < bet:
        return await m.reply("❌ Недостаточно лир!", parse_mode="HTML")

    treasures = 2 if len(args) > 2 and args[2] == "2" else 1
    coef = 1.44 if treasures == 2 else 2.88

    upd_bal(u[0], -bet)

    kb = InlineKeyboardBuilder()
    for i in range(1, 4):
        kb.button(text=f"💀 {i}", callback_data=f"pirate:{i}:{treasures}:{bet}:{m.from_user.id}")
    kb.button(text="🤖 Авто-выбор", callback_data=f"pirate:auto:{treasures}:{bet}:{m.from_user.id}")
    kb.adjust(3, 1)

    text = (
        "⚓️ Игра <b>Brawl Pirate</b>!\n\n"
        "<blockquote>"
        f"💰 Ставка: <b>{bet:,}</b> лир\n"
        f"🎁 Сокровищ: <b>{treasures}</b> (Коэффициент: <b>x{coef}</b>)\n"
        "</blockquote>\n"
        "💀 <b>Выберите 1 из 3 черепов:</b>"
    )

    msg = await m.reply(text, reply_markup=kb.as_markup(), parse_mode="HTML", reply_to_message_id=m.message_id)

    await state.set_data({
        "type": "pirate",
        "finished": False,
        "text": text,
        "kb": kb.as_markup(),
        "user_id": m.from_user.id
    })


@dp.callback_query(F.data.startswith("pirate:"))
async def pirate_callback(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    if not data or data.get("type") != "pirate" or data.get("finished"):
        return await call.answer("⏳ Игра уже завершена", show_alert=False)

    _, choice, treasures, bet, user_id = call.data.split(":")
    treasures = int(treasures)
    bet = int(bet)
    user_id = int(user_id)

    if call.from_user.id != user_id:
        return await call.answer("Это не твоя игра! 🏴‍☠️", show_alert=True)

    await state.update_data(finished=True)
    await call.answer()

    if choice == "auto":
        choice = random.randint(1, 3)
    else:
        choice = int(choice)

    is_win = random.random() < (treasures / 3)
    coef = 1.44 if treasures == 2 else 2.88

    if is_win:
        win_total = int(bet * coef)
        upd_bal(user_id, win_total)
        result_icon = "💎"
        result_title = "Вы нашли сокровище!"
        result_amount = f"🏆 Выигрыш: <b>{win_total:,}</b> лир"
    else:
        result_icon = "💀"
        result_title = "Там было пусто..."
        result_amount = f"📉 Проигрыш: <b>{bet:,}</b> лир"

    text = (
        f"{result_icon} <b>{result_title}</b>\n\n"
        "<blockquote>"
        f"🎰 Выбор пал на: <b>череп №{choice}</b>\n"
        f"📈 Коэффициент: <b>x{coef}</b>\n"
        f"{result_amount}"
        "</blockquote>"
    )

    await call.message.edit_text(text, reply_markup=None, parse_mode="HTML")
    await state.clear()


@dp.message(F.text.lower().startswith(("шар", "вероятность")))
async def magic_ball(m: types.Message):
    answers = [
        "🔮 Я думаю — <b>Нет</b>",
        "🔮 Мне кажется — <b>Нет</b>",
        "🔮 Думаю — <b>Да</b>",
        "🔮 Знаки говорят — <b>Да</b>",
        "🔮 Вероятность крайне мала",
        "🔮 Скорее всего — <b>Да</b>",
        "🔮 Звезды говорят — <b>Нет</b>",
        "🔮 Определенно — <b>Да</b>"
    ]
    await m.reply(random.choice(answers), parse_mode="HTML")

@dp.message(F.text.lower().startswith("шанс"))
async def chance_cmd(m: types.Message):
    # Генерируем случайное число от 1 до 100
    percent = random.randint(1, 100)
    
    # Формируем текст строго по твоему запросу
    text = f"🎱 <b>Шанс этого {percent}%</b>"
    
    # Отвечаем реплаем на сообщение пользователя
    await m.reply(text, parse_mode="HTML")

import re
import random
import time
import sqlite3
from aiogram import types, F

# --- 1. РАБОТА С БАЗОЙ ДАННЫХ ---
def db_query(query, params=(), commit=False, fetchone=False):
    conn = sqlite3.connect("lira_ultimate_v2.db")
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        if commit: conn.commit()
        if fetchone: return cur.fetchone()
        return cur.fetchall()
    finally:
        conn.close()

def log_roulette_result(num, emoji):
    db_query("CREATE TABLE IF NOT EXISTS roulette_history (id INTEGER PRIMARY KEY, number INTEGER, color_emoji TEXT)", commit=True)
    db_query("INSERT INTO roulette_history (number, color_emoji) VALUES (?, ?)", (num, emoji), commit=True)
    db_query("DELETE FROM roulette_history WHERE id NOT IN (SELECT id FROM roulette_history ORDER BY id DESC LIMIT 10)", commit=True)

# --- 2. НАСТРОЙКИ ---
RED_NUMS = [1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36]
BLACK_NUMS = [2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35]

VALID_TYPES = {
    'к': 'красное', 'красное': 'красное', 'ч': 'черное', 'черное': 'черное',
    'з': 'зеро', 'зеро': 'зеро', '0': 'зеро', 'чет': 'чет', 'евен': 'чет',
    'нечет': 'нечет', 'одд': 'нечет', 'м': '1-18', 'б': '19-36'
}

roulette_games = {}

def get_mention(uid, name):
    """Генерирует синее кликабельное имя"""
    return f'<b><a href="tg://user?id={uid}">{name}</a></b>'

# --- 3. ОБРАБОТКА СТАВКИ ---
@dp.message(F.text.lower().startswith("рул"))
async def roulette_handler(m: types.Message):
    # Исправленный вызов get_u: передаем и ID, и Имя
    u = get_u(m.from_user.id, m.from_user.full_name) 
    args = m.text.lower().split()
    cid = m.chat.id

    if len(args) > 1 and args[1] in ["отмена", "cancel"]:
        if cid in roulette_games and u[0] in roulette_games[cid]['players']:
            total_return = sum(b['bet'] for b in roulette_games[cid]['players'][u[0]])
            upd_bal(u[0], total_return)
            del roulette_games[cid]['players'][u[0]]
            return await m.reply(f"✅ {get_mention(u[0], u[1])}, ставки аннулированы. Возвращено: <b>{total_return:,}</b> лир.", parse_mode="HTML")
        return await m.reply("❌ У вас нет активных ставок.")

    if len(args) < 3:
        return await m.reply("🎰 <b>РУЛЕТКА</b>\n\n📝 <code>рул [сумма] [тип]</code>\nПример: <code>рул 100 к</code>", parse_mode="HTML")

    target = args[2]
    is_valid_word = target in VALID_TYPES
    is_valid_numbers = re.fullmatch(r'^(\d{1,2},?)+$', target)

    if not (is_valid_word or is_valid_numbers):
        return await m.reply(f"❌ Тип <code>{target}</code> не распознан.")

    try:
        amount = parse_bet(args[1], u[2])
    except: return

    if amount < 100: return await m.reply("❌ Минимум 100 лир!")
    if u[2] < amount: return await m.reply("❌ Недостаточно лир!")

    if cid not in roulette_games:
        roulette_games[cid] = {'players': {}, 'start_time': time.time(), 'is_spinning': False}
    
    if u[0] not in roulette_games[cid]['players']:
        # Сохраняем имя сразу, чтобы потом не вызывать get_u с ошибкой
        roulette_games[cid]['players'][u[0]] = {'name': u[1], 'bets': []}

    roulette_games[cid]['players'][u[0]]['bets'].append({'bet': amount, 'target': target})
    upd_bal(u[0], -amount)

    await m.reply(
        f"✅ {get_mention(u[0], u[1])} поставил <b>{amount:,}</b> на <code>{target}</code>\n"
        f"🚀 Пиши <b>«го»</b> для запуска! (через 10 сек)", 
        parse_mode="HTML"
    )

# --- 4. ЗАПУСК ИГРЫ (ГО) ---
@dp.message(F.text.lower() == "го")
async def roulette_spin(m: types.Message):
    cid = m.chat.id
    if cid not in roulette_games or not roulette_games[cid]['players']:
        return await m.reply("❌ Ставок еще нет!")
    
    game = roulette_games[cid]
    if game['is_spinning']: return 

    # Проверка 10 секунд
    wait = int(10 - (time.time() - game['start_time']))
    if wait > 0:
        return await m.reply(f"⏳ Рано! Подождите еще <b>{wait}</b> сек.", parse_mode="HTML")

    game['is_spinning'] = True 
    
    res_num = random.randint(0, 36)
    color = "🟢" if res_num == 0 else "🔴" if res_num in RED_NUMS else "⚫️"
    log_roulette_result(res_num, color)

    header = f"🎰 <b>ВЫПАЛО: {res_num} {color}</b>\n━━━━━━━━━━━━━━\n"
    report = ""

    for uid, data in game['players'].items():
        name = data['name']
        win_total = 0
        details = ""
        
        for b in data['bets']:
            t, a = b['target'], b['bet']
            win, mult = False, 2
            
            # Логика типов ставок
            if t in ['к', 'красное'] and res_num in RED_NUMS: win = True
            elif t in ['ч', 'черное'] and res_num in BLACK_NUMS: win = True
            elif t in ['з', 'зеро', '0'] and res_num == 0: win, mult = True, 36
            elif t in ['чет', 'евен'] and res_num != 0 and res_num % 2 == 0: win = True
            elif t in ['нечет', 'одд'] and res_num % 2 != 0: win = True
            elif t == 'м' and 1 <= res_num <= 18: win = True
            elif t == 'б' and 19 <= res_num <= 36: win = True
            elif t.replace(',', '').isdigit():
                nums = [int(x) for x in t.split(',') if x]
                if res_num in nums: win, mult = True, 36 / len(nums)

            if win:
                w_amt = int(a * mult)
                win_total += w_amt
                details += f"  ✅ <code>{t}</code>: +{w_amt:,}\n"
            else:
                details += f"  ❌ <code>{t}</code>: -{a:,}\n"
        
        if win_total > 0:
            upd_bal(uid, win_total)
        
        report += f"👤 {get_mention(uid, name)}\n<blockquote>{details}</blockquote>\n"

    del roulette_games[cid]
    await m.answer(header + report, parse_mode="HTML")

@dp.message(F.text.lower() == "лог")
async def roulette_log(m: types.Message):
    try:
        # Прямой запрос к БД без использования словарей с эмодзи
        rows = db_query("SELECT number, color_emoji FROM roulette_history ORDER BY id DESC LIMIT 10")
        
        if not rows:
            return await m.reply("📜 История игр пока пуста.")
        
        # Формируем строку истории
        history_line = "  ".join([f"<b>{r[0]}</b>{r[1]}" for r in rows])
        await m.reply(f"📃 <b>ПОСЛЕДНИЕ ВЫПАВШИЕ ЧИСЛА:</b>\n\n{history_line}", parse_mode="HTML")
    except Exception as e:
        print(f"Ошибка в логе: {e}")
        await m.reply("❌ Не удалось загрузить историю.")
    
# --- СИСТЕМА КАЗНЫ ---
@dp.message(F.text.lower().startswith("казна"))
async def kazna_commands(m: types.Message):
    args = m.text.lower().split()
    cid = m.chat.id
    user_id = m.from_user.id
    u = get_u(user_id, m.from_user.full_name) # Твоя функция получения юзера

    if len(args) == 1:
        balance, reward = get_kazna(cid)
        text = (
            f"🏛 <b>Казна чата</b>\n━━━━━━━━━━━━━━\n"
            f"💰 Баланс: <b>{balance:,}</b> лир\n"
            f"🎁 Приз за вход: <b>{reward:,}</b> лир\n\n"
            f"📥 <code>казна пополнить [сумма]</code>\n"
            f"⚙️ <code>казна приз [сумма]</code>"
        )
        return await m.reply(text, parse_mode="HTML")

    if args[1] == "пополнить" and len(args) > 2:
        try:
            amount = parse_bet(args[2], u[2]) # Твоя функция парсинга суммы
            if u[2] < amount: return await m.reply("❌ Недостаточно лир!")
            upd_bal(user_id, -amount)
            update_kazna_balance(cid, amount)
            await m.reply(f"✅ Казна пополнена на <b>{amount:,}</b> лир!")
        except: await m.reply("❌ Ошибка при вводе суммы.")

    elif args[1] == "приз" and len(args) > 2:
        member = await m.chat.get_member(user_id)
        if member.status not in ["administrator", "creator"]:
            return await m.reply("❌ Настраивать приз может только администратор!")
        try:
            val = int(args[2])
            set_kazna_reward(cid, val)
            await m.reply(f"✅ Награда за вход установлена: <b>{val:,}</b> лир.")
        except: await m.reply("❌ Введите корректное число.")

# --- АВТОМАТИЧЕСКАЯ ВЫДАЧА ПРИЗА ИЗ КАЗНЫ ---
# --- АВТОМАТИЧЕСКАЯ ВЫДАЧА ПРИЗА ПРИГЛАСИВШЕМУ ---
@dp.message(F.new_chat_members)
async def reward_inviter(m: types.Message):
    cid = m.chat.id
    inviter = m.from_user  # Тот, кто нажал кнопку "Добавить"
    
    # Получаем настройки казны чата
    balance, reward = get_kazna(cid)

    # Если приз не настроен или казна пуста — ничего не делаем
    if reward <= 0 or balance <= 0:
        return

    new_members = m.new_chat_members
    real_new_count = 0

    for user in new_members:
        # 1. Пропускаем ботов
        if user.is_bot:
            continue
        
        # 2. Пропускаем самовступление (если человек зашел по ссылке сам, inviter.id == user.id)
        if inviter.id == user.id:
            continue

        # 3. ПРОВЕРКА НА ПОВТОР (был ли он в этом чате?)
        already_joined = db_query("SELECT 1 FROM joined_users WHERE chat_id = ? AND user_id = ?", 
                                 (cid, user.id), fetchone=True)
        
        if not already_joined:
            # Если раньше не был — записываем его и считаем как нового
            db_query("INSERT INTO joined_users (chat_id, user_id) VALUES (?, ?)", (cid, user.id), commit=True)
            real_new_count += 1

    # Если не добавлено ни одного "нового" человека — выходим
    if real_new_count == 0:
        return

    # Считаем общую сумму
    total_reward = reward * real_new_count

    # Проверка: не разорим ли мы казну больше, чем в ней есть
    if balance < total_reward:
        total_reward = balance

    # Выполняем начисление
    update_kazna_balance(cid, -total_reward)
    upd_bal(inviter.id, total_reward)
    
    # Красивое уведомление
    mention = f'<a href="tg://user?id={inviter.id}">{inviter.first_name}</a>'
    await m.answer(
        f"🤝 {mention}, спасибо за приглашение новичков!\n"
        f"<blockquote>"
        f"💰 Выдано из казны: <b>{total_reward:,}</b> лир\n"
        f"👥 Новых участников: <b>{real_new_count}</b>\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"ℹ️ <i>Награда выдается только за тех, кто ранее не вступал в этот чат.</i>"
        f"</blockquote>",
        parse_mode="HTML"
    )        

import asyncio
import random
from aiogram import types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Хранилище для предотвращения дабл-кликов
active_cube_games = {}

@dp.message(F.text.lower().startswith("кубы"))
async def cubes_start(m: types.Message):
    # Получаем данные отправителя
    u = get_u(m.from_user.id, m.from_user.full_name)
    args = m.text.split()
    
    if not m.reply_to_message:
        return await m.reply("<b>🎲 КУБЫ | МЕНЮ</b>\n━━━━━━━━━━━━━━\n⚠️ <i>Для игры ответьте на сообщение оппонента!</i>", parse_mode="HTML")
    
    target = m.reply_to_message.from_user
    if target.id == m.from_user.id:
        return await m.reply("❌ <b>Ошибка:</b> Нельзя играть с самим собой!", parse_mode="HTML")
    
    # ИСПРАВЛЕНИЕ ОШИБКИ ТУТ: передаем два аргумента в get_u
    t_data = get_u(target.id, target.full_name)

    try:
        bet = parse_bet(args[1] if len(args) > 1 else "0", u[2])
    except:
        return await m.reply("⚠️ <b>Формат:</b> <code>кубы [ставка]</code>", parse_mode="HTML")

    if bet < 100:
        return await m.reply("❌ <b>Минимальная ставка:</b> 100 лир.", parse_mode="HTML")
    if u[2] < bet:
        return await m.reply(f"❌ <b>Недостаточно лир!</b>\nВаш баланс: <code>{u[2]:,}</code>", parse_mode="HTML")

    kb = InlineKeyboardBuilder()
    # Коллбэк в формате: cb_action_creatorID_targetID_bet
    kb.button(text="🤝 Принять вызов", callback_data=f"dice_acc_{m.from_user.id}_{target.id}_{bet}")
    kb.button(text="🚫 Отклонить", callback_data=f"dice_dec_{m.from_user.id}_{target.id}")
    kb.adjust(1)
    
    text = (
        f"<b>🎲 ВЫЗОВ НА ДУЭЛЬ</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 <b>От:</b> {get_link(u)}\n"
        f"🎯 <b>Кому:</b> {get_link(t_data)}\n"
        f"💰 <b>Ставка:</b> <code>{bet:,}</code> лир\n"
        f"━━━━━━━━━━━━━━\n"
        f"<i>Нажмите кнопку ниже, чтобы начать!</i>"
    )
    
    await m.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("dice_"))
async def cubes_callback(call: types.CallbackQuery):
    data = call.data.split("_")
    action = data[1]
    c_id = int(data[2])
    t_id = int(data[3])
    
    # Моментальный ответ, чтобы убрать "часики"
    await call.answer()

    if call.from_user.id not in [c_id, t_id]:
        return await call.answer("✋ Это не ваш вызов!", show_alert=True)

    if action == "dec":
        txt = "❌ <b>Дуэль отменена.</b>"
        return await call.message.edit_text(txt, parse_mode="HTML")

    if action == "acc":
        if call.from_user.id != t_id:
            return await call.answer("⚠️ Только оппонент может принять вызов!", show_alert=True)
        
        # Защита от повторных нажатий
        if call.message.message_id in active_cube_games:
            return
        active_cube_games[call.message.message_id] = True

        bet = int(data[4])
        # Свежие данные из БД
        p1 = get_u(c_id, "User")
        p2 = get_u(t_id, "User")

        if p1[2] < bet or p2[2] < bet:
            active_cube_games.pop(call.message.message_id, None)
            return await call.message.edit_text("⚠️ <b>Ошибка:</b> Недостаточно лир у одного из игроков.")

        # Списание
        upd_bal(c_id, -bet)
        upd_bal(t_id, -bet)

        await call.message.edit_reply_markup(reply_markup=None)
        status = await call.message.edit_text("<b>🎲 Кубики заряжены... Начинаем броски!</b>", parse_mode="HTML")
        
        await asyncio.sleep(2)
        
        # Рандом порядка
        order = [(p1, "Игрок 1"), (p2, "Игрок 2")]
        random.shuffle(order)
        
        # Первый бросок
        await status.edit_text(f"🎲 Свой ход делает <b>{order[0][0][1]}</b>...")
        msg1 = await call.message.answer_dice("🎲")
        v1 = msg1.dice.value
        await asyncio.sleep(4)

        # Второй бросок
        await status.edit_text(f"🎲 Теперь очередь <b>{order[1][0][1]}</b>...")
        msg2 = await call.message.answer_dice("🎲")
        v2 = msg2.dice.value
        await asyncio.sleep(4)

        # Финал
        res = f"<b>📊 РЕЗУЛЬТАТЫ БРОСКОВ</b>\n━━━━━━━━━━━━━━\n"
        res += f"👤 {order[0][0][1]}: <b>{v1}</b>\n"
        res += f"👤 {order[1][0][1]}: <b>{v2}</b>\n"
        res += f"━━━━━━━━━━━━━━\n"

        if v1 == v2:
            upd_bal(c_id, bet)
            upd_bal(t_id, bet)
            res += "🤝 <b>НИЧЬЯ!</b> Все остались при своих."
        else:
            win_u = order[0][0] if v1 > v2 else order[1][0]
            win_sum = int(bet * 1.9)
            upd_bal(win_u[0], win_sum)
            
            # Обновляем ежедневку
            try:
                cur.execute("UPDATE users SET daily = daily + ? WHERE uid = ?", (win_sum, win_u[0]))
                conn.commit()
            except: pass

            res += f"🏆 Победитель: <b>{win_u[1]}</b>\n💰 Выигрыш: <code>{win_sum:,}</code> лир"

        await status.delete()
        await call.message.answer(res, parse_mode="HTML")
        active_cube_games.pop(call.message.message_id, None)
        
import random
import time
from aiogram import types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State


import time

# Словарь для хранения времени последнего клика
last_click_time = {} 
# Кулдаун в секундах (например, 0.8 секунд)
CLICK_CD = 1.5
# ================= НАСТРОЙКИ =================
TOWER_SETTINGS = {
    1: [1.2, 1.5, 1.9, 2.4, 3.0, 3.8, 4.8],
    2: [1.6, 2.7, 4.5, 7.5, 12.0, 20.0, 35.0],
    3: [2.4, 6.0, 15.0, 37.0, 90.0, 220.0, 550.0],
    4: [4.8, 24.0, 120.0, 600.0, 3000.0, 15000.0, 75000.0]
}

ROWS = 7
COLS = 5


active_tower_games = {}


# ================= ОБНОВЛЕННЫЙ РЕНДЕР (С ЗАГОЛОВКОМ АКТИВНОЙ ИГРЫ) =================
async def tower_render(m, game, finished=False, lose_choice=None, is_active_alert=False):
    kb = InlineKeyboardBuilder()
    
    lvl = game["lvl"]
    bombs = game["bombs"]
    history = game["history"]
    b_count = game["b_count"]
    levels = TOWER_SETTINGS[b_count]

    # Рисуем кнопки
    display_rows = ROWS if finished else lvl + 1
    for i in range(display_rows - 1, -1, -1):
        row = []
        for j in range(COLS):
            if finished or i < lvl:
                if j in bombs[i]:
                    text = "💥" if (lose_choice == j and i == lvl) else "💣"
                else:
                    text = "💎" if history.get(i) == j else "☁️"
                row.append(types.InlineKeyboardButton(text=text, callback_data="none"))
            else:
                row.append(types.InlineKeyboardButton(text="❓", callback_data=f"twr_pick_{j}"))
        kb.row(*row)

    if not finished:
        if lvl > 0:
            win_now = int(game["bet"] * levels[lvl - 1])
            kb.row(types.InlineKeyboardButton(text=f"💰 Забрать {win_now:,}", callback_data="twr_take"))
        kb.row(types.InlineKeyboardButton(text="🔄 Автовыбор", callback_data="twr_auto"))

    # Заголовок
    header = "#Активная Игра\n" if is_active_alert else ""
    
    status = "🎮 Выберите ячейку"
    if finished:
        status = f"💥 <b>ПРОИГРЫШ!</b>\nПотеряно: <b>{game['bet']:,}</b>" if lose_choice else f"🏆 <b>ПОБЕДА!</b>\nВыигрыш: <b>{int(game['bet'] * levels[lvl-1]):,}</b>"

    text = (
        f"<b>{header}</b>"
        f"🗼 <b>ИГРА: БАШНЯ</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"👤 Игрок: <b>{m.from_user.first_name}</b>\n"
        f"💣 Мин: <b>{b_count}</b> | 💵 Ставка: <b>{game['bet']:,}</b>\n"
        f"🏔 Этаж: <b>{lvl + 1}/{ROWS}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"{status}"
    )

    try:
        if isinstance(m, types.Message):
            await m.reply(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        else:
            await m.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    except:
        pass
# ================= СТАРТ =================
# ================= СТАРТ =================
# ================= СТАРТ ИГРЫ (С УМНОЙ СТАВКОЙ И ПРОВЕРКОЙ) =================
@dp.message(F.text.lower().startswith("башня"))
async def tower_start(m: types.Message, state: FSMContext):
    uid = m.from_user.id
    
    # 1. ПРОВЕРКА НА АКТИВНУЮ ИГРУ
    current_state = await state.get_state()
    if current_state == GameStates.tower and uid in active_tower_games:
        game = active_tower_games[uid]
        # Показываем, что игра уже идет, и дублируем её вид
        return await tower_render(m, game, is_active_alert=True)

    # 2. ПОЛУЧАЕМ БАЛАНС
    cur.execute("SELECT bal FROM users WHERE uid = ?", (uid,))
    res = cur.fetchone()
    balance = res[0] if res else 0

    # 3. ПАРСИНГ СТАВКИ (К, ВСЕ, ВАБАНК)
    args = m.text.split()
    if len(args) < 2:
        return await m.reply("❓ Пиши: <code>башня [ставка] [мины]</code>\nПример: <code>башня 1к 2</code>", parse_mode="HTML")

    bet_raw = args[1].lower().replace("к", "000").replace("k", "000")
    
    if bet_raw in ["все", "вабанк"]:
        bet = balance
    elif bet_raw.isdigit():
        bet = int(bet_raw)
    else:
        # Для поддержки дробных типа 1.5к
        try:
            if "000" in bet_raw:
                bet = int(float(args[1].lower().replace("к", "").replace("k", "")) * 1000)
            else:
                bet = 0
        except:
            bet = 0

    # 4. ПРОВЕРКИ
    if bet < 100:
        return await m.reply("❌ Минимум 100 лир")
    if balance < bet:
        return await m.reply(f"❌ Недостаточно лир. Баланс: <b>{balance:,}</b>", parse_mode="HTML")

    # 5. МИНЫ
    bombs_count = int(args[2]) if len(args) > 2 and args[2].isdigit() else 1
    bombs_count = min(max(bombs_count, 1), 4)

    # 6. СОЗДАНИЕ ИГРЫ
    upd_bal(uid, -bet)
    bombs = [random.sample(range(COLS), bombs_count) for _ in range(ROWS)]
    
    game = {
        "bet": bet,
        "lvl": 0,
        "bombs": bombs,
        "history": {},
        "b_count": bombs_count
    }

    active_tower_games[uid] = game
    await state.set_state(GameStates.tower)
    await tower_render(m, game)

# ================= ЛОГИКА =================
@dp.callback_query(F.data.startswith("twr_"), GameStates.tower)
async def tower_logic(call: types.CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    now = time.time()

    # --- ПРОВЕРКА КД ---
    if uid in last_click_time:
        diff = now - last_click_time[uid]
        if diff < CLICK_CD:
            # Отвечаем на запрос, чтобы убрать "часики" с кнопки, но ничего не меняем
            return await call.answer(f"⌛ Подождите {CLICK_CD - diff:.1f} сек.", show_alert=False)
    
    # Обновляем время последнего успешного клика
    last_click_time[uid] = now
    # -------------------

    game = active_tower_games.get(uid)
    if not game: 
        await state.clear()
        return await call.answer("Игра завершена или не найдена.")

    lvl = game["lvl"]

    # Кнопка "Забрать"
    if call.data == "twr_take":
        if lvl == 0: 
            return await call.answer("Нужно пройти хотя бы один этаж!", show_alert=True)
        
        win = int(game["bet"] * TOWER_SETTINGS[game["b_count"]][lvl - 1])
        upd_bal(uid, win)
        await tower_render(call, game, finished=True)
        active_tower_games.pop(uid, None)
        last_click_time.pop(uid, None) # Очищаем КД после игры
        await state.clear()
        return await call.answer(f"💰 Забрали {win}!")

    # Кнопка выбора или автовыбор
    if "pick" in call.data or call.data == "twr_auto":
        choice = random.randint(0, 4) if "auto" in call.data else int(call.data.split("_")[-1])
        
        game["history"][lvl] = choice

        # Попал в бомбу
        if choice in game["bombs"][lvl]:
            await tower_render(call, game, finished=True, lose_choice=choice)
            active_tower_games.pop(uid, None)
            last_click_time.pop(uid, None)
            await state.clear()
            return await call.answer("💥 БА-БАХ!")

        # Угадал
        game["lvl"] += 1
        
        if game["lvl"] >= ROWS:
            win = int(game["bet"] * TOWER_SETTINGS[game["b_count"]][ROWS - 1])
            upd_bal(uid, win)
            await tower_render(call, game, finished=True)
            active_tower_games.pop(uid, None)
            last_click_time.pop(uid, None)
            await state.clear()
            return await call.answer("🏆 ГОРУ ПОКОРИЛ!")

        # Если играем дальше
        await tower_render(call, game)
        await call.answer("💎 Чисто!")

# --- КОМАНДЫ СНЯТИЯ БАЛАНСА (ТОЛЬКО ДЛЯ АДМИНА) ---

# 1. Снятие через ответ на сообщение (Реплай)
@dp.message(F.text.lower().startswith("снять "))
async def adm_remove_reply(m: types.Message):
    # 1. Проверка доступа для списка админов
    if m.from_user.id not in ADMIN_ID: 
        return

    # 2. Проверка на реплай
    if not m.reply_to_message:
        return await m.reply("❌ **Ответьте на сообщение игрока, у которого нужно снять лиры!**", parse_mode="Markdown")
    
    try:
        args = m.text.split()
        if len(args) < 2:
            return await m.reply("❌ **Введите сумму или слово 'все'**\nПример: `снять 50к` или `снять все`", parse_mode="Markdown")

        target_uid = m.reply_to_message.from_user.id
        target_name = m.reply_to_message.from_user.full_name
        
        # Получаем данные игрока (u[2] — это баланс)
        u = get_u(target_uid, target_name)
        current_balance = u[2]

        # 3. Обработка суммы
        input_val = args[1].lower()
        if input_val == "все" or input_val == "всё":
            amount = current_balance
        else:
            # Поддержка к, кк, k, kk
            summ_raw = input_val.replace("кк", "000000").replace("kk", "000000").replace("к", "000").replace("k", "000")
            amount = int(summ_raw)

        # 4. Проверки баланса
        if amount <= 0:
            return await m.reply("❌ **Сумма должна быть больше 0!**")
        
        if amount > current_balance:
            amount = current_balance # Забираем всё, что есть, если просят больше
            
        # 5. Списание (передаем отрицательное число в вашу функцию)
        upd_bal(target_uid, -amount)
        
        await m.reply(
            f"📉 **ИЗЪЯТИЕ СРЕДСТВ**\n"
            f"━━━━━━━━━━━━━━\n"
            f"👤 Игрок: **{u[1]}**\n"
            f"💰 Списано: **{amount:,}** лир\n"
            f"━━━━━━━━━━━━━━\n"
            f"Действие выполнил администратор.", 
            parse_mode="Markdown"
        )
        
    except ValueError:
        await m.reply("❌ **Ошибка!** Введите корректную сумму (например: `снять 10к`).", parse_mode="Markdown")
    except Exception as e:
        print(f"Ошибка в команде снять: {e}")
        await m.reply("❌ **Произошла ошибка при выполнении команды.**")
        
# 2. Снятие по ID игрока
@dp.message(F.text.lower().startswith("обнуление "))
async def adm_remove_id(m: types.Message):
    if m.from_user.id != ADMIN_ID: return
    
    try:
        args = m.text.split() # обнулить [id] [сумма]
        target_id = int(args[1])
        u = get_u(target_id)
        
        if args[2].lower() == "все":
            amount = u[2]
        else:
            amount = int(args[2].lower().replace("к", "000").replace("кк", "000000"))
            
        upd_bal(target_id, -amount)
        await m.answer(f"📉 С баланса игрока `{target_id}` снято **{amount:,}** лир!", parse_mode="Markdown")
    except:
        await m.reply("❌ Формат: `обнулить [ID] [сумма/все]`")

from datetime import datetime
import pytz

@dp.message(F.text.lower() == "время")
async def show_city_time(m: types.Message):
    zones = {
        "Киев": "Europe/Kyiv",
        "Москва": "Europe/Moscow",
        "Омск": "Asia/Omsk",
        "Китай": "Asia/Shanghai",
        "Астана": "Asia/Almaty"
    }
    
    text = "•-• <b>Текущее время в:</b>\n\n"
    
    for city, zone in zones.items():
        now = datetime.now(pytz.timezone(zone))
        fmt_time = now.strftime("%d.%m.%Y %H:%M:%S")
        text += f"<b>{city}</b> — <code>{fmt_time}</code>\n"
        
    await m.reply(text, parse_mode="HTML")

@dp.message(Command("admin"))
async def admin_panel(m: types.Message):
    if is_admin(m.from_user.id):
        await m.answer("🔧 **Админ-панель Lira:**", reply_markup=admin_inline(), parse_mode="Markdown")
    else:
        await m.answer("❌ **Доступ запрещен.**")

@dp.message(F.text.lower() == "куровень")
async def buy_level_request(m: types.Message):
    # Узнаем текущий уровень (используем uid или id, проверь как у тебя)
    cur.execute("SELECT level FROM users WHERE uid = ?", (m.from_user.id,))
    res = cur.fetchone()
    u_lv = res[0] if res else 1
    
    if u_lv >= 10:
        return await m.reply("⭐ <b>У вас максимальный уровень!</b>", parse_mode="HTML")

    next_lv = u_lv + 1
    price = LEVELS[next_lv]["price"]
    
    kb = InlineKeyboardBuilder()
    # Сокращенный callback, чтобы не было ошибок длины
    kb.button(text="✅ Купить", callback_data=f"lv_up_{next_lv}_{m.from_user.id}")
    kb.button(text="❌ Отмена", callback_data=f"lv_stop_{m.from_user.id}")
    kb.adjust(2)
    
    await m.reply(
        f"⬆️ <b>ПОВЫШЕНИЕ УРОВНЯ</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"Желаете купить <b>{next_lv} уровень</b>?\n"
        f"💰 Цена: <b>{price:,}</b> лир\n"
        f"📊 Новый лимит: <b>{LEVELS[next_lv]['limit']:,}</b>\n"
        f"━━━━━━━━━━━━━━",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("lv_"))
async def buy_level_callback(call: types.CallbackQuery):
    data = call.data.split("_")
    action = data[1] # up или stop
    owner_id = int(data[-1])

    if call.from_user.id != owner_id:
        return await call.answer("❌ Это не ваше меню!", show_alert=True)

    if action == "stop":
        return await call.message.edit_text("❌ <b>Покупка уровня отменена.</b>", parse_mode="HTML")

    next_lv = int(data[2])
    price = LEVELS[next_lv]["price"]

    # --- ИСПРАВЛЕНИЕ ОШИБКИ ТУТ ---
    # Получаем названия всех колонок в таблице users
    columns = [col[1] for col in db_query("PRAGMA table_info(users)")]
    
    # Ищем, как у тебя называется баланс (bal или balance или money)
    bal_col = next((c for c in ['bal', 'balance', 'money', 'coins'] if c in columns), None)
    
    if not bal_col:
        return await call.answer("❌ Ошибка: колонка баланса не найдена в БД", show_alert=True)

    # Берем баланс игрока из правильной колонки
    cur.execute(f"SELECT {bal_col} FROM users WHERE uid = ?", (call.from_user.id,))
    res = cur.fetchone()
    user_bal = res[0] if res else 0

    if user_bal < price:
        return await call.answer(f"❌ Недостаточно лир! Нужно {price:,}", show_alert=True)
    
    # Списываем баланс и обновляем уровень
    upd_bal(call.from_user.id, -price)
    cur.execute("UPDATE users SET level = ?, used_limit = 0 WHERE uid = ?", (next_lv, call.from_user.id))
    conn.commit()
    
    await call.message.edit_text(
        f"✅ <b>Уровень {next_lv} успешно куплен!</b>\n"
        f"📈 Суточный лимит повышен до <b>{LEVELS[next_lv]['limit']:,}</b>", 
        parse_mode="HTML"
    )    

import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Настройки уровней
LEVELS = {
    1: {"limit": 75000, "price": 0},
    2: {"limit": 125000, "price": 150000},
    3: {"limit": 200000, "price": 250000},
    4: {"limit": 300000, "price": 400000},
    5: {"limit": 750000, "price": 1250000},
    6: {"limit": 1500000, "price": 2000000},
    7: {"limit": 3000000, "price": 5000000},
    8: {"limit": 5000000, "price": 12500000},
    9: {"limit": 15000000, "price": 25000000},
    10: {"limit": 999999999999, "price": 50000000} # Безлимит
}

# Вставь это в init_db, чтобы бот не выдавал ошибку "no such column: level"
try:
    cur.execute("ALTER TABLE users ADD COLUMN level INTEGER DEFAULT 1")
    conn.commit()
except:
    pass

@dp.message(F.text.lower() == "уровень")
async def show_level(m: types.Message):
    cur.execute("SELECT level, used_limit FROM users WHERE uid = ?", (m.from_user.id,))
    res = cur.fetchone()
    
    u_lv = res[0] if res else 1
    u_used = res[1] if res else 0
    
    max_l = LEVELS[u_lv]["limit"]
    remains = max_l - u_used
    if remains < 0: remains = 0
    
    l_text = f"<b>{max_l:,}</b>" if u_lv < 10 else "<b>Безлимит</b>"
    
    await m.reply(
        f"📊 <b>ВАШ СТАТУС</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"⭐ Уровень: <b>{u_lv}</b>\n"
        f"💰 Суточный лимит: {l_text}\n"
        f"📉 Осталось на сегодня: <b>{remains:,}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🔄 Обнуление лимитов в <b>22:00 МСК</b>\n"
        f"🛒 Повысить лимит: <code>куровень</code>",
        parse_mode="HTML"
    )


# --- КЛИЕНТСКАЯ ЧАСТЬ ---

@dp.message(Command("q"), F.chat.type == "private")
async def cmd_q(message: types.Message, state: FSMContext):
    await message.answer("💬 <b>Опишите вашу проблему.</b>\n\nВы можете отправить текст, фото или фото с описанием. Админы рассмотрят ваше обращение.", parse_mode="HTML")
    await state.set_state(SupportStates.waiting_for_report)

@dp.message(SupportStates.waiting_for_report)
async def process_support_report(message: types.Message, state: FSMContext):
    # Создаем кнопки для админа
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="✅ Ответить", callback_data=f"support_ans_{message.from_user.id}"),
        types.InlineKeyboardButton(text="❌ Игнорить", callback_data="support_ignore")
    )
    
    admin_text = f"📩 <b>Новое обращение!</b>\n\n"
    user_info = f"\n\n👤 <b>От:</b> {message.from_user.full_name} (<code>{message.from_user.id}</code>)"
    
    # Отправляем всем админам из вашего конфига (ADMIN_ID)
    for admin_id in ADMIN_ID:
        try:
            if message.photo:
                caption = (message.caption or "<i>[Без текста]</i>") + user_info
                await bot.send_photo(admin_id, message.photo[-1].file_id, caption=caption, reply_markup=kb.as_markup(), parse_mode="HTML")
            else:
                await bot.send_message(admin_id, admin_text + message.text + user_info, reply_markup=kb.as_markup(), parse_mode="HTML")
        except:
            pass

    await message.answer("✅ <b>Ваше сообщение отправлено!</b> Ожидайте ответа от администрации.", parse_mode="HTML")
    await state.clear()

# --- АДМИНСКАЯ ЧАСТЬ ---

@dp.callback_query(F.data.startswith("support_"))
async def admin_support_actions(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_ID:
        return await call.answer("Вы не админ!", show_alert=True)

    if call.data == "support_ignore":
        await call.message.delete()
        return await call.answer("Удалено.")

    user_id = call.data.split("_")[2]
    await call.message.answer(f"✍️ <b>Введите ответ для пользователя</b> {user_id}:")
    await state.set_state(SupportStates.waiting_for_admin_answer)
    await state.update_data(reply_to_user=user_id)
    await call.answer()

@dp.message(SupportStates.waiting_for_admin_answer)
async def send_admin_answer(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_ID: return
    
    data = await state.get_data()
    user_id = data.get("reply_to_user")

    try:
        await bot.send_message(user_id, f"⚠️ <b>Ответ от администрации:</b>\n\n{message.text}", parse_mode="HTML")
        await message.answer(f"✅ Ответ отправлен пользователю <code>{user_id}</code>")
    except Exception as e:
        await message.answer(f"❌ Ошибка при отправке: {e}")
    
    await state.clear()

import random
from aiogram import types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

WIN_CHANCE = 40  # шанс победы в процентах

# --- Состояния игры ---
class VilinStates(StatesGroup):
    confirm = State()


# --- Команда запуска ---
@dp.message(F.text and F.text.lower() == "вилин")
async def vilin_start(m: types.Message, state: FSMContext):
    u = get_u(m.from_user.id, m.from_user.full_name)
    balance = u[2]

    if balance <= 0:
        return await m.reply("❌ У вас 0 лир, играть не на что!")

    win_amount = balance * 2  # выигрыш ровно 2x

    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(text="✅ Принять", callback_data="vilin_accept"),
        types.InlineKeyboardButton(text="❌ Отклонить", callback_data="vilin_decline")
    )

    await m.reply(
        f"🛑 <b>ВНИМАНИЕ!</b>\n\n"
        f"Вы уверены, что хотите сыграть в игру <b>ВСЕ или НИЧЕГО</b>?\n"
        f"Вы можете <b>ПРОИГРАТЬ</b> {balance:,} лир или же <b>ВЫИГРАТЬ</b> {win_amount:,} лир.",
        reply_markup=kb.as_markup(),
        parse_mode="HTML"
    )

    # сохраняем данные в стейт, но не списываем баланс сразу
    await state.set_state(VilinStates.confirm)
    await state.update_data(bet=balance, win=win_amount, user_id=m.from_user.id)


# --- Обработка кнопок ---
@dp.callback_query(F.data.startswith("vilin_"), VilinStates.confirm)
async def vilin_logic(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    # Проверка, что нажал тот же пользователь
    if call.from_user.id != data.get("user_id"):
        return await call.answer("Это не ваша игра!", show_alert=True)

    if call.data == "vilin_decline":
        await call.message.edit_text("🚫 <b>Вы отказались от игры.</b>", parse_mode="HTML")
        await state.clear()
        return await call.answer()

    # --- Нажата кнопка Принять ---
    bet = data.get("bet")
    win_amount = data.get("win")
    
    # проверяем баланс **только при нажатии**
    u = get_u(call.from_user.id, call.from_user.full_name)
    balance = u[2]

    if balance < bet:
        await call.answer("❌ Недостаточно лир для игры!", show_alert=True)
        await call.message.edit_text("❌ У вас недостаточно лир для этой ставки. Пополните баланс.")
        await state.clear()
        return

    # --- Шанс победы ---
    roll = random.randint(1, 100)
    if roll <= WIN_CHANCE:
        # ПОБЕДА
        upd_bal(call.from_user.id, bet)  # начисляем выигрыш (ставка уже в игре)
        await call.message.edit_text(
            f"🎉 Поздравляем! Вы выиграли!\nВаш баланс теперь <b>{win_amount:,}</b> лир!",
            parse_mode="HTML"
        )
    else:
        # ПРОИГРЫШ
        upd_bal(call.from_user.id, -bet)
        await call.message.edit_text(
            f"💀 К сожалению, вы проиграли.\nВаш баланс теперь <b>{u[2] - bet:,}</b> лир!",
            parse_mode="HTML"
        )

    await state.clear()
    await call.answer()





@dp.message(F.text.lower().in_(["гайд колесо", "к помощь"]))
async def wheel_instruction(m: types.Message):
    text = (
        f"🎡 <b>ИНСТРУКЦИЯ: КОЛЕСО ФОРТУНЫ</b>\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"Испытай свою удачу! Ставь лиры и крути колесо, чтобы приумножить свой баланс.\n\n"
        f"📝 <b>Как играть:</b>\n"
        f"Введите: <code>колесо [сумма]</code>\n"
        f"Например: <code>колесо 1000</code>\n\n"
        f"📊 <b>Шансы и Сектора:</b>\n"
        f"🔴 <b>x0</b> — Проигрыш (40%)\n"
        f"⚪️ <b>x0.5</b> — Возврат половины (25%)\n"
        f"🟡 <b>x1.5</b> — Небольшой плюс (15%)\n"
        f"🔵 <b>x2</b> — Удвоение (10%)\n"
        f"🟣 <b>x5</b> — Крупный выигрыш (7%)\n"
        f"💎 <b>x15</b> — ДЖЕКПОТ (3%)\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"⚠️ <i>Минимальная ставка: 100 лир.</i>"
    )
    await m.reply(text, parse_mode="HTML")

@dp.message(F.text.lower() == "сброс лимитов")
async def manual_reset_limits(m: types.Message):
    # 1. Проверка на админа
    if m.from_user.id not in ADMIN_ID:
        return

    # 2. Считаем, у скольких людей лимит был не нулевой (для отчета)
    cur.execute("SELECT COUNT(*) FROM users WHERE used_limit > 0")
    count = cur.fetchone()[0]

    # 3. Обнуляем лимиты в базе
    cur.execute("UPDATE users SET used_limit = 0")
    conn.commit()

    # 4. Красивый ответ
    await m.answer(
        f"⚙️ <b>СИСТЕМНЫЙ СБРОС</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"✅ Лимиты всех игроков успешно обнулены.\n"
        f"👥 Затронуто пользователей: <b>{count}</b>\n"
        f"📅 Время: <b>{datetime.now().strftime('%H:%M:%S')}</b>\n"
        f"━━━━━━━━━━━━━━\n"
        f"🔒 <i>Теперь все снова могут передавать лиры!</i>",
        parse_mode="HTML"
    )

@dp.message(F.text.lower().in_(["обнул все", "эко всё"]))
async def reset_all_balances(m: types.Message):
    if m.from_user.id not in ADMIN_ID:
        return

    try:
        # Получаем список всех колонок в таблице users
        columns_info = db_query("PRAGMA table_info(users)")
        column_names = [col[1] for col in columns_info]

        # Список возможных названий для баланса и банка
        balance_variants = ['balance', 'money', 'coins', 'cash', 'bal']
        bank_variants = ['bank', 'deposit', 'vault']

        # Ищем, какие из них есть в твоей базе
        found_balance = next((c for c in balance_variants if c in column_names), None)
        found_bank = next((c for c in bank_variants if c in column_names), None)

        if not found_balance:
            return await m.reply(f"❌ Ошибка: не удалось найти колонку баланса. Список колонок: {', '.join(column_names)}")

        # Формируем и выполняем запрос обнуления
        query = f"UPDATE users SET {found_balance} = 0"
        if found_bank:
            query += f", {found_bank} = 0"
        
        db_query(query, commit=True)

        # Также обнуляем казну, если таблица существует
        try:
            db_query("UPDATE kazna SET balance = 0", commit=True)
        except:
            pass

        await m.reply(
            "⚠️ <b>ГЛОБАЛЬНЫЙ СБРОС ЭКОНОМИКИ</b>\n\n"
            f"✅ Колонка баланса (<code>{found_balance}</code>) обнулена.\n"
            f"{'✅ Колонка банка (<code>' + found_bank + '</code>) обнулена.' if found_bank else 'ℹ️ Колонка банка не найдена.'}\n"
            "🏛 Казна чатов сброшена.",
            parse_mode="HTML"
        )

    except Exception as e:
        await m.reply(f"❌ Ошибка базы данных: <code>{str(e)}</code>", parse_mode="HTML")

@dp.message(F.text.lower() == "бот")
async def bot_status_minimal(m: types.Message):
    await m.reply(
        "✅ <b>Все стабильно!</b>\n\n"
        "<blockquote>Бот работает в штатном режиме.</blockquote>",
        parse_mode="HTML"
    )

from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# 1. Описываем состояния
class AdminDistribute(StatesGroup):
    waiting_for_amount = State()

# 2. Команда для начала раздачи
@dp.message(F.text.lower() == "раздать всем")
async def start_distribute(m: types.Message, state: FSMContext):
    if m.from_user.id not in ADMIN_ID:
        return
    
    await m.reply("💰 <b>Введите сумму, которую хотите выдать ВСЕМ игрокам:</b>\n\n<i>(Можно использовать 'к', например 50к)</i>", parse_mode="HTML")
    await state.set_state(AdminDistribute.waiting_for_amount)

# 3. Обработка введенной суммы и раздача
@dp.message(AdminDistribute.waiting_for_amount)
async def process_distribute(m: types.Message, state: FSMContext):
    if m.from_user.id not in ADMIN_ID:
        await state.clear()
        return

    try:
        # Парсим сумму (поддерживаем 'к')
        summ_raw = m.text.lower().replace("к", "000").replace("k", "000").replace("м", "000000")
        amount = int(summ_raw)
        
        if amount <= 0:
            return await m.reply("❌ Сумма должна быть больше 0!")

        # Выполняем массовое начисление через SQL
        # Ищем колонку баланса так же, как в коде обнуления
        columns_info = db_query("PRAGMA table_info(users)")
        column_names = [col[1] for col in columns_info]
        balance_col = next((c for c in ['balance', 'money', 'coins', 'bal'] if c in column_names), 'balance')

        db_query(f"UPDATE users SET {balance_col} = {balance_col} + ?", (amount,), commit=True)
        
        # Получаем количество затронутых игроков для отчета
        total_players = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]

        await m.reply(
            "🎁 <b>ГЛОБАЛЬНАЯ РАЗДАЧА</b>\n\n"
            f"<blockquote>"
            f"💰 Каждому выдано: <b>{amount:,}</b> лир\n"
            f"👥 Получателей: <b>{total_players}</b> чел.\n"
            f"━━━━━━━━━━━━━━\n"
            f"✅ Баланс всех игроков успешно обновлен!"
            f"</blockquote>",
            parse_mode="HTML"
        )
        
    except ValueError:
        await m.reply("❌ Ошибка! Введите корректное число или напишите <code>отмена</code>", parse_mode="HTML")
        return # Не сбрасываем состояние, даем попробовать еще раз
    except Exception as e:
        await m.reply(f"❌ Произошла ошибка: {e}")
    
    await state.clear()

# Доп. команда отмены
@dp.message(AdminDistribute.waiting_for_amount, F.text.lower() == "отмена")
async def cancel_distribute(m: types.Message, state: FSMContext):
    await state.clear()
    await m.reply("🚫 Раздача отменена.")

from aiogram.utils.keyboard import InlineKeyboardBuilder

@dp.message(F.text == "/logs")
async def admin_logs_main(m: types.Message):
    if m.from_user.id not in ADMIN_ID:
        return
    await send_logs_page(m, 0)

async def send_logs_page(m, page: int):
    items_per_page = 10
    offset = page * items_per_page
    
    # Запрос последних 100 игр с пагинацией
    cur.execute(
        "SELECT user_name, user_id, game_name, coef, amount, is_win FROM game_logs ORDER BY id DESC LIMIT ? OFFSET ?",
        (items_per_page, offset)
    )
    rows = cur.fetchall()

    if not rows:
        text = "<b>🗄 Логи отсутствуют.</b>"
    else:
        text = f"<b>📜 ГЛОБАЛЬНЫЕ ЛОГИ | Стр. {page + 1}</b>\n"
        text += "━━━━━━━━━━━━━━\n"
        for row in rows:
            name, uid, game, coef, amt, is_win = row
            # Убираем лишние символы из имени для безопасности HTML
            safe_name = str(name).replace("<", "").replace(">", "")
            
            if is_win == 1:
                text += f"👤 {safe_name} (<code>{uid}</code>)\n🎮 <b>[{game}]</b> | 📈 x{coef} | ✅ +{amt:,}\n"
            else:
                text += f"👤 {safe_name} (<code>{uid}</code>)\n🎮 <b>[{game}]</b> | ❌ -{amt:,}\n"
            text += "┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"

    kb = InlineKeyboardBuilder()
    # Кнопки управления
    btns = []
    if page > 0:
        btns.append(types.InlineKeyboardButton(text="⬅️ Назад", callback_data=f"log_step_{page-1}"))
    
    btns.append(types.InlineKeyboardButton(text="🔄 Обновить", callback_data=f"log_step_{page}"))
    
    # Ограничение в 10 страниц (100 игр)
    if len(rows) == items_per_page and page < 9:
        btns.append(types.InlineKeyboardButton(text="Вперед ➡️", callback_data=f"log_step_{page+1}"))
    
    kb.row(*btns)

    if isinstance(m, types.Message):
        await m.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    else:
        try:
            await m.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        except:
            pass

@dp.callback_query(F.data.startswith("log_step_"))
async def log_callback(call: types.CallbackQuery):
    if call.from_user.id not in ADMIN_ID:
        return await call.answer("Доступ запрещен", show_alert=True)
    
    page = int(call.data.split("_")[2])
    await send_logs_page(call, page)
    await call.answer()

#FORTUNA
    import random
import asyncio
from aiogram import types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Настройка секторов (эмодзи, множитель, шанс в весах)
WHEEL_SECTORS = [
    ("🔴", 0, 45),      # Проигрыш (40% шанс)
    ("⚪️", 0.5, 25),    # Возврат половины (25% шанс)
    ("🟡", 1.5, 13),    # Небольшой плюс (15% шанс)
    ("🔵", 2, 9),      # Удвоение (10% шанс)
    ("🟣", 5, 6),       # Пятикратный выигрыш (7% шанс)
    ("💎", 15, 2),      # Джекпот сектора (3% шанс)
]

@dp.message(F.text.lower().startswith("колесо"))
async def wheel_start(m: types.Message):
    if m.chat.id != X50_CHAT_ID: 
        return await m.reply("❌ Игра доступна только в официальном чате!")
    
    u = get_u(m.from_user.id, m.from_user.full_name)
    args = m.text.split()
    
    # Парсим ставку
    bet = parse_bet(args[1] if len(args) > 1 else "0", u[2])
    
    if bet < 100: 
        return await m.reply("❌ Минимальная ставка — <b>100</b> лир!", parse_mode="HTML")
    if u[2] < bet:
        return await m.reply("❌ У вас недостаточно лир!")

    # Списываем ставку
    upd_bal(u[0], -bet)
    
    # Анимация кручения
    msg = await m.reply(
        f"🎡 <b>{u[1]}</b> запускает колесо...\n"
        f"🎰 Ставка: <b>{bet:,}</b> лир\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"🔄 <code>[ 🔴 🔵 🟡 🟣 ⚪️ ]</code>", 
        parse_mode="HTML"
    )
    
    await asyncio.sleep(1.5)
    
    # Выбор результата на основе весов
    sector_icons = [s[0] for s in WHEEL_SECTORS]
    weights = [s[2] for s in WHEEL_SECTORS]
    res_sector = random.choices(WHEEL_SECTORS, weights=weights, k=1)[0]
    
    icon, mult, _ = res_sector
    win_amount = int(bet * mult)
    
    # Если выиграл, зачисляем
    if win_amount > 0:
        upd_bal(u[0], win_amount)

    # Финальный текст как на твоих скринах
    text = f"🎡 <b>КОЛЕСО ФОРТУНЫ</b>\n"
    text += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    text += f"👤 Игрок: <b>{u[1]}</b>\n"
    text += f"💵 Ставка: <b>{bet:,}</b>\n"
    text += f"🎯 Выпало: {icon} (<b>x{mult}</b>)\n"
    text += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    
    if win_amount > bet:
        text += f"✅ <b>ВЫИГРЫШ: {win_amount:,} лир!</b>"
    elif win_amount == bet:
        text += f"⚖️ <b>ВЫШЛИ В НОЛЬ!</b>"
    elif win_amount > 0:
        text += f"⚠️ <b>ЧАСТИЧНЫЙ ВОЗВРАТ: {win_amount:,} лир</b>"
    else:
        text += f"❌ <b>ПРОИГРЫШ! Попробуйте снова.</b>"

    await msg.edit_text(text, parse_mode="HTML")

    

# ================== IMPORTS ==================
import asyncio
import aiohttp
import uuid
import time

from aiogram import types, F
from aiogram.types import LabeledPrice, PreCheckoutQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================== НАСТРОЙКИ ==================

# ⭐ Telegram Stars
STAR_RATE = 20000        # 1 звезда = 8000 лир
MIN_STARS = 10

# 💎 CryptoBot (USDT)
CRYPTO_PAY_TOKEN = "511895:AAxFsCmo9VNfzvXbjWycXqHLtfev2YuMCgC"   # токен из @CryptoBot
CRYPTO_RATE = 1_000_000                       # 1 USDT = 100 000 лир

# 📢 Логи
LOG_CHANNEL_ID = -1003662370565

# ================== ВРЕМЕННОЕ ХРАНИЛИЩЕ ==================
pending_crypto = {}
# invoice_id: { user_id, usdt, lira }

# ================== DONATE STARS ==================

@dp.message(F.text.lower().startswith("донат"))
async def donate_stars(m: types.Message):
    if m.chat.type != "private":
        return await m.reply("❌ Донат доступен только в личных сообщениях с ботом!")

    args = m.text.split()
     
    if len(args) < 2 or not args[1].isdigit():
        return await m.reply(
            "⭐ <b>Донат звездами</b>\n\n"
            "Пример: <code>донат 10</code>",
            parse_mode="HTML"
        )

    stars = int(args[1])
    if stars < MIN_STARS:
        return await m.reply(
            f"❌ Минимум <b>{MIN_STARS} звезд</b>",
            parse_mode="HTML"
        )

    lira = stars * STAR_RATE
    prices = [LabeledPrice(label="Telegram Stars", amount=stars)]

    await m.bot.send_invoice(
        chat_id=m.chat.id,
        title="⭐ Пополнение баланса",
        description=(
            f"⭐ Звезды: {stars}\n"
            f"💰 Начислится: {lira:,} лир\n"
            f"📈 Курс: 1 ⭐ = {STAR_RATE:,} лир"
        ),
        payload=f"stars_{stars}",
        provider_token="",   # ⚠️ ОБЯЗАТЕЛЬНО ПУСТО
        currency="XTR",
        prices=prices,
        reply_to_message_id=m.message_id
    )

# ================== PRE CHECKOUT ==================

@dp.pre_checkout_query()
async def pre_checkout(pre: PreCheckoutQuery):
    await pre.answer(ok=True)

# ================== STARS SUCCESS ==================

@dp.message(F.successful_payment)
async def stars_success(m: types.Message):
    stars = m.successful_payment.total_amount
    lira = stars * STAR_RATE
    uid = m.from_user.id

    upd_bal(uid, lira)

    await m.answer(
        f"✅ <b>Оплата успешна!</b>\n\n"
        f"⭐ Потрачено: <b>{stars}</b>\n"
        f"💰 Начислено: <b>{lira:,}</b> лир",
        parse_mode="HTML"
    )

    await m.bot.send_message(
        LOG_CHANNEL_ID,
        f"⭐ <b>DONATE STARS</b>\n"
        f"👤 UID: <code>{uid}</code>\n"
        f"⭐ {stars}\n"
        f"💰 {lira:,} лир",
        parse_mode="HTML"
    )

# ================== CRYPTO CREATE INVOICE ==================

async def crypto_create_invoice(usdt: float):
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN
    }

    payload = {
        "asset": "USDT",
        "amount": usdt,
        "description": "Пополнение баланса",
        "payload": "donate"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://pay.crypt.bot/api/createInvoice",
            json=payload,
            headers=headers
        ) as r:
            data = await r.json()
            return data["result"]

# ================== DONATE CRYPTO ==================

@dp.message(F.text.lower().startswith("крипто"))
async def donate_crypto(m: types.Message):
    if m.chat.type != "private":
        return await m.reply("❌ Донат доступен только в личных сообщениях с ботом!")

    args = m.text.split()
    if len(args) < 2:
        return await m.reply("Пример: <code>крипто 5</code>", parse_mode="HTML")

    try:
        usdt = float(args[1])
    except:
        return

    invoice = await crypto_create_invoice(usdt)
    lira = int(usdt * CRYPTO_RATE)

    invoice_id = invoice["invoice_id"]

    pending_crypto[invoice_id] = {
        "user_id": m.from_user.id,
        "usdt": usdt,
        "lira": lira
    }

    kb = InlineKeyboardBuilder()
    kb.button(
        text="🔄 Проверить оплату",
        callback_data=f"check_crypto:{invoice_id}"
    )

    await m.answer(
        f"💎 <b>Crypto Donate</b>\n\n"
        f"💳 Сумма: <b>{usdt} USDT</b>\n"
        f"💰 Начислится: <b>{lira:,} лир</b>\n\n"
        f"👉 <a href='{invoice['pay_url']}'>ОПЛАТИТЬ</a>\n\n"
        f"После оплаты нажмите кнопку ниже 👇",
        reply_markup=kb.as_markup(),
        parse_mode="HTML",
        disable_web_page_preview=True
    )
# ================== CRYPTO CHECK LOOP ==================

@dp.callback_query(F.data.startswith("check_crypto:"))
async def check_crypto_payment(call: types.CallbackQuery):
    invoice_id = call.data.split(":")[1]

    headers = {
        "Crypto-Pay-API-Token": CRYPTO_PAY_TOKEN
    }

    # 🔥 ВСЕГДА проверяем CryptoBot
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://pay.crypt.bot/api/getInvoices?invoice_ids={invoice_id}",
            headers=headers
        ) as r:
            data = await r.json()

    if not data["result"]["items"]:
        return await call.answer("❌ Инвойс не найден в CryptoBot", show_alert=True)

    invoice = data["result"]["items"][0]

    if invoice["status"] != "paid":
        return await call.answer("⏳ Оплата ещё не поступила", show_alert=True)

    # 🔥 если бот перезапускался — считаем заново
    usdt = float(invoice["amount"])
    lira = int(usdt * CRYPTO_RATE)
    user_id = call.from_user.id

    upd_bal(user_id, lira)

    await call.message.edit_text(
        f"✅ <b>Оплата подтверждена!</b>\n\n"
        f"💳 {usdt} USDT\n"
        f"💰 +{lira:,} лир",
        parse_mode="HTML"
    )

    await call.bot.send_message(
        LOG_CHANNEL_ID,
        f"💎 <b>CRYPTO DONATE</b>\n"
        f"👤 UID: <code>{user_id}</code>\n"
        f"💳 {usdt} USDT\n"
        f"💰 {lira:,} лир",
        parse_mode="HTML"
    )

# ================== STARTUP ==================

async def on_startup(bot):
    asyncio.create_task(crypto_check_loop(bot))

import json

def save_bridges_game(uid, d):
    cur.execute("""
    REPLACE INTO active_bridges 
    (user_id, bet, safe, rows, step, last, text)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        uid,
        d["bet"],
        json.dumps(d["safe"]),
        json.dumps(d["rows"]),
        d["step"],
        d["last"],
        d["text"]
    ))
    conn.commit()


def load_bridges_game(uid):
    cur.execute("SELECT * FROM active_bridges WHERE user_id = ?", (uid,))
    r = cur.fetchone()
    if not r:
        return None

    return {
        "type": "bridges",
        "user_id": r[0],
        "bet": r[1],
        "safe": json.loads(r[2]),
        "rows": json.loads(r[3]),
        "step": r[4],
        "last": r[5],
        "resolved": False,
        "text": r[6]
    }


def delete_bridges_game(uid):
    cur.execute("DELETE FROM active_bridges WHERE user_id = ?", (uid,))
    conn.commit()

import random
import time
from aiogram import types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ================= НАСТРОЙКИ =================
BRIDGE_MULTS = [1.9, 3.8, 5.7, 7.6, 9.5, 11.4, 13.3, 15.2, 17.1]
COLORS = ["🟫","⬜️","⬛️","🟪","🟧","🟨","🟩","🟦","🟥"]
COOLDOWN = 1.5

# ================= ХРАНИЛИЩЕ ИГР =================
BRIDGES_GAMES = {}  # user_id -> game_data

# ================= ПАРСИНГ СТАВКИ =================
def parse_bet(arg: str, balance: int) -> int:
    arg = arg.lower().replace(",", "").replace("_", "")
    if arg == "все":
        return balance
    if arg.endswith("кк"):
        return int(arg[:-2]) * 1_000_000
    if arg.endswith("к"):
        return int(arg[:-1]) * 1_000
    if arg.isdigit():
        return int(arg)
    return 0

# ================= КЛАВИАТУРА =================
def bridges_kb(rows, bet, user_id, show_take=False):
    kb = InlineKeyboardBuilder()
    for i in range(len(rows)-1, -1, -1):
        kb.row(
            types.InlineKeyboardButton(
                text=rows[i][0],
                callback_data=f"bridge:{i}:0:{bet}:{user_id}"
            ),
            types.InlineKeyboardButton(
                text=rows[i][1],
                callback_data=f"bridge:{i}:1:{bet}:{user_id}"
            )
        )
    if show_take:
        kb.row(
            types.InlineKeyboardButton(
                text="💰 Забрать",
                callback_data=f"bridge:take:{bet}:{user_id}"
            )
        )
    return kb.as_markup()

# ================= СТАРТ =================
@dp.message(F.text.lower().startswith("мосты"))
async def bridges_start(m: types.Message):
    user_id = m.from_user.id
    u = get_u(user_id, m.from_user.full_name)

    # если есть активная игра — возвращаем её
    if user_id in BRIDGES_GAMES:
        game = BRIDGES_GAMES[user_id]
        await m.reply(
            "#Активная_игра\n\n" + game["text"],
            reply_markup=game["kb"],
            parse_mode="HTML",
            reply_to_message_id=m.message_id
        )
        return

    args = m.text.split()
    if len(args) < 2:
        return await m.reply("❌ Используй: <b>Мосты [ставка]</b>", parse_mode="HTML")

    bet = parse_bet(args[1], u[2])
    if bet < 100:
        return await m.reply("❌ Минимум <b>100</b> лир", parse_mode="HTML")
    if u[2] < bet:
        return await m.reply("❌ Недостаточно лир", parse_mode="HTML")

    upd_bal(user_id, -bet)

    safe = [random.randint(0, 1) for _ in COLORS]
    rows = [[c, c] for c in COLORS]

    text = (
        "🪜 <b>СТЕКЛЯННЫЕ МОСТЫ</b>\n\n"
        "<blockquote>"
        f"💰 Ставка: <b>{bet:,}</b> лир\n"
        "📈 Коэффициент: <b>x1.0</b>\n"
        "</blockquote>\n"
        "Начинай снизу ⬇️"
    )

    kb = bridges_kb(rows, bet, user_id)
    await m.reply(text, reply_markup=kb, parse_mode="HTML", reply_to_message_id=m.message_id)

    BRIDGES_GAMES[user_id] = {
        "bet": bet,
        "safe": safe,
        "rows": rows,
        "step": 0,
        "last": 0,
        "text": text,
        "kb": kb
    }

# ================= CALLBACK =================
@dp.callback_query(F.data.startswith("bridge:"))
async def bridges_cb(call: types.CallbackQuery):
    parts = call.data.split(":")
    action = parts[1]
    bet = int(parts[-2])
    owner_id = int(parts[-1])

    # ❗ ЧУЖАЯ ИГРА
    if call.from_user.id != owner_id:
        return await call.answer("Это не твоя игра!", show_alert=True)

    game = BRIDGES_GAMES.get(owner_id)
    if not game:
        return await call.answer("⏳ Игра завершена")

    now = time.time()
    if now - game["last"] < COOLDOWN:
        return await call.answer("⏳ Подожди немного")
    game["last"] = now

    rows = game["rows"]
    safe = game["safe"]
    step = game["step"]

    # 💰 ЗАБРАТЬ
    if action == "take":
        win = int(bet * BRIDGE_MULTS[step - 1])
        upd_bal(owner_id, win)

        for i in range(len(rows)):
            rows[i][safe[i]] = "🧊"
            rows[i][1 - safe[i]] = "💣"

        await call.message.edit_text(
            f"💰 <b>ВЫ ЗАБРАЛИ</b>\n\n<blockquote>🏆 {win:,} лир</blockquote>",
            reply_markup=bridges_kb(rows, bet, owner_id),
            parse_mode="HTML"
        )
        BRIDGES_GAMES.pop(owner_id, None)
        return await call.answer()

    row = int(parts[1])
    side = int(parts[2])

    if row != step:
        return await call.answer("❌ Начинай снизу", show_alert=True)

    # ❌ ПРОВАЛ
    if side != safe[step]:
        rows[step][side] = "💥"
        rows[step][1 - side] = "🧊"

        for i in range(step + 1, len(rows)):
            rows[i][safe[i]] = "🧊"
            rows[i][1 - safe[i]] = "💣"

        await call.message.edit_text(
            f"💥 <b>ВЗРЫВ!</b>\n\n<blockquote>❌ Потеряно: {bet:,} лир</blockquote>",
            reply_markup=bridges_kb(rows, bet, owner_id),
            parse_mode="HTML"
        )
        BRIDGES_GAMES.pop(owner_id, None)
        return await call.answer()

    # ✅ УСПЕХ
    rows[step][side] = "💎"
    rows[step][1 - side] = "💣"
    step += 1
    game["step"] = step

    if step == len(BRIDGE_MULTS):
        win = int(bet * BRIDGE_MULTS[-1])
        upd_bal(owner_id, win)

        await call.message.edit_text(
            f"🎉 <b>ИДЕАЛЬНЫЙ ПРОХОД</b>\n\n<blockquote>🏆 {win:,}</blockquote>",
            reply_markup=bridges_kb(rows, bet, owner_id),
            parse_mode="HTML"
        )
        BRIDGES_GAMES.pop(owner_id, None)
        return await call.answer()

    text = (
        "🪜 <b>СТЕКЛЯННЫЕ МОСТЫ</b>\n\n"
        "<blockquote>"
        f"💰 Ставка: <b>{bet:,}</b> лир\n"
        f"📈 Коэффициент: <b>x{BRIDGE_MULTS[step - 1]}</b>\n"
        "</blockquote>\n"
        "Поднимайся выше ⬆️"
    )

    kb = bridges_kb(rows, bet, owner_id, show_take=True)
    game["text"] = text
    game["kb"] = kb

    await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")

# ================= БЛЭКДЖЕК =================
import random
import time
from aiogram import types, F
from aiogram.utils.keyboard import InlineKeyboardBuilder

COOLDOWN = 1.5

# ================= ХРАНИЛИЩЕ ИГР =================
BLACKJACK_GAMES = {}  # user_id -> game_data

# ================= КАРТЫ =================
CARD_VALUES = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8,
    "9": 9, "10": 10, "J": 10, "Q": 10, "K": 10, "A": 11
}

# ================= ПАРСИНГ СТАВКИ =================
def parse_bet(arg: str, balance: int) -> int:
    arg = arg.lower().replace(",", "").replace("_","")
    if arg == "все":
        return balance
    if arg.endswith("кк"):
        return int(arg[:-2]) * 1_000_000
    if arg.endswith("к"):
        return int(arg[:-1]) * 1_000
    if arg.isdigit():
        return int(arg)
    return 0

# ================= СУММА КАРТ =================
def sum_cards(cards):
    total = 0
    aces = 0
    for c in cards:
        total += CARD_VALUES[c]
        if c == "A":
            aces += 1
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    return total

# ================= СТАРТ =================
@dp.message(F.text.lower().startswith("бж"))
async def blackjack_start(m: types.Message):
    user_id = m.from_user.id
    u = get_u(user_id, m.from_user.full_name)

    # есть активная игра
    if user_id in BLACKJACK_GAMES:
        game = BLACKJACK_GAMES[user_id]
        await m.reply(
            "#Активная_игра\n\n" + game["text"],
            reply_markup=game["kb"],
            parse_mode="HTML",
            reply_to_message_id=m.message_id
        )
        return

    args = m.text.split()
    if len(args) < 2:
        return await m.reply("❌ Используй: <b>Бж [ставка]</b>", parse_mode="HTML")

    bet = parse_bet(args[1], u[2])
    if bet < 100:
        return await m.reply("❌ Минимум <b>100</b> лир", parse_mode="HTML")
    if u[2] < bet:
        return await m.reply("❌ Недостаточно лир", parse_mode="HTML")

    upd_bal(user_id, -bet)

    deck = list(CARD_VALUES.keys()) * 4
    random.shuffle(deck)

    player_cards = [deck.pop(), deck.pop()]
    dealer_cards = [deck.pop(), deck.pop()]

    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="🃏 Взять карту",
            callback_data=f"bj:hit:{bet}:{user_id}"
        ),
        types.InlineKeyboardButton(
            text="🛑 Стоп",
            callback_data=f"bj:stand:{bet}:{user_id}"
        )
    )

    dealer_hidden = ["❓", dealer_cards[1]]

    text = (
        "🂡 <b>Блэкджек</b>\n\n"
        "<blockquote>"
        f"💰 Ставка: <b>{bet:,}</b> лир\n"
        f"🧑 Игрок: {', '.join(player_cards)} (сумма: <b>{sum_cards(player_cards)}</b>)\n"
        f"🤵 Дилер: {', '.join(dealer_hidden)}\n"
        "</blockquote>\nВыберите действие:"
    )

    await m.reply(text, reply_markup=kb.as_markup(), parse_mode="HTML", reply_to_message_id=m.message_id)

    BLACKJACK_GAMES[user_id] = {
        "bet": bet,
        "player": player_cards,
        "dealer": dealer_cards,
        "deck": deck,
        "kb": kb.as_markup(),
        "text": text,
        "last": 0
    }

# ================= CALLBACK =================
@dp.callback_query(F.data.startswith("bj:"))
async def blackjack_cb(call: types.CallbackQuery):
    parts = call.data.split(":")
    action = parts[1]
    bet = int(parts[2])
    owner_id = int(parts[3])

    # ❗ чужая игра
    if call.from_user.id != owner_id:
        return await call.answer("Это не твоя игра!", show_alert=True)

    game = BLACKJACK_GAMES.get(owner_id)
    if not game:
        return await call.answer("⏳ Игра завершена")

    now = time.time()
    if now - game["last"] < COOLDOWN:
        return await call.answer("⏳ Подожди немного")
    game["last"] = now

    player = game["player"]
    dealer = game["dealer"]
    deck = game["deck"]

    # ================= HIT =================
    if action == "hit":
        player.append(deck.pop())
        total = sum_cards(player)

        if total > 21:
            await call.message.edit_text(
                f"❌ <b>ПРОИГРЫШ!</b>\n\n"
                f"<blockquote>🧑 Игрок: {', '.join(player)} ({total})\n"
                f"🤵 Дилер: {', '.join(dealer)}\n"
                f"💰 Потеряно: {bet:,} лир</blockquote>",
                parse_mode="HTML"
            )
            BLACKJACK_GAMES.pop(owner_id, None)
            return await call.answer()

    # ================= STAND =================
    else:
        while sum_cards(dealer) < 17:
            dealer.append(deck.pop())

        player_total = sum_cards(player)
        dealer_total = sum_cards(dealer)

        if dealer_total > 21 or player_total > dealer_total:
            win = bet * 2
            upd_bal(owner_id, win)
            result = f"✅ <b>ПОБЕДА!</b>\n🏆 {win:,} лир"
        elif player_total == dealer_total:
            upd_bal(owner_id, bet)
            result = "⚖️ <b>НИЧЬЯ</b>\n💰 Ставка возвращена"
        else:
            result = f"❌ <b>ПРОИГРЫШ!</b>\n💰 Потеряно: {bet:,} лир"

        await call.message.edit_text(
            f"🂡 <b>Блэкджек</b>\n\n"
            f"<blockquote>🧑 Игрок: {', '.join(player)} ({player_total})\n"
            f"🤵 Дилер: {', '.join(dealer)} ({dealer_total})\n"
            f"{result}</blockquote>",
            parse_mode="HTML"
        )
        BLACKJACK_GAMES.pop(owner_id, None)
        return await call.answer()

    # ================= ОБНОВЛЕНИЕ =================
    kb = InlineKeyboardBuilder()
    kb.row(
        types.InlineKeyboardButton(
            text="🃏 Взять карту",
            callback_data=f"bj:hit:{bet}:{owner_id}"
        ),
        types.InlineKeyboardButton(
            text="🛑 Стоп",
            callback_data=f"bj:stand:{bet}:{owner_id}"
        )
    )

    dealer_hidden = ["❓", dealer[1]]

    text = (
        "🂡 <b>Блэкджек</b>\n\n"
        "<blockquote>"
        f"💰 Ставка: <b>{bet:,}</b> лир\n"
        f"🧑 Игрок: {', '.join(player)} (сумма: {sum_cards(player)})\n"
        f"🤵 Дилер: {', '.join(dealer_hidden)}\n"
        "</blockquote>\nВыберите действие:"
    )

    game["kb"] = kb.as_markup()
    game["text"] = text

    await call.message.edit_text(text, reply_markup=game["kb"], parse_mode="HTML")
    await call.answer()

import random
from aiogram import F, types

# ===============================
# ВЫБОР СЛУЧАЙНОГО ВАРИАНТА
# ===============================
@dp.message(F.text.lower().startswith("выбери"))
async def choose_cmd(m: types.Message):
    # Убираем слово "выбери"
    text = m.text[6:].strip()

    # Проверка формата
    if not text:
        return await m.reply(
            "❌ Формат:\n<b>Выбери вариант1 или вариант2</b>",
            parse_mode="HTML"
        )

    # Делим по слову "или"
    options = [opt.strip() for opt in text.split("или") if opt.strip()]

    if len(options) < 2:
        return await m.reply(
            "❌ Нужно минимум <b>2 варианта</b> через слово <b>или</b>",
            parse_mode="HTML"
        )

    # Случайный выбор
    choice = random.choice(options)

    # Красивый ответ
    await m.reply(
        f"<blockquote>🎯 <b>Я выбираю — {choice}</b></blockquote>",
        parse_mode="HTML"
    )



import sqlite3
from datetime import datetime, timedelta
import asyncio, random, pytz
from aiogram import F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

KZT = pytz.timezone("Asia/Almaty")

BOT_USERNAME = "@LiraGame_Bot"
NEWS_CHANNEL = "@LiraGameNews"

PRIZE = 33333
WINNERS_COUNT = 5

participants = set()
winners_history = []


# ─── ПРОВЕРКА ПОДПИСКИ ──────────────────────────────────────
async def is_subscribed(bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(NEWS_CHANNEL, user_id)
        return member.status in ("member", "administrator", "creator")
    except:
        return False


# ─── ТЕКСТ РОЗЫГРЫША ────────────────────────────────────────
def giveaway_text(user_id: int | None = None) -> str:
    now = datetime.now(KZT)
    draw_time = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    remaining = draw_time - now

    h = remaining.seconds // 3600
    m = (remaining.seconds % 3600) // 60
    s = remaining.seconds % 60

    joined = user_id in participants if user_id else False

    text = (
        "<blockquote>"
        "⚜️ <b>ЕЖЕДНЕВНЫЙ РОЗЫГРЫШ</b> ⚜️\n\n"
        f"⏰ До результата: <b>{h}ч {m}м {s}с</b>\n"
        f"🎁 Призовой фонд: <b>{PRIZE:,}</b> лир\n"
        f"🏆 Победителей: <b>{WINNERS_COUNT}</b>\n"
        f"👥 Участников: <b>{len(participants)}</b>\n\n"
        "📋 <b>Условия:</b>\n"
        f"├ Ник содержит {BOT_USERNAME}\n"
        f"├ Подписка на {NEWS_CHANNEL}\n"
    )

    if joined:
        text += "\n✅ <b>Вы уже участвуете!</b>"

    text += "</blockquote>"
    return text


# ─── КЛАВИАТУРА ─────────────────────────────────────────────
def giveaway_kb(user_id: int | None = None):
    buttons = []

    if not user_id or user_id not in participants:
        buttons.append(
            [InlineKeyboardButton(text="💠 Участвовать", callback_data="giveaway_join")]
        )

    buttons.append(
        [InlineKeyboardButton(text="❤️‍🔥 Победители", callback_data="giveaway_winners")]
    )

    return InlineKeyboardMarkup(inline_keyboard=buttons)


# ─── ОБНОВЛЕНИЕ ТАЙМЕРА ─────────────────────────────────────
async def giveaway_timer(message: types.Message, user_id: int):
    while True:
        try:
            await message.edit_text(
                giveaway_text(user_id),
                reply_markup=giveaway_kb(user_id),
                parse_mode="HTML"
            )
        except:
            return

        await asyncio.sleep(30)


# ─── КОМАНДА «ХАЛЯВА» ───────────────────────────────────────
@dp.message(F.text.lower().startswith("халява"))
async def giveaway_show(m: types.Message):
    msg = await m.reply(
        giveaway_text(m.from_user.id),
        reply_markup=giveaway_kb(m.from_user.id),
        parse_mode="HTML"
    )
    asyncio.create_task(giveaway_timer(msg, m.from_user.id))


# ─── УЧАСТИЕ ────────────────────────────────────────────────
@dp.callback_query(F.data == "giveaway_join")
async def giveaway_join(c: types.CallbackQuery):
    user = c.from_user

    if BOT_USERNAME not in user.full_name:
        return await c.answer(
            f"❌ Добавьте {BOT_USERNAME} в ник!",
            show_alert=True
        )

    if not await is_subscribed(bot, user.id):
        return await c.answer(
            f"❌ Подпишитесь на {NEWS_CHANNEL}!",
            show_alert=True
        )

    if user.id in participants:
        return await c.answer("✅ Вы уже участвуете!", show_alert=True)

    participants.add(user.id)

    await c.message.edit_text(
        giveaway_text(user.id),
        reply_markup=giveaway_kb(user.id),
        parse_mode="HTML"
    )
    await c.answer("🎉 Участие подтверждено!")


# ─── ПОБЕДИТЕЛИ ─────────────────────────────────────────────
@dp.callback_query(F.data == "giveaway_winners")
async def giveaway_winners(c: types.CallbackQuery):
    if not winners_history:
        return await c.answer("Победителей пока нет.", show_alert=True)

    text = "⚜️ <b>ПОСЛЕДНИЕ ПОБЕДИТЕЛИ</b> ⚜️\n\n"
    for i, w in enumerate(winners_history, 1):
        text += (
            f"{i}️⃣ <b>{w['name']}</b>\n"
            f"💎 {w['prize']:,} лир | 📅 {w['date']}\n\n"
        )

    await bot.send_message(c.from_user.id, text, parse_mode="HTML")
    await c.answer("📬 Отправлено в ЛС")

import asyncio
import random
import string
import logging
from datetime import datetime
import pytz

from aiogram import F, types
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ================= НАСТРОЙКИ =================
PROMO_MIN_SUM = 7000
PROMO_MAX_SUM = 25000
PROMO_MIN_USES = 11
PROMO_MAX_USES = 20

KZT = pytz.timezone("Asia/Almaty")

# ================= ЛОГИ =================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= PROMO =================
def generate_promo_code():
    return "LIRA-" + "".join(
        random.choices(string.ascii_uppercase + string.digits, k=6)
    )

async def create_hourly_promo():
    code = generate_promo_code()
    amount = random.randint(PROMO_MIN_SUM, PROMO_MAX_SUM)
    uses = random.randint(PROMO_MIN_USES, PROMO_MAX_USES)

    try:
        cur.execute(
            "INSERT INTO promo (code, amount, uses) VALUES (?, ?, ?)",
            (code, amount, uses)
        )
        conn.commit()

        logger.info(f"🎁 PROMO | {code} | {amount} | uses={uses}")

        await bot.send_message(
            X50_CHAT_ID,
            (
                "🎁 <b>НОВЫЙ ПРОМОКОД!</b>\n\n"
                f"<code>Промо {code}</code>\n\n"
                f"💰 <b>{amount:,}</b> лир\n"
                f"👤 Активаций: <b>{uses}</b>"
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"PROMO ERROR: {e}")

# ================= СБРОС ЛИМИТОВ =================
async def reset_limits():
    cur.execute("SELECT COUNT(*) FROM users WHERE used_limit > 0")
    count = cur.fetchone()[0]

    cur.execute("UPDATE users SET used_limit = 0")
    conn.commit()

    now = datetime.now(KZT)
    logger.info(
        f"⚙️ Автосброс лимитов! Пользователей: {count} | {now.strftime('%H:%M:%S')}"
    )

# --- Scheduler для ежедневного розыгрыша ---
async def daily_giveaway():
    if not participants:
        return

    all_participants = list(participants)
    winners = random.sample(all_participants, min(5, len(all_participants)))
    prize = 33333
    date_str = datetime.now(KZT).strftime("%d.%m.%Y")

    winners_history.clear()
    for uid in winners:
        chat = await bot.get_chat(uid)
        winners_history.append({"name": chat.first_name, "prize": prize, "date": date_str})
        upd_bal(uid, prize)
        try:
            await bot.send_message(uid, f"🎉 Поздравляем! Вы выиграли <b>{prize:,}</b> лир в ежедневном розыгрыше!", parse_mode="HTML")
        except:
            pass

    participants.clear()

# ================= СБРОС ТОПА =================
async def reset_top_daily():
    # Получаем топ-5 игроков по дневной прибыли
    rows = cur.execute(
        "SELECT name, daily, uid FROM users WHERE daily > 0 ORDER BY daily DESC LIMIT 5"
    ).fetchall()

    if not rows:
        logger.info("⚠️ Нет игроков в топе для выдачи призов.")
        return

    prizes = [100_000, 80_000, 60_000, 40_000, 20_000]
    report_text = "🎉 <b>Топ-5 игроков за сегодня!</b>\n\n"

    for i, row in enumerate(rows):
        name, profit, uid = row
        prize = prizes[i]

        # Начисляем на баланс
        cur.execute("UPDATE users SET bal = bal + ? WHERE uid = ?", (prize, uid))

        # Отправка ЛС игроку
        try:
            await bot.send_message(
                uid,
                f"🏆 <b>Поздравляем!</b>\n\n"
                f"Вы вошли в топ игроков за сегодня!\n"
                f"Ваше место: <b>{i+1}</b>\n"
                f"Ваша награда: <b>{prize:,} лир</b>",
                parse_mode="HTML"
            )
        except:
            pass  # Игрок мог закрыть ЛС

        profile_link = f"http://t.me/@id{uid}"
        report_text += f'“{i+1} <a href="{profile_link}"><b>{name}</b></a> | <b>{prize:,} лир</b>”\n\n'

    # Обнуляем дневной топ
    cur.execute("UPDATE users SET daily = 0")
    conn.commit()

    prizes_text = (
        '“<b>🥇 1 место — 100,000 лир</b>\n'
        '<b>🥈 2 место — 80,000 лир</b>\n'
        '<b>🥉 3 место — 60,000 лир</b>\n'
        '<b>4️⃣ 4 место — 40,000 лир</b>\n'
        '<b>5️⃣ 5 место — 20,000 лир</b>”\n'
    )
    report_text += prizes_text

    # Отправка админу (первый в списке ADMIN_ID)
    await bot.send_message(ADMIN_ID[0], report_text, parse_mode="HTML", disable_web_page_preview=True)
    logger.info("✅ Ежедневный топ сброшен и призы выданы.")

# ================= SCHEDULER =================
scheduler = AsyncIOScheduler(timezone=KZT)

async def on_startup():
    print("NOW:", datetime.now(KZT))

    # PROMO каждый час в :00
    scheduler.add_job(
        create_hourly_promo,
        trigger="cron",
        minute=0,
        id="hourly_promo",
        replace_existing=True,
        misfire_grace_time=300
    )

    # СБРОС лимитов (пример: 14:46)
    scheduler.add_job(
        reset_limits,
        trigger="cron",
        hour=0,
        minute=0,
        id="reset_limits",
        replace_existing=True,
        misfire_grace_time=300
    )

    # СБРОС ТОП-5 игроков каждый день в 00:00
    scheduler.add_job(
        reset_top_daily,
        trigger="cron",
        hour=0,
        minute=0,
        id="reset_top_daily",
        replace_existing=True,
        misfire_grace_time=300
    )

    scheduler.add_job(
        daily_giveaway,       # функция, которая разыгрывает призы и отправляет ЛС победителям
        trigger="cron",       # ежедневный триггер
        hour=0,               # время по Алматы (KZT) — 00:00
        minute=0,
        second=0,
        id="daily_giveaway",  # уникальный ID задачи
        replace_existing=True,
        misfire_grace_time=300  # если бот был оффлайн, подождать до 5 минут
    )

    scheduler.start()
    logger.info("🚀 Scheduler запущен")

# ================= ADMIN TEST =================
@dp.message(F.text.lower() == "тест промо")
async def test_promo(m: types.Message):
    if m.from_user.id not in ADMIN_ID:
        return
    await create_hourly_promo()
    await m.reply("🧪 Тестовый промокод создан")

# ================= MAIN =================
async def main():
    await on_startup()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())