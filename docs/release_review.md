# Repository sharing and public-release review

Review date: 22 September 2026.

Publication follow-up: the owner subsequently requested uploading to their specified
GitHub repository. The inspected 186-file set was published on `main` as initial commit
`54fe15550371d1ed8fefe57878e7c9a45bd55f2c`; its hosted Linux build, native/Python tests,
and smoke run passed. License selection and full attribution/rights documentation remain
pending. The pre-publication findings below are retained as the historical review.

## Sharing for research supervision

The project can be presented as a working synthetic shared-control research prototype with
paired experiments, implementation evidence, failure analysis, and a written report.
For an authorized supervisor, send the revised academic report plus a compact code/results
package, rather than the entire local working directory. Confirm permission before sharing
an inherited manuscript or someone else's source with a new recipient.

Suggested contents:

- The project README, experimental results, and selected figures.
- Controller, independent plant, configurations, tests, build files, and deployment templates.
- Frozen aggregate statistics, trial summaries, failure records, and provenance.
- The project-authored academic PDF as a separate, approved attachment.
- Relevant raw trajectories on request, through an approved data-sharing route.

The local folder was approximately 2.3 GiB before the review rebuild, dominated by raw runs,
tool caches, and binaries. Those are not useful as an unsolicited email attachment.
After the ignore-rule and documentation updates, the Git-eligible set contained 186 files
totaling approximately 3.11 MiB. This is an inspected candidate set, not an uploaded release
or a distribution license. The local report PDF remains a separate attachment.

## Remaining decisions before public GitHub release

| Item | Current state | Required action |
|---|---|---|
| Copyright and redistribution | Owner/supervisor authorization not recorded | Confirm rights for new code, adaptations, inherited material, and results |
| Repository license | No LICENSE file; metadata explicitly pending | Rights holder chooses terms; do not label the repository MIT or open source beforehand |
| Package authorship | Placeholder author remains in package metadata | Confirm actual contributors and attribution, then update metadata |
| Inherited two-dimensional prototype | Local snapshot ignored by Git | Keep excluded unless redistribution permission is documented |
| Academic materials | Report-authoring directory and PDFs excluded | Decide separately whether the project report may be released; do not publish third-party manuscripts |
| Raw data and exact replay | Aggregates included; raw traces and frozen binaries local | Approve a separate archive or document regeneration; do not promise one-command historical replay from a bare clone |
| Release verification | Fresh local desktop build/tests passed | Inspect the final publication set; test a clean checkout and run hosted Linux CI after an authorized first push |
| Hardware claims | Generic cross-build/templates and desktop mock/replay evidence | Keep physical board and boat validation separate |

No remote was configured and no commit existed at review time. This review did not create
a remote, commit, public repository, release, or upload. GitHub permits a public repository
without a chosen open-source license, but that does not grant general reuse rights.
See [GitHub's licensing guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).

## Publication hygiene applied in this review

- Excluded the entire local report-authoring directory from Git so render logs and personal
  paths do not enter the publication set. The report and its editable sources remain on disk.
- Copied eight project-result figures into the documentation directory for portable links.
- Kept application-specific resume notes out of the publication set; retained research
  statistics, protocols, negative results, and all existing local files.
- Replaced personal interpreter paths in two reproduction guides with portable setup.
- Corrected the introductory Kalman/multiple-model description to match the implementation.

Ignore rules are not a security boundary: forced additions, a different packaging tool,
or later changes can include ignored files. Inspect the actual staged files before any
publication. Pattern scans for local paths and common secret formats are supplementary;
they do not establish legal clearance or guarantee the absence of all sensitive content.
The review found no matching personal Windows paths, private-key headers, or common token
patterns in the Git-eligible text files. Seventy local documentation/image links resolved;
all eight copied figures matched the academic-report originals byte for byte. Headline
authority, integration-work, latency, and confirmation values matched the frozen statistics.

## Read-only pre-publication checks

Run from the repository root:

```sh
git status --short
git ls-files --cached --others --exclude-standard
git diff --cached --name-only
git diff --cached --check
```

Review the listed files, obtain the pending rights/metadata decisions, and create a compact
release from that inspected set. This checklist does not authorize uploading the working
directory or force-adding ignored data.

## Suggested repository identity

- Repository slug: `cocommand-usv`.
- Display title: **CoCommand-USV: Authority-Consistent Predictive Safety Filtering for Shared Vessel Control**.
- About: **Authority-consistent predictive safety filtering for human–autonomy USV control, with a shared C++ core and paired simulation studies of safety, intervention, and compute budgets.**
- Topics: `robotics`, `marine-robotics`, `unmanned-surface-vehicle`, `shared-control`,
  `predictive-safety-filter`, `collision-avoidance`, `control-systems`, `motion-planning`,
  `cpp`, `python`, `simulation`, `reproducible-research`.

The title emphasizes the tested control-design question. Avoid CBF, reinforcement-learning,
field-validated, or human-study labels for the current implementation and evidence.
