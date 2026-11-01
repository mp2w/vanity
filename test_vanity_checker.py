import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from vanity_checker import Discord, scan, read_codes, validate_webhook


class CheckerTests(unittest.TestCase):
    def test_only_unknown_invite_is_candidate(self):
        client = Discord()
        for response, expected in [((200, {}), "taken"), ((404, {"code": 10006}), "potentially_available")]:
            client.request = Mock(return_value=response)
            self.assertEqual(client.check("example"), expected)
        for response in [(403, {}), (404, {}), (500, {}), (429, {})]:
            client.request = Mock(return_value=response)
            with self.assertRaises(RuntimeError):
                client.check("example")

    def test_alert_failure_retries_and_success_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = {}
            client = Mock()
            client.check.return_value = "potentially_available"
            client.alert.side_effect = RuntimeError("delivery failed")
            self.assertEqual(scan(client, ["example"], state, path, "webhook"), 1)
            self.assertEqual(state, {})
            client.alert.side_effect = None
            scan(client, ["example"], state, path, "webhook")
            scan(client, ["example"], state, path, "webhook")
            self.assertEqual(client.alert.call_count, 2)
            client.check.return_value = "taken"
            scan(client, ["example"], state, path, "webhook")
            client.check.return_value = "potentially_available"
            scan(client, ["example"], state, path, "webhook")
            self.assertEqual(client.alert.call_count, 3)

    def test_rate_limit_retries_with_server_delay(self):
        def response(status, body, headers):
            result = Mock()
            result.__enter__ = Mock(return_value=result)
            result.__exit__ = Mock(return_value=False)
            result.code = status
            result.headers = headers
            result.read.return_value = body
            return result
        replies = [response(429, b'{"retry_after": 12}', {}), response(200, b'{}', {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset-After": "8"})]
        with patch("vanity_checker.urlopen", side_effect=replies), patch("vanity_checker.time.sleep") as sleep, patch("vanity_checker.time.monotonic", return_value=100):
            client = Discord()
            self.assertEqual(client.request("https://discord.com/api/v10/invites/test"), (200, {}))
            self.assertGreaterEqual(sleep.call_args_list[1].args[0], 12)
            self.assertGreaterEqual(client.next_request, 108)

    def test_watchlist_and_webhook_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "codes.txt"
            path.write_text("# comment\nexample\nexample\n", encoding="utf-8")
            self.assertEqual(read_codes(path), ["example"])
            path.write_text("https://discord.gg/example", encoding="utf-8")
            with self.assertRaises(ValueError):
                read_codes(path)
        with self.assertRaises(ValueError):
            validate_webhook("https://example.com/api/webhooks/123/token")


if __name__ == "__main__":
    unittest.main()
