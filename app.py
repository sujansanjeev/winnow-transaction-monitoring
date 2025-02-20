from flask import Flask, render_template, request, redirect, url_for, flash
import sqlite3
from datetime import datetime
import pandas as pd
import os

app = Flask(__name__)
app.secret_key = "transaction_monitoring_secret"

def init_db():
    conn = sqlite3.connect('transactions.db')
    cursor = conn.cursor()

  
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        serial_number INTEGER,
        registration_no TEXT NOT NULL,
        customer_name TEXT NOT NULL,
        transaction_type TEXT NOT NULL,
        product TEXT NOT NULL,
        amount REAL NOT NULL,
        upload_date DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS upload_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
        record_count INTEGER
    )
    ''')

    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        registration_no TEXT NOT NULL,
        customer_name TEXT NOT NULL,
        transaction_type TEXT NOT NULL,
        product TEXT NOT NULL,
        amount REAL NOT NULL,
        alert_reason TEXT NOT NULL,
        upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'Pending for review',
        slip_file TEXT
    )
    ''')

    
    cursor.execute("PRAGMA table_info(alerts)")
    columns = [col[1] for col in cursor.fetchall()]

    if "status" not in columns:
        cursor.execute("ALTER TABLE alerts ADD COLUMN status TEXT DEFAULT 'Pending Review'")
        conn.commit()

    conn.close()


init_db()

