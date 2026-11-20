"""Отделение персональных данных от текста резюме — без нейросетей, по правилам.

Метод выбран по замеру на архиве «Кадры» (hq/work/2026-11-19-stage-0a-01-import/plan.md):
NER Natasha давал ≈20 % верных находок, правила — ≈119 из 120.

Шесть шагов, по порядку:
1. Шаблоны контактов: email, телефон, ссылки на профили, `@ник`.
2. Шапка hh.ru: «ФИО N», строка «Женщина, 48 лет, родилась …», «Кандидат №N», `mailto:`.
3. Подписанные поля: «Телефон: …», «Почта: …», «Тг: …», «ФИО: …».
4. Имена по подсказкам: подпись письма («С уважением, …»), представление («Меня зовут …»),
   строка рядом с контактами, ФИО с отчеством, «Автор: …» в блоке работодателя hh.ru.
   Слово-кандидат сверяем со словарём pymorphy3 (пометки «имя», «фамилия», «отчество»).
5. Распространение: найденные имена (во всех падежах) и ники ищем по всему тексту.
6. Проверка: ничего из найденного не осталось в тексте, нет остатков контактов. Иначе — карантин.

Что не трогаем: род глаголов («работала») — контракт БД п. 11.7; город и гражданство — п. 11.8.
"""
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

from pydantic import ValidationError

from app.db.enums import FileFormat
from app.schemas.pii import PiiData

# v2 (ingest-02): личные ссылки с путём (Google Drive/Docs, Figma, Notion, Яндекс.Диск, личные сайты)
# и личный хостинг; «Git: CI/CD» больше не считается адресом.
REDACTION_METHOD = "ingest-rules v2"

MASK_NAME = "[имя скрыто]"
MASK_CONTACT = "[контакт скрыт]"
MASK_LINK = "[ссылка скрыта]"
MASK_PERSON = "[пол, возраст и дата рождения скрыты]"
MASK_ARCHIVE_ID = "[номер кандидата скрыт]"
MASKS = (MASK_NAME, MASK_CONTACT, MASK_LINK, MASK_PERSON, MASK_ARCHIVE_ID)

MIN_CONTENT_CHARS = 50  # меньше — после очистки нечего оценивать


