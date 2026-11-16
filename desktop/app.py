from __future__ import annotations
import argparse, concurrent.futures, http.server, json, math, mimetypes, pathlib, re, secrets, shutil, socket, subprocess, sys, threading, time, uuid, webbrowser
from urllib.parse import urlparse, parse_qs, unquote
import engine
ROOT=pathlib.Path(__file__).resolve().parent
DATA=engine.DATA
TOKEN=secrets.token_urlsafe(32)
POOL=concurrent.futures.ThreadPoolExecutor(max_workers=1)
LOCK=threading.RLock()
EVENTS={}
PORT=8765
MAX_UPLOAD=2*1024**3

def atomic(path,obj):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)

def jid(value):
    if not isinstance(value,str) or not re.fullmatch(r'[a-f0-9]{32}',value):raise ValueError('Invalid identifier.')
    return value

def source_record(source_id):
    return json.loads((DATA/'sources'/jid(source_id)/'source.json').read_text(encoding='utf-8'))

def read_jobs():
    result=[]
    for p in sorted((DATA/'jobs').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
        if not re.fullmatch(r'[a-f0-9]{32}',p.stem):continue
        if len(result)>=30:break
        try:result.append(json.loads(p.read_text(encoding='utf-8')))
        except (OSError,ValueError):continue
    return result

def update_job(job_id,**values):
    with LOCK:
        p=DATA/'jobs'/f'{job_id}.json';job=json.loads(p.read_text(encoding='utf-8'));job.update(values);job['updated']=time.time();atomic(p,job)

def new_job(kind,args):
    with LOCK:
        if any(j['state'] in ('queued','running') for j in read_jobs()):raise ValueError('One job is already active. Wait for it or cancel before starting another.')
        job_id=uuid.uuid4().hex
        atomic(DATA/'jobs'/f'{job_id}.json',{'id':job_id,'kind':kind,'args':args,'state':'queued','message':'Waiting to start…','progress':0,'created':time.time(),'clips':[]})
        event=threading.Event();EVENTS[job_id]=event
        POOL.submit(worker,job_id,kind,args,event)
        return job_id

def worker(job_id,kind,args,cancel):
    try:
        update_job(job_id,state='running',message='Starting…')
        if kind=='import':
            import yt_dlp
            source_id=uuid.uuid4().hex;folder=DATA/'sources'/source_id;folder.mkdir()
            def hook(status):
                if cancel.is_set():raise engine.Cancelled('Import cancelled.')
                downloaded=status.get('downloaded_bytes',0);total=status.get('total_bytes') or status.get('total_bytes_estimate') or 0
                if downloaded>MAX_UPLOAD:raise ValueError('Import exceeds 2 GB.')
                update_job(job_id,message='Downloading source video…',progress=min(95,round(downloaded/total*95)) if total else 10)
            options={'format':'best[ext=mp4][height<=720][acodec!=none]/best[height<=720][acodec!=none]/best[acodec!=none]','outtmpl':str(folder/'source.%(ext)s'),'noplaylist':True,'max_filesize':MAX_UPLOAD,'progress_hooks':[hook],'quiet':True,'socket_timeout':20,'retries':1,'cachedir':str(DATA/'models'/'ytdlp')}
            with yt_dlp.YoutubeDL(options) as ydl:
                info=ydl.extract_info(args['url'],download=True)
                path=pathlib.Path(ydl.prepare_filename(info))
            if not path.is_file():raise ValueError('Import did not produce a video. Select a local video file instead.')
            meta=engine.probe(path);record={'id':source_id,'name':info.get('title','Imported video'),'file':path.name,**meta};atomic(folder/'source.json',record)
            update_job(job_id,state='done',progress=100,message='Video imported.',source=record)
            return
        source=source_record(args['source_id']);path=DATA/'sources'/source['id']/source['file']
        start=args['start'];end=args['end']
        transcript=[]
        if args['mode']=='ai' or args['captions']:
            transcript=engine.transcribe(path,start,end,args['model'],cancel,lambda text,pct:update_job(job_id,message=text,progress=pct))
            atomic(DATA/'jobs'/f'{job_id}-transcript.json',{'segments':transcript})
        if args['mode']=='ai':
            selected=engine.rank_highlights(transcript,start,end,args['length'],args['count'],args['focus'],cancel,lambda text,pct:update_job(job_id,message=text,progress=pct),semantic=args['semantic'])
        else:selected=[{'start':start,'end':min(end,start+args['length']),'title':'Manual clip','reason':'Start and length selected by you.','score':None}]
        rendered=[]
        for i,clip in enumerate(selected):
            if cancel.is_set():raise engine.Cancelled('Job cancelled.')
            update_job(job_id,message=f'Rendering clip {i+1} of {len(selected)}…',progress=65+int(i/len(selected)*32))
            folder=DATA/'exports'/job_id/str(i+1)
            engine.render(path,clip,transcript,folder,cancel,args['captions'],args['fit'])
            item={**clip,'url':f'/exports/{job_id}/{i+1}/clip.mp4','srt':f'/exports/{job_id}/{i+1}/captions.srt'}
            rendered.append(item);update_job(job_id,clips=rendered)
        if transcript:
            (DATA/'exports'/job_id/'transcript.txt').write_text('\n'.join(f"[{s['start']:.2f}] {s['text']}" for s in transcript),encoding='utf-8')
        update_job(job_id,state='done',progress=100,message=f'{len(rendered)} clip(s) ready. All processing ran on this computer.',clips=rendered,transcript=f'/exports/{job_id}/transcript.txt' if transcript else None)
    except Exception as exc:
        state='cancelled' if cancel.is_set() or isinstance(exc,engine.Cancelled) else 'error'
        detail=str(exc)
        if kind=='import' and state=='error':detail+=' YouTube may restrict downloads or require additional runtime support. Use a video file you already have; no sign-in or bot-check bypass is attempted.'
        update_job(job_id,state=state,message=detail[-2500:])
    finally:
        with LOCK:EVENTS.pop(job_id,None)

def number(value,name,low,high):
    try:n=float(value)
    except (TypeError,ValueError):raise ValueError(f'Enter a valid {name}.')
    if not math.isfinite(n) or not low<=n<=high:raise ValueError(f'{name} must be between {low} and {high}.')
    return n

def validate_job(args):
    source=source_record(args.get('source_id'));start=number(args.get('start'), 'range start',0,source['duration']);end=number(args.get('end'),'range end',0,source['duration']+.02)
    if end-start<1 or end-start>1800:raise ValueError('Choose a range from 1 second to 30 minutes.')
    mode=args.get('mode','ai')
    if mode not in ('ai','manual'):raise ValueError('Choose AI highlights or manual clip.')
    if mode=='ai' and end-start<10:raise ValueError('AI highlights need at least 10 seconds of source.')
    length=number(args.get('length'), 'clip length',1,180)
    if length>end-start+.02:raise ValueError('Clip length must fit within the selected range.')
    count=int(number(args.get('count'),'clip count',1,10))
    model=args.get('model','base.en')
    if model not in ('tiny.en','base.en','small.en'):raise ValueError('Choose a supported speech model.')
    fit=args.get('fit','crop')
    if fit not in ('crop','contain'):raise ValueError('Choose a supported framing mode.')
    focus=str(args.get('focus','')).strip()
    if len(focus)>500:raise ValueError('Keep the focus prompt under 500 characters.')
    return {'source_id':source['id'],'start':start,'end':end,'length':length,'count':count,'mode':mode,'model':model,'fit':fit,'focus':focus,'captions':args.get('captions') is True,'semantic':args.get('semantic') is True}

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def valid_host(self):return self.headers.get('Host') in (f'127.0.0.1:{PORT}',f'localhost:{PORT}')
    def send(self,status,body,ctype='application/json'):
        body=body.encode('utf-8') if isinstance(body,str) else body
        self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' blob:; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'");self.end_headers();self.wfile.write(body)
    def reply(self,status,obj):self.send(status,json.dumps(obj,ensure_ascii=False))
    def stream(self,path):
        size=path.stat().st_size;a=0;b=size-1;partial=False
        if self.headers.get('Range'):
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',self.headers['Range'])
            if not match:return self.send(416,'Invalid range','text/plain')
            left,right=match.groups()
            if not left and not right:return self.send(416,'Invalid range','text/plain')
            if not left:a=max(0,size-int(right))
            else:a=int(left);b=min(size-1,int(right)) if right else size-1
            if a>=size or b<a:return self.send(416,'Invalid range','text/plain')
            partial=True
        self.send_response(206 if partial else 200);self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream');self.send_header('Content-Length',str(b-a+1));self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        if partial:self.send_header('Content-Range',f'bytes {a}-{b}/{size}')
        self.end_headers()
        try:
            with path.open('rb') as src:
                src.seek(a);remain=b-a+1
                while remain:
                    chunk=src.read(min(1024**2,remain))
                    if not chunk:break
                    self.wfile.write(chunk);remain-=len(chunk)
        except (ConnectionError,OSError):pass
    def do_GET(self):
        if not self.valid_host():return self.send(403,'Invalid host','text/plain')
        path=urlparse(self.path).path
        try:
            if path=='/':return self.send(200,(ROOT/'ui'/'index.html').read_text(encoding='utf-8').replace('__SESSION_TOKEN__',TOKEN),'text/html; charset=utf-8')
            if path in ('/app.js','/style.css'):return self.send(200,(ROOT/'ui'/path[1:]).read_bytes(),'text/javascript' if path.endswith('.js') else 'text/css')
            if path=='/api/state':
                sources=[]
                for item in (DATA/'sources').glob('*/source.json'):
                    try:sources.append(json.loads(item.read_text(encoding='utf-8')))
                    except (OSError,ValueError):continue
                return self.reply(200,{'sources':sources,'jobs':[j for j in read_jobs() if '-transcript' not in j.get('id','')],'version':'2.0.0','independent':True})
            if path.startswith('/media/'):
                record=source_record(path.split('/')[-1]);return self.stream(DATA/'sources'/record['id']/record['file'])
            if path.startswith('/exports/'):
                parts=path.split('/')[2:]
                if len(parts)<2 or jid(parts[0])!=parts[0]:raise ValueError('Invalid export.')
                candidate=(DATA/'exports'/pathlib.Path(*parts)).resolve();base=(DATA/'exports').resolve()
                if not candidate.is_relative_to(base) or not candidate.is_file():raise ValueError('Export not found.')
                return self.stream(candidate)
            self.send(404,'Not found','text/plain')
        except (ValueError,OSError,KeyError):self.reply(404,{'error':'File not found.'})
    def do_POST(self):
        if not self.valid_host() or self.headers.get('Origin') not in (f'http://127.0.0.1:{PORT}',f'http://localhost:{PORT}') or not secrets.compare_digest(self.headers.get('X-Clipper-Key',''),TOKEN):
            self.close_connection=True;return self.reply(403,{'error':'Open the app on this computer and refresh the page.'})
        path=urlparse(self.path).path
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size<1 or size>(MAX_UPLOAD if path=='/api/upload' else 16000):raise ValueError('Request too large or empty.')
            if path=='/api/upload':
                name=parse_qs(urlparse(self.path).query).get('name',['video.mp4'])[0];ext=pathlib.Path(name).suffix.lower()
                if ext not in ('.mp4','.mov','.webm','.mkv','.m4v','.avi'):raise ValueError('Choose an MP4, MOV, WebM, MKV, M4V or AVI file.')
                source_id=uuid.uuid4().hex;folder=DATA/'sources'/source_id;folder.mkdir();dest=folder/('source'+ext)
                try:
                    with dest.open('wb') as out:
                        left=size
                        while left:
                            chunk=self.rfile.read(min(left,1024**2))
                            if not chunk:raise ValueError('Upload interrupted.')
                            out.write(chunk);left-=len(chunk)
                    record={'id':source_id,'name':name[:180],'file':dest.name,**engine.probe(dest)};atomic(folder/'source.json',record)
                    return self.reply(200,{'source':record})
                except Exception:
                    shutil.rmtree(folder,ignore_errors=True);raise
            args=json.loads(self.rfile.read(size))
            if path=='/api/create':return self.reply(202,{'job_id':new_job('create',validate_job(args))})
            if path=='/api/import':
                url=str(args.get('url',''));u=urlparse(url)
                if u.scheme!='https' or u.hostname not in ('youtube.com','www.youtube.com','m.youtube.com','youtu.be'):raise ValueError('Enter a YouTube HTTPS link, or choose a local file.')
                return self.reply(202,{'job_id':new_job('import',{'url':url})})
            if path=='/api/cancel':
                job_id=jid(args.get('job_id'))
                with LOCK:
                    event=EVENTS.get(job_id)
                    if event:event.set()
                return self.reply(200,{'message':'Cancellation requested. Model loading or a running AI operation may take a moment to stop.'})
            self.reply(404,{'error':'Unknown action.'})
        except Exception as exc:
            self.close_connection=True;self.reply(400,{'error':str(exc)[:1000]})

def main():
    global PORT
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8765);parser.add_argument('--no-browser',action='store_true');options=parser.parse_args();PORT=options.port
    for record in read_jobs():
        if record['state'] in ('queued','running'):update_job(record['id'],state='error',message='App was closed before this job finished. It has not been restarted automatically.')
    try:server=http.server.ThreadingHTTPServer(('127.0.0.1',PORT),Handler)
    except OSError as exc:raise SystemExit(f'Cannot open port {PORT}. Close an earlier copy of AI Clipper, or run app.py --port 8766.\n{exc}')
    print(f'\nCreator Spotlight Independent AI Clipper\nOpen http://127.0.0.1:{PORT}\nData stays in {DATA}\nKeep this window open. Press Ctrl+C to stop.\n',flush=True)
    if not options.no_browser:threading.Timer(1,lambda:webbrowser.open(f'http://127.0.0.1:{PORT}')).start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        for event in list(EVENTS.values()):event.set()
        server.server_close();POOL.shutdown(wait=False,cancel_futures=True)
if __name__=='__main__':main()
