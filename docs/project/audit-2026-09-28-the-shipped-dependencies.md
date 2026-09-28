# Audit: the shipped dependencies against the rule of #577

**Status:** AUDIT, 2026-09-28. A dated reading rather than a member of the
document set, and **nothing here is decided until the operator rules on it.**
It is epic #665's report and nothing else: no code, manifest, Spec or process
file changes with it, and every judgment call is marked for the operator.

**Base:** `e39f1339` on main. Every dependency below was read from `Cargo.lock`
with `cargo tree -e normal --locked --offline`, per crate, first at the features
each manifest defaults to and then at the features the deploy builds. Nothing is
taken from a manifest's own account of itself where the lock could be asked.

## The rule, and the hypothesis it tests

The operator's rule of 2026-09-23, recorded on #577: nothing is compiled into a
binary unless operations require it, and a library pulled in for one function
is a vulnerability import. The epic's hypothesis is that this program's shape,
Unix sockets, no async runtime, no network stack and no web framework, keeps
the surface small and mostly justified. This report measures that.

**The measure, up front.** At the manifests' default features the hypothesis holds for
every one of the ten crates: the ten share one serialization family, four take `nix` for
the socket and process calls, two take a hash, one takes SQLite, one takes a YAML
parser, one takes a tensor reader, and the pure member takes nothing. Forty-one external
crates in all, five of them the proc-macro toolchain that compiles on the host and never
links into a shipped binary. **At the features the deploy builds, the hypothesis does
not hold for one crate.** `weaver-state`'s `postgres` feature, which
`deploy/update-stack.sh` carries, brings an async runtime and a network client,
seventy-five crates in place of twenty-four, and `weaver-harness`'s `pyworker` feature
links the Python interpreter. Both are elections the documents made and neither is
hidden, and what the operator decides about them is the report's largest call.

## Out of scope, by name

`weaver-spu` is the olympus lane and is not read here. `weaver-web` left the
repository on 2026-09-26 for `WeaverTools_Project/weaver-web/` and is not read
here. Neither is skipped silently.

## What each crate ships, at its default features

The direct normal dependencies, the features they are taken with, and what
each does in the crate. Workspace-internal crates are named where they are
linked and not counted as external.

| Crate | Direct external dependencies | What for | Call |
|---|---|---|---|
| `weaver-traits` | `serde` (derive) | the message model's wire derives | none |
| `weaver-types` | `serde` (derive), `serde_json` (raw_value), `serde_yaml_ng` behind the `config` feature | the wire types, the record's raw boxes, the declaration parse | **[1]** the YAML parser is one function's |
| `weaver-trace` | `serde` (derive), `serde_json` (raw_value) | the record's line encoding | none |
| `weaver-diagnostic` | `serde` (derive), `serde_json` (raw_value), links `weaver-traits` | the diagnostic trace's encoding | none |
| `weaver-harness` | `serde_json`, `nix` (socket, fs, process, uio, user, poll, signal), `pyo3` behind `pyworker`, links `weaver-traits`, `weaver-types`, `weaver-trace`, `weaver-diagnostic` | the sockets and the fork, the Python loop | **[2]** `pyworker`, and **[3]** the `nix` feature set |
| `weaver-gate` | `serde_json`, `nix` (socket, fs, process, user, poll, signal), links `weaver-types` | the gate socket and its peer checks | **[3]** |
| `weaver-admin` | `serde_json`, `nix` (socket, fs, process, uio, user), `sha2`, links `weaver-types` with `config` | the coordination socket, the inventory's digests | **[4]** `sha2` is two functions' |
| `weaver-state` | `serde_json` (raw_value), `nix` (socket, fs, uio, user, poll), `rusqlite` (bundled) behind `sqlite`, `postgres` behind `postgres`, links `weaver-types` | the member's socket, the two store engines | **[5]** `postgres`, **[6]** `rusqlite` bundled |
| `weaver-analysis` | `serde` (derive), `serde_json` (raw_value), `safetensors`, `sha2` | the record reader, the residual columns, the capture digests | **[7]** `safetensors` |
| `weaver-internal` | none | the pure member, by its own manifest instrument | none |

