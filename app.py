import csv
import os
import secrets
import sqlite3
from datetime import datetime, timedelta
from io import StringIO
from functools import wraps

from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from flask_wtf.csrf import CSRFProtect

from config import ADMIN_EMAIL, ADMIN_PASSWORD, DB_PATH, SECRET_KEY

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
csrf = CSRFProtect(app)

app.static_folder = os.path.join(os.path.dirname(__file__), "static")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS delivery_partners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            phone TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            address TEXT NOT NULL,
            profile_photo TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partner_id INTEGER NOT NULL,
            attendance_date TEXT NOT NULL,
            check_in_time TEXT,
            check_out_time TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(partner_id, attendance_date),
            FOREIGN KEY (partner_id) REFERENCES delivery_partners(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS delivery_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partner_id INTEGER NOT NULL,
            record_date TEXT NOT NULL,
            pickups INTEGER NOT NULL DEFAULT 0,
            completed_deliveries INTEGER NOT NULL DEFAULT 0,
            returns INTEGER NOT NULL DEFAULT 0,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(partner_id, record_date),
            FOREIGN KEY (partner_id) REFERENCES delivery_partners(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            token TEXT NOT NULL UNIQUE,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    delivery_columns = [row[1] for row in conn.execute("PRAGMA table_info(delivery_records)").fetchall()]
    if "returns" not in delivery_columns:
        conn.execute("ALTER TABLE delivery_records ADD COLUMN returns INTEGER NOT NULL DEFAULT 0")

    conn.commit()
    conn.close()



def ensure_admin_account():
    email = ADMIN_EMAIL.strip().lower()
    password = ADMIN_PASSWORD.strip()
    if not email or not password:
        raise ValueError("Admin email and password must be set in the environment.")

    conn = get_db_connection()
    user = conn.execute("SELECT id, password_hash FROM admins WHERE email = ?", (email,)).fetchone()
    password_hash = generate_password_hash(password)

    if user is None:
        conn.execute(
            "INSERT INTO admins (email, password_hash) VALUES (?, ?)",
            (email, password_hash),
        )
    else:
        if not check_password_hash(user["password_hash"], password):
            conn.execute(
                "UPDATE admins SET password_hash = ? WHERE email = ?",
                (password_hash, email),
            )
    conn.commit()
    conn.close()



def ensure_storage_dirs():
    os.makedirs(os.path.join(app.static_folder, "images", "uploads", "partners"), exist_ok=True)



def get_current_date():
    return datetime.now().strftime("%Y-%m-%d")



def get_current_datetime():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")



def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default



def format_currency(value):
    return f"₹{float(value):,.2f}"



def partner_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "partner" or not session.get("partner_id"):
            flash("Please log in as a delivery partner to continue.", "error")
            return redirect(url_for("partner_login"))

        conn = get_db_connection()
        partner = conn.execute(
            "SELECT * FROM delivery_partners WHERE id = ? AND is_active = 1",
            (session["partner_id"],),
        ).fetchone()
        conn.close()

        if partner is None:
            session.clear()
            flash("This delivery partner account is not active or was not found.", "error")
            return redirect(url_for("partner_login"))

        return view(*args, **kwargs)

    return wrapped



def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Administrator access is required.", "error")
            return redirect(url_for("admin_login"))

        return view(*args, **kwargs)

    return wrapped



def get_partner_by_id(partner_id):
    conn = get_db_connection()
    partner = conn.execute("SELECT * FROM delivery_partners WHERE id = ?", (partner_id,)).fetchone()
    conn.close()
    return partner



def get_partner_stats(partner_id):
    today = get_current_date()
    conn = get_db_connection()
    attendance = conn.execute(
        "SELECT * FROM attendance WHERE partner_id = ? AND attendance_date = ?",
        (partner_id, today),
    ).fetchone()
    record = conn.execute(
        "SELECT COALESCE(SUM(pickups), 0) AS total_pickups, COALESCE(SUM(completed_deliveries), 0) AS total_deliveries, COALESCE(SUM(returns), 0) AS total_returns FROM delivery_records WHERE partner_id = ? AND record_date = ?",
        (partner_id, today),
    ).fetchone()
    lifetime = conn.execute(
        "SELECT COALESCE(SUM(completed_deliveries), 0) AS total_deliveries, COALESCE(SUM(returns), 0) AS total_returns FROM delivery_records WHERE partner_id = ?",
        (partner_id,),
    ).fetchone()
    conn.close()

    total_pickups = safe_int(record["total_pickups"], 0) if record else 0
    total_deliveries = safe_int(record["total_deliveries"], 0) if record else 0
    total_returns = safe_int(record["total_returns"], 0) if record else 0
    lifetime_deliveries = safe_int(lifetime["total_deliveries"], 0) if lifetime else 0
    lifetime_returns = safe_int(lifetime["total_returns"], 0) if lifetime else 0
    lifetime_earnings = (lifetime_deliveries + lifetime_returns) * 15
    today_earnings = (total_deliveries + total_returns) * 15

    return {
        "attendance": attendance,
        "today_pickups": total_pickups,
        "today_deliveries": total_deliveries,
        "today_returns": total_returns,
        "today_earnings": today_earnings,
        "lifetime_earnings": lifetime_earnings,
    }



def get_admin_stats():
    today = get_current_date()
    conn = get_db_connection()
    registered_partners = conn.execute("SELECT COUNT(*) AS total FROM delivery_partners").fetchone()["total"]
    active_partners = conn.execute("SELECT COUNT(*) AS total FROM delivery_partners WHERE is_active = 1").fetchone()["total"]
    today_present = conn.execute(
        "SELECT COUNT(DISTINCT partner_id) AS total FROM attendance WHERE attendance_date = ? AND check_in_time IS NOT NULL",
        (today,),
    ).fetchone()["total"]
    today_pickups = conn.execute(
        "SELECT COALESCE(SUM(pickups), 0) AS total FROM delivery_records WHERE record_date = ?",
        (today,),
    ).fetchone()["total"]
    today_completed = conn.execute(
        "SELECT COALESCE(SUM(completed_deliveries), 0) AS total FROM delivery_records WHERE record_date = ?",
        (today,),
    ).fetchone()["total"]
    today_returns = conn.execute(
        "SELECT COALESCE(SUM(returns), 0) AS total FROM delivery_records WHERE record_date = ?",
        (today,),
    ).fetchone()["total"]
    today_earnings = (safe_int(today_completed, 0) + safe_int(today_returns, 0)) * 15
    overall_earnings = conn.execute(
        "SELECT COALESCE(SUM(completed_deliveries + returns), 0) AS total FROM delivery_records"
    ).fetchone()["total"]
    conn.close()
    return {
        "registered_partners": registered_partners,
        "active_partners": active_partners,
        "today_present": today_present,
        "today_pickups": today_pickups,
        "today_completed": today_completed,
        "today_returns": today_returns,
        "today_earnings": today_earnings,
        "overall_earnings": safe_int(overall_earnings, 0) * 15,
    }



def get_chart_payload():
    conn = get_db_connection()
    dates = []
    delivery_values = []
    return_values = []
    earnings_values = []
    pickup_values = []
    today = datetime.now().date()

    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        date_text = day.strftime("%Y-%m-%d")
        dates.append(day.strftime("%b %d"))
        record = conn.execute(
            "SELECT COALESCE(SUM(completed_deliveries), 0) AS completed, COALESCE(SUM(returns), 0) AS returns, COALESCE(SUM(pickups), 0) AS pickups FROM delivery_records WHERE record_date = ?",
            (date_text,),
        ).fetchone()
        completed = safe_int(record["completed"], 0) if record else 0
        returns = safe_int(record["returns"], 0) if record else 0
        pickups = safe_int(record["pickups"], 0) if record else 0
        delivery_values.append(completed)
        return_values.append(returns)
        pickup_values.append(pickups)
        earnings_values.append((completed + returns) * 15)

    monthly_earnings = []
    monthly_labels = []
    month_rows = conn.execute(
        "SELECT substr(record_date, 1, 7) AS month, COALESCE(SUM(completed_deliveries + returns), 0) AS total_actions FROM delivery_records GROUP BY substr(record_date, 1, 7) ORDER BY month DESC LIMIT 6"
    ).fetchall()
    for row in reversed(month_rows):
        monthly_labels.append(row["month"])
        monthly_earnings.append(safe_int(row["total_actions"], 0) * 15)

    present_count = conn.execute(
        "SELECT COUNT(DISTINCT partner_id) AS total FROM attendance WHERE attendance_date = ? AND check_in_time IS NOT NULL",
        (get_current_date(),),
    ).fetchone()["total"]
    active_count = conn.execute("SELECT COUNT(*) AS total FROM delivery_partners WHERE is_active = 1").fetchone()["total"]
    absent_count = max(active_count - present_count, 0)
    conn.close()

    return {
        "daily_labels": dates,
        "daily_deliveries": delivery_values,
        "daily_returns": return_values,
        "daily_earnings": earnings_values,
        "monthly_labels": monthly_labels,
        "monthly_earnings": monthly_earnings,
        "attendance_labels": ["Present", "Off Duty"],
        "attendance_values": [present_count, absent_count],
        "comparison_labels": ["Pickup Count", "Completed + Returns"],
        "comparison_values": [sum(pickup_values), sum(delivery_values) + sum(return_values)],
    }



def generate_report_csv(rows, headers):
    csv_buffer = StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(headers)
    for row in rows:
        writer.writerow(row)
    csv_buffer.seek(0)
    return csv_buffer


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/partner-login", methods=["GET", "POST"])
def partner_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("partner_login.html")

        conn = get_db_connection()
        partner = conn.execute(
            "SELECT * FROM delivery_partners WHERE email = ?",
            (email,),
        ).fetchone()
        conn.close()

        if partner is None or not check_password_hash(partner["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("partner_login.html")

        if partner["is_active"] != 1:
            flash("Your partner account is currently inactive.", "error")
            return render_template("partner_login.html")

        session.clear()
        session["role"] = "partner"
        session["partner_id"] = partner["id"]
        session["partner_name"] = partner["full_name"]
        flash("Welcome back! Your dashboard is ready.", "success")
        return redirect(url_for("partner_dashboard"))

    return render_template("partner_login.html")


@app.route("/partner-signup", methods=["GET", "POST"])
def partner_signup():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        address = request.form.get("address", "").strip()

        if not all([full_name, email, phone, password, confirm_password, address]):
            flash("Please complete all required fields.", "error")
            return render_template("partner_signup.html")

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("partner_signup.html")

        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "error")
            return render_template("partner_signup.html")

        if "@" not in email:
            flash("Enter a valid email address.", "error")
            return render_template("partner_signup.html")

        profile_photo = None
        uploaded_file = request.files.get("profile_photo")
        if uploaded_file and uploaded_file.filename:
            filename = secure_filename(uploaded_file.filename)
            allowed_ext = {"png", "jpg", "jpeg", "webp"}
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            if ext not in allowed_ext:
                flash("Profile photo must be a PNG, JPG, JPEG, or WEBP image.", "error")
                return render_template("partner_signup.html")
            ensure_storage_dirs()
            upload_dir = os.path.join(app.static_folder, "images", "uploads", "partners")
            unique_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            file_path = os.path.join(upload_dir, unique_name)
            uploaded_file.save(file_path)
            profile_photo = os.path.relpath(file_path, app.static_folder).replace("\\", "/")

        conn = get_db_connection()
        existing = conn.execute("SELECT id FROM delivery_partners WHERE email = ?", (email,)).fetchone()
        if existing:
            conn.close()
            flash("An account with this email already exists.", "error")
            return render_template("partner_signup.html")

        conn.execute(
            "INSERT INTO delivery_partners (full_name, email, phone, password_hash, address, profile_photo, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (full_name, email, phone, generate_password_hash(password), address, profile_photo, get_current_datetime(), get_current_datetime()),
        )
        conn.commit()
        conn.close()

        flash("Registration successful. Please log in to continue.", "success")
        return redirect(url_for("partner_login"))

    return render_template("partner_signup.html")


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email:
            flash("Please enter your email address.", "error")
            return render_template("forgot_password.html")

        conn = get_db_connection()
        partner = conn.execute("SELECT id FROM delivery_partners WHERE email = ?", (email,)).fetchone()
        if partner is None:
            conn.close()
            flash("No account found for that email address.", "error")
            return render_template("forgot_password.html")

        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "INSERT INTO password_reset_tokens (email, token, expires_at, created_at) VALUES (?, ?, ?, ?)",
            (email, token, expires_at, get_current_datetime()),
        )
        conn.commit()
        conn.close()
        flash(f"Password reset token created. Use the link below to reset your password: {url_for('reset_password', token=token, _external=True)}", "success")
        return redirect(url_for("forgot_password"))

    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    conn = get_db_connection()
    reset_request = conn.execute(
        "SELECT * FROM password_reset_tokens WHERE token = ? AND expires_at > ?",
        (token, get_current_datetime()),
    ).fetchone()
    conn.close()

    if reset_request is None:
        flash("This password reset link is invalid or expired.", "error")
        return redirect(url_for("partner_login"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "error")
            return render_template("reset_password.html", token=token)
        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("reset_password.html", token=token)

        conn = get_db_connection()
        conn.execute(
            "UPDATE delivery_partners SET password_hash = ?, updated_at = ? WHERE email = ?",
            (generate_password_hash(password), get_current_datetime(), reset_request["email"]),
        )
        conn.execute("DELETE FROM password_reset_tokens WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        flash("Your password has been updated successfully.", "success")
        return redirect(url_for("partner_login"))

    return render_template("reset_password.html", token=token)


@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("admin_login.html")

        conn = get_db_connection()
        admin = conn.execute("SELECT * FROM admins WHERE email = ?", (email,)).fetchone()
        conn.close()

        if admin is None or not check_password_hash(admin["password_hash"], password):
            flash("Invalid admin credentials.", "error")
            return render_template("admin_login.html")

        session.clear()
        session["role"] = "admin"
        session["admin_email"] = admin["email"]
        flash("Admin login successful.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("index"))


@app.route("/partner-dashboard")
@partner_required
def partner_dashboard():
    partner = get_partner_by_id(session["partner_id"])
    stats = get_partner_stats(session["partner_id"])
    attendance_history = []
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM attendance WHERE partner_id = ? ORDER BY attendance_date DESC LIMIT 10",
        (session["partner_id"],),
    ).fetchall()
    conn.close()
    for row in rows:
        attendance_history.append(dict(row))

    return render_template(
        "partner_dashboard.html",
        partner=partner,
        stats=stats,
        attendance_history=attendance_history,
    )


@app.route("/attendance", methods=["GET", "POST"])
@partner_required
def attendance_page():
    if request.method == "POST":
        action = request.form.get("action")
        today = get_current_date()
        conn = get_db_connection()
        row = conn.execute(
            "SELECT * FROM attendance WHERE partner_id = ? AND attendance_date = ?",
            (session["partner_id"], today),
        ).fetchone()

        if action == "check_in":
            if row and row["check_in_time"]:
                flash("You have already checked in today.", "error")
                return redirect(url_for("attendance_page"))
            now_value = get_current_datetime()
            if row:
                conn.execute(
                    "UPDATE attendance SET check_in_time = ?, updated_at = ? WHERE id = ?",
                    (now_value, get_current_datetime(), row["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO attendance (partner_id, attendance_date, check_in_time, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                    (session["partner_id"], today, now_value, get_current_datetime(), get_current_datetime()),
                )
            conn.commit()
            conn.close()
            flash("Check-in successful. Welcome to the day.", "success")
            return redirect(url_for("attendance_page"))

        if action == "check_out":
            if row is None or not row["check_in_time"]:
                flash("You must check in before checking out.", "error")
                conn.close()
                return redirect(url_for("attendance_page"))
            if row["check_out_time"]:
                flash("You have already checked out today.", "error")
                conn.close()
                return redirect(url_for("attendance_page"))
            now_value = get_current_datetime()
            conn.execute(
                "UPDATE attendance SET check_out_time = ?, updated_at = ? WHERE id = ?",
                (now_value, get_current_datetime(), row["id"]),
            )
            conn.commit()
            conn.close()
            flash("Check-out successful. Have a great day.", "success")
            return redirect(url_for("attendance_page"))

    conn = get_db_connection()
    attendance_rows = conn.execute(
        "SELECT * FROM attendance WHERE partner_id = ? ORDER BY attendance_date DESC LIMIT 30",
        (session["partner_id"],),
    ).fetchall()
    partner = conn.execute("SELECT * FROM delivery_partners WHERE id = ?", (session["partner_id"],)).fetchone()
    conn.close()
    return render_template("attendance.html", attendance_rows=attendance_rows, partner=partner)


@app.route("/delivery-records", methods=["GET", "POST"])
@partner_required
def delivery_records():
    if request.method == "POST":
        record_date = request.form.get("record_date", get_current_date())
        pickups = safe_int(request.form.get("pickups"), 0)
        completed_deliveries = safe_int(request.form.get("completed_deliveries"), 0)
        returns = safe_int(request.form.get("returns"), 0)
        notes = request.form.get("notes", "").strip()

        if pickups < 0 or completed_deliveries < 0 or returns < 0:
            flash("Pickup, delivery, and return counts cannot be negative.", "error")
            return redirect(url_for("delivery_records"))

        conn = get_db_connection()
        existing = conn.execute(
            "SELECT * FROM delivery_records WHERE partner_id = ? AND record_date = ?",
            (session["partner_id"], record_date),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE delivery_records SET pickups = ?, completed_deliveries = ?, returns = ?, notes = ?, updated_at = ? WHERE id = ?",
                (pickups, completed_deliveries, returns, notes, get_current_datetime(), existing["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO delivery_records (partner_id, record_date, pickups, completed_deliveries, returns, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (session["partner_id"], record_date, pickups, completed_deliveries, returns, notes, get_current_datetime(), get_current_datetime()),
            )
        conn.commit()
        conn.close()
        flash("Delivery record saved successfully. Delivery and return fees are calculated at ₹15 each.", "success")
        return redirect(url_for("delivery_records"))

    conn = get_db_connection()
    records = conn.execute(
        "SELECT * FROM delivery_records WHERE partner_id = ? ORDER BY record_date DESC",
        (session["partner_id"],),
    ).fetchall()
    partner = conn.execute("SELECT * FROM delivery_partners WHERE id = ?", (session["partner_id"],)).fetchone()
    conn.close()

    for record in records:
        record["earnings"] = (safe_int(record["completed_deliveries"], 0) + safe_int(record["returns"], 0)) * 15

    default_date = get_current_date()
    return render_template("delivery_records.html", records=records, partner=partner, default_date=default_date)


@app.route("/profile", methods=["GET", "POST"])
@partner_required
def profile_page():
    partner = get_partner_by_id(session["partner_id"])

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        photo_file = request.files.get("profile_photo")

        if not all([full_name, phone, address]):
            flash("Full name, phone number, and address are required.", "error")
            return render_template("profile.html", partner=partner)

        profile_photo = partner["profile_photo"]
        if photo_file and photo_file.filename:
            filename = secure_filename(photo_file.filename)
            ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
            if ext not in {"png", "jpg", "jpeg", "webp"}:
                flash("Profile photo must be a PNG, JPG, JPEG, or WEBP image.", "error")
                return render_template("profile.html", partner=partner)
            ensure_storage_dirs()
            upload_dir = os.path.join(app.static_folder, "images", "uploads", "partners")
            unique_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{filename}"
            file_path = os.path.join(upload_dir, unique_name)
            photo_file.save(file_path)
            profile_photo = os.path.relpath(file_path, app.static_folder).replace("\\", "/")

        if password or confirm_password:
            if password != confirm_password:
                flash("New password and confirm password do not match.", "error")
                return render_template("profile.html", partner=partner)
            if len(password) < 8:
                flash("New password must be at least 8 characters long.", "error")
                return render_template("profile.html", partner=partner)
            partner_hash = generate_password_hash(password)
        else:
            partner_hash = partner["password_hash"]

        conn = get_db_connection()
        conn.execute(
            "UPDATE delivery_partners SET full_name = ?, phone = ?, address = ?, profile_photo = ?, password_hash = ?, updated_at = ? WHERE id = ?",
            (full_name, phone, address, profile_photo, partner_hash, get_current_datetime(), session["partner_id"]),
        )
        conn.commit()
        conn.close()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("profile_page"))

    return render_template("profile.html", partner=partner)


@app.route("/admin-dashboard")
@admin_required
def admin_dashboard():
    stats = get_admin_stats()
    chart_data = get_chart_payload()
    conn = get_db_connection()
    partners = conn.execute(
        "SELECT * FROM delivery_partners ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return render_template("admin_dashboard.html", stats=stats, chart_data=chart_data, partners=partners)


@app.route("/admin/partners")
@admin_required
def admin_partners():
    query = request.args.get("q", "").strip()
    conn = get_db_connection()
    if query:
        partners = conn.execute(
            "SELECT * FROM delivery_partners WHERE full_name LIKE ? OR email LIKE ? ORDER BY created_at DESC",
            (f"%{query}%", f"%{query}%"),
        ).fetchall()
    else:
        partners = conn.execute("SELECT * FROM delivery_partners ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("admin_dashboard.html", stats=get_admin_stats(), chart_data=get_chart_payload(), partners=partners, query=query)


@app.route("/admin/partner/<int:partner_id>")
@admin_required
def partner_profile_admin(partner_id):
    partner = get_partner_by_id(partner_id)
    if partner is None:
        flash("Partner not found.", "error")
        return redirect(url_for("admin_dashboard"))

    conn = get_db_connection()
    attendance_rows = conn.execute(
        "SELECT * FROM attendance WHERE partner_id = ? ORDER BY attendance_date DESC",
        (partner_id,),
    ).fetchall()
    records = conn.execute(
        "SELECT * FROM delivery_records WHERE partner_id = ? ORDER BY record_date DESC",
        (partner_id,),
    ).fetchall()
    conn.close()

    for record in records:
        record["earnings"] = (safe_int(record["completed_deliveries"], 0) + safe_int(record["returns"], 0)) * 15

    return render_template(
        "profile.html",
        partner=partner,
        attendance_rows=attendance_rows,
        records=records,
        admin_view=True,
    )


@app.route("/admin/partner/<int:partner_id>/toggle-status", methods=["POST"])
@admin_required
def toggle_partner_status(partner_id):
    partner = get_partner_by_id(partner_id)
    if partner is None:
        flash("Partner not found.", "error")
        return redirect(url_for("admin_dashboard"))

    new_status = 0 if partner["is_active"] == 1 else 1
    conn = get_db_connection()
    conn.execute("UPDATE delivery_partners SET is_active = ?, updated_at = ? WHERE id = ?", (new_status, get_current_datetime(), partner_id))
    conn.commit()
    conn.close()
    flash(f"Partner status updated: {'Active' if new_status else 'Inactive'}.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/reports")
@admin_required
def reports_page():
    period = request.args.get("period", "7d")
    partner_id = request.args.get("partner_id")
    conn = get_db_connection()
    partners = conn.execute("SELECT id, full_name, email FROM delivery_partners ORDER BY full_name ASC").fetchall()

    if partner_id:
        records = conn.execute(
            "SELECT * FROM delivery_records WHERE partner_id = ? ORDER BY record_date DESC LIMIT 30",
            (int(partner_id),),
        ).fetchall()
    else:
        records = conn.execute(
            "SELECT * FROM delivery_records ORDER BY record_date DESC LIMIT 30"
        ).fetchall()
    conn.close()

    summary = []
    for record in records:
        summary.append(
            {
                "date": record["record_date"],
                "partner_id": record["partner_id"],
                "pickups": record["pickups"],
                "completed": record["completed_deliveries"],
                "returns": record.get("returns", 0),
                "earnings": (safe_int(record["completed_deliveries"], 0) + safe_int(record.get("returns", 0), 0)) * 15,
            }
        )

    return render_template("reports.html", period=period, partners=partners, records=summary, selected_partner_id=partner_id)


@app.route("/admin/export-report")
@admin_required
def export_report():
    period = request.args.get("period", "7d")
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=6)

    if period == "monthly":
        start_date = end_date - timedelta(days=30)
    elif period == "all":
        start_date = None

    conn = get_db_connection()
    if start_date:
        rows = conn.execute(
            "SELECT r.record_date, p.full_name, r.pickups, r.completed_deliveries, r.returns, ((r.completed_deliveries + r.returns) * 15) AS earnings FROM delivery_records r LEFT JOIN delivery_partners p ON p.id = r.partner_id WHERE r.record_date BETWEEN ? AND ? ORDER BY r.record_date DESC",
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT r.record_date, p.full_name, r.pickups, r.completed_deliveries, r.returns, ((r.completed_deliveries + r.returns) * 15) AS earnings FROM delivery_records r LEFT JOIN delivery_partners p ON p.id = r.partner_id ORDER BY r.record_date DESC"
        ).fetchall()
    conn.close()

    csv_buffer = generate_report_csv(
        [
            [row["record_date"], row["full_name"], row["pickups"], row["completed_deliveries"], row["returns"], row["earnings"]]
            for row in rows
        ],
        ["Date", "Partner", "Pickups", "Completed Deliveries", "Returns", "Earnings (INR)"],
    )
    return send_file(
        csv_buffer,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"rely-{period}-report.csv",
    )


@app.route("/health")
def health_check():
    return jsonify({"status": "ok", "message": "RELY app is running."})


init_db()
ensure_admin_account()
ensure_storage_dirs()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
