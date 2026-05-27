from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_file, send_from_directory, current_app
from flask_socketio import emit, join_room, leave_room
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import os
import io
import json
import csv
import re
import uuid
import secrets
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from authlib.integrations.flask_client import OAuth

from app.extensions import db, socketio, migrate, csrf
from app.services.analytics import get_event_analytics, get_category_stats
from app.services.announcements import create_announcement, delete_announcement, get_all_announcements, mark_all_read
from app.utils.generate_participant_id import generate_participant_id, get_college_code
from app.utils.audit_logger import log_audit

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'campuscore-sist-secret-2024')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///campuscore.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WTF_CSRF_CHECK_DEFAULT'] = False

# File upload configuration
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'csv'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Flask-Mail configuration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@campuscore.sist.edu')

db.init_app(app)
migrate.init_app(app, db)
csrf.init_app(app)
socketio.init_app(app, cors_allowed_origins="*", async_mode="threading")

mail = Mail(app)

# --- OAuth setup ---
oauth = OAuth(app)

google = oauth.register(
    name='google',
    client_id=os.environ.get('GOOGLE_CLIENT_ID'),
    client_secret=os.environ.get('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile'
    }
)

@app.template_filter('from_json')
def from_json_filter(value):
    try:
        return json.loads(value) if value else []
    except (ValueError, TypeError):
        return []

@app.context_processor
def inject_theme():
    if 'user_id' in session:
        settings = UserSetting.query.filter_by(user_id=session['user_id']).first()
        theme = settings.theme if settings else 'light'
    else:
        theme = 'light'
    return {'theme_preference': theme}

# ─── Models ───────────────────────────────────────────────────────────────────

from app.models.user import User
from app.models.event import Event
from app.models.registration import Registration
from app.models.attendance import Attendance
from app.models.announcement import Announcement
from app.models.score import Score
from app.models.notification import Notification
from app.models.user_setting import UserSetting
from app.models.system_setting import SystemSetting
from app.models.certificate_signatory import CertificateSignatory
from app.models.team import Team
from app.models.audit_log import AuditLog

from app.blueprints.admin.analytics import bp as analytics_bp
app.register_blueprint(analytics_bp)
from app.blueprints.admin.announcements import bp as announcements_bp
app.register_blueprint(announcements_bp)
from app.blueprints.student.announcements import bp as student_ann_bp
app.register_blueprint(student_ann_bp)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            if request.path.startswith('/api/'):
                return jsonify({'error': 'Authentication required'}), 401
            flash('Please login to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('student_dashboard'))
        return f(*args, **kwargs)
    return decorated

def organizer_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to continue.', 'warning')
            return redirect(url_for('login'))
        if session.get('role') not in ('admin', 'organizer'):
            flash('Organizer access required.', 'danger')
            return redirect(url_for('student_dashboard'))
        return f(*args, **kwargs)
    return decorated

def get_current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

def send_email_notification(user_email, subject, body):
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        return
    try:
        msg = Message(subject, recipients=[user_email], body=body)
        mail.send(msg)
    except Exception as e:
        print(f"Email send failed to {user_email}: {e}")

def create_notification(user_id, type, title, message, related_event_id=None):
    notif = Notification(
        user_id=user_id, type=type, title=title,
        message=message, related_event_id=related_event_id
    )
    db.session.add(notif)
    db.session.commit()
    socketio.emit('notification:new', {
        'id': notif.id, 'type': type, 'title': title,
        'message': message, 'related_event_id': related_event_id,
        'is_read': False, 'created_at': notif.created_at.isoformat()
    }, room=f'user_{user_id}')
    # Send email if user has email notifications enabled
    user = User.query.get(user_id)
    if user:
        settings = UserSetting.query.filter_by(user_id=user_id).first()
        if settings and settings.email_notifications:
            send_email_notification(user.email, title, message)
    return notif

def notify_event_update(event, change_description):
    for reg in event.registrations:
        create_notification(
            user_id=reg.user_id, type='event_update',
            title=f'Update: {event.title}',
            message=change_description,
            related_event_id=event.id
        )

def get_unread_count(user_id):
    return Notification.query.filter_by(user_id=user_id, is_read=False).count()

# ─── Socket.IO Events ─────────────────────────────────────────────────────────

@socketio.on('connect')
def handle_connect():
    if 'user_id' in session:
        join_room(f'user_{session["user_id"]}')

@socketio.on('disconnect')
def handle_disconnect():
    if 'user_id' in session:
        leave_room(f'user_{session["user_id"]}')

@socketio.on('join_event_room')
def handle_join_event(data):
    if 'user_id' in session:
        join_room(f'event_{data.get("event_id")}')

# ─── Auth Routes ──────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('role') == 'admin':
            return redirect(url_for('admin_dashboard'))
        if session.get('role') == 'organizer':
            return redirect(url_for('organizer_dashboard'))
        return redirect(url_for('student_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(email=email).first()
        if user and user.password and check_password_hash(user.password, password):
            user.last_login = datetime.utcnow()
            user.last_login_ip = request.remote_addr or request.headers.get('X-Forwarded-For', '')
            db.session.commit()
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['role'] = user.role
            if user.force_password_reset:
                flash('You must reset your password before continuing.', 'warning')
                return redirect(url_for('reset_password'))
            flash(f'Welcome back, {user.name}!', 'success')
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            if user.role == 'organizer':
                return redirect(url_for('organizer_dashboard'))
            return redirect(url_for('student_dashboard'))
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        reg_number = request.form.get('reg_number', '').strip()
        department = request.form.get('department', '').strip()
        role = 'student'
        phone = request.form.get('phone', '').strip()
        year_raw = request.form.get('year_of_study', '')
        year_of_study = int(year_raw) if year_raw and year_raw.isdigit() else None

        if not name or not email or not password:
            flash('All fields are required.', 'danger')
            return render_template('register.html')

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('register.html')

        name_parts = name.strip().split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''

        college_name = 'Sathyabama Institute of Science and Technology'
        college_code = get_college_code(college_name)
        participant_id = generate_participant_id(college_code)

        user = User(
            name=name, email=email,
            first_name=first_name, last_name=last_name,
            password=generate_password_hash(password),
            role=role, reg_number=reg_number, department=department,
            college=college_name,
            phone=phone, year_of_study=year_of_study,
            participant_id=participant_id
        )
        db.session.add(user)
        db.session.commit()
        # Notify all admins of new user registration
        admins = User.query.filter_by(role='admin').all()
        for admin in admins:
            settings = UserSetting.query.filter_by(user_id=admin.id).first()
            if settings and not settings.email_notifications:
                continue
            admin_url = url_for('admin_user_detail', uid=user.id, _external=True)
            send_html_email(admin.email, f'👤 New {user.role.title()} registered — CampusCore SIST',
                'new_user_notification.html', admin=admin, new_user=user, admin_url=admin_url)
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if 'user_id' not in session:
        flash('You must be logged in to reset your password.', 'warning')
        return redirect(url_for('login'))
    u = User.query.get(session['user_id'])
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if not password or len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
        elif password != confirm:
            flash('Passwords do not match.', 'danger')
        else:
            u.password = generate_password_hash(password)
            u.force_password_reset = False
            db.session.commit()
            send_html_email(u.email, '🔐 Password Updated - CampusCore',
                'password_reset_notification.html', user=u, forced=False)
            flash('Password updated successfully. You can now continue.', 'success')
            if u.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            if u.role == 'organizer':
                return redirect(url_for('organizer_dashboard'))
            return redirect(url_for('student_dashboard'))
    return render_template('reset_password.html')


@app.route('/reset-password/token/<token>', methods=['GET', 'POST'])
def reset_password_with_token(token):
    u = User.query.filter_by(reset_token=token).first()
    if not u or not u.reset_token_expiry or u.reset_token_expiry < datetime.utcnow():
        flash('This reset link has expired or is invalid. Please contact an administrator.', 'danger')
        return redirect(url_for('login'))
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        if not password or len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
        elif password != confirm:
            flash('Passwords do not match.', 'danger')
        else:
            u.password = generate_password_hash(password)
            u.force_password_reset = False
            u.reset_token = None
            u.reset_token_expiry = None
            db.session.commit()
            send_html_email(u.email, '🔐 Password Updated - CampusCore',
                'password_reset_notification.html', user=u, forced=False)
            flash('Password updated successfully. You can now log in.', 'success')
            return redirect(url_for('login'))
    return render_template('reset_password.html', token=token, user_name=u.name)


@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('login'))

# ─── Google OAuth Routes ──────────────────────────────────────────────────────

@app.route('/login/google')
def google_login():
    """Redirect the user to Google's OAuth consent screen."""
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)


@app.route('/login/google/callback')
def google_callback():
    """Handle the redirect back from Google after authentication."""
    try:
        token = google.authorize_access_token()
    except Exception:
        flash('Google login was cancelled or failed. Please try again.', 'danger')
        return redirect(url_for('login'))

    userinfo = token.get('userinfo')
    if not userinfo:
        flash('Could not retrieve account information from Google.', 'danger')
        return redirect(url_for('login'))

    google_id = userinfo['sub']          # unique Google user ID
    email     = userinfo['email']
    name      = userinfo.get('name', email.split('@')[0])

    # 1. Check if a user already linked this Google account
    user = User.query.filter_by(google_id=google_id).first()

    if not user:
        # 2. Check if an account with this email already exists (email/password user)
        user = User.query.filter_by(email=email).first()
        if user:
            # Link the Google ID to the existing account
            user.google_id = google_id
            db.session.commit()
        else:
            # 3. First-time Google sign-in: create a new student account
            participant_id = generate_participant_id()
            user = User(
                name=name,
                email=email,
                password=None,           # no password for OAuth users
                role='student',
                google_id=google_id,
                participant_id=participant_id
            )
            db.session.add(user)
            db.session.commit()
            flash(f'Welcome to CampusCore, {name}! Your account has been created.', 'success')

    # Log the user in using the same session pattern as the existing login route
    user.last_login = datetime.utcnow()
    user.last_login_ip = request.remote_addr or request.headers.get('X-Forwarded-For', '')
    db.session.commit()
    session['user_id']   = user.id
    session['user_name'] = user.name
    session['role']      = user.role

    flash(f'Welcome back, {user.name}!', 'success')

    if user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('student_dashboard'))

