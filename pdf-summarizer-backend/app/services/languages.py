"""Small deterministic language helpers; no network detector or document upload."""
import re
import unicodedata

DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
NAMES = {'fa':'Persian (فارسی)', 'ar':'Arabic', 'en':'English', 'es':'Spanish', 'fr':'French', 'de':'German',
         'tr':'Turkish', 'ur':'Urdu', 'hi':'Hindi', 'zh':'Chinese', 'ja':'Japanese', 'ko':'Korean', 'ru':'Russian', 'pt':'Portuguese'}


def normalize_digits(text):
    return text.translate(DIGITS).replace('٫','.').replace('−','-').translate(dict.fromkeys(map(ord,'\u200e\u200f\u2066\u2067\u2068\u2069')))


def normalize_document_text(text):
    # Arabic presentation forms are glyph encodings, not different language words.
    return unicodedata.normalize('NFKC', text).replace('\u00a0',' ')


def detect_language(text):
    if re.search('[پچژگکی]|[۰-۹]', text): return 'fa'
    if re.search('[\u0600-\u06ff]', text): return 'ar'
    if re.search('[\u3040-\u30ff]', text): return 'ja'
    if re.search('[\u4e00-\u9fff]', text): return 'zh'
    if re.search('[\uac00-\ud7af]', text): return 'ko'
    if re.search('[\u0400-\u04ff]', text): return 'ru'
    if re.search('[\u0900-\u097f]', text): return 'hi'
    return 'auto'


def language_instruction(language='auto', text=''):
    selected = detect_language(text) if language == 'auto' else language
    name = NAMES.get(selected, selected)
    output = f'Write the answer and explanations in {name}.' if selected != 'auto' else 'Write in the language of the current question; follow an explicit translation request.'
    return (output + ' Never switch to English merely because reference notes or tool labels are English. '
            'Automatically typeset mathematical expressions with $...$ inline and $$...$$ on separate lines for display equations. '
            'Use standard LaTeX commands, Latin mathematical variables and digits inside equations; keep prose in the answer language. '
            'Keep [S1] source markers unchanged and outside equations. Do not translate a verbatim quotation. '
            'If evidence is missing or contradictory, explain that in the answer language rather than guessing.')


def localize_calculation(markdown, language):
    if language != 'fa': return markdown
    replacements = {'Calculated result':'نتیجهٔ محاسبه', 'Method':'روش حل', 'Checks':'بررسی‌ها', 'passed':'درست',
        'not verified':'تأیید نشده', 'Domain: real.':'دامنه: اعداد حقیقی.', 'Domain: complex.':'دامنه: اعداد مختلط.',
        'Trigonometric arguments use radians.':'زاویه‌های توابع مثلثاتی بر حسب رادیان هستند.',
        'Symbolic checks apply on the common defined domain; this is not a proof checker.':'بررسی نمادی در دامنهٔ تعریف مشترک انجام می‌شود؛ این ابزار اثبات عمومی نیست.',
        'Solve over the real numbers.':'معادله را در اعداد حقیقی حل می‌کنیم.',
        'Solve over the complex numbers.':'معادله را در اعداد مختلط حل می‌کنیم.',
        'Check each finite candidate by substitution; domain restrictions still apply.':'هر جواب با جای‌گذاری در معادلهٔ اصلی بررسی می‌شود؛ محدودیت‌های دامنه همچنان معتبرند.',
        'Write the equation as':'معادله را به این صورت می‌نویسیم:', 'Factor:':'تجزیه:',
        'Quadratic coefficients:':'ضرایب معادلهٔ درجهٔ دوم:', 'The discriminant is':'ممیّز برابر است با',
        'Dimensions match':'ابعاد واحدها سازگارند', 'Substitute x =':'جای‌گذاری x =',
        'Input:':'ورودی:', 'Differentiate the antiderivative':'مشتق‌گیری از پادمشتق',
        'Derivative agrees after symbolic round trip':'مشتق در بررسی نمادی سازگار است',
        'The unit registry checked dimensional compatibility.':'سامانهٔ واحدها سازگاری ابعاد را بررسی کرد.',
        'Numerical approximation, 12 significant digits':'تقریب عددی با ۱۲ رقم معنادار'}
    for source,target in replacements.items(): markdown = markdown.replace(source,target)
    markdown = re.sub(r'Apply (\w+) with respect to (\w), where applicable\.', lambda m: f'عملیات {m[1]} را نسبت به {m[2]} اعمال می‌کنیم.', markdown)
    return markdown
