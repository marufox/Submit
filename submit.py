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

# ================= 💎 [ PREMIUM EMOJIS - UPDATED ] =================

PEM = {
    # 📱 Social Media - Premium
    "facebook": "📘",
    "fb": "📘",
    "fb_0fd_2fa": "📘",
    "fb_cookies": "🍪",
    "whatsapp": "💬",
    "wa": "💬",
    "telegram": "✈️",
    "tg": "✈️",
    "whatsapp_business": "💼",
    "wab": "💼",
    "imo": "💭",
    "instagram": "📸",
    "ig": "📸",
    "ig_cookies": "📱",
    "ig_2fa": "🔐",
    "apple": "🍎",
    "google": "🔍",
    "microsoft": "🪟",
    "teams": "🧑‍🤝‍🧑",
    "tiktok": "🎵",
    
    # 💰 Payment
    "bkash": "🏦",
    "nagad": "🏧",
    "rocket": "🚀",
    "binance": "💱",
    "bybit": "📈",
    "paypal": "💰",
    "stripe": "💳",
    
    # 🔧 General
    "ok": "✅",
    "no": "❌",
    "warn": "⚠️",
    "admin": "👑",
    "user": "👤",
    "file": "📁",
    "graph": "📊",
    "money": "💰",
    "gift": "🎁",
    "msg": "💬",
    "gear": "⚙️",
    "link": "🔗",
    "trash": "🗑️",
    "upload": "📤",
    "world": "🌐",
    "lock": "🔐",
    "phone": "📱",
    "num": "🔢",
    "pin": "📍",
    "star": "✨",
    "hi": "👋",
    "cookies": "🍪",
    "uid": "🆔",
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "payment": "💳",
    "stats": "📊",
    "bot": "🤖",
    "master": "👑",
    "time": "⏰",
    "date": "📅",
    "download": "📥",
    "settings": "⚙️",
    "search": "🔍",
    "refresh": "🔄",
    "add": "➕",
    "remove": "➖",
    "back": "🔙",
    "info": "ℹ️",
    "check": "✔️",
    "broadcast": "📢",
    "message": "💬",
    "attention": "‼️",
    "fire": "🔥",
    "crown": "👑",
    "shield": "🛡️",
    "online": "🟢",
    "offline": "🔴",
    "pending": "🟡",
    "approved": "✅",
    "rejected": "❌",
    "processing": "⏳",
    "completed": "✅",
    "cancelled": "❌",
    "paused": "⏸️",
    "stopped": "⏹️",
    "running": "▶️",
    "waiting": "⏳",
    "error": "❌",
    "success": "✅",
    "failed": "❌"
}

# ================= 🔧 [ TYPE NAMES & ICONS - UPDATED ] =================

TYPE_NAMES = {
    "ig_cookies": "Instagram Cookies",
    "ig_2fa": "Instagram 2FA",
    "fb_0fd_2fa": "Facebook 0FD Cookies"
}

TYPE_ICONS = {
    "ig_cookies": PEM.get("ig_cookies", "📱"),
    "ig_2fa": PEM.get("ig_2fa", "🔐"),
    "fb_0fd_2fa": PEM.get("fb_0fd_2fa", "📘")
}

# ================= 🔧 [ CONFIGURATION ] =================

# Environment Variables
MASTER_ADMIN_TOKEN = os.environ.get("MASTER_ADMIN_TOKEN")
ADMIN_IDS_STR = os.environ.get("ADMIN_IDS", "6293094676")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(",")]

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
    "scan_type": None,
    "ok_list_count": 0,
    "total_files_scanned": 0,
    "total_data_scanned": 0
}

def get_type_display_name(type_key):
    return TYPE_NAMES.get(type_key, type_key)

def get_type_icon(type_key):
    return TYPE_ICONS.get(type_key, "📁")

# User IDs
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
os.makedirs("reports", exist_ok=True)

# ================= 📁 [ DATABASE ] =================

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
                "global_unique_keys": [],
                "user_payment_settings": {}
            }
            with open(DB_FILE, "w") as f:
                json.dump(default, f, indent=4)
            return default
        with open(DB_FILE, "r") as f:
            data = json.load(f)
            if "global_unique_keys" not in data:
                data["global_unique_keys"] = []
            if "user_payment_settings" not in data:
                data["user_payment_settings"] = {}
            return data

def save_db(data):
    with db_lock:
        temp_file = DB_FILE + ".tmp"
        with open(temp_file, "w") as f:
            json.dump(data, f, indent=4)
        os.replace(temp_file, DB_FILE)

# ================= 🔐 [ FILE PROCESSING - FACEBOOK 0FD COOKIES SUPPORT ] =================

def auto_detect_columns(row):
    user_val = ""
    pass_val = ""
    cookies_val = ""
    uid_val = ""
    
    row_lower = {str(k).lower().strip(): v for k, v in row.items()}
    
    for k, v in row_lower.items():
        v_str = str(v).strip()
        if v_str and v_str != 'nan' and v_str != 'None':
            if k in ['uid', 'user_id', 'id', 'userid']:
                uid_val = v_str
            elif k in ['cookies', 'cookie', 'c_user', 'xs', 'datr', 'sb', 'dpr', 'wd', 'm_pixel_ratio', 'ps_l', 'ps_n', 'fr']:
                if not cookies_val:
                    cookies_val = v_str
                else:
                    cookies_val += "; " + v_str
            elif k in ['pass', 'password', 'pwd']:
                pass_val = v_str
            elif k in ['user', 'username', 'email', 'mail']:
                user_val = v_str
    
    if uid_val and cookies_val:
        return uid_val, pass_val, cookies_val, "cookies_mode"
    
    if uid_val and pass_val:
        return uid_val, pass_val, "", "uid_mode"
    
    values = [str(v).strip() for v in row.values() if str(v).strip() and str(v).strip() != 'nan' and str(v).strip() != 'None']
    
    if len(values) == 0:
        return "", "", "", ""
    if len(values) == 1:
        return values[0], "", "", ""
    if len(values) == 2:
        return values[0], values[1], "", ""
    if len(values) >= 3:
        email_idx = -1
        for i, val in enumerate(values):
            if '@' in val and '.' in val:
                email_idx = i
                break
        
        if email_idx != -1:
            user_val = values[email_idx]
            for i, val in enumerate(values):
                if i != email_idx and len(val) >= 4:
                    if not pass_val:
                        pass_val = val
                    elif not cookies_val and (';' in val or '=' in val):
                        cookies_val = val
            if not cookies_val:
                for i, val in enumerate(values):
                    if i != email_idx and val != pass_val:
                        if ';' in val or '=' in val:
                            cookies_val = val
        else:
            user_val = values[0]
            pass_val = values[1]
            if len(values) >= 3:
                cookies_val = values[2]
    
    return user_val, pass_val, cookies_val, "normal_mode"

def process_file_with_columns(file_path, original_filename, file_type):
    try:
        if original_filename.endswith('.csv'):
            df = pd.read_csv(file_path)
        elif original_filename.endswith('.xlsx'):
            df = pd.read_excel(file_path)
        else:
            return None, 0, None, 0, 0
        
        if df is None or df.empty:
            return None, 0, None, 0, 0
        
        filtered_data = []
        empty_count = 0
        rows_with_cookies = 0
        
        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            user_val, pass_val, cookies_val, mode = auto_detect_columns(row_dict)
            
            if mode == "cookies_mode":
                filtered_data.append({
                    "user": user_val,
                    "pass": pass_val,
                    "cookies": cookies_val,
                    "2fa": "",
                    "mode": "cookies"
                })
                rows_with_cookies += 1
            elif mode == "uid_mode":
                filtered_data.append({
                    "user": user_val,
                    "pass": pass_val,
                    "cookies": "",
                    "2fa": "",
                    "mode": "uid"
                })
            else:
                if cookies_val and (';' in cookies_val or '=' in cookies_val):
                    filtered_data.append({
                        "user": user_val,
                        "pass": pass_val,
                        "cookies": cookies_val,
                        "2fa": "",
                        "mode": "cookies"
                    })
                    rows_with_cookies += 1
                else:
                    filtered_data.append({
                        "user": user_val,
                        "pass": pass_val,
                        "cookies": "",
                        "2fa": cookies_val if cookies_val else "",
                        "mode": "normal"
                    })
        
        with open(file_path, "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        
        valid_rows = len([d for d in filtered_data if d['user'] or d['pass'] or d['cookies']])
        
        return filtered_data, valid_rows, file_hash, empty_count, rows_with_cookies
        
    except Exception as e:
        print(f"Process error: {e}")
        return None, 0, None, 0, 0

def process_file_worker(bot, chat_id, file_type, file_path, original_name, payment_method, payment_number, username):
    try:
        db = load_db()
        
        filtered_data, valid_rows, file_hash, empty_rows, rows_with_cookies = process_file_with_columns(
            file_path, original_name, file_type
        )
        
        if filtered_data is None or not filtered_data or valid_rows == 0:
            os.remove(file_path)
            bot.send_message(
                chat_id, 
                f"{PEM['no']} NO DATA FOUND!\n\nYour file was empty or had no readable data."
            )
            return False
        
        file_db = db["files"][file_type]
        
        if file_hash in file_db:
            with open(file_path, "rb") as dup_file:
                bot.send_document(chat_id, dup_file, caption=f"{PEM['warn']} DUPLICATE FILE!")
            os.remove(file_path)
            return False
        
        unique_rows = []
        duplicate_rows = []
        seen_keys = set()
        
        for row in filtered_data:
            row_key = f"{row['user']}_{row['pass']}_{row['cookies']}".lower()
            if row_key in seen_keys:
                duplicate_rows.append(row)
            else:
                seen_keys.add(row_key)
                unique_rows.append(row)
        
        global_unique_keys = set(db.get("global_unique_keys", []))
        
        truly_unique_rows = []
        global_duplicate_rows = []
        
        for row in unique_rows:
            row_key = f"{row['user']}_{row['pass']}_{row['cookies']}".lower()
            if row_key in global_unique_keys:
                global_duplicate_rows.append(row)
            else:
                global_unique_keys.add(row_key)
                truly_unique_rows.append(row)
        
        db["global_unique_keys"] = list(global_unique_keys)
        
        filtered_data = truly_unique_rows
        valid_rows = len(filtered_data)
        
        if valid_rows == 0:
            os.remove(file_path)
            bot.send_message(
                chat_id,
                f"{PEM['no']} NO UNIQUE DATA!\n\nAll rows already exist in database."
            )
            return False
        
        current_date = datetime.now().strftime("%Y%m%d_%H%M%S")
        
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
            "empty_rows": empty_rows,
            "received_date": current_date,
            "rows_with_cookies": rows_with_cookies
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
            "total_rows": valid_rows,
            "received_date": current_date,
            "rows_with_cookies": rows_with_cookies
        }
        
        save_db(db)
        
        backup_filename = f"{file_type}_{current_date}_{original_name}"
        backup_path = os.path.join("backup", backup_filename)
        with open(file_path, "rb") as src, open(backup_path, "wb") as dst:
            dst.write(src.read())
        
        result_msg = f"""{PEM['ok']} <b>FILE PROCESSED SUCCESSFULLY</b> {PEM['ok']}

{PEM['file']} <b>File:</b> {original_name}
{get_type_icon(file_type)} <b>Type:</b> {get_type_display_name(file_type)}
{PEM['payment']} <b>Payment:</b> {payment_method} - {payment_number}
{PEM['date']} <b>Received:</b> {current_date}

━━━━━━━━━━━━━━━━━━━━
{PEM['stats']} <b>Valid rows:</b> {valid_rows}
"""
        
        if rows_with_cookies > 0:
            result_msg += f"{PEM['cookies']} <b>Cookies rows:</b> {rows_with_cookies}\n"
        
        result_msg += f"""
{PEM['star']} <b>Status:</b> Successfully received

━━━━━━━━━━━━━━━━━━━━
{PEM['shield']} <b>Secure • Fast • Reliable</b>"""
        
        bot.send_message(chat_id, result_msg, parse_mode="HTML")
        
        for admin_id in ADMIN_IDS:
            try:
                master_bot.send_message(
                    admin_id, 
                    f"""{PEM['broadcast']} <b>NEW FILE RECEIVED!</b>

{PEM['user']} <b>User:</b> {username}
{get_type_icon(file_type)} <b>Type:</b> {get_type_display_name(file_type)}
{PEM['stats']} <b>Rows:</b> {valid_rows}
{PEM['payment']} <b>Payment:</b> {payment_method} - {payment_number}
{PEM['date']} <b>Date:</b> {current_date}""",
                    parse_mode="HTML"
                )
            except:
                pass
        
        return True
        
    except Exception as e:
        bot.send_message(chat_id, f"{PEM['no']} ERROR!\n\n{str(e)}")
        return False

