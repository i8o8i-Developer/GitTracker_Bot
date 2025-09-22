# GitTracker Bot 🤖

A Sophisticated Telegram Bot For Tracking GitHub Repository Events With Real-Time Notifications, Comprehensive Logging, And Production-Grade Deployment Capabilities.

<a href="https://www.producthunt.com/products/telegram-gittracker-bot?utm_source=badge-follow&utm_medium=badge&utm_source=badge-telegram&#0045;gittracker&#0045;bot" target="_blank"><img src="https://api.producthunt.com/widgets/embed-image/v1/follow.svg?product_id=1110176&theme=dark" alt="Telegram&#0032;GitTracker&#0032;Bot - Real&#0045;Time&#0032;GitHub&#0032;Notifications&#0032;Straight&#0032;To&#0032;Telegram | Product Hunt" style="width: 250px; height: 54px;" width="250" height="54" /></a>
<a href="https://www.producthunt.com/products/telegram-gittracker-bot/reviews?utm_source=badge-product_review&utm_medium=badge&utm_source=badge-telegram&#0045;gittracker&#0045;bot" target="_blank"><img src="https://api.producthunt.com/widgets/embed-image/v1/product_review.svg?product_id=1110176&theme=light" alt="Telegram&#0032;GitTracker&#0032;Bot - Real&#0045;Time&#0032;GitHub&#0032;Notifications&#0032;Straight&#0032;To&#0032;Telegram | Product Hunt" style="width: 250px; height: 54px;" width="250" height="54" /></a>

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-3.0.3-lightgrey.svg)
![Telegram](https://img.shields.io/badge/Telegram-Bot_API-blue.svg)
![MySQL](https://img.shields.io/badge/MySQL-8.0-orange.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)
![Coolify](https://img.shields.io/badge/Coolify-Deployed-green.svg)

## ✨ Features

* **Real-Time GitHub Tracking**: Monitor Push Events, Pull Requests, Issues, and Releases
* **Telegram Notifications**: Beautiful, Formatted Messages With Emojis And Developer Branding
* **Webhook Security**: HMAC Signature Verification For GitHub Webhooks
* **Database Integration**: MySQL With Connection Pooling For Reliable Data Storage
* **Comprehensive Logging**: Structured Logging With File Rotation and Multiple Log Levels
* **Health Monitoring**: Built-In Health Checks and Monitoring Endpoints
* **Docker Support**: Containerized Deployment With Multi-Stage Builds
* **Coolify Deployment**: One-Click Deployment With Coolify Platform
* **Environment Configuration**: Secure Configuration Management Via Environment Variables
* **Error Handling**: Robust Error Handling With Graceful Degradation

## 🚀 Quick Start

### Prerequisites

* Python 3.11+
* MySQL 8.0+
* Telegram Bot Token (From [@BotFather](https://t.me/botfather))
* GitHub OAuth App Credentials

### Local Development

1. **Clone The Repository**

   ```bash
   git clone https://github.com/i8o8i-Developer/GitTracker_Bot.git
   cd GitTracker_Bot
   ```

2. **Create Environment File**

   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Install Dependencies**

   ```bash
   pip install -r Requirements.txt
   ```

4. **Setup Database**

   ```bash
   mysql -u root -p < Database.sql
   ```

5. **Run The Bot**

   ```bash
   python Bot.py
   ```

## 🐳 Docker Deployment

### Build And Run With Docker Compose

```bash
# Build The Image
docker build -t gittracker-bot .

# Run With Docker Compose (If You Have docker-compose.yml)
docker-compose up -d
```

### Coolify Deployment

1. **Connect Your Repository To Coolify**
2. **Use The Provided `coolify.yaml` Configuration**
3. **Set Environment Variables In Coolify Dashboard**
4. **Deploy!**

## ⚙️ Configuration

### Environment Variables

| Variable                | Description                                      | Required | Default      |
| ----------------------- | ------------------------------------------------ | -------- | ------------ |
| `TELEGRAM_TOKEN`        | Telegram Bot Token From BotFather                | ✅        | -            |
| `DB_HOST`               | MySQL Database Host                              | ❌        | `127.0.0.1`  |
| `DB_PORT`               | MySQL Database Port                              | ❌        | `3306`       |
| `DB_NAME`               | MySQL Database Name                              | ❌        | `Tracer_Bot` |
| `DB_USER`               | MySQL Database User                              | ❌        | `root`       |
| `DB_PASSWORD`           | MySQL Database Password                          | ❌        | `""`         |
| `GITHUB_CLIENT_ID`      | GitHub OAuth App Client ID                       | ✅        | -            |
| `GITHUB_CLIENT_SECRET`  | GitHub OAuth App Client Secret                   | ✅        | -            |
| `GITHUB_WEBHOOK_SECRET` | GitHub Webhook Secret For Signature Verification | ❌        | -            |
| `WEBHOOK_URL`           | Public URL For Webhooks                          | ✅        | -            |
| `SERVER_HOST`           | Server Bind Host                                 | ❌        | `0.0.0.0`    |
| `SERVER_PORT`           | Server Bind Port                                 | ❌        | `5000`       |
| `DEBUG`                 | Enable Debug Mode                                | ❌        | `false`      |
| `LOG_LEVEL`             | Logging Level (DEBUG, INFO, WARNING, ERROR)      | ❌        | `INFO`       |

### Database Schema

The Bot Uses The Following Main Tables:

* `Users`: Telegram User Information
* `Repositories`: Tracked GitHub Repositories
* `Events`: GitHub Webhook Events Log

## 📱 Usage

### Telegram Commands

* `/start` - Initialize The Bot And Get Welcome Message
* `/help` - Show Available Commands
* `/track <repo>` - Start Tracking A GitHub Repository
* `/untrack <repo>` - Stop Tracking A Repository
* `/list` - List All Tracked Repositories
* `/status` - Show Bot Status and Statistics

### Webhook Integration

Set Up GitHub Webhooks For Your Repositories:

1. Go To Repository Settings → Webhooks
2. Add Webhook URL: `https://your-domain.com/webhook`
3. Content Type: `application/json`
4. Secret: Your Webhook Secret
5. Events: Push, Pull Request, Issues, Releases

## 🏗️ Project Structure

```
GitTracker_Bot/
├── Bot.py                 # Main Application File
├── Config.py              # Configuration Management
├── DataBase.py            # Database Operations
├── Logging_Config.py      # Logging Configuration
├── Requirements.txt       # Python Dependencies
├── Database.sql           # Database Schema
├── Dockerfile             # Docker Configuration
├── .env.example           # Environment Variables Template
├── README.md              # Project Documentation
└── Logs/                  # Application Logs (Created At Runtime)
```

## 🔧 Development

### Code Quality

* **Type Hints**: Full Type Annotation Support
* **Error Handling**: Comprehensive Exception Handling
* **Logging**: Structured Logging With Multiple Levels
* **Security**: Input Validation And Secure Practices

### Testing

```bash
# Run Tests (When Implemented)
python -m pytest tests/

# Check Code Quality
python -m flake8
python -m mypy
```

### Contributing

1. Fork The Repository
2. Create A Feature Branch (`git checkout -b feature/amazing-feature`)
3. Commit Your Changes (`git commit -m 'Add Amazing Feature'`)
4. Push To The Branch (`git push origin feature/amazing-feature`)
5. Open A Pull Request

## 📊 Monitoring

### Health Checks

The Application Provides Health Check Endpoints:

* `GET /health` - General Health Status
* `GET /health/db` - Database Connectivity Check
* `GET /health/telegram` - Telegram Bot Connectivity Check

### Logs

Logs Are Written To:

* Console (For Development)
* `logs/bot.log` (Rotating File Logs)
* Structured JSON Format For Production Monitoring

## 🚀 Deployment Options

### Coolify (Recommended)

1. Import Your Repository Into Coolify
2. Use The Provided `coolify.yaml` Configuration
3. Configure Environment Variables
4. Deploy With One Click

### Docker

```bash
# Build Image
docker build -t gittracker-bot .

# Run Container
docker run -d \
  --name gittracker-bot \
  -p 5000:5000 \
  -e TELEGRAM_TOKEN=your_token \
  -e DB_HOST=your_db_host \
  gittracker-bot
```

### Manual Deployment

1. Set Up MySQL Database
2. Configure Environment Variables
3. Install Dependencies: `pip install -r Requirements.txt`
4. Run: `python Bot.py`

## 🛡️ Security

* **Webhook Verification**: HMAC Signature Validation
* **Input Sanitization**: All User Inputs Are Validated
* **Secure Configuration**: Sensitive Data Via Environment Variables
* **Database Security**: Prepared Statements And Connection Pooling
* **Logging Security**: No Sensitive Data In Logs

## 📄 License

This Project Is Licensed Under The MIT License - See The [LICENSE](LICENSE) File For Details.

## 👨‍💻 Developer

**I8O8I DEVELOPER**

* Telegram: [@I8O8I\_Developer](https://t.me/I8O8I_Developer)
* GitHub: [i8o8i-Developer](https://github.com/i8o8i-Developer)

---

Made With ❤️ By I8O8I DEVELOPER
