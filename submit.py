import telebot
import os
import json
import hashlib
import time
import threading
import csv
import pandas as pd
from telebot import types
from datetime import datetime

# ================= 🔧 [ 1. CONFIGURATION ] =================

MASTER_ADMIN_TOKEN = "8685933992:AAFCo_sbZdsKEDbrckJBTmB4Kmh0ZLorfU8"
ADMIN_IDS = [6293094676]

master_bot = telebot.TeleBot(MASTER_ADMIN_TOKEN)
DB_FILE = "id_receiver_data.json"
user_sessions = {}
active_bots = set()
db_lock = threading.Lock()

# Type status
type_status = {
    "ig_cookies": True,
    "ig_2fa": True,
    "fb_0fd_2fa": True
}

# Current OK data storage
current_ok_data = {
    "total_ok": 0,
    "total_users": 0,
    "last_scan_time": None,
    "results": {},
    "scan_type": None
}

# User IDs tracking for broadcast
USER_IDS_FILE = "user_ids.json"

def load_user_ids():
    if not os.path.exists(USER_IDS_FILE):
        return []
    with open(USER_IDS_FILE, "r") as f:
        return json.load(f)

def save_user_id(user_id):
    user_ids = load_user_ids()
    if user_id not in user_ids:
        user_ids.append(user_id)
        with open(USER_IDS_FILE, "w") as f:
            json.dump(user_ids, f, indent=4)

# Folders
os.makedirs("uploads/ig_cookies", exist_ok=True)
os.makedirs("uploads/ig_2fa", exist_ok=True)
os.makedirs("uploads/fb_0fd_2fa", exist_ok=True)
os.makedirs("duplicate_files", exist_ok=True)
os.makedirs("backup", exist_ok=True)

# ================= 📁 [ 2. DATABASE ] =================

def load_db():
    with db_lock:
        if not os.path.exists(DB_FILE):
            default = {
                "tokens": [],
                "files": {
                    "ig_cookies": {},
                    "ig_2fa": {},
                    "fb_0fd_2fa": {}
                },
                "all_unique_data": {
                    "ig_cookies": {},
                    "ig_2fa": {},
                    "fb_0fd_2fa": {}
                },
                "global_unique_keys": []
            }
            with open(DB_FILE, "w") as f:
                json.dump(default, f, indent=4)
            return default
        with open(DB_FILE, "r") as f:
            data = json.load(f)
            if "global_unique_keys" not in data:
                data["global_unique_keys"] = []
            return data

def save_db(data):
    with db_lock:
        temp_file = DB_FILE + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(data, f, indent=4)
        os.replace(temp_file, DB_FILE)

# ================= 🔐 [ 3. FILE PROCESSING ] =================

def find_columns_case_insensitive(row):
    """
    Find column names case-insensitively: 'user', 'pass', '2fa'
    """
    user_val = ""
    pass_val = ""
    twofa_val = ""
    
    # Convert row keys to lowercase for case-insensitive matching
    row_lower = {k.lower(): v for k, v in row.items()}
    
    # Check for user column
    if 'user' in row_lower:
        val = row_lower['user']
        if val and str(val).strip():
            user_val = str(val).strip()
    
    # Check for pass column
    if 'pass' in row_lower:
        val = row_lower['pass']
        if val and str(val).strip():
            pass_val = str(val).strip()
    
    # Check for 2fa column
    if '2fa' in row_lower:
        val = row_lower['2fa']
        if val and str(val).strip():
            twofa_val = str(val).strip()
    
    return user_val, pass_val, twofa_val

