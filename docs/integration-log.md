# Integration Log

The repository was reduced to the active runtime shape:

- `musecli/cli.py` owns command handling and terminal output.
- `musecli/queue.py` owns SQLite queue state.
- `musecli/journal.py` owns daily JSONL journal entries.
- `musecli/config.py` owns data paths.
- `musecli/utils.py` owns shared local helpers.

Major simplifications:

- Removed legacy package layers that were no longer imported.
- Kept the public command set to `muse`, `add`, `inbox`, `focus`, `check-in`, and `today`.
- Kept focus choices to `[d] done` and `[q] quit`.
- Kept tests on the active capture, inbox, focus, check-in, and today flow.

## Visible workspace vertical slice

- Added one framework-neutral, process-local `SessionController` shared by the
  simple and Textual presentations.
- Kept the demonstration honest: it records visible intent, plan, skipped
  context/permission/tool/verification, and a result that says the requested
  task was not executed.
- Kept historical workflow evidence read-only and authoritative through the
  existing workflow index, strict trace loader, renderer, and evaluator.
- Added lazy, privacy-bounded run navigation; malformed, incomplete,
  mismatched, unreadable, and contradictory evidence remains visible without
  being repaired or promoted to success.
- Preserved the five-command `muse` surface and byte-for-byte non-TTY snapshot
  behaviour while adding `muse --tui` and TTY-only bare interactive startup.
- Added Python 3.9/3.13, headless Textual, packaging, installed-wheel, and
  clean-exit pseudo-terminal verification.
