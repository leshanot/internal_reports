import sqlite3

c = sqlite3.connect("salary_program.db")

rows = c.execute(
    "SELECT therapist_name, category, rate, effective_from FROM therapist_rates WHERE therapist_name LIKE ? OR therapist_name LIKE ? OR therapist_name LIKE ?",
    ("%שני%", "%שפע%", "%קוגן%"),
).fetchall()

print(rows)
c.close()