class RedactionError(Exception):
    """Очистка не прошла проверку: текст нельзя отдавать модели."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass
class Redacted:
    text: str
    pii: PiiData
    headline: str | None
    warnings: list[str] = field(default_factory=list)


# --- Шаблоны -----------------------------------------------------------------

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Разделители в номерах: пробел, неразрывные пробелы и все виды дефисов и тире
# (в архиве встречается неразрывный дефис U+2011: «999‑99‑99»).
_SPACE = r" \t  "
_DASH = r"\-‐-―−"
_SEP = rf"[{_SPACE}{_DASH}.]"
PHONE = re.compile(
    rf"(?<![\w+])(?:\+[{_SPACE}]?7|8){_SEP}*\(?{_SEP}*\d{{3}}{_SEP}*\)?{_SEP}*\d{{3}}{_SEP}*\d{{2}}{_SEP}*\d{{2}}(?!\d)"
)
PHONE_INTL = re.compile(
    rf"(?<![\w])\+[{_SPACE}]?\d{{1,3}}{_SEP}*\(?{_SEP}*\d{{2,4}}{_SEP}*\)?{_SEP}*\d{{2,4}}{_SEP}*\d{{2,4}}"
    rf"(?:{_SEP}*\d{{2,4}})?(?!\d)"
)
# Остаток: 10–12 цифр отдельным словом (можно с пробелами, скобками, дефисами) — телефон без +7.
# Точки не допускаем: так выглядят даты «01.2019-05.2021»; цифры внутри ссылок и номеров с буквами не берём.
LONG_DIGITS = re.compile(rf"(?<![\w./=:#{_DASH}])\d(?:[{_SPACE}(){_DASH}]{{0,2}}\d){{9,11}}(?![\w./{_DASH}])")
PROFILE_DOMAINS = (
    r"github\.com|gitlab\.com|t\.me|telegram\.me|vk\.com|linkedin\.com|hh\.ru/resume|behance\.net|"
    r"dribbble\.com|career\.habr\.com|habr\.com/(?:ru/)?users|instagram\.com|ok\.ru|facebook\.com|"
    r"leetcode\.com|kaggle\.com|codewars\.com|stepik\.org/users|figma\.com/@|wa\.me"
)
PROFILE_URL = re.compile(
    rf"(?i)(?:https?://)?(?:www\.)?(?:{PROFILE_DOMAINS})/?([^\s|)\]>,;\"'«»]*)"
)
# «@ник», «@@ник», «Телеграм@ник». Не ник: «@pytest.mark» и «@app.get(» (декораторы), часть email (латиница перед @).
NICK = re.compile(r"(?<![A-Za-z0-9_.@/])@+([A-Za-z][A-Za-z0-9_]{3,31})\b(?!\.\w|\()")
# Аннотации Java и декораторы Python в IT-резюме выглядят как ник, но ими не являются.
NOT_NICKS = {
    "override", "test", "component", "autowired", "service", "entity", "bean", "configuration",
    "controller", "restcontroller", "repository", "transactional", "data", "getter", "setter",
    "param", "return", "media", "import", "keyframes", "mail", "gmail", "yandex",
}

ARCHIVE_NAME = re.compile(r"ФИО[ \t]*\d+")
ARCHIVE_NUMBER = re.compile(r"Кандидат[ \t]*№[ \t]*\d+")
MAILTO = re.compile(r"(?:mailto:)+")
PERSON_LINE = re.compile(
    r"(?m)^[ \t]*(Мужчина|Женщина)"
    r"(?:,[ \t]*(\d{1,3})[ \t]*(?:год|года|лет))?"
    r"(?:,[ \t]*родил(?:ся|ась)[ \t]+(\d{1,2})[ \t]+([а-яё]+)[ \t]+(\d{4}))?"
    r"[ \t]*$"
)
MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
HEADER_LINES = 15  # строка «Женщина, 48 лет…» бывает только в шапке

# Подписанное поле: «Телефон: …», «Тг → …». Значение — до конца строки или до «|».
ALWAYS_LABELS = (
    r"телефон|тел\.?|моб(?:ильный)?\.?|whats\s?app|viber|e-?mail|почта|эл\.?\s*почта|электронная\s+почта|"
    r"telegram|телеграм|телега|тг|tg|фио|дата\s+рождения|д\.\s?р\.|возраст|пол"
)
# Эти подписи встречаются и в навыках («Git: уверенно»), поэтому значение скрываем,
# только если оно похоже на адрес (есть «/», «@», «.» или цифры).
LINK_LABELS = r"github|гитхаб|git|gitlab|vk|вк|вконтакте|linkedin|портфолио|portfolio|behance|сайт-портфолио"
# Разделитель после подписи: «:», «→» или тире с пробелами («Дата рождения – 01.02.2000»).
LABELED_FIELD = re.compile(
    rf"(?im)(?<![\w-])(?P<label>{ALWAYS_LABELS}|{LINK_LABELS})[ \t]*(?::|→|(?<=[ \t])[–—-](?=[ \t]))[ \t]*"
    rf"(?P<value>[^\n|]+)"
)
# Телефон после «Тел.» без двоеточия и без +7: «Тел. + (999) 00 00 00 00».
LABELED_PHONE = re.compile(
    rf"(?i)(?<![\w-])(?:тел(?:ефон)?|моб(?:ильный)?)\.?[ \t]*(?P<value>\+?[{_SPACE}]*\(?\d[\d{_SPACE}(){_DASH}.]{{8,}}\d)"
)
# Сайт на GitHub/GitLab Pages: поддомен — это ник («ivan-petrov.github.io»).
PAGES_URL = re.compile(r"(?i)(?:https?://)?([\w-]+)\.(?:github|gitlab)\.io\b[^\s|)\]>,;\"'«»]*")
# Любая ссылка: с протоколом/www или «домен.зона/путь». Решение — в _personal_url: скрываем ссылку с путём
# (файл на Google Drive, макет Figma, страница Notion ведут к человеку) и личный хостинг без пути.
# Сайт компании без пути («www.sibur.ru» после города в выгрузке hh) — не ПДн кандидата, остаётся.
# Слева не латиница и не точка: так берётся и «Москваyandex.ru/…» (город склеен со ссылкой в выгрузке hh).
ANY_URL = re.compile(
    r"(?<![A-Za-z0-9@.\-/_])(?P<scheme>https?://(?:www\.)?|www\.)?"
    r"(?P<host>(?:[A-Za-z0-9-]+\.)+(?P<tld>[A-Za-z]{2,}|рф))(?::\d{2,5})?"
    r"(?P<path>/[^\s|)\]>,;\"'«»]*)?",
    re.IGNORECASE,
)
URL_TLDS = {
    "ru", "com", "net", "org", "io", "me", "so", "site", "app", "dev", "рф", "su", "info", "pro", "tech",
    "online", "ai", "co", "us", "uk", "de", "by", "kz", "ua", "xyz", "biz", "ws", "page", "space", "store",
    "ae", "uz", "am", "ge", "kg", "az", "eu", "tv", "cc", "gg", "ly", "fm", "sh", "pl", "cz", "lt", "lv", "ee",
    "fi", "se", "nl", "fr", "it", "es", "il", "tr", "cn", "jp", "website", "link", "cloud", "digital",
}
# Хостинг личных страниц: поддомен — страница человека даже без пути.
PERSONAL_HOSTS = (
    "notion.site", "github.io", "gitlab.io", "netlify.app", "vercel.app", "tilda.ws", "wixsite.com",
    "carrd.co", "readymag.com", "taplink.cc", "narod.ru", "ucoz.ru", "pages.dev", "sites.google.com",
    "framer.app", "framer.website", "webflow.io", "wordpress.com", "blogspot.com", "tumblr.com",
    "herokuapp.com", "onrender.com", "pythonanywhere.com", "surge.sh", "glitch.me", "replit.app",
    "na4u.ru", "github.dev",
    # Динамический DNS: адрес домашнего сервера человека.
    "chickenkiller.com", "zapto.org", "ddns.net", "no-ip.org", "duckdns.org",
)
BIRTH_DATE_RESIDUE = re.compile(r"(?i)(?:дата рождения|д\.\s?р\.|г\.\s?р\.)[ \t]*[:–—-]?[ \t]*\d")

CAP = r"[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?"
FULL = rf"{CAP}(?:[ \t]+{CAP}){{0,2}}"
# Сильные подсказки: после них всегда имя, поэтому берём слова даже без словаря
# (редкие и придуманные имена словарь не знает).
STRONG_SIGNATURE = re.compile(rf"(?i:с уважением|с наилучшими пожеланиями)[ \t]*[,.!]?[ \t]*\n?[ \t]*({FULL})")
STRONG_INTRODUCTION = re.compile(rf"(?:[Мм]еня зовут|[Мм]о[её] имя)[ \t]*[—–-]?[ \t]+({FULL})")
# Слабые подсказки: после них бывает и не имя («Спасибо за внимание. Опыт…»), поэтому слово сверяем со словарём.
WEAK_SIGNATURE = re.compile(
    rf"(?i:хорошего дня|хорошего вечера|спасибо|благодарю)[^\n]{{0,40}}?[,.!]?[ \t]*\n?[ \t]*({FULL})"
)
WEAK_INTRODUCTION = re.compile(rf"(?m)(?:^|[.!,][ \t]*)[Яя](?:[ \t]*[—–-])?[ \t]+({FULL})")
EMPLOYER_AUTHOR = re.compile(rf"Автор:[ \t]+({FULL})")
EMPLOYER_DATED = re.compile(rf"(?m)^[ \t]*({FULL}),[ \t]*\d{{2}}\.\d{{2}}\.\d{{2,4}}")
PATRONYMIC = re.compile(rf"(?<!им\. )(?<!имени )\b({CAP}[ \t]+{CAP}[ \t]+[А-ЯЁ][а-яё]+(?:вич|вна|ична|чна))\b")
NAME_ONLY_LINE = re.compile(rf"{CAP}(?:[ \t]+{CAP}){{0,2}}")
CONTACT_NEARBY = re.compile(
    r"(?i)(?:telegram|телеграм|тг|tg|email|e-mail|почта|телефон|тел\.|github|phone)[ \t]*[:→—-]"
    r"|@[A-Za-z]|[\w.+-]+@[\w-]+\.\w+|\+7|t\.me/"
)
# Слова, которые словарь иногда считает фамилией, а в письме это обращение.
# И заголовки контактов, которые оказываются в одной строке с именем («Мария Телефон»).
NOT_NAMES = {
    "Ваш", "Ваша", "Ваше", "Вашей", "Вашего", "Добрый", "День", "Здравствуйте", "Уважаемый", "Уважаемые",
    "Телефон", "Тел", "Почта", "Телеграм", "Контакты", "Связь", "Резюме", "Портфолио", "Опыт", "Навыки",
    "Образование", "Обо", "Мне", "Команда",
}

EMPLOYER_BLOCK = re.compile(r"Автор:[ \t]|Отказ:[ \t]*не подходит|из \d+ обязательных требований")
HEADLINE_TXT = re.compile(r"(?m)^Резюме:[ \t]*(.+)$")
HEADLINE_DOCX = re.compile(r"(?m)^Желаемая должность и зарплата[ \t]*\n[ \t]*(.+)$")

NAME_TAGS = {"Name", "Surn", "Patr"}


# --- Словарь имён ------------------------------------------------------------

@lru_cache(maxsize=1)
def _morph():
    import pymorphy3
    return pymorphy3.MorphAnalyzer()


@lru_cache(maxsize=50_000)
def is_name_word(word: str) -> bool:
    """Есть ли у слова разбор «имя», «фамилия» или «отчество» в словаре pymorphy3."""
    if word in NOT_NAMES or len(word) < 3:
        return False
    return any(NAME_TAGS & parse.tag.grammemes for parse in _morph().parse(word))


@lru_cache(maxsize=50_000)
def name_forms(word: str) -> frozenset[str]:
    """Все падежные формы имени («Иван» → «Ивана», «Иваном»…) с заглавной буквы."""
    forms = {word}
    for parse in _morph().parse(word):
        if NAME_TAGS & parse.tag.grammemes:
            forms |= {form.word.capitalize() for form in parse.lexeme}
    return frozenset(forms)


# --- Сбор найденного ---------------------------------------------------------

@dataclass
class _Found:
    phones: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    nicks: set[str] = field(default_factory=set)
    name_words: set[str] = field(default_factory=set)       # имена кандидата и третьих лиц для маскировки
    full_name: str | None = None
    gender: str | None = None
    age: int | None = None
    birth_date: date | None = None
    extra: dict = field(default_factory=dict)

    def add_unique(self, values: list[str], value: str) -> None:
        value = value.strip()
        if value and value not in values:
            values.append(value)

    def add_nick(self, raw: str) -> None:
        """Ник из адреса: «https://github.com/ivan-petrov/repo» → «ivan-petrov», «@ivan» → «ivan»."""
        raw = re.sub(r"^\w+://", "", raw.strip()).strip("@")
        parts = [part for part in raw.split("/") if part]
        if len(parts) > 1 and "." in parts[0]:
            parts = parts[1:]  # первый сегмент — домен
        nick = parts[0].split("?")[0].lstrip("@") if parts else ""
        if len(nick) >= 4 and nick.casefold() not in NOT_NICKS and not re.fullmatch(r"[\d.]+", nick):
            self.nicks.add(nick)


