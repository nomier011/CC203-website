import os
from flask import Flask, render_template, request, flash, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TelField
from wtforms.validators import DataRequired, Email, Length, Optional
from datetime import datetime
import email_validator


# ------------------------------
# CONFIGURATION
# ------------------------------

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production'

# Dynamically build path to SQLite DB in the project folder
basedir = os.path.abspath(os.path.dirname(__file__))
db_path = os.path.join(basedir, 'app.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Ensure the directory exists (for SQLite to create the file)
if not os.path.exists(basedir):
    os.makedirs(basedir)

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# ------------------------------
# MODELS
# ------------------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(128), nullable=False)  # bcrypt hash
    phone = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    table_type = db.Column(db.String(20), nullable=False)
    reservation_date = db.Column(db.String(20), nullable=False)
    reservation_time = db.Column(db.String(20), nullable=False)
    duration = db.Column(db.Integer, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')
    payment_method = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref=db.backref('reservations', lazy=True))

# ------------------------------
# FORMS
# ------------------------------

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = TelField('Phone', validators=[Optional(), Length(max=20)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Create Account')

# ------------------------------
# INIT DATABASE
# ------------------------------

with app.app_context():
    db.create_all()

# ------------------------------
# ROUTES
# ------------------------------

@app.route('/')
def landing():
    if 'user_id' in session:
        return redirect(url_for('home'))
    return render_template('landing.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data
        email = form.email.data
        phone = form.phone.data
        password = form.password.data

        # Check for duplicates
        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or Email already exists', 'error')
            return redirect(url_for('register'))

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        new_user = User(
            username=username,
            email=email,
            phone=phone,
            password=hashed_password
        )
        db.session.add(new_user)
        db.session.commit()

        flash('Account created successfully! You can now log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('home'))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('Login successful!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Invalid email or password!', 'error')

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('landing'))

@app.route('/home')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('home.html', username=session['username'])

@app.route('/tables')
def tables():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('tables.html')

@app.route('/book', methods=['POST'])
def book_table():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    try:
        table_type = request.form['table_type']
        reservation_date = request.form['reservation_date']
        reservation_time = request.form['reservation_time']
        duration = int(request.form['duration'])

        price_per_hour = 400 if table_type.lower() == 'vip' else 200
        total_price = price_per_hour * duration

        reservation = Reservation(
            user_id=session['user_id'],
            table_type=table_type,
            reservation_date=reservation_date,
            reservation_time=reservation_time,
            duration=duration,
            total_price=total_price
        )

        db.session.add(reservation)
        db.session.commit()

        session['reservation_id'] = reservation.id
        flash('Table booked successfully! Proceed to payment.', 'success')
        return redirect(url_for('payment'))

    except Exception as e:
        flash(f'Error booking table: {str(e)}', 'error')
        return redirect(url_for('tables'))

@app.route('/payment')
def payment():
    if 'user_id' not in session or 'reservation_id' not in session:
        return redirect(url_for('tables'))

    reservation = Reservation.query.get(session['reservation_id'])
    return render_template('payment.html', reservation=reservation)

@app.route('/process_payment', methods=['POST'])
def process_payment():
    if 'user_id' not in session or 'reservation_id' not in session:
        return redirect(url_for('tables'))

    payment_method = request.form['payment_method']
    reservation = Reservation.query.get(session['reservation_id'])
    reservation.payment_method = payment_method
    reservation.status = 'paid'
    db.session.commit()

    session.pop('reservation_id', None)
    flash('Payment successful! Your reservation is confirmed.', 'success')
    return redirect(url_for('home'))

@app.route('/my_reservations')
def my_reservations():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    reservations = Reservation.query.filter_by(user_id=session['user_id']).order_by(
        Reservation.created_at.desc()).all()
    return render_template('my_reservations.html', reservations=reservations)

# ------------------------------
# RUN SERVER
# ------------------------------

if __name__ == '__main__':
    #app.run(debug=True)
    app.run(host='0.0.0.0', port=5000, debug=True)
