from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import random
import string

# ------------------------------------------------
# FLASK APP & DATABASE CONFIG
# ------------------------------------------------
app = Flask(__name__)

app.config["SECRET_KEY"] = "super-secret-hackathon-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///hackathon.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ------------------------------------------------
# HACKATHON END TIME (for countdown)
# ------------------------------------------------
# TODO: change this to your real hackathon end date/time
HACKATHON_END = datetime(2025, 1, 19, 9, 0, 0)  # year, month, day, hour, minute


@app.context_processor
def inject_hackathon_time():
    """
    This makes {{ hackathon_end_iso }} available
    in ALL templates (index, dashboard, etc.).
    """
    return {"hackathon_end_iso": HACKATHON_END.isoformat()}


# ------------------------------------------------
# DATABASE MODELS
# ------------------------------------------------
class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_name = db.Column(db.String(100), nullable=False)
    invite_code = db.Column(db.String(10), unique=True, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("user.id"))

    # relationship to User.team_id
    members = db.relationship(
        "User",
        backref="team",
        lazy=True,
        foreign_keys="User.team_id",
    )


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    college = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    team_id = db.Column(db.Integer, db.ForeignKey("team.id"))

    submissions = db.relationship("Submission", backref="user", lazy=True)
    feedbacks = db.relationship("Feedback", backref="user", lazy=True)


class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    github = db.Column(db.String(255), nullable=False)
    video = db.Column(db.String(255), nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)


class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    rating = db.Column(db.String(10), nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))


class Sponsor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    tier = db.Column(db.String(50), nullable=False)
    link = db.Column(db.String(255))


class LiveUpdate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(255), nullable=False)


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(255), nullable=False)


# ------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------
def generate_invite_code():
    """Generate a random 6-char invite code."""
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choice(chars) for _ in range(6))


def get_current_user():
    """Return logged-in user object or None."""
    if "user_id" in session:
        return User.query.get(session["user_id"])
    return None


def seed_sponsors():
    """Insert some default sponsors if table is empty."""
    if Sponsor.query.count() == 0:
        sponsors = [
            Sponsor(name="Alpha Tech Solutions", tier="Gold", link="https://example.com"),
            Sponsor(name="Beta Cloud Services", tier="Silver", link="https://example.com"),
            Sponsor(name="CodeCraft Academy", tier="Bronze", link="https://example.com"),
        ]
        db.session.add_all(sponsors)
        db.session.commit()


def require_admin():
    """Check if admin is logged in."""
    if not session.get("is_admin"):
        flash("Admin access required.", "error")
        return False
    return True


# ------------------------------------------------
# PUBLIC ROUTES
# ------------------------------------------------

@app.route("/")
def home():
    """
    Landing page:
    - Shows countdown (via hackathon_end_iso from context processor)
    - Shows live snapshot (participants, teams, submissions)
    - Shows mini top-3 leaderboard preview
    """
    total_users = User.query.count()
    total_teams = Team.query.count()
    total_submissions = Submission.query.count()

    # Top 3 earliest submissions
    top_submissions = Submission.query.order_by(Submission.id.asc()).limit(3).all()

    return render_template(
        "index.html",
        total_users=total_users,
        total_teams=total_teams,
        total_submissions=total_submissions,
        top_submissions=top_submissions,
    )


