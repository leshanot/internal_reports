import csv
import io
import re
import sqlite3
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

import streamlit as st


DATABASE_FILE = "salary_program.db"
REPORTS_DIR = Path("monthly_reports")
SELECTED_MONTH_FILE = Path(".selected_salary_month")
LEGACY_CSV_FILE = Path("PaymentAndBudgetReport24_09_2026_12_33.csv")
REPORTS_DIR.mkdir(exist_ok=True)

# Preserve the original August report the first time the upgraded app is opened.
legacy_august = REPORTS_DIR / "2026-08.csv"
if not legacy_august.exists() and LEGACY_CSV_FILE.exists():
    shutil.copy2(LEGACY_CSV_FILE, legacy_august)

def _available_report_months():
    return sorted([f.stem for f in REPORTS_DIR.glob("????-??.csv")], reverse=True)

def _startup_salary_month():
    available = _available_report_months()
    if SELECTED_MONTH_FILE.exists():
        saved = SELECTED_MONTH_FILE.read_text(encoding="utf-8").strip()
        if saved in available:
            return saved
    return available[0] if available else "2026-08"

SALARY_MONTH = _startup_salary_month()
CSV_FILE = str(REPORTS_DIR / f"{SALARY_MONTH}.csv")


DEFAULT_PAY_CATEGORIES = [
    "אבחון",
    "אבחון קלינאית",
    "אבחון ריפוי בעיסוק",
    "אימון",
    "אימון זוגי",
    "ביטוח לאומי - קלינאית תקשורת",
    "ביטול",
    "ביטול - צוות",
    "ביטול קבוצה",
    "בקשה להמשך טיפול",
    "דוח לשימוש פנימי בלבד",
    "דו״ח",
    "הדרכה",
    "הדרכת הורים",
    "הכנה",
    "המלצה לביטוח לאומי",
    "המלצה לצה״ל",
    "השכרה",
    "טיפול",
    "טיפול זוגי",
    "טיפול פסיכותרפיה",
    "ישיבת צוות",
    "יעוץ פסיכיאטרי",
    "יעוץ פסיכיאטרי - מבוגר",
    "לא הגיע",
    "מכתב סיכום",
    "מעקב",
    "מעקב פסיכיאטרי מבוגר",
    "קבוצה",
    "קלינאית תקשורת",
    "ריפוי בעיסוק",
    "הערכה פסיכיאטרית",
]


def connect_database():
    return sqlite3.connect(DATABASE_FILE)


def create_database():
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS therapist_profiles (
            therapist_name TEXT PRIMARY KEY,
            employment_type TEXT NOT NULL,
            vat_status TEXT,
            effective_from TEXT NOT NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS therapist_rates (
            therapist_name TEXT NOT NULL,
            category TEXT NOT NULL,
            rate REAL NOT NULL,
            effective_from TEXT NOT NULL,
            PRIMARY KEY (
                therapist_name,
                category,
                effective_from
            )
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pay_categories (
            category TEXT PRIMARY KEY,
            active INTEGER NOT NULL DEFAULT 1
        )
        """
    )

    for category in DEFAULT_PAY_CATEGORIES:
        cursor.execute(
            """
            INSERT OR IGNORE INTO pay_categories (
                category,
                active
            )
            VALUES (?, 1)
            """,
            (category,),
        )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pay_structures (
            therapist_name TEXT NOT NULL,
            pay_structure TEXT NOT NULL,
            monthly_salary REAL NOT NULL DEFAULT 0,
            effective_from TEXT NOT NULL,
            PRIMARY KEY (
                therapist_name,
                effective_from
            )
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS therapist_status (
            therapist_name TEXT PRIMARY KEY,
            archived INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_rates (
            provider TEXT NOT NULL,
            activity TEXT NOT NULL,
            rate REAL NOT NULL DEFAULT 0,
            effective_from TEXT NOT NULL,
            PRIMARY KEY (
                provider,
                activity,
                effective_from
            )
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            setting_name TEXT NOT NULL,
            setting_value TEXT NOT NULL,
            effective_from TEXT NOT NULL,
            PRIMARY KEY (setting_name, effective_from)
        )
        """
    )
    cursor.execute(
        """
        INSERT OR IGNORE INTO app_settings (setting_name, setting_value, effective_from)
        VALUES ('clinic_vat_rate', '18.0', '2026-01')
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS provider_vat_settings (
            provider TEXT NOT NULL,
            vat_mode TEXT NOT NULL DEFAULT 'Plus VAT',
            effective_from TEXT NOT NULL,
            PRIMARY KEY (provider, effective_from)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS therapist_personal_details (
            therapist_name TEXT PRIMARY KEY,
            id_number TEXT DEFAULT '',
            birth_date TEXT DEFAULT '',
            address TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            email TEXT DEFAULT '',
            bank_name TEXT DEFAULT '',
            bank_branch TEXT DEFAULT '',
            bank_account TEXT DEFAULT '',
            start_date TEXT DEFAULT '',
            profession TEXT DEFAULT '',
            employee_number TEXT DEFAULT '',
            source TEXT DEFAULT 'Manual'
        )
        """
    )

    # Add newer HR/pension fields safely to existing databases.
    cursor.execute("PRAGMA table_info(therapist_personal_details)")
    existing_personal_columns = {row[1] for row in cursor.fetchall()}
    for column_name, column_sql in {
        "existing_pension": "TEXT DEFAULT 'Unknown'",
        "pension_reminder_email": "TEXT DEFAULT ''",
        "pension_reminder_days": "INTEGER DEFAULT 30",
    }.items():
        if column_name not in existing_personal_columns:
            cursor.execute(
                f"ALTER TABLE therapist_personal_details ADD COLUMN {column_name} {column_sql}"
            )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS monthly_reports (
            salary_month TEXT PRIMARY KEY,
            original_filename TEXT NOT NULL,
            uploaded_at TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS therapist_documents (
            document_id INTEGER PRIMARY KEY AUTOINCREMENT,
            therapist_name TEXT NOT NULL,
            document_type TEXT NOT NULL,
            document_title TEXT DEFAULT '',
            filename TEXT NOT NULL,
            mime_type TEXT DEFAULT 'application/octet-stream',
            uploaded_at TEXT NOT NULL,
            file_content BLOB NOT NULL
        )
        """
    )

    cursor.execute(
        """
        UPDATE pay_structures
        SET pay_structure = 'Fixed salary + activity'
        WHERE pay_structure = 'Manager / Supervisor'
        """
    )

    connection.commit()
    connection.close()



def save_monthly_report(salary_month, uploaded_file):
    salary_month = salary_month.strip()
    if not re.fullmatch(r"\d{4}-\d{2}", salary_month):
        raise ValueError("Salary month must be YYYY-MM")
    month_number = int(salary_month[-2:])
    if month_number < 1 or month_number > 12:
        raise ValueError("Salary month must contain a valid month")
    data = uploaded_file.getvalue()
    destination = REPORTS_DIR / f"{salary_month}.csv"
    destination.write_bytes(data)
    connection = connect_database()
    cursor = connection.cursor()
    cursor.execute(
        """INSERT INTO monthly_reports (salary_month, original_filename, uploaded_at)
           VALUES (?, ?, ?)
           ON CONFLICT(salary_month) DO UPDATE SET
             original_filename=excluded.original_filename,
             uploaded_at=excluded.uploaded_at""",
        (salary_month, uploaded_file.name, datetime.now().isoformat(timespec="seconds")),
    )
    connection.commit()
    connection.close()


def set_selected_salary_month(salary_month):
    SELECTED_MONTH_FILE.write_text(salary_month, encoding="utf-8")


def list_monthly_reports():
    months = _available_report_months()
    connection = connect_database()
    cursor = connection.cursor()
    cursor.execute("SELECT salary_month, original_filename, uploaded_at FROM monthly_reports")
    meta = {row[0]: {"filename": row[1], "uploaded_at": row[2]} for row in cursor.fetchall()}
    connection.close()
    return [(month, meta.get(month, {})) for month in months]


def save_therapist_document(therapist_name, document_type, document_title, uploaded_file):
    connection = connect_database()
    cursor = connection.cursor()
    cursor.execute(
        """INSERT INTO therapist_documents
           (therapist_name, document_type, document_title, filename, mime_type, uploaded_at, file_content)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            therapist_name,
            document_type,
            document_title.strip(),
            uploaded_file.name,
            uploaded_file.type or "application/octet-stream",
            datetime.now().isoformat(timespec="seconds"),
            uploaded_file.getvalue(),
        ),
    )
    connection.commit()
    connection.close()


