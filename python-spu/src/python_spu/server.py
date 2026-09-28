"""SPU process entry. No bind, no daemon installation, no remote model fetch."""
import argparse
import json
import math
import sys
from .transport import adopt,ChannelFault,Closed
from .wire import Envelope,SpuInstruction,TOKEN_DIRECTIVE,dump
from .session import Session,Refusal
from .engine import HFEngine,AdmissionError

class Service:
    def __init__(self,cpu=False,engine_factory=HFEngine):
        self.cpu=cpu; self.factory=engine_factory; self.position='before_admit'
        self.engine=None; self.session=None
    def close(self):
        self.session=None
        if self.engine is not None: self.engine.close(); self.engine=None
    def lifecycle(self,value):
        try: envelope=Envelope.model_validate(value)
        except ValueError as e: raise ChannelFault('malformed lifecycle envelope') from e
        payload=envelope.payload
        if 'kind' not in payload: raise ChannelFault('malformed lifecycle payload')
        body=payload.get('body',{})
        if not isinstance(body,dict): raise ChannelFault('malformed lifecycle body')
        kind=body.get('kind')
        answer={'kind':'refusal','body':{'kind':'out_of_order'}}
        admitted=False
        if envelope.position=='open' and envelope.exchange.opener=='harness' and payload['kind']=='directive':
            if kind=='admit':
                # Invalid serialization is a channel fault, not an admission attempt.
                try: instruction=SpuInstruction.model_validate(body['instruction'])
                except (KeyError,ValueError) as e: raise ChannelFault('malformed instruction') from e
                if self.position=='before_admit':
                    self.position='admit_refused'
                    try:
                        self.admit(instruction)
                        self.position='admitted'; admitted=True
                        answer={'kind':'answer','body':{'kind':'admitted'}}
                    except AdmissionError as e:
                        self.close()
                        print(json.dumps({'admission_refused':e.kind,'detail':str(e)}),file=sys.stderr)
                        answer={'kind':'refusal','body':{'kind':e.kind,**e.fields}}
            elif kind=='release' and self.position=='admitted':
                self.close(); self.position='released'
                answer={'kind':'answer','body':{'kind':'released'}}
        return {'exchange':envelope.exchange.model_dump(),'position':'close','payload':answer},admitted
    def admit(self,instruction):
        d=instruction.decoder
        values=d.tunable_values
        resolved=[]
        for name,minimum,maximum in [('seed',0,2**64),('context-capacity',0,2**64),('max-tokens-per-turn',0,2**64)]:
            value=values.get(name)
            if value is None or not math.isfinite(value) or value!=int(value) or not minimum<=value<maximum:
                raise AdmissionError('config_invalid',f'invalid or missing {name}',field=f'tunable-values.{name}')
            resolved.append(int(value))
        if d.field_election is not None and d.field_election.depth<40:
            raise AdmissionError('config_invalid','field depth below sampling cutoff 40',field='spu-instruction.decoder.field-election.depth')
        # Classifier uses a separate process in Rust. A complete paired deployment
        # is not yet certified; refuse a declaration asking this prototype for it.
        if instruction.classify is not None:
            raise AdmissionError('artifact_unreadable','classifier residency not yet supported')
        self.engine=self.factory(d.model_binding.artifact,d.model_binding.devices,cpu=self.cpu,
                                 readout=d.residual_readout_election)
        seed,capacity,limit=resolved
        if capacity>self.engine.max_context:
            raise AdmissionError('device_cannot_admit','context exceeds artifact position bound')
        self.session=Session(self.engine,d,capacity,limit,seed)
    def decode(self,value,channel):
        try: directive=dump(TOKEN_DIRECTIVE.validate_python(value))
        except ValueError as e: raise ChannelFault('malformed decode directive') from e
        kind=directive['kind']
        if self.session is None: raise Refusal('not_open')
        s=self.session
        if kind=='open': return s.open(directive['messages'],directive['column_ask'])
        s.require_open()
        if kind=='cancel': return {'kind':'at_rest'}
        if kind=='flush': return s.flush(directive['keep'])
        if kind=='elide': return s.elide(directive['from'],directive['to'])
        def cancel():
            incoming=channel.receive(nonblocking=True)
            if incoming is None: return False
            try: ask=dump(TOKEN_DIRECTIVE.validate_python(incoming))
            except ValueError as e: raise ChannelFault('malformed cancel poll') from e
            if ask['kind']=='cancel': return True
            channel.send({'kind':'out_of_order'})
            return False
        if kind=='append_and_generate':
            return s.generate(directive['turn'],directive['delta'],channel.send,cancel)
        return s.generate(directive['turn'],[],channel.send,cancel,
                          refeed=(directive['rendered'],directive['path']))
    def serve_decode(self,channel):
        while True:
            try: request=channel.receive()
            except Closed: return
            try: reply=self.decode(request,channel)
            except Refusal as e: reply=e.payload
            channel.send(reply)
    def serve(self,lifecycle,decode):
        try:
            while True:
                try: request=lifecycle.receive()
                except Closed: return
                answer,admitted=self.lifecycle(request)
                lifecycle.send(answer)
                if admitted: self.serve_decode(decode)
        finally: self.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpu-experiment',action='store_true',help='explicit CPU deployment; device ordinal must be 0')
    args=parser.parse_args()
    try:
        lifecycle,decode=adopt()
        Service(cpu=args.cpu_experiment).serve(lifecycle,decode)
    except Exception as e:
        print(json.dumps({'python_spu_fault':type(e).__name__,'detail':str(e)}),file=sys.stderr)
        return 1
    return 0
if __name__=='__main__': sys.exit(main())
