import argparse
import asyncio
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from PIL import Image
from playwright.async_api import async_playwright


# Default capture settings.
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720
SCROLL_STEP = 5
CAPTURE_DELAY_MS = 100
FRAME_DURATION_MS = 33
MAX_FRAMES = 1000
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
SCALE_OPTIONS = (1, 0.85, 0.7, 0.55, 0.4, 0.25)
COLOR_OPTIONS = (256, 128, 64, 32)


@dataclass(frozen=True)
class EncodingSettings:
    frame_count: int
    colors: int
    scale: float
    frame_duration: int


def build_scroll_positions(
    max_scroll: int,
    step: int,
    max_frames: int,
) -> list[int]:
    """Return evenly distributed scroll positions including both endpoints."""
    positions = list(range(0, max_scroll + 1, step))
    if not positions or positions[-1] != max_scroll:
        positions.append(max_scroll)

    if len(positions) <= max_frames:
        return positions
    if max_frames == 1:
        return [0]

    indices = [
        round(i * (len(positions) - 1) / (max_frames - 1))
        for i in range(max_frames)
    ]
    limited_positions = [positions[index] for index in indices]
    limited_positions[-1] = max_scroll
    return limited_positions


def save_gif_candidate(
    frames: Sequence[Image.Image],
    colors: int,
    scale: float,
    duration: int,
    output_path: Path,
) -> None:
    """Encode one GIF candidate using a shared palette and optimization."""
    candidate_frames = list(frames)
    if scale != 1:
        width = round(candidate_frames[0].width * scale)
        height = round(candidate_frames[0].height * scale)
        candidate_frames = [
            frame.resize((width, height), Image.Resampling.LANCZOS)
            for frame in candidate_frames
        ]

    palette = candidate_frames[0].quantize(
        colors=colors,
        method=Image.Quantize.MEDIANCUT,
    )
    gif_frames = [
        frame.quantize(
            palette=palette,
            dither=Image.Dither.NONE,
        )
        for frame in candidate_frames
    ]
    gif_frames[0].save(
        output_path,
        format="GIF",
        save_all=True,
        append_images=gif_frames[1:],
        duration=duration,
        loop=0,
        optimize=True,
        disposal=2,
    )


def encode_gif_under_size_limit(
    frames: Sequence[Image.Image],
    output_path: Path,
    frame_duration: int,
    max_file_size: int,
) -> EncodingSettings:
    """Choose the highest-quality candidate that fits within the size limit."""
    temporary_path = output_path.with_name(
        f".{output_path.stem}.tmp{output_path.suffix}"
    )

    try:
        for scale in SCALE_OPTIONS:
            stride = 1
            while stride <= len(frames):
                sampled_frames = list(frames[::stride])
                if sampled_frames[-1] is not frames[-1]:
                    sampled_frames.append(frames[-1])

                for colors in COLOR_OPTIONS:
                    save_gif_candidate(
                        sampled_frames,
                        colors,
                        scale,
                        frame_duration * stride,
                        temporary_path,
                    )
                    if temporary_path.stat().st_size <= max_file_size:
                        temporary_path.replace(output_path)
                        return EncodingSettings(
                            frame_count=len(sampled_frames),
                            colors=colors,
                            scale=scale,
                            frame_duration=frame_duration * stride,
                        )
                stride *= 2
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

    raise RuntimeError(
        f"Unable to create a GIF under {max_file_size} bytes."
    )