def _find_names(text: str, found: _Found) -> None:
    """Шаг 4: имена по подсказкам. Позиции не меняем — только запоминаем слова."""
    def take(phrase: str, *, check_each: bool) -> list[str]:
        words = phrase.split()
        return [w for w in words if is_name_word(w)] if check_each else words

    # Сильные шаблоны: берём фразу целиком.
    for match in PATRONYMIC.finditer(text):
        words = take(match.group(1), check_each=False)
        found.name_words.update(words)
        found.full_name = found.full_name or " ".join(words)
    for pattern in (EMPLOYER_AUTHOR, EMPLOYER_DATED):  # рекрутеры, а не кандидат: в PiiData не пишем
        for match in pattern.finditer(text):
            if any(is_name_word(w) for w in match.group(1).split()):
                found.name_words.update(match.group(1).split())

    # Подсказки в письме. После сильных берём фразу целиком, после слабых — только слова из словаря имён.
    for pattern, check_each in (
        (STRONG_SIGNATURE, False), (STRONG_INTRODUCTION, False), (WEAK_SIGNATURE, True), (WEAK_INTRODUCTION, True),
    ):
        for match in pattern.finditer(text):
            words = [w for w in take(match.group(1), check_each=check_each) if w not in NOT_NAMES]
            if words:
                found.name_words.update(words)
                found.full_name = found.full_name or " ".join(words)

    # Отдельная строка «Имя Фамилия» рядом с контактами.
    lines = text.split("\n")
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not NAME_ONLY_LINE.fullmatch(stripped):
            continue
        words = stripped.split()
        if not any(is_name_word(w) for w in words):
            continue
        window = "\n".join(lines[max(0, index - 2):index + 4])
        words = [w for w in words if w not in NOT_NAMES]
        if words and CONTACT_NEARBY.search(window):
            found.name_words.update(words)
            found.full_name = found.full_name or " ".join(words)


