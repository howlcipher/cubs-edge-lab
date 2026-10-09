"""Run with python3 -m cubs_edge_lab.probe."""

import argparse
from pathlib import Path

from .client import ApiError, Client, atomic_json
from .evidence import Recorder
from .probes import run
from .report import render
from .summary import summarize


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--replay', action='store_true',
                      help='Regenerate using verified cached responses only')
    mode.add_argument('--offline', action='store_true',
                      help='Write an unassessed report without network')
    parser.add_argument('--root', type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    research = args.root / 'research'
    research.mkdir(parents=True, exist_ok=True)
    result = None
    failed = False
    if not args.offline:
        try:
            recorder = Recorder(Client(args.root, offline=args.replay))
            result = run(recorder)
            atomic_json(args.root / 'data/evidence.json', recorder.records,
                        indent=None)
            failed = any('failure' in item for item in result)
        except (ApiError, ValueError, TypeError, KeyError) as exc:
            result = [{'failure': str(exc), 'query': 'probe aborted'}]
            failed = True
    atomic_json(args.root / 'data/observations.json', result)
    if not args.replay and not (research / 'raw_manifest.json').exists():
        atomic_json(research / 'raw_manifest.json', [])
    summary = summarize(result)
    atomic_json(research / 'summary.json', summary)
    (research / 'FEASIBILITY.md').write_text(render(summary))
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
