# Telegram Message Forwarding

This project provides two solutions for forwarding messages from specific users in public groups to your target channel:

1. **MTProto Solution (Python - Recommended)** - Can monitor public groups without joining them
2. **Bot API Solution (Go)** - Requires adding your bot to the groups

## Recommended: MTProto Solution (Python)

The Python solution uses Telethon and the Telegram MTProto API to monitor public groups without joining them.

### Setup

1. **Get Telegram API credentials**:
   - Visit https://my.telegram.org/apps
   - Create a new application
   - Note your API ID and API Hash

2. **Create .env file**:
   ```
   TELEGRAM_API_ID=12345
   TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure config.json with sources and target channel**:
   ```json
   {
     "target_channel_id": -1002541506815,
     "sources": [
       {
         "type": "channel",
         "id": -1001420009399
       },
       {
         "type": "public_group",
         "username": "GemiCryptoChat",
         "user_ids": [1939628595, 1180351016]
       },
       {
         "type": "public_group",
         "username": "mtristan_test_bot",
         "user_ids": [1180351016]
       }
     ]
   }
   ```

### Running the Python client
```bash
python telegram_monitor.py
```

On first run, you'll be prompted to:
1. Enter your phone number
2. Enter the verification code sent to your Telegram account
This only happens once - your session is saved in `user_session` file.

## Alternative: Bot API Solution (Go)

The original solution uses Telegram Bot API, but has a limitation: **bots cannot receive messages from groups they haven't joined**.

### Configuration

Create a `.env` file with your bot token:
```
TELEGRAM_BOT_TOKEN=your_bot_token_here
```

Use the same `config.json` as the Python solution.

### Running the Bot API client
```bash
go run main.go
```

## Source Types

- `channel`: Forward all posts from a specific channel (requires channel ID)
- `public_group`: Forward only messages from specified users in a public group (requires username and user_ids)
- `user`: Forward direct messages from specific users (requires user_ids)

## How to Get IDs

- Use the `/id` command in the bot to get user/group IDs
- Or look at logs from the Python script to get entity IDs by username
- You can use https://t.me/username to find public group usernames

## Troubleshooting

- Make sure you're using correct user IDs and group usernames
- For public groups, ensure you've entered the username correctly (with or without @ is fine)
- Check logs for any errors or connection issues
- For the Python solution, make sure your user account has permission to access all channels

## License

MIT 