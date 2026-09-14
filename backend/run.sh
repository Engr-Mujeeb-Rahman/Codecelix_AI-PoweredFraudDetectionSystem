#!/usr/bin/env bash
cd "$(dirname "$0")"
if [ ! -d venv ]; then
  python -m venv venv
fi
source venv/Scripts/activate 2>/dev/null || source venv/bin/activate
pip install -q -r requirements.txt
uvicorn app.main:app --reload --port 8000
