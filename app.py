
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from io import BytesIO
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font, Alignment

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///timesheets.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='contractor')
    security_answer = db.Column(db.String(120), nullable=True)  # for password reset

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

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if user:
            return redirect(url_for('reset_password', user_id=user.id))
        flash('No account found with that email.', 'danger')
    return render_template('forgot_password.html')

@app.route('/reset-password/<int:user_id>', methods=['GET', 'POST'])
def reset_password(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        answer = request.form['security_answer']
        new_password = request.form['new_password']
        if answer.strip().lower() == user.security_answer.strip().lower():
            user.password = generate_password_hash(new_password)
            db.session.commit()
            flash('Password reset successful. You can now log in.', 'success')
            return redirect(url_for('login'))
        flash('Incorrect security answer.', 'danger')
    return render_template('reset_password.html', user=user)

# Additional routes like register, login, logout, submit, etc. would be here...

if __name__ == '__main__':
    app.run(debug=True)
