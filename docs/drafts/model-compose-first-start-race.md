# Draft issue for hanyeol/model-compose (not sent)

**Title:** First `model-compose up`: components that install the same GitHub package race on the shared clone

**Environment:** model-compose `9a7dad4f`, Python 3.12, Linux aarch64 (DGX Spark), uv 0.10.

**What happens.** With several `typed-decision` components of one family (three `kev` checkpoints, each with its own
`runtime.path`) and fresh runtimes, the first `model-compose up` fails:

```
RuntimeError: Worker 'kev-4b' failed to start: Command '['uv', 'pip', 'install', '--python',
'.runtime/kev-4b/bin/python', '--link-mode=hardlink', '/tmp/mindor-git-sources/kev/c9c1f855...']' returned
non-zero exit status 2.
```

A second start succeeds once one install finished, and every later start is fine (`is_package_installed("kev")`
skips the install).

**Why.** Components start concurrently (`asyncio.gather` in `ControllerBase._start_components`), and
`install_package_from_github` (`core/foundation/package/installer.py`) checks `if not clone_dir.exists()` before
cloning into the shared `$TMPDIR/mindor-git-sources/<module>/<revision>`. The second component sees the directory
the first one is still cloning into and installs from a partial tree.

A related race: two components with the **same** `runtime.path` both create the virtualenv at first start, and one
fails with `FileExistsError` in `venv.EnvBuilder.create`.

**Suggestions.**
1. Clone into a temporary sibling directory and `os.replace` it into place, and/or hold a file lock
   (`<clone_dir>.lock`) around clone and install.
2. Serialise virtualenv bootstrap per path with a lock, or document that `runtime.path` must be unique.

**Workaround we use.** Start each component alone once (a small script writes a one-component compose file and
runs `model-compose -f <file> up` until the API answers), then start everything together.
