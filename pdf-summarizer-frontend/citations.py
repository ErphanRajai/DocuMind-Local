"""Turn source markers into links using API metadata, never model URLs."""

import re


def source_map(sources):
    valid = {}
    for source in sources or []:
        if (isinstance(source, dict) and re.fullmatch(r"S[1-9]\d*", str(source.get("id", "")))
                and type(source.get("pdf_id")) is int and source["pdf_id"] > 0
                and type(source.get("page")) is int and source["page"] > 0):
            valid[source["id"]] = source
    return valid


def source_url(source, backend_url):
    return f"{backend_url.rstrip('/')}/summarizer/documents/{source['pdf_id']}/view?page={source['page']}"


def markdown_label(text):
    return re.sub(r"([\\`*_{}\[\]()<>#!|])", r"\\\1", str(text).replace("\n", " ").replace("\r", " "))


def cited_markdown(answer, sources, backend_url):
    valid = source_map(sources)

    def link(match):
        key = match.group(1).upper()
        source = valid.get(key)
        if source is None:
            return match.group(0)
        label = f"{int(key[1:])} · p. {source['page']}"
        title = markdown_label(f"{source.get('filename', 'PDF')} · PDF page {source['page']}").replace('"', "'")
        return f'[{label}]({source_url(source, backend_url)} "{title}")'

    # Leave code, existing Markdown links, and images unchanged. A model marker
    # in code is an example, not a clickable evidence claim.
    parts = re.split(r"(```[\s\S]*?(?:```|$)|`[^`]*`|!?\[[^\]]*\]\([^\n)]*\))", answer)
    return "".join(part if index % 2 else re.sub(r"\[(S[1-9]\d*)\]", link, part, flags=re.I)
                   for index, part in enumerate(parts))
