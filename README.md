# Multi-Board Fabrication Export

A KiCad 11+ plugin that exports a separate set of fabrication outputs for each board on a panel.
You mark out each board with a rule area on the `Edge.Cuts` layer and give it a `board_name`
custom property. The plugin then produces gerber and drill files for that board only, puts them
in a folder named after it, and zips them.

It needs KiCad 11.0 or newer. It was developed and tested against the 10.99 development builds
that led up to 11.0, which is why that number appears in the examples below.

Design: [docs/superpowers/specs/2026-09-19-multi-board-fab-export-design.md](docs/superpowers/specs/2026-09-19-multi-board-fab-export-design.md)

## Marking boards

1. Draw a polygonal **rule area** on the `Edge.Cuts` layer around one board. It must fully
   surround that board's outline, tracks, footprints and so on.
2. Add the custom property `board_name` to the rule area. Its value names the board.

The name becomes a folder and a zip name, so it must be usable as one: not empty, no
`\ / : * ? " < > |` or control characters, not ending in a dot, and unique ignoring case. Names
are never silently repaired; a bad name is an error.

A Windows device name (`CON`, `PRN`, `AUX`, `NUL`, `COM1`-`COM9`, `LPT1`-`LPT9`, with or without an
extension) is accepted but produces a warning: current Windows 11 handles such folders and zips,
but older Windows versions and some tools do not.

Rule areas on Edge.Cuts without a `board_name` are skipped, and the dry run lists the custom
property keys they do have, so a misspelt key is easy to spot.

## What goes into each board

| Item | Belongs to a board when |
|---|---|
| Footprints, vias, text, dimensions, images | its position is inside the rule area |
| Tracks, arcs, graphics (including the board outline) | its first point is inside. A warning is given if another point is outside |
| Copper zones and keepouts | the zone's outline intersects the rule area. A pour spanning several boards goes into each |
| Groups and tuning patterns | at least one of their members belongs to the board |
| The rule areas themselves | never copied |

Items inside no rule area are left out of every board and listed in the report. An item inside
two rule areas is an error.

A footprint is assigned by its position alone; its pads are not checked, so the straddle warning
does not cover footprints. One whose position is inside a rule area is exported whole even if its
pads cross the boundary, and one whose position is outside is left out even if its body lies
inside (the report lists it as unowned). Check the dry run for footprints near a boundary.

Copper pours are refilled inside each board's outline (`--check-zones`), so a pour that spans the
panel never carries a neighbouring board's copper into your gerbers.

## Output

Next to the board file, using the output directory saved in the plot dialog (`fab/` if none is
saved):

```
<output dir>/<board_name>/    gerber and drill files
<output dir>/<board_name>.zip only whitelisted file types produced by this run, no folders
```

Plot settings come from the board's saved plot parameters. Drill options come from the drill
dialog's remembered values in your KiCad user configuration; anything that cannot be read falls
back to `kicad-cli` defaults, and the report says which source each option came from. The plugin
never deletes anything and never modifies your board, your project or any other file. It writes
only its own outputs: on a re-run it replaces the board's zip and any gerber or drill file with the
same name. Other files already in a board's folder are left alone and kept out of the zip.

A file counts as produced by a run when its modification time or size changed. On a file system
with coarse timestamps (FAT, exFAT), a layer re-plotted within the same timestamp tick with an
unchanged size would be taken for an old file and left out of the zip. The report lists such files
under `left alone, not zipped (stale)`, so check that list if a layer is missing from a zip.

## Installing

1. In KiCad, enable the API server (`api.enable_server` in `kicad_common.json`; in current builds
   it is an option on the Plugins page of Preferences).
2. Check the Python interpreter KiCad uses for plugins (`api.interpreter_path` in
   `kicad_common.json`, also on the Plugins page of Preferences). KiCad builds the plugin's own
   environment with it, so it must point at a working Python 3.9 or newer; a nightly's settings can
   still point at an older KiCad's interpreter.
3. Copy the `plugins` folder into KiCad's user plugins folder, for example
   `Documents\KiCad\10.99\plugins\multiboard-fab-export\`. KiCad finds it by scanning for
   `plugin.json`, builds a Python environment for it and installs `requirements.txt` on first use.
4. Restart KiCad. The PCB editor toolbar gets an **Export Boards** button.

### Building the PCM package

To install through KiCad's Plugin and Content Manager (PCM > "Install from File..."), build the
package zip:

```
.\scripts\build_package.ps1        # Windows
scripts/build_package.sh           # Linux / macOS / Git Bash
python scripts/build_package.py    # anywhere Python 3.9+ runs
```

This writes `dist/<identifier>-<version>-pcm.zip` (the version comes from `metadata.json`). It
contains only what KiCad needs: `metadata.json` and `LICENSE` at the archive root, everything under
`plugins/` (minus `__pycache__` and `.pyc` files) and a `resources/` folder if you add one for an
icon. Tests, docs, the sample project and backups are left out. Before writing, the script checks
that `metadata.json` and `plugins/plugin.json` share an identifier and that every action's
entrypoint exists, and afterwards it re-opens the zip to confirm the layout. Builds are
reproducible: the same sources give a byte-identical zip.

`--list` shows what would be packaged without writing anything; `--out-dir` changes the output
folder. The script prints the `download_sha256`, `download_size` and `install_size` values a PCM
repository entry needs. See [KiCad's addon docs](https://dev-docs.kicad.org/en/addons/index.html)
for the layout PCM expects. Manual installation (step 3 above) does not need `metadata.json` at
all.

## Using it

Click **Export Boards** in the PCB editor toolbar. A window opens and immediately analyses the board
KiCad has open, without writing anything. It shows the board file, the output root, the `kicad-cli`
in use, counts (boards, items, unowned items, skipped areas, errors, warnings) and the full report
in a text view. Read that first: it is the dry run.

- **Export** writes every board's folder and zip from the plan you are looking at, then replaces the
  text view with the result. It is disabled while the plan has errors.
- **Refresh** takes a new snapshot of the board, for after you have changed it in KiCad (KiCad stays
  usable while the window is open).
- **Copy** puts the text view's contents on the clipboard.

The window needs wxPython, which KiCad's own Python includes. Where it is missing, the button writes
`dry_run_report.txt` into the plugin's settings folder and opens it instead; nothing is exported
in that case, so use the command line below.

## Command line

The same pipeline runs on a saved board file without KiCad running:

```
python -m multiboard path\to\panel.kicad_pcb --dry-run --kicad-cli path\to\kicad-cli.exe
```

Run it from the `plugins` folder, or set `PYTHONPATH` to it. `--kicad-cli` defaults to `$KICAD_CLI`.
The exit code is 0 on success, 1 if a board failed and 2 if the plan has errors.

## Development

```
python -m pip install -r requirements-dev.txt
python -m pytest
```

Integration tests need a real `kicad-cli` from a 10.99 build (the fixtures were written by one):

```
. .\scripts\kicad-dev-env.ps1        # sets KICAD_CLI and the DLL search path for a local build
python -m pytest
```

A robustness check over KiCad's own board files is opt-in (about two minutes):

```
$env:KICAD_SOURCE = "C:\path\to\kicad"
python -m pytest tests/test_corpus.py
```

What can only be verified in a running KiCad is listed in
[docs/smoke-test.md](docs/smoke-test.md).
