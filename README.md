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

This installs the `spectate` command (also runnable as
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
spectate check --config specquotes.toml src/invoice.c
```

`spectate` exits 0 if every quote is found verbatim (modulo whitespace)
in the spec, or 1 and prints `file:line:message` for anything that
doesn't match.

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

`spectate` doesn't fetch anything -- point `dir`/`file` at a checkout or
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
    symlink and the real file for the same id and `spectate` refuses
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

`spectate check --coverage=FILE ...` appends a record for every quote
that matched. `spectate coverage --coverage=FILE` then reports spec text
in Requirements sections (or, with `--all-sections`, every section) that
no quote covers:

```
spectate check --config specquotes.toml --coverage=.coverage src/*.c
spectate coverage --config specquotes.toml --coverage=.coverage
```

Restrict to specific documents with `--source NAME[:ID]` (repeatable);
by default every `(source, id)` pair found in the coverage file is
checked. `--mode` must match whatever mode `check` used to write the
coverage file, since match offsets are mode-specific.

## CI output

Both subcommands accept `--format json` for machine-readable output
instead of the default `file:line:message` text, if you want to post
results elsewhere rather than just scrape build logs.
