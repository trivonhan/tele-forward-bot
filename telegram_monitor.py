#!/usr/bin/env python3
"""
Telegram User Monitor - Forward messages from public groups without joining them
This script uses a regular Telegram user account to monitor messages and forward them.
"""

import os
import json
import logging
import asyncio
import signal
import sys
import time
import fcntl
import yaml  # Add YAML import
import shutil
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.tl.types import Channel, User, Chat, ChatEmpty, PeerChannel, PeerChat, PeerUser
from telethon.errors import ChatAdminRequiredError, ChannelPrivateError, UsernameNotOccupiedError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Proxy configuration for Telethon (SOCKS5 at 127.0.0.1:1111)
PROXY = ('socks5', '127.0.0.1', 1111)

# Create example config file
def create_example_config():
    example_config = """# Target supergroup where messages will be forwarded to
# This must be a supergroup to support topics
target_channel_id: -1001234567890

# Optional: Global topic ID (will be used if no source-specific topic is provided)
# topic_id: 1

# List of sources to monitor
sources:
  # Channel sources (messages from these channels will be forwarded without filtering)
  - type: channel
    id: -1001111111111  # Channel ID
    target_topic: 2  # Optional: Topic ID where messages from this source will be forwarded

  - type: channel
    id: -1001222222222  # Channel ID
    target_topic: 3  # Messages from this channel will go to topic 3

  # Private group sources (messages will be filtered based on sender)
  - type: private_group
    id: -1001333333333  # Private group ID
    target_topic: 4  # Messages will go to topic 4
    # Optional: Filter by specific users
    sender_info:
      username: ["username1"]  # Only messages from this username will be forwarded
      user_id: [123456789, 987654321]  # Or from these user IDs

  # Public group sources (messages will be filtered based on sender)
  - type: public_group
    username: "public_group_name"  # Public group username (without @)
    target_topic: 5  # Messages will go to topic 5
    # Optional: Filter by specific users
    sender_info:
      user_id: [123456789]  # Only messages from these user IDs
      username: ["username2", "username3"]  # Or from these usernames
      
  # Example without a target_topic (will use the global topic_id if set)
  - type: public_group
    username: "another_group_name"
    # No target_topic specified, will use global topic_id if set or main chat if not
"""
    try:
        with open('config.yaml.example', 'w') as f:
            f.write(example_config)
        logger.info("Created example configuration file: config.yaml.example")
    except Exception as e:
        logger.error(f"Error creating example config file: {e}")

# Load configuration
def load_config():
    try:
        # Try to load YAML config first
        if os.path.exists('config.yaml'):
            with open('config.yaml', 'r') as f:
                config = yaml.safe_load(f)
                logger.info("Loaded configuration from config.yaml")
        # Fall back to JSON if YAML doesn't exist
        elif os.path.exists('config.json'):
            with open('config.json', 'r') as f:
                config = json.load(f)
                logger.info("Loaded configuration from config.json")
        else:
            logger.error("No configuration file found. Please create either config.yaml or config.json")
            
            # Create example config file if it doesn't exist
            if not os.path.exists('config.yaml.example'):
                create_example_config()
            
            logger.info("You can use config.yaml.example as a template")
            return None
        
        # Check for required config values
        if 'target_channel_id' not in config:
            logger.error("target_channel_id is required in the configuration")
            logger.info("Please add target_channel_id to your config file")
            return None
        
        # Check if global topic_id is provided
        if 'topic_id' in config:
            logger.info(f"Global topic ID configured: {config['topic_id']}")
        
        # Check for per-source target_topic
        if 'sources' in config:
            for i, source in enumerate(config['sources']):
                if 'target_topic' in source:
                    source_name = source.get('id', source.get('username', f'source {i+1}'))
                    logger.info(f"Source-specific topic ID configured for {source_name}: {source['target_topic']}")
        
        return config
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return None

# Initialize Telegram client
api_id = os.getenv('TELEGRAM_API_ID')
api_hash = os.getenv('TELEGRAM_API_HASH')

if not api_id or not api_hash:
    logger.error("API ID or API Hash not found in environment variables")
    exit(1)

client = TelegramClient('user_session', api_id, api_hash, proxy=PROXY)

