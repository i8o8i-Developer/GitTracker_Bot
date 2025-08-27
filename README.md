# 📌 Git & GitHub Tracer Bot

A Powerful Telegram Bot That Integrates With GitHub Using Webhooks.
It Automatically Notifies You About **Commits, Pull Requests, Issues, Branch Events, And More** — Directly In Telegram.

---

## ✨ Features

* 🔨 **Push Events** → Get Detailed Commit Notifications With Compare Links, Authors, And Bullet-Point Descriptions.
* 🔀 **Pull Requests** → Get Alerts When PRs Are Opened, Closed, Or Merged.
* 🐞 **Issues** → Get Alerts When Issues Are Opened, Assigned, Or Closed.
* 🌱 **Branch Events** → Track New Branch Creation And Deletion.
* 📋 **Webhook Management** → List Or Delete Repo Webhooks From Telegram.
* 💬 **Comment Command** → Post Comments To Issues Or PRs Directly From Telegram.
* 🔗 **PascalCase Formatting** → All Bot Messages, Variables, And Comments Are Pascal Styled For A Clean Look.
* 🗄 **Auto Database Setup** → MySQL Database And Users Table Created Automatically.

---

## ⚙️ Tech Stack

* 🐍 Python 3.11+
* 🤖 [python-telegram-bot](https://python-telegram-bot.org/)
* 🌐 Flask (For GitHub Webhook Receiver)
* 🗄 PyMySQL (For Database)
* 🚀 Ngrok (For Exposing Localhost To Webhook)

---

## 📦 Installation

### 1️⃣ Clone Repo

```bash
git clone https://github.com/YourUsername/GitTracer_Bot.git
cd GitTracer_Bot
```

### 2️⃣ Setup Virtual Environment

```bash
python -m venv .venv
source .venv/bin/activate   # Linux / Mac
.venv\Scripts\activate      # Windows
```

### 3️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

### 4️⃣ Setup Database

Edit `DataBase.py` With Your MySQL Credentials.
The Bot Automatically Creates `Tracer_Bot` Database & `Users` Table On First Run.

### 5️⃣ Configure

Edit `Config.py`:

```python
Telegram_Token = "YOUR_TELEGRAM_BOT_TOKEN"
Github_Client_Id = "YOUR_GITHUB_CLIENT_ID"
Github_Client_Secret = "YOUR_GITHUB_CLIENT_SECRET"
Ngrok_Url = "YOUR_PUBLIC_NGROK_URL"
```

---

## ▶️ Run Bot

```bash
python Bot.py
```

Bot Will:

* Start Telegram Polling
* Start Flask Web Server At `http://127.0.0.1:5000`
* Accept GitHub Webhooks

---

## 📌 Telegram Commands

| Command                                 | Description                               |
| --------------------------------------- | ----------------------------------------- |
| `/start`                                | Show Welcome Help                         |
| `/connect`                              | Connect Your GitHub Account               |
| `/setrepo owner/repo`                   | Set Default Repository (Installs Webhook) |
| `/getrepo`                              | Show Current Repository                   |
| `/listwebhooks`                         | List All Webhooks In Repo                 |
| `/delwebhook id`                        | Delete A Webhook By Id                    |
| `/comment owner/repo issue_number text` | Post Comment To Issue Or PR               |

---

## 📥 Example Notifications

**Push Event**

```
🔨 2 New Commits By Alice (https://github.com/org/repo/compare/abc...def) To Org/Repo:Main

✨ Abc123 (https://github.com/org/repo/commit/abc123): Added Login Feature — Alice
- Updated Authentication Logic
- Improved Security
🐛 Def456 (https://github.com/org/repo/commit/def456): Fixed Crash Bug — Bob
```

**Pull Request**

```
🔀 Pull Request OPENED In Org/Repo
👤 By: Alice
📝 Add Dark Mode Support
🔗 https://github.com/org/repo/pull/15
```

**Issue**

```
🐞 Issue CLOSED In Org/Repo
👤 By: Bob
📝 Fix App Crash On Startup
🔗 https://github.com/org/repo/issues/12
```

---

## 📜 License

This Project Is Licensed Under The **MIT License**.
You Are Free To Use, Modify, And Distribute With Attribution.

---