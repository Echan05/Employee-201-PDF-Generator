import csv
import json
import urllib.request
from collections import Counter, defaultdict

BASE_URL = "https://cmiitdept.com/hr"
MAIN_URL = f"{BASE_URL}/api_hr_201_01_main.php"
LICENSE_URL = "https://ar-api.wms.cmatrixinc.com/api/mtc/licenses/latest"
LICENSE_ID_FIELD = "employee_id"

# name -> (endpoint, pooling field that should match 01's rm_tran_no)
CHILD_APIS = {
    "02_parents":    ("api_hr_201_02_parents.php",    "fam_pooling"),
    "03_education":  ("api_hr_201_03_educ.php",       "edu_pool_id"),
    "04_employment": ("api_hr_201_04_employment.php", "history_pooling"),
    "05_training":   ("api_hr_201_05_traning.php",    "training_pooling_no"),
    "06_minor":      ("api_hr_201_06_minor.php",      "minor_pooling"),
}
BAD_IDS = {"", "0", "none", "null"}


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)


def records(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for value in data.values():
            if isinstance(value, list):
                return value
    return []


def clean(value):
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in BAD_IDS else text


def column(recs, key):
    out = set()
    for r in recs:
        v = clean(r.get(key)) if isinstance(r, dict) else None
        if v:
            out.add(v)
    return out


# 1. Main API: erms_id -> its rm_tran_no values (an employee can have several rows)
main = records(fetch(MAIN_URL))
emp_to_tran = defaultdict(set)
for r in main:
    emp, tran = clean(r.get("erms_id")), clean(r.get("rm_tran_no"))
    if emp:
        emp_to_tran[emp]  # creates the key even when rm_tran_no is blank
        if tran:
            emp_to_tran[emp].add(tran)
all_trans = {t for ts in emp_to_tran.values() for t in ts}

print(f"01_main: {len(main)} rows, {len(emp_to_tran)} valid erms_id, "
      f"{len(all_trans)} distinct rm_tran_no")
print(f"   employees with more than one rm_tran_no: "
      f"{sum(1 for ts in emp_to_tran.values() if len(ts) > 1)}")
print(f"   sample rm_tran_no: {sorted(all_trans)[:3]}")

# 2. Child APIs: pooling field vs 01 rm_tran_no (this is the checkpoint)
child_pools = {}
print("\nJoin check (pooling field vs 01 rm_tran_no):")
for name, (endpoint, field) in CHILD_APIS.items():
    recs = records(fetch(f"{BASE_URL}/{endpoint}"))
    pool = column(recs, field)
    child_pools[name] = pool
    print(f"   {name}: {len(recs)} rows, {len(pool)} distinct {field}, "
          f"{len(pool & all_trans)} match")
    print(f"      sample {field}: {sorted(pool)[:3]}")

# 3. License API
lic = records(fetch(LICENSE_URL))
license_ids = column(lic, LICENSE_ID_FIELD)
print(f"\nlicense: {len(lic)} rows, {len(license_ids)} distinct {LICENSE_ID_FIELD}")
print(f"   sample {LICENSE_ID_FIELD}: {sorted(license_ids)[:3]}")
print(f"   match 01 erms_id: {len(license_ids & set(emp_to_tran))}")
print(f"   match 01 rm_tran_no: {len(license_ids & all_trans)}")

# 4. Rank employees: in license first, then most 02-06 coverage
rows = []
for emp, trans in emp_to_tran.items():
    hits = sorted(n for n, pool in child_pools.items() if trans & pool)
    rows.append((emp in license_ids, len(hits), emp, hits))
rows.sort(reverse=True)

dist = Counter((flag, n) for flag, n, _, _ in rows)
print("\nDistribution, (in_license, 02-06 coverage out of 5): employees")
for key in sorted(dist, reverse=True):
    print(f"   {key}: {dist[key]}")

print("\nTop 20:")
for flag, n, emp, hits in rows[:20]:
    print(f"   erms_id={emp} license={flag} coverage={n}/5 {hits}")

with open("candidates.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["erms_id", "in_license", "coverage_02_06", "found_in"])
    for flag, n, emp, hits in rows:
        w.writerow([emp, flag, n, ";".join(hits)])
print("\nWrote candidates.csv (IDs and coverage only)")