def get_type_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    if type_status["ig_cookies"]:
        kb.add(types.InlineKeyboardButton(
            f"{get_type_icon('ig_cookies')} {get_type_display_name('ig_cookies')}", 
            callback_data="type_ig_cookies"
        ))
    else:
        kb.add(types.InlineKeyboardButton(
            f"{PEM['offline']} {get_type_display_name('ig_cookies')} (Closed)", 
            callback_data="type_disabled_ig_cookies"
        ))
    
    if type_status["ig_2fa"]:
        kb.add(types.InlineKeyboardButton(
            f"{get_type_icon('ig_2fa')} {get_type_display_name('ig_2fa')}", 
            callback_data="type_ig_2fa"
        ))
    else:
        kb.add(types.InlineKeyboardButton(
            f"{PEM['offline']} {get_type_display_name('ig_2fa')} (Closed)", 
            callback_data="type_disabled_ig_2fa"
        ))
    
    if type_status["fb_0fd_2fa"]:
        kb.add(types.InlineKeyboardButton(
            f"{get_type_icon('fb_0fd_2fa')} {get_type_display_name('fb_0fd_2fa')}", 
            callback_data="type_fb_0fd_2fa"
        ))
    else:
        kb.add(types.InlineKeyboardButton(
            f"{PEM['offline']} {get_type_display_name('fb_0fd_2fa')} (Closed)", 
            callback_data="type_disabled_fb_0fd_2fa"
        ))
    
    kb.add(types.InlineKeyboardButton(f"{PEM['no']} Cancel", callback_data="cancel_submit"))
    
    return kb

# ================= 🤖 [ USER BOT ] =================

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
            btn1 = types.InlineKeyboardButton(f"{PEM['file']} Submit File", callback_data="submit_file")
            btn2 = types.InlineKeyboardButton(f"{PEM['payment']} Change Payment", callback_data="change_payment")
            kb.add(btn1, btn2)
            
            db = load_db()
            user_payment = db["user_payment_settings"].get(str(m.chat.id), {})
            
            payment_info = ""
            if user_payment:
                payment_info = f"\n\n{PEM['payment']} Current Payment:\n{user_payment.get('payment_method', 'N/A')} - {user_payment.get('payment_number', 'N/A')}"
            
            bot.send_message(
                m.chat.id,
                f"""{PEM['star']} <b>ID RECEIVER BOT</b> {PEM['star']}

{PEM['hi']} <b>Hello</b> {m.from_user.first_name}!{payment_info}

{PEM['file']} <b>Supported:</b> Any file format
{PEM['info']} <b>Auto Detect:</b> Columns automatically
{PEM['payment']} <b>Payment:</b> bKash, Nagad, Rocket, Binance
{PEM['refresh']} <b>Duplicate:</b> Auto remove

━━━━━━━━━━━━━━━━━━━━
{PEM['pin']} <b>Click below to start</b>

{PEM['shield']} <b>Secure • Fast • Reliable</b>""",
                reply_markup=kb,
                parse_mode="HTML"
            )

        @bot.callback_query_handler(func=lambda c: True)
        def cb_handler(c):
            user_id = c.message.chat.id
            
            if c.data == "change_payment":
                try:
                    bot.delete_message(c.message.chat.id, c.message.message_id)
                except:
                    pass
                
                kb = types.InlineKeyboardMarkup(row_width=2)
                btn1 = types.InlineKeyboardButton(f"{PEM['bkash']} bKash", callback_data="change_pay_bkash")
                btn2 = types.InlineKeyboardButton(f"{PEM['nagad']} Nagad", callback_data="change_pay_nagad")
                btn3 = types.InlineKeyboardButton(f"{PEM['rocket']} Rocket", callback_data="change_pay_rocket")
                btn4 = types.InlineKeyboardButton(f"{PEM['binance']} Binance", callback_data="change_pay_binance")
                btn5 = types.InlineKeyboardButton(f"{PEM['no']} Cancel", callback_data="cancel_payment_change")
                kb.add(btn1, btn2, btn3, btn4, btn5)
                
                bot.send_message(
                    user_id,
                    f"{PEM['payment']} Change Payment Method\n\nSelect your new payment method:",
                    reply_markup=kb
                )
            
            elif c.data.startswith("change_pay_"):
                method = c.data.replace("change_pay_", "")
                method_name = method.capitalize()
                if method == "bkash":
                    method_name = "bKash"
                elif method == "binance":
                    method_name = "Binance"
                
                user_sessions[user_id] = {"changing_payment": True, "new_method": method_name}
                
                try:
                    bot.delete_message(c.message.chat.id, c.message.message_id)
                except:
                    pass
                
                bot.send_message(
                    user_id,
                    f"{PEM['ok']} {method_name} Selected\n\n{PEM['upload']} Send your new {method_name} number:"
                )
                bot.register_next_step_handler_by_chat_id(user_id, update_payment_number)
            
            elif c.data == "cancel_payment_change":
                try:
                    bot.delete_message(c.message.chat.id, c.message.message_id)
                except:
                    pass
                
                kb = types.InlineKeyboardMarkup(row_width=1)
                btn1 = types.InlineKeyboardButton(f"{PEM['file']} Submit File", callback_data="submit_file")
                btn2 = types.InlineKeyboardButton(f"{PEM['payment']} Change Payment", callback_data="change_payment")
                kb.add(btn1, btn2)
                
                bot.send_message(
                    user_id,
                    f"{PEM['no']} Payment change cancelled",
                    reply_markup=kb
                )
            
            elif c.data == "submit_file":
                try:
                    bot.delete_message(c.message.chat.id, c.message.message_id)
                except:
                    pass
                
                bot.send_message(
                    c.message.chat.id,
                    f"{PEM['file']} Select File Type:",
                    reply_markup=get_type_keyboard()
                )
            
            elif c.data.startswith("type_disabled_"):
                bot.answer_callback_query(c.id, f"{PEM['no']} This type is currently closed!", show_alert=True)
            
            elif c.data.startswith("type_"):
                file_type = c.data.replace("type_", "")
                
                if not type_status.get(file_type, False):
                    bot.answer_callback_query(c.id, f"{PEM['no']} This type is currently closed!", show_alert=True)
                    return
                
                db = load_db()
                user_payment = db["user_payment_settings"].get(str(user_id), {})
                
                if user_payment and user_payment.get("payment_method") and user_payment.get("payment_number"):
                    user_sessions[user_id] = {
                        "file_type": file_type,
                        "payment_method": user_payment["payment_method"],
                        "payment_number": user_payment["payment_number"]
                    }
                    
                    try:
                        bot.delete_message(c.message.chat.id, c.message.message_id)
                    except:
                        pass
                    
                    bot.send_message(
                        user_id,
                        f"{PEM['ok']} Auto Payment Selected\n\n"
                        f"{PEM['payment']} {user_payment['payment_method']} - {user_payment['payment_number']}\n\n"
                        f"{PEM['file']} Send your file now"
                    )
                    bot.register_next_step_handler_by_chat_id(user_id, receive_file)
                else:
                    user_sessions[user_id] = {"file_type": file_type}
                    
                    kb = types.InlineKeyboardMarkup(row_width=2)
                    btn1 = types.InlineKeyboardButton(f"{PEM['bkash']} bKash", callback_data="pay_bkash")
                    btn2 = types.InlineKeyboardButton(f"{PEM['nagad']} Nagad", callback_data="pay_nagad")
                    btn3 = types.InlineKeyboardButton(f"{PEM['rocket']} Rocket", callback_data="pay_rocket")
                    btn4 = types.InlineKeyboardButton(f"{PEM['binance']} Binance", callback_data="pay_binance")
                    btn5 = types.InlineKeyboardButton(f"{PEM['no']} Cancel", callback_data="cancel_submit")
                    kb.add(btn1, btn2, btn3, btn4, btn5)
                    
                    try:
                        bot.delete_message(c.message.chat.id, c.message.message_id)
                    except:
                        pass
                    
                    bot.send_message(
                        c.message.chat.id,
                        f"{PEM['payment']} Select Payment Method:",
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
                    f"{PEM['ok']} {method_name} Selected\n\n{PEM['upload']} Send your {method_name} number (you won't need to enter this again):"
                )
                bot.register_next_step_handler_by_chat_id(user_id, save_payment_and_continue)
            
            elif c.data == "cancel_submit":
                user_sessions.pop(user_id, None)
                
                kb = types.InlineKeyboardMarkup(row_width=1)
                btn1 = types.InlineKeyboardButton(f"{PEM['file']} Submit File", callback_data="submit_file")
                btn2 = types.InlineKeyboardButton(f"{PEM['payment']} Change Payment", callback_data="change_payment")
                kb.add(btn1, btn2)
                
                try:
                    bot.delete_message(c.message.chat.id, c.message.message_id)
                except:
                    pass
                
                bot.send_message(
                    c.message.chat.id,
                    f"{PEM['no']} Cancelled\n\nClick below to start over:",
                    reply_markup=kb
                )

        def update_payment_number(m):
            user_id = m.chat.id
            
            if user_id not in user_sessions or not user_sessions[user_id].get("changing_payment"):
                bot.send_message(user_id, f"{PEM['no']} Session expired. Use /start")
                return
            
            new_number = m.text.strip()
            new_method = user_sessions[user_id]["new_method"]
            
            db = load_db()
            db["user_payment_settings"][str(user_id)] = {
                "payment_method": new_method,
                "payment_number": new_number
            }
            save_db(db)
            
            user_sessions.pop(user_id, None)
            
            kb = types.InlineKeyboardMarkup(row_width=1)
            btn1 = types.InlineKeyboardButton(f"{PEM['file']} Submit File", callback_data="submit_file")
            btn2 = types.InlineKeyboardButton(f"{PEM['payment']} Change Payment", callback_data="change_payment")
            kb.add(btn1, btn2)
            
            bot.send_message(
                user_id,
                f"{PEM['ok']} Payment Updated!\n\n"
                f"{PEM['payment']} {new_method} - {new_number}\n\n"
                f"Your payment method has been saved.",
                reply_markup=kb
            )

        def save_payment_and_continue(m):
            user_id = m.chat.id
            
            if user_id not in user_sessions:
                bot.send_message(user_id, f"{PEM['no']} Session expired. Use /start")
                return
            
            payment_number = m.text.strip()
            user_sessions[user_id]["payment_number"] = payment_number
            
            db = load_db()
            db["user_payment_settings"][str(user_id)] = {
                "payment_method": user_sessions[user_id]["payment_method"],
                "payment_number": payment_number
            }
            save_db(db)
            
            bot.send_message(
                user_id,
                f"{PEM['ok']} Payment saved!\n\n"
                f"{PEM['payment']} {user_sessions[user_id]['payment_method']} - {payment_number}\n"
                f"{PEM['refresh']} You won't need to enter this again.\n\n"
                f"{PEM['file']} Send your file now"
            )
            bot.register_next_step_handler_by_chat_id(user_id, receive_file)

        def receive_file(m):
            user_id = m.chat.id
            
            if user_id not in user_sessions:
                bot.send_message(user_id, f"{PEM['no']} Session expired. Use /start")
                return
            
            if not m.document:
                bot.send_message(user_id, f"{PEM['no']} Send a valid file!")
                return
            
            file_type = user_sessions[user_id]["file_type"]
            current_date = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            file_info = bot.get_file(m.document.file_id)
            save_name = f"{user_id}_{current_date}_{m.document.file_name}"
            save_path = os.path.join("uploads", file_type, save_name)
            
            downloaded_file = bot.download_file(file_info.file_path)
            with open(save_path, "wb") as f:
                f.write(downloaded_file)
            
            bot.send_message(user_id, f"{PEM['processing']} Processing...")
            
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

