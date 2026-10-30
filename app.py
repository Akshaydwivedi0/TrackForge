from flask import Flask, render_template,request,redirect,url_for,session,flash
from werkzeug.security import generate_password_hash,check_password_hash
import mysql.connector
import secrets
import string
from werkzeug.security import generate_password_hash



import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY")
db = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    port=int(os.getenv("DB_PORT", 3306)),
    ssl_ca=os.getenv("DB_SSL_CA"),
    ssl_verify_cert=True
)

@app.route("/")
def home():
    return render_template("User/index.html")

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]
        address = request.form["address"]
        password = request.form["password"]

        hashed_password = generate_password_hash(password)

        cursor = db.cursor()

        query = """
        insert into users (name,email,phone,address,password)
        values (%s,%s,%s,%s,%s)
        """

        cursor.execute(
            query,(name,email,phone,address,hashed_password)
        )

        db.commit()
        cursor.close()

        flash("Registration successful please log in." "success")
        return redirect(url_for("login"))

    return render_template("User/register.html")

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        cursor = db.cursor(dictionary=True)

        cursor.execute("select * from users where email = %s",(email,))

        user = cursor.fetchone()
        cursor.close()


        if user and check_password_hash(user["password"],password):

            session["user_id"] = user["user_id"]
            session["user_name"] = user["name"]

            return redirect(url_for("dashboard"))

        flash("invalid email or password.","danger")

    return render_template("User/login.html")
@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    cursor = db.cursor(dictionary=True)

    try:

        # Total parcels
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM parcels
            WHERE user_id = %s
        """, (session["user_id"],))

        total = cursor.fetchone()["total"]


        # In Transit parcels
        cursor.execute("""
            SELECT COUNT(*) AS in_transit
            FROM parcels p
            WHERE p.user_id = %s
            AND COALESCE(
                (
                    SELECT t.status
                    FROM tracking t
                    WHERE t.parcel_id = p.parcel_id
                    ORDER BY t.updated_at DESC, t.tracking_id DESC
                    LIMIT 1
                ),
                'Booked'
            ) = 'In Transit'
        """, (session["user_id"],))

        in_transit = cursor.fetchone()["in_transit"]


        # Pending / Booked parcels
        cursor.execute("""
            SELECT COUNT(*) AS pending
            FROM parcels p
            WHERE p.user_id = %s
            AND COALESCE(
                (
                    SELECT t.status
                    FROM tracking t
                    WHERE t.parcel_id = p.parcel_id
                    ORDER BY t.updated_at DESC, t.tracking_id DESC
                    LIMIT 1
                ),
                'Booked'
            ) = 'Booked'
        """, (session["user_id"],))

        pending = cursor.fetchone()["pending"]


        # Recent shipments
        cursor.execute("""
            SELECT
                p.tracking_id,
                p.receiver_name,
                p.destination,
                COALESCE(
                    (
                        SELECT t.status
                        FROM tracking t
                        WHERE t.parcel_id = p.parcel_id
                        ORDER BY t.updated_at DESC, t.tracking_id DESC
                        LIMIT 1
                    ),
                    'Booked'
                ) AS status
            FROM parcels p
            WHERE p.user_id = %s
            ORDER BY p.booking_date DESC
            LIMIT 5
        """, (session["user_id"],))

        recent_parcels = cursor.fetchall()


        return render_template(
            "User/dashboard.html",
            name=session.get("user_name","User"),
            total=total,
            in_transit=in_transit,
            pending=pending,
            recent_parcels=recent_parcels
        )


    except mysql.connector.Error:
        flash("Unable to load dashboard data.", "danger")

        return render_template(
            "User/dashboard.html",
            name=session.get("name"),
            total=0,
            in_transit=0,
            pending=0,
            recent_parcels=[]
        )


    finally:
        cursor.close()
@app.route("/logout")
def logout():

    session.clear()

    return redirect("home")
def generate_tracking_id(cursor):
    characters = string.ascii_uppercase + string.digits

    while True:
        tracking_id = "TRK" + "".join(
            secrets.choice(characters) for _ in range(8)
        )

        cursor.execute(
            "SELECT parcel_id FROM parcels WHERE tracking_id = %s",
            (tracking_id,)
        )

        if cursor.fetchone() is None:
            return tracking_id


@app.route("/book", methods=["GET", "POST"])
def book_parcel():
    if "user_id" not in session:
        flash("Please log in before booking a parcel.", "warning")
        return redirect(url_for("login"))

    if request.method == "POST":
        # Get form values. Names must match book_parcel.html exactly.
        receiver_name = request.form.get("Receiver_name", "").strip()
        receiver_phone = request.form.get("Receiver_phone", "").strip()
        origin = request.form.get("origin", "").strip()
        destination = request.form.get("destination", "").strip()
        parcel_detail = request.form.get("Parcel_details", "").strip()

        # Validate all required fields.
        empty_fields = [
            name for name, value in [
                ("Receiver Name", receiver_name),
                ("Receiver Phone", receiver_phone),
                ("Pickup Address", origin),
                ("Delivery Address", destination),
                ("Parcel Description", parcel_detail)
            ]
            if not value
        ]

        if empty_fields:
            flash(
                "Please fill in: " + ", ".join(empty_fields),
                "warning"
            )
            return render_template("User/book_parcel.html")

        cursor = db.cursor()

        try:
            # Generate a unique public tracking ID.
            tracking_id = generate_tracking_id(cursor)

            # Insert the parcel only once.
            cursor.execute(
                """
                INSERT INTO parcels (
                    user_id,
                    tracking_id,
                    receiver_name,
                    receiver_phone,
                    origin,
                    destination,
                    parcel_detail
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    session["user_id"],
                    tracking_id,
                    receiver_name,
                    receiver_phone,
                    origin,
                    destination,
                    parcel_detail
                )
            )

            # Get the newly created parcel's internal ID.
            parcel_id = cursor.lastrowid

            # Create the first tracking record.
            cursor.execute(
                """
                INSERT INTO tracking (
                    parcel_id,
                    status,
                    location
                )
                VALUES (%s, %s, %s)
                """,
                (parcel_id, "Booked", origin)
            )
            cursor.execute(
    """
    INSERT INTO payment (
        parcel_id,
        amount,
        method,
        status
    )
    VALUES (%s, %s, %s, %s)
    """,
    (parcel_id, 100.00, "Cash on Delivery", "pending")
)
            db.commit()

            flash(
                f"Parcel booked successfully! Your tracking ID is {tracking_id}",
                "success"
            )

            return redirect(url_for("my_parcels"))

        except mysql.connector.Error as e:
            db.rollback()
            flash(f"Booking failed: {e}", "danger")

        finally:
            cursor.close()

    return render_template("User/book_parcel.html")
