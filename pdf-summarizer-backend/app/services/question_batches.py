"""Recognize explicit numbered question lists without asking a model to split them."""
import re

from .errors import GenerationError
from .citations import canonical_citations

_DIGITS = str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789')
_NUMBER = re.compile(r'(?<!\S)(?:(?:Question|Q|سؤال|سوال|پرسش|السؤال)\s*)?(\d{1,3})\s*[.)：:、-]\s+(?=\S)', re.I)


def numbered_questions(text):
    """Only a contiguous list starting at 1 is a batch; keep original wording/digits."""
    if '```' in text:
        return []
    matches = list(_NUMBER.finditer(text.translate(_DIGITS)))
    if len(matches) < 2 or [int(m[1]) for m in matches] != list(range(1, len(matches) + 1)):
        return []
    parts = [text[m.end():matches[i + 1].start() if i + 1 < len(matches) else len(text)].strip() for i, m in enumerate(matches)]
    # Ordinary numeric data or an answer-format list is not enough evidence of questions.
    if any(not re.search(r'[A-Za-z\u0600-\u06ff\u4e00-\u9fff]', p) for p in parts):
        return []
    if len(parts) > 20:
        raise GenerationError('Send at most 20 numbered questions at a time. No questions were omitted.')
    directive = text[:matches[0].start()].strip()
    return [{'number':i + 1, 'text':p, 'directive':directive} for i, p in enumerate(parts)]


def remap_citations(text, mapping):
    """Keep per-question source markers unique in the combined answer."""
    pieces = re.split(r'(```[\s\S]*?(?:```|$)|`[^`]*`|\$\$[\s\S]*?(?:\$\$|$)|\$[^$\n]+\$)', text)
    for index in range(0, len(pieces), 2):
        pieces[index] = re.sub(r'\[(S\d+)\]', lambda m: '[' + mapping[m[1]] + ']' if m[1] in mapping else '[unverified source]', pieces[index])
    return ''.join(pieces)


class CitationStream:
    """Emit live text while holding only an unfinished source marker.

    Closing Markdown code/math can change how earlier brackets are interpreted.
    Rare corrections replace the draft; ordinary model chunks remain deltas.
    """
    def __init__(self, mapping):
        self.mapping = mapping
        self.raw = ''
        self.rendered = ''

    def feed(self, chunk='', *, final=False):
        self.raw += chunk
        ready = self.raw
        pending = re.search(r'\[\s*(?:[Ssس]\s*[0-9۰-۹٠-٩]*\s*)?$', ready)
        if not final and pending and len(pending[0]) <= 64:
            ready = ready[:pending.start()]
        current = remap_citations(canonical_citations(ready), self.mapping)
        if current == self.rendered:
            return None
        replace = not current.startswith(self.rendered)
        content = current if replace else current[len(self.rendered):]
        self.rendered = current
        return content, replace