# ─── Admin Routes ─────────────────────────────────────────────────────────────

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    user = get_current_user()
    today = date.today()
    tomorrow = today + timedelta(days=1)
    total_events = Event.query.count()
    total_students = User.query.filter_by(role='student').count()
    total_registrations = Registration.query.count()
    total_present = Attendance.query.filter_by(status='present').count()
    all_events = Event.query.order_by(Event.date).all()
    active_events = [e for e in all_events if e.date == today]
    upcoming_events = [e for e in all_events if e.date >= tomorrow]
    return render_template('admin/dashboard.html',
        total_events=total_events, total_students=total_students,
        total_registrations=total_registrations, total_present=total_present,
        events=all_events, active_events=len(active_events),
        upcoming_count=len(upcoming_events),
        today=today, tomorrow=tomorrow,
        user=user)

@app.route('/admin/events')
@admin_required
def admin_events():
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    tab = request.args.get('tab', 'all')
    today = date.today()

    query = Event.query
    if search:
        query = query.filter(Event.title.ilike(f'%{search}%'))
    if category:
        query = query.filter_by(category=category)

    events = query.order_by(Event.date.desc()).all()

    if tab == 'upcoming':
        events = [e for e in events if e.date >= today]
    elif tab == 'past':
        events = [e for e in events if e.date < today]

    categories = db.session.query(Event.category).distinct().all()
    reg_counts = {}
    for e in events:
        reg_counts[e.id] = len(e.registrations)

    return render_template('admin/events.html', events=events,
        categories=[c[0] for c in categories], search=search,
        selected_category=category, today=today, user=get_current_user(),
        tab=tab, reg_counts=reg_counts)

@app.route('/admin/events/create', methods=['GET', 'POST'])
@admin_required
def create_event():
    user = get_current_user()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        event_date_str = request.form.get('date', '')
        time_str = request.form.get('time', '')
        venue = request.form.get('venue', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', 'General')
        max_p_str = request.form.get('max_participants', '')
        image_url = request.form.get('image_url', '').strip()
        tags_raw = request.form.get('tags', '')

        if not title or not event_date_str:
            flash('Title and date are required.', 'danger')
            return render_template('admin/event_form.html', event=None, user=user, event_time=time_str, tags=[])

        try:
            event_date = datetime.strptime(event_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format.', 'danger')
            return render_template('admin/event_form.html', event=None, user=user, event_time=time_str, tags=[])

        try:
            max_participants = int(max_p_str) if max_p_str else 100
        except (ValueError, TypeError):
            max_participants = 100

        # PDF upload
        pdf_filename = None
        if 'pdf_file' in request.files:
            file = request.files['pdf_file']
            if file and file.filename and allowed_file(file.filename):
                original_name = secure_filename(file.filename)
                ext = original_name.rsplit('.', 1)[1].lower() if '.' in original_name else 'pdf'
                pdf_filename = f'{secrets.token_hex(8)}--{original_name}'
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename))
            elif file and file.filename and not allowed_file(file.filename):
                flash('Only PDF files are allowed.', 'danger')

        # Conflict detection (warning only — event still created)
        conflicts = Event.query.filter_by(date=event_date, venue=venue).all()
        if conflicts and venue:
            flash(f'⚠️ Conflict detected: "{conflicts[0].title}" is already scheduled at {venue} on this date.', 'warning')

        tag_list = [t.strip() for t in tags_raw.replace('\n', ',').split(',') if t.strip()]

        event = Event(title=title, date=event_date, time=time_str, venue=venue,
            description=description, category=category,
            max_participants=max_participants,
            image_url=image_url, tags=','.join(tag_list),
            pdf_file=pdf_filename,
            created_by=session['user_id'])
        db.session.add(event)
        db.session.commit()
        from app.services.notifications import notify_new_event
        notify_new_event(
            title=event.title,
            date=event.date.strftime("%d %b %Y"),
            venue=event.venue or "TBD",
        )
        notify_event_created(event, user.name)
        socketio.emit('event:created', {
            'id': event.id,
            'title': event.title,
            'description': event.description[:100] if event.description else '',
            'date': event.date.strftime('%Y-%m-%d'),
            'date_display': event.date.strftime('%d %B %Y'),
            'time': event.time or '',
            'venue': event.venue or '',
            'category': event.category,
            'image_url': event.image_url or '',
            'pdf_file': event.pdf_file or '',
            'max_participants': event.max_participants,
            'tags': event.tags or '',
            'reg_count': 0
        })
        flash('Event created successfully!', 'success')
        return redirect(url_for('admin_events'))
    return render_template('admin/event_form.html', event=None, user=user, event_time='', tags=[])

@app.route('/admin/events/<int:event_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_event(event_id):
    user = get_current_user()
    event = Event.query.get_or_404(event_id)

    if request.method == 'POST':
        # PDF removal only — don't touch other fields
        if request.form.get('remove_pdf') == '1' and event.pdf_file:
            old_path = os.path.join(app.config['UPLOAD_FOLDER'], event.pdf_file)
            if os.path.exists(old_path):
                os.remove(old_path)
            event.pdf_file = None
            db.session.commit()
            flash('PDF removed successfully.', 'info')
            return redirect(url_for('edit_event', event_id=event.id))

        old_title = event.title
        old_date = event.date
        old_time = event.time
        old_venue = event.venue
        old_category = event.category

        event.title = request.form.get('title', '').strip()
        try:
            event.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        except (ValueError, TypeError):
            flash('Invalid date format.', 'danger')
            return redirect(url_for('edit_event', event_id=event.id))
        event.time = request.form.get('time', '')
        event.venue = request.form.get('venue', '').strip()
        event.description = request.form.get('description', '').strip()
        event.category = request.form.get('category', 'General')
        max_p_str = request.form.get('max_participants', '')
        try:
            event.max_participants = int(max_p_str) if max_p_str else event.max_participants
        except (ValueError, TypeError):
            pass
        event.image_url = request.form.get('image_url', '').strip()
        tags_raw = request.form.get('tags', '')
        tag_list = [t.strip() for t in tags_raw.replace('\n', ',').split(',') if t.strip()]
        event.tags = ','.join(tag_list)

        # PDF upload (replace existing)
        if 'pdf_file' in request.files:
            file = request.files['pdf_file']
            if file and file.filename and allowed_file(file.filename):
                # Remove old file
                if event.pdf_file:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], event.pdf_file)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                original_name = secure_filename(file.filename)
                ext = original_name.rsplit('.', 1)[1].lower() if '.' in original_name else 'pdf'
                event.pdf_file = f'{secrets.token_hex(8)}--{original_name}'
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], event.pdf_file))
            elif file and file.filename and not allowed_file(file.filename):
                flash('Only PDF files are allowed.', 'danger')

        db.session.commit()

        changes = []
        if event.title != old_title:
            changes.append({'field': 'title', 'old_value': old_title, 'new_value': event.title})
        if event.date != old_date:
            changes.append({'field': 'date', 'old_value': old_date.strftime('%d %b %Y'), 'new_value': event.date.strftime('%d %b %Y')})
        if event.time != old_time:
            changes.append({'field': 'time', 'old_value': old_time or 'TBD', 'new_value': event.time or 'TBD'})
        if event.venue != old_venue:
            changes.append({'field': 'venue', 'old_value': old_venue or 'TBD', 'new_value': event.venue or 'TBD'})
        if event.category != old_category:
            changes.append({'field': 'category', 'old_value': old_category, 'new_value': event.category})
        if changes:
            notify_event_update_to_participants(event, changes)

        socketio.emit('event:updated', {
            'id': event.id,
            'title': event.title,
            'description': event.description[:100] if event.description else '',
            'date': event.date.strftime('%Y-%m-%d'),
            'date_display': event.date.strftime('%d %B %Y'),
            'time': event.time or '',
            'venue': event.venue or '',
            'category': event.category,
            'image_url': event.image_url or '',
            'pdf_file': event.pdf_file or '',
            'max_participants': event.max_participants,
            'tags': event.tags or '',
        })

        flash('Event updated successfully!', 'success')
        return redirect(url_for('admin_events'))

    tag_list = [t for t in event.tags.split(',') if t] if event.tags else []
    event_time = event.time if event.time else ''
    return render_template('admin/event_form.html', event=event, user=user, tags=tag_list, event_time=event_time)


# ─── Signatory management ──────────────────────────────────────────────────────

SIGNATURE_FOLDER = os.path.join(app.config['UPLOAD_FOLDER'], 'signatures')
os.makedirs(SIGNATURE_FOLDER, exist_ok=True)


@app.route('/api/events/<int:event_id>/signatories/add', methods=['POST'])
@login_required
def api_add_signatory(event_id):
    event = Event.query.get_or_404(event_id)
    name = request.form.get('name', '').strip()
    title = request.form.get('title', '').strip() or 'Event Coordinator'
    if not name:
        return jsonify({'error': 'Name is required'}), 400

    sig_image = None
    if 'signature_image' in request.files:
        file = request.files['signature_image']
        if file and file.filename:
            original_name = secure_filename(file.filename)
            sig_image = f'sig_{secrets.token_hex(8)}_{original_name}'
            file.save(os.path.join(SIGNATURE_FOLDER, sig_image))

    ordering = request.form.get('ordering', 0, type=int)
    sig = CertificateSignatory(event_id=event.id, name=name, title=title,
                               signature_image=sig_image, ordering=ordering)
    db.session.add(sig)
    db.session.commit()
    return jsonify({
        'id': sig.id, 'name': sig.name, 'title': sig.title,
        'signature_image': sig.signature_image, 'ordering': sig.ordering
    })


@app.route('/api/events/<int:event_id>/signatories/<int:signatory_id>/remove', methods=['POST'])
@login_required
def api_remove_signatory(event_id, signatory_id):
    sig = CertificateSignatory.query.filter_by(id=signatory_id, event_id=event_id).first_or_404()
    if sig.signature_image:
        img_path = os.path.join(SIGNATURE_FOLDER, sig.signature_image)
        if os.path.exists(img_path):
            os.remove(img_path)
    db.session.delete(sig)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/admin/events/<int:event_id>/delete', methods=['POST'])
@admin_required
def delete_event(event_id):
    event = Event.query.get_or_404(event_id)
    # Notify registered students before deleting
    notify_event_cancelled(event)
    # Clean up uploaded PDF
    if event.pdf_file:
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], event.pdf_file)
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
    socketio.emit('event:deleted', {'id': event.id, 'title': event.title})
    Registration.query.filter_by(event_id=event_id).delete()
    Attendance.query.filter_by(event_id=event_id).delete()
    db.session.delete(event)
    db.session.commit()
    flash('Event deleted.', 'info')
    return redirect(url_for('admin_events'))

