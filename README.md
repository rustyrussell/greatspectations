# Great Spectations

Checks that quotes of a spec embedded in source-code comments actually
say what the spec says -- so when the spec changes, the comments (and
the requirement they claim to implement) don't silently drift out of
sync.

Originally CLN's `check_quotes.py`/`bolt-coverage.py`, hardwired to
BOLTs. `greatspectations` generalizes the same idea to any spec source
you point it at: BOLTs, BIPs, RFCs, or a single-file spec like
`SPECIFICATION.md`.

## Install

```
pip install -e .
```

This installs the `greatspectate` command (also runnable as
`python -m greatspectations`).

## Quickstart

A comment like:

```c
/* BOLT #11: A writer:
 *  - MUST set `payment_hash` to the SHA256 of `payment_preimage`.
 */
```

is checked against your BOLT spec checkout by:

```
greatspectate check --config specquotes.toml src/invoice.c
```

`greatspectate` exits 0 if every quote is found verbatim (modulo whitespace)
in the spec, or 1 and prints `file:line:message` for anything that
doesn't match.

When a quote fails to match anything, `check` also looks for spec text
that's merely *similar* -- the wording probably drifted rather than
vanished -- and if it finds something reasonably close, prints a
gcc-style `note:` line pointing at it (the same `file:line:` format
your editor already knows how to jump to, e.g. from Emacs' `compile`
or Vim's quickfix):

```
src/invoice.c:12:cannot find match
11-payment-encoding.md:6: note: closest match (85%): 'MUST set `payment_hash` to the SHA256 of `payment_preimage`. - MUST set'
```

This is a best-effort hint (stdlib `difflib`, no network, fully
deterministic) -- it never affects whether a quote passes or fails, and
says nothing if nothing clears a similarity threshold.

## `specquotes.toml`

Each repository that wants quote-checking declares its own
`specquotes.toml`, naming the spec sources it checks against:

```toml
[sources.bolt]
format = "markdown"
dir = "../lightning-rfc"
pattern = "{id:02d}-*.md"

[sources.bip]
format = "mediawiki"
dir = "../bips"
pattern = "bip-{id:04d}.mediawiki"

[sources.cmdata-spec]
format = "markdown"
file = "SPECIFICATION.md"

[sources.rfc]
format = "rfc-text"
dir = "/usr/share/doc/RFC/standard"
pattern = "rfc{id}.txt.gz"
```

`greatspectate` doesn't fetch anything -- point `dir`/`file` at a checkout or
package you already have (a `git clone` of `bitcoin/bips`, `apt install
doc-rfc-std`, or a spec file that lives in your own repo).

Each `[sources.NAME]` table is:

- `format` -- which parser splits the document into sections:
  - `markdown` -- splits on `#`-prefixed headers. BOLT files and
    single-file specs like `SPECIFICATION.md` both use this.
  - `mediawiki` -- splits on `==Header==` lines, as used by
    `bitcoin/bips`.
  - `rfc-text` -- the classic RFC-editor plaintext layout, as shipped by
    Debian's `doc-rfc-std` package (`/usr/share/doc/RFC/<category>/
    rfcNNNN.txt.gz`). Transparently gunzips `.gz` files, strips page
    headers/footers and form-feed page breaks so a requirement split
    across a page boundary still reads as one section, and splits on
    column-0 `N.`/`N.N.` numbered headers -- while ignoring the table of
    contents, whose entries have the same shape but end in a
    right-aligned page number (space- or dot-leader-padded), which a
    real header never does. `doc-rfc-std` splits RFCs across category
    subdirectories (`standard/`, `draft-standard/`, ...); point `dir`
    at the single category you need, as in the example above. A
    recursive `pattern` like `"**/rfc{id}.txt.gz"` also works if your
    RFCs span categories, but `doc-rfc-std` additionally ships a
    `links/` directory that symlinks every RFC into one flat directory
    regardless of category, so a recursive pattern matches both the
    symlink and the real file for the same id and `greatspectate` refuses
    the ambiguity (`glob.glob` has no way to exclude a subdirectory by
    name). If you need multiple categories, glob each one explicitly
    with a separate `[sources.NAME]` table instead.
- `dir` + `pattern` -- for a source with one file per id (BOLT, BIP,
  RFC): `pattern` is a glob template with an `{id}` placeholder, e.g.
  `"{id:02d}-*.md"`, `"bip-{id:04d}.mediawiki"`, or
  `"rfc{id}.txt.gz"`.
- `file` -- for a source that's a single fixed document (no id needed),
  e.g. a spec that lives directly in your repo.
- `comment_marker` (optional) -- the literal word that opens a quote
  comment for this source. Defaults to the source name, uppercased
  (`bolt` -> `BOLT`, `cmdata-spec` -> `CMDATA-SPEC`), which is exactly
  CLN's existing `# BOLT #11:` convention -- no source comments need to
  change to adopt this tool for BOLT.
- `normative` (optional) -- exactly which spec text must be quoted by
  something, as an alternative to guessing from RFC 2119/8174 keywords
  (see Coverage below). Meant to be generated once (by an LLM, or by
  hand for a short document) rather than maintained by feel. For a
  `file` source it's a flat array of places; for a `dir` source, since
  each id is a different document, it's a table keyed by id:

  ```toml
  [sources.cmdata-spec]
  format = "markdown"
  file = "SPECIFICATION.md"
  normative = ["12-15", "20:5-30:10"]

  [sources.bolt.normative]
  11 = ["42-58", "70"]
  ```

  Each place is 1-indexed and inclusive: `"42"` is the whole line;
  `"42:10-20"` is columns 10-20 of line 42; `"42-50"` is lines 42
  through 50; `"-50"`/`"42-"` are open-ended (start/end of file);
  `"42:10-50:20"` is a precise span from column 10 of line 42 through
  column 20 of line 50. See `normative.py`'s module docstring for the
  full grammar and its edge cases.

Relative `dir`/`file` paths are resolved against the directory
containing `specquotes.toml`, not your current working directory.

## Marker syntax

```
<MARKER>[-<commit>][ #<id>][/<section-hint>]: <quoted text>
```

- `<MARKER>` is a source's `comment_marker`.
- `-<commit>` is CLN's "draft BOLT" convention: the line is only parsed
  when `<commit>` is a prefix of one of `--include-commit`'s values
  (repeatable), letting a branch reference an unmerged spec PR by
  commit. Ignored otherwise.
- `#<id>` selects the document for sources with `dir`+`pattern`
  (required there, and disallowed for `file` sources).
- `/<section-hint>` restricts the match to sections whose header
  contains that text (case-insensitive). Useful when near-identical
  wording repeats across sections -- e.g. `SPECIFICATION.md`'s "Reader
  Requirements" and "Writer Requirements" both have a "MUST fail
  parsing if the length is wrong" bullet, and without a hint a quote
  could silently match the wrong one:

  ```c
  /* CMDATA-SPEC/Reader Requirements: A reader:
   *  - MUST fail parsing if the length is wrong.
   */
  ```

- The quoted text may use `...` as a wildcard, including once at the
  very start of a quote to mean "must immediately follow the previous
  quote from this source in this file" (handy for splitting one long
  requirement across several separately-commented lines of code).
