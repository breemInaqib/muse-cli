# museCLI

museCLI is a small, local-first CLI for capturing thoughts and working through them step by step.

It is designed to feel calm, simple, and predictable to return to every day.

Command: `muse`

---

## install

```bash
pip install musecli
```

For development:

```bash
pip install -e .
```

---

## flow

```text
add -> inbox -> focus -> check-in -> today
```

A simple loop:

- capture something
- decide what to do with it
- keep a small set of active items
- reflect briefly

---

## home

Run `muse` to see your current state.

```text
museCLI

  inbox: 0

focus
  empty

today
  no check-in
```

This view shows:

- how many items are waiting
- what you are currently focused on
- your latest check-in today

---

## capture

Add something quickly:

```bash
muse add "text"
muse add --stdin
muse add --clipboard  # uses clipboard if available
```

Output:

```text
added
```

---

## inbox

Process items one at a time:

```text
inbox

  task text

  [k] keep   [d] discard   [p] pin   [q] quit
```

- `k` keep it
- `d` discard it
- `p` pin it to focus
- `q` exit

Empty:

```text
inbox

  empty
```

---

## focus

Work through pinned items:

```text
focus

  task text

  [d] done   [q] quit
```

- `d` mark as done (removes it from focus)
- `q` exit

Empty:

```text
focus

  empty
```

---

## check-in

Record a simple reflection:

```bash
muse check-in --mood 4 --note "steady"
```

Output:

```text
saved
```

---

## today

View today’s latest check-in:

```text
today

  no check-in
```

or:

```text
today

  mood: 4
  note: steady
```

---

## storage

All data is stored locally in `~/.muse`:

- queue: `~/.muse/muse.db`
- journal: `~/.muse/journal/YYYY/MM/YYYY-MM-DD.jsonl`

You can override the location:

```bash
muse --data-dir PATH
```

---

## notes

museCLI keeps things intentionally small.

It is not a full note system or task manager.  
It is a simple loop for capturing, deciding, focusing, and reflecting.

The goal is to reduce noise, not organise everything.