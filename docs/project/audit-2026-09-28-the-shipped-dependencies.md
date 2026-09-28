# Audit: the shipped dependencies against the rule of #577

**Status:** AUDIT, 2026-09-28. A dated reading rather than a member of the
document set, and **nothing here is decided until the operator rules on it.**
It is epic #665's report and nothing else: no code, manifest, Spec or process
file changes with it, and every judgment call is marked for the operator.

**Base:** `e39f1339` on main. Every dependency below was read from `Cargo.lock`
with `cargo tree -e normal,no-proc-macro --locked --offline`, per crate, first at
the features each manifest defaults to and then at the features the deploy builds.
Nothing is taken from a manifest's own account of itself where the lock could be
asked.

## The rule, and the hypothesis it tests

The operator's rule of 2026-09-23, recorded on #577: nothing is compiled into a
binary unless operations require it, and a library pulled in for one function
is a vulnerability import. The epic's hypothesis is that this program's shape,
Unix sockets, no async runtime, no network stack and no web framework, keeps
the surface small and mostly justified. This report measures that.

**The counting basis, and why it changed.** The rule is about what is compiled into
a binary, so the count is the linked closure: the crates `cargo tree` reaches over
normal edges with proc-macro crates excluded, which is what the binary carries. A
proc-macro crate and what only it pulls run on the host at compile time and link into
nothing, and the lock's build and dev edges likewise never reach a binary. Earlier
readings of this report counted `-e normal`, which carries the proc-macro crates and
their closure, and every figure moved by that set's size when the basis was corrected,
so every figure here is re-derived on the linked basis rather than adjusted. Counts are
by name and version, with the by-name figure beside them where the two differ.

**The host-side set, named once and in no count below.** Every crate that derives
`serde` compiles `serde_derive` with `syn` 3.0, `quote`, `proc-macro2` and
`unicode-ident`, five crates. The `pyworker` feature adds `pyo3-macros`,
`pyo3-macros-backend`, `pyo3-build-config`, `heck`, `indoc`, `target-lexicon` and a
second `syn` at 2.0, seven more, and `postgres` adds `async-trait`, one more. None of
the thirteen links into a shipped binary.

**The measure, up front.** At the manifests' default features the hypothesis holds for
every one of the ten crates: the ten share one serialization family, four take `nix` for
the socket and process calls, two take a hash, one takes SQLite, one takes a YAML
parser, one takes a tensor reader, and the pure member takes nothing. Thirty-six linked
crates in all, thirty-three by name. **At the features the deploy builds, the hypothesis
does not hold for one crate.** `weaver-state`'s `postgres` feature, which
`deploy/update-stack.sh` carries, brings an async runtime and a network client,
sixty-nine linked crates in place of nineteen, and `weaver-harness`'s `pyworker` feature
links the Python interpreter. Both are elections the documents made and neither is
hidden, and what the operator decides about them is the report's largest call.

## Out of scope, by name

`weaver-spu` is the olympus lane and is not read here. `weaver-web` left the
repository on 2026-09-26 for `WeaverTools_Project/weaver-web/` and is not read
here. Neither is skipped silently.

## What each crate ships, at its default features

The direct normal dependencies, the features they are taken with, what each does in
the crate, and the crate's linked closure. Every workspace crate a package depends on
directly, as `cargo tree -e normal --depth 1` shows it, is named in its row, and none
is counted as external.

| Crate | Direct external dependencies | What for | Linked | Call |
|---|---|---|---|---|
| `weaver-traits` | `serde` (derive), links no workspace crate | the message model's wire derives | 2 | none |
| `weaver-types` | `serde` (derive), `serde_json` (raw_value), `serde_yaml_ng` behind the `config` feature, links `weaver-traits` | the wire types, the record's raw boxes, the declaration parse | 6 | **[1]** the YAML parser is one function's |
| `weaver-trace` | `serde` (derive), `serde_json` (raw_value), links no workspace crate | the record's line encoding | 6 | none |
| `weaver-diagnostic` | `serde` (derive), `serde_json` (raw_value), links `weaver-traits` | the diagnostic trace's encoding | 6 | none |
| `weaver-harness` | `serde_json`, `nix` (socket, fs, process, uio, user, poll, signal), `pyo3` behind `pyworker`, links `weaver-traits`, `weaver-types`, `weaver-trace`, `weaver-diagnostic` | the sockets and the fork, the Python loop | 11 | **[2]** `pyworker`, and **[3]** the `nix` feature set |
| `weaver-gate` | `serde_json`, `nix` (socket, fs, process, user, poll, signal), links `weaver-types` | the gate socket and its peer checks | 11 | **[3]** |
| `weaver-admin` | `serde_json`, `nix` (socket, fs, process, uio, user), `sha2`, links `weaver-types` with `config` | the coordination socket, the inventory's digests | 24 | **[4]** `sha2` is two functions' |
| `weaver-state` | `serde_json` (raw_value), `nix` (socket, fs, uio, user, poll), `rusqlite` (bundled) behind `sqlite`, on by default, `postgres` behind `postgres`, links `weaver-types` | the member's socket, the two store engines | 19 | **[5]** `postgres`, **[6]** `rusqlite` bundled |
| `weaver-analysis` | `serde` (derive), `serde_json` (raw_value), `safetensors`, `sha2`, links no workspace crate | the record reader, the residual columns, the capture digests | 19 | **[7]** `safetensors` |
| `weaver-internal` | none, and links no workspace crate | the pure member, by its own manifest instrument | 0 | none |

