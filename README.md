# Tarbeya

> **Multi-tenant SaaS for Islamic school (madrasah) administration** — QR attendance, student counseling (BK), teaching journal, grading, EMIS import, and class advisor tools, all in one platform.

[![Live Demo](https://img.shields.io/badge/demo-vps.alaiksander.my.id%2Fapps-blue)](https://vps.alaiksander.my.id/apps/)
[![Stack](https://img.shields.io/badge/backend-FastAPI%20%2B%20SQLAlchemy%202.0-009688)]()
[![Frontend](https://img.shields.io/badge/frontend-Jinja2%20%2B%20HTMX%20%2B%20Flutter-02569B)]()
[![Tests](https://img.shields.io/badge/tests-530%20pass-green)]()
[![Endpoints](https://img.shields.io/badge/endpoints-389%20(173%20API%20%2B%20216%20web)-orange)]()

---

## 🎯 What is Tarbeya?

Tarbeya is a **multi-tenant SaaS platform** built for the operational needs of Indonesian *madrasah* (Islamic schools), from MTs (Madrasah Tsanawiyah / junior high) to MA (Madrasah Aliyah / senior high) and beyond.

It replaces the fragmented, manual workflows that consume hours of teacher and admin time each week:

| Module | What it does | Replaces |
|--------|--------------|----------|
| **Absensi QR** | Student scan-in via QR card → live attendance dashboard → printable recap | Paper attendance book |
| **Jurnal Mengajar** | Teacher logs daily lesson topics, attendance, materials | Manual lesson log book |
| **Bimbingan Konseling (BK)** | Student violation points, counseling sessions, status SP (Surat Peringatan) | Manual violation tracking |
| **Penilaian** | KKTP formatif-sumatif grading, per-materi assessment, RDM export | Spreadsheet grade books |
| **Pembayaran** | Tuition/fee billing, installments, discounts, deferrals, auto-generate per type | Manual fee ledger |
| **Wali Kelas** | Class advisor dashboard: student roster, parent contacts, periodic reports | Manual roll books |
| **Import EMIS** | Bulk import from EMIS Excel, auto-map to classes | Manual data entry into EMIS |
| **Role & Permission Matrix** | Admin defines roles; menus/buttons auto-hide based on permissions | Hard-coded role checks |
| **Multi-madrasah tenant** | One deployment serves many schools; data isolated per schema | Each school needs its own server |

---

## 🛠️ Tech Stack

### Backend (`backend/`)

| Component | Technology |
|-----------|------------|
| **Framework** | [FastAPI](https://fastapi.tiangolo.com/) 0.110+ (async) |
| **ORM** | SQLAlchemy 2.0 + Alembic (migrations) |
| **Database (dev)** | SQLite 3 (file-based, per-tenant) |
| **Database (prod)** | PostgreSQL 16 (schema-per-tenant isolation) |
| **Auth** | JWT (PyJWT) + HttpOnly cookies (HttpOnly + Secure on HTTPS) |
| **Validation** | Pydantic v2 |
| **Templates** | Jinja2 + HTMX 2.0 + Tailwind CSS (CDN) + Lucide icons (local) + Fuse.js (local) |
| **QR** | `qrcode` + Pillow |
| **Excel I/O** | openpyxl |
| **PDF** | reportlab |
| **Server** | uvicorn + nginx reverse proxy + systemd |

### Frontend

| Component | Technology |
|-----------|------------|
| **Web admin UI** | Jinja2 + HTMX 2.0 + Tailwind (served at `/apps/`) |
| **Mobile app** | [Flutter](https://flutter.dev/) 3.x web build (served at `/madrasah/`) |
| **API client** | `http` package + custom AuthService |
| **Storage** | SharedPreferences (token + user cache) |

### Deployment & Ops

| Component | Technology |
|-----------|------------|
| **Process manager** | systemd (`tarbeya-backend.service`, uvicorn on `127.0.0.1:8013`) |
| **Reverse proxy** | nginx with brotli + HTTP/2 + keepalive pool |
| **CI/CD** | Manual `push-to-prod.sh` script (zero-downtime rsync + verify) |
| **Observability** | journalctl + nginx access log + per-app health endpoints |
| **Secrets** | `~/.hermes/.env` (chmod 600) — never committed to Git |

---

## 📁 Project Structure

```
tarbeya/
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── main.py             # Application entry point
│   │   ├── config.py           # Pydantic settings (DB URL, JWT, etc.)
│   │   ├── db.py               # SQLAlchemy engine + per-tenant session factory
│   │   ├── models.py           # ORM models (multi-tenant aware)
│   │   ├── schemas.py          # Pydantic request/response schemas
│   │   ├── deps.py             # FastAPI dependencies (auth, permission, db)
│   │   ├── permissions.py      # Permission codes + role defaults
│   │   ├── routers/            # API endpoints (173 total)
│   │   │   ├── absensi.py      # Attendance (QR scan, manual, recap)
│   │   │   ├── bk.py           # Bimbingan Konseling
│   │   │   ├── jurnal.py       # Teaching journal
│   │   │   ├── murid.py        # Students CRUD + import/export
│   │   │   ├── kelas.py        # Classes + naik kelas
│   │   │   ├── tagihan.py      # Billing / payments
│   │   │   ├── superadmin.py   # Tenant management, backup, audit
│   │   │   └── ...
│   │   ├── web/                # Web admin UI (Jinja2 + HTMX)
│   │   │   ├── core/           # Shared: auth, deps, templates
│   │   │   └── modules/
│   │   │       └── absensi/    # Per-modul views + templates
│   │   └── static/             # CSS, JS, images (served via nginx)
│   ├── alembic/                # Database migrations
│   ├── requirements.txt
│   └── .env.example            # Template (real .env is gitignored)
│
├── app/                        # Flutter web frontend (mobile)
│   ├── lib/
│   │   ├── main.dart
│   │   ├── services/           # auth, api, storage
│   │   ├── screens/            # absensi, profile, login
│   │   └── widgets/
│   ├── web/                    # Web build output (gitignored)
│   └── pubspec.yaml
│
├── marketing/                  # Marketing materials (slides, social cards)
├── README.md                   # ← you are here
├── .gitignore                  # Comprehensive (secrets, venv, DB, build artifacts)
└── LICENSE                     # TBD
```

---

## 🚀 Quick Start (Local Development)

### Prerequisites

- Python 3.11+ (tested on 3.11 and 3.12)
- Flutter 3.x (for mobile web build)
- Git
- ~500 MB disk space

### 1. Clone & setup

```bash
git clone https://github.com/alaiksander/hermes-madrasah-app-dev.git
cd hermes-madrasah-app-dev

# Backend setup
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy env template
cp .env.example .env
# Edit .env — at minimum set JWT_SECRET (use: python3 -c "import secrets; print(secrets.token_hex(32))")
```

### 2. Initialize database

```bash
# Run migrations
alembic upgrade head

# (Optional) seed demo data
python3 -c "from app.db import init_global_db; init_global_db()"
```

### 3. Start backend

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8013
# API docs: http://127.0.0.1:8013/docs (Swagger UI)
# Web admin: http://127.0.0.1:8013/apps/
```

### 4. Start Flutter web (separate terminal, optional)

```bash
cd ../app
flutter pub get
flutter run -d web-server --web-port 8080 --web-hostname 0.0.0.0
# Open: http://127.0.0.1:8080
```

### 5. Login

Default credentials (development only):
- **Kode Madrasah**: `mtsn2kudus`
- **Username**: `admin`
- **Password**: `admin123`

> ⚠️ **Change immediately in production**. The default password is for local development only.

---

## 🏗️ Architecture

### Multi-Tenant Strategy

Two modes, single codebase:

| Mode | Database | Use case | Tenant isolation |
|------|----------|----------|-----------------|
| **Dev (default)** | SQLite, one file per tenant (`data/tenants/<kode>.db`) | Local development | File separation |
| **Prod** | PostgreSQL, one schema per tenant (`<kode>` schema in `madrasah` DB) | Production / multi-madrasah | Schema separation via `SET search_path` |

The `TenantBase` ORM base intentionally **does NOT have a `tenant_id` column** — isolation is structural (file or schema), not a WHERE clause. This means zero risk of cross-tenant data leaks from a forgotten filter.

### Module Pattern (Backend)

```
app/routers/
├── <module>.py    # API endpoints (FastAPI APIRouter)
└── <module>_crud.py (optional, for complex CRUD logic)

app/web/modules/<module>/
├── views/         # Web views (Jinja2 templates)
├── templates/     # HTML + partials
└── _menu/         # Sidebar group (if applicable)
```

### Permission System

1. Each user has a `role` (admin/guru) AND optionally a `role_id` (custom role)
2. **Custom roles win** — DB lookup `RolePermission` for `role_id`
3. Falls back to `admin` → `ROLE_DEFAULT_PERMISSIONS["guru"]` → `False`
4. Sidebar + API use the same `user_has_permission()` check

Admin can toggle each permission per role via `/apps/system/role/{id}/matrix`. Groups auto-hide if all submenus have no permission.

---

## 📡 API Overview

The project has **389 endpoints** total: **173 REST API + 216 web views**.

### API Base Path
- Dev: `http://127.0.0.1:8013/api/...`
- Prod: `https://vps.alaiksander.my.id/apps-api/api/...`

### Quick examples

```bash
# Login
curl -X POST http://127.0.0.1:8013/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"kode_madrasah":"mtsn2kudus","username":"admin","password":"admin123"}'

# List students (with Bearer token)
curl -H "Authorization: Bearer ***" \
  "http://127.0.0.1:8013/api/murid?page=1&per_page=50"

# Get attendance today
curl -H "Authorization: Bearer ***" \
  http://127.0.0.1:8013/api/absensi/hari-ini
```

### Full API reference

After starting the backend, visit **http://127.0.0.1:8013/docs** for interactive Swagger UI (auto-generated by FastAPI).

---

## 🧪 Tests

```bash
cd backend
./venv/bin/python test_auth_role.py    # Run a single test file
./venv/bin/python test_*.py            # Run all test files
```

- **530 test assertions** across 17 test files, **0 failures**
- Covers all 173 API endpoints (100% coverage)
- Tests use isolated test tenants — never touch real `mtsn2kudus` data

---

## 🤝 Contributing

This is currently a **single-author project** built by a teacher. If you find it useful and want to contribute:

1. **Open an issue** first — describe the use case or bug
2. **Fork the repo** and create a feature branch (`git checkout -b feat/your-feature`)
3. **Write tests** for new features (target: maintain full API coverage)
4. **Follow existing patterns**:
   - Multi-tenant aware (no raw `tenant_id` filters — isolation is structural)
   - Permission-driven (sidebar + API use `user_has_permission()`)
   - HTMX 2.0 + Tailwind for web, no heavy JS framework
5. **Submit a Pull Request** with:
   - Description of what + why
   - Test results (`./venv/bin/python test_*.py`)
   - Migration file (if schema change): `alembic revision -m "msg"`

### Code of Conduct

Be kind. This is built by an Indonesian teacher who codes at night after teaching all day. Constructive feedback welcome, rudeness is not.

---

## 📜 License

**TBD** — Currently private use, considering MIT or AGPL-3.0 once stable. Contact Mr. Alaik on Telegram @alaiksander if you want to use this commercially.

---

## 👤 Author

**Mr. Alaik** (alaiksander)
- 🏫 Guru MTs N 2 Kudus, Indonesia
- 🌐 [vps.alaiksander.my.id](https://vps.alaiksander.my.id)
- 🤖 Built with assistance from [Hermes Agent](https://hermes-agent.nousresearch.com/)

---

## 🌟 Star History

If this project helps your school or community, consider giving it a star ⭐ — it helps others find it.

---

## 📚 Related Documentation

This repo tracks extensive in-repo documentation:

- `backend/alembic/` — Database migration history
- `marketing/` — Landing page copy, social media assets
- Skill references (in the Hermes Agent ecosystem): `madrasah-app`, `tarbeya-migrate-path`, `permission-driven-menu`, `mobile-friendly-patterns`

---

**Made with ❤️ in Kudus, Central Java, Indonesia**
