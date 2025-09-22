"""
GitTracker Bot - A Telegram Bot For Tracking GitHub Repository Events.
Production-Grade Implementation With Comprehensive Error Handling And Logging.
"""

import threading
import requests
import asyncio
import hmac
import hashlib
import time
import re
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from typing import Optional

import DataBase
import Config
from Logging_Config import logger

# ---------------- Initialize Database ----------------
try:
    if not DataBase.Init_Db():
        logger.error("Failed To Initialize Database")
        exit(1)
    logger.info("Database Initialized Successfully")
except Exception as e:
    logger.critical(f"Critical Error During Database Initialization: {e}")
    exit(1)

# ---------------- Config ----------------
try:
    telegram_token = Config.config.telegram.token
    github_client_id = Config.config.github.client_id
    github_client_secret = Config.config.github.client_secret
    webhook_url = Config.config.server.webhook_url
    logger.info("Configuration Loaded Successfully")
except ValueError as e:
    logger.critical(f"Configuration Error: {e}")
    exit(1)

# ---------------- Globals ----------------
App = Flask(__name__)
BotApp = None
BotLoop = None   # Store Telegram Bot Loop

# ---------------- Helper Functions ----------------
def verify_webhook_signature(payload: bytes, signature: str, secret: str) -> bool:
    """
    Verify GitHub Webhook Signature For security.

    Args:
        payload: Raw Request Payload
        signature: GitHub Signature Header
        secret: Webhook Secret

    Returns:
        bool: True If Signature Is Valid
    """
    if not secret or not signature:
        return False

    expected_signature = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    expected_signature = f"sha256={expected_signature}"

    return hmac.compare_digest(expected_signature, signature)


def GetCommitTag(message: str) -> str:
    """Return Emoji Based On Commit Message Keywords."""
    msg = message.lower()
    if "fix" in msg or "bug" in msg:
        return "🐛"
    if "feat" in msg or "add" in msg or "new" in msg:
        return "✨"
    if "doc" in msg or "readme" in msg:
        return "📝"
    if "style" in msg or "ui" in msg:
        return "🎨"
    if "hotfix" in msg or "urgent" in msg:
        return "🔥"
    return "🔨"

# ---------------- Input Validation ----------------
def validate_github_repo(repo_input: str) -> Optional[str]:
    """
    Validate And Normalize GitHub Repository Input.

    Args:
        repo_input: Repository In Format "owner/repo" Or Full GitHub URL

    Returns:
        Normalized "owner/repo" Format Or None If Invalid
    """
    if not repo_input or not isinstance(repo_input, str):
        return None

    repo_input = repo_input.strip()

    # Handle Full GitHub URLs
    if repo_input.startswith("http"):
        if "github.com/" not in repo_input:
            return None
        try:
            repo = repo_input.rstrip("/").split("github.com/")[1]
        except IndexError:
            return None
    else:
        repo = repo_input

    # Validate owner/repo Format
    if "/" not in repo or repo.count("/") > 1:
        return None

    owner, repo_name = repo.split("/")
    if not owner or not repo_name:
        return None

    # Basic Validation For Allowed Characters
    import re
    if not re.match(r"^[a-zA-Z0-9._-]+$", owner) or not re.match(r"^[a-zA-Z0-9._-]+$", repo_name):
        return None

    return f"{owner}/{repo_name}"


def validate_issue_number(issue_str: str) -> Optional[int]:
    """
    Validate Issue/PR Number.

    Args:
        issue_str: String Representation Of Issue Number

    Returns:
        Integer Issue Number Or None If Invalid
    """
    try:
        issue_num = int(issue_str)
        if issue_num <= 0:
            return None
        return issue_num
    except ValueError:
        return None


def validate_comment_text(text: str) -> bool:
    """
    Validate Comment Text For Basic Security.

    Args:
        text: Comment Text To Validate

    Returns:
        True If Valid, False Otherwise
    """
    if not text or not isinstance(text, str):
        return False

    text = text.strip()
    if len(text) == 0 or len(text) > 65536:  # GitHub's Comment Limit
        return False

    # Check For Potentially Malicious Content
    dangerous_patterns = [
        "<script", "</script>", "javascript:", "data:", "vbscript:"
    ]

    text_lower = text.lower()
    for pattern in dangerous_patterns:
        if pattern in text_lower:
            return False

    return True

# ---------------- Telegram Handlers ----------------
async def Start(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "🎉 <b>Welcome to GitTracker Bot!</b> 🎉\n\n"
        "🚀 <b>Your Ultimate GitHub Repository Monitor</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📋 <b>Available Commands:</b>\n\n"
        "🔗 <code>/connect</code> → Link Your GitHub Account\n"
        "📌 <code>/setrepo Owner/Repo</code> → Connect Repository\n"
        "� <code>/getrepo</code> → View Your Connections\n"
        "💬 <code>/comment Owner/Repo #ID Message</code> → Comment on Issues\n"
        "� <code>/stats Owner/Repo</code> → Repository Statistics\n"
        "�📋 <code>/listwebhooks</code> → Manage Webhooks\n"
        "🗑 <code>/removerepo Owner/Repo</code> → Remove Connection\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✨ <b>Features:</b>\n"
        "• Real-time GitHub notifications\n"
        "• Multi-chat repository connections\n"
        "• Push, PR, and Issue tracking\n"
        "• Secure webhook integration\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "👨‍� <b>Developed By:</b> <code>I8O8I DEVELOPER</code>\n"
        "🌟 <b>Version:</b> <code>Production v2.0</code>"
    )
    await Update.message.reply_text(welcome_message, parse_mode="HTML")

