"""Shared checked, alternating-order timing for CPU reference and revision comparisons."""
import os
from pathlib import Path
import statistics
import subprocess
import time


def run_checked(command, *, cwd=None, env=None, timeout=180):
    start = time.perf_counter()
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                            check=True, timeout=timeout)
    return time.perf_counter() - start, (result.stdout, result.stderr)


def interleaved(commands, runs, *, check_output=True):
    if runs < 1:
        raise ValueError('runs must be positive')
    samples = {name: [] for name in commands}
    expected = None
    names = list(commands)
    for round_number in range(runs):
        order = names if round_number % 2 == 0 else names[::-1]
        for name in order:
            seconds, output = run_checked(**commands[name])
            if check_output:
                if expected is None:
                    expected = output
                elif output != expected:
                    raise ValueError('OUTPUT MISMATCH: ' + name + ' in round ' + str(round_number + 1)
                                     + f' expected={expected!r} actual={output!r}')
            samples[name].append(seconds)
    return {name: statistics.median(values) for name, values in samples.items()}, samples


def tin_command(root, source, output, compiler=None):
    root = Path(root).resolve()
    sources = [str(source)]
    return {'command': [str(Path(compiler).resolve() if compiler else root / 'bin/tinc'),
                        '-o', str(output), *sources],
            'cwd': str(root), 'env': dict(os.environ, TIN_ROOT=str(root), LC_ALL='C')}


def benchmark_names(directory, selected):
    names = sorted(p.stem for p in directory.glob('*.tin'))
    unknown = set(selected) - set(names)
    if unknown:
        raise ValueError('unknown benchmarks: ' + ', '.join(sorted(unknown)))
    if selected:
        names = [name for name in names if name in selected]
    if not names:
        raise ValueError('no benchmarks found in ' + str(directory))
    return names