**What `nix` is used for, read from the source against what each feature gates.** A
feature named in a manifest is code compiled whether or not the crate calls it, so the
reading below is per crate and per feature: the calls the crate makes that the feature
gates in `nix` 0.31.3, or **not reached** where the feature is named and no call the
crate makes needs it, **tests only** where the only call is in a test, or a dash where
the crate does not name it. It was checked by the grep and then by the compiler, in a
throwaway checkout, for every named feature of every crate, two ways: `cargo check` for
the shipped code and `cargo check --tests` for the tests. A feature reads reached in the
shipped binary where the first check fails without it, tests only where the first builds
and the second fails, and not reached where both build. Two of the forty-six checks are
uninformative rather than clean: `signal` implies `process` in `nix`'s own manifest, so
dropping `process` from the harness or the gate, which both name `signal`, removes
nothing, and their `process` reading rests on the calls alone. The reading counts only
what the features gate, so `errno`, the `Signal` and `OFlag` types, and the raw `libc`
calls the harness and admin make through the re-export, which no feature gates, are not
in it. Note that `sendmsg`, `recvmsg` and the control-message types sit in the socket
module but behind `uio`, which is why two crates reach `uio` through the socket and one
does not.

| Crate | `socket` | `fs` | `uio` | `user` | `poll` | `process` | `signal` |
|---|---|---|---|---|---|---|---|
| `weaver-harness` | `socket`, `socketpair`, `bind`, `listen`, `accept4`, `send`, `recv`, `getsockopt` | `fcntl`, `umask`, `pipe2` | `sendmsg`, `recvmsg`, `ControlMessage` | **tests only**, `getuid` in `tests/service.rs` | `poll` | `fork`, `Pid`, `waitpid` | `kill` |
| `weaver-gate` | `socketpair`, `send`, `recv`, `getsockopt` | `fcntl`, `umask` | - | `getuid`, `User` | `poll` | `set_dumpable`, `set_pdeathsig`, `waitid`, `Pid` | `kill`, `killpg` |
| `weaver-admin` | `socket`, `socketpair`, `bind`, `listen`, `connect`, `accept4` | `fcntl` | `sendmsg`, `recvmsg`, `ControlMessage`, `cmsg_space` | `getuid`, `geteuid`, `getgid`, `Uid`, `User`, `Group`, `getgrouplist` | - | **not reached** | - |
| `weaver-state` | `getsockopt` | `fcntl`, `umask` | **not reached** | **tests only**, `getuid` under `cfg(test)` | `poll` | - | - |

Four of the twenty-three named features are not reached by the shipped binary, and two
of the four are reached by tests alone. The harness names `user`, reads its peer's
credentials through `getsockopt`, which `socket` gates, and asks for its own uid only in
an integration test. State names `user` and asks for its uid only under `cfg(test)`, in
`main.rs` and in the comparison module that `postgres` compiles for tests. Admin names
`process` and launches nothing through `nix`, its agents starting under
`std::process::Command` and `systemd-run`, so no fork, wait or prctl call needs it.
State names `uio` and moves no descriptor over its socket, so none of the message calls
that need it are made. Each is a feature the manifest names and no line of the shipped
crate needs, and each is **[3]**.

## The linked closure at default features, thirty-six crates

The basis in one sentence: every crate `cargo tree -e normal,no-proc-macro` lists for a
package at its default features, by name and version, counted once however many groups
pull it. Grouped by what pulls them, so the operator can see what one election costs,
and a package's linked count in the table above is the sum of the groups it takes,
`cfg-if` and `equivalent` being the two pulled by more than one group.

- **The serialization family, six**, in every crate but the pure member: `serde`,
  `serde_core`, `serde_json`, `itoa`, `zmij`, `memchr`. `weaver-traits` takes the
  first two alone, having no JSON to write.