**What `nix` is used for, read from the source against what each feature gates.** A
feature named in a manifest is code compiled whether or not the crate calls it, so the
reading below is per crate and per feature: the calls the crate makes that the feature
gates in `nix` 0.31.3, or **not reached** where the feature is named and no call the
crate makes needs it, or a dash where the crate does not name it. It was checked by the
grep and then by the compiler, in a throwaway checkout: with each not-reached feature
dropped from its manifest the crate still builds, and with a reached one dropped, `fs`
from state and `uio` from admin as the controls, it does not. The reading counts only
what the features gate, so `errno`, the `Signal` and `OFlag` types, and the raw `libc`
calls the harness and admin make through the re-export, which no feature gates, are not
in it. Note that `sendmsg`, `recvmsg` and the control-message types sit in the socket
module but behind `uio`, which is why two crates reach `uio` through the socket and one
does not.

| Crate | `socket` | `fs` | `uio` | `user` | `poll` | `process` | `signal` |
|---|---|---|---|---|---|---|---|
| `weaver-harness` | `socket`, `socketpair`, `bind`, `listen`, `accept4`, `send`, `recv`, `getsockopt` | `fcntl`, `umask`, `pipe2` | `sendmsg`, `recvmsg`, `ControlMessage` | **not reached** | `poll` | `fork`, `Pid`, `waitpid` | `kill` |
| `weaver-gate` | `socketpair`, `send`, `recv`, `getsockopt` | `fcntl`, `umask` | - | `getuid`, `User` | `poll` | `set_dumpable`, `set_pdeathsig`, `waitid`, `Pid` | `kill`, `killpg` |
| `weaver-admin` | `socket`, `socketpair`, `bind`, `listen`, `connect`, `accept4` | `fcntl` | `sendmsg`, `recvmsg`, `ControlMessage`, `cmsg_space` | `getuid`, `geteuid`, `getgid`, `Uid`, `User`, `Group`, `getgrouplist` | - | **not reached** | - |
| `weaver-state` | `getsockopt` | `fcntl`, `umask` | **not reached** | `getuid` | `poll` | - | - |

Three of the twenty-three named features are not reached. The harness names `user` and
reads its peer's credentials through `getsockopt`, which `socket` gates, and never asks
for a uid or a user by name. Admin names `process` and launches nothing through `nix`,
its agents starting under `std::process::Command` and `systemd-run`, so no fork, wait or
prctl call needs it. State names `uio` and moves no descriptor over its socket, so none
of the message calls that need it are made. Each is a feature the manifest names and no
line of the crate needs, and each is **[3]**.

## The closure at default features, forty-one crates

Grouped by what pulls them, so the operator can see what one election costs.

- **The serialization family**, in every crate: `serde`, `serde_core`,
  `serde_json`, `itoa`, `ryu`, `zmij`, `memchr`. Beside them the proc-macro
  toolchain, `serde_derive`, `syn`, `quote`, `proc-macro2`, `unicode-ident`,
  which compiles on the host and is not linked into a binary.
- **The socket layer**, in the four socket crates: `nix`, `libc`, `bitflags`,
  `cfg-if`, `memoffset`.
- **The hash**, in admin and analysis: `sha2`, `digest`, `block-buffer`,
  `crypto-common`, `generic-array`, `typenum`, `cpufeatures`.
- **The YAML parser**, in types under `config` and so in admin: `serde_yaml_ng`,
  `unsafe-libyaml`, `indexmap`, `hashbrown` 0.17, `equivalent`. `unsafe-libyaml`
  is the C library's logic carried into Rust under `unsafe`, which is what
  **[1]** weighs.
- **SQLite**, in state under `sqlite`: `rusqlite`, `libsqlite3-sys`, `hashlink`,
  `hashbrown` 0.15, `foldhash` 0.1, `fallible-iterator`,
  `fallible-streaming-iterator`, `smallvec`. The `bundled` feature compiles the
  SQLite amalgamation into the binary, which is **[6]**.
- **The tensor reader**, in analysis: `safetensors`, `hashbrown` 0.16,
  `foldhash` 0.2, `allocator-api2`.

Three versions of `hashbrown` and two of `foldhash` stand in one lock. No one
binary links more than one of each, since each comes with its own puller, so
this is lock hygiene rather than shipped surface, noted as **[8]**.

## The closure at the features the deploy builds

`deploy/update-stack.sh` builds the workspace with `weaver-harness/pyworker`,
`weaver-state/sqlite` and `weaver-state/postgres`, and installs `worker`,
`pyworker`, `weaver-admin`, `weaver-gate`, `weaver-spu` and `weaver-state`. Two
of those features change the picture.

