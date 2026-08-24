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

# Environment Variables
MASTER_ADMIN_TOKEN = os.environ.get("MASTER_ADMIN_TOKEN")
ADMIN_IDS_STR = os.environ.get("ADMIN_IDS", "6293094676")
ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS_STR.split(",")]

# ========================================================
TYPE_NAMES = {
    "ig_cookies": "Instagram Cookies",
    "ig_2fa": "Instagram 2FA",
    "fb_0fd_2fa": "Facebook 0FD Cookies"
}

TYPE_ICONS = {
    "ig_cookies": "📱",
    "ig_2fa": "🔐",
    "fb_0fd_2fa": "📘"
}
# ========================================================

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

# ================= 🔐 [ 3. FILE PROCESSING - FACEBOOK 0FD COOKIES FIXED ] =================

def auto_detect_columns(row):
    """Detect columns: uid, pass, cookies for Facebook 0FD"""
    user_val = ""
    pass_val = ""
    cookies_val = ""
    
    # প্রথমে সব কলামের নাম লোয়ার কেসে কনভার্ট করুন
    row_lower = {str(k).lower().strip(): v for k, v in row.items()}
    
    for k, v in row_lower.items():
        v_str = str(v).strip()
        if v_str and v_str != 'nan' and v_str != 'None':
            # UID ডিটেক্ট করুন (uid, user_id, id, userid)
            if k in ['uid', 'user_id', 'id', 'userid']:
                user_val = v_str
            # Cookies ডিটেক্ট করুন (সম্পূর্ণ কুকি স্ট্রিং)
            elif k in ['cookies', 'cookie', 'c_user', 'xs', 'datr', 'sb', 'dpr', 'wd', 'm_pixel_ratio', 'ps_l', 'ps_n', 'fr', 'locale', 'pas', 'wl_cbv', 'fbl_st', 'vpd', 'x-referer']:
                if not cookies_val:
                    cookies_val = v_str
                else:
                    cookies_val += "; " + v_str
            # Password ডিটেক্ট করুন
            elif k in ['pass', 'password', 'pwd']:
                pass_val = v_str
            # Username/Email ডিটেক্ট করুন
            elif k in ['user', 'username', 'email', 'mail']:
                if not user_val:
                    user_val = v_str
    
    # 🔥 Cookies Mode: user (uid) + pass + cookies
    if user_val and cookies_val:
        return user_val, pass_val, cookies_val, "cookies_mode"
    
    # সাধারণ ডিটেকশন (Instagram ইত্যাদির জন্য)
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
            
            # 🔥 Facebook 0FD Cookies Mode
            if mode == "cookies_mode":
                filtered_data.append({
                    "user": user_val,       # UID
                    "pass": pass_val,       # Password
                    "cookies": cookies_val, # 🔥 সম্পূর্ণ Cookies
                    "2fa": "",              # খালি
                    "mode": "cookies"
                })
                rows_with_cookies += 1
            else:
                # যদি cookies ডিটেক্ট হয়
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
                "❌ NO DATA FOUND!\n\nYour file was empty or had no readable data."
            )
            return False
        
        file_db = db["files"][file_type]
        
        if file_hash in file_db:
            with open(file_path, "rb") as dup_file:
                bot.send_document(chat_id, dup_file, caption=f"⚠️ DUPLICATE FILE!")
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
                "❌ NO UNIQUE DATA!\n\nAll rows already exist in database."
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
        
        result_msg = (
            f"✅ FILE PROCESSED SUCCESSFULLY!\n\n"
            f"📁 File: {original_name}\n"
            f"📂 Type: {get_type_display_name(file_type)}\n"
            f"💳 Payment: {payment_method} - {payment_number}\n"
            f"📅 Received: {current_date}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Valid rows: {valid_rows}\n"
        )
        
        if rows_with_cookies > 0:
            result_msg += f"🍪 Cookies rows: {rows_with_cookies}\n"
        
        result_msg += f"✨ Status: Successfully received"
        
        bot.send_message(chat_id, result_msg)
        
        for admin_id in ADMIN_IDS:
            try:
                master_bot.send_message(
                    admin_id, 
                    f"📢 NEW FILE RECEIVED!\n"
                    f"👤 {username}\n"
                    f"📂 {get_type_display_name(file_type)}\n"
                    f"📊 {valid_rows} unique rows\n"
                    f"💳 {payment_method} - {payment_number}\n"
                    f"📅 {current_date}"
                )
            except:
                pass
        
        return True
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ ERROR!\n\n{str(e)}")
        return False

