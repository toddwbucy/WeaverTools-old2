# The Blackwell baseline runs, thinkpad, 2026-09-27 to 2026-09-28

The determinism matrix, `../../determinism-matrix-Spec.md`, run on thinkpad's RTX PRO
5000 Blackwell Generation Laptop GPU at 0000:01:00.0, on the stack built at 39fe573.
Four runs, each with a folder here holding its note, where it has one, a `COMMANDS.md`
saying how it was executed, and every script that produced a number in its note. The
data stays on the share: the record, the log, the summary, the config, the box facts,
the clock readings and the journal evidence are in each run's deposit, named below with
the sha256 of every file as it sits there, and none of it is copied here. Each note is a
verbatim copy of the note in its deposit, so where a note says "this directory" or
"here", or names an evidence subdirectory such as `run3-evidence/` or `run2-close/`, it
means that deposit on the shared bulk store:
`/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573-run3/` for
run3 and
`/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573-run2/` for
run2, on olympus, and the same paths under `/mnt` on the thinkpad. The harness is not
copied in either. Each `COMMANDS.md` names its commit, and git holds it.

## The runs

| Run | Window, CDT | Stack | Harness | Sessions | Reproduced | Diverged | Faults | Exit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `partial` | 2026-09-27 10:58:20 to 11:44:42, stopped when the terminal closed | 39fe573 | `d04da2a`, carried as `afae421` | 764 | 764 | 0 | 0 | none: the hangup ended it before any summary |
| `run2` | 2026-09-27 11:47:05 to 18:47:08 | 39fe573 | `d04da2a`, carried as `afae421` | 6,883 | 6,883 | 0 | 0 | not echoed, 0 by its harness's rule over its summary |
| `run3-smoke` | 2026-09-27 21:41:36 to 21:43:32 | 39fe573 | `07a7e5d` | 31 | 31 | 0 | 0 | 0, echoed |
| `run3` | 2026-09-27 21:55:05 to 2026-09-28 04:55:09 | 39fe573 | `07a7e5d` | 6,887 | 6,886 | 0 | 1 | not echoed, 1 by its harness's rule, for the one fault alone |

All four ran on one box, one card and one stack: the six binaries, the five engine
libraries, the 0.5b at q6_k (`2f822336`) and karl's declaration (`a2a03d10`), re-hashed
unchanged before each run. The harness changed between run2 and the smoke.

**What each run establishes, and what it does not**, in its note's words:

- **`partial`**: 764 sessions reproduced over 24 sweeps, with 11,008 turns compared and
  0 unmatched. It is not a completed run, and it carries no closing provenance reading.
  Its serving device is not verified for any session, since its harness read the device
  only at the end and the run never reached the end. `PARTIAL-2026-09-27.md`.
- **`run2`**: 6,883 of 6,883 reproduced over 216 sweeps, with 99,766 turns compared and
  0 unmatched, and the stack held across the window. A cold reload and the serving
  device are shown for the last 125 sessions only, by the journal's tail. For the 6,758
  before them, nothing recorded shows the unload completing, the reload starting a new
  process, or the device. `RESULT-2026-09-27.md`.
- **`run3-smoke`**: 31 of 31 reproduced on #716's harness, with 62 distinct invocations
  for 62 loads, one complete binding on the card, the seed recorded on both halves, and
  every window field unchanged. It is a smoke of about two minutes, and it wrote no
  note.
- **`run3`**: 6,886 of 6,886 compared sessions reproduced over 216 sweeps, with 99,758
  turns and 0 unmatched. For every one of them the harness verified a cold reload,
  13,772 distinct invocations for 13,772 loads, the serving device by each load's own
  complete block, and the served texts. One session was lost before comparison:
  journald's rate limit dropped its replay load's device lines, and the harness failed
  closed. That fault is the exit's only cause. The faulted session's verdict is not
  established. `RESULT-2026-09-28.md`.

Every run inherits the probe's standing limits, per its Spec's section 8. karl declares
no loop file, the model is the 0.5b, and time to first token is not measured. No clock
was held: the card's clock state was recorded instead. What an exit 0 certifies, and
what it does not guard against, is the Spec's section 5.

**Open**: epic #698's item "journald's rate limit can drop a load's device lines,
faulting the session" awaits the operator's ruling on `LogRateLimitIntervalSec=0` for
the worker unit.

## Where the deposits live

On the bulk store olympus exports and thinkpad mounts, one directory per run under
`/mnt/bulk-store/weaver-testing/`. Each deposit's `run-console.log`, where the run
wrote one, is byte-identical to its `matrix.log` by `cmp`.

The notes here are verbatim copies of the notes in the deposits, so the hashes below
hold for both. G1 was applied to the new prose here, this index and the `COMMANDS.md`
files, and not to the notes, each being a record. The scripts are the commands as run,
and where one read a path under the operator's home its header says what that path is
written as here. No home path, IP address, email address or username appears in any
file here.

Checked with `sha256sum -c` from inside each deposit, 2026-09-28:

`partial`, `determinism-matrix-thinkpad-2026-09-27-39fe573/`:

```
684e82fad5d1c3395e3accb59cdc941ac5e566bc2b12e530a0a9b85d2c25464b  box-facts.txt
caeadd536d4a8f2e8e56b98b5519d437eb4907344971cf91071e36b5008b7eb8  clock.log
d0b3641b25c0e907f17deaeb02aa85d9990962349acdd3304d5aa5a84c551ea2  config.json
d3dbab7bd125d8d822eb0f615d4a1ab20398638db5d549d848cba7413fa0147a  matrix.jsonl
7cba473f113e876f1353834ebf5fa68f2809884dbce455e98d256a6c75a0a9e8  matrix.log
15230d8066c6bb4add95f9b5f68d5257f529d0db99a6bccfdebd472efd0bfb5a  PARTIAL-2026-09-27.md
7cba473f113e876f1353834ebf5fa68f2809884dbce455e98d256a6c75a0a9e8  run-console.log
```

`run2`, `determinism-matrix-thinkpad-2026-09-27-39fe573-run2/`:

```
c157645d4c6a8dfa465a30e85674e2894adaa8c4481bb2883565e9f31688d3df  box-facts.txt
5fa32aea0e564afba3578e64ddf6cf6e0e2fc929c86ae10ebe0e74cb61b8327a  clock_join.py
6a90a14ef923c0bcb3f9c781902f3adbf8a81030848af2777b7bed7f0f44a646  clock.log
d0b3641b25c0e907f17deaeb02aa85d9990962349acdd3304d5aa5a84c551ea2  config.json
addd76eac164703bb8baa12685875ea2cfdcbc17c7e5b07fee22605ec72ee115  matrix.jsonl
5bff46a1d32f728f102d4cf048a40443c63d78d0424192269bff1d7bf03c2ca8  matrix.log
6d4c2300a81f80e63c1ad434cf9f844052395d2edd8d53f39bd99aa7af1b0b2d  RESULT-2026-09-27.md
4238765483757b5b7eb5c74315e9dde2a7c1d5c9bf8d09e56588a2683643f34f  run2-close/captured-at.txt
76c3aa2152bb32bde71b75746a51cbd863d7c8372fd116130b76449bbfc9d465  run2-close/clock-join.txt
fd9542383fb9922cec441d91d1ec69065a88773c1ece5bfe1de4370515563624  run2-close/journal-usage.txt
978e966461881509fcb4396d02236c6c3b8aff3ed99315dc5ba992749b3c9509  run2-close/stats.txt
a02a7e2bcd8bc850bffafed2ee124c8a9b8e7ac8d6967fff3223cc0870368574  run2-close/worker-journal.json
498ed968040488eb018f479c2a06c0c5687ccf7e90290936a92a45406d0c35b6  run2-close/worker-journal.txt
5bff46a1d32f728f102d4cf048a40443c63d78d0424192269bff1d7bf03c2ca8  run-console.log
f6ecc9fb5baee18ed921e6413584a7973c89907bb2bdda94261d40e76295584e  summary.json
```

`run3-smoke`, `determinism-matrix-thinkpad-2026-09-27-39fe573-run3-smoke/`:

```
7a0cf1fb8c073d8a43cfd881f52f906aba0b48c6757b13e46d5d9d6849a4a6f3  box-facts.txt
d0b3641b25c0e907f17deaeb02aa85d9990962349acdd3304d5aa5a84c551ea2  config.json
4096443649c14b8b1ca621f68d457008b415a91425508373889a388f857d9c0e  matrix.jsonl
b76212345fe65e11100330717fc835ecd84632a6fa80ed6edbdb7556977fb800  matrix.log
669d5ca2419c6706ba70ee4d16728fb7da6ff24afbf9b11f9de789416cdc6e51  summary.json
```

`run3`, `determinism-matrix-thinkpad-2026-09-27-39fe573-run3/`:

```
4fb7aadbe25b8bf587965afe0797ee5599e2573502cb56ba23b62069a6a09fa7  box-facts.txt
841570da38a05f40a7928f50de30379fc9db522e2f3418abed8e5b026524c251  clock.log
d0b3641b25c0e907f17deaeb02aa85d9990962349acdd3304d5aa5a84c551ea2  config.json
22239a9cf3074774c7e1e1f8a8416395f460732d9fbfd8efeb88cae9dd7bc73c  matrix.jsonl
35a3c3186fd13e13b92ee6bce24d9650f247168e9c9bebeb478ec7eecba75336  matrix.log
0c331575d266b5542a22abdd8d9b608a152f2c97c069d2fe361945e61a14c783  RESULT-2026-09-28.md
3521b3479a6620d95b2c1e6d216f1f4f9808b7736fd4d1086471e64419afc9fd  run3-evidence/capture.py
209353fc5495b7b77ca147f39263a0236ba15241f88e8499d230209fac112bfe  run3-evidence/clock_join.py
505cc7a2b7d1ceaf28c3ce36bf243e4f355b5f8d3fba699a2c397d06c1209b8b  run3-evidence/clock-join.txt
db148be0f1d03d01ed2e933be7e5f84f08ae1159d2bd090e8ad1c143923c508d  run3-evidence/invocations-final.jsonl
1f9901ad62d514ab9dae293faa64ba2394ee7060754550ce6d674553b7f04df9  run3-evidence/suppressed-unique.txt
35a3c3186fd13e13b92ee6bce24d9650f247168e9c9bebeb478ec7eecba75336  run-console.log
5ebc905c99932237fab4528f3e5d7d1393a468e23beb8603b84976d2954ee40c  summary.json
```
