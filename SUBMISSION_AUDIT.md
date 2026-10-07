# GeoGuard submission audit — 7 October 2026

Scope: current repository, notebooks, bundled data/results, website and shared report, assessed against the seven guide screenshots supplied by the user. Screenshots are reference requirements, not evidence that boxes have been completed. Historical notes remain records of earlier work.

| Requirement | Status / evidence |
|---|---|
| Accessible repository | Public GitHub repository; anonymous remote read checked. Portal URL entry still requires checking. |
| Nonempty root README; ten required topics in order | Present: title/summary, use case, problem, data, approach, installation, running, examples, results/limits, team/terms. |
| Executable notebook with visible outputs | Root PoC has six executed code cells, no errors, and the result figure. Runner starts a fresh kernel. Interactive notebook remains a separate fresh-query interface. |
| Pinned requirements | Root requirements pin the complete Python 3.12 submission runner. Optional interactive/live dependencies are separately documented. |
| Example input | Config and actual raw Earth Engine reductions committed; exact coordinates, dates, product, radius and source paths. |
| Example output and inline README figure | Executed notebook, JSON, CSV summaries and dated image evidence committed. |
| Relative paths / randomness | Source input/output references are repository-relative; runtime root discovery is portable. Credential-free calculations are deterministic; Python random seed set to 0. No stochastic model training is performed. |
| Reproducibility | Fresh-kernel PoC run passes locally; Ubuntu CI executes pinned runner. Existing clean Python 3.12 environment originally installed from root requirements. A second physical machine has not been checked. |
| Data identity, dates, processing level, terms | README table and third-party notices distinguish products, modeled wind, cloud/model weights, backgrounds and limitations. |
| Code/data/output separation | Recognisable equivalent structure: code modules, source inputs, committed examples/figures, ignored new outputs. Suggested folder names are not used literally. |
| Credentials or restricted assets | Tracked content and new outputs scanned for common secret signatures and private host paths. Raw satellite imagery/model weights excluded. Signature scans are not proof against every secret. |
| English and project alignment | Current materials use English and Air Quality Intelligence theme; pilot UAE. Portal and title slide not available for comparison. |
| Team registration and eligibility | Not verified. Documented contributor names/roles do not establish portal registration, nationality or eligibility. |
| Pitch PDF attached | Not verified. The Google report and Zainab source PDF are not a pitch deck or evidence of attachment. No current pitch deck supplied. |
| Submission form URL / acknowledgements / judging | Not verified. No receipt or acknowledgement inspected. |
| Deadline | Supplied guide says 11 October 2026 at 23:59 in the team creator’s local time. Creator’s time zone and completed submission time not verified. |

## Remaining submission work

Confirm every listed member is registered and eligible, use the same official theme in the portal/README/title slide, attach the final pitch PDF, verify the entered GitHub URL, complete required acknowledgements and retain a submission receipt before the stated deadline. The deadline’s creator-local-time rule must be checked against the creator’s actual time zone; the UAE pilot does not establish that time zone.

Decide a licence for original team-authored code with the authors if redistribution permissions are required. Third-party data/model terms are documented; a blanket licence has not been invented.

Software validation is separate from independent scientific validation. The PoC recomputes archived atmospheric observations and replays dated methane evidence. It does not claim newly measured gas, verified emissions, surface AQI, a safety verdict or validated UAE forecasting.