@app.route('/admin/events/<int:event_id>/attendance', methods=['GET', 'POST'])
@admin_required
def manage_attendance(event_id):
    event = Event.query.get_or_404(event_id)
    registrations = db.session.query(Registration, User)\
        .join(User, Registration.user_id == User.id)\
        .filter(Registration.event_id == event_id).all()

    if request.method == 'POST':
        for reg, user in registrations:
            status = request.form.get(f'attendance_{user.id}', 'absent')
            att = Attendance.query.filter_by(user_id=user.id, event_id=event_id).first()
            if att:
                att.status = status
                att.marked_at = datetime.utcnow()
            else:
                att = Attendance(user_id=user.id, event_id=event_id, status=status)
                db.session.add(att)
        db.session.commit()
        from app.services.notifications import notify_attendance_marked
        for reg, student in registrations:
            if request.form.get(f"attendance_{student.id}") == "present":
                notify_attendance_marked(
                    user_id=student.id,
                    event_title=event.title,
                )
            socketio.emit('attendance:updated', {
                'event_id': event.id,
                'event_title': event.title,
                'status': request.form.get(f'attendance_{student.id}', 'absent')
            }, room=f'user_{student.id}')
        flash('Attendance saved successfully!', 'success')
        return redirect(url_for('manage_attendance', event_id=event_id))

    attendance_map = {}
    for att in Attendance.query.filter_by(event_id=event_id).all():
        attendance_map[att.user_id] = att.status

    return render_template('admin/attendance.html', event=event,
        registrations=registrations, attendance_map=attendance_map, user=get_current_user())

@app.route('/organizer/events/<int:event_id>/attendance', methods=['GET', 'POST'])
@organizer_required
def organizer_manage_attendance(event_id):
    event = Event.query.get_or_404(event_id)
    if event.created_by != session.get('user_id') and session.get('role') not in ('admin', 'organizer'):
        flash('You can only manage attendance for your own events.', 'danger')
        return redirect(url_for('organizer_dashboard'))
    registrations = db.session.query(Registration, User)\
        .join(User, Registration.user_id == User.id)\
        .filter(Registration.event_id == event_id).all()
    if request.method == 'POST':
        for reg, user in registrations:
            status = request.form.get(f'attendance_{user.id}', 'absent')
            att = Attendance.query.filter_by(user_id=user.id, event_id=event_id).first()
            if att:
                att.status = status
                att.marked_at = datetime.utcnow()
            else:
                att = Attendance(user_id=user.id, event_id=event_id, status=status)
                db.session.add(att)
        db.session.commit()
        from app.services.notifications import notify_attendance_marked
        for reg, student in registrations:
            if request.form.get(f"attendance_{student.id}") == "present":
                notify_attendance_marked(
                    user_id=student.id,
                    event_title=event.title,
                )
            socketio.emit('attendance:updated', {
                'event_id': event.id,
                'event_title': event.title,
                'status': request.form.get(f'attendance_{student.id}', 'absent')
            }, room=f'user_{student.id}')
        flash('Attendance saved successfully!', 'success')
        return redirect(url_for('organizer_manage_attendance', event_id=event_id))
    attendance_map = {}
    for att in Attendance.query.filter_by(event_id=event_id).all():
        attendance_map[att.user_id] = att.status
    return render_template('admin/attendance.html', event=event,
        registrations=registrations, attendance_map=attendance_map, user=get_current_user())

@app.route('/admin/students')
@admin_required
def admin_students():
    students = User.query.filter_by(role='student').all()
    return render_template('admin/students.html', students=students, user=get_current_user())


# ─── Admin: User Management ──────────────────────────────────────────────────

@app.route('/admin/users')
@admin_required
def admin_users():
    search = request.args.get('search', '')
    role_filter = request.args.get('role', '')
    query = User.query
    if search:
        query = query.filter(db.or_(
            User.name.ilike(f'%{search}%'),
            User.email.ilike(f'%{search}%'),
            User.participant_id.ilike(f'%{search}%')
        ))
    if role_filter:
        query = query.filter_by(role=role_filter)
    users = query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=users, user=get_current_user(),
        search=search, role_filter=role_filter)


@app.route('/admin/users/export')
@admin_required
def admin_export_users():
    search = request.args.get('search', '')
    role_filter = request.args.get('role', '')
    fmt = request.args.get('format', 'csv')
    query = User.query
    if search:
        query = query.filter(db.or_(
            User.name.ilike(f'%{search}%'),
            User.email.ilike(f'%{search}%'),
            User.participant_id.ilike(f'%{search}%')
        ))
    if role_filter:
        query = query.filter_by(role=role_filter)
    users = query.order_by(User.created_at.desc()).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Participant ID', 'Name', 'Email', 'Phone', 'Role',
        'College', 'Department', 'Year of Study', 'Reg. Number',
        'GitHub', 'LinkedIn', 'Status', 'Registered At'
    ])
    for u in users:
        writer.writerow([
            u.participant_id or '', u.name, u.email, u.phone or '',
            u.role, u.college or '', u.department or '',
            u.year_of_study or '', u.reg_number or '',
            u.github_url or '', u.linkedin_url or '',
            'Active' if u.is_active else 'Inactive',
            u.created_at.strftime('%Y-%m-%d %H:%M')
        ])
    output.seek(0)

    filename = 'users_export.csv'
    if role_filter:
        filename = f'{role_filter}s_export.csv'

    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        as_attachment=True,
        download_name=filename,
        mimetype='text/csv'
    )


@app.route('/admin/users/create', methods=['GET', 'POST'])
@admin_required
def admin_create_user():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'student')
        college = request.form.get('college', '').strip()
        department = request.form.get('department', '').strip()
        phone = request.form.get('phone', '').strip()
        year_raw = request.form.get('year_of_study', '')
        year_of_study = int(year_raw) if year_raw and year_raw.isdigit() else None
        github_url = request.form.get('github_url', '').strip()
        linkedin_url = request.form.get('linkedin_url', '').strip()
        profile_photo_url = request.form.get('profile_photo_url', '').strip()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        reg_number = request.form.get('reg_number', '').strip()
        if not name or not email or not password:
            flash('Name, email, and password are required.', 'danger')
            return render_template('admin/user_form.html', user_obj=None, user=get_current_user())
        if User.query.filter_by(email=email).first():
            flash('Email already exists.', 'danger')
            return render_template('admin/user_form.html', user_obj=None, user=get_current_user())
        name_parts = name.split(' ', 1)
        if not first_name:
            first_name = name_parts[0] if name_parts else name
        if not last_name:
            last_name = name_parts[1] if len(name_parts) > 1 else ''
        college_code = get_college_code(college or 'Sathyabama Institute of Science and Technology')
        participant_id = generate_participant_id(college_code)
        u = User(name=name, first_name=first_name, last_name=last_name,
            email=email, password=generate_password_hash(password), role=role, college=college,
            department=department, phone=phone, year_of_study=year_of_study,
            reg_number=reg_number,
            github_url=github_url, linkedin_url=linkedin_url, profile_photo_url=profile_photo_url,
            participant_id=participant_id)
        db.session.add(u)
        db.session.flush()
        log_audit(target_user_id=u.id, action='created', changed_by=session['user_id'],
            changes=f'User created as {role}', new_value=f'role={role}')
        db.session.commit()
        admins = User.query.filter_by(role='admin').all()
        for admin in admins:
            if admin.id == session['user_id']:
                continue
            settings = UserSetting.query.filter_by(user_id=admin.id).first()
            if settings and not settings.email_notifications:
                continue
            admin_url = url_for('admin_user_detail', uid=u.id, _external=True)
            send_html_email(admin.email, f'👤 New {u.role.title()} created — CampusCore SIST',
                'new_user_notification.html', admin=admin, new_user=u, admin_url=admin_url)
        flash(f'User {name} created as {role}.', 'success')
        return redirect(url_for('admin_users'))
    return render_template('admin/user_form.html', user_obj=None, user=get_current_user())


