"""
Cipher — Telegram intake bot (@therealinsidercipherbot)

Purpose: walk a user through a short, structured set of questions about a
crypto/blockchain issue they're experiencing, so responses can be reviewed
and analyzed afterward.

Setup:
    pip install -r requirements.txt
    export CIPHER_BOT_TOKEN="your-bot-token-from-BotFather"
    python cipher_bot.py

Notes:
    - Get a token from @BotFather on Telegram, set the bot's username to
      therealinsidercipherbot when prompted, and paste the token into the
      env var above (never hardcode it in the script).
    - Optionally set ADMIN_CHAT_ID to your own Telegram chat id to get a
      copy of every completed submission forwarded to you.
    - Submissions are appended to submissions.jsonl in this folder as
      simple, auditable line-delimited JSON — swap in a database later if
      you outgrow a flat file.
"""

import json
import logging
import os
from datetime import datetime, timezone

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("cipher_bot")

# ── Branding ──────────────────────────────────────────────────────────
BOT_DISPLAY_NAME = "Cipher"
BRAND_TAGLINE = "Blockchain issue intake, structured for fast analysis."

# ── Conversation stages ──────────────────────────────────────────────
ISSUE_TYPE, CHAIN, DESCRIPTION, URGENCY, CONTACT_OK, CONFIRM = range(6)
TOTAL_STEPS = 5

ISSUE_TYPE_OPTIONS = [
    ("wallet", "🔑 Wallet / private key"),
    ("contract", "📜 Smart contract"),
    ("exchange", "🏦 Exchange / custodial"),
    ("suspicious_tx", "🚨 Suspicious transaction"),
    ("other", "❓ Other"),
]

URGENCY_OPTIONS = [
    ("low", "🟢 Low"),
    ("medium", "🟡 Medium"),
    ("high", "🟠 High"),
    ("critical", "🔴 Critical — funds at risk"),
]

YES_NO_OPTIONS = [("yes", "✅ Yes"), ("no", "🚫 No")]
CONFIRM_OPTIONS = [("submit", "✅ Submit"), ("restart", "🔄 Start over")]

SUBMISSIONS_FILE = os.path.join(os.path.dirname(__file__), "submissions.jsonl")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  # optional, as a string


def _keyboard(options: list[tuple[str, str]], row_width: int = 2) -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(label, callback_data=key) for key, label in options]
    rows = [buttons[i : i + row_width] for i in range(0, len(buttons), row_width)]
    return InlineKeyboardMarkup(rows)


def _step_header(n: int) -> str:
    return f"*Step {n} of {TOTAL_STEPS}*"


def _label_for(options: list[tuple[str, str]], key: str) -> str:
    return dict(options).get(key, key)


# ── Handlers ─────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        f"*{BOT_DISPLAY_NAME}*\n_{BRAND_TAGLINE}_\n\n"
        "I'll ask a handful of quick questions about the issue you're "
        "facing, then show you a summary to confirm before anything is "
        "logged for review.\n\n"
        "Send /cancel at any point to stop.\n\n"
        f"{_step_header(1)}\nWhat kind of issue is this?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_keyboard(ISSUE_TYPE_OPTIONS),
    )
    return ISSUE_TYPE


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        f"*{BOT_DISPLAY_NAME} — commands*\n\n"
        "/start — begin a new submission\n"
        "/cancel — abandon the current submission\n"
        "/help — show this message",
        parse_mode=ParseMode.MARKDOWN,
    )


async def issue_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["issue_type"] = query.data
    await query.edit_message_text(
        f"{_step_header(1)}\nWhat kind of issue is this?\n\n"
        f"➡️ {_label_for(ISSUE_TYPE_OPTIONS, query.data)}",
        parse_mode=ParseMode.MARKDOWN,
    )
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"{_step_header(2)}\nWhich chain or network is involved?\n"
        "_e.g. Bitcoin, Ethereum, Solana — or \"not sure\"_",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=ReplyKeyboardRemove(),
    )
    return CHAIN


