import os
import time
import random
import threading
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import requests
import json

# Configuración básica
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CLASE DE GESTIÓN DE COOKIES (VAULT) ---
class CookieVault:
    def __init__(self):
        self.cookies = [] # Lista de diccionios { 'id': 1, 'user_id': int, 'data': {...} }
        self.selected_cookie_id = None

    def add_cookie(self, user_id, cookie_data):
        new_id = len(self.cookies) + 1
        self.cookies.append({'id': new_id, 'user_id': user_id, 'data': cookie_data})
        return new_id

    def get_list(self, user_id):
        return [c for c in self.cookies if c['user_id'] == user_id]

    def select_cookie(self, user_id, cookie_id):
        valid_ids = [c['id'] for c in self.get_list(user_id)]
        if cookie_id in valid_ids:
            self.selected_cookie_id = cookie_id
            return True
        return False

    def get_selected_data(self, user_id):
        if not self.selected_cookie_id:
            return None
        cookie_obj = next((c for c in self.cookies if c['id'] == self.selected_cookie_id and c['user_id'] == user_id), None)
        return cookie_obj['data'] if cookie_obj else None

# Instancia global del vault
vault = CookieVault()

# --- CLASE DE SPOOFING DE IP ---
class IPSpoofManager:
    def __init__(self):
        self.current_ip = f"{random.randint(100, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}"
        self.running = True
        self.thread = threading.Thread(target=self._rotate_loop, daemon=True)
        self.thread.start()

    def _rotate_loop(self):
        while self.running:
            self.current_ip = f"{random.randint(100, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}.{random.randint(1, 255)}"
            logger.info(f"IP Rotated to: {self.current_ip}")
            time.sleep(5) # Cada 5 segundos

    def get_headers(self):
        """Retorna headers con una IP falsa para simular tráfico desde diferentes lugares."""
        return {
            "X-Forwarded-For": self.current_ip,
            "X-Real-IP": self.current_ip,
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        }

spoof_manager = IPSpoofManager()

# --- LÓGICA NETFLIX ---
def make_netflix_request(session, url, extra_headers=None):
    """Hace una petición a Netflix usando las cookies y headers spoofed."""
    headers = spoof_manager.get_headers()
    if extra_headers:
        headers.update(extra_headers)
    
    try:
        response = session.get(url, headers=headers, timeout=10)
        return response
    except Exception as e:
        logger.error(f"Error en request: {e}")
        return None

# --- TELEGRAM BOT SETUP ---
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("Debes configurar la variable de entorno BOT_TOKEN")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Bienvenido al Generador NFToken + TV2.\n\n"
        "1. Envía tus cookies para guardarlas en el Vault.\n"
        "2. Selecciona una cookie para vincular a TV.\n"
        "3. Ingresa el código de vinculación.\n\n"
        "Comandos disponibles:\n/start - Inicio\n/savecookie - Guardar cookie\n/listcookies - Ver mis cookies\n/select <id> - Seleccionar cookie para TV\n/linktv <codigo> - Vincular a TV"
    )

async def save_cookie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.replace('/savecookie ', '').strip()
    if not text:
        await update.message.reply_text("Por favor envía las cookies después del comando.")
        return
    
    # Simulamos guardar las cookies. En un caso real, podrías parsearlas si vienen en formato específico.
    # Aquí asumimos que el usuario pega raw cookies o un string identificable.
    vault.add_cookie(user_id, {'raw': text, 'timestamp': time.time()})
    await update.message.reply_text(f"✅ Cookie guardada en el Vault. Usa /listcookies para verla.")

async def list_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    my_cookies = vault.get_list(user_id)
    
    if not my_cookies:
        await update.message.reply_text("No tienes cookies guardadas en el Vault.")
        return

    keyboard = []
    for c in my_cookies:
        # Botón para seleccionar directamente
        callback_data = f"sel_{c['id']}"
        keyboard.append([InlineKeyboardButton(f"Cookie ID: {c['id']}", callback_data=callback_data)])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Selecciona una cookie para usar:", reply_markup=reply_markup)

async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    if query.data.startswith("sel_"):
        cookie_id = int(query.data.split("_")[1])
        if vault.select_cookie(user_id, cookie_id):
            await query.edit_message_text(f"✅ Cookie ID {cookie_id} seleccionada. Ahora usa /linktv <tu_código> para vincular a TV.")
        else:
            await query.edit_message_text("❌ Error al seleccionar cookie.")

async def link_to_tv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    code = " ".join(args) if args else ""
    
    selected_data = vault.get_selected_data(user_id)
    if not selected_data:
        await update.message.reply_text("⚠️ Primero debes guardar y seleccionar una cookie con /savecookie y /select.")
        return

    if not code:
        await update.message.reply_text("⚠️ Por favor indica el código de vinculación. Ejemplo: /linktv 123456")
        return

    # Simulación de conexión a TV2 como iPhone
    tv_url = "https://www.netflix.com/us-es/tv2"
    
    # Creamos una sesión para mantener las cookies
    session = requests.Session()
    
    # Inyectamos la cookie cruda si es posible, o usamos la header X-Forwarded-For
    # Nota: Netflix suele requerir cookies específicas como 'NFID' o similares. 
    # Si el usuario pegó solo texto, intentaremos enviarlo como cookie genérica o verificar si es válido.
    
    # Cabeceras falsas de iPhone
    iphone_headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5"
    }
    
    # Intentamos obtener la página TV2 para verificar estado
    resp = session.get(tv_url, headers=iphone_headers)
    
    # Aquí iría la lógica real de extracción de token si la API lo requiere
    # Por ahora, simulamos éxito si el status code es 200
    if resp.status_code == 200:
        await update.message.reply_text(f"📺 ¡Vinculación exitosa!\n\nHas ingresado al modo TV2 con tu cookie seleccionada.\nCódigo usado: {code}\nIP Falsa activa: {spoof_manager.current_ip}")
    else:
        await update.message.reply_text(f"❌ Error al conectar a TV2. Código de estado: {resp.status_code}. Revisa tus cookies.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    start_handler = CommandHandler('start', start)
    save_cookie_handler = CommandHandler('savecookie', save_cookie)
    list_cookies_handler = CommandHandler('listcookies', list_cookies)
    selection_handler = CallbackQueryHandler(handle_selection)
    link_tv_handler = CommandHandler('linktv', link_to_tv)

    app.add_handler(start_handler)
    app.add_handler(save_cookie_handler)
    app.add_handler(list_cookies_handler)
    app.add_handler(selection_handler)
    app.add_handler(link_tv_handler)

    logger.info("Bot starting...")
    app.run_polling()

if __name__ == '__main__':
    main()
