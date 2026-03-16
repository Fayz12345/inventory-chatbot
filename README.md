# Inventory AI Chatbot

A standalone internal AI chatbot that allows management staff to ask natural language questions about inventory data. Built on a Python Flask backend, powered by the Anthropic Claude API for text-to-SQL generation, and backed by a pre-computed flat SQL table refreshed hourly.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Infrastructure](#infrastructure)
- [SQL Server Setup](#sql-server-setup)
- [Linux EC2 Setup](#linux-ec2-setup)
- [How It Works](#how-it-works)
- [Key Files](#key-files)
- [Configuration](#configuration)
- [Running the App](#running-the-app)
- [Known Issues & Fixes](#known-issues--fixes)
- [Future Improvements](#future-improvements)

---

## Overview

The existing inventory reporting system relies on a stored procedure (`GetMasterDetailInventoryList_TemplateRawData_02Version`) that performs dynamic pivots across 15+ joined tables. This is too slow for real-time AI-driven queries.

To solve this, a flat denormalized reporting table (`ReportingInventoryFlat`) was created on the SQL Server and refreshed hourly via a SQL Server Agent Job. The chatbot queries this flat table instead, enabling fast natural language lookups for internal management.

---

## Architecture

```
User (Browser)
     |
     v
Flask App (Linux EC2 - Ubuntu 24.04)
     |
     |---> Anthropic Claude API
     |       - Receives natural language question
     |       - Returns generated SQL query
     |
     |---> SQL Server (Windows EC2)
             - Executes SQL against ReportingInventoryFlat
             - Returns results
             - Claude formats results into plain English answer
```

**Flow:**
1. User logs in and types a natural language question
2. Flask sends the question to Claude with a schema prompt
3. Claude returns a SQL SELECT query
4. Flask executes the query against `ReportingInventoryFlat`
5. Results are sent back to Claude to format as a plain English answer
6. Answer is displayed in the chat interface

---

## Infrastructure

| Component | Details |
|---|---|
| SQL Server (Windows EC2) | IP: 3.96.24.178, hosts the flat reporting table |
| Linux EC2 | Ubuntu 24.04, t2.micro, hosts the Flask chatbot app |
| Linux EC2 Public IP | 3.99.133.244 |
| Linux EC2 Private IP | 172.31.9.41 |
| Flask port | 5000 |
| SQL Server port | 1433 |
| Python version | 3.12.3 |
| Virtual environment | ~/chatbot-env |
| Project folder | ~/inventory-chatbot |

**Networking:**
- Port 1433 opened in Windows EC2 Security Group for Linux EC2's **public** IP (3.99.133.244)
- Windows Firewall inbound rule added for port 1433
- Port 5000 opened in Linux EC2 Security Group for chatbot access
- SSH access via key pair: `BrainAddon.pem`

---

## SQL Server Setup

### Flat Reporting Table: `ReportingInventoryFlat`

Created on the SQL Server database to serve as a fast, pre-joined snapshot of in-stock inventory.

**Columns:**

| Column | Type | Source |
|---|---|---|
| ESN | nvarchar | ReceiveDetail.ESN |
| ProjectName | nvarchar | Project.Name |
| ProjectTag | nvarchar | ReceiveDetail.ProjectTag |
| ReceiveDate | datetime | ReceiveDetail.CreateDate |
| Product_Place | nvarchar | Option.OptionText (DropDown) |
| Manufacturer | nvarchar | Option.OptionText (DropDown) |
| Model | nvarchar | Option.OptionText (DropDown) |
| Colour | nvarchar | Option.OptionText (DropDown) |
| Grade | nvarchar | Option.OptionText (DropDown) |
| Received_Grade | nvarchar | Option.OptionText (DropDown) |
| DeviceCost | decimal(10,2) | ReceiveDetailItem.Value (Numeric) |
| Function_Test_Created | datetime | ReceiveDetailProcessLog.CreateDate |
| Grading_Created | datetime | ReceiveDetailProcessLog.CreateDate |
| LastRefreshed | datetime | GETDATE() at refresh time |

**Indexes:** ESN, Model, Manufacturer, Product_Place, ReceiveDate

### Stored Procedure: `RefreshReportingInventoryFlat`

Truncates and rebuilds the flat table. Key design decisions:

- `WHERE rd.Version = '000'` — in-stock devices only (MVP scope)
- `SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED` — performance optimization
- `ReceiveDetailItem.Version = 0` — current/active QC answers only (not device version)
- Question values join through `Option.OptionText` for DropDown types, `ReceiveDetailItem.Value` for Numeric types
- Runs in approximately 4-5 minutes, loads ~41,277 rows
- Triggered hourly by SQL Server Agent Job

**Version codes in ReceiveDetail:**

| Version | Meaning |
|---|---|
| 000 | In stock (MVP scope) |
| 001 | Shipped (1M+ records, excluded) |
| 002+ | Other states |

**Source tables:** ReceiveDetail, Project, ReceiveDetailItem, Option, Question, ReceiveDetailProcessLog, Process

**Verified Question names:** `'Product Place'`, `'Grade'`, `'Received Grade'`, `'DeviceCost'`, `'Manufacturer'`, `'Model'`, `'Colour'`

**Verified Process names:** `'Function Test'`, `'Grading'`

### Important: DropDown vs Numeric Question Types

This distinction caused a major bug during development. In the source schema:

- **DropDown / RadialButton questions:** `ReceiveDetailItem.Value = '1'` just means the option was selected. The actual text value (e.g., 'A', 'B', 'Apple', 'iPhone 13') is stored in `Option.OptionText`.
- **Numeric questions:** `ReceiveDetailItem.Value` stores the actual value (e.g., '150.00' for DeviceCost).

The SP joins: `ReceiveDetailItem → [Option] (via OptionID) → Question (via QuestionID)`

---

## Linux EC2 Setup

### Installation Steps

```bash
# Update packages
sudo apt-get update && sudo apt-get upgrade -y

# Python virtual environment
python3 -m venv ~/chatbot-env
source ~/chatbot-env/bin/activate

# Install Python packages
pip install flask pyodbc anthropic gunicorn

# Install ODBC Driver 18 for SQL Server (Ubuntu 24.04)
curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /tmp/microsoft.gpg
sudo install -o root -g root -m 644 /tmp/microsoft.gpg /etc/apt/trusted.gpg.d/
echo "deb [arch=amd64] https://packages.microsoft.com/ubuntu/22.04/prod jammy main" | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
```

> **Note:** Ubuntu 24.04 does not have a dedicated Microsoft repo entry. The Ubuntu 22.04 (jammy) repo URL works on 24.04. Use `gpg --dearmor` instead of the deprecated `apt-key add`.

### Verify ODBC installation

```bash
odbcinst -q -d
# Should return: [ODBC Driver 18 for SQL Server]
```

---

## How It Works

### app.py — Core Flask Application

- `GET /` — redirects to login or chat
- `GET/POST /login` — session-based login with username/password from config
- `POST /ask` — receives question, calls Claude, executes SQL, returns answer
- `GET /logout` — clears session

**Safety:** The app blocks any non-SELECT SQL queries before execution.

**Two-step AI approach:**
1. Claude generates SQL from the natural language question + schema context
2. Claude formats the raw SQL results into a plain English answer

### config.py — Configuration (not committed to git)

```python
DB_SERVER = "3.96.24.178"
DB_NAME = "your_database_name"
DB_USER = "your_db_user"
DB_PASSWORD = "your_db_password"
ANTHROPIC_API_KEY = "sk-ant-..."
SECRET_KEY = "your_flask_secret_key"
CHAT_USERNAME = "admin"
CHAT_PASSWORD = "your_chat_password"
```

---

## Key Files

```
inventory-chatbot/
├── app.py                  # Flask application
├── config.py               # Credentials and settings (excluded from git)
├── config.example.py       # Template with placeholder values
└── templates/
    ├── login.html          # Login page
    └── chat.html           # Chat interface
```

---

## Running the App

### Development (on EC2)

```bash
source ~/chatbot-env/bin/activate
cd ~/inventory-chatbot
python app.py
```

App runs on `http://0.0.0.0:5000`

### Production (gunicorn)

```bash
source ~/chatbot-env/bin/activate
cd ~/inventory-chatbot
gunicorn --bind 0.0.0.0:5000 app:app
```

> **Note:** Use `gunicorn` on Linux, not `waitress` (Windows-only).

To keep it running after terminal closes:
```bash
nohup gunicorn --bind 0.0.0.0:5000 app:app &
```

---

## Known Issues & Fixes

### EC2 Instance Connect paste indentation bug
The browser-based terminal adds 2 leading spaces to all pasted lines except the first, causing `IndentationError` in Python files.

**Fix:**
```bash
sed -i 's/^  //' app.py
sed -i 's/^  //' config.py
```

### ODBC Driver not found on Ubuntu 24.04
`E: Unable to locate package msodbcsql18` — Ubuntu 24.04 has no dedicated Microsoft repo.

**Fix:** Use the Ubuntu 22.04 (jammy) repo URL — it works on 24.04.

### Port 1433 connection timeout
Using the Linux EC2 private IP in the Windows EC2 Security Group inbound rule. Traffic from the Linux EC2 arrives via its **public IP**, not private IP.

**Fix:** Get the public IP with `curl ifconfig.me` and use that in the Security Group rule.

### Flask only listening on 127.0.0.1
Default `app.run()` binds to localhost only — not reachable from browser.

**Fix:** Change to `app.run(host='0.0.0.0', port=5000, debug=False)`

### Chatbot returning 0 for all queries
Grade, Product_Place, and Received_Grade columns were populated with `'1'` instead of the actual text values because the SP used `rdi.Value` for DropDown question types.

**Fix:** Changed those three columns to use `o.OptionText` in `RefreshReportingInventoryFlat`. Re-ran the refresh SP.

### ProjectName trailing space
`'Bridge Product'` stored as `'Bridge Product '` (trailing space) in the database. Claude-generated SQL using exact match `= 'Bridge Product'` returns 0 rows.

**Workaround:** The AI prompt instructs Claude to use `LIKE` or `RTRIM` for ProjectName comparisons where appropriate.

### SP column name errors (`Invalid column name 'Id'`)
Initial SP used generic `Id` column names. The actual schema uses full names: `ReceiveDetailID`, `ProjectID`, `QuestionID`, `OptionID`, `ProcessID`, etc.

Also: `rd.Created` → `rd.CreateDate`, `rdpl.Created` → `rdpl.CreateDate`, `rd.ProjectTag` is on `ReceiveDetail` not `Project`.

---

## Future Improvements

- Set up gunicorn as a `systemd` service so it restarts automatically on reboot
- Add HTTPS via nginx reverse proxy + Let's Encrypt
- Expand MVP scope to include shipped devices (Version = '001') with user toggle
- Add more columns to `ReportingInventoryFlat` as reporting needs grow
- Improve AI prompt to handle trailing spaces and case sensitivity automatically
- Add query history / logging per user session