**`weaver-state` with `postgres`: twenty-four crates become seventy-five.** The
`postgres` crate is the synchronous face of `tokio-postgres`, so the closure gains
`tokio` 1.53 with `mio`, `socket2`, `tokio-util`, `pin-project-lite` and the `futures`
family, which is the async runtime the hypothesis expected away. It gains the wire
protocol, `postgres-protocol` and `postgres-types` with `byteorder`, `bytes`, `base64`,
`percent-encoding` and `phf`, the authentication stack, `md-5`, `hmac`, `sha2` 0.11,
`chacha20`, `rand` 0.10, `getrandom`, `stringprep` with `unicode-bidi`,
`unicode-normalization` and `unicode-properties`, and `whoami`, `log`, `async-trait`,
`parking_lot` and `lock_api`. The member speaks to a local server over a socket, and the
crate that speaks for it is a network client with a network client's dependencies. The
`sha2` here is 0.11, a second major beside admin's and analysis's 0.10, with `digest`,
`block-buffer`, `crypto-common` and `cpufeatures` at a second major beside it, so the
deployed stack carries both lines across its binaries though no one binary links both.
This is **[5]**.

**`weaver-harness` with `pyworker`: `pyo3` 0.27 and the interpreter.** The
closure gains `pyo3`, `pyo3-ffi`, `once_cell`, a second `syn` at 2.0 for the
macros, and `indoc`, `unindent`, `heck` and `target-lexicon` for the build, and
the `pyworker` binary links `libpython` at run time. `worker`, the Rust worker
in the same crate, carries none of it. Which of the two a box runs is its
`worker-binary` entry, and the deploy installs both. This is **[2]**.

## The judgment calls, each the operator's

1. **`serde_yaml_ng` in `weaver-types`**, behind `config`, for one function:
   parsing an agent's declaration. It is the rule's own example, one function
   and a library, and it brings `unsafe-libyaml`. Only admin turns the feature
   on, so only `weaver-admin` ships it. The alternative is a declaration format
   the wire already has, JSON, or a parser of the subset the declaration uses.
   The call is whether YAML earns `unsafe-libyaml` in the binary that runs as
   root.
2. **`pyo3` in `pyworker`.** The Python loop is a documented route, the
   `worker-binary` entry chooses it per box, and the deploy installs `pyworker`
   beside `worker` on every box whether or not the entry names it. The call is
   whether the deployed stack should carry the interpreter's binary at all
   where the entry names the Rust worker, and whether `pyworker` belongs in the
   default deploy or behind an election.
3. **The `nix` feature sets.** Three named features are not reached, per the table
   above: `user` in the harness, `process` in admin and `uio` in state, each compiling
   code its crate never calls, which is the rule's case at the feature grain. Their
   removal is the operator's call, since each is a manifest change and this report
   makes none. The further call is whether an instrument should hold each crate's set
   to its calls, since nothing today refuses a feature no call needs.
4. **`sha2` in `weaver-admin`**, for two functions: a file's digest in the
   inventory and a declaration's digest, both sha256 to hex. Two functions and
   a library, and the same library analysis takes for the capture digests. The
   call is whether a shared digest belongs in a floor crate the two link, so
   the hash is taken once, or whether two functions in admin are the rule's
   case.
5. **`postgres` in the deployed `weaver-state`.** The store charter elects the
   engine and the deploy builds it, so this is a documented election and not
   a stray import, and it is also the async runtime and the network client the
   hypothesis excluded, fifty-one crates for one engine. The options are the
   operator's: keep it as elected, move the postgres engine behind a feature
   the default deploy does not build, or serve the store on SQLite alone until
   a deployment elects otherwise.
6. **`rusqlite` bundled.** The `bundled` feature compiles SQLite's amalgamation
   into the binary rather than linking the system library, which fixes the
   version the record is written under at the cost of carrying the C source's
   surface. The call is which of the two the record's custody prefers.
7. **`safetensors` in `weaver-analysis`.** It reads the residual columns'
   tensors and their dtype, which is what the lens is for, so it reads as
   required by operations. Named here so the reading is the operator's and not
   assumed.
8. **Lock hygiene.** Three `hashbrown`, two `foldhash`, two `syn`, and under `postgres`
   two `sha2` majors with their four companions each at two majors. No single binary
   links two of a kind, at default features or the deploy's, and the deployed stack as a
   whole carries two of each across its binaries. The call is whether the lock should be
   held to one version per crate where the pullers allow it.

## What this report does not do

It does not change a manifest, a Spec, a process file or a line of code, per
the epic. It does not read `weaver-spu` or `weaver-web`. It does not judge
transitive crates one by one below the groups above, since each group stands
or falls with its puller. It reads the lock at `e39f1339` and goes stale with
the next manifest change, which is why the counts are dated.
