# Licensing and public-release checklist

No repository license is asserted because the copyright owner and preferred terms were not
provided. The `pyproject.toml` metadata deliberately says license confirmation is pending.

Before publishing:

1. Confirm authorship/copyright and select a license for the newly written code.
2. Confirm whether any legacy source may be redistributed. The current source snapshot is
   ignored and should remain local unless permission is documented.
3. Keep the manuscript, third-party papers, `.pt` pickle files, private logs, secrets,
   machine-specific build caches, and hardware tokens out of Git.
4. Review dependency licenses for the compiler/build environment. The runtime core and
   Python orchestrator have no vendored third-party runtime library.
5. Do not add fabricated DOI, affiliation, acceptance status, author list, benchmark, or
   validation badge.

