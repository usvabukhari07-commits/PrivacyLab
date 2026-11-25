# User guide (analysts and viewers)

## What PrivacyLab does
PrivacyLab lets you ask questions about a dataset (how many people, total, average) without exposing
any individual. Every answer has random noise added, so it is close to the truth but never exact.
Each question uses part of a limited privacy budget (epsilon). When the budget is used up, no more
questions can be asked about that dataset.

## Roles
| Role | What you can do |
|---|---|
| Analyst | Upload CSV files, run private queries, view released results, download a sanitized report |
| Viewer | View released (noisy) results only |
| Admin | Everything an analyst can do, plus the admin page, accuracy report and audit log (see the admin guide) |

## Logging in
1. Open `http://localhost:8000`.
2. Enter your username and password and click **Log in**.
3. Sessions expire after 30 minutes. After 5 wrong passwords you are blocked for 5 minutes.

## Uploading a dataset (analysts)
1. On the dashboard, click **Choose File** and select a `.csv` file.
2. Declare bounds for every numeric column you want to use in sums or averages, in the form
   `column:min:max`, separated by commas. Example: `age:18:100,salary:0:300000`.
   Values outside the bounds are clipped to them; this is what keeps the privacy guarantee valid.
3. Click **Upload**. A green message shows the number of rows accepted.

File rules: `.csv` only, at most 2 MB, 10,000 rows and 20 columns; column names must start with a
letter and use only letters, digits and underscores; cells in text columns may not start with
`=`, `+`, `-` or `@`.

## Running a private query (analysts)
1. Click **Run private queries** on the dashboard.
2. Choose the dataset, operation (`count`, `sum` or `mean`), the column (for sum and mean), and
   optionally a text column to group by.
3. Choose epsilon between 0.01 and 2.0. Smaller epsilon means more noise and stronger privacy.
4. Choose the mechanism: Laplace, or Gaussian (epsilon must be below 1).
5. Click **Run query**.

## Reading the result
- **Noisy value:** the released answer. **Noise scale:** how large the typical noise is.
- **Budget charged and remaining:** how much epsilon this query used and what is left.
- **Hidden groups:** groups with fewer than the minimum size (default 5) are not shown, so no
  individual can be singled out.
- **Evidence box:** mechanism, epsilon, how sensitivity was computed, clamping bounds, minimum
  group size.
- **Privacy risk box:** LOW, MEDIUM or HIGH, with the rule that caused each level (R1 to R6) and a
  recommended action.

## Asking the same question again
Repeating exactly the same query returns the saved answer and costs nothing. This stops anyone
from averaging many noisy answers to remove the noise. Changing epsilon, column, grouping or
mechanism counts as a new question and uses budget.

## Downloading a report
On the dashboard click **Download sanitized report (JSON)**. It contains only noisy results,
settings and budget status. It never contains raw rows or true values.

## Viewers
After logging in you see the **Released results** table on the dashboard. That is all a viewer can
access; every other page or request returns "Access denied".

## Error messages
| Code | Meaning | What to do |
|---|---|---|
| E_FILE_TYPE / E_FILE_SIZE / E_FILE_EMPTY / E_FILE_BINARY / E_ENCODING | File is not an acceptable CSV | Use a UTF-8 `.csv` under 2 MB |
| E_TOO_MANY_ROWS / E_TOO_MANY_COLUMNS / E_NO_ROWS | File size limits | Reduce the file |
| E_DUPLICATE_COLUMNS / E_COLUMN_NAME | Bad column names | Rename columns |
| E_BOUNDS_FORMAT / E_BOUNDS_RANGE / E_BOUNDS_COLUMN | Bounds text is wrong | Use `column:min:max` with min below max and existing columns |
| E_NOT_NUMERIC | A bounded column has non-numbers | Clean the column |
| E_FORMULA_INJECTION | A text cell starts with = + - or @ | Remove or rewrite that cell |
| E_QUERY_OP / E_QUERY_COLUMN / E_QUERY_GROUP / E_QUERY_MECH | Invalid query option | Pick options from the lists |
| E_QUERY_EPSILON / E_GAUSS_EPSILON | Epsilon out of range | Use 0.01 to 2.0 (below 1 for Gaussian) |
| E_BUDGET_EXHAUSTED | Not enough budget left | Ask an admin to review the budget |
| E_RATE_LIMIT | Too many requests | Wait a minute |
| E_DATASET_NOT_FOUND | Unknown dataset | Pick one from the list |
| E_INTERNAL | Unexpected server problem | Try again; tell an admin (it is logged) |