# ================= 👑 [ MASTER PANEL ] =================

# Store only bot reply message IDs to delete (excluding main menu)
bot_reply_messages = {}
main_menu_id = {}

def delete_previous_bot_replies(chat_id):
    if chat_id in bot_reply_messages:
        for msg_id in bot_reply_messages[chat_id]:
            if chat_id in main_menu_id and msg_id == main_menu_id[chat_id]:
                continue
            try:
                master_bot.delete_message(chat_id, msg_id)
            except:
                pass
        bot_reply_messages[chat_id] = []

@master_bot.message_handler(commands=['start'])
def m_start(m):
    if m.from_user.id not in ADMIN_IDS:
        master_bot.send_message(m.chat.id, f"{PEM['no']} Unauthorized!")
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row(f"{PEM['stats']} Total Stats", f"{PEM['payment']} Payment List")
    kb.row(f"{PEM['file']} Download by Type", f"{PEM['settings']} Type Control")
    kb.row(f"{PEM['search']} Report Check", f"{PEM['broadcast']} Broadcast")
    kb.row(f"{PEM['gear']} More Options")
    
    msg = master_bot.send_message(
        m.chat.id,
        f"""{PEM['master']} <b>MASTER ADMIN PANEL</b> {PEM['master']}

{PEM['settings']} <b>Current Status:</b>
{PEM['online']} {get_type_display_name('ig_cookies')}: {'ON' if type_status['ig_cookies'] else 'OFF'}
{PEM['online']} {get_type_display_name('ig_2fa')}: {'ON' if type_status['ig_2fa'] else 'OFF'}
{PEM['online']} {get_type_display_name('fb_0fd_2fa')}: {'ON' if type_status['fb_0fd_2fa'] else 'OFF'}

━━━━━━━━━━━━━━━━━━━━
{PEM['pin']} <b>Select an option below</b>

{PEM['shield']} <b>Secure • Fast • Reliable</b>""",
        reply_markup=kb,
        parse_mode="HTML"
    )
    
    main_menu_id[m.chat.id] = msg.message_id
    
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

