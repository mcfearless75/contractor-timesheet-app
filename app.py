from flask import Flask, render_template, request, redirect, send_file, url_for, session, flash, abort
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import pandas as pd
import io
import os

app = Flask(__name__)

# ── SECRET KEY FOR SESSIONS ───────────────────────────────────────────────────
# Change this to something random in production
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev_secret_key_please_change')

# ── DATABASE CONFIG ────────────────────────────────────────────────────────────
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///timesheets.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ── YOUR TIMSHEET MODEL ───────────────────────────────────────────────────────
class Timesheet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contractor_name = db.Column(db.String(100), nullable=False)
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
        return f'<Timesheet {self.contractor_name} ({self.week_start} to {self.week_end})>'

with app.app_context():
    db.create_all()

# ── SIMPLE LOGIN CONFIG ────────────────────────────────────────────────────────
MANAGER_USERNAME = "admin"
MANAGER_PASSWORD = "letmein123"   # <– Change this to a strong password in production

# ── ROUTE: LOGIN ───────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        if username == MANAGER_USERNAME and password == MANAGER_PASSWORD:
            session['is_manager'] = True
            flash("Logged in successfully.", "success")
            # Redirect to dashboard after successful login
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials. Try again.", "danger")
            return redirect(url_for('login'))
    return render_template('login.html')

# ── ROUTE: LOGOUT ──────────────────────────────────────────────────────────────
@app.route('/logout')
def logout():
    session.pop('is_manager', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('submit_timesheet'))

# ── ROUTE: HOME / SUBMIT TIMESHEET ─────────────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
def submit_timesheet():
    if request.method == 'POST':
        try:
            # 1) Grab & validate form data
            name = request.form.get('contractor_name')
            client = request.form.get('client')
            site = request.form.get('site_address')

            if not name or not client or not site:
                raise ValueError("Name, client, and site address are all required.")

            ws_str = request.form.get('week_start')
            if not ws_str:
                raise ValueError("Week start date is missing.")
            week_start = datetime.strptime(ws_str, '%Y-%m-%d').date()
            week_end   = week_start + timedelta(days=6)

            # 2) Weekday hours
            monday    = float(request.form.get('monday') or 0)
            tuesday   = float(request.form.get('tuesday') or 0)
            wednesday = float(request.form.get('wednesday') or 0)
            thursday  = float(request.form.get('thursday') or 0)
            friday    = float(request.form.get('friday') or 0)
            basic     = monday + tuesday + wednesday + thursday + friday

            # 3) Weekend hours
            sat = float(request.form.get('saturday_hours') or 0)
            sun = float(request.form.get('sunday_hours') or 0)

            # 4) Rate
            rate = float(request.form.get('hourly_rate') or 0)
            if rate <= 0:
                raise ValueError("Hourly rate must be greater than £0.")

            # 5) Totals
            total = basic + sat + sun
            pay   = (basic * rate) + (sat * rate * 1.5) + (sun * rate * 1.75)

            # 6) Save to DB
            ts = Timesheet(
                contractor_name=name,
                client=client,
                site_address=site,
                week_start=week_start,
                week_end=week_end,
                basic_hours=basic,
                saturday_hours=sat,
                sunday_hours=sun,
                hourly_rate=rate,
                total_hours=total,
                calculated_pay=pay,
                approved=False
            )
            db.session.add(ts)
            db.session.commit()
            return redirect(url_for('thank_you'))

        except Exception as err:
            app.logger.error(f"Error processing form: {err}", exc_info=True)
            return f"<h2>Oops! {err}</h2><p>Please go back and fix the form.</p>", 400

    return render_template('submit.html')

# ── ROUTE: THANK YOU ───────────────────────────────────────────────────────────
@app.route('/thankyou')
def thank_you():
    return """
      <div class="alert alert-success text-center mt-5" style="max-width:400px; margin:auto;">
        <h4>Thanks! Your timesheet was submitted for approval. 😊</h4>
        <p><a href="{}">Go back to Home</a></p>
      </div>
    """.format(url_for('submit_timesheet'))

# ── ROUTE: MANAGER DASHBOARD (PROTECTED) ────────────────────────────────────────
@app.route('/dashboard')
def dashboard():
    # If not logged in as manager, show 403 or redirect to login
    if not session.get('is_manager'):
        abort(403)   # or: return redirect(url_for('login'))

    pending = Timesheet.query.filter_by(approved=False).all()
    return render_template('dashboard.html', timesheets=pending)

# ── ROUTE: APPROVE TIMESHEET (PROTECTED) ────────────────────────────────────────
@app.route('/approve/<int:ts_id>')
def approve(ts_id):
    if not session.get('is_manager'):
        abort(403)

    ts = Timesheet.query.get_or_404(ts_id)
    ts.approved = True
    ts.approved_on = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('dashboard'))

# ── ROUTE: EXPORT EXCEL (PROTECTED) ────────────────────────────────────────────
@app.route('/export')
def export_excel():
    if not session.get('is_manager'):
        abort(403)

    approved = Timesheet.query.filter_by(approved=True).all()
    # … [existing export logic from earlier] …
    # (You can copy the two‐sheet code here or keep it as is.)
    # For brevity, I’ll include a simplified single‐sheet fallback:
    rows = []
    for t in approved:
        rows.append({
            'Name': t.contractor_name,
            'Client': t.client,
            'Site Address': t.site_address,
            'Basic Hours': t.basic_hours,
            'Sat Hours (1.5×)': t.saturday_hours,
            'Sun Hours (1.75×)': t.sunday_hours,
            'Total Hours': t.total_hours,
            'Rate (£)': t.hourly_rate,
            'Calculated Pay (£)': t.calculated_pay,
            'Date Range': f"{t.week_start.strftime('%d/%m/%Y')}–{t.week_end.strftime('%d/%m/%Y')}",
            'Extracted On': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        })
    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Approved Timesheets')
    output.seek(0)
    return send_file(
        output,
        download_name="approved_timesheets.xlsx",
        as_attachment=True
    )

# ── RUN THE FLASK APP ───────────────────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True)
