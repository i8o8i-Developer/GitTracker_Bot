import threading
import requests
import asyncio
from flask import Flask, Request
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import DataBase
import Config

# ---------------- Initialize Database ----------------
DataBase.Init_Db()

# ---------------- Config ----------------
TelegramToken = Config.Telegram_Token
GithubClientId = Config.Github_Client_Id
GithubClientSecret = Config.Github_Client_Secret

# ---------------- Globals ----------------
App = Flask(__name__)
BotApp = None
BotLoop = None   # Store Telegram Bot Loop

# ---------------- Helper ----------------
def GetCommitTag(Message: str) -> str:
    """Return Emoji Based On Commit Message Keywords."""
    Msg = Message.lower()
    if "fix" in Msg or "bug" in Msg:
        return "🐛"
    if "feat" in Msg or "add" in Msg or "new" in Msg:
        return "✨"
    if "doc" in Msg or "readme" in Msg:
        return "📝"
    if "style" in Msg or "ui" in Msg:
        return "🎨"
    if "hotfix" in Msg or "urgent" in Msg:
        return "🔥"
    return "🔨"

# ---------------- Telegram Handlers ----------------
async def Start(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    await Update.message.reply_text(
        "👋 Welcome To GitTracer Bot!\n\n"
        "Commands:\n"
        "🔗 /connect → Link GitHub Account\n"
        "📌 /setrepo Owner/Repo Or Full GitHub Url → Choose A Repository\n"
        "📌 /getrepo → Show Your Current Repository\n"
        "💬 /comment Owner/Repo Issue_Number Message → Comment On Issues\n"
        "📋 /listwebhooks → List Webhooks On Repo\n"
        "🗑 /delwebhook Id → Delete A Webhook By Id\n"
    )

async def Connect(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    TelegramId = Update.effective_user.id
    AuthUrl = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GithubClientId}&scope=repo"
        f"&state={TelegramId}"
    )
    await Update.message.reply_text(f"🔗 Connect Your GitHub: {AuthUrl}")

