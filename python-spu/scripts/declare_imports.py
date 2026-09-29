"""Generates the declared import set, per python-spu-Spec section 8.

Each launch runs the real serving path, python -m python_spu.server and, where given,
the zipapp, with --declare-imports: the process records the modules it holds at
admission and after its first generation, then exits. The union of every launch,
with every name imports.txt already holds, is written back sorted beneath the file's
header, and the run's device line in the header is stamped. The tiny model is built
in a separate process, so building it adds nothing to what is recorded.

Usage: python scripts/declare_imports.py --device cpu [--zipapp PATH] [--model DIR]
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from python_spu.client import LocalProcess  # noqa: E402

LIST = ROOT / "src" / "python_spu" / "imports.txt"

TINY = r'''
import sys, torch
from transformers import Qwen2Config, Qwen2ForCausalLM, PreTrainedTokenizerFast
from tokenizers import Tokenizer, models, pre_tokenizers
path = sys.argv[1]
vocab = {'[UNK]': 0, '<|im_start|>': 1, '<|im_end|>': 2, 'system': 3, 'user': 4,
         'assistant': 5, 'hello': 6, 'world': 7, 'be': 8, 'precise': 9}
vocab.update({f'word{i}': i for i in range(10, 64)})
backend = Tokenizer(models.WordLevel(vocab, unk_token='[UNK]'))
backend.pre_tokenizer = pre_tokenizers.WhitespaceSplit()
PreTrainedTokenizerFast(tokenizer_object=backend, unk_token='[UNK]', eos_token='<|im_end|>',
    additional_special_tokens=['<|im_start|>', '<|im_end|>']).save_pretrained(path)
torch.manual_seed(726)
Qwen2ForCausalLM(Qwen2Config(vocab_size=64, hidden_size=32, intermediate_size=64,
    num_hidden_layers=2, num_attention_heads=4, num_key_value_heads=2,
    max_position_embeddings=256, bos_token_id=1, eos_token_id=2)).save_pretrained(path)
'''


def launch(command, arguments, model, record, device):
    with tempfile.TemporaryDirectory() as scratch:
        process = LocalProcess(Path(scratch) / "stderr.txt", command=command,
                               arguments=[*arguments, "--declare-imports", str(record)])
        identity = [{"role": "system", "content": [{"type": "text", "text": "be precise"}]}]
        instruction = {"decoder": {
            "model-binding": {"artifact": str(model), "devices": [0]},
            "residual-readout-election": False, "surprisal-election": True,
            "identity": identity,
            "tunable-values": {"seed": 11, "context-capacity": 256, "max-tokens-per-turn": 4}}}
        answer = process.ask({"kind": "admit", "instruction": instruction})
        assert answer["payload"] == {"kind": "answer", "body": {"kind": "admitted"}}, answer
        decode = process.channels[1]
        decode.send({"kind": "open", "session": "declare", "messages": identity})
        assert decode.receive() == {"kind": "opened"}
        decode.send({"kind": "append_and_generate", "turn": "declare-turn", "delta": [
            {"role": "user", "content": [{"type": "text", "text": "hello world"}]}]})
        _, status = os.waitpid(process.pid, 0)
        code = os.waitstatus_to_exitcode(status)
        if code != 0:
            raise RuntimeError(f"the declaring launch exited {code}: "
                               + (Path(scratch) / "stderr.txt").read_text())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device", choices=("cpu", "cuda"), required=True)
    parser.add_argument("--zipapp", type=Path)
    parser.add_argument("--model", type=Path)
    args = parser.parse_args(argv)
    arguments = ["--cpu-experiment"] if args.device == "cpu" else []
    with tempfile.TemporaryDirectory() as scratch:
        model = args.model
        if model is None:
            model = Path(scratch) / "tiny-qwen2"
            subprocess.run([sys.executable, "-c", TINY, str(model)], check=True)
        record = Path(scratch) / "record.txt"
        env_path = os.environ.get("PYTHONPATH")
        os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, [str(ROOT / "src"), env_path]))
        launch(None, arguments, model, record, args.device)
        if args.zipapp is not None:
            launch([sys.executable, str(args.zipapp.resolve())], arguments, model, record,
                   args.device)
        recorded = {line.strip() for line in record.read_text().splitlines() if line.strip()}
    text = LIST.read_text()
    header = [line for line in text.splitlines() if line.startswith("#")]
    names = {line.strip() for line in text.splitlines()
             if line.strip() and not line.startswith("#")}
    stamp = (f"# {args.device}: {datetime.date.today().isoformat()}, "
             f"python {sys.version.split()[0]}, "
             f"{'with the zipapp' if args.zipapp else 'without the zipapp'}")
    header = [stamp if line.startswith(f"# {args.device}:") else line for line in header]
    merged = sorted(names | recorded)
    LIST.write_text("\n".join(header) + "\n" + "\n".join(merged) + "\n")
    print(json.dumps({"device": args.device, "recorded": len(recorded),
                      "added": len(recorded - names), "declared": len(merged)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
