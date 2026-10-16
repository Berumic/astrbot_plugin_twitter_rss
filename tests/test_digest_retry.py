import datetime
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from test_command_scope import Plugin


class DigestRetryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.real_datetime = datetime.datetime
        class Clock(datetime.datetime):
            current = datetime.datetime(2026, 10, 20, 8, 30)
            @classmethod
            def now(cls):
                return cls.current
        self.clock = Clock
        self.p = p = Plugin()
        p.config = {"group_subscriptions": [
            {"group_name": "A", "target_umo": "platform:GroupMessage:A"},
            {"group_name": "B", "target_umo": "platform:GroupMessage:B"},
        ]}
        p.state = {}
        p.digest_archive = {}
        p._save_state = AsyncMock()
        p.run_daily_digest = AsyncMock(side_effect=[(True, "a.png"), (False, "failed")])
        p._get_or_rerender_archived_digest = AsyncMock(return_value=(True, "b.png"))
        p._make_image_comp = Mock(side_effect=lambda x: x)
        p.context = SimpleNamespace(send_message=AsyncMock())
        self.clock_patch = patch.dict(Plugin._digest_tick.__globals__, datetime=SimpleNamespace(datetime=Clock))
        self.clock_patch.start()
        self.addCleanup(self.clock_patch.stop)

    async def test_failed_group_retries_original_archive_successful_group_is_skipped(self):
        p = self.p
        await p._digest_tick()
        self.assertEqual(p.run_daily_digest.await_count, 2)
        a, b = [rule["target_umo"] for rule in p.config["group_subscriptions"]]
        self.assertTrue(p.state["digest_deliveries"][a]["sent"])
        self.assertFalse(p.state["digest_deliveries"][b]["sent"])
        # Not yet time to retry.
        await p._digest_tick()
        self.assertEqual(p.run_daily_digest.await_count, 2)
        p.digest_archive[b] = {"2026-10-20": {"items_meta": ["frozen edition"], "scheduled_at": "2026-10-20T08:30:00"}}
        p.state["digest_deliveries"][b]["retry_at"] = 0
        self.clock.current = self.real_datetime(2026, 10, 20, 9, 0)
        await p._digest_tick()
        p._get_or_rerender_archived_digest.assert_awaited_once_with(b, "2026-10-20")
        p.context.send_message.assert_awaited_once_with(b, ["b.png"])
        self.assertTrue(p.state["digest_deliveries"][b]["sent"])
        await p._digest_tick()
        self.assertEqual(p.context.send_message.await_count, 1)

    async def test_yesterday_is_never_retried(self):
        p = self.p
        p.state["digest_deliveries"] = {"old": {"date": "2026-10-19", "sent": False}}
        self.clock.current = self.real_datetime(2026, 10, 20, 7, 0)
        await p._digest_tick()
        p.run_daily_digest.assert_not_awaited()
        self.assertEqual(p.state["digest_deliveries"], {})

    async def test_restart_after_scheduled_time_generates_today_edition_at_original_time(self):
        self.clock.current = self.real_datetime(2026, 10, 20, 12, 0)
        await self.p._digest_tick()
        for call in self.p.run_daily_digest.await_args_list:
            self.assertEqual(call.kwargs["scheduled_at"], self.real_datetime(2026, 10, 20, 8, 30))

    async def test_saved_success_survives_restart(self):
        for rule in self.p.config["group_subscriptions"]:
            self.p.state.setdefault("digest_deliveries", {})[rule["target_umo"]] = {
                "date": "2026-10-20", "scheduled_at": "2026-10-20T08:30:00", "sent": True}
        await self.p._digest_tick()
        self.p.run_daily_digest.assert_not_awaited()

    async def test_cross_midnight_during_restore_prevents_send(self):
        p = self.p
        p.config["group_subscriptions"] = p.config["group_subscriptions"][:1]
        umo = p.config["group_subscriptions"][0]["target_umo"]
        p.digest_archive[umo] = {"2026-10-20": {"items_meta": ["edition"], "scheduled_at": "2026-10-20T08:30:00"}}
        async def restore(*args):
            self.clock.current = self.real_datetime(2026, 10, 21, 0, 0)
            return True, "late.png"
        p._get_or_rerender_archived_digest.side_effect = restore
        await p._digest_tick()
        p.context.send_message.assert_not_awaited()

    async def test_one_group_exception_does_not_block_other_group(self):
        self.p.run_daily_digest.side_effect = [RuntimeError("renderer down"), (True, "b.png")]
        await self.p._digest_tick()
        self.assertEqual(self.p.run_daily_digest.await_count, 2)


if __name__ == "__main__":
    unittest.main()