# Store known entities to avoid repeated resolution
known_entities = {}

async def resolve_entities(config):
    """Pre-resolve all entities in the configuration"""
    global known_entities
    
    # Resolve target channel
    try:
        target_channel = await client.get_entity(config['target_channel_id'])
        known_entities[config['target_channel_id']] = target_channel
        logger.info(f"Successfully resolved target channel: {target_channel.title}")
        
        # Inform if using global topic in a supergroup
        if 'topic_id' in config:
            logger.info(f"Configured to send messages to global topic {config['topic_id']} in group {target_channel.title}")
            # Check if the target is actually a supergroup (required for topics)
            if not hasattr(target_channel, 'megagroup') or not target_channel.megagroup:
                logger.warning(f"Warning: Target {target_channel.title} may not be a supergroup. Topics may not work.")
        
        # Check if using per-source topics
        topic_sources = []
        if 'sources' in config:
            for source in config['sources']:
                if 'target_topic' in source:
                    source_name = source.get('id', source.get('username', 'unknown source'))
                    topic_sources.append(f"{source_name} → topic {source['target_topic']}")
            
            if topic_sources:
                logger.info(f"Configured to use per-source topics: {', '.join(topic_sources)}")
                # Check if the target is actually a supergroup (required for topics)
                if not hasattr(target_channel, 'megagroup') or not target_channel.megagroup:
                    logger.warning(f"Warning: Target {target_channel.title} may not be a supergroup. Topics may not work.")
    except Exception as e:
        logger.error(f"Error resolving target channel: {e}")
        logger.error(f"Could not resolve target channel ID from config: {config['target_channel_id']}")
        logger.error("Please check your config.yaml file and ensure the target_channel_id is correct")
        exit(1)
    
    # Resolve source entities
    if 'sources' in config:
        for source in config['sources']:
            try:
                if source.get('type') == 'channel' and 'id' in source:
                    try:
                        entity = await client.get_entity(source['id'])
                        known_entities[source['id']] = entity
                        logger.info(f"Resolved channel: {entity.title}")
                    except Exception as e:
                        logger.warning(f"Could not resolve channel {source['id']}: {e}")
                elif source.get('type') == 'public_group' and 'username' in source:
                    try:
                        entity = await client.get_entity(source['username'])
                        known_entities[source['username']] = entity
                        logger.info(f"Resolved public group: {entity.title}")
                    except Exception as e:
                        logger.warning(f"Could not resolve public group @{source['username']}: {e}")
                elif source.get('type') == 'private_group' and 'id' in source:
                    # Store the ID for later use in message handler
                    known_entities[source['id']] = {'id': source['id'], 'type': 'private_group'}
                    logger.info(f"Stored private group ID: {source['id']}")
            except Exception as e:
                source_id = source.get('id', source.get('username', 'unknown'))
                logger.warning(f"Error processing source {source_id}: {e}")
                logger.warning("This source will be skipped")