def get_type_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    
    if type_status["ig_cookies"]:
        kb.add(types.InlineKeyboardButton(
            f"📱 {get_type_display_name('ig_cookies')}", 
            callback_data="type_ig_cookies"
        ))
    else:
        kb.add(types.InlineKeyboardButton(
            f"🔴 {get_type_display_name('ig_cookies')} (Closed)", 
            callback_data="type_disabled_ig_cookies"
        ))
    
    if type_status["ig_2fa"]:
        kb.add(types.InlineKeyboardButton(
            f"🔐 {get_type_display_name('ig_2fa')}", 
            callback_data="type_ig_2fa"
        ))
    else:
        kb.add(types.InlineKeyboardButton(
            f"🔴 {get_type_display_name('ig_2fa')} (Closed)", 
            callback_data="type_disabled_ig_2fa"
        ))
    
    if type_status["fb_0fd_2fa"]:
        kb.add(types.InlineKeyboardButton(
            f"📘 {get_type_display_name('fb_0fd_2fa')}", 
            callback_data="type_fb_0fd_2fa"
        ))
    else:
        kb.add(types.InlineKeyboardButton(
            f"🔴 {get_type_display_name('fb_0fd_2fa')} (Closed)", 
            callback_data="type_disabled_fb_0fd_2fa"
        ))
    
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
            btn2 = types.InlineKeyboardButton("💳 Change Payment", callback_data="change_payment")
            kb.add(btn1, btn2)
            
            db = load_db()
            user_payment = db["user_payment_settings"].get(str(m.chat.id), {})
            
            payment_info = ""
            if user_payment:
                payment_info = f"\n\n💳 Current Payment:\n{user_payment.get('payment_method', 'N/A')} - {user_payment.get('payment_number', 'N/A')}"
            
            bot.send_message(
                m.chat.id,
                f"✨ ID RECEIVER BOT ✨\n\n"
                f"👋 Hello {m.from_user.first_name}!{payment_info}\n\n"
                f"📂 Supported: Any file format\n"
                f"📌 Auto detects: uid, pass, cookies\n"
                f"💳 Payment: bKash, Nagad, Rocket, Binance\n"
                f"🔄 Auto duplicate remove\n\n"
                f"📌 Click below to start",
                reply_markup=kb
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
                btn1 = types.InlineKeyboardButton("🏦 bKash", callback_data="change_pay_bkash")
                btn2 = types.InlineKeyboardButton("🏧 Nagad", callback_data="change_pay_nagad")
                btn3 = types.InlineKeyboardButton("💳 Rocket", callback_data="change_pay_rocket")
                btn4 = types.InlineKeyboardButton("₿ Binance", callback_data="change_pay_binance")
                btn5 = types.InlineKeyboardButton("❌ Cancel", callback_data="cancel_payment_change")
                kb.add(btn1, btn2, btn3, btn4, btn5)
                
                bot.send_message(
                    user_id,
                    "💰 Change Payment Method\n\nSelect your new payment method:",
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
                    f"✅ {method_name} Selected\n\n📝 Send your new {method_name} number:"
                )
                bot.register_next_step_handler_by_chat_id(user_id, update_payment_number)
            
            elif c.data == "cancel_payment_change":
                try:
                    bot.delete_message(c.message.chat.id, c.message.message_id)
                except:
                    pass
                
                kb = types.InlineKeyboardMarkup(row_width=1)
                btn1 = types.InlineKeyboardButton("📁 Submit File", callback_data="submit_file")
                btn2 = types.InlineKeyboardButton("💳 Change Payment", callback_data="change_payment")
                kb.add(btn1, btn2)
                
                bot.send_message(
                    user_id,
                    "❌ Payment change cancelled",
                    reply_markup=kb
                )
            
            elif c.data == "submit_file":
                try:
                    bot.delete_message(c.message.chat.id, c.message.message_id)
                except:
                    pass
                
                bot.send_message(
                    c.message.chat.id,
                    "📂 Select File Type:",
                    reply_markup=get_type_keyboard()
                )
            
            elif c.data.startswith("type_disabled_"):
                bot.answer_callback_query(c.id, "❌ This type is currently closed!", show_alert=True)
            
            elif c.data.startswith("type_"):
                file_type = c.data.replace("type_", "")
                
                if not type_status.get(file_type, False):
                    bot.answer_callback_query(c.id, "❌ This type is currently closed!", show_alert=True)
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
                        f"✅ Auto Payment Selected\n\n"
                        f"💳 {user_payment['payment_method']} - {user_payment['payment_number']}\n\n"
                        f"📎 Send your file now"
                    )
                    bot.register_next_step_handler_by_chat_id(user_id, receive_file)
                else:
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
                        "💰 Select Payment Method:",
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
                    f"✅ {method_name} Selected\n\n📝 Send your {method_name} number (you won't need to enter this again):"
                )
                bot.register_next_step_handler_by_chat_id(user_id, save_payment_and_continue)
            
            elif c.data == "cancel_submit":
                user_sessions.pop(user_id, None)
                
                kb = types.InlineKeyboardMarkup(row_width=1)
                btn1 = types.InlineKeyboardButton("📁 Submit File", callback_data="submit_file")
                btn2 = types.InlineKeyboardButton("💳 Change Payment", callback_data="change_payment")
                kb.add(btn1, btn2)
                
                try:
                    bot.delete_message(c.message.chat.id, c.message.message_id)
                except:
                    pass
                
                bot.send_message(
                    c.message.chat.id,
                    "❌ Cancelled\n\nClick below to start over:",
                    reply_markup=kb
                )

        def update_payment_number(m):
            user_id = m.chat.id
            
            if user_id not in user_sessions or not user_sessions[user_id].get("changing_payment"):
                bot.send_message(user_id, "❌ Session expired. Use /start")
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
            btn1 = types.InlineKeyboardButton("📁 Submit File", callback_data="submit_file")
            btn2 = types.InlineKeyboardButton("💳 Change Payment", callback_data="change_payment")
            kb.add(btn1, btn2)
            
            bot.send_message(
                user_id,
                f"✅ Payment Updated!\n\n"
                f"💳 {new_method} - {new_number}\n\n"
                f"Your payment method has been saved.",
                reply_markup=kb
            )

        def save_payment_and_continue(m):
            user_id = m.chat.id
            
            if user_id not in user_sessions:
                bot.send_message(user_id, "❌ Session expired. Use /start")
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
                f"✅ Payment saved!\n\n"
                f"💳 {user_sessions[user_id]['payment_method']} - {payment_number}\n"
                f"🔄 You won't need to enter this again.\n\n"
                f"📎 Send your file now"
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
            current_date = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            file_info = bot.get_file(m.document.file_id)
            save_name = f"{user_id}_{current_date}_{m.document.file_name}"
            save_path = os.path.join("uploads", file_type, save_name)
            
            downloaded_file = bot.download_file(file_info.file_path)
            with open(save_path, "wb") as f:
                f.write(downloaded_file)
            
            bot.send_message(user_id, "⏳ Processing...")
            
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
        master_bot.send_message(m.chat.id, "❌ Unauthorized!")
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row("📊 Total Stats", "📥 Payment List")
    kb.row("📁 Download by Type", "🎛️ Type Control")
    kb.row("📋 Report Check", "📢 Broadcast")
    kb.row("⚙️ More Options")
    
    msg = master_bot.send_message(
        m.chat.id,
        f"👑 MASTER ADMIN PANEL 👑\n\n"
        f"🎛️ Current Status:\n"
        f"🟢 {get_type_display_name('ig_cookies')}: {'ON' if type_status['ig_cookies'] else 'OFF'}\n"
        f"🟢 {get_type_display_name('ig_2fa')}: {'ON' if type_status['ig_2fa'] else 'OFF'}\n"
        f"🟢 {get_type_display_name('fb_0fd_2fa')}: {'ON' if type_status['fb_0fd_2fa'] else 'OFF'}\n\n"
        f"📌 Select an option below",
        reply_markup=kb
    )
    
    main_menu_id[m.chat.id] = msg.message_id
    
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

