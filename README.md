# Discord vanity monitor

A dependency-free Python 3.10+ script that watches selected Discord invite codes and sends Discord webhook alerts. No bot token or user token needed.

**An unknown invite means potentially available, not guaranteed claimable.** Discord's public invite lookup cannot prove that a code is eligible, unreserved, or claimable by your server. Confirm in your server's Custom Invite Link settings. This script does not claim codes.

## Setup (PowerShell)

1. Install Python 3.10 or newer.
2. Edit `vanities.txt`: one bare code per line, such as `my-community`. Blank lines and lines beginning with `#` are ignored.
3. In your Discord channel, open **Edit Channel → Integrations → Webhooks**, create a webhook, and copy its URL. Keep it private.
4. From this folder, run:

```powershell
$env:DISCORD_WEBHOOK_URL = 'https://discord.com/api/webhooks/YOUR_ID/YOUR_TOKEN'
py vanity_checker.py
```

If your Python command is `python`, substitute that for `py`. No packages to install. Leave the process running on your computer or a server; stop with Ctrl+C. Setting the environment variable does not send a message until you run the script.

## Options

On Windows, double-click `start_checker.bat` or run `.\start_checker.bat` in PowerShell. It loads the saved webhook automatically. Stop with Ctrl+C.

Each webhook-enabled launch sends a startup message to your channel. To verify delivery without starting a scan, run `.\start_checker.bat --test-webhook`. Previously alerted candidates remain deduplicated.

The default request pause is now 0.75 seconds including the safety buffer, previously 2.25 seconds. Network latency, webhook deliveries and Discord rate limits add time. To slow requests down, use `--request-delay 2`. This changes scan speed, not the reliability of claimability detection.

You can also save the webhook URL alone in `webhook.txt` beside the script. This file is ignored by Git. The `DISCORD_WEBHOOK_URL` environment variable takes priority when set.

```powershell
# Single scan (exit 1 if a lookup or notification fails)
py vanity_checker.py --once

# Console alerts without configuring a webhook
py vanity_checker.py --console-only --once

# Scan every ten minutes
py vanity_checker.py --interval 600

# Use another watchlist and state file
py vanity_checker.py --codes other-names.txt --state other-state.json
```

The default pause is five minutes after each complete scan, with requests spaced apart. Discord's rate-limit headers and retry delays are respected; network/API failures never count as availability. Only HTTP 404 with Discord error `10006` (Unknown Invite) triggers an availability alert.

The first potentially available result triggers an alert, then `state.json` prevents repeats across restarts. A code that becomes taken and later potentially available alerts again. Failed webhook deliveries are retried on the next scan. A crash after delivery but before state is saved can cause a duplicate; webhook timeouts can also leave delivery uncertain. Delete `state.json` to reset alert history. Use one running process per state file, and restart after editing the watchlist. Console mode also updates state; use a separate `--state` file when testing if you want fresh webhook alerts afterward.

## Verification

```powershell
py -m unittest -v
```

API references: [Get Invite](https://discord.com/developers/docs/resources/invite#get-invite), [rate limits](https://discord.com/developers/docs/topics/rate-limits).