# Register event handlers for each source type
async def register_event_handlers():
    """Register event handlers for each source type"""
    # Get all channel IDs from config
    channel_ids = []
    for source in config['sources']:
        if source['type'] == 'channel' and 'id' in source:
            # Ensure channel ID is in the correct format
            channel_id = source['id']
            # If the ID doesn't start with -100, add it
            if not str(channel_id).startswith('-100'):
                channel_id = int(f"-100{abs(channel_id)}")
                source['id'] = channel_id  # Update the config with the correct ID
            channel_ids.append(channel_id)
            logger.info(f"Added channel ID: {channel_id}")
    
    # Register a specific handler for channels if we have any
    if channel_ids:
        logger.info(f"Registering event handler for channels: {channel_ids}")
        
        @client.on(events.NewMessage(chats=channel_ids))
        async def channel_handler(event):
            """Handle messages from channels"""
            try:
                # Get the chat where the message was sent
                chat = await event.get_chat()
                logger.info(f"Received message from channel: {chat.id} - {chat.title}")
                
                # Find the matching source config
                source_config = None
                for source in config['sources']:
                    if source['type'] == 'channel':
                        # Normalize both IDs to the same format for comparison
                        config_id = str(source['id']).replace('-100', '')
                        event_id = str(chat.id).replace('-100', '')
                        if config_id == event_id:
                            source_config = source
                            break
                
                if not source_config:
                    logger.warning(f"No matching source config found for channel {chat.id}")
                    return
                
                # Forward all channel messages
                logger.info(f"Forwarding message from channel {chat.title}")
                await forward_message(event)
            
            except Exception as e:
                logger.error(f"Error processing channel message: {e}")
    
    # Get all private group IDs from config
    private_group_ids = []
    for source in config['sources']:
        if source['type'] == 'private_group' and 'id' in source:
            private_group_ids.append(source['id'])
    
    # Register a specific handler for private groups if we have any
    if private_group_ids:
        logger.info(f"Registering event handler for private groups: {private_group_ids}")
        
        @client.on(events.NewMessage(chats=private_group_ids))
        async def private_group_handler(event):
            """Handle messages from private groups"""
            try:
                # Get the chat where the message was sent
                chat = await event.get_chat()
                logger.info(f"Received message from private group: {chat.id} - {chat.title}")
                
                # Find the matching source config
                source_config = None
                for source in config['sources']:
                    if source['type'] == 'private_group' and chat.id == source['id']:
                        source_config = source
                        break
                
                if not source_config:
                    logger.warning(f"No matching source config found for private group {chat.id}")
                    return
                
                # Get the sender of the message
                sender = await event.get_sender()
                logger.info(f"Message sender: {sender.id} - {sender.first_name}")
                
                # Check if we should forward based on sender_info
                should_forward = False
                
                # If sender_info is configured, check if the sender is in the allowed list
                if 'sender_info' in source_config:
                    sender_info = source_config['sender_info']
                    
                    # Check username list if configured
                    if 'username' in sender_info:
                        usernames = sender_info['username']
                        if isinstance(usernames, str):
                            usernames = [usernames]
                        
                        if hasattr(sender, 'username') and sender.username in usernames:
                            should_forward = True
                    
                    # Check user_id list if configured
                    if 'user_id' in sender_info:
                        user_ids = sender_info['user_id']
                        if not isinstance(user_ids, list):
                            user_ids = [user_ids]
                        
                        if sender.id in user_ids:
                            should_forward = True
                
                # If no sender_info or sender not in allowed list, check user_ids
                elif 'user_ids' in source_config and source_config['user_ids']:
                    if sender.id in source_config['user_ids']:
                        should_forward = True
                else:
                    # If no filtering is configured, forward all messages
                    should_forward = True
                
                if should_forward:
                    logger.info(f"Forwarding message from {sender.first_name} in private group {chat.id}")
                    await forward_message(event)
                else:
                    logger.debug(f"Ignoring message from non-monitored user {sender.first_name} in private group {chat.id}")
            
            except Exception as e:
                logger.error(f"Error processing private group message: {e}")
    
    # Register a general handler for all other message types
    @client.on(events.NewMessage())
    async def general_handler(event):
        """Handle messages from channels and public groups"""
        try:
            # Get the chat where the message was sent
            chat = await event.get_chat()
            logger.info(f"Received message from: {chat.id} - {getattr(chat, 'title', 'Unknown')}")
            
            # Skip if this is a private group (handled by the specific handler)
            if any(source['type'] == 'private_group' and chat.id == source['id'] for source in config['sources']):
                logger.debug(f"Skipping private group message in general handler: {chat.id}")
                return
            
            # Skip if this is a channel (handled by the specific handler)
            if any(source['type'] == 'channel' and chat.id == source['id'] for source in config['sources']):
                logger.debug(f"Skipping channel message in general handler: {chat.id}")
                return
            
            # Check if this is a public group we're monitoring
            source_config = None
            for source in config['sources']:
                if source['type'] == 'public_group' and hasattr(chat, 'username') and chat.username == source['username']:
                    source_config = source
                    break
            
            if not source_config:
                return
            
            # Get the sender of the message
            sender = await event.get_sender()
            
            # For channels, forward all messages
            if source_config['type'] == 'channel':
                logger.info(f"Forwarding message from channel {chat.title}")
                await forward_message(event)
                return
            
            # For public groups, check if we should forward based on sender_info or user_ids
            if source_config['type'] == 'public_group':
                should_forward = False
                
                # Check sender_info if configured
                if 'sender_info' in source_config:
                    sender_info = source_config['sender_info']
                    
                    # Check username list
                    if 'username' in sender_info:
                        usernames = sender_info['username']
                        if isinstance(usernames, str):
                            usernames = [usernames]
                        
                        if hasattr(sender, 'username') and sender.username in usernames:
                            should_forward = True
                    
                    # Check user_id list
                    if 'user_id' in sender_info:
                        user_ids = sender_info['user_id']
                        if not isinstance(user_ids, list):
                            user_ids = [user_ids]
                        
                        if sender.id in user_ids:
                            should_forward = True
                
                # If no sender_info or sender not in allowed list, check user_ids
                elif 'user_ids' in source_config and source_config['user_ids']:
                    if sender.id in source_config['user_ids']:
                        should_forward = True
                else:
                    # If no filtering is configured, forward all messages
                    should_forward = True
                
                if should_forward:
                    logger.info(f"Forwarding message from {sender.first_name} in {chat.title}")
                    await forward_message(event)
                else:
                    logger.debug(f"Ignoring message from non-monitored user {sender.first_name} in {chat.title}")
        
        except Exception as e:
            logger.error(f"Error processing message: {e}")