@master_bot.message_handler(func=lambda m: m.text == "⚙️ More Options")
def m_more_options(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row("➕ Add Bot", "❌ Remove Bot")
    kb.row("🔄 Reset All Types", "🗑 Clear Data")
    kb.row("💳 User Payments", "🔍 Search User")
    kb.row("🔙 Back to Main Menu")
    
    msg = master_bot.send_message(
        m.chat.id,
        "⚙️ MORE OPTIONS\n\nSelect an option below:",
        reply_markup=kb
    )
    
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

@master_bot.message_handler(func=lambda m: m.text == "🔙 Back to Main Menu")
def back_to_main_menu(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row("📊 Total Stats", "📥 Payment List")
    kb.row("📁 Download by Type", "🎛️ Type Control")
    kb.row("📋 Report Check", "📢 Broadcast")
    kb.row("⚙️ More Options")
    
    msg = master_bot.send_message(
        m.chat.id,
        f"👑 MASTER ADMIN PANEL 👑\n\n"
        f"🎛️ Current Status:\n"
        f"🟢 {get_type_display_name('ig_cookies')}: {'ON' if type_status['ig_cookies'] else 'OFF'}\n"
        f"🟢 {get_type_display_name('ig_2fa')}: {'ON' if type_status['ig_2fa'] else 'OFF'}\n"
        f"🟢 {get_type_display_name('fb_0fd_2fa')}: {'ON' if type_status['fb_0fd_2fa'] else 'OFF'}\n\n"
        f"📌 Select an option below",
        reply_markup=kb
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
    kb.row("📊 Total Stats", "📥 Payment List")
    kb.row("📁 Download by Type", "🎛️ Type Control")
    kb.row("📋 Report Check", "📢 Broadcast")
    kb.row("⚙️ More Options")
    
    msg = master_bot.send_message(
        c.message.chat.id,
        f"👑 MASTER ADMIN PANEL 👑\n\n"
        f"🎛️ Current Status:\n"
        f"🟢 {get_type_display_name('ig_cookies')}: {'ON' if type_status['ig_cookies'] else 'OFF'}\n"
        f"🟢 {get_type_display_name('ig_2fa')}: {'ON' if type_status['ig_2fa'] else 'OFF'}\n"
        f"🟢 {get_type_display_name('fb_0fd_2fa')}: {'ON' if type_status['fb_0fd_2fa'] else 'OFF'}\n\n"
        f"📌 Select an option below",
        reply_markup=kb
    )
    
    main_menu_id[c.message.chat.id] = msg.message_id
    
    if c.message.chat.id not in bot_reply_messages:
        bot_reply_messages[c.message.chat.id] = []
    bot_reply_messages[c.message.chat.id].append(msg.message_id)

# ================= 📢 [ BROADCAST ] =================

@master_bot.message_handler(func=lambda m: m.text == "📢 Broadcast")
def m_broadcast(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    user_ids = load_user_ids()
    if not user_ids:
        msg = master_bot.send_message(m.chat.id, "❌ No users found!")
        if m.chat.id not in bot_reply_messages:
            bot_reply_messages[m.chat.id] = []
        bot_reply_messages[m.chat.id].append(msg.message_id)
        return
    
    if not active_bots:
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("➕ Add Bot", callback_data="goto_add_bot_from_broadcast"))
        msg = master_bot.send_message(
            m.chat.id,
            "❌ NO ACTIVE USER BOTS!\n\nPlease add a bot first:",
            reply_markup=kb
        )
        if m.chat.id not in bot_reply_messages:
            bot_reply_messages[m.chat.id] = []
        bot_reply_messages[m.chat.id].append(msg.message_id)
        return
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("📝 Send Message", callback_data="broadcast_text"),
        types.InlineKeyboardButton("🔙 Back", callback_data="broadcast_back")
    )
    
    msg = master_bot.send_message(
        m.chat.id,
        f"📢 BROADCAST\n\n🤖 Active Bots: {len(active_bots)}\n👥 Total Users: {len(user_ids)}\n\nClick below to start:",
        reply_markup=kb
    )
    
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

@master_bot.callback_query_handler(func=lambda c: c.data == "goto_add_bot_from_broadcast")
def goto_add_bot_from_broadcast(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, "❌ Unauthorized!")
        return
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    msg = master_bot.send_message(
        c.message.chat.id,
        "🤖 Send Bot Token:\n\nGet token from @BotFather\nSend /cancel to cancel:"
    )
    master_bot.register_next_step_handler(msg, save_bot_token)

@master_bot.callback_query_handler(func=lambda c: c.data.startswith("broadcast_"))
def broadcast_callback(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, "❌ Unauthorized!")
        return
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    if c.data == "broadcast_back":
        back_to_main_menu(c)
        return
    
    if c.data == "broadcast_text":
        msg = master_bot.send_message(
            c.message.chat.id,
            "📝 Send your message\n\nSend /cancel to cancel:"
        )
        master_bot.register_next_step_handler(msg, send_text_broadcast)

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
    
    user_message = m.text
    
    final_message = f"""‼️ ATTENTION ‼️

{user_message}

Thanks by MAX FUTURE ✅"""
    
    user_ids = load_user_ids()
    
    if not user_ids:
        master_bot.send_message(m.chat.id, "❌ No users found!")
        return
    
    if not active_bots:
        master_bot.send_message(m.chat.id, "❌ No active user bots!")
        return
    
    total_users = len(user_ids)
    status_msg = master_bot.send_message(m.chat.id, f"⏳ Sending to {total_users} users...")
    
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
                    f"⏳ Sending...\n\n📤 Sent: {success}\n❌ Failed: {fail}\n📊 Progress: {idx + 1}/{total_users}",
                    chat_id=status_msg.chat.id,
                    message_id=status_msg.message_id
                )
            except:
                pass
        
        time.sleep(0.03)
    
    try:
        master_bot.delete_message(m.chat.id, status_msg.message_id)
    except:
        pass
    
    result_msg = f"✅ Broadcast Complete!\n\n📤 Success: {success}\n❌ Failed: {fail}\n👥 Total users: {total_users}"
    
    if fail > 0:
        result_msg += f"\n\n⚠️ {fail} users didn't receive the message."
    
    master_bot.send_message(m.chat.id, result_msg)

# ================= 📋 [ REPORT CHECK ] =================

@master_bot.message_handler(func=lambda m: m.text == "📋 Report Check")
def m_report_check(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"📱 {get_type_display_name('ig_cookies')}", callback_data="report_select_ig_cookies"),
        types.InlineKeyboardButton(f"🔐 {get_type_display_name('ig_2fa')}", callback_data="report_select_ig_2fa"),
        types.InlineKeyboardButton(f"📘 {get_type_display_name('fb_0fd_2fa')}", callback_data="report_select_fb_0fd_2fa"),
        types.InlineKeyboardButton("📊 All Types", callback_data="report_select_all"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="report_cancel")
    )
    
    msg = master_bot.send_message(
        m.chat.id,
        "📋 REPORT CHECK\n\nSelect which type to check with OK list:\n\n💡 You will need to upload a TXT file containing usernames/emails.",
        reply_markup=kb
    )
    
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

