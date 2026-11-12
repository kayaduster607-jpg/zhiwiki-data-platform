"""Export the real browser walkthrough as a compact MP4 with portable chapters."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def checked_path(value):
    """Reject dotenv components before reading an explicitly selected artifact."""
    path = Path(value)
    if any(part.lower().startswith(".env") for part in path.parts):
        raise ValueError("Environment paths are forbidden")
    resolved = path.resolve()
    if any(part.lower().startswith(".env") for part in resolved.parts):
        raise ValueError("Environment paths are forbidden")
    return resolved


def command(executable, arguments):
    result = subprocess.run([str(executable), *arguments], capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode:
        raise RuntimeError(result.stderr[-4000:])
    return result


def subtitle_time(seconds):
    milliseconds = max(0, round(seconds * 1000))
    hours, rest = divmod(milliseconds, 3600000)
    minutes, rest = divmod(rest, 60000)
    secs, fraction = divmod(rest, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{fraction:03}"


def write_subtitles(path, chapters, duration):
    blocks = []
    for index, chapter in enumerate(chapters):
        start = chapter["start_seconds"]
        end = min(duration, chapters[index + 1]["start_seconds"] - 0.05) if index + 1 < len(chapters) else duration
        if start >= duration:
            continue
        blocks.append(f"{len(blocks)+1}\n{subtitle_time(start)} --> {subtitle_time(end)}\n"
                      f"{chapter['title']}\n{chapter['description']}")
    path.write_bytes(("\n\n".join(blocks) + "\n").encode("utf-8"))


def recording_offset(ffmpeg, source, capture):
    """Align wall-clock chapter notes with the recorder's earlier first frame."""
    probe = command(ffmpeg, ["-hide_banner", "-i", str(source), "-t", "0", "-f", "null", "-"])
    match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", probe.stderr)
    if not match or "wall_total_seconds" not in capture:
        return 0.0
    duration = int(match[1]) * 3600 + int(match[2]) * 60 + float(match[3])
    offset = duration - capture["wall_total_seconds"]
    if not -1 <= offset <= 5:
        raise ValueError("Unexpected recording clock offset")
    return offset


def export(report, ffmpeg, output):
    capture = report["browser"]["video"]
    source = checked_path(capture["path"])
    if source.suffix != ".webm" or report["browser"]["uncaught_errors"]:
        raise ValueError("Expected a successful real-browser recording")
    if not report["restore"]["database_original_files_and_grants_restored"]:
        raise ValueError("Restore verification is incomplete")
    offset = recording_offset(ffmpeg, source, capture)
    chapters = [{**item, "start_seconds": round(max(0, item["start_seconds"] + offset), 3)} for item in capture["chapters"]]
    duration = capture["end_seconds"] + offset - 0.75  # Exclude the subsequent mobile-only check.
    if duration <= 1:
        raise ValueError("The desktop recording is incomplete")
    output.mkdir(parents=True, exist_ok=True)
    target = output / "zhizheng-workbench-demo.mp4"
    command(ffmpeg, ["-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-t", str(duration), "-map", "0:v:0", "-an", "-c:v", "libx264", "-preset", "fast",
        "-crf", "20", "-pix_fmt", "yuv420p", "-profile:v", "high", "-level:v", "4.0",
        "-r", "25", "-threads", "4", "-movflags", "+faststart", str(target)])
    # Decode every output frame, rather than treating file creation as validation.
    decoded = command(ffmpeg, ["-hide_banner", "-loglevel", "error", "-xerror", "-i", str(target),
        "-nostats", "-progress", "pipe:1", "-f", "null", "-"])
    frames = re.findall(r"^frame=(\d+)$", decoded.stdout, re.M)
    timestamps = re.findall(r"^out_time_us=(\d+)$", decoded.stdout, re.M)
    if not frames or not timestamps or "progress=end" not in decoded.stdout:
        raise ValueError("Full video decode did not finish")
    actual_duration = int(timestamps[-1]) / 1000000
    metadata = {"duration_seconds": actual_duration, "frame_count": int(frames[-1]),
        "width": 1600, "height": 900, "codec": "H.264", "audio": False,
        "synthetic_data": True, "real_local_api_and_worker": True,
        "credential_redaction": "opaque during token display; generated token subsequently revoked",
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(), "bytes": target.stat().st_size,
        "full_decode_verified": True, "timing_offset_seconds": round(offset, 3), "chapters": chapters}
    write_subtitles(output / "zhizheng-workbench-demo.srt", chapters, actual_duration)
    (output / "zhizheng-workbench-demo.json").write_bytes((json.dumps(metadata, ensure_ascii=False, indent=2)+"\n").encode("utf-8"))
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True)
    parser.add_argument("--ffmpeg", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    report = json.loads(checked_path(args.report).read_text(encoding="utf-8"))
    result = export(report, checked_path(args.ffmpeg), checked_path(args.output))
    print(json.dumps({key: value for key, value in result.items() if key != "chapters"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
