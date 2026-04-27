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
