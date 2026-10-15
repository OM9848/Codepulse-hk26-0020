# python app.py
# cloudflared tunnel --url http://localhost:5000
from flask import Flask, render_template, request, redirect, url_for, send_file, session
from functools import wraps
import sqlite3
import os
import uuid
import qrcode

from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor


# =========================================================
# FLASK APP
# =========================================================

app = Flask(__name__)

# Session ke liye secret key
app.secret_key = "BITL_SMART_ID_SECRET_2026"


# =========================================================
# CONFIGURATION
# =========================================================

# CURRENT CLOUDFLARE URL
# Agar cloudflared naya URL de, isko change karna hoga.
PUBLIC_URL = "https://screening-right-foundation-favour.trycloudflare.com"

DATABASE = "database.db"

UPLOAD_FOLDER = "static/uploads"
QR_FOLDER = "static/qr"
ID_CARD_FOLDER = "static/id_cards"

COLLEGE_IMAGE = "static/college.jpg"


# =========================================================
# ADMIN LOGIN DETAILS
# =========================================================

ADMIN_USERNAME = "collegeadmin"
ADMIN_PASSWORD = "BITL@2026"


# =========================================================
# CREATE FOLDERS
# =========================================================

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QR_FOLDER, exist_ok=True)
os.makedirs(ID_CARD_FOLDER, exist_ok=True)


# =========================================================
# ADMIN LOGIN PROTECTION
# =========================================================

def admin_required(f):

    @wraps(f)
    def decorated_function(*args, **kwargs):

        if not session.get("admin_logged_in"):
            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return decorated_function


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def init_db():

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            roll_no TEXT UNIQUE NOT NULL,
            branch TEXT NOT NULL,
            year TEXT NOT NULL,
            phone TEXT,
            token TEXT UNIQUE NOT NULL,
            photo TEXT
        )
    """)

    # Existing database ke columns check karo
    cursor.execute("PRAGMA table_info(students)")

    columns = [
        column[1]
        for column in cursor.fetchall()
    ]

    # Agar old database mein photo column nahi hai
    if "photo" not in columns:

        cursor.execute(
            "ALTER TABLE students ADD COLUMN photo TEXT"
        )

    conn.commit()
    conn.close()


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():

    return render_template("index.html")


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    # Agar already login hai
    if session.get("admin_logged_in"):

        return redirect(url_for("admin"))

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if (
            username == ADMIN_USERNAME
            and password == ADMIN_PASSWORD
        ):

            session["admin_logged_in"] = True

            return redirect(url_for("admin"))

        return render_template(
            "login.html",
            error="Invalid username or password."
        )

    return render_template("login.html")


# =========================================================
# ADMIN LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# =========================================================
# REGISTER STUDENT
# =========================================================

@app.route("/register", methods=["GET", "POST"])
@admin_required
def register():

    if request.method == "POST":

        # -------------------------------------------------
        # FORM DATA
        # -------------------------------------------------

        name = request.form.get(
            "name",
            ""
        ).strip()

        roll_no = request.form.get(
            "roll_no",
            ""
        ).strip()

        branch = request.form.get(
            "branch",
            ""
        ).strip()

        year = request.form.get(
            "year",
            ""
        ).strip()

        phone = request.form.get(
            "phone",
            ""
        ).strip()

        photo = request.files.get("photo")


        # -------------------------------------------------
        # VALIDATION
        # -------------------------------------------------

        if not name:
            return "Student name is required."

        if not roll_no:
            return "Roll number is required."

        if not branch:
            return "Branch is required."

        if not year:
            return "Year is required."

        if not photo or photo.filename == "":
            return "Please upload student photo."


        # -------------------------------------------------
        # IMAGE EXTENSION
        # -------------------------------------------------

        allowed_extensions = {
            "jpg",
            "jpeg",
            "png",
            "webp"
        }

        original_filename = photo.filename

        if "." not in original_filename:
            return "Invalid image file."

        extension = original_filename.rsplit(
            ".",
            1
        )[1].lower()

        if extension not in allowed_extensions:

            return (
                "Only JPG, JPEG, PNG and WEBP "
                "images are allowed."
            )


        # -------------------------------------------------
        # UNIQUE PHOTO NAME
        # -------------------------------------------------

        photo_filename = (
            str(uuid.uuid4())
            + "."
            + extension
        )

        photo_path = os.path.join(
            UPLOAD_FOLDER,
            photo_filename
        )

        photo.save(photo_path)


        # -------------------------------------------------
        # UNIQUE TOKEN
        # -------------------------------------------------

        token = str(uuid.uuid4())


        # -------------------------------------------------
        # DATABASE INSERT
        # -------------------------------------------------

        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        try:

            cursor.execute("""
                INSERT INTO students
                (
                    name,
                    roll_no,
                    branch,
                    year,
                    phone,
                    token,
                    photo
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                name,
                roll_no,
                branch,
                year,
                phone,
                token,
                photo_filename
            ))

            student_id = cursor.lastrowid

            conn.commit()

        except sqlite3.IntegrityError:

            conn.close()

            # Registration failed, photo delete
            if os.path.exists(photo_path):
                os.remove(photo_path)

            return "Roll number already registered."

        conn.close()


        # -------------------------------------------------
        # QR CODE
        # -------------------------------------------------

        verify_url = (
            PUBLIC_URL
            + "/verify/"
            + token
        )

        qr = qrcode.make(verify_url)

        qr_path = os.path.join(
            QR_FOLDER,
            f"{roll_no}.png"
        )

        qr.save(qr_path)


        # -------------------------------------------------
        # ID CARD
        # -------------------------------------------------

        return redirect(
            url_for(
                "id_card",
                student_id=student_id
            )
        )


    return render_template(
        "register.html"
    )


