CREATE DATABASE IF NOT EXISTS Tracer_Bot;

USE Tracer_Bot;

CREATE TABLE IF NOT EXISTS Users (
    Id INT AUTO_INCREMENT PRIMARY KEY,
    Telegram_Id BIGINT NOT NULL UNIQUE,
    Github_Username VARCHAR(255),
    Github_Token TEXT,
    Created_At TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS User_Repo_Connections (
    Id INT AUTO_INCREMENT PRIMARY KEY,
    Telegram_Id BIGINT NOT NULL,
    Repo_Name VARCHAR(255) NOT NULL,
    Chat_Id BIGINT NOT NULL,
    Chat_Type ENUM('private', 'group', 'supergroup') NOT NULL,
    Topic_Id BIGINT NULL,
    Created_At TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY unique_connection (Telegram_Id, Repo_Name, Chat_Id, Topic_Id)
);