def load_therapist_documents(therapist_name):
    connection = connect_database()
    cursor = connection.cursor()
    cursor.execute(
        """SELECT document_id, document_type, document_title, filename, mime_type, uploaded_at, file_content
           FROM therapist_documents WHERE therapist_name=? ORDER BY uploaded_at DESC, document_id DESC""",
        (therapist_name,),
    )
    rows = cursor.fetchall()
    connection.close()
    return [
        {"id": r[0], "type": r[1], "title": r[2], "filename": r[3], "mime": r[4], "uploaded_at": r[5], "content": r[6]}
        for r in rows
    ]


def delete_therapist_document(document_id):
    connection = connect_database()
    cursor = connection.cursor()
    cursor.execute("DELETE FROM therapist_documents WHERE document_id=?", (document_id,))
    connection.commit()
    connection.close()


def therapist_document_status(documents):
    types = {d["type"] for d in documents}
    return {
        "Form 101": "Form 101" in types,
        "Contract": "Contract" in types,
        "Tofes Kubiyot": "Tofes Kubiyot" in types,
        "Professional license": "Professional license" in types,
        "Diploma / degree": "Diploma / degree" in types,
    }


def load_pay_categories(active_only=True):
    connection = connect_database()
    cursor = connection.cursor()

    if active_only:
        cursor.execute(
            """
            SELECT category
            FROM pay_categories
            WHERE active = 1
            ORDER BY category
            """
        )
        rows = cursor.fetchall()
        connection.close()
        return [row[0] for row in rows]

    cursor.execute(
        """
        SELECT category, active
        FROM pay_categories
        ORDER BY category
        """
    )

    rows = cursor.fetchall()
    connection.close()
    return rows


def add_pay_category(category):
    category = category.strip()

    if not category:
        return False

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO pay_categories (
            category,
            active
        )
        VALUES (?, 1)
        ON CONFLICT(category)
        DO UPDATE SET
            active = 1
        """,
        (category,),
    )

    connection.commit()
    connection.close()
    return True


def rename_pay_category(old_name, new_name):
    new_name = new_name.strip()

    if not new_name or new_name == old_name:
        return False

    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT 1
        FROM pay_categories
        WHERE category = ?
        """,
        (new_name,),
    )

    if cursor.fetchone():
        connection.close()
        return False

    try:
        cursor.execute(
            """
            UPDATE pay_categories
            SET category = ?
            WHERE category = ?
            """,
            (new_name, old_name),
        )

        cursor.execute(
            """
            UPDATE therapist_rates
            SET category = ?
            WHERE category = ?
            """,
            (new_name, old_name),
        )

        connection.commit()

    except sqlite3.IntegrityError:
        connection.rollback()
        connection.close()
        return False

    connection.close()
    return True


def set_pay_category_active(category, active):
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        UPDATE pay_categories
        SET active = ?
        WHERE category = ?
        """,
        (
            1 if active else 0,
            category,
        ),
    )

    connection.commit()
    connection.close()


def is_therapist_archived(therapist_name):
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT archived
        FROM therapist_status
        WHERE therapist_name = ?
        """,
        (therapist_name,),
    )

    row = cursor.fetchone()
    connection.close()
    return bool(row[0]) if row else False


def set_therapist_archived(therapist_name, archived):
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO therapist_status (
            therapist_name,
            archived
        )
        VALUES (?, ?)
        ON CONFLICT(therapist_name)
        DO UPDATE SET archived = excluded.archived
        """,
        (therapist_name, 1 if archived else 0),
    )

    connection.commit()
    connection.close()


def load_archived_therapists():
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT therapist_name
        FROM therapist_status
        WHERE archived = 1
        ORDER BY therapist_name
        """
    )

    rows = cursor.fetchall()
    connection.close()
    return [row[0] for row in rows]
def load_provider_rates(salary_month=None):
    connection = connect_database()
    cursor = connection.cursor()

    if salary_month:
        cursor.execute(
            """
            SELECT
                provider,
                activity,
                rate,
                effective_from
            FROM provider_rates
            WHERE effective_from <= ?
            ORDER BY effective_from
            """,
            (salary_month,),
        )
    else:
        cursor.execute(
            """
            SELECT
                provider,
                activity,
                rate,
                effective_from
            FROM provider_rates
            ORDER BY effective_from
            """
        )

    rows = cursor.fetchall()
    connection.close()

    rates = {}

    for provider, activity, rate, effective_from in rows:
        rates[(provider, activity)] = float(rate)

    return rates