@app.route('/admin/users/<int:uid>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit_user(uid):
    u = User.query.get_or_404(uid)
    if request.method == 'POST':
        old_role = u.role
        old_active = u.is_active
        old_college = u.college
        old_dept = u.department
        old_phone = u.phone
        old_year = u.year_of_study
        old_name = u.name
        old_email = u.email
        old_reg_number = u.reg_number

        u.name = request.form.get('name', '').strip()
        u.first_name = request.form.get('first_name', '').strip()
        u.last_name = request.form.get('last_name', '').strip()
        new_email = request.form.get('email', '').strip()
        if new_email != u.email:
            existing = User.query.filter_by(email=new_email).first()
            if existing:
                flash('That email is already in use by another user.', 'danger')
                return render_template('admin/user_form.html', user_obj=u, user=get_current_user())
        u.email = new_email
        u.role = request.form.get('role', 'student')
        u.college = request.form.get('college', '').strip()
        u.department = request.form.get('department', '').strip()
        u.reg_number = request.form.get('reg_number', '').strip()
        u.phone = request.form.get('phone', '').strip()
        year_raw = request.form.get('year_of_study', '')
        u.year_of_study = int(year_raw) if year_raw and year_raw.isdigit() else None
        u.github_url = request.form.get('github_url', '').strip()
        u.linkedin_url = request.form.get('linkedin_url', '').strip()
        u.profile_photo_url = request.form.get('profile_photo_url', '').strip()
        u.is_active = request.form.get('is_active') == '1'

        changes = []
        if u.role != old_role:
            changes.append(f'role: {old_role} → {u.role}')
        if u.is_active != old_active:
            changes.append(f'status: {"Active" if old_active else "Inactive"} → {"Active" if u.is_active else "Inactive"}')
        if u.name != old_name:
            changes.append(f'name: {old_name} → {u.name}')
        if u.email != old_email:
            changes.append(f'email: {old_email} → {u.email}')
        if u.college != old_college:
            changes.append(f'college: {old_college} → {u.college}')
        if u.department != old_dept:
            changes.append(f'department: {old_dept} → {u.department}')
        if u.phone != old_phone:
            changes.append(f'phone: {old_phone} → {u.phone}')
        if u.year_of_study != old_year:
            changes.append(f'year: {old_year} → {u.year_of_study}')

        log_audit(target_user_id=u.id, action='updated', changed_by=session['user_id'],
            changes='; '.join(changes) if changes else 'Profile updated',
            old_value=','.join(str(v) for v in [old_role, old_active, old_name, old_email, old_college, old_dept, old_phone, old_year]),
            new_value=','.join(str(v) for v in [u.role, u.is_active, u.name, u.email, u.college, u.department, u.phone, u.year_of_study]))
        db.session.commit()
        if changes:
            settings = UserSetting.query.filter_by(user_id=u.id).first()
            if not settings or settings.email_notifications:
                send_html_email(u.email, f"🔔 Your CampusCore Account Has Been Updated",
                    'account_update_notification.html', user=u, changes=changes)
        flash(f'User {u.name} updated.', 'success')
        return redirect(url_for('admin_users'))
    return render_template('admin/user_form.html', user_obj=u, user=get_current_user())


@app.route('/admin/users/<int:uid>')
@admin_required
def admin_user_detail(uid):
    u = User.query.get_or_404(uid)

    regs = db.session.query(Registration, Event, Attendance)\
        .join(Event, Registration.event_id == Event.id)\
        .outerjoin(Attendance, db.and_(
            Attendance.event_id == Registration.event_id,
            Attendance.user_id == Registration.user_id
        ))\
        .filter(Registration.user_id == uid)\
        .order_by(Event.date.desc()).all()

    teams = u.teams
    logs = AuditLog.query.filter_by(user_id=uid)\
        .order_by(AuditLog.created_at.desc()).all()

    return render_template('admin/user_detail.html', user_obj=u, user=get_current_user(),
        registrations=regs, teams=teams, audit_logs=logs)


@app.route('/admin/users/<int:uid>/delete', methods=['POST'])
@admin_required
def admin_delete_user(uid):
    u = User.query.get_or_404(uid)
    if u.id == session['user_id']:
        flash('Cannot delete yourself.', 'danger')
        return redirect(url_for('admin_users'))
    Registration.query.filter_by(user_id=uid).delete()
    Attendance.query.filter_by(user_id=uid).delete()
    Score.query.filter_by(user_id=uid).delete()
    Notification.query.filter_by(user_id=uid).delete()
    UserSetting.query.filter_by(user_id=uid).delete()
    AuditLog.query.filter_by(user_id=uid).delete()
    AuditLog.query.filter_by(changed_by=uid).update({'changed_by': None})
    db.session.execute(db.text('DELETE FROM team_members WHERE user_id = :uid'), {'uid': uid})
    db.session.delete(u)
    db.session.commit()
    flash('User deleted.', 'info')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:uid>/force-reset', methods=['POST'])
@admin_required
def admin_force_reset(uid):
    u = User.query.get_or_404(uid)
    admin = get_current_user()
    # Generate secure one-time token
    u.reset_token = secrets.token_urlsafe(48)
    u.reset_token_expiry = datetime.utcnow() + timedelta(hours=1)
    u.force_password_reset = True
    log_audit(target_user_id=uid, action='force_password_reset', changed_by=session['user_id'],
        changes=f'Password reset forced by admin ({admin.name})', new_value='force_password_reset=True')
    db.session.commit()
    reset_link = url_for('reset_password_with_token', token=u.reset_token, _external=True)
    send_html_email(u.email, '🔐 Your CampusCore password was reset by an administrator',
        'force_password_reset.html', user=u, admin=admin, reset_link=reset_link, utcnow=datetime.utcnow())
    flash(f'Password reset email sent to {u.name}.', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/bulk/export', methods=['POST'])
@admin_required
def admin_bulk_export_users():
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'error': 'No users selected'}), 400
    users = User.query.filter(User.id.in_(ids)).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Participant ID', 'Name', 'Email', 'Role', 'College', 'Department', 'Phone', 'Status', 'Registered'])
    for u in users:
        writer.writerow([
            u.participant_id or '', u.name, u.email, u.role,
            u.college or '', u.department or '', u.phone or '',
            'Active' if u.is_active else 'Inactive',
            u.created_at.strftime('%Y-%m-%d')
        ])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        as_attachment=True,
        download_name='selected_users.csv',
        mimetype='text/csv'
    )


@app.route('/admin/users/<int:uid>/toggle-status', methods=['POST'])
@admin_required
def admin_toggle_user_status(uid):
    u = User.query.get_or_404(uid)
    if u.id == session['user_id']:
        return jsonify({'error': 'Cannot toggle own status'}), 400
    old_status = u.is_active
    u.is_active = not u.is_active
    status_label = 'Active' if u.is_active else 'Inactive'
    log_audit(target_user_id=uid, action='status_toggled', changed_by=session['user_id'],
        changes=f'Status changed to {status_label}',
        old_value=str(old_status), new_value=str(u.is_active))
    db.session.commit()
    return jsonify({'success': True, 'is_active': u.is_active})


@app.route('/admin/users/<int:uid>/notify', methods=['POST'])
@admin_required
def admin_notify_user(uid):
    u = User.query.get_or_404(uid)
    data = request.get_json(silent=True) or {}
    subject = data.get('subject', '').strip()
    message = data.get('message', '').strip()
    if not subject or not message:
        return jsonify({'error': 'Subject and message are required'}), 400
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        return jsonify({'error': 'Mail server not configured'}), 500
    try:
        msg = Message(subject, recipients=[u.email], html=f'<p>{message}</p>')
        mail.send(msg)
    except Exception as e:
        print(f"Email send failed to {u.email}: {e}")
        return jsonify({'error': 'Failed to send email'}), 500
    return jsonify({'success': True, 'email': u.email})


@app.route('/admin/users/bulk', methods=['POST'])
@admin_required
def admin_bulk_users():
    data = request.get_json(silent=True) or {}
    ids = data.get('ids', [])
    action = data.get('action', '')
    if not ids or action != 'delete':
        return jsonify({'error': 'Invalid request'}), 400

    if action == 'delete':
        for uid in ids:
            if uid == session['user_id']:
                continue
            u = User.query.get(uid)
            if not u:
                continue
            Registration.query.filter_by(user_id=uid).delete()
            Attendance.query.filter_by(user_id=uid).delete()
            Score.query.filter_by(user_id=uid).delete()
            Notification.query.filter_by(user_id=uid).delete()
            UserSetting.query.filter_by(user_id=uid).delete()
            AuditLog.query.filter_by(user_id=uid).delete()
            AuditLog.query.filter_by(changed_by=uid).update({'changed_by': None})
            db.session.execute(db.text('DELETE FROM team_members WHERE user_id = :uid'), {'uid': uid})
            db.session.delete(u)

    db.session.commit()
    return jsonify({'success': True, 'affected': len(ids)})


@app.route('/admin/user-settings', methods=['GET', 'POST'])
@admin_required
def admin_user_settings():
    user = get_current_user()
    settings = UserSetting.query.filter_by(user_id=user.id).first()
    if not settings:
        settings = UserSetting(user_id=user.id)
        db.session.add(settings)
        db.session.commit()

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        college = request.form.get('college', '').strip()

        if first_name or email:
            if not first_name or not email:
                flash('First name and email are required.', 'danger')
                return render_template('admin/user_settings.html', user=user, settings=settings)

            existing = User.query.filter(User.email == email, User.id != user.id).first()
            if existing:
                flash('Email already in use.', 'danger')
                return render_template('admin/user_settings.html', user=user, settings=settings)

            user.first_name = first_name
            user.last_name = last_name
            user.name = f'{first_name} {last_name}'.strip()
            user.email = email
            user.college = college
            session['user_name'] = user.name

        settings.email_notifications = '1' in request.form.getlist('email_notifications')
        settings.theme = request.form.get('theme', 'light')
        settings.language = request.form.get('language', 'english')
        db.session.commit()
        flash('Settings saved successfully!', 'success')
        return redirect(url_for('admin_user_settings'))

    return render_template('admin/user_settings.html', user=user, settings=settings)


@app.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_system_settings():
    if request.method == 'POST':
        default_theme = request.form.get('default_theme', 'light')
        default_language = request.form.get('default_language', 'english')
        # Store in a system-level setting
        settings = SystemSetting.query.all()
        for key, val in [('default_theme', default_theme), ('default_language', default_language)]:
            s = SystemSetting.query.filter_by(key=key).first()
            if s:
                s.value = val
            else:
                s = SystemSetting(key=key, value=val)
                db.session.add(s)
        db.session.commit()
        flash('System settings saved!', 'success')
        return redirect(url_for('admin_system_settings'))
    settings_map = {s.key: s.value for s in SystemSetting.query.all()}
    return render_template('admin/settings.html', settings=settings_map, user=get_current_user())

# ─── Admin Profile ────────────────────────────────────────────────────────────

@app.route('/admin/profile', methods=['GET', 'POST'])
@admin_required
def admin_profile():
    user = get_current_user()
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        college = request.form.get('college', '').strip()

        if not first_name or not email:
            flash('First name and email are required.', 'danger')
            return render_template('admin/profile.html', user=user, edit_mode=True)

        existing = User.query.filter(User.email == email, User.id != user.id).first()
        if existing:
            flash('Email already in use.', 'danger')
            return render_template('admin/profile.html', user=user, edit_mode=True)

        user.first_name = first_name
        user.last_name = last_name
        user.name = f'{first_name} {last_name}'.strip()
        user.email = email
        user.college = college
        session['user_name'] = user.name
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('admin_profile'))

    edit_mode = request.args.get('edit', '0') == '1'
    return render_template('admin/profile.html', user=user, edit_mode=edit_mode)


# ─── Helper: Email Notification Service ─────────────────────────────────────

def send_html_email(recipient_email, subject, template_name, **context):
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        return
    try:
        context.setdefault('year', datetime.utcnow().year)
        context.setdefault('frontend_url', os.environ.get('FRONTEND_URL', 'http://localhost:5000'))
        html = render_template(f'email/{template_name}', **context)
        msg = Message(subject, recipients=[recipient_email], html=html)
        mail.send(msg)
    except Exception as e:
        print(f"Email send failed to {recipient_email}: {e}")


def notify_registration_confirmation(student, event):
    settings = UserSetting.query.filter_by(user_id=student.id).first()
    if settings and not settings.email_notifications:
        return
    organizer = User.query.get(event.created_by)
    organizer_name = organizer.name if organizer else 'Organizer'
    send_html_email(
        student.email,
        f"✅ You're registered for {event.title}",
        'event_registration_confirmation.html',
        student=student, event=event, organizer_name=organizer_name
    )


def notify_event_update_to_participants(event, changes):
    if not changes:
        return
    fields_changed = [c['field'] for c in changes]
    if 'venue' in fields_changed:
        subject = f"📍 Venue update for {event.title}"
    elif 'date' in fields_changed:
        subject = f"📅 Date changed for {event.title}"
    elif 'time' in fields_changed:
        subject = f"🕐 Time changed for {event.title}"
    else:
        subject = f"🔔 Update for {event.title} you registered for"
    for reg in event.registrations:
        u = User.query.get(reg.user_id)
        if not u:
            continue
        settings = UserSetting.query.filter_by(user_id=u.id).first()
        if settings and not settings.email_notifications:
            continue
        send_html_email(
            u.email, subject,
            'event_update_notification.html',
            user=u, event=event, changes=changes
        )