@master_bot.callback_query_handler(func=lambda c: c.data.startswith("report_select_"))
def m_report_select_callback(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, "❌ Unauthorized!")
        return
    
    if c.data == "report_cancel":
        try:
            master_bot.delete_message(c.message.chat.id, c.message.message_id)
        except:
            pass
        msg = master_bot.send_message(c.message.chat.id, "❌ Report check cancelled.")
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
        f"✅ {display_type} Selected\n\n"
        f"📁 Now send your OK TXT file:\n\n"
        f"💡 Each line should contain one username/email\n"
        f"📌 Example:\n"
        f"   • john_doe\n"
        f"   • jane@email.com\n\n"
        f"Send /cancel to cancel:"
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
        msg = master_bot.send_message(m.chat.id, "❌ Please send a TXT file!")
        if m.chat.id not in bot_reply_messages:
            bot_reply_messages[m.chat.id] = []
        bot_reply_messages[m.chat.id].append(msg.message_id)
        return
    
    if not m.document.file_name.endswith('.txt'):
        msg = master_bot.send_message(m.chat.id, "❌ Only TXT files are supported!")
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
        "⏳ Reading OK list file..."
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
            f"❌ Failed to read file!\n\nError: {str(e)}"
        )
        return
    
    if not ok_list:
        master_bot.send_message(m.chat.id, "❌ No valid data found in TXT file!")
        return
    
    try:
        master_bot.edit_message_text(
            f"⏳ Scanning {len(ok_list)} unique users...\n\n📂 Type: {get_type_display_name(scan_type) if scan_type != 'all' else 'ALL TYPES'}\n🔍 Searching database...",
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
            f"❌ NO MATCHES FOUND!\n\n"
            f"📊 OK List: {len(ok_list)} users\n"
            f"📁 Files Scanned: {total_files_scanned}\n"
            f"📊 Data Scanned: {total_data_scanned}\n"
            f"✅ Matches Found: 0"
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
    
    report = f"✅ REPORT CHECK COMPLETE!\n\n"
    report += f"📂 Type: {display_type}\n"
    report += f"📊 OK List: {len(ok_list)} users\n"
    report += f"📁 Files Scanned: {total_files_scanned}\n"
    report += f"📊 Data Scanned: {total_data_scanned}\n"
    report += f"━━━━━━━━━━━━━━━━━━━━\n"
    report += f"✅ Matched Submitters: {len(results)}\n"
    report += f"📈 Total OK Found: {len(found_ok_usernames)}\n"
    report += f"🕐 Scan Time: {current_ok_data['last_scan_time']}\n"
    report += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    report += f"💳 Payment Breakdown:\n"
    report += f"🏦 bKash: {bkash_count} submitters\n"
    report += f"🏧 Nagad: {nagad_count} submitters\n"
    report += f"💳 Rocket: {rocket_count} submitters\n"
    report += f"₿ Binance: {binance_count} submitters"
    
    msg = master_bot.send_message(m.chat.id, report)
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

# ================= 📥 [ PAYMENT LIST ] =================

@master_bot.message_handler(func=lambda m: m.text == "📥 Payment List")
def m_payment_list(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"📱 {get_type_display_name('ig_cookies')}", callback_data="paylist_select_ig_cookies"),
        types.InlineKeyboardButton(f"🔐 {get_type_display_name('ig_2fa')}", callback_data="paylist_select_ig_2fa"),
        types.InlineKeyboardButton(f"📘 {get_type_display_name('fb_0fd_2fa')}", callback_data="paylist_select_fb_0fd_2fa"),
        types.InlineKeyboardButton("📊 All Types", callback_data="paylist_select_all"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="paylist_cancel")
    )
    
    msg = master_bot.send_message(
        m.chat.id,
        f"📥 PAYMENT LIST\n\nSelect which type you want to see:",
        reply_markup=kb
    )
    
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

