# PowerShell script to set up the MiningCore project structure on Windows

# Specify the base directory for the project (change if needed)
$BASE_DIR = "C:\Users\wl\Desktop\bot\bot2"

# Create directory structure
Write-Host "Creating directory structure in $BASE_DIR..."
New-Item -ItemType Directory -Force -Path "$BASE_DIR\src\stratum_proxy" | Out-Null
New-Item -ItemType Directory -Force -Path "$BASE_DIR\src\telegram_bot" | Out-Null
New-Item -ItemType Directory -Force -Path "$BASE_DIR\config" | Out-Null
New-Item -ItemType Directory -Force -Path "$BASE_DIR\logs" | Out-Null
New-Item -ItemType Directory -Force -Path "$BASE_DIR\data" | Out-Null
New-Item -ItemType Directory -Force -Path "$BASE_DIR\scripts" | Out-Null

# Move existing files (if they exist)
Write-Host "Moving existing files..."
$filesToMove = @(
    @{ Source = ".\config.json"; Dest = "$BASE_DIR\config\config.json" },
    @{ Source = ".\user_settings.json"; Dest = "$BASE_DIR\config\user_settings.json" },
    @{ Source = ".\current_mode.txt"; Dest = "$BASE_DIR\data\current_mode.txt" },
    @{ Source = ".\last_mode_change.json"; Dest = "$BASE_DIR\data\last_mode_change.json" },
    @{ Source = ".\mcpool.log"; Dest = "$BASE_DIR\logs\mcpool.log" },
    @{ Source = ".\hashrate_log.csv"; Dest = "$BASE_DIR\logs\hashrate_log.csv" }
)

foreach ($file in $filesToMove) {
    if (Test-Path $file.Source) {
        Move-Item -Path $file.Source -Destination $file.Dest -Force
        Write-Host "Moved file: $($file.Source) -> $($file.Dest)"
    } else {
        Write-Host "File not found: $($file.Source), skipping..."
    }
}

# Create .gitignore
Write-Host "Creating .gitignore..."
$gitignoreContent = @"
# Ignore logs
logs/*
!logs/.gitkeep

# Ignore temporary files
*.log
*.csv
*.pyc
__pycache__/

# Ignore sensitive data
data/*
!data/current_mode.txt
!data/last_mode_change.json

# Ignore Python dependencies
venv/
.env
"@
Set-Content -Path "$BASE_DIR\.gitignore" -Value $gitignoreContent -Encoding UTF8

# Create README.md (if it doesn't exist)
if (-not (Test-Path "$BASE_DIR\README.md")) {
    Write-Host "Creating README.md..."
    $readmeContent = @"
# MiningCore Proxy and Bot

## Overview
This project includes a Stratum proxy and a Telegram bot for managing a MiningCore pool. The proxy handles miner connections and redirects them to different pools based on the mode. The bot monitors hashrate, workers, and blocks, and allows mode switching via Telegram.

## Directory Structure
- src/                    # Source code
  - stratum_proxy/       # Stratum proxy modules
  - telegram_bot/        # Telegram bot modules
  - main.py             # Entry point (optional)
- config/                 # Configuration files
- logs/                   # Logs (mcpool.log, hashrate_log.csv, proxy.log)
- data/                   # Runtime data (current_mode.txt, last_mode_change.json)
- scripts/                # Utility scripts
- README.md               # This file

## Setup
1. Install dependencies (Windows):
   ```powershell
   pip install aiogram==3.3.0 aiohttp==3.8.4 watchdog==2.1.9 pandas==1.5.3 pytz
   ```
2. Copy configuration files to `config/`.
3. Run the Stratum proxy:
   ```powershell
   python src/stratum_proxy/proxy.py
   ```
4. Run the Telegram bot:
   ```powershell
   python src/telegram_bot/bot.py
   ```

## Deployment to Linux
1. Copy the project to the server (e.g., /home/simple1/miningcore).
2. Install dependencies:
   ```bash
   sudo apt update
   sudo apt install -y python3 python3-pip libzmq3-dev postgresql postgresql-contrib
   pip3 install aiogram==3.3.0 aiohttp==3.8.4 watchdog==2.1.9 pandas==1.5.3 pytz
   ```
3. Start services as described above.

## Configuration
- `config/config.json`: Defines modes, users, nodes, and paths.
- `config/user_settings.json`: Stores user timezone settings.
- `data/current_mode.txt`: Current proxy mode.
- `data/last_mode_change.json`: Tracks mode change timestamps.
"@
    Set-Content -Path "$BASE_DIR\README.md" -Value $readmeContent -Encoding UTF8
}

# Create .gitkeep for empty directories
Write-Host "Creating .gitkeep for empty directories..."
$emptyDirs = @("$BASE_DIR\logs", "$BASE_DIR\scripts")
foreach ($dir in $emptyDirs) {
    New-Item -ItemType File -Path "$dir\.gitkeep" -Force | Out-Null
}

# Initialize Git repository (if not already initialized)
if (-not (Test-Path "$BASE_DIR\.git")) {
    Write-Host "Initializing Git repository..."
    Set-Location $BASE_DIR
    git init
    git add .
    git commit -m "Initial commit: Project structure setup"
}

Write-Host "Project structure created successfully!"
Write-Host "Base directory: $BASE_DIR"
Write-Host "Next steps:"
Write-Host "1. Copy source files (proxy.py, bot.py, etc.) to appropriate folders (src/stratum_proxy/, src/telegram_bot/)."
Write-Host "2. Add your configuration files to config/."
Write-Host "3. Install dependencies: pip install aiogram==3.3.0 aiohttp==3.8.4 watchdog==2.1.9 pandas==1.5.3 pytz"
Write-Host "4. Test the project: python src/stratum_proxy/proxy.py and python src/telegram_bot/bot.py"
Write-Host "5. Push to Git: git remote add origin <your-repo-url>; git push -u origin main"