def notify_event_cancelled(event):
    for reg in event.registrations:
        u = User.query.get(reg.user_id)
        if not u:
            continue
        settings = UserSetting.query.filter_by(user_id=u.id).first()
        if settings and not settings.email_notifications:
            continue
        send_html_email(
            u.email,
            f"❌ {event.title} has been cancelled",
            'event_update_notification.html',
            user=u, event=event, changes=[{'field': 'cancelled', 'old_value': 'Scheduled', 'new_value': 'Cancelled'}]
        )


def notify_event_created(event, creator_name):
    admins = User.query.filter_by(role='admin').all()
    for admin in admins:
        if admin.id == event.created_by:
            continue
        settings = UserSetting.query.filter_by(user_id=admin.id).first()
        if settings and not settings.email_notifications:
            continue
        send_html_email(
            admin.email,
            f"🎉 New Event: {event.title}",
            'new_event_notification.html',
            admin=admin, event=event, creator_name=creator_name
        )


# ─── Student Routes ───────────────────────────────────────────────────────────

@app.route('/student/dashboard')
@login_required
def student_dashboard():
    user = get_current_user()
    upcoming = Event.query.filter(Event.date >= date.today()).order_by(Event.date).all()
    reg_ids = [r.event_id for r in Registration.query.filter_by(user_id=user.id).all()]
    present_count = Attendance.query.filter_by(user_id=user.id, status='present').count()
    return render_template('student/dashboard.html', user=user, events=upcoming,
        registered_ids=reg_ids, present_count=present_count, reg_count=len(reg_ids))

@app.route('/student/events')
@login_required
def student_events():
    user = get_current_user()
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    tab = request.args.get('tab', 'all')
    today = date.today()

    query = Event.query
    if search:
        query = query.filter(Event.title.ilike(f'%{search}%'))
    if category:
        query = query.filter_by(category=category)

    events = query.order_by(Event.date.desc()).all()

    if tab == 'upcoming':
        events = [e for e in events if e.date >= today]
    elif tab == 'past':
        events = [e for e in events if e.date < today]

    reg_ids = [r.event_id for r in Registration.query.filter_by(user_id=user.id).all()]
    reg_counts = {}
    for e in events:
        reg_counts[e.id] = Registration.query.filter_by(event_id=e.id).count()
    categories = db.session.query(Event.category).distinct().all()
    return render_template('student/events.html', events=events, user=user,
        registered_ids=reg_ids, reg_counts=reg_counts,
        categories=[c[0] for c in categories], search=search,
        selected_category=category, tab=tab, today=today)

@app.route('/student/events/<int:event_id>/register', methods=['POST'])
@login_required
def register_event(event_id):
    user = get_current_user()
    event = Event.query.get_or_404(event_id)
    existing = Registration.query.filter_by(user_id=user.id, event_id=event_id).first()
    if existing:
        flash('Already registered for this event.', 'warning')
    else:
        count = Registration.query.filter_by(event_id=event_id).count()
        if count >= event.max_participants:
            flash('Event is full. Registration closed.', 'danger')
        else:
            reg = Registration(user_id=user.id, event_id=event_id)
            db.session.add(reg)
            db.session.commit()
            flash(f'Successfully registered for "{event.title}"!', 'success')
            # Send registration confirmation email to student
            notify_registration_confirmation(user, event)
            # Notify organizer
            create_notification(event.created_by, 'registration',
                f'New registration: {event.title}',
                f'{user.name} has registered for "{event.title}".', event.id)
            socketio.emit('participant:registered', {
                'event_id': event.id,
                'event_title': event.title,
                'user_name': user.name
            }, room=f'event_{event.id}')
    return redirect(url_for('student_events'))

@app.route('/student/my-events')
@login_required
def my_events():
    user = get_current_user()
    regs = db.session.query(Registration, Event)\
        .join(Event, Registration.event_id == Event.id)\
        .filter(Registration.user_id == user.id)\
        .order_by(Event.date.desc()).all()
    attendance_map = {}
    for att in Attendance.query.filter_by(user_id=user.id).all():
        attendance_map[att.event_id] = att.status
    return render_template('student/my_events.html', user=user,
        registrations=regs, attendance_map=attendance_map, today=date.today())


@app.route('/student/events/<int:event_id>/deregister', methods=['POST'])
@login_required
def deregister_event(event_id):
    user = get_current_user()
    reg = Registration.query.filter_by(user_id=user.id, event_id=event_id).first()
    if not reg:
        flash('You are not registered for this event.', 'warning')
    else:
        event = Event.query.get(event_id)
        db.session.delete(reg)
        db.session.commit()
        if event:
            create_notification(event.created_by, 'event_update',
                f'Registration cancelled: {event.title}',
                f'{user.name} has cancelled their registration for "{event.title}".',
                event.id)
            socketio.emit('participant:deregistered', {
                'event_id': event.id,
                'event_title': event.title,
                'user_name': user.name
            }, room=f'event_{event.id}')
        flash('Registration cancelled successfully.', 'info')
    return redirect(url_for('my_events'))


@app.route('/student/event/<int:event_id>')
@login_required
def student_event_detail(event_id):
    user = get_current_user()
    event = Event.query.get_or_404(event_id)
    reg_ids = [r.event_id for r in Registration.query.filter_by(user_id=user.id).all()]
    reg_count = len(event.registrations)
    organizer = User.query.get(event.created_by) if event.created_by else None
    tag_list = [t for t in event.tags.split(',') if t] if event.tags else []
    return render_template('student/event_detail.html', user=user, event=event,
        registered_ids=reg_ids, reg_count=reg_count, organizer=organizer,
        tags=tag_list, today=date.today())


@app.route('/api/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notif_id):
    notif = Notification.query.get_or_404(notif_id)
    if notif.user_id != session['user_id']:
        return jsonify({'error': 'Permission denied'}), 403
    notif.is_read = True
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/notifications/read-all', methods=['POST'])
@login_required
def mark_all_notifications_read():
    Notification.query.filter_by(user_id=session['user_id'], is_read=False)\
        .update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/notifications/unread-count')
@login_required
def unread_notification_count():
    count = Notification.query.filter_by(user_id=session['user_id'], is_read=False).count()
    return jsonify({'count': count})


@app.route('/student/profile', methods=['GET', 'POST'])
@login_required
def student_profile():
    user = get_current_user()
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        college = request.form.get('college', '').strip()
        department = request.form.get('department', '').strip()
        reg_number = request.form.get('reg_number', '').strip()
        phone = request.form.get('phone', '').strip()
        year_raw = request.form.get('year_of_study', '')
        year_of_study = int(year_raw) if year_raw and year_raw.isdigit() else None
        github_url = request.form.get('github_url', '').strip()
        linkedin_url = request.form.get('linkedin_url', '').strip()
        if not first_name or not email:
            flash('First name and email are required.', 'danger')
            return render_template('student/profile.html', user=user, edit_mode=True)
        user.first_name = first_name
        user.last_name = last_name
        user.name = f'{first_name} {last_name}'.strip()
        user.email = email
        user.college = college
        user.department = department
        user.reg_number = reg_number
        user.phone = phone
        user.year_of_study = year_of_study
        user.github_url = github_url
        user.linkedin_url = linkedin_url
        session['user_name'] = user.name
        db.session.commit()
        flash('Profile updated successfully!', 'success')
        return redirect(url_for('student_profile'))
    edit_mode = request.args.get('edit', '0') == '1'
    total_events = len(user.registrations)
    present_count = Attendance.query.filter_by(user_id=user.id, status='present').count()
    return render_template('student/profile.html', user=user, edit_mode=edit_mode,
        total_events=total_events, present_count=present_count)


@app.route('/student/settings', methods=['GET', 'POST'])
@login_required
def student_settings():
    user = get_current_user()
    settings = UserSetting.query.filter_by(user_id=user.id).first()
    if not settings:
        settings = UserSetting(user_id=user.id)
        db.session.add(settings)
        db.session.commit()

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        college = request.form.get('college', '').strip()

        if first_name or email:
            if not first_name or not email:
                flash('First name and email are required.', 'danger')
                return render_template('student/settings.html', user=user, settings=settings)

            existing = User.query.filter(User.email == email, User.id != user.id).first()
            if existing:
                flash('Email already in use.', 'danger')
                return render_template('student/settings.html', user=user, settings=settings)

            user.first_name = first_name
            user.last_name = last_name
            user.name = f'{first_name} {last_name}'.strip()
            user.email = email
            user.college = college
            session['user_name'] = user.name

        settings.email_notifications = '1' in request.form.getlist('email_notifications')
        settings.theme = request.form.get('theme', 'light')
        settings.language = request.form.get('language', 'english')
        db.session.commit()
        flash('Settings saved successfully!', 'success')
        return redirect(url_for('student_settings'))

    return render_template('student/settings.html', user=user, settings=settings)


# ─── Organizer: Participant Management ──────────────────────────────────────

@app.route('/organizer/events/<int:event_id>/participants')
@organizer_required
def organizer_event_participants(event_id):
    user = get_current_user()
    event = Event.query.get_or_404(event_id)
    if user.id != event.created_by and user.role not in ('admin', 'organizer'):
        flash('Permission denied.', 'danger')
        return redirect(url_for('organizer_events'))
    search = request.args.get('search', '')
    registrations = db.session.query(Registration, User)\
        .join(User, Registration.user_id == User.id)\
        .filter(Registration.event_id == event_id)
    if search:
        registrations = registrations.filter(db.or_(
            User.name.ilike(f'%{search}%'),
            User.email.ilike(f'%{search}%'),
            User.college.ilike(f'%{search}%')
        ))
    registrations = registrations.order_by(Registration.registered_at).all()
    return render_template('organizer/participants.html', user=user, event=event,
        registrations=registrations, search=search)


@app.route('/organizer/events/<int:event_id>/participants/export')
@organizer_required
def organizer_export_participants(event_id):
    user = get_current_user()
    event = Event.query.get_or_404(event_id)
    if user.id != event.created_by and user.role not in ('admin', 'organizer'):
        flash('Permission denied.', 'danger')
        return redirect(url_for('organizer_events'))
    registrations = db.session.query(Registration, User)\
        .join(User, Registration.user_id == User.id)\
        .filter(Registration.event_id == event_id)\
        .order_by(Registration.registered_at).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Participant ID', 'Name', 'Email', 'College', 'Department', 'Registration Date'])
    for reg, stu in registrations:
        writer.writerow([stu.participant_id or '', stu.name, stu.email, stu.college or '',
            stu.department or '', reg.registered_at.strftime('%Y-%m-%d %H:%M')])
    output.seek(0)
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        as_attachment=True,
        download_name=f'participants_{event.title.replace(" ","_")}.csv',
        mimetype='text/csv'
    )


