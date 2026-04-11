"""
Database Operations For GitTracker Bot.
Provides Connection Pooling And Comprehensive Error Handling.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from dbutils.pooled_db import PooledDB
import logging
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from Config import config
from Logging_Config import logger


class DatabaseManager:
    """Database Manager With Connection Pooling."""

    def __init__(self):
        """Initialize Database Connection Pool."""
        self.pool = PooledDB(
            creator=psycopg2,
            host=config.database.host,
            user=config.database.user,
            password=config.database.password,
            database=config.database.name,
            port=config.database.port,
            cursor_factory=RealDictCursor,
            connect_timeout=10,
            mincached=0,
            maxcached=10,
            maxconnections=20,
            blocking=True
        )
        logger.info(f"Database Connection Pool Initialized For {config.database.host}:{config.database.port}")

    @contextmanager
    def get_connection(self):
        """Get A Database Connection From The Pool."""
        conn = None
        try:
            conn = self.pool.connection()
            yield conn
        except Exception as e:
            logger.error(f"Database Connection Error: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def init_database(self) -> bool:
        """
        Initialize Database And Create Tables If They Don't Exist.

        Returns:
            bool: True If Successful, False Otherwise
        """
        try:
            # First Connect Without Database To Create It
            temp_conn = psycopg2.connect(
                host=config.database.host,
                user=config.database.user,
                password=config.database.password,
                port=config.database.port,
                dbname='postgres',  # Connect to default postgres database
                connect_timeout=10
            )
            temp_conn.autocommit = True

            with temp_conn.cursor() as cursor:
                cursor.execute(f"CREATE DATABASE {config.database.name}")
                logger.info(f"Database '{config.database.name}' Created Or Already Exists")

            temp_conn.close()

            # Now Create Tables
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    # Users Table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS Users (
                            Id SERIAL PRIMARY KEY,
                            Telegram_Id BIGINT NOT NULL UNIQUE,
                            Github_Username VARCHAR(255),
                            Github_Token TEXT,
                            Created_At TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)

                    
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON Users(Telegram_Id)
                    """)

                    # User_Repo_Connections Table
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS User_Repo_Connections (
                            Id SERIAL PRIMARY KEY,
                            Telegram_Id BIGINT NOT NULL,
                            Repo_Name VARCHAR(255) NOT NULL,
                            Chat_Id BIGINT NOT NULL,
                            Chat_Type VARCHAR(20) NOT NULL,
                            Topic_Id BIGINT NULL,
                            Created_At TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(Telegram_Id, Repo_Name, Chat_Id, Topic_Id)
                        )
                    """)

                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_connections_telegram_id ON User_Repo_Connections(Telegram_Id)
                    """)
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_connections_repo_name ON User_Repo_Connections(Repo_Name)
                    """)
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS idx_connections_chat_id ON User_Repo_Connections(Chat_Id)
                    """)

                    logger.info("Database Tables Created Successfully")
                    return True

        except Exception as e:
            logger.error(f"Failed To Initialize Database: {e}")
            return False

    def check_database_connection(self) -> bool:
        """
        Check If Database Connection Is Working.

        Returns:
            bool: True If Connection Is Healthy
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    return result is not None
        except Exception as e:
            logger.error(f"Database Health Check Failed: {e}")
            return False

    def save_user(self, telegram_id: int, github_username: str, github_token: str) -> bool:
        """
        Save Or Update User Information.

        Args:
            telegram_id: Telegram User ID
            github_username: GitHub Username
            github_token: GitHub Access Token

        Returns:
            bool: True If Successful
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO Users (Telegram_Id, Github_Username, Github_Token)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (Telegram_Id) DO UPDATE SET
                            Github_Username=EXCLUDED.Github_Username,
                            Github_Token=EXCLUDED.Github_Token
                    """, (telegram_id, github_username, github_token))

                    logger.info(f"User {telegram_id} ({github_username}) Saved Successfully")
                    return True

        except Exception as e:
            logger.error(f"Failed To Save User {telegram_id}: {e}")
            return False

    def get_token(self, telegram_id: int) -> Optional[str]:
        """
        Get GitHub Token For A User.

        Args:
            telegram_id: Telegram User ID

        Returns:
            GitHub Token Or None If Not Found
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT Github_Token FROM Users WHERE Telegram_Id = %s", (telegram_id,))
                    row = cursor.fetchone()
                    return row['github_token'] if row else None

        except Exception as e:
            logger.error(f"Failed To Get Token For User {telegram_id}: {e}")
            return None

    def add_repo_connection(self, telegram_id: int, repo_name: str, chat_id: int,
                          chat_type: str, topic_id: Optional[int] = None) -> bool:
        """
        Add A Repository Connection For A Specific Chat Context.

        Args:
            telegram_id: Telegram User ID
            repo_name: Repository Name (owner/repo format)
            chat_id: Telegram Chat ID
            chat_type: Type Of Chat (private, group, supergroup)
            topic_id: Topic ID For Supergroups (optional)

        Returns:
            bool: True If Successful
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO User_Repo_Connections (Telegram_Id, Repo_Name, Chat_Id, Chat_Type, Topic_Id)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (Telegram_Id, Repo_Name, Chat_Id, Topic_Id) DO UPDATE SET
                            Repo_Name=EXCLUDED.Repo_Name
                    """, (telegram_id, repo_name, chat_id, chat_type, topic_id))

                    logger.info(f"Repository Connection Added: {repo_name} for user {telegram_id} in chat {chat_id}")
                    return True

        except Exception as e:
            logger.error(f"Failed To Add Repo Connection For User {telegram_id}: {e}")
            return False

    def remove_repo_connection(self, telegram_id: int, repo_name: str, chat_id: int,
                             topic_id: Optional[int] = None) -> bool:
        """
        Remove A Repository Connection.

        Args:
            telegram_id: Telegram User ID
            repo_name: Repository Name
            chat_id: Telegram Chat ID
            topic_id: Topic ID (optional)

        Returns:
            bool: True If Successful
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    if topic_id is not None:
                        cursor.execute("""
                            DELETE FROM User_Repo_Connections
                            WHERE Telegram_Id=%s AND Repo_Name=%s AND Chat_Id=%s AND Topic_Id=%s
                        """, (telegram_id, repo_name, chat_id, topic_id))
                    else:
                        cursor.execute("""
                            DELETE FROM User_Repo_Connections
                            WHERE Telegram_Id=%s AND Repo_Name=%s AND Chat_Id=%s AND Topic_Id IS NULL
                        """, (telegram_id, repo_name, chat_id))

                    logger.info(f"Repository Connection Removed: {repo_name} For User {telegram_id} In Chat {chat_id}")
                    return True

        except Exception as e:
            logger.error(f"Failed To Remove Repo Connection For User {telegram_id}: {e}")
            return False

    def get_user_repo_connections(self, telegram_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get Repository Connections For A User Or All Users.

        Args:
            telegram_id: Telegram User ID (optional, if None Returns All Connections)

        Returns:
            List Of Connection Dictionaries
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    if telegram_id:
                        cursor.execute("""
                            SELECT Telegram_Id, Repo_Name, Chat_Id, Chat_Type, Topic_Id
                            FROM User_Repo_Connections
                            WHERE Telegram_Id=%s
                        """, (telegram_id,))
                    else:
                        cursor.execute("""
                            SELECT Telegram_Id, Repo_Name, Chat_Id, Chat_Type, Topic_Id
                            FROM User_Repo_Connections
                        """)

                    connections = cursor.fetchall()
                    # Convert RealDictRow to regular dict
                    connections = [dict(row) for row in connections]
                    logger.debug(f"Retrieved {len(connections)} Connections")
                    return connections

        except Exception as e:
            logger.error(f"Failed To Get Repo Connections: {e}")
            return []

    def get_user_repo_connections_by_repo(self, repo_name: str) -> List[Dict[str, Any]]:
        """
        Get All Connections For A Specific Repository.

        Args:
            repo_name: Repository Name (Case-Insensitive Search)

        Returns:
            List Of Connection Dictionaries
        """
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("""
                        SELECT Telegram_Id, Repo_Name, Chat_Id, Chat_Type, Topic_Id
                        FROM User_Repo_Connections
                        WHERE LOWER(Repo_Name)=LOWER(%s)
                    """, (repo_name,))

                    connections = cursor.fetchall()
                    connections = [dict(row) for row in connections]
                    logger.debug(f"Retrieved {len(connections)} Connections For Repo {repo_name}")
                    return connections

        except Exception as e:
            logger.error(f"Failed To Get Connections For Repo {repo_name}: {e}")
            return []


# Global Database Manager Instance
db_manager = DatabaseManager()


# Backward Compatibility Functions
def Init_Db():
    """Initialize Database (Backward Compatibility)."""
    return db_manager.init_database()

def Save_User(telegram_id, github_username, github_token):
    """Save User (Backward Compatibility)."""
    return db_manager.save_user(telegram_id, github_username, github_token)

def Get_Token(telegram_id):
    """Get Token (Backward Compatibility)."""
    return db_manager.get_token(telegram_id)

def Add_Repo_Connection(telegram_id, repo, chat_id, chat_type, topic_id=None):
    """Add Repo Connection (Backward Compatibility)."""
    return db_manager.add_repo_connection(telegram_id, repo, chat_id, chat_type, topic_id)

def Remove_Repo_Connection(telegram_id, repo, chat_id, topic_id=None):
    """Remove Repo Connection (Backward Compatibility)."""
    return db_manager.remove_repo_connection(telegram_id, repo, chat_id, topic_id)

def Get_User_Repo_Connections(telegram_id=None):
    """Get User Repo Connections (Backward Compatibility)."""
    return db_manager.get_user_repo_connections(telegram_id)

def get_user_repo_connections(telegram_id=None):
    """Get User Repo Connections (Backward Compatibility - lowercase version)."""
    return db_manager.get_user_repo_connections(telegram_id)

def Get_Connections_For_Repo(repo_name):
    """Get Connections For Repo (Backward Compatibility)."""
    return db_manager.get_user_repo_connections_by_repo(repo_name)

def get_user_repo_connections_by_repo(repo_name):
    """Get User Repo Connections By Repo (Backward Compatibility - lowercase version)."""
    return db_manager.get_user_repo_connections_by_repo(repo_name)

def check_database_connection():
    """Check Database Connection (Backward Compatibility)."""
    return db_manager.check_database_connection()

# Deprecated Functions
def Set_Default_Repo(*args, **kwargs):
    """Deprecated: Use Add_Repo_Connection Instead."""
    logger.warning("Set_Default_Repo Is Deprecated, Use Add_Repo_Connection Instead")
    return False

def Get_Default_Repo(*args, **kwargs):
    """Deprecated: Use Get_User_Repo_Connections Instead."""
    logger.warning("Get_Default_Repo Is Deprecated, Use Get_User_Repo_Connections Instead")
    return None

def Get_AllUsers():
    """Get All Users (Backward Compatibility)."""
    return db_manager.get_user_repo_connections()
