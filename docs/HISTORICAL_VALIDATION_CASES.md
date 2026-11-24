# Illustrative historical case specifications

These are proposed adjudication exercises. No forecast archive is supplied. Each
cutoff is illustrative and outcome definitions still require independent source
review. The examples were selected with knowledge of their outcomes. Use them to
check rules and data alignment, then run the full preregistered eligible unit-time
panel, including periods with complete coverage and no events.

All cutoffs and target windows below are UTC. Each target starts one minute after
cutoff and runs for 30 days. Eligible information in each case requires the exact
vintage and contemporaneous availability evidence. Current versions of official
records are candidate outcome sources, subject to coverage and release review.

| Case and unit | Cutoff and target | Eligible information and candidate sources | Leakage risks and limitations |
| --- | --- | --- | --- |
| Russia’s full-scale invasion of Ukraine, February 2022. Ukraine country unit with versioned borders and Russia–Ukraine actor coding. | 2022-02-01 00:00. Window 2022-02-01 00:01 to 2022-03-03 00:01. Resolve whether regular Russian forces began a new, sustained, multi-axis ground offensive within the window. Operationalize as confirmed new ground entries on two distinct geographic axes within 48 hours of the first entry, with the first entry as onset. Define corroboration and axis coding before adjudication. | Exact pre-cutoff public diplomatic statements and dated reporting, if independently archived. Candidate outcomes include event records and contemporaneous official chronology, cross-checked with the UN resolution on aggression against Ukraine. [UN A/RES/ES-11/1](https://docs.un.org/en/A/RES/ES-11/1) | Exclude later declassified intelligence, reconstructed movement timelines and later revisions from features. Fighting before 2022 makes generic interstate onset a different question. Classification can depend on axis boundaries and date precision. |
| 2020 Nagorno-Karabakh war. Armenia–Azerbaijan dyad within a preregistered conflict-area polygon. | 2020-09-01 00:00. Window 2020-09-01 00:01 to 2020-10-01 00:01. Resolve whether a new sustained episode of direct organized armed clashes began in the polygon. Use the first day of a sequence with qualifying dyadic events on three consecutive UTC days, preceded by 14 adjudicated days with no qualifying dyadic event in the polygon. Define actor coding and carry-in rules in advance. | Archived pre-cutoff statements from the OSCE Minsk Group and dated event reports with verified availability. Consider UCDP GED and independent chronologies for outcome coding. [OSCE Minsk Group](https://www.osce.org/mg) · [UCDP downloads](https://ucdp.uu.se/downloads/) | Later chronologies, shifting geocoding and changes in actor attribution can backfill information. Prior clashes outside the polygon can affect interpretation. Uncertain borders and sparse episode coverage limit cross-case comparability. A dyad score belongs in its own stratum. |
| Outbreak of the Sudan conflict, April 2023. Sudan country unit with Sudanese Armed Forces and Rapid Support Forces actor IDs. | 2023-04-01 00:00. Window 2023-04-01 00:01 to 2023-05-01 00:01. Resolve whether direct organized armed clashes between those forces began in the window. Define onset as the first qualifying clash if corroborated direct clashes follow on another UTC day within seven days and the prior 30 days are adjudicated free of qualifying clashes. | Archived statements about the transition process or military integration and contemporaneous reporting published by cutoff. Consider UCDP GED and ACLED for outcomes, alongside dated UN reporting. [UCDP downloads](https://ucdp.uu.se/downloads/) · [ACLED methodology](https://acleddata.com/methodology) | Later reporting may backdate tensions, edit actor assignments or document previously unseen clashes. Exclude later coverage from features. This armed-actor target differs from onset of any internal armed conflict in Sudan. Uneven surveillance can prevent negative labeling. |

For all cases, adjudicate independently of forecast values and retain disagreements,
timezone uncertainty, exact source IDs and pinned bytes. Freeze any necessary lookback
or confirmation tail beyond the target window and wait for it to mature before
resolving the onset label. Pre-register the same definitions and adjudication effort
for eligible negative windows. Candidate source links above establish research
starting points only. None certifies completeness, issue time or archived forecasts.