@app.route("/track-parcel", methods=["GET", "POST"])
def track_parcel():
    if "user_id" not in session:
        return redirect("login")

    parcel = None
    history = []
    searched_tracking_id = ""

    if request.method == "POST":
        searched_tracking_id = request.form.get("tracking_id", "").strip().upper()

    elif request.method == "GET":
        searched_tracking_id = request.args.get("tracking_id", "").strip().upper()

    if searched_tracking_id:
        cursor = db.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT
                    p.parcel_id,
                    p.tracking_id,
                    p.receiver_name,
                    p.origin,
                    p.destination,
                    p.booking_date,
                    da.name AS agent_name,
                    da.phone AS agent_phone,
                    b.branch_name
                FROM parcels p
                LEFT JOIN delivery_agents da
                    ON p.agent_id = da.agent_id
                LEFT JOIN branches b
                    ON p.branch_id = b.branch_id
                WHERE p.tracking_id = %s
                  AND p.user_id = %s
            """, (searched_tracking_id, session["user_id"]))

            parcel = cursor.fetchone()

            if parcel:

                cursor.execute("""
                    SELECT status, location, updated_at
                    FROM tracking
                    WHERE parcel_id = %s
                    ORDER BY updated_at ASC, tracking_id ASC
                """, (parcel["parcel_id"],))

                history = cursor.fetchall()

                parcel["current_status"] = (
                    history[-1]["status"] if history else "Booked"
                )

                parcel.pop("parcel_id", None)

            else:
                flash("No matching parcel found in your account", "danger")

        except mysql.connector.Error as e:
            db.rollback()
            flash(f"Tracking error: {e}", "danger")

        finally:
            cursor.close()

    return render_template(
        "User/track_parcel.html",
        parcel=parcel,
        history=history,
        searched_tracking_id=searched_tracking_id
    )
@app.route("/my-parcels")
def my_parcels():
    if"user_id" not in session:
        return redirect(url_for("login"))
    cursor =db.cursor(dictionary=True)
    cursor.execute("""
      select p.parcel_id,p.tracking_id,p.receiver_name,p.destination,p.booking_date,
          ( select t.status from tracking t where t.parcel_id=p.parcel_id
            order by t.updated_at desc, t.tracking_id desc limit 1
            ) as status  from parcels p where p.user_id=%s
              order by p.booking_date desc """,(session["user_id"],))
    parcels=cursor.fetchall()
    cursor.close()
    return render_template("User/my_parcels.html",parcels=parcels)
@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        cursor = db.cursor(dictionary=True)

        cursor.execute(
            "SELECT * FROM admin WHERE email = %s",
            (email,)
        )

        admin = cursor.fetchone()
        cursor.close()

        if admin and check_password_hash(admin["password"], password):

            session["admin_id"] = admin["admin_id"]
            session["admin_name"] = admin["name"]

            return redirect(url_for("admin_dashboard"))

        flash("Invalid admin email or password.", "danger")

    return render_template("Admin/admin_login.html")

@app.route("/admin-dashboard")
def admin_dashboard():

    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    cursor = db.cursor(dictionary=True)

    # Dashboard statistics
    cursor.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(status = 'Booked') AS booked,
            SUM(status = 'In Transit') AS in_transit,
            SUM(status = 'Delivered') AS delivered
        FROM (
            SELECT
                p.parcel_id,
                COALESCE(
                    (
                        SELECT t.status
                        FROM tracking t
                        WHERE t.parcel_id = p.parcel_id
                        ORDER BY t.updated_at DESC
                        LIMIT 1
                    ),
                    'Booked'
                ) AS status
            FROM parcels p
        ) AS x
    """)

    stats = cursor.fetchone()

    # Recent shipments
    cursor.execute("""
        SELECT
            p.parcel_id,
            p.tracking_id,
            u.name AS customer_name,
            p.destination,
            COALESCE(
                (
                    SELECT t.status
                    FROM tracking t
                    WHERE t.parcel_id = p.parcel_id
                    ORDER BY t.updated_at DESC
                    LIMIT 1
                ),
                'Booked'
            ) AS status
        FROM parcels p
        JOIN users u ON p.user_id = u.user_id
        ORDER BY p.booking_date DESC
        LIMIT 5
    """)

    recent_parcels = cursor.fetchall()

    cursor.close()

    stats = {
        "total": stats["total"] or 0,
        "booked": stats["booked"] or 0,
        "in_transit": stats["in_transit"] or 0,
        "delivered": stats["delivered"] or 0
    }

    return render_template(
        "Admin/admin_dashboard.html",
        stats=stats,
        recent_parcels=recent_parcels
    )

