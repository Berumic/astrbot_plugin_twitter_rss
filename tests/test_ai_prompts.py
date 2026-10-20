import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock

from test_command_scope import Plugin


ROOT = Path(__file__).resolve().parents[1]


class PromptTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.plugin = Plugin()
        self.plugin.config = {}
        self.tweet = dict(author_name="Author", username="example", orig_body="作品です {body}",
                          orig_tags=["#作品"], local_images=["image.jpg"])
        self.rule = dict(text_filter_prompt="仅推送作品发布", must_include_image_tags=["插画"],
                         any_include_image_tags=["角色"], exclude_image_tags=["广告"])

    async def test_vision_prompts_preserve_dynamic_tags_and_contract(self):
        p = self.plugin
        p.config = {"ai_config": {"vision_system_prompt": "自定义图片角色", "vision_filter_instructions": "自定义识别 {literal}"}}
        p._call_llm = AsyncMock(return_value=json.dumps(dict(matched_must_tags=["插画"],
                                    matched_any_tags=["角色"], matched_exclude_tags=[], translated_body="作品")))
        result = await p._evaluate_vision_for_group(self.tweet, self.rule)
        args = p._call_llm.await_args.kwargs
        self.assertEqual(args["system_prompt"], "自定义图片角色")
        self.assertEqual(args["image_urls"], ["image.jpg"])
        for fragment in ("自定义识别 {literal}", "插画", "角色", "广告", self.tweet["orig_body"],
                         '"matched_must_tags"', '"matched_any_tags"', '"matched_exclude_tags"',
                         '"translated_body"', '"translated_tags"'):
            self.assertIn(fragment, args["prompt"])
        self.assertTrue(result["passed"])

    async def test_text_prompts_preserve_group_criteria_data_and_contract(self):
        p = self.plugin
        p.config = {"ai_config": {"text_system_prompt": "自定义文本角色", "text_filter_instructions": "只进行直译 {literal}"}}
        p._call_llm = AsyncMock(return_value='{"worth_pushing": false, "reason": "不满足标准"}')
        result = await p._evaluate_text_for_group(self.tweet, self.rule)
        args = p._call_llm.await_args.kwargs
        self.assertEqual(args["system_prompt"], "自定义文本角色")
        for fragment in ("只进行直译 {literal}", self.rule["text_filter_prompt"], "Author (@example)",
                         self.tweet["orig_body"], '"worth_pushing"', '"translated_body"',
                         '"translated_tags"', '"reason"'):
            self.assertIn(fragment, args["prompt"])
        self.assertFalse(result["worth_pushing"])

    async def test_missing_empty_or_whitespace_prompts_use_defaults(self):
        p = self.plugin
        p._call_llm = AsyncMock(return_value='{}')
        for method, kind in ((p._evaluate_vision_for_group, "vision"), (p._evaluate_text_for_group, "text")):
            p.config = {}
            await method(self.tweet, self.rule)
            baseline = p._call_llm.await_args.kwargs
            for blank in ("", " \n ", None):
                p.config = {"ai_config": {f"{kind}_system_prompt": blank, f"{kind}_filter_instructions": blank}}
                await method(self.tweet, self.rule)
                self.assertEqual(p._call_llm.await_args.kwargs, baseline)

    async def test_schema_defaults_match_runtime_and_flat_settings_work(self):
        items = json.loads((ROOT / "_conf_schema.json").read_text(encoding="utf-8-sig"))["ai_config"]["items"]
        for kind in ("vision", "text"):
            for suffix in ("system_prompt", "filter_instructions"):
                key = f"{kind}_{suffix}"
                self.assertEqual(items[key]["type"], "text")
                self.assertEqual(self.plugin._get_ai_prompt(key), items[key]["default"])
                self.plugin.config[key] = "兼容顶层设置"
                self.assertEqual(self.plugin._get_ai_prompt(key), "兼容顶层设置")


if __name__ == "__main__":
    unittest.main()