async def capture_scroll_gif(
    url: str,
    output: str,
    step: int,
    delay_ms: int,
    frame_duration: int,
    max_frames: int,
    max_file_size: int,
):
    frames = []

    print("\n========== CAPTURE SETTINGS ==========")
    print(f"URL: {url}")
    print(f"Viewport: {VIEWPORT_WIDTH}x{VIEWPORT_HEIGHT}")
    print(f"Scroll step: {step}px")
    print(f"Capture delay: {delay_ms}ms")
    print(f"GIF frame duration: {frame_duration}ms")
    print(f"Playback speed: {1000 / frame_duration:.1f} FPS")
    print(f"Maximum frames per direction: {max_frames}")
    print("======================================\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        page = await browser.new_page(
            viewport={
                "width": VIEWPORT_WIDTH,
                "height": VIEWPORT_HEIGHT,
            },
            device_scale_factor=1,
        )

        try:
            print(f"Opening {url}...")

            await page.goto(
                url,
                wait_until="networkidle",
                timeout=60000,
            )

            await page.evaluate("document.fonts.ready")
            await page.wait_for_timeout(1000)

            # Determine the page's scrollable height.
            dimensions = await page.evaluate("""
                () => ({
                    height: Math.max(
                        document.documentElement.scrollHeight,
                        document.body.scrollHeight
                    ),
                    viewport: window.innerHeight
                })
            """)

            max_scroll = max(
                0,
                dimensions["height"] - dimensions["viewport"],
            )

            positions = build_scroll_positions(
                max_scroll,
                step,
                max_frames,
            )

            print(f"Page height: {dimensions['height']}px")
            print(f"Frames per direction: {len(positions)}")
            print("Capturing frames...\n")

            async def capture_at(y):
                await page.evaluate(
                    "(y) => window.scrollTo(0, y)",
                    y,
                )

                await page.wait_for_timeout(delay_ms)

                screenshot = await page.screenshot(
                    full_page=False,
                    animations="disabled",
                    type="png",
                )

                return Image.open(
                    io.BytesIO(screenshot)
                ).convert("RGB")

            # Capture the downward scroll.
            for i, y in enumerate(positions):
                frames.append(await capture_at(y))

                if (i + 1) % 25 == 0 or i == len(positions) - 1:
                    print(
                        f"Scrolling down: "
                        f"{i + 1}/{len(positions)}"
                    )

            # Capture the upward scroll, avoiding duplicate endpoints.
            reverse_positions = list(reversed(positions[1:-1]))

            for i, y in enumerate(reverse_positions):
                frames.append(await capture_at(y))

                if (i + 1) % 25 == 0 or i == len(reverse_positions) - 1:
                    print(
                        f"Scrolling up: "
                        f"{i + 1}/{len(reverse_positions)}"
                    )

        finally:
            await browser.close()

    if not frames:
        raise RuntimeError("No frames were captured.")

    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("\nEncoding GIF (maximum size: "
          f"{max_file_size / (1024 * 1024):.1f} MB)...")

    selected_settings = encode_gif_under_size_limit(
        frames,
        output_path,
        frame_duration,
        max_file_size,
    )

    # Read the saved GIF back to verify its actual timing.
    with Image.open(output_path) as saved_gif:
        saved_frame_count = saved_gif.n_frames
        saved_duration = saved_gif.info.get("duration", "unknown")

    print("\n========== GIF SAVED ==========")
    print(f"File: {output_path}")
    print(f"Total frames: {saved_frame_count}")
    print(f"Frame duration: {saved_duration}ms")
    print(f"File size: {output_path.stat().st_size / (1024 * 1024):.2f} MB")
    print(f"Encoding settings: {selected_settings}")
    print("Loop: infinite")
    print("===============================\n")


def main():
    parser = argparse.ArgumentParser(
        description="Create a smooth, looping web page scroll GIF."
    )

    parser.add_argument(
        "url",
        help="Target web app URL",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="scroll.gif",
        help="Output filename",
    )
    parser.add_argument(
        "--step",
        type=int,
        default=SCROLL_STEP,
        help=f"Scroll increment in pixels (default: {SCROLL_STEP})",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=CAPTURE_DELAY_MS,
        help=f"Capture delay in milliseconds (default: {CAPTURE_DELAY_MS})",
    )
    parser.add_argument(
        "--frame-duration",
        type=int,
        default=FRAME_DURATION_MS,
        help=(
            "GIF playback duration per frame in milliseconds "
            f"(default: {FRAME_DURATION_MS})"
        ),
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=MAX_FRAMES,
        help=f"Maximum frames per direction (default: {MAX_FRAMES})",
    )
    parser.add_argument(
        "--max-size-mb",
        type=float,
        default=MAX_FILE_SIZE_BYTES / (1024 * 1024),
        help=(
            "Maximum output GIF size in MB "
            f"(default: {MAX_FILE_SIZE_BYTES / (1024 * 1024):.1f})"
        ),
    )

    args = parser.parse_args()

    if args.step <= 0:
        parser.error("--step must be greater than zero")
    if args.delay < 0:
        parser.error("--delay cannot be negative")
    if args.frame_duration < 20:
        parser.error("--frame-duration must be at least 20ms")
    if args.max_frames < 1:
        parser.error("--max-frames must be at least 1")
    if args.max_size_mb <= 0:
        parser.error("--max-size-mb must be greater than zero")

    asyncio.run(
        capture_scroll_gif(
            url=args.url,
            output=args.output,
            step=args.step,
            delay_ms=args.delay,
            frame_duration=args.frame_duration,
            max_frames=args.max_frames,
            max_file_size=round(args.max_size_mb * 1024 * 1024),
        )
    )


if __name__ == "__main__":
    main()