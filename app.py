import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import Flask, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-this-key")
DATABASE = os.path.join(os.path.dirname(__file__), "plateconnect.db")


def connect_db():
    """Open a SQLite connection and return rows by column name."""
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    """Create the tables when the app is first started."""
    with connect_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'receiver',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            food_name TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            location TEXT NOT NULL,
            pickup_until TEXT NOT NULL,
            description TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Available',
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS food_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            message TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY(listing_id) REFERENCES listings(id),
            FOREIGN KEY(receiver_id) REFERENCES users(id)
        );
        """)


@app.before_request
def load_user():
    g.user = None
    if session.get("user_id"):
        with connect_db() as db:
            g.user = db.execute(
                "SELECT id, name, email, role FROM users WHERE id = ?",
                (session["user_id"],)
            ).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not g.user:
            flash("Please log in to continue.", "info")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/")
def index():
    search = request.args.get("q", "").strip()
    with connect_db() as db:
        if search:
            listings = db.execute("""
                SELECT listings.*, users.name AS provider_name
                FROM listings JOIN users ON users.id = listings.user_id
                WHERE listings.status = 'Available'
                  AND (listings.food_name LIKE ? OR listings.category LIKE ? OR listings.location LIKE ?)
                ORDER BY listings.created_at DESC
            """, (f"%{search}%", f"%{search}%", f"%{search}%")).fetchall()
        else:
            listings = db.execute("""
                SELECT listings.*, users.name AS provider_name
                FROM listings JOIN users ON users.id = listings.user_id
                WHERE listings.status = 'Available'
                ORDER BY listings.created_at DESC
            """).fetchall()
    return render_template("index.html", listings=listings, search=search)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "receiver")
        if role not in ("provider", "receiver", "volunteer"):
            role = "receiver"
        if not name or not email or len(password) < 8:
            flash("Enter your name, email, and a password with at least 8 characters.", "error")
            return render_template("register.html")
        try:
            with connect_db() as db:
                db.execute(
                    "INSERT INTO users (name, email, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
                    (name, email, generate_password_hash(password), role, datetime.now().isoformat(timespec="minutes"))
                )
            flash("Account created. Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("That email is already registered.", "error")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        with connect_db() as db:
            user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            flash("Welcome back!", "success")
            return redirect(url_for("dashboard"))
        flash("Incorrect email or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    with connect_db() as db:
        my_listings = db.execute(
            "SELECT * FROM listings WHERE user_id = ? ORDER BY id DESC", (g.user["id"],)
        ).fetchall()
        my_requests = db.execute("""
            SELECT food_requests.*, listings.food_name, listings.location
            FROM food_requests JOIN listings ON listings.id = food_requests.listing_id
            WHERE food_requests.receiver_id = ? ORDER BY food_requests.id DESC
        """, (g.user["id"],)).fetchall()
        incoming = db.execute("""
            SELECT food_requests.*, listings.food_name, users.name AS receiver_name
            FROM food_requests JOIN listings ON listings.id = food_requests.listing_id
            JOIN users ON users.id = food_requests.receiver_id
            WHERE listings.user_id = ? ORDER BY food_requests.id DESC
        """, (g.user["id"],)).fetchall()
    return render_template("dashboard.html", my_listings=my_listings, my_requests=my_requests, incoming=incoming)


@app.route("/listings/new", methods=["GET", "POST"])
@login_required
def new_listing():
    if request.method == "POST":
        food_name = request.form.get("food_name", "").strip()
        category = request.form.get("category", "").strip()
        location = request.form.get("location", "").strip()
        pickup_until = request.form.get("pickup_until", "").strip()
        description = request.form.get("description", "").strip()
        try:
            quantity = int(request.form.get("quantity", "0"))
        except ValueError:
            quantity = 0
        if not all([food_name, category, location, pickup_until]) or quantity <= 0:
            flash("Fill in all required fields and enter a quantity greater than zero.", "error")
            return render_template("new_listing.html")
        with connect_db() as db:
            db.execute("""
                INSERT INTO listings (user_id, food_name, category, quantity, location, pickup_until, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (g.user["id"], food_name, category, quantity, location, pickup_until, description,
                  datetime.now().isoformat(timespec="minutes")))
        flash("Food listing published.", "success")
        return redirect(url_for("dashboard"))
    return render_template("new_listing.html")


