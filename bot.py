import sqlite3
import os
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
TOKEN = os.getenv("8536029458:AAFGvI9zZqvithELvT3FitVToplB5AALFqU")
BOT_USERNAME = "FREEDGB_EaRN_BOT"

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

conn.commit()

# =========================
# DATABASE FUNCTIONS
# =========================
def add_user_if_not_exists(user_id):
    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if cursor.fetchone() is None:
        cursor.execute("""
        INSERT INTO users (user_id,balance,referrals,wallet,invited_by,joined)
        VALUES (?,0,0,'Not set',NULL,0)
        """, (user_id,))
        conn.commit()

def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()

def save_wallet(user_id, wallet):
    cursor.execute("UPDATE users SET wallet=? WHERE user_id=?", (wallet,user_id))
    conn.commit()

def get_total_users():
    cursor.execute("SELECT COUNT(*) FROM users")
    return cursor.fetchone()[0]

def get_all_user_ids():
    cursor.execute("SELECT user_id FROM users")
    rows = cursor.fetchall()
    return [r[0] for r in rows]

# =========================
# MENUS
# =========================
def main_menu():
    keyboard = [
        ["👤 Account","🔗 Referral"],
        ["💳 Set Wallet","🎁 Redeem"],
        ["📊 Stats"]
    ]
    return ReplyKeyboardMarkup(keyboard,resize_keyboard=True)

def join_menu():
    keyboard = [
        [InlineKeyboardButton("Join Channel 1",url=CHANNEL_LINKS["@slbttt"])],
        [InlineKeyboardButton("Join Channel 2",url=CHANNEL_LINKS["@zxzzzcw"])],
        [InlineKeyboardButton("Join Proof Channel",url=CHANNEL_LINKS["@dgpaidproofs"])],
        [InlineKeyboardButton("✅ Joined",callback_data="check_join")]
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_menu():
    keyboard = [
        [InlineKeyboardButton("📢 Broadcast",callback_data="broadcast")]
    ]
    return InlineKeyboardMarkup(keyboard)

# =========================
# START
# =========================
async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    add_user_if_not_exists(user_id)

    await update.message.reply_text(
        "Welcome!\nJoin sponsor channels first.",
        reply_markup=join_menu()
    )

# =========================
# JOIN CHECK
# =========================
async def check_join(update:Update,context:ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.message.reply_text(
        "✅ Verification success!",
        reply_markup=main_menu()
    )

# =========================
# USER MENU
# =========================
async def menu(update:Update,context:ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id
    text = update.message.text

    add_user_if_not_exists(user_id)
    user = get_user(user_id)

    balance = user[1]
    referrals = user[2]
    wallet = user[3]

    if text == "👤 Account":
        await update.message.reply_text(
            f"Balance: {balance}\nReferrals: {referrals}\nWallet: {wallet}"
        )

    elif text == "🔗 Referral":
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        await update.message.reply_text(link)

    elif text == "💳 Set Wallet":
        waiting_for_wallet.add(user_id)
        await update.message.reply_text("Send your wallet address")

    elif user_id in waiting_for_wallet:
        save_wallet(user_id,text)
        waiting_for_wallet.remove(user_id)
        await update.message.reply_text("Wallet saved",reply_markup=main_menu())

    elif text == "📊 Stats":
        total = get_total_users()
        await update.message.reply_text(f"Total Users: {total}")

# =========================
# ADMIN PANEL
# =========================
async def admin(update:Update,context:ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Not authorized")
        return

    await update.message.reply_text(
        "Admin Panel",
        reply_markup=admin_menu()
    )

# =========================
# BROADCAST BUTTON
# =========================
async def admin_buttons(update:Update,context:ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    if query.data == "broadcast":
        waiting_for_broadcast.add(query.from_user.id)
        await query.message.reply_text(
            "Send message or photo to broadcast."
        )

# =========================
# BROADCAST
# =========================
async def broadcast(update:Update,context:ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    if user_id not in waiting_for_broadcast:
        return

    waiting_for_broadcast.remove(user_id)

    users = get_all_user_ids()

    for u in users:
        try:
            if update.message.text:
                await context.bot.send_message(u,update.message.text)

            elif update.message.photo:
                await context.bot.send_photo(
                    u,
                    update.message.photo[-1].file_id,
                    caption=update.message.caption
                )
        except:
            pass

    await update.message.reply_text("Broadcast finished")

# =========================
# MAIN
# =========================
def main():

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("admin",admin))

    app.add_handler(CallbackQueryHandler(check_join,pattern="check_join"))
    app.add_handler(CallbackQueryHandler(admin_buttons))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,menu))
    app.add_handler(MessageHandler((filters.TEXT|filters.PHOTO),broadcast))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
