from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
from mysql.connector import pooling
from datetime import datetime
from config import DB_CONFIG, SECRET_KEY

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Create a small pool so connections are reused
cnxpool = pooling.MySQLConnectionPool(pool_name="smpool", pool_size=5, **DB_CONFIG)

def db_execute(sql, params=None, fetch="none"):
    """
    fetch: "one" | "all" | "none"
    """
    conn = cnxpool.get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params or ())
        result = None
        if fetch == "one":
            result = cur.fetchone()
        elif fetch == "all":
            result = cur.fetchall()
        if sql.strip().lower().startswith(("insert", "update", "delete", "create", "drop", "alter")):
            conn.commit()
        cur.close()
        return result
    finally:
        conn.close()

def init_db():
    # Create tables if not exists
    db_execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT PRIMARY KEY AUTO_INCREMENT,
            username VARCHAR(50) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db_execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INT PRIMARY KEY AUTO_INCREMENT,
            roll_no VARCHAR(30) UNIQUE NOT NULL,
            name VARCHAR(100) NOT NULL,
            course VARCHAR(100),
            email VARCHAR(120),
            phone VARCHAR(20),
            dob DATE,
            address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Seed default admin if users table is empty
    row = db_execute("SELECT COUNT(*) AS c FROM users", fetch="one")
    if row and row["c"] == 0:
        admin_hash = generate_password_hash("admin123")
        db_execute("INSERT INTO users (username, password_hash) VALUES (%s, %s)", ("admin", admin_hash))
        print("Seeded default admin user → username: admin, password: admin123")

@app.before_first_request
def before_first_request():
    init_db()

# ------------ Auth helpers ------------
def login_required(view_func):
    from functools import wraps
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view_func(*args, **kwargs)
    return wrapper

# ------------ Routes ------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        uname = request.form.get("username", "").strip()
        pwd = request.form.get("password", "")
        user = db_execute("SELECT * FROM users WHERE username=%s", (uname,), fetch="one")
        if user and check_password_hash(user["password_hash"], pwd):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash("Welcome back!", "success")
            return redirect(url_for("home"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html", title="Login")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login"))

@app.route("/")
@login_required
def home():
    q = request.args.get("q", "").strip()
    params = []
    sql = "SELECT * FROM students"
    if q:
        sql += " WHERE name LIKE %s OR roll_no LIKE %s OR course LIKE %s OR email LIKE %s"
        like = f"%{q}%"
        params = [like, like, like, like]
    sql += " ORDER BY created_at DESC"
    rows = db_execute(sql, params, fetch="all")
    return render_template("index.html", title="Students", students=rows, q=q)

@app.route("/add", methods=["GET", "POST"])
@login_required
def add_student():
    if request.method == "POST":
        data = {
            "roll_no": request.form.get("roll_no", "").strip(),
            "name": request.form.get("name", "").strip(),
            "course": request.form.get("course", "").strip(),
            "email": request.form.get("email", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "dob": request.form.get("dob", "").strip() or None,
            "address": request.form.get("address", "").strip(),
        }
        # basic validation
        if not data["roll_no"] or not data["name"]:
            flash("Roll No and Name are required.", "warning")
            return render_template("add_student.html", title="Add Student", form=data)

        db_execute("""
            INSERT INTO students (roll_no, name, course, email, phone, dob, address)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """, (data["roll_no"], data["name"], data["course"], data["email"], data["phone"], data["dob"], data["address"]))
        flash("Student added successfully.", "success")
        return redirect(url_for("home"))
    return render_template("add_student.html", title="Add Student")

@app.route("/edit/<int:sid>", methods=["GET", "POST"])
@login_required
def edit_student(sid):
    student = db_execute("SELECT * FROM students WHERE id=%s", (sid,), fetch="one")
    if not student:
        flash("Student not found.", "danger")
        return redirect(url_for("home"))

    if request.method == "POST":
        data = {
            "roll_no": request.form.get("roll_no", "").strip(),
            "name": request.form.get("name", "").strip(),
            "course": request.form.get("course", "").strip(),
            "email": request.form.get("email", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "dob": request.form.get("dob", "").strip() or None,
            "address": request.form.get("address", "").strip(),
        }
        if not data["roll_no"] or not data["name"]:
            flash("Roll No and Name are required.", "warning")
            return render_template("edit_student.html", title="Edit Student", student={**student, **data})
        db_execute("""
            UPDATE students
               SET roll_no=%s, name=%s, course=%s, email=%s, phone=%s, dob=%s, address=%s
             WHERE id=%s
        """, (data["roll_no"], data["name"], data["course"], data["email"], data["phone"], data["dob"], data["address"], sid))
        flash("Student updated.", "success")
        return redirect(url_for("home"))

    return render_template("edit_student.html", title="Edit Student", student=student)

@app.route("/delete/<int:sid>", methods=["POST"])
@login_required
def delete_student(sid):
    db_execute("DELETE FROM students WHERE id=%s", (sid,))
    flash("Student deleted.", "info")
    return redirect(url_for("home"))

if _name_ == "__main__":
    app.run(debug=True)