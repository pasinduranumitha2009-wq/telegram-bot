import sqlite3
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# CONFIG
# =========================
TOKEN = "8536029458:AAFGvI9zZqvithELvT3FitVToplB5AALFqU"
BOT_USERNAME = "FREEDGB_EaRN_BOT"   # without @

ADMIN_ID = 7949290215
PROOF_CHANNEL = "@dgpaidproofs"

CHANNELS = ["@slbttt", "@zxzzzcw", "@dgpaidproofs"]
CHANNEL_LINKS = {
    "@slbttt": "https://t.me/slbttt",
    "@zxzzzcw": "https://t.me/zxzzzcw",
    "@dgpaidproofs": "https://t.me/dgpaidproofs",
}

REFERRAL_REWARD = 1
MIN_REDEEM = 10

waiting_for_wallet = set()
waiting_for_redeem = set()
waiting_for_broadcast = set()

# =========================
# DATABASE
# =========================
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    referrals INTEGER DEFAULT 0,
    wallet TEXT DEFAULT 'Not set',
    invited_by INTEGER DEFAULT NULL,
    joined INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS redeem_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    wallet TEXT NOT NULL,
    amount INTEGER NOT NULL,
    status TEXT DEFAULT 'pending'
)
""")

conn.commit()

# =========================
# DB HELPERS
# =========================
def add_user_if_not_exists(user_id: int) -> None:
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone() is None:
        cursor.execute("""
            INSERT INTO users (user_id, balance, referrals, wallet, invited_by, joined)
            VALUES (?, 0, 0, 'Not set', NULL, 0)
        """, (user_id,))
        conn.commit()

def get_user(user_id: int):
    cursor.execute("""
        SELECT user_id, balance, referrals, wallet, invited_by, joined
        FROM users WHERE user_id = ?
    """, (user_id,))
    return cursor.fetchone()

def set_joined(user_id: int, joined: int) -> None:
    cursor.execute("UPDATE users SET joined = ? WHERE user_id = ?", (joined, user_id))
    conn.commit()

def save_wallet(user_id: int, wallet: str) -> None:
    cursor.execute("UPDATE users SET wallet = ? WHERE user_id = ?", (wallet, user_id))
    conn.commit()

def add_referral(referrer_id: int) -> None:
    cursor.execute("""
        UPDATE users
        SET referrals = referrals + 1,
            balance = balance + ?
        WHERE user_id = ?
    """, (REFERRAL_REWARD, referrer_id))
    conn.commit()

def set_invited_by(user_id: int, referrer_id: int) -> None:
    cursor.execute("""
        UPDATE users
        SET invited_by = ?
        WHERE user_id = ? AND invited_by IS NULL
    """, (referrer_id, user_id))
    conn.commit()

def get_total_users() -> int:
    cursor.execute("SELECT COUNT(*) FROM users")
    return cursor.fetchone()[0]

def get_all_user_ids():
    cursor.execute("SELECT user_id FROM users")
    rows = cursor.fetchall()
    return [row[0] for row in rows]

def create_redeem_request(user_id: int, wallet: str, amount: int) -> int:
    cursor.execute("""
        INSERT INTO redeem_requests (user_id, wallet, amount, status)
        VALUES (?, ?, ?, 'pending')
    """, (user_id, wallet, amount))
    conn.commit()
    return cursor.lastrowid

def get_pending_requests():
    cursor.execute("""
        SELECT id, user_id, wallet, amount, status
        FROM redeem_requests
        WHERE status = 'pending'
        ORDER BY id ASC
    """)
    return cursor.fetchall()

def get_request_by_id(request_id: int):
    cursor.execute("""
        SELECT id, user_id, wallet, amount, status
        FROM redeem_requests
        WHERE id = ?
    """, (request_id,))
    return cursor.fetchone()

def mark_request_paid(request_id: int):
    cursor.execute("""
        UPDATE redeem_requests
        SET status = 'approved'
        WHERE id = ?
    """, (request_id,))
    conn.commit()

def mark_request_rejected(request_id: int):
    cursor.execute("""
        SELECT user_id, amount, status
        FROM redeem_requests
        WHERE id = ?
    """, (request_id,))
    row = cursor.fetchone()

    if not row:
        return False, None, None

    user_id, amount, status = row
    if status != "pending":
        return False, user_id, amount

    cursor.execute("""
        UPDATE redeem_requests
        SET status = 'rejected'
        WHERE id = ?
    """, (request_id,))
    cursor.execute("""
        UPDATE users
        SET balance = balance + ?
        WHERE user_id = ?
    """, (amount, user_id))
    conn.commit()
    return True, user_id, amount

# =========================
# UI
# =========================
def get_main_menu() -> ReplyKeyboardMarkup:
    keyboard = [
        ["👤 Account", "🔗 Referral"],
        ["💳 Set Wallet", "🎁 Redeem"],
        ["📊 Stats"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_join_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("Join Channel 1", url=CHANNEL_LINKS["@slbttt"])],
        [InlineKeyboardButton("Join Channel 2", url=CHANNEL_LINKS["@zxzzzcw"])],
        [InlineKeyboardButton("Join Proof Channel", url=CHANNEL_LINKS["@dgpaidproofs"])],
        [InlineKeyboardButton("✅ Joined", callback_data="check_join")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Pending Requests", callback_data="admin_requests")],
        [InlineKeyboardButton("📢 Broadcast Message", callback_data="admin_broadcast")]
    ])

def get_request_action_buttons(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{request_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{request_id}")
        ]
    ])

# =========================
# HELPERS
# =========================
async def send_proof_message(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    try:
        await context.bot.send_message(chat_id=PROOF_CHANNEL, text=text)
    except Exception as e:
        print("Proof channel send error:", e)

async def is_joined_all_channels(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    for channel in CHANNELS:
        member = await context.bot.get_chat_member(channel, user_id)
        if member.status not in ["member", "administrator", "creator"]:
            return False
    return True

# =========================
# USER COMMANDS
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    add_user_if_not_exists(user_id)

    if context.args:
        try:
            referrer_id = int(context.args[0])
            if referrer_id != user_id:
                add_user_if_not_exists(referrer_id)
                user = get_user(user_id)
                invited_by = user[4]
                if invited_by is None:
                    set_invited_by(user_id, referrer_id)
        except ValueError:
            pass

    await update.message.reply_text(
        "Welcome.\n\nPlease join all sponsor channels first, then press ✅ Joined.",
        reply_markup=get_join_keyboard(),
    )

async def check_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.from_user:
        return

    await query.answer()
    user_id = query.from_user.id
    add_user_if_not_exists(user_id)

    try:
        joined = await is_joined_all_channels(context, user_id)
    except Exception as e:
        print("Join check error:", e)
        await query.message.reply_text(
            "Error while checking channels.\nMake sure the bot is admin in all sponsor channels."
        )
        return

    if not joined:
        await query.message.reply_text(
            "You have not joined all channels yet.",
            reply_markup=get_join_keyboard(),
        )
        return

    user = get_user(user_id)
    already_joined = user[5]
    invited_by = user[4]

    if already_joined == 0:
        set_joined(user_id, 1)
        if invited_by is not None:
            add_referral(invited_by)
            try:
                await context.bot.send_message(
                    chat_id=invited_by,
                    text=(
                        f"🎉 New Referral Completed!\n\n"
                        f"User ID: {user_id}\n"
                        f"You received {REFERRAL_REWARD} point(s)."
                    )
                )
            except Exception as e:
                print("Inviter notify error:", e)

    await query.message.reply_text(
        "✅ Verification successful!\n\nYou joined all sponsor channels.\nWelcome to the main menu.",
        reply_markup=get_main_menu(),
    )

async def handle_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    user_id = update.effective_user.id
    text = update.message.text.strip() if update.message.text else ""
    add_user_if_not_exists(user_id)

    # =========================
    # ADMIN BROADCAST (TEXT / PHOTO)
    # =========================
    if user_id in waiting_for_broadcast:
        if user_id != ADMIN_ID:
            waiting_for_broadcast.discard(user_id)
            await update.message.reply_text("Not authorized.")
            return

        user_ids = get_all_user_ids()
        sent = 0
        failed = 0

        # Text broadcast
        if update.message.text:
            waiting_for_broadcast.discard(user_id)
            broadcast_text = update.message.text

            await update.message.reply_text("📢 Broadcasting text to all users...")

            for target_id in user_ids:
                try:
                    await context.bot.send_message(
                        chat_id=target_id,
                        text=broadcast_text
                    )
                    sent += 1
                except Exception as e:
                    print(f"Broadcast text failed for {target_id}: {e}")
                    failed += 1

            await update.message.reply_text(
                f"✅ Broadcast completed.\n\nSent: {sent}\nFailed: {failed}"
            )
            return

        # Photo broadcast
        elif update.message.photo:
            waiting_for_broadcast.discard(user_id)
            photo_file_id = update.message.photo[-1].file_id
            caption = update.message.caption if update.message.caption else ""

            await update.message.reply_text("📢 Broadcasting photo to all users...")

            for target_id in user_ids:
                try:
                    await context.bot.send_photo(
                        chat_id=target_id,
                        photo=photo_file_id,
                        caption=caption
                    )
                    sent += 1
                except Exception as e:
                    print(f"Broadcast photo failed for {target_id}: {e}")
                    failed += 1

            await update.message.reply_text(
                f"✅ Broadcast completed.\n\nSent: {sent}\nFailed: {failed}"
            )
            return

        else:
            await update.message.reply_text(
                "Please send text or photo with caption for broadcast."
            )
            return

    user = get_user(user_id)
    balance = user[1]
    referrals = user[2]
    wallet = user[3]
    joined = user[5]

    if joined == 0:
        await update.message.reply_text(
            "Please join all sponsor channels first.",
            reply_markup=get_join_keyboard(),
        )
        return

    if user_id in waiting_for_wallet:
        if wallet != "Not set":
            waiting_for_wallet.discard(user_id)
            await update.message.reply_text(
                f"You have already saved a wallet address.\n\nSaved wallet:\n{wallet}",
                reply_markup=get_main_menu(),
            )
            return

        if not text:
            await update.message.reply_text(
                "Send your wallet address as text.",
                reply_markup=get_main_menu(),
            )
            return

        save_wallet(user_id, text)
        waiting_for_wallet.remove(user_id)
        await update.message.reply_text(
            "✅ Wallet saved successfully.",
            reply_markup=get_main_menu(),
        )
        return

    if user_id in waiting_for_redeem:
        waiting_for_redeem.remove(user_id)

        if not text.isdigit():
            await update.message.reply_text(
                "Please send a valid number amount.",
                reply_markup=get_main_menu(),
            )
            return

        amount = int(text)

        if wallet == "Not set":
            await update.message.reply_text(
                "You must set your wallet first.",
                reply_markup=get_main_menu(),
            )
            return

        if amount < MIN_REDEEM:
            await update.message.reply_text(
                f"Minimum redeem amount is {MIN_REDEEM}.",
                reply_markup=get_main_menu(),
            )
            return

        if amount > balance:
            await update.message.reply_text(
                "Insufficient balance.",
                reply_markup=get_main_menu(),
            )
            return

        request_id = create_redeem_request(user_id, wallet, amount)

        cursor.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ?",
            (amount, user_id),
        )
        conn.commit()

        await update.message.reply_text(
            f"✅ Redeem request submitted.\nRequest ID: {request_id}\nAmount: {amount}\nWallet: {wallet}",
            reply_markup=get_main_menu(),
        )

        proof_text = (
            f"📥 New Redeem Request\n\n"
            f"Request ID: {request_id}\n"
            f"User ID: {user_id}\n"
            f"Amount: {amount}\n"
            f"Wallet: {wallet}\n"
            f"Status: Pending"
        )
        await send_proof_message(context, proof_text)
        return

    if text == "👤 Account":
        await update.message.reply_text(
            f"👤 Account Info\n\n"
            f"Balance: {balance}\n"
            f"Referrals: {referrals}\n"
            f"Wallet: {wallet}"
        )

    elif text == "🔗 Referral":
        ref_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        await update.message.reply_text(
            f"🔗 Your referral link:\n{ref_link}\n\n"
            f"Referrals: {referrals}\n"
            f"Reward per referral: {REFERRAL_REWARD}"
        )

    elif text == "💳 Set Wallet":
        if wallet != "Not set":
            await update.message.reply_text(
                f"You have already added a wallet address.\n\nSaved wallet:\n{wallet}"
            )
        else:
            waiting_for_wallet.add(user_id)
            await update.message.reply_text("Send your wallet address.")

    elif text == "🎁 Redeem":
        if wallet == "Not set":
            await update.message.reply_text("Set your wallet first.")
        else:
            await update.message.reply_text(
                f"Your balance: {balance}\nMinimum redeem: {MIN_REDEEM}\n\nSend amount to redeem."
            )
            waiting_for_redeem.add(user_id)

    elif text == "📊 Stats":
        total_users = get_total_users()
        await update.message.reply_text(
            f"📊 Stats\n\nTotal users: {total_users}\nReferral reward: {REFERRAL_REWARD}\nMinimum redeem: {MIN_REDEEM}"
        )

    else:
        await update.message.reply_text(
            "Please choose an option from the menu.",
            reply_markup=get_main_menu(),
        )

# =========================
# ADMIN
# =========================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("You are not authorized to use this command.")
        return

    await update.message.reply_text(
        "🛠 Admin Panel",
        reply_markup=get_admin_keyboard()
    )

async def admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.from_user:
        return

    if query.from_user.id != ADMIN_ID:
        await query.answer("Not authorized.", show_alert=True)
        return

    data = query.data
    await query.answer()

    if data == "admin_requests":
        requests = get_pending_requests()

        if not requests:
            await query.message.reply_text("No pending redeem requests.")
            return

        for req in requests:
            req_id, user_id, wallet, amount, status = req
            text = (
                f"📋 Redeem Request\n\n"
                f"ID: {req_id}\n"
                f"User ID: {user_id}\n"
                f"Wallet: {wallet}\n"
                f"Amount: {amount}\n"
                f"Status: {status}"
            )
            await query.message.reply_text(
                text,
                reply_markup=get_request_action_buttons(req_id)
            )

    elif data == "admin_broadcast":
        waiting_for_broadcast.add(query.from_user.id)
        await query.message.reply_text(
            "📢 Send the text or photo with caption you want to broadcast to all users."
        )

    elif data.startswith("approve_"):
        request_id = int(data.split("_")[1])
        req = get_request_by_id(request_id)

        if not req:
            await query.message.reply_text("Request not found.")
            return

        _, req_user_id, req_wallet, req_amount, req_status = req

        if req_status != "pending":
            await query.message.reply_text(f"Request is already {req_status}.")
            return

        mark_request_paid(request_id)

        await query.message.reply_text(f"✅ Request {request_id} approved.")

        try:
            await context.bot.send_message(
                chat_id=req_user_id,
                text=f"✅ Your redeem request #{request_id} has been approved."
            )
        except Exception as e:
            print("User notify approve error:", e)

        proof_text = (
            f"✅ Redeem Approved\n\n"
            f"Request ID: {request_id}\n"
            f"User ID: {req_user_id}\n"
            f"Amount: {req_amount}\n"
            f"Wallet: {req_wallet}\n"
            f"Status: Approved"
        )
        await send_proof_message(context, proof_text)

    elif data.startswith("reject_"):
        request_id = int(data.split("_")[1])
        req = get_request_by_id(request_id)

        if not req:
            await query.message.reply_text("Request not found.")
            return

        _, req_user_id, req_wallet, req_amount, req_status = req

        if req_status != "pending":
            await query.message.reply_text(f"Request is already {req_status}.")
            return

        success, user_id, amount = mark_request_rejected(request_id)

        if not success:
            await query.message.reply_text("Request not found or already processed.")
            return

        await query.message.reply_text(
            f"❌ Request {request_id} rejected.\n{amount} returned to user balance."
        )

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ Your redeem request #{request_id} was rejected. {amount} has been returned to your balance."
            )
        except Exception as e:
            print("User notify reject error:", e)

        proof_text = (
            f"❌ Redeem Rejected\n\n"
            f"Request ID: {request_id}\n"
            f"User ID: {req_user_id}\n"
            f"Amount: {req_amount}\n"
            f"Wallet: {req_wallet}\n"
            f"Status: Rejected"
        )
        await send_proof_message(context, proof_text)

# =========================
# MAIN
# =========================
def main() -> None:
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_panel))

    app.add_handler(CallbackQueryHandler(check_join, pattern="^check_join$"))
    app.add_handler(CallbackQueryHandler(
        admin_buttons,
        pattern="^(admin_requests|admin_broadcast|approve_\\d+|reject_\\d+)$"
    ))

    app.add_handler(
        MessageHandler((filters.TEXT | filters.PHOTO) & ~filters.COMMAND, handle_menu)
    )

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()