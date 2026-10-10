import os
import sqlite3
import logging
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

from telegram import (Update, InlineKeyboardButton,
                      InlineKeyboardMarkup)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import database as db

logging.basicConfig(level=logging.INFO)
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

(
    ASK_DEADLINE,
    ASK_SUBJECT, ASK_CHAPTER, ASK_CLASS_COUNT,
    ASK_CLASS_TIME, ASK_IS_BIG,
) = range(6)

SUBJECTS = [
    "Physics 1st", "Physics 2nd",
    "Chemistry 1st", "Chemistry 2nd",
    "Math 1st", "Math 2nd",
    "Biology 1st", "Biology 2nd"
]

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db.init_db()
    text = (
        "🎯 *HSC Study Planner Bot*\n\n"
        "আমি তোমার পুরো HSC সিলেবাস প্ল্যান করবো!\n\n"
        "📌 *Commands:*\n"
        "/setdeadline — পরীক্ষার তারিখ সেট করো\n"
        "/addchapter — নতুন Chapter যোগ করো\n"
        "/today — আজকের Task দেখো\n"
        "/done — Task complete করো\n"
        "/progress — মোট Progress দেখো\n"
        "/syllabus — পুরো সিলেবাস দেখো\n"
        "/report — রাতের রিপোর্ট\n\n"
        "শুরু করো 👉 /setdeadline"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def set_deadline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📅 HSC পরীক্ষা কবে?\n"
        "Format: *DD-MM-YYYY*\n"
        "উদাহরণ: `02-04-2025`",
        parse_mode="Markdown"
    )
    return ASK_DEADLINE

async def save_deadline_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        exam_date = datetime.strptime(text, "%d-%m-%Y").date()
        days_left = (exam_date - date.today()).days
        if days_left <= 0:
            await update.message.reply_text("❌ ভবিষ্যতের তারিখ দাও!")
            return ASK_DEADLINE
        db.save_deadline(update.effective_user.id, text)
        await update.message.reply_text(
            f"✅ Deadline: *{text}*\n"
            f"⏳ বাকি: *{days_left} দিন*\n\n"
            f"এখন Chapter যোগ করো 👉 /addchapter",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            "❌ Format ঠিক নেই! উদাহরণ: `02-04-2025`",
            parse_mode="Markdown"
        )
        return ASK_DEADLINE