@app.route("/admin/parcels")
def admin_parcels():

    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            p.parcel_id,
            p.tracking_id,
            u.name AS customer_name,
            p.receiver_name,
            p.destination,
            p.agent_id,
            p.branch_id,
            COALESCE(
                (
                    SELECT t.status
                    FROM tracking t
                    WHERE t.parcel_id = p.parcel_id
                    ORDER BY t.updated_at DESC
                    LIMIT 1
                ),
                'Booked'
            ) AS status,
            da.name AS agent_name,
            b.branch_name
        FROM parcels p
        JOIN users u ON p.user_id = u.user_id
        LEFT JOIN delivery_agents da ON p.agent_id = da.agent_id
        LEFT JOIN branches b ON p.branch_id = b.branch_id
        ORDER BY p.booking_date DESC
    """)
    parcels = cursor.fetchall()

    cursor.execute("""
        SELECT agent_id, name
        FROM delivery_agents
        WHERE status = 'available'
        ORDER BY name
    """)
    agents = cursor.fetchall()

    cursor.execute("""
        SELECT branch_id, branch_name
        FROM branches
        ORDER BY branch_name
    """)
    branches = cursor.fetchall()

    cursor.close()

    return render_template(
        "Admin/admin_parcels.html",
        parcels=parcels,
        agents=agents,
        branches=branches
    )
@app.route("/admin/assign-parcel/<int:parcel_id>", methods=["POST"])
def assign_parcel(parcel_id):

    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    agent_id = request.form.get("agent_id") or None
    branch_id = request.form.get("branch_id") or None

    cursor = db.cursor()

    try:
        cursor.execute("""
            UPDATE parcels
            SET agent_id = %s,
                branch_id = %s
            WHERE parcel_id = %s
        """, (agent_id, branch_id, parcel_id))

        db.commit()
        flash("Agent and branch assigned successfully.", "success")

    except mysql.connector.Error:
        db.rollback()
        flash("Unable to assign agent or branch.", "danger")

    finally:
        cursor.close()

    return redirect(url_for("admin_parcels"))

@app.route("/admin/update-status/<int:parcel_id>", methods=["POST"])
def update_status(parcel_id):

    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    status = request.form.get("status")

    if status not in ["Booked", "In Transit", "Delivered"]:
        flash("Invalid status.", "danger")
        return redirect(url_for("admin_parcels"))

    cursor = db.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT origin
            FROM parcels
            WHERE parcel_id = %s
        """, (parcel_id,))

        parcel = cursor.fetchone()

        if not parcel:
            flash("Parcel not found.", "danger")
            return redirect(url_for("admin_parcels"))

        cursor.execute("""
            INSERT INTO tracking
            (parcel_id, status, location)
            VALUES (%s, %s, %s)
        """, (
            parcel_id,
            status,
            parcel["origin"]
        ))

        db.commit()

        flash("Parcel status updated.", "success")

    except mysql.connector.Error:
        db.rollback()
        flash("Unable to update status.", "danger")

    finally:
        cursor.close()

    return redirect(url_for("admin_parcels"))

