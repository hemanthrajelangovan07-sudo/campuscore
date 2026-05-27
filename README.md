# CampusCore — SIST Event Management Portal

A full-stack web application for managing college events at **Sathyabama Institute of Science and Technology**.

---

## 📁 Folder Structure

```
campuscore/
├── app.py                  # Main Flask application (routes, models, logic)
├── run.py                  # Startup script
├── requirements.txt        # Python dependencies
├── instance/
│   └── campuscore.db       # SQLite database (auto-created on first run)
├── static/
│   ├── css/
│   │   └── main.css        # Full stylesheet (navy/gold university theme)
│   ├── js/
│   │   └── main.js         # Frontend JS (notifications, animations, etc.)
│   ├── images/
│   │   └── sist_logo.png   # SIST official logo (used in UI + certificates)
│   └── certificates/       # (optional local storage for certs)
└── templates/
    ├── base.html            # Shared layout with sidebar, topbar, flash msgs
    ├── login.html           # Login page
    ├── register.html        # Registration page
    ├── admin/
    │   ├── dashboard.html   # Admin overview with stats
    │   ├── events.html      # Events list with search/filter
    │   ├── event_form.html  # Create / Edit event form
    │   ├── attendance.html  # Mark attendance per event
    │   └── students.html    # Student directory
    └── student/
        ├── dashboard.html   # Student overview
        ├── events.html      # Browse & register for events
        └── my_events.html   # My registered events + certificate download
```

---

## ⚙️ Setup & Run

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Run the application
```bash
python run.py
```

### 3. Open in browser
```
http://localhost:5000
```

---

## 🔐 Default Login Credentials

| Role    | Email                    | Password     |
|---------|--------------------------|--------------|
| Admin   | admin@sist.ac.in         | admin123     |
| Student | student@sist.ac.in       | student123   |

---

## ✨ Features

### Admin
- Dashboard with live stats (events, students, registrations, attendance)
- Create / Edit / Delete events with conflict detection
- View all registered students per event
- Mark attendance (Present / Absent) with bulk actions
- Student directory

### Student
- Browse and register for upcoming events
- View registered events and attendance status
- Download PDF certificate when marked Present

### Certificate PDF
- Landscape A4 format with SIST branding
- College logo, double border (navy + gold)
- Student name, event name, date, venue
- Signature placeholders (Event Coordinator + Vice Chancellor)
- Unique certificate number
- Generated dynamically using ReportLab

---

## 🛠️ Tech Stack

| Layer     | Technology          |
|-----------|---------------------|
| Backend   | Python Flask        |
| Database  | SQLite + SQLAlchemy |
| Frontend  | HTML5, CSS3, JS     |
| PDF Gen   | ReportLab           |
| Icons     | Font Awesome 6      |
| Fonts     | Playfair Display, DM Sans |
