import pytest

from app.engine.schema import validate_csv, MAX_BYTES
from tests.helpers import make_csv, BOUNDS

HEADER_LINE = "name_id,department,age,salary\n"


def codes(result):
    return [e.split(":")[0] for e in result["errors"]]


def test_valid_file_is_accepted():
    r = validate_csv(make_csv(), "employees.csv", BOUNDS)
    assert r["ok"] is True
    assert r["rows"] == 200
    assert r["columns"] == ["name_id", "department", "age", "salary"]


def test_out_of_bounds_values_give_warning_not_error():
    r = validate_csv(make_csv(), "employees.csv", "age:18:100,salary:0:100000")
    assert r["ok"] is True
    assert any(w.startswith("W_OUT_OF_BOUNDS") for w in r["warnings"])


def test_wrong_extension_rejected():
    assert "E_FILE_TYPE" in codes(validate_csv(make_csv(), "data.exe", BOUNDS))


def test_oversized_file_rejected():
    assert "E_FILE_SIZE" in codes(validate_csv(b"a" * (MAX_BYTES + 1), "x.csv", ""))


def test_empty_file_rejected():
    assert "E_FILE_EMPTY" in codes(validate_csv(b"", "x.csv", ""))


def test_binary_content_rejected():
    assert "E_FILE_BINARY" in codes(validate_csv(b"a,b\n1,\x00\n", "x.csv", ""))


def test_non_utf8_rejected():
    assert "E_ENCODING" in codes(validate_csv(b"a,b\n\xff,\xfe\n", "x.csv", ""))


def test_duplicate_columns_rejected():
    assert "E_DUPLICATE_COLUMNS" in codes(validate_csv(b"a,a\n1,2\n", "x.csv", ""))


def test_bad_column_name_rejected():
    assert "E_COLUMN_NAME" in codes(validate_csv(b"my col,b\n1,2\n", "x.csv", ""))


def test_too_many_columns_rejected():
    header = ",".join(f"c{i}" for i in range(21))
    row = ",".join("1" for _ in range(21))
    raw = (header + "\n" + row + "\n").encode()
    assert "E_TOO_MANY_COLUMNS" in codes(validate_csv(raw, "x.csv", ""))


def test_too_many_rows_rejected():
    raw = b"a\n" + b"1\n" * 10001
    assert "E_TOO_MANY_ROWS" in codes(validate_csv(raw, "x.csv", ""))


def test_header_only_file_rejected():
    assert "E_NO_ROWS" in codes(validate_csv(b"a,b\n", "x.csv", ""))


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
def test_formula_injection_rejected(prefix):
    raw = (HEADER_LINE + f"E1,{prefix}1+1,30,50000\nE2,IT,31,60000\n").encode()
    assert "E_FORMULA_INJECTION" in codes(validate_csv(raw, "x.csv", BOUNDS))


def test_non_numeric_value_in_bounded_column_rejected():
    raw = (HEADER_LINE + "E1,IT,abc,50000\n").encode()
    assert "E_NOT_NUMERIC" in codes(validate_csv(raw, "x.csv", BOUNDS))


def test_bounds_for_missing_column_rejected():
    assert "E_BOUNDS_COLUMN" in codes(validate_csv(make_csv(), "x.csv", "height:1:2"))


@pytest.mark.parametrize("bounds,expected", [
    ("age:18", "E_BOUNDS_FORMAT"),
    ("age:a:b", "E_BOUNDS_FORMAT"),
    ("age:100:18", "E_BOUNDS_RANGE"),
])
def test_bad_bounds_text_rejected(bounds, expected):
    assert expected in codes(validate_csv(make_csv(), "x.csv", bounds))