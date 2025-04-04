# Telegram Bot

A simple Telegram bot written in Go that responds to basic commands.

## Features

- `/start` - Welcome message
- `/help` - Show available commands
- `/echo <text>` - Echo back your message

## Prerequisites

- Go 1.21 or higher
- A Telegram Bot Token (get it from [@BotFather](https://t.me/botfather))

## Setup

1. Clone this repository
2. Install dependencies:
   ```bash
   go mod tidy
   ```
3. Set your Telegram Bot Token as an environment variable:
   ```bash
   export TELEGRAM_BOT_TOKEN="your_bot_token_here"
   ```

## Running the Bot

To run the bot, simply execute:
```bash
go run main.go
```

## Usage

1. Start a chat with your bot on Telegram
2. Send `/start` to get a welcome message
3. Send `/help` to see available commands
4. Send `/echo <text>` to have the bot echo back your message

## Development

The bot is built using the [telegram-bot-api](https://github.com/go-telegram-bot-api/telegram-bot-api) package.
You can extend the functionality by adding more command handlers in the `main.go` file. 