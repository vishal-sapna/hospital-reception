from flask import Flask, render_template, request, redirect, send_file
from datetime import datetime, date
import os
import csv

app = Flask(__name__)
data = []              # OPD Patients
ipd_data = []          # IPD Patients
ARCHIVE_DIR = "archives"

if not os.path.exists(ARCHIVE_DIR):
    os.makedirs(ARCHIVE_DIR)

def reset_daily_records():
    today = date.today().strftime("%Y-%m-%d")
    archive_file = os.path.join(ARCHIVE_DIR, f"{today}.csv")
    flag_file = os.path.join(ARCHIVE_DIR, f"{today}.flag")

    if os.path.exists(flag_file):
        return  # Already archived today

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
    return render_template('intro.html')  # ✅ show intro when opened directly

@app.route('/start')
def start():
    return render_template('index.html')  # ✅ OPD form when clicked Home

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
        'date': datetime.now().strftime("%d-%m-%Y %H:%M")
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
    filename = "current_patients.csv"
    with open(filename, "w", newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "name", "age", "mobile", "reason", "address", "fees", "payment_mode", "date"
        ])
        writer.writeheader()
        writer.writerows(data)
    return send_file(filename, as_attachment=True)

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
            'date': datetime.now().strftime("%d-%m-%Y %H:%M")
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)