async def chain(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["chain"] = update.message.text.strip()
    await update.message.reply_text(
        f"{_step_header(3)}\nDescribe what happened in a few sentences — "
        "include dates, amounts, or transaction/wallet addresses if you "
        "have them.",
        parse_mode=ParseMode.MARKDOWN,
    )
    return DESCRIPTION


async def description(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["description"] = update.message.text.strip()
    await update.message.reply_text(
        f"{_step_header(4)}\nHow urgent is this?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_keyboard(URGENCY_OPTIONS),
    )
    return URGENCY


async def urgency(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["urgency"] = query.data
    await query.edit_message_text(
        f"{_step_header(4)}\nHow urgent is this?\n\n"
        f"➡️ {_label_for(URGENCY_OPTIONS, query.data)}",
        parse_mode=ParseMode.MARKDOWN,
    )
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"{_step_header(5)}\nOK to follow up with you here on Telegram "
        "about this?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_keyboard(YES_NO_OPTIONS),
    )
    return CONTACT_OK


async def contact_ok(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    context.user_data["contact_ok"] = query.data
    await query.edit_message_text(
        f"{_step_header(5)}\nOK to follow up with you here on Telegram "
        f"about this?\n\n➡️ {_label_for(YES_NO_OPTIONS, query.data)}",
        parse_mode=ParseMode.MARKDOWN,
    )

    d = context.user_data
    summary = (
        "*Review your submission*\n\n"
        f"*Type:* {_label_for(ISSUE_TYPE_OPTIONS, d.get('issue_type'))}\n"
        f"*Chain:* {d.get('chain')}\n"
        f"*Urgency:* {_label_for(URGENCY_OPTIONS, d.get('urgency'))}\n"
        f"*Follow-up OK:* {_label_for(YES_NO_OPTIONS, d.get('contact_ok'))}\n"
        f"*Details:* {d.get('description')}\n\n"
        "Submit this for review, or start over?"
    )
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=summary,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_keyboard(CONFIRM_OPTIONS),
    )
    return CONFIRM


async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "restart":
        context.user_data.clear()
        await query.edit_message_text(
            "Starting over — send /start whenever you're ready.",
        )
        return ConversationHandler.END

    user = update.effective_user
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "telegram_user_id": user.id,
        "telegram_username": user.username,
        **context.user_data,
    }

    with open(SUBMISSIONS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    await query.edit_message_text(
        "✅ *Submitted.* Thanks — this has been logged for review.\n\n"
        "Send /start any time to submit another issue.",
        parse_mode=ParseMode.MARKDOWN,
    )

    if ADMIN_CHAT_ID:
        admin_summary = (
            f"📥 *New {BOT_DISPLAY_NAME} submission* from "
            f"@{user.username or user.id}\n"
            f"*Type:* {_label_for(ISSUE_TYPE_OPTIONS, record.get('issue_type'))}\n"
            f"*Chain:* {record.get('chain')}\n"
            f"*Urgency:* {_label_for(URGENCY_OPTIONS, record.get('urgency'))}\n"
            f"*Follow-up OK:* {_label_for(YES_NO_OPTIONS, record.get('contact_ok'))}\n"
            f"*Details:* {record.get('description')}"
        )
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=admin_summary,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            logger.exception("Failed to forward submission to admin chat")

    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "No problem, cancelled. Send /start whenever you're ready.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


def main() -> None:
    token = os.environ.get("CIPHER_BOT_TOKEN")
    if not token:
        raise SystemExit(
            "Set the CIPHER_BOT_TOKEN environment variable to your bot's "
            "token before running (get one from @BotFather)."
        )

    application = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ISSUE_TYPE: [CallbackQueryHandler(issue_type)],
            CHAIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, chain)],
            DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, description)],
            URGENCY: [CallbackQueryHandler(urgency)],
            CONTACT_OK: [CallbackQueryHandler(contact_ok)],
            CONFIRM: [CallbackQueryHandler(confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