@app.route("/admin/customers")
def admin_customers():

    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            user_id,
            name,
            email,
            phone,
            Address,
            created_at
        FROM users
        ORDER BY created_at DESC
    """)

    customers = cursor.fetchall()
    cursor.close()

    return render_template(
        "Admin/admin_customers.html",
        customers=customers
    )

@app.route("/admin/agents")
def admin_agents():

    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            agent_id,
            name,
            phone,
            area,
            status
        FROM delivery_agents
        ORDER BY name
    """)

    agents = cursor.fetchall()
    cursor.close()

    return render_template(
        "Admin/admin_agents.html",
        agents=agents
    )

@app.route("/ai-assistant", methods=["GET", "POST"])
def ai_assistant():

    if "user_id" not in session:
        return redirect(url_for("login"))

    answer = None

    if request.method == "POST":

        question = request.form.get("question", "").strip()
        question_lower = question.lower()

        if not question:
            flash("Please enter a question.", "warning")

        else:
            cursor = db.cursor(dictionary=True)

            # User's parcel information
            cursor.execute("""
                SELECT
                    p.parcel_id,
                    p.tracking_id,
                    p.receiver_name,
                    p.destination,
                    COALESCE(
                        (
                            SELECT t.status
                            FROM tracking t
                            WHERE t.parcel_id = p.parcel_id
                            ORDER BY t.updated_at DESC, t.tracking_id DESC
                            LIMIT 1
                        ),
                        'Booked'
                    ) AS status
                FROM parcels p
                WHERE p.user_id = %s
                ORDER BY p.booking_date DESC
            """, (session["user_id"],))

            parcels = cursor.fetchall()

            # User's payment information
            cursor.execute("""
                SELECT
                    pay.amount,
                    pay.method,
                    pay.status,
                    p.tracking_id
                FROM payment pay
                JOIN parcels p
                    ON pay.parcel_id = p.parcel_id
                WHERE p.user_id = %s
                ORDER BY pay.payment_date DESC
            """, (session["user_id"],))

            payments = cursor.fetchall()

            cursor.close()

            # AI-style response using actual database information

            if "status" in question_lower or "track" in question_lower:

                if parcels:
                    parcel = parcels[0]

                    answer = (
                        f"Your latest parcel {parcel['tracking_id']} "
                        f"is currently {parcel['status']}. "
                        f"Destination: {parcel['destination']}."
                    )
                else:
                    answer = "You don't have any booked parcels yet."

            elif "where" in question_lower or "location" in question_lower:

                if parcels:
                    parcel = parcels[0]

                    answer = (
                        f"Your latest parcel is currently "
                        f"{parcel['status']}. "
                        f"You can view its detailed tracking history "
                        f"from the Track Parcel section."
                    )
                else:
                    answer = "You don't have any parcels to track."

            elif "payment" in question_lower:

                if payments:
                    payment = payments[0]

                    answer = (
                        f"Your latest payment for tracking ID "
                        f"{payment['tracking_id']} is "
                        f"{payment['status']}. "
                        f"Amount: ₹{payment['amount']}."
                    )
                else:
                    answer = "No payment records were found."

            elif "how many" in question_lower or "total" in question_lower:

                answer = (
                    f"You currently have {len(parcels)} parcel(s) "
                    f"booked with TrackForge."
                )

            elif "book" in question_lower:

                answer = (
                    "To book a parcel, open the Book a Parcel section "
                    "and enter the receiver, pickup and delivery details."
                )

            elif "delivery" in question_lower:

                if parcels:
                    parcel = parcels[0]

                    answer = (
                        f"Your latest parcel is currently "
                        f"{parcel['status']} and is being delivered to "
                        f"{parcel['destination']}."
                    )
                else:
                    answer = "You don't have any active parcels."

            else:

                answer = (
                    "I can help you with parcel tracking, delivery status, "
                    "payments, bookings and your shipment information."
                )

    return render_template(
        "User/ai_assistant.html",
        answer=answer
    )

