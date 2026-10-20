import csv
import json
import urllib.request
from collections import Counter

BASE_URL = "https://cmiitdept.com/hr"
MAIN_URL = f"{BASE_URL}/api_hr_201_01_main.php"
LICENSE_URL = "https://ar-api.wms.cmatrixinc.com/api/mtc/licenses/latest"

MAIN_ID_FIELD = "erms_id"          # 01 -> license employee_id
LICENSE_ID_FIELD = "employee_id"
MAIN_TRAN_FIELD = "rm_tran_no"     # 01 -> pooling field in 02-06

CHILD_APIS = {
    "02_parents":    ("api_hr_201_02_parents.php",    "fam_pooling"),
    "03_education":  ("api_hr_201_03_educ.php",       "edu_pool_id"),
    "04_employment": ("api_hr_201_04_employment.php", "history_pooling"),
    "05_training":   ("api_hr_201_05_traning.php",    "training_pooling_no"),
    "06_minor":      ("api_hr_201_06_minor.php",      "minor_pooling"),
}

# Exact field names as returned by 01 (the API spells it "heath_card_image")
FILE_FIELDS = (
    "gcash_image", "sss_image", "drug_test_image", "valid_id_image",
    "valid_id_image_rear", "heath_card_image", "hcb_image", "pag_image",
    "ph_image", "nbi_image", "ub_image", "signed_contract",
)

EMPTY_VALUES = {"", "0", "null", "none", "n/a"}


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
    """Stripped string, or None when the value is empty/placeholder."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in EMPTY_VALUES else text


def column(recs, key):
    out = set()
    for r in recs:
        v = clean(r.get(key)) if isinstance(r, dict) else None
        if v:
            out.add(v)
    return out


def file_state(value):
    """'file' = a filename follows the last '/', 'folder_only' = bare folder URL
    (like https://cmiitdept.com/hr/upload_remarks/), 'empty' = null/blank."""
    text = clean(value)
    if not text:
        return "empty"
    return "file" if text.split("/")[-1].strip() else "folder_only"


# ---- Stage 1: file fields in the main API ----------------------------------
main = records(fetch(MAIN_URL))

emp_to_tran = {}    # erms_id -> set of rm_tran_no (an employee can have several rows)
emp_files = {}      # erms_id -> {field: True if any row has a real filename}
row_states = {f: Counter() for f in FILE_FIELDS}

for r in main:
    emp = clean(r.get(MAIN_ID_FIELD))
    if not emp:
        continue
    trans = emp_to_tran.setdefault(emp, set())
    files = emp_files.setdefault(emp, {f: False for f in FILE_FIELDS})
    tran = clean(r.get(MAIN_TRAN_FIELD))
    if tran:
        trans.add(tran)
    for f in FILE_FIELDS:
        state = file_state(r.get(f))
        row_states[f][state] += 1
        if state == "file":
            files[f] = True

all_trans = {t for ts in emp_to_tran.values() for t in ts}
print(f"01_main: {len(main)} rows, {len(emp_to_tran)} valid {MAIN_ID_FIELD}")

print("\nStage 1 - file fields in 01 (employees with a real filename):")
for f in FILE_FIELDS:
    n = sum(1 for e in emp_files.values() if e[f])
    s = row_states[f]
    print(f"   {f:<20} {n:>6} employees | rows: file={s['file']} "
          f"folder_only={s['folder_only']} empty={s['empty']}")

total_fields = len(FILE_FIELDS)
dist = Counter(sum(flags.values()) for flags in emp_files.values())
print(f"\nEmployees by number of file fields filled (out of {total_fields}):")
for k in sorted(dist, reverse=True):
    print(f"   {k:>2}/{total_fields}: {dist[k]}")

# ---- Stage 2: child APIs (rm_tran_no vs pooling field) ----------------------
child_pools = {}
print("\nStage 2 - join check (pooling field vs 01 rm_tran_no):")
for name, (endpoint, field) in CHILD_APIS.items():
    recs = records(fetch(f"{BASE_URL}/{endpoint}"))
    pool = column(recs, field)
    child_pools[name] = pool
    print(f"   {name}: {len(recs)} rows, {len(pool)} distinct {field}, "
          f"{len(pool & all_trans)} match")

# ---- Stage 3: license API (erms_id vs employee_id) --------------------------
lic = records(fetch(LICENSE_URL))
license_ids = column(lic, LICENSE_ID_FIELD)
not_in_main = license_ids - set(emp_to_tran)
print(f"\nStage 3 - license: {len(lic)} rows, {len(license_ids)} distinct {LICENSE_ID_FIELD}, "
      f"{len(license_ids) - len(not_in_main)} found in 01, {len(not_in_main)} not in 01")

# ---- Per-employee results ---------------------------------------------------
rows = []
for emp, trans in emp_to_tran.items():
    flags = emp_files[emp]
    hits = sorted(n for n, pool in child_pools.items() if trans & pool)
    row = {
        "erms_id": emp,
        "in_license": emp in license_ids,
        "files_filled": sum(flags.values()),
        "missing": ";".join(f for f in FILE_FIELDS if not flags[f]),
        "coverage_02_06": len(hits),
        "found_in": ";".join(hits),
    }
    row.update({f: flags[f] for f in FILE_FIELDS})
    rows.append(row)

rows.sort(key=lambda r: (r["in_license"], r["files_filled"], r["coverage_02_06"]),
          reverse=True)

with open("overlap_results.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)

full = [r for r in rows if r["files_filled"] == total_fields]
lic_rows = [r for r in rows if r["in_license"]]

print(f"\nEmployees with all {total_fields} file fields: {len(full)}, "
      f"of those in license: {sum(1 for r in full if r['in_license'])}")

print(f"\nLicensed employees by files filled (out of {total_fields}):")
lic_dist = Counter(r["files_filled"] for r in lic_rows)
for k in sorted(lic_dist, reverse=True):
    print(f"   {k:>2}/{total_fields}: {lic_dist[k]}")

print("\nLicensed employees, most files first (up to 30):")
for r in lic_rows[:30]:
    print(f"   erms_id={r['erms_id']} files={r['files_filled']}/{total_fields} "
          f"coverage_02_06={r['coverage_02_06']}/5 missing=[{r['missing']}]")

print("\nWrote overlap_results.csv (one row per employee, one True/False column per file field)")