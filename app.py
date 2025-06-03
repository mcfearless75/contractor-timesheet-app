import re
from flask import (
    Flask, render_template, redirect, url_for,
    request, flash
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user,
    login_required, logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'change-this-in-prod!')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'sqlite:///timesheets.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ─── SET UP FLASK-LOGIN ────────────────────────────────────────────────
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ─── USER MODEL ─────────────────────────────────────────────────────────
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), default='contractor')

    timesheets = db.relationship('Timesheet', backref='contractor', lazy=True)

    def set_password(self, plaintext_password):
        self.password_hash = generate_password_hash(plaintext_password)

    def check_password(self, plaintext_password):
        return check_password_hash(self.password_hash, plaintext_password)

    def __repr__(self):
        return f'<User {self.username}>'


# ─── TIMESHEET MODEL ────────────────────────────────────────────────────
class Timesheet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    client = db.Column(db.String(100), nullable=False)
    site_address = db.Column(db.String(200), nullable=False)
    week_start = db.Column(db.Date, nullable=False)
    week_end = db.Column(db.Date, nullable=False)
    basic_hours = db.Column(db.Float, nullable=False)
    saturday_hours = db.Column(db.Float, nullable=False)
    sunday_hours = db.Column(db.Float, nullable=False)
    hourly_rate = db.Column(db.Float, nullable=False)
    total_hours = db.Column(db.Float, nullable=False)
    calculated_pay = db.Column(db.Float, nullable=False)
    approved = db.Column(db.Boolean, default=False)
    submitted_on = db.Column(db.DateTime, default=datetime.utcnow)
    approved_on = db.Column(db.DateTime, nullable=True)

    def __repr__(self):
        return (f'<Timesheet {self.contractor.username} '
                f'({self.week_start}–{self.week_end})>')


# ─── USER LOADER ─────────────────────────────────────────────────────────
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ─── INITIALIZE DATABASE ─────────────────────────────────────────────────
with app.app_context():
    db.create_all()


# ─── EMAIL VALIDATION REGEX ───────────────────────────────────────────────
EMAIL_REGEX = re.compile(r'^[^@]+@[^@]+\.[^@]+$')


