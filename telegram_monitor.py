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
from telethon.tl.types import PeerChannel, PeerChat, PeerUser, InputPeerChannel
from telethon.errors import ChannelPrivateError, FloodWaitError
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Store known entities
known_entities = {}

# Load configuration
def load_config(filename):
    with open(filename, 'r') as f:
        return json.load(f)

async def resolve_entities(client, config):
    """Pre-resolve all entities in the config"""
    for source in config['sources']:
        if source['type'] == 'channel' and 'id' in source:
            try:
                channel_id = source['id']
                logger.info(f"Trying to resolve channel ID: {channel_id}")
                
                # Try to get the channel entity
                try:
                    entity = await client.get_entity(channel_id)
                    logger.info(f"Successfully resolved channel {channel_id} as {entity.title}")
                    known_entities[channel_id] = entity
                except Exception as e:
                    logger.error(f"Could not resolve channel {channel_id}: {e}")
                    logger.info(f"You may need to join this channel first.")
            except Exception as e:
                logger.error(f"Error resolving channel {channel_id}: {e}")

        elif source['type'] == 'public_group' and 'username' in source:
            try:
                username = source['username'].lstrip('@')
                logger.info(f"Trying to resolve group username: @{username}")
                
                # Try to get the group entity
                try:
                    entity = await client.get_entity(f"@{username}")
                    logger.info(f"Successfully resolved @{username} as {entity.title} (ID: {entity.id})")
                    known_entities[entity.id] = entity
                    known_entities[username.lower()] = entity
                except Exception as e:
                    logger.error(f"Could not resolve group @{username}: {e}")
                    logger.info(f"Make sure the group is public and the username is correct.")
            except Exception as e:
                logger.error(f"Error resolving group @{username}: {e}")

    # Also resolve the target channel
    try:
        target_id = config['target_channel_id']
        logger.info(f"Trying to resolve target channel ID: {target_id}")
        entity = await client.get_entity(target_id)
        logger.info(f"Successfully resolved target channel as {entity.title}")
        known_entities[target_id] = entity
    except Exception as e:
        logger.error(f"Could not resolve target channel {target_id}: {e}")
        logger.info("You must add your user account as an admin to the target channel.")

async def main():
    # Load environment variables
    api_id = int(os.environ.get('TELEGRAM_API_ID', 0))
    api_hash = os.environ.get('TELEGRAM_API_HASH', '')
    
    if not api_id or not api_hash:
        logger.error("You must set TELEGRAM_API_ID and TELEGRAM_API_HASH environment variables")
        logger.info("Get these values from https://my.telegram.org/apps")
        return
    
    # Load config
    try:
        config = load_config('config.json')
        target_channel_id = config['target_channel_id']
        logger.info(f"Target channel ID: {target_channel_id}")
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        return
    
    # Create the client
    client = TelegramClient('user_session', api_id, api_hash)
    await client.start()
    logger.info("User client started")
    
    # Print some information about the account
    me = await client.get_me()
    logger.info(f"Logged in as {me.username} (ID: {me.id})")
    
    # Pre-resolve all entities in the config
    await resolve_entities(client, config)
    
    # Register event handler for new messages
    @client.on(events.NewMessage)
    async def handler(event):
        # Get message details
        try:
            chat = await event.get_chat()
            sender = await event.get_sender()
            
            chat_id = getattr(chat, 'id', 0)
            chat_username = getattr(chat, 'username', None)
            sender_id = getattr(sender, 'id', 0)
            
            logger.info(f"Message from chat {chat_username} (ID: {chat_id}) from user {sender_id}")
            
            # Check if this is a monitored source
            for source in config['sources']:
                # Channel messages
                if source['type'] == 'channel' and 'id' in source and chat_id == source['id']:
                    logger.info(f"Forwarding message from channel {chat_id}")
                    
                    try:
                        await client.forward_messages(target_channel_id, event.message)
                        logger.info("Message forwarded successfully")
                    except FloodWaitError as e:
                        logger.error(f"Rate limited. Need to wait {e.seconds} seconds")
                    except Exception as e:
                        logger.error(f"Error forwarding message: {e}")
                    
                    break
                    
                # Public group messages
                elif source['type'] == 'public_group' and 'username' in source and chat_username:
                    # Remove @ if present for comparison
                    config_username = source['username'].lstrip('@')
                    chat_username = chat_username.lstrip('@')
                    
                    if config_username.lower() == chat_username.lower():
                        logger.info(f"Found matching group: {chat_username}")
                        
                        # Check if sender is in monitored users
                        if 'user_ids' in source and sender_id in source['user_ids']:
                            logger.info(f"Forwarding message from user {sender_id} in group {chat_username}")
                            
                            try:
                                await client.forward_messages(target_channel_id, event.message)
                                logger.info("Message forwarded successfully")
                            except FloodWaitError as e:
                                logger.error(f"Rate limited. Need to wait {e.seconds} seconds")
                            except Exception as e:
                                logger.error(f"Error forwarding message: {e}")
                            
                            break
                        else:
                            logger.info(f"User {sender_id} not in monitored list for this group")
                            
                # Direct messages
                elif source['type'] == 'user' and 'user_ids' in source and sender_id in source['user_ids']:
                    logger.info(f"Forwarding direct message from user {sender_id}")
                    
                    try:
                        await client.forward_messages(target_channel_id, event.message)
                        logger.info("Message forwarded successfully")
                    except FloodWaitError as e:
                        logger.error(f"Rate limited. Need to wait {e.seconds} seconds")
                    except Exception as e:
                        logger.error(f"Error forwarding message: {e}")
                    
                    break
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    logger.info("Monitoring for messages from configured sources...")
    logger.info("Press Ctrl+C to exit")
    
    # Keep the client running
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user") 