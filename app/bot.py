import asyncio
import logging
import os

from telegram import BotCommand, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.config import TELEGRAM_BOT_TOKEN, DEFAULT_RATES, VERSION
from app.gpt_client import ask_gpt
from app.html_builder import render_estimate, render_estimate_pdf
from app.prompt import build_system_prompt

logger = logging.getLogger(__name__)

WAITING_FOR_BRIEF, DIALOG, REFINE = range(3)


# ── helpers ──────────────────────────────────────────────

async def _keep_typing(chat):
    while True:
        await chat.send_action(ChatAction.TYPING)
        await asyncio.sleep(4)


def _get_rates(context: ContextTypes.DEFAULT_TYPE) -> dict[str, int]:
    return context.user_data.get("rates", DEFAULT_RATES)


def _format_questions(questions: list[str]) -> str:
    lines = [f"{i}. {q}" for i, q in enumerate(questions, 1)]
    return "\n".join(lines)


def _user_tag(update: Update) -> str:
    """Format user info for log lines."""
    u = update.effective_user
    name = u.full_name if u else "?"
    uid = u.id if u else "?"
    username = f"@{u.username}" if u and u.username else ""
    return f"user={uid} ({name} {username})".strip()


# ── commands ─────────────────────────────────────────────

HELP_TEXT = (
    "Как пользоваться:\n"
    "1. Отправь бриф — описание проекта\n"
    "2. Ответь на уточняющие вопросы\n"
    "3. Получи смету (HTML + PDF)\n"
    "4. Напиши правки — получишь обновлённую смету\n\n"
    "Команды:\n"
    "/new — новая смета (сброс диалога)\n"
    "/rates — текущие ставки по ролям\n"
    "/help — эта справка\n"
    "/cancel — отменить диалог\n\n"
    f"Версия: {VERSION}"
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("CMD /start | %s", _user_tag(update))
    context.user_data.clear()
    await update.message.reply_text(
        "Привет! Я SmartSmeta — бот для генерации IT-смет.\n\n"
        + HELP_TEXT
        + "\n\nОтправь бриф, чтобы начать."
    )
    return WAITING_FOR_BRIEF


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("CMD /help | %s", _user_tag(update))
    await update.message.reply_text(HELP_TEXT)


async def new(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("CMD /new | %s", _user_tag(update))
    context.user_data.pop("response_id", None)
    await update.message.reply_text(
        "Начинаем заново. Отправь бриф нового проекта."
    )
    return WAITING_FOR_BRIEF


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("CMD /cancel | %s", _user_tag(update))
    context.user_data.pop("response_id", None)
    await update.message.reply_text(
        "Диалог отменён. Отправь /new чтобы начать заново."
    )
    return ConversationHandler.END


async def rates_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("CMD /rates | %s", _user_tag(update))
    rates = _get_rates(context)
    lines = [f"  {role}: {rate} руб/ч" for role, rate in rates.items()]
    await update.message.reply_text(
        "Текущие ставки:\n" + "\n".join(lines)
    )


# ── conversation handlers ────────────────────────────────

async def handle_brief(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User sent the initial brief."""
    user_text = update.message.text
    logger.info("BRIEF | %s | len=%d | text=%s", _user_tag(update), len(user_text), user_text[:300])
    rates = _get_rates(context)
    system_prompt = build_system_prompt(rates)

    typing_task = asyncio.create_task(_keep_typing(update.message.chat))
    try:
        gpt_resp, response_id = await ask_gpt(
            system_prompt=system_prompt,
            user_message=user_text,
            previous_response_id=None,
        )
    except Exception:
        logger.exception("GPT ERROR on brief | %s", _user_tag(update))
        await update.message.reply_text(
            "Произошла ошибка при обращении к GPT. Попробуйте ещё раз."
        )
        return WAITING_FOR_BRIEF
    finally:
        typing_task.cancel()

    context.user_data["response_id"] = response_id
    logger.info("BRIEF OK | %s | response_id=%s", _user_tag(update), response_id)

    return await _process_gpt_response(update, context, gpt_resp, rates)


async def handle_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User replied to follow-up questions."""
    user_text = update.message.text
    prev_id = context.user_data.get("response_id")
    logger.info("DIALOG | %s | prev_id=%s | text=%s", _user_tag(update), prev_id, user_text[:300])
    rates = _get_rates(context)
    system_prompt = build_system_prompt(rates)

    typing_task = asyncio.create_task(_keep_typing(update.message.chat))
    try:
        gpt_resp, response_id = await ask_gpt(
            system_prompt=system_prompt,
            user_message=user_text,
            previous_response_id=prev_id,
        )
    except Exception:
        logger.exception("GPT ERROR on dialog | %s | prev_id=%s", _user_tag(update), prev_id)
        await update.message.reply_text(
            "Произошла ошибка при обращении к GPT. Попробуйте ещё раз."
        )
        return DIALOG
    finally:
        typing_task.cancel()

    context.user_data["response_id"] = response_id
    logger.info("DIALOG OK | %s | response_id=%s", _user_tag(update), response_id)

    return await _process_gpt_response(update, context, gpt_resp, rates)


async def _process_gpt_response(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gpt_resp,
    rates: dict[str, int],
) -> int:
    tag = _user_tag(update)

    if gpt_resp.status == "need_info":
        logger.info("GPT→QUESTIONS | %s | count=%d", tag, len(gpt_resp.questions))
        text = "У меня есть уточняющие вопросы:\n\n" + _format_questions(gpt_resp.questions)
        await update.message.reply_text(text)
        return DIALOG

    if gpt_resp.status == "ready" and gpt_resp.result:
        logger.info(
            "GPT→ESTIMATE | %s | project=%s variants=%d",
            tag, gpt_resp.result.project_name, len(gpt_resp.result.variants),
        )
        await update.message.reply_text("Смета готова! Генерирую файлы...")

        html_path = pdf_path = None
        try:
            html_path = render_estimate(gpt_resp.result, rates)
        except Exception:
            logger.exception("HTML RENDER ERROR | %s", tag)

        try:
            pdf_path = render_estimate_pdf(gpt_resp.result, rates)
        except Exception:
            logger.exception("PDF RENDER ERROR | %s", tag)

        if not html_path and not pdf_path:
            await update.message.reply_text(
                "Ошибка при генерации файлов. Попробуйте /new."
            )
            return REFINE

        project_name = gpt_resp.result.project_name
        try:
            if html_path:
                with open(html_path, "rb") as f:
                    await update.message.reply_document(
                        document=f,
                        filename=f"{project_name}.html",
                    )
            if pdf_path:
                with open(pdf_path, "rb") as f:
                    await update.message.reply_document(
                        document=f,
                        filename=f"{project_name}.pdf",
                    )
            logger.info("FILES SENT | %s | project=%s html=%s pdf=%s",
                        tag, project_name, bool(html_path), bool(pdf_path))
        finally:
            if html_path:
                os.unlink(html_path)
            if pdf_path:
                os.unlink(pdf_path)

        await update.message.reply_text(
            "Готово! HTML — для просмотра в браузере, PDF — для печати.\n\n"
            "Можете написать правки — я пересгенерирую смету.\n"
            "/new — начать новую смету с чистого листа"
        )
        return REFINE

    logger.warning("GPT→UNEXPECTED | %s | status=%s", tag, gpt_resp.status)
    await update.message.reply_text(
        "Неожиданный ответ от GPT. Попробуйте ещё раз или /new."
    )
    return DIALOG


async def handle_refine(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """User wants to refine the delivered estimate."""
    user_text = update.message.text
    prev_id = context.user_data.get("response_id")
    logger.info("REFINE | %s | prev_id=%s | text=%s", _user_tag(update), prev_id, user_text[:300])
    rates = _get_rates(context)
    system_prompt = build_system_prompt(rates)

    typing_task = asyncio.create_task(_keep_typing(update.message.chat))
    try:
        gpt_resp, response_id = await ask_gpt(
            system_prompt=system_prompt,
            user_message=user_text,
            previous_response_id=prev_id,
        )
    except Exception:
        logger.exception("GPT ERROR on refine | %s | prev_id=%s", _user_tag(update), prev_id)
        await update.message.reply_text(
            "Произошла ошибка при обращении к GPT. Попробуйте ещё раз."
        )
        return REFINE
    finally:
        typing_task.cancel()

    context.user_data["response_id"] = response_id
    logger.info("REFINE OK | %s | response_id=%s", _user_tag(update), response_id)

    return await _process_gpt_response(update, context, gpt_resp, rates)


# ── bot factory ──────────────────────────────────────────

async def _post_init(application) -> None:
    """Register bot commands in Telegram menu."""
    await application.bot.set_my_commands([
        BotCommand("new", "Новая смета (сброс диалога)"),
        BotCommand("rates", "Текущие ставки по ролям"),
        BotCommand("help", "Справка"),
        BotCommand("cancel", "Отменить диалог"),
    ])


def create_bot() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(_post_init).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("new", new),
        ],
        states={
            WAITING_FOR_BRIEF: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_brief),
            ],
            DIALOG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_dialog),
            ],
            REFINE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_refine),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("new", new),
            CommandHandler("start", start),
        ],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("rates", rates_cmd))
    app.add_handler(CommandHandler("help", help_cmd))

    return app
