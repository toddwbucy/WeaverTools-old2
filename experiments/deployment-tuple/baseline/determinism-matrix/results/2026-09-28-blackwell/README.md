# The Blackwell baseline runs, thinkpad, 2026-09-27 to 2026-09-29

The determinism matrix, `../../determinism-matrix-Spec.md`, run on thinkpad's RTX PRO
5000 Blackwell Generation Laptop GPU at 0000:01:00.0, on the stack built at 39fe573.
Five runs and four smokes. Each run, and run3's smoke, has a folder here holding its
note, where it has one, a `COMMANDS.md` saying how it was executed, and every script
that produced a number in its note. The later smokes are told in the `COMMANDS.md` of
the run they preceded. The data stays on the share: the record, the log, the summary,
the config, the box facts, the clock readings and the journal evidence are in each run's
deposit, named below with the sha256 of every file as it sits there, and none of it is
copied here. Each note is a verbatim copy of the note in its deposit, so where a note
says "this directory" or "here", or names an evidence subdirectory such as
`run3-evidence/` or `run2-close/`, it means that deposit on the shared bulk store, under
`/bulk-store/weaver-testing/` on olympus and the same path under `/mnt` on the thinkpad,
by the deposit names below. The harness is not copied in any. Each `COMMANDS.md` names
its commit, and git holds it.

## The runs

| Run | Window, CDT | Stack | Harness | Sessions | Reproduced | Diverged | Faults | Exit |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `partial` | 2026-09-27 10:58:20 to 11:44:42, stopped when the terminal closed | 39fe573 | `d04da2a`, carried as `afae421` | 764 | 764 | 0 | 0 | none: the hangup ended it before any summary |
| `run2` | 2026-09-27 11:47:05 to 18:47:08 | 39fe573 | `d04da2a`, carried as `afae421` | 6,883 | 6,883 | 0 | 0 | not echoed, 0 by its harness's rule over its summary |
| `run3-smoke` | 2026-09-27 21:41:36 to 21:43:32 | 39fe573 | `07a7e5d` | 31 | 31 | 0 | 0 | 0, echoed |
| `run3` | 2026-09-27 21:55:05 to 2026-09-28 04:55:09 | 39fe573 | `07a7e5d` | 6,887 | 6,886 | 0 | 1 | not echoed, 1 by its harness's rule, for the one fault alone |
| `run4-smoke` | 2026-09-28 09:53:51 to 09:55:46 | 39fe573 | `6072c69` | 31 | 31 | 0 | 0 | 0, echoed |
| `run4-smoke2` | 2026-09-28 10:00:14 to 10:02:11 | 39fe573 | `6072c69` | 31 | 31 | 0 | 0 | not echoed, 0 by its harness's rule over its summary |
| `run4` | 2026-09-28 10:06:53 to 14:42:09, interrupted by the operator | 39fe573 | `6072c69` | 4,479 | 4,477 | 0 | 2 | not echoed, interrupted: not a reproduction result |
| `run5-smoke` | 2026-09-28 19:49:36 to 19:51:30 | 39fe573 | `bb28f4f` | 31 | 31 | 0 | 0 | 0, echoed |
| `run5` | 2026-09-28 19:51:54 to 2026-09-29 02:52:09 | 39fe573 | `bb28f4f` | 6,855 | 6,855 | 0 | 0 | not echoed, 0 by its harness's rule over its summary |

All of them ran on one box, one card and one stack: the six binaries, the five engine
libraries, the 0.5b at q6_k (`2f822336`) and karl's declaration (`a2a03d10`), re-hashed
unchanged before each run. The harness changed between run2 and run3's smoke, and
again before run4's smokes, `determinism_matrix.py` taking #717's interrupt guard. It
is the same two files at `6072c69` and at `bb28f4f`. Between run3 and run4 the worker
unit's journald rate limit was lifted, and between run4 and run5 the journal's size cap
was raised, both by the operator.

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
- **`run4-smoke` and `run4-smoke2`**: 31 of 31 each, the same sessions and volume, the
  first under `LogRateLimitIntervalSec=0`, where journald still suppressed 392 worker
  lines, and the second under `LogRateLimitIntervalSec=30s` and
  `LogRateLimitBurst=1000000`, where it suppressed none. Neither wrote a note, and the
  comparison is run4's `box-facts.txt`.
- **`run4`**: interrupted by the operator at 14:42 to free the card, so not a
  reproduction result. 4,477 of 4,479 sessions reproduced over 140 sweeps, with 64,864
  turns compared and 0 unmatched. One session was cut by the interrupt, and one faulted
  at 13:24 on a replay load reading the card twice, a doubled `using device` line whose
  cause is not established, since the lifted rate limit let the 50M journal hold only
  about 13.5 minutes and its lines had rotated out. `RESULT-2026-09-28.md`.
