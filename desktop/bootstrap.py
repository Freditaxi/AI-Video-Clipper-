"""Create an isolated environment and launch the local clipper."""
import hashlib,os,pathlib,subprocess,sys,venv
ROOT=pathlib.Path(__file__).resolve().parent
if not (3,11)<=sys.version_info[:2]<(3,14):
    raise SystemExit('Please install Python 3.12 (64-bit) from https://www.python.org/downloads/ and enable Add Python to PATH, then run START_WINDOWS.bat again.')
python=ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
try:
    if not python.exists():
        print('Creating your private Python environment…',flush=True);venv.create(ROOT/'.venv',with_pip=True)
    requirements=ROOT/'requirements.txt';digest=hashlib.sha256(requirements.read_bytes()).hexdigest();stamp=ROOT/'.venv'/'.clipper-requirements'
    if not stamp.exists() or stamp.read_text()!=digest:
        print('Installing open-source components from PyPI. First setup needs internet; no subscription or account is required.',flush=True)
        subprocess.run([str(python),'-m','pip','install','-r',str(requirements)],check=True,cwd=ROOT)
        subprocess.run([str(python),'-m','pip','check'],check=True,cwd=ROOT);stamp.write_text(digest)
    subprocess.run([str(python),str(ROOT/'app.py')],check=True,cwd=ROOT)
except (OSError,subprocess.CalledProcessError) as exc:
    raise SystemExit(f'Setup or launch failed: {exc}\nCheck your internet connection, use Python 3.12 (64-bit), and try again. Keep this error message if you need help.')