@app.route("/listings/<int:listing_id>")
def listing_detail(listing_id):
    with connect_db() as db:
        listing = db.execute("""
            SELECT listings.*, users.name AS provider_name
            FROM listings JOIN users ON users.id = listings.user_id WHERE listings.id = ?
        """, (listing_id,)).fetchone()
    if not listing:
        flash("Listing not found.", "error")
        return redirect(url_for("index"))
    return render_template("listing_detail.html", listing=listing)


@app.route("/listings/<int:listing_id>/request", methods=["POST"])
@login_required
def request_food(listing_id):
    try:
        quantity = int(request.form.get("quantity", "0"))
    except ValueError:
        quantity = 0
    message = request.form.get("message", "").strip()
    with connect_db() as db:
        listing = db.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
        if not listing or listing["status"] != "Available":
            flash("This listing is no longer available.", "error")
        elif listing["user_id"] == g.user["id"]:
            flash("You cannot request your own listing.", "error")
        elif quantity <= 0 or quantity > listing["quantity"]:
            flash("Enter a quantity between 1 and the listed amount.", "error")
        else:
            db.execute("""
                INSERT INTO food_requests (listing_id, receiver_id, quantity, message, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (listing_id, g.user["id"], quantity, message, datetime.now().isoformat(timespec="minutes")))
            flash("Request submitted. The provider can review it on their dashboard.", "success")
    return redirect(url_for("listing_detail", listing_id=listing_id))


@app.route("/requests/<int:request_id>/<action>", methods=["POST"])
@login_required
def update_request(request_id, action):
    if action not in ("approve", "decline"):
        flash("Invalid request action.", "error")
        return redirect(url_for("dashboard"))
    new_status = "Approved" if action == "approve" else "Declined"
    with connect_db() as db:
        item = db.execute("""
            SELECT food_requests.id, listings.user_id, listings.id AS listing_id,
                   listings.quantity AS available_quantity, food_requests.quantity AS requested_quantity,
                   food_requests.status
            FROM food_requests JOIN listings ON listings.id = food_requests.listing_id
            WHERE food_requests.id = ?
        """, (request_id,)).fetchone()
        if not item or item["user_id"] != g.user["id"]:
            flash("You do not have permission to update this request.", "error")
        elif item["status"] != "Pending":
            flash("This request has already been reviewed.", "info")
        elif action == "approve" and item["requested_quantity"] > item["available_quantity"]:
            flash("Not enough quantity remains to approve this request.", "error")
        else:
            db.execute("UPDATE food_requests SET status = ? WHERE id = ?", (new_status, request_id))
            if action == "approve":
                remaining = item["available_quantity"] - item["requested_quantity"]
                db.execute("UPDATE listings SET quantity = ?, status = ? WHERE id = ?",
                           (remaining, "Available" if remaining > 0 else "Unavailable", item["listing_id"]))
            flash(f"Request {new_status.lower()}.", "success")
    return redirect(url_for("dashboard"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        role = request.form.get("role", g.user["role"])
        if role not in ("provider", "receiver", "volunteer"):
            role = g.user["role"]
        if not name:
            flash("Name cannot be empty.", "error")
        else:
            with connect_db() as db:
                db.execute("UPDATE users SET name = ?, role = ? WHERE id = ?", (name, role, g.user["id"]))
            flash("Profile updated.", "success")
            return redirect(url_for("profile"))
    return render_template("profile.html", user=g.user)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
