from flask import Flask, render_template, request, redirect, Response
from datetime import datetime, date
from pytz import timezone
import os
import csv
from io import StringIO

app = Flask(__name__)
data = []              # OPD Patients
ipd_data = []          # IPD Patients
ARCHIVE_DIR = "archives"

if not os.path.exists(ARCHIVE_DIR):
    os.makedirs(ARCHIVE_DIR)

def current_indian_time():
    return datetime.now(timezone("Asia/Kolkata")).strftime("%d-%m-%Y %H:%M")

def reset_daily_records():
    today = datetime.now(timezone("Asia/Kolkata")).strftime("%Y-%m-%d")
    archive_file = os.path.join(ARCHIVE_DIR, f"{today}.csv")
    flag_file = os.path.join(ARCHIVE_DIR, f"{today}.flag")

    if os.path.exists(flag_file):
        return

    if data:
        with open(archive_file, "w", newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                "name", "age", "mobile", "reason", "address", "fees", "payment_mode", "date"
            ])
            writer.writeheader()
            writer.writerows(data)
        with open(flag_file, "w") as f:
            f.write("archived")

@app.route('/')
def home():
    reset_daily_records()
    return render_template('intro.html')

@app.route('/start')
def start():
    return render_template('index.html')

@app.route('/submit', methods=['POST'])
def submit():
    entry = {
        'name': request.form['name'],
        'age': request.form['age'],
        'mobile': request.form['mobile'],
        'reason': request.form['reason'],
        'address': request.form.get('address', ''),
        'fees': request.form['fees'],
        'payment_mode': request.form['payment_mode'],
        'date': current_indian_time()
    }
    data.append(entry)
    return redirect('/records')

@app.route('/records')
def records():
    return render_template('records.html', data=data)

@app.route('/edit/<int:index>', methods=['GET', 'POST'])
def edit(index):
    if index < 0 or index >= len(data):
        return redirect('/records')
    if request.method == 'POST':
        data[index] = {
            'name': request.form['name'],
            'age': request.form['age'],
            'mobile': request.form['mobile'],
            'reason': request.form['reason'],
            'address': request.form.get('address', ''),
            'fees': request.form['fees'],
            'payment_mode': request.form['payment_mode'],
            'date': data[index]['date']
        }
        return redirect('/records')
    return render_template('edit.html', entry=data[index], index=index)

@app.route('/delete/<int:index>')
def delete(index):
    if 0 <= index < len(data):
        del data[index]
    return redirect('/records')

@app.route('/export')
def export():
    si = StringIO()
    writer = csv.DictWriter(si, fieldnames=[
        "Sr No", "Name", "Age", "Mobile", "Reason", "Address", "Fees", "Payment Mode", "Date"
    ])
    writer.writeheader()

    for i, entry in enumerate(data, start=1):
        writer.writerow({
            "Sr No": i,
            "Name": entry['name'],
            "Age": entry['age'],
            "Mobile": entry['mobile'],
            "Reason": entry['reason'],
            "Address": entry['address'],
            "Fees": entry['fees'],
            "Payment Mode": entry['payment_mode'],
            "Date": entry['date'].split()[0]
        })

    output = si.getvalue()
    response = Response(output, mimetype='text/csv')
    response.headers.set("Content-Disposition", "attachment", filename="current_patients.csv")
    return response

@app.route('/old-records')
def old_records():
    files = sorted([f for f in os.listdir(ARCHIVE_DIR) if f.endswith(".csv")])
    records = {}
    for file in files:
        with open(os.path.join(ARCHIVE_DIR, file), newline='') as f:
            reader = csv.DictReader(f)
            records[file] = list(reader)
    return render_template("old_records.html", records=records)

@app.route('/ipd', methods=['GET', 'POST'])
def ipd():
    if request.method == 'POST':
        entry = {
            'name': request.form['name'],
            'age': request.form['age'],
            'mobile': request.form['mobile'],
            'reason': request.form['reason'],
            'address': request.form.get('address', ''),
            'total_bill': request.form['total_bill'],
            'payment_mode': request.form['payment_mode'],
            'date': current_indian_time()
        }
        ipd_data.append(entry)
        return redirect('/ipd-records')

    prefill = {
        'name': request.args.get('name', ''),
        'age': request.args.get('age', ''),
        'mobile': request.args.get('mobile', ''),
        'reason': request.args.get('reason', ''),
        'address': request.args.get('address', '')
    } if request.args else None

    return render_template('ipd.html', prefill=prefill)

@app.route('/ipd-records')
def ipd_records():
    return render_template('ipd_records.html', ipd_data=ipd_data)

@app.route('/move-to-ipd/<int:index>')
def move_to_ipd(index):
    if 0 <= index < len(data):
        entry = data[index]
        return redirect(
            f"/ipd?name={entry['name']}&age={entry['age']}&mobile={entry['mobile']}"
            f"&reason={entry['reason']}&address={entry['address']}"
        )
    return redirect('/records')

@app.route('/ipd-edit/<int:index>', methods=['GET', 'POST'])
def ipd_edit(index):
    if index < 0 or index >= len(ipd_data):
        return redirect('/ipd-records')
    if request.method == 'POST':
        ipd_data[index] = {
            'name': request.form['name'],
            'age': request.form['age'],
            'mobile': request.form['mobile'],
            'reason': request.form['reason'],
            'address': request.form.get('address', ''),
            'total_bill': request.form['total_bill'],
            'payment_mode': request.form['payment_mode'],
            'date': ipd_data[index]['date']
        }
        return redirect('/ipd-records')
    return render_template('ipd_edit.html', entry=ipd_data[index], index=index)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
