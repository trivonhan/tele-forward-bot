# Telegram Monitor

A Python script that uses a regular Telegram user account to monitor messages from public and private groups/channels, and forward them to a specific destination (channel, group, or user). It also supports forwarding to specific topics in supergroups.

## Features

- Monitor public groups without joining them
- Monitor channels you have access to
- Monitor private groups you are a member of
- Forward messages from specific users only
- Add source information to forwarded messages
- Forward messages to specific topics in supergroups
- Support for media messages

## Setup

1. Clone this repository
2. Install the required packages: `pip install -r requirements.txt`
3. Create a `.env` file with your Telegram API credentials (see `.env.example`)
4. Create a configuration file (`config.yaml` or `config.json`)
5. Run the script: `python telegram_monitor.py`

## Configuration

You can configure the script using either YAML or JSON format. Here's a sample configuration:

```yaml
# Target channel/group where messages will be forwarded to
target_channel_id: -1002541506815

# Optional global topic ID (will be used if no source-specific topic is defined)
topic_id: 1

# List of sources to monitor
sources:
  # Channel sources (messages from these channels will be forwarded without filtering)
  - type: channel
    id: -1001420009399  # Sample channel ID
    target_topic: 2  # Optional: Topic ID where messages from this source will be forwarded

  # Private group sources (messages will be filtered based on sender)
  - type: private_group
    id: 2304400688
    target_topic: 3  # Optional: Topic ID where messages from this source will be forwarded
    sender_info:
      username: ["user1"]  # Only messages from this username will be forwarded
      user_id: [123456789, 987654321]  # Or these user IDs

  # Public group sources (messages will be filtered based on sender)
  - type: public_group
    username: "group_username"
    target_topic: 4  # Optional: Topic ID where messages from this source will be forwarded
    sender_info:
      user_id: [123456789]  # Only messages from these user IDs
      username: ["user1", "user2"]  # Or these usernames
```

## Source Types

- `channel`: Forward all posts from a specific channel (requires channel ID)
- `private_group`: Forward messages from a private group you're a member of (requires group ID)
- `public_group`: Forward messages from a public group (requires username)

For both private and public groups, you can specify `sender_info` with `username` and/or `user_id` to filter messages from specific users only.

### Using Topics in Supergroups

To forward messages to specific topics in a supergroup:

1. Make sure your target is a supergroup (not a regular group, channel, or user)
2. Find the topic ID you want to use (topic IDs are usually numbers like 1, 2, 3...)
3. Configure either:
   - A global `topic_id` that will be used for all sources without a specific target_topic
   - Individual `target_topic` values for each source

Note: To use topics, your Telegram client must be logged in to a user account that has access to the supergroup and its topics.

## Finding IDs

### How to get channel/group IDs:
1. Forward a message from the channel/group to [@userinfobot](https://t.me/userinfobot)
2. The bot will reply with the ID of the channel/group

### How to get user IDs:
1. Forward a message from the user to [@userinfobot](https://t.me/userinfobot)
2. The bot will reply with the ID of the user

### How to get topic IDs:
1. Open the topic in your web browser
2. Look at the URL, it will be in the format: `https://t.me/c/1234567890/123?thread=789`
3. The number after `thread=` is the topic ID (in this example, 789)

## Running the Script

```bash
python telegram_monitor.py
```

The script will connect to Telegram using your user account, resolve all configured entities, and start monitoring for messages. When a matching message is found, it will be forwarded to your configured target channel/group, optionally in the specified topic.

## Troubleshooting

- Make sure you're using correct user IDs and group usernames
- For public groups, ensure you've entered the username correctly (with or without @ is fine)
- Check logs for any errors or connection issues
- Make sure your user account has permission to access all channels and groups
- For topics, verify that your target is a supergroup (not a regular group or channel)
- Ensure the topic IDs are correct and that your user has access to those topics

## License

MIT 