async def Connect(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    """Handle GitHub OAuth Connection Setup."""
    try:
        telegram_id = Update.effective_user.id
        auth_url = (
            f"https://github.com/login/oauth/authorize"
            f"?client_id={github_client_id}&scope=repo"
            f"&state={telegram_id}"
        )
        connect_msg = (
            "🔗 <b>CONNECT YOUR GITHUB ACCOUNT</b> 🔗\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Click The Link Below To Authorize GitTracker Bot:\n\n"
            f"🔗 <a href='{auth_url}'>Authorize GitHub Access</a>\n\n"
            "📋 <b>Permissions Requested:</b>\n"
            "• Read Access To Your Repositories\n"
            "• Create Webhooks For Notifications\n\n"
            "🔒 <b>Your Data Is Secure And Encrypted.</b>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👨‍💻 <b>Developed by:</b> <code>I8O8I DEVELOPER</code>"
        )
        await Update.message.reply_text(connect_msg, parse_mode="HTML")
        logger.info(f"Generated GitHub Auth URL For User {telegram_id}")
    except Exception as e:
        error_msg = (
            "❌ <b>CONNECTION ERROR</b> ❌\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Failed To Generate GitHub Authorization Link.\n\n"
            "Please Try Again Later Or Contact Support.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👨‍💻 <b>Developed by:</b> <code>I8O8I DEVELOPER</code>"
        )
        await Update.message.reply_text(error_msg, parse_mode="HTML")
        logger.error(f"Error Generating Connection Link For User {Update.effective_user.id}: {e}")

async def SetRepo(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        if not Context.args:
            await Update.message.reply_text("⚠ Usage: /setrepo Owner/Repo Or Full GitHub Url")
            return

        RepoInput = Context.args[0]

        # Validate Repository Input
        Repo = validate_github_repo(RepoInput)
        if not Repo:
            await Update.message.reply_text("❌ Invalid Repository Format. Use Owner/Repo or Full GitHub URL")
            return

        TelegramId = Update.effective_user.id
        ChatId = Update.effective_chat.id
        ChatType = Update.effective_chat.type
        TopicId = getattr(Update.effective_message, 'message_thread_id', None) if ChatType == 'supergroup' else None

        Token = DataBase.Get_Token(TelegramId)
        if not Token:
            await Update.message.reply_text("❌ You Are Not Connected. Use /connect First.")
            return

        # Check If Repository Connection Already Exists For This Chat
        existing_connections = DataBase.get_user_repo_connections(TelegramId)
        for conn in existing_connections:
            if conn['Repo_Name'] == Repo and conn['Chat_Id'] == ChatId and conn['Topic_Id'] == TopicId:
                await Update.message.reply_text(f"⚠ Repository {Repo} Is Already Connected To This Chat")
                return

        # Add The Repo Connection
        DataBase.Add_Repo_Connection(TelegramId, Repo, ChatId, ChatType, TopicId)

        HookUrl = f"{webhook_url}/webhook"
        ApiUrl = f"https://api.github.com/repos/{Repo}/hooks"
        Headers = {"Authorization": f"token {Token}"}
        Data = {
            "name": "web",
            "active": True,
            "events": ["push", "pull_request", "issues", "delete", "create", "release"],
            "config": {"url": HookUrl, "content_type": "json", "insecure_ssl": "0"},
        }

        # Add Webhook Secret If Configured
        if Config.config.github.webhook_secret:
            Data["config"]["secret"] = Config.config.github.webhook_secret

        Response = requests.post(ApiUrl, json=Data, headers=Headers, timeout=10)

        if Response.status_code in [200, 201]:
            success_msg = (
                "✅ <b>REPOSITORY CONNECTED SUCCESSFULLY!</b> ✅\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📦 <b>Repository:</b> <code>{Repo}</code>\n"
                f"🔗 <b>Webhook:</b> Installed & Active\n"
                f"📱 <b>Chat:</b> {ChatType.capitalize()}\n"
                f"🔔 <b>Notifications:</b> Enabled\n\n"
                "You'll Now Receive Notifications For:\n"
                "• 🚀 Push Events & Commits\n"
                "• 🔀 Pull Request Updates\n"
                "• 🐛 Issue Activities\n"
                "• 🌱 Branch/Tag Changes\n"
                "• 📦 Release Updates\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "👨‍💻 <b>Developed by:</b> <code>I8O8I DEVELOPER</code>"
            )
            await Update.message.reply_text(success_msg, parse_mode="HTML")
            logger.info(f"Repository {Repo} Connected For User {TelegramId} In Chat {ChatId}")
        else:
            error_msg = (
                "⚠️ <b>REPOSITORY SAVED WITH WARNINGS</b> ⚠️\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📦 <b>Repository:</b> <code>{Repo}</code>\n"
                f"💾 <b>Status:</b> Saved To Database\n"
                f"🔗 <b>Webhook:</b> Failed To Install\n\n"
                f"❌ <b>GitHub Response:</b>\n<code>{Response.text}</code>\n\n"
                "Repository Is Connected But Webhook Installation Failed.\n"
                "You May Need To Manually Configure Webhooks On GitHub.\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "👨‍💻 <b>Developed by:</b> <code>I8O8I DEVELOPER</code>"
            )
            await Update.message.reply_text(error_msg, parse_mode="HTML")
            logger.warning(f"Failed To Create Webhook For {Repo}: {Response.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Network Error Setting Repo For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text("❌ Network Error Occurred While Setting Up Webhook. Please Try Again.")
    except Exception as e:
        logger.error(f"Unexpected Error Setting Repo For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text("❌ An Unexpected Error Occurred While Setting The Repository.")

async def GetRepo(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        TelegramId = Update.effective_user.id
        Connections = DataBase.Get_User_Repo_Connections(TelegramId)
        if Connections:
            message = (
                "� <b>YOUR REPOSITORY CONNECTIONS</b> 📊\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            )

            for i, Conn in enumerate(Connections, 1):
                ChatType = Conn['Chat_Type']
                TopicInfo = f" (Topic: {Conn['Topic_Id']})" if Conn['Topic_Id'] else ""
                chat_emoji = {
                    'private': '👤',
                    'group': '👥',
                    'supergroup': '🏢'
                }.get(ChatType, '💬')

                message += f"{i}. {chat_emoji} <code>{Conn['Repo_Name']}</code>\n"
                message += f"   └─ {ChatType.capitalize()}{TopicInfo}\n\n"

            message += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            message += "👨‍💻 <b>Developed By:</b> <code>I8O8I DEVELOPER</code>"

            await Update.message.reply_text(message, parse_mode="HTML")
        else:
            no_connections_msg = (
                "⚠️ <b>NO REPOSITORY CONNECTIONS</b> ⚠️\n\n"
                "You Haven't Connected Any Repositories Yet.\n\n"
                "💡 <b>To Get Started:</b>\n"
                "1. Use <code>/connect</code> To Link Your GitHub Account\n"
                "2. Use <code>/setrepo Owner/Repo</code> To Connect Repositories\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "👨‍💻 <b>Developed By:</b> <code>I8O8I DEVELOPER</code>"
            )
            await Update.message.reply_text(no_connections_msg, parse_mode="HTML")
    except Exception as e:
        error_msg = (
            "❌ <b>ERROR RETRIEVING REPOSITORIES</b> ❌\n\n"
            "An Unexpected Error Occurred While Fetching Your Connections.\n\n"
            "Please Try Again Later Or Contact Support.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👨‍💻 <b>Developed By:</b> <code>I8O8I DEVELOPER</code>"
        )
        await Update.message.reply_text(error_msg, parse_mode="HTML")

async def RemoveRepo(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        if not Context.args:
            await Update.message.reply_text("⚠ Usage: /removerepo Owner/Repo")
            return

        Repo = Context.args[0]
        TelegramId = Update.effective_user.id
        ChatId = Update.effective_chat.id
        TopicId = getattr(Update.effective_message, 'message_thread_id', None) if Update.effective_chat.type == 'supergroup' else None

        DataBase.Remove_Repo_Connection(TelegramId, Repo, ChatId, TopicId)
        success_msg = (
            "🗑️ <b>REPOSITORY CONNECTION REMOVED</b> 🗑️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"� <b>Repository:</b> <code>{Repo}</code>\n"
            f"📱 <b>Chat:</b> {Update.effective_chat.type.capitalize()}\n"
            f"✅ <b>Status:</b> Connection Removed\n\n"
            "You Will No Longer Receive Notifications For This Repository In This Chat.\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👨‍💻 <b>Developed By:</b> <code>I8O8I DEVELOPER</code>"
        )
        await Update.message.reply_text(success_msg, parse_mode="HTML")
    except Exception as e:
        await Update.message.reply_text("❌ An Error Occurred While Removing The Repository Connection.")

async def Comment(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(Context.args) < 3:
            await Update.message.reply_text("⚠ Usage: /comment Owner/Repo Issue_Number Message")
            return

        RepoInput = Context.args[0]
        IssueNumberStr = Context.args[1]
        CommentText = " ".join(Context.args[2:])

        # Validate Inputs
        Repo = validate_github_repo(RepoInput)
        if not Repo:
            await Update.message.reply_text("❌ Invalid Repository Format. Use Owner/Repo")
            return

        IssueNumber = validate_issue_number(IssueNumberStr)
        if not IssueNumber:
            await Update.message.reply_text("❌ Invalid Issue Number. Must Be A Positive Integer.")
            return

        if not validate_comment_text(CommentText):
            await Update.message.reply_text("❌ Invalid Comment Text. Please Check Your Input.")
            return

        TelegramId = Update.effective_user.id

        Token = DataBase.Get_Token(TelegramId)
        if not Token:
            await Update.message.reply_text("❌ You Are Not Connected. Use /connect First.")
            return

        Url = f"https://api.github.com/repos/{Repo}/issues/{IssueNumber}/comments"
        Headers = {"Authorization": f"token {Token}"}
        Response = requests.post(Url, json={"body": CommentText}, headers=Headers, timeout=10)

        if Response.status_code == 201:
            success_msg = (
                "💬 <b>COMMENT POSTED SUCCESSFULLY!</b> 💬\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📦 <b>Repository:</b> <code>{Repo}</code>\n"
                f"🔢 <b>Issue/PR:</b> #{IssueNumber}\n"
                f"✅ <b>Status:</b> Comment Posted\n\n"
                f"💭 <b>Your comment:</b>\n<code>{CommentText[:100]}{'...' if len(CommentText) > 100 else ''}</code>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "👨‍💻 <b>Developed By:</b> <code>I8O8I DEVELOPER</code>"
            )
            await Update.message.reply_text(success_msg, parse_mode="HTML")
            logger.info(f"Comment Posted By User {TelegramId} on {Repo}#{IssueNumber}")
        else:
            error_msg = (
                "❌ <b>FAILED TO POST COMMENT</b> ❌\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📦 <b>Repository:</b> <code>{Repo}</code>\n"
                f"🔢 <b>Issue/PR:</b> #{IssueNumber}\n"
                f"❌ <b>Status:</b> Failed\n\n"
                f"🔍 <b>GitHub Response:</b>\n<code>{error_msg}</code>\n\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "👨‍💻 <b>Developed By:</b> <code>I8O8I DEVELOPER</code>"
            )
            await Update.message.reply_text(error_msg, parse_mode="HTML")
            logger.warning(f"Failed To Post Comment On {Repo}#{IssueNumber}: {error_msg}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Network Error Posting Comment For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text("❌ Network Error Occurred While Posting Comment. Please Try Again.")
    except Exception as e:
        logger.error(f"Unexpected Error Posting Comment For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text("❌ An Unexpected Error Occurred While Posting The Comment.")

async def ListWebhooks(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        TelegramId = Update.effective_user.id
        Repo = DataBase.Get_Default_Repo(TelegramId)  
        if not Repo:
            Connections = DataBase.Get_User_Repo_Connections(TelegramId)
            Repo = Connections[0]['Repo_Name'] if Connections else None

        Token = DataBase.Get_Token(TelegramId)

        if not Repo or not Token:
            await Update.message.reply_text("⚠ Please /setrepo And /connect First.")
            return

        Url = f"https://api.github.com/repos/{Repo}/hooks"
        Headers = {"Authorization": f"token {Token}"}
        Response = requests.get(Url, headers=Headers, timeout=10)
        if Response.status_code != 200:
            await Update.message.reply_text(f"❌ Failed To Fetch Hooks: {Response.text}")
            return

        Hooks = Response.json()
        if not Hooks:
            await Update.message.reply_text("📭 No Webhooks Found")
            return

        Msg = "📋 Webhooks:\n"
        for H in Hooks:
            Msg += f"Id: {H['id']} | Url: {H['config']['url']}\n"
        await Update.message.reply_text(Msg)
    except requests.exceptions.RequestException as e:
        await Update.message.reply_text("❌ Network Error Occurred While Fetching Webhooks. Please Try Again.")
    except KeyError as e:
        await Update.message.reply_text("❌ Invalid Webhook Data Received From GitHub.")
    except Exception as e:
        await Update.message.reply_text("❌ An Unexpected Error Occurred While Listing Webhooks.")

async def DelWebhook(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        if not Context.args:
            await Update.message.reply_text("⚠ Usage: /delwebhook Id")
            return
        HookId = Context.args[0]
        TelegramId = Update.effective_user.id
        Repo = DataBase.Get_Default_Repo(TelegramId) 
        if not Repo:
            Connections = DataBase.Get_User_Repo_Connections(TelegramId)
            Repo = Connections[0]['Repo_Name'] if Connections else None

        Token = DataBase.Get_Token(TelegramId)

        if not Repo or not Token:
            await Update.message.reply_text("⚠ Please /setrepo And /connect First.")
            return

        Url = f"https://api.github.com/repos/{Repo}/hooks/{HookId}"
        Headers = {"Authorization": f"token {Token}"}
        Response = requests.delete(Url, headers=Headers, timeout=10)

        if Response.status_code == 204:
            await Update.message.reply_text(f"🗑 Webhook {HookId} Deleted")
        else:
            await Update.message.reply_text(f"❌ Failed To Delete: {Response.text}")
    except requests.exceptions.RequestException as e:
        await Update.message.reply_text("❌ Network Error Occurred While Deleting Webhook. Please Try Again.")
    except Exception as e:
        await Update.message.reply_text("❌ An Unexpected Error Occurred While Deleting The Webhook.")

async def Stats(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        if not Context.args:
            await Update.message.reply_text("⚠ Usage: /stats Owner/Repo")
            return

        RepoInput = Context.args[0]

        Repo = validate_github_repo(RepoInput)
        if not Repo:
            await Update.message.reply_text("❌ Invalid Repository Format. Use Owner/Repo or Full GitHub URL")
            return

        TelegramId = Update.effective_user.id

        Token = DataBase.Get_Token(TelegramId)
        if not Token:
            await Update.message.reply_text("❌ You Are Not Connected. Use /connect First.")
            return

        Url = f"https://api.github.com/repos/{Repo}"
        Headers = {"Authorization": f"token {Token}"}
        Response = requests.get(Url, headers=Headers, timeout=10)

        if Response.status_code != 200:
            await Update.message.reply_text(f"❌ Failed To Fetch Repository Stats: {Response.text}")
            return

        Data = Response.json()

        # Extract Stats
        name = Data.get('name', 'Unknown')
        full_name = Data.get('full_name', Repo)
        description = Data.get('description', 'No description')
        stars = Data.get('stargazers_count', 0)
        forks = Data.get('forks_count', 0)
        issues = Data.get('open_issues_count', 0)
        language = Data.get('language', 'Unknown')
        created = Data.get('created_at', 'Unknown')[:10]  # YYYY-MM-DD
        updated = Data.get('updated_at', 'Unknown')[:10]
        size = Data.get('size', 0)

        message = (
            "📊 <b>REPOSITORY STATISTICS</b> 📊\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 <b>Name:</b> <code>{name}</code>\n"
            f"🔗 <b>Full Name:</b> <code>{full_name}</code>\n"
            f"📝 <b>Description:</b> {description}\n\n"
            f"⭐ <b>Stars:</b> {stars:,}\n"
            f"🍴 <b>Forks:</b> {forks:,}\n"
            f"🐛 <b>Open Issues:</b> {issues:,}\n"
            f"💻 <b>Language:</b> {language}\n"
            f"📅 <b>Created:</b> {created}\n"
            f"🔄 <b>Last Updated:</b> {updated}\n"
            f"💾 <b>Size:</b> {size:,} KB\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👨‍💻 <b>Developed By:</b> <code>I8O8I DEVELOPER</code>"
        )

        await Update.message.reply_text(message, parse_mode="HTML")
    except requests.exceptions.RequestException as e:
        logger.error(f"Network Error Fetching Stats For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text("❌ Network Error Occurred While Fetching Repository Stats. Please Try Again.")
    except Exception as e:
        logger.error(f"Unexpected Error Fetching Stats For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text("❌ An Unexpected Error Occurred While Fetching Repository Statistics.")

async def Recent(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        if not Context.args:
            await Update.message.reply_text("⚠ Usage: /recent Owner/Repo")
            return

        RepoInput = Context.args[0]

        Repo = validate_github_repo(RepoInput)
        if not Repo:
            await Update.message.reply_text("❌ Invalid Repository Format. Use Owner/Repo or Full GitHub URL")
            return

        TelegramId = Update.effective_user.id

        Token = DataBase.Get_Token(TelegramId)
        if not Token:
            await Update.message.reply_text("❌ You Are Not Connected. Use /connect First.")
            return

        Url = f"https://api.github.com/repos/{Repo}/commits?per_page=10"
        Headers = {"Authorization": f"token {Token}"}
        Response = requests.get(Url, headers=Headers, timeout=10)

        if Response.status_code != 200:
            await Update.message.reply_text(f"❌ Failed To Fetch Recent Commits: {Response.text}")
            return

        Commits = Response.json()

        if not Commits:
            await Update.message.reply_text("📭 No Recent Commits Found")
            return

        message = (
            "🕒 <b>RECENT COMMITS</b> 🕒\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 <b>Repository:</b> <code>{Repo}</code>\n\n"
        )

        for i, commit in enumerate(Commits[:10], 1):
            sha = commit.get('sha', '')[:7]
            author = commit.get('commit', {}).get('author', {}).get('name', 'Unknown')
            message_commit = commit.get('commit', {}).get('message', '').split('\n')[0]
            date = commit.get('commit', {}).get('author', {}).get('date', '')[:10]
            url = commit.get('html_url', '')

            tag = GetCommitTag(message_commit)

            message += f"{i}. {tag} <code>{sha}</code>\n"
            message += f"   💬 {message_commit}\n"
            message += f"   👤 {author} | 📅 {date}\n"
            if url:
                message += f"   🔗 <a href='{url}'>View Commit</a>\n"
            message += "\n"

        message += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        message += "👨‍💻 <b>Developed By:</b> <code>I8O8I DEVELOPER</code>"

        await Update.message.reply_text(message, parse_mode="HTML")
    except requests.exceptions.RequestException as e:
        logger.error(f"Network Error Fetching Recent Commits For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text("❌ Network Error Occurred While Fetching Recent Commits. Please Try Again.")
    except Exception as e:
        logger.error(f"Unexpected Error Fetching Recent Commits For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text("❌ An Unexpected Error Occurred While Fetching Recent Commits.")

async def Branches(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        if not Context.args:
            await Update.message.reply_text("⚠ Usage: /branches Owner/Repo")
            return

        RepoInput = Context.args[0]

        Repo = validate_github_repo(RepoInput)
        if not Repo:
            await Update.message.reply_text("❌ Invalid Repository Format. Use Owner/Repo or Full GitHub URL")
            return

        TelegramId = Update.effective_user.id

        Token = DataBase.Get_Token(TelegramId)
        if not Token:
            await Update.message.reply_text("❌ You Are Not Connected. Use /connect First.")
            return

        Url = f"https://api.github.com/repos/{Repo}/branches"
        Headers = {"Authorization": f"token {Token}"}
        Response = requests.get(Url, headers=Headers, timeout=10)

        if Response.status_code != 200:
            await Update.message.reply_text(f"❌ Failed To Fetch Branches: {Response.text}")
            return

        Branches = Response.json()

        if not Branches:
            await Update.message.reply_text("🌿 No Branches Found")
            return

        message = (
            "🌿 <b>REPOSITORY BRANCHES</b> 🌿\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 <b>Repository:</b> <code>{Repo}</code>\n"
            f"📊 <b>Total Branches:</b> {len(Branches)}\n\n"
        )

        for branch in Branches[:20]:  # Limit to 20 branches
            name = branch.get('name', 'Unknown')
            sha = branch.get('commit', {}).get('sha', '')[:7]
            protected = branch.get('protected', False)
            protected_icon = "🔒" if protected else "🌿"

            message += f"{protected_icon} <code>{name}</code> ({sha})\n"

        if len(Branches) > 20:
            message += f"\n⋯⋯ And {len(Branches) - 20} More Branches ⋯⋯\n"

        message += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        message += "👨‍💻 <b>Developed By:</b> <code>I8O8I DEVELOPER</code>"

        await Update.message.reply_text(message, parse_mode="HTML")
    except requests.exceptions.RequestException as e:
        logger.error(f"Network Error Fetching Branches For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text("❌ Network Error Occurred While Fetching Branches. Please Try Again.")
    except Exception as e:
        logger.error(f"Unexpected Error Fetching Branches For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text("❌ An Unexpected Error Occurred While Fetching Branches.")

async def Contributors(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        if not Context.args:
            await Update.message.reply_text("⚠ Usage: /contributors Owner/Repo")
            return

        RepoInput = Context.args[0]

        Repo = validate_github_repo(RepoInput)
        if not Repo:
            await Update.message.reply_text("❌ Invalid Repository Format. Use Owner/Repo or Full GitHub URL")
            return

        TelegramId = Update.effective_user.id

        Token = DataBase.Get_Token(TelegramId)
        if not Token:
            await Update.message.reply_text("❌ You Are Not Connected. Use /connect First.")
            return

        Url = f"https://api.github.com/repos/{Repo}/contributors?per_page=10"
        Headers = {"Authorization": f"token {Token}"}
        Response = requests.get(Url, headers=Headers, timeout=10)

        if Response.status_code != 200:
            await Update.message.reply_text(f"❌ Failed To Fetch Contributors: {Response.text}")
            return

        Contributors = Response.json()

        if not Contributors:
            await Update.message.reply_text("👥 No Contributors Found")
            return

        message = (
            "👥 <b>TOP CONTRIBUTORS</b> 👥\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 <b>Repository:</b> <code>{Repo}</code>\n\n"
        )

        for i, contributor in enumerate(Contributors[:10], 1):
            login = contributor.get('login', 'Unknown')
            contributions = contributor.get('contributions', 0)
            avatar_url = contributor.get('avatar_url', '')

            message += f"{i}. <a href='https://github.com/{login}'>@{login}</a> - {contributions:,} commits\n"

        message += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        message += "👨‍💻 <b>Developed By:</b> <code>I8O8I DEVELOPER</code>"

        await Update.message.reply_text(message, parse_mode="HTML")
    except requests.exceptions.RequestException as e:
        logger.error(f"Network Error Fetching Contributors For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text("❌ Network Error Occurred While Fetching Contributors. Please Try Again.")
    except Exception as e:
        logger.error(f"Unexpected Error Fetching Contributors For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text("❌ An Unexpected Error Occurred While Fetching Contributors.")

# ---------------- Flask Routes ----------------
@App.route("/")
def Home():
    return "✅ GitTracer Bot Running"

@App.route("/health")
def Health():
    """Health Check Endpoint For Monitoring."""
    try:
        # Check database connectivity
        db_status = DataBase.check_database_connection()
        if not db_status:
            return jsonify({"status": "unhealthy", "database": "disconnected"}), 503

        return jsonify({
            "status": "healthy",
            "database": "connected",
            "timestamp": time.time()
        }), 200
    except Exception as e:
        logger.error(f"Health Check Failed: {e}")
        return jsonify({"status": "unhealthy", "error": str(e)}), 503

@App.route("/callback")
def Callback():
    """Handle GitHub OAuth Callback."""
    try:
        code = request.args.get("code")
        telegram_id = request.args.get("state")

        if not code or not telegram_id:
            logger.warning("Missing Authorization Code Or State In Callback")
            return "❌ Missing Authorization Code Or State.", 400

        token_url = "https://github.com/login/oauth/access_token"
        data = {"client_id": github_client_id, "client_secret": github_client_secret, "code": code}
        headers = {"Accept": "application/json"}
        response = requests.post(token_url, data=data, headers=headers, timeout=10)
        token_json = response.json()

        access_token = token_json.get("access_token")
        if not access_token:
            logger.error(f"Failed To Get Access Token: {token_json}")
            return f"❌ Failed To Get Token: {token_json}", 400

        user_info = requests.get("https://api.github.com/user", headers={"Authorization": f"token {access_token}"}, timeout=10).json()

        if "login" not in user_info:
            logger.error(f"Failed To Fetch User Info: {user_info}")
            return f"❌ Failed To Fetch User Info: {user_info}", 400

        github_username = user_info["login"]
        if not DataBase.Save_User(int(telegram_id), github_username, access_token):
            logger.error(f"Failed To Save User {telegram_id}")
            return "❌ Failed To Save User Data.", 500

        logger.info(f"User {telegram_id} Connected As GitHub user {github_username}")
        success_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GitTracker Bot - Connected!</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            color: white;
        }}
        .container {{
            background: rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 40px;
            text-align: center;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            max-width: 500px;
        }}
        .success-icon {{
            font-size: 4em;
            margin-bottom: 20px;
        }}
        .title {{
            font-size: 2em;
            margin-bottom: 10px;
            font-weight: bold;
        }}
        .subtitle {{
            font-size: 1.2em;
            margin-bottom: 30px;
            opacity: 0.9;
        }}
        .username {{
            background: rgba(255, 255, 255, 0.2);
            padding: 10px 20px;
            border-radius: 10px;
            display: inline-block;
            margin-bottom: 30px;
            font-weight: bold;
        }}
        .next-steps {{
            text-align: left;
            background: rgba(255, 255, 255, 0.1);
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .developer {{
            font-size: 0.9em;
            opacity: 0.7;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="success-icon">✅</div>
        <div class="title">Connection Successful!</div>
        <div class="subtitle">Welcome to GitTracker Bot</div>
        <div class="username">@{github_username}</div>

        <div class="next-steps">
            <strong>🎯 Next Steps:</strong><br><br>
            1. Return to Telegram<br>
            2. Use <code>/setrepo owner/repo</code> To Connect Repositories<br>
            3. Start Receiving GitHub Notifications!<br><br>
            <em>Example: /setrepo microsoft/vscode</em>
        </div>

        <div class="developer">
            👨‍💻 Developed by <strong>I8O8I DEVELOPER</strong>
        </div>
    </div>
</body>
</html>
"""
        return success_html, 200
    except requests.exceptions.RequestException as e:
        logger.error(f"Network Error During GitHub Authentication: {e}")
        return "❌ Network Error During GitHub Authentication.", 500
    except Exception as e:
        logger.error(f"Unexpected Error During Authentication: {e}")
        return "❌ An Unexpected Error Occurred During Authentication.", 500

@App.route("/webhook", methods=["POST"])
def Webhook():
    """Handle GitHub Webhook Events With Signature Verification."""
    try:
        # Get Raw Payload And Signature
        payload = request.get_data()
        signature = request.headers.get("X-Hub-Signature-256")
        event_type = request.headers.get("X-GitHub-Event")

        logger.info(f"Received Webhook Event: {event_type}")

        # Verify Webhook Signature If Secret Is Configured
        if Config.config.github.webhook_secret:
            if not verify_webhook_signature(payload, signature, Config.config.github.webhook_secret):
                logger.warning("Invalid Webhook Signature Received")
                return jsonify({"error": "Invalid Signature"}), 401

        # Parse JSON Payload
        try:
            data = request.get_json()
        except Exception as e:
            logger.error(f"Failed To Parse Webhook JSON: {e}")
            return jsonify({"error": "Invalid JSON"}), 400

        if not data:
            logger.warning("Empty Webhook Payload Received")
            return jsonify({"error": "Empty Payload"}), 400

        # Process Different Event Types
        if event_type == "push":
            return handle_push_event(data)
        elif event_type == "pull_request":
            return handle_pull_request_event(data)
        elif event_type == "issues":
            return handle_issues_event(data)
        elif event_type == "create":
            return handle_create_event(data)
        elif event_type == "delete":
            return handle_delete_event(data)
        elif event_type == "release":
            return handle_release_event(data)
        else:
            logger.info(f"Ignored Unsupported Event Type: {event_type}")
            return jsonify({"status": "ignored"}), 200

    except Exception as e:
        logger.error(f"Webhook Processing Error: {e}", exc_info=True)
        return jsonify({"error": "Internal Server Error"}), 500


def handle_push_event(data: dict) -> tuple:
    """Handle GitHub Push Events."""
    try:
        repo_name = data.get("repository", {}).get("full_name")
        if not repo_name:
            logger.warning("Push Event Missing Repository Name")
            return jsonify({"error": "Missing Repository"}), 400

        # Get All Connections For This Repository
        connections = DataBase.get_user_repo_connections_by_repo(repo_name)
        if not connections:
            logger.info(f"No Connections Found For Repository: {repo_name}")
            return jsonify({"status": "No Connections"}), 200

        commits = data.get("commits", [])
        if not commits:
            logger.info("Push Event With No Commits")
            return jsonify({"status": "No Commits"}), 200

        # Process Commits And Send To All Connected Chats
        for connection in connections:
            try:
                chat_id = connection["Chat_Id"]
                message = format_push_message(data, commits, connection)
                asyncio.run_coroutine_threadsafe(
                    send_message_to_chat(chat_id, message, connection),
                    BotLoop
                )
            except Exception as e:
                chat_id = connection.get("Chat_Id", "Unknown")
                logger.error(f"Failed To Send Push Message To Chat {chat_id}: {e}")

        return jsonify({"status": "Processed"}), 200

    except Exception as e:
        logger.error(f"Push Event Handling Error: {e}", exc_info=True)
        return jsonify({"error": "Push Processing Failed"}), 500


def handle_pull_request_event(data: dict) -> tuple:
    """Handle GitHub Pull Request Events."""
    try:
        repo_name = data.get("repository", {}).get("full_name")
        action = data.get("action")

        if not repo_name or not action:
            logger.warning("Pull Request Event Missing Required Fields")
            return jsonify({"error": "Missing Fields"}), 400

        # Get Connections And Send Notification
        connections = DataBase.get_user_repo_connections_by_repo(repo_name)
        for connection in connections:
            try:
                chat_id = connection["Chat_Id"]
                message = format_pr_message(data, connection)
                asyncio.run_coroutine_threadsafe(
                    send_message_to_chat(chat_id, message, connection),
                    BotLoop
                )
            except Exception as e:
                chat_id = connection.get("Chat_Id", "Unknown")
                logger.error(f"Failed To Send PR Message To Chat {chat_id}: {e}")

        return jsonify({"status": "Processed"}), 200

    except Exception as e:
        logger.error(f"Pull Request Event Handling Error: {e}", exc_info=True)
        return jsonify({"error": "PR Processing Failed"}), 500


def handle_issues_event(data: dict) -> tuple:
    """Handle GitHub Issues Events."""
    try:
        repo_name = data.get("repository", {}).get("full_name")
        action = data.get("action")

        if not repo_name or not action:
            logger.warning("Issues Event Missing Required Fields")
            return jsonify({"error": "Missing Fields"}), 400

        # Get Connections And Send Notification
        connections = DataBase.get_user_repo_connections_by_repo(repo_name)
        for connection in connections:
            try:
                chat_id = connection["Chat_Id"]
                message = format_issue_message(data, connection)
                asyncio.run_coroutine_threadsafe(
                    send_message_to_chat(chat_id, message, connection),
                    BotLoop
                )
            except Exception as e:
                chat_id = connection.get("Chat_Id", "Unknown")
                logger.error(f"Failed To Send Issue Message To Chat {chat_id}: {e}")

        return jsonify({"status": "Processed"}), 200

    except Exception as e:
        logger.error(f"Issues Event Handling Error: {e}", exc_info=True)
        return jsonify({"error": "Issue Processing Failed"}), 500


def handle_create_event(data: dict) -> tuple:
    """Handle GitHub Create Events (Branch/Tag Creation)."""
    try:
        repo_name = data.get("repository", {}).get("full_name")
        ref_type = data.get("ref_type")
        ref = data.get("ref")

        if not repo_name or not ref_type or not ref:
            logger.warning("Create Event Missing Required Fields")
            return jsonify({"error": "Missing Fields"}), 400

        connections = DataBase.get_user_repo_connections_by_repo(repo_name)
        message = (
            "🌱 <b>BRANCH/TAG CREATED</b> 🌱\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 <b>Repository:</b> <code>{repo_name.split('/')[1]}</code>\n"
            f"� <b>Type:</b> {ref_type.capitalize()}\n"
            f"📝 <b>Name:</b> <code>{ref}</code>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👨‍💻 <b>Developed by:</b> <code>I8O8I DEVELOPER</code>"
        )

        for connection in connections:
            try:
                chat_id = connection["Chat_Id"]
                asyncio.run_coroutine_threadsafe(
                    send_message_to_chat(chat_id, message, connection),
                    BotLoop
                )
            except Exception as e:
                chat_id = connection.get("Chat_Id", "Unknown")
                logger.error(f"Failed To Send Create Message To Chat {chat_id}: {e}")

        return jsonify({"status": "Processed"}), 200

    except Exception as e:
        logger.error(f"Create Event Handling Error: {e}", exc_info=True)
        return jsonify({"error": "Create Processing Failed"}), 500


def handle_delete_event(data: dict) -> tuple:
    """Handle GitHub Delete Events (Branch/Tag Deletion)."""
    try:
        repo_name = data.get("repository", {}).get("full_name")
        ref_type = data.get("ref_type")
        ref = data.get("ref")

        if not repo_name or not ref_type or not ref:
            logger.warning("Delete Event Missing Required Fields")
            return jsonify({"error": "Missing Fields"}), 400

        connections = DataBase.get_user_repo_connections_by_repo(repo_name)
        message = (
            "🗑️ <b>BRANCH/TAG DELETED</b> 🗑️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"� <b>Repository:</b> <code>{repo_name.split('/')[1]}</code>\n"
            f"❌ <b>Type:</b> {ref_type.capitalize()}\n"
            f"📝 <b>Name:</b> <code>{ref}</code>\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👨‍💻 <b>Developed by:</b> <code>I8O8I DEVELOPER</code>"
        )

        for connection in connections:
            try:
                chat_id = connection["Chat_Id"]
                asyncio.run_coroutine_threadsafe(
                    send_message_to_chat(chat_id, message, connection),
                    BotLoop
                )
            except Exception as e:
                chat_id = connection.get("Chat_Id", "Unknown")
                logger.error(f"Failed To Send Delete Message To Chat {chat_id}: {e}")

        return jsonify({"status": "Processed"}), 200

    except Exception as e:
        logger.error(f"Delete Event Handling Error: {e}", exc_info=True)
        return jsonify({"error": "Delete Processing Failed"}), 500


def handle_release_event(data: dict) -> tuple:
    """Handle GitHub Release Events."""
    try:
        repo_name = data.get("repository", {}).get("full_name")
        action = data.get("action")

        if not repo_name or not action:
            logger.warning("Release Event Missing Required Fields")
            return jsonify({"error": "Missing Fields"}), 400

        # Get Connections And Send Notification
        connections = DataBase.get_user_repo_connections_by_repo(repo_name)
        for connection in connections:
            try:
                chat_id = connection["Chat_Id"]
                message = format_release_message(data, connection)
                asyncio.run_coroutine_threadsafe(
                    send_message_to_chat(chat_id, message, connection),
                    BotLoop
                )
            except Exception as e:
                chat_id = connection.get("Chat_Id", "Unknown")
                logger.error(f"Failed To Send Release Message To Chat {chat_id}: {e}")

        return jsonify({"status": "Processed"}), 200

    except Exception as e:
        logger.error(f"Release Event Handling Error: {e}", exc_info=True)
        return jsonify({"error": "Release Processing Failed"}), 500


def format_release_message(data: dict, connection: dict) -> str:
    """Format Release Event Message With Attractive UI."""
    release = data.get("release", {})
    repo_name = data.get("repository", {}).get("name", "Unknown")
    action = data.get("action", "published")

    # Choose Emoji Based on Action
    action_emoji = {
        "published": "📦",
        "unpublished": "🚫",
        "created": "🆕",
        "edited": "✏️",
        "deleted": "🗑️",
        "prereleased": "🔬",
        "released": "🚀"
    }.get(action, "📦")

    message = (
        f"{action_emoji} <b>RELEASE {action.upper()}</b> {action_emoji}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 <b>Repository:</b> <code>{repo_name}</code>\n"
        f"🏷️ <b>Tag:</b> <code>{release.get('tag_name')}</code>\n\n"
        f"📝 <b>Title:</b> {release.get('name')}\n\n"
        f"👨‍� <b>Author:</b> {release.get('author', {}).get('login', 'Unknown')}\n"
    )

    # Add Release Notes If Available
    body = release.get('body')
    if body:
        body_preview = body[:200] + ('...' if len(body) > 200 else '')
        message += f"\n📄 <b>Release Notes:</b>\n<code>{body_preview}</code>\n"

    # Add Prerelease Info
    if release.get('prerelease'):
        message += "🔬 <b>Status:</b> Pre-release\n"

    message += f"\n🔗 <a href='{release.get('html_url')}'>🔍 View Release</a>\n\n"
    message += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    message += "👨‍💻 <b>Developed by:</b> <code>I8O8I DEVELOPER</code>"

    return message


async def send_message_to_chat(chat_id: int, message: str, connection: dict = None):
    """Send Message To Specific Telegram Chat."""
    try:
        # Handle Topic-Specific Messages For SuperGroups
        if connection and connection.get("Topic_Id") and connection.get("Chat_Type") == "supergroup":
            await BotApp.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="HTML",
                message_thread_id=connection["Topic_Id"]
            )
        else:
            await BotApp.bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
        logger.info(f"Message Sent To Chat {chat_id}")
    except Exception as e:
        logger.error(f"Failed To Send Message To Chat {chat_id}: {e}")


def format_push_message(data: dict, commits: list, connection: dict) -> str:
    """Format Push Event Message With Attractive UI."""
    repo_name = data.get("repository", {}).get("name", "Unknown")
    branch = data.get("ref", "").split("/")[-1]
    pusher = data.get("pusher", {}).get("name", "Unknown")
    compare_url = data.get("compare", "")

    message = (
        "� <b>GIT PUSH DETECTED!</b> 🚀\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 <b>Repository:</b> <code>{repo_name}</code>\n"
        f"🌿 <b>Branch:</b> <code>{branch}</code>\n"
        f"�‍💻 <b>Pushed by:</b> {pusher}\n"
        f"📊 <b>Commits:</b> {len(commits)}\n"
    )

    if compare_url:
        message += f"🔗 <a href='{compare_url}'>📊 Compare Changes</a>\n"

    message += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    message += "📝 <b>COMMIT DETAILS:</b>\n\n"

    for i, commit in enumerate(commits[:5], 1):  # Limit To 5 Commits
        tag = GetCommitTag(commit.get("message", ""))
        short_sha = commit.get("id", "")[:7]
        commit_url = commit.get("url", "")
        author = commit.get("author", {}).get("name", "Unknown")
        commit_msg = commit.get("message", "").split('\n')[0]

        message += f"#{i} {tag} <code>{short_sha}</code>\n"
        message += f"   💬 {commit_msg}\n"
        message += f"   👤 <i>{author}</i>"
        if commit_url:
            message += f" | <a href='{commit_url}'>🔗 View</a>"
        message += "\n\n"

    if len(commits) > 5:
        message += f"⋯⋯ And {len(commits) - 5} More Commits ⋯⋯\n\n"

    message += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    message += "👨‍💻 <b>Developed by:</b> <code>I8O8I DEVELOPER</code>"

    return message


def format_pr_message(data: dict, connection: dict) -> str:
    """Format Pull Request Event Message With Attractive UI."""
    pr = data.get("pull_request", {})
    repo_name = data.get("repository", {}).get("name", "Unknown")
    action = data.get("action", "updated")

    # Choose Emoji Based on Action
    action_emoji = {
        "opened": "🆕",
        "closed": "❌",
        "merged": "✅",
        "reopened": "🔄",
        "ready_for_review": "👀"
    }.get(action, "🔀")

    message = (
        f"{action_emoji} <b>PULL REQUEST {action.upper()}</b> {action_emoji}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 <b>Repository:</b> <code>{repo_name}</code>\n"
        f"🔢 <b>PR #{pr.get('number')}</b>\n\n"
        f"📝 <b>Title:</b> {pr.get('title')}\n\n"
        f"👨‍� <b>Author:</b> {pr.get('user', {}).get('login', 'Unknown')}\n"
    )

    # Add Additional Info If Available
    if pr.get('merged'):
        message += "✅ <b>Status:</b> Merged\n"
    elif pr.get('state') == 'closed':
        message += "❌ <b>Status:</b> Closed\n"
    else:
        message += "🟡 <b>Status:</b> Open\n"

    if pr.get('additions') is not None and pr.get('deletions') is not None:
        additions = pr.get('additions', 0)
        deletions = pr.get('deletions', 0)
        message += f"📈 <b>Changes:</b> +{additions} -{deletions} Lines\n"

    message += f"\n🔗 <a href='{pr.get('html_url')}'>🔍 View Pull Request</a>\n\n"
    message += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    message += "👨‍💻 <b>Developed by:</b> <code>I8O8I DEVELOPER</code>"

    return message


def format_issue_message(data: dict, connection: dict) -> str:
    """Format Issue Event Message With Attractive UI."""
    issue = data.get("issue", {})
    repo_name = data.get("repository", {}).get("name", "Unknown")
    action = data.get("action", "updated")

    # Choose Emoji Based On Action
    action_emoji = {
        "opened": "🆕",
        "closed": "✅",
        "reopened": "🔄",
        "assigned": "👤",
        "unassigned": "👤",
        "labeled": "🏷️",
        "unlabeled": "🏷️"
    }.get(action, "🐛")

    message = (
        f"{action_emoji} <b>ISSUE {action.upper()}</b> {action_emoji}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📦 <b>Repository:</b> <code>{repo_name}</code>\n"
        f"🔢 <b>Issue #{issue.get('number')}</b>\n\n"
        f"📝 <b>Title:</b> {issue.get('title')}\n\n"
        f"👨‍� <b>Author:</b> {issue.get('user', {}).get('login', 'Unknown')}\n"
    )

    # Add Status and Labels If Available
    if issue.get('state'):
        state_emoji = "🟢" if issue['state'] == 'open' else "🔴"
        message += f"{state_emoji} <b>Status:</b> {issue['state'].title()}\n"

    if issue.get('labels'):
        labels = [f"#{label['name']}" for label in issue['labels'][:3]]  # Limit to 3 labels
        if labels:
            message += f"🏷️ <b>Labels:</b> {' '.join(labels)}\n"

    # Add Assignees If Available
    if issue.get('assignees'):
        assignees = [assignee['login'] for assignee in issue['assignees'][:3]]
        if assignees:
            message += f"👥 <b>Assignees:</b> {', '.join(assignees)}\n"

    message += f"\n🔗 <a href='{issue.get('html_url')}'>🔍 View Issue</a>\n\n"
    message += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    message += "👨‍💻 <b>Developed by:</b> <code>I8O8I DEVELOPER</code>"

    return message

# ---------------- Main ----------------
def RunFlask():
    """Run Flask Server With Production Configuration."""
    try:
        logger.info(f"Starting Flask Server On {Config.config.server.host}:{Config.config.server.port}")
        App.run(
            host=Config.config.server.host,
            port=Config.config.server.port,
            debug=Config.config.server.debug,
            threaded=True
        )
    except Exception as e:
        logger.critical(f"Flask Server Error: {e}")
        raise

if __name__ == "__main__":
    try:
        logger.info("Starting GitTracker Bot...")
        ApplicationInstance = Application.builder().token(telegram_token).build()
        BotApp = ApplicationInstance

        # Register Command Handlers
        commands = [
            ("start", Start),
            ("connect", Connect),
            ("setrepo", SetRepo),
            ("getrepo", GetRepo),
            ("removerepo", RemoveRepo),
            ("comment", Comment),
            ("listwebhooks", ListWebhooks),
            ("delwebhook", DelWebhook),
            ("stats", Stats),
            ("recent", Recent),
            ("branches", Branches),
            ("contributors", Contributors),
        ]

        for command, handler in commands:
            ApplicationInstance.add_handler(CommandHandler(command, handler))
            logger.debug(f"Registered Command Handler: {command}")

        # Start Flask Server In Background Thread
        flask_thread = threading.Thread(target=RunFlask, daemon=True)
        flask_thread.start()
        logger.info(f"Flask Server Started On {Config.config.server.host}:{Config.config.server.port}")

        # Start Telegram Bot
        logger.info("Starting Telegram Bot Polling...")
        BotLoop = asyncio.get_event_loop()
        ApplicationInstance.run_polling()

    except KeyboardInterrupt:
        logger.info("Bot Stopped By User")
    except Exception as e:
        logger.critical(f"Failed To Start Bot: {e}")
        exit(1)