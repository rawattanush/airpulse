# Validation protocol 7.0: news-adjusted outlook

STATUS: PRE-REGISTERED 2026-10-09 (change record CL-028), before any run. Not edited afterwards.

1. **Question.** Given the seasonal baseline's probabilities for a month, do news features observed before issuance improve them?
2. **Target, labels, issuance dates, flat band, training filter (final label known at issuance), minimum of 36 training labels, metrics:** those of the frozen benchmark. Series: IC1312.
3. **Forecasters, scored on identical months.** SEA: the seasonal baseline. T0: logistic regression on the three log-probabilities of SEA. T1: logistic regression on those three and the six features `NEWS_EVENT_FEATURES_V1` (30-day window, rates), as of 00:00 UTC of the issuance date. Class `LogisticModel` of the project, unchanged, seed as the benchmark. The SEA probabilities used as inputs are those SEA gave at each row's own origin (out of sample).
4. **Window.** Training rows start where the archive has a full 30-day window and SEA has its minimum training size; the first scored origin is the first with 36 such rows.
5. **Decision rule.** News adds value only if Brier(T1) < Brier(SEA) and Brier(T1) < Brier(T0), and both 95% paired-bootstrap intervals (5,000 resamples) of the differences lie below zero.
6. **Consequence, whatever the result.** SEA remains the official outlook. T1 is shown on the site as an experimental news-adjusted view with its own record and the comparison of this protocol. One run; nothing is tuned after seeing it.
