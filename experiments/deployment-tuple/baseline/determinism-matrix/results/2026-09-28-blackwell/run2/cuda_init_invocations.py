"""How many worker invocations in run2's closing journal capture logged a CUDA
initialization, which RESULT-2026-09-27.md reports. The inline command run
2026-09-27 at 18:47 CDT, verbatim but for the capture's directory, which was
under the operator's home and is written here as where the file sits on the
share."""
import json
J='/mnt/bulk-store/weaver-testing/determinism-matrix-thinkpad-2026-09-27-39fe573-run2/run2-close'
inv=set()
for l in open(J+'/worker-journal.json'):
    try: e=json.loads(l)
    except: continue
    if 'ggml_cuda_init: found' in str(e.get('MESSAGE','')): inv.add(e.get('_SYSTEMD_INVOCATION_ID'))
print('distinct invocations with a cuda init:', len(inv))
