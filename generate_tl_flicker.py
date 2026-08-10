#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import os
import random
from collections import deque
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from PIL import Image


WORKER_CONTEXT: dict[str, object] = {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate flickering TL tube frames from a base image and mask."
    )
    parser.add_argument("--base", type=Path, default=Path("kuleuven-punk.png"))
    parser.add_argument("--mask", type=Path, default=Path("kuleuven-punk-tl.png"))
    parser.add_argument(
        "--neon-mask", type=Path, default=Path("kuleuven-punk-neon-border.png")
    )
    parser.add_argument(
        "--logo-mask", type=Path, default=Path("kuleuven-punk-neon-logo.png")
    )
    parser.add_argument("--output-dir", type=Path, default=Path("frames"))
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--jobs", type=int, default=(os.cpu_count() or 1))
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--threshold", type=int, default=16)
    parser.add_argument("--change-probability", type=float, default=0.45)
    parser.add_argument("--max-flicker-frames", type=int, default=8)
    parser.add_argument("--feather-margin", type=int, default=3)
    parser.add_argument("--neon-threshold", type=int, default=0)
    parser.add_argument("--neon-alpha-threshold", type=int, default=1)
    parser.add_argument("--neon-feather-margin", type=int, default=6)
    parser.add_argument("--neon-period", type=float, default=35.0)
    parser.add_argument("--neon-min-scale", type=float, default=0.55)
    parser.add_argument("--neon-max-scale", type=float, default=1.6)
    parser.add_argument("--logo-threshold", type=int, default=0)
    parser.add_argument("--logo-alpha-threshold", type=int, default=1)
    parser.add_argument("--logo-feather-margin", type=int, default=6)
    parser.add_argument("--logo-flicker-probability", type=float, default=0.02)
    parser.add_argument("--logo-min-flicker-frames", type=int, default=2)
    parser.add_argument("--logo-max-flicker-frames", type=int, default=9)
    parser.add_argument("--logo-flicker-on-probability", type=float, default=0.25)
    return parser.parse_args()


def connected_components(mask: list[list[bool]]) -> tuple[list[list[int]], int]:
    height = len(mask)
    width = len(mask[0]) if height else 0
    labels = [[0 for _ in range(width)] for _ in range(height)]
    current_label = 0

    for y in range(height):
        for x in range(width):
            if not mask[y][x] or labels[y][x] != 0:
                continue

            current_label += 1
            queue: deque[tuple[int, int]] = deque()
            queue.append((y, x))
            labels[y][x] = current_label

            while queue:
                cy, cx = queue.popleft()
                for ny, nx in (
                    (cy - 1, cx),
                    (cy + 1, cx),
                    (cy, cx - 1),
                    (cy, cx + 1),
                ):
                    if ny < 0 or nx < 0 or ny >= height or nx >= width:
                        continue
                    if not mask[ny][nx] or labels[ny][nx] != 0:
                        continue
                    labels[ny][nx] = current_label
                    queue.append((ny, nx))

    return labels, current_label


def random_flicker_level() -> float:
    roll = random.random()
    if roll < 0.45:
        return 0.15
    if roll < 0.75:
        return 0.3
    return 0.65


def compute_feather_weights(mask: list[list[bool]], margin: int) -> list[list[float]]:
    height = len(mask)
    width = len(mask[0]) if height else 0
    if margin <= 0:
        return [[1.0 if mask[y][x] else 0.0 for x in range(width)] for y in range(height)]

    inf = 10**9
    distances = [[inf for _ in range(width)] for _ in range(height)]
    queue: deque[tuple[int, int]] = deque()

    for y in range(height):
        for x in range(width):
            if not mask[y][x]:
                continue
            for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
                if ny < 0 or nx < 0 or ny >= height or nx >= width or not mask[ny][nx]:
                    distances[y][x] = 1
                    queue.append((y, x))
                    break

    while queue:
        cy, cx = queue.popleft()
        nd = distances[cy][cx] + 1
        for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
            if ny < 0 or nx < 0 or ny >= height or nx >= width:
                continue
            if not mask[ny][nx] or distances[ny][nx] <= nd:
                continue
            distances[ny][nx] = nd
            queue.append((ny, nx))

    weights = [[0.0 for _ in range(width)] for _ in range(height)]
    for y in range(height):
        for x in range(width):
            if not mask[y][x]:
                continue
            weights[y][x] = min(distances[y][x] / float(margin), 1.0)

    return weights