- **`run5-smoke`**: 31 of 31 reproduced under both settings, the journal's cap raised to
  4G. It wrote no note.
- **`run5`**: the first Blackwell baseline to exit clean. 6,855 of 6,855 reproduced over
  215 sweeps, with 99,310 turns compared and 0 unmatched, a cold reload and the device
  verified for all 13,710 loads, and every window field unchanged. journald suppressed
  nothing over the run, every load kept its three device markers, and the journal kept
  the whole run at 2G of 4G. `RESULT-2026-09-29.md`.

Every run inherits the probe's standing limits, per its Spec's section 8. karl declares
no loop file, the model is the 0.5b, and time to first token is not measured. No clock
was held: the card's clock state was recorded instead. What an exit 0 certifies, and
what it does not guard against, is the Spec's section 5.

**Closed on thinkpad by run5**: epic #698's items "journald's rate limit can drop a
load's device lines, faulting the session" and "the journal's size cap must rise
whenever the rate limit is lifted", each ticked with run5 as the confirming run. Olympus
needs the same two settings before its next baseline run, where it does not already
carry them.

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

Checked with `sha256sum -c` from inside each deposit, 2026-09-28 for the first four and
2026-09-29 for the rest:

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

`run4-smoke`, `determinism-matrix-thinkpad-2026-09-28-39fe573-run4-smoke/`:

```
7ac895272de98b43820a8fab1f53a120828b8794106c0dfdb652ebbd084980ce  box-facts.txt
d0b3641b25c0e907f17deaeb02aa85d9990962349acdd3304d5aa5a84c551ea2  config.json
429b555e1b19d337ff04c123e080be898cbe428527e75db58bbc4f3895a0ab9e  matrix.jsonl
98933e8e4ffb8a3843d3780509a0f425e59f9c10e84a03032ac6e247c1f13a3a  matrix.log
669d5ca2419c6706ba70ee4d16728fb7da6ff24afbf9b11f9de789416cdc6e51  summary.json
```

`run4-smoke2`, `determinism-matrix-thinkpad-2026-09-28-39fe573-run4-smoke2/`:

```
bf97d526b6d25bafdcc7277243b3adad5c2afb20bd98065d7d601e3f44690fff  box-facts.txt
d0b3641b25c0e907f17deaeb02aa85d9990962349acdd3304d5aa5a84c551ea2  config.json
4b338140038aeca63ee480bb732849ebc78ecdf2b47d472cb7ee47e6bca776a7  matrix.jsonl
aa838d44e0396b7e9cfec60265614115b2ed886b828fd2594b9a85dbfb3de031  matrix.log
669d5ca2419c6706ba70ee4d16728fb7da6ff24afbf9b11f9de789416cdc6e51  summary.json
```

`run4`, `determinism-matrix-thinkpad-2026-09-28-39fe573-run4/`:

```
682a8f05b4584847795f2c5b0bbfacb318d35722693db35cdeb7fcd0be36d30a  box-facts.txt
f9cf4a4da8ba38e7f8fd739157387847b2347b57b675d208ad4b4fa9d2736311  clock.log
d0b3641b25c0e907f17deaeb02aa85d9990962349acdd3304d5aa5a84c551ea2  config.json
465c6fe660ee675717ffb68165cf61f7b919427e7f2a490c4ca686164e7b3b81  matrix.jsonl
6c753ec7c7f805d14f7b3ffb5764e089d9cbd9d0ba3c40a1fee77948e6efc1a4  matrix.log
9bc043d7a7f2c8043e1ae4ffde63b631f34f262c5294864a28b2d3799ca14273  RESULT-2026-09-28.md
df0f691eb213663c92cf063b9671dadf8f2cc021a9334ab85eb00e62935bb615  run4-evidence/capture.py
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  run4-evidence/capture.stderr
209353fc5495b7b77ca147f39263a0236ba15241f88e8499d230209fac112bfe  run4-evidence/clock_join.py
2f12d87268079b09acd47697b89af76ec7e383b2b9720751377002c055c5ae85  run4-evidence/clock-join.txt
dc5c4b4574a76e2a170bf957e4bb9859e90d8bc870819233e6d9c3e260ed5956  run4-evidence/invocation_markers.py
7f5b1430ee9198371b6085f2da71b9e353d464b70f58611fbc440fbb8b260f2a  run4-evidence/invocation-markers.txt
5055141270281bc1f2e6b2cb01229d5c63822e241fc199dd81d87766252a4578  run4-evidence/line-counts.json
47fd2630fc52ce898bde104e4e7063778c05027f82cb6b0ee24b4d5c440f3bba  run4-evidence/markers.jsonl
4dfd297eb7f04cadf5bd950827a2cbeeee126bd8191fa8f020b4c1e8ed468a31  run4-evidence/reads.log
722bb3a3bdfb4eb2ab2415a0b85504b37351261e9db3c728f3225e22df8e61fb  run4-evidence/record_counts.py
95a9f3e7f3231c307799c5d6408d4ae3ec672ac59bb3cce238be531f50fea49e  run4-evidence/record-counts.txt
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  run4-evidence/suppressed.txt
6c753ec7c7f805d14f7b3ffb5764e089d9cbd9d0ba3c40a1fee77948e6efc1a4  run-console.log
e08d2fb7f09c644008ba771a8730b221e9962b9e2cccc35f5d520ab4dc2233c3  summary.json
```