# =========================================================
# SHOW ID CARD
# =========================================================

@app.route("/id-card/<int:student_id>")
@admin_required
def id_card(student_id):

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM students WHERE id=?",
        (student_id,)
    )

    student = cursor.fetchone()

    conn.close()

    if not student:
        return "Student not found.", 404

    return render_template(
        "id_card.html",
        student=student
    )


# =========================================================
# DOWNLOAD SINGLE-SIDE ID CARD
# =========================================================

@app.route("/download-id-card/<int:student_id>")
@admin_required
def download_id_card(student_id):

    # -----------------------------------------------------
    # GET STUDENT
    # -----------------------------------------------------

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM students WHERE id=?",
        (student_id,)
    )

    student = cursor.fetchone()

    conn.close()

    if not student:
        return "Student not found.", 404


    # -----------------------------------------------------
    # PDF NAME
    # -----------------------------------------------------

    pdf_filename = (
        f"id_card_{student[2]}.pdf"
    )

    pdf_path = os.path.join(
        ID_CARD_FOLDER,
        pdf_filename
    )


    # -----------------------------------------------------
    # CARD SIZE
    # -----------------------------------------------------

    card_width = 400
    card_height = 600


    # -----------------------------------------------------
    # CREATE PDF
    # -----------------------------------------------------

    c = canvas.Canvas(
        pdf_path,
        pagesize=(
            card_width,
            card_height
        )
    )


    # =====================================================
    # BACKGROUND
    # =====================================================

    c.setFillColor(
        HexColor("#111827")
    )

    c.roundRect(
        10,
        10,
        card_width - 20,
        card_height - 20,
        18,
        fill=1,
        stroke=0
    )


    # =====================================================
    # COLLEGE IMAGE
    # =====================================================

    if os.path.exists(COLLEGE_IMAGE):

        try:

            c.drawImage(
                COLLEGE_IMAGE,
                30,
                480,
                width=340,
                height=85,
                preserveAspectRatio=True,
                anchor="c",
                mask="auto"
            )

        except Exception:
            pass


    # =====================================================
    # COLLEGE NAME
    # =====================================================

    c.setFillColor(
        HexColor("#FFFFFF")
    )

    c.setFont(
        "Helvetica-Bold",
        12
    )

    c.drawCentredString(
        card_width / 2,
        458,
        "BANSAL INSTITUTE OF ENGINEERING"
    )

    c.drawCentredString(
        card_width / 2,
        442,
        "AND TECHNOLOGY, LUCKNOW"
    )


    # =====================================================
    # DIVIDER
    # =====================================================

    c.setStrokeColor(
        HexColor("#374151")
    )

    c.setLineWidth(1)

    c.line(
        30,
        425,
        370,
        425
    )


    # =====================================================
    # STUDENT PHOTO
    # =====================================================

    photo_filename = student[7]

    if photo_filename:

        photo_path = os.path.join(
            UPLOAD_FOLDER,
            photo_filename
        )

        if os.path.exists(photo_path):

            try:

                c.drawImage(
                    photo_path,
                    35,
                    275,
                    width=115,
                    height=130,
                    preserveAspectRatio=True,
                    anchor="c",
                    mask="auto"
                )

            except Exception:
                pass

    else:

        c.setStrokeColor(
            HexColor("#6B7280")
        )

        c.rect(
            35,
            275,
            115,
            130,
            fill=0,
            stroke=1
        )

        c.setFillColor(
            HexColor("#9CA3AF")
        )

        c.setFont(
            "Helvetica",
            10
        )

        c.drawCentredString(
            92,
            335,
            "PHOTO"
        )


    # =====================================================
    # STUDENT INFORMATION
    # =====================================================

    info_x = 175


    # -----------------------------------------------------
    # NAME
    # -----------------------------------------------------

    c.setFillColor(
        HexColor("#FFFFFF")
    )

    c.setFont(
        "Helvetica-Bold",
        15
    )

    name = str(student[1])

    if len(name) > 20:

        name = (
            name[:20]
            + "..."
        )

    c.drawString(
        info_x,
        385,
        name
    )


    # -----------------------------------------------------
    # DETAILS
    # -----------------------------------------------------

    c.setFont(
        "Helvetica",
        10
    )

    c.setFillColor(
        HexColor("#D1D5DB")
    )


    # Roll number

    c.drawString(
        info_x,
        355,
        f"Roll No : {student[2]}"
    )


    # Branch

    branch = str(student[3])

    if len(branch) > 22:

        branch = (
            branch[:22]
            + "..."
        )

    c.drawString(
        info_x,
        330,
        f"Branch  : {branch}"
    )


    # Year

    c.drawString(
        info_x,
        305,
        f"Year    : {student[4]}"
    )


    # Phone

    phone = (
        student[5]
        if student[5]
        else "Not Provided"
    )

    c.drawString(
        info_x,
        280,
        f"Phone   : {phone}"
    )


    # =====================================================
    # SECOND DIVIDER
    # =====================================================

    c.setStrokeColor(
        HexColor("#374151")
    )

    c.line(
        30,
        245,
        370,
        245
    )


    # =====================================================
    # QR CODE
    # =====================================================

    qr_path = os.path.join(
        QR_FOLDER,
        f"{student[2]}.png"
    )

    if os.path.exists(qr_path):

        try:

            c.drawImage(
                qr_path,
                140,
                75,
                width=120,
                height=120,
                preserveAspectRatio=True,
                anchor="c",
                mask="auto"
            )

        except Exception:
            pass


    # =====================================================
    # QR TEXT
    # =====================================================

    c.setFillColor(
        HexColor("#D1D5DB")
    )

    c.setFont(
        "Helvetica",
        9
    )

    c.drawCentredString(
        card_width / 2,
        55,
        "Scan QR Code to Verify Student"
    )


    # =====================================================
    # ONE PAGE ONLY
    # =====================================================

    c.showPage()
    c.save()


    # -----------------------------------------------------
    # SEND PDF
    # -----------------------------------------------------

    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=pdf_filename
    )


