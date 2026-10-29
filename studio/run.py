#!/usr/bin/env python3
"""SpeakPower Studio -- turn one recording into publishable assets.

This is what the GitHub Action runs. You do not type this command yourself:
you fill in the form on the Actions tab and GitHub runs it for you.

It can also be run directly, on any machine that has Python and ffmpeg:

    python3 run.py --source "https://drive.google.com/file/d/..." \
                   --context "Interview with a church media director" \
                   --out ./outputs
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from core import analyse, config, jobs, pipeline


def summarise(state: dict, destination: Path) -> None:
    """Print what was produced, and leave the same thing as a readable file.

    The Actions log scrolls away; a summary file travels with the download.
    """
    outputs = state.get("outputs", {})
    shorts = outputs.get("shorts", [])

    lines: list[str] = []
    title = state.get("episode_title") or "Untitled"
    lines.append(f"# {title}")
    lines.append("")
    if state.get("duration_minutes"):
        lines.append(f"Source length: {state['duration_minutes']} minutes")
    stats = outputs.get("episode_stats") or {}
    if stats.get("removed_minutes") is not None:
        lines.append(
            f"Dead air removed: {stats['removed_minutes']} minutes "
            f"({stats.get('silences', 0)} silences)"
        )
    lines.append("")

    if state.get("editorial_note"):
        lines += ["## Editor's note", "", state["editorial_note"], ""]

    lines += [f"## Shorts ({len(shorts)})", ""]
    for index, short in enumerate(shorts, start=1):
        lines.append(f"**{index}. {short['title']}** — {short['seconds']}s, "
                     f"from {short['source_start']}")
        if short.get("hook"):
            lines.append(f"> {short['hook']}")
        if short.get("why"):
            lines.append(f"_{short['why']}_")
        lines.append("")

    (destination / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")

    print("\n" + "=" * 58)
    print(f"  {title}")
    print("=" * 58)
    print(f"  {len(shorts)} shorts")
    if outputs.get("episode"):
        print(f"  1 cleaned episode: {outputs['episode']}")
    print(f"  {len(outputs.get('text', []))} text files")
    print(f"\n  Everything is in: {destination}")
    print("=" * 58)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True,
                        help="a shareable link, or a path to a local file")
    parser.add_argument("--context", default="",
                        help="what the recording is, and who it is for")
    parser.add_argument("--style", choices=("blur", "crop"), default="blur",
                        help="vertical framing for the shorts")
    parser.add_argument("--clips", type=int, default=None,
                        help="how many shorts to aim for")
    parser.add_argument("--out", type=Path, default=Path("outputs"),
                        help="where to put the finished assets")
    parser.add_argument("--skip-episode", action="store_true",
                        help="skip the cleaned long edit (much faster)")
    parser.add_argument("--mode", choices=("auto", "transcribe", "cut"),
                        default="auto",
                        help="auto: Claude chooses the moments (needs API "
                             "credit). transcribe: get the words out and stop, "
                             "free. cut: render a clip list you supply, free.")
    parser.add_argument("--clips-text", default="",
                        help="a clip list, one 'start end title' per line. "
                             "Implies --mode cut.")
    parser.add_argument("--clips-file", type=Path, default=None,
                        help="read the clip list from a file instead")
    arguments = parser.parse_args()

    if arguments.clips:
        config.TARGET_CLIP_COUNT = max(1, min(arguments.clips, 20))

    clips_text = arguments.clips_text or ""
    if arguments.clips_file:
        if not arguments.clips_file.is_file():
            print(f"No such clips file: {arguments.clips_file}", file=sys.stderr)
            return 2
        clips_text = arguments.clips_file.read_text(encoding="utf-8")

    mode = arguments.mode
    # Supplying a list is an unambiguous request to use it.
    if clips_text.strip() and mode == "auto":
        mode = "cut"
    if mode == "cut" and not clips_text.strip():
        print("--mode cut needs a clip list (--clips-text or --clips-file).",
              file=sys.stderr)
        return 2

    # Only the "auto" path spends anything, so it alone needs the key.
    try:
        config.validate() if mode == "auto" else config.validate_basics()
    except config.ConfigError as error:
        print(f"Configuration problem: {error}", file=sys.stderr)
        return 2

    source = arguments.source.strip()
    source_kind = "link" if source.lower().startswith(("http://", "https://")) else "upload"
    if source_kind == "upload" and not Path(source).is_file():
        print(f"No such file: {source}", file=sys.stderr)
        return 2

    job_id = jobs.new_job_id()
    jobs.create(job_id, source, source_kind)
    print(f"Studio job {job_id}")
    print(f"Source: {source[:120]}")
    print(f"Mode: {mode}")
    print(f"Transcription: {config.transcription_backend()}")
    if mode == "auto":
        print(f"Editor model: {config.ANALYSIS_MODEL} (this spends API credit)")
        # Check the API will answer before transcribing. A key with no credit
        # passes every local check, so without this the run would transcribe
        # for half an hour and only then discover it cannot pay.
        print("Checking the API can be reached before starting...")
        try:
            analyse.preflight()
        except analyse.AnalysisError as error:
            print(f"\nCannot run in 'auto' mode:\n\n{error}\n", file=sys.stderr)
            return 1
        print("  API reachable.")
    else:
        print("Editor model: none -- this run costs nothing in API credit")

    pipeline.run(
        job_id, source, source_kind,
        context=arguments.context,
        style=arguments.style,
        skip_episode=arguments.skip_episode or mode == "transcribe",
        mode=mode,
        clips_text=clips_text,
    )

    state = jobs.read(job_id) or {}

    # Collect whatever was produced BEFORE deciding success or failure. A run
    # that dies while choosing the moments has already spent half an hour
    # transcribing, and that transcript is exactly what the free workflow
    # needs; throwing it away because a later stage failed wastes the most
    # expensive thing in the job.
    arguments.out.mkdir(parents=True, exist_ok=True)
    produced = jobs.job_dir(job_id) / "outputs"
    salvaged = 0
    if produced.is_dir():
        for item in produced.iterdir():
            if item.is_file():
                shutil.copy2(item, arguments.out / item.name)
                salvaged += 1

    if state.get("status") != "done":
        print(f"\nFAILED: {state.get('error') or 'unknown error'}", file=sys.stderr)
        if salvaged:
            print(
                f"\n{salvaged} file(s) were produced before the failure and "
                f"are in the artifact anyway:",
                file=sys.stderr,
            )
            for item in sorted(arguments.out.iterdir()):
                print(f"  {item.name}", file=sys.stderr)
            if (arguments.out / "transcript.txt").is_file():
                print(
                    "\nThe transcript survived. You can use it with Mode "
                    "'cut' without transcribing again.",
                    file=sys.stderr,
                )
        return 1

    (arguments.out / "analysis.json").write_text(
        json.dumps(state.get("outputs", {}), indent=1), encoding="utf-8"
    )

    summarise(state, arguments.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
