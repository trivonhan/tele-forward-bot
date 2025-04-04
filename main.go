package main

import (
	"encoding/json"
	"fmt"
	"log"
	"os"
	"strings"

	tgbotapi "github.com/go-telegram-bot-api/telegram-bot-api/v5"
	"github.com/joho/godotenv"
)

type Source struct {
	Type     string  `json:"type"`
	ID       int64   `json:"id,omitempty"`
	Username string  `json:"username,omitempty"`
	UserIDs  []int64 `json:"user_ids,omitempty"`
}

type Config struct {
	TargetChannelID int64    `json:"target_channel_id"`
	Sources         []Source `json:"sources"`
}

func loadConfig(filename string) (*Config, error) {
	data, err := os.ReadFile(filename)
	if err != nil {
		return nil, fmt.Errorf("error reading config file: %v", err)
	}

	var config Config
	if err := json.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("error parsing config file: %v", err)
	}

	// Clean up usernames (remove @ if present)
	for i := range config.Sources {
		if config.Sources[i].Type == "group" && config.Sources[i].Username != "" {
			config.Sources[i].Username = strings.TrimPrefix(config.Sources[i].Username, "@")
		}
	}

	return &config, nil
}

func main() {
	// Load .env file for bot token
	if err := godotenv.Load(); err != nil {
		log.Fatal("Error loading .env file")
	}

	// Get bot token from environment variable
	token := os.Getenv("TELEGRAM_BOT_TOKEN")
	if token == "" {
		log.Fatal("TELEGRAM_BOT_TOKEN is not set in .env file")
	}

	// Load configuration from config.json
	config, err := loadConfig("config.json")
	if err != nil {
		log.Fatal(err)
	}

	// Create a new bot instance
	bot, err := tgbotapi.NewBotAPI(token)
	if err != nil {
		log.Fatal(err)
	}

	// Enable debug mode
	bot.Debug = true

	log.Printf("Authorized on account %s", bot.Self.UserName)
	log.Printf("Monitoring for user IDs: %v", getAllUserIDs(config))

	// Create update configuration with a longer timeout
	u := tgbotapi.NewUpdate(0)
	u.Timeout = 60
	u.AllowedUpdates = []string{"message", "channel_post"} // Only get message and channel_post updates

	// Get updates channel
	updates := bot.GetUpdatesChan(u)

	// Handle incoming updates
	for update := range updates {
		// Handle channel posts
		if update.ChannelPost != nil {
			handleChannelPost(bot, update.ChannelPost, config)
			continue
		}

		// Handle messages (including public group messages and direct messages)
		if update.Message != nil {
			handleMessage(bot, update.Message, config)
		}
	}
}

func getAllUserIDs(config *Config) []int64 {
	userIDMap := make(map[int64]bool)
	for _, source := range config.Sources {
		for _, userID := range source.UserIDs {
			userIDMap[userID] = true
		}
	}

	var userIDs []int64
	for userID := range userIDMap {
		userIDs = append(userIDs, userID)
	}
	return userIDs
}

func handleChannelPost(bot *tgbotapi.BotAPI, post *tgbotapi.Message, config *Config) {
	log.Printf("Channel Post Details:")
	log.Printf("  Channel ID: %d", post.Chat.ID)
	log.Printf("  Channel Title: %s", post.Chat.Title)
	log.Printf("  Message Text: %s", post.Text)
	log.Printf("-------------------")

	// Check if post is from monitored channel
	for _, source := range config.Sources {
		if source.Type == "channel" && post.Chat.ID == source.ID {
			forwardMessage(bot, config.TargetChannelID, post.Chat.ID, post.MessageID)
			break
		}
	}
}

func handleMessage(bot *tgbotapi.BotAPI, message *tgbotapi.Message, config *Config) {
	// Log message details
	log.Printf("Message Details:")
	log.Printf("  Chat Username: %s", message.Chat.UserName)
	log.Printf("  Chat ID: %d", message.Chat.ID)
	log.Printf("  Chat Title: %s", message.Chat.Title)
	log.Printf("  Chat Type: %s", message.Chat.Type)
	log.Printf("  From User ID: %d", message.From.ID)
	log.Printf("  From Username: %s", message.From.UserName)
	log.Printf("  Message Text: %s", message.Text)
	log.Printf("-------------------")

	// Handle commands first
	if message.IsCommand() {
		handleCommand(bot, message)
		return
	}

	// Check if the user is in any of our monitored user lists
	isMonitoredUser := false
	for _, source := range config.Sources {
		for _, userID := range source.UserIDs {
			if message.From.ID == userID {
				isMonitoredUser = true
				break
			}
		}
		if isMonitoredUser {
			break
		}
	}

	if !isMonitoredUser {
		log.Printf("Message from unmonitored user: %d", message.From.ID)
		return
	}

	// If it's a direct message to the bot, forward it
	if message.Chat.Type == "private" {
		log.Printf("Received direct message from monitored user %d", message.From.ID)
		forwardMessage(bot, config.TargetChannelID, message.Chat.ID, message.MessageID)
		return
	}

	// Check if message is from monitored groups
	for _, source := range config.Sources {
		if source.Type == "group" {
			// Clean up username for comparison
			messageUsername := strings.TrimPrefix(message.Chat.UserName, "@")
			configUsername := strings.TrimPrefix(source.Username, "@")

			log.Printf("Comparing group usernames - Message: %s, Config: %s", messageUsername, configUsername)

			if strings.EqualFold(messageUsername, configUsername) {
				log.Printf("Found matching group: %s", messageUsername)
				forwardMessage(bot, config.TargetChannelID, message.Chat.ID, message.MessageID)
				break
			}
		}
	}
}

func handleCommand(bot *tgbotapi.BotAPI, message *tgbotapi.Message) {
	msg := tgbotapi.NewMessage(message.Chat.ID, "")

	switch message.Command() {
	case "start":
		msg.Text = "Welcome! I'm monitoring messages and will forward them to the target channel if they match the criteria."
	case "help":
		msg.Text = "Available commands:\n/start - Start the bot\n/help - Show this help message\n/id - Show chat information"
	case "id":
		msg.Text = fmt.Sprintf("Chat Username: %s\nChat ID: %d\nChat Title: %s\nChat Type: %s\nFrom User ID: %d\nFrom Username: %s",
			message.Chat.UserName,
			message.Chat.ID,
			message.Chat.Title,
			message.Chat.Type,
			message.From.ID,
			message.From.UserName)
	default:
		msg.Text = "I don't know that command. Use /help to see available commands."
	}

	if _, err := bot.Send(msg); err != nil {
		log.Printf("Error sending message: %v", err)
	}
}

func forwardMessage(bot *tgbotapi.BotAPI, targetID, fromChatID int64, messageID int) {
	forward := tgbotapi.NewForward(targetID, fromChatID, messageID)
	if _, err := bot.Send(forward); err != nil {
		log.Printf("Error forwarding message: %v", err)
	} else {
		log.Printf("Successfully forwarded message from chat %d", fromChatID)
	}
} 