def save_provider_rate(
    provider,
    activity,
    rate,
    effective_from,
):
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO provider_rates (
            provider,
            activity,
            rate,
            effective_from
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(
            provider,
            activity,
            effective_from
        )
        DO UPDATE SET
            rate = excluded.rate
        """,
        (
            provider,
            activity,
            rate,
            effective_from,
        ),
    )

    connection.commit()
    connection.close()


def load_setting(setting_name, salary_month=SALARY_MONTH, default=0.0):
    connection = connect_database()
    cursor = connection.cursor()
    cursor.execute(
        """SELECT setting_value FROM app_settings
           WHERE setting_name = ? AND effective_from <= ?
           ORDER BY effective_from DESC LIMIT 1""",
        (setting_name, salary_month),
    )
    row = cursor.fetchone()
    connection.close()
    return float(row[0]) if row else float(default)


def save_setting(setting_name, value, effective_from):
    connection = connect_database()
    cursor = connection.cursor()
    cursor.execute(
        """INSERT INTO app_settings (setting_name, setting_value, effective_from)
           VALUES (?, ?, ?)
           ON CONFLICT(setting_name, effective_from) DO UPDATE SET setting_value=excluded.setting_value""",
        (setting_name, str(value), effective_from),
    )
    connection.commit(); connection.close()


def load_provider_vat_mode(provider, salary_month=SALARY_MONTH):
    connection = connect_database(); cursor = connection.cursor()
    cursor.execute(
        """SELECT vat_mode FROM provider_vat_settings
           WHERE provider=? AND effective_from <= ?
           ORDER BY effective_from DESC LIMIT 1""", (provider, salary_month))
    row=cursor.fetchone(); connection.close()
    return row[0] if row else "Plus VAT"


def save_provider_vat_mode(provider, vat_mode, effective_from):
    connection=connect_database(); cursor=connection.cursor()
    cursor.execute(
        """INSERT INTO provider_vat_settings(provider, vat_mode, effective_from) VALUES(?,?,?)
           ON CONFLICT(provider,effective_from) DO UPDATE SET vat_mode=excluded.vat_mode""",
        (provider, vat_mode, effective_from))
    connection.commit(); connection.close()


def load_personal_details(therapist_name):
    connection = connect_database()
    cursor = connection.cursor()
    cursor.execute(
        """SELECT id_number,birth_date,address,phone,email,bank_name,bank_branch,bank_account,
                  start_date,profession,employee_number,source,existing_pension,pension_reminder_email,
                  pension_reminder_days
           FROM therapist_personal_details WHERE therapist_name=?""",
        (therapist_name,),
    )
    row = cursor.fetchone()
    connection.close()
    keys = [
        "id_number","birth_date","address","phone","email","bank_name","bank_branch",
        "bank_account","start_date","profession","employee_number","source","existing_pension",
        "pension_reminder_email","pension_reminder_days"
    ]
    if row:
        result = dict(zip(keys, row))
        result["existing_pension"] = result.get("existing_pension") or "Unknown"
        result["pension_reminder_email"] = result.get("pension_reminder_email") or ""
        result["pension_reminder_days"] = int(result.get("pension_reminder_days") or 30)
        return result
    result = {k: "" for k in keys}
    result["source"] = "Manual"
    result["existing_pension"] = "Unknown"
    result["pension_reminder_days"] = 30
    return result


def save_personal_details(therapist_name, details):
    connection = connect_database()
    cursor = connection.cursor()
    cursor.execute(
        """INSERT INTO therapist_personal_details
        (therapist_name,id_number,birth_date,address,phone,email,bank_name,bank_branch,bank_account,
         start_date,profession,employee_number,source,existing_pension,pension_reminder_email,pension_reminder_days)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(therapist_name) DO UPDATE SET
        id_number=excluded.id_number,birth_date=excluded.birth_date,address=excluded.address,
        phone=excluded.phone,email=excluded.email,bank_name=excluded.bank_name,
        bank_branch=excluded.bank_branch,bank_account=excluded.bank_account,start_date=excluded.start_date,
        profession=excluded.profession,employee_number=excluded.employee_number,source=excluded.source,
        existing_pension=excluded.existing_pension,pension_reminder_email=excluded.pension_reminder_email,
        pension_reminder_days=excluded.pension_reminder_days""",
        (therapist_name, details["id_number"], details["birth_date"], details["address"],
         details["phone"], details["email"], details["bank_name"], details["bank_branch"],
         details["bank_account"], details["start_date"], details["profession"], details["employee_number"],
         details.get("source", "Manual"), details.get("existing_pension", "Unknown"),
         details.get("pension_reminder_email", ""), int(details.get("pension_reminder_days", 30))))
    connection.commit()
    connection.close()


def _add_months(date_value, months):
    month_index = date_value.month - 1 + months
    year = date_value.year + month_index // 12
    month = month_index % 12 + 1
    month_days = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                  31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    return date_value.replace(year=year, month=month, day=min(date_value.day, month_days[month - 1]))


def calculate_pension_dates(start_date_text, existing_pension, reminder_days=30):
    if not start_date_text or existing_pension not in ("Yes", "No"):
        return None
    parsed = None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            parsed = datetime.strptime(start_date_text.strip(), fmt).date()
            break
        except ValueError:
            pass
    if parsed is None:
        return {"error": "Use start date as YYYY-MM-DD or DD/MM/YYYY."}
    if existing_pension == "Yes":
        three_months = _add_months(parsed, 3)
        year_end = parsed.replace(month=12, day=31)
        action_due = min(three_months, year_end)
        entitlement_from = parsed
        explanation = "Existing pension: entitlement is from the first day; deposits are due after 3 months, retroactive to the start date, or by year-end if earlier."
    else:
        action_due = _add_months(parsed, 6)
        entitlement_from = action_due
        explanation = "No existing pension: mandatory pension generally begins after 6 months of employment."
    reminder_date = action_due - timedelta(days=int(reminder_days or 30))
    return {"entitlement_from": entitlement_from, "action_due": action_due, "reminder_date": reminder_date, "explanation": explanation}


def load_profile(therapist_name):
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        SELECT
            employment_type,
            vat_status,
            effective_from
        FROM therapist_profiles
        WHERE therapist_name = ?
        """,
        (therapist_name,),
    )

    row = cursor.fetchone()
    connection.close()

    if not row:
        return None

    return {
        "employment_type": row[0],
        "vat_status": row[1],
        "effective_from": row[2],
    }


def load_rates(therapist_name, salary_month=None):
    connection = connect_database()
    cursor = connection.cursor()

    if salary_month:
        cursor.execute(
            """
            SELECT
                category,
                rate,
                effective_from
            FROM therapist_rates
            WHERE therapist_name = ?
              AND effective_from <= ?
            ORDER BY effective_from
            """,
            (
                therapist_name,
                salary_month,
            ),
        )

    else:
        cursor.execute(
            """
            SELECT
                category,
                rate,
                effective_from
            FROM therapist_rates
            WHERE therapist_name = ?
            ORDER BY effective_from
            """,
            (therapist_name,),
        )

    rows = cursor.fetchall()
    connection.close()

    rates = {}

    for category, rate, effective_from in rows:
        rates[category] = rate

    return rates