@master_bot.message_handler(func=lambda m: m.text == f"{PEM['gear']} More Options")
def m_more_options(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row(f"{PEM['add']} Add Bot", f"{PEM['remove']} Remove Bot")
    kb.row(f"{PEM['refresh']} Reset All Types", f"{PEM['trash']} Clear Data")
    kb.row(f"{PEM['payment']} User Payments", f"{PEM['search']} Search User")
    kb.row(f"{PEM['back']} Back to Main Menu")
    
    msg = master_bot.send_message(
        m.chat.id,
        f"{PEM['gear']} MORE OPTIONS\n\nSelect an option below:",
        reply_markup=kb
    )
    
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

@master_bot.message_handler(func=lambda m: m.text == f"{PEM['back']} Back to Main Menu")
def back_to_main_menu(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row(f"{PEM['stats']} Total Stats", f"{PEM['payment']} Payment List")
    kb.row(f"{PEM['file']} Download by Type", f"{PEM['settings']} Type Control")
    kb.row(f"{PEM['search']} Report Check", f"{PEM['broadcast']} Broadcast")
    kb.row(f"{PEM['gear']} More Options")
    
    msg = master_bot.send_message(
        m.chat.id,
        f"""{PEM['master']} <b>MASTER ADMIN PANEL</b> {PEM['master']}

{PEM['settings']} <b>Current Status:</b>
{PEM['online']} {get_type_display_name('ig_cookies')}: {'ON' if type_status['ig_cookies'] else 'OFF'}
{PEM['online']} {get_type_display_name('ig_2fa')}: {'ON' if type_status['ig_2fa'] else 'OFF'}
{PEM['online']} {get_type_display_name('fb_0fd_2fa')}: {'ON' if type_status['fb_0fd_2fa'] else 'OFF'}

━━━━━━━━━━━━━━━━━━━━
{PEM['pin']} <b>Select an option below</b>

{PEM['shield']} <b>Secure • Fast • Reliable</b>""",
        reply_markup=kb,
        parse_mode="HTML"
    )
    
    main_menu_id[m.chat.id] = msg.message_id
    
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

@master_bot.callback_query_handler(func=lambda c: c.data == "back_to_menu")
def m_back_to_menu_callback(c):
    if c.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(c.message.chat.id)
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row(f"{PEM['stats']} Total Stats", f"{PEM['payment']} Payment List")
    kb.row(f"{PEM['file']} Download by Type", f"{PEM['settings']} Type Control")
    kb.row(f"{PEM['search']} Report Check", f"{PEM['broadcast']} Broadcast")
    kb.row(f"{PEM['gear']} More Options")
    
    msg = master_bot.send_message(
        c.message.chat.id,
        f"""{PEM['master']} <b>MASTER ADMIN PANEL</b> {PEM['master']}

{PEM['settings']} <b>Current Status:</b>
{PEM['online']} {get_type_display_name('ig_cookies')}: {'ON' if type_status['ig_cookies'] else 'OFF'}
{PEM['online']} {get_type_display_name('ig_2fa')}: {'ON' if type_status['ig_2fa'] else 'OFF'}
{PEM['online']} {get_type_display_name('fb_0fd_2fa')}: {'ON' if type_status['fb_0fd_2fa'] else 'OFF'}

━━━━━━━━━━━━━━━━━━━━
{PEM['pin']} <b>Select an option below</b>

{PEM['shield']} <b>Secure • Fast • Reliable</b>""",
        reply_markup=kb,
        parse_mode="HTML"
    )
    
    main_menu_id[c.message.chat.id] = msg.message_id
    
    if c.message.chat.id not in bot_reply_messages:
        bot_reply_messages[c.message.chat.id] = []
    bot_reply_messages[c.message.chat.id].append(msg.message_id)

# ================= 📢 [ BROADCAST ] =================

@master_bot.message_handler(func=lambda m: m.text == f"{PEM['broadcast']} Broadcast")
def m_broadcast(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    user_ids = load_user_ids()
    if not user_ids:
        msg = master_bot.send_message(m.chat.id, f"{PEM['no']} No users found!")
        if m.chat.id not in bot_reply_messages:
            bot_reply_messages[m.chat.id] = []
        bot_reply_messages[m.chat.id].append(msg.message_id)
        return
    
    if not active_bots:
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton(f"{PEM['add']} Add Bot", callback_data="goto_add_bot_from_broadcast"))
        msg = master_bot.send_message(
            m.chat.id,
            f"{PEM['no']} NO ACTIVE USER BOTS!\n\nPlease add a bot first:",
            reply_markup=kb
        )
        if m.chat.id not in bot_reply_messages:
            bot_reply_messages[m.chat.id] = []
        bot_reply_messages[m.chat.id].append(msg.message_id)
        return
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(f"{PEM['message']} Send Message", callback_data="broadcast_text"),
        types.InlineKeyboardButton(f"{PEM['back']} Back", callback_data="broadcast_back")
    )
    
    msg = master_bot.send_message(
        m.chat.id,
        f"""{PEM['broadcast']} <b>BROADCAST</b>

{PEM['bot']} <b>Active Bots:</b> {len(active_bots)}
{PEM['user']} <b>Total Users:</b> {len(user_ids)}

━━━━━━━━━━━━━━━━━━━━
{PEM['pin']} <b>Click below to start</b>""",
        reply_markup=kb,
        parse_mode="HTML"
    )
    
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

@master_bot.callback_query_handler(func=lambda c: c.data == "goto_add_bot_from_broadcast")
def goto_add_bot_from_broadcast(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, f"{PEM['no']} Unauthorized!")
        return
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    msg = master_bot.send_message(
        c.message.chat.id,
        f"{PEM['bot']} Send Bot Token:\n\nGet token from @BotFather\nSend /cancel to cancel:"
    )
    master_bot.register_next_step_handler(msg, save_bot_token)

@master_bot.callback_query_handler(func=lambda c: c.data.startswith("broadcast_"))
def broadcast_callback(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, f"{PEM['no']} Unauthorized!")
        return
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    if c.data == "broadcast_back":
        back_to_main_menu(c)
        return
    
    if c.data == "broadcast_text":
        kb = types.InlineKeyboardMarkup(row_width=4)
        
        social_emojis = [
            ("📸", "📸"), ("📘", "📘"), ("💬", "💬"), ("✈️", "✈️"),
            ("💼", "💼"), ("💭", "💭"), ("🍎", "🍎"), ("🔍", "🔍"),
            ("🪟", "🪟"), ("🧑‍🤝‍🧑", "🧑‍🤝‍🧑"), ("🎵", "🎵"),
        ]
        
        status_emojis = [
            ("✅", "✅"), ("❌", "❌"), ("⚠️", "⚠️"), ("⭐", "⭐"),
            ("🔥", "🔥"), ("🚀", "🚀"), ("🎁", "🎁"), ("👑", "👑"),
            ("📢", "📢"), ("💬", "💬"), ("‼️", "‼️"), ("🛡️", "🛡️"),
        ]
        
        payment_emojis = [
            ("🏦", "🏦"), ("🏧", "🏧"), ("🚀", "🚀"), ("💱", "💱"),
            ("📈", "📈"), ("💰", "💰"), ("📱", "📱"), ("🛒", "🛒"),
        ]
        
        all_emojis = social_emojis + status_emojis + payment_emojis
        
        for emoji_char, emoji_name in all_emojis:
            kb.add(types.InlineKeyboardButton(
                emoji_char, 
                callback_data=f"broadcast_emoji_{emoji_char}"
            ))
        
        kb.add(types.InlineKeyboardButton(f"{PEM['ok']} Send", callback_data="broadcast_send"))
        kb.add(types.InlineKeyboardButton(f"{PEM['trash']} Clear", callback_data="broadcast_clear"))
        kb.add(types.InlineKeyboardButton(f"{PEM['no']} Cancel", callback_data="broadcast_cancel"))
        
        msg = master_bot.send_message(
            c.message.chat.id,
            f"""{PEM['message']} <b>BROADCAST MESSAGE</b>

📸 Instagram | 📘 Facebook | 💬 WhatsApp | ✈️ Telegram
Select emojis or type your message:
Click emojis to add them to your message.
Click 'Send' when ready.

━━━━━━━━━━━━━━━━━━━━
<b>Current Message:</b>
_(Empty)_""",
            reply_markup=kb,
            parse_mode="HTML"
        )
        
        user_sessions[c.message.chat.id] = {
            "broadcast_mode": True,
            "broadcast_message": "",
            "broadcast_msg_id": msg.message_id
        }

@master_bot.callback_query_handler(func=lambda c: c.data.startswith("broadcast_emoji_"))
def broadcast_emoji_handler(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, f"{PEM['no']} Unauthorized!")
        return
    
    emoji = c.data.replace("broadcast_emoji_", "")
    
    if c.message.chat.id not in user_sessions:
        return
    
    session = user_sessions[c.message.chat.id]
    if not session.get("broadcast_mode"):
        return
    
    session["broadcast_message"] += emoji
    
    current_msg = session["broadcast_message"]
    if not current_msg:
        current_msg = "_(Empty)_"
    
    kb = types.InlineKeyboardMarkup(row_width=4)
    social_emojis = [
        ("📸", "📸"), ("📘", "📘"), ("💬", "💬"), ("✈️", "✈️"),
        ("💼", "💼"), ("💭", "💭"), ("🍎", "🍎"), ("🔍", "🔍"),
        ("🪟", "🪟"), ("🧑‍🤝‍🧑", "🧑‍🤝‍🧑"), ("🎵", "🎵"),
    ]
    status_emojis = [
        ("✅", "✅"), ("❌", "❌"), ("⚠️", "⚠️"), ("⭐", "⭐"),
        ("🔥", "🔥"), ("🚀", "🚀"), ("🎁", "🎁"), ("👑", "👑"),
        ("📢", "📢"), ("💬", "💬"), ("‼️", "‼️"), ("🛡️", "🛡️"),
    ]
    payment_emojis = [
        ("🏦", "🏦"), ("🏧", "🏧"), ("🚀", "🚀"), ("💱", "💱"),
        ("📈", "📈"), ("💰", "💰"), ("📱", "📱"), ("🛒", "🛒"),
    ]
    all_emojis = social_emojis + status_emojis + payment_emojis
    
    for emoji_char, emoji_name in all_emojis:
        kb.add(types.InlineKeyboardButton(
            emoji_char, 
            callback_data=f"broadcast_emoji_{emoji_char}"
        ))
    
    kb.add(types.InlineKeyboardButton(f"{PEM['ok']} Send", callback_data="broadcast_send"))
    kb.add(types.InlineKeyboardButton(f"{PEM['trash']} Clear", callback_data="broadcast_clear"))
    kb.add(types.InlineKeyboardButton(f"{PEM['no']} Cancel", callback_data="broadcast_cancel"))
    
    try:
        master_bot.edit_message_text(
            f"""{PEM['message']} <b>BROADCAST MESSAGE</b>

📸 Instagram | 📘 Facebook | 💬 WhatsApp | ✈️ Telegram
Select emojis or type your message:
Click emojis to add them to your message.
Click 'Send' when ready.

━━━━━━━━━━━━━━━━━━━━
<b>Current Message:</b>
{current_msg}""",
            chat_id=c.message.chat.id,
            message_id=session["broadcast_msg_id"],
            reply_markup=kb,
            parse_mode="HTML"
        )
    except:
        pass
    
    master_bot.answer_callback_query(c.id, f"Added {emoji}")

@master_bot.callback_query_handler(func=lambda c: c.data == "broadcast_clear")
def broadcast_clear_handler(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, f"{PEM['no']} Unauthorized!")
        return
    
    if c.message.chat.id not in user_sessions:
        return
    
    session = user_sessions[c.message.chat.id]
    if not session.get("broadcast_mode"):
        return
    
    session["broadcast_message"] = ""
    
    kb = types.InlineKeyboardMarkup(row_width=4)
    social_emojis = [
        ("📸", "📸"), ("📘", "📘"), ("💬", "💬"), ("✈️", "✈️"),
        ("💼", "💼"), ("💭", "💭"), ("🍎", "🍎"), ("🔍", "🔍"),
        ("🪟", "🪟"), ("🧑‍🤝‍🧑", "🧑‍🤝‍🧑"), ("🎵", "🎵"),
    ]
    status_emojis = [
        ("✅", "✅"), ("❌", "❌"), ("⚠️", "⚠️"), ("⭐", "⭐"),
        ("🔥", "🔥"), ("🚀", "🚀"), ("🎁", "🎁"), ("👑", "👑"),
        ("📢", "📢"), ("💬", "💬"), ("‼️", "‼️"), ("🛡️", "🛡️"),
    ]
    payment_emojis = [
        ("🏦", "🏦"), ("🏧", "🏧"), ("🚀", "🚀"), ("💱", "💱"),
        ("📈", "📈"), ("💰", "💰"), ("📱", "📱"), ("🛒", "🛒"),
    ]
    all_emojis = social_emojis + status_emojis + payment_emojis
    
    for emoji_char, emoji_name in all_emojis:
        kb.add(types.InlineKeyboardButton(
            emoji_char, 
            callback_data=f"broadcast_emoji_{emoji_char}"
        ))
    
    kb.add(types.InlineKeyboardButton(f"{PEM['ok']} Send", callback_data="broadcast_send"))
    kb.add(types.InlineKeyboardButton(f"{PEM['no']} Cancel", callback_data="broadcast_cancel"))
    
    try:
        master_bot.edit_message_text(
            f"""{PEM['message']} <b>BROADCAST MESSAGE</b>

📸 Instagram | 📘 Facebook | 💬 WhatsApp | ✈️ Telegram
Select emojis or type your message:
Click emojis to add them to your message.
Click 'Send' when ready.

━━━━━━━━━━━━━━━━━━━━
<b>Current Message:</b>
_(Empty)_""",
            chat_id=c.message.chat.id,
            message_id=session["broadcast_msg_id"],
            reply_markup=kb,
            parse_mode="HTML"
        )
    except:
        pass
    
    master_bot.answer_callback_query(c.id, f"{PEM['ok']} Cleared!")

@master_bot.callback_query_handler(func=lambda c: c.data == "broadcast_send")
def broadcast_send_handler(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, f"{PEM['no']} Unauthorized!")
        return
    
    if c.message.chat.id not in user_sessions:
        return
    
    session = user_sessions[c.message.chat.id]
    if not session.get("broadcast_mode"):
        return
    
    broadcast_message = session.get("broadcast_message", "")
    
    if not broadcast_message:
        master_bot.answer_callback_query(c.id, f"{PEM['no']} Message is empty!", show_alert=True)
        return
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    user_sessions.pop(c.message.chat.id, None)
    
    user_ids = load_user_ids()
    
    if not user_ids:
        master_bot.send_message(c.message.chat.id, f"{PEM['no']} No users found!")
        return
    
    if not active_bots:
        master_bot.send_message(c.message.chat.id, f"{PEM['no']} No active user bots!")
        return
    
    final_message = f"""{PEM['attention']} ATTENTION {PEM['attention']}

{broadcast_message}

{PEM['crown']} Thanks by MAX FUTURE {PEM['ok']}"""
    
    total_users = len(user_ids)
    status_msg = master_bot.send_message(c.message.chat.id, f"{PEM['processing']} Sending to {total_users} users...")
    
    success = 0
    fail = 0
    bot_tokens = list(active_bots)
    
    for idx, user_id in enumerate(user_ids):
        sent = False
        for bot_token in bot_tokens:
            try:
                bot = telebot.TeleBot(bot_token)
                bot.send_message(user_id, final_message, parse_mode="HTML")
                success += 1
                sent = True
                break
            except:
                continue
        
        if not sent:
            fail += 1
        
        if (idx + 1) % 50 == 0 or (idx + 1) == total_users:
            try:
                master_bot.edit_message_text(
                    f"{PEM['processing']} Sending...\n\n{PEM['ok']} Sent: {success}\n{PEM['no']} Failed: {fail}\n{PEM['stats']} Progress: {idx + 1}/{total_users}",
                    chat_id=status_msg.chat.id,
                    message_id=status_msg.message_id
                )
            except:
                pass
        
        time.sleep(0.03)
    
    try:
        master_bot.delete_message(c.message.chat.id, status_msg.message_id)
    except:
        pass
    
    result_msg = f"""{PEM['ok']} Broadcast Complete!

{PEM['ok']} Success: {success}
{PEM['no']} Failed: {fail}
{PEM['user']} Total users: {total_users}"""
    
    if fail > 0:
        result_msg += f"\n\n{PEM['warn']} {fail} users didn't receive the message."
    
    master_bot.send_message(c.message.chat.id, result_msg)

@master_bot.callback_query_handler(func=lambda c: c.data == "broadcast_cancel")
def broadcast_cancel_handler(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, f"{PEM['no']} Unauthorized!")
        return
    
    user_sessions.pop(c.message.chat.id, None)
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    master_bot.send_message(c.message.chat.id, f"{PEM['no']} Broadcast cancelled.")

# ================= 📋 [ REPORT CHECK - UNIQUE OK ] =================

@master_bot.message_handler(func=lambda m: m.text == f"{PEM['search']} Report Check")
def m_report_check(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"{get_type_icon('ig_cookies')} {get_type_display_name('ig_cookies')}", callback_data="report_select_ig_cookies"),
        types.InlineKeyboardButton(f"{get_type_icon('ig_2fa')} {get_type_display_name('ig_2fa')}", callback_data="report_select_ig_2fa"),
        types.InlineKeyboardButton(f"{get_type_icon('fb_0fd_2fa')} {get_type_display_name('fb_0fd_2fa')}", callback_data="report_select_fb_0fd_2fa"),
        types.InlineKeyboardButton(f"{PEM['stats']} All Types", callback_data="report_select_all"),
        types.InlineKeyboardButton(f"{PEM['no']} Cancel", callback_data="report_cancel")
    )
    
    msg = master_bot.send_message(
        m.chat.id,
        f"""{PEM['search']} REPORT CHECK

Select which type to check with OK list:

{PEM['info']} You will need to upload a TXT file containing usernames/emails.

━━━━━━━━━━━━━━━━━━━━
{PEM['pin']} <b>Select an option below</b>""",
        reply_markup=kb,
        parse_mode="HTML"
    )
    
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