async def forward_message(event):
    """Send a copy of the message to the target channel with source information"""
    try:
        chat = await event.get_chat()
        sender = await event.get_sender()
        message_text = event.message.text if event.message.text else ""

        sender_name = None
        if hasattr(sender, 'username') and sender.username:
            sender_name = f"@{sender.username}"
        elif hasattr(sender, 'first_name'):
            sender_name = sender.first_name
        elif hasattr(sender, 'title'):
            sender_name = sender.title
        else:
            sender_name = "Unknown"

        logger.info(f"Attempting to send message from {chat.title} by {sender_name}")
        logger.info(f"Message content: {message_text[:100]}{'...' if len(message_text) > 100 else ''}")

        # Download media if present
        media_path = None
        if event.message.media:
            logger.info(f"Message contains media, downloading...")
            try:
                os.makedirs("downloaded_media", exist_ok=True)
                media_path = await event.message.download_media("downloaded_media")
                logger.info(f"Media downloaded to: {media_path}")
            except Exception as e:
                logger.error(f"Error downloading media: {e}")

        # Find the source config for this message
        source_config = None
        topic_id = None

        for source in config['sources']:
            if source['type'] == 'channel' and str(chat.id).replace('-100', '') == str(source['id']).replace('-100', ''):
                source_config = source
                break
            elif source['type'] == 'private_group' and chat.id == source['id']:
                source_config = source
                break
            elif source['type'] == 'public_group' and hasattr(chat, 'username') and chat.username == source['username']:
                source_config = source
                break

        if source_config and 'target_topic' in source_config:
            topic_id = source_config['target_topic']
            logger.info(f"Using source-specific topic ID: {topic_id}")
        elif 'topic_id' in config:
            topic_id = config['topic_id']
            logger.info(f"Using global topic ID: {topic_id}")
        else:
            logger.info("No topic ID found, sending to main chat")

        # If this message is a reply, send the replied-to message first and capture its message ID
        reply_to_msg_id = None
        if event.message.reply_to:
            try:
                replied_message = await event.message.get_reply_message()
                if replied_message:
                    replied_sender = await replied_message.get_sender()
                    replied_sender_name = None
                    if hasattr(replied_sender, 'username') and replied_sender.username:
                        replied_sender_name = f"@{replied_sender.username}"
                    elif hasattr(replied_sender, 'first_name'):
                        replied_sender_name = replied_sender.first_name
                    elif hasattr(replied_sender, 'title'):
                        replied_sender_name = replied_sender.title
                    else:
                        replied_sender_name = "Unknown"
                    replied_text = replied_message.text if replied_message.text else ""
                    replied_formatted = f"Replied from {replied_sender_name}:\n{replied_text}"

                    # Download media if present in replied message
                    replied_media_path = None
                    if replied_message.media:
                        try:
                            os.makedirs("downloaded_media", exist_ok=True)
                            replied_media_path = await replied_message.download_media("downloaded_media")
                        except Exception as e:
                            logger.error(f"Error downloading replied media: {e}")

                    # Send the replied message first, with or without media
                    if replied_media_path:
                        sent = await client.send_file(
                            config['target_channel_id'],
                            replied_media_path,
                            caption=replied_formatted if replied_text else f"Replied from {replied_sender_name}",
                            reply_to=topic_id
                        )
                    else:
                        # If the replied message has no text and no media, send a placeholder
                        if not replied_text:
                            replied_formatted = f"Replied from {replied_sender_name}: [no text or media]"
                        sent = await client.send_message(
                            config['target_channel_id'],
                            replied_formatted,
                            reply_to=topic_id
                        )
                    reply_to_msg_id = sent.id
            except Exception as e:
                logger.error(f"Error forwarding replied message: {e}")

        # Prepare the formatted message for the main message
        formatted_message = ""
        if message_text:
            formatted_message += f"{message_text}\n"
        formatted_message += "--------------------------------\n"
        formatted_message += f"From: {chat.title} - {sender_name}"

        # Send the main message, replying to the forwarded replied message if applicable
        try:
            if media_path:
                logger.info(f"Sending message with downloaded media: {media_path}")
                await client.send_file(
                    config['target_channel_id'],
                    media_path,
                    caption=formatted_message,
                    reply_to=reply_to_msg_id if reply_to_msg_id else topic_id
                )
                logger.info("Message sent with media successfully")
            else:
                await client.send_message(
                    config['target_channel_id'],
                    formatted_message,
                    reply_to=reply_to_msg_id if reply_to_msg_id else topic_id
                )
                logger.info("Message sent as text successfully")
        except Exception as e:
            logger.error(f"Error sending message: {e}")
    except Exception as e:
        logger.error(f"Error in forward_message: {e}")

