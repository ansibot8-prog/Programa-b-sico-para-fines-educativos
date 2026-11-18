import os
import time
import random
import threading
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import requests
from bs4 import BeautifulSoup

# --- CONFIGURACIÓN DE LOGS ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CLASE DE GESTIÓN DE COOKIES (VAULT) ---
class CookieVault:
    def __init__(self):
        self.cookies = [] 

    def add_cookie(self, user_id, cookie_data):
        new_id = len(self.cookies) + 1
        self.cookies.append({'id': new_id, 'user_id': user_id, 'data': str(cookie_data)})
        return new_id

    def get_list(self, user_id):
        return [c for c in self.cookies if c['user_id'] == user_id]

    def set_selected_cookie(self, user_id, cookie_obj):
        # Guardamos la cookie seleccionada en la sesión del usuario
        if not hasattr(self, '_selected_cookies'):
            self._selected_cookies = {}
        self._selected_cookies[user_id] = cookie_obj

    def get_selected_cookie(self, user_id):
        if hasattr(self, '_selected_cookies'):
            return self._selected_cookies.get(user_id)
        return None

vault = CookieVault()

# --- CLASE DE SPOOFING DE IP ---
class IPSpoofManager:
    def __init__(self):
        self.current_ip = self._generate_ip()
        self.running = True
        self.thread = threading.Thread(target=self._rotate_loop, daemon=True)
        self.thread.start()

    def _generate_ip(self):
        return f"{random.randint(100, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}"

    def _rotate_loop(self):
        while self.running:
            self.current_ip = self._generate_ip()
            logger.info(f"IP Rotated to: {self.current_ip}")
            time.sleep(5) # Cada 5 segundos

    def get_headers(self):
        """Retorna headers simulando un iPhone con la IP falsa"""
        return {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            "X-Forwarded-For": self.current_ip,
            "X-Real-IP": self.current_ip,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        }

spoof_manager = IPSpoofManager()

# --- LÓGICA TELEGRAM BOT ---
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("Debes configurar la variable de entorno BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bienvenido al Generador NFToken + TV2.\n\n"
        "1. Envía tus cookies con /savecookie <tus_cookies>\n"
        "2. Lista tus cookies con /listcookies\n"
        "3. Selecciona una con /select <id>\n"
        "4. Vincula a TV con /linktv <codigo>"
    )

async def save_cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.replace('/savecookie ', '').strip()
    if not text:
        await update.message.reply_text("Envía las cookies después del comando.")
        return
    
    vault.add_cookie(user_id, text)
    await update.message.reply_text(f"✅ Cookie guardada. Usa /listcookies para verlas.")

async def list_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    my_cookies = vault.get_list(user_id)
    
    if not my_cookies:
        await update.message.reply_text("No tienes cookies guardadas.")
        return

    keyboard = []
    for c in my_cookies:
        callback_data = f"sel_{c['id']}"
        preview = c['data'][:20] + "..." if len(c['data']) > 20 else c['data']
        keyboard.append([InlineKeyboardButton(f"ID: {c['id']} ({preview})", callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Selecciona una cookie:", reply_markup=reply_markup)

async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data.startswith("sel_"):
        cookie_id = int(query.data.split("_")[1])
        matching_cookies = [c for c in vault.get_list(user_id) if c['id'] == cookie_id]
        
        if matching_cookies:
            vault.set_selected_cookie(user_id, matching_cookies[0])
            await query.edit_message_text(f"✅ Cookie ID {cookie_id} seleccionada. Ahora usa /linktv <tu_código> para vincular a TV.")
        else:
           
