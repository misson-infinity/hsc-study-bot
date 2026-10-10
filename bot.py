import os
import asyncio
from datetime import datetime, date, timedelta
from dotenv import load_dotenv

from telegram import (Update, InlineKeyboardButton,
                      InlineKeyboardMarkup, BotCommand)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, CallbackQueryHandler,
    filters, ContextTypes
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import database as db

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

# ── Conversation States ───────────────────────────────────────────
(
    ASK_DEADLINE,
    ASK_SUBJECT, ASK_CHAPTER, ASK_CLASS_COUNT,
    ASK_CLASS_TIME, ASK_IS_BIG, ASK_BIG_CONFIRM,
    TASK_REPORT
) = range(8)

SUBJECTS = [
    "Physics 1st", "Physics 2nd",
    "Chemistry 1st", "Chemistry 2nd",
    "Math 1st", "Math 2nd",
    "Biology 1st", "Biology 2nd"
]

# ── /start ────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db.init_db()
    text = (
        "🎯 *HSC Study Planner Bot*\n\n"
        "আমি তোমার পুরো HSC সিলেবাস প্ল্যান করতে সাহায্য করবো!\n\n"
        "📌 *Commands:*\n"
        "/setdeadline — পরীক্ষার তারিখ সেট করো\n"
        "/addchapter — নতুন Chapter যোগ করো\n"
        "/today — আজকের Task দেখো\n"
        "/done — Task complete করো\n"
        "/progress — মোট Progress দেখো\n"
        "/syllabus — পুরো সিলেবাস দেখো\n"
        "/report — রাত ১২টার রিপোর্ট\n\n"
        "শুরু করো 👉 /setdeadline"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ── /setdeadline ──────────────────────────────────────────────────
async def set_deadline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📅 তোমার HSC পরীক্ষা কবে?\n"
        "তারিখ লেখো এই format এ: *DD-MM-YYYY*\n"
        "উদাহরণ: `02-04-2025`",
        parse_mode="Markdown"
    )
    return ASK_DEADLINE

async def save_deadline(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        exam_date = datetime.strptime(text, "%d-%m-%Y").date()
        days_left = (exam_date - date.today()).days
        if days_left <= 0:
            await update.message.reply_text(
                "❌ তারিখটা ভবিষ্যতের হতে হবে! আবার দাও।"
            )
            return ASK_DEADLINE
        db.save_deadline(update.effective_user.id, text)
        await update.message.reply_text(
            f"✅ Deadline সেট হয়েছে: *{text}*\n"
            f"⏳ বাকি আছে: *{days_left} দিন*\n\n"
            f"এখন Chapter যোগ করো 👉 /addchapter",
            parse_mode="Markdown"
        )
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text(
            "❌ Format ঠিক নেই। উদাহরণ: `02-04-2025`",
            parse_mode="Markdown"
        )
        return ASK_DEADLINE

# ── /addchapter ───────────────────────────────────────────────────
async def add_chapter_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    settings = db.get_settings(update.effective_user.id)
    if not settings:
        await update.message.reply_text(
            "⚠️ আগে deadline সেট করো! /setdeadline"
        )
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
        f"🎬 এই chapter এ মোট কতটা class আছে? (সংখ্যা দাও)",
        parse_mode="Markdown"
    )
    return ASK_CLASS_COUNT

async def class_count_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(update.message.text.strip())
        ctx.user_data['class_count'] = count
        await update.message.reply_text(
            f"🕐 প্রতিটি class গড়ে কত মিনিটের?\n"
            f"(উদাহরণ: ৪৫ বা ৬০)"
        )
        return ASK_CLASS_TIME
    except ValueError:
        await update.message.reply_text("❌ সংখ্যা দাও! যেমন: 5")
        return ASK_CLASS_COUNT

