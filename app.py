from flask import Flask, render_template, request, redirect, session, send_from_directory, url_for
import mysql.connector
import os
import uuid
from similarity_engine import calculate_similarity
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
from datetime import datetime
from reportlab.pdfgen import canvas
from io import BytesIO
from flask import make_response


app = Flask(__name__)
app.secret_key = "secret"

# ---------------- FILE UPLOAD ----------------
UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ---------------- MAIL CONFIG ----------------
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'projectevaluator36@gmail.com'
app.config['MAIL_PASSWORD'] = 'ukxl plyx avol iccd'
mail = Mail(app)
serializer = URLSafeTimedSerializer(app.secret_key)

# ---------------- DATABASE CONNECTION ----------------
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root123",
        database="project_evaluator"
    )

# ---------------- HOME ----------------
@app.route('/')
def home():
    return render_template("home.html")

# =========================================================
# 🔐 FORGOT PASSWORD (ALL USERS)
# =========================================================
@app.route('/forgot-password/<role>', methods=['GET', 'POST'])
def forgot_password(role):
    if request.method == 'POST':
        email = request.form['email']
        table = {"student": "students", "faculty": "faculty", "admin": "admin"}[role]
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(f"SELECT * FROM {table} WHERE email=%s", (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user:
            token = serializer.dumps({'email': email, 'role': role}, salt='password-reset')
            BASE_URL = "https://hypergrammatically-buboed-denice.ngrok-free.dev"
            reset_link = f"{BASE_URL}/reset-password/{token}"
            msg = Message(
                subject="Reset Your Password",
                sender=app.config['MAIL_USERNAME'],
                recipients=[email]
            )
            msg.body = f"""
Hello {user.get('name','User')},

Click the link to reset your password:
{reset_link}

Link valid for 10 minutes.
"""
            mail.send(msg)
            return "📧 Reset link sent to your email"
        return render_template('forgot_password.html', error="Email not found")
    return render_template('forgot_password.html', role=role)

# =========================================================
# 🔐 RESET PASSWORD
# =========================================================
@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        data = serializer.loads(token, salt='password-reset', max_age=600)
        email = data['email']
        role = data['role']
    except:
        return "❌ Invalid or expired link"
    table = {"student": "students", "faculty": "faculty", "admin": "admin"}[role]
    if request.method == 'POST':
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        if new_password != confirm_password:
            return render_template('reset_password.html', error="Passwords do not match")
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE {table} SET password=%s WHERE email=%s", (new_password, email))
        conn.commit()
        cursor.close()
        conn.close()
        return "✅ Password updated successfully"
    return render_template('reset_password.html')

# =========================================================
# 👩‍🎓 STUDENT MODULE
# =========================================================
from flask import render_template, request, redirect, url_for, session

@app.route('/student/signup', methods=['GET', 'POST'])
def student_signup():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email', '').strip().lower()
        roll_no = request.form.get('roll_no', '').strip()
        password = request.form.get('password').strip()
        dept = request.form.get('department', '').strip().upper()
        year = request.form.get('year')

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Check existing
        cursor.execute("SELECT * FROM students WHERE email=%s OR roll_no=%s", (email, roll_no))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return render_template('student/signup.html', error="Email or Roll No already exists")

        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO students (name, roll_no, email, password, department, year)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (name, roll_no, email, password, dept, year))
            
            conn.commit()
            cursor.close()
            conn.close()

            return redirect('/student/login')

        except Exception as e:
            return render_template('student/signup.html', error=str(e))

    return render_template('student/signup.html')

@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM students WHERE email=%s", (email,))
        student = cursor.fetchone()

        cursor.close()
        conn.close()

        if student and student['password'] == password:
            session.clear()
            session['student_id'] = student['id']
            session['name'] = student['name']
            session['roll_no'] = student['roll_no']
            session['department'] = student['department']
            session['role'] = 'student'
            return redirect('/student/dashboard')

        return render_template('student/login.html', error="Invalid Email or Password")

    return render_template('student/login.html')

@app.route('/student/dashboard', methods=['GET', 'POST'])
def student_dashboard():
    if 'student_id' not in session:
        return redirect('/student/login')

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # ---------- PROJECT SUBMISSION ----------
        if request.method == 'POST':
            title = request.form['title']
            description = request.form['description']
            file = request.files['file']

            filename = str(uuid.uuid4()) + "_" + file.filename
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(filepath)

            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                new_project_text = f.read()

            # Existing projects for plagiarism check
            cursor.execute("SELECT title, file_path FROM projects")
            existing_rows = cursor.fetchall()

            old_project_texts = []
            project_titles = []

            for row in existing_rows:
                path = os.path.join(app.config["UPLOAD_FOLDER"], row['file_path'])
                if os.path.exists(path):
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        old_project_texts.append(f.read())
                        project_titles.append(row['title'])

            similarity, match_index = calculate_similarity(new_project_text, old_project_texts)

            matched_with = project_titles[match_index] if match_index is not None and similarity > 0 else "Original"
            status = "Flagged" if similarity > 60 else "Pending"

            # Deadline check
            cursor.execute(
                "SELECT deadline FROM department_settings WHERE department=%s",
                (session['department'],)
            )
            deadline_row = cursor.fetchone()

            submission_note = "On-Time"
            if deadline_row and deadline_row['deadline']:
                if datetime.now() > deadline_row['deadline']:
                    submission_note = "Late Submission"

            cursor.execute("""
                INSERT INTO projects 
                (student_id, title, description, file_path, similarity_percentage, status, matched_with, submission_note)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                session['student_id'],
                title,
                description,
                filename,
                similarity,
                status,
                matched_with,
                submission_note
            ))

            conn.commit()

        # ---------- FETCH PROJECTS + MARKS + FEEDBACK ----------
        cursor.execute("""
            SELECT 
                p.*, 
                s.name, 
                s.roll_no, 
                s.department,
                e.marks,
                e.feedback
            FROM projects p
            JOIN students s ON p.student_id = s.id
            LEFT JOIN evaluations e ON p.id = e.project_id
            WHERE p.student_id = %s
            ORDER BY p.submission_date DESC
        """, (session['student_id'],))

        projects = cursor.fetchall()

        cursor.execute(
            "SELECT name, roll_no, department FROM students WHERE id=%s",
            (session['student_id'],)
        )
        student_info = cursor.fetchone()

        return render_template(
            'student/dashboard.html',
            projects=projects,
            student=student_info
        )

    except Exception as e:
        print("❌ Error in student dashboard:", e)
        return "Internal Server Error", 500

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
            
# =========================================================
# 👩‍🏫 FACULTY MODULE
# =========================================================
# -------- FACULTY SIGNUP -------- 
@app.route('/faculty/signup', methods=['GET', 'POST']) 
def faculty_signup(): 
    if request.method == 'POST': 
        data = request.form 
        conn = get_db_connection() 
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM faculty WHERE email=%s", (data['email'],))
        if cursor.fetchone():
            return render_template('faculty/signup.html', error="Email already exists")

        cursor.execute("INSERT INTO faculty (name, email, password, department) VALUES (%s,%s,%s,%s)", 
                       (data['name'], data['email'], data['password'], data['department'])) 
        conn.commit() 
        conn.close() 
        return redirect('/faculty/login') 
    return render_template('faculty/signup.html')

@app.route('/faculty/login', methods=['GET', 'POST'])
def faculty_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM faculty WHERE email=%s AND password=%s", (email, password))
        faculty = cursor.fetchone()
        cursor.close()
        conn.close()
        if faculty:
            session['faculty_id'] = faculty['id']
            session['department'] = faculty['department']
            return redirect('/faculty/dashboard')
        return render_template('faculty/login.html', error="Invalid credentials")
    return render_template('faculty/login.html')

@app.route('/faculty/dashboard')
def faculty_dashboard():
    if 'faculty_id' not in session:
        return redirect('/faculty/login')

    dept = session['department']
    faculty_id = session['faculty_id']

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT 
            p.*, 
            s.name AS student_name, 
            s.roll_no, 
            s.department,
            e.marks,
            e.feedback
        FROM projects p
        JOIN students s ON p.student_id = s.id
        LEFT JOIN evaluations e 
            ON p.id = e.project_id AND e.faculty_id = %s
        WHERE s.department = %s
        ORDER BY p.id DESC
    """, (faculty_id, dept))

    projects = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('faculty/dashboard.html', projects=projects)

@app.route('/faculty/evaluate/<int:project_id>', methods=['GET', 'POST'])
def faculty_evaluate(project_id):

    if 'faculty_id' not in session:
        return redirect(url_for('faculty_login'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # ---------------- POST METHOD ----------------
    if request.method == 'POST':
        try:
            marks = request.form.get('marks')
            feedback = request.form.get('feedback')

            if not marks or not feedback:
                return "Marks and Feedback are required", 400

            marks = int(marks)

            if marks < 0 or marks > 100:
                return "Marks must be between 0 and 100", 400

            faculty_id = session['faculty_id']

            # 1️⃣ Update project status
            cursor.execute("""
                UPDATE projects
                SET status = 'Evaluated'
                WHERE id = %s
            """, (project_id,))

            # 2️⃣ Insert or update evaluation
            cursor.execute("""
                INSERT INTO evaluations (project_id, faculty_id, marks, feedback)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    marks = VALUES(marks),
                    feedback = VALUES(feedback),
                    faculty_id = VALUES(faculty_id)
            """, (
                project_id,
                faculty_id,
                marks,
                feedback
            ))

            conn.commit()

            return redirect(url_for('faculty_dashboard'))

        except Exception as e:
            conn.rollback()
            print("❌ Error while saving evaluation:", e)
            return "Internal Server Error", 500

        finally:
            cursor.close()
            conn.close()

    # ---------------- GET METHOD ----------------
    faculty_id = session['faculty_id']

    cursor.execute("""
        SELECT 
            p.*, 
            s.name AS student_name,
            s.roll_no,
            e.marks,
            e.feedback
        FROM projects p
        JOIN students s ON p.student_id = s.id
        LEFT JOIN evaluations e 
            ON p.id = e.project_id AND e.faculty_id = %s
        WHERE p.id = %s
    """, (faculty_id, project_id))

    project = cursor.fetchone()

    cursor.close()
    conn.close()

    if not project:
        return "Project not found", 404

    return render_template('faculty/evaluate.html', project=project)

# =========================================================
# 🧑‍💼 ADMIN MODULE (Auth)
# =========================================================
# =========================================================
# 🧑‍💼 ADMIN MODULE (HoD Restricted)
# =========================================================

@app.route('/admin/signup', methods=['GET', 'POST'])
def admin_signup():
    HOD_SECRET_KEY = "HOD_ADMIN_2026" 
    if request.method == 'POST':
        name = request.form['name']
        dept = request.form['department'].upper().strip() # Capture and Clean
        email = request.form['email'].strip()
        password = request.form['password']
        entered_code = request.form['secret_code']

        if entered_code != HOD_SECRET_KEY:
            return render_template('admin/signup.html', error="Invalid Secret Code")

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check if email exists
        cursor.execute("SELECT * FROM admin WHERE email=%s", (email,))
        if cursor.fetchone():
            conn.close()
            return render_template('admin/signup.html', error="Email already registered")

        # FIX: Include 'department' in the INSERT statement
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO admin (name, email, password, department) 
            VALUES (%s, %s, %s, %s)
        """, (name, email, password, dept))
        
        conn.commit()
        conn.close()
        return redirect('/admin/login')

    return render_template('admin/signup.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Verify credentials from the admin table
        cursor.execute("SELECT * FROM admin WHERE email=%s AND password=%s", (email, password))
        admin = cursor.fetchone()
        conn.close()

        if admin:
            # Clear previous sessions (students/faculty) to prevent access issues
            session.clear()
            
            # Set up Admin Session
            session['admin_id'] = admin['id']
            session['admin_name'] = admin['name']
            session['role'] = 'admin'
            
            # Save department - using .strip() to avoid errors from accidental spaces
            session['department'] = admin['department'].strip()
            
            return redirect('/admin/dashboard')

        # If login fails
        return render_template('admin/login.html', error="Invalid Admin Credentials")

    return render_template('admin/login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect('/admin/login')

    admin_dept = session.get('department')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch projects with evaluation details
    cursor.execute("""
        SELECT 
            p.*, 
            s.name, 
            s.roll_no, 
            s.department,
            e.marks,
            e.feedback
        FROM projects p 
        JOIN students s ON p.student_id = s.id 
        LEFT JOIN evaluations e ON p.id = e.project_id
        WHERE s.department = %s
        ORDER BY p.id DESC
    """, (admin_dept,))

    projects = cursor.fetchall()

    # Analytics
    cursor.execute("""
        SELECT status, COUNT(*) as count 
        FROM projects p 
        JOIN students s ON p.student_id = s.id 
        WHERE s.department = %s 
        GROUP BY status
    """, (admin_dept,))

    analytics = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template("admin/dashboard.html",
                           projects=projects,
                           analytics=analytics,
                           dept=admin_dept)

@app.route('/admin/download-report')
def download_report():
    if session.get('role') != 'admin':
        return redirect('/admin/login')

    dept = session.get('department')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # ✅ FIX: Join with students table to filter department correctly
    cursor.execute("""
        SELECT p.title, p.similarity_percentage, s.name, s.roll_no
        FROM projects p
        JOIN students s ON p.student_id = s.id
        WHERE p.status = 'Flagged' AND s.department = %s
    """, (dept,))

    flagged_projects = cursor.fetchall()
    conn.close()

    # -------- PDF CREATION --------
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(150, 800, f"Flagged Projects Report - {dept}")

    y = 760
    pdf.setFont("Helvetica", 10)

    if not flagged_projects:
        pdf.drawString(100, y, "No flagged projects found.")
    else:
        for proj in flagged_projects:
            pdf.drawString(50, y, f"Student : {proj['name']} ({proj['roll_no']})")
            y -= 15
            pdf.drawString(50, y, f"Project : {proj['title']}")
            y -= 15
            pdf.drawString(50, y, f"Similarity : {proj['similarity_percentage']}%")
            y -= 25

            # if page overflow create new page
            if y < 50:
                pdf.showPage()
                pdf.setFont("Helvetica", 10)
                y = 800

    pdf.save()

    buffer.seek(0)

    response = make_response(buffer.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=flagged_report.pdf'

    return response

# ---------------- FILE DOWNLOAD ----------------
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ---------------- LOGOUT ----------------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

