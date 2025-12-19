from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
import os
from datetime import datetime
import requests
import base64

repository_name = 'Mainu'
owner_name = 'aalvincris03'

app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "unique-secret-key-for-flask-app-12345"

db = SQLAlchemy(app)

class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

class Debt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    name_id = db.Column(db.Integer, db.ForeignKey('person.id'))
    lender_id = db.Column(db.Integer, db.ForeignKey('person.id'))
    amount = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    status = db.Column(db.Boolean, default=False)
    name = db.relationship("Person", foreign_keys=[name_id], backref="debts")
    lender = db.relationship("Person", foreign_keys=[lender_id])

class History(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(20))
    debt_id = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.Text)

@app.route('/')
def display_all_data():
    inspector = inspect(db.engine)
    all_tables = inspector.get_table_names()
    # Exclude system tables
    tables = [t for t in all_tables if not t.startswith('sqlite_') and t != 'android_metadata']
    all_data = {}
    active_tab = request.args.get('tab', 'debt' if 'debt' in tables else (tables[0] if tables else None))

    # Compute summary of unpaid debts
    unpaid_summary = db.session.execute(text("""
        SELECT p1.id as borrower_id, p1.name as borrower_name, SUM(d.amount) as total_unpaid, p2.id as lender_id, p2.name as lender_name
        FROM debt d
        JOIN person p1 ON d.name_id = p1.id
        JOIN person p2 ON d.lender_id = p2.id
        WHERE d.status = 0
        GROUP BY p1.id, p1.name, p2.id, p2.name
        ORDER BY total_unpaid DESC
    """)).mappings().all()
    unpaid_summary = [dict(r) for r in unpaid_summary]

    for table in tables:
        try:
            if table == 'debt':
                # Join with person table to get names instead of IDs
                query = text("""
                    SELECT d.id, d.date, d.name_id, d.lender_id, p1.name as borrower_name, p2.name as lender_name, d.amount, d.reason, d.status
                    FROM debt d
                    JOIN person p1 ON d.name_id = p1.id
                    JOIN person p2 ON d.lender_id = p2.id
                """)
                rows = db.session.execute(query).mappings().all()
            else:
                rows = db.session.execute(text(f'SELECT * FROM "{table}"')).mappings().all()
            rows = [dict(r) for r in rows]
            all_data[table] = rows
        except Exception as e:
            all_data[table] = {'error': str(e)}

    return render_template('display.html', all_data=all_data, tables=tables, active_tab=active_tab, unpaid_summary=unpaid_summary)

@app.route('/add_person', methods=['POST'])
def add_person():
    name = request.form['name']
    if name:
        existing_person = Person.query.filter_by(name=name).first()
        if existing_person:
            flash('Person with this name already exists.', 'danger')
        else:
            new_person = Person(name=name)
            db.session.add(new_person)
            db.session.commit()
            flash('Person added successfully.', 'success')
    return redirect(url_for('display_all_data', tab='person'))

@app.route('/edit_person/<int:person_id>', methods=['POST'])
def edit_person(person_id):
    person = Person.query.get_or_404(person_id)
    name = request.form['name']
    if name:
        existing_person = Person.query.filter_by(name=name).first()
        if existing_person and existing_person.id != person_id:
            flash('Person with this name already exists.', 'danger')
        else:
            old_name = person.name
            person.name = name
            db.session.commit()
            history = History(action="edit_person", person_id=person_id, details=f"Edited person: {old_name} -> {name}")
            db.session.add(history)
            db.session.commit()
            flash('Person updated successfully.', 'success')
    return redirect(url_for('display_all_data', tab='person'))

@app.route('/delete_person/<int:person_id>', methods=['POST'])
def delete_person(person_id):
    person = Person.query.get_or_404(person_id)
    name = person.name
    db.session.delete(person)
    db.session.commit()
    history = History(action="delete_person", details=f"Deleted person: {name}")
    db.session.add(history)
    db.session.commit()
    flash('Person deleted successfully.', 'success')
    return redirect(url_for('display_all_data', tab='person'))

@app.route('/add_debt', methods=['POST'])
def add_debt():
    borrower_id = request.form['borrower']
    lender_id = request.form['lender']
    amount = float(request.form['amount'])
    reason = request.form['reason']
    status = bool(int(request.form['status']))
    new_debt = Debt(name_id=borrower_id, lender_id=lender_id, amount=amount, reason=reason, status=status)
    db.session.add(new_debt)
    db.session.commit()
    borrower = Person.query.get(borrower_id)
    lender = Person.query.get(lender_id)
    history = History(action="add_debt", debt_id=new_debt.id, details=f"Added debt: {amount} from {borrower.name} to {lender.name}, reason: {reason}, status: {'Paid' if status else 'Unpaid'}")
    db.session.add(history)
    db.session.commit()
    flash('Debt added successfully.', 'success')
    return redirect(url_for('display_all_data', tab='debt'))

