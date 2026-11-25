# Limitations and ethics statement

## Purpose
PrivacyLab is a teaching system that demonstrates differential privacy with an enforced privacy
budget. It is not a production service.

## Technical limitations
| Limitation | Effect | Possible improvement |
|---|---|---|
| Plain HTTP on localhost | Traffic is not encrypted | Serve over HTTPS |
| Fixed demo passwords | Anyone reading the code knows them | Force a password change at first login |
| Rate-limit counters kept in memory | Reset on restart | Store them in the database |
| Data at rest is unencrypted | Uploaded files and database are readable on the laptop | Encrypt storage |
| Sessions are stateless cookies | A session cannot be revoked before it expires | Server-side session table |
| Small-group rule uses true group sizes | Standard practice but not formally private | Decide suppression from a noisy count |
| Mean divides by the group size | Assumes group sizes are not sensitive | Release noisy sum and noisy count |
| Basic composition only | Budget is used up faster than with advanced accounting | Advanced or Renyi accounting |
| Floating-point noise | Known theoretical weaknesses of naive floating-point Laplace sampling | Use a hardened library such as OpenDP |
| Correct bounds are the uploader's responsibility | Wrong bounds can break the sensitivity assumption | Validate bounds against policy |
| Budget is per dataset | Does not model one person appearing in several datasets | Per-user or per-person accounting |
| Group labels are visible | The existence of a group name is itself disclosed when it is large enough | Pre-declare allowed groups |
| Single process, local SQLite | Not built for many users | Move to a server database |
| Deprecation warnings in tests | `on_event` and the HTTP client in the test tools are older styles | Update to lifespan handlers |

## What the privacy guarantee does and does not mean
- It limits what any answer reveals about one individual, up to the total epsilon spent on a dataset.
- It does not protect against harms that come from conclusions about whole groups.
- It depends on correct sensitivity, which depends on correct bounds and on the code being correct.
- Once the budget is spent, privacy is traded against usefulness: no more answers are available.
- Noise can make small numbers unreliable. The risk explanation flags these cases, but a reader can
  still misuse a noisy figure.

## Ethics
- **Data used.** Only synthetic, instructor-approved sample data is included. No real personal data
  is used. Real personal data should only be loaded with proper authorization, consent or legal basis.
- **Purpose limitation.** The system exists to release aggregates safely. Attempts to re-identify
  people, split queries to dodge limits, or flood the system are blocked or logged.
- **Fairness.** Hiding small groups protects members of small communities but also makes them
  invisible in the statistics. Administrators should weigh privacy against fair representation when
  choosing the threshold.
- **Power of administrators.** Admins can change budgets and thresholds, which can weaken privacy.
  Changes require confirmation and are permanently logged with old and new values.
- **Transparency.** Every release shows its epsilon, mechanism, rules and risk level so readers can
  judge how far to trust it.
- **Data minimisation.** Logs hold no passwords, file contents or raw rows; exports hold only noisy
  values.
- **Scope of testing.** All security tests were run against this system on a local machine. No
  external systems were targeted.
