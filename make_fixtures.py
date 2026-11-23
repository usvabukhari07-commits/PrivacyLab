import csv
import os
import random

random.seed(1)
os.makedirs("fixtures", exist_ok=True)

HEADER = ["name_id", "department", "age", "salary"]
depts = ["HR", "IT", "Sales", "Finance"]

# 1. Good file: 200 normal rows
with open("fixtures/employees.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(HEADER)
    for i in range(200):
        w.writerow([f"E{i:03d}", random.choice(depts), random.randint(22, 60), random.randint(40000, 200000)])

# 2. Malicious: formula injection in a text column
with open("fixtures/bad_formula.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(HEADER)
    w.writerow(["E001", "=cmd|' /C calc'!A0", 30, 50000])
    w.writerow(["E002", "IT", 31, 60000])

# 3. Oversized: about 4 MB, should be rejected (limit is 2 MB)
with open("fixtures/too_big.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(HEADER)
    for i in range(200000):
        w.writerow([f"E{i}", "IT", 30, 50000])

# 4. Small-group test: three tiny "Legal" department rows
with open("fixtures/small_groups.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(HEADER)
    for i in range(90):
        w.writerow([f"S{i:03d}", ["HR", "IT", "Sales"][i % 3], random.randint(22, 60), random.randint(40000, 200000)])
    for i in range(3):
        w.writerow([f"L{i}", "Legal", 40, 90000])

print("Fixtures created in ./fixtures")