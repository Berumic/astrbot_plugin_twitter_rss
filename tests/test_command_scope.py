"""Exercise actual plugin methods without starting AstrBot or making network calls."""
import ast
import asyncio
import base64
import copy
import datetime
import logging
import pathlib
from pathlib import Path
import random
import re
import time
from types import SimpleNamespace
import unittest
import httpx
from furigana import annotate_original
from unittest.mock import AsyncMock, Mock, patch


def load_plugin_methods():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8-sig"))
    wanted = {
        "_get_setting", "_get_group_rules", "_clean_str_list", "_extract_clean_handle",
        "_get_rule_accounts", "_get_rule_hashtags", "_tweet_identity", "_resolve_target_umo",
        "_record_event_umo", "_find_or_create_group_rule", "check_all_accounts",
        "test_push_for_group", "tw_test", "tw_check", "run_daily_digest", "_matches_rule_subscription",
        "_render_font_css", "push_tweet_to_umo", "_send_to_umo",
        "_validate_rendered_image_sync", "_render_html_to_image", "_http_get_with_recovery",
        "_init_http_client", "_normalize_proxy_url", "_fetch_feed_response", "_feed_host",
        "_feed_hosts", "_cool_down_feed",
        "_digest_tick", "_set_account_unavailable", "tw_list",
        "_account_availability_suffix", "_ingest_account_switches_from_rules",
        "_account_switch_panels", "_format_override_summary", "_parse_switch_mode",
    }
    original = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "TwitterRssPlugin")
    methods = [n for n in original.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in wanted]
    for method in methods:
        if method.name.startswith("tw_"):
            method.decorator_list = []
    sections = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CONFIG_SECTIONS" for t in n.targets))
    module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
                             ast.ClassDef(name="Plugin", bases=[], keywords=[], body=methods, decorator_list=[])], type_ignores=[])
    namespace = dict(asyncio=asyncio, copy=copy, random=random, re=re, base64=base64, httpx=httpx,
                     annotate_original=annotate_original,
                     __file__=str(Path(__file__).resolve().parents[1] / "main.py"),
                     TWEET_CARD_TMPL="tweet-template",
                     time=time, datetime=datetime, pathlib=pathlib,
                     MACARON_PALETTES=[{}], DAILY_DIGEST_TMPL="digest-template",
                     _clean_digest_text=lambda text, **kwargs: text,
                     _compute_harmonious_digest_theme=lambda items, theme: (theme, theme, theme),
                     MessageChain=lambda items: items,
                     logger=logging.getLogger("scope-tests"), CONFIG_SECTIONS=ast.literal_eval(sections.value))
    exec(compile(ast.fix_missing_locations(module), "main.py (extracted methods)", "exec"), namespace)
    return namespace["Plugin"]


Plugin = load_plugin_methods()


class Event:
    unified_msg_origin = "platform:GroupMessage:A"

    def get_group_id(self):
        return "A"

    def plain_result(self, text):
        return text


class CommandScopeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.rule = dict(group_name="A", target_umo=Event.unified_msg_origin,
                         twitter_accounts=["alice", "bob", "carol", "dave"], twitter_hashtags=["art"])
        self.other = dict(group_name="B", target_umo="platform:GroupMessage:B", twitter_accounts=["foreign"])
        self.plugin = p = Plugin()
        p.config = {"group_subscriptions": [self.rule, self.other]}
        p.state = {}
        p.history_tweets = []
        p._lock = asyncio.Lock()
        p._not_found_accounts = set()
        p._should_skip_tweet = Mock(return_value=False)
        p._prepare_tweet_media = AsyncMock(side_effect=lambda tweet: tweet)
        p.evaluate_tweet_for_group = AsyncMock(side_effect=lambda tweet, rule: (True, tweet))
        p.push_tweet_to_umo = AsyncMock(return_value=True)
        p._save_state = AsyncMock()
        p._save_history = AsyncMock()
        p._save_plugin_config = Mock()
        p._sync_subscribed_accounts_to_schema = Mock()
        p._has_admin_permission = Mock(return_value=True)
        p._fetch_account_tweets = AsyncMock(side_effect=self.tweets)
        p._fetch_hashtag_tweets = AsyncMock(side_effect=lambda tag: self.tweets("#" + tag))

    async def test_missing_account_is_retained_during_check_and_test(self):
        p = self.plugin
        before = copy.deepcopy(p.config)
        async def missing(account):
            await p._set_account_unavailable(account, True)
            return []
        p._fetch_account_tweets = AsyncMock(side_effect=missing)
        p._fetch_hashtag_tweets = AsyncMock(return_value=[])
        await p.check_all_accounts(manual=True, target_rule=self.rule)
        await p.test_push_for_group(self.rule, limit=1, target_account="alice")
        self.assertEqual(p.config, before)
        p._save_plugin_config.assert_not_called()
        self.assertIn("alice", p.state["unavailable_accounts"])

    async def test_settings_mark_missing_account_without_changing_handle_or_switches(self):
        p = self.plugin
        p.state["unavailable_accounts"] = {"alice": "疑似不存在或暂不可用"}
        p._ingest_account_switches_from_rules()
        self.assertEqual(self.rule["twitter_accounts"][0], "alice [疑似不存在或暂不可用]")
        self.assertEqual(p._get_rule_accounts(self.rule)[0], "alice")
        self.assertEqual(self.rule["account_switches"]["account"], "alice [疑似不存在或暂不可用]")
        self.assertIn("ov_alice__push_image", self.rule["account_switches"])
        await p._set_account_unavailable("alice", False)
        p._sync_subscribed_accounts_to_schema.assert_called_once()
        p._ingest_account_switches_from_rules()
        self.assertEqual(self.rule["twitter_accounts"][0], "alice")
        self.assertEqual(self.rule["account_switches"]["account"], "alice")

    async def test_account_status_is_persisted_and_cleared_on_recovery(self):
        p = self.plugin
        await p._set_account_unavailable("@Alice", True)
        self.assertIn("alice", p.state["unavailable_accounts"])
        p._save_state.assert_awaited_once()
        await p._set_account_unavailable("ALICE", False)
        self.assertNotIn("alice", p.state["unavailable_accounts"])
        self.assertNotIn("alice", p._not_found_accounts)
        self.assertEqual(p._save_state.await_count, 2)

    async def test_subscription_list_displays_persisted_warning(self):
        p = self.plugin
        p.state["unavailable_accounts"] = {"alice": "疑似不存在或暂不可用"}
        p._format_account_with_overrides = Mock(side_effect=lambda a, r: "@" + a)
        p._get_global_type_defaults = Mock(return_value=dict.fromkeys(
            ["retweet", "quote_retweet", "reply", "text", "image"], True))
        messages = [m async for m in p.tw_list(Event())]
        self.assertIn("@alice ⚠️ [疑似不存在或暂不可用]", messages[0])
        self.assertNotIn("@bob ⚠️", messages[0])

    @staticmethod
    def tweets(account):
        return [dict(id=f"{account}-{i}", username=account) for i in range(5)]

    async def test_random_count_limits_sources_and_one_tweet_per_source(self):
        p = self.plugin
        stats = await p.test_push_for_group(self.rule, limit=3)
        fetched = [c.args[0] for c in p._fetch_account_tweets.await_args_list]
        fetched += ["#" + c.args[0] for c in p._fetch_hashtag_tweets.await_args_list]
        self.assertEqual(len(fetched), 3)
        self.assertTrue(set(fetched) <= {"alice", "bob", "carol", "dave", "#art"})
        self.assertEqual(stats["sampled"], 3)
        self.assertEqual({c.args[0]["username"] for c in p.evaluate_tweet_for_group.await_args_list}, set(fetched))
        self.assertTrue(all(c.args[1] == self.rule["target_umo"] for c in p.push_tweet_to_umo.await_args_list))

    async def test_failed_or_empty_sources_do_not_expand_sample(self):
        p = self.plugin
        p._fetch_account_tweets = AsyncMock(side_effect=[RuntimeError("timeout"), []])
        with patch.object(random, "sample", side_effect=lambda pool, k: list(pool)[:k]):
            stats = await p.test_push_for_group(self.rule, limit=2)
        self.assertEqual(p._fetch_account_tweets.await_count, 2)
        p._fetch_hashtag_tweets.assert_not_awaited()
        self.assertEqual(stats["sampled"], 0)

    async def test_type_filter_does_not_fetch_replacements(self):
        p = self.plugin
        p._should_skip_tweet.return_value = True
        stats = await p.test_push_for_group(self.rule, limit=2)
        self.assertEqual(stats["subscriptions"], 2)
        self.assertEqual(stats["sampled"], 0)
        p.evaluate_tweet_for_group.assert_not_awaited()

    async def test_duplicate_tweet_does_not_expand_source_selection(self):
        p = self.plugin
        p._fetch_account_tweets.side_effect = lambda _: [dict(id="same", username="alice")]
        with patch.object(random, "sample", side_effect=lambda pool, k: list(pool)[:k]):
            stats = await p.test_push_for_group(self.rule, limit=2)
        self.assertEqual(stats["subscriptions"], 2)
        self.assertEqual(stats["sampled"], 1)

    async def test_explicit_account_fetches_once_and_samples_two_tweets(self):
        p = self.plugin
        stats = await p.test_push_for_group(self.rule, limit=2, target_account="@specified")
        p._fetch_account_tweets.assert_awaited_once_with("specified")
        p._fetch_hashtag_tweets.assert_not_awaited()
        self.assertEqual(stats["sampled"], 2)

    async def test_check_fetches_and_processes_only_target_group(self):
        p = self.plugin
        with self.assertLogs("scope-tests", level="INFO") as logs:
            stats = await p.check_all_accounts(manual=True, target_rule=self.rule)
        self.assertEqual({c.args[0] for c in p._fetch_account_tweets.await_args_list}, {"alice", "bob", "carol", "dave"})
        p._fetch_hashtag_tweets.assert_awaited_once_with("art")
        self.assertGreater(stats["pushed"], 0)
        self.assertTrue(all(c.args[1] is self.rule for c in p.evaluate_tweet_for_group.await_args_list))
        self.assertTrue(all(c.args[1] == self.rule["target_umo"] for c in p.push_tweet_to_umo.await_args_list))
        self.assertNotIn(self.other["target_umo"], str(p.state))
        self.assertIn("手动检查 群[A]", "\n".join(logs.output))

    async def test_manual_check_cannot_fall_back_to_global(self):
        with self.assertRaises(ValueError):
            await self.plugin.check_all_accounts(manual=True)
        self.plugin._fetch_account_tweets.assert_not_awaited()

    async def test_background_scan_still_includes_all_groups(self):
        with self.assertLogs("scope-tests", level="INFO") as logs:
            await self.plugin.check_all_accounts()
        self.assertIn("foreign", [c.args[0] for c in self.plugin._fetch_account_tweets.await_args_list])
        self.assertIn("后台扫描 全部群聊", "\n".join(logs.output))

    async def test_check_command_passes_current_group(self):
        self.plugin.check_all_accounts = AsyncMock(return_value=dict(fetched=0, new=0, pushed=0))
        _ = [text async for text in self.plugin.tw_check(Event())]
        self.plugin.check_all_accounts.assert_awaited_once_with(manual=True, target_rule=self.rule)

    async def test_test_command_parses_both_count_forms(self):
        p = self.plugin
        stats = dict(fetched=5, sampled=2, evaluated=2, pushed=2, filtered=0, failed=0, subscriptions=2)
        p.test_push_for_group = AsyncMock(return_value=stats)
        _ = [text async for text in p.tw_test(Event(), "2")]
        p.test_push_for_group.assert_awaited_once_with(group_rule=self.rule, limit=2, target_account="")
        p.test_push_for_group.reset_mock()
        _ = [text async for text in p.tw_test(Event(), "@specified", "2")]
        p.test_push_for_group.assert_awaited_once_with(group_rule=self.rule, limit=2, target_account="specified")

    async def test_unbound_commands_never_claim_template_or_scan(self):
        p = self.plugin
        template = dict(group_name="template", target_umo="", twitter_accounts=["template_account"])
        p.config["group_subscriptions"] = [template, self.other]
        before = copy.deepcopy(p.config)
        p.check_all_accounts = AsyncMock()
        p.test_push_for_group = AsyncMock()
        for command in (p.tw_check, p.tw_test):
            messages = [text async for text in command(Event())]
            self.assertIn("未绑定", messages[0])
        p.check_all_accounts.assert_not_awaited()
        p.test_push_for_group.assert_not_awaited()
        p._save_plugin_config.assert_not_called()
        self.assertEqual(p.config, before)

    async def test_busy_command_reports_queue_before_fetching(self):
        p = self.plugin
        await p._lock.acquire()
        command = p.tw_test(Event(), "2")
        try:
            message = await command.__anext__()
            self.assertIn("已排队", message)
            self.assertIn("尚未开始抓取", message)
            p._fetch_account_tweets.assert_not_awaited()
            p._fetch_hashtag_tweets.assert_not_awaited()
        finally:
            p._lock.release()
            await command.aclose()

    async def test_digest_renders_archives_and_sends_local_subscription_count(self):
        p = self.plugin
        p.history_tweets = [dict(id="1", username="alice", timestamp=time.time()-60, text="new work"),
                            dict(id="2", username="foreign", timestamp=time.time()-60, text="other group")]
        p._call_llm = AsyncMock(return_value="result")
        p._extract_json_dict = Mock(return_value={"items": [{"tweet_index": 0, "title": "new work", "summary": "summary"}]})
        p._render_html_to_image = AsyncMock(return_value="digest.png")
        p._archive_daily_digest = AsyncMock(return_value="archived.png")
        p._make_image_comp = Mock(side_effect=lambda path: path)
        p.context = SimpleNamespace(send_message=AsyncMock())
        for tag_only in (False, True):
            with self.subTest(tag_only=tag_only):
                if tag_only:
                    self.rule["twitter_accounts"] = []
                    p.history_tweets[0]["subscription_hashtags"] = ["art"]
                    p._extract_json_dict.return_value = {}  # Also exercise AI fallback.
                ok, path = await p.run_daily_digest(target_rule=self.rule)
                self.assertTrue(ok)
                data = p._render_html_to_image.await_args.args[1]
                self.assertEqual(data["account_count"], 1 if tag_only else 5)
                self.assertEqual(data["total_count"], 1)
                self.assertEqual(len(data["items"]), 1)
                self.assertEqual(p._archive_daily_digest.await_args.kwargs["render_data"], data)
                self.assertEqual(p.context.send_message.await_args.args[0], self.rule["target_umo"])

    async def test_scheduled_digest_freezes_window_and_saves_edition_before_render(self):
        p = self.plugin
        edition = datetime.datetime.now().replace(microsecond=0)
        p.history_tweets = [
            dict(id="before", username="alice", timestamp=edition.timestamp()-60, text="included"),
            dict(id="after", username="alice", timestamp=edition.timestamp()+60, text="excluded"),
        ]
        p._call_llm = AsyncMock(return_value="result")
        p._extract_json_dict = Mock(return_value={"items": [{"tweet_index": 0, "title": "news", "summary": "summary"}]})
        p._archive_daily_digest = AsyncMock(return_value="archive.png")
        async def render(*args):
            # The exact edition is persisted even if rendering fails afterwards.
            self.assertEqual(p._archive_daily_digest.await_count, 1)
            self.assertEqual(p._archive_daily_digest.await_args.kwargs["digest_img_path"], "")
            return "rendered.png"
        p._render_html_to_image = AsyncMock(side_effect=render)
        p._make_image_comp = Mock(side_effect=lambda path: path)
        p.context = SimpleNamespace(send_message=AsyncMock())
        ok, _ = await p.run_daily_digest(target_rule=self.rule, scheduled_at=edition)
        self.assertTrue(ok)
        data = p._render_html_to_image.await_args.args[1]
        self.assertEqual(data["total_count"], 1)
        self.assertEqual(data["scheduled_at"], edition.isoformat())
        self.assertEqual(p._archive_daily_digest.await_count, 2)

    async def test_render_preserves_styled_unicode_and_quote_text(self):
        text = "ʕ̢·͡˔·Ɂ̡̣ ⋈ 𝙉𝙚𝙬 𝘼𝙡𝙗𝙪𝙢 𝙍𝙚𝙡𝙚𝙖𝙨𝙚 ⋈ ʕ̢·͡˔·Ɂ̡̣"
        tweet = dict(orig_body=text, translated_body=text, author_name=text,
                     quote_info={"orig_body": text, "display_images": ["https://example.org/Ａ.jpg"]})
        before = copy.deepcopy(tweet)
        self.plugin._render_html_to_image = AsyncMock(side_effect=RuntimeError("stop before sending"))
        with self.assertRaisesRegex(RuntimeError, "stop before sending"):
            await Plugin.push_tweet_to_umo(self.plugin, tweet, self.rule["target_umo"])
        payload = self.plugin._render_html_to_image.await_args.args[1]
        for field in ("orig_body", "translated_body", "author_name", "quote_info"):
            self.assertEqual(payload[field], tweet[field])
        self.assertEqual(tweet, before)

    async def test_proactive_send_marks_qq_group_scene_and_rejects_false_result(self):
        p = self.plugin
        platform = Mock()
        platform.meta.return_value.id = "default_1905597608"
        platform.remember_session_scene = Mock()
        platform._allow_group_proactive_send = False
        p.context = SimpleNamespace(
            platform_manager=SimpleNamespace(platform_insts=[platform]),
            send_message=AsyncMock(return_value=True),
        )
        umo = "default_1905597608:GroupMessage:0BE46DBF041818B40E1B0CDAFDC67BA0"
        self.assertTrue(await p._send_to_umo(umo, "chain"))
        platform.remember_session_scene.assert_called_once_with(umo.rsplit(":", 1)[-1], "group")
        self.assertTrue(platform._allow_group_proactive_send)
        p.context.send_message.return_value = False
        with self.assertRaisesRegex(RuntimeError, "消息未发送"):
            await p._send_to_umo(umo, "chain")

    async def test_furigana_setting_controls_actual_render_payload(self):
        tweet = dict(orig_body="明日は学校へ行きます。", translated_body="明天去学校。")
        self.plugin._render_html_to_image = AsyncMock(side_effect=RuntimeError("stop before send"))
        for enabled, style in ((True, "平假名"), (True, "罗马音"), (False, "罗马音")):
            self.plugin.config["push_format_config"] = {
                "enable_japanese_furigana": enabled, "japanese_furigana_style": style,
            }
            with self.assertRaisesRegex(RuntimeError, "stop before send"):
                await Plugin.push_tweet_to_umo(self.plugin, tweet, self.rule["target_umo"])
            payload = self.plugin._render_html_to_image.await_args.args[1]
            self.assertEqual("orig_body_ruby" in payload, enabled)
            self.assertEqual(payload["translated_body"], tweet["translated_body"])
            if enabled:
                reading = "gakkou" if style == "罗马音" else "がっこう"
                self.assertIn(f"<rt>{reading}</rt>", payload["orig_body_ruby"])


if __name__ == "__main__":
    unittest.main()