async def cleanup_downloaded_media():
    """Clean up the downloaded_media directory"""
    try:
        if os.path.exists("downloaded_media"):
            shutil.rmtree("downloaded_media")
            os.makedirs("downloaded_media", exist_ok=True)
            logger.info("Successfully cleaned up downloaded_media directory")
    except Exception as e:
        logger.error(f"Error cleaning up downloaded_media directory: {e}")

async def schedule_cleanup():
    """Schedule daily cleanup at midnight"""
    while True:
        now = datetime.now()
        # Calculate time until next midnight
        next_midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        seconds_until_midnight = (next_midnight - now).total_seconds()
        
        # Wait until midnight
        await asyncio.sleep(seconds_until_midnight)
        
        # Perform cleanup
        await cleanup_downloaded_media()

async def main():
    """Main function to run the client"""
    global config
    
    # Load configuration
    config = load_config()
    if not config:
        logger.error("Failed to load configuration. Exiting.")
        return
    
    # Connect to Telegram
    try:
        await client.start()
        
        # Log successful connection
        me = await client.get_me()
        logger.info(f"Connected as {me.first_name} (ID: {me.id})")
        
        # Resolve all entities at startup
        await resolve_entities(config)
        
        # Register event handlers
        await register_event_handlers()
        
        # Print all configured sources for debugging
        if 'sources' in config and config.get('sources'):
            logger.info("Configured sources:")
            for source in config['sources']:
                if source.get('type') == 'channel' and 'id' in source:
                    logger.info(f"  - Channel: {source['id']}")
                elif source.get('type') == 'public_group' and 'username' in source:
                    logger.info(f"  - Public group: {source['username']}")
                elif source.get('type') == 'private_group' and 'id' in source:
                    logger.info(f"  - Private group: {source['id']}")
                else:
                    source_id = source.get('id', source.get('username', 'unknown'))
                    logger.info(f"  - Unknown source type: {source.get('type', 'unknown')} ({source_id})")
        else:
            logger.warning("No sources configured. The bot is running but won't monitor any messages.")
        
        # Start the cleanup scheduler
        asyncio.create_task(schedule_cleanup())
        
        # Keep the client running
        await client.run_until_disconnected()
    except Exception as e:
        logger.error(f"Error in main function: {e}")
        sys.exit(1)
    finally:
        # Make sure we disconnect cleanly
        if client.is_connected():
            await client.disconnect()
            logger.info("Disconnected from Telegram")

if __name__ == "__main__":
    asyncio.run(main())