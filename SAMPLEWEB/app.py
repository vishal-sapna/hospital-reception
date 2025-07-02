from flask import Flask, render_template, request, redirect, Response
from datetime import datetime, date
from pytz import timezone
import os
import csv
from io import StringIO
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from pydrive.files import GoogleDriveFile
import time

app = Flask(__name__)
DATA_DIR = "data"
ARCHIVE_DIR = "archives"
OPD_FILE = os.path.join(DATA_DIR, "opd_data.csv")
IPD_FILE = os.path.join(DATA_DIR, "ipd_data.csv")
RESTORE_FLAG = os.path.join(DATA_DIR, ".restored")

# Create data directory if it doesn't exist
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)
if not os.path.exists(ARCHIVE_DIR):
    os.makedirs(ARCHIVE_DIR)

# Initialize data lists by loading from CSV files
data = []  # OPD Patients
ipd_data = []  # IPD Patients

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
    ipd_archive_file = os.path.join(ARCHIVE_DIR, f"ipd_{today}.csv")
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
    
    if ipd_data:
        with open(ipd_archive_file, "w", newline='') as f:
            writer = csv.DictWriter(f, fieldnames=[
                "name", "age", "mobile", "reason", "address", "total_bill", "payment_mode", "date"
            ])
            writer.writeheader()
            writer.writerows(ipd_data)
    
    with open(flag_file, "w") as f:
        f.write("archived")
    
    save_opd_data()
    save_ipd_data()
    return archive_file if os.path.exists(archive_file) else None

def download_from_drive(filename):
    """Download a file from Google Drive 'Hospital_Backups' folder"""
    try:
        if not all([os.getenv("GOOGLE_CLIENT_ID"), os.getenv("GOOGLE_CLIENT_SECRET")]):
            print("Google Drive credentials not configured. Skipping restore.")
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
        
        if not folders:
            print(f"Folder '{folder_name}' not found on Google Drive")
            return False

        folder = folders[0]
        file_query = f"title='{filename}' and '{folder['id']}' in parents and trashed=false"
        files = drive.ListFile({'q': file_query}).GetList()
        
        if not files:
            print(f"File '{filename}' not found in backup folder")
            return False

        file = files[0]
        file.GetContentFile(os.path.join(DATA_DIR, filename))
        print(f"Successfully downloaded {filename} from Google Drive")
        return True
    except Exception as e:
        print(f"Error downloading from Google Drive: {str(e)}")
        return False

def restore_data():
    """Restore OPD and IPD data from Google Drive if local files are missing"""
    global data, ipd_data
    
    # Skip if already restored in this session
    if os.path.exists(RESTORE_FLAG):
        return True
    
    restored = False
    
    # Check if we need to restore OPD data
    if not os.path.exists(OPD_FILE) or os.path.getsize(OPD_FILE) == 0:
        print("Restoring OPD data from Google Drive...")
        if download_from_drive("opd_data.csv"):
            restored = True
    
    # Check if we need to restore IPD data
    if not os.path.exists(IPD_FILE) or os.path.getsize(IPD_FILE) == 0:
        print("Restoring IPD data from Google Drive...")
        if download_from_drive("ipd_data.csv"):
            restored = True
    
    # Load the restored data
    if os.path.exists(OPD_FILE):
        with open(OPD_FILE, mode='r', newline='') as f:
            reader = csv.DictReader(f)
            data = list(reader)
    
    if os.path.exists(IPD_FILE):
        with open(IPD_FILE, mode='r', newline='') as f:
            reader = csv.DictReader(f)
            ipd_data = list(reader)
    
    # Create restore flag
    if restored:
        with open(RESTORE_FLAG, 'w') as f:
            f.write("restored")
    
    return restored

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

# Restore data on startup
print("Checking if data restoration is needed...")
if restore_data():
    print("Data restoration completed. Creating daily records and uploading...")
    archive_file = reset_daily_records()
    if archive_file:
        upload_to_drive(archive_file)
    # Also upload the main data files
    save_opd_data()
    save_ipd_data()
    upload_to_drive(OPD_FILE)
    upload_to_drive(IPD_FILE)
else:
    print("No data restoration needed or restoration failed")

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
    save_opd_data()
    
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
        save_opd_data()
        return redirect('/records')
    return render_template('edit.html', entry=data[index], index=index)

@app.route('/delete/<int:index>')
def delete(index):
    if 0 <= index < len(data):
        del data[index]
        save_opd_data()
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
    files = sorted([f for f in os.listdir(ARCHIVE_DIR) if f.endswith(".csv") and not f.startswith("ipd_")])
    ipd_files = sorted([f for f in os.listdir(ARCHIVE_DIR) if f.startswith("ipd_")])
    
    records = {}
    for file in files:
        with open(os.path.join(ARCHIVE_DIR, file), newline='') as f:
            reader = csv.DictReader(f)
            records[file] = list(reader)
    
    ipd_records = {}
    for file in ipd_files:
        with open(os.path.join(ARCHIVE_DIR, file), newline='') as f:
            reader = csv.DictReader(f)
            ipd_records[file] = list(reader)
    
    return render_template("old_records.html", records=records, ipd_records=ipd_records)

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
        save_ipd_data()
        
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
        save_ipd_data()
        return redirect('/ipd-records')
    return render_template('ipd_edit.html', entry=ipd_data[index], index=index)

@app.route('/ipd-delete/<int:index>')
def ipd_delete(index):
    if 0 <= index < len(ipd_data):
        del ipd_data[index]
        save_ipd_data()
    return redirect('/ipd-records')

@app.route('/ipd-export')
def ipd_export():
    si = StringIO()
    writer = csv.DictWriter(si, fieldnames=[
        "Sr No", "Name", "Age", "Mobile", "Reason", "Address", "Total Bill", "Payment Mode", "Date"
    ])
    writer.writeheader()

    for i, entry in enumerate(ipd_data, start=1):
        writer.writerow({
            "Sr No": i,
            "Name": entry['name'],
            "Age": entry['age'],
            "Mobile": entry['mobile'],
            "Reason": entry['reason'],
            "Address": entry['address'],
            "Total Bill": entry['total_bill'],
            "Payment Mode": entry['payment_mode'],
            "Date": entry['date'].split()[0]
        })

    output = si.getvalue()
    response = Response(output, mimetype='text/csv')
    response.headers.set("Content-Disposition", "attachment", filename="current_ipd_patients.csv")
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)