"""Independent CPU-based clipping engine. No paid API or vidIQ dependency."""
from __future__ import annotations
import json, math, os, pathlib, re, shutil, subprocess, threading, time
from typing import Callable
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY','1')
os.environ.setdefault('DO_NOT_TRACK','1')
ROOT=pathlib.Path(__file__).resolve().parent
DATA=pathlib.Path(os.environ.get('CLIPPER_DATA_DIR', str(ROOT/'data'))).resolve()
for name in ('sources','jobs','exports','models'):(DATA/name).mkdir(parents=True,exist_ok=True)
_MODEL=None
_EMBED=None
class Cancelled(Exception):pass

def ffmpeg():
    executable=shutil.which('ffmpeg')
    if executable:return executable
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()

def probe(path):
    import av
    with av.open(str(path)) as container:
        streams=[s for s in container.streams if s.type=='video']
        if not streams:raise ValueError('This file contains no video.')
        stream=streams[0]
        duration=float(container.duration/av.time_base) if container.duration else float(stream.duration*stream.time_base) if stream.duration else 0
        if not math.isfinite(duration) or duration<1:raise ValueError('Cannot determine this video’s duration.')
        return {'duration':duration,'width':stream.width,'height':stream.height,'audio':any(s.type=='audio' for s in container.streams)}

def command(args,cancel,timeout=3600):
    import tempfile
    with tempfile.TemporaryFile() as log:
        process=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=log)
        started=time.monotonic()
        try:
            while process.poll() is None:
                if cancel.is_set():raise Cancelled('Job cancelled.')
                if time.monotonic()-started>timeout:raise RuntimeError('Processing timed out. Try a shorter section.')
                time.sleep(.1)
            if process.returncode:
                log.seek(0);detail=log.read().decode('utf-8',errors='replace')[-2000:]
                raise RuntimeError('Video processing failed: '+detail)
        finally:
            if process.poll() is None:process.kill();process.wait()

def transcribe(path,start,end,model_name,cancel,progress):
    global _MODEL
    from faster_whisper import WhisperModel
    progress('Loading speech model. First use downloads free model files.',3)
    if _MODEL is None or _MODEL[0]!=model_name:
        _MODEL=(model_name,WhisperModel(model_name,device='cpu',compute_type='int8',download_root=str(DATA/'models'),cpu_threads=max(1,min(4,os.cpu_count() or 2))))
    if cancel.is_set():raise Cancelled('Job cancelled.')
    audio=DATA/'jobs'/f'audio-{threading.get_ident()}.wav'
    command([ffmpeg(),'-hide_banner','-loglevel','error','-y','-ss',str(start),'-i',str(path),'-t',str(end-start),'-vn','-ac','1','-ar','16000',str(audio)],cancel)
    try:
        segments,info=_MODEL[1].transcribe(str(audio),language='en',word_timestamps=True,vad_filter=True,beam_size=3,condition_on_previous_text=False)
        output=[]
        for segment in segments:
            if cancel.is_set():raise Cancelled('Job cancelled.')
            output.append({'start':segment.start+start,'end':segment.end+start,'text':segment.text.strip(),'words':[{'start':w.start+start,'end':w.end+start,'text':w.word.strip()} for w in segment.words or []]})
            progress('Transcribing speech on your CPU…',8+int(min(1,segment.end/(end-start))*45))
        if not output:raise ValueError('No clear English speech was found in this range. Choose a different section or use manual clipping.')
        return output
    finally:audio.unlink(missing_ok=True)

def candidates(segments,start,end,duration):
    selections=[]
    for segment in segments:
        begin=max(start,segment['start']-.12)
        if end-begin<min(5,duration*.5):continue
        finish=min(end,begin+duration)
        # Prefer a sentence boundary near the requested length.
        nearby=[s['end'] for s in segments if begin+duration*.75<=s['end']<=min(end,begin+duration*1.15)]
        if nearby:finish=min(nearby,key=lambda x:abs(x-begin-duration))
        text=' '.join(s['text'] for s in segments if s['end']>begin and s['start']<finish).strip()
        if not text:continue
        words=re.findall(r'\b\w+\b',text.lower())
        speaking=sum(max(0,min(s['end'],finish)-max(s['start'],begin)) for s in segments if s['end']>begin and s['start']<finish)
        coverage=min(1,speaking/max(.1,finish-begin));diversity=len(set(words))/max(1,len(words))
        hook=.15 if re.search(r'\b(why|how|secret|mistake|learn|never|important|because|imagine)\b',text[:180],re.I) else 0
        selections.append({'start':round(begin,2),'end':round(finish,2),'text':text,'quality':coverage*.65+diversity*.2+hook})
    # Cap expensive embedding work while sampling throughout long inputs.
    if len(selections)>500:
        step=len(selections)/500;selections=[selections[int(i*step)] for i in range(500)]
    return selections

