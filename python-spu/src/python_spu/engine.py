"""Local Qwen2, explicit placement, cached forwards and full rollback rebuild."""
import gc
from blake3 import blake3
from pathlib import Path

class AdmissionError(Exception):
    def __init__(self,kind,detail,**fields): self.kind=kind; self.fields=fields; super().__init__(detail)

class HFEngine:
    def __init__(self,artifact,devices,cpu=False,readout=False):
        import torch
        from transformers import AutoConfig, AutoModelForCausalLM
        from tokenizers import Tokenizer
        self.torch=torch
        self.model=None; self.cache=None; self.hooks=[]
        self.logits=None; self.norms=[]; self.current_norms=[]; self.readout=readout
        path=Path(artifact)
        if not path.is_dir(): raise AdmissionError('artifact_unresolvable',str(path))
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
            self.model=AutoModelForCausalLM.from_pretrained(path,local_files_only=True,
                trust_remote_code=False,dtype=torch.float32,attn_implementation='eager').to(self.device).eval()
            self.layers=config.num_hidden_layers
            if readout:
                for layer in self.model.model.layers:
                    self.hooks.append(layer.register_forward_hook(self._tap))
            weights=sorted(path.glob('*.safetensors'))
            if not weights: raise AdmissionError('artifact_unreadable','safetensors required')
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