@master_bot.callback_query_handler(func=lambda c: c.data.startswith("report_select_"))
def m_report_select_callback(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, f"{PEM['no']} Unauthorized!")
        return
    
    if c.data == "report_cancel":
        try:
            master_bot.delete_message(c.message.chat.id, c.message.message_id)
        except:
            pass
        msg = master_bot.send_message(c.message.chat.id, f"{PEM['no']} Report check cancelled.")
        if c.message.chat.id not in bot_reply_messages:
            bot_reply_messages[c.message.chat.id] = []
        bot_reply_messages[c.message.chat.id].append(msg.message_id)
        return
    
    scan_type = c.data.replace("report_select_", "")
    
    if scan_type == "all":
        display_type = "ALL TYPES"
    else:
        display_type = get_type_display_name(scan_type)
    
    user_sessions[c.message.chat.id] = {"scan_type": scan_type}
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    msg = master_bot.send_message(
        c.message.chat.id,
        f"""{PEM['ok']} {display_type} Selected

{PEM['file']} Now send your OK TXT file:

{PEM['info']} Each line should contain one username/email
📌 Example:
   • john_doe
   • jane@email.com

Send /cancel to cancel:"""
    )
    
    if c.message.chat.id not in bot_reply_messages:
        bot_reply_messages[c.message.chat.id] = []
    bot_reply_messages[c.message.chat.id].append(msg.message_id)
    
    master_bot.register_next_step_handler(c.message, scan_ok_list_clean)

