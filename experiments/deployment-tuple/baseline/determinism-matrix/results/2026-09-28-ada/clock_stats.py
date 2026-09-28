"""Summarise one deposit's clock.log, the nvidia-smi dmon samples beside the run.

    python3 clock_stats.py <deposit>

Stdlib only. It reads the deposit's clock.log and writes nothing. The columns are
dmon -s pc -o DT's: date, time, gpu, pwr, gtemp, mtemp, mclk, pclk.

It backs the clock paragraph of fred-ada/RESULT-2026-09-28.md and of README.md: the sample count, the graphics-clock range and how
many samples read 1,700 MHz or more, the memory clock's readings and counts, the GPU
temperature range and the peak power. It does not join samples to sessions.
"""
import collections
import os
import sys


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: clock_stats.py <deposit>")
    samples = 0
    pclk = []
    mclk = collections.Counter()
    gtemp = []
    power = []
    with open(os.path.join(sys.argv[1], "clock.log")) as fh:
        for line in fh:
            fields = line.split()
            if not fields or fields[0].startswith("#") or len(fields) < 8:
                continue
            samples += 1
            power.append(int(fields[3]))
            gtemp.append(int(fields[4]))
            mclk[int(fields[6])] += 1
            pclk.append(int(fields[7]))
    print(f"samples: {samples}")
    print(f"graphics clock: {min(pclk)} to {max(pclk)} MHz, "
          f"{sum(1 for p in pclk if p >= 1700)} samples at 1,700 MHz or more")
    print("memory clock: " + ", ".join(f"{k} MHz x{v}" for k, v in sorted(mclk.items())))
    print(f"GPU temperature: {min(gtemp)} to {max(gtemp)} C")
    print(f"power peak: {max(power)} W")


if __name__ == "__main__":
    main()
