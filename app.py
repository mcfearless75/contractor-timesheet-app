# app.py
import os
from datetime import datetime, timedelta
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, Alignment

# Config
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'devkey')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///timesheets.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(50), default='contractor')

class Timesheet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contractor_name = db.Column(db.String(100))
    client = db.Column(db.String(100))
    site_address = db.Column(db.String(200))
    week_start = db.Column(db.Date)
    week_end = db.Column(db.Date)
    basic_hours = db.Column(db.Float)
    saturday_hours = db.Column(db.Float)
    sunday_hours = db.Column(db.Float)
    hourly_rate = db.Column(db.Float)
    total_hours = db.Column(db.Float)
    calculated_pay = db.Column(db.Float)
    approved = db.Column(db.Boolean, default=False)
    submitted_on = db.Column(db.DateTime, default=datetime.utcnow)
    approved_on = db.Column(db.DateTime, nullable=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
@login_required
def submit_timesheet():
    if current_user.role != 'contractor':
        abort(403)
    return render_template('submit.html')

@app.route('/', methods=['POST'])
@login_required
def handle_submission():
    if current_user.role != 'contractor':
        abort(403)

    data = request.form
    week_start = datetime.strptime(data['week_start'], '%Y-%m-%d').date()
    week_end = week_start + timedelta(days=6)
    basic = float(data['basic_hours'])
    sat = float(data['saturday_hours'])
    sun = float(data['sunday_hours'])
    rate = float(data['hourly_rate'])

    # Calculate pay
    total_hours = basic + sat + sun
    pay = (basic * rate) + (sat * rate * 1.5) + (sun * rate * 1.75)

    ts = Timesheet(
        contractor_name=data['contractor_name'],
        client=data['client'],
        site_address=data['site_address'],
        week_start=week_start,
        week_end=week_end,
        basic_hours=basic,
        saturday_hours=sat,
        sunday_hours=sun,
        hourly_rate=rate,
        total_hours=total_hours,
        calculated_pay=pay,
        approved=False,
        submitted_on=datetime.utcnow()
    )
    db.session.add(ts)
    db.session.commit()
    return render_template('thank_you.html')

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role != 'manager':
        abort(403)
    sheets = Timesheet.query.order_by(Timesheet.submitted_on.desc()).all()
    return render_template('dashboard.html', sheets=sheets)

@app.route('/approve/<int:sheet_id>')
@login_required
def approve_timesheet(sheet_id):
    if current_user.role != 'manager':
        abort(403)
    ts = Timesheet.query.get_or_404(sheet_id)
    ts.approved = True
    ts.approved_on = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/export')
@login_required
def export_timesheets():
    if current_user.role != 'manager':
        abort(403)

    submissions = Timesheet.query.filter_by(approved=True).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "Approved Timesheets"

    headers = [
        "Contractor", "Client", "Site", "Week Start", "Week End",
        "Basic Hours", "Saturday Hours", "Sunday Hours",
        "Hourly Rate", "Total Hours", "Calculated Pay", "Submitted On"
    ]
    ws.append(headers)

    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal='center')

    for ts in submissions:
        ws.append([
            ts.contractor_name,
            ts.client,
            ts.site_address,
            ts.week_start.strftime('%Y-%m-%d'),
            ts.week_end.strftime('%Y-%m-%d'),
            ts.basic_hours,
            ts.saturday_hours,
            ts.sunday_hours,
            ts.hourly_rate,
            ts.total_hours,
            ts.calculated_pay,
            ts.submitted_on.strftime('%Y-%m-%d %H:%M')
        ])

    for column in ws.columns:
        max_length = 0
        column_letter = get_column_letter(column[0].column)
        for cell in column:
            if cell.value:
                max_length = max(max_length, len(str(cell.value)))
        ws.column_dimensions[column_letter].width = max_length + 2

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return send_file(output, download_name='Approved_Timesheets.xlsx', as_attachment=True)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            login_user(user)
            return redirect(url_for('submit_timesheet'))
        flash('Invalid username or password', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        if not email or '@' not in email:
            flash('Invalid email address.', 'danger')
            return redirect(url_for('register'))

        hashed_pw = generate_password_hash(request.form['password'])
        user = User(
            username=request.form['username'],
            email=email,
            password=hashed_pw
        )
        db.session.add(user)
        db.session.commit()
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