def scan_ok_list_clean(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    session = user_sessions.get(m.chat.id, {})
    scan_type = session.get("scan_type", "all")
    user_sessions.pop(m.chat.id, None)
    
    if not m.document:
        msg = master_bot.send_message(m.chat.id, f"{PEM['no']} Please send a TXT file!")
        if m.chat.id not in bot_reply_messages:
            bot_reply_messages[m.chat.id] = []
        bot_reply_messages[m.chat.id].append(msg.message_id)
        return
    
    if not m.document.file_name.endswith('.txt'):
        msg = master_bot.send_message(m.chat.id, f"{PEM['no']} Only TXT files are supported!")
        if m.chat.id not in bot_reply_messages:
            bot_reply_messages[m.chat.id] = []
        bot_reply_messages[m.chat.id].append(msg.message_id)
        return
    
    try:
        master_bot.delete_message(m.chat.id, m.message_id)
    except:
        pass
    
    status_msg = master_bot.send_message(
        m.chat.id,
        f"{PEM['processing']} Reading OK list file..."
    )
    
    try:
        file_info = master_bot.get_file(m.document.file_id)
        downloaded_file = master_bot.download_file(file_info.file_path)
        content = downloaded_file.decode('utf-8')
        
        ok_list_raw = [line.strip() for line in content.split('\n') if line.strip()]
        
        ok_list = []
        seen = set()
        for item in ok_list_raw:
            item_lower = item.lower()
            if item_lower not in seen and item_lower:
                seen.add(item_lower)
                ok_list.append(item_lower)
        
    except Exception as e:
        master_bot.send_message(
            m.chat.id, 
            f"{PEM['no']} Failed to read file!\n\nError: {str(e)}"
        )
        return
    
    if not ok_list:
        master_bot.send_message(m.chat.id, f"{PEM['no']} No valid data found in TXT file!")
        return
    
    try:
        master_bot.edit_message_text(
            f"{PEM['processing']} Scanning {len(ok_list)} unique users...\n\n{PEM['file']} Type: {get_type_display_name(scan_type) if scan_type != 'all' else 'ALL TYPES'}\n{PEM['search']} Searching database...",
            chat_id=status_msg.chat.id,
            message_id=status_msg.message_id
        )
    except:
        pass
    
    db = load_db()
    
    if scan_type == "all":
        types_to_scan = ["ig_cookies", "ig_2fa", "fb_0fd_2fa"]
    else:
        types_to_scan = [scan_type]
    
    results = {}
    total_files_scanned = 0
    total_data_scanned = 0
    
    found_ok_usernames = set()
    submitter_data = {}
    
    for file_type in types_to_scan:
        files_data = db["files"].get(file_type, {})
        total_files_scanned += len(files_data)
        
        for file_hash, file_info in files_data.items():
            original_data = file_info.get("original_data", [])
            submitted_by = file_info.get("submitted_by", "Unknown")
            payment_method = file_info.get("payment_method", "Unknown")
            payment_number = file_info.get("payment_number", "Unknown")
            
            if submitted_by not in submitter_data:
                submitter_data[submitted_by] = {
                    "submitted_by": submitted_by,
                    "payment_method": payment_method,
                    "payment_number": payment_number,
                    "file_type": file_type,
                    "found_ok": set(),
                    "matches": []
                }
            
            for row in original_data:
                total_data_scanned += 1
                
                user_field = str(row.get("user", "")).strip().lower()
                pass_field = str(row.get("pass", "")).strip()
                cookies_field = str(row.get("cookies", "")).strip()
                
                if not user_field:
                    continue
                
                for ok_username in ok_list:
                    if ok_username and ok_username == user_field:
                        if ok_username not in submitter_data[submitted_by]["found_ok"]:
                            submitter_data[submitted_by]["found_ok"].add(ok_username)
                            submitter_data[submitted_by]["matches"].append({
                                "user": user_field,
                                "pass": pass_field,
                                "cookies": cookies_field,
                                "ok_username": ok_username
                            })
                            found_ok_usernames.add(ok_username)
    
    for submitted_by, data in submitter_data.items():
        if data["found_ok"]:
            results[submitted_by] = {
                "total_ok": len(data["found_ok"]),
                "submitted_by": data["submitted_by"],
                "payment_method": data["payment_method"],
                "payment_number": data["payment_number"],
                "file_type": data["file_type"],
                "matches": data["matches"]
            }
    
    global current_ok_data
    current_ok_data = {
        "total_ok": len(found_ok_usernames),
        "total_users": len(results),
        "last_scan_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "results": results,
        "scan_type": scan_type,
        "ok_list_count": len(ok_list),
        "total_files_scanned": total_files_scanned,
        "total_data_scanned": total_data_scanned
    }
    
    try:
        master_bot.delete_message(m.chat.id, status_msg.message_id)
    except:
        pass
    
    if not results:
        msg = master_bot.send_message(
            m.chat.id,
            f"""{PEM['no']} NO MATCHES FOUND!

{PEM['stats']} OK List: {len(ok_list)} users
{PEM['file']} Files Scanned: {total_files_scanned}
{PEM['stats']} Data Scanned: {total_data_scanned}
{PEM['ok']} Matches Found: 0"""
        )
        if m.chat.id not in bot_reply_messages:
            bot_reply_messages[m.chat.id] = []
        bot_reply_messages[m.chat.id].append(msg.message_id)
        return
    
    display_type = get_type_display_name(scan_type) if scan_type != 'all' else "ALL TYPES"
    
    bkash_count = 0
    nagad_count = 0
    rocket_count = 0
    binance_count = 0
    
    for submitted_by, data in results.items():
        payment_method = data["payment_method"]
        if payment_method == "bKash":
            bkash_count += 1
        elif payment_method == "Nagad":
            nagad_count += 1
        elif payment_method == "Rocket":
            rocket_count += 1
        elif payment_method == "Binance":
            binance_count += 1
    
    report = f"""{PEM['ok']} REPORT CHECK COMPLETE!

{PEM['file']} Type: {display_type}
{PEM['stats']} OK List: {len(ok_list)} users
{PEM['file']} Files Scanned: {total_files_scanned}
{PEM['stats']} Data Scanned: {total_data_scanned}
━━━━━━━━━━━━━━━━━━━━
{PEM['ok']} Matched Submitters: {len(results)}
{PEM['stats']} Total OK Found: {len(found_ok_usernames)}
{PEM['time']} Scan Time: {current_ok_data['last_scan_time']}
━━━━━━━━━━━━━━━━━━━━

{PEM['payment']} Payment Breakdown:
{PEM['bkash']} bKash: {bkash_count} submitters
{PEM['nagad']} Nagad: {nagad_count} submitters
{PEM['rocket']} Rocket: {rocket_count} submitters
{PEM['binance']} Binance: {binance_count} submitters"""
    
    msg = master_bot.send_message(m.chat.id, report)
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

# ================= 📥 [ PAYMENT LIST ] =================

@master_bot.message_handler(func=lambda m: m.text == f"{PEM['payment']} Payment List")
def m_payment_list(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"{get_type_icon('ig_cookies')} {get_type_display_name('ig_cookies')}", callback_data="paylist_select_ig_cookies"),
        types.InlineKeyboardButton(f"{get_type_icon('ig_2fa')} {get_type_display_name('ig_2fa')}", callback_data="paylist_select_ig_2fa"),
        types.InlineKeyboardButton(f"{get_type_icon('fb_0fd_2fa')} {get_type_display_name('fb_0fd_2fa')}", callback_data="paylist_select_fb_0fd_2fa"),
        types.InlineKeyboardButton(f"{PEM['stats']} All Types", callback_data="paylist_select_all"),
        types.InlineKeyboardButton(f"{PEM['no']} Cancel", callback_data="paylist_cancel")
    )
    
    msg = master_bot.send_message(
        m.chat.id,
        f"""{PEM['payment']} PAYMENT LIST

Select which type you want to see:

━━━━━━━━━━━━━━━━━━━━
{PEM['pin']} <b>Select an option below</b>""",
        reply_markup=kb,
        parse_mode="HTML"
    )
    
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

@master_bot.callback_query_handler(func=lambda c: c.data.startswith("paylist_select_"))
def m_paylist_select_callback(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, f"{PEM['no']} Unauthorized!")
        return
    
    if c.data == "paylist_cancel":
        try:
            master_bot.delete_message(c.message.chat.id, c.message.message_id)
        except:
            pass
        msg = master_bot.send_message(c.message.chat.id, f"{PEM['no']} Cancelled.")
        if c.message.chat.id not in bot_reply_messages:
            bot_reply_messages[c.message.chat.id] = []
        bot_reply_messages[c.message.chat.id].append(msg.message_id)
        return
    
    selected_type = c.data.replace("paylist_select_", "")
    
    if selected_type == "all":
        file_types = ["ig_cookies", "ig_2fa", "fb_0fd_2fa"]
        type_label = "ALL TYPES"
    else:
        file_types = [selected_type]
        type_label = get_type_display_name(selected_type).upper()
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    generate_payment_list_file(c.message.chat.id, file_types, type_label)

def generate_payment_list_file(chat_id, file_types, type_label):
    db = load_db()
    
    submitter_data = []
    
    for file_type in file_types:
        files_data = db["files"].get(file_type, {})
        
        for file_hash, file_info in files_data.items():
            submitted_by = file_info.get("submitted_by", "Unknown")
            payment_method = file_info.get("payment_method", "Unknown")
            payment_number = file_info.get("payment_number", "Unknown")
            total_rows = file_info.get("total_rows_in_file", 0)
            original_name = file_info.get("original_name", "Unknown")
            received_date = file_info.get("received_date", "Unknown")
            
            try:
                if received_date and received_date != "Unknown":
                    date_part = received_date.split('_')[0]
                    year = date_part[:4]
                    month = date_part[4:6]
                    day = date_part[6:8]
                    formatted_date = f"{day}-{month}-{year}"
                else:
                    formatted_date = "Unknown"
            except:
                formatted_date = received_date
            
            ok_count = 0
            if current_ok_data.get("results"):
                if submitted_by in current_ok_data["results"]:
                    ok_count = current_ok_data["results"][submitted_by].get("total_ok", 0)
            
            submitter_data.append({
                "submitted_by": submitted_by,
                "payment_method": payment_method,
                "payment_number": payment_number,
                "total_rows": total_rows,
                "ok_count": ok_count,
                "file_name": original_name,
                "received_date": formatted_date,
                "file_hash": file_hash[:8]
            })
    
    if not submitter_data:
        master_bot.send_message(
            chat_id, 
            f"{PEM['no']} NO DATA FOUND!\n\nType: {type_label}"
        )
        return
    
    status_msg = master_bot.send_message(
        chat_id, 
        f"{PEM['processing']} Generating {type_label} Payment List..."
    )
    
    payment_order = {"bKash": 1, "Nagad": 2, "Rocket": 3, "Binance": 4}
    submitter_data.sort(key=lambda x: (payment_order.get(x["payment_method"], 999), x["submitted_by"]))
    
    df = pd.DataFrame(submitter_data)
    df = df[["submitted_by", "payment_method", "payment_number", "total_rows", "ok_count", "file_name", "received_date"]]
    
    current_date = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    data_file = f"reports/payment_list_{type_label.replace(' ', '_')}_{current_date}_{chat_id}.xlsx"
    try:
        df.to_excel(data_file, index=False)
    except:
        data_file = f"reports/payment_list_{type_label.replace(' ', '_')}_{current_date}_{chat_id}.csv"
        df.to_csv(data_file, index=False, encoding='utf-8-sig')
    
    total_submitters = len(submitter_data)
    total_rows = sum(d["total_rows"] for d in submitter_data)
    total_ok = sum(d["ok_count"] for d in submitter_data)
    
    try:
        master_bot.delete_message(chat_id, status_msg.message_id)
    except:
        pass
    
    summary = f"""{PEM['ok']} PAYMENT LIST REPORT

{PEM['file']} Type: {type_label}
{PEM['date']} Generated: {current_date}
━━━━━━━━━━━━━━━━━━━━
{PEM['file']} Total Files: {total_submitters}
{PEM['stats']} Total Rows: {total_rows}
{PEM['ok']} Total OK: {total_ok}
━━━━━━━━━━━━━━━━━━━━

{PEM['download']} Downloading file..."""
    
    msg = master_bot.send_message(chat_id, summary)
    if chat_id not in bot_reply_messages:
        bot_reply_messages[chat_id] = []
    bot_reply_messages[chat_id].append(msg.message_id)
    
    with open(data_file, "rb") as f:
        master_bot.send_document(
            chat_id, 
            f, 
            caption=f"""📊 {type_label} PAYMENT LIST
📅 Date: {current_date}
📁 Total Files: {total_submitters}
✅ Total OK: {total_ok}

Columns: submitted_by, payment_method, payment_number, total_rows, ok_count, file_name, received_date"""
        )
    
    os.remove(data_file)

# ================= 💳 [ USER PAYMENTS ] =================

