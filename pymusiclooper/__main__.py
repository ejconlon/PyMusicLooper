#!/usr/bin/python3
# coding=utf-8
""" PyMusicLooper
    Copyright (C) 2020  Hazem Nabil

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>."""

import argparse
import logging
import os
import sys
import warnings
from multiprocessing import Process

from tqdm import tqdm

from .core import MusicLooper


def loop_track(filename, min_duration_multiplier):
    try:
        # Load the file
        logging.info("Loading {}...".format(filename))

        track = MusicLooper(filename, min_duration_multiplier)

        loop_pair_list = track.find_loop_pairs()

        if len(loop_pair_list) == 0:
            logging.error(f"No suitable loop point found for '{filename}'.")
            sys.exit(1)

        loop_start = loop_pair_list[0]["loop_start"]
        loop_end = loop_pair_list[0]["loop_end"]
        score = loop_pair_list[0]["score"]

        print(
            "Playing with loop from {} back to {}; similarity: {:.1%}".format(
                track.frames_to_ftime(loop_end),
                track.frames_to_ftime(loop_start),
                score if score is not None else 0,
            )
        )
        print("(press Ctrl+C to exit)")

        track.play_looping(loop_start, loop_end)

    except (TypeError, FileNotFoundError) as e:
        logging.error("Error: {}".format(e))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="python -m pymusiclooper",
        description="A script for repeating music seamlessly and endlessly, by automatically finding the best loop points.",
    )
    parser.add_argument("path", type=str, help="path to music file.")

    play_options = parser.add_argument_group("Play")
    export_options = parser.add_argument_group("Export")
    parameter_options = parser.add_argument_group("Parameter adjustment")

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="enable verbose logging output",
    )

    play_options.add_argument(
        "-p",
        "--play",
        action="store_true",
        default=True,
        help="play the song on repeat with the best discovered loop point (default).",
    )
    export_options.add_argument(
        "-e",
        "--export",
        action="store_true",
        default=False,
        help="export the song into intro, loop and outro files (WAV format).",
    )
    export_options.add_argument(
        "-j",
        "--json",
        action="store_true",
        default=False,
        help="export the loop points (in samples) to a JSON file in the song's directory.",
    )
    export_options.add_argument(
        "-b",
        "--batch",
        action="store_true",
        default=False,
        help="batch process all the files within the given path (usage with export args [-e] or [-j] only).",
    )
    export_options.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        default=False,
        help="process directories and their contents recursively (usage with [-b/--batch] only).",
    )
    parameter_options.add_argument(
        "-o",
        "--output-dir",
        type=str,
        default=os.path.join(os.getcwd(), "looper_output"),
        help="specify a different output directory.",
    )

    def bounded_float(x):
        try:
            x = float(x)
        except ValueError:
            raise argparse.ArgumentTypeError("%r not a floating-point literal" % (x,))

        if x <= 0.0 or x >= 1.0:
            raise argparse.ArgumentTypeError(
                "%r not in range (0.0, 1.0) exclusive" % (x,)
            )
        return x

    parameter_options.add_argument(
        "-m",
        "--min-duration-multiplier",
        type=bounded_float,
        default=0.35,
        help="specify minimum loop duration as a multiplier of song duration (default: 0.35)",
    )

    args = parser.parse_args()

    if args.batch and not args.verbose:
        warnings.filterwarnings("ignore")
        logging.basicConfig(level=logging.ERROR)
    elif args.verbose:
        warnings.filterwarnings("ignore")
        logging.basicConfig(level=logging.ERROR)
    else:
        logging.basicConfig(level=logging.INFO)

    output_dir = args.output_dir

    def export_handler(file_path):
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)

        output_path = os.path.join(output_dir, os.path.split(file_path)[1])

        try:
            track = MusicLooper(file_path, args.min_duration_multiplier)
        except TypeError as e:
            logging.error(f"Skipping '{file_path}'. {e}")
            return

        logging.info("Loaded '{}'".format(file_path))

        loop_pair_list = track.find_loop_pairs()
        if len(loop_pair_list) == 0:
            logging.error(f"No suitable loop point found for '{file_path}'.")
            return
        loop_start = loop_pair_list[0]["loop_start"]
        loop_end = loop_pair_list[0]["loop_end"]
        score = loop_pair_list[0]["score"]

        if args.json:
            track.export_json(loop_start, loop_end, score, output_dir=output_dir)
            logging.info(
                f"Successfully exported loop points to '{output_path}.loop_points.json'"
            )
        if args.export:
            track.export(loop_start, loop_end, output_dir=output_dir)
            logging.info(
                f"Successfully exported intro/loop/outro sections to '{output_dir}'"
            )
        logging.info("")

    if args.batch:
        if not args.export or not args.json:
            raise parser.error("Export mode not specified. -e or -j required.")

        if args.recursive:
            files = []
            for directory, sub_dir_list, file_list in os.walk(args.path):
                for filename in file_list:
                    files.append(os.path.join(directory, filename))
        else:
            files = [
                f
                for f in os.listdir(args.path)
                if os.path.isfile(os.path.join(args.path, f))
            ]

        if len(files) == 0:
            logging.error(f"No files found in '{args.path}'")

        affinity = len(os.sched_getaffinity(0))

        processes = []
        i = 0
        num_files = len(files)

        with tqdm(total=num_files) as pbar:
            while i < num_files:
                for pid in range(affinity):
                    p = Process(
                        target=export_handler, args=(files[i]), daemon=True
                    )
                    processes.append(p)
                    p.start()
                    i += 1
                    if i >= num_files:
                        break
                for process in processes:
                    process.join()
                    pbar.update()

                processes = []

        sys.exit(0)

    if args.export or args.json:
        export_handler(args.path)

    if args.play and not (args.export or args.json or args.batch):
        loop_track(args.path, args.min_duration_multiplier)