@app.route('/organizer/events/<int:event_id>/participants/<int:uid>/remove', methods=['POST'])
@organizer_required
def organizer_remove_participant(event_id, uid):
    user = get_current_user()
    event = Event.query.get_or_404(event_id)
    if user.id != event.created_by and user.role not in ('admin', 'organizer'):
        return jsonify({'error': 'Permission denied'}), 403
    reg = Registration.query.filter_by(user_id=uid, event_id=event_id).first()
    if not reg:
        return jsonify({'error': 'Registration not found'}), 404
    participant = User.query.get(uid)
    db.session.delete(reg)
    if participant:
        create_notification(uid, 'event_update',
            f'Removed from {event.title}',
            f'You have been removed from the event "{event.title}" by the organizer.')
    db.session.commit()
    flash(f'Participant removed.', 'info')
    return redirect(url_for('organizer_event_participants', event_id=event_id))


# ─── Organizer Routes ────────────────────────────────────────────────────────

@app.route('/organizer/dashboard')
@organizer_required
def organizer_dashboard():
    user = get_current_user()
    all_events = Event.query.filter_by(created_by=user.id).order_by(Event.date).all()
    today = date.today()
    tomorrow = today + timedelta(days=1)

    total_registrations = sum(len(e.registrations) for e in all_events)
    active_events = [e for e in all_events if e.date == today]
    upcoming_events_list = [e for e in all_events if e.date >= tomorrow]

    # Status badges calculated in template, pass today/tomorrow
    return render_template('organizer/dashboard.html', user=user,
        events=all_events, total_events=len(all_events),
        total_registrations=total_registrations,
        active_events=len(active_events),
        upcoming_count=len(upcoming_events_list),
        today=today, tomorrow=tomorrow)


@app.route('/organizer/events')
@organizer_required
def organizer_events():
    user = get_current_user()
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    tab = request.args.get('tab', 'all')
    today = date.today()

    query = Event.query
    if search:
        query = query.filter(Event.title.ilike(f'%{search}%'))
    if category:
        query = query.filter_by(category=category)

    events = query.order_by(Event.date.desc()).all()

    if tab == 'upcoming':
        events = [e for e in events if e.date >= today]
    elif tab == 'past':
        events = [e for e in events if e.date < today]

    categories = db.session.query(Event.category).distinct().all()
    reg_counts = {}
    for e in events:
        reg_counts[e.id] = len(e.registrations)

    return render_template('organizer/events.html', user=user, events=events,
        categories=[c[0] for c in categories], search=search,
        selected_category=category, today=today, reg_counts=reg_counts, tab=tab)


@app.route('/organizer/analytics')
@organizer_required
def organizer_analytics():
    event_analytics = get_event_analytics()
    category_stats = get_category_stats()

    cat_labels = [s.category for s in category_stats]
    cat_counts = [s.count for s in category_stats]

    event_analytics_json = [
        {
            "category": ea.category,
            "registrations": ea.total_registrations,
            "present": ea.total_present,
            "absent": ea.total_absent,
        }
        for ea in event_analytics
    ]

    return render_template(
        "admin/analytics.html",
        event_analytics=event_analytics,
        cat_labels=cat_labels,
        cat_counts=cat_counts,
        event_analytics_json=event_analytics_json,
    )


@app.route('/organizer/announcements', methods=['GET', 'POST'])
@organizer_required
def organizer_announcements():
    if request.method == 'POST':
        message  = request.form.get('message', '')
        priority = request.form.get('priority', 'info')

        try:
            create_announcement(
                message=message,
                priority=priority,
                author_id=session['user_id'],
            )
            flash('Announcement broadcast to all connected users.', 'success')
        except ValueError as exc:
            flash(str(exc), 'danger')

        return redirect(url_for('organizer_announcements'))

    session['ann_last_seen'] = mark_all_read()

    return render_template(
        'admin/announcements.html',
        announcements=get_all_announcements(),
        current_role=session.get('role'),
        current_user_id=session.get('user_id'),
    )


@app.route('/organizer/user-settings', methods=['GET', 'POST'])
@organizer_required
def organizer_user_settings():
    user = get_current_user()
    settings = UserSetting.query.filter_by(user_id=user.id).first()
    if not settings:
        settings = UserSetting(user_id=user.id)
        db.session.add(settings)
        db.session.commit()

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        college = request.form.get('college', '').strip()

        if first_name or email:
            if not first_name or not email:
                flash('First name and email are required.', 'danger')
                return render_template('organizer/user_settings.html', user=user, settings=settings)

            existing = User.query.filter(User.email == email, User.id != user.id).first()
            if existing:
                flash('Email already in use.', 'danger')
                return render_template('organizer/user_settings.html', user=user, settings=settings)

            user.first_name = first_name
            user.last_name = last_name
            user.name = f'{first_name} {last_name}'.strip()
            user.email = email
            user.college = college
            session['user_name'] = user.name

        settings.email_notifications = '1' in request.form.getlist('email_notifications')
        settings.theme = request.form.get('theme', 'light')
        settings.language = request.form.get('language', 'english')
        db.session.commit()
        flash('Settings saved successfully!', 'success')
        return redirect(url_for('organizer_user_settings'))

    return render_template('organizer/user_settings.html', user=user, settings=settings)


@app.route('/events/create', methods=['GET', 'POST'])
@organizer_required
def organizer_create_event():
    user = get_current_user()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        event_date_str = request.form.get('date', '')
        time_str = request.form.get('time', '')
        venue = request.form.get('venue', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', 'General')
        max_p_str = request.form.get('max_participants', '')
        image_url = request.form.get('image_url', '').strip()
        tags_raw = request.form.get('tags', '')

        if not title or not event_date_str:
            flash('Title and date are required.', 'danger')
            return render_template('organizer/event_form.html', event=None, user=user, event_time='', tags=[])

        try:
            event_date = datetime.strptime(event_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format.', 'danger')
            return render_template('organizer/event_form.html', event=None, user=user, event_time=time_str, tags=[])

        try:
            max_participants = int(max_p_str) if max_p_str else 100
        except (ValueError, TypeError):
            max_participants = 100

        # PDF upload
        pdf_filename = None
        if 'pdf_file' in request.files:
            file = request.files['pdf_file']
            if file and file.filename and allowed_file(file.filename):
                original_name = secure_filename(file.filename)
                ext = original_name.rsplit('.', 1)[1].lower() if '.' in original_name else 'pdf'
                pdf_filename = f'{secrets.token_hex(8)}--{original_name}'
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename))
            elif file and file.filename and not allowed_file(file.filename):
                flash('Only PDF files are allowed.', 'danger')

        # Conflict detection (warning only — event still created)
        conflicts = Event.query.filter_by(date=event_date, venue=venue).all()
        if conflicts and venue:
            flash(f'⚠️ Conflict detected: "{conflicts[0].title}" is already scheduled at {venue} on this date.', 'warning')

        tag_list = [t.strip() for t in tags_raw.replace('\n', ',').split(',') if t.strip()]

        event = Event(
            title=title, date=event_date, time=time_str, venue=venue,
            description=description, category=category,
            max_participants=max_participants,
            image_url=image_url, tags=','.join(tag_list),
            pdf_file=pdf_filename,
            organizer_name=user.name,
            created_by=user.id
        )
        db.session.add(event)
        db.session.commit()
        from app.services.notifications import notify_new_event
        notify_new_event(
            title=event.title,
            date=event.date.strftime("%d %b %Y"),
            venue=getattr(event, "venue", None) or "TBD",
        )
        notify_event_created(event, user.name)
        socketio.emit('event:created', {
            'id': event.id,
            'title': event.title,
            'description': event.description[:100] if event.description else '',
            'date': event.date.strftime('%Y-%m-%d'),
            'date_display': event.date.strftime('%d %B %Y'),
            'time': event.time or '',
            'venue': event.venue or '',
            'category': event.category,
            'image_url': event.image_url or '',
            'pdf_file': event.pdf_file or '',
            'max_participants': event.max_participants,
            'tags': event.tags or '',
            'reg_count': 0
        })
        flash('Event created successfully!', 'success')
        return redirect(url_for('organizer_events'))
    return render_template('organizer/event_form.html', event=None, user=user, event_time='', tags=[])


@app.route('/events/<int:event_id>/edit', methods=['GET', 'POST'])
@organizer_required
def organizer_edit_event(event_id):
    user = get_current_user()
    event = Event.query.get_or_404(event_id)

    # Auth check
    if user.id != event.created_by and user.role not in ('admin', 'organizer'):
        flash('You do not have permission to edit this event.', 'danger')
        return redirect(url_for('organizer_events'))

    if request.method == 'POST':
        old_title = event.title
        old_date = event.date
        old_time = event.time
        old_venue = event.venue
        old_category = event.category

        event.title = request.form.get('title', '').strip()
        try:
            event.date = datetime.strptime(request.form.get('date'), '%Y-%m-%d').date()
        except (ValueError, TypeError):
            flash('Invalid date format.', 'danger')
            return redirect(url_for('organizer_edit_event', event_id=event.id))
        event.time = request.form.get('time', '')
        event.venue = request.form.get('venue', '').strip()
        event.description = request.form.get('description', '').strip()
        event.category = request.form.get('category', 'General')
        max_p_str = request.form.get('max_participants', '')
        try:
            event.max_participants = int(max_p_str) if max_p_str else event.max_participants
        except (ValueError, TypeError):
            pass
        event.image_url = request.form.get('image_url', '').strip()
        tags_raw = request.form.get('tags', '')
        tag_list = [t.strip() for t in tags_raw.replace('\n', ',').split(',') if t.strip()]
        event.tags = ','.join(tag_list)
        db.session.commit()

        changes = []
        if event.title != old_title:
            changes.append({'field': 'title', 'old_value': old_title, 'new_value': event.title})
        if event.date != old_date:
            changes.append({'field': 'date', 'old_value': old_date.strftime('%d %b %Y'), 'new_value': event.date.strftime('%d %b %Y')})
        if event.time != old_time:
            changes.append({'field': 'time', 'old_value': old_time or 'TBD', 'new_value': event.time or 'TBD'})
        if event.venue != old_venue:
            changes.append({'field': 'venue', 'old_value': old_venue or 'TBD', 'new_value': event.venue or 'TBD'})
        if event.category != old_category:
            changes.append({'field': 'category', 'old_value': old_category, 'new_value': event.category})
        if changes:
            notify_event_update_to_participants(event, changes)

        socketio.emit('event:updated', {
            'id': event.id,
            'title': event.title,
            'description': event.description[:100] if event.description else '',
            'date': event.date.strftime('%Y-%m-%d'),
            'date_display': event.date.strftime('%d %B %Y'),
            'time': event.time or '',
            'venue': event.venue or '',
            'category': event.category,
            'image_url': event.image_url or '',
            'pdf_file': event.pdf_file or '',
            'max_participants': event.max_participants,
            'tags': event.tags or '',
        })

        flash('Event updated successfully!', 'success')
        return redirect(url_for('organizer_events'))

    tag_list = [t for t in event.tags.split(',') if t] if event.tags else []
    event_time = event.time if event.time else ''
    return render_template('organizer/event_form.html', event=event, user=user, tags=tag_list, event_time=event_time)