# =========================================================
# VERIFY STUDENT
# =========================================================

@app.route("/verify/<token>")
def verify(token):

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM students WHERE token=?",
        (token,)
    )

    student = cursor.fetchone()

    conn.close()


    # =====================================================
    # INVALID TOKEN
    # =====================================================

    if not student:

        return """
<!DOCTYPE html>
<html>

<head>

    <meta charset="UTF-8">

    <meta name="viewport"
          content="width=device-width, initial-scale=1.0">

    <title>Invalid ID</title>

    <style>

        body {

            margin: 0;

            font-family: Arial, sans-serif;

            background: #111827;

            color: white;

            min-height: 100vh;

            display: flex;

            justify-content: center;

            align-items: center;

            padding: 20px;

        }

        .box {

            background: #1f2937;

            padding: 40px;

            border-radius: 20px;

            text-align: center;

            max-width: 400px;

            width: 100%;

            box-shadow:
                0 20px 60px
                rgba(0,0,0,0.4);

        }

        h1 {
            color: #ef4444;
        }

    </style>

</head>

<body>

    <div class="box">

        <h1>
            ❌ Invalid ID
        </h1>

        <p>
            This student ID could not be verified.
        </p>

    </div>

</body>

</html>
"""


    # =====================================================
    # STUDENT PHOTO
    # =====================================================

    photo_html = ""

    if student[7]:

        photo_path = os.path.join(
            UPLOAD_FOLDER,
            student[7]
        )

        if os.path.exists(photo_path):

            photo_html = f"""
            <img
                src="/static/uploads/{student[7]}"
                class="student-photo"
                alt="Student Photo"
            >
            """


    # =====================================================
    # PHONE
    # =====================================================

    phone = (
        student[5]
        if student[5]
        else "Not Provided"
    )


    # =====================================================
    # VERIFIED PAGE
    # =====================================================

    return f"""
<!DOCTYPE html>

<html>

<head>

    <meta charset="UTF-8">

    <meta name="viewport"
          content="width=device-width, initial-scale=1.0">

    <title>Student Verified</title>

    <style>

        * {{
            box-sizing: border-box;
        }}

        body {{

            margin: 0;

            padding: 20px;

            font-family: Arial, sans-serif;

            background:
                linear-gradient(
                    135deg,
                    #0f172a,
                    #1e293b
                );

            color: white;

            min-height: 100vh;

            display: flex;

            justify-content: center;

            align-items: center;

        }}

        .card {{

            width: 100%;

            max-width: 430px;

            background: #111827;

            padding: 30px;

            border-radius: 20px;

            text-align: center;

            box-shadow:
                0 20px 60px
                rgba(0,0,0,0.45);

        }}

        .verified {{

            display: inline-block;

            background: #16a34a;

            color: white;

            padding: 10px 20px;

            border-radius: 30px;

            font-weight: bold;

            margin-bottom: 20px;

        }}

        .college {{

            font-size: 18px;

            font-weight: bold;

            line-height: 1.5;

            margin-bottom: 20px;

        }}

        .student-photo {{

            width: 130px;

            height: 150px;

            object-fit: cover;

            border-radius: 12px;

            border: 3px solid #374151;

            margin-bottom: 15px;

        }}

        h1 {{

            font-size: 24px;

            margin: 10px 0 20px;

        }}

        .details {{

            background: #1f2937;

            border-radius: 12px;

            padding: 15px;

            text-align: left;

        }}

        .row {{

            display: flex;

            justify-content: space-between;

            gap: 15px;

            padding: 10px 0;

            border-bottom:
                1px solid #374151;

        }}

        .row:last-child {{
            border-bottom: none;
        }}

        .label {{

            color: #94a3b8;

            font-weight: bold;

        }}

        .value {{

            color: white;

            text-align: right;

            word-break: break-word;

        }}

        .footer {{

            margin-top: 20px;

            color: #94a3b8;

            font-size: 12px;

        }}

    </style>

</head>

<body>

    <div class="card">

        <div class="verified">
            ✓ STUDENT VERIFIED
        </div>

        <div class="college">

            BANSAL INSTITUTE OF ENGINEERING
            <br>
            AND TECHNOLOGY, LUCKNOW

        </div>

        {photo_html}

        <h1>
            {student[1]}
        </h1>

        <div class="details">

            <div class="row">

                <span class="label">
                    Roll No
                </span>

                <span class="value">
                    {student[2]}
                </span>

            </div>


            <div class="row">

                <span class="label">
                    Branch
                </span>

                <span class="value">
                    {student[3]}
                </span>

            </div>


            <div class="row">

                <span class="label">
                    Year
                </span>

                <span class="value">
                    {student[4]}
                </span>

            </div>


            <div class="row">

                <span class="label">
                    Phone
                </span>

                <span class="value">
                    {phone}
                </span>

            </div>

        </div>

        <div class="footer">

            ID verified through
            Smart Secure ID Card System.

        </div>

    </div>

</body>

</html>
"""


