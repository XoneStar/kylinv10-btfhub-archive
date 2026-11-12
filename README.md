# kylinv10-btfhub-archive

The BTFhub Archive repository provides BTF files for those published kernels that lack native support for embedded BTF, thereby enhancing the versatility of eBPF programs across different kylin v10 kernel versions.

## Archive layout

```
kylin/V10/
├── manifest.json                  # source RPM → BTF provenance and checksums
├── x86_64/
│   └── 4.19.90-52.70.v2207.ky10.btf.tar.xz
└── arm64/
    └── 4.19.90-52.70.v2207.ky10.btf.tar.xz
```

`aarch64` packages are stored under `arm64/`; every other architecture keeps
its upstream name.

Each file is a tar archive compressed with xz; the archive contains a single
`{kernel-version}.btf` member. The matching kernel version is encoded in the
filename:

```bash
tar -xJf 4.19.90-52.70.v2207.ky10.btf.tar.xz
```

`manifest.json` records the source RPM URL, the repository sha256, and both
compressed and uncompressed BTF checksums.

## Automated updates

[`.github/workflows/update-btf.yml`](.github/workflows/update-btf.yml) runs every
Monday at **01:00 Asia/Shanghai** (`0 17 * * 0` UTC). It:

1. Reads the `repodata` primary metadata for every configured
   version/architecture/repository.
2. Compares `kernel-debuginfo` packages against `kylin/V10/manifest.json`.
3. Downloads new RPMs (with resume + sha256 verification).
4. Extracts `vmlinux`, dumps embedded `.BTF` or generates it with `pahole -J`.
5. Validates the BTF header, packs it into `.btf.tar.xz`, and commits it.
6. Uploads a JSON/Markdown run report and fails the job on any package error.

Configured matrix:

- Versions: `V10.0`, `V10.1`, `V10SP1`, `V10SP1.1`, `V10SP2`, `V10SP3`,
  `V10SP3.1`
- Architectures: `x86_64`, `aarch64`, `loongarch64`
- Repositories: `updates` and `base`

Upstream package path (verified against the live server):

```
https://update.cs2c.com.cn/NS/V10/{version}/os/adv/lic/{repo}/{arch}/debug/
```

`base` is required for versions whose kernel is not present in `updates`
(for example `V10.0` and `V10SP3.1`).

The run is incremental and bounded: `--max-new` defaults to 10 kernels per run,
and the job stops starting new kernels after 330 minutes so large backlogs are
spread over several days. Packages are processed 3 at a time by default
(`--concurrency`, 1-8): downloads, extraction and xz compression overlap, so
raise `max_new` when you want a manual catch-up run. The initial backlog is
roughly 400 kernels. Trigger a manual run from
**Actions → Update Kylin V10 BTF archive → Run workflow**; `dry_run` lists
pending kernels without downloading anything.

A complete archive of compressed BTF files can approach or exceed GitHub's
soft 1 GiB repository-size recommendation. Each individual file stays well
below the 100 MiB hard limit.

## Running locally

Requirements: Linux, Python 3.11+, `rpm2cpio`, `cpio`, `pahole` (dwarves),
and `objcopy` (binutils or LLVM). On Debian/Ubuntu:

```bash
sudo apt-get install -y rpm cpio dwarves binutils xz-utils
python -m pip install pytest
python -m pytest -q
python -I scripts/update_btf.py --repo-root . --dry-run --max-new 5
```

Useful options:

```text
--versions V10SP3,V10SP3.1   limit the matrix
--arches x86_64              limit architectures
--repos updates              skip base repositories
--max-new N                  cap kernels processed this run
--concurrency N              packages processed in parallel (default 3, max 8)
--force                      regenerate already archived kernels
--work-dir DIR               store temporary RPM/vmlinux data outside /tmp
--report-json/--report-md    write machine/human readable reports
```

Exit codes: `0` success, `1` fatal configuration/tool error, `2` one or more
packages or repositories failed (successful packages are still committed).

## Notes

- GitHub scheduled workflows are disabled after 60 days without repository
  activity; re-enable from the Actions tab if the archive goes quiet.
- GitHub rejects files over 100 MiB. The updater refuses to commit a compressed
  BTF above 95 MiB.
- `kernel-tools-debuginfo`, `kernel-hash-init-debuginfo`,
  `kernel-debuginfo-common` and `.src.rpm` packages are intentionally ignored;
  they contain no `vmlinux`.
