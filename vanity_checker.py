"""Monitor Discord invite codes using Python 3.10+ (no dependencies)."""

import argparse
import json
import logging
import math
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

LOG = logging.getLogger("vanity")
API = "https://discord.com/api/v10"


def seconds(value, fallback=60.0):
    try:
        number = float(value)
        return number if math.isfinite(number) and number >= 0 else fallback
    except (TypeError, ValueError):
        return fallback


class Discord:
    def __init__(self, request_delay=0.5):
        self.request_delay = request_delay
        self.next_request = 0.0

    def request(self, url, payload=None):
        """Serialize requests and honor Discord retry/reset headers."""
        for attempt in range(4):
            time.sleep(max(0, self.next_request - time.monotonic()))
            data = None if payload is None else json.dumps(payload).encode()
            request = Request(url, data=data, headers={
                "User-Agent": "DiscordVanityMonitor/1.0",
                "Content-Type": "application/json",
            })
            try:
                response = urlopen(request, timeout=20)
            except HTTPError as exc:
                response = exc
            except (URLError, TimeoutError, OSError):
                raise RuntimeError("Network error contacting Discord") from None
            with response:
                status = response.code
                headers = response.headers
                try:
                    body = json.loads(response.read().decode())
                except (ValueError, UnicodeError):
                    body = {}
            delay = self.request_delay
            if headers.get("X-RateLimit-Remaining") == "0":
                delay = max(delay, seconds(headers.get("X-RateLimit-Reset-After")))
            if status == 429:
                retry = body.get("retry_after") if isinstance(body, dict) else None
                delay = max(delay, seconds(retry, seconds(headers.get("Retry-After"))))
            self.next_request = time.monotonic() + delay + 0.25
            if status == 429 or 500 <= status < 600:
                self.next_request = max(self.next_request, time.monotonic() + 2 ** attempt)
                LOG.warning("Discord HTTP %s; backing off", status)
                continue
            return status, body
        raise RuntimeError("Discord unavailable after retries; try again later")

    def check(self, code):
        status, body = self.request(f"{API}/invites/{code}?with_counts=false&with_expiration=false")
        if status == 200:
            return "taken"
        if status == 404 and isinstance(body, dict) and body.get("code") == 10006:
            return "potentially_available"
        raise RuntimeError(f"Invite lookup returned HTTP {status}; availability unknown")

    def alert(self, webhook, code):
        status, _ = self.request(webhook + "?wait=true", {
            "content": f"Potentially available vanity: https://discord.gg/{code}\n"
                       "Discord reports Unknown Invite. Confirm claimability in your server settings; "
                       "this does not guarantee the code can be claimed.",
            "allowed_mentions": {"parse": []},
        })
        if status not in (200, 204):
            raise RuntimeError(f"Webhook returned HTTP {status}")

    def announce(self, webhook, message):
        status, _ = self.request(webhook + "?wait=true", {
            "content": message, "allowed_mentions": {"parse": []},
        })
        if status not in (200, 204):
            raise RuntimeError(f"Webhook returned HTTP {status}")


def read_codes(path):
    codes = []
    for line in path.read_text(encoding="utf-8").splitlines():
        code = line.strip()
        if not code or code.startswith("#"):
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]{2,100}", code):
            raise ValueError(f"Invalid code {code!r}: use bare codes, 2–100 letters, digits, _ or -")
        if code not in codes:
            codes.append(code)
    if not codes:
        raise ValueError("The watchlist contains no codes")
    return codes


def validate_webhook(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or parsed.netloc != "discord.com"
            or not re.fullmatch(r"/api(?:/v10)?/webhooks/\d+/[A-Za-z0-9_.-]+", parsed.path)
            or parsed.query or parsed.fragment):
        raise ValueError("DISCORD_WEBHOOK_URL must be an HTTPS discord.com webhook URL without query parameters")
    return value


def save_state(path, state):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def scan(client, codes, state, path, webhook):
    failures = 0
    for code in codes:
        try:
            status = client.check(code)
            LOG.info("%s: %s", code, status.replace("_", " "))
            if status == "potentially_available" and state.get(code) != status:
                if webhook:
                    client.alert(webhook, code)
                else:
                    print(f"ALERT: discord.gg/{code} may be available — confirm in server settings", flush=True)
            # Only record a new availability after successful delivery, so failures retry.
            state[code] = status
            save_state(path, state)
        except RuntimeError as exc:
            failures += 1
            LOG.warning("%s: %s", code, exc)
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codes", type=Path, default=Path("vanities.txt"))
    parser.add_argument("--state", type=Path, default=Path("state.json"))
    parser.add_argument("--interval", type=float, default=300, help="Seconds between scans (minimum 60)")
    parser.add_argument("--request-delay", type=float, default=0.5,
                        help="Minimum pause between requests, plus 0.25s buffer (default 0.5; minimum 0.5)")
    parser.add_argument("--once", action="store_true", help="Scan once and exit")
    parser.add_argument("--console-only", action="store_true", help="Print alerts without a webhook")
    parser.add_argument("--test-webhook", action="store_true", help="Send a test message and exit")
    args = parser.parse_args()
    if args.test_webhook and args.console_only:
        parser.error("--test-webhook cannot be combined with --console-only")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not math.isfinite(args.interval) or args.interval < 60:
        parser.error("--interval must be a finite number of at least 60 seconds")
    if not math.isfinite(args.request_delay) or args.request_delay < 0.5:
        parser.error("--request-delay must be a finite number of at least 0.5 seconds")
    try:
        webhook_file = Path(__file__).resolve().with_name("webhook.txt")
        webhook_value = os.environ.get("DISCORD_WEBHOOK_URL", "")
        if not args.console_only and not webhook_value and webhook_file.exists():
            webhook_value = webhook_file.read_text(encoding="utf-8-sig").strip()
        webhook = None if args.console_only else validate_webhook(webhook_value)
        client = Discord(request_delay=args.request_delay)
        if args.test_webhook:
            client.announce(webhook, "Vanity checker: webhook connected successfully. Candidate alerts will appear in this channel.")
            LOG.info("Webhook test delivered successfully")
            return 0
        codes = read_codes(args.codes)
        state = json.loads(args.state.read_text(encoding="utf-8")) if args.state.exists() else {}
        if not isinstance(state, dict) or any(v not in ("taken", "potentially_available") for v in state.values()):
            raise ValueError("Invalid state file; move it aside to start fresh")
        if webhook:
            client.announce(webhook, f"Vanity checker started. Watching {len(codes)} codes. "
                            "Alerts indicate potentially available invites; confirm claimability in server settings.")
            LOG.info("Webhook connected; startup message delivered")
        while True:
            failures = scan(client, codes, state, args.state, webhook)
            if args.once:
                return 1 if failures else 0
            LOG.info("Scan complete; next scan in %s seconds", args.interval)
            time.sleep(args.interval)
    except (ValueError, OSError, RuntimeError) as exc:
        # Never include network exceptions containing a secret webhook URL.
        LOG.error("Configuration or state error: %s", exc)
        return 1
    except KeyboardInterrupt:
        LOG.info("Stopped")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