- Continuation lines repeat the marker's `--comment-continue` prefix
  (default `#`); an inline/single-line comment style also needs
  `--comment-end` (e.g. for C: `--comment-start='/* ' --comment-continue='*'
  --comment-end='*/'`).
- `--comment-aside` marks a prefix for commentary that lives inside a
  quote block but isn't part of the quote -- a continuation line
  starting with it is dropped instead of appended, so it's never
  checked against the spec:

  ```c
  /* BOLT #2: A sending node:
   *  - MUST set `funding_satoshis`.
   * Note: We did not implement this yet.
   */
  ```

  with `--comment-aside='* Note:'` (adjust the prefix to match
  whatever `--comment-continue` you're using, e.g. `'# Note:'` for the
  default `#`-style comments).

## Matching modes

`--mode normalized` (default) collapses runs of whitespace in both the
quote and the spec before comparing, so line-wrapping differences don't
matter. `--mode exact` compares the literal, uncollapsed text instead,
for specs where exact byte matching matters.

## Coverage

`greatspectate check --coverage=FILE ...` appends a record for every quote
that matched. `greatspectate coverage --coverage=FILE` then annotates every
line of the spec document with its coverage status:

```
greatspectate check --config specquotes.toml --coverage=.coverage src/*.c
greatspectate coverage --config specquotes.toml --coverage=.coverage
```

