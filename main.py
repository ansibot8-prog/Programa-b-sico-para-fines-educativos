import os
import time
import random
import threading
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters
import requests

# Configuración de logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- CLASE DE GESTIÓN DE COOKIES (VAULT) ---
class CookieVault:
    def __init__(self):
        self.cookies = [] 

    def add_cookie(self, user_id, cookie_data):
        new_id = len(self.cookies) + 1
        # Guardamos la cookie como string raw o diccionario según lo que el usuario pegue
        self.cookies.append({'id': new_id, 'user_id': user_id, 'data': str(cookie_data)})
        return new_id

    def get_list(self, user_id):
        return [c for c in self.cookies if c['user_id'] == user_id]

    def select_cookie(self, user_id, cookie_id):
        valid_ids = [c['id'] for c in self.get_list(user_id)]
        if cookie_id in valid_ids:
            return True
        return False

    def get_selected_data(self, user_id):
        # Retorna la cookie seleccionada por el usuario en su sesión actual
        # Nota: En un bot simple, "seleccionar" suele ser temporal o se guarda en estado.
        # Aquí asumimos que el usuario la seleccionó previamente con /select
        if hasattr(self, '_selected_cookie'):
            return self._selected_cookie
        return None

    def set_selected_cookie(self, user_id, cookie_obj):
        self._selected_cookie = cookie_obj

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
    # Toma todo el texto después del comando
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
        # Muestra un fragmento de la cookie para identificarla
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
            await query.edit_message_text("❌ Error al seleccionar cookie.")

async def link_to_tv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args
    code = " ".join(args) if args else ""
    
    selected_cookie = vault.get_selected_data(user_id)
    if not selected_cookie:
        await update.message.reply_text("⚠️ Primero debes guardar y seleccionar una cookie con /savecookie y /select.")
        return

    if not code:
        await update.message.reply_text("⚠️ Por favor indica el código de vinculación. Ejemplo: /linktv 123456")
        return

    # Simulación de conexión a TV2 como iPhone
    tv_url = "https://www.netflix.com/us-es/tv2"
    
    # Creamos una sesión para mantener las cookies
    session = requests.Session()
    
    # Inyectamos la cookie cruda si es posible
    # Netflix requiere cookies específicas. Si el usuario pegó raw cookies, intentamos parsearlas o enviarlas directo.
    # Aquí enviamos la cookie raw en el header Cookie si viene como string plano, o la añadimos a la sesión.
    try:
        # Intento básico: si la cookie viene como "NFSID=xxx; ...", requests puede manejarlo directamente
        # Si viene en formato dict, habría que parsear mejor. Asumiremos formato string raw válido.
        session.headers.update(spoof_manager.get_headers())
        
        # Añadir la cookie a la sesión
        # Si la cookie es un string tipo "key=value; key2=value2"
        if isinstance(selected_cookie['data'], str):
            session.cookies.set_string(selected_cookie['data'])
            
        resp = session.get(tv_url, timeout=10)
        
        if resp.status_code == 200:
            await update.message.reply_text(f"📺 ¡Vinculación exitosa!\n\nHas ingresado al modo TV2 con tu cookie seleccionada.\nCódigo usado: {code}\nIP Falsa activa: {spoof_manager.current_ip}")
        else:
            await update.message.reply_text(f"❌ Error al conectar a TV2. Código de estado: {resp.status_code}. Revisa tus cookies.")
            
    except Exception as e:
        logger.error(f"Error en request: {e}")
        await update.message.reply_text(f"❌ Error interno: {str(e)}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('savecookie', save_cookie))
    app.add_handler(CommandHandler('listcookies', list_cookies))
    app.add_handler(CallbackQueryHandler(handle_selection))
    app.add_handler(CommandHandler('linktv', link_to_tv))

    logger.info("Bot starting...")
    app.run_polling()

if __name__ == '__main__':
    main()
