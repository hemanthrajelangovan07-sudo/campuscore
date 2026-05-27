<div align="center">

<img src="https://img.shields.io/badge/Python-3.11.9-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/Flask-3.0-000000?style=for-the-badge&logo=flask&logoColor=white"/>
<img src="https://img.shields.io/badge/SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white"/>
<img src="https://img.shields.io/badge/Socket.IO-4.7.2-010101?style=for-the-badge&logo=socket.io&logoColor=white"/>
<img src="https://img.shields.io/badge/Node.js-18+-339933?style=for-the-badge&logo=node.js&logoColor=white"/>
<img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge"/>

# CampusCore
### College Event Management System

*A production-grade, full-stack web application for managing college events end-to-end —*
*built with Flask, real-time WebSockets, Google OAuth 2.0, and automated PDF certificate generation.*

[Live Demo](#) · [Report a Bug](#) · [Request a Feature](#)

</div>

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Project Structure](#project-structure)
- [Database Models](#database-models)
- [Author](#author)
- [License](#license)

---

## Overview

CampusCore is a fully functional, end-to-end college event management platform that handles the complete lifecycle of campus events — from creation and registration to real-time attendance tracking and automated certificate issuance.

The system supports three distinct user roles (**Student**, **Organizer**, **Admin**), each with a tailored dashboard experience. It integrates Google OAuth 2.0 for frictionless authentication, WebSocket-powered live updates for real-time interactivity, and a dual email pipeline using both Flask-Mail and a dedicated Node.js microservice.

> **Screenshots** — *(add 2–3 screenshots of your UI here)*

---

## Features

### Authentication & Security
- Google OAuth 2.0 (OpenID Connect) via Authlib for one-click sign-in
- Traditional email/password login with Werkzeug secure password hashing
- Session-based authentication with CSRF protection (Flask-WTF)
- Role-based access control across all routes — **Student / Organizer / Admin**

### Event Management
- Full CRUD for events — organizers can create, publish, edit, and close events
- Student event discovery, registration, and personal attendance history
- Admin dashboard with platform-wide oversight and user management

### Real-Time Communication
- Live push notifications via **Flask-SocketIO** (WebSocket + eventlet)
- Real-time attendance counters and event status broadcasts

### Email Notifications
- Dual-pipeline email delivery: **Flask-Mail** (Python/SMTP) + **Nodemailer** (Node.js microservice)
- Automated registration confirmations, reminders, and event updates

### PDF Certificate Generation
- Auto-generated, styled participation certificates via **ReportLab + Pillow**
- Downloadable by students upon event completion

### UI / UX
- Custom **navy/gold** design theme with a 645-line handcrafted stylesheet
- Dark mode toggle, responsive sidebar, and Font Awesome icon set
- Playfair Display + DM Sans typography via Google Fonts
- Zero SPA framework — pure Jinja2 server-side rendering + Vanilla JS

---

## Tech Stack

### Backend

| Library | Version | Purpose |
|---|---|---|
| Flask | ≥ 3.0 | Core web framework |
| Flask-SQLAlchemy | ≥ 3.1 | ORM — 13 relational models |
| Flask-Migrate / Alembic | latest | Schema versioning & migrations |
| Flask-WTF | latest | Form handling + CSRF protection |
| Flask-SocketIO + eventlet | ≥ 5.3 | Real-time WebSocket server |
| Flask-Mail | latest | SMTP email via Gmail |
| Authlib | ≥ 1.3 | Google OAuth 2.0 / OpenID Connect |
| ReportLab + Pillow | ≥ 4.1 | PDF certificate generation |
| Werkzeug | latest | Password hashing, secure filenames |
| Requests / python-dotenv | latest | HTTP client, environment config |

### Frontend

| Technology | Version | Purpose |
|---|---|---|
| HTML5 / CSS3 | — | Jinja2 templates + custom navy/gold theme |
| JavaScript | ES6+ | Sidebar, dark mode, form validation, notifications |
| Socket.IO Client | 4.7.2 | Real-time event updates & attendance |
| Font Awesome | 6.4.0 | Icon system |
| Google Fonts | — | Playfair Display + DM Sans |

### Services & Infrastructure

| Layer | Technology |
|---|---|
| Database | SQLite (`campuscore.db`) — 13 models, file-based |
| Email Microservice | Node.js 18+ · Nodemailer · dotenv |
| Authentication | Google OAuth 2.0 · Session-based auth |

---

## Architecture

```
┌─────────────────────────────────────────────┐
│                   Client                    │
│     Jinja2 Templates · Vanilla JS ES6+      │
│     Socket.IO Client · Custom CSS Theme     │
└────────────────────┬────────────────────────┘
                     │ HTTP / WebSocket
┌────────────────────▼────────────────────────┐
│              Flask Application              │
│                                             │
│  ┌──────────┐ ┌──────────┐ ┌─────────────┐ │
│  │  Auth    │ │  Events  │ │   Admin     │ │
│  │ Blueprint│ │ Blueprint│ │  Blueprint  │ │
│  └──────────┘ └──────────┘ └─────────────┘ │
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │         Services Layer               │  │
│  │  OAuth · Email · PDF · WebSocket     │  │
│  └──────────────────────────────────────┘  │
└─────────┬──────────────┬───────────────────┘
          │              │
┌─────────▼──────┐  ┌────▼──────────────────┐
│   SQLite DB    │  │  Node.js Email Service │
│  13 ORM Models │  │  Nodemailer · SMTP     │
└────────────────┘  └───────────────────────┘
```

---

## Getting Started

### Prerequisites

- Python **3.11+**
- Node.js **18+** and npm
- A Gmail account with an [App Password](https://support.google.com/accounts/answer/185833) enabled
- A [Google Cloud Console](https://console.cloud.google.com/) project with OAuth 2.0 credentials

### Installation

**1. Clone the repository**
```bash
git clone https://github.com/hemanthrajelangovan07-sudo/campuscore.git
cd campuscore
```

**2. Create and activate a Python virtual environment**
```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

**3. Install Python dependencies**
```bash
pip install -r requirements.txt
```

**4. Configure environment variables**
```bash
cp .env.example .env
# Open .env and fill in all required values (see Environment Variables section)
```

**5. Run database migrations**
```bash
flask db upgrade
```

**6. Start the Flask application**
```bash
python run.py
```

**7. (Optional) Start the Node.js email microservice**
```bash
cd email-service
npm install
node index.js
```

**8. Open in your browser**
```
http://localhost:5000
```

---

## Environment Variables

Copy `.env.example` to `.env` and populate the following:

```env
# Application
SECRET_KEY=your_random_secret_key

# Google OAuth 2.0
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret

# Email (Flask-Mail via Gmail SMTP)
MAIL_USERNAME=your_gmail@gmail.com
MAIL_PASSWORD=your_gmail_app_password

# Email (Node.js Nodemailer — optional microservice)
NODE_MAIL_USER=your_gmail@gmail.com
NODE_MAIL_PASS=your_gmail_app_password
```

> **Note:** Never commit your `.env` file. It is already included in `.gitignore`.

---

## Project Structure

```
campuscore/
│
├── app/
│   ├── __init__.py          # App factory, extensions init
│   ├── models/              # 13 SQLAlchemy ORM models
│   ├── routes/              # Flask Blueprints
│   │   ├── auth.py          # Login, OAuth, registration
│   │   ├── events.py        # Event CRUD & registration
│   │   ├── student.py       # Student dashboard & history
│   │   ├── organizer.py     # Organizer portal
│   │   └── admin.py         # Admin panel
│   ├── templates/           # Jinja2 HTML templates
│   ├── static/
│   │   ├── css/             # Custom 645-line stylesheet
│   │   └── js/              # Vanilla JS modules
│   └── services/
│       ├── email.py         # Flask-Mail integration
│       ├── pdf.py           # ReportLab certificate generator
│       └── oauth.py         # Authlib OAuth config
│
├── migrations/              # Alembic migration scripts
├── email-service/           # Node.js + Nodemailer microservice
│   ├── index.js
│   └── package.json
│
├── .env.example             # Environment variable template
├── requirements.txt         # Python dependencies
├── run.py                   # Application entry point
└── README.md
```

---

## Database Models

The application uses **12 SQLAlchemy model classes + 1 raw association table = 13 tables** backed by SQLite:

| # | Model | File |
|---|---|---|
| 1 | `User` | `app/models/user.py` |
| 2 | `Event` | `app/models/event.py` |
| 3 | `Registration` | `app/models/registration.py` |
| 4 | `Attendance` | `app/models/attendance.py` |
| 5 | `Notification` | `app/models/notification.py` |
| 6 | `Announcement` | `app/models/announcement.py` |
| 7 | `Score` | `app/models/score.py` |
| 8 | `Team` | `app/models/team.py` |
| 9 | `UserSetting` | `app/models/user_setting.py` |
| 10 | `SystemSetting` | `app/models/system_setting.py` |
| 11 | `CertificateSignatory` | `app/models/certificate_signatory.py` |
| 12 | `AuditLog` | `app/models/audit_log.py` |
| — | `team_members` *(association table)* | `app/models/team.py` |

Schema migrations are managed via **Flask-Migrate (Alembic)**, ensuring version-controlled, reproducible database changes.

---

## Author

**Hemanth Raj**

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Connect-0A66C2?style=flat&logo=linkedin)](https://www.linkedin.com/in/hemanth-raj-21811b2b5)
[![GitHub](https://img.shields.io/badge/GitHub-Follow-181717?style=flat&logo=github)](https://github.com/hemanthrajelangovan07-sudo)
[![Email](https://img.shields.io/badge/Email-Contact-EA4335?style=flat&logo=gmail)](mailto:hemanthrajelangovan07@gmail.com)

---

## License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for more information.

---

<div align="center">

*If you found this project useful, consider giving it a ⭐ — it helps a lot!*

</div>