Every physical line of every checked document gets one of three
statuses:

- **covered** -- at least one quote's matched text touches this line.
- **gap** -- nothing quotes this line, but the line is expected to be
  quoted, so it looks like a requirement nothing implements.
- **neutral** -- neither: ordinary prose, headers, examples, rationale.
  Not expected to be quoted, so it's never flagged.

A line is "expected to be quoted" one of two ways:

- If the source's config declares `normative` spans for this document
  (see above), a line is expected exactly when it falls inside one of
  them. This is the precise option -- but it means someone (typically
  an LLM, or a human for a short document) had to name the spans up
  front, and it's the ground truth for that document once configured:
  it replaces the keyword guess below entirely, rather than adding to
  it.
- Otherwise, it falls back to guessing from an RFC 2119/8174 normative
  keyword (`MUST`, `MUST NOT`, `SHALL`, `SHALL NOT`, `SHOULD`, `SHOULD
  NOT`, `REQUIRED`, `RECOMMENDED`, `OPTIONAL`, `MAY`), deliberately
  case-sensitive: RFC 8174 limits normative force to the all-caps form,
  which BOLT and most modern RFCs follow, and it's also what keeps this
  quiet on plain English "must"/"should" in pre-2119 RFCs and most
  BIPs, neither of which reliably use the convention.

(Either way, status is decided per physical line, not per sentence, so
two different requirements hard-wrapped onto the same line can
occasionally mask each other -- a deliberate precision/simplicity
tradeoff.)

`--format text` (the default) prints one line per annotated line, with
a 3-character status prefix: `***` for a gap, `+`/`++`/`+++` for a
covered line quoted 1/2/3-or-more times, or three spaces for neutral --
followed by the usual `file:line:text`:

```
    src/BOLT-11.md:5:A writer:
+   src/BOLT-11.md:6:  - MUST set `payment_hash` to the SHA256 of `payment_preimage`.
*** src/BOLT-11.md:7:  - MUST set `payment_secret` to a fresh, random value.
```

`--format json` emits the same information as `{"documents": [{"source",
"id", "path", "lines": [{"line", "text", "status", "mentions"}, ...]},
...], "summary": {"any_uncovered"}}`.

`--format html --output-dir DIR` writes one self-contained HTML page per
document (`DIR/{source}-{id}.html`, or `DIR/{source}.html` for
single-file sources) with the same three statuses shown as red/green/
plain, for a human to skim.

Restrict to specific documents with `--source NAME[:ID]` (repeatable);
by default every `(source, id)` pair found in the coverage file is
checked. `--mode` must match whatever mode `check` used to write the
coverage file, since match offsets are mode-specific. The exit code is
1 if any line anywhere is a gap, 0 otherwise.

## CI output

`check` and `greatspectate coverage --format text/json` both default to (or
accept) machine-scrapable `file:line:message`/JSON output; `coverage
--format html` is the human-facing option, meant for local review or
publishing as a build artifact rather than for CI to parse.
