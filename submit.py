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
# 🔥 এখানে আপনার ইচ্ছামতো নাম ও আইকন পরিবর্তন করুন
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

# ================= 🔐 [ 3. FILE PROCESSING - COMPLETE AUTO DETECT ] =================

def auto_detect_columns(row):
    """
    Completely auto-detect columns - NO specific column names required!
    """
    user_val = ""
    pass_val = ""
    twofa_val = ""
    
    values = []
    for k, v in row.items():
        v_str = str(v).strip()
        if v_str and v_str != 'nan' and v_str != 'None':
            values.append(v_str)
    
    if len(values) == 0:
        return "", "", ""
    if len(values) == 1:
        return values[0], "", ""
    if len(values) == 2:
        return values[0], values[1], ""
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
                    elif not twofa_val and len(val) <= 6 and val.isdigit():
                        twofa_val = val
            if not twofa_val:
                for i, val in enumerate(values):
                    if i != email_idx and val != pass_val:
                        if len(val) <= 8 and (val.isdigit() or val.isalpha()):
                            twofa_val = val
        else:
            user_val = values[0]
            pass_val = values[1]
            if len(values) >= 3:
                twofa_val = values[2]
    
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
        print(f"📊 Total rows: {len(df)}")
        
        if len(df.columns) < 1:
            return None, 0, None, 0
        
        filtered_data = []
        empty_count = 0
        rows_with_2fa = 0
        
        for idx, row in df.iterrows():
            row_dict = row.to_dict()
            user_val, pass_val, twofa_val = auto_detect_columns(row_dict)
            
            if twofa_val:
                rows_with_2fa += 1
            
            if idx < 5:
                print(f"Row {idx}: user='{user_val}', pass='{pass_val}', 2fa='{str(twofa_val)[:30]}...'")
            
            filtered_data.append({
                "user": user_val,
                "pass": pass_val,
                "2fa": twofa_val
            })
        
        with open(file_path, "rb") as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        
        valid_rows = len([d for d in filtered_data if d['user'] or d['pass']])
        
        print(f"✅ Total rows: {len(filtered_data)}, Valid rows: {valid_rows}, Rows with 2fa: {rows_with_2fa}")
        
        return filtered_data, valid_rows, file_hash, empty_count
        
    except Exception as e:
        print(f"Process error: {e}")
        return None, 0, None, 0