def _header(text: str, found: _Found) -> str:
    """Шаг 2: шапка hh.ru."""
    labels = ARCHIVE_NAME.findall(text)
    if labels:
        found.extra["archive_label"] = labels[0]
    text = ARCHIVE_NAME.sub(MASK_NAME, text)

    numbers = ARCHIVE_NUMBER.findall(text)
    if numbers:
        found.extra["archive_number"] = numbers[0]
    text = ARCHIVE_NUMBER.sub(MASK_ARCHIVE_ID, text)

    text = MAILTO.sub("", text)

    lines = text.split("\n")
    for index in range(min(HEADER_LINES, len(lines))):
        match = PERSON_LINE.fullmatch(lines[index])
        if match is None:
            continue
        gender, age, day, month, year = match.groups()
        found.gender = "мужской" if gender == "Мужчина" else "женский"
        if age:
            found.age = int(age)
        if day and month in MONTHS:
            try:
                found.birth_date = date(int(year), MONTHS[month], int(day))
            except ValueError:
                found.extra["birth_date_raw"] = f"{day} {month} {year}"
        lines[index] = MASK_PERSON
        break
    return "\n".join(lines)


def _labeled_fields(text: str, found: _Found) -> str:
    """Шаг 3: значения подписанных полей."""
    def replace(match: re.Match) -> str:
        label = match.group("label").casefold()
        value = match.group("value").strip()
        if not value or value in MASKS:
            return match.group(0)
        # Адрес — есть «@», протокол, домен («name.ru») или длинное число. «Git: CI/CD» — навык.
        looks_like_address = bool(re.search(r"@|https?://|www\.|[a-z0-9-]\.[a-z]{2,}|\d{5,}", value, re.IGNORECASE))
        if re.fullmatch(LINK_LABELS, label) and not looks_like_address:
            return match.group(0)  # «Git: уверенно» — это навык, не контакт

        if re.match(r"telegram|телеграм|телега|тг|tg", label):
            found.add_unique(found.links, value)
            found.add_nick(value.split()[0])
        elif re.match(r"тел|моб|whats|viber", label):
            found.add_unique(found.phones, value)
        elif re.match(r"e-?mail|почта|эл|электрон", label):
            found.add_unique(found.emails, value)
            local = value.split("@")[0].strip()
            if "@" in value and len(local) >= 5:
                found.add_nick(local)
        elif label == "фио":
            words = [w for w in re.findall(CAP, value)]
            found.name_words.update(words)
            found.full_name = found.full_name or value
        elif re.match(r"дата|д\.", label):
            found.extra["birth_date_raw"] = value
        elif label == "возраст":
            digits = re.search(r"\d{1,3}", value)
            if digits:
                found.age = found.age or int(digits.group())
        elif label == "пол":
            found.gender = found.gender or value[:16]
        else:
            found.add_unique(found.links, value)
            found.add_nick(value)
        return match.group(0)[: match.start("value") - match.start(0)] + MASK_CONTACT

    def phone(match: re.Match) -> str:
        found.add_unique(found.phones, match.group("value"))
        return match.group(0)[: match.start("value") - match.start(0)] + MASK_CONTACT

    text = LABELED_FIELD.sub(replace, text)
    return LABELED_PHONE.sub(phone, text)


