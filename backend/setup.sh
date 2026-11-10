#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required"'
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-dev.txt
if [ ! -f .env ]; then cp .env.example .env; fi
printf '%s\n' 'Configure backend/.env, then run: uvicorn main:app --reload --port 8000'
