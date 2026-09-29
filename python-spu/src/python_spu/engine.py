"""Local Qwen2, explicit placement, cached forwards and full rollback rebuild."""
import gc
import os
import stat
from blake3 import blake3
from pathlib import Path

# The dtype the first version loads at, per python-spu-Spec sections 4 and 9: named
# once, used by the load and read by the smoke's report, so the two cannot disagree.
DTYPE='bfloat16'

# The headroom the Rust SPU compiles in, `HEADROOM_BYTES` in weaver-spu's main.rs, which
# stands wherever the worker's vector states none.
HEADROOM_BYTES=512*1024*1024
U64_MAX=2**64-1

class AdmissionError(Exception):
    def __init__(self,kind,detail,**fields): self.kind=kind; self.fields=fields; super().__init__(detail)

def _split(name):
    """weaver-spu artifact.rs `split_pattern`, ported: `<stem>-NNNNN-of-NNNNN` before a
    `.gguf` or `.safetensors` suffix, both fields five ASCII digits, the index within the
    count. Answers (stem, count, suffix), or None for a name outside the pattern."""
    for suffix in ('.gguf','.safetensors'):
        if name.endswith(suffix):
            rest=name[:-len(suffix)]
            break
    else:
        return None
    if len(rest)<15: return None
    head,of_part=rest[:-9],rest[-9:]
    if not of_part.startswith('-of-'): return None
    count_digits=of_part[4:]
    if not all(c in '0123456789' for c in count_digits): return None
    count=int(count_digits)
    if len(head)<6: return None
    stem_dash,index_digits=head[:-5],head[-5:]
    if not all(c in '0123456789' for c in index_digits): return None
    if not stem_dash.endswith('-'): return None
    stem=stem_dash[:-1]
    if not stem or count==0: return None
    index=int(index_digits)
    if index==0 or index>count: return None
    return stem,count,suffix

def containers(directory):
    """The files the Rust SPU pins for a directory artifact, ported from weaver-spu
    artifact.rs: `resolve`'s `container_within`, then `pin`. The containers are the
    regular files named `.gguf` or `.safetensors`, symbolic links followed. One of them
    resolves, or several resolve as one exactly where they are one split's shards, every
    shard present. Anything else is two artifacts in one directory and refuses as
    unresolvable. Answers the pinned files in shard order."""
    directory=Path(directory)
    try: names=os.listdir(directory)
    except OSError as e: raise AdmissionError('artifact_unreadable',f'{directory}: {e}') from None
    found=[directory/name for name in names
           if Path(name).suffix in ('.gguf','.safetensors') and os.path.isfile(directory/name)]
    if not found:
        raise AdmissionError('artifact_unresolvable',f'{directory} holds no container')
    if len(found)==1:
        first=found[0]
    else:
        parsed=[_split(p.name) for p in found]
        if None in parsed or len(set(parsed))!=1 or len(found)!=parsed[0][1]:
            raise AdmissionError('artifact_unresolvable',
                                 f'{directory} holds {len(found)} containers that are not one split')
        stem,count,suffix=parsed[0]
        first=directory/f'{stem}-{1:05}-of-{count:05}{suffix}'
    split=_split(first.name)
    members=[first] if split is None else [
        directory/f'{split[0]}-{index:05}-of-{split[1]:05}{split[2]}' for index in range(1,split[1]+1)]
    for member in members:
        try: mode=os.stat(member).st_mode
        except FileNotFoundError: raise AdmissionError('artifact_unresolvable',f'{member} is absent') from None
        except OSError as e: raise AdmissionError('artifact_unreadable',f'{member}: {e}') from None
        if not stat.S_ISREG(mode): raise AdmissionError('artifact_unresolvable',f'{member} is not a file')
    return members

def judge_room(ordinal,free,total,shard_bytes,headroom):
    """weaver-spu gpu/mod.rs `room_and_reach`, its room half, ported: a device admits
    when its free memory is at least the shard plus the headroom, the sum saturating at
    u64. It refuses and never evicts. The Rust SPU's `NoRoom` crosses the wire as the bare
    `device_cannot_admit`, so the figures travel in the refusal's detail, never as wire
    fields."""
    needed=min(shard_bytes+headroom,U64_MAX)
    if free<needed:
        raise AdmissionError('device_cannot_admit',
                             f'no room on device {ordinal}: free {free}, needed {needed}, total {total}')