def rank_highlights(segments,start,end,duration,count,focus,cancel,progress,semantic=True):
    global _EMBED
    choices=candidates(segments,start,end,duration)
    if not choices:raise ValueError('Not enough speech to propose a clip in this range.')
    if semantic:
        import numpy as np
        from fastembed import TextEmbedding
        progress('Loading local highlight model. First use downloads free model files.',56)
        if _EMBED is None:_EMBED=TextEmbedding('BAAI/bge-small-en-v1.5',cache_dir=str(DATA/'models'/'embeddings'),threads=max(1,min(4,os.cpu_count() or 2)))
        if cancel.is_set():raise Cancelled('Job cancelled.')
        query=focus.strip() or 'A compelling self-contained explanation with a practical lesson, surprising insight, useful advice, or an interesting story.'
        vectors=list(_EMBED.embed([query]+[c['text'][:3000] for c in choices],batch_size=16))
        q=vectors[0];q=q/max(float(np.linalg.norm(q)),1e-9)
        for choice,vector in zip(choices,vectors[1:]):
            similarity=float(np.dot(q,vector)/max(float(np.linalg.norm(vector)),1e-9));choice['score']=round(similarity*.8+choice['quality']*.2,4)
    else:
        # Explicitly requested basic mode: no claim of semantic AI scoring.
        focus_words=set(re.findall(r'\w+',focus.lower()))
        for choice in choices:
            overlap=len(focus_words&set(re.findall(r'\w+',choice['text'].lower())))/max(1,len(focus_words))
            choice['score']=round(choice['quality']*.8+overlap*.2,4)
    if cancel.is_set():raise Cancelled('Job cancelled.')
    selected=[]
    for candidate in sorted(choices,key=lambda c:c['score'],reverse=True):
        if any(max(0,min(candidate['end'],s['end'])-max(candidate['start'],s['start']))>min(candidate['end']-candidate['start'],s['end']-s['start'])*.15 for s in selected):continue
        title=re.sub(r'\s+',' ',candidate['text']).strip();candidate['title']=title[:87]+('…' if len(title)>87 else '')
        candidate['reason']='Ranked by local semantic relevance and speech coverage.' if semantic else 'Ranked by speech coverage and keyword matches (basic mode).'
        selected.append(candidate)
        if len(selected)>=count:break
    return selected

def timestamp(seconds,ass=False):
    seconds=max(0,seconds)
    if ass:
        n=round(seconds*100);h,n=divmod(n,360000);m,n=divmod(n,6000);s,cs=divmod(n,100);return f'{h}:{m:02}:{s:02}.{cs:02}'
    n=round(seconds*1000);h,n=divmod(n,3600000);m,n=divmod(n,60000);s,ms=divmod(n,1000);return f'{h:02}:{m:02}:{s:02},{ms:03}'

def cues(segments,start,end):
    result=[]
    for segment in segments:
        words=[w for w in segment.get('words',[]) if w['end']>start and w['start']<end]
        if words:
            for pos in range(0,len(words),6):
                group=words[pos:pos+6];a=max(start,group[0]['start']);b=min(end,group[-1]['end']);text=' '.join(w['text'] for w in group)
                if b>a:result.append((a-start,b-start,text))
        elif segment['end']>start and segment['start']<end:
            result.append((max(0,segment['start']-start),min(end-start,segment['end']-start),segment['text']))
    return result

def write_captions(segments,start,end,directory):
    rows=cues(segments,start,end)
    (directory/'captions.srt').write_text('\n\n'.join(f'{i+1}\n{timestamp(a)} --> {timestamp(b)}\n{text}' for i,(a,b,text) in enumerate(rows))+'\n',encoding='utf-8')
    header='''[Script Info]\nScriptType: v4.00+\nPlayResX: 720\nPlayResY: 1280\nWrapStyle: 0\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Arial,44,&H00FFFFFF,&H000000FF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,45,45,180,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'''
    safe=lambda text:text.replace('\\',' ').replace('{','(').replace('}',')').replace('\n',' ')
    (directory/'captions.ass').write_text(header+''.join(f'Dialogue: 0,{timestamp(a,True)},{timestamp(b,True)},Default,,0,0,0,,{safe(text)}\n' for a,b,text in rows),encoding='utf-8')

def render(path,clip,segments,folder,cancel,captions=True,fit='crop'):
    folder.mkdir(parents=True,exist_ok=True);write_captions(segments,clip['start'],clip['end'],folder)
    filters='scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1' if fit=='crop' else 'scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2:black,setsar=1'
    if captions:
        # Relative filter paths avoid Windows drive-letter escaping and shell injection.
        filters+=',ass=captions.ass'
    output=folder/'clip.mp4'
    args=[ffmpeg(),'-hide_banner','-loglevel','error','-y','-ss',str(clip['start']),'-i',str(path),'-t',str(clip['end']-clip['start']),'-vf',filters,'-map','0:v:0','-map','0:a?','-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-movflags','+faststart',str(output)]
    # Only one worker renders at a time; subprocess cwd does not change the server cwd.
    with __import__('tempfile').TemporaryFile() as log:
        process=subprocess.Popen(args,cwd=str(folder),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=log)
        t=time.monotonic()
        try:
            while process.poll() is None:
                if cancel.is_set():raise Cancelled('Job cancelled.')
                if time.monotonic()-t>3600:raise RuntimeError('Rendering timed out.')
                time.sleep(.1)
            if process.returncode:
                log.seek(0);raise RuntimeError('Rendering failed: '+log.read().decode(errors='replace')[-2000:])
        finally:
            if process.poll() is None:process.kill();process.wait()
    return output
