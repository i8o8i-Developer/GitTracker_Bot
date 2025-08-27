import pymysql as PyMySQL

DbHost = "127.0.0.1"
DbUser = "root"
DbPassword = ""
DbName = "Tracer_Bot"
DbPort = 1677

def Get_Connection(Database=True):
    """Return A Connection To Database Or Server."""
    return PyMySQL.connect(
        host=DbHost,
        user=DbUser,
        password=DbPassword,
        database=DbName if Database else None,
        port=DbPort,
        cursorclass=PyMySQL.cursors.DictCursor
    )

def Init_Db():
    """Create Database And Users Table If Not Exists."""
    # First Connect Without Database
    Conn = PyMySQL.connect(
        host=DbHost,
        user=DbUser,
        password=DbPassword,
        port=DbPort,
        cursorclass=PyMySQL.cursors.DictCursor
    )
    Cursor = Conn.cursor()
    Cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DbName}")
    Conn.commit()
    Conn.close()

    # Now Connect To Database And Create Table
    Conn = Get_Connection()
    Cursor = Conn.cursor()
    Cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS Users (
            Id INT AUTO_INCREMENT PRIMARY KEY,
            Telegram_Id BIGINT NOT NULL UNIQUE,
            Github_Username VARCHAR(255),
            Github_Token TEXT,
            Default_Repo VARCHAR(255),
            Created_At TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    Conn.commit()
    Conn.close()

def Save_User(TelegramId, GithubUsername, GithubToken):
    Conn = Get_Connection()
    Cursor = Conn.cursor()
    Cursor.execute("""
        INSERT INTO Users (Telegram_Id, Github_Username, Github_Token)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE
            Github_Username=VALUES(Github_Username),
            Github_Token=VALUES(Github_Token)
    """, (TelegramId, GithubUsername, GithubToken))
    Conn.commit()
    Conn.close()

def Set_Default_Repo(TelegramId, Repo):
    Conn = Get_Connection()
    Cursor = Conn.cursor()
    Cursor.execute("UPDATE Users SET Default_Repo=%s WHERE Telegram_Id=%s", (Repo, TelegramId))
    Conn.commit()
    Conn.close()

def Get_Default_Repo(TelegramId):
    Conn = Get_Connection()
    Cursor = Conn.cursor()
    Cursor.execute("SELECT Default_Repo FROM Users WHERE Telegram_Id=%s", (TelegramId,))
    Row = Cursor.fetchone()
    Conn.close()
    return Row["Default_Repo"] if Row else None

def Get_Token(TelegramId):
    Conn = Get_Connection()
    Cursor = Conn.cursor()
    Cursor.execute("SELECT Github_Token FROM Users WHERE Telegram_Id=%s", (TelegramId,))
    Row = Cursor.fetchone()
    Conn.close()
    return Row["Github_Token"] if Row else None

def Get_All_Users():
    Conn = Get_Connection()
    Cursor = Conn.cursor()
    Cursor.execute("SELECT Telegram_Id, Default_Repo FROM Users")
    Users = Cursor.fetchall()
    Conn.close()
    return Users