class HFEngine:
    def __init__(self,artifact,devices,cpu=False,readout=False,headroom=HEADROOM_BYTES):
        import torch
        from transformers import AutoConfig, AutoModelForCausalLM
        from tokenizers import Tokenizer
        self.torch=torch
        self.model=None; self.cache=None; self.hooks=[]
        self.logits=None; self.norms=[]; self.current_norms=[]; self.readout=readout
        path=Path(artifact)
        if not path.is_dir(): raise AdmissionError('artifact_unresolvable',str(path))
        # Step one, as the Rust SPU's: the directory resolves to its containers, free.
        members=containers(path)
        if members[0].suffix!='.safetensors': raise AdmissionError('artifact_unreadable','safetensors required')
        if len(devices)!=1: raise AdmissionError('device_cannot_admit','one device required')
        if cpu and devices!=[0]: raise AdmissionError('device_cannot_admit','CPU experiment requires ordinal 0')
        self.device='cpu' if cpu else f'cuda:{devices[0]}'
        if not cpu and (not torch.cuda.is_available() or devices[0]>=torch.cuda.device_count()):
            raise AdmissionError('device_cannot_admit','assigned CUDA device unavailable')
        try:
            config=AutoConfig.from_pretrained(path,local_files_only=True,trust_remote_code=False)
            if config.model_type!='qwen2': raise AdmissionError('artifact_unreadable','only qwen2 is verified')
            if getattr(config,'quantization_config',None): raise AdmissionError('artifact_unreadable','quantized artifacts unsupported')
            self.max_context=config.max_position_embeddings
            self.tokenizer=Tokenizer.from_file(str(path/'tokenizer.json'))
            self.terminator=self.tokenizer.token_to_id('<|im_end|>')
            for marker in ('<|im_start|>','<|im_end|>'):
                ids=self.tokenizer.encode(marker,add_special_tokens=False).ids
                if len(ids)!=1 or self.tokenizer.id_to_token(ids[0])!=marker:
                    raise AdmissionError('artifact_unreadable',f'marker not promoted: {marker}')
            # **Room is judged before the weights load**, per python-spu-Spec section 3,
            # as the Rust SPU judges it: the shard is the pinned containers' size over
            # the device count. A CPU experiment has no device and so no room to judge.
            if not cpu:
                shard_bytes=sum(os.stat(m).st_size for m in members)//len(devices)
                try: free,total=torch.cuda.mem_get_info(devices[0])
                except RuntimeError as e: raise AdmissionError('device_cannot_admit',f'device {devices[0]} unreachable: {e}') from None
                judge_room(devices[0],free,total,shard_bytes,headroom)
            self.model=AutoModelForCausalLM.from_pretrained(path,local_files_only=True,
                trust_remote_code=False,dtype=getattr(torch,DTYPE),attn_implementation='eager').to(self.device).eval()
            self.layers=config.num_hidden_layers
            if readout:
                for layer in self.model.model.layers:
                    self.hooks.append(layer.register_forward_hook(self._tap))
            digest=blake3()
            def walk(directory):
                for file in sorted(directory.iterdir(),key=lambda p:p.name):
                    if file.is_symlink(): continue
                    if file.is_dir(): yield from walk(file)
                    elif file.is_file(): yield file
            for file in walk(path):
                digest.update(str(file.relative_to(path)).encode())
                with file.open('rb') as stream:
                    for chunk in iter(lambda:stream.read(1024*1024),b''): digest.update(chunk)
            self.weights_hash=digest.hexdigest()
            self.artifact=str(path.resolve())
            torch.set_num_threads(1)
            torch.use_deterministic_algorithms(True)
        except AdmissionError:
            self.close(); raise
        except torch.OutOfMemoryError as e:
            self.close(); raise AdmissionError('device_cannot_admit',str(e)) from e
        except Exception as e:
            self.close(); raise AdmissionError('artifact_unreadable',str(e)) from e
    def _tap(self,module,args,output):
        values=output[0] if isinstance(output,tuple) else output
        norm=values.detach().float().square().sum().sqrt().item()
        self.current_norms.append(norm)
    def tokenize(self,text): return self.tokenizer.encode(text,add_special_tokens=False).ids
    def detokenize(self,tokens):
        return self.tokenizer.decode(tokens,skip_special_tokens=False)
    def append(self,tokens):
        if not tokens: return
        torch=self.torch
        self.current_norms=[]
        with torch.inference_mode():
            result=self.model(input_ids=torch.tensor([tokens],device=self.device),
                              past_key_values=self.cache,use_cache=True)
        self.cache=result.past_key_values
        self.logits=result.logits[0,-1].float().cpu().tolist()
        if self.readout:
            if len(self.current_norms)!=self.layers: raise RuntimeError('incomplete residual tap')
            self.norms.extend(self.current_norms)
    def rebuild(self,tokens):
        self.cache=None; self.logits=None; self.norms=[]
        self.append(tokens)
    def close(self):
        for hook in self.hooks: hook.remove()
        self.hooks=[]; self.cache=None; self.model=None; self.logits=None
        gc.collect()
        if getattr(self,'device','cpu').startswith('cuda'):
            with self.torch.cuda.device(self.device): self.torch.cuda.empty_cache()