# ─── REGISTRATION ─────────────────────────────────────────────────────────
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('submit_timesheet'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        # 1) Basic presence checks
        if not username or not email or not password or not confirm:
            flash('All fields are required.', 'danger')
            return render_template('register.html')

        # 2) Password confirmation
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return render_template('register.html')

        # 3) Email format validation
        if not EMAIL_REGEX.match(email):
            flash('Please enter a valid email address.', 'danger')
            return render_template('register.html')

        # 4) Check uniqueness of username/email
        existing_user = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()
        if existing_user:
            flash('Username or email already taken.', 'danger')
            return render_template('register.html')

        # 5) Create and save the user
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


# ─── LOGIN ──────────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('submit_timesheet'))

    if request.method == 'POST':
        username_or_email = request.form.get('username_or_email', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter(
            (User.username == username_or_email) | (User.email == username_or_email)
        ).first()

        if user and user.check_password(password):
            login_user(user)
            flash(f'Welcome back, {user.username}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('submit_timesheet'))
        else:
            flash('Invalid credentials. Please try again.', 'danger')
            return render_template('login.html')

    return render_template('login.html')


# ─── LOGOUT ─────────────────────────────────────────────────────────────────
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# ─── SUBMIT TIMESHEET (CONTRACTOR ONLY) ────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
@login_required
def submit_timesheet():
    # Only contractors (not managers) should see the submit form
    if current_user.role != 'contractor':
        flash('Only contractors can submit timesheets.', 'warning')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        client = request.form.get('client')
        site_address = request.form.get('site_address')
        week_start = datetime.strptime(request.form.get('week_start'), '%Y-%m-%d').date()

        # Parse hours
        monday = float(request.form.get('monday') or 0)
        tuesday = float(request.form.get('tuesday') or 0)
        wednesday = float(request.form.get('wednesday') or 0)
        thursday = float(request.form.get('thursday') or 0)
        friday = float(request.form.get('friday') or 0)
        saturday = float(request.form.get('saturday_hours') or 0)
        sunday = float(request.form.get('sunday_hours') or 0)
        rate = float(request.form.get('hourly_rate') or 0)

        basic = monday + tuesday + wednesday + thursday + friday
        total = basic + saturday + sunday
        pay = (basic * rate) + (saturday * rate * 1.5) + (sunday * rate * 1.75)

        ts = Timesheet(
            user_id=current_user.id,
            client=client,
            site_address=site_address,
            week_start=week_start,
            week_end=week_start + timedelta(days=6),
            basic_hours=basic,
            saturday_hours=saturday,
            sunday_hours=sunday,
            hourly_rate=rate,
            total_hours=total,
            calculated_pay=pay,
            approved=False,
            submitted_on=datetime.utcnow()
        )
        db.session.add(ts)
        db.session.commit()

        return render_template('thank_you.html')

    return render_template('submit.html')


# ─── DASHBOARD (MANAGER ONLY) ───────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'manager':
        flash('Access denied. Managers only.', 'warning')
        return redirect(url_for('submit_timesheet'))

    pending = Timesheet.query.filter_by(approved=False).all()
    return render_template('dashboard.html', timesheets=pending)


@app.route('/approve/<int:ts_id>')
@login_required
def approve(ts_id):
    if current_user.role != 'manager':
        flash('Access denied. Managers only.', 'warning')
        return redirect(url_for('submit_timesheet'))

    ts = Timesheet.query.get_or_404(ts_id)
    ts.approved = True
    ts.approved_on = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('dashboard'))


# ─── EXPORT EXCEL (MANAGER ONLY) ───────────────────────────────────────────
@app.route('/export')
@login_required
def export_excel():
    if current_user.role != 'manager':
        flash('Access denied. Managers only.', 'warning')
        return redirect(url_for('submit_timesheet'))

    approved = Timesheet.query.filter_by(approved=True).all()

    # ... (existing export logic unchanged) ...

    # If no approved rows, return empty template, etc.
    if not approved:
        timesheet_columns = [
            'Name', 'Client', 'Site Address',
            'Basic Hours', 'Sat Hours (1.5×)', 'Sun Hours (1.75×)',
            'Total Hours', 'Rate (£)', 'Calculated Pay (£)',
            'Date Range', 'File Name', 'Extracted On'
        ]
        summary_columns = [
            'Name',
            'Basic Hrs for Accounts',
            'Total Overtime 1.5 Hrs for Accounts',
            'Overtime 1.75 Hrs for Accounts'
        ]
        df_empty_main = pd.DataFrame(columns=timesheet_columns)
        df_empty_summary = pd.DataFrame(columns=summary_columns)

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_empty_main.to_excel(writer, index=False, sheet_name='Timesheets')
            df_empty_summary.to_excel(writer, index=False, sheet_name='Accounts Summary')
        output.seek(0)
        return send_file(
            output,
            download_name="approved_timesheets.xlsx",
            as_attachment=True
        )

    # Build DataFrames for approved timesheets and summary...
    # (same as before)

    rows = []
    for t in approved:
        rows.append({
            'Name': t.contractor.username,
            'Client': t.client,
            'Site Address': t.site_address,
            'Basic Hours': t.basic_hours,
            'Sat Hours (1.5×)': t.saturday_hours,
            'Sun Hours (1.75×)': t.sunday_hours,
            'Total Hours': t.total_hours,
            'Rate (£)': t.hourly_rate,
            'Calculated Pay (£)': t.calculated_pay,
            'Date Range': f"{t.week_start.strftime('%d/%m/%Y')}–{t.week_end.strftime('%d/%m/%Y')}",
            'File Name': "approved_timesheets.xlsx",
            'Extracted On': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        })

    df_timesheets = pd.DataFrame(rows)

    df_for_summary = pd.DataFrame([{
        'Name': t.contractor.username,
        'Basic Hrs for Accounts': t.basic_hours,
        'Total Overtime 1.5 Hrs for Accounts': t.saturday_hours,
        'Overtime 1.75 Hrs for Accounts': t.sunday_hours
    } for t in approved])
    df_summary = df_for_summary.groupby('Name', as_index=False).sum()

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_timesheets.to_excel(writer, index=False, sheet_name='Timesheets')
        df_summary.to_excel(writer, index=False, sheet_name='Accounts Summary')
    output.seek(0)

    return send_file(
        output,
        download_name="approved_timesheets.xlsx",
        as_attachment=True
    )


# ─── RUN LOCALLY ─────────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True)