def load_pay_structure(therapist_name, salary_month=None):
    connection = connect_database()
    cursor = connection.cursor()

    if salary_month:
        cursor.execute(
            """
            SELECT
                pay_structure,
                monthly_salary,
                effective_from
            FROM pay_structures
            WHERE therapist_name = ?
              AND effective_from <= ?
            ORDER BY effective_from DESC
            LIMIT 1
            """,
            (
                therapist_name,
                salary_month,
            ),
        )

    else:
        cursor.execute(
            """
            SELECT
                pay_structure,
                monthly_salary,
                effective_from
            FROM pay_structures
            WHERE therapist_name = ?
            ORDER BY effective_from DESC
            LIMIT 1
            """,
            (therapist_name,),
        )

    row = cursor.fetchone()
    connection.close()

    if not row:
        return {
            "pay_structure": "Per activity",
            "monthly_salary": 0.0,
            "effective_from": SALARY_MONTH,
        }

    return {
        "pay_structure": row[0],
        "monthly_salary": float(row[1]),
        "effective_from": row[2],
    }


def save_therapist(
    therapist_name,
    employment_type,
    vat_status,
    pay_structure,
    monthly_salary,
    effective_from,
    rates,
):
    connection = connect_database()
    cursor = connection.cursor()

    cursor.execute(
        """
        INSERT INTO therapist_profiles (
            therapist_name,
            employment_type,
            vat_status,
            effective_from
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(therapist_name)
        DO UPDATE SET
            employment_type = excluded.employment_type,
            vat_status = excluded.vat_status,
            effective_from = excluded.effective_from
        """,
        (
            therapist_name,
            employment_type,
            vat_status,
            effective_from,
        ),
    )

    cursor.execute(
        """
        INSERT INTO pay_structures (
            therapist_name,
            pay_structure,
            monthly_salary,
            effective_from
        )
        VALUES (?, ?, ?, ?)
        ON CONFLICT(
            therapist_name,
            effective_from
        )
        DO UPDATE SET
            pay_structure = excluded.pay_structure,
            monthly_salary = excluded.monthly_salary
        """,
        (
            therapist_name,
            pay_structure,
            monthly_salary,
            effective_from,
        ),
    )

    for category, rate in rates.items():
        cursor.execute(
            """
            INSERT INTO therapist_rates (
                therapist_name,
                category,
                rate,
                effective_from
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(
                therapist_name,
                category,
                effective_from
            )
            DO UPDATE SET
                rate = excluded.rate
            """,
            (
                therapist_name,
                category,
                rate,
                effective_from,
            ),
        )

    connection.commit()
    connection.close()


