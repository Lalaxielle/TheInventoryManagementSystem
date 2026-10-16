#!/usr/bin/env bash
cd "$(dirname "$0")"
echo "Starting TheInventoryManagementSystem..."
python3 app.py 2>/dev/null || python app.py