@app.route('/')
def index():
    conn = sqlite3.connect('transactions.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM transactions ORDER BY upload_date DESC")
    transactions = cursor.fetchall()

    cursor.execute("SELECT * FROM upload_history ORDER BY upload_date DESC LIMIT 1")
    last_upload = cursor.fetchone()

    cursor.execute("SELECT * FROM alerts ORDER BY upload_date DESC")
    alerts = [dict(row) for row in cursor.fetchall()]

    # Existing counts
    pending_alerts = len([a for a in alerts if a['status'] == 'Pending for review'])
    closed_alerts = len([a for a in alerts if a['status'] in [
        'Closed as not suspicious', 
        'Source of funds are genuine. Withdrawal slip from SBI bank verified.'
    ]])
    suspicious_activities = len([a for a in alerts if a['status'] == 'Closed as suspicious and STR/SAR reported'])
    under_investigation = len([a for a in alerts if a['status'] == 'Under Investigation'])

    # New rule breach counts (based on alert_reason)
    multiple_times_count = len([a for a in alerts if 'Multiple transactions (3 or more)' in a['alert_reason']])
    daily_exceed_count = len([a for a in alerts if 'exceeds 55,000' in a['alert_reason']])
    single_high_value_count = len([a for a in alerts if 'High-value transaction(s) of 55,000' in a['alert_reason']])

    conn.close()

    return render_template(
        'index.html',
        transactions=transactions,
        last_upload=last_upload,
        alerts=alerts,
        pending_alerts=pending_alerts,
        closed_alerts=closed_alerts,
        suspicious_activities=suspicious_activities,
        under_investigation=under_investigation,
        multiple_times_count=multiple_times_count,
        daily_exceed_count=daily_exceed_count,
        single_high_value_count=single_high_value_count
    )


@app.route('/upload', methods=['GET', 'POST'])
def upload_excel():
    if request.method == 'POST':
        if 'excel_file' not in request.files:
            flash('No file part', 'error')
            return redirect(request.url)

        file = request.files['excel_file']
        if file.filename == '':
            flash('No selected file', 'error')
            return redirect(request.url)

        if not file.filename.endswith(('.xlsx', '.xls')):
            flash('File must be an Excel file (.xlsx or .xls)', 'error')
            return redirect(request.url)

        try:
            df = pd.read_excel(file)
            column_mapping = {
                df.columns[0]: 'serial_number',
                df.columns[1]: 'registration_no',
                df.columns[2]: 'customer_name',
                df.columns[3]: 'transaction_type',
                df.columns[4]: 'product',
                df.columns[5]: 'amount'
            }
            df = df.rename(columns=column_mapping)

            
            df['upload_date'] = pd.to_datetime('now').date()

            conn = sqlite3.connect('transactions.db')
            cursor = conn.cursor()

            record_count = 0
            transactions_by_customer = {}

            
            for _, row in df.iterrows():
                customer_id = str(row['registration_no'])
                
                if customer_id not in transactions_by_customer:
                    transactions_by_customer[customer_id] = {
                        "customer_name": row["customer_name"],
                        "transactions": [],
                        "daily_total": 0
                    }

                transactions_by_customer[customer_id]["transactions"].append({
                    "amount": float(row["amount"]),
                    "date": row["upload_date"]
                })
                transactions_by_customer[customer_id]["daily_total"] += float(row["amount"])

                
                cursor.execute('''
                INSERT INTO transactions (
                    serial_number, registration_no, customer_name, 
                    transaction_type, product, amount
                ) VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    int(row['serial_number']) if pd.notna(row['serial_number']) else None,
                    customer_id,
                    str(row['customer_name']),
                    str(row['transaction_type']),
                    str(row['product']),
                    float(row['amount'])
                ))

                record_count += 1

           
            for customer_id, data in transactions_by_customer.items():
                alert_reasons = set()
                transaction_details = []

                
                if len(data["transactions"]) >= 3:
                    alert_reasons.add("Multiple transactions (3 or more)")

                
                if data["daily_total"] > 55000:
                    alert_reasons.add(f"total exceeds 55,000 AED (Total: {data['daily_total']:,.2f} AED)")

                
                high_value_transactions = [t for t in data["transactions"] if t["amount"] >= 55000]
                if high_value_transactions:
                    alert_reasons.add(f"High-value transaction(s) of 55,000 AED or more")
                    for tx in high_value_transactions:
                        transaction_details.append(f"{tx['amount']:,.2f} AED")

                if alert_reasons:
                    alert_text = " | ".join(sorted(alert_reasons))
                    amount_text = f" Total: {data['daily_total']:,.2f} AED"
                    if transaction_details:
                        amount_text += f" | High-value transactions: {', '.join(transaction_details)}"

                    
                    cursor.execute("SELECT alert_reason, amount FROM alerts WHERE registration_no = ?", (customer_id,))
                    existing_alert = cursor.fetchone()

                    if existing_alert:
                        existing_reasons = set(existing_alert[0].split(" | "))
                        updated_reasons = existing_reasons.union(alert_reasons)
                        final_alert_reason = " | ".join(sorted(updated_reasons))

                        cursor.execute('''
                        UPDATE alerts 
                        SET alert_reason = ?, amount = ? 
                        WHERE registration_no = ?
                        ''', (final_alert_reason, amount_text, customer_id))
                    else:
                        cursor.execute('''
                        INSERT INTO alerts (registration_no, customer_name, transaction_type, product, amount, alert_reason)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ''', (customer_id, data["customer_name"], "", "", amount_text, alert_text))

            
            cursor.execute('''
            INSERT INTO upload_history (filename, record_count)
            VALUES (?, ?)
            ''', (file.filename, record_count))

            conn.commit()
            conn.close()

            flash(f'Successfully uploaded {record_count} transactions', 'success')
            return redirect(url_for('index'))

        except Exception as e:
            flash(f'Error processing file: {str(e)}', 'error')
            return redirect(request.url)

    return render_template('upload.html')


@app.route('/alert/<int:alert_id>')
def alert_details(alert_id):
    conn = sqlite3.connect('transactions.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

   
    cursor.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,))
    alert = cursor.fetchone()

    if not alert:
        flash("Alert not found!", "error")
        return redirect(url_for('index'))

   
    cursor.execute("SELECT * FROM transactions WHERE registration_no = ?", (alert["registration_no"],))
    transactions = cursor.fetchall()

    conn.close()

    return render_template('alert_details.html', alert=alert, transactions=transactions)


@app.route('/update_alert_status/<int:alert_id>', methods=['POST'])
def update_alert_status(alert_id):
    new_status = request.form.get('status')
    slip_file = request.files.get('slip_file')

    if not new_status:
        flash("Invalid status!", "error")
        return redirect(url_for('alert_details', alert_id=alert_id))

    conn = sqlite3.connect('transactions.db')
    cursor = conn.cursor()

    if new_status == 'Source of funds are genuine. Withdrawal slip from SBI bank verified.' and slip_file:
        if slip_file.filename == '':
            flash('No selected file', 'error')
            return redirect(url_for('alert_details', alert_id=alert_id))

        if not slip_file.filename.endswith(('.png', '.jpg', '.jpeg', '.pdf')):
            flash('File must be an image or PDF', 'error')
            return redirect(url_for('alert_details', alert_id=alert_id))

        
        upload_dir = os.path.join('static', 'uploads')
        if not os.path.exists(upload_dir):
            os.makedirs(upload_dir)

        
        filename = f"{alert_id}_{slip_file.filename}"
        file_path = os.path.join(upload_dir, filename)
        slip_file.save(file_path)

        
        relative_file_path = f"uploads/{filename}"
        cursor.execute("UPDATE alerts SET status = ?, slip_file = ? WHERE id = ?", (new_status, relative_file_path, alert_id))
    else:
        cursor.execute("UPDATE alerts SET status = ? WHERE id = ?", (new_status, alert_id))

    conn.commit()
    conn.close()

    flash("Alert status updated successfully!", "success")
    return redirect(url_for('alert_details', alert_id=alert_id))




if __name__ == '__main__':
    app.run(debug=True)
