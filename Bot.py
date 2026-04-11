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
import signal
import sys
import textwrap
from flask import Flask, request, jsonify, render_template
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from typing import Optional
from werkzeug.middleware.proxy_fix import ProxyFix

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
App = Flask(__name__, template_folder="Templates")
App.wsgi_app = ProxyFix(App.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)
ApplicationInstance = None
BotApp = None
BotLoop = None   # Store Telegram Bot Loop
BotThread = None
BotStartupError = None
BotReady = False
BotStartTime = time.time()

# ---------------- Helper Functions ----------------
def build_public_url(path: str) -> str:
    """Build An Absolute Public URL From The Configured Base URL."""
    if not webhook_url:
        raise ValueError("WEBHOOK_URL Environment Variable Is Required For Webhook Mode")

    normalized_path = path if path.startswith("/") else f"/{path}"
    return f"{webhook_url}{normalized_path}"


def telegram_bot_is_ready() -> bool:
    """Return Whether The Telegram Application Is Ready To Process Webhooks."""
    return (
        BotReady
        and BotApp is not None
        and BotLoop is not None
        and not BotLoop.is_closed()
        and BotLoop.is_running()
    )


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
    welcome_message = build_message_card(
        "Welcome to GitTracker Bot!",
        [
            "🚀 Your GitHub Repository Monitor In Telegram.",
            "",
            "📋 Available commands:",
            "🔗 <code>/connect</code> — Link Your GitHub Account",
            "📌 <code>/setrepo Owner/Repo</code> — Add Repository Tracking",
            "📥 <code>/getrepo</code> — Show Connected Repositories",
            "💬 <code>/comment Owner/Repo #ID Message</code> — Post a Comment",
            "📊 <code>/stats Owner/Repo</code> — Repository Overview",
            "📋 <code>/listwebhooks</code> — View Repository Webhooks",
            "🗑 <code>/removerepo Owner/Repo</code> — Stop Notifications",
            "",
            "✨ Features:",
            "• Real-time GitHub Activity Alerts",
            "• Multi-Chat Repository Support",
            "• Issue, PR, Push, Release Tracking",
            "• Secure Webhook Integration",
            "",
            "🌟 Version: Production v2.0"
        ],
        emoji="🎉"
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
        connect_msg = build_message_card(
            "Connect Your GitHub Account",
            [
                "Click The Link Below To Authorize GitTracker Bot.",
                f"🔗 <a href='{auth_url}'>Authorize GitHub Access</a>",
                "",
                "📋 Permissions Requested:",
                "• Read Access To Your Repositories",
                "• Create Webhooks For Notifications",
                "",
                "🔒 Your Data Is Handled Securely And Privately."
            ],
            emoji="🔗"
        )
        await Update.message.reply_text(connect_msg, parse_mode="HTML")
        logger.info(f"Generated GitHub Auth URL For User {telegram_id}")
    except Exception as e:
        error_msg = build_error_card(
            "Connection Error",
            [
                "Unable To Generate The GitHub Authorization Link.",
                "Please Try Again Later Or Contact Support If This Continues."
            ]
        )
        await Update.message.reply_text(error_msg, parse_mode="HTML")
        logger.error(f"Error Generating Connection Link For User {Update.effective_user.id}: {e}")


async def Help(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    """Show A Friendly Help Menu."""
    help_message = build_message_card(
        "Bot Help",
        [
            "Use Any Of The Commands Below To Manage Your GitHub Tracking:",
            "",
            "🔗 <code>/connect</code> — Link Your GitHub Account",
            "📌 <code>/setrepo Owner/Repo</code> — Add Repository Tracking",
            "📥 <code>/getrepo</code> — Show Connected Repositories",
            "🗑 <code>/removerepo Owner/Repo</code> — Remove A Repository Connection",
            "💬 <code>/comment Owner/Repo #ID Message</code> — Post Issue Or PR Comments",
            "📊 <code>/stats Owner/Repo</code> — Show Repository Statistics",
            "🕒 <code>/recent Owner/Repo</code> — Show Recent Commits",
            "🌿 <code>/branches Owner/Repo</code> — Show Repository Branches",
            "👥 <code>/contributors Owner/Repo</code> — Show Top Contributors",
            "📈 <code>/status</code> — Show Bot And Service Status",
            "ℹ️ <code>/about</code> — About GitTracker Bot"
        ],
        emoji="📘"
    )
    await Update.message.reply_text(help_message, parse_mode="HTML")


async def About(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    """Show Bot About Information."""
    about_message = build_message_card(
        "About GitTracker Bot",
        [
            "GitTracker Bot Sends GitHub Repository Events Directly To Telegram.",
            "",
            "• Real-Time Push, Pull Request, Issue, And Release Tracking",
            "• Secure GitHub Webhook Integration",
            "• Clean And Consistent Message Formatting",
            "• Multi-Chat And Topic Support",
            "",
            f"• Domain: <code>{Config.config.server.webhook_url or 'Not Configured'}</code>"
        ],
        emoji="🤖"
    )
    await Update.message.reply_text(about_message, parse_mode="HTML")


async def Status(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    """Show Bot Status And Health Metrics."""
    try:
        uptime_seconds = int(time.time() - BotStartTime)
        uptime_hours = uptime_seconds // 3600
        uptime_minutes = (uptime_seconds % 3600) // 60
        uptime_seconds = uptime_seconds % 60

        TelegramId = Update.effective_user.id
        Connections = DataBase.Get_User_Repo_Connections(TelegramId)
        connection_count = len(Connections) if Connections else 0

        status_message = build_message_card(
            "Bot Status",
            [
                f"🟢 Bot Status : Running",
                f"⏱ Uptime: {uptime_hours}h {uptime_minutes}m {uptime_seconds}s",
                f"📦 Connected Repositories: {connection_count}",
                f"🌐 Webhook Domain: <code>{Config.config.server.webhook_url or 'Not Configured'}</code>",
                f"🖥 Server Host: <code>{Config.config.server.host}:{Config.config.server.port}</code>"
            ],
            emoji="📈"
        )
        await Update.message.reply_text(status_message, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error Generating Status For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text(
            build_error_card(
                "Status Error",
                ["Unable To Generate Status Right Now.", "Please Try Again Later."]
            ),
            parse_mode="HTML"
        )

async def SetRepo(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        if not Context.args:
            await Update.message.reply_text(
                build_warning_card(
                    "Set Repository",
                    ["Usage: <code>/setrepo Owner/Repo</code> Or A Full GitHub URL"]
                ),
                parse_mode="HTML"
            )
            return

        RepoInput = Context.args[0]

        # Validate Repository Input
        Repo = validate_github_repo(RepoInput)
        if not Repo:
            await Update.message.reply_text(
                build_error_card(
                    "Invalid Repository",
                    ["Use Owner/Repo Format Or A GitHub URL Like <code>https://github.com/owner/repo</code>"]
                ),
                parse_mode="HTML"
            )
            return

        TelegramId = Update.effective_user.id
        ChatId = Update.effective_chat.id
        ChatType = Update.effective_chat.type
        TopicId = getattr(Update.effective_message, 'message_thread_id', None) if ChatType == 'supergroup' else None

        Token = DataBase.Get_Token(TelegramId)
        if not Token:
            await Update.message.reply_text(
                build_warning_card(
                    "Account Not Connected",
                    ["Please Use <code>/connect</code> Before Adding A Repository."]
                ),
                parse_mode="HTML"
            )
            return

        # Check If Repository Connection Already Exists For This Chat
        existing_connections = DataBase.get_user_repo_connections(TelegramId)
        for conn in existing_connections:
            if conn['Repo_Name'] == Repo and conn['Chat_Id'] == ChatId and conn['Topic_Id'] == TopicId:
                await Update.message.reply_text(
                    build_warning_card(
                        "Already Connected",
                        [f"Repository <code>{Repo}</code> Is Already Connected For This Chat."]
                    ),
                    parse_mode="HTML"
                )
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
            success_msg = build_success_card(
                "Repository Connected",
                [
                    f"📦 Repository: <code>{Repo}</code>",
                    f"🔗 Webhook: Installed And Active",
                    f"📱 Chat: {ChatType.capitalize()}",
                    "",
                    "You Will Now Receive Updates For:",
                    "• Pushes And Commits",
                    "• Pull Request Activity",
                    "• Issues And Comments",
                    "• Branch/Tag Creations And Deletions",
                    "• Releases"
                ]
            )
            await Update.message.reply_text(success_msg, parse_mode="HTML")
            logger.info(f"Repository {Repo} Connected For User {TelegramId} In Chat {ChatId}")
        else:
            error_msg = build_warning_card(
                "Repository Added With Warnings",
                [
                    f"📦 Repository: <code>{Repo}</code>",
                    "🔗 Webhook Installation Failed",
                    "",
                    f"GitHub Response: <code>{Response.text}</code>",
                    "",
                    "The Repository Is Saved, But Webhook Delivery May Not Be Active.",
                    "Please Verify The Webhook Settings On GitHub If Needed."
                ]
            )
            await Update.message.reply_text(error_msg, parse_mode="HTML")
            logger.warning(f"Failed To Create Webhook For {Repo}: {Response.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Network Error Setting Repo For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text(
            build_error_card(
                "Network Error",
                ["Unable To Connect To GitHub At This Time.", "Please Try Again In A Few Minutes."]
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Unexpected Error Setting Repo For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text(
            build_error_card(
                "Unexpected Error",
                ["An Unexpected Error Occurred While Setting The Repository.", "Please Try Again Later."]
            ),
            parse_mode="HTML"
        )

async def GetRepo(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        TelegramId = Update.effective_user.id
        Connections = DataBase.Get_User_Repo_Connections(TelegramId)
        if Connections:
            lines = [
                "Here Are The Repositories Currently Connected To This Account:",
                ""
            ]
            for i, Conn in enumerate(Connections, 1):
                ChatType = Conn['Chat_Type']
                TopicInfo = f" (Topic: {Conn['Topic_Id']})" if Conn['Topic_Id'] else ""
                chat_emoji = {
                    'private': '👤',
                    'group': '👥',
                    'supergroup': '🏢'
                }.get(ChatType, '💬')

                lines.append(f"{i}. {chat_emoji} <code>{Conn['Repo_Name']}</code>")
                lines.append(f"   • {ChatType.capitalize()}{TopicInfo}")
                lines.append("")

            message = build_message_card("Connected Repositories", lines)
            await Update.message.reply_text(message, parse_mode="HTML")
        else:
            no_connections_msg = build_warning_card(
                "No Repository Connections",
                [
                    "You Haven't Connected Any Repositories Yet.",
                    "",
                    "To Get Started:",
                    "• Use <code>/connect</code> To Link Your GitHub Account.",
                    "• Use <code>/setrepo Owner/Repo</code> To Add A Repository."
                ]
            )
            await Update.message.reply_text(no_connections_msg, parse_mode="HTML")
    except Exception as e:
        await Update.message.reply_text(
            build_error_card(
                "Error Retrieving Connections",
                [
                    "An Unexpected Error Occurred While Fetching Your Repository Connections.",
                    "Please Try Again Later."
                ]
            ),
            parse_mode="HTML"
        )

async def RemoveRepo(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        if not Context.args:
            await Update.message.reply_text(
                build_warning_card(
                    "Remove Repository",
                    ["Usage: <code>/removerepo Owner/Repo</code>"]
                ),
                parse_mode="HTML"
            )
            return

        Repo = Context.args[0]
        TelegramId = Update.effective_user.id
        ChatId = Update.effective_chat.id
        TopicId = getattr(Update.effective_message, 'message_thread_id', None) if Update.effective_chat.type == 'supergroup' else None

        DataBase.Remove_Repo_Connection(TelegramId, Repo, ChatId, TopicId)
        success_msg = build_success_card(
            "Repository Removed",
            [
                f"📦 Repository: <code>{Repo}</code>",
                f"📱 Chat: {Update.effective_chat.type.capitalize()}",
                "",
                "The Repository Connection Has Been Removed For This Chat.",
                "You Will No Longer Receive Notifications Here."
            ]
        )
        await Update.message.reply_text(success_msg, parse_mode="HTML")
    except Exception as e:
        await Update.message.reply_text(
            build_error_card(
                "Removal Failed",
                ["An Error Occurred While Removing The Repository Connection.", "Please Try Again Later."]
            ),
            parse_mode="HTML"
        )

async def Comment(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        if len(Context.args) < 3:
            await Update.message.reply_text(
                build_warning_card(
                    "Post Comment",
                    ["Usage: <code>/comment Owner/Repo Issue_Number Message</code>"]
                ),
                parse_mode="HTML"
            )
            return

        RepoInput = Context.args[0]
        IssueNumberStr = Context.args[1]
        CommentText = " ".join(Context.args[2:])

        # Validate Inputs
        Repo = validate_github_repo(RepoInput)
        if not Repo:
            await Update.message.reply_text(
                build_error_card(
                    "Invalid Repository",
                    ["Use A Valid Owner/Repo Format."]
                ),
                parse_mode="HTML"
            )
            return

        IssueNumber = validate_issue_number(IssueNumberStr)
        if not IssueNumber:
            await Update.message.reply_text(
                build_error_card(
                    "Invalid Issue Number",
                    ["Issue Number Must Be A Positive Integer."]
                ),
                parse_mode="HTML"
            )
            return

        if not validate_comment_text(CommentText):
            await Update.message.reply_text(
                build_warning_card(
                    "Invalid Comment",
                    ["Please Provide A Valid Comment Message Without Unsafe Content."]
                ),
                parse_mode="HTML"
            )
            return

        TelegramId = Update.effective_user.id

        Token = DataBase.Get_Token(TelegramId)
        if not Token:
            await Update.message.reply_text(
                build_warning_card(
                    "Not Connected",
                    ["Please Use <code>/connect</code> To Link Your GitHub Account First."]
                ),
                parse_mode="HTML"
            )
            return

        Url = f"https://api.github.com/repos/{Repo}/issues/{IssueNumber}/comments"
        Headers = {"Authorization": f"token {Token}"}
        Response = requests.post(Url, json={"body": CommentText}, headers=Headers, timeout=10)

        if Response.status_code == 201:
            success_msg = build_success_card(
                "Comment Posted",
                [
                    f"📦 Repository: <code>{Repo}</code>",
                    f"🔢 Issue/PR: #{IssueNumber}",
                    "",
                    f"💬 Comment: <code>{CommentText[:100]}{'...' if len(CommentText) > 100 else ''}</code>"
                ]
            )
            await Update.message.reply_text(success_msg, parse_mode="HTML")
            logger.info(f"Comment Posted By User {TelegramId} on {Repo}#{IssueNumber}")
        else:
            error_msg = build_error_card(
                "Comment Failed",
                [
                    f"📦 Repository: <code>{Repo}</code>",
                    f"🔢 Issue/PR: #{IssueNumber}",
                    "",
                    "Unable To Post Your Comment.",
                    f"GitHub Response: <code>{Response.text}</code>"
                ]
            )
            await Update.message.reply_text(error_msg, parse_mode="HTML")
            logger.warning(f"Failed To Post Comment On {Repo}#{IssueNumber}: {Response.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Network Error Posting Comment For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text(
            build_error_card(
                "Network Error",
                ["Unable To Reach GitHub Right Now.", "Please Try Again Later."]
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Unexpected Error Posting Comment For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text(
            build_error_card(
                "Unexpected Error",
                ["An Unexpected Error Occurred While Posting The Comment.", "Please Try Again Later."]
            ),
            parse_mode="HTML"
        )

async def ListWebhooks(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        TelegramId = Update.effective_user.id
        Repo = DataBase.Get_Default_Repo(TelegramId)
        if not Repo:
            Connections = DataBase.Get_User_Repo_Connections(TelegramId)
            Repo = Connections[0]['Repo_Name'] if Connections else None

        Token = DataBase.Get_Token(TelegramId)

        if not Repo or not Token:
            await Update.message.reply_text(
                build_warning_card(
                    "List Webhooks",
                    ["Please Connect A Repository First With <code>/setrepo</code> And <code>/connect</code>."]
                ),
                parse_mode="HTML"
            )
            return

        Url = f"https://api.github.com/repos/{Repo}/hooks"
        Headers = {"Authorization": f"token {Token}"}
        Response = requests.get(Url, headers=Headers, timeout=10)
        if Response.status_code != 200:
            await Update.message.reply_text(
                build_error_card(
                    "Fetch Failed",
                    [f"Unable To Fetch Webhooks For <code>{Repo}</code>.", f"GitHub Response: <code>{Response.text}</code>"]
                ),
                parse_mode="HTML"
            )
            return

        Hooks = Response.json()
        if not Hooks:
            await Update.message.reply_text(
                build_message_card(
                    "No Webhooks Found",
                    [f"No webhooks are currently installed for <code>{Repo}</code>."]
                ),
                parse_mode="HTML"
            )
            return

        lines = [f"Webhooks for <code>{Repo}</code>:", ""]
        for H in Hooks:
            lines.append(f"• Id: {H['id']} — <code>{H['config']['url']}</code>")

        await Update.message.reply_text(
            build_message_card("Repository Webhooks", lines),
            parse_mode="HTML"
        )
    except requests.exceptions.RequestException as e:
        await Update.message.reply_text(
            build_error_card(
                "Network Error",
                ["Unable To Reach GitHub Right Now.", "Please Try Again Later."]
            ),
            parse_mode="HTML"
        )
    except KeyError as e:
        await Update.message.reply_text(
            build_error_card(
                "Invalid Data",
                ["Received Unexpected Webhook Data From GitHub.", "Try Again Later."]
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        await Update.message.reply_text(
            build_error_card(
                "Error Listing Webhooks",
                ["An Unexpected Error Occurred While Listing Webhooks.", "Please Try Again Later."]
            ),
            parse_mode="HTML"
        )

async def DelWebhook(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        if not Context.args:
            await Update.message.reply_text(
                build_warning_card(
                    "Delete Webhook",
                    ["Usage: <code>/delwebhook HookId</code>"]
                ),
                parse_mode="HTML"
            )
            return
        HookId = Context.args[0]
        TelegramId = Update.effective_user.id
        Repo = DataBase.Get_Default_Repo(TelegramId)
        if not Repo:
            Connections = DataBase.Get_User_Repo_Connections(TelegramId)
            Repo = Connections[0]['Repo_Name'] if Connections else None

        Token = DataBase.Get_Token(TelegramId)

        if not Repo or not Token:
            await Update.message.reply_text(
                build_warning_card(
                    "Webhook Delete",
                    ["Please Use <code>/setrepo</code> And <code>/connect</code> Before Modifying Webhooks."]
                ),
                parse_mode="HTML"
            )
            return

        Url = f"https://api.github.com/repos/{Repo}/hooks/{HookId}"
        Headers = {"Authorization": f"token {Token}"}
        Response = requests.delete(Url, headers=Headers, timeout=10)

        if Response.status_code == 204:
            await Update.message.reply_text(
                build_success_card(
                    "Webhook Deleted",
                    [f"Webhook <code>{HookId}</code> Has Been Removed From <code>{Repo}</code>."]
                ),
                parse_mode="HTML"
            )
        else:
            await Update.message.reply_text(
                build_error_card(
                    "Delete Failed",
                    [f"Unable To Delete Webhook <code>{HookId}</code>.", f"GitHub Response: <code>{Response.text}</code>"]
                ),
                parse_mode="HTML"
            )
    except requests.exceptions.RequestException as e:
        await Update.message.reply_text(
            build_error_card(
                "Network Error",
                ["Unable To Reach GitHub Right Now.", "Please Try Again Later."]
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        await Update.message.reply_text(
            build_error_card(
                "Unexpected Error",
                ["An Unexpected Error Occurred While Deleting The Webhook.", "Please Try Again Later."]
            ),
            parse_mode="HTML"
        )

async def Stats(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        if not Context.args:
            await Update.message.reply_text(
                build_warning_card(
                    "Repository Stats",
                    ["Usage: <code>/stats Owner/Repo</code>"]
                ),
                parse_mode="HTML"
            )
            return

        RepoInput = Context.args[0]

        Repo = validate_github_repo(RepoInput)
        if not Repo:
            await Update.message.reply_text(
                build_error_card(
                    "Invalid Repository",
                    ["Use Owner/Repo or a GitHub URL like <code>https://github.com/owner/repo</code>."]
                ),
                parse_mode="HTML"
            )
            return

        TelegramId = Update.effective_user.id

        Token = DataBase.Get_Token(TelegramId)
        if not Token:
            await Update.message.reply_text(
                build_warning_card(
                    "Not Connected",
                    ["Please Use <code>/connect</code> Before Requesting Repository Stats."]
                ),
                parse_mode="HTML"
            )
            return

        Url = f"https://api.github.com/repos/{Repo}"
        Headers = {"Authorization": f"token {Token}"}
        Response = requests.get(Url, headers=Headers, timeout=10)

        if Response.status_code != 200:
            await Update.message.reply_text(
                build_error_card(
                    "Fetch Failed",
                    [f"Unable To Fetch Stats For <code>{Repo}</code>.", f"GitHub Response: <code>{Response.text}</code>"]
                ),
                parse_mode="HTML"
            )
            return

        Data = Response.json()

        # Extract Stats
        name = Data.get('name', 'Unknown')
        full_name = Data.get('full_name', Repo)
        description = Data.get('description', 'No Description')
        stars = Data.get('stargazers_count', 0)
        forks = Data.get('forks_count', 0)
        issues = Data.get('open_issues_count', 0)
        language = Data.get('language', 'Unknown')
        created = Data.get('created_at', 'Unknown')[:10]
        updated = Data.get('updated_at', 'Unknown')[:10]
        size = Data.get('size', 0)

        stats_message = build_message_card(
            "Repository Statistics",
            [
                f"📦 Name: <code>{name}</code>",
                f"🔗 Full Name: <code>{full_name}</code>",
                f"📝 Description: {description}",
                "",
                f"⭐ Stars: {stars:,}",
                f"🍴 Forks: {forks:,}",
                f"🐛 Open Issues: {issues:,}",
                f"💻 Language: {language}",
                f"📅 Created: {created}",
                f"🔄 Last Updated: {updated}",
                f"💾 Size: {size:,} KB"
            ]
        )

        await Update.message.reply_text(stats_message, parse_mode="HTML")
    except requests.exceptions.RequestException as e:
        logger.error(f"Network Error Fetching Stats For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text(
            build_error_card(
                "Network Error",
                ["Unable To Reach GitHub Right Now.", "Please Try Again Later."]
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Unexpected Error Fetching Stats For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text(
            build_error_card(
                "Unexpected Error",
                ["An Unexpected Error Occurred While Fetching Repository Statistics.", "Please Try Again Later."]
            ),
            parse_mode="HTML"
        )

async def Recent(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        if not Context.args:
            await Update.message.reply_text(
                build_warning_card(
                    "Recent Commits",
                    ["Usage: <code>/recent Owner/Repo</code>"]
                ),
                parse_mode="HTML"
            )
            return

        RepoInput = Context.args[0]

        Repo = validate_github_repo(RepoInput)
        if not Repo:
            await Update.message.reply_text(
                build_error_card(
                    "Invalid Repository",
                    ["Use Owner/Repo Or A GitHub URL Like <code>https://github.com/owner/repo</code>."]
                ),
                parse_mode="HTML"
            )
            return

        TelegramId = Update.effective_user.id

        Token = DataBase.Get_Token(TelegramId)
        if not Token:
            await Update.message.reply_text(
                build_warning_card(
                    "Not Connected",
                    ["Please Use <code>/connect</code> Before Fetching Recent Commits."]
                ),
                parse_mode="HTML"
            )
            return

        Url = f"https://api.github.com/repos/{Repo}/commits?per_page=10"
        Headers = {"Authorization": f"token {Token}"}
        Response = requests.get(Url, headers=Headers, timeout=10)

        if Response.status_code != 200:
            await Update.message.reply_text(
                build_error_card(
                    "Fetch Failed",
                    [f"Unable To Retrieve Commits For <code>{Repo}</code>.", f"GitHub Response: <code>{Response.text}</code>"]
                ),
                parse_mode="HTML"
            )
            return

        Commits = Response.json()

        if not Commits:
            await Update.message.reply_text(
                build_message_card(
                    "No Recent Commits",
                    [f"No Recent Commits Were Found For <code>{Repo}</code>."]
                ),
                parse_mode="HTML"
            )
            return

        lines = [f"Recent Commits For <code>{Repo}</code>:", ""]
        for i, commit in enumerate(Commits[:10], 1):
            sha = commit.get('sha', '')[:7]
            author = commit.get('commit', {}).get('author', {}).get('name', 'Unknown')
            message_commit = commit.get('commit', {}).get('message', '').split('\n')[0]
            date = commit.get('commit', {}).get('author', {}).get('date', '')[:10]
            url = commit.get('html_url', '')
            tag = GetCommitTag(message_commit)

            commit_line = f"{i}. {tag} <code>{sha}</code> — {message_commit}"
            lines.append(commit_line)
            lines.append(f"   👤 {author} | 📅 {date}")
            if url:
                lines.append(f"   🔗 <a href='{url}'>View Commit</a>")
            lines.append("")

        await Update.message.reply_text(
            build_message_card("Recent Commits", lines),
            parse_mode="HTML"
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Network Error Fetching Recent Commits For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text(
            build_error_card(
                "Network Error",
                ["Unable To Reach GitHub Right Now.", "Please Try Again Later."]
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Unexpected Error Fetching Recent Commits For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text(
            build_error_card(
                "Unexpected Error",
                ["An Unexpected Error Occurred While Fetching Recent Commits.", "Please Try Again Later."]
            ),
            parse_mode="HTML"
        )

async def Branches(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        if not Context.args:
            await Update.message.reply_text(
                build_warning_card(
                    "Repository Branches",
                    ["Usage: <code>/branches Owner/Repo</code>"]
                ),
                parse_mode="HTML"
            )
            return

        RepoInput = Context.args[0]

        Repo = validate_github_repo(RepoInput)
        if not Repo:
            await Update.message.reply_text(
                build_error_card(
                    "Invalid Repository",
                    ["Use Owner/Repo Or A GitHub URL Like <code>https://github.com/owner/repo</code>."]
                ),
                parse_mode="HTML"
            )
            return

        TelegramId = Update.effective_user.id

        Token = DataBase.Get_Token(TelegramId)
        if not Token:
            await Update.message.reply_text(
                build_warning_card(
                    "Not Connected",
                    ["Please Use <code>/connect</code> Before Requesting Branch Info."]
                ),
                parse_mode="HTML"
            )
            return

        Url = f"https://api.github.com/repos/{Repo}/branches"
        Headers = {"Authorization": f"token {Token}"}
        Response = requests.get(Url, headers=Headers, timeout=10)

        if Response.status_code != 200:
            await Update.message.reply_text(
                build_error_card(
                    "Fetch Failed",
                    [f"Unable To Fetch Branches For <code>{Repo}</code>.", f"GitHub Response: <code>{Response.text}</code>"]
                ),
                parse_mode="HTML"
            )
            return

        Branches = Response.json()

        if not Branches:
            await Update.message.reply_text(
                build_message_card(
                    "No Branches Found",
                    [f"No Branches Were Found For <code>{Repo}</code>."]
                ),
                parse_mode="HTML"
            )
            return

        lines = [
            f"Branches For <code>{Repo}</code>:",
            f"Total: {len(Branches)}",
            ""
        ]

        for branch in Branches[:20]:
            name = branch.get('name', 'Unknown')
            sha = branch.get('commit', {}).get('sha', '')[:7]
            protected = branch.get('protected', False)
            protected_icon = "🔒" if protected else "🌿"
            lines.append(f"{protected_icon} <code>{name}</code> — {sha}")

        if len(Branches) > 20:
            lines.append("")
            lines.append(f"⋯⋯ And {len(Branches) - 20} More Branches ⋯⋯")

        await Update.message.reply_text(
            build_message_card("Repository Branches", lines),
            parse_mode="HTML"
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Network Error Fetching Branches For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text(
            build_error_card(
                "Network Error",
                ["Unable to reach GitHub right now.", "Please try again later."]
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Unexpected Error Fetching Branches For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text(
            build_error_card(
                "Unexpected Error",
                ["An unexpected error occurred while fetching branches.", "Please try again later."]
            ),
            parse_mode="HTML"
        )

async def Contributors(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    try:
        if not Context.args:
            await Update.message.reply_text(
                build_warning_card(
                    "Top Contributors",
                    ["Usage: <code>/contributors Owner/Repo</code>"]
                ),
                parse_mode="HTML"
            )
            return

        RepoInput = Context.args[0]

        Repo = validate_github_repo(RepoInput)
        if not Repo:
            await Update.message.reply_text(
                build_error_card(
                    "Invalid Repository",
                    ["Use Owner/Repo or a GitHub URL like <code>https://github.com/owner/repo</code>."]
                ),
                parse_mode="HTML"
            )
            return

        TelegramId = Update.effective_user.id

        Token = DataBase.Get_Token(TelegramId)
        if not Token:
            await Update.message.reply_text(
                build_warning_card(
                    "Not Connected",
                    ["Please use <code>/connect</code> before requesting contributors."]
                ),
                parse_mode="HTML"
            )
            return

        Url = f"https://api.github.com/repos/{Repo}/contributors?per_page=10"
        Headers = {"Authorization": f"token {Token}"}
        Response = requests.get(Url, headers=Headers, timeout=10)

        if Response.status_code != 200:
            await Update.message.reply_text(
                build_error_card(
                    "Fetch Failed",
                    [f"Unable to fetch contributors for <code>{Repo}</code>.", f"GitHub response: <code>{Response.text}</code>"]
                ),
                parse_mode="HTML"
            )
            return

        Contributors = Response.json()

        if not Contributors:
            await Update.message.reply_text(
                build_message_card(
                    "No Contributors",
                    [f"No contributors were found for <code>{Repo}</code>."]
                ),
                parse_mode="HTML"
            )
            return

        lines = [
            f"Top contributors for <code>{Repo}</code>:",
            ""
        ]
        for i, contributor in enumerate(Contributors[:10], 1):
            login = contributor.get('login', 'Unknown')
            contributions = contributor.get('contributions', 0)
            lines.append(f"{i}. <a href='https://github.com/{login}'>@{login}</a> — {contributions:,} contributions")

        await Update.message.reply_text(
            build_message_card("Top Contributors", lines),
            parse_mode="HTML"
        )
    except requests.exceptions.RequestException as e:
        logger.error(f"Network Error Fetching Contributors For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text(
            build_error_card(
                "Network Error",
                ["Unable to reach GitHub right now.", "Please try again later."]
            ),
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Unexpected Error Fetching Contributors For User {Update.effective_user.id}: {e}")
        await Update.message.reply_text(
            build_error_card(
                "Unexpected Error",
                ["An Unexpected Error Occurred While Fetching Contributors.", "Please Try Again Later."]
            ),
            parse_mode="HTML"
        )

# ---------------- Flask Routes ----------------
@App.route("/")
def Home():
    base_url = webhook_url or request.url_root.rstrip("/")
    return render_template(
        "Home.html",
        app_name="GitTracker Bot",
        webhook_url=base_url,
        telegram_webhook_endpoint=f"{base_url}/telegram/webhook",
        github_webhook_endpoint=f"{base_url}/webhook",
        callback_endpoint=f"{base_url}/callback",
        health_endpoint=f"{base_url}/health",
        status_text="Live And Operational"
    )

@App.route("/health")
def Health():
    """Health Check Endpoint For Monitoring."""
    try:
        # Check database connectivity
        db_status = DataBase.check_database_connection()
        if not db_status:
            return jsonify({"status": "unhealthy", "database": "disconnected"}), 503

        if BotStartupError:
            return jsonify({
                "status": "unhealthy",
                "database": "connected",
                "bot": "startup_failed",
                "error": BotStartupError,
                "timestamp": time.time()
            }), 503

        bot_status = "connected" if telegram_bot_is_ready() else "starting"

        if bot_status != "connected":
            return jsonify({
                "status": "unhealthy",
                "database": "connected",
                "bot": bot_status,
                "timestamp": time.time()
            }), 503

        return jsonify({
            "status": "healthy",
            "database": "connected",
            "bot": bot_status,
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
        return render_template("Connected.html", github_username=github_username), 200
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


@App.route("/telegram/webhook", methods=["GET", "POST"])
def TelegramWebhook():
    """Handle Telegram Bot Webhook Updates."""
    try:
        if request.method == "GET":
            status_code = 200 if telegram_bot_is_ready() else 503
            return jsonify({
                "status": "ok" if status_code == 200 else "unavailable",
                "bot_ready": telegram_bot_is_ready(),
                "error": BotStartupError
            }), status_code

        if Config.config.telegram.webhook_secret:
            secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
            if not hmac.compare_digest(secret_token, Config.config.telegram.webhook_secret):
                logger.warning("Telegram Webhook Rejected Due To Invalid Secret Token")
                return jsonify({"error": "Invalid Secret Token"}), 401

        if not telegram_bot_is_ready():
            logger.error("Telegram Webhook Received While Bot Is Not Ready")
            return jsonify({"error": "Telegram Bot Is Not Ready", "detail": BotStartupError}), 503

        logger.info(f"Received Telegram Webhook Request")
        json_data = request.get_json()
        if not json_data:
            logger.warning("Telegram Webhook: Empty or invalid JSON")
            return jsonify({"error": "Invalid JSON"}), 400

        update = Update.de_json(json_data, BotApp.bot)
        logger.info(f"Telegram Webhook: Processing Update {update.update_id}")

        future = asyncio.run_coroutine_threadsafe(
            BotApp.process_update(update),
            BotLoop
        )
        try:
            future.result(timeout=10)
        except Exception as coro_error:
            logger.error(f"CoRoutine Error: {coro_error}")

        return jsonify({"status": "ok"}), 200
    except Exception as e:
        logger.error(f"Telegram Webhook Error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


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
        message = build_message_card(
            "BRANCH/TAG CREATED",
            [
                f"📦 <b>Repository:</b> <code>{repo_name.split('/')[1]}</code>",
                f"🔧 <b>Type:</b> {ref_type.capitalize()}",
                f"📝 <b>Name:</b> <code>{ref}</code>",
            ],
            emoji='🌱',
            footer="👨‍💻 <b>Developed by:</b> <code>i8o8i Developer</code>",
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
        message = build_message_card(
            "BRANCH/TAG DELETED",
            [
                f"📦 <b>Repository:</b> <code>{repo_name.split('/')[1]}</code>",
                f"❌ <b>Type:</b> {ref_type.capitalize()}",
                f"📝 <b>Name:</b> <code>{ref}</code>",
            ],
            emoji='🗑️',
            footer="👨‍💻 <b>Developed by:</b> <code>i8o8i Developer</code>",
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

    action_emoji = {
        "published": "📦",
        "unpublished": "🚫",
        "created": "🆕",
        "edited": "✏️",
        "deleted": "🗑️",
        "prereleased": "🔬",
        "released": "🚀"
    }.get(action, "📦")

    lines = [
        f"📦 <b>Repository:</b> <code>{repo_name}</code>",
        f"🏷️ <b>Tag:</b> <code>{release.get('tag_name')}</code>",
        "",
        f"📝 <b>Title:</b> {release.get('name')}",
        "",
        f"👨‍💻 <b>Author:</b> {release.get('author', {}).get('login', 'Unknown')}",
    ]

    body = release.get('body')
    if body:
        body_preview = body[:200] + ('...' if len(body) > 200 else '')
        lines.extend([
            "",
            "📄 <b>Release Notes:</b>",
            f"<code>{body_preview}</code>",
        ])

    if release.get('prerelease'):
        lines.append("🔬 <b>Status:</b> Pre-release")

    lines.extend([
        "",
        f"🔗 <a href='{release.get('html_url')}'>🔍 View Release</a>",
    ])

    return build_message_card(
        f"RELEASE {action.upper()}",
        lines,
        emoji=action_emoji,
        footer="👨‍💻 <b>Developed by:</b> <code>i8o8i Developer</code>",
    )


async def send_message_to_chat(chat_id: int, message: str, connection: dict = None):
    """Send Message To Specific Telegram Chat With Retry Logic For Network Errors."""
    max_retries = 3
    retry_delay = 5
    
    for attempt in range(max_retries):
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
            return  # Success, Exit Retry Loop
            
        except Exception as e:
            error_str = str(e)
            if ("NetworkError" in error_str or "ReadError" in error_str or 
                "TimeoutError" in error_str or "ConnectionError" in error_str):
                if attempt < max_retries - 1:
                    logger.warning(f"Network Error Sending To Chat {chat_id}, Attempt {attempt + 1}/{max_retries}: {e}")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2  # Exponential Backoff
                    continue
                else:
                    logger.error(f"Failed To Send Message To Chat {chat_id} After {max_retries} Attempts: {e}")
            else:
                logger.error(f"Failed To Send Message To Chat {chat_id}: {e}")
                break  # Non-Network Error, Don't Retry


def format_push_message(data: dict, commits: list, connection: dict) -> str:
    """Format Push Event Message With Attractive UI."""
    repo_name = data.get("repository", {}).get("name", "Unknown")
    branch = data.get("ref", "").split("/")[-1]
    pusher = data.get("pusher", {}).get("name", "Unknown")
    compare_url = data.get("compare", "")

    lines = [
        f"📦 <b>Repository:</b> <code>{repo_name}</code>",
        f"🌿 <b>Branch:</b> <code>{branch}</code>",
        f"👨‍💻 <b>Pushed by:</b> {pusher}",
        f"📊 <b>Commits:</b> {len(commits)}",
    ]

    if compare_url:
        lines.append(f"🔗 <a href='{compare_url}'>📊 Compare Changes</a>")

    lines.extend([
        "",
        "📝 <b>COMMIT DETAILS:</b>",
        "",
    ])

    for i, commit in enumerate(commits[:5], 1):
        tag = GetCommitTag(commit.get("message", ""))
        short_sha = commit.get("id", "")[:7]
        commit_url = commit.get("url", "")
        author = commit.get("author", {}).get("name", "Unknown")
        commit_msg = commit.get("message", "").split('\n')[0]

        detail_line = f"   👤 <i>{author}</i>"
        if commit_url:
            detail_line += f" | <a href='{commit_url}'>🔗 View</a>"

        lines.extend([
            f"#{i} {tag} <code>{short_sha}</code>",
            f"   💬 {commit_msg}",
            detail_line,
            "",
        ])

    if len(commits) > 5:
        lines.append(f"⋯⋯ And {len(commits) - 5} More Commits ⋯⋯")

    return build_message_card(
        "GIT PUSH DETECTED",
        lines,
        emoji='🚀',
        footer="👨‍💻 <b>Developed by:</b> <code>i8o8i Developer</code>",
    )


def format_pr_message(data: dict, connection: dict) -> str:
    """Format Pull Request Event Message With Attractive UI."""
    pr = data.get("pull_request", {})
    repo_name = data.get("repository", {}).get("name", "Unknown")
    action = data.get("action", "updated")

    action_emoji = {
        "opened": "🆕",
        "closed": "❌",
        "merged": "✅",
        "reopened": "🔄",
        "ready_for_review": "👀"
    }.get(action, "🔀")

    lines = [
        f"📦 <b>Repository:</b> <code>{repo_name}</code>",
        f"🔢 <b>PR #{pr.get('number')}</b>",
        "",
        f"📝 <b>Title:</b> {pr.get('title')}",
        "",
        f"👨‍💻 <b>Author:</b> {pr.get('user', {}).get('login', 'Unknown')}",
    ]

    if pr.get('merged'):
        lines.append("✅ <b>Status:</b> Merged")
    elif pr.get('state') == 'closed':
        lines.append("❌ <b>Status:</b> Closed")
    else:
        lines.append("🟡 <b>Status:</b> Open")

    if pr.get('additions') is not None and pr.get('deletions') is not None:
        additions = pr.get('additions', 0)
        deletions = pr.get('deletions', 0)
        lines.append(f"📈 <b>Changes:</b> +{additions} -{deletions} Lines")

    lines.extend([
        "",
        f"🔗 <a href='{pr.get('html_url')}'>🔍 View Pull Request</a>",
    ])

    return build_message_card(
        f"PULL REQUEST {action.upper()}",
        lines,
        emoji=action_emoji,
        footer="👨‍💻 <b>Developed by:</b> <code>i8o8i Developer</code>",
    )


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

    lines = [
        f"📦 <b>Repository:</b> <code>{repo_name}</code>",
        f"🔢 <b>Issue #{issue.get('number')}</b>",
        "",
        f"📝 <b>Title:</b> {issue.get('title')}",
        "",
        f"👨‍💻 <b>Author:</b> {issue.get('user', {}).get('login', 'Unknown')}",
    ]

    if issue.get('state'):
        state_emoji = "🟢" if issue['state'] == 'open' else "🔴"
        lines.append(f"{state_emoji} <b>Status:</b> {issue['state'].title()}")

    if issue.get('labels'):
        labels = [f"#{label['name']}" for label in issue['labels'][:3]]  # Limit to 3 labels
        if labels:
            lines.append(f"🏷️ <b>Labels:</b> {' '.join(labels)}")

    if issue.get('assignees'):
        assignees = [assignee['login'] for assignee in issue['assignees'][:3]]
        if assignees:
            lines.append(f"👥 <b>Assignees:</b> {', '.join(assignees)}")

    lines.extend([
        "",
        f"🔗 <a href='{issue.get('html_url')}'>🔍 View Issue</a>",
    ])

    return build_message_card(
        f"ISSUE {action.upper()}",
        lines,
        emoji=action_emoji,
        footer="👨‍💻 <b>Developed by:</b> <code>i8o8i Developer</code>",
    )

# ---------------- Message Formatting Helpers ----------------
def _wrap_lines(lines: list[str], max_width: int = 42) -> list[str]:
    wrapped_lines: list[str] = []
    for line in lines:
        if line.strip() == "":
            wrapped_lines.append("")
            continue
        wrapped_lines.extend(
            textwrap.wrap(
                line,
                width=max_width,
                break_long_words=False,
                break_on_hyphens=False,
            )
        )
    return wrapped_lines


def build_message_card(
    title: str,
    lines: list[str],
    emoji: str = 'ℹ️',
    footer: Optional[str] = None,
    max_width: int = 42,
) -> str:
    """Build A Polished Message Card For User-Facing Bot Replies."""
    footer_text = footer if footer is not None else "👨‍💻 <b>GitTracker Bot</b> • Use /help For Commands"
    separator = "━━━━━━━━━━━━━━━━━━━━"
    message = f"{emoji} <b>{title}</b>\n{separator}"
    if lines:
        body = "\n".join(lines)
        message += f"\n\n{body}"
    if footer_text:
        message += f"\n\n{separator}\n{footer_text}"
    return message


def build_success_card(title: str, lines: list[str]) -> str:
    return build_message_card(title, lines, emoji='✅')


def build_error_card(title: str, lines: list[str]) -> str:
    return build_message_card(title, lines, emoji='❌')


def build_warning_card(title: str, lines: list[str]) -> str:
    return build_message_card(title, lines, emoji='⚠️')

# ---------------- Graceful Shutdown Handler ----------------
async def stop_telegram_runtime() -> None:
    """Stop The Telegram Application Cleanly."""
    if not BotApp:
        return

    await BotApp.stop()
    await BotApp.shutdown()


def signal_handler(signum, frame):
    """Handle Shutdown Signals Gracefully."""
    global BotReady

    logger.info(f"Received Signal {signum}, Initiating Graceful Shutdown...")
    if BotApp and BotLoop and not BotLoop.is_closed():
        try:
            future = asyncio.run_coroutine_threadsafe(stop_telegram_runtime(), BotLoop)
            future.result(timeout=15)
        except Exception as e:
            logger.error(f"Error Stopping Bot: {e}")

        if BotLoop.is_running():
            BotLoop.call_soon_threadsafe(BotLoop.stop)

    BotReady = False
    sys.exit(0)

# ---------------- Global Error Handler ----------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global Error Handler For The Bot."""
    logger.error(f"Exception While Handling An Update: {context.error}")

    # Try To Send Error Message To User If Possible
    try:
        if update and hasattr(update, 'effective_chat'):
            error_message = build_error_card(
                "Temporary Error",
                [
                    "A Temporary Error Occurred. Please Try Again In A Moment.",
                    "If The Problem Persists, Contact Support."
                ]
            )
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=error_message,
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Failed To Send Error Message To User: {e}")

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


def build_telegram_application() -> Application:
    """Build The Telegram Application Instance."""
    application = (
        Application.builder()
        .token(telegram_token)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(10.0)
        .build()
    )

    commands = [
        ("start", Start),
        ("help", Help),
        ("about", About),
        ("status", Status),
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
        application.add_handler(CommandHandler(command, handler))
        logger.debug(f"Registered Command Handler: {command}")

    application.add_error_handler(error_handler)
    logger.info("Global Error Handler Registered")
    return application


async def initialize_telegram_runtime(application: Application) -> None:
    """Initialize And Start The Telegram Application In Webhook Mode."""
    await application.initialize()
    await application.start()

    telegram_webhook_url = build_public_url("/telegram/webhook")
    logger.info(f"Setting Telegram Webhook To: {telegram_webhook_url}")

    webhook_kwargs = {
        "url": telegram_webhook_url,
        "drop_pending_updates": True,
    }
    if Config.config.telegram.webhook_secret:
        webhook_kwargs["secret_token"] = Config.config.telegram.webhook_secret

    await application.bot.set_webhook(**webhook_kwargs)
    logger.info("Telegram Webhook Configured Successfully")


def start_telegram_runtime() -> None:
    """Start The Telegram Application And Background Event Loop."""
    global ApplicationInstance, BotApp, BotLoop, BotThread, BotReady, BotStartupError

    startup_complete = threading.Event()
    ApplicationInstance = build_telegram_application()
    BotApp = ApplicationInstance
    BotReady = False
    BotStartupError = None

    def run_loop() -> None:
        global BotLoop, BotReady, BotStartupError

        loop = asyncio.new_event_loop()
        BotLoop = loop
        asyncio.set_event_loop(loop)

        try:
            loop.run_until_complete(initialize_telegram_runtime(ApplicationInstance))
            BotReady = True
        except Exception as e:
            BotStartupError = str(e)
            BotReady = False
            logger.critical(f"Failed To Start Telegram Runtime: {e}", exc_info=True)
        finally:
            startup_complete.set()

        if not BotReady:
            loop.close()
            BotLoop = None
            return

        loop.run_forever()
        loop.close()

    logger.info("Starting Telegram Bot In Webhook Mode...")
    BotThread = threading.Thread(target=run_loop, daemon=True, name="telegram-bot-loop")
    BotThread.start()

    if not startup_complete.wait(timeout=30):
        BotStartupError = "Timed Out Waiting For Telegram Runtime Startup"
        raise TimeoutError(BotStartupError)

    if BotStartupError:
        raise RuntimeError(BotStartupError)

    logger.info("Bot Event Loop Started In Background Thread")

if __name__ == "__main__":
    try:
        logger.info("Starting GitTracker Bot...")

        # Register Signal Handlers For Graceful Shutdown
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            start_telegram_runtime()
        except Exception as e:
            BotStartupError = str(e)
            logger.error(f"Telegram Runtime Failed To Start: {e}")

        # Start Flask Server
        logger.info(f"Starting Unified Server On {Config.config.server.host}:{Config.config.server.port}...")
        App.run(
            host=Config.config.server.host,
            port=Config.config.server.port,
            debug=Config.config.server.debug,
            threaded=True,
            use_reloader=False
        )

    except KeyboardInterrupt:
        logger.info("Bot Stopped By User")
    except Exception as e:
        logger.critical(f"Failed To Start Bot: {e}")
        exit(1)