async def SetRepo(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    if not Context.args:
        await Update.message.reply_text("⚠ Usage: /setrepo Owner/Repo Or Full GitHub Url")
        return

    RepoInput = Context.args[0]

    if RepoInput.startswith("http"):
        try:
            Repo = RepoInput.rstrip("/").split("github.com/")[1]
        except Exception:
            await Update.message.reply_text("❌ Invalid GitHub Url. Use /setrepo Owner/Repo")
            return
    else:
        Repo = RepoInput

    TelegramId = Update.effective_user.id
    DataBase.Set_Default_Repo(TelegramId, Repo)

    Token = DataBase.Get_Token(TelegramId)
    if not Token:
        await Update.message.reply_text("❌ You Are Not Connected. Use /connect First.")
        return

    HookUrl = f"{Config.Ngrok_Url}/webhook"
    ApiUrl = f"https://api.github.com/repos/{Repo}/hooks"
    Headers = {"Authorization": f"token {Token}"}
    Data = {
        "name": "web",
        "active": True,
        "events": ["push", "pull_request", "issues", "delete", "create"],
        "config": {"url": HookUrl, "content_type": "json", "insecure_ssl": "0"},
    }

    Response = requests.post(ApiUrl, json=Data, headers=Headers)

    if Response.status_code in [200, 201]:
        await Update.message.reply_text(f"✅ Default Repository Set To: {Repo}\n🔗 Webhook Installed")
    else:
        await Update.message.reply_text(f"⚠ Repo Saved, But Failed To Add Webhook.\nGitHub Says: {Response.text}")

async def GetRepo(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    TelegramId = Update.effective_user.id
    Repo = DataBase.Get_Default_Repo(TelegramId)
    if Repo:
        await Update.message.reply_text(f"📌 Your Default Repository Is: {Repo}")
    else:
        await Update.message.reply_text("⚠ No Default Repository Set. Use /setrepo Owner/Repo")

async def Comment(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    if len(Context.args) < 3:
        await Update.message.reply_text("⚠ Usage: /comment Owner/Repo Issue_Number Message")
        return

    Repo = Context.args[0]
    IssueNumber = Context.args[1]
    CommentText = " ".join(Context.args[2:])
    TelegramId = Update.effective_user.id

    Token = DataBase.Get_Token(TelegramId)
    if not Token:
        await Update.message.reply_text("❌ You Are Not Connected. Use /connect First.")
        return

    Url = f"https://api.github.com/repos/{Repo}/issues/{IssueNumber}/comments"
    Headers = {"Authorization": f"token {Token}"}
    Response = requests.post(Url, json={"body": CommentText}, headers=Headers)

    if Response.status_code == 201:
        await Update.message.reply_text(f"✅ Comment Posted On {Repo} Issue #{IssueNumber}")
    else:
        await Update.message.reply_text(f"❌ Failed To Post Comment: {Response.text}")

async def ListWebhooks(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    TelegramId = Update.effective_user.id
    Repo = DataBase.Get_Default_Repo(TelegramId)
    Token = DataBase.Get_Token(TelegramId)

    if not Repo or not Token:
        await Update.message.reply_text("⚠ Please /setrepo And /connect First.")
        return

    Url = f"https://api.github.com/repos/{Repo}/hooks"
    Headers = {"Authorization": f"token {Token}"}
    Response = requests.get(Url, headers=Headers)
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

async def DelWebhook(Update: Update, Context: ContextTypes.DEFAULT_TYPE):
    if not Context.args:
        await Update.message.reply_text("⚠ Usage: /delwebhook Id")
        return
    HookId = Context.args[0]
    TelegramId = Update.effective_user.id
    Repo = DataBase.Get_Default_Repo(TelegramId)
    Token = DataBase.Get_Token(TelegramId)

    if not Repo or not Token:
        await Update.message.reply_text("⚠ Please /setrepo And /connect First.")
        return

    Url = f"https://api.github.com/repos/{Repo}/hooks/{HookId}"
    Headers = {"Authorization": f"token {Token}"}
    Response = requests.delete(Url, headers=Headers)

    if Response.status_code == 204:
        await Update.message.reply_text(f"🗑 Webhook {HookId} Deleted")
    else:
        await Update.message.reply_text(f"❌ Failed To Delete: {Response.text}")

# ---------------- Flask Routes ----------------
@App.route("/")
def Home():
    return "✅ GitTracer Bot Running"

@App.route("/callback")
def Callback():
    Code = Request.args.get("code")
    TelegramId = Request.args.get("state")

    TokenUrl = "https://github.com/login/oauth/access_token"
    Data = {"client_id": GithubClientId, "client_secret": GithubClientSecret, "code": Code}
    Headers = {"Accept": "application/json"}
    Response = requests.post(TokenUrl, data=Data, headers=Headers)
    TokenJson = Response.json()

    AccessToken = TokenJson.get("access_token")
    if not AccessToken:
        return f"❌ Failed To Get Token: {TokenJson}", 400

    UserInfo = requests.get("https://api.github.com/user", headers={"Authorization": f"token {AccessToken}"}).json()

    if "login" not in UserInfo:
        return f"❌ Failed To Fetch User Info: {UserInfo}", 400

    GithubUsername = UserInfo["login"]
    DataBase.Save_User(TelegramId, GithubUsername, AccessToken)

    return f"✅ Connected As {GithubUsername}. You Can Now Set Your Repo With /setrepo"

@App.route("/webhook", methods=["POST"])
def Webhook():
    global BotLoop
    try:
        Payload = Request.json
        Event = Request.headers.get("X-GitHub-Event")
        RepoFullName = Payload["repository"]["full_name"]

        print(f"📥 Webhook Received: {Event} From {RepoFullName}")

        Users = DataBase.Get_All_Users()
        Messages = []

        # Push Events
        if Event == "push":
            Branch = Payload["ref"].split("/")[-1]
            CommitCount = len(Payload["commits"])
            CompareUrl = Payload.get("compare")
            Pusher = Payload["pusher"]["name"]

            Header = f"🔨 {CommitCount} New Commit(s) By {Pusher} ({CompareUrl}) To {RepoFullName}:{Branch}:\n"

            CommitLines = []
            for C in Payload["commits"]:
                Sha = C["id"][:7]
                CommitMsg = C["message"].split("\n")[0].title()
                CommitUrl = C["url"]
                Author = C["author"]["name"]

                Tag = GetCommitTag(CommitMsg)
                Line = f"{Tag} {Sha} ({CommitUrl}): {CommitMsg} — {Author.title()}"
                CommitLines.append(Line)

                Details = "\n".join(f"- {Line.strip().title()}" for Line in C["message"].split("\n")[1:] if Line.strip())
                if Details:
                    CommitLines.append(Details)

            Messages.append(Header + "\n".join(CommitLines))

        # Pull Requests
        elif Event == "pull_request":
            Action = Payload["action"]
            Pr = Payload["pull_request"]
            Messages.append(
                f"🔀 Pull Request {Action.upper()} In {RepoFullName}\n"
                f"👤 By: {Pr['user']['login'].title()}\n📝 {Pr['title'].title()}\n🔗 {Pr['html_url']}"
            )

        # Issues
        elif Event == "issues":
            Action = Payload["action"]
            Issue = Payload["issue"]
            Messages.append(
                f"🐞 Issue {Action.upper()} In {RepoFullName}\n"
                f"👤 By: {Issue['user']['login'].title()}\n📝 {Issue['title'].title()}\n🔗 {Issue['html_url']}"
            )

        # Branch Create/Delete
        elif Event == "create":
            RefType = Payload["ref_type"]
            Ref = Payload["ref"]
            Messages.append(f"🌱 {RefType.capitalize()} Created: {Ref.title()} In {RepoFullName}")

        elif Event == "delete":
            RefType = Payload["ref_type"]
            Ref = Payload["ref"]
            Messages.append(f"🗑 {RefType.capitalize()} Deleted: {Ref.title()} In {RepoFullName}")

        else:
            Messages.append(f"⚡ Event '{Event}' Received From {RepoFullName}")

        for User in Users:
            if User["Default_Repo"] and User["Default_Repo"].lower() == RepoFullName.lower():
                for Msg in Messages:
                    try:
                        asyncio.run_coroutine_threadsafe(
                            BotApp.bot.send_message(chat_id=User["Telegram_Id"], text=Msg),
                            BotLoop,
                        )
                        print(f"✅ Queued Message For {User['Telegram_Id']}")
                    except Exception as E:
                        print(f"❌ Failed To Send Message: {E}")

        return "OK", 200

    except Exception as E:
        print(f"❌ Webhook Error: {E}")
        return "Error", 500

# ---------------- Main ----------------
def RunFlask():
    App.run(host="0.0.0.0", port=5000)

if __name__ == "__main__":
    ApplicationInstance = Application.builder().token(TelegramToken).build()
    BotApp = ApplicationInstance

    ApplicationInstance.add_handler(CommandHandler("start", Start))
    ApplicationInstance.add_handler(CommandHandler("connect", Connect))
    ApplicationInstance.add_handler(CommandHandler("setrepo", SetRepo))
    ApplicationInstance.add_handler(CommandHandler("getrepo", GetRepo))
    ApplicationInstance.add_handler(CommandHandler("comment", Comment))
    ApplicationInstance.add_handler(CommandHandler("listwebhooks", ListWebhooks))
    ApplicationInstance.add_handler(CommandHandler("delwebhook", DelWebhook))

    threading.Thread(target=RunFlask, daemon=True).start()

    try:
        BotLoop = asyncio.get_event_loop()
        ApplicationInstance.run_polling()
    except KeyboardInterrupt:
        print("\n🛑 Bot Stopped By User")