# Independent AI Clipper — Creator Spotlight

Your own local clipping system. There is no vidIQ integration, paid AI API, subscription, account sign-in, or per-clip credit charge. It uses open-source models and FFmpeg on your computer.

## Windows: start here
1. Install **Python 3.12, 64-bit** from https://www.python.org/downloads/. Select **Add Python to PATH** during installation. Python 3.11–3.13 are supported.
2. Extract the entire ZIP to a normal folder, such as Documents/AI-Clipper. Do not run it inside the compressed ZIP.
3. Double-click **START_WINDOWS.bat**. First setup installs open-source packages from PyPI. Keep the terminal window open.
4. Your browser opens at **http://127.0.0.1:8765**. If it does not, enter that address manually.
5. Choose a local video. Start with a short section, for example 0–120 seconds. Select clip length and count, then **Create my clips**.
6. On first AI use, model files download from their public model hosts. The app reports this stage; the download may take several minutes. Subsequent runs reuse those files.
7. Download the resulting vertical MP4 clips and caption SRT files. The originals and exports also remain in the app's `data` folder.

If Windows asks what to do with a downloaded file, review its source and contents before running it. This is Python source, not a signed Windows installer. Nothing has been installed on your laptop by this chat.

## What works
- Local MP4/MOV/WebM/MKV/AVI footage, up to 2 GB.
- CPU speech recognition using faster-whisper (Tiny, Base or Small English).
- Local semantic highlight ranking using FastEmbed/BGE, supplemented by speech coverage and sentence boundaries.
- A topic/focus prompt and non-overlapping clip suggestions. Fewer clips may be produced when the range is short.
- Automatic speech captions burned into real H.264/AAC 720×1280 MP4s; separate SRT captions and a transcript download.
- Center crop or fit the full source with black padding.
- Manual start/length clipping; uncheck captions and semantic ranking for a simple cut without loading models.
- Saved source files and job history, progress, cancellation, and video preview.
- Optional YouTube URL import via yt-dlp for videos you may download. Availability depends on YouTube and local runtime requirements. If it fails, use a source file you already have. The app does not bypass sign-in, DRM, or bot checks. Some YouTube downloads require a supported JavaScript runtime; see https://github.com/yt-dlp/yt-dlp.

## Costs and limits
No paid processing provider is required. Your computer supplies the processing power, electricity, disk space and internet for initial setup/downloads. A public service would still need hosting, storage and processing infrastructure.

Default models support English. More accurate models take more CPU time and memory; an older laptop may be slow. Start with Tiny and a short source range. Tiny is the default for a faster first run; Base can improve accuracy. Keep the terminal open and the laptop awake. Cancellation during model download or embedding calculation may take time; completed exports remain available.

Highlight ranking suggests moments; it does not understand every context or guarantee viral results. The title is a transcript excerpt, not an invented hook. Review both the selected footage and caption accuracy before posting. Framing is center crop, not face tracking. Output length can adjust toward sentence boundaries.

This release **does not automatically publish** to YouTube or Instagram. Export and upload through those platforms. Direct social integrations can be added separately with your own platform developer credentials and account authorization.

After packages and model files are downloaded, processing local footage can run without a paid API. Online imports and initial model downloads need internet. Cached models can be removed by deleting `data/models`, which causes the next AI run to download them again. Data is stored locally; back up the folder if needed. The app is bound to localhost and intentionally does not open access from a phone or the public internet.

## Mac / Linux
Install Python 3.12 and run `sh START_MAC_LINUX.sh` from the extracted folder. Linux may require its distribution's Python venv package. This release was exercised on Linux; the Windows launcher and Windows-specific caption path handling were reviewed but require a first run on the target laptop.

## Troubleshooting
- **Python not found:** install Python 3.12 and enable PATH, then reopen the launcher.
- **Port already in use:** close the earlier app terminal, or run `.venv/Scripts/python.exe app.py --port 8766` on Windows.
- **Model download fails:** check internet access to Hugging Face/model hosts and retry. Basic keyword ranking avoids the embedding model; manual mode with captions off avoids speech models too.
- **No speech detected:** use a different spoken section or manual mode. This app is designed around speech videos.
- **Data cleanup:** close the app, then remove unneeded folders under `data/sources`, `data/exports`, or `data/jobs`. Never delete them during a job.

## Components and licensing
Application source: MIT (see LICENSE). Components retain their own licenses: faster-whisper and Whisper models (MIT), FastEmbed (Apache-2.0), BGE-small-en-v1.5 (MIT), PyAV and imageio-ffmpeg, yt-dlp, and the selected FFmpeg build (LGPL/GPL depending on configuration). Dependencies and models are downloaded during setup/use, not bundled into this ZIP. Review upstream licenses before distributing a compiled commercial package; this list does not replace their license texts.

## Development
`python -m pip install -r requirements.txt`; `python app.py --no-browser`; tests: `python -m unittest discover -s tests -v`.
No provider credentials belong in this repository. Runtime video files, models, virtual environments and job data must remain untracked.