- **The socket layer, five**, in the four socket crates: `nix`, `libc`, `bitflags`,
  `cfg-if`, `memoffset`, the last brought by `nix`'s `socket` feature.
- **The hash, seven**, in admin and analysis: `sha2`, `digest`, `block-buffer`,
  `crypto-common`, `generic-array`, `typenum`, `cpufeatures`, and `cfg-if` again under
  `cpufeatures`.
- **The YAML parser, six**, in types under `config` and so in admin: `serde_yaml_ng`,
  `unsafe-libyaml`, `indexmap`, `hashbrown` 0.17, `equivalent`, `ryu`.
  `unsafe-libyaml` is the C library's logic carried into Rust under `unsafe`, which is
  what **[1]** weighs.
- **SQLite, eight**, in state under `sqlite`, which is its default: `rusqlite`,
  `libsqlite3-sys`, `hashlink`, `hashbrown` 0.15, `foldhash` 0.1, `fallible-iterator`
  0.3, `fallible-streaming-iterator`, `smallvec`. The `bundled` feature compiles the
  SQLite amalgamation into the binary, which is **[6]**.
- **The tensor reader, four**, in analysis: `safetensors`, `hashbrown` 0.16, `foldhash`
  0.2, `allocator-api2`, and `equivalent` again under `hashbrown`.

So `weaver-traits` is 2, the three JSON crates are 6 each, the harness and the gate
are 6 + 5 = 11, admin is 6 + 5 + 7 + 6 = 24, state is 6 + 5 + 8 = 19, and analysis is
6 + 7 + 4 + 2 = 19, the 2 being `cfg-if` and `equivalent`.

Three versions of `hashbrown` and two of `foldhash` stand in one lock, which is the
three between thirty-six and thirty-three. Each version has its own puller, `hashlink`,
`safetensors` and `indexmap` for the three `hashbrown` and two of those `hashbrown` for
the two `foldhash`, and no one binary links more than one of each at default features,
so this is lock hygiene rather than shipped surface, noted as **[8]**.

## The linked closure at the features the deploy builds

`deploy/update-stack.sh` builds the workspace with `weaver-harness/pyworker`,
`weaver-state/sqlite` and `weaver-state/postgres`, and installs `worker`,
`pyworker`, `weaver-admin`, `weaver-gate`, `weaver-spu` and `weaver-state`. Two
of those features change the picture.

**Each closure below is complete, read as `cargo tree -p <crate> -e normal,no-proc-macro
--locked --offline --features <feature>` diffed against the same command without the
feature**, by name and version, so a count re-derives from the list beside it. Two
crates a reader of the lock will look for are absent because they never link:
`rustversion`, a build dependency of `indoc`, and `portable-atomic`, which `pyo3` takes
only on a target without 64-bit atomics, which this one is not.

**`weaver-state` with `postgres`: nineteen linked crates become sixty-nine, fifty
added, sixty-eight by name.** The `postgres` crate is the synchronous face of
`tokio-postgres`, and the fifty, grouped:

- **The async runtime the hypothesis expected away, fifteen:** `tokio` 1.53, `mio`,
  `socket2`, `tokio-util`, `pin-project-lite`, `futures-core`, `futures-channel`,
  `futures-sink`, `futures-task`, `futures-util`, `parking_lot`, `parking_lot_core`,
  `lock_api`, `scopeguard`, `log`.
- **The wire protocol, twelve:** `postgres`, `tokio-postgres`, `postgres-protocol`,
  `postgres-types`, `byteorder`, `bytes`, `base64`, `percent-encoding`, `phf`,
  `phf_shared`, `siphasher`, and `fallible-iterator` 0.2 beside the 0.3 that
  `rusqlite` holds, the one name this binary links at two versions.
- **The authentication stack, sixteen:** `md-5`, `hmac`, `sha2` 0.11, `digest` 0.11,
  `block-buffer` 0.12, `crypto-common` 0.2, `cpufeatures` 0.3, `hybrid-array`,
  `typenum`, `const-oid`, `chacha20`, `rand` 0.10, `rand_core`, `getrandom`, `cmov`,
  `ctutils`.
- **String preparation, six:** `stringprep`, `unicode-bidi`, `unicode-normalization`,
  `unicode-properties`, `tinyvec`, `tinyvec_macros`.
- **And `whoami`**, one.

The member speaks to a local server over a socket, and the crate that speaks for it is
a network client with a network client's dependencies. The `sha2` here is 0.11, a
second major beside admin's and analysis's 0.10, with `digest`, `block-buffer`,
`crypto-common` and `cpufeatures` at a second major beside it, so the deployed stack
carries both lines across its binaries though no one binary links both. This is
**[5]**.