def compute_outward_feather_groups(
    labels: list[list[int]], group_count: int, margin: int
) -> list[list[tuple[int, int, float]]]:
    height = len(labels)
    width = len(labels[0]) if height else 0
    groups: list[list[tuple[int, int, float]]] = [[] for _ in range(group_count)]

    for y in range(height):
        for x in range(width):
            label = labels[y][x]
            if label > 0:
                groups[label - 1].append((x, y, 1.0))

    if margin <= 0 or group_count == 0:
        return groups

    inf = 10**9
    distances = [[inf for _ in range(width)] for _ in range(height)]
    owners = [[0 for _ in range(width)] for _ in range(height)]
    queue: deque[tuple[int, int]] = deque()

    for y in range(height):
        for x in range(width):
            label = labels[y][x]
            if label > 0:
                distances[y][x] = 0
                owners[y][x] = label
                queue.append((y, x))

    while queue:
        cy, cx = queue.popleft()
        current_distance = distances[cy][cx]
        if current_distance >= margin:
            continue

        owner = owners[cy][cx]
        nd = current_distance + 1

        for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
            if ny < 0 or nx < 0 or ny >= height or nx >= width:
                continue
            if labels[ny][nx] > 0 or distances[ny][nx] <= nd:
                continue
            distances[ny][nx] = nd
            owners[ny][nx] = owner
            queue.append((ny, nx))

    for y in range(height):
        for x in range(width):
            if labels[y][x] > 0:
                continue
            distance = distances[y][x]
            owner = owners[y][x]
            if owner <= 0 or distance <= 0 or distance > margin:
                continue
            weight = max(0.0, 1.0 - (distance / float(margin + 1)))
            if weight > 0.0:
                groups[owner - 1].append((x, y, weight))

    return groups


def print_progress(current: int, total: int, width: int = 40) -> None:
    filled = int(width * current / total)
    bar = "#" * filled + "-" * (width - filled)
    percent = (100.0 * current) / total
    print(f"\rGenerating frames [{bar}] {current}/{total} ({percent:5.1f}%)", end="", flush=True)


def init_worker(context: dict[str, object]) -> None:
    global WORKER_CONTEXT
    WORKER_CONTEXT = context


def render_frame(frame: int) -> int:
    width = WORKER_CONTEXT["width"]
    height = WORKER_CONTEXT["height"]
    base_data = WORKER_CONTEXT["base_data"]
    output_dir = WORKER_CONTEXT["output_dir"]
    tube_effect_pixels = WORKER_CONTEXT["tube_effect_pixels"]
    tube_levels = WORKER_CONTEXT["tube_levels"]
    neon_effect_pixels = WORKER_CONTEXT["neon_effect_pixels"]
    neon_phases = WORKER_CONTEXT["neon_phases"]
    neon_speed_jitter = WORKER_CONTEXT["neon_speed_jitter"]
    neon_amplitude_jitter = WORKER_CONTEXT["neon_amplitude_jitter"]
    neon_period = WORKER_CONTEXT["neon_period"]
    neon_min_scale = WORKER_CONTEXT["neon_min_scale"]
    neon_max_scale = WORKER_CONTEXT["neon_max_scale"]
    logo_effect_pixels = WORKER_CONTEXT["logo_effect_pixels"]
    logo_levels = WORKER_CONTEXT["logo_levels"]

    frame_image = Image.new("RGBA", (width, height))
    frame_image.putdata(base_data)
    frame_pixels = frame_image.load()
    frame_levels = tube_levels[frame]

    for i, pixels in enumerate(tube_effect_pixels):
        level = frame_levels[i]
        for x, y, weight in pixels:
            effective_level = 1.0 - ((1.0 - level) * weight)
            red, green, blue, alpha = frame_pixels[x, y]
            frame_pixels[x, y] = (
                int(red * effective_level),
                int(green * effective_level),
                int(blue * effective_level),
                alpha,
            )

    logo_level = logo_levels[frame]
    if logo_effect_pixels and logo_level < 1.0:
        for x, y, weight in logo_effect_pixels:
            effective_level = 1.0 - ((1.0 - logo_level) * weight)
            red, green, blue, alpha = frame_pixels[x, y]
            frame_pixels[x, y] = (
                int(red * effective_level),
                int(green * effective_level),
                int(blue * effective_level),
                alpha,
            )

    neon_group_count = len(neon_effect_pixels)
    if neon_group_count > 0:
        for i, pixels in enumerate(neon_effect_pixels):
            phase = neon_phases[i]
            speed = neon_speed_jitter[i]
            amplitude = neon_amplitude_jitter[i]
            cycle = ((frame / neon_period) * speed * (2.0 * math.pi)) + phase
            pulse = (math.sin(cycle) + 1.0) * 0.5
            group_scale = neon_min_scale + ((neon_max_scale - neon_min_scale) * pulse * amplitude)

            for x, y, weight in pixels:
                effective_scale = 1.0 + ((group_scale - 1.0) * weight)
                red, green, blue, alpha = frame_pixels[x, y]
                frame_pixels[x, y] = (
                    max(0, min(255, int(red * effective_scale))),
                    max(0, min(255, int(green * effective_scale))),
                    max(0, min(255, int(blue * effective_scale))),
                    alpha,
                )

    output_path = Path(output_dir) / f"frame_{frame:04d}.png"
    frame_image.save(output_path)
    return frame


