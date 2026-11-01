# PlateConnect 🍲
Smart Surplus Food Matching & Distribution Management System for College Campuses.

PlateConnect helps campus food providers list surplus food and lets receivers discover listings and submit requests. This is a beginner-friendly Flask + SQLite academic demo.

## Features
- Register and log in securely (passwords are hashed).
- Create and view surplus-food listings.
- Search listings by food name or category.
- Request food from available listings.
- View your listings and requests on a dashboard.

## Requirements
- Python 3.10+
- pip

## Run locally
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000. The SQLite database is created automatically.

## Demo notes
This is an educational starter project, not a production food-safety or logistics system. Confirm food safety and pickup details with the provider. Add CSRF protection, email verification, deployment secrets, and stronger authorization checks before production use.
