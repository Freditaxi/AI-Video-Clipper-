# AI Video Clipper / Creator Spotlight

A static, browser-based video editor deployed to the existing ai-video-clipper Vercel project. No server, paid API, account, or install is needed. All media processing takes place on the user's device.

## Available
- Import a browser-playable local video up to 1 GB (H.264/AAC MP4 recommended).
- Preview and trim a 1–180 second moment; use the source playhead as the start.
- Export 9:16, square, or landscape at 720p with audio.
- Fill/crop or fit whole video; adjust horizontal crop position.
- Burn in a title or captions from an imported SRT file with source timestamps.
- Save up to 20 selections in a session queue and export in order.
- Add evenly spaced time-based selections for manual review.
- Preview and download output; native file sharing on supported devices.
- Cancel exports and detect backgrounding or stalled playback.

## Export behavior
Uses Canvas captureStream, Web Audio, and MediaRecorder. MP4 is preferred when supported by the browser; WebM is the fallback, with the correct file extension. Export runs at playback speed, so keep the tab visible and the device awake. A screen wake lock is requested where supported. Devices that cannot sustain playback/encoding should use shorter clips or a faster computer. Output is re-encoded, so trimming is approximate to a frame/playback scheduling interval rather than sample-exact.

The app does not upload videos and has no server-side storage or credentials. Source media, selections, and exports are kept only in memory for the current session. Download finished files before refreshing/closing. The user must obtain source footage separately.

## Not connected
Automatic AI highlight identification, speech transcription, face tracking, YouTube URL downloads, and direct YouTube/Instagram publishing are not implemented. Time-based batch selections are explicitly labeled; subtitle import is not automatic transcription.

## Development and deployment
Serve this directory with `python3 -m http.server 8765` and open localhost in a supported browser. No build dependencies. The lowercase root `index.html` is required for Vercel static hosting. `vercel.json` defines security and caching headers. Deploy only the existing ai-video-clipper project, linked to Freditaxi/AI-Video-Clipper-.

## Verification
Use a synthetic video with known audio and duration. Import it, trim a middle segment, export, download, and inspect the output streams, dimensions, duration, and non-silent audio. Also check invalid ranges, SRT caption rendering, crop/fit, queue export, cancellation, and phone-width layout.