@master_bot.message_handler(func=lambda m: m.text == f"{PEM['payment']} User Payments")
def m_user_payments(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    db = load_db()
    user_payments = db.get("user_payment_settings", {})
    
    if not user_payments:
        msg = master_bot.send_message(
            m.chat.id, 
            f"{PEM['no']} No user payment data found!"
        )
        if m.chat.id not in bot_reply_messages:
            bot_reply_messages[m.chat.id] = []
        bot_reply_messages[m.chat.id].append(msg.message_id)
        return
    
    status_msg = master_bot.send_message(
        m.chat.id, 
        f"{PEM['processing']} Generating User Payment List..."
    )
    
    payment_data = []
    for user_id, payment_info in user_payments.items():
        payment_data.append({
            "User ID": user_id,
            "Username": "Unknown",
            "Method": payment_info.get("payment_method", "N/A"),
            "Number": payment_info.get("payment_number", "N/A")
        })
    
    current_date = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    df = pd.DataFrame(payment_data)
    df = df[["User ID", "Username", "Method", "Number"]]
    
    data_file = f"reports/user_payments_{current_date}_{m.chat.id}.xlsx"
    try:
        df.to_excel(data_file, index=False)
    except:
        data_file = f"reports/user_payments_{current_date}_{m.chat.id}.csv"
        df.to_csv(data_file, index=False, encoding='utf-8-sig')
    
    try:
        master_bot.delete_message(m.chat.id, status_msg.message_id)
    except:
        pass
    
    summary = f"""{PEM['payment']} USER PAYMENT REPORT

📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
👥 Total Users: {len(payment_data)}
━━━━━━━━━━━━━━━━━━━━

📥 Downloading file..."""
    
    msg = master_bot.send_message(m.chat.id, summary)
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)
    
    with open(data_file, "rb") as f:
        master_bot.send_document(
            m.chat.id, 
            f, 
            caption=f"""📊 USER PAYMENT LIST
📅 Date: {current_date}
👥 Total Users: {len(payment_data)}

Columns: User ID, Username, Method, Number"""
        )
    
    os.remove(data_file)

# ================= 📊 [ TOTAL STATS ] =================

