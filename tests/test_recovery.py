import asyncio
import tempfile
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx
from PIL import Image

from test_command_scope import Plugin


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.plugin = Plugin()
        self.plugin.config = {}
        self.plugin._http_reinit_lock = asyncio.Lock()
        self.plugin.http_client = None

    async def test_render_error_text_retries_then_uses_valid_png(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder) / "bad.png"
            bad.write_text("Internal Server Error")
            good = Path(folder) / "good.png"
            Image.new("RGB", (10, 10)).save(good)
            p = self.plugin
            p.html_render = AsyncMock(side_effect=[str(bad), str(good)])
            p._trim_rendered_image_sync = Mock()
            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await p._render_html_to_image("template", {})
            self.assertEqual(result, str(good))
            self.assertEqual(p.html_render.await_count, 2)
            p._trim_rendered_image_sync.assert_called_once_with(str(good))

    async def test_embedded_fonts_are_passed_to_renderer(self):
        with tempfile.TemporaryDirectory() as folder:
            good = Path(folder) / "good.png"
            Image.new("RGB", (10, 10)).save(good)
            p = self.plugin
            p.html_render = AsyncMock(return_value=str(good))
            p._trim_rendered_image_sync = Mock()
            await p._render_html_to_image("<html><head></head><body>{{ orig_body }}</body></html>", {"orig_body": "𝙉𝙚𝙬"})
            template, data = p.html_render.await_args.args
            self.assertIn("data:font/woff2;base64,", template)
            self.assertIn("Twitter Math", template)
            self.assertEqual(data["orig_body"], "𝙉𝙚𝙬")

    async def test_persistent_invalid_render_stops_before_upload(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder) / "bad.png"
            bad.write_text("Internal Server Error")
            self.plugin.html_render = AsyncMock(return_value=str(bad))
            self.plugin._trim_rendered_image_sync = Mock()
            with patch("asyncio.sleep", new_callable=AsyncMock):
                with self.assertRaisesRegex(RuntimeError, "停止归档和上传"):
                    await self.plugin._render_html_to_image("template", {})
            self.plugin._trim_rendered_image_sync.assert_not_called()

    async def test_pool_reset_does_not_close_other_inflight_request(self):
        p = self.plugin
        active = asyncio.Event()
        release = asyncio.Event()
        old = Mock(is_closed=False)
        old.aclose = AsyncMock()
        async def old_get(url, **kwargs):
            if url.endswith("slow"):
                active.set()
                await release.wait()
                return "slow result"
            raise httpx.PoolTimeout("pool full")
        old.get = AsyncMock(side_effect=old_get)
        p.http_client = old
        new = Mock(is_closed=False)
        new.aclose = AsyncMock()
        new.get = AsyncMock(return_value="recovered")
        with patch.dict(Plugin._init_http_client.__globals__, urlsplit=__import__('urllib.parse', fromlist=['urlsplit']).urlsplit):
            with patch.object(httpx, "AsyncClient", return_value=new):
                slow = asyncio.create_task(p._http_get_with_recovery("https://example.org/slow"))
                try:
                    await active.wait()
                    self.assertEqual(await p._http_get_with_recovery("https://example.org/pool"), "recovered")
                    old.aclose.assert_not_awaited()
                    release.set()
                    self.assertEqual(await slow, "slow result")
                    old.aclose.assert_awaited_once()
                finally:
                    release.set()
                    await slow

    async def test_second_pool_timeout_is_bounded(self):
        p = self.plugin
        first = Mock(is_closed=False, get=AsyncMock(side_effect=httpx.PoolTimeout("full")), aclose=AsyncMock())
        second = Mock(is_closed=False, get=AsyncMock(side_effect=httpx.PoolTimeout("full")), aclose=AsyncMock())
        p.http_client = first
        async def replace():
            p._http_retired.add(first)
            p.http_client = second
        p._init_http_client = AsyncMock(side_effect=replace)
        with self.assertRaises(httpx.PoolTimeout):
            await p._http_get_with_recovery("https://example.org")
        p._init_http_client.assert_awaited_once()
        self.assertEqual(p._http_users, {})

    async def test_pool_timeout_does_not_cool_down_source(self):
        p = self.plugin
        p._http_get_with_recovery = AsyncMock(side_effect=httpx.PoolTimeout("full"))
        p._cool_down_feed = Mock()
        from urllib.parse import urlsplit
        with patch.dict(Plugin._fetch_feed_response.__globals__, urlsplit=urlsplit):
            with self.assertRaises(httpx.PoolTimeout):
                await p._fetch_feed_response("https://example.org/feed")
        p._cool_down_feed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
