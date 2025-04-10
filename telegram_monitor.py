#!/usr/bin/env python3
"""
Telegram User Monitor - Forward messages from public groups without joining them
This script uses a regular Telegram user account to monitor messages and forward them.
"""

import os
import json
import logging
import asyncio
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
        with open('config.json', 'r') as f:
            return json.load(f)
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
                    
                    # Check username list
                    if 'username' in sender_info:
                        usernames = sender_info['username']
                        if isinstance(usernames, str):
                            usernames = [usernames]
                        
                        if hasattr(sender, 'username') and sender.username in usernames:
                            should_forward = True
                    
                    # Check user_id list
                    elif 'user_id' in sender_info:
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
            
            # Check if this is a channel or public group we're monitoring
            source_config = None
            for source in config['sources']:
                if source['type'] == 'channel' and chat.id == source['id']:
                    source_config = source
                    break
                elif source['type'] == 'public_group' and hasattr(chat, 'username') and chat.username == source['username']:
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
                    elif 'user_id' in sender_info:
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
        
        logger.info(f"Attempting to send message from {chat.title} by {sender.first_name}")
        logger.info(f"Message content: {message_text[:100]}{'...' if len(message_text) > 100 else ''}")
        
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
        
        # Get sender information based on configuration
        sender_info = None
        for source in config['sources']:
            if (source['type'] == 'channel' and chat.id == source['id']) or \
               (source['type'] == 'public_group' and hasattr(chat, 'username') and chat.username == source['username']) or \
               (source['type'] == 'private_group' and chat.id == source['id']):
                if 'sender_info' in source:
                    sender_info = source['sender_info']
                break
        
        # If sender_info is configured, use it
        if sender_info:
            # Handle username as a string or array
            if 'username' in sender_info:
                usernames = sender_info['username']
                # Convert single username to array for consistent handling
                if isinstance(usernames, str):
                    usernames = [usernames]
                
                # Join all usernames with commas
                if usernames:
                    username_list = ", ".join([f"@{username}" for username in usernames])
                    source_info += f"Author: {username_list}\n"
            
            # Handle user_id as a string, number, or array
            elif 'user_id' in sender_info:
                user_ids = sender_info['user_id']
                # Convert single user_id to array for consistent handling
                if not isinstance(user_ids, list):
                    user_ids = [user_ids]
                
                # Try to get user info from IDs
                user_names = []
                for user_id in user_ids:
                    try:
                        user = await client.get_entity(user_id)
                        if hasattr(user, 'username') and user.username:
                            user_names.append(f"@{user.username}")
                        elif hasattr(user, 'first_name'):
                            user_names.append(user.first_name)
                    except Exception as e:
                        logger.error(f"Error getting user info from ID {user_id}: {e}")
                        user_names.append(f"User ID {user_id}")
                
                # Join all user names with commas
                if user_names:
                    user_name_list = ", ".join(user_names)
                    source_info += f"Author: {user_name_list}\n"
        else:
            # Fall back to actual sender info
            if hasattr(sender, 'username') and sender.username:
                source_info += f"Author: @{sender.username}\n"
            elif hasattr(sender, 'first_name'):
                source_info += f"Author: {sender.first_name}\n"
        
        # If there's text, add it to the message
        if message_text:
            source_info += f"Original message: {message_text}"
        
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