def process_file_worker(bot, chat_id, file_type, file_path, original_name, payment_method, payment_number, username):
    try:
        db = load_db()
        
        filtered_data, valid_rows, file_hash, empty_rows = process_file_with_columns(file_path, original_name, file_type)
        
        if filtered_data is None or not filtered_data or valid_rows == 0:
            os.remove(file_path)
            bot.send_message(
                chat_id, 
                "❌ *NO DATA FOUND!*\n\n"
                "📌 Your file was empty or had no readable data.\n\n"
                "✅ Try uploading a file with at least 1 column of data.",
                parse_mode="Markdown"
            )
            return False
        
        file_db = db["files"][file_type]
        
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
                        caption=f"⚠️ *DUPLICATE DATA FOUND!*\n\n📊 {len(global_duplicate_rows)} rows already exist in database.\n\n✅ Only truly unique rows were saved."
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
                f"📁 File: `{original_name}`\n"
                f"⚠️ All rows already exist in database.\n\n"
                f"📊 {len(global_duplicate_rows)} duplicate rows found.",
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
                        caption=f"⚠️ *DUPLICATE ROWS IN YOUR FILE!*\n\n📁 File: `{original_name}`\n📊 {len(duplicate_rows)} duplicate rows found inside your file.\n\n✅ Only unique rows were processed further."
                    )
                os.remove(dup_file_path)
            except:
                pass
        
        # Get current date for filename
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
            "duplicate_rows_count": len(duplicate_rows),
            "global_duplicate_count": len(global_duplicate_rows),
            "received_date": current_date
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
            "received_date": current_date
        }
        
        save_db(db)
        
        # Save backup with date in filename
        backup_filename = f"{file_type}_{current_date}_{original_name}"
        backup_path = os.path.join("backup", backup_filename)
        with open(file_path, "rb") as src, open(backup_path, "wb") as dst:
            dst.write(src.read())
        
        warning_msg = ""
        if duplicate_rows:
            warning_msg += f"\n⚠️ {len(duplicate_rows)} duplicate rows removed from your file!"
        if global_duplicate_rows:
            warning_msg += f"\n⚠️ {len(global_duplicate_rows)} rows already existed in database!"
        
        result_msg = (
            f"✅ *FILE PROCESSED!*\n\n"
            f"📁 *File:* `{original_name}`\n"
            f"📂 *Type:* `{get_type_display_name(file_type)}`\n"
            f"💳 *Payment:* {payment_method} - `{payment_number}`\n"
            f"📅 *Received:* `{current_date}`\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 *Valid rows:* `{valid_rows}`\n"
            f"{warning_msg}\n"
            f"✨ *Status:* Successfully received"
        )
        
        bot.send_message(chat_id, result_msg, parse_mode="Markdown")
        
        # Send to admin with date in filename
        for admin_id in ADMIN_IDS:
            try:
                master_bot.send_message(
                    admin_id, 
                    f"📢 *NEW FILE RECEIVED!*\n"
                    f"👤 {username}\n"
                    f"📂 {get_type_display_name(file_type)}\n"
                    f"📊 {valid_rows} unique rows\n"
                    f"💳 {payment_method} - {payment_number}\n"
                    f"📅 {current_date}",
                    parse_mode="Markdown"
                )
            except:
                pass
        
        return True
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ *ERROR!*\n\n{str(e)}", parse_mode="Markdown")
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
            f"🔴 {get_type_display_name('ig_cookies')} (Closed)", 
            callback_data="type_disabled_ig_cookies"
        ))
    
    if type_status["ig_2fa"]:
        kb.add(types.InlineKeyboardButton(
            f"{get_type_icon('ig_2fa')} {get_type_display_name('ig_2fa')}", 
            callback_data="type_ig_2fa"
        ))
    else:
        kb.add(types.InlineKeyboardButton(
            f"🔴 {get_type_display_name('ig_2fa')} (Closed)", 
            callback_data="type_disabled_ig_2fa"
        ))
    
    if type_status["fb_0fd_2fa"]:
        kb.add(types.InlineKeyboardButton(
            f"{get_type_icon('fb_0fd_2fa')} {get_type_display_name('fb_0fd_2fa')}", 
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
                payment_info = f"\n\n💳 *Current Payment:*\n{user_payment.get('payment_method', 'N/A')} - `{user_payment.get('payment_number', 'N/A')}`"
            
            bot.send_message(
                m.chat.id,
                f"✨ *ID RECEIVER BOT* ✨\n\n"
                f"👋 *Hello {m.from_user.first_name}!*{payment_info}\n\n"
                f"📂 *Supported:* Any file format\n"
                f"📌 *No specific columns needed!*\n"
                f"   • Auto-detects user, pass, 2fa\n"
                f"💳 *Payment:* bKash, Nagad, Rocket, Binance\n"
                f"🔄 *Auto duplicate remove*\n\n"
                f"📌 *Click below to start*",
                parse_mode="Markdown",
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
                    "💰 *Change Payment Method*\n\n"
                    "Select your new payment method:",
                    parse_mode="Markdown",
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
                    f"✅ *{method_name} Selected*\n\n"
                    f"📝 Send your new {method_name} number:",
                    parse_mode="Markdown"
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
                    "❌ *Payment change cancelled*",
                    parse_mode="Markdown",
                    reply_markup=kb
                )
            
            elif c.data == "submit_file":
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
                        f"✅ *Auto Payment Selected*\n\n"
                        f"💳 {user_payment['payment_method']} - `{user_payment['payment_number']}`\n\n"
                        f"📎 *Send your file now*\n\n"
                        f"📌 Any file format accepted\n"
                        f"🔄 Auto-detects columns",
                        parse_mode="Markdown"
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
                    f"✅ *{method_name} Selected*\n\n📝 Send your {method_name} number (you won't need to enter this again):",
                    parse_mode="Markdown"
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
                    "❌ *Cancelled*\n\nClick below to start over:",
                    parse_mode="Markdown",
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
                f"✅ *Payment Updated!*\n\n"
                f"💳 {new_method} - `{new_number}`\n\n"
                f"Your payment method has been saved.",
                parse_mode="Markdown",
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
                f"✅ *Payment saved!*\n\n"
                f"💳 {user_sessions[user_id]['payment_method']} - `{payment_number}`\n"
                f"🔄 You won't need to enter this again.\n\n"
                f"📎 *Send your file now*",
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
            
            # Get current date for filename
            current_date = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            file_info = bot.get_file(m.document.file_id)
            save_name = f"{user_id}_{current_date}_{m.document.file_name}"
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
        f"🟢 {get_type_display_name('ig_cookies')}: {'ON' if type_status['ig_cookies'] else 'OFF'}\n"
        f"🟢 {get_type_display_name('ig_2fa')}: {'ON' if type_status['ig_2fa'] else 'OFF'}\n"
        f"🟢 {get_type_display_name('fb_0fd_2fa')}: {'ON' if type_status['fb_0fd_2fa'] else 'OFF'}\n\n"
        f"📌 Select an option below",
        parse_mode="Markdown",
        reply_markup=kb
    )

@master_bot.message_handler(func=lambda m: m.text == "⚙️ More Options")
def m_more_options(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.row("➕ Add Bot", "❌ Remove Bot")
    kb.row("🔄 Reset All Types", "🗑 Clear Data")
    kb.row("💳 User Payments", "🔍 Search User")
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
        f"🟢 {get_type_display_name('ig_cookies')}: {'ON' if type_status['ig_cookies'] else 'OFF'}\n"
        f"🟢 {get_type_display_name('ig_2fa')}: {'ON' if type_status['ig_2fa'] else 'OFF'}\n"
        f"🟢 {get_type_display_name('fb_0fd_2fa')}: {'ON' if type_status['fb_0fd_2fa'] else 'OFF'}\n\n"
        f"📌 Select an option below",
        parse_mode="Markdown",
        reply_markup=kb
    )

# ================= 📢 [ BROADCAST - COMPLETE ] =================

@master_bot.message_handler(func=lambda m: m.text == "📢 Broadcast")
def m_broadcast(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    user_ids = load_user_ids()
    if not user_ids:
        master_bot.send_message(m.chat.id, "❌ No users found! Users need to start the bot first.", parse_mode="Markdown")
        return
    
    if not active_bots:
        kb = types.InlineKeyboardMarkup(row_width=1)
        kb.add(types.InlineKeyboardButton("➕ Add Bot", callback_data="goto_add_bot_from_broadcast"))
        master_bot.send_message(
            m.chat.id,
            "❌ *NO ACTIVE USER BOTS!*\n\nPlease add a bot first:\n⚙️ More Options → ➕ Add Bot",
            parse_mode="Markdown",
            reply_markup=kb
        )
        return
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("📝 Send Message", callback_data="broadcast_text"),
        types.InlineKeyboardButton("🔙 Back", callback_data="broadcast_back")
    )
    
    master_bot.send_message(
        m.chat.id,
        f"📢 *BROADCAST*\n\n🤖 Active Bots: {len(active_bots)}\n👥 Total Users: {len(user_ids)}\n\n📌 Supports: Bold, Italic, Underline, Strikethrough, Links, Emojis, Code, Multiple lines\n\nClick below to start:",
        parse_mode="Markdown",
        reply_markup=kb
    )

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
        "🤖 *Send Bot Token:*\n\nGet token from @BotFather\nSend /cancel to cancel:",
        parse_mode="Markdown"
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
            "📝 *Send your message*\n\n✅ Supports: Bold, Italic, Underline, Strikethrough, Links, Emojis, Code, Multiple lines\n\nSend /cancel to cancel:",
            parse_mode="Markdown"
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
    
    final_message = f"""‼️ *ATTENTION* ‼️

{user_message}

Thanks by *MAX FUTURE* ✅"""
    
    user_ids = load_user_ids()
    
    if not user_ids:
        master_bot.send_message(m.chat.id, "❌ No users found!")
        return
    
    if not active_bots:
        master_bot.send_message(m.chat.id, "❌ *No active user bots!*", parse_mode="Markdown")
        return
    
    total_users = len(user_ids)
    status_msg = master_bot.send_message(m.chat.id, f"⏳ *Sending to {total_users} users...*", parse_mode="Markdown")
    
    success = 0
    fail = 0
    failed_users = []
    bot_tokens = list(active_bots)
    
    for idx, user_id in enumerate(user_ids):
        sent = False
        for bot_token in bot_tokens:
            try:
                bot = telebot.TeleBot(bot_token)
                bot.send_message(user_id, final_message, parse_mode="Markdown", disable_web_page_preview=False)
                success += 1
                sent = True
                break
            except:
                continue
        
        if not sent:
            fail += 1
            failed_users.append(user_id)
        
        if (idx + 1) % 50 == 0 or (idx + 1) == total_users:
            try:
                master_bot.edit_message_text(
                    f"⏳ *Sending...*\n\n📤 Sent: {success}\n❌ Failed: {fail}\n📊 Progress: {idx + 1}/{total_users}",
                    chat_id=status_msg.chat.id,
                    message_id=status_msg.message_id,
                    parse_mode="Markdown"
                )
            except:
                pass
        
        time.sleep(0.03)
    
    try:
        master_bot.delete_message(m.chat.id, status_msg.message_id)
    except:
        pass
    
    result_msg = f"✅ *Broadcast Complete!*\n\n📤 Success: {success}\n❌ Failed: {fail}\n👥 Total users: {total_users}"
    
    if fail > 0:
        result_msg += f"\n\n⚠️ {fail} users didn't receive the message."
        if failed_users:
            result_msg += f"\n💡 Failed users: {failed_users[:10]}"
            if len(failed_users) > 10:
                result_msg += f" ... and {len(failed_users) - 10} more"
    
    master_bot.send_message(m.chat.id, result_msg, parse_mode="Markdown")


# ================= 💳 [ PAYMENT LIST SCANNER - TYPE CONTROL FREE ] =================

@master_bot.message_handler(func=lambda m: m.text == "💳 Payment List Scanner")
def m_payment_scanner(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"{get_type_icon('ig_cookies')} {get_type_display_name('ig_cookies')}", callback_data="scan_type_ig_cookies"),
        types.InlineKeyboardButton(f"{get_type_icon('ig_2fa')} {get_type_display_name('ig_2fa')}", callback_data="scan_type_ig_2fa"),
        types.InlineKeyboardButton(f"{get_type_icon('fb_0fd_2fa')} {get_type_display_name('fb_0fd_2fa')}", callback_data="scan_type_fb_0fd_2fa"),
        types.InlineKeyboardButton("📊 All Types", callback_data="scan_type_all"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="scan_type_cancel")
    )
    
    master_bot.send_message(
        m.chat.id,
        "📁 *Which type to scan?*\n\nSelect an option below:",
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
    
    if scan_type == "all":
        display_type = "ALL TYPES"
    else:
        display_type = get_type_display_name(scan_type)
    
    user_sessions[c.message.chat.id] = {"scan_type": scan_type}
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    master_bot.send_message(
        c.message.chat.id,
        f"✅ *{display_type} Selected*\n\n"
        f"📁 Now send your OK TXT file:\n\n"
        f"💡 Each line should contain one username/email\n"
        f"📌 Example:\n"
        f"   • john_doe\n"
        f"   • jane@email.com\n"
        f"   • user123\n\n"
        f"Send /cancel to cancel:",
        parse_mode="Markdown"
    )
    
    master_bot.register_next_step_handler_by_chat_id(c.message.chat.id, scan_ok_list_accurate)


def scan_ok_list_accurate(m):
    """100% Accurate OK List Scanner"""
    if m.from_user.id not in ADMIN_IDS:
        return
    
    session = user_sessions.get(m.chat.id, {})
    scan_type = session.get("scan_type", "all")
    user_sessions.pop(m.chat.id, None)
    
    if not m.document:
        master_bot.send_message(m.chat.id, "❌ Please send a TXT file!")
        return
    
    if not m.document.file_name.endswith('.txt'):
        master_bot.send_message(m.chat.id, "❌ Only TXT files are supported!")
        return
    
    try:
        master_bot.delete_message(m.chat.id, m.message_id)
    except:
        pass
    
    status_msg = master_bot.send_message(
        m.chat.id,
        "⏳ *Reading OK list file...*",
        parse_mode="Markdown"
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
            f"❌ *Failed to read file!*\n\nError: {str(e)}", 
            parse_mode="Markdown"
        )
        return
    
    if not ok_list:
        master_bot.send_message(m.chat.id, "❌ *No valid data found in TXT file!*", parse_mode="Markdown")
        return
    
    try:
        master_bot.edit_message_text(
            f"⏳ *Scanning {len(ok_list)} users...*\n\n"
            f"📂 Type: {get_type_display_name(scan_type) if scan_type != 'all' else 'ALL TYPES'}\n"
            f"🔍 Searching database...",
            chat_id=status_msg.chat.id,
            message_id=status_msg.message_id,
            parse_mode="Markdown"
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
    total_matches = 0
    
    for file_type in types_to_scan:
        files_data = db["files"].get(file_type, {})
        total_files_scanned += len(files_data)
        
        for file_hash, file_info in files_data.items():
            original_data = file_info.get("original_data", [])
            submitted_by = file_info.get("submitted_by", "Unknown")
            payment_method = file_info.get("payment_method", "Unknown")
            payment_number = file_info.get("payment_number", "Unknown")
            
            user_matches = {}
            
            for row in original_data:
                total_data_scanned += 1
                
                user_field = str(row.get("user", "")).strip().lower()
                pass_field = str(row.get("pass", "")).strip()
                twofa_field = str(row.get("2fa", "")).strip()
                
                if not user_field:
                    continue
                
                for ok_username in ok_list:
                    if ok_username and ok_username == user_field:
                        if submitted_by not in user_matches:
                            user_matches[submitted_by] = {
                                "submitted_by": submitted_by,
                                "payment_method": payment_method,
                                "payment_number": payment_number,
                                "file_type": file_type,
                                "matches": [],
                                "total_ok": 0
                            }
                        
                        user_matches[submitted_by]["matches"].append({
                            "user": user_field,
                            "pass": pass_field,
                            "2fa": twofa_field,
                            "ok_username": ok_username
                        })
                        user_matches[submitted_by]["total_ok"] += 1
                        total_matches += 1
    
    for submitted_by, data in user_matches.items():
        results[submitted_by] = {
            "total_ok": data["total_ok"],
            "submitted_by": data["submitted_by"],
            "payment_method": data["payment_method"],
            "payment_number": data["payment_number"],
            "file_type": data["file_type"],
            "matches": data["matches"]
        }
    
    global current_ok_data
    current_ok_data = {
        "total_ok": total_matches,
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
        master_bot.send_message(
            m.chat.id,
            f"❌ *NO MATCHES FOUND!*\n\n"
            f"📊 OK List: {len(ok_list)} users\n"
            f"📁 Files Scanned: {total_files_scanned}\n"
            f"📊 Data Scanned: {total_data_scanned}\n"
            f"✅ Matches Found: 0",
            parse_mode="Markdown"
        )
        return
    
    display_type = get_type_display_name(scan_type) if scan_type != 'all' else "ALL TYPES"
    
    report_data = []
    for submitted_by, data in results.items():
        report_data.append({
            "Submitted By": submitted_by,
            "Payment Method": data["payment_method"],
            "Payment Number": data["payment_number"],
            "File Type": get_type_display_name(data["file_type"]),
            "Total OK": data["total_ok"],
            "Matched Users": ", ".join([m["user"] for m in data["matches"]][:10]) + ("..." if len(data["matches"]) > 10 else "")
        })
    
    current_date = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    df = pd.DataFrame(report_data)
    report_file = f"reports/scan_report_{current_date}_{m.chat.id}.xlsx"
    try:
        df.to_excel(report_file, index=False)
    except:
        report_file = f"reports/scan_report_{current_date}_{m.chat.id}.csv"
        df.to_csv(report_file, index=False, encoding='utf-8-sig')
    
    bkash_count = len([x for x in report_data if x["Payment Method"] == "bKash"])
    nagad_count = len([x for x in report_data if x["Payment Method"] == "Nagad"])
    rocket_count = len([x for x in report_data if x["Payment Method"] == "Rocket"])
    binance_count = len([x for x in report_data if x["Payment Method"] == "Binance"])
    
    summary = f"✅ *SCAN COMPLETE!*\n\n"
    summary += f"📂 *Type:* {display_type}\n"
    summary += f"📊 *OK List:* {len(ok_list)} users\n"
    summary += f"📁 *Files Scanned:* {total_files_scanned}\n"
    summary += f"📊 *Total Data Scanned:* {total_data_scanned}\n"
    summary += f"━━━━━━━━━━━━━━━━━━━━\n"
    summary += f"✅ *Matched Submitters:* {len(results)}\n"
    summary += f"📈 *Total OK Count:* {total_matches}\n"
    summary += f"🕐 *Scan Time:* {current_ok_data['last_scan_time']}\n"
    summary += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    summary += f"💳 *Payment Breakdown:*\n"
    summary += f"🏦 bKash: {bkash_count} submitters\n"
    summary += f"🏧 Nagad: {nagad_count} submitters\n"
    summary += f"💳 Rocket: {rocket_count} submitters\n"
    summary += f"₿ Binance: {binance_count} submitters\n\n"
    summary += f"📥 *Downloading detailed report...*"
    
    master_bot.send_message(m.chat.id, summary, parse_mode="Markdown")
    
    with open(report_file, "rb") as f:
        master_bot.send_document(
            m.chat.id,
            f,
            caption=f"📊 SCAN REPORT\n"
                    f"📅 Date: {current_date}\n"
                    f"Type: {display_type}\n"
                    f"Total Matches: {total_matches}\n"
                    f"Matched Submitters: {len(results)}"
        )
    
    os.remove(report_file)
    
    top_submitters = sorted(results.items(), key=lambda x: x[1]["total_ok"], reverse=True)[:5]
    if top_submitters:
        top_msg = f"🏆 *TOP 5 SUBMITTERS*\n\n"
        for i, (name, data) in enumerate(top_submitters, 1):
            top_msg += f"{i}. {name} - {data['total_ok']} OK\n"
            top_msg += f"   💳 {data['payment_method']} - {data['payment_number']}\n"
        
        master_bot.send_message(m.chat.id, top_msg, parse_mode="Markdown")


# ================= 📥 [ PAYMENT LIST - TYPE WISE ] =================

@master_bot.message_handler(func=lambda m: m.text == "📥 Payment List")
def m_payment_list(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    db = load_db()
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"{get_type_icon('ig_cookies')} {get_type_display_name('ig_cookies')}", callback_data="paylist_ig_cookies"),
        types.InlineKeyboardButton(f"{get_type_icon('ig_2fa')} {get_type_display_name('ig_2fa')}", callback_data="paylist_ig_2fa"),
        types.InlineKeyboardButton(f"{get_type_icon('fb_0fd_2fa')} {get_type_display_name('fb_0fd_2fa')}", callback_data="paylist_fb_0fd_2fa"),
        types.InlineKeyboardButton("📊 All Types", callback_data="paylist_all"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="paylist_cancel")
    )
    
    scan_info = ""
    if current_ok_data.get("results"):
        scan_info = f"\n\n📊 *Last Scan:*\n✅ Total OK: {current_ok_data.get('total_ok', 0)}\n👥 Submitters: {current_ok_data.get('total_users', 0)}\n🕐 Scanned: {current_ok_data.get('last_scan_time', 'Never')}"
    
    master_bot.send_message(
        m.chat.id,
        f"📥 *PAYMENT LIST*\n\nSelect which type you want to see:{scan_info}",
        parse_mode="Markdown",
        reply_markup=kb
    )


@master_bot.callback_query_handler(func=lambda c: c.data.startswith("paylist_"))
def m_paylist_callback(c):
    if c.from_user.id not in ADMIN_IDS:
        master_bot.answer_callback_query(c.id, "❌ Unauthorized!")
        return
    
    if c.data == "paylist_cancel":
        try:
            master_bot.delete_message(c.message.chat.id, c.message.message_id)
        except:
            pass
        master_bot.send_message(c.message.chat.id, "❌ Cancelled.")
        return
    
    selected_type = c.data.replace("paylist_", "")
    
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
    
    generate_payment_list(c.message.chat.id, file_types, type_label)


def generate_payment_list(chat_id, file_types, type_label):
    """Generate payment list - type wise"""
    db = load_db()
    
    submitter_data = []
    
    for file_type in file_types:
        files_data = db["files"].get(file_type, {})
        
        for file_hash, file_info in files_data.items():
            submitted_by = file_info.get("submitted_by", "Unknown")
            payment_method = file_info.get("payment_method", "Unknown")
            payment_number = file_info.get("payment_number", "Unknown")
            total_rows = file_info.get("total_rows_in_file", 0)
            
            ok_count = 0
            if current_ok_data.get("results") and submitted_by in current_ok_data["results"]:
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
        master_bot.send_message(
            chat_id, 
            f"❌ *NO DATA FOUND!*\n\nType: {type_label}", 
            parse_mode="Markdown"
        )
        return
    
    status_msg = master_bot.send_message(
        chat_id, 
        f"⏳ *Generating {type_label} Payment List...*",
        parse_mode="Markdown"
    )
    
    grouped_data = {}
    for item in submitter_data:
        key = f"{item['submitted_by']}_{item['payment']}_{item['number']}"
        if key not in grouped_data:
            grouped_data[key] = {
                "submitted_by": item["submitted_by"],
                "payment": item["payment"],
                "number": item["number"],
                "total_files": 0,
                "total_rows": 0,
                "ok": 0
            }
        grouped_data[key]["total_files"] += item["total_files"]
        grouped_data[key]["total_rows"] += item["total_rows"]
        grouped_data[key]["ok"] += item["ok"]
    
    final_data = []
    for key, data in grouped_data.items():
        final_data.append({
            "submitted_by": data["submitted_by"],
            "payment": data["payment"],
            "number": data["number"],
            "total_files": data["total_files"],
            "total_rows": data["total_rows"],
            "ok": data["ok"]
        })
    
    payment_order = {"bKash": 1, "Nagad": 2, "Rocket": 3, "Binance": 4}
    final_data.sort(key=lambda x: (payment_order.get(x["payment"], 999), -x["total_rows"]))
    
    df = pd.DataFrame(final_data)
    
    current_date = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    data_file = f"reports/payment_list_{current_date}_{chat_id}.xlsx"
    try:
        df.to_excel(data_file, index=False)
    except:
        data_file = f"reports/payment_list_{current_date}_{chat_id}.csv"
        df.to_csv(data_file, index=False, encoding='utf-8-sig')
    
    total_submitters = len(final_data)
    total_files = sum(d["total_files"] for d in final_data)
    total_rows = sum(d["total_rows"] for d in final_data)
    total_ok = sum(d["ok"] for d in final_data)
    
    bkash_count = len([x for x in final_data if x["payment"] == "bKash"])
    nagad_count = len([x for x in final_data if x["payment"] == "Nagad"])
    rocket_count = len([x for x in final_data if x["payment"] == "Rocket"])
    binance_count = len([x for x in final_data if x["payment"] == "Binance"])
    
    try:
        master_bot.delete_message(chat_id, status_msg.message_id)
    except:
        pass
    
    summary = f"✅ *PAYMENT LIST REPORT*\n\n"
    summary += f"📂 *Type:* {type_label}\n"
    summary += f"📅 *Generated:* {current_date}\n"
    summary += f"━━━━━━━━━━━━━━━━━━━━\n"
    summary += f"👥 Total Submitters: {total_submitters}\n"
    summary += f"📁 Total Files: {total_files}\n"
    summary += f"📊 Total Rows: {total_rows}\n"
    summary += f"✅ Total OK: {total_ok}\n"
    summary += f"━━━━━━━━━━━━━━━━━━━━\n\n"
    summary += f"💳 *Payment Breakdown:*\n"
    summary += f"🏦 bKash: {bkash_count} users\n"
    summary += f"🏧 Nagad: {nagad_count} users\n"
    summary += f"💳 Rocket: {rocket_count} users\n"
    summary += f"₿ Binance: {binance_count} users\n\n"
    summary += f"📥 Downloading file..."
    
    master_bot.send_message(chat_id, summary, parse_mode="Markdown")
    
    with open(data_file, "rb") as f:
        master_bot.send_document(
            chat_id, 
            f, 
            caption=f"📊 {type_label} PAYMENT LIST\n"
                    f"📅 Date: {current_date}\n"
                    f"Total OK: {total_ok}\n\n"
                    f"Columns: submitted_by, payment, number, total_files, total_rows, ok"
        )
    
    os.remove(data_file)


# ================= 🎛️ [ TYPE CONTROL ] =================

@master_bot.message_handler(func=lambda m: m.text == "🎛️ Type Control")
def m_type_control(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(f"{'🟢' if type_status['ig_cookies'] else '🔴'} {get_type_display_name('ig_cookies')}", callback_data="toggle_ig_cookies"),
        types.InlineKeyboardButton(f"{'🟢' if type_status['ig_2fa'] else '🔴'} {get_type_display_name('ig_2fa')}", callback_data="toggle_ig_2fa"),
        types.InlineKeyboardButton(f"{'🟢' if type_status['fb_0fd_2fa'] else '🔴'} {get_type_display_name('fb_0fd_2fa')}", callback_data="toggle_fb_0fd_2fa"),
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
    master_bot.answer_callback_query(c.id, f"{get_type_display_name(type_name)} is now {status_text}")
    
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton(f"{'🟢' if type_status['ig_cookies'] else '🔴'} {get_type_display_name('ig_cookies')}", callback_data="toggle_ig_cookies"),
        types.InlineKeyboardButton(f"{'🟢' if type_status['ig_2fa'] else '🔴'} {get_type_display_name('ig_2fa')}", callback_data="toggle_ig_2fa"),
        types.InlineKeyboardButton(f"{'🟢' if type_status['fb_0fd_2fa'] else '🔴'} {get_type_display_name('fb_0fd_2fa')}", callback_data="toggle_fb_0fd_2fa"),
        types.InlineKeyboardButton("🔙 Back", callback_data="back_to_menu")
    )
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    master_bot.send_message(
        c.message.chat.id,
        f"🎛️ *TYPE CONTROL PANEL*\n\n"
        f"🟢 {get_type_display_name('ig_cookies')}: {'ON' if type_status['ig_cookies'] else 'OFF'}\n"
        f"🟢 {get_type_display_name('ig_2fa')}: {'ON' if type_status['ig_2fa'] else 'OFF'}\n"
        f"🟢 {get_type_display_name('fb_0fd_2fa')}: {'ON' if type_status['fb_0fd_2fa'] else 'OFF'}\n\n"
        f"Click to toggle:",
        parse_mode="Markdown",
        reply_markup=kb
    )

# ================= 📊 [ TOTAL STATS ] =================

@master_bot.message_handler(func=lambda m: m.text == "📊 Total Stats")
def m_stats(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
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
        f"📊 *TOTAL STATISTICS*\n"
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🤖 *Bots:* `{bot_count}`\n"
        f"👥 *Users:* `{len(user_ids)}`\n"
        f"💳 *Payment Users:* `{user_payment_count}`\n"
        f"📊 *Global Records:* `{global_unique_count}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📂 *TYPE WISE STATISTICS*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    for file_type, stats in type_stats.items():
        display_name = get_type_display_name(file_type)
        icon = get_type_icon(file_type)
        status_icon = "🟢" if stats["status"] else "🔴"
        
        stats_msg += (
            f"{icon} {display_name}\n"
            f"  {status_icon} Status: {'ON' if stats['status'] else 'OFF'}\n"
            f"  📁 Files: `{stats['files']}`\n"
            f"  📊 Rows: `{stats['rows']}`\n"
            f"  📋 Unique: `{stats['unique']}`\n\n"
        )
    
    stats_msg += (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📈 *SUMMARY*\n"
        f"📁 Total Files: `{total_files_all}`\n"
        f"📊 Total Rows: `{total_rows_all}`\n"
        f"🔄 Active Types: `{sum(1 for s in type_status.values() if s)}/{len(type_status)}`"
    )
    
    master_bot.send_message(m.chat.id, stats_msg, parse_mode="Markdown")


# ================= 📁 [ DOWNLOAD BY TYPE ] =================

@master_bot.message_handler(func=lambda m: m.text == "📁 Download by Type")
def m_download_by_type(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"{get_type_icon('ig_cookies')} {get_type_display_name('ig_cookies')}", callback_data="dltype_ig_cookies"),
        types.InlineKeyboardButton(f"{get_type_icon('ig_2fa')} {get_type_display_name('ig_2fa')}", callback_data="dltype_ig_2fa"),
        types.InlineKeyboardButton(f"{get_type_icon('fb_0fd_2fa')} {get_type_display_name('fb_0fd_2fa')}", callback_data="dltype_fb_0fd_2fa"),
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
        f"⏳ Generating {display_type} data...",
        parse_mode="Markdown"
    )
    
    current_date = datetime.now().strftime("%Y%m%d_%H%M%S")
    data_file = f"reports/user_data_{file_type}_{current_date}_{c.message.chat.id}.csv"
    
    total_rows = 0
    rows_with_2fa = 0
    
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
                        rows_with_2fa += 1
                    
                    writer.writerow([
                        user_val if user_val else "",
                        pass_val if pass_val else "",
                        twofa_val if twofa_val else "",
                        item.get("submitted_by", ""),
                        item.get("submitted_at", ""),
                        received_date
                    ])
            else:
                writer.writerow([
                    item.get("user", ""),
                    item.get("pass", ""),
                    item.get("2fa", ""),
                    item.get("submitted_by", ""),
                    item.get("submitted_at", ""),
                    item.get("received_date", "Unknown")
                ])
    
    try:
        master_bot.delete_message(c.message.chat.id, status_msg.message_id)
    except:
        pass
    
    with open(data_file, "rb") as f:
        master_bot.send_document(
            c.message.chat.id, 
            f, 
            caption=f"📊 {display_type}\n"
                    f"📅 Date: {current_date}\n"
                    f"📋 All user data\n\n"
                    f"Total rows: {total_rows}\n"
                    f"Rows with 2FA: {rows_with_2fa}"
        )
    
    os.remove(data_file)


# ================= 🗑 [ CLEAR DATA - TYPE WISE ] =================

@master_bot.message_handler(func=lambda m: m.text == "🗑 Clear Data")
def m_clear_data(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"{get_type_icon('ig_cookies')} {get_type_display_name('ig_cookies')}", callback_data="clear_ig_cookies"),
        types.InlineKeyboardButton(f"{get_type_icon('ig_2fa')} {get_type_display_name('ig_2fa')}", callback_data="clear_ig_2fa"),
        types.InlineKeyboardButton(f"{get_type_icon('fb_0fd_2fa')} {get_type_display_name('fb_0fd_2fa')}", callback_data="clear_fb_0fd_2fa"),
        types.InlineKeyboardButton("🗑 Clear All", callback_data="clear_all"),
        types.InlineKeyboardButton("❌ Cancel", callback_data="clear_cancel")
    )
    
    master_bot.send_message(
        m.chat.id,
        "🗑 *CLEAR DATA*\n\nSelect which type to clear:",
        parse_mode="Markdown",
        reply_markup=kb
    )

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
        master_bot.send_message(c.message.chat.id, "❌ Cancelled.")
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
        
        master_bot.send_message(c.message.chat.id, "✅ *ALL DATA CLEARED!*", parse_mode="Markdown")
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
                        key = f"{row.get('user', '')}_{row.get('pass', '')}_{row.get('2fa', '')}".lower()
                        if key:
                            all_keys.add(key)
    db["global_unique_keys"] = list(all_keys)
    
    save_db(db)
    
    try:
        master_bot.delete_message(c.message.chat.id, c.message.message_id)
    except:
        pass
    
    master_bot.send_message(
        c.message.chat.id, 
        f"✅ *{display_name} DATA CLEARED!*", 
        parse_mode="Markdown"
    )


# ================= 💳 [ USER PAYMENTS ] =================

@master_bot.message_handler(func=lambda m: m.text == "💳 User Payments")
def m_user_payments(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    db = load_db()
    user_payments = db.get("user_payment_settings", {})
    
    if not user_payments:
        master_bot.send_message(
            m.chat.id, 
            "❌ *No user payment data found!*", 
            parse_mode="Markdown"
        )
        return
    
    payment_data = []
    for user_id, payment_info in user_payments.items():
        payment_data.append({
            "User ID": user_id,
            "Method": payment_info.get("payment_method", "N/A"),
            "Number": payment_info.get("payment_number", "N/A")
        })
    
    current_date = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    df = pd.DataFrame(payment_data)
    data_file = f"reports/user_payments_{current_date}_{m.chat.id}.xlsx"
    try:
        df.to_excel(data_file, index=False)
    except:
        data_file = f"reports/user_payments_{current_date}_{m.chat.id}.csv"
        df.to_csv(data_file, index=False, encoding='utf-8-sig')
    
    bkash = len([p for p in payment_data if p["Method"] == "bKash"])
    nagad = len([p for p in payment_data if p["Method"] == "Nagad"])
    rocket = len([p for p in payment_data if p["Method"] == "Rocket"])
    binance = len([p for p in payment_data if p["Method"] == "Binance"])
    unknown = len([p for p in payment_data if p["Method"] == "N/A"])
    
    summary = f"💳 *USER PAYMENT REPORT*\n\n"
    summary += f"📅 Date: {current_date}\n"
    summary += f"👥 Total Users: {len(payment_data)}\n"
    summary += f"━━━━━━━━━━━━━━━━━━━━\n"
    summary += f"🏦 bKash: {bkash} users\n"
    summary += f"🏧 Nagad: {nagad} users\n"
    summary += f"💳 Rocket: {rocket} users\n"
    summary += f"₿ Binance: {binance} users\n"
    summary += f"❓ Unknown: {unknown} users\n\n"
    summary += f"📥 Downloading file..."
    
    master_bot.send_message(m.chat.id, summary, parse_mode="Markdown")
    
    with open(data_file, "rb") as f:
        master_bot.send_document(
            m.chat.id, 
            f, 
            caption=f"📊 USER PAYMENT LIST\n"
                    f"📅 Date: {current_date}\n\n"
                    f"User ID, Payment Method, Payment Number"
        )
    
    os.remove(data_file)


# ================= 🔍 [ SEARCH USER ] =================

@master_bot.message_handler(func=lambda m: m.text == "🔍 Search User")
def m_search_user(m):
    if m.from_user.id not in ADMIN_IDS:
        return
    
    msg = master_bot.send_message(
        m.chat.id, 
        "🔍 *Enter User ID:*\n\n"
        "Type the User ID to search:\n"
        "Send /cancel to cancel",
        parse_mode="Markdown"
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
        
        result_text = f"🔍 *User Found!*\n\n"
        result_text += f"👤 *User ID:* `{search_query}`\n"
        result_text += f"💳 *Method:* {payment.get('payment_method', 'N/A')}\n"
        result_text += f"📱 *Number:* `{payment.get('payment_number', 'N/A')}`\n"
        
        master_bot.send_message(m.chat.id, result_text, parse_mode="Markdown")
    else:
        master_bot.send_message(
            m.chat.id, 
            f"❌ *No user found with ID:* `{search_query}`",
            parse_mode="Markdown"
        )


# ================= ➕ [ ADD/REMOVE BOT ] =================

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


# ================= 🔄 [ RESET ALL TYPES ] =================

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


# ================= 🔄 [ BACK TO MENU CALLBACK ] =================

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
        f"🟢 {get_type_display_name('ig_cookies')}: {'ON' if type_status['ig_cookies'] else 'OFF'}\n"
        f"🟢 {get_type_display_name('ig_2fa')}: {'ON' if type_status['ig_2fa'] else 'OFF'}\n"
        f"🟢 {get_type_display_name('fb_0fd_2fa')}: {'ON' if type_status['fb_0fd_2fa'] else 'OFF'}\n\n"
        f"📌 Select an option below",
        parse_mode="Markdown",
        reply_markup=kb
    )


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
    print("👑 ID RECEIVER SYSTEM v21.0")
    print("🎛️ COMPLETE AUTO-DETECTION")
    print("🎛️ NO COLUMN NAMES REQUIRED")
    print("🎛️ AUTO PAYMENT SAVE")
    print("🎛️ TYPE-WISE CLEAR DATA")
    print("🎛️ CUSTOM TYPE NAMES")
    print("🎛️ FULL BROADCAST SUPPORT")
    print("🎛️ DATE ADDED TO FILES")
    print("🎛️ 100% ACCURATE SCANNER")
    print("🎛️ TYPE CONTROL FREE PAYMENT LIST")
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
