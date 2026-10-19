import copy
import html
from pathlib import Path
import re
import unittest
from jinja2 import Environment

from furigana import annotate_original, ruby_text


def visible_original(markup):
    markup = re.sub(r"<rt>.*?</rt>|<rp>.*?</rp>", "", markup)
    return html.unescape(re.sub(r"</?ruby>", "", markup))


class FuriganaTests(unittest.TestCase):
    def test_kanji_readings_and_okurigana(self):
        result = ruby_text("食べる、学校へ行きます。")
        self.assertIn("<ruby>食<rp>(</rp><rt>た</rt><rp>)</rp></ruby>べる", result)
        self.assertIn("<rt>がっこう</rt>", result)
        self.assertEqual(visible_original(result), "食べる、学校へ行きます。")

    def test_switch_between_hiragana_and_romaji_without_changing_original(self):
        text = "食べる、学校へ行きます。\nhttps://example.org/作品?q=漢字&v=1"
        kana = ruby_text(text)
        romaji = ruby_text(text, style="罗马音")
        self.assertIn("<rt>がっこう</rt>", kana)
        self.assertIn("<rt>gakkou</rt>", romaji)
        self.assertIn("<ruby>食<rp>(</rp><rt>ta</rt><rp>)</rp></ruby>べる", romaji)
        self.assertEqual(visible_original(romaji), text)
        self.assertEqual(ruby_text(text), kana)
        self.assertEqual(ruby_text(text, style="unknown"), kana)

    def test_romaji_applies_to_body_tags_and_quote_only(self):
        data = dict(orig_body="学校へ行きます。", orig_tags=["#学校"],
                    translated_body="去学校。", translated_tags=["#学校"],
                    quote_info={"orig_body": "学校へ行きます。", "orig_tags": ["#学校"]})
        before = copy.deepcopy(data)
        result = annotate_original(data, style="罗马音")
        for block in (result, result["quote_info"]):
            for key in ("orig_body_ruby", "orig_tags_ruby"):
                self.assertIn("<rt>gakkou</rt>", block[key])
        self.assertEqual(result["translated_body"], data["translated_body"])
        self.assertEqual(result["translated_tags"], data["translated_tags"])
        self.assertEqual(data, before)

    def test_styled_characters_and_urls_are_preserved(self):
        text = "ʕ̢·͡˔·Ɂ̡̣ ⋈ 𝙉𝙚𝙬 𝘼𝙡𝙗𝙪𝙢 ⋈ 日本の音楽です。\nhttps://example.org/作品?q=漢字&v=1"
        result = ruby_text(text)
        self.assertIn("<ruby>", result)
        self.assertIn("𝙉𝙚𝙬 𝘼𝙡𝙗𝙪𝙢", result)
        self.assertIn("https://example.org/作品?q=漢字&amp;v=1", result)
        self.assertEqual(visible_original(result), text)

    def test_non_japanese_and_html_injection(self):
        self.assertEqual(ruby_text("今天发表新作品"), "今天发表新作品")
        self.assertEqual(ruby_text("English 123"), "English 123")
        self.assertNotIn("<script>", ruby_text("<script>日本の作品です</script>"))
        self.assertIn("&lt;script&gt;", ruby_text("<script>日本の作品です</script>"))

    def test_main_and_quote_are_independent_translation_is_untouched(self):
        data = dict(orig_body="日本の作品です。", orig_tags=["#新作"], translated_body="新的作品",
                    translated_tags=["#新作品"], quote_info={"orig_body": "中文内容", "orig_tags": []})
        before = copy.deepcopy(data)
        result = annotate_original(data)
        self.assertEqual(data, before)
        self.assertIn("<ruby>", result["orig_body_ruby"])
        self.assertIn("<ruby>", result["orig_tags_ruby"])
        self.assertNotIn("orig_body_ruby", result["quote_info"])
        self.assertEqual(result["quote_info"]["orig_body"], "中文内容")
        self.assertEqual(result["translated_body"], data["translated_body"])
        self.assertEqual(result["translated_tags"], data["translated_tags"])

    def test_templates_with_and_without_annotation(self):
        template = Environment(autoescape=True).from_string(
            (Path(__file__).resolve().parents[1] / "templates/tweet_card.html").read_text(encoding="utf-8"))
        data = dict(orig_body="新しい作品です。", orig_tags=[], translated_body="新作品", translated_tags=[],
                    quote_info={"orig_body": "明日は学校へ行きます。"})
        enabled = template.render(**annotate_original(data))
        disabled = template.render(**data)
        self.assertIn("<ruby>", enabled)
        self.assertNotIn("&lt;ruby&gt;", enabled)
        self.assertNotIn("<ruby>", disabled)
        self.assertIn('class="trans-body">新作品</div>', enabled)


if __name__ == "__main__":
    unittest.main()
