# Repository working agreement

- Build with C++17, warnings enabled, no `-ffast-math`, and no network fetches during CMake configuration.
- Run `ctest` and `python -m unittest discover -s tests/python -v` before claiming a change is tested.
- Keep `legacy/source_snapshot/`, manuscripts, third-party papers, `.pt` files, private logs, keys, and generated runs out of Git.
- Treat `synthetic_vessel_v1` as software-test data only. Never label it as identified vessel data or field validation.
- Controllers consume observation snapshots only; simulator truth is restricted to the plant and offline scorer.
- Physical actuation is fail-closed. Mock/replay/loopback may run by default; real output needs a complete, reviewed hardware profile and explicit arming.
- Distinguish exhaustive no-witness from timeout/unknown, and never accept a partially evaluated branch as a witness.
- Update `IMPLEMENTATION_STATUS.md` with evidence whenever an implementation or validation state changes.
