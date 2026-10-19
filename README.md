# Scroll GIF Capture

Create a smooth, looping GIF of a webpage scrolling from top to bottom and
back again.

The script uses Playwright to render the page in Chromium and Pillow to encode
the captured screenshots as an optimized GIF. It automatically keeps the
highest-quality encoding it can under the configured file-size limit.

## Features

- Headless Chromium page capture
- Smooth scrolling with configurable capture and playback timing
- Automatic top-to-bottom and bottom-to-top looping
- Shared color palette to reduce flicker
- Adaptive encoding that prioritizes:
  1. Full resolution
  2. Maximum color depth
  3. Maximum frame count
- 10 MB output limit by default
- Keeps the first and last scroll positions when reducing frames

## Requirements

- Python 3.10 or newer
- A working internet connection for the target webpage

Install the Python dependencies:

```powershell
py -m pip install pillow playwright
```

Install Playwright's Chromium browser:

```powershell
py -m playwright install chromium
```

## Basic usage

```powershell
py capture_scroll.py "https://example.com"
```

The default output is `scroll.gif`.

Specify an output file:

```powershell
py capture_scroll.py "https://example.com" --output example-scroll.gif
```

## Command-line flags

| Flag | Default | Description |
| --- | ---: | --- |
| `url` | — | Webpage URL to capture. |
| `-o`, `--output` | `scroll.gif` | Output GIF path. Parent directories are created automatically. |
| `--step` | `5` | Scroll distance in pixels between positions. Smaller values can look smoother but create more frames. |
| `--delay` | `100` | Wait time in milliseconds after each scroll position before taking a screenshot. Increase this for pages with heavy animations or lazy-loaded content. |
| `--frame-duration` | `33` | GIF display time per frame in milliseconds. `33` targets approximately 30 FPS. |
| `--max-frames` | `1000` | Maximum captured positions in each scroll direction. |
| `--max-size-mb` | `10` | Maximum output file size in megabytes. |

### Examples

Capture at approximately 30 FPS with the default 10 MB limit:

```powershell
py capture_scroll.py "https://example.com" --frame-duration 33
```

Use a smaller scroll increment for more motion detail:

```powershell
py capture_scroll.py "https://example.com" --step 3
```

Capture a page that needs more time to settle after scrolling:

```powershell
py capture_scroll.py "https://example.com" --delay 250
```

Allow a larger file for better quality:

```powershell
py capture_scroll.py "https://example.com" --max-size-mb 20
```

## How the size limit works

GIF files can become large quickly because every frame is stored separately.
The encoder tries candidates in this order:

1. Full resolution, all frames, 256 colors
2. Fewer colors
3. Fewer frames, preserving the requested playback speed
4. Reduced resolution

If frames are skipped, their display duration is multiplied by the same stride
so the overall scroll speed remains consistent. The final file size and chosen
encoding settings are printed after a successful export.

## Output details

- The GIF loops continuously.
- The capture starts at the top of the page.
- The capture scrolls down, then returns upward.
- Duplicate endpoints are omitted from the return trip.
- The viewport is fixed at `1280x720`.
- CSS animations are disabled while screenshots are captured.

## Troubleshooting

### `Executable doesn't exist`

Install Chromium for Playwright:

```powershell
py -m playwright install chromium
```

### The page looks incomplete

Some websites load content after scrolling or require more settling time. Try
increasing the delay:

```powershell
py capture_scroll.py "https://example.com" --delay 500
```

### The GIF is still too large

The script automatically reduces quality until the limit is met. To make the
result smaller while keeping the same limit, reduce the number of frames:

```powershell
py capture_scroll.py "https://example.com" --max-frames 500
```

### The GIF looks less smooth

Use a smaller `--step`, increase `--max-frames`, or use a larger
`--max-size-mb` limit. A GIF cannot provide unlimited smoothness and
resolution within a fixed file size.

## License

This project is licensed under the MIT Licence.
