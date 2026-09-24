import csv
import re
from collections import Counter

CSV_FILE = "PaymentAndBudgetReport24_09_2026_12_33.csv"
VAT_RATE = 0.18

# Pay categories that can be given an individual rate
PAY_CATEGORIES = {
    "טיפול": 0,
    "טיפול פסיכותרפיה": 0,
    "קלינאית תקשורת": 0,
    "ריפוי בעיסוק": 0,
    "ביטול": 0,
    "אבחון": 0,
    "קבוצה": 0,
    "דו״ח": 0,
    "הדרכה": 0,
    "ישיבת צוות": 0,
    "הכנה": 0,
    "מעקב": 0,
    "הערכה פסיכיאטרית": 0,
    "המלצה לצה״ל": 0,
}

# Therapist profiles.
# Later these settings will be edited from the program itself.
therapist_profiles = {}

therapists = {}
current_therapist = None
inside_meetings = False

with open(CSV_FILE, "r", encoding="utf-8-sig", newline="") as file:
    reader = csv.reader(file)

    for row in reader:
        row += [""] * (17 - len(row))

        marker = row[4].strip()

        match = re.search(r"מפגשים עבור (.+?)-*$", marker)

        if match:
            current_therapist = match.group(1).strip("- ").strip()
            therapists.setdefault(current_therapist, Counter())
            inside_meetings = False
            continue

        if current_therapist and row[0].strip() == "תאריך מפגש":
            inside_meetings = True
            continue

        if inside_meetings:
            date = row[0].strip()
            meeting_type = row[3].strip()

            if re.fullmatch(r"\d{2}/\d{2}/\d{4}", date) and meeting_type:
                therapists[current_therapist][meeting_type] += 1

for therapist, counts in therapists.items():
    print()
    print("=" * 50)
    print(therapist)

    profile = therapist_profiles.get(therapist)

    if profile:
        print(f"Employment: {profile.get('employment_type', 'NOT SET')}")
        print(f"VAT status: {profile.get('vat_status', 'NOT SET')}")
    else:
        print("Profile: NOT SET YET")

    print()
    print("Activity found:")

    for meeting_type, count in counts.items():
        print(f"  {meeting_type}: {count}")

    print()
    print("Pay rates:")

    for category, default_rate in PAY_CATEGORIES.items():
        if profile:
            rates = profile.get("rates", {})
            rate = rates.get(category, default_rate)
        else:
            rate = default_rate

        print(f"  {category}: {rate} NIS")