@master_bot.message_handler(func=lambda m: m.text == f"{PEM['stats']} Total Stats")
def m_stats(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    db = load_db()
    
    type_stats = {}
    total_files_all = 0
    total_rows_all = 0
    
    for file_type in ["ig_cookies", "ig_2fa", "fb_0fd_2fa"]:
        files_data = db["files"].get(file_type, {})
        file_count = len(files_data)
        total_files_all += file_count
        
        total_rows = 0
        for file_hash, file_info in files_data.items():
            total_rows += file_info.get("total_rows_in_file", 0)
        total_rows_all += total_rows
        
        unique_data = db["all_unique_data"].get(file_type, {})
        unique_count = len(unique_data)
        
        type_stats[file_type] = {
            "files": file_count,
            "rows": total_rows,
            "unique": unique_count,
            "status": type_status.get(file_type, False)
        }
    
    user_ids = load_user_ids()
    global_unique_count = len(db.get("global_unique_keys", []))
    bot_count = len(db.get("tokens", []))
    user_payment_count = len(db.get("user_payment_settings", {}))
    
    stats_msg = f"""{PEM['stats']} TOTAL STATISTICS
📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{PEM['bot']} Bots: {bot_count}
{PEM['user']} Users: {len(user_ids)}
{PEM['payment']} Payment Users: {user_payment_count}
{PEM['stats']} Global Records: {global_unique_count}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📂 TYPE WISE STATISTICS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
    
    for file_type, stats in type_stats.items():
        display_name = get_type_display_name(file_type)
        icon = get_type_icon(file_type)
        status_icon = "🟢" if stats["status"] else "🔴"
        
        stats_msg += (
            f"{icon} {display_name}\n"
            f"  {status_icon} Status: {'ON' if stats['status'] else 'OFF'}\n"
            f"  📁 Files: {stats['files']}\n"
            f"  📊 Rows: {stats['rows']}\n"
            f"  📋 Unique: {stats['unique']}\n\n"
        )
    
    stats_msg += (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 SUMMARY\n"
        f"📁 Total Files: {total_files_all}\n"
        f"📊 Total Rows: {total_rows_all}\n"
        f"🔄 Active Types: {sum(1 for s in type_status.values() if s)}/{len(type_status)}"
    )
    
    msg = master_bot.send_message(m.chat.id, stats_msg)
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

# ================= 🎛️ [ TYPE CONTROL ] =================

@master_bot.message_handler(func=lambda m: m.text == f"{PEM['settings']} Type Control")
def m_type_control(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(f"{'🟢' if type_status['ig_cookies'] else '🔴'} {get_type_display_name('ig_cookies')}", callback_data="toggle_ig_cookies"),
        types.InlineKeyboardButton(f"{'🟢' if type_status['ig_2fa'] else '🔴'} {get_type_display_name('ig_2fa')}", callback_data="toggle_ig_2fa"),
        types.InlineKeyboardButton(f"{'🟢' if type_status['fb_0fd_2fa'] else '🔴'} {get_type_display_name('fb_0fd_2fa')}", callback_data="toggle_fb_0fd_2fa"),
        types.InlineKeyboardButton(f"{PEM['back']} Back", callback_data="back_to_menu")
    )
    
    msg = master_bot.send_message(
        m.chat.id,
        f"""{PEM['settings']} TYPE CONTROL PANEL

Click to toggle ON/OFF:

━━━━━━━━━━━━━━━━━━━━
{PEM['pin']} <b>Select an option below</b>""",
        reply_markup=kb,
        parse_mode="HTML"
    )
    
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

@master_bot.callback_query_handler(func=lambda c: c.data.startswith("toggle_"))
def m_toggle_type(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, f"{PEM['no']} Unauthorized!")
        return
    
    type_name = c.data.replace("toggle_", "")
    type_status[type_name] = not type_status.get(type_name, True)
    
    status_text = "ON" if type_status[type_name] else "OFF"
    master_bot.answer_callback_query(c.id, f"{get_type_display_name(type_name)} is now {status_text}")
    
    delete_previous_bot_replies(c.message.chat.id)
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(f"{'🟢' if type_status['ig_cookies'] else '🔴'} {get_type_display_name('ig_cookies')}", callback_data="toggle_ig_cookies"),
        types.InlineKeyboardButton(f"{'🟢' if type_status['ig_2fa'] else '🔴'} {get_type_display_name('ig_2fa')}", callback_data="toggle_ig_2fa"),
        types.InlineKeyboardButton(f"{'🟢' if type_status['fb_0fd_2fa'] else '🔴'} {get_type_display_name('fb_0fd_2fa')}", callback_data="toggle_fb_0fd_2fa"),
        types.InlineKeyboardButton(f"{PEM['back']} Back", callback_data="back_to_menu")
    )
    
    msg = master_bot.send_message(
        c.message.chat.id,
        f"""{PEM['settings']} TYPE CONTROL PANEL

🟢 {get_type_display_name('ig_cookies')}: {'ON' if type_status['ig_cookies'] else 'OFF'}
🟢 {get_type_display_name('ig_2fa')}: {'ON' if type_status['ig_2fa'] else 'OFF'}
🟢 {get_type_display_name('fb_0fd_2fa')}: {'ON' if type_status['fb_0fd_2fa'] else 'OFF'}

━━━━━━━━━━━━━━━━━━━━
{PEM['pin']} <b>Click to toggle:</b>""",
        reply_markup=kb,
        parse_mode="HTML"
    )
    
    if c.message.chat.id not in bot_reply_messages:
        bot_reply_messages[c.message.chat.id] = []
    bot_reply_messages[c.message.chat.id].append(msg.message_id)

# ================= 📁 [ DOWNLOAD BY TYPE ] =================

@master_bot.message_handler(func=lambda m: m.text == f"{PEM['file']} Download by Type")
def m_download_by_type(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"{get_type_icon('ig_cookies')} {get_type_display_name('ig_cookies')}", callback_data="dltype_ig_cookies"),
        types.InlineKeyboardButton(f"{get_type_icon('ig_2fa')} {get_type_display_name('ig_2fa')}", callback_data="dltype_ig_2fa"),
        types.InlineKeyboardButton(f"{get_type_icon('fb_0fd_2fa')} {get_type_display_name('fb_0fd_2fa')}", callback_data="dltype_fb_0fd_2fa"),
        types.InlineKeyboardButton(f"{PEM['no']} Cancel", callback_data="dltype_cancel")
    )
    msg = master_bot.send_message(m.chat.id, f"{PEM['file']} Select type:", reply_markup=kb)
    
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

@master_bot.callback_query_handler(func=lambda c: c.data.startswith("dltype_"))
def m_download_type_callback(c):
    if c.data == "dltype_cancel":
        try:
            master_bot.delete_message(c.message.chat.id, c.message.message_id)
        except:
            pass
        msg = master_bot.send_message(c.message.chat.id, f"{PEM['no']} Cancelled.")
        if c.message.chat.id not in bot_reply_messages:
            bot_reply_messages[c.message.chat.id] = []
        bot_reply_messages[c.message.chat.id].append(msg.message_id)
        return
    
    file_type = c.data.replace("dltype_", "")
    db = load_db()
    
    display_type = get_type_display_name(file_type)
    
    all_unique_data = db["all_unique_data"].get(file_type, {})
    
    if not all_unique_data:
        master_bot.answer_callback_query(c.id, f"{PEM['no']} No data for {display_type}")
        return
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    status_msg = master_bot.send_message(
        c.message.chat.id, 
        f"{PEM['processing']} Generating {display_type} data..."
    )
    
    current_date = datetime.now().strftime("%Y%m%d_%H%M%S")
    data_file = f"reports/user_data_{file_type}_{current_date}_{c.message.chat.id}.csv"
    
    total_rows = 0
    rows_with_cookies = 0
    
    with open(data_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["user", "pass", "cookies", "2fa", "submitted_by", "submitted_at", "received_date"])
        
        for key, item in all_unique_data.items():
            if "data" in item and isinstance(item["data"], list):
                for row in item["data"]:
                    total_rows += 1
                    user_val = row.get("user", "")
                    pass_val = row.get("pass", "")
                    cookies_val = row.get("cookies", "")
                    twofa_val = row.get("2fa", "")
                    received_date = item.get("received_date", "Unknown")
                    
                    if cookies_val:
                        rows_with_cookies += 1
                    
                    writer.writerow([
                        user_val if user_val else "",
                        pass_val if pass_val else "",
                        cookies_val if cookies_val else "",
                        twofa_val if twofa_val else "",
                        item.get("submitted_by", ""),
                        item.get("submitted_at", ""),
                        received_date
                    ])
    
    try:
        master_bot.delete_message(c.message.chat.id, status_msg.message_id)
    except:
        pass
    
    with open(data_file, "rb") as f:
        master_bot.send_document(
            c.message.chat.id, 
            f, 
            caption=f"""📊 {display_type}
📅 Date: {current_date}
Total rows: {total_rows}
Rows with Cookies: {rows_with_cookies}"""
        )
    
    os.remove(data_file)

# ================= 🗑 [ CLEAR DATA ] =================

@master_bot.message_handler(func=lambda m: m.text == f"{PEM['trash']} Clear Data")
def m_clear_data(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"{get_type_icon('ig_cookies')} {get_type_display_name('ig_cookies')}", callback_data="clear_ig_cookies"),
        types.InlineKeyboardButton(f"{get_type_icon('ig_2fa')} {get_type_display_name('ig_2fa')}", callback_data="clear_ig_2fa"),
        types.InlineKeyboardButton(f"{get_type_icon('fb_0fd_2fa')} {get_type_display_name('fb_0fd_2fa')}", callback_data="clear_fb_0fd_2fa"),
        types.InlineKeyboardButton(f"{PEM['trash']} Clear All", callback_data="clear_all"),
        types.InlineKeyboardButton(f"{PEM['no']} Cancel", callback_data="clear_cancel")
    )
    
    msg = master_bot.send_message(
        m.chat.id,
        f"""{PEM['trash']} CLEAR DATA

Select which type to clear:

━━━━━━━━━━━━━━━━━━━━
{PEM['pin']} <b>Select an option below</b>

{PEM['warn']} <b>Warning:</b> This action cannot be undone!""",
        reply_markup=kb,
        parse_mode="HTML"
    )
    
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

@master_bot.callback_query_handler(func=lambda c: c.data.startswith("clear_"))
def m_clear_callback(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, f"{PEM['no']} Unauthorized!")
        return
    
    if c.data == "clear_cancel":
        try:
            master_bot.delete_message(c.message.chat.id, c.message.message_id)
        except:
            pass
        msg = master_bot.send_message(c.message.chat.id, f"{PEM['no']} Cancelled.")
        if c.message.chat.id not in bot_reply_messages:
            bot_reply_messages[c.message.chat.id] = []
        bot_reply_messages[c.message.chat.id].append(msg.message_id)
        return
    
    db = load_db()
    
    if c.data == "clear_all":
        for file_type in ["ig_cookies", "ig_2fa", "fb_0fd_2fa"]:
            db["files"][file_type] = {}
            db["all_unique_data"][file_type] = {}
            
            folder_path = f"uploads/{file_type}"
            if os.path.exists(folder_path):
                for f in os.listdir(folder_path):
                    try:
                        os.remove(os.path.join(folder_path, f))
                    except:
                        pass
        
        db["global_unique_keys"] = []
        save_db(db)
        
        try:
            master_bot.delete_message(c.message.chat.id, c.message.message_id)
        except:
            pass
        
        msg = master_bot.send_message(c.message.chat.id, f"{PEM['ok']} ALL DATA CLEARED!")
        if c.message.chat.id not in bot_reply_messages:
            bot_reply_messages[c.message.chat.id] = []
        bot_reply_messages[c.message.chat.id].append(msg.message_id)
        return
    
    type_to_clear = c.data.replace("clear_", "")
    display_name = get_type_display_name(type_to_clear)
    
    db["files"][type_to_clear] = {}
    db["all_unique_data"][type_to_clear] = {}
    
    folder_path = f"uploads/{type_to_clear}"
    if os.path.exists(folder_path):
        for f in os.listdir(folder_path):
            try:
                os.remove(os.path.join(folder_path, f))
            except:
                pass
    
    all_keys = set()
    for file_type in ["ig_cookies", "ig_2fa", "fb_0fd_2fa"]:
        if file_type != type_to_clear:
            for item in db["all_unique_data"][file_type].values():
                if "data" in item:
                    for row in item["data"]:
                        key = f"{row.get('user', '')}_{row.get('pass', '')}_{row.get('cookies', '')}_{row.get('2fa', '')}".lower()
                        if key:
                            all_keys.add(key)
    db["global_unique_keys"] = list(all_keys)
    
    save_db(db)
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    msg = master_bot.send_message(
        c.message.chat.id, 
        f"{PEM['ok']} {display_name} DATA CLEARED!"
    )
    if c.message.chat.id not in bot_reply_messages:
        bot_reply_messages[c.message.chat.id] = []
    bot_reply_messages[c.message.chat.id].append(msg.message_id)

# ================= 🔍 [ SEARCH USER ] =================

@master_bot.message_handler(func=lambda m: m.text == f"{PEM['search']} Search User")
def m_search_user(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    msg = master_bot.send_message(
        m.chat.id, 
        f"""{PEM['search']} Enter User ID:

Type the User ID to search:
Send /cancel to cancel"""
    )
    master_bot.register_next_step_handler(msg, search_user_payment)

def search_user_payment(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    if m.text and m.text.startswith('/cancel'):
        master_bot.send_message(m.chat.id, f"{PEM['no']} Cancelled.")
        return
    
    search_query = m.text.strip()
    
    db = load_db()
    user_payments = db.get("user_payment_settings", {})
    
    if search_query in user_payments:
        payment = user_payments[search_query]
        
        result_text = f"""{PEM['ok']} User Found!

{PEM['user']} User ID: {search_query}
{PEM['payment']} Method: {payment.get('payment_method', 'N/A')}
📱 Number: {payment.get('payment_number', 'N/A')}"""
        
        msg = master_bot.send_message(m.chat.id, result_text)
        if m.chat.id not in bot_reply_messages:
            bot_reply_messages[m.chat.id] = []
        bot_reply_messages[m.chat.id].append(msg.message_id)
    else:
        msg = master_bot.send_message(
            m.chat.id, 
            f"{PEM['no']} No user found with ID: {search_query}"
        )
        if m.chat.id not in bot_reply_messages:
            bot_reply_messages[m.chat.id] = []
        bot_reply_messages[m.chat.id].append(msg.message_id)

# ================= ➕ [ ADD/REMOVE BOT ] =================

@master_bot.message_handler(func=lambda m: m.text == f"{PEM['add']} Add Bot")
def m_add_bot(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    msg = master_bot.send_message(m.chat.id, f"{PEM['bot']} Send Bot Token:")
    master_bot.register_next_step_handler(msg, save_bot_token)

def save_bot_token(m):
    if m.text.startswith('/'):
        master_bot.send_message(m.chat.id, f"{PEM['no']} Cancelled.")
        return
    
    token = m.text.strip()
    if ':' not in token or len(token) < 30:
        master_bot.send_message(m.chat.id, f"{PEM['no']} Invalid token!")
        return
    
    db = load_db()
    if token not in db["tokens"]:
        db["tokens"].append(token)
        save_db(db)
        threading.Thread(target=start_user_bot, args=(token,), daemon=True).start()
        msg = master_bot.send_message(m.chat.id, f"{PEM['ok']} Bot added!")
        if m.chat.id not in bot_reply_messages:
            bot_reply_messages[m.chat.id] = []
        bot_reply_messages[m.chat.id].append(msg.message_id)
    else:
        master_bot.send_message(m.chat.id, f"{PEM['warn']} Bot already exists!")

@master_bot.message_handler(func=lambda m: m.text == f"{PEM['remove']} Remove Bot")
def m_remove_bot(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    db = load_db()
    if not db["tokens"]:
        master_bot.send_message(m.chat.id, f"{PEM['no']} No bots!")
        return
    
    kb = types.InlineKeyboardMarkup()
    for i, token in enumerate(db["tokens"]):
        kb.add(types.InlineKeyboardButton(f"{PEM['bot']} Bot {i+1}", callback_data=f"remove_{i}"))
    kb.add(types.InlineKeyboardButton(f"{PEM['no']} Cancel", callback_data="remove_cancel"))
    master_bot.send_message(m.chat.id, f"{PEM['remove']} Select bot:", reply_markup=kb)

@master_bot.callback_query_handler(func=lambda c: c.data.startswith("remove_"))
def m_remove_callback(c):
    if c.data == "remove_cancel":
        try:
            master_bot.delete_message(c.message.chat.id, c.message.message_id)
        except:
            pass
        master_bot.send_message(c.message.chat.id, f"{PEM['no']} Cancelled.")
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
        
        master_bot.send_message(c.message.chat.id, f"{PEM['ok']} Bot removed")

# ================= 🔄 [ RESET ALL TYPES ] =================

@master_bot.message_handler(func=lambda m: m.text == f"{PEM['refresh']} Reset All Types")
def m_reset_types(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    global type_status
    type_status = {
        "ig_cookies": True,
        "ig_2fa": True,
        "fb_0fd_2fa": True
    }
    
    msg = master_bot.send_message(m.chat.id, f"{PEM['ok']} All types reset to ON!")
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

# ================= 🔄 [ MAIN FUNCTION ] =================

def main():
    """Main entry point for the bot"""
    print("=" * 50)
    print("👑 ID RECEIVER SYSTEM v30.0")
    print("🎛️ UNIQUE OK COUNT")
    print("🎛️ EACH FILE SEPARATE IN PAYMENT LIST")
    print("🎛️ DATE FORMAT: DD-MM-YYYY")
    print("🎛️ PAYMENT METHOD ORDER: bKash → Nagad → Rocket → Binance")
    print("🎛️ MAIN MENU KEEPS")
    print("🎛️ USER MESSAGES KEPT")
    print("🎛️ ONLY BOT REPLIES DELETED")
    print("🎛️ PREMIUM EMOJI SUPPORT")
    print("🎛️ FACEBOOK 0FD COOKIES SUPPORT")
    print("🎛️ COOKIES IN SEPARATE COLUMN")
    print("=" * 50)
    
    if not MASTER_ADMIN_TOKEN:
        print("❌ ERROR: MASTER_ADMIN_TOKEN not found in environment variables!")
        print("📌 Please set MASTER_ADMIN_TOKEN in Railway Variables")
        return
    
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

def run_all_bots():
    db = load_db()
    tokens = db.get("tokens", [])
    print(f"🔄 Loading {len(tokens)} user bots...")
    for token in tokens:
        if token not in active_bots:
            threading.Thread(target=start_user_bot, args=(token,), daemon=True).start()
            time.sleep(2)

if __name__ == "__main__":
    main()