@app.route('/edit_debt/<int:debt_id>', methods=['POST'])
def edit_debt(debt_id):
    debt = Debt.query.get_or_404(debt_id)
    old_borrower = Person.query.get(debt.name_id)
    old_lender = Person.query.get(debt.lender_id)
    old_details = f"Old: borrower {old_borrower.name}, lender {old_lender.name}, amount {debt.amount}, reason {debt.reason}, status {'Paid' if debt.status else 'Unpaid'}"
    debt.name_id = request.form['borrower']
    debt.lender_id = request.form['lender']
    debt.amount = float(request.form['amount'])
    debt.reason = request.form['reason']
    debt.status = bool(int(request.form['status']))
    db.session.commit()
    new_borrower = Person.query.get(debt.name_id)
    new_lender = Person.query.get(debt.lender_id)
    new_details = f"New: borrower {new_borrower.name}, lender {new_lender.name}, amount {debt.amount}, reason {debt.reason}, status {'Paid' if debt.status else 'Unpaid'}"
    history = History(action="edit_debt", debt_id=debt_id, details=f"{old_details} -> {new_details}")
    db.session.add(history)
    db.session.commit()
    flash('Debt updated successfully.', 'success')
    return redirect(url_for('display_all_data', tab='debt'))

@app.route('/delete_debt/<int:debt_id>', methods=['POST'])
def delete_debt(debt_id):
    debt = Debt.query.get_or_404(debt_id)
    borrower = Person.query.get(debt.name_id)
    lender = Person.query.get(debt.lender_id)
    details = f"Deleted debt: borrower {borrower.name}, lender {lender.name}, amount {debt.amount}, reason {debt.reason}, status {'Paid' if debt.status else 'Unpaid'}"
    db.session.delete(debt)
    db.session.commit()
    history = History(action="delete_debt", debt_id=debt_id, details=details)
    db.session.add(history)
    db.session.commit()
    flash('Debt deleted successfully.', 'success')
    return redirect(url_for('display_all_data', tab='debt'))

@app.route('/split_debt', methods=['POST'])
def split_debt():
    lender_id = request.form['lender']
    amount = float(request.form['amount'])
    reason = request.form['reason']
    selected_names = request.form.getlist("split_names")

    lender_obj = Person.query.get(lender_id)

    split_amount = round(amount / len(selected_names), 2)
    for name in selected_names:
        person = Person.query.filter_by(name=name).first()
        if not person:
            person = Person(name=name)
            db.session.add(person)
            db.session.commit()

        debt = Debt(name_id=person.id, lender_id=lender_obj.id, amount=split_amount, reason=reason)
        db.session.add(debt)
        db.session.commit()

        history = History(action="split_add", debt_id=debt.id, details=f"Added new debt by Split function :\n{name} amount : {split_amount} ({reason})")
        db.session.add(history)
        db.session.commit()

    flash('Debt split successfully.', 'success')
    return redirect(url_for('display_all_data', tab='debt'))

@app.route('/unpaid_details/<int:borrower_id>/<int:lender_id>')
def unpaid_details(borrower_id, lender_id):
    borrower = Person.query.get_or_404(borrower_id)
    lender = Person.query.get_or_404(lender_id)
    unpaid_debts = Debt.query.filter_by(name_id=borrower_id, lender_id=lender_id, status=False).all()
    return render_template('unpaid_details.html', borrower=borrower, lender=lender, unpaid_debts=unpaid_debts)

@app.route('/unpaid_all')
def unpaid_all():
    unpaid_debts = Debt.query.filter_by(status=False).all()
    return render_template('unpaid_all.html', unpaid_debts=unpaid_debts)

@app.route('/upload_to_github', methods=['POST'])
def upload_to_github():
    github_token = request.form['github_token']
    # Hardcoded repository details - change these to your repository
    # Example: If your GitHub username is 'john-doe' and your repo is 'my-debt-database'
    repo_owner = owner_name  # Replace with your GitHub username
    repo_name = repository_name    # Replace with your repository name
    commit_message = request.form['commit_message']

    # Read the database file
    db_path = os.path.join(BASE_DIR, 'database.db')
    with open(db_path, 'rb') as f:
        file_content = f.read()

    # Encode to base64
    encoded_content = base64.b64encode(file_content).decode('utf-8')

    # GitHub API URL
    url = f'https://api.github.com/repos/{repo_owner}/{repo_name}/contents/database.db'

    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    # Check if file exists
    response = requests.get(url, headers=headers)
    sha = None
    if response.status_code == 200:
        sha = response.json()['sha']

    # Prepare data for upload
    data = {
        'message': commit_message,
        'content': encoded_content
    }
    if sha:
        data['sha'] = sha

    # Upload file
    response = requests.put(url, headers=headers, json=data)

    if response.status_code in [200, 201]:
        flash('Database uploaded to GitHub successfully!', 'success')
    else:
        flash(f'Failed to upload to GitHub: {response.json().get("message", "Unknown error")}', 'danger')

    return redirect(url_for('display_all_data'))

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