@app.route('/events/<int:event_id>/delete', methods=['POST'])
@organizer_required
def organizer_delete_event(event_id):
    user = get_current_user()
    event = Event.query.get_or_404(event_id)
    if user.id != event.created_by and user.role not in ('admin', 'organizer'):
        flash('Permission denied.', 'danger')
        return redirect(url_for('organizer_events'))
    # Notify registered students before deleting
    notify_event_cancelled(event)
    socketio.emit('event:deleted', {'id': event.id, 'title': event.title})
    Registration.query.filter_by(event_id=event_id).delete()
    Attendance.query.filter_by(event_id=event_id).delete()
    Score.query.filter_by(event_id=event_id).delete()
    db.session.delete(event)
    db.session.commit()
    flash('Event deleted.', 'info')
    return redirect(url_for('organizer_events'))


# ─── Organizer API Profile ───────────────────────────────────────────────────

@app.route('/api/profile')
@organizer_required
def api_get_profile():
    user = get_current_user()
    return jsonify({
        'id': user.id, 'name': user.name,
        'first_name': user.first_name or user.name.split()[0] if user.name else '',
        'last_name': user.last_name or ' '.join(user.name.split()[1:]) if user.name and len(user.name.split()) > 1 else '',
        'email': user.email, 'college': user.college or '',
        'department': user.department or '', 'role': user.role
    })


@app.route('/api/settings', methods=['GET', 'POST'])
@login_required
def api_settings():
    user = get_current_user()
    settings = UserSetting.query.filter_by(user_id=user.id).first()
    if not settings:
        settings = UserSetting(user_id=user.id)
        db.session.add(settings)
        db.session.commit()

    if request.method == 'POST':
        data = request.get_json()
        if data:
            if 'email_notifications' in data:
                settings.email_notifications = data['email_notifications']
            if 'theme' in data:
                settings.theme = data['theme']
            if 'language' in data:
                settings.language = data['language']
            db.session.commit()
            return jsonify({'success': True, 'message': 'Settings saved!'})
        return jsonify({'error': 'Invalid data'}), 400

    return jsonify({
        'email_notifications': settings.email_notifications,
        'theme': settings.theme,
        'language': settings.language
    })


@app.route('/student/certificate/<int:event_id>')
@login_required
def download_certificate(event_id):
    user = get_current_user()
    event = Event.query.get_or_404(event_id)
    att = Attendance.query.filter_by(user_id=user.id, event_id=event_id, status='present').first()
    if not att:
        flash('Certificate not available. Attendance not marked as present.', 'danger')
        return redirect(url_for('my_events'))
    try:
        pdf_buffer = generate_certificate(user, event)
        safe_name = re.sub(r'[^\w\s-]', '', event.title).strip().replace(' ', '_')
        safe_user = re.sub(r'[^\w\s-]', '', user.name).strip().replace(' ', '_')
        return send_file(pdf_buffer, as_attachment=True,
            download_name=f'Certificate_{safe_user}_{safe_name}.pdf',
            mimetype='application/pdf')
    except Exception as e:
        current_app.logger.error(f'Certificate generation failed for event {event_id}, user {user.id}: {e}')
        flash('Could not generate certificate. Please try again later.', 'danger')
        return redirect(url_for('my_events'))

# ─── Certificate Generation ───────────────────────────────────────────────────

def generate_certificate(user, event):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm, cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader

    buffer = io.BytesIO()
    page_width, page_height = landscape(A4)

    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    W, H = page_width, page_height

    # Background
    c.setFillColor(colors.HexColor('#FAFAF8'))
    c.rect(0, 0, W, H, fill=1, stroke=0)

    # Outer border (navy gold double border)
    border_margin = 18
    c.setStrokeColor(colors.HexColor('#1a3a6b'))
    c.setLineWidth(6)
    c.rect(border_margin, border_margin, W - 2*border_margin, H - 2*border_margin, fill=0)
    c.setStrokeColor(colors.HexColor('#C9A84C'))
    c.setLineWidth(2)
    c.rect(border_margin + 8, border_margin + 8, W - 2*(border_margin+8), H - 2*(border_margin+8), fill=0)

    # Gold top and bottom decorative band
    c.setFillColor(colors.HexColor('#1a3a6b'))
    c.rect(border_margin, H - border_margin - 48, W - 2*border_margin, 48, fill=1, stroke=0)
    c.rect(border_margin, border_margin, W - 2*border_margin, 48, fill=1, stroke=0)

    c.setFillColor(colors.HexColor('#C9A84C'))
    c.rect(border_margin, H - border_margin - 52, W - 2*border_margin, 4, fill=1, stroke=0)
    c.rect(border_margin, border_margin + 48, W - 2*border_margin, 4, fill=1, stroke=0)

    # University name in top band
    c.setFillColor(colors.HexColor('#FFFFFF'))
    c.setFont('Helvetica-Bold', 11)
    c.drawCentredString(W/2, H - border_margin - 30, 'SATHYABAMA INSTITUTE OF SCIENCE AND TECHNOLOGY')
    c.setFont('Helvetica', 9)
    c.drawCentredString(W/2, H - border_margin - 44, 'Deemed to be University | Accredited with "A+" Grade by NAAC')

    # Bottom band text
    c.setFillColor(colors.HexColor('#C9A84C'))
    c.setFont('Helvetica-Bold', 9)
    c.drawCentredString(W/2, border_margin + 18, 'Jeppiaar Nagar, Rajiv Gandhi Salai, Chennai - 600 119, Tamil Nadu, India')

    # Logo
    logo_path = os.path.join(os.path.dirname(__file__), 'static', 'images', 'sist_logo.png')
    if os.path.exists(logo_path):
        c.drawImage(logo_path, W/2 - 35, H - border_margin - 140, width=70, height=70)

    # Certificate title
    c.setFillColor(colors.HexColor('#C9A84C'))
    c.setFont('Helvetica-Bold', 28)
    c.drawCentredString(W/2, H - border_margin - 175, 'CERTIFICATE OF PARTICIPATION')

    # Decorative line
    c.setStrokeColor(colors.HexColor('#C9A84C'))
    c.setLineWidth(1.5)
    c.line(W/2 - 150, H - border_margin - 185, W/2 + 150, H - border_margin - 185)

    # Body text
    c.setFillColor(colors.HexColor('#2c2c2c'))
    c.setFont('Helvetica', 13)
    c.drawCentredString(W/2, H - border_margin - 215, 'This is to certify that')

    # Student name
    c.setFillColor(colors.HexColor('#1a3a6b'))
    c.setFont('Helvetica-Bold', 26)
    c.drawCentredString(W/2, H - border_margin - 250, user.name.upper())

    # Underline for name
    name_width = c.stringWidth(user.name.upper(), 'Helvetica-Bold', 26)
    c.setStrokeColor(colors.HexColor('#C9A84C'))
    c.setLineWidth(1)
    c.line(W/2 - name_width/2, H - border_margin - 255, W/2 + name_width/2, H - border_margin - 255)

    # Details
    c.setFillColor(colors.HexColor('#2c2c2c'))
    c.setFont('Helvetica', 13)
    dept_text = f'({user.department or "Student"}{", " + user.reg_number if user.reg_number else ""})'
    c.drawCentredString(W/2, H - border_margin - 275, dept_text)

    c.setFont('Helvetica', 13)
    c.drawCentredString(W/2, H - border_margin - 305,
        'has successfully participated in the event')

    # Event name
    c.setFillColor(colors.HexColor('#1a3a6b'))
    c.setFont('Helvetica-Bold', 20)
    c.drawCentredString(W/2, H - border_margin - 335, f'"{event.title}"')

    # Date and venue
    c.setFillColor(colors.HexColor('#2c2c2c'))
    c.setFont('Helvetica', 12)
    date_str = event.date.strftime('%d %B %Y')
    venue_info = f'held on {date_str}'
    if event.venue:
        venue_info += f' at {event.venue}'
    c.drawCentredString(W/2, H - border_margin - 360, venue_info)

    # Signatures
    signatories = CertificateSignatory.query.filter_by(event_id=event.id).order_by(CertificateSignatory.ordering).all()
    sig_y = border_margin + 90
    if signatories:
        n = len(signatories)
        for i, sig in enumerate(signatories):
            cx = (i + 1) * W / (n + 1)
            if sig.signature_image:
                sig_img_path = os.path.join(SIGNATURE_FOLDER, sig.signature_image)
                if os.path.exists(sig_img_path):
                    try:
                        from reportlab.lib.utils import ImageReader
                        sig_img = ImageReader(sig_img_path)
                        img_w, img_h = sig_img.getSize()
                        max_w = 120
                        max_h = 45
                        scale = min(max_w / img_w if img_w else 1, max_h / img_h if img_h else 1)
                        dw, dh = img_w * scale, img_h * scale
                        c.drawImage(sig_img, cx - dw/2, sig_y + 27, width=dw, height=dh)
                    except Exception:
                        pass
            c.setStrokeColor(colors.HexColor('#888888'))
            c.setLineWidth(0.8)
            c.line(cx - 60, sig_y + 25, cx + 60, sig_y + 25)
            c.setFillColor(colors.HexColor('#2c2c2c'))
            c.setFont('Helvetica-Bold', 10)
            c.drawCentredString(cx, sig_y + 8, sig.title)
            c.setFont('Helvetica', 9)
            c.setFillColor(colors.HexColor('#555555'))
            c.drawCentredString(cx, sig_y - 6, sig.name)
    else:
        c.setFillColor(colors.HexColor('#2c2c2c'))
        c.setStrokeColor(colors.HexColor('#888888'))
        c.setLineWidth(0.8)
        c.line(W/4 - 50, sig_y + 25, W/4 + 50, sig_y + 25)
        c.setFont('Helvetica-Bold', 10)
        c.drawCentredString(W/4, sig_y + 8, 'Event Coordinator')
        c.setFont('Helvetica', 9)
        c.setFillColor(colors.HexColor('#555555'))
        c.drawCentredString(W/4, sig_y - 6, 'Sathyabama Institute of Science')
        c.drawCentredString(W/4, sig_y - 18, 'and Technology')

        c.setFillColor(colors.HexColor('#2c2c2c'))
        c.line(3*W/4 - 50, sig_y + 25, 3*W/4 + 50, sig_y + 25)
        c.setFont('Helvetica-Bold', 10)
        c.drawCentredString(3*W/4, sig_y + 8, 'The Vice Chancellor')
        c.setFont('Helvetica', 9)
        c.setFillColor(colors.HexColor('#555555'))
        c.drawCentredString(3*W/4, sig_y - 6, 'Sathyabama Institute of Science')
        c.drawCentredString(3*W/4, sig_y - 18, 'and Technology')

    # Certificate number
    c.setFillColor(colors.HexColor('#888888'))
    c.setFont('Helvetica', 8)
    cert_no = f'SIST/CERT/{event.id:04d}/{user.id:04d}'
    c.drawString(border_margin + 16, border_margin + 60, f'Certificate No: {cert_no}')
    c.drawRightString(W - border_margin - 16, border_margin + 60,
        f'Issue Date: {datetime.now().strftime("%d %B %Y")}')

    c.save()
    buffer.seek(0)
    return buffer

