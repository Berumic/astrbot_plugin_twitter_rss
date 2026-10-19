"""Generate escaped ruby markup for Japanese originals using an offline dictionary."""
import copy
from functools import lru_cache
import html
import re
import threading


_KANA = re.compile(r"[\u3041-\u3096\u30a1-\u30fa\uff66-\uff9f]")
_KANJI = re.compile(r"[\u3400-\u9fff\uf900-\ufaff\U00020000-\U000323af々〆〇]")
_URL = re.compile(r"https?://[^\s<>]+", re.I)
_JP_RUN = re.compile(r"[\u3041-\u3096\u30a1-\u30fa\uff66-\uff9f\u3400-\u9fff\uf900-\ufaff\U00020000-\U000323af々〆〇ー]+")
_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def _converter():
    from pykakasi import kakasi
    return kakasi()


def _ruby_word(word, reading):
    if not _KANJI.search(word) or not reading or not re.fullmatch(r"[\u3041-\u3096ー]+", reading):
        return html.escape(word)
    # Leave kana prefixes/okurigana outside ruby where the dictionary aligns them.
    left, right = 0, 0
    while left < min(len(word), len(reading)) and word[left] == reading[left]:
        left += 1
    while right < min(len(word)-left, len(reading)-left) and word[-right-1] == reading[-right-1]:
        right += 1
    base = word[left:len(word)-right if right else None]
    kana = reading[left:len(reading)-right if right else None]
    if not base or not kana or not _KANJI.search(base):
        return html.escape(word)
    return (html.escape(word[:left]) + "<ruby>" + html.escape(base)
            + "<rp>(</rp><rt>" + html.escape(kana) + "</rt><rp>)</rp></ruby>"
            + (html.escape(word[-right:]) if right else ""))


@lru_cache(maxsize=512)
def ruby_text(text, japanese=False):
    """Return trusted markup; raw text, URL contents and special styles are preserved."""
    if not japanese and not _KANA.search(text):
        return html.escape(text)
    if not _KANJI.search(text):
        return html.escape(text)
    parts = []
    # URL contents must never be segmented or annotated.
    cursor = 0
    for match in list(_URL.finditer(text)) + [None]:
        end = match.start() if match else len(text)
        chunk = text[cursor:end]
        offset = 0
        for run in _JP_RUN.finditer(chunk):
            parts.append(html.escape(chunk[offset:run.start()]))
            original = run.group()
            with _LOCK:
                tokens = _converter().convert(original)
            # Never let dictionary normalization change the original characters.
            if "".join(token["orig"] for token in tokens) != original:
                parts.append(html.escape(original))
            else:
                parts.extend(_ruby_word(token["orig"], token.get("hira", "")) for token in tokens)
            offset = run.end()
        parts.append(html.escape(chunk[offset:]))
        if match:
            parts.append(html.escape(match.group()))
            cursor = match.end()
    return "".join(parts)


def annotate_original(payload):
    """Annotate original body/tags independently for the tweet and quoted tweet."""
    result = copy.deepcopy(payload)
    for block in (result, result.get("quote_info")):
        if not isinstance(block, dict):
            continue
        body = str(block.get("orig_body") or "")
        tags = block.get("orig_tags") or []
        japanese = bool(_KANA.search(_URL.sub("", body + " " + " ".join(tags))))
        body_markup = ruby_text(body, japanese)
        tags_markup = " ".join(ruby_text(tag, japanese) for tag in tags)
        if "<ruby>" in body_markup:
            block["orig_body_ruby"] = body_markup
        if "<ruby>" in tags_markup:
            block["orig_tags_ruby"] = tags_markup
    return result