async def add_chapter_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    settings = db.get_settings(update.effective_user.id)
    if not settings:
        await update.message.reply_text("⚠️ আগে /setdeadline দাও!")
        return ConversationHandler.END
    keyboard = [
        [InlineKeyboardButton(s, callback_data=f"sub_{s}")]
        for s in SUBJECTS
    ]
    await update.message.reply_text(
        "📚 Subject বেছে নাও:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return ASK_SUBJECT

async def subject_chosen(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    ctx.user_data['subject'] = query.data.replace("sub_", "")
    await query.edit_message_text(
        f"✅ Subject: *{ctx.user_data['subject']}*\n\n"
        f"📖 Chapter এর নাম লেখো:",
        parse_mode="Markdown"
    )
    return ASK_CHAPTER

async def chapter_name_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data['chapter'] = update.message.text.strip()
    await update.message.reply_text(
        f"📘 Chapter: *{ctx.user_data['chapter']}*\n\n"
        f"🎬 মোট কতটা class? (সংখ্যা দাও)",
        parse_mode="Markdown"
    )
    return ASK_CLASS_COUNT

async def class_count_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data['class_count'] = int(update.message.text.strip())
        await update.message.reply_text(
            "🕐 প্রতিটি class কত মিনিটের?\n(যেমন: 45 বা 60)"
        )
        return ASK_CLASS_TIME
    except ValueError:
        await update.message.reply_text("❌ সংখ্যা দাও! যেমন: 5")
        return ASK_CLASS_COUNT

async def class_time_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        ctx.user_data['class_time'] = int(update.message.text.strip())
        keyboard = [
            [InlineKeyboardButton("✅ হ্যাঁ, বড় Chapter", callback_data="big_yes"),
             InlineKeyboardButton("❌ না, স্বাভাবিক", callback_data="big_no")]
        ]
        await update.message.reply_text(
            f"⏱ প্রতি class: *{ctx.user_data['class_time']} মিনিট*\n\n"
            f"❓ এটা কি বড়/কঠিন Chapter?\n"
            f"(বড় হলে practice time বেশি দেওয়া হবে)",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ASK_IS_BIG
    except ValueError:
        await update.message.reply_text("❌ মিনিট দাও! যেমন: 60")
        return ASK_CLASS_TIME

async def is_big_chosen(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    is_big = 1 if query.data == "big_yes" else 0
    uid = query.from_user.id
    db.add_chapter(
        user_id=uid,
        subject=ctx.user_data['subject'],
        chapter_name=ctx.user_data['chapter'],
        total_classes=ctx.user_data['class_count'],
        class_time_min=ctx.user_data['class_time'],
        is_big=is_big
    )
    big_label = "🔴 বড় Chapter" if is_big else "🟢 স্বাভাবিক"
    await query.edit_message_text(
        f"✅ *Chapter যোগ হয়েছে!*\n\n"
        f"📚 {ctx.user_data['subject']}\n"
        f"📖 {ctx.user_data['chapter']}\n"
        f"🎬 {ctx.user_data['class_count']}টি class "
        f"× {ctx.user_data['class_time']} মিনিট\n"
        f"📊 {big_label}\n\n"
        f"আরেকটি: /addchapter\n"
        f"আজকের plan: /today",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def generate_today_plan(uid, today_str, settings):
    deadline = datetime.strptime(settings[1], "%d-%m-%Y").date()
    days_left = (deadline - date.today()).days
    if days_left <= 0:
        return
    chapters = db.get_pending_chapters(uid)
    if not chapters:
        return
    daily_budget = 600
    tasks_today = []
    used = 0
    for ch in chapters:
        (cid, cuid, subject, chapter_name, total_cls, done_cls,
         time_min, is_big, note, practice, revision, exam_ready,
         exam_done, status) = ch
        remaining_cls = total_cls - done_cls
        if remaining_cls > 0:
            if used + time_min <= daily_budget:
                tasks_today.append((cid, "class"))
                used += time_min
        if done_cls >= total_cls and not note:
            tasks_today.append((cid, "note"))
            used += 30
        practice_time = time_min * 2 if is_big else time_min
        if done_cls >= total_cls and note and not practice:
            if used + practice_time <= daily_budget:
                tasks_today.append((cid, "practice"))
                used += practice_time
        if practice and not revision:
            tasks_today.append((cid, "revision"))
            used += 20
        if (exam_ready and not exam_done and
                len([t for t in tasks_today if t[1] == "exam"]) == 0):
            tasks_today.append((cid, "exam"))
        if used >= daily_budget:
            break
    if tasks_today:
        db.save_daily_tasks(uid, today_str, tasks_today)

async def today_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    today_str = date.today().strftime("%d-%m-%Y")
    settings = db.get_settings(uid)
    if not settings:
        await update.message.reply_text("⚠️ আগে /setdeadline দাও!")
        return
    tasks = db.get_today_tasks(uid, today_str)
    if not tasks:
        await generate_today_plan(uid, today_str, settings)
        tasks = db.get_today_tasks(uid, today_str)
    if not tasks:
        await update.message.reply_text(
            "🎉 আজকের কোনো task নেই!\n"
            "নতুন chapter যোগ করো: /addchapter"
        )
        return
    total, done = db.get_today_progress(uid, today_str)
    pct = int((done / total) * 100) if total > 0 else 0
    task_icons = {
        "class": "🎬", "note": "📝",
        "practice": "💪", "revision": "🔄", "exam": "📝✅"
    }
    lines = [
        f"📅 *আজকের Plan — {today_str}*",
        f"📊 Progress: {done}/{total} ({pct}%)\n",
        f"{'─'*28}"
    ]
    for i, (tid, subject, chapter, task_type, completed) in enumerate(tasks, 1):
        status = "✅" if completed else "⬜"
        icon = task_icons.get(task_type, "📌")
        lines.append(
            f"{status} {i}. {icon} [{subject}]\n"
            f"    📖 {chapter}\n"
            f"    🏷 {task_type.upper()}"
        )
    lines.append("\n✅ Complete করতে: /done")
    await update.message.reply_text(
        "\n".join(lines), parse_mode="Markdown"
    )

async def done_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    today_str = date.today().strftime("%d-%m-%Y")
    tasks = db.get_today_tasks(uid, today_str)
    incomplete = [
        (tid, subj, ch, tt)
        for tid, subj, ch, tt, comp in tasks if not comp
    ]
    if not incomplete:
        await update.message.reply_text(
            "🎉 আজকের সব task complete! দারুণ! 💪"
        )
        return
    keyboard = [
        [InlineKeyboardButton(
            f"{ch[:22]} — {tt.upper()}",
            callback_data=f"done_{tid}"
        )]
        for tid, subj, ch, tt in incomplete
    ]
    await update.message.reply_text(
        "✅ কোন task complete করলে?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def task_completed_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    task_id = int(query.data.replace("done_", ""))
    conn = sqlite3.connect(db.DB)
    c = conn.cursor()
    c.execute("SELECT chapter_id, task_type FROM daily_tasks WHERE id=?",
              (task_id,))
    row = c.fetchone()
    conn.close()
    if row:
        db.complete_task(task_id, row[0], row[1])
        await query.edit_message_text(
            "✅ *Task Complete!* 🎉\n\n"
            "দারুণ! এগিয়ে যাও! 💪\n"
            "বাকি task: /today",
            parse_mode="Markdown"
        )

async def progress(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    today_str = date.today().strftime("%d-%m-%Y")
    settings = db.get_settings(uid)
    total_ch, done_ch = db.get_progress(uid)
    today_total, today_done = db.get_today_progress(uid, today_str)
    if total_ch == 0:
        await update.message.reply_text(
            "📚 কোনো Chapter নেই। /addchapter দিয়ে শুরু করো।"
        )
        return
    overall_pct = int((done_ch / total_ch) * 100) if total_ch > 0 else 0
    today_pct = int((today_done / today_total) * 100) if today_total > 0 else 0
    bar_o = "█" * (overall_pct // 10) + "░" * (10 - overall_pct // 10)
    bar_t = "█" * (today_pct // 10) + "░" * (10 - today_pct // 10)
    deadline_text = ""
    if settings and settings[1]:
        exam_date = datetime.strptime(settings[1], "%d-%m-%Y").date()
        days_left = (exam_date - date.today()).days
        deadline_text = (
            f"📅 Deadline: {settings[1]}\n"
            f"⏳ বাকি: {days_left} দিন\n\n"
        )
    text = (
        f"📊 *Progress Report*\n{'─'*28}\n"
        f"{deadline_text}"
        f"📚 *মোট Syllabus:*\n|{bar_o}| {overall_pct}%\n"
        f"✅ {done_ch}/{total_ch} chapters\n\n"
        f"📅 *আজকের Progress:*\n|{bar_t}| {today_pct}%\n"
        f"✅ {today_done}/{today_total} tasks"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def syllabus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    chapters = db.get_all_chapters(uid)
    if not chapters:
        await update.message.reply_text(
            "📚 কোনো Chapter নেই। /addchapter দিয়ে যোগ করো।"
        )
        return
    grouped = {}
    for ch in chapters:
        subj = ch[2]
        if subj not in grouped:
            grouped[subj] = []
        grouped[subj].append(ch)
    lines = ["📚 *পুরো Syllabus*\n"]
    for subj, chs in grouped.items():
        lines.append(f"\n📘 *{subj}*")
        for ch in chs:
            if ch[13] == "done":
                icon = "✅"
            elif ch[11]:
                icon = "📝✅"
            elif ch[9]:
                icon = "💪"
            elif ch[8]:
                icon = "📝"
            else:
                icon = "🎬"
            big = " 🔴" if ch[7] else ""
            lines.append(
                f"  {icon} {ch[3]}{big} ({ch[5]}/{ch[4]} class)"
            )
    await update.message.reply_text(
        "\n".join(lines), parse_mode="Markdown"
    )

async def night_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    today_str = date.today().strftime("%d-%m-%Y")
    tomorrow_str = (date.today() + timedelta(days=1)).strftime("%d-%m-%Y")
    total, done = db.get_today_progress(uid, today_str)
    pct = int((done / total) * 100) if total > 0 else 0
    carried = db.carry_incomplete_tasks(uid, today_str, tomorrow_str)
    msg = (
        f"🌙 *রাতের রিপোর্ট — {today_str}*\n{'─'*28}\n"
        f"✅ Completed: {done}/{total}\n"
        f"📊 Score: {pct}%\n\n"
    )
    if carried > 0:
        msg += (
            f"⚠️ *{carried}টি task কাল এ add হয়েছে*\n"
            f"⚡ Deadline এর মধ্যে শেষ করো!\n\n"
        )
    else:
        msg += "🎉 *সব task শেষ! অসাধারণ!* 💪\n\n"
    if pct >= 80:
        msg += "⭐ দারুণ পারফরম্যান্স!"
    elif pct >= 50:
        msg += "📈 ভালো! কাল আরেকটু বেশি করো!"
    else:
        msg += "💡 কাল সকালে ঠিকঠাক শুরু করো! তুমি পারবে! 💪"
    await update.message.reply_text(msg, parse_mode="Markdown")

async def morning_task_sender(app):
    conn = sqlite3.connect(db.DB)
    c = conn.cursor()
    c.execute("SELECT user_id FROM user_settings")
    users = c.fetchall()
    conn.close()
    today_str = date.today().strftime("%d-%m-%Y")
    for (uid,) in users:
        try:
            settings = db.get_settings(uid)
            tasks = db.get_today_tasks(uid, today_str)
            if not tasks:
                await generate_today_plan(uid, today_str, settings)
                tasks = db.get_today_tasks(uid, today_str)
            if tasks:
                exam_date = datetime.strptime(settings[1], "%d-%m-%Y").date()
                days_left = (exam_date - date.today()).days
                text = (
                    f"🌅 *সুপ্রভাত! সকাল ৫টা!*\n\n"
                    f"⏳ Exam এর আগে বাকি: *{days_left} দিন*\n"
                    f"📋 আজকে *{len(tasks)}টি task* আছে\n\n"
                    f"💪 শুরু করো! /today"
                )
                await app.bot.send_message(uid, text, parse_mode="Markdown")
        except Exception:
            pass

async def midnight_checker(app):
    conn = sqlite3.connect(db.DB)
    c = conn.cursor()
    c.execute("SELECT user_id FROM user_settings")
    users = c.fetchall()
    conn.close()
    today_str = date.today().strftime("%d-%m-%Y")
    tomorrow_str = (date.today() + timedelta(days=1)).strftime("%d-%m-%Y")
    for (uid,) in users:
        try:
            total, done = db.get_today_progress(uid, today_str)
            pct = int((done / total) * 100) if total > 0 else 0
            carried = db.carry_incomplete_tasks(uid, today_str, tomorrow_str)
            text = (
                f"🌙 *রাত ১২টা — Daily Report*\n"
                f"📊 Score: *{pct}%* ({done}/{total})\n"
            )
            if carried:
                text += f"⚠️ {carried}টি task কাল add হয়েছে\n"
            text += "\nঘুমাও, কাল আবার শুরু! 💤"
            await app.bot.send_message(uid, text, parse_mode="Markdown")
        except Exception:
            pass

def main():
    db.init_db()

    app = (
        Application.builder()
        .token(TOKEN)
        .updater(None)
        .build()
    )

    deadline_conv = ConversationHandler(
        entry_points=[CommandHandler("setdeadline", set_deadline)],
        states={
            ASK_DEADLINE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    save_deadline_handler
                )
            ]
        },
        fallbacks=[]
    )

    chapter_conv = ConversationHandler(
        entry_points=[CommandHandler("addchapter", add_chapter_start)],
        states={
            ASK_SUBJECT: [
                CallbackQueryHandler(subject_chosen, pattern="^sub_")
            ],
            ASK_CHAPTER: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    chapter_name_received
                )
            ],
            ASK_CLASS_COUNT: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    class_count_received
                )
            ],
            ASK_CLASS_TIME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    class_time_received
                )
            ],
            ASK_IS_BIG: [
                CallbackQueryHandler(is_big_chosen, pattern="^big_")
            ],
        },
        fallbacks=[]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(deadline_conv)
    app.add_handler(chapter_conv)
    app.add_handler(CommandHandler("today", today_tasks))
    app.add_handler(CommandHandler("done", done_task))
    app.add_handler(CommandHandler("progress", progress))
    app.add_handler(CommandHandler("syllabus", syllabus))
    app.add_handler(CommandHandler("report", night_report))
    app.add_handler(
        CallbackQueryHandler(task_completed_callback, pattern="^done_")
    )

    scheduler = AsyncIOScheduler(timezone="Asia/Dhaka")
    scheduler.add_job(
        morning_task_sender, 'cron',
        hour=5, minute=0, args=[app]
    )
    scheduler.add_job(
        midnight_checker, 'cron',
        hour=0, minute=0, args=[app]
    )
    scheduler.start()

    print("🤖 HSC Study Planner Bot চালু হয়েছে!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
