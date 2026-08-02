# Local-data recovery

museCLI never repairs, deletes, replaces, or resets incompatible or corrupt
queue data during ordinary startup, reads, or writes.

## Queue database

The active queue consists of `muse.db` and any associated SQLite sidecars:

```text
muse.db
muse.db-wal
muse.db-shm
muse.db-journal
```

Before opening an existing database for normal use, museCLI validates its table,
column, and stored status/pin contracts through a read-only SQLite connection.
Unsupported schemas or values fail as incompatible. SQLite malformed-database
errors fail as corrupt. Locks and other access failures are reported separately
where SQLite provides a dependable distinction.

On failure:

- the command exits non-zero;
- the database and every sidecar remain in place;
- no fresh database is created over the failed one;
- no migration, repair statement, or backup is attempted;
- the error does not include stored record contents or a traceback.

museCLI currently has no destructive reset or automatic migration command. It
therefore creates no recovery backups and has no backup naming or collision
policy. To deliberately start with a fresh queue, first close all museCLI
processes, copy the database and every existing sidecar to a recovery location,
then move all of those originals out of the active data directory. A later
command may create a new queue only after `muse.db` is absent. This manual step
is the explicit destructive boundary; removing only the main file while leaving
sidecars is unsafe.

Use `--data-dir PATH` to inspect application behavior with a separate empty
directory without touching the failed data.

## Journal files

Journal files remain append-only JSONL. Reading a day validates every non-empty
line independently:

- valid entries remain available and are sorted normally;
- malformed JSON, invalid journal records, and invalid UTF-8 lines are counted
  and reported with their line numbers;
- warnings identify only the journal-relative date path and issue kind;
- malformed contents are never echoed;
- the original file is not rewritten or repaired;
- `today` displays valid entries with an explicit degraded-state warning rather
  than presenting the partial result as fully healthy.

`check-in` continues to append. If malformed evidence already exists, the
existing bytes remain unchanged and the new valid line is added at the end.
There is no automatic journal repair command.

## Privacy and backups

Queue databases, sidecars, journal files, and user-created recovery copies are
private local data. Preserve restrictive filesystem permissions and review any
copy before sharing it. museCLI does not upload recovery evidence.
