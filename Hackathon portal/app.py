from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import random
import string

app = Flask(__name__)

# ---------------- CONFIG ----------------
app.config['SECRET_KEY'] = 'super-secret-hackathon-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///hackathon.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ---------------- MODELS ----------------

class Team(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    team_name = db.Column(db.String(100), nullable=False)
    invite_code = db.Column(db.String(10), unique=True, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))

    members = db.relationship(
        "User",
        backref="team",
        lazy=True,
        foreign_keys="User.team_id"
    )


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    college = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    team_id = db.Column(db.Integer, db.ForeignKey('team.id'))

    submissions = db.relationship('Submission', backref='user', lazy=True)
    feedbacks = db.relationship('Feedback', backref='user', lazy=True)


class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    github = db.Column(db.String(255), nullable=False)
    video = db.Column(db.String(255), nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    rating = db.Column(db.String(10), nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))


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


# ---------------- HELPERS ----------------

def generate_invite_code():
    return ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))


def get_user():
    if "user_id" in session:
        return User.query.get(session["user_id"])
    return None


def seed_sponsors():
    if Sponsor.query.count() == 0:
        sponsors = [
            Sponsor(name="Alpha Tech Solutions", tier="Gold", link="https://example.com"),
            Sponsor(name="Beta Cloud Services", tier="Silver", link="https://example.com"),
            Sponsor(name="CodeCraft Academy", tier="Bronze", link="https://example.com"),
        ]
        db.session.add_all(sponsors)
        db.session.commit()


def require_admin():
    if not session.get("is_admin"):
        flash("Admin access required.", "error")
        return False
    return True


# ---------------- ROUTES ----------------

@app.route("/")
def home():
    return render_template("index.html")


# ---------- REGISTER ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        name = request.form.get("name")
        email = request.form.get("email")
        phone = request.form.get("phone")
        college = request.form.get("college")
        password = request.form.get("password")
        team_choice = request.form.get("teamChoice")
        team_name = request.form.get("teamName")
        invite_input = request.form.get("inviteCode")

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            return redirect(url_for("login"))

        hashed = generate_password_hash(password)
        new_user = User(name=name, email=email, phone=phone,
                        college=college, password_hash=hashed)

        if team_choice == "create":
            if not team_name:
                team_name = f"Team-{name.split()[0]}"
            inv = generate_invite_code()
            while Team.query.filter_by(invite_code=inv).first():
                inv = generate_invite_code()

            team = Team(team_name=team_name, invite_code=inv)
            db.session.add(team)
            db.session.flush()

            new_user.team_id = team.id

        elif team_choice == "join":
            team = Team.query.filter_by(invite_code=invite_input).first()
            if not team:
                flash("Invalid invite code!", "error")
                return redirect(url_for("register"))
            new_user.team_id = team.id

        db.session.add(new_user)
        db.session.commit()

        flash("Registration successful.", "success")
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
            flash("Logged in!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid credentials!", "error")

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
    user = get_user()
    if not user:
        flash("Login required.", "error")
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
        notifications=notifications
    )


# ---------- SUBMISSION ----------
@app.route("/submit", methods=["GET", "POST"])
def submit():
    user = get_user()
    if not user:
        flash("Login required.", "error")
        return redirect(url_for("login"))

    if request.method == "POST":
        sub = Submission.query.filter_by(user_id=user.id).first()

        if not sub:
            sub = Submission(
                title=request.form.get("title"),
                description=request.form.get("desc"),
                github=request.form.get("github"),
                video=request.form.get("video"),
                user_id=user.id
            )
            db.session.add(sub)
        else:
            sub.title = request.form.get("title")
            sub.description = request.form.get("desc")
            sub.github = request.form.get("github")
            sub.video = request.form.get("video")

        db.session.commit()
        flash("Submission saved!", "success")
        return redirect(url_for("dashboard"))

    return render_template("submit.html")


# ---------- FEEDBACK ----------
@app.route("/feedback", methods=["GET", "POST"])
def feedback():
    user = get_user()
    if not user:
        return render_template("feedback.html", feedbacks=[])

    if request.method == "POST":
        fb = Feedback(
            text=request.form.get("text"),
            rating=request.form.get("rating"),
            user_id=user.id
        )
        db.session.add(fb)
        db.session.commit()

        flash("Feedback submitted!", "success")
        return redirect(url_for("feedback"))

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


# ---------------- ADMIN SYSTEM ----------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    ADMIN_EMAIL = "admin@hackathon.com"
    ADMIN_PASSWORD = "admin123"

    if request.method == "POST":
        if request.form.get("email") == ADMIN_EMAIL and request.form.get("password") == ADMIN_PASSWORD:
            session["is_admin"] = True
            flash("Admin login successful!", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials!", "error")

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

    return render_template(
        "admin_dashboard.html",
        updates=LiveUpdate.query.all(),
        notifications=Notification.query.all()
    )


@app.route("/admin/add_update", methods=["POST"])
def admin_add_update():
    if not require_admin(): return redirect(url_for("admin_login"))
    db.session.add(LiveUpdate(text=request.form.get("text")))
    db.session.commit()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/add_notification", methods=["POST"])
def admin_add_notification():
    if not require_admin(): return redirect(url_for("admin_login"))
    db.session.add(Notification(text=request.form.get("text")))
    db.session.commit()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete_update/<int:id>")
def admin_delete_update(id):
    if not require_admin(): return redirect(url_for("admin_login"))
    db.session.delete(LiveUpdate.query.get(id))
    db.session.commit()
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/delete_notification/<int:id>")
def admin_delete_notification(id):
    if not require_admin(): return redirect(url_for("admin_login"))
    db.session.delete(Notification.query.get(id))
    db.session.commit()
    return redirect(url_for("admin_dashboard"))


# ---------- ADMIN: VIEW ALL TEAMS ----------
@app.route("/admin/teams")
def admin_teams():
    if not require_admin(): return redirect(url_for("admin_login"))
    return render_template("admin_teams.html", teams=Team.query.all())




# ---------- RUN ----------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
