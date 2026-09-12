# Bot Integration

KITT provides Slack and Discord bots that let team members trigger benchmarks
and view results directly from chat.

---

## Installation

The bot dependencies are optional extras:

```bash
# Slack (uses slack-bolt)
poetry install -E slack

# Discord (uses discord.py)
poetry install -E discord
```

---

## Slack Bot Setup

1. Create a Slack app at <https://api.slack.com/apps>.
2. Enable **Socket Mode** and generate an app-level token (`xapp-...`).
3. Under **Slash Commands**, add a `/kitt` command.
4. Install the app to your workspace and copy the bot token (`xoxb-...`).
5. Start the bot:

```bash
kitt bot start --platform slack --token xoxb-... --app-token xapp-...
```

The Slack bot uses `slack-bolt` in Socket Mode, so no public URL or ingress is
required. The `/kitt` slash command accepts the same arguments as the CLI.

---

## Discord Bot Setup

1. Create a Discord application at <https://discord.com/developers>.
2. Under **Bot**, create a bot and copy the token.
3. Enable the **Message Content Intent** under Privileged Gateway Intents.
4. Generate an invite URL with the **Send Messages** permission and add the bot
   to your server.
5. Start the bot:

```bash
kitt bot start --platform discord --token <BOT_TOKEN>
```

The Discord bot listens for messages prefixed with `!kitt` and responds with
benchmark results.

---

## Bot Commands

Both platforms support the same core commands:

| Command | Description |
|---------|-------------|
| `run -m MODEL -e ENGINE -s SUITE` | Start a benchmark |
| `engines list` | List available engines |
| `results list` | List stored results |
| `status` | Show current run status |

---

## Configuration Reference

View setup instructions for both platforms:

```bash
kitt bot config
```

This prints step-by-step instructions for creating the Slack and Discord
applications, obtaining tokens, and starting the bot.

---

## Running in Production

For long-lived deployments, run the bot as a systemd service:

```ini
[Unit]
Description=KITT Slack Bot
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/kitt bot start --platform slack --token xoxb-... --app-token xapp-...
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Store tokens in environment variables or a secrets manager rather than passing
them directly on the command line in production.
