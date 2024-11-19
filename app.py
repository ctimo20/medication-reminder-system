from flask import Flask, jsonify, request, render_template, flash, redirect, url_for, session
from flask_mysqldb import MySQL
from wtforms import Form, StringField, DateField, IntegerField, FloatField, TimeField, PasswordField, validators
from passlib.hash import sha256_crypt
from functools import wraps
import uuid
import datetime as dt
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/medication/*": {"origins": "http://127.0.0.1:5000"}})

# Config MySQL
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'medicine'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'
app.config['MYSQL_PORT'] = 3307

# Init MySQL
mysql = MySQL(app)

# Index Route
@app.route('/')
def index():
    return render_template('home.html')

@app.route('/about')
def about():
    return render_template('about.html')

# Register Form Class
class RegisterForm(Form):
    name = StringField('Name', [validators.Length(min=1, max=50)])
    username = StringField('Username', [validators.Length(min=4, max=25)])
    email = StringField('Email', [validators.Length(min=6, max=50)])
    password = PasswordField('Password', [
        validators.DataRequired(),
        validators.EqualTo('confirm', message='Passwords do not match')
    ])
    confirm = PasswordField('Confirm Password')

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm(request.form)
    if request.method == 'POST' and form.validate():
        name = form.name.data
        email = form.email.data
        username = form.username.data
        password = sha256_crypt.encrypt(str(form.password.data))

        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO admin(admin_name, email, username, password) VALUES(%s, %s, %s, %s)", 
                    (name, email, username, password))
        mysql.connection.commit()
        cur.close()

        flash('You are now registered and can log in', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

# User login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password_candidate = request.form['password']

        cur = mysql.connection.cursor()
        result = cur.execute("SELECT * FROM admin WHERE username = %s", [username])

        if result > 0:
            data = cur.fetchone()
            password = data['password']
            if sha256_crypt.verify(password_candidate, password):
                session['logged_in'] = True
                session['username'] = username
                return redirect(url_for('dashboard'))
            else:
                flash('Incorrect password', 'danger')
        else:
            flash('Username not found', 'danger')
        cur.close()

    return render_template('login.html')

# Check if user logged in
def is_logged_in(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'logged_in' in session:
            return f(*args, **kwargs)
        else:
            flash('Unauthorized, Please login', 'danger')
            return redirect(url_for('login'))
    return wrap

@app.route('/logout')
def logout():
    session.clear()
    flash('You are now logged out', 'success')
    return redirect(url_for('login'))

# Medication Dashboard
@app.route('/dashboard')
@is_logged_in
def dashboard():
    cur = mysql.connection.cursor()

    # Fetch all medications from the database
    cur.execute("SELECT * FROM medication")
    medications = cur.fetchall()

    # Calculate the current time
    current_time = dt.datetime.now()

    # Classify medications into upcoming and taken
    upcoming_medications = []
    taken_medications = []

    for medication in medications:
        medication_time = medication['medication_time']
        if medication_time:
            # Convert medication_time to a datetime.time object if needed
            if isinstance(medication_time, dt.timedelta):
                medication_time = (dt.datetime.min + medication_time).time()
            elif isinstance(medication_time, dt.datetime):
                medication_time = medication_time.time()

            # Create a datetime object with the current date and medication time
            medication_datetime = dt.datetime.combine(current_time.date(), medication_time)

            if medication_datetime > current_time:
                upcoming_medications.append(medication)
            else:
                taken_medications.append(medication)

    # Sort medications
    upcoming_medications.sort(
        key=lambda m: dt.datetime.combine(current_time.date(), m['medication_time'].time() 
                                          if isinstance(m['medication_time'], dt.datetime) 
                                          else (dt.datetime.min + m['medication_time']).time())
    )
    taken_medications.sort(
        key=lambda m: dt.datetime.combine(current_time.date(), m['medication_time'].time() 
                                          if isinstance(m['medication_time'], dt.datetime) 
                                          else (dt.datetime.min + m['medication_time']).time()), 
        reverse=True
    )

    # Calculate medication counts
    total_medication = len(medications)
    medicationtime_soon_count = sum(1 for m in medications if m['medication_time'] and 
                                    dt.datetime.combine(current_time.date(), 
                                    m['medication_time'].time() if isinstance(m['medication_time'], dt.datetime) 
                                    else (dt.datetime.min + m['medication_time']).time()) 
                                    <= (current_time + dt.timedelta(hours=1)))
    taken_medication_count = sum(1 for m in medications if m.get('taken') == 1 and 
                                 dt.datetime.combine(current_time.date(), 
                                 m['medication_time'].time() if isinstance(m['medication_time'], dt.datetime) 
                                 else (dt.datetime.min + m['medication_time']).time()) < current_time)

    cur.close()

    # Pass converted medication_time as string to the template
    for med in upcoming_medications + taken_medications:
        med['medication_time'] = med['medication_time'].strftime('%H:%M') if isinstance(med['medication_time'], dt.time) else str(med['medication_time'])

    return render_template(
        'dashboard.html', 
        total_medication=total_medication, 
        medicationtime_soon_count=medicationtime_soon_count,
        taken_medication_count=taken_medication_count, 
        upcoming_medications=upcoming_medications,
        taken_medications=taken_medications
    )

# Inventory Form Class
class InventoryForm(Form):
    quantity = IntegerField('Quantity', [validators.DataRequired()])
    brand = StringField('Brand', [validators.Length(min=4, max=50)])
    category = StringField('Category', [validators.Length(min=4, max=50)])
    medication_time = DateField('Medication Time', format='%Y-%m-%d', default=dt.datetime.now())

@app.route('/inventory/add', methods=['GET', 'POST'])
def inventory():
    form = InventoryForm(request.form)
    if request.method == 'POST' and form.validate():
        quantity = form.quantity.data
        brand = form.brand.data
        category = form.category.data
        medication_time = form.medication_time.data

        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO inventory (quantity, brand, category, medication_time) VALUES(%s, %s, %s, %s)", 
                    (quantity, brand, category, medication_time))
        mysql.connection.commit()
        cur.close()

        flash('New batch added', 'success')
        return redirect(url_for('dashboard'))
    return render_template('inventory.html', form=form)

# Medication Form Class with additional fields
class MedicationForm(Form):
    medication_name = StringField('Medication Name', [validators.Length(min=4, max=50)])
    description = StringField('Description', [validators.Length(min=4, max=200)])
    price = FloatField('Price (in USD)', [validators.DataRequired()])
    inv_id = StringField('Inventory ID', [validators.Length(min=4, max=50)])
    dosage = StringField('Dosage (e.g., 500mg)', [validators.Length(min=1, max=20)])
    medication_time = TimeField('Medication Time (HH:MM)', format='%H:%M')
    frequency = StringField('Frequency (e.g., Once daily)', [validators.Length(min=4, max=50)])

@app.route('/medication/add', methods=['GET', 'POST'])
@is_logged_in
def medication():
    form = MedicationForm(request.form)
    if request.method == 'POST' and form.validate():
        medication_name = form.medication_name.data
        description = form.description.data
        price = form.price.data
        inventory_id = form.inv_id.data
        dosage = form.dosage.data
        medication_time = form.medication_time.data
        frequency = form.frequency.data

        # Insert values into the medication table
        cur = mysql.connection.cursor()
        cur.execute("""INSERT INTO medication 
            (medication_name, description, price, inventory_id, dosage, medication_time, frequency) 
            VALUES(%s, %s, %s, %s, %s, %s, %s)""",
            (medication_name, description, price, inventory_id, dosage, medication_time, frequency))
        mysql.connection.commit()
        cur.close()

        flash('Medication added successfully!', 'success')
        return redirect(url_for('dashboard'))

    return render_template('add_medication.html', form=form)

# Run the app
if __name__ == '__main__':
    app.secret_key = 'secret123'
    app.run(debug=True)