async def class_time_received(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        time_min = int(update.message.text.strip())
        ctx.user_data['class_time'] = time_min

        keyboard = [
            [InlineKeyboardButton("✅ হ্যাঁ, বড় Chapter", callback_data="big_yes"),
             InlineKeyboardButton("❌ না, স্বাভাবিক", callback_data="big_no")]
        ]
        await update.message.reply_text(
            f"⏱ প্রতি class: *{time_min} মিনিট*\n\n"
            f"❓ এটা কি বড় বা কঠিন Chapter?\n"
            f"(বড় হলে practice time বেশি দেওয়া হবে)",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return ASK_IS_BIG
    except ValueError:
        await update.message.reply_text("❌ মিনিট সংখ্যা দাও! যেমন: 60")
        return ASK_CLASS_TIME

async def is_big_chosen(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    is_big = 1 if query.data == "big_yes" else 0
    ctx.user_data['is_big'] = is_big

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
    total_min = ctx.user_data['class_count'] * ctx.user_data['class_time']
    practice_min = total_min * 2 if is_big else total_min

    await query.edit_message_text(
        f"✅ *Chapter যোগ হয়েছে!*\n\n"
        f"📚 Subject: {ctx.user_data['subject']}\n"
        f"📖 Chapter: {ctx.user_data['chapter']}\n"
        f"🎬 Classes: {ctx.user_data['class_count']}টি\n"
        f"⏱ প্রতি class: {ctx.user_data['class_time']} মিনিট\n"
        f"📊 ধরণ: {big_label}\n"
        f"🏋️ Practice Time: ~{practice_min} মিনিট\n\n"
        f"আরেকটি যোগ করতে: /addchapter\n"
        f"আজকের plan দেখতে: /today",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ── /today ────────────────────────────────────────────────────────
async def today_tasks(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    today_str = date.today().strftime("%d-%m-%Y")
    settings = db.get_settings(uid)

    if not settings:
        await update.message.reply_text("⚠️ আগে /setdeadline দিয়ে শুরু করো!")
        return

    tasks = db.get_today_tasks(uid, today_str)

    # যদি আজকের task না থাকে, auto-generate করো
    if not tasks:
        await generate_today_plan(uid, today_str, settings)
        tasks = db.get_today_tasks(uid, today_str)

    if not tasks:
        await update.message.reply_text(
            "🎉 আজকের জন্য কোনো task নেই!\n"
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
        f"📅 *আজকের Study Plan — {today_str}*",
        f"⏰ সকাল ৫টা থেকে রাত ১২টা",
        f"📊 Progress: {done}/{total} ({pct}%)\n",
        f"{'─'*30}"
    ]

    for i, (tid, subject, chapter, task_type, completed) in enumerate(tasks, 1):
        status = "✅" if completed else "⬜"
        icon = task_icons.get(task_type, "📌")
        lines.append(
            f"{status} {i}. {icon} [{subject}]\n"
            f"    📖 {chapter}\n"
            f"    🏷 {task_type.upper()}"
        )

    lines.append(f"\n✅ Complete করতে: /done")
    await update.message.reply_text(
        "\n".join(lines), parse_mode="Markdown"
    )

async def generate_today_plan(uid, today_str, settings):
    """Deadline ও remaining chapter অনুযায়ী আজকের plan বানাও"""
    deadline = datetime.strptime(settings[1], "%d-%m-%Y").date()
    days_left = (deadline - date.today()).days
    if days_left <= 0:
        return

    chapters = db.get_pending_chapters(uid)
    if not chapters:
        return

    # প্রতিদিন ১০ ঘণ্টা = ৬০০ মিনিট class+practice
    daily_budget = 600
    tasks_today = []
    used = 0

    for ch in chapters:
        (cid, cuid, subject, chapter_name, total_cls, done_cls,
         time_min, is_big, note, practice, revision, exam_ready,
         exam_done, status) = ch

        remaining_cls = total_cls - done_cls

        # Class task
        if remaining_cls > 0:
            cls_time = time_min
            if used + cls_time <= daily_budget:
                tasks_today.append((cid, "class"))
                used += cls_time

        # Note task (class শেষ হলে)
        if done_cls >= total_cls and not note:
            tasks_today.append((cid, "note"))
            used += 30

        # Practice task
        practice_time = time_min * 2 if is_big else time_min
        if done_cls >= total_cls and note and not practice:
            if used + practice_time <= daily_budget:
                tasks_today.append((cid, "practice"))
                used += practice_time

        # Revision task
        if practice and not revision:
            tasks_today.append((cid, "revision"))
            used += 20

        # Exam task (১টা chapter exam প্রতিদিন)
        if exam_ready and not exam_done and len([t for t in tasks_today if t[1] == "exam"]) == 0:
            tasks_today.append((cid, "exam"))

        if used >= daily_budget:
            break

    if tasks_today:
        db.save_daily_tasks(uid, today_str, tasks_today)

# ── /done ─────────────────────────────────────────────────────────
async def done_task(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    today_str = date.today().strftime("%d-%m-%Y")
    tasks = db.get_today_tasks(uid, today_str)

    incomplete = [(tid, subj, ch, tt) for tid, subj, ch, tt, comp in tasks if not comp]

    if not incomplete:
        await update.message.reply_text(
            "🎉 আজকের সব task complete! দারুণ! 💪"
        )
        return

    keyboard = [
        [InlineKeyboardButton(
            f"{'🎬📝💪🔄📝'[['class','note','practice','revision','exam'].index(tt) if tt in ['class','note','practice','revision','exam'] else 0]} {ch[:20]} — {tt.upper()}",
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

    # Chapter ID ও task type বের করো
    import sqlite3
    conn = sqlite3.connect(db.DB)
    c = conn.cursor()
    c.execute("SELECT chapter_id, task_type FROM daily_tasks WHERE id=?", (task_id,))
    row = c.fetchone()
    conn.close()

    if row:
        db.complete_task(task_id, row[0], row[1])
        await query.edit_message_text(
            f"✅ *Task Complete!* 🎉\n\n"
            f"দারুণ কাজ! এগিয়ে যাও! 💪\n"
            f"বাকি task দেখতে: /today",
            parse_mode="Markdown"
        )

# ── /progress ─────────────────────────────────────────────────────
async def progress(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    today_str = date.today().strftime("%d-%m-%Y")
    settings = db.get_settings(uid)

    total_ch, done_ch = db.get_progress(uid)
    today_total, today_done = db.get_today_progress(uid, today_str)

    if total_ch == 0:
        await update.message.reply_text(
            "📚 এখনো কোনো Chapter যোগ হয়নি!\n/addchapter দিয়ে শুরু করো।"
        )
        return

    overall_pct = int((done_ch / total_ch) * 100) if total_ch > 0 else 0
    today_pct = int((today_done / today_total) * 100) if today_total > 0 else 0

    deadline_text = ""
    if settings and settings[1]:
        deadline = datetime.strptime(settings[1], "%d-%m-%Y").date()
        days_left = (deadline - date.today()).days
        deadline_text = f"📅 Deadline: {settings[1]}\n⏳ বাকি: {days_left} দিন\n"

    # Progress bar তৈরি
    bar_overall = "█" * (overall_pct // 10) + "░" * (10 - overall_pct // 10)
    bar_today = "█" * (today_pct // 10) + "░" * (10 - today_pct // 10)

    text = (
        f"📊 *Study Progress Report*\n"
        f"{'─'*30}\n"
        f"{deadline_text}\n"
        f"📚 *মোট Syllabus:*\n"
        f"|{bar_overall}| {overall_pct}%\n"
        f"✅ Complete: {done_ch}/{total_ch} chapters\n\n"
        f"📅 *আজকের Progress:*\n"
        f"|{bar_today}| {today_pct}%\n"
        f"✅ Complete: {today_done}/{today_total} tasks\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ── /syllabus ─────────────────────────────────────────────────────
async def syllabus(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    chapters = db.get_all_chapters(uid)

    if not chapters:
        await update.message.reply_text(
            "📚 কোনো Chapter নেই। /addchapter দিয়ে যোগ করো।"
        )
        return

    # Subject অনুযায়ী group করো
    grouped = {}
    for ch in chapters:
        subj = ch[2]
        if subj not in grouped:
            grouped[subj] = []
        grouped[subj].append(ch)

    lines = ["📚 *পুরো Syllabus Overview*\n"]
    for subj, chs in grouped.items():
        lines.append(f"\n📘 *{subj}*")
        for ch in chs:
            status_icon = "✅" if ch[13] == "done" else (
                "📝✅" if ch[11] else (
                    "💪" if ch[9] else (
                        "📝" if ch[8] else "🎬"
                    )
                )
            )
            big = " 🔴" if ch[7] else ""
            lines.append(
                f"  {status_icon} {ch[3]}{big}\n"
                f"     Classes: {ch[5]}/{ch[4]}"
            )

    await update.message.reply_text(
        "\n".join(lines), parse_mode="Markdown"
    )

# ── /report (রাত ১২টার Review) ────────────────────────────────────
async def night_report(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    today_str = date.today().strftime("%d-%m-%Y")
    tomorrow_str = (date.today() + timedelta(days=1)).strftime("%d-%m-%Y")

    total, done = db.get_today_progress(uid, today_str)
    pct = int((done / total) * 100) if total > 0 else 0

    # অসম্পূর্ণ task carry করো
    carried = db.carry_incomplete_tasks(uid, today_str, tomorrow_str)

    msg = (
        f"🌙 *রাতের রিপোর্ট — {today_str}*\n"
        f"{'─'*30}\n"
        f"✅ Completed: {done}/{total} tasks\n"
        f"📊 আজকের Score: {pct}%\n\n"
    )

    if carried > 0:
        msg += (
            f"⚠️ *{carried}টি task বাকি ছিল*\n"
            f"➡️ কালকের plan এ add করা হয়েছে\n"
            f"⚡ Deadline এর মধ্যে শেষ করতে হবে!\n\n"
        )
    else:
        msg += "🎉 *সব task শেষ! অসাধারণ!* 💪\n\n"

    if pct >= 80:
        msg += "⭐ দারুণ পারফরম্যান্স! এভাবেই এগিয়ে যাও!"
    elif pct >= 50:
        msg += "📈 ভালো শুরু! কাল আরেকটু বেশি করো!"
    else:
        msg += "💡 কাল সকালে ঠিকঠাক শুরু করো! তুমি পারবে! 💪"

    await update.message.reply_text(msg, parse_mode="Markdown")

# ── Scheduler (Auto Morning & Night messages) ─────────────────────
async def morning_task_sender(app):
    """প্রতিদিন সকাল ৫টায় সব user কে task পাঠাও"""
    conn = __import__('sqlite3').connect(db.DB)
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
                total = len(tasks)
                deadline = settings[1] if settings else "N/A"
                exam_date = datetime.strptime(deadline, "%d-%m-%Y").date() if settings else None
                days_left = (exam_date - date.today()).days if exam_date else "?"

                text = (
                    f"🌅 *সুপ্রভাত! সকাল ৫টা বাজে!*\n\n"
                    f"⏳ Exam এর আগে বাকি: *{days_left} দিন*\n"
                    f"📋 আজকে *{total}টি task* আছে\n\n"
                    f"💪 শুরু করো! /today"
                )
                await app.bot.send_message(uid, text, parse_mode="Markdown")
        except Exception:
            pass

async def midnight_checker(app):
    """রাত ১২টায় progress চেক"""
    conn = __import__('sqlite3').connect(db.DB)
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
                f"📊 আজকের Score: *{pct}%* ({done}/{total})\n"
            )
            if carried:
                text += f"⚠️ {carried}টি task কাল এ add হয়েছে\n"
            text += "\nঘুমাও, কাল আবার শুরু! 💤"

            await app.bot.send_message(uid, text, parse_mode="Markdown")
        except Exception:
            pass

# ── Main ──────────────────────────────────────────────────────────
def main():
    db.init_db()
    app = Application.builder().token(TOKEN).build()

    # Deadline conversation
    deadline_conv = ConversationHandler(
        entry_points=[CommandHandler("setdeadline", set_deadline)],
        states={ASK_DEADLINE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_deadline)]},
        fallbacks=[]
    )

    # Chapter add conversation
    chapter_conv = ConversationHandler(
        entry_points=[CommandHandler("addchapter", add_chapter_start)],
        states={
            ASK_SUBJECT:     [CallbackQueryHandler(subject_chosen, pattern="^sub_")],
            ASK_CHAPTER:     [MessageHandler(filters.TEXT & ~filters.COMMAND, chapter_name_received)],
            ASK_CLASS_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, class_count_received)],
            ASK_CLASS_TIME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, class_time_received)],
            ASK_IS_BIG:      [CallbackQueryHandler(is_big_chosen, pattern="^big_")],
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
    app.add_handler(CallbackQueryHandler(task_completed_callback, pattern="^done_"))

    # Scheduler setup
    scheduler = AsyncIOScheduler(timezone="Asia/Dhaka")
    scheduler.add_job(
        morning_task_sender, 'cron',
        hour=5, minute=0,
        args=[app]
    )
    scheduler.add_job(
        midnight_checker, 'cron',
        hour=0, minute=0,
        args=[app]
    )
    scheduler.start()

    print("🤖 HSC Study Planner Bot চালু হয়েছে!")
    app.run_polling()

if __name__ == "__main__":
    main()
