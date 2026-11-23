import csv
import io
import re
import pandas as pd

MAX_BYTES = 2 * 1024 * 1024   # 2 MB
MAX_ROWS = 10000
MAX_COLS = 20
COL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,39}$")
FORMULA_PREFIXES = ("=", "+", "-", "@")


def parse_bounds(text: str):
    """Parse 'age:18:100,salary:0:300000' into {'age': (18.0, 100.0), ...}"""
    bounds, errors = {}, []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        pieces = part.split(":")
        if len(pieces) != 3:
            errors.append("E_BOUNDS_FORMAT: use column:min:max")
            continue
        col, lo, hi = pieces[0].strip(), pieces[1], pieces[2]
        try:
            lo, hi = float(lo), float(hi)
        except ValueError:
            errors.append(f"E_BOUNDS_FORMAT: min/max for '{col[:30]}' must be numbers")
            continue
        if lo >= hi:
            errors.append(f"E_BOUNDS_RANGE: min must be less than max for '{col[:30]}'")
            continue
        bounds[col] = (lo, hi)
    return bounds, errors


def validate_csv(raw: bytes, filename: str, bounds_text: str) -> dict:
    result = {"ok": False, "errors": [], "warnings": [], "columns": [], "rows": 0, "bounds": {}}
    errors = result["errors"]

    # 1. File-level checks
    if not filename.lower().endswith(".csv"):
        errors.append("E_FILE_TYPE: only .csv files are accepted")
    if len(raw) > MAX_BYTES:
        errors.append(f"E_FILE_SIZE: file larger than {MAX_BYTES // (1024 * 1024)} MB")
    if len(raw) == 0:
        errors.append("E_FILE_EMPTY: file is empty")
    if b"\x00" in raw:
        errors.append("E_FILE_BINARY: file is not a text CSV")
    if errors:
        return result

    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        errors.append("E_ENCODING: file must be UTF-8 text")
        return result

    # 2. Header checks
    try:
        header = next(csv.reader(io.StringIO(text)))
    except Exception:
        errors.append("E_CSV_PARSE: could not read header")
        return result
    header = [h.strip() for h in header]
    if len(header) > MAX_COLS:
        errors.append(f"E_TOO_MANY_COLUMNS: max {MAX_COLS}")
    if len(set(header)) != len(header):
        errors.append("E_DUPLICATE_COLUMNS: column names must be unique")
    if not all(COL_RE.match(h) for h in header):
        errors.append("E_COLUMN_NAME: use letters, digits, underscore only (start with a letter)")
    if errors:
        return result

    # 3. Parse body (as text, so nothing is auto-converted)
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    except Exception:
        errors.append("E_CSV_PARSE: file structure is invalid (check commas/quotes)")
        return result
    df.columns = header
    if len(df) == 0:
        errors.append("E_NO_ROWS: file has no data rows")
    if len(df) > MAX_ROWS:
        errors.append(f"E_TOO_MANY_ROWS: max {MAX_ROWS}")
    if errors:
        return result

    # 4. Bounds for numeric columns
    bounds, b_errors = parse_bounds(bounds_text)
    errors.extend(b_errors)
    for col, (lo, hi) in bounds.items():
        if col not in df.columns:
            errors.append(f"E_BOUNDS_COLUMN: '{col[:30]}' not found in file")
            continue
        nums = pd.to_numeric(df[col], errors="coerce")
        bad = int(nums.isna().sum())
        if bad:
            errors.append(f"E_NOT_NUMERIC: column '{col}' has {bad} non-numeric values")
            continue
        outside = int(((nums < lo) | (nums > hi)).sum())
        if outside:
            result["warnings"].append(
                f"W_OUT_OF_BOUNDS: {outside} values in '{col}' outside [{lo}, {hi}] (will be clamped)"
            )

    # 5. CSV/formula injection in text columns
    for col in df.columns:
        if col in bounds:
            continue
        if df[col].apply(lambda v: v.startswith(FORMULA_PREFIXES)).any():
            errors.append(f"E_FORMULA_INJECTION: column '{col}' has cells starting with = + - or @")

    if errors:
        return result

    result.update(ok=True, columns=list(df.columns), rows=len(df), bounds=bounds)
    return result