def process_file_with_columns(file_path, original_filename, file_type):
    try:
        if original_filename.endswith('.csv'):
            df = pd.read_csv(file_path)
        elif original_filename.endswith('.xlsx'):
            df = pd.read_excel(file_path)
        else:
            return None, 0, None, 0
        
        if df is None or df.empty:
            return None, 0, None, 0
        
        print(f"\n📋 Columns found in {original_filename}: {list(df.columns)}")
        
        total_rows = len(df)
        
        # Convert dataframe columns to lowercase for checking
        df_columns_lower = [col.lower() for col in df.columns]
        
        # Check if required columns exist (case-insensitive)
        has_user = 'user' in df_columns_lower
        has_pass = 'pass' in df_columns_lower
        
        if not (has_user and has_pass):
            return None, 0, None, 0
        
        filtered_data = []
        empty_count = 0
        rows_with_2fa = 0
        
        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            
            user_val, pass_val, twofa_val = find_columns_case_insensitive(row_dict)
            
            if twofa_val:
                rows_with_2fa += 1
            
            if idx < 3:
                print(f"Row {idx}: user='{user_val}', pass='{pass_val}', 2fa='{str(twofa_val)[:30]}...'")
            
            if user_val or pass_val:
                filtered_data.append({
                    "user": user_val,
                    "pass": pass_val,
                    "2fa": twofa_val
                })
            else:
                empty_count += 1
        
        with open(file_path, "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        
        print(f"✅ Valid rows: {len(filtered_data)}, Empty rows: {empty_count}, Rows with 2fa: {rows_with_2fa}")
        
        return filtered_data, len(filtered_data), file_hash, empty_count
        
    except Exception as e:
        print(f"Process error: {e}")
        return None, 0, None, 0

def process_file_worker(bot, chat_id, file_type, file_path, original_name, payment_method, payment_number, username):
    try:
        db = load_db()
        
        filtered_data, valid_rows, file_hash, empty_rows = process_file_with_columns(file_path, original_name, file_type)
        
        if filtered_data is None or not filtered_data:
            os.remove(file_path)
            bot.send_message(
                chat_id, 
                "❌ *NO VALID DATA FOUND!*\n\n"
                "📌 Your file must have these columns (case-insensitive):\n"
                "• user / User / USER\n"
                "• pass / Pass / PASS\n"
                "• 2fa / 2Fa / 2FA (optional)\n\n"
                "✅ Any case variation will work!",
                parse_mode="Markdown"
            )
            return False
        
        file_db = db["files"][file_type]
        
        # ========== DUPLICATE FILE CHECK ==========
        if file_hash in file_db:
            with open(file_path, "rb") as dup_file:
                bot.send_document(
                    chat_id, 
                    dup_file, 
                    caption=f"⚠️ *DUPLICATE FILE!*\n\n📁 File: `{original_name}`\n❌ This exact file was already submitted.",
                    parse_mode="Markdown"
                )
            os.remove(file_path)
            return False
        
        # ========== CHECK DUPLICATE DATA (3 columns: user+pass+2fa) ==========
        unique_rows = []
        duplicate_rows = []
        seen_keys = set()
        
        for row in filtered_data:
            row_key = f"{row['user']}_{row['pass']}_{row['2fa']}".lower()
            if row_key in seen_keys:
                duplicate_rows.append(row)
            else:
                seen_keys.add(row_key)
                unique_rows.append(row)
        
        # ========== CHECK GLOBAL DUPLICATES ==========
        global_unique_keys = set(db.get("global_unique_keys", []))
        
        truly_unique_rows = []
        global_duplicate_rows = []
        
        for row in unique_rows:
            row_key = f"{row['user']}_{row['pass']}_{row['2fa']}".lower()
            if row_key in global_unique_keys:
                global_duplicate_rows.append(row)
            else:
                global_unique_keys.add(row_key)
                truly_unique_rows.append(row)
        
        db["global_unique_keys"] = list(global_unique_keys)
        
        # Send global duplicates back to user
        if global_duplicate_rows:
            dup_df = pd.DataFrame(global_duplicate_rows)
            dup_file_path = f"duplicate_rows_global_{int(time.time())}_{original_name}"
            try:
                if original_name.endswith('.csv'):
                    dup_df.to_csv(dup_file_path, index=False)
                else:
                    dup_df.to_excel(dup_file_path, index=False)
                
                with open(dup_file_path, "rb") as f:
                    bot.send_document(
                        chat_id,
                        f,
                        caption=f"⚠️ *DUPLICATE DATA FOUND!*\n\n📊 {len(global_duplicate_rows)} rows already exist in database."
                    )
                os.remove(dup_file_path)
            except:
                pass
        
        filtered_data = truly_unique_rows
        valid_rows = len(filtered_data)
        
        if valid_rows == 0:
            os.remove(file_path)
            bot.send_message(
                chat_id,
                "❌ *NO UNIQUE DATA!*\n\n"
                f"⚠️ All rows already exist in database.",
                parse_mode="Markdown"
            )
            return False
        
        if duplicate_rows:
            dup_df = pd.DataFrame(duplicate_rows)
            dup_file_path = f"duplicate_rows_internal_{int(time.time())}_{original_name}"
            try:
                if original_name.endswith('.csv'):
                    dup_df.to_csv(dup_file_path, index=False)
                else:
                    dup_df.to_excel(dup_file_path, index=False)
                
                with open(dup_file_path, "rb") as f:
                    bot.send_document(
                        chat_id,
                        f,
                        caption=f"⚠️ *DUPLICATE ROWS IN YOUR FILE!*\n\n📊 {len(duplicate_rows)} duplicate rows found inside your file."
                    )
                os.remove(dup_file_path)
            except:
                pass
        
        file_info = {
            "hash": file_hash,
            "original_name": original_name,
            "original_data": filtered_data,
            "submitted_by": username,
            "payment_method": payment_method,
            "payment_number": payment_number,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "file_type": file_type,
            "total_rows_in_file": valid_rows,
            "empty_rows": empty_rows
        }
        
        file_db[file_hash] = file_info
        
        all_unique_db = db["all_unique_data"][file_type]
        data_key = f"{file_hash}_{int(time.time())}"
        all_unique_db[data_key] = {
            "file_hash": file_hash,
            "original_name": original_name,
            "data": filtered_data,
            "submitted_by": username,
            "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "file_type": file_type,
            "payment_method": payment_method,
            "payment_number": payment_number,
            "total_rows": valid_rows
        }
        
        save_db(db)
        
        warning_msg = ""
        if empty_rows > 0:
            warning_msg = f"\n⚠️ {empty_rows} rows had no data!"
        if duplicate_rows:
            warning_msg += f"\n⚠️ {len(duplicate_rows)} duplicate rows removed!"
        if global_duplicate_rows:
            warning_msg += f"\n⚠️ {len(global_duplicate_rows)} rows already existed!"
        
        result_msg = (
            f"✅ *FILE PROCESSED!*\n\n"
            f"📁 *File:* `{original_name}`\n"
            f"📂 *Type:* `{file_type}`\n"
            f"💳 *Payment:* {payment_method} - `{payment_number}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *Valid rows:* `{valid_rows}`\n"
            f"{warning_msg}\n"
            f"✨ *Status:* Successfully received"
        )
        
        bot.send_message(chat_id, result_msg, parse_mode="Markdown")
        
        return True
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ *ERROR!*\n\n{str(e)}", parse_mode="Markdown")
        return False

def get_type_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    if type_status["ig_cookies"]:
        kb.add(types.InlineKeyboardButton("🟢 IG Cookies", callback_data="type_ig_cookies"))
    else:
        kb.add(types.InlineKeyboardButton("🔴 IG Cookies (Closed)", callback_data="type_disabled_ig_cookies"))
    
    if type_status["ig_2fa"]:
        kb.add(types.InlineKeyboardButton("🟢 IG 2FA", callback_data="type_ig_2fa"))
    else:
        kb.add(types.InlineKeyboardButton("🔴 IG 2FA (Closed)", callback_data="type_disabled_ig_2fa"))
    
    if type_status["fb_0fd_2fa"]:
        kb.add(types.InlineKeyboardButton("🟢 FB 0FD 2FA", callback_data="type_fb_0fd_2fa"))
    else:
        kb.add(types.InlineKeyboardButton("🔴 FB 0FD 2FA (Closed)", callback_data="type_disabled_fb_0fd_2fa"))
    
    kb.add(types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_submit"))
    
    return kb

# ================= 🤖 [ 4. USER BOT ] =================

def start_user_bot(token):
    if token in active_bots:
        return
    try:
        bot = telebot.TeleBot(token)
        active_bots.add(token)
        print(f"✅ User Bot started: {token[:15]}...")

        @bot.message_handler(commands=['start'])
        def welcome(m):
            save_user_id(m.chat.id)
            
            kb = types.InlineKeyboardMarkup(row_width=1)
            btn1 = types.InlineKeyboardButton("📁 Submit File", callback_data="submit_file")
            kb.add(btn1)
            
            bot.send_message(
                m.chat.id,
                f"✨ *ID RECEIVER BOT* ✨\n\n"
                f"👋 *Hello {m.from_user.first_name}!*\n\n"
                f"📂 *Supported:* XLSX, CSV\n"
                f"📌 *Required columns (case-insensitive):*\n"
                f"   • user / User / USER\n"
                f"   • pass / Pass / PASS\n"
                f"   • 2fa / 2Fa / 2FA (optional)\n"
                f"💳 *Payment:* bKash, Nagad, Rocket, Binance\n"
                f"🔄 *Auto duplicate remove*\n\n"
                f"📌 *Click below to start*",
                parse_mode="Markdown",
                reply_markup=kb
            )

        @bot.callback_query_handler(func=lambda c: True)
        def cb_handler(c):
            user_id = c.message.chat.id
            
            if c.data == "submit_file":
                try:
                    bot.delete_message(c.message.chat.id, c.message.message_id)
                except:
                    pass
                
                bot.send_message(
                    c.message.chat.id,
                    "📂 *Select File Type:*",
                    parse_mode="Markdown",
                    reply_markup=get_type_keyboard()
                )
            
            elif c.data.startswith("type_disabled_"):
                bot.answer_callback_query(c.id, "❌ This type is currently closed!", show_alert=True)
            
            elif c.data.startswith("type_"):
                file_type = c.data.replace("type_", "")
                
                if not type_status.get(file_type, False):
                    bot.answer_callback_query(c.id, "❌ This type is currently closed!", show_alert=True)
                    return
                
                user_sessions[user_id] = {"file_type": file_type}
                
                kb = types.InlineKeyboardMarkup(row_width=2)
                btn1 = types.InlineKeyboardButton("🏦 bKash", callback_data="pay_bkash")
                btn2 = types.InlineKeyboardButton("🏧 Nagad", callback_data="pay_nagad")
                btn3 = types.InlineKeyboardButton("💳 Rocket", callback_data="pay_rocket")
                btn4 = types.InlineKeyboardButton("₿ Binance", callback_data="pay_binance")
                btn5 = types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_submit")
                kb.add(btn1, btn2, btn3, btn4, btn5)
                
                try:
                    bot.delete_message(c.message.chat.id, c.message.message_id)
                except:
                    pass
                
                bot.send_message(
                    c.message.chat.id,
                    "💰 *Select Payment Method:*",
                    parse_mode="Markdown",
                    reply_markup=kb
                )
            
            elif c.data.startswith("pay_"):
                method = c.data.replace("pay_", "")
                method_name = method.capitalize()
                if method == "bkash":
                    method_name = "bKash"
                elif method == "binance":
                    method_name = "Binance"
                
                user_sessions[user_id]["payment_method"] = method_name
                
                try:
                    bot.delete_message(c.message.chat.id, c.message.message_id)
                except:
                    pass
                
                bot.send_message(
                    user_id,
                    f"✅ *{method_name} Selected*\n\n📝 Send your {method_name} number:",
                    parse_mode="Markdown"
                )
                bot.register_next_step_handler_by_chat_id(user_id, get_payment_number)
            
            elif c.data == "cancel_submit":
                user_sessions.pop(user_id, None)
                
                kb = types.InlineKeyboardMarkup(row_width=1)
                kb.add(types.InlineKeyboardButton("📁 Submit File", callback_data="submit_file"))
                
                try:
                    bot.delete_message(c.message.chat.id, c.message.message_id)
                except:
                    pass
                
                bot.send_message(
                    c.message.chat.id,
                    "❌ *Cancelled*\n\nClick below to start over:",
                    parse_mode="Markdown",
                    reply_markup=kb
                )

        def get_payment_number(m):
            user_id = m.chat.id
            
            if user_id not in user_sessions:
                bot.send_message(user_id, "❌ Session expired. Use /start")
                return
            
            payment_number = m.text.strip()
            user_sessions[user_id]["payment_number"] = payment_number
            
            bot.send_message(
                user_id,
                f"📎 *Send your file*\n\n📂 XLSX or CSV file\n📌 Must have columns: user, pass, 2fa (case-insensitive)\n\n📌 Upload:",
                parse_mode="Markdown"
            )
            bot.register_next_step_handler_by_chat_id(user_id, receive_file)

        def receive_file(m):
            user_id = m.chat.id
            
            if user_id not in user_sessions:
                bot.send_message(user_id, "❌ Session expired. Use /start")
                return
            
            if not m.document:
                bot.send_message(user_id, "❌ Send a valid file!")
                return
            
            file_type = user_sessions[user_id]["file_type"]
            filename = m.document.file_name.lower()
            
            if not (filename.endswith(".xlsx") or filename.endswith(".csv")):
                bot.send_message(user_id, "❌ Only .xlsx or .csv files are supported!")
                return
            
            file_info = bot.get_file(m.document.file_id)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_name = f"{user_id}_{timestamp}_{m.document.file_name}"
            save_path = os.path.join("uploads", file_type, save_name)
            
            downloaded_file = bot.download_file(file_info.file_path)
            with open(save_path, "wb") as f:
                f.write(downloaded_file)
            
            bot.send_message(user_id, "⏳ *Processing...*", parse_mode="Markdown")
            
            threading.Thread(
                target=process_file_worker,
                args=(
                    bot, user_id, file_type, save_path, 
                    m.document.file_name,
                    user_sessions[user_id]["payment_method"],
                    user_sessions[user_id]["payment_number"],
                    m.from_user.username or m.from_user.first_name
                ),
                daemon=True
            ).start()
            
            user_sessions.pop(user_id, None)

        bot.infinity_polling(timeout=60, skip_pending=True)
        
    except Exception as e:
        print(f"❌ User Bot Error: {e}")
        if token in active_bots:
            active_bots.remove(token)

# ================= 👑 [ 5. MASTER PANEL ] =================

@master_bot.message_handler(commands=['start'])
def m_start(m):
    if m.from_user.id not in ADMIN_IDS:
        master_bot.send_message(m.chat.id, "❌ Unauthorized!")
        return
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row("📊 Total Stats", "📥 Payment List")
    kb.row("📁 Download by Type", "🎛️ Type Control")
    kb.row("💳 Payment List Scanner", "📢 Broadcast")
    kb.row("⚙️ More Options")
    
    master_bot.send_message(
        m.chat.id,
        f"👑 *MASTER ADMIN PANEL* 👑\n\n"
        f"🎛️ *Current Status:*\n"
        f"🟢 IG Cookies: {'ON' if type_status['ig_cookies'] else 'OFF'}\n"
        f"🟢 IG 2FA: {'ON' if type_status['ig_2fa'] else 'OFF'}\n"
        f"🟢 FB 0FD 2FA: {'ON' if type_status['fb_0fd_2fa'] else 'OFF'}\n\n"
        f"📌 Select an option below",
        parse_mode="Markdown",
        reply_markup=kb
    )


# ================= ⚙️ [ 5.1 MORE OPTIONS ] =================

@master_bot.message_handler(func=lambda m: m.text == "⚙️ More Options")
def m_more_options(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row("➕ Add Bot", "❌ Remove Bot")
    kb.row("🔄 Reset All Types", "🗑 Clear All Data")
    kb.row("🔙 Back to Main Menu")
    
    master_bot.send_message(
        m.chat.id,
        "⚙️ *MORE OPTIONS*\n\nSelect an option below:",
        parse_mode="Markdown",
        reply_markup=kb
    )


@master_bot.message_handler(func=lambda m: m.text == "🔙 Back to Main Menu")
def back_to_main_menu(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    try:
        master_bot.delete_message(m.chat.id, m.message_id - 1)
    except:
        pass
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row("📊 Total Stats", "📥 Payment List")
    kb.row("📁 Download by Type", "🎛️ Type Control")
    kb.row("💳 Payment List Scanner", "📢 Broadcast")
    kb.row("⚙️ More Options")
    
    master_bot.send_message(
        m.chat.id,
        f"👑 *MASTER ADMIN PANEL* 👑\n\n"
        f"🎛️ *Current Status:*\n"
        f"🟢 IG Cookies: {'ON' if type_status['ig_cookies'] else 'OFF'}\n"
        f"🟢 IG 2FA: {'ON' if type_status['ig_2fa'] else 'OFF'}\n"
        f"🟢 FB 0FD 2FA: {'ON' if type_status['fb_0fd_2fa'] else 'OFF'}\n\n"
        f"📌 Select an option below",
        parse_mode="Markdown",
        reply_markup=kb
    )


# ================= 📢 [ 5.2 BROADCAST MESSAGE ] =================

@master_bot.message_handler(func=lambda m: m.text == "📢 Broadcast")
def m_broadcast(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    user_ids = load_user_ids()
    if not user_ids:
        master_bot.send_message(m.chat.id, "❌ No users found!", parse_mode="Markdown")
        return
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("📝 Text Message", callback_data="broadcast_text"),
        types.InlineKeyboardButton("📎 File/Media", callback_data="broadcast_file"),
        types.InlineKeyboardButton("🔙 Back", callback_data="broadcast_back")
    )
    
    master_bot.send_message(
        m.chat.id,
        f"📢 *BROADCAST MENU*\n\n"
        f"👥 Total users: {len(user_ids)}\n\n"
        f"Select what you want to broadcast:",
        parse_mode="Markdown",
        reply_markup=kb
    )


@master_bot.callback_query_handler(func=lambda c: c.data.startswith("broadcast_"))
def broadcast_callback(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, "❌ Unauthorized!")
        return
    
    if c.data == "broadcast_text":
        try:
            master_bot.delete_message(c.message.chat.id, c.message.message_id)
        except:
            pass
        
        msg = master_bot.send_message(
            c.message.chat.id,
            "📝 *Send your message*\n\n"
            "You can use Markdown formatting:\n"
            "• *bold*\n"
            "• _italic_\n"
            "• [link](url)\n\n"
            "Send /cancel to cancel:",
            parse_mode="Markdown"
        )
        master_bot.register_next_step_handler(msg, send_text_broadcast)
    
    elif c.data == "broadcast_file":
        try:
            master_bot.delete_message(c.message.chat.id, c.message.message_id)
        except:
            pass
        
        msg = master_bot.send_message(
            c.message.chat.id,
            "📎 *Send your file/photo/video*\n\n"
            "You can send:\n"
            "• Photo\n"
            "• Video\n"
            "• Document\n"
            "• Audio\n\n"
            "Send /cancel to cancel:",
            parse_mode="Markdown"
        )
        master_bot.register_next_step_handler(msg, send_media_broadcast)
    
    elif c.data == "broadcast_back":
        back_to_main_menu(c)


def send_text_broadcast(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    if m.text and m.text.startswith('/cancel'):
        master_bot.send_message(m.chat.id, "❌ Broadcast cancelled.")
        return
    
    try:
        master_bot.delete_message(m.chat.id, m.message_id)
    except:
        pass
    
    message_text = m.text
    entities = m.entities
    
    user_ids = load_user_ids()
    
    if not user_ids:
        master_bot.send_message(m.chat.id, "❌ No users found!")
        return
    
    status_msg = master_bot.send_message(m.chat.id, f"⏳ Sending to {len(user_ids)} users...")
    
    success = 0
    fail = 0
    
    for user_id in user_ids:
        sent = False
        for bot_token in active_bots:
            try:
                bot = telebot.TeleBot(bot_token)
                bot.send_message(user_id, message_text, parse_mode="Markdown", entities=entities)
                success += 1
                sent = True
                break
            except:
                continue
        if not sent:
            fail += 1
    
    try:
        master_bot.delete_message(m.chat.id, status_msg.message_id)
    except:
        pass
    
    result_msg = f"✅ *Broadcast Complete!*\n\n"
    result_msg += f"📤 Success: {success}\n"
    result_msg += f"❌ Failed: {fail}\n"
    result_msg += f"👥 Total users: {len(user_ids)}"
    
    master_bot.send_message(m.chat.id, result_msg, parse_mode="Markdown")


def send_media_broadcast(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    user_ids = load_user_ids()
    
    if not user_ids:
        master_bot.send_message(m.chat.id, "❌ No users found!")
        return
    
    try:
        master_bot.delete_message(m.chat.id, m.message_id)
    except:
        pass
    
    status_msg = master_bot.send_message(m.chat.id, f"⏳ Sending to {len(user_ids)} users...")
    
    success = 0
    fail = 0
    
    for user_id in user_ids:
        sent = False
        for bot_token in active_bots:
            try:
                bot = telebot.TeleBot(bot_token)
                
                if m.photo:
                    bot.send_photo(user_id, m.photo[-1].file_id, caption=m.caption)
                elif m.video:
                    bot.send_video(user_id, m.video.file_id, caption=m.caption)
                elif m.document:
                    bot.send_document(user_id, m.document.file_id, caption=m.caption)
                elif m.audio:
                    bot.send_audio(user_id, m.audio.file_id, caption=m.caption)
                else:
                    master_bot.send_message(m.chat.id, "❌ Unsupported media type!")
                    return
                
                success += 1
                sent = True
                break
            except:
                continue
        if not sent:
            fail += 1
    
    try:
        master_bot.delete_message(m.chat.id, status_msg.message_id)
    except:
        pass
    
    result_msg = f"✅ *Broadcast Complete!*\n\n"
    result_msg += f"📤 Success: {success}\n"
    result_msg += f"❌ Failed: {fail}\n"
    result_msg += f"👥 Total users: {len(user_ids)}"
    
    master_bot.send_message(m.chat.id, result_msg, parse_mode="Markdown")


# ================= 📥 [ 5.3 PAYMENT LIST ] =================

@master_bot.message_handler(func=lambda m: m.text == "📥 Payment List")
def m_payment_list(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    global current_ok_data
    db = load_db()
    
    submitter_data = []
    
    for file_type in ["ig_cookies", "ig_2fa", "fb_0fd_2fa"]:
        files_data = db["files"].get(file_type, {})
        
        for file_hash, file_info in files_data.items():
            submitted_by = file_info.get("submitted_by", "Unknown")
            payment_method = file_info.get("payment_method", "Unknown")
            payment_number = file_info.get("payment_number", "Unknown")
            total_rows = file_info.get("total_rows_in_file", 0)
            ok_count = 0
            
            if current_ok_data["results"] and submitted_by in current_ok_data["results"]:
                ok_count = current_ok_data["results"][submitted_by].get("total_ok", 0)
            
            submitter_data.append({
                "submitted_by": submitted_by,
                "payment": payment_method,
                "number": payment_number,
                "total_files": 1,
                "total_rows": total_rows,
                "ok": ok_count
            })
    
    if not submitter_data:
        master_bot.send_message(m.chat.id, "❌ No data found!", parse_mode="Markdown")
        return
    
    # Group and sort by payment method
    payment_order = {"bKash": 1, "Nagad": 2, "Rocket": 3, "Binance": 4}
    submitter_data.sort(key=lambda x: (payment_order.get(x["payment"], 999), -x["total_rows"]))
    
    df = pd.DataFrame(submitter_data)
    
    data_file = f"payment_list_{m.chat.id}.xlsx"
    try:
        df.to_excel(data_file, index=False)
    except:
        data_file = f"payment_list_{m.chat.id}.csv"
        df.to_csv(data_file, index=False, encoding='utf-8-sig')
    
    total_submitters = len(submitter_data)
    total_files = sum(d["total_files"] for d in submitter_data)
    total_rows = sum(d["total_rows"] for d in submitter_data)
    total_ok = sum(d["ok"] for d in submitter_data)
    
    bkash_count = len([x for x in submitter_data if x["payment"] == "bKash"])
    nagad_count = len([x for x in submitter_data if x["payment"] == "Nagad"])
    rocket_count = len([x for x in submitter_data if x["payment"] == "Rocket"])
    binance_count = len([x for x in submitter_data if x["payment"] == "Binance"])
    
    summary = f"✅ *PAYMENT LIST REPORT*\n\n"
    summary += f"👥 Total Submitters: {total_submitters}\n"
    summary += f"📁 Total Files: {total_files}\n"
    summary += f"📊 Total Rows: {total_rows}\n"
    summary += f"✅ Total OK: {total_ok}\n"
    summary += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    summary += f"🏦 *bKash:* {bkash_count} users\n"
    summary += f"🏧 *Nagad:* {nagad_count} users\n"
    summary += f"💳 *Rocket:* {rocket_count} users\n"
    summary += f"₿ *Binance:* {binance_count} users\n\n"
    summary += f"📥 Downloading file..."
    
    master_bot.send_message(m.chat.id, summary, parse_mode="Markdown")
    
    with open(data_file, "rb") as f:
        master_bot.send_document(
            m.chat.id, 
            f, 
            caption=f"📊 PAYMENT LIST\n\nColumns: submitted_by, payment, number, total_files, total_rows, ok"
        )
    
    os.remove(data_file)


# ================= 💳 [ 5.4 PAYMENT LIST SCANNER ] =================

@master_bot.message_handler(func=lambda m: m.text == "💳 Payment List Scanner")
def m_payment_scanner(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📁 IG Cookies", callback_data="scan_type_ig_cookies"),
        types.InlineKeyboardButton("🔐 IG 2FA", callback_data="scan_type_ig_2fa"),
        types.InlineKeyboardButton("📘 FB 0FD 2FA", callback_data="scan_type_fb_0fd_2fa"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="scan_type_cancel")
    )
    
    master_bot.send_message(
        m.chat.id,
        "📁 *Which type to scan?*\n\n"
        "Select an option below:",
        parse_mode="Markdown",
        reply_markup=kb
    )


@master_bot.callback_query_handler(func=lambda c: c.data.startswith("scan_type_"))
def m_scan_type_callback(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, "❌ Unauthorized!")
        return
    
    if c.data == "scan_type_cancel":
        try:
            master_bot.delete_message(c.message.chat.id, c.message.message_id)
        except:
            pass
        master_bot.send_message(c.message.chat.id, "❌ Cancelled.")
        return
    
    scan_type = c.data.replace("scan_type_", "")
    
    type_names = {
        "ig_cookies": "📁 IG Cookies",
        "ig_2fa": "🔐 IG 2FA", 
        "fb_0fd_2fa": "📘 FB 0FD 2FA"
    }
    display_type = type_names.get(scan_type, scan_type)
    
    user_sessions[c.message.chat.id] = {"scan_type": scan_type}
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    msg = master_bot.send_message(
        c.message.chat.id,
        f"✅ *{display_type} Selected*\n\n"
        f"📁 Now send your OK TXT file:\n\n"
        f"💡 Tip: Only {display_type} data will be scanned.",
        parse_mode="Markdown"
    )
    
    master_bot.register_next_step_handler_by_chat_id(c.message.chat.id, scan_ok_list)


def scan_ok_list(m):
    global current_ok_data
    
    if m.from_user.id not in ADMIN_IDS:
        return
    
    scan_type = user_sessions.get(m.chat.id, {}).get("scan_type", "all")
    user_sessions.pop(m.chat.id, None)
    
    if not m.document:
        master_bot.send_message(m.chat.id, "❌ Send a TXT file!")
        return
    
    if not m.document.file_name.endswith('.txt'):
        master_bot.send_message(m.chat.id, "❌ Only TXT files are supported!")
        return
    
    try:
        master_bot.delete_message(m.chat.id, m.message_id)
    except:
        pass
    
    file_info = master_bot.get_file(m.document.file_id)
    downloaded_file = master_bot.download_file(file_info.file_path)
    
    try:
        content = downloaded_file.decode('utf-8')
        ok_list = [line.strip().lower() for line in content.split('\n') if line.strip()]
    except:
        master_bot.send_message(m.chat.id, "❌ Failed to read file! Use UTF-8 encoding.")
        return
    
    if not ok_list:
        master_bot.send_message(m.chat.id, "❌ No data found in TXT file!")
        return
    
    type_display = {
        "ig_cookies": "📁 IG Cookies",
        "ig_2fa": "🔐 IG 2FA",
        "fb_0fd_2fa": "📘 FB 0FD 2FA"
    }
    
    status_msg = master_bot.send_message(
        m.chat.id, 
        f"⏳ *Scanning started...*\n\n"
        f"📂 Type: {type_display.get(scan_type, scan_type)}\n"
        f"📊 OK List: {len(ok_list)} users\n\n"
        f"🔍 Searching for matches...",
        parse_mode="Markdown"
    )
    
    db = load_db()
    results = {}
    
    files_data = db["files"].get(scan_type, {})
    
    total_files = len(files_data)
    total_user_data = 0
    
    for file_hash, file_info in files_data.items():
        original_data = file_info.get("original_data", [])
        submitted_by = file_info.get("submitted_by", "Unknown")
        payment_method = file_info.get("payment_method", "Unknown")
        payment_number = file_info.get("payment_number", "Unknown")
        
        for row in original_data:
            total_user_data += 1
            user_field = str(row.get("user", "")).strip().lower()
            
            for ok_username in ok_list:
                if ok_username and ok_username == user_field:
                    if submitted_by not in results:
                        results[submitted_by] = {
                            "total_ok": 0,
                            "submitted_by": submitted_by,
                            "payment_method": payment_method,
                            "payment_number": payment_number,
                            "file_type": scan_type
                        }
                    results[submitted_by]["total_ok"] += 1
    
    current_ok_data = {
        "total_ok": sum(r["total_ok"] for r in results.values()),
        "total_users": len(results),
        "last_scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
        "scan_type": scan_type
    }
    
    try:
        master_bot.delete_message(m.chat.id, status_msg.message_id)
    except:
        pass
    
    if not results:
        master_bot.send_message(
            m.chat.id,
            f"❌ *NO MATCHES FOUND!*\n\n"
            f"📂 Type: {type_display.get(scan_type, scan_type)}\n"
            f"📊 Checked: {len(ok_list)} users\n"
            f"📁 Files scanned: {total_files}\n"
            f"📊 Data scanned: {total_user_data}\n"
            f"✅ Matches: 0",
            parse_mode="Markdown"
        )
        return
    
    total_ok_count = current_ok_data['total_ok']
    
    summary = f"✅ *SCAN COMPLETE!*\n\n"
    summary += f"📂 *Type:* {type_display.get(scan_type, scan_type)}\n"
    summary += f"📊 *OK List:* {len(ok_list)} users\n"
    summary += f"📁 *Files Scanned:* {total_files}\n"
    summary += f"📊 *Total Data Scanned:* {total_user_data}\n"
    summary += f"━━━━━━━━━━━━━━━━━━━━\n"
    summary += f"✅ *Matched Submitters:* {len(results)}\n"
    summary += f"📈 *Total OK Count:* {total_ok_count}\n"
    summary += f"🕐 *Scan Time:* {current_ok_data['last_scan_time']}\n\n"
    summary += f"💡 Click '📥 Payment List' to download full report"
    
    master_bot.send_message(m.chat.id, summary, parse_mode="Markdown")


# ================= 🎛️ [ 5.5 TYPE CONTROL ] =================

@master_bot.message_handler(func=lambda m: m.text == "🎛️ Type Control")
def m_type_control(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(f"{'🟢' if type_status['ig_cookies'] else '🔴'} IG Cookies", callback_data="toggle_ig_cookies"),
        types.InlineKeyboardButton(f"{'🟢' if type_status['ig_2fa'] else '🔴'} IG 2FA", callback_data="toggle_ig_2fa"),
        types.InlineKeyboardButton(f"{'🟢' if type_status['fb_0fd_2fa'] else '🔴'} FB 0FD 2FA", callback_data="toggle_fb_0fd_2fa"),
        types.InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")
    )
    
    master_bot.send_message(
        m.chat.id,
        "🎛️ *TYPE CONTROL PANEL*\n\nClick to toggle ON/OFF:",
        parse_mode="Markdown",
        reply_markup=kb
    )


@master_bot.callback_query_handler(func=lambda c: c.data.startswith("toggle_"))
def m_toggle_type(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, "❌ Unauthorized!")
        return
    
    type_name = c.data.replace("toggle_", "")
    type_status[type_name] = not type_status.get(type_name, True)
    
    status_text = "ON 🟢" if type_status[type_name] else "OFF 🔴"
    master_bot.answer_callback_query(c.id, f"{type_name} is now {status_text}")
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(f"{'🟢' if type_status['ig_cookies'] else '🔴'} IG Cookies", callback_data="toggle_ig_cookies"),
        types.InlineKeyboardButton(f"{'🟢' if type_status['ig_2fa'] else '🔴'} IG 2FA", callback_data="toggle_ig_2fa"),
        types.InlineKeyboardButton(f"{'🟢' if type_status['fb_0fd_2fa'] else '🔴'} FB 0FD 2FA", callback_data="toggle_fb_0fd_2fa"),
        types.InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")
    )
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    master_bot.send_message(
        c.message.chat.id,
        f"🎛️ *TYPE CONTROL PANEL*\n\n"
        f"🟢 IG Cookies: {'ON' if type_status['ig_cookies'] else 'OFF'}\n"
        f"🟢 IG 2FA: {'ON' if type_status['ig_2fa'] else 'OFF'}\n"
        f"🟢 FB 0FD 2FA: {'ON' if type_status['fb_0fd_2fa'] else 'OFF'}\n\n"
        f"Click to toggle:",
        parse_mode="Markdown",
        reply_markup=kb
    )


# ================= 📊 [ 5.6 TOTAL STATS ] =================

@master_bot.message_handler(func=lambda m: m.text == "📊 Total Stats")
def m_stats(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    db = load_db()
    total_files = 0
    
    for file_type, files in db["files"].items():
        total_files += len(files)
    
    user_ids = load_user_ids()
    
    global_unique_count = len(db.get("global_unique_keys", []))
    
    stats_msg = (
        f"📊 *STATISTICS*\n\n"
        f"🤖 Bots: {len(db['tokens'])}\n"
        f"👥 Users: {len(user_ids)}\n"
        f"📁 Files: {total_files}\n"
        f"📊 Total Records (unique user+pass+2fa): {global_unique_count}\n\n"
        f"🎛️ *Type Status:*\n"
        f"IG Cookies: {'🟢 ON' if type_status['ig_cookies'] else '🔴 OFF'}\n"
        f"IG 2FA: {'🟢 ON' if type_status['ig_2fa'] else '🔴 OFF'}\n"
        f"FB 0FD 2FA: {'🟢 ON' if type_status['fb_0fd_2fa'] else '🔴 OFF'}"
    )
    master_bot.send_message(m.chat.id, stats_msg, parse_mode="Markdown")


# ================= 📁 [ 5.7 DOWNLOAD BY TYPE ] =================

@master_bot.message_handler(func=lambda m: m.text == "📁 Download by Type")
def m_download_by_type(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📁 IG Cookies", callback_data="dltype_ig_cookies"),
        types.InlineKeyboardButton("🔐 IG 2FA", callback_data="dltype_ig_2fa"),
        types.InlineKeyboardButton("📘 FB 0FD 2FA", callback_data="dltype_fb_0fd_2fa"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="dltype_cancel")
    )
    master_bot.send_message(m.chat.id, "Select type:", reply_markup=kb)


@master_bot.callback_query_handler(func=lambda c: c.data.startswith("dltype_"))
def m_download_type_callback(c):
    if c.data == "dltype_cancel":
        try:
            master_bot.delete_message(c.message.chat.id, c.message.message_id)
        except:
            pass
        master_bot.send_message(c.message.chat.id, "Cancelled.")
        return
    
    file_type = c.data.replace("dltype_", "")
    db = load_db()
    
    type_names = {"ig_cookies": "IG Cookies", "ig_2fa": "IG 2FA", "fb_0fd_2fa": "FB 0FD 2FA"}
    display_type = type_names.get(file_type, file_type)
    
    all_unique_data = db["all_unique_data"].get(file_type, {})
    
    if not all_unique_data:
        master_bot.answer_callback_query(c.id, f"No data for {display_type}")
        return
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    status_msg = master_bot.send_message(
        c.message.chat.id, 
        f"⏳ Generating {display_type} data...",
        parse_mode="Markdown"
    )
    
    data_file = f"user_data_{file_type}_{c.message.chat.id}.csv"
    
    total_rows = 0
    rows_with_2fa = 0
    
    with open(data_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["user", "pass", "2fa", "submitted_by", "submitted_at"])
        
        for key, item in all_unique_data.items():
            if "data" in item and isinstance(item["data"], list):
                for row in item["data"]:
                    total_rows += 1
                    user_val = row.get("user", "")
                    pass_val = row.get("pass", "")
                    twofa_val = row.get("2fa", "")
                    
                    if twofa_val:
                        rows_with_2fa += 1
                    
                    writer.writerow([
                        user_val,
                        pass_val,
                        twofa_val,
                        item.get("submitted_by", ""),
                        item.get("submitted_at", "")
                    ])
    
    try:
        master_bot.delete_message(c.message.chat.id, status_msg.message_id)
    except:
        pass
    
    with open(data_file, "rb") as f:
        master_bot.send_document(
            c.message.chat.id, 
            f, 
            caption=f"📊 {display_type}\n\nTotal rows: {total_rows}\nRows with 2FA: {rows_with_2fa}"
        )
    
    os.remove(data_file)
    master_bot.answer_callback_query(c.id, f"{display_type} data sent!")


# ================= ➕ [ 5.8 ADD/REMOVE BOT ] =================

@master_bot.message_handler(func=lambda m: m.text == "➕ Add Bot")
def m_add_bot(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    msg = master_bot.send_message(m.chat.id, "🤖 *Send Bot Token:*", parse_mode="Markdown")
    master_bot.register_next_step_handler(msg, save_bot_token)


def save_bot_token(m):
    if m.text.startswith('/'):
        master_bot.send_message(m.chat.id, "❌ Cancelled.")
        return
    
    token = m.text.strip()
    if ':' not in token or len(token) < 30:
        master_bot.send_message(m.chat.id, "❌ Invalid token!")
        return
    
    db = load_db()
    if token not in db["tokens"]:
        db["tokens"].append(token)
        save_db(db)
        threading.Thread(target=start_user_bot, args=(token,), daemon=True).start()
        master_bot.send_message(m.chat.id, "✅ Bot added!")
    else:
        master_bot.send_message(m.chat.id, "⚠️ Bot already exists!")


@master_bot.message_handler(func=lambda m: m.text == "❌ Remove Bot")
def m_remove_bot(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    db = load_db()
    if not db["tokens"]:
        master_bot.send_message(m.chat.id, "❌ No bots!")
        return
    
    kb = types.InlineKeyboardMarkup()
    for i, token in enumerate(db["tokens"]):
        kb.add(types.InlineKeyboardButton(f"🤖 Bot {i+1}", callback_data=f"remove_{i}"))
    kb.add(types.InlineKeyboardButton("❌ Cancel", callback_data="remove_cancel"))
    master_bot.send_message(m.chat.id, "Select bot:", reply_markup=kb)


@master_bot.callback_query_handler(func=lambda c: c.data.startswith("remove_"))
def m_remove_callback(c):
    if c.data == "remove_cancel":
        try:
            master_bot.delete_message(c.message.chat.id, c.message.message_id)
        except:
            pass
        master_bot.send_message(c.message.chat.id, "❌ Cancelled.")
        return
    
    idx = int(c.data.split("_")[1])
    db = load_db()
    if 0 <= idx < len(db["tokens"]):
        removed = db["tokens"].pop(idx)
        save_db(db)
        if removed in active_bots:
            active_bots.remove(removed)
        
        try:
            master_bot.delete_message(c.message.chat.id, c.message.message_id)
        except:
            pass
        
        master_bot.send_message(c.message.chat.id, f"✅ Bot removed")


# ================= 🗑 [ 5.9 CLEAR ALL DATA ] =================

@master_bot.message_handler(func=lambda m: m.text == "🗑 Clear All Data")
def m_clear_all(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("⚠️ YES", callback_data="confirm_clear_all"),
        types.InlineKeyboardButton("❌ NO", callback_data="cancel_clear_all")
    )
    
    master_bot.send_message(m.chat.id, "⚠️ *DELETE ALL DATA?*", parse_mode="Markdown", reply_markup=kb)


@master_bot.callback_query_handler(func=lambda c: c.data == "confirm_clear_all")
def m_confirm_clear(c):
    if c.from_user.id not in ADMIN_IDS:
        return
    
    for folder in ["ig_cookies", "ig_2fa", "fb_0fd_2fa"]:
        folder_path = f"uploads/{folder}"
        if os.path.exists(folder_path):
            for f in os.listdir(folder_path):
                try:
                    os.remove(os.path.join(folder_path, f))
                except:
                    pass
    
    db = load_db()
    db["files"] = {"ig_cookies": {}, "ig_2fa": {}, "fb_0fd_2fa": {}}
    db["all_unique_data"] = {"ig_cookies": {}, "ig_2fa": {}, "fb_0fd_2fa": {}}
    db["global_unique_keys"] = []
    save_db(db)
    
    global current_ok_data
    current_ok_data = {
        "total_ok": 0,
        "total_users": 0,
        "last_scan_time": None,
        "results": {},
        "scan_type": None
    }
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    master_bot.send_message(c.message.chat.id, "✅ *ALL DATA DELETED!*", parse_mode="Markdown")


@master_bot.callback_query_handler(func=lambda c: c.data == "cancel_clear_all")
def m_cancel_clear(c):
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    master_bot.send_message(c.message.chat.id, "❌ Cancelled", parse_mode="Markdown")


# ================= 🔄 [ 5.10 RESET ALL TYPES ] =================

@master_bot.message_handler(func=lambda m: m.text == "🔄 Reset All Types")
def m_reset_types(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    global type_status
    type_status = {
        "ig_cookies": True,
        "ig_2fa": True,
        "fb_0fd_2fa": True
    }
    
    master_bot.send_message(m.chat.id, "✅ *All types reset to ON!*", parse_mode="Markdown")


# ================= 🔄 [ 5.11 BACK TO MENU CALLBACK ] =================

@master_bot.callback_query_handler(func=lambda c: c.data == "back_to_menu")
def m_back_to_menu(c):
    if c.from_user.id not in ADMIN_IDS:
        return
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row("📊 Total Stats", "📥 Payment List")
    kb.row("📁 Download by Type", "🎛️ Type Control")
    kb.row("💳 Payment List Scanner", "📢 Broadcast")
    kb.row("⚙️ More Options")
    
    master_bot.send_message(
        c.message.chat.id,
        f"👑 *MASTER ADMIN PANEL* 👑\n\n"
        f"🎛️ *Current Status:*\n"
        f"🟢 IG Cookies: {'ON' if type_status['ig_cookies'] else 'OFF'}\n"
        f"🟢 IG 2FA: {'ON' if type_status['ig_2fa'] else 'OFF'}\n"
        f"🟢 FB 0FD 2FA: {'ON' if type_status['fb_0fd_2fa'] else 'OFF'}\n\n"
        f"📌 Select an option below",
        parse_mode="Markdown",
        reply_markup=kb
    )


# ================= 🔄 [ 6. MAIN ] =================

def run_all_bots():
    db = load_db()
    tokens = db.get("tokens", [])
    print(f"🔄 Loading {len(tokens)} user bots...")
    for token in tokens:
        if token not in active_bots:
            threading.Thread(target=start_user_bot, args=(token,), daemon=True).start()
            time.sleep(2)


if __name__ == "__main__":
    print("=" * 50)
    print("👑 ID RECEIVER SYSTEM v17.0")
    print("🎛️ CASE-INSENSITIVE COLUMN MATCHING")
    print("🎛️ 3-COLUMN DUPLICATE CHECK (user+pass+2fa)")
    print("=" * 50)
    
    load_db()
    run_all_bots()
    
    print(f"✅ Master Bot Online!")
    print(f"📌 Send /start to access admin panel")
    print("=" * 50)
    
    while True:
        try:
            master_bot.infinity_polling(timeout=60, skip_pending=True)
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(5)