# =========================================================
# DELETE STUDENT
# =========================================================

@app.route(
    "/delete-student/<int:student_id>",
    methods=["POST"]
)
@admin_required
def delete_student(student_id):

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM students WHERE id=?",
        (student_id,)
    )

    student = cursor.fetchone()

    if not student:

        conn.close()

        return "Student not found.", 404


    # -----------------------------------------------------
    # DELETE PHOTO
    # -----------------------------------------------------

    photo_filename = student[7]

    if photo_filename:

        photo_path = os.path.join(
            UPLOAD_FOLDER,
            photo_filename
        )

        if os.path.exists(photo_path):
            os.remove(photo_path)


    # -----------------------------------------------------
    # DELETE QR
    # -----------------------------------------------------

    qr_path = os.path.join(
        QR_FOLDER,
        f"{student[2]}.png"
    )

    if os.path.exists(qr_path):
        os.remove(qr_path)


    # -----------------------------------------------------
    # DELETE PDF
    # -----------------------------------------------------

    pdf_path = os.path.join(
        ID_CARD_FOLDER,
        f"id_card_{student[2]}.pdf"
    )

    if os.path.exists(pdf_path):
        os.remove(pdf_path)


    # -----------------------------------------------------
    # DELETE DATABASE RECORD
    # -----------------------------------------------------

    cursor.execute(
        "DELETE FROM students WHERE id=?",
        (student_id,)
    )

    conn.commit()
    conn.close()

    return redirect(
        url_for("admin")
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin")
@admin_required
def admin():

    search = request.args.get(
        "search",
        ""
    ).strip()

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()


    # -----------------------------------------------------
    # SEARCH
    # -----------------------------------------------------

    if search:

        cursor.execute("""
            SELECT *
            FROM students
            WHERE roll_no LIKE ?
            ORDER BY id DESC
        """, (
            "%" + search + "%",
        ))

    else:

        cursor.execute("""
            SELECT *
            FROM students
            ORDER BY id DESC
        """)


    students = cursor.fetchall()

    conn.close()


    return render_template(
        "admin.html",
        students=students,
        search=search
    )


# =========================================================
# START SERVER
# =========================================================

if __name__ == "__main__":

    init_db()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )