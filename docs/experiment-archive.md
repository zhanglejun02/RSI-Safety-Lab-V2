# Archive previous experiments

The current natural experiment campaign starts with fresh outputs under
`runs/current/`. Previous natural runs, scripted controls, saved plans, frozen
reviews and exported validation records are historical evidence and are not pooled
with this campaign.

Preview the archive selection, then archive it explicitly:

```bash
bash scripts/archive_experiments.sh plan
bash scripts/archive_experiments.sh archive
```

The Bash file contains the repository paths and preserved directories. It keeps
`runs/vendor/`, `runs/datasets/`, `runs/current/` and `runs/archive/` in place.
All other immediate entries in `runs/`, plus entries in `exports/`, are selected.
Build output in `build/` and `dist/`, the repository environment and credentials
are outside this selection. `.env`-like files encountered inside a selected tree
cause a failure before anything is moved.

Stop experiment writers before archiving. The script checks known CLI processes,
but a separately authored Python launcher may not be recognizable. An interrupted
archive retains originals in its `staging/` directory; do not delete it or rerun
against a different selection before inspecting the failure.

Each archive is stored in `runs/archive/<timestamp>/` with:

- `archive-plan.json`: selected original paths, byte and file counts, exclusions.
- `manifest.json`: relative paths, types, metadata, SHA256 for every regular file,
  and the literal targets of symlinks. Symlink targets are never followed.
- `experiments.tar.gz`: compressed original contents with `runs/...` and
  `exports/...` paths.
- `verification.json`: verification outcome, compressed archive hash and whether
  original copies were removed.
- `RESTORE.md`: the exact archive extraction command.

Originals are renamed into staging, hashed and compressed. Every archived file is
read back and compared with its SHA256; directory and symlink entries are also
checked. Staged metadata must still match before removal. Failure preserves
staging for recovery. This is byte-preserving archival, not result analysis or
conversion to the latest protocol.

Restore into an empty directory first:

```bash
mkdir -p /tmp/rsi-history-restore
tar -xzf runs/archive/<timestamp>/experiments.tar.gz -C /tmp/rsi-history-restore
```

Absolute paths inside historical records are unchanged. To resume an old run,
restore its original location and required frozen dependencies explicitly. Do not
overwrite current outputs or combine its measurements with the current campaign.