# ---------- REGISTER ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        college = request.form.get("college")
        password = request.form.get("password")
        team_choice = request.form.get("teamChoice")  # "create" or "join"
        team_name = request.form.get("teamName")
        invite_code = request.form.get("inviteCode")

        # Check if email is already used
        if User.query.filter_by(email=email).first():
            flash("Email already registered. Please login.", "error")
            return redirect(url_for("login"))

        # Create user
        password_hash = generate_password_hash(password)
        user = User(
            name=name,
            email=email,
            phone=phone,
            college=college,
            password_hash=password_hash,
        )

        # Handle team logic
        if team_choice == "create":
            # Auto fallback name if blank
            if not team_name:
                team_name = f"Team-{name.split()[0]}"

            code = generate_invite_code()
            # Ensure unique invite code
            while Team.query.filter_by(invite_code=code).first():
                code = generate_invite_code()

            new_team = Team(team_name=team_name, invite_code=code)
            db.session.add(new_team)
            db.session.flush()  # give new_team.id without committing

            user.team_id = new_team.id

        elif team_choice == "join":
            team = Team.query.filter_by(invite_code=invite_code).first()
            if not team:
                flash("Invalid invite code!", "error")
                return redirect(url_for("register"))
            user.team_id = team.id

        db.session.add(user)
        db.session.commit()

        flash("Registration successful. Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


# ---------- LOGIN ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            flash("Logged in successfully!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password.", "error")

    return render_template("login.html")


# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("home"))


# ---------- DASHBOARD ----------
@app.route("/dashboard")
def dashboard():
    user = get_current_user()
    if not user:
        flash("Please login to access dashboard.", "error")
        return redirect(url_for("login"))

    team = user.team
    team_members = User.query.filter_by(team_id=team.id).all() if team else []
    submission = Submission.query.filter_by(user_id=user.id).first()

    seed_sponsors()
    sponsors = Sponsor.query.all()

    live_updates = LiveUpdate.query.order_by(LiveUpdate.id.desc()).all()
    notifications = Notification.query.order_by(Notification.id.desc()).all()

    return render_template(
        "dashboard.html",
        user=user,
        team=team,
        team_members=team_members,
        submission=submission,
        sponsors=sponsors,
        live_updates=live_updates,
        notifications=notifications,
    )


# ---------- SUBMISSION ----------
@app.route("/submit", methods=["GET", "POST"])
def submit():
    user = get_current_user()
    if not user:
        flash("Please login to submit.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        title = request.form.get("title")
        desc = request.form.get("desc")
        github = request.form.get("github")
        video = request.form.get("video")

        sub = Submission.query.filter_by(user_id=user.id).first()

        if not sub:
            sub = Submission(
                title=title,
                description=desc,
                github=github,
                video=video,
                user_id=user.id,
            )
            db.session.add(sub)
        else:
            sub.title = title
            sub.description = desc
            sub.github = github
            sub.video = video

        db.session.commit()
        flash("Submission saved!", "success")
        return redirect(url_for("dashboard"))

    return render_template("submit.html")


# ---------- FEEDBACK ----------
@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    user = get_current_user()

    if request.method == "POST":
        if not user:
            flash("Login required to give feedback.", "error")
            return redirect(url_for("login"))

        text = request.form.get("text")
        rating = request.form.get("rating")

        fb = Feedback(text=text, rating=rating, user_id=user.id)
        db.session.add(fb)
        db.session.commit()
        flash("Thank you for your feedback!", "success")
        return redirect(url_for("feedback"))

    # If user logged in, show only their feedbacks
    feedbacks = []
    if user:
        feedbacks = Feedback.query.filter_by(
            user_id=user.id).order_by(Feedback.id.desc()).all()

    return render_template("feedback.html", feedbacks=feedbacks)


# ---------- SPONSORS ----------
@app.route("/sponsors")
def sponsors_page():
    seed_sponsors()
    sponsors = Sponsor.query.all()
    return render_template("sponsors.html", sponsors=sponsors)


# ---------- FAQ ----------
@app.route("/faq")
def faq():
    return render_template("faq.html")


# ---------- LEADERBOARD ----------
@app.route("/leaderboard")
def leaderboard():
    """
    Simple leaderboard:
    - Rank by earliest submission (smallest id first)
    """
    submissions = Submission.query.order_by(Submission.id.asc()).all()
    return render_template("leaderboard.html", submissions=submissions)


# ------------------------------------------------
# ADMIN ROUTES
# ------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    # Hard-coded admin credentials
    ADMIN_EMAIL = "admin@hackathon.com"
    ADMIN_PASSWORD = "admin123"

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("Admin login successful!", "success")
            return redirect(url_for("admin_dashboard"))
        else:
            flash("Invalid admin credentials.", "error")

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    flash("Admin logged out.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin/dashboard")
def admin_dashboard():
    if not require_admin():
        return redirect(url_for("admin_login"))

    updates = LiveUpdate.query.order_by(LiveUpdate.id.desc()).all()
    notifications = Notification.query.order_by(Notification.id.desc()).all()

    return render_template(
        "admin_dashboard.html",
        updates=updates,
        notifications=notifications,
    )


@app.route("/admin/add_update", methods=["POST"])
def admin_add_update():
    if not require_admin():
        return redirect(url_for("admin_login"))

    text = request.form.get("text")
    if text:
        db.session.add(LiveUpdate(text=text))
        db.session.commit()

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/add_notification", methods=["POST"])
def admin_add_notification():
    if not require_admin():
        return redirect(url_for("admin_login"))

    text = request.form.get("text")
    if text:
        db.session.add(Notification(text=text))
        db.session.commit()

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete_update/<int:id>")
def admin_delete_update(id):
    if not require_admin():
        return redirect(url_for("admin_login"))

    item = LiveUpdate.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete_notification/<int:id>")
def admin_delete_notification(id):
    if not require_admin():
        return redirect(url_for("admin_login"))

    item = Notification.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()

    return redirect(url_for("admin_dashboard"))


@app.route("/admin/teams")
def admin_teams():
    if not require_admin():
        return redirect(url_for("admin_login"))

    teams = Team.query.all()
    return render_template("admin_teams.html", teams=teams)


# ------------------------------------------------
# MAIN ENTRY
# ------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # create tables if not exist
    app.run(debug=True)
