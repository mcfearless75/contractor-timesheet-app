import os
from flask import Flask, render_template, request, redirect, send_file, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import pandas as pd
import io

app = Flask(__name__)

# Use DATABASE_URL from environment (Render) or fall back to local SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///timesheets.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# -----------------------
# 1) Define the database model
# -----------------------
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

# -----------------------
# 2) Routes: Home / Submit Form
# -----------------------
@app.route('/', methods=['GET', 'POST'])
def submit_timesheet():
    if request.method == 'POST':
        # Grab form data
        name = request.form.get('contractor_name')
        client = request.form.get('client')
        site = request.form.get('site_address')

        # week_start as a date, must be a Monday (frontend JS warns if not)
        week_start = datetime.strptime(request.form.get('week_start'), '%Y-%m-%d').date()
        # week_end = week_start + 6 days
        week_end = week_start + timedelta(days=6)

        # Individual weekday hours (Mon–Fri)
        monday    = float(request.form.get('monday')    or 0)
        tuesday   = float(request.form.get('tuesday')   or 0)
        wednesday = float(request.form.get('wednesday') or 0)
        thursday  = float(request.form.get('thursday')  or 0)
        friday    = float(request.form.get('friday')    or 0)

        # Aggregate basic_hours
        basic = monday + tuesday + wednesday + thursday + friday

        # Weekend hours
        sat = float(request.form.get('saturday_hours') or 0)
        sun = float(request.form.get('sunday_hours')   or 0)

        # Hourly rate
        rate = float(request.form.get('hourly_rate') or 0)

        # Compute totals
        total = basic + sat + sun
        pay = (basic * rate) + (sat * rate * 1.5) + (sun * rate * 1.75)

        # Create a new Timesheet record
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

    return render_template('submit.html')

# -----------------------
# 3) Simple Thank-You Page
# -----------------------
@app.route('/thankyou')
def thank_you():
    return "<h2>Thanks! Your timesheet was submitted for approval. 😊</h2>"

# -----------------------
# 4) Manager Dashboard: View Pending & Approve
# -----------------------
@app.route('/dashboard')
def dashboard():
    pending = Timesheet.query.filter_by(approved=False).all()
    return render_template('dashboard.html', timesheets=pending)

@app.route('/approve/<int:ts_id>')
def approve(ts_id):
    ts = Timesheet.query.get_or_404(ts_id)
    ts.approved = True
    ts.approved_on = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('dashboard'))

# -----------------------
# 5) Export All Approved as Excel
# -----------------------
@app.route('/export')
def export_excel():
    approved = Timesheet.query.filter_by(approved=True).all()

    # Build a list of dicts for pandas
    data = []
    for t in approved:
        data.append({
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
            'Approved On': t.approved_on.strftime('%d/%m/%Y %H:%M'),
        })

    df = pd.DataFrame(data)
    # Use an in-memory buffer to avoid writing to disk
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Approved Timesheets')
    output.seek(0)

    return send_file(
        output,
        download_name="approved_timesheets.xlsx",
        as_attachment=True
    )

# -----------------------
# 6) Run the Flask app (and create DB if it doesn’t exist)
# -----------------------
if __name__ == '__main__':
    # Ensure the tables are created before first request
    with app.app_context():
        db.create_all()

    # Start Flask’s development server
    app.run(debug=True)
