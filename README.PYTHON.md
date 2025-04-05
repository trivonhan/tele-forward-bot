# Python Telegram User Monitor

This Python script solves the problem of monitoring public groups without having to add a bot to them. It uses a regular Telegram user account instead of a bot account to monitor messages.

## How It Works

The script uses the Telethon library to:
1. Log in with a regular Telegram user account
2. Monitor messages from specified public groups
3. Forward messages from specific users to your target channel

## Advantages Over Bot API

- Can monitor public groups without joining them
- Works with any public group on Telegram
- No need to add a bot to your monitored groups
- Uses the same config.json format as the Go bot

## Setup Instructions

1. **Get Telegram API credentials**:
   - Visit https://my.telegram.org/apps
   - Create a new application
   - Note your API ID and API Hash

2. **Set up the environment**:
   - Copy `.env.python.example` to `.env`
   - Add your API ID and API Hash from the previous step
   ```
   TELEGRAM_API_ID=12345
   TELEGRAM_API_HASH=abcdef1234567890abcdef1234567890
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Use your existing config.json file** (no changes needed)

5. **Run the script**:
   ```bash
   python user_monitor.py
   ```

6. **First-time login**:
   - You'll be prompted to enter your phone number
   - Enter the verification code sent to your Telegram account
   - You'll only need to do this once

## Important Notes

- This uses a regular user account, not a bot account
- The user account must have access to the public groups you want to monitor
- Your user session is saved in `user_session` file
- Make sure your target channel has this user account as an admin with posting rights

## Ethical Considerations

Only use this for legitimate purposes and in accordance with Telegram's Terms of Service. Excessive automation with user accounts can potentially lead to restrictions.

## License

MIT 