def main() -> None:
    args = parse_args()
    if args.count <= 0:
        raise ValueError("--count must be greater than zero")
    if args.jobs <= 0:
        raise ValueError("--jobs must be greater than zero")
    if args.max_flicker_frames <= 0 or args.max_flicker_frames >= 10:
        raise ValueError("--max-flicker-frames must be between 1 and 9")
    if args.feather_margin < 0:
        raise ValueError("--feather-margin must be zero or greater")
    if args.neon_feather_margin < 0:
        raise ValueError("--neon-feather-margin must be zero or greater")
    if args.logo_feather_margin < 0:
        raise ValueError("--logo-feather-margin must be zero or greater")
    if args.neon_threshold < 0 or args.neon_threshold > 255:
        raise ValueError("--neon-threshold must be between 0 and 255")
    if args.neon_alpha_threshold < 0 or args.neon_alpha_threshold > 255:
        raise ValueError("--neon-alpha-threshold must be between 0 and 255")
    if args.logo_threshold < 0 or args.logo_threshold > 255:
        raise ValueError("--logo-threshold must be between 0 and 255")
    if args.logo_alpha_threshold < 0 or args.logo_alpha_threshold > 255:
        raise ValueError("--logo-alpha-threshold must be between 0 and 255")
    if args.neon_period <= 0:
        raise ValueError("--neon-period must be greater than zero")
    if args.neon_min_scale <= 0 or args.neon_max_scale <= 0:
        raise ValueError("--neon-min-scale and --neon-max-scale must be greater than zero")
    if args.neon_min_scale > args.neon_max_scale:
        raise ValueError("--neon-min-scale must be less than or equal to --neon-max-scale")
    if args.logo_flicker_probability < 0.0 or args.logo_flicker_probability > 1.0:
        raise ValueError("--logo-flicker-probability must be between 0 and 1")
    if args.logo_flicker_on_probability < 0.0 or args.logo_flicker_on_probability > 1.0:
        raise ValueError("--logo-flicker-on-probability must be between 0 and 1")
    if args.logo_min_flicker_frames <= 0:
        raise ValueError("--logo-min-flicker-frames must be greater than zero")
    if args.logo_max_flicker_frames < args.logo_min_flicker_frames:
        raise ValueError(
            "--logo-max-flicker-frames must be greater than or equal to --logo-min-flicker-frames"
        )

    if args.seed is not None:
        random.seed(args.seed)

    base_image = Image.open(args.base).convert("RGBA")
    mask_image = Image.open(args.mask).convert("L")
    neon_mask_image = Image.open(args.neon_mask).convert("RGBA")
    logo_mask_image = Image.open(args.logo_mask).convert("RGBA")

    if (
        base_image.size != mask_image.size
        or base_image.size != neon_mask_image.size
        or base_image.size != logo_mask_image.size
    ):
        raise ValueError(
            "Base image, TL mask, neon mask, and logo mask must have exactly the same dimensions"
        )

    width, height = base_image.size
    base_pixels = base_image.load()
    mask_pixels = mask_image.load()
    neon_mask_pixels = neon_mask_image.load()
    logo_mask_pixels = logo_mask_image.load()

    mask_binary = [
        [mask_pixels[x, y] >= args.threshold for x in range(width)] for y in range(height)
    ]
    labels, tube_count = connected_components(mask_binary)
    tube_effect_pixels = compute_outward_feather_groups(
        labels, tube_count, args.feather_margin
    )

    neon_mask_binary = []
    for y in range(height):
        row: list[bool] = []
        for x in range(width):
            red, green, blue, alpha = neon_mask_pixels[x, y]
            luminance = int((0.299 * red) + (0.587 * green) + (0.114 * blue))
            row.append(
                luminance >= args.neon_threshold and alpha >= args.neon_alpha_threshold
            )
        neon_mask_binary.append(row)
    neon_labels, neon_group_count = connected_components(neon_mask_binary)
    neon_effect_pixels = compute_outward_feather_groups(
        neon_labels, neon_group_count, args.neon_feather_margin
    )

    logo_mask_binary = []
    for y in range(height):
        row: list[bool] = []
        for x in range(width):
            red, green, blue, alpha = logo_mask_pixels[x, y]
            luminance = int((0.299 * red) + (0.587 * green) + (0.114 * blue))
            row.append(
                luminance >= args.logo_threshold and alpha >= args.logo_alpha_threshold
            )
        logo_mask_binary.append(row)
    logo_labels, logo_group_count = connected_components(logo_mask_binary)
    logo_group_effects = compute_outward_feather_groups(
        logo_labels, logo_group_count, args.logo_feather_margin
    )
    logo_effect_pixels = [pixel for group in logo_group_effects for pixel in group]

    if tube_count == 0:
        raise ValueError("No TL tube pixels found in mask with the selected threshold")

    neon_phases = [random.random() * (2.0 * math.pi) for _ in range(neon_group_count)]
    neon_speed_jitter = [random.uniform(0.95, 1.15) for _ in range(neon_group_count)]
    neon_amplitude_jitter = [random.uniform(0.99, 1.0) for _ in range(neon_group_count)]

    levels = [1.0] * tube_count
    flicker_remaining = [0] * tube_count
    needs_bright_frame = [False] * tube_count
    active_tube: int | None = None
    args.output_dir.mkdir(parents=True, exist_ok=True)

    tube_levels: list[list[float]] = []
    for _ in range(args.count):
        frame_levels = [1.0] * tube_count
        if active_tube is not None and flicker_remaining[active_tube] > 0:
            levels[active_tube] = random_flicker_level()
            flicker_remaining[active_tube] -= 1
            if flicker_remaining[active_tube] == 0:
                needs_bright_frame[active_tube] = True
        elif active_tube is not None and needs_bright_frame[active_tube]:
            levels[active_tube] = 1.0
            needs_bright_frame[active_tube] = False
            active_tube = None
        else:
            active_tube = None
            if random.random() < args.change_probability:
                active_tube = random.randrange(tube_count)
                flicker_remaining[active_tube] = random.randint(1, args.max_flicker_frames)
                levels[active_tube] = random_flicker_level()
                flicker_remaining[active_tube] -= 1
                if flicker_remaining[active_tube] == 0:
                    needs_bright_frame[active_tube] = True

        for i in range(tube_count):
            if i != active_tube:
                levels[i] = 1.0
                flicker_remaining[i] = 0
                needs_bright_frame[i] = False
            frame_levels[i] = levels[i]
        tube_levels.append(frame_levels)

    logo_levels: list[float] = []
    logo_flicker_remaining = 0
    logo_needs_bright_frame = False
    for _ in range(args.count):
        logo_level = 1.0
        if logo_flicker_remaining > 0:
            logo_level = 1.0 if random.random() < args.logo_flicker_on_probability else 0.0
            logo_flicker_remaining -= 1
            if logo_flicker_remaining == 0:
                logo_needs_bright_frame = True
        else:
            if logo_needs_bright_frame:
                logo_level = 1.0
                logo_needs_bright_frame = False
            elif random.random() < args.logo_flicker_probability:
                logo_flicker_remaining = random.randint(
                    args.logo_min_flicker_frames, args.logo_max_flicker_frames
                )
                logo_level = 0.0
                logo_flicker_remaining -= 1
                if logo_flicker_remaining == 0:
                    logo_needs_bright_frame = True
        logo_levels.append(logo_level)

    worker_context: dict[str, object] = {
        "width": width,
        "height": height,
        "base_data": [base_pixels[x, y] for y in range(height) for x in range(width)],
        "output_dir": str(args.output_dir),
        "tube_effect_pixels": tube_effect_pixels,
        "tube_levels": tube_levels,
        "neon_effect_pixels": neon_effect_pixels,
        "neon_phases": neon_phases,
        "neon_speed_jitter": neon_speed_jitter,
        "neon_amplitude_jitter": neon_amplitude_jitter,
        "neon_period": args.neon_period,
        "neon_min_scale": args.neon_min_scale,
        "neon_max_scale": args.neon_max_scale,
        "logo_effect_pixels": logo_effect_pixels,
        "logo_levels": logo_levels,
    }

    if args.jobs == 1:
        init_worker(worker_context)
        for frame in range(args.count):
            render_frame(frame)
            print_progress(frame + 1, args.count)
    else:
        completed = 0
        with ProcessPoolExecutor(max_workers=args.jobs, initializer=init_worker, initargs=(worker_context,)) as executor:
            futures = [executor.submit(render_frame, frame) for frame in range(args.count)]
            for _ in as_completed(futures):
                completed += 1
                print_progress(completed, args.count)

    print()


if __name__ == "__main__":
    main()
