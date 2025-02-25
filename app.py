import os
import re
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
import PyPDF2
import docx

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///cv_database.db'
app.config['SQLALCHEMY_TRACK_CHANGES'] = False
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB max file size

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# Define the Candidate model
class Candidate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    date = db.Column(db.DateTime, default=datetime.now)
    email = db.Column(db.String(100))
    phone_number = db.Column(db.String(20))
    cv_file = db.Column(db.String(255))
    current_status = db.Column(db.String(50), default='CV Review')
    status_due_date = db.Column(db.DateTime, nullable=True)
    assignee = db.Column(db.String(100), nullable=True)
    position = db.Column(db.String(100), nullable=True)
    notified = db.Column(db.Boolean, default=False)
    fail_stage = db.Column(db.String(50), nullable=True)
    failed_reason = db.Column(db.Text, nullable=True)
    source_notes = db.Column(db.Text, nullable=True)
    last_updated = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self):
        return f'<Candidate {self.name}>'

# Function to extract text from PDF
def extract_text_from_pdf(pdf_path):
    text = ""
    with open(pdf_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            text += page.extract_text()
    return text

# Function to extract text from DOCX
def extract_text_from_docx(docx_path):
    doc = docx.Document(docx_path)
    text = ""
    for paragraph in doc.paragraphs:
        text += paragraph.text + "\n"
    return text

# Function to extract information from CV text
def extract_cv_info(text):
    # Sample extraction patterns (improve these for better accuracy)
    email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    phone_pattern = r'(\+\d{1,3}[\s-]?)?(\(?\d{3}\)?[\s-]?)?\d{3}[\s-]?\d{4}'
    name_pattern = r'^([A-Z][a-z]+([\s-][A-Z][a-z]+)+)'
    
    # Extract information
    email = re.search(email_pattern, text)
    phone = re.search(phone_pattern, text)
    name = re.search(name_pattern, text, re.MULTILINE)
    
    # Get the first 100 chars to help find the name if pattern didn't work
    first_part = text[:100]
    
    return {
        'name': name.group(0) if name else None,
        'email': email.group(0) if email else None,
        'phone': phone.group(0) if phone else None,
        'first_part': first_part  # For debugging or manual extraction
    }

# Initialize the database
with app.app_context():
    db.create_all()

# Routes
@app.route('/')
def index():
    candidates = Candidate.query.all()
    return render_template('index.html', candidates=candidates)

@app.route('/upload', methods=['GET', 'POST'])
def upload_cv():
    if request.method == 'POST':
        # Check if file part exists
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        
        file = request.files['file']
        
        # If user does not select file
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        
        if file:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            
            # Extract text based on file type
            text = ""
            if filename.lower().endswith('.pdf'):
                text = extract_text_from_pdf(file_path)
            elif filename.lower().endswith('.docx'):
                text = extract_text_from_docx(file_path)
            else:
                flash('Unsupported file format. Please upload PDF or DOCX')
                return redirect(request.url)
            
            # Extract information from CV text
            info = extract_cv_info(text)
            
            # Create a new candidate entry
            new_candidate = Candidate(
                name=info['name'],
                email=info['email'],
                phone_number=info['phone'],
                cv_file=filename
            )
            
            db.session.add(new_candidate)
            db.session.commit()
            
            flash('CV uploaded successfully!')
            return redirect(url_for('edit_candidate', id=new_candidate.id))
    
    return render_template('upload.html')

@app.route('/candidate/<int:id>', methods=['GET', 'POST'])
def edit_candidate(id):
    candidate = Candidate.query.get_or_404(id)
    
    if request.method == 'POST':
        # Update candidate information from form
        candidate.name = request.form['name']
        candidate.email = request.form['email']
        candidate.phone_number = request.form['phone_number']
        candidate.current_status = request.form['current_status']
        
        if request.form['status_due_date']:
            candidate.status_due_date = datetime.strptime(request.form['status_due_date'], '%Y-%m-%d')
        
        candidate.assignee = request.form['assignee']
        candidate.position = request.form['position']
        candidate.notified = 'notified' in request.form
        candidate.fail_stage = request.form['fail_stage'] if request.form['fail_stage'] else None
        candidate.failed_reason = request.form['failed_reason']
        candidate.source_notes = request.form['source_notes']
        
        # Update last_updated timestamp
        candidate.last_updated = datetime.now()
        
        db.session.commit()
        flash('Candidate information updated successfully!')
        return redirect(url_for('index'))
    
    return render_template('edit.html', candidate=candidate)

@app.route('/delete/<int:id>', methods=['POST'])
def delete_candidate(id):
    candidate = Candidate.query.get_or_404(id)
    
    # Delete the CV file if it exists
    if candidate.cv_file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], candidate.cv_file)
        if os.path.exists(file_path):
            os.remove(file_path)
    
    db.session.delete(candidate)
    db.session.commit()
    flash('Candidate deleted successfully!')
    return redirect(url_for('index'))

# Add a simple template filter for date formatting
@app.template_filter('format_date')
def format_date(date, format='%Y-%m-%d'):
    if date:
        return date.strftime(format)
    return ''

if __name__ == '__main__':
    app.run(debug=True)