from flask import Flask, render_template, request, redirect, send_file, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import pandas as pd
import io
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///timesheets.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

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

@app.route('/export')
def export_excel():
    # 1) Query all approved timesheets
    approved = Timesheet.query.filter_by(approved=True).all()

    if not approved:
        # If no approved rows, return an empty Excel with both sheets but no data
        # Build empty DataFrames with the correct columns for each sheet:
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

    # 2) Build the main "Timesheets" DataFrame
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
            'File Name': "approved_timesheets.xlsx",  # can be adjusted as needed
            'Extracted On': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        })

    df_timesheets = pd.DataFrame(rows)

    # 3) Build the "Accounts Summary" DataFrame by grouping
    #    Sum up basic_hours, saturday_hours (as 1.5× overtime), and sunday_hours (1.75×)
    df_for_summary = pd.DataFrame([{
        'Name': t.contractor_name,
        'Basic Hrs for Accounts': t.basic_hours,
        'Total Overtime 1.5 Hrs for Accounts': t.saturday_hours,
        'Overtime 1.75 Hrs for Accounts': t.sunday_hours
    } for t in approved])

    df_summary = df_for_summary.groupby('Name', as_index=False).sum()

    # 4) Write both DataFrames to an in-memory Excel file with two sheets
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # First sheet: full details
        df_timesheets.to_excel(writer, index=False, sheet_name='Timesheets')

        # Second sheet: accounts summary
        df_summary.to_excel(writer, index=False, sheet_name='Accounts Summary')

    output.seek(0)

    # 5) Send the file to the user
    return send_file(
        output,
        download_name="approved_timesheets.xlsx",
        as_attachment=True
    )
