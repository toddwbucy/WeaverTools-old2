"""Rust-compatible seed derivation; explicitly separate Python sampling stream."""
import math
import random
MASK=2**64-1

def derived_seed(seed,turn,generation):
    if type(seed) is not int or type(generation) is not int or not 0<=seed<=MASK or not 0<=generation<=MASK:
        raise ValueError('seed and generation must be u64')
    def mix(x):
        z=(x+0x9e3779b97f4a7c15)&MASK
        z=((z^(z>>30))*0xbf58476d1ce4e5b9)&MASK
        z=((z^(z>>27))*0x94d049bb133111eb)&MASK
        return z^(z>>31)
    h=0xcbf29ce484222325
    for b in turn.encode(): h=((h^b)*0x100000001b3)&MASK
    return mix(mix(seed^h)^generation)

def distribution(logits):
    if not logits or any(not math.isfinite(x) for x in logits): raise ValueError('invalid logits')
    m=max(logits)
    z=sum(math.exp(x-m) for x in logits)
    logp=[x-m-math.log(z) for x in logits]
    p=[math.exp(x) for x in logp]
    entropy=-sum(a*b for a,b in zip(p,logp))/math.log(2)
    return p,logp,entropy

class Sampler:
    def __init__(self,seed,temperature=.7,top_k=40,top_p=.95,penalty=1.1,window=64):
        self.rng=random.Random(seed)
        self.temperature=temperature; self.top_k=top_k; self.top_p=top_p
        self.penalty=penalty; self.window=window
    def sample(self,logits,resident):
        values=list(logits)
        for t in set(resident[-self.window:] if self.window else []):
            values[t]=values[t]*self.penalty if values[t]<0 else values[t]/self.penalty
        if self.temperature==0: return max(range(len(values)),key=values.__getitem__)
        values=[x/self.temperature for x in values]
        p,_,_=distribution(values)
        ranked=sorted(range(len(p)),key=lambda i:(-p[i],i))
        if self.top_k: ranked=ranked[:self.top_k]
        # Nucleus probability is normalized after top-k, matching native order.
        total=sum(p[i] for i in ranked)
        kept=[]; cumulative=0
        for i in ranked:
            kept.append(i); cumulative+=p[i]/total
            if cumulative>=self.top_p: break
        return self.rng.choices(kept,weights=[p[i] for i in kept],k=1)[0]
