"""All user-facing bot texts.

Templates are formatted by the calling code via .format(...).
No parse_mode: user input (reason_text) is inserted as is.
"""

from config import BOT_BRAND_NAME

# --- ACL and errors ---
ACCESS_DENIED = "🚫 Доступ заборонено"
ADMIN_ONLY = "🚫 Команда доступна лише адмінам"
# Used when an inline callback has expired (absence/confirm flow): short, action-oriented.
STALE_CALLBACK = "Застаріло, почни спочатку"
ERROR_REPLY = "Щось пішло не так 😔"

# --- main menu ---
MENU_ABSENCE = "🗂 Мене не буде"

# --- /start ---
START_GREETING = "{brand} — бот-помічник.\nТвій ID: {user_id}"
START_IN_GROUP = "Ти в списку групи"
START_PENDING = "⏳ Заявка вже на розгляді. Чекай підтвердження..."
START_REQUEST_SENT = "✅ Заявка надіслана на розгляд"
ONBOARDING_PROMPT = (
    "Напиши своє прізвище та ім'я одним повідомленням\n\n"
    "Формат: рівно два слова, лише літери, дефіс та апостроф\n"
    "Приклади: «Петренко Іван», «Стрілецька Марія»"
)
REQUEST_CARD = "🆕 Заявка: {display_name} ({username}) — ID {user_id}"

# --- roles and menu ---
MENU_REPORTS = "📊 Вибірки"
NOT_ALLOWED_ABSENCE = "Відмічати пропуски можуть лише студенти та старости"
NOT_ALLOWED_REPORTS = "Вибірки доступні старості, супервайзеру та адмінам"
ROLE_UPDATE_NOTIFY = "🔔 Твоя роль оновлена: {role}."
ROLE_BACK_TO_STUDENT = "🔔 Роль знята — ти знову студент"
ACCESS_CLOSED_NOTIFY = "🚫 Доступ закрито"

# --- reports (selections) ---
REPORT_PROMPT = "📊 Вибірки\nОбери звіт:"
REPORT_TODAY_BUTTON = "📅 За сьогодні"
REPORT_TODAY_HEADER = "📊 Відсутні на {date} ({weekday}):"
REPORT_LINE = "• {name} — {reason}"
REPORT_TODAY_EMPTY = "✅ Сьогодні відсутніх немає"

# --- requests (/pending, cards) ---
BUTTON_ACCEPT = "✅ Прийняти"
BUTTON_REJECT = "❌ Відхилити"
PENDING_EMPTY = "Немає заявок"
APPROVED_NOTIFY = "✅ Заявка схвалена 🎉"
CARD_APPROVED = "✅ Схвалено: {display_name} ({username}) — ID {user_id}"
CARD_REJECTED = "❌ Відхилено: {display_name} ({username}) — ID {user_id}"
NO_USERNAME = "без юзернейма"
NOT_A_MANAGER = "Розгляд заявок доступний старості та адмінам"

# --- admin commands (interactive, no ID input) ---
PROMOTE_PROMPT = "Кого підвищити?"
DEMOTE_PROMPT = "У кого зняти роль?"
REMOVE_PROMPT = "Кого виключити?"
HEAD_LEAD_PROMPT = "Хто головний староста (отримувач заявок)?"
HEAD_LEAD_CROWN = "👑 "
DAY_MARKER_SELECTED = "✅ "
DAY_MARKER_UNSELECTED = "📅 "
PROMOTE_EMPTY = "Немає кандидатів"
DEMOTE_EMPTY = "Усі без ролей"
REMOVE_EMPTY = "Немає кого виключати"
HEAD_LEAD_EMPTY = "Спочатку призначте старосту — /promote"
ROLE_CHOICE_PROMPT = "Обери роль для {name}:"
BUTTON_ROLE_GROUP_LEAD = "👑 Староста"
BUTTON_ROLE_SUPERVISOR = "🎓 Супервайзер"
PROMOTE_DONE = "✅ {name} — тепер {role}"
DEMOTE_DONE = "✅ Роль знята: {name}"
REMOVE_DONE = "🚫 Доступ закрито: {name}"
HEAD_LEAD_SET = "👑 Головний староста: {name}. Заявки тепер надходять йому"
HEAD_LEAD_CLEARED = "Головний староста знятий — заявки знову йдуть адмінам"
# Used when an admin/pending card has expired (state no longer matches the button):
# longer, explains the card is stale and the command must be re-issued.
# Kept separate from STALE_CALLBACK because the two serve different UX contexts
# (inline callback vs. inline card) and carry different wording.
STALE_CARD = "Вже неактуально, наберіть команду спочатку"

# Admin alert when the roster is corrupt: writing fails, manual intervention needed.
ADMIN_STORAGE_ALERT = (
    "⚠️ Файл учасників пошкоджено — записи не зберігаються. "
    "Потрібне втручання адміністратора: перевірте логи."
)

# --- shared buttons ---
BUTTON_NEXT = "➡️ Далі"
BUTTON_BACK = "⬅️ Назад"
BUTTON_CANCEL = "❌ Скасувати"
BUTTON_SEND = "✅ Надіслати"
BUTTON_SEND_REPLACE = "✅ Замінити та надіслати"

# --- "I will be absent" flow ---
DAY_PROMPT = "Познач дні, коли тебе не буде (можна кілька).\nОбрано: {count}"
ALERT_PICK_DAY = "Спочатку познач день"
REASON_PROMPT = "📅 Обрано: {dates}\n\nПричина пропуску:"
OTHER_TEXT_PROMPT = "Напиши причину своїми словами (до {limit} символів).\nДля скасування — /cancel"
OTHER_TEXT_EMPTY = "Порожньо — напиши причину текстом (до {limit} символів)"
OTHER_TEXT_TOO_LONG = "Причина занадто довга (макс. {limit})"
CANCELLED = "Скасовано"
CONFIRM_NEW_LINE = "📅 {date} ({weekday})"
CONFIRM_REPLACED_LINE = "🔄 {date} ({weekday}) — замінить «{old_reason}»"
CONFIRM_IDENTICAL_LINE = "✅ {date} ({weekday}) — вже так"
CONFIRM_REASON = "{emoji} Причина: {name}"
CONFIRM_OTHER_REASON = "✍️ Інше: {text}"
CONFIRM_QUESTION = "Надіслати?"
ALL_IDENTICAL = "Усе вже позначено: {dates} — {reason}"
SUCCESS = (
    "✅ Позначено: {dates} — {reason}\n\n"
    "Якщо щось не так — познач ті самі дати спочатку з іншою причиною: запис заміниться"
)


def brand_greeting(user_id: int) -> str:
    """Greeting for /start with the brand name from config."""
    return START_GREETING.format(brand=BOT_BRAND_NAME, user_id=user_id)
