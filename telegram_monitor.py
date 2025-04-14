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

# Load configuration
def load_config():
    try:
        # Try to load YAML config first
        if os.path.exists('config.yaml'):
            with open('config.yaml', 'r') as f:
                return yaml.safe_load(f)
        # Fall back to JSON if YAML doesn't exist
        elif os.path.exists('config.json'):
            with open('config.json', 'r') as f:
                return json.load(f)
        else:
            logger.error("No configuration file found. Please create either config.yaml or config.json")
            return None
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return None

# Initialize Telegram client
api_id = os.getenv('TELEGRAM_API_ID')
api_hash = os.getenv('TELEGRAM_API_HASH')

if not api_id or not api_hash:
    logger.error("API ID or API Hash not found in environment variables")
    exit(1)

client = TelegramClient('user_session', api_id, api_hash)

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
    except Exception as e:
        logger.error(f"Error resolving target channel: {e}")
        # Ask user if they want to use their own user ID as target
        me = await client.get_me()
        logger.info(f"Your user ID is: {me.id}")
        use_own_id = input("Do you want to use your own user ID as target? (y/n): ").lower() == 'y'
        if use_own_id:
            config['target_channel_id'] = me.id
            known_entities[me.id] = me
            logger.info(f"Using your user ID ({me.id}) as target")
        else:
            target_id = input("Please enter a valid channel ID or username: ")
            try:
                if target_id.startswith('@'):
                    target_id = target_id[1:]
                if target_id.isdigit():
                    target_id = int(target_id)
                target = await client.get_entity(target_id)
                config['target_channel_id'] = target.id
                known_entities[target.id] = target
                logger.info(f"Successfully resolved new target: {target.title}")
            except Exception as e:
                logger.error(f"Error resolving new target: {e}")
                exit(1)
    
    # Resolve source entities
    for source in config['sources']:
        try:
            if source['type'] == 'channel':
                entity = await client.get_entity(source['id'])
                known_entities[source['id']] = entity
                logger.info(f"Resolved channel: {entity.title}")
            elif source['type'] == 'public_group':
                entity = await client.get_entity(source['username'])
                known_entities[source['username']] = entity
                logger.info(f"Resolved public group: {entity.title}")
                # Check if user_ids is empty or not provided
                if 'user_ids' not in source or not source['user_ids']:
                    logger.info(f"No specific user IDs provided for {entity.title}, will forward messages from all users")
            elif source['type'] == 'private_group':
                # For private groups, we need the group ID
                if 'id' in source:
                    # Store the ID for later use in message handler
                    # We'll handle private groups differently in the message handler
                    known_entities[source['id']] = {'id': source['id'], 'type': 'private_group'}
                    logger.info(f"Stored private group ID: {source['id']}")
                    
                    # Check if user_ids is empty or not provided
                    if 'user_ids' not in source or not source['user_ids']:
                        logger.info(f"No specific user IDs provided for private group {source['id']}, will forward messages from all users")
                else:
                    logger.error("Private group configuration missing 'id' field")
        except Exception as e:
            logger.error(f"Error resolving {source['type']} {source.get('id', source.get('username', 'unknown'))}: {e}")

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
        # Get message details for debugging
        chat = await event.get_chat()
        sender = await event.get_sender()
        message_text = event.message.text if event.message.text else ""
        
        # Get sender name safely
        sender_name = None
        if hasattr(sender, 'username') and sender.username:
            sender_name = f"@{sender.username}"
        elif hasattr(sender, 'first_name'):
            sender_name = sender.first_name
        elif hasattr(sender, 'title'):  # For channels
            sender_name = sender.title
        else:
            sender_name = "Unknown"
        
        logger.info(f"Attempting to send message from {chat.title} by {sender_name}")
        logger.info(f"Message content: {message_text[:100]}{'...' if len(message_text) > 100 else ''}")
        
        # Check if this is a reply to another message
        replied_message = None
        if event.message.reply_to:
            try:
                replied_message = await event.message.get_reply_message()
                logger.info(f"Message is a reply to: {replied_message.text[:100] if replied_message.text else 'media message'}")
            except Exception as e:
                logger.error(f"Error getting replied message: {e}")
        
        # Download media if present
        media_path = None
        if event.message.media:
            logger.info(f"Message contains media, downloading...")
            try:
                # Create a directory for media if it doesn't exist
                os.makedirs("downloaded_media", exist_ok=True)
                
                # Download the media
                media_path = await event.message.download_media("downloaded_media")
                logger.info(f"Media downloaded to: {media_path}")
            except Exception as e:
                logger.error(f"Error downloading media: {e}")
        
        # Prepare source information for all messages
        source_info = f"From: {chat.title}\n"
        
        # Add sender info
        source_info += f"Author: {sender_name}\n"
        
        # If this is a reply, add the replied message info
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
            
            replied_text = replied_message.text if replied_message.text else "media message"
            source_info += f"Replying to {replied_sender_name}: {replied_text[:100]}{'...' if len(replied_text) > 100 else ''}\n"
        
        # If there's text, add it to the message
        if message_text:
            source_info += f"Message: {message_text}"
        
        # Send the message with media if available
        try:
            if media_path:
                logger.info(f"Sending message with downloaded media: {media_path}")
                await client.send_file(
                    config['target_channel_id'],
                    media_path,
                    caption=source_info
                )
                logger.info("Message sent with media successfully")
            else:
                # Send just the text if no media
                await client.send_message(
                    config['target_channel_id'],
                    source_info
                )
                logger.info("Message sent as text successfully")
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            
            # If sending with media fails, try to send just the text
            try:
                await client.send_message(
                    config['target_channel_id'],
                    source_info
                )
                logger.info("Message sent as text (media sending failed)")
            except Exception as e2:
                logger.error(f"Error sending message as text: {e2}")
    except Exception as e:
        logger.error(f"Error in forward_message: {e}")

async def main():
    """Main function to run the client"""
    global config
    config = load_config()
    if not config:
        return
    
    # Connect to Telegram
    await client.start()
    
    # Resolve all entities at startup
    await resolve_entities(config)
    
    # Register event handlers
    await register_event_handlers()
    
    # Log successful connection
    me = await client.get_me()
    logger.info(f"Connected as {me.first_name} (ID: {me.id})")
    
    # Print all configured sources for debugging
    logger.info("Configured sources:")
    for source in config['sources']:
        if source['type'] == 'channel':
            logger.info(f"  - Channel: {source['id']}")
        elif source['type'] == 'public_group':
            logger.info(f"  - Public group: {source['username']}")
        elif source['type'] == 'private_group':
            logger.info(f"  - Private group: {source['id']}")
    
    # Keep the client running
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main()) 