**`weaver-harness` with `pyworker`: eleven linked crates become fifteen, four added.**
`pyo3` 0.27, `pyo3-ffi`, `once_cell` and `unindent`, and the `pyworker` binary links
`libpython` at run time, which no count here carries. `worker`, the Rust worker in the
same crate, carries none of it. Which of the two a box runs is its `worker-binary`
entry, and the deploy installs both. This is **[2]**.

**The two engines of state, on the same basis.** `sqlite` is state's default feature,
so the nineteen-crate closure above is the default build, and the build without SQLite
is `--no-default-features`, eleven crates: the eight of the SQLite group are what the
default adds. `weaver-types` with `config` is twelve crates in place of six, the six of
the YAML parser's group, and admin is the one consumer that turns it on.

## The judgment calls, each the operator's

Each is re-read on the linked basis and against the crate rules the corpus carries,
and an alternative that neither makes effective is not offered.

1. **`serde_yaml_ng` in `weaver-types`**, behind `config`, for one function:
   parsing an agent's declaration. It is the rule's own example, one function
   and a library, and it brings `unsafe-libyaml`. Only admin turns the feature
   on, so only `weaver-admin` ships it, six linked crates of its twenty-four.
   The alternative is a declaration format the wire already has, JSON, or a
   parser of the subset the declaration uses. The call is whether YAML earns
   `unsafe-libyaml` in the binary that runs as root.
2. **`pyo3` in `pyworker`.** The Python loop is a documented route, the
   `worker-binary` entry chooses it per box, and the deploy installs `pyworker`
   beside `worker` on every box whether or not the entry names it. The linked
   cost is four crates and the interpreter at run time, in the one binary. The
   call is whether the deployed stack should carry the interpreter's binary at
   all where the entry names the Rust worker, and whether `pyworker` belongs in
   the default deploy or behind an election.
3. **The `nix` feature sets.** Four named features are not reached by the shipped
   binary, per the table above: `user` in the harness and in state, `process` in
   admin and `uio` in state, each compiling code its binary never calls, which is
   the rule's case at the feature grain. The two `user` reaches are by tests alone,
   and a test's need is dev-time under the rule, which speaks of what is compiled
   into a binary that ships, so what a test alone needs is a feature for the test
   build rather than for the binary. Their removal is the operator's call, since
   each is a manifest change and this report makes none. The further call is
   whether an instrument should hold each crate's set to its calls, since nothing
   today refuses a feature no call needs.
4. **`sha2` in `weaver-admin`**, for two functions: a file's digest in the
   inventory and a declaration's digest, both sha256 to hex. Two functions and
   a library, and the same library analysis takes for the capture digests. Two
   binaries link it either way: `weaver-analysis` links no workspace crate, by its
   Spec's section 1 as its manifest records, so no shared helper can serve both,
   and a helper placed in a floor crate would make the hash transitive for every
   binary that links that crate while reducing neither of these two. The call is
   whether two functions in admin are the rule's case, with the hash linked twice
   across the stack whichever way it goes.
5. **`postgres` in the deployed `weaver-state`.** The store charter elects the
   engine and the deploy builds it, so this is a documented election and not
   a stray import, and it is also the async runtime and the network client the
   hypothesis excluded, fifty linked crates for one engine. The options are the
   operator's: keep it as elected, stop building the feature in the default
   deploy so that a deployment elects it, or serve the store on SQLite alone
   until a deployment elects otherwise.
6. **`rusqlite` bundled.** The `bundled` feature compiles SQLite's amalgamation
   into the binary rather than linking the system library, which fixes the
   version the record is written under at the cost of carrying the C source's
   surface. The call is which of the two the record's custody prefers.
7. **`safetensors` in `weaver-analysis`.** It reads the residual columns'
   tensors and their dtype, which is what the lens is for, so it reads as
   required by operations. Named here so the reading is the operator's and not
   assumed.
8. **Lock hygiene.** Three `hashbrown` and two `foldhash` at default features, and
   under `postgres` two `fallible-iterator` minors in one binary and two `sha2`
   majors with their four companions across the stack. The lock cannot unify the
   `hashbrown` three, each puller naming its own major, so the call is whether to
   carry them, to wait on the pullers, or to drop a puller, `safetensors` and
   `indexmap` being the two this report already weighs under **[7]** and **[1]**.

## What this report does not do

It does not change a manifest, a Spec, a process file or a line of code, per
the epic. It does not read `weaver-spu` or `weaver-web`. It does not judge
transitive crates one by one below the groups above, since each group stands
or falls with its puller. It reads the lock at `e39f1339` and goes stale with
the next manifest change, which is why the counts are dated.