def load_therapists():
    therapists = {}
    current_therapist = None
    current_section = None

    with open(
        CSV_FILE,
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.reader(file)

        for row in reader:
            row += [""] * (17 - len(row))

            row_text = " ".join(
                cell.strip()
                for cell in row
                if cell.strip()
            )

            # Start of a therapist's MEETINGS section.
            meeting_match = re.search(
                r"מפגשים עבור (.+?)-*$",
                row_text,
            )

            if meeting_match:
                current_therapist = (
                    meeting_match.group(1)
                    .strip("- ")
                    .strip()
                )

                therapists.setdefault(
                    current_therapist,
                    {
                        "counts": Counter(),
                        "provider_counts": Counter(),
                    },
                )

                current_section = "meetings"
                continue

            # Start of a therapist's ACTIVITIES section.
            activity_match = re.search(
                r"פעילויות עבור (.+?)-*$",
                row_text,
            )

            if activity_match:
                current_therapist = (
                    activity_match.group(1)
                    .strip("- ")
                    .strip()
                )

                therapists.setdefault(
                    current_therapist,
                    {
                        "counts": Counter(),
                        "provider_counts": Counter(),
                    },
                )

                current_section = "activities"
                continue

            if not current_therapist:
                continue

            date = row[0].strip()

            if not re.fullmatch(
                r"\d{2}/\d{2}/\d{4}",
                date,
            ):
                continue

            if current_section == "meetings":
                item_type = row[3].strip()
                provider = row[8].strip()
                patient_payment_text = row[9].strip()

                try:
                    patient_payment = float(
                        patient_payment_text.replace(",", "")
                    )
                except ValueError:
                    patient_payment = 0.0

                if not provider and patient_payment > 0:
                    provider = "Private"

                if not provider:
                    provider = "Not specified"

            elif current_section == "activities":
                item_type = row[1].strip()
                provider = row[6].strip()
                patient_payment = 0.0

                if not provider:
                    provider = "Not specified"

            else:
                continue

            if item_type:
                therapists[current_therapist][
                    "counts"
                ][item_type] += 1

                therapists[current_therapist][
                    "provider_counts"
                ][
                    (
                        item_type,
                        provider,
                        patient_payment,
                    )
                ] += 1

    return therapists


def calculate_salary(therapist_name, counts):
    profile = load_profile(therapist_name)

    pay_info = load_pay_structure(
        therapist_name,
        SALARY_MONTH,
    )

    rates = load_rates(
        therapist_name,
        SALARY_MONTH,
    )

    active_categories = set(
        load_pay_categories()
    )

    calculation = []
    unmapped = []

    if pay_info["pay_structure"] == "Fixed monthly salary":
        subtotal = pay_info["monthly_salary"]

    else:
        subtotal = (
            pay_info["monthly_salary"]
            if pay_info["pay_structure"] == "Fixed salary + activity"
            else 0.0
        )

        for activity, count in sorted(counts.items()):
            if activity == "ביטול - צוות":
                continue

            if activity in active_categories:
                rate = float(
                    rates.get(activity, 0)
                )

                amount = count * rate

                calculation.append(
                    {
                        "activity": activity,
                        "count": count,
                        "rate": rate,
                        "amount": amount,
                    }
                )

                subtotal += amount

            else:
                unmapped.append(
                    {
                        "activity": activity,
                        "count": count,
                    }
                )

    vat = 0.0

    if (
        profile
        and profile["employment_type"] == "Freelance"
        and profile["vat_status"] == "עוסק מורשה — +18% VAT"
    ):
        vat = subtotal * (load_setting("clinic_vat_rate", SALARY_MONTH, 18.0) / 100.0)

    total = subtotal + vat

    return {
        "profile": profile,
        "pay_info": pay_info,
        "calculation": calculation,
        "unmapped": unmapped,
        "subtotal": subtotal,
        "vat": vat,
        "total": total,
    }



def calculate_clinic_income(provider_counts):
    provider_rates = load_provider_rates(SALARY_MONTH)
    active_categories = set(load_pay_categories())
    vat_rate = load_setting("clinic_vat_rate", SALARY_MONTH, 18.0) / 100.0
    rows = []
    unmapped = []
    total_pre_vat = 0.0
    total_incl_vat = 0.0

    for (activity, provider, patient_payment), count in sorted(provider_counts.items()):
        if activity not in active_categories:
            unmapped.append({"activity": activity, "provider": provider, "count": count})
            continue
        provider_rate = float(provider_rates.get((provider, activity), 0.0))
        vat_mode = load_provider_vat_mode(provider, SALARY_MONTH)
        if vat_mode == "VAT included":
            provider_pre_vat = provider_rate / (1.0 + vat_rate) if vat_rate else provider_rate
            provider_incl_vat = provider_rate
        elif vat_mode == "No VAT":
            provider_pre_vat = provider_rate
            provider_incl_vat = provider_rate
        else:  # Plus VAT
            provider_pre_vat = provider_rate
            provider_incl_vat = provider_rate * (1.0 + vat_rate)

        # Tipulog patient amounts are treated as VAT-inclusive clinic receipts.
        patient_incl_vat = patient_payment
        patient_pre_vat = patient_payment / (1.0 + vat_rate) if patient_payment and vat_rate else patient_payment
        income_pre_vat = count * (provider_pre_vat + patient_pre_vat)
        income_incl_vat = count * (provider_incl_vat + patient_incl_vat)
        rows.append({
            "activity": activity, "provider": provider, "count": count,
            "provider_rate": provider_rate, "vat_mode": vat_mode,
            "patient_payment": patient_payment,
            "income_pre_vat": income_pre_vat, "income_incl_vat": income_incl_vat,
        })
        total_pre_vat += income_pre_vat
        total_incl_vat += income_incl_vat

    return {"rows": rows, "unmapped": unmapped, "total_pre_vat": total_pre_vat,
            "total_income": total_incl_vat, "total_incl_vat": total_incl_vat}


def get_providers(therapists):
    return sorted({
        provider
        for therapist_data in therapists.values()
        for activity, provider, patient_payment in therapist_data["provider_counts"].keys()
        if provider != "Not specified"
    })

def build_monthly_rows(therapists):
    rows = []

    for therapist_name, therapist_data in therapists.items():
        result = calculate_salary(
            therapist_name,
            therapist_data["counts"],
        )

        clinic = calculate_clinic_income(therapist_data["provider_counts"])
        profile = result["profile"]

        if profile:
            employment = profile["employment_type"]
        else:
            employment = "Not set"

        rows.append(
            {
                "Name": therapist_name,
                "Employment": employment,
                "Pay structure": (
                    result["pay_info"]["pay_structure"]
                    if profile
                    else "Not set"
                ),
                "Subtotal": result["subtotal"],
                "VAT": result["vat"],
                "Total": result["total"],
                "Clinic pre VAT": clinic["total_pre_vat"],
                "Clinic incl VAT": clinic["total_incl_vat"],
                "Profit pre VAT": clinic["total_pre_vat"] - result["subtotal"],
                "Profile saved": (
                    "Yes" if profile else "No"
                ),
            }
        )

    return sorted(
        rows,
        key=lambda row: row["Name"],
    )


def create_accountant_csv(rows):
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(
        [
            "Therapist",
            "Salary month",
            "Amount to pay",
        ]
    )

    for row in rows:
        writer.writerow(
            [
                row["Name"],
                "August 2026",
                f"{row['Total']:.2f}",
            ]
        )

    return output.getvalue().encode("utf-8-sig")


create_database()

st.set_page_config(
    page_title="Salary Program",
    page_icon="💰",
    layout="wide",
)


try:
    therapists = load_therapists()

except FileNotFoundError:
    st.error(
        f"Could not find {CSV_FILE}"
    )
    st.stop()


therapist_names = sorted(
    name
    for name in therapists.keys()
    if not is_therapist_archived(name)
)

active_therapists = {
    name: therapists[name]
    for name in therapist_names
}


st.title("Salary Program")
st.caption("Therapist salary management")

page = st.sidebar.radio(
    "Menu",
    [
        "💰 Monthly Salaries",
        "👤 Therapists",
        "🏥 Providers",
        "⚙ Settings",
    ],
)


if page == "💰 Monthly Salaries":
    st.header("Monthly Salaries")

    st.subheader("Monthly Tipulog report")
    report_list = list_monthly_reports()
    report_months = [m for m, _ in report_list]
    if report_months:
        chosen_month = st.selectbox(
            "Salary month",
            report_months,
            index=report_months.index(SALARY_MONTH) if SALARY_MONTH in report_months else 0,
            key="salary_month_selector",
        )
        if chosen_month != SALARY_MONTH:
            set_selected_salary_month(chosen_month)
            st.rerun()

    up1, up2 = st.columns([1, 2])
    upload_month = up1.text_input("Month for new report (YYYY-MM)", value=SALARY_MONTH, key="upload_report_month")
    monthly_upload = up2.file_uploader("Upload Tipulog CSV", type=["csv"], key="monthly_tipulog_upload")
    replacing_existing = (REPORTS_DIR / f"{upload_month.strip()}.csv").exists()
    confirm_replace = True
    if replacing_existing and monthly_upload is not None:
        st.warning(f"A Tipulog report already exists for {upload_month}. Saving will replace that month's report.")
        confirm_replace = st.checkbox("I understand — replace the existing monthly report", key="confirm_report_replace")
    if st.button("Save monthly report", type="primary", disabled=monthly_upload is None or not confirm_replace, use_container_width=True):
        try:
            save_monthly_report(upload_month, monthly_upload)
            set_selected_salary_month(upload_month.strip())
            st.success(f"Tipulog report saved for {upload_month.strip()}.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))

    st.caption(f"Currently calculating from the saved Tipulog report for {SALARY_MONTH}.")
    st.divider()

    monthly_rows = build_monthly_rows(active_therapists)
    filter_choice = st.radio(
        "Show", ["All", "Employees", "Freelancers"], horizontal=True
    )

    if filter_choice == "Employees":
        visible_rows = [r for r in monthly_rows if r["Employment"] == "Employee"]
    elif filter_choice == "Freelancers":
        visible_rows = [r for r in monthly_rows if r["Employment"] == "Freelance"]
    else:
        visible_rows = monthly_rows

    table_rows = [{
        "Therapist": r["Name"],
        "Employment": r["Employment"],
        "Pay structure": r["Pay structure"],
        "Subtotal": f"₪{r['Subtotal']:,.2f}",
        "VAT": f"₪{r['VAT']:,.2f}",
        "Salary pre VAT": f"₪{r['Subtotal']:,.2f}",
        "Salary incl VAT": f"₪{r['Total']:,.2f}",
        "Clinic income pre VAT": f"₪{r['Clinic pre VAT']:,.2f}",
        "Clinic income incl VAT": f"₪{r['Clinic incl VAT']:,.2f}",
        "Profit pre VAT": f"₪{r['Profit pre VAT']:,.2f}",
        "Profile saved": r["Profile saved"],
    } for r in visible_rows]
    st.dataframe(table_rows, use_container_width=True, hide_index=True)
    t1, t2, t3, t4, t5 = st.columns(5)
    t1.metric("Salary pre VAT", f"₪{sum(r['Subtotal'] for r in visible_rows):,.2f}")
    t2.metric("Salary incl VAT", f"₪{sum(r['Total'] for r in visible_rows):,.2f}")
    t3.metric("Clinic income pre VAT", f"₪{sum(r['Clinic pre VAT'] for r in visible_rows):,.2f}")
    t4.metric("Clinic income incl VAT", f"₪{sum(r['Clinic incl VAT'] for r in visible_rows):,.2f}")
    t5.metric("Profit pre VAT", f"₪{sum(r['Profit pre VAT'] for r in visible_rows):,.2f}")

    if filter_choice == "Employees":
        employee_rows = [r for r in visible_rows if r["Profile saved"] == "Yes"]
        st.download_button(
            "Download Accountant Report",
            data=create_accountant_csv(employee_rows),
            file_name=f"accountant_report_{SALARY_MONTH.replace('-', '_')}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.divider()
    st.subheader("Individual calculation")

    if not therapist_names:
        st.info("There are no active therapists to display.")
    else:
        selected_therapist = st.selectbox(
            "Select therapist", therapist_names, key="monthly_therapist"
        )
        st.markdown(f"## {selected_therapist}")
        therapist_data = therapists[selected_therapist]
        result = calculate_salary(selected_therapist, therapist_data["counts"])
        clinic = calculate_clinic_income(therapist_data["provider_counts"])
        profile = result["profile"]

        if not profile:
            st.warning("This therapist does not have a saved profile yet.")
        else:
            info1, info2, info3, info4, info5 = st.columns(5)
            info1.metric("Employment", profile["employment_type"])
            info2.metric("Salary pre VAT", f"₪{result['subtotal']:,.2f}")
            info3.metric("Salary incl VAT", f"₪{result['total']:,.2f}")
            info4.metric("Clinic income pre VAT", f"₪{clinic['total_pre_vat']:,.2f}")
            info5.metric("Profit pre VAT", f"₪{clinic['total_pre_vat'] - result['subtotal']:,.2f}")

            if result["pay_info"]["pay_structure"] in (
                "Fixed monthly salary", "Fixed salary + activity"
            ):
                st.info(
                    "Monthly base salary: "
                    f"₪{result['pay_info']['monthly_salary']:,.2f}"
                )

            st.subheader("Activity breakdown")
            therapist_rates = load_rates(selected_therapist, SALARY_MONTH)
            provider_rates = load_provider_rates(SALARY_MONTH)
            active_categories = set(load_pay_categories())
            breakdown = []
            for (activity, provider, patient_payment), count in sorted(therapist_data["provider_counts"].items()):
                if activity == "ביטול - צוות":
                    therapist_rate = 0.0
                    therapist_pay = 0.0
                elif activity in active_categories:
                    therapist_rate = float(therapist_rates.get(activity, 0.0))
                    therapist_pay = count * therapist_rate
                else:
                    therapist_rate = 0.0
                    therapist_pay = 0.0

                provider_rate = float(provider_rates.get((provider, activity), 0.0))
                clinic_row = next((r for r in clinic["rows"] if r["activity"] == activity and r["provider"] == provider and r["patient_payment"] == patient_payment and r["count"] == count), None)
                clinic_pre_vat = clinic_row["income_pre_vat"] if clinic_row else 0.0
                clinic_incl_vat = clinic_row["income_incl_vat"] if clinic_row else 0.0
                activity_profit = clinic_pre_vat - therapist_pay
                breakdown.append({
                    "Activity": activity,
                    "Provider": provider,
                    "Quantity": count,
                    "Therapist rate": f"₪{therapist_rate:,.2f}",
                    "Provider rate": f"₪{provider_rate:,.2f}",
                    "Patient payment": f"₪{patient_payment:,.2f}",
                    "Therapist pay pre VAT": f"₪{therapist_pay:,.2f}",
                    "Clinic income pre VAT": f"₪{clinic_pre_vat:,.2f}",
                    "Clinic income incl VAT": f"₪{clinic_incl_vat:,.2f}",
                    "Activity profit pre VAT": (f"₪{activity_profit:,.2f}" if result["pay_info"]["pay_structure"] == "Per activity" else "Included in monthly total"),
                })
            st.dataframe(breakdown, use_container_width=True, hide_index=True)

            if result["unmapped"]:
                st.warning(
                    "Some Tipulog activity is not mapped yet and has NOT been included in salary."
                )
                for item in result["unmapped"]:
                    st.write(f"⚠ {item['activity']} — {item['count']}")

            st.divider()
            st.write(f"Subtotal: **₪{result['subtotal']:,.2f}**")
            if result["vat"] > 0:
                st.write(f"VAT 18%: **₪{result['vat']:,.2f}**")
            st.subheader(f"Total salary: ₪{result['total']:,.2f}")


elif page == "👤 Therapists":
    st.header("Therapists")

    if not therapist_names:
        st.info("There are no active therapists to display.")
        st.stop()

    selected_therapist = st.selectbox(
        "Select therapist", therapist_names, key="profile_therapist"
    )
    st.markdown(f"## {selected_therapist}")
    profile = load_profile(selected_therapist)
    personal = load_personal_details(selected_therapist)
    saved_rates = load_rates(selected_therapist)
    saved_pay_info = load_pay_structure(selected_therapist)

    if profile:
        st.success("Saved therapist profile")
    else:
        st.warning("Therapist profile has not been saved yet")

    st.subheader("Personal information")
    p1, p2, p3, p4 = st.columns(4)
    personal["id_number"] = p1.text_input("ID number", personal["id_number"], key=f"id_{selected_therapist}")
    personal["birth_date"] = p2.text_input("Date of birth", personal["birth_date"], key=f"dob_{selected_therapist}")
    personal["phone"] = p3.text_input("Phone", personal["phone"], key=f"phone_{selected_therapist}")
    personal["email"] = p4.text_input("Email", personal["email"], key=f"email_{selected_therapist}")
    p5, p6, p7, p8 = st.columns(4)
    personal["address"] = p5.text_input("Address", personal["address"], key=f"address_{selected_therapist}")
    personal["profession"] = p6.text_input("Profession / role", personal["profession"], key=f"profession_{selected_therapist}")
    personal["start_date"] = p7.text_input("Start date", personal["start_date"], key=f"start_{selected_therapist}")
    personal["employee_number"] = p8.text_input("Employee number", personal["employee_number"], key=f"empno_{selected_therapist}")
    b1, b2, b3 = st.columns(3)
    personal["bank_name"] = b1.text_input("Bank", personal["bank_name"], key=f"bank_{selected_therapist}")
    personal["bank_branch"] = b2.text_input("Branch", personal["bank_branch"], key=f"branch_{selected_therapist}")
    personal["bank_account"] = b3.text_input("Account number", personal["bank_account"], key=f"account_{selected_therapist}")

    if profile and profile["employment_type"] == "Employee":
        st.subheader("Pension")
        pen1, pen2, pen3 = st.columns(3)
        pension_options = ["Unknown", "Yes", "No"]
        saved_existing = personal.get("existing_pension", "Unknown")
        if saved_existing not in pension_options:
            saved_existing = "Unknown"
        personal["existing_pension"] = pen1.selectbox(
            "Had an active pension arrangement when employment began?",
            pension_options,
            index=pension_options.index(saved_existing),
            key=f"existing_pension_{selected_therapist}",
        )
        personal["pension_reminder_email"] = pen2.text_input(
            "Reminder email",
            personal.get("pension_reminder_email", ""),
            placeholder="Email address for pension reminder",
            key=f"pension_email_{selected_therapist}",
        )
        personal["pension_reminder_days"] = int(pen3.number_input(
            "Remind me this many days before",
            min_value=1, max_value=120,
            value=int(personal.get("pension_reminder_days", 30) or 30),
            step=1,
            key=f"pension_days_{selected_therapist}",
        ))
        pension_dates = calculate_pension_dates(
            personal.get("start_date", ""), personal["existing_pension"], personal["pension_reminder_days"]
        )
        if pension_dates and pension_dates.get("error"):
            st.warning(pension_dates["error"])
        elif pension_dates:
            pc1, pc2, pc3 = st.columns(3)
            pc1.metric("Pension entitlement from", pension_dates["entitlement_from"].strftime("%d/%m/%Y"))
            pc2.metric("Pension action due", pension_dates["action_due"].strftime("%d/%m/%Y"))
            pc3.metric("Email reminder date", pension_dates["reminder_date"].strftime("%d/%m/%Y"))
            st.caption(pension_dates["explanation"])
            today = datetime.now().date()
            if today >= pension_dates["reminder_date"]:
                st.warning("⚠ Pension action reminder is due now." if today <= pension_dates["action_due"] else "⚠ Pension action date has passed.")
        st.caption("The reminder date is saved/calculated here. Automatic email delivery will activate when the online app is connected to an email service; the local app cannot send scheduled email while it is closed.")

    documents = load_therapist_documents(selected_therapist)
    doc_status = therapist_document_status(documents)
    status_cols = st.columns(5)
    for col, label in zip(status_cols, ["Form 101", "Contract", "Tofes Kubiyot", "Professional license", "Diploma / degree"]):
        col.metric(label, "✓ Saved" if doc_status[label] else "— Missing")

    st.subheader("Documents")
    st.caption("Documents are saved inside the therapist's profile database and remain available when you reopen the app.")
    d1, d2 = st.columns([1, 2])
    document_type = d1.selectbox(
        "Document type",
        ["Form 101", "Contract", "Tofes Kubiyot", "Professional license", "Diploma / degree", "Other"],
        key=f"doc_type_{selected_therapist}",
    )
    document_title = d1.text_input(
        "Document name / description",
        placeholder="Optional, e.g. Speech Therapy license",
        key=f"doc_title_{selected_therapist}",
    )
    document_upload = d2.file_uploader(
        "Upload document",
        type=["pdf", "png", "jpg", "jpeg", "doc", "docx"],
        key=f"doc_upload_{selected_therapist}",
    )
    if st.button("Save document", type="primary", disabled=document_upload is None, key=f"save_doc_{selected_therapist}"):
        save_therapist_document(selected_therapist, document_type, document_title, document_upload)
        st.success(f"{document_type} saved for {selected_therapist}.")
        st.rerun()

    if documents:
        for doc in documents:
            dc1, dc2, dc3, dc4 = st.columns([2, 3, 2, 1])
            dc1.write(f"**{doc['type']}**")
            dc2.write(doc['title'] or doc['filename'])
            dc3.download_button(
                "Open / Download",
                data=doc["content"],
                file_name=doc["filename"],
                mime=doc["mime"],
                key=f"download_doc_{doc['id']}",
                use_container_width=True,
            )
            if dc4.button("Delete", key=f"delete_doc_{doc['id']}"):
                delete_therapist_document(doc["id"])
                st.rerun()
    else:
        st.info("No documents saved for this therapist yet.")

    st.caption("Personal details can be entered manually above. Form 101 is now stored here; automatic field-reading from Form 101 can be added without changing the saved profile structure.")
    st.divider()

    left, right = st.columns([1, 2])

    with left:
        st.subheader("Profile")
        saved_employment = profile["employment_type"] if profile else "Employee"
        employment_options = ["Employee", "Freelance"]
        employment_type = st.radio(
            "Employment type",
            employment_options,
            index=employment_options.index(saved_employment),
            horizontal=True,
            key=f"employment_{selected_therapist}",
        )

        vat_status = None
        if employment_type == "Freelance":
            vat_options = ["עוסק פטור — no VAT", "עוסק מורשה — +18% VAT"]
            saved_vat = (
                profile["vat_status"]
                if profile and profile["vat_status"] in vat_options
                else vat_options[0]
            )
            vat_status = st.radio(
                "Freelance status",
                vat_options,
                index=vat_options.index(saved_vat),
                key=f"vat_{selected_therapist}",
            )

        st.subheader("Pay structure")
        pay_structure_options = [
            "Per activity", "Fixed monthly salary", "Fixed salary + activity"
        ]
        current_pay_structure = saved_pay_info["pay_structure"]
        if current_pay_structure == "Manager / Supervisor":
            current_pay_structure = "Fixed salary + activity"
        if current_pay_structure not in pay_structure_options:
            current_pay_structure = "Per activity"

        pay_structure = st.radio(
            "How is this therapist paid?",
            pay_structure_options,
            index=pay_structure_options.index(current_pay_structure),
            key=f"pay_structure_{selected_therapist}",
        )

        monthly_salary = 0.0
        if pay_structure in ("Fixed monthly salary", "Fixed salary + activity"):
            monthly_salary = st.number_input(
                "Monthly salary (NIS)",
                min_value=0.0,
                value=max(0.0, float(saved_pay_info["monthly_salary"])),
                step=100.0,
                format="%.2f",
                key=f"monthly_salary_{selected_therapist}",
            )

        effective_from = st.text_input(
            "Effective from",
            value=profile["effective_from"] if profile else SALARY_MONTH,
            key=f"effective_{selected_therapist}",
        )

    with right:
        st.subheader(f"{SALARY_MONTH} activity")
        counts = therapists[selected_therapist]["counts"]
        if counts:
            for meeting_type, count in sorted(counts.items()):
                st.write(f"**{meeting_type}** — {count}")
        else:
            st.write("No activity found.")

        st.divider()
        if pay_structure in ("Per activity", "Fixed salary + activity"):
            st.subheader("Pay rates")
            rates = {}
            for category in load_pay_categories():
                rates[category] = st.number_input(
                    category,
                    min_value=-10000.0,
                    value=float(saved_rates.get(category, 0)),
                    step=5.0,
                    format="%.2f",
                    key=f"rate_{selected_therapist}_{category}",
                )
            if pay_structure == "Fixed salary + activity":
                st.info(
                    "Salary is calculated as the monthly base salary plus payable activity using the rates above."
                )
                st.metric("Monthly base salary", f"₪{monthly_salary:,.2f}")
        else:
            rates = saved_rates
            st.subheader("Fixed monthly salary")
            st.write(
                "This therapist's salary is not calculated by multiplying Tipulog sessions by a rate."
            )
            st.metric("Monthly base salary", f"₪{monthly_salary:,.2f}")
            st.write("Tipulog activity is still shown above for checking.")

    st.divider()
    if st.button("Save changes", type="primary", use_container_width=True):
        save_therapist(
            selected_therapist, employment_type, vat_status, pay_structure,
            monthly_salary, effective_from, rates
        )
        save_personal_details(selected_therapist, personal)
        st.success(
            f"{selected_therapist}'s profile, pay structure and rates were saved."
        )

    st.divider()
    st.subheader("Archive therapist")
    st.caption(
        "Archiving removes this therapist from the active lists without deleting their saved profile, rates or salary settings."
    )
    if st.button("Archive therapist", key=f"archive_{selected_therapist}"):
        set_therapist_archived(selected_therapist, True)
        st.success(f"{selected_therapist} was archived.")
        st.rerun()


elif page == "🏥 Providers":
    st.header("Providers")
    st.caption("Provider profiles and clinic income rates")

    providers = get_providers(active_therapists)
    if not providers:
        st.info("No funding providers were found in the Tipulog report.")
    else:
        selected_provider = st.selectbox(
            "Select provider", providers, key="provider_profile"
        )
        st.subheader(selected_provider)
        st.write(
            "Clinic income rates use the same Pay Categories master list as therapist pay rates."
        )

        saved_provider_rates = load_provider_rates()
        vat_modes = ["Plus VAT", "VAT included", "No VAT"]
        current_vat_mode = load_provider_vat_mode(selected_provider, SALARY_MONTH)
        provider_vat_mode = st.radio("Provider rate VAT treatment", vat_modes, index=vat_modes.index(current_vat_mode) if current_vat_mode in vat_modes else 0, horizontal=True)
        provider_values = {}
        for category in load_pay_categories():
            provider_values[category] = st.number_input(
                category,
                min_value=0.0,
                value=float(saved_provider_rates.get((selected_provider, category), 0.0)),
                step=5.0,
                format="%.2f",
                key=f"provider_rate_{selected_provider}_{category}",
            )

        effective_from = st.text_input(
            "Effective from", value=SALARY_MONTH, key=f"provider_effective_{selected_provider}"
        )
        if st.button("Save provider profile", type="primary", use_container_width=True):
            for category, rate in provider_values.items():
                save_provider_rate(selected_provider, category, rate, effective_from)
            save_provider_vat_mode(selected_provider, provider_vat_mode, effective_from)
            st.success(f"{selected_provider} rates were saved.")


elif page == "⚙ Settings":
    st.header("Settings")

    st.subheader("VAT")
    current_vat = load_setting("clinic_vat_rate", SALARY_MONTH, 18.0)
    vat_value = st.number_input("VAT rate (%)", min_value=0.0, max_value=100.0, value=float(current_vat), step=0.1, format="%.1f")
    vat_effective = st.text_input("VAT effective from", value=SALARY_MONTH, key="vat_effective")
    if st.button("Save VAT setting", type="primary"):
        save_setting("clinic_vat_rate", vat_value, vat_effective)
        st.success("VAT setting saved.")
        st.rerun()
    st.caption("Tipulog patient-payment amounts are treated as VAT-inclusive receipts. Provider rates use the VAT treatment saved on each provider profile.")

    st.divider()
    st.subheader("Archived Therapists")
    archived_therapists = load_archived_therapists()
    if archived_therapists:
        st.write(
            "Archived therapists do not appear in the normal therapist or salary dropdowns."
        )
        for archived_name in archived_therapists:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"**{archived_name}**")
            with col2:
                if st.button("Reactivate", key=f"reactivate_{archived_name}"):
                    set_therapist_archived(archived_name, False)
                    st.success(f"{archived_name} was reactivated.")
                    st.rerun()
    else:
        st.info("No archived therapists.")

    st.divider()
    st.subheader("Pay Categories")
    st.write(
        "This is the shared master list used for therapist pay rates and provider clinic-income rates."
    )

    new_category = st.text_input("New category", key="new_pay_category")
    if st.button("Add category", type="primary"):
        if add_pay_category(new_category):
            st.success(f"Added: {new_category.strip()}")
            st.rerun()
        else:
            st.warning("Enter a category name.")

    st.divider()
    st.write("Current categories")
    for category, active in load_pay_categories(active_only=False):
        col1, col2, col3 = st.columns([4, 1, 1])
        with col1:
            edited_name = st.text_input(
                "Category name",
                value=category,
                key=f"category_name_{category}",
                label_visibility="collapsed",
            )
        with col2:
            if st.button("Rename", key=f"rename_{category}"):
                if rename_pay_category(category, edited_name):
                    st.success("Category renamed.")
                    st.rerun()
                else:
                    st.warning("That name is empty, unchanged, or already exists.")
        with col3:
            button_label = "Deactivate" if active else "Activate"
            if st.button(button_label, key=f"active_{category}"):
                set_pay_category_active(category, not bool(active))
                st.rerun()