def _contacts(text: str, found: _Found) -> str:
    """Шаг 1: шаблоны контактов в любом месте текста."""
    def link(match: re.Match) -> str:
        found.add_unique(found.links, match.group(0))
        found.add_nick(match.group(1))
        return MASK_LINK

    def email(match: re.Match) -> str:
        found.add_unique(found.emails, match.group(0))
        local = match.group(0).split("@")[0]
        if len(local) >= 5:
            found.add_nick(local)
        return MASK_CONTACT

    def phone(match: re.Match) -> str:
        found.add_unique(found.phones, match.group(0))
        return MASK_CONTACT

    def nick(match: re.Match) -> str:
        if match.group(1).casefold() in NOT_NICKS:
            return match.group(0)
        found.add_nick(match.group(1))
        found.add_unique(found.links, "@" + match.group(1))
        return MASK_CONTACT

    def pages(match: re.Match) -> str:
        found.add_unique(found.links, match.group(0))
        found.add_nick(match.group(1))
        return MASK_LINK

    def personal_url(match: re.Match) -> str:
        url, host = match.group(0), match.group("host").casefold()
        explicit = match.group("scheme") is not None
        if not explicit and (match.group("host") != host or match.group("tld").casefold() not in URL_TLDS):
            return url  # «ASP.NET/Core», «Node.js/Express» — технологии, не ссылки
        has_path = bool((match.group("path") or "").strip("/"))  # «/#/» у SPA — тоже путь
        personal = any(host == suffix or host.endswith("." + suffix) for suffix in PERSONAL_HOSTS)
        if not (has_path or personal):
            return url
        found.add_unique(found.links, url)  # ник из такой ссылки не берём: «file», «d» — не ники
        return MASK_LINK

    text = PROFILE_URL.sub(link, text)
    text = PAGES_URL.sub(pages, text)
    text = EMAIL.sub(email, text)
    text = ANY_URL.sub(personal_url, text)
    text = PHONE.sub(phone, text)
    text = PHONE_INTL.sub(phone, text)
    return NICK.sub(nick, text)


