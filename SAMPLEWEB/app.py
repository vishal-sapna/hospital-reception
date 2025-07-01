from flask import Flask, render_template, request, redirect, Response
from datetime import datetime, date
from pytz import timezone
import os
import csv
from io import StringIO
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from pydrive.files import GoogleDriveFile

app = Flask(__name__)
DATA_DIR = "data"
ARCHIVE_DIR = "archives"
OPD_FILE = os.path.join(DATA_DIR, "opd_data.csv")
IPD_FILE = os.path.join(DATA_DIR, "ipd_data.csv")

# Create data directory if it doesn't exist
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
if not os.path.exists(ARCHIVE_DIR):
    os.makedirs(ARCHIVE_DIR)

# Initialize data lists by loading from CSV files
data = []  # OPD Patients
ipd_data = []  # IPD Patients

# Load existing OPD data
if os.path.exists(OPD_FILE):
    with open(OPD_FILE, mode='r', newline='') as f:
        reader = csv.DictReader(f)
        data = list(reader)

# Load existing IPD data
if os.path.exists(IPD_FILE):
    with open(IPD_FILE, mode='r', newline='') as f:
        reader = csv.DictReader(f)
        ipd_data = list(reader)

# Environment-based credentials configuration
credentials = {
    "installed": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "project_id": os.getenv("GOOGLE_PROJECT_ID"),
        "auth_uri": os.getenv("GOOGLE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth"),
        "token_uri": os.getenv("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
        "auth_provider_x509_cert_url": os.getenv("GOOGLE_CERT_URL", "https://www.googleapis.com/oauth2/v1/certs"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "redirect_uris": [os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8080/")]
    }
}

# Initialize Google Drive authentication
gauth = GoogleAuth()
gauth.settings["client_config_backend"] = "settings"
gauth.settings["client_config"] = credentials
drive = GoogleDrive(gauth)

def current_indian_time():
    return datetime.now(timezone("Asia/Kolkata")).strftime("%d-%m-%Y %H:%M")

def save_opd_data():
    """Save OPD data to CSV file"""
    with open(OPD_FILE, mode='w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "name", "age", "mobile", "reason", "address", "fees", "payment_mode", "date"
        ])
        writer.writeheader()
        writer.writerows(data)

def save_ipd_data():
    """Save IPD data to CSV file"""
    with open(IPD_FILE, mode='w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "name", "age", "mobile", "reason", "address", "total_bill", "payment_mode", "date"
        ])
        writer.writeheader()
        writer.writerows(ipd_data)

def reset_daily_records():
    """Archive today's records and create daily backup"""
    today = datetime.now(timezone("Asia/Kolkata")).strftime("%Y-%m-%d")
    archive_file = os.path.join(ARCHIVE_DIR, f"{today}.csv")
    flag_file = os.path.join(ARCHIVE_DIR, f"{today}.flag")

    if os.path.exists(flag_file):
        return archive_file if os.path.exists(archive_file) else None

    if data:
        with open(archive_file, "w", newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                "name", "age", "mobile", "reason", "address", "fees", "payment_mode", "date"
            ])
            writer.writeheader()
            writer.writerows(data)
        with open(flag_file, "w") as f:
            f.write("archived")
    
    save_opd_data()  # Ensure main OPD data is saved
    return archive_file if os.path.exists(archive_file) else None

def upload_to_drive(file_path):
    """Uploads a file to Google Drive in the 'Hospital_Backups' folder"""
    try:
        if not file_path or not os.path.exists(file_path):
            return False
        
        if not all([os.getenv("GOOGLE_CLIENT_ID"), os.getenv("GOOGLE_CLIENT_SECRET")]):
            print("Google Drive credentials not configured. Skipping backup.")
            return False

        if gauth.credentials is None:
            gauth.LocalWebserverAuth()
        elif gauth.access_token_expired:
            gauth.Refresh()
        else:
            gauth.Authorize()

        folder_name = "Hospital_Backups"
        folder_query = f"title='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        folders = drive.ListFile({'q': folder_query}).GetList()
        
        if folders:
            folder = folders[0]
        else:
            folder = drive.CreateFile({
                'title': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            })
            folder.Upload()

        file_name = os.path.basename(file_path)
        gfile = drive.CreateFile({
            'title': file_name,
            'parents': [{'id': folder['id']}]
        })
        gfile.SetContentFile(file_path)
        gfile.Upload()
        
        print(f"Successfully uploaded {file_name} to Google Drive")
        return True
    except Exception as e:
        print(f"Error uploading to Google Drive: {str(e)}")
        return False

@app.route('/')
def home():
    reset_daily_records()
    return render_template('intro.html')

@app.route('/start')
def start():
    opd_count = len(data)
    ipd_count = len(ipd_data)
    total_income = sum(float(entry.get('fees', 0)) for entry in data) + \
                   sum(float(entry.get('total_bill', 0)) for entry in ipd_data)
    
    return render_template('index.html', 
                         opd_count=opd_count,
                         ipd_count=ipd_count,
                         total_income=total_income)

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
    save_opd_data()  # Save to permanent storage
    
    archive_file = reset_daily_records()
    if archive_file:
        upload_to_drive(archive_file)
    
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
        save_opd_data()  # Save changes to permanent storage
        return redirect('/records')
    return render_template('edit.html', entry=data[index], index=index)

@app.route('/delete/<int:index>')
def delete(index):
    if 0 <= index < len(data):
        del data[index]
        save_opd_data()  # Save changes to permanent storage
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
        save_ipd_data()  # Save to permanent storage
        
        archive_file = reset_daily_records()
        if archive_file:
            upload_to_drive(archive_file)
            
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
        save_ipd_data()  # Save changes to permanent storage
        return redirect('/ipd-records')
    return render_template('ipd_edit.html', entry=ipd_data[index], index=index)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)