# ─── API endpoints (for AJAX) ─────────────────────────────────────────────────

@app.route('/api/events/<int:event_id>/registrations')
@admin_required
def api_event_registrations(event_id):
    regs = db.session.query(Registration, User)\
        .join(User, Registration.user_id == User.id)\
        .filter(Registration.event_id == event_id).all()
    return jsonify([{
        'id': u.id, 'name': u.name, 'email': u.email,
        'participant_id': u.participant_id,
        'reg_number': u.reg_number, 'department': u.department
    } for _, u in regs])

@app.route('/api/notifications')
@login_required
def api_notifications():
    user = get_current_user()
    notes = []
    if user.role == 'student':
        new_events = Event.query.filter(Event.date >= date.today())\
            .order_by(Event.created_at.desc()).limit(3).all()
        for e in new_events:
            notes.append({'msg': f'New event: {e.title} on {e.date.strftime("%d %b %Y")}', 'type': 'info'})
        certs = db.session.query(Attendance, Event)\
            .join(Event, Attendance.event_id == Event.id)\
            .filter(Attendance.user_id == user.id, Attendance.status == 'present').all()
        for att, e in certs:
            notes.append({'msg': f'Certificate ready for {e.title}!', 'type': 'success'})
    return jsonify(notes)

@app.route('/api/events/<int:event_id>/charts')
@admin_required
def api_event_charts(event_id):
    event = Event.query.get_or_404(event_id)
    regs = Registration.query.filter_by(event_id=event_id).all()
    reg_count = len(regs)
    present = Attendance.query.filter_by(event_id=event_id, status='present').count()
    absent = reg_count - present

    college_data = db.session.query(User.college, db.func.count(Registration.id))\
        .join(Registration, User.id == Registration.user_id)\
        .filter(Registration.event_id == event_id)\
        .group_by(User.college).all()

    dept_data = db.session.query(User.department, db.func.count(Registration.id))\
        .join(Registration, User.id == Registration.user_id)\
        .filter(Registration.event_id == event_id)\
        .group_by(User.department).all()

    registration_dates = db.session.query(
        db.func.date(Registration.registered_at).label('day'),
        db.func.count(Registration.id).label('count')
    ).filter(Registration.event_id == event_id)\
     .group_by(db.func.date(Registration.registered_at))\
     .order_by('day').all()

    return jsonify({
        'reg_count': reg_count,
        'present': present,
        'absent': absent,
        'capacity': event.max_participants,
        'college_data': [{'label': c or 'N/A', 'count': n} for c, n in college_data],
        'dept_data': [{'label': d or 'N/A', 'count': n} for d, n in dept_data],
        'registration_trend': [{'day': str(d), 'count': n} for d, n in registration_dates],
    })

# ─── Serve uploaded PDFs ──────────────────────────────────────────────────────────

@app.route('/static/uploads/<filename>')
def serve_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ─── Init DB ──────────────────────────────────────────────────────────────────

def init_db():
    with app.app_context():
        db.create_all()

        # Backfill participant_id for existing users
        existing = User.query.filter(User.participant_id.is_(None)).all()
        if existing:
            for u in existing:
                college_code = get_college_code(u.college)
                u.participant_id = generate_participant_id(college_code)
            db.session.commit()
            print(f"   Backfilled participant_id for {len(existing)} user(s).")
        # Create default admin
        admin_id = None
        if not User.query.filter_by(email='admin@sist.ac.in').first():
            admin = User(
                name='Admin SIST', first_name='Admin', last_name='SIST',
                email='admin@sist.ac.in',
                password=generate_password_hash('admin123'),
                role='admin',
                college='Sathyabama Institute of Science and Technology',
                participant_id=generate_participant_id()
            )
            db.session.add(admin)
            db.session.flush()
            admin_id = admin.id
        else:
            admin_id = User.query.filter_by(email='admin@sist.ac.in').first().id

        # Create demo student
        student_id = None
        if not User.query.filter_by(email='student@sist.ac.in').first():
            student = User(
                name='Demo Student', first_name='Demo', last_name='Student',
                email='student@sist.ac.in',
                password=generate_password_hash('student123'),
                role='student',
                reg_number='SIST2024001',
                department='Computer Science Engineering',
                college='Sathyabama Institute of Science and Technology',
                participant_id=generate_participant_id()
            )
            db.session.add(student)
            db.session.flush()
            student_id = student.id
        else:
            student_id = User.query.filter_by(email='student@sist.ac.in').first().id

        # Create demo organizer
        org_id = None
        if not User.query.filter_by(email='organizer@sist.ac.in').first():
            org = User(
                name='Dr. Rajesh Kumar', first_name='Rajesh', last_name='Kumar',
                email='organizer@sist.ac.in',
                password=generate_password_hash('organizer123'),
                role='organizer',
                department='Computer Science Engineering',
                college='Sathyabama Institute of Science and Technology',
                participant_id=generate_participant_id()
            )
            db.session.add(org)
            db.session.flush()
            org_id = org.id
        else:
            org_id = User.query.filter_by(email='organizer@sist.ac.in').first().id

        # Sample events
        if Event.query.count() == 0:
            sample_events = [
                Event(title='Annual Tech Fest 2025', date=date.today() + timedelta(days=10),
                    time='09:00 AM', venue='Main Auditorium', category='Technical',
                    description='Annual technical festival with competitions and workshops.',
                    tags='technology,competition,workshop',
                    image_url='https://images.unsplash.com/photo-1540575467063-178a50c2df87?w=400',
                    organizer_name='Dr. Rajesh Kumar', created_by=org_id),
                Event(title='Cultural Night', date=date.today() + timedelta(days=15),
                    time='06:00 PM', venue='Open Air Theatre', category='Cultural',
                    description='A night of music, dance, and cultural performances.',
                    tags='cultural,music,dance',
                    image_url='https://images.unsplash.com/photo-1493225457124-a3eb161ffa5f?w=400',
                    organizer_name='Dr. Rajesh Kumar', created_by=org_id),
                Event(title='Hackathon 24H', date=date.today() + timedelta(days=5),
                    time='10:00 AM', venue='CS Block Lab', category='Technical',
                    description='24-hour coding hackathon for innovative solutions.',
                    tags='hackathon,coding,innovation', max_participants=50,
                    image_url='https://images.unsplash.com/photo-1504384308090-c894fdcc538d?w=400',
                    organizer_name='Admin SIST', created_by=admin_id),
                Event(title='Sports Day', date=date.today() + timedelta(days=20),
                    time='07:00 AM', venue='Sports Ground', category='Sports',
                    description='Annual inter-department sports competitions.',
                    tags='sports,competition,team', max_participants=200,
                    organizer_name='Admin SIST', created_by=admin_id),
                Event(title='AI Workshop', date=date.today() + timedelta(days=3),
                    time='02:00 PM', venue='AI Lab', category='Workshop',
                    description='Hands-on workshop on artificial intelligence and machine learning.',
                    tags='AI,machine learning,workshop', max_participants=30,
                    image_url='https://images.unsplash.com/photo-1677442136019-21780ecad995?w=400',
                    organizer_name='Dr. Rajesh Kumar', created_by=org_id),
            ]
            for e in sample_events:
                db.session.add(e)
            db.session.flush()

            # Register student for some events
            all_events = Event.query.all()
            if student_id and all_events:
                for ev in all_events[:3]:
                    if not Registration.query.filter_by(user_id=student_id, event_id=ev.id).first():
                        db.session.add(Registration(user_id=student_id, event_id=ev.id))

            # Sample announcements
            if Announcement.query.count() == 0:
                sample_ann = [
                    Announcement(message='Welcome to CampusCore! Stay tuned for exciting events!',
                        created_by=admin_id),
                    Announcement(message='Tech Fest 2025 registration is now open. Limited seats available!',
                        created_by=org_id),
                    Announcement(message='AI workshop schedule has been updated. Check event details.',
                        created_by=org_id),
                ]
                for a in sample_ann:
                    db.session.add(a)

            # Sample scores
            if Score.query.count() == 0 and student_id and all_events:
                for ev in all_events[:2]:
                    score = Score(
                        user_id=student_id, event_id=ev.id,
                        points=95, reason='First Place - Best Innovation'
                    )
                    db.session.add(score)

            # Settings
            if not UserSetting.query.filter_by(user_id=admin_id).first():
                db.session.add(UserSetting(user_id=admin_id))
            if org_id and not UserSetting.query.filter_by(user_id=org_id).first():
                db.session.add(UserSetting(user_id=org_id))

        # Sample teams (always check, not inside events block)
        if Team.query.count() == 0:
            team1 = Team(name='Tech Titans', description='Competitive coding team',
                created_by=org_id or admin_id)
            team2 = Team(name='Innovators Hub', description='Project development team',
                created_by=admin_id)
            db.session.add_all([team1, team2])
            db.session.flush()
            if student_id:
                from app.models.team import team_members
                db.session.execute(team_members.insert().values(
                    team_id=team1.id, user_id=student_id
                ))
                db.session.execute(team_members.insert().values(
                    team_id=team2.id, user_id=student_id
                ))

        db.session.commit()
        print("✅ Database initialized with demo data.")
        print("   Admin: admin@sist.ac.in / admin123")
        print("   Organizer: organizer@sist.ac.in / organizer123")
        print("   Student: student@sist.ac.in / student123")

if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)
