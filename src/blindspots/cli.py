"""Command line: `blindspots <command> [options]` (or `python -m blindspots`).

    lab          Experiment 1: planted faults in a five-agent chain, six guard configs   (API calls)
    wild         Experiment 2: the same checker on real agent mistakes                  (API calls)
    skeptic      Experiment 2b: a skeptical prompt and the clue judge                    (API calls)
    analyze      recompute every reported number from results/                          (no API calls)
    export-site  write the JSON the web explorer reads                                   (needs tau2-bench)

Every experiment accepts --dry-run (stub replies, no API calls) and writes to results/dry-run/ in that mode.
"""

from __future__ import annotations

import argparse
import logging

from blindspots import analysis, export
from blindspots.experiments import lab, skeptic, wild

COMMANDS = {
    "lab": (lab, "Experiment 1: planted faults and guard configurations"),
    "wild": (wild, "Experiment 2: real agent mistakes"),
    "skeptic": (skeptic, "Experiment 2b: skeptical prompt and clue judge"),
    "analyze": (analysis, "Recompute every reported number from results/"),
    "export-site": (export, "Write site/public/data/*.json for the web explorer"),
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="blindspots", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="show every call and retry")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, (module, help_text) in COMMANDS.items():
        module.add_arguments(
            sub.add_parser(
                name, help=help_text, description=module.__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
            )
        )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    for noisy in ("httpx", "httpcore", "anthropic", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    COMMANDS[args.command][0].run(args)


if __name__ == "__main__":
    main()