@app.route("/admin/branches")
def admin_branches():

    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            branch_id,
            branch_name,
            location,
            phone
        FROM branches
        ORDER BY branch_name
    """)

    branches = cursor.fetchall()
    cursor.close()

    return render_template(
        "Admin/admin_branches.html",
        branches=branches
    )

@app.route("/admin/tracking")
def admin_tracking():

    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            t.tracking_id,
            t.parcel_id,
            p.tracking_id AS tracking_code,
            t.status,
            t.location,
            t.updated_at
        FROM tracking t
        JOIN parcels p
            ON t.parcel_id = p.parcel_id
        ORDER BY t.updated_at DESC, t.tracking_id DESC
    """)

    tracking = cursor.fetchall()
    cursor.close()

    return render_template(
        "Admin/admin_tracking.html",
        tracking=tracking
    )

@app.route("/admin/payments")
def admin_payments():

    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    cursor = db.cursor(dictionary=True)

    cursor.execute("""
        SELECT
            py.payment_id,
            p.tracking_id,
            u.name AS customer_name,
            py.amount,
            py.method,
            py.status,
            py.payment_date
        FROM payment py
        JOIN parcels p
            ON py.parcel_id = p.parcel_id
        JOIN users u
            ON p.user_id = u.user_id
        ORDER BY py.payment_date DESC
    """)

    payments = cursor.fetchall()
    cursor.close()

    return render_template(
        "Admin/admin_payments.html",
        payments=payments
    )

@app.route("/admin/update-payment/<int:payment_id>", methods=["POST"])
def update_payment(payment_id):

    if "admin_id" not in session:
        return redirect(url_for("admin_login"))

    status = request.form.get("status")

    if status not in ["pending", "paid", "failed"]:
        flash("Invalid payment status.", "danger")
        return redirect(url_for("admin_payments"))

    cursor = db.cursor()

    try:
        cursor.execute("""
            UPDATE payment
            SET status = %s
            WHERE payment_id = %s
        """, (status, payment_id))

        db.commit()

        flash("Payment status updated.", "success")

    except mysql.connector.Error:
        db.rollback()
        flash("Unable to update payment status.", "danger")

    finally:
        cursor.close()

    return redirect(url_for("admin_payments"))
@app.route("/admin-logout")
def admin_logout():
    session.pop("admin_id", None)
    session.pop("admin_name", None)

    return redirect(url_for("admin_login"))
if __name__ == "__main__":
    app.run(debug=True)