def _names(text: str, found: _Found) -> str:
    """Шаг 5: имена во всех падежах и ники — по всему тексту."""
    forms: set[str] = set()
    for word in found.name_words:
        forms |= name_forms(word)
    if forms:
        alternatives = "|".join(sorted((re.escape(f) for f in forms), key=len, reverse=True))
        text = re.sub(rf"(?<![\w-])(?:{alternatives})(?![\w-])", MASK_NAME, text)
    for nick in sorted(found.nicks, key=len, reverse=True):
        if len(nick) >= 5:
            text = re.sub(rf"(?i)(?<![\w]){re.escape(nick)}(?![\w])", MASK_CONTACT, text)
    return text


def _check(text: str, found: _Found) -> None:
    """Шаг 6: в готовом тексте не должно остаться ничего из найденного."""
    lowered = text.casefold()
    for email in found.emails:
        if email.casefold() in lowered:
            raise RedactionError("PII_RESIDUE", "в очищенном тексте остался email")
    for nick in found.nicks:
        if len(nick) >= 5 and re.search(rf"(?i)(?<![\w]){re.escape(nick)}(?![\w])", text):
            raise RedactionError("PII_RESIDUE", "в очищенном тексте остался ник или адрес профиля")
    for word in found.name_words:
        if re.search(rf"(?<![\w-]){re.escape(word)}(?![\w-])", text):
            raise RedactionError("PII_RESIDUE", "в очищенном тексте осталось найденное имя")
    if EMAIL.search(text):
        raise RedactionError("PII_RESIDUE", "в очищенном тексте остался email")
    if PHONE.search(text) or LONG_DIGITS.search(text):
        raise RedactionError("PII_RESIDUE", "в очищенном тексте осталась цепочка цифр, похожая на телефон")
    if BIRTH_DATE_RESIDUE.search(text):
        raise RedactionError("PII_RESIDUE", "в очищенном тексте осталась дата рождения")
    if PERSON_LINE.search("\n".join(text.split("\n")[:HEADER_LINES])):
        raise RedactionError("PII_RESIDUE", "в шапке осталась строка с полом и возрастом")

    content = text
    for mask in MASKS:
        content = content.replace(mask, "")
    if len(re.sub(r"\s", "", content)) < MIN_CONTENT_CHARS:
        raise RedactionError("EMPTY_AFTER_REDACTION", "после очистки в резюме почти не осталось текста")


