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
   `powershell
   pip install aiogram==3.3.0 aiohttp==3.8.4 watchdog==2.1.9 pandas==1.5.3 pytz
   `
2. Copy configuration files to config/.
3. Run the Stratum proxy:
   `powershell
   python src/stratum_proxy/proxy.py
   `
4. Run the Telegram bot:
   `powershell
   python src/telegram_bot/bot.py
   `

## Deployment to Linux
1. Copy the project to the server (e.g., /home/simple1/miningcore).
2. Install dependencies:
   `ash
   sudo apt update
   sudo apt install -y python3 python3-pip libzmq3-dev postgresql postgresql-contrib
   pip3 install aiogram==3.3.0 aiohttp==3.8.4 watchdog==2.1.9 pandas==1.5.3 pytz
   `
3. Start services as described above.

## Configuration
- config/config.json: Defines modes, users, nodes, and paths.
- config/user_settings.json: Stores user timezone settings.
- data/current_mode.txt: Current proxy mode.
- data/last_mode_change.json: Tracks mode change timestamps.