@master_bot.callback_query_handler(func=lambda c: c.data.startswith("paylist_select_"))
def m_paylist_select_callback(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, "❌ Unauthorized!")
        return
    
    if c.data == "paylist_cancel":
        try:
            master_bot.delete_message(c.message.chat.id, c.message.message_id)
        except:
            pass
        msg = master_bot.send_message(c.message.chat.id, "❌ Cancelled.")
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
            f"❌ NO DATA FOUND!\n\nType: {type_label}"
        )
        return
    
    status_msg = master_bot.send_message(
        chat_id, 
        f"⏳ Generating {type_label} Payment List..."
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
    
    summary = f"✅ PAYMENT LIST REPORT\n\n"
    summary += f"📂 Type: {type_label}\n"
    summary += f"📅 Generated: {current_date}\n"
    summary += f"━━━━━━━━━━━━━━━━━━━━\n"
    summary += f"📁 Total Files: {total_submitters}\n"
    summary += f"📊 Total Rows: {total_rows}\n"
    summary += f"✅ Total OK: {total_ok}\n"
    summary += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    summary += f"📥 Downloading file..."
    
    msg = master_bot.send_message(chat_id, summary)
    if chat_id not in bot_reply_messages:
        bot_reply_messages[chat_id] = []
    bot_reply_messages[chat_id].append(msg.message_id)
    
    with open(data_file, "rb") as f:
        master_bot.send_document(
            chat_id, 
            f, 
            caption=f"📊 {type_label} PAYMENT LIST\n"
                    f"📅 Date: {current_date}\n"
                    f"📁 Total Files: {total_submitters}\n"
                    f"✅ Total OK: {total_ok}\n\n"
                    f"Columns: submitted_by, payment_method, payment_number, total_rows, ok_count, file_name, received_date"
        )
    
    os.remove(data_file)

# ================= 💳 [ USER PAYMENTS ] =================

@master_bot.message_handler(func=lambda m: m.text == "💳 User Payments")
def m_user_payments(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    db = load_db()
    user_payments = db.get("user_payment_settings", {})
    
    if not user_payments:
        msg = master_bot.send_message(
            m.chat.id, 
            "❌ No user payment data found!"
        )
        if m.chat.id not in bot_reply_messages:
            bot_reply_messages[m.chat.id] = []
        bot_reply_messages[m.chat.id].append(msg.message_id)
        return
    
    status_msg = master_bot.send_message(
        m.chat.id, 
        "⏳ Generating User Payment List..."
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
    
    summary = f"💳 USER PAYMENT REPORT\n\n"
    summary += f"📅 Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    summary += f"👥 Total Users: {len(payment_data)}\n"
    summary += f"━━━━━━━━━━━━━━━━━━━━\n"
    summary += f"📥 Downloading file..."
    
    msg = master_bot.send_message(m.chat.id, summary)
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)
    
    with open(data_file, "rb") as f:
        master_bot.send_document(
            m.chat.id, 
            f, 
            caption=f"📊 USER PAYMENT LIST\n"
                    f"📅 Date: {current_date}\n"
                    f"👥 Total Users: {len(payment_data)}\n\n"
                    f"Columns: User ID, Username, Method, Number"
        )
    
    os.remove(data_file)

# ================= 📊 [ TOTAL STATS ] =================

@master_bot.message_handler(func=lambda m: m.text == "📊 Total Stats")
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
    
    stats_msg = (
        f"📊 TOTAL STATISTICS\n"
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🤖 Bots: {bot_count}\n"
        f"👥 Users: {len(user_ids)}\n"
        f"💳 Payment Users: {user_payment_count}\n"
        f"📊 Global Records: {global_unique_count}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📂 TYPE WISE STATISTICS\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
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

@master_bot.message_handler(func=lambda m: m.text == "🎛️ Type Control")
def m_type_control(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(f"{'🟢' if type_status['ig_cookies'] else '🔴'} {get_type_display_name('ig_cookies')}", callback_data="toggle_ig_cookies"),
        types.InlineKeyboardButton(f"{'🟢' if type_status['ig_2fa'] else '🔴'} {get_type_display_name('ig_2fa')}", callback_data="toggle_ig_2fa"),
        types.InlineKeyboardButton(f"{'🟢' if type_status['fb_0fd_2fa'] else '🔴'} {get_type_display_name('fb_0fd_2fa')}", callback_data="toggle_fb_0fd_2fa"),
        types.InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")
    )
    
    msg = master_bot.send_message(
        m.chat.id,
        "🎛️ TYPE CONTROL PANEL\n\nClick to toggle ON/OFF:",
        reply_markup=kb
    )
    
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

@master_bot.callback_query_handler(func=lambda c: c.data.startswith("toggle_"))
def m_toggle_type(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, "❌ Unauthorized!")
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
        types.InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")
    )
    
    msg = master_bot.send_message(
        c.message.chat.id,
        f"🎛️ TYPE CONTROL PANEL\n\n"
        f"🟢 {get_type_display_name('ig_cookies')}: {'ON' if type_status['ig_cookies'] else 'OFF'}\n"
        f"🟢 {get_type_display_name('ig_2fa')}: {'ON' if type_status['ig_2fa'] else 'OFF'}\n"
        f"🟢 {get_type_display_name('fb_0fd_2fa')}: {'ON' if type_status['fb_0fd_2fa'] else 'OFF'}\n\n"
        f"Click to toggle:",
        reply_markup=kb
    )
    
    if c.message.chat.id not in bot_reply_messages:
        bot_reply_messages[c.message.chat.id] = []
    bot_reply_messages[c.message.chat.id].append(msg.message_id)

# ================= 📁 [ DOWNLOAD BY TYPE ] =================

@master_bot.message_handler(func=lambda m: m.text == "📁 Download by Type")
def m_download_by_type(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"📱 {get_type_display_name('ig_cookies')}", callback_data="dltype_ig_cookies"),
        types.InlineKeyboardButton(f"🔐 {get_type_display_name('ig_2fa')}", callback_data="dltype_ig_2fa"),
        types.InlineKeyboardButton(f"📘 {get_type_display_name('fb_0fd_2fa')}", callback_data="dltype_fb_0fd_2fa"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="dltype_cancel")
    )
    msg = master_bot.send_message(m.chat.id, "Select type:", reply_markup=kb)
    
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
        msg = master_bot.send_message(c.message.chat.id, "❌ Cancelled.")
        if c.message.chat.id not in bot_reply_messages:
            bot_reply_messages[c.message.chat.id] = []
        bot_reply_messages[c.message.chat.id].append(msg.message_id)
        return
    
    file_type = c.data.replace("dltype_", "")
    db = load_db()
    
    display_type = get_type_display_name(file_type)
    
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
        f"⏳ Generating {display_type} data..."
    )
    
    current_date = datetime.now().strftime("%Y%m%d_%H%M%S")
    data_file = f"reports/user_data_{file_type}_{current_date}_{c.message.chat.id}.csv"
    
    total_rows = 0
    rows_with_cookies = 0
    
    # 🔥 Facebook 0FD Cookies এর জন্য আলাদা ফরম্যাট
    if file_type == "fb_0fd_2fa":
        with open(data_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            # 🔥 আপনার চাওয়া ফরম্যাট: uid, pass, cookies, submitted_by, submitted_at, received_date
            writer.writerow(["uid", "pass", "cookies", "submitted_by", "submitted_at", "received_date"])
            
            for key, item in all_unique_data.items():
                if "data" in item and isinstance(item["data"], list):
                    for row in item["data"]:
                        total_rows += 1
                        uid_val = row.get("user", "")
                        pass_val = row.get("pass", "")
                        cookies_val = row.get("cookies", "")
                        received_date = item.get("received_date", "Unknown")
                        
                        if cookies_val:
                            rows_with_cookies += 1
                        
                        writer.writerow([
                            uid_val if uid_val else "",
                            pass_val if pass_val else "",
                            cookies_val if cookies_val else "",
                            item.get("submitted_by", ""),
                            item.get("submitted_at", ""),
                            received_date
                        ])
    else:
        # Instagram এর জন্য পুরানো ফরম্যাট
        with open(data_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["user", "pass", "2fa", "submitted_by", "submitted_at", "received_date"])
            
            for key, item in all_unique_data.items():
                if "data" in item and isinstance(item["data"], list):
                    for row in item["data"]:
                        total_rows += 1
                        user_val = row.get("user", "")
                        pass_val = row.get("pass", "")
                        twofa_val = row.get("2fa", "")
                        received_date = item.get("received_date", "Unknown")
                        
                        if twofa_val:
                            rows_with_cookies += 1
                        
                        writer.writerow([
                            user_val if user_val else "",
                            pass_val if pass_val else "",
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

@master_bot.message_handler(func=lambda m: m.text == "🗑 Clear Data")
def m_clear_data(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"📱 {get_type_display_name('ig_cookies')}", callback_data="clear_ig_cookies"),
        types.InlineKeyboardButton(f"🔐 {get_type_display_name('ig_2fa')}", callback_data="clear_ig_2fa"),
        types.InlineKeyboardButton(f"📘 {get_type_display_name('fb_0fd_2fa')}", callback_data="clear_fb_0fd_2fa"),
        types.InlineKeyboardButton("🗑 Clear All", callback_data="clear_all"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="clear_cancel")
    )
    
    msg = master_bot.send_message(
        m.chat.id,
        "🗑 CLEAR DATA\n\nSelect which type to clear:",
        reply_markup=kb
    )
    
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

@master_bot.callback_query_handler(func=lambda c: c.data.startswith("clear_"))
def m_clear_callback(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, "❌ Unauthorized!")
        return
    
    if c.data == "clear_cancel":
        try:
            master_bot.delete_message(c.message.chat.id, c.message.message_id)
        except:
            pass
        msg = master_bot.send_message(c.message.chat.id, "❌ Cancelled.")
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
        
        msg = master_bot.send_message(c.message.chat.id, "✅ ALL DATA CLEARED!")
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
        f"✅ {display_name} DATA CLEARED!"
    )
    if c.message.chat.id not in bot_reply_messages:
        bot_reply_messages[c.message.chat.id] = []
    bot_reply_messages[c.message.chat.id].append(msg.message_id)

# ================= 🔍 [ SEARCH USER ] =================

@master_bot.message_handler(func=lambda m: m.text == "🔍 Search User")
def m_search_user(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    msg = master_bot.send_message(
        m.chat.id, 
        "🔍 Enter User ID:\n\nType the User ID to search:\nSend /cancel to cancel"
    )
    master_bot.register_next_step_handler(msg, search_user_payment)

def search_user_payment(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    if m.text and m.text.startswith('/cancel'):
        master_bot.send_message(m.chat.id, "❌ Cancelled.")
        return
    
    search_query = m.text.strip()
    
    db = load_db()
    user_payments = db.get("user_payment_settings", {})
    
    if search_query in user_payments:
        payment = user_payments[search_query]
        
        result_text = f"🔍 User Found!\n\n"
        result_text += f"👤 User ID: {search_query}\n"
        result_text += f"💳 Method: {payment.get('payment_method', 'N/A')}\n"
        result_text += f"📱 Number: {payment.get('payment_number', 'N/A')}\n"
        
        msg = master_bot.send_message(m.chat.id, result_text)
        if m.chat.id not in bot_reply_messages:
            bot_reply_messages[m.chat.id] = []
        bot_reply_messages[m.chat.id].append(msg.message_id)
    else:
        msg = master_bot.send_message(
            m.chat.id, 
            f"❌ No user found with ID: {search_query}"
        )
        if m.chat.id not in bot_reply_messages:
            bot_reply_messages[m.chat.id] = []
        bot_reply_messages[m.chat.id].append(msg.message_id)

# ================= ➕ [ ADD/REMOVE BOT ] =================

@master_bot.message_handler(func=lambda m: m.text == "➕ Add Bot")
def m_add_bot(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
    msg = master_bot.send_message(m.chat.id, "🤖 Send Bot Token:")
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
        msg = master_bot.send_message(m.chat.id, "✅ Bot added!")
        if m.chat.id not in bot_reply_messages:
            bot_reply_messages[m.chat.id] = []
        bot_reply_messages[m.chat.id].append(msg.message_id)
    else:
        master_bot.send_message(m.chat.id, "⚠️ Bot already exists!")

@master_bot.message_handler(func=lambda m: m.text == "❌ Remove Bot")
def m_remove_bot(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    delete_previous_bot_replies(m.chat.id)
    
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

# ================= 🔄 [ RESET ALL TYPES ] =================

@master_bot.message_handler(func=lambda m: m.text == "🔄 Reset All Types")
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
    
    msg = master_bot.send_message(m.chat.id, "✅ All types reset to ON!")
    if m.chat.id not in bot_reply_messages:
        bot_reply_messages[m.chat.id] = []
    bot_reply_messages[m.chat.id].append(msg.message_id)

# ================= 🔄 [ MAIN ] =================

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
    print("👑 ID RECEIVER SYSTEM v30.0")
    print("🎛️ UNIQUE OK COUNT")
    print("🎛️ EACH FILE SEPARATE IN PAYMENT LIST")
    print("🎛️ DATE FORMAT: DD-MM-YYYY")
    print("🎛️ PAYMENT METHOD ORDER: bKash → Nagad → Rocket → Binance")
    print("🎛️ MAIN MENU KEEPS")
    print("🎛️ USER MESSAGES KEPT")
    print("🎛️ ONLY BOT REPLIES DELETED")
    print("🎛️ FACEBOOK 0FD COOKIES FIXED")
    print("🎛️ COOKIES IN SEPARATE COLUMN")
    print("=" * 50)
    
    if not MASTER_ADMIN_TOKEN:
        print("❌ ERROR: MASTER_ADMIN_TOKEN not found in environment variables!")
        print("📌 Please set MASTER_ADMIN_TOKEN in Railway Variables")
    else:
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
