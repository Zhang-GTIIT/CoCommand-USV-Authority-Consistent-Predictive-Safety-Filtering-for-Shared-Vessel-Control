# Source audit

## Inputs actually read

| Input | Current SHA-256 | Handling |
|---|---|---|
| `main.pdf` | `8e6d5ffe81b18212b39fcdafca46a54615da2050a91a28a2182af39df7c784ca` | All 22 pages rendered; equations, tables, and result placeholders visually checked. Not copied into the repository. |
| `CoCommand.zip` | `ac53bb7d713f8fa1b0a76b05158e6864a30d58016fd775f7a366921e72b58bcf` | Paths validated before selective extraction. `.pt`, PDFs, caches, macOS metadata, Office temporary files were not loaded. |
| `CODEX_MASTER_PROMPT_ZH.md` | local task brief | Read completely; treated as an implementation instruction because the user explicitly requested it. |
| `EXPERIMENT_PLAN_V1.md` | local task brief | Read completely and represented in the derived manifest. |
| `SOURCE_AUDIT_V1.md` | local task brief | Read completely; its claims were independently checked where possible. |
| `experiment_manifest_v1.yaml` | absent | The supplied directory did not contain this file. `configs/experiment_manifest_v1.yaml` is a clearly marked derivation from the experiment plan. |

The current `main.pdf` hash differs from the audit document's recorded
`5463a4790dc36de3ae63b46413d53ed4185da00fe5dcd8e0d29320344742d959`.
The current file, not the stale hash, is the source for this implementation snapshot.

## Legacy observations

The ignored local snapshot confirms that `CoCommand.py` uses a 2-D point/acceleration model,
`DT=0.1`, 18 prediction steps, eight initial held steps followed by braking, 36 headings times
three amplitudes plus exact/zero candidates, circular clearance, and direct construction of
tracks from obstacle truth in its main loop. It imports desktop/ML packages and saves pickle-
based `.pt` files. It was inspected statically and was not executed.

`Imperative_learning_2D_moving.py` contains radar, detection, and tracking functions and uses
them in its own main flow. Their presence does not make `CoCommand.py` a manuscript vessel
implementation. No old source is linked into the new C++ core.

The source snapshot is excluded from Git because ownership/license permission was not
provided. `legacy/README.md` records the boundary without redistributing the material.