`run5-smoke`, `determinism-matrix-thinkpad-2026-09-28-39fe573-run5-smoke/`:

```
816df295a197029a8fb572c23dd75304ac3b8436bc9a27f639d953ea38f154d3  box-facts.txt
d0b3641b25c0e907f17deaeb02aa85d9990962349acdd3304d5aa5a84c551ea2  config.json
ff753035662ad278afaedd79ccb0fe3615fbf84fe935a88cb5a54f862d3bf7c9  matrix.jsonl
d2342c247dd1711880112d00418d67ee24061baf017bee5f42b071563a1152c9  matrix.log
669d5ca2419c6706ba70ee4d16728fb7da6ff24afbf9b11f9de789416cdc6e51  summary.json
```

`run5`, `determinism-matrix-thinkpad-2026-09-28-39fe573-run5/`:

```
6610435c4b1e9676af9166d6216eaeb4366536f09cedc36d0bf5fa78a9973059  box-facts.txt
1685b177e367120e60f9313895cacee2bbf7e2e2fb65b66fad6a07bf08b05486  clock.log
d0b3641b25c0e907f17deaeb02aa85d9990962349acdd3304d5aa5a84c551ea2  config.json
9a6bc0feb7bafa9a1283b42161ee27b233bc5e225abe5d3e53af80176448d78c  matrix.jsonl
ef7c60565c9e0e33fafae2692fc3a26223dc1571a586e814d90344093229b675  matrix.log
4b57f95e6951588b192a721b0b9829d10206e12d865d2ca43af4d57fe31d2a03  RESULT-2026-09-29.md
305894edda7a7211b78e3e2b2ff783e423ff3bd63ecdedd97f0e6b0c1b1bb4bf  run5-evidence/capture.py
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  run5-evidence/capture.stderr
209353fc5495b7b77ca147f39263a0236ba15241f88e8499d230209fac112bfe  run5-evidence/clock_join.py
342508c32c386cc1a2b9e9950cf353eba840745f8be87c36469222c8d190babb  run5-evidence/clock-join.txt
e37c9da48ed8cc99e88a6ff1d519aa0de01d50eafe4750b943cd5f3064e16c1b  run5-evidence/found.txt
4777fd344470de979e666d5007a1e9833a59f607dfbc2f6a7b38b074afe17c44  run5-evidence/invocation_markers.py
a9e2bb8bbd38f117619b48cb4394d53edb5dfe77a2fa6e61dfddd173c8d4eb3c  run5-evidence/invocation-markers.txt
71ef0233724c96d5fb4d37c787843899fcac5db4292318ef471821c2ddcdf12e  run5-evidence/journal-after.txt
403a74dbbdcf9fde950dbc6772a913ae0f8b11fa3e97f712e48ce885d39a781b  run5-evidence/line-counts.json
d58f26f20b7050277605f5025744aec48cf5d587fe104b320849555ed15eee28  run5-evidence/markers.jsonl
a7910a05f81285092cea36f30bcd65b6ba45a8c467faf4826c5044ceac5dfd41  run5-evidence/reads.log
2569f8d2e3ef9022556b6f0b2adbf6e29b69a461f03cda066fe4cd08b2dd50a3  run5-evidence/record_counts.py
523544b06e5ae37e98bf5748b53f779406b364e539accba066a92e39e8ef35f0  run5-evidence/record-counts.txt
e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  run5-evidence/suppressed.txt
ef7c60565c9e0e33fafae2692fc3a26223dc1571a586e814d90344093229b675  run-console.log
322aaed9c4894d6084676f41ac04f9163d4f4ade0d46f9017c21f98271b8d52f  summary.json
```