def _pii(found: _Found) -> PiiData:
    extra = dict(found.extra)
    if len(found.phones) > 1:
        extra["phones"] = found.phones[1:]
    if len(found.emails) > 1:
        extra["emails"] = found.emails[1:]
    data = {
        "full_name": found.full_name[:512] if found.full_name else None,
        "gender": found.gender,
        "birth_date": found.birth_date,
        "age": found.age,
        "phone": found.phones[0][:64] if found.phones else None,
        "email": found.emails[0][:256] if found.emails else None,
        "links": found.links,
        "extra": extra,
    }
    try:
        return PiiData(**data)
    except ValidationError:
        # Возраст вне 14–100 — ошибка в источнике; храним как есть в extra, а не теряем.
        extra["age_raw"] = data.pop("age")
        return PiiData(**data, age=None)


def _headline(text: str, file_format: FileFormat) -> str | None:
    pattern = HEADLINE_DOCX if file_format in (FileFormat.HH_DOCX, FileFormat.DOCX) else HEADLINE_TXT
    match = pattern.search(text)
    if match is None:
        return None
    headline = match.group(1).strip()
    return headline[:512] if headline and MASK_NAME not in headline else None


def redact(text: str, file_format: FileFormat) -> Redacted:
    """Отделить ПДн. Возвращает очищенный текст и `PiiData`; при сбое проверки — `RedactionError`."""
    found = _Found()
    _find_names(text, found)                # имена ищем по исходному тексту: позиции подсказок не сдвинуты
    redacted = _header(text, found)
    redacted = _labeled_fields(redacted, found)
    redacted = _contacts(redacted, found)
    redacted = _names(redacted, found)
    _check(redacted, found)

    warnings = []
    if EMPLOYER_BLOCK.search(text):
        warnings.append("employer_block_present")
    return Redacted(text=redacted, pii=_pii(found), headline=_headline(redacted, file_format), warnings=warnings)
