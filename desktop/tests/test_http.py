import http.server,json,pathlib,subprocess,sys,tempfile,threading,time,unittest,urllib.request,urllib.error
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import app,engine
class LocalHTTPTests(unittest.TestCase):
    def test_upload_security_render_and_seek(self):
        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),app.Handler);app.PORT=server.server_address[1]
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        root=f'http://127.0.0.1:{app.PORT}';client=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            headers={'Content-Type':'application/json','Origin':'https://untrusted.example','X-Clipper-Key':app.TOKEN}
            with self.assertRaises(urllib.error.HTTPError) as denied:client.open(urllib.request.Request(root+'/api/create',data=b'{}',headers=headers))
            self.assertEqual(denied.exception.code,403)
            with tempfile.TemporaryDirectory() as directory:
                video=pathlib.Path(directory)/'test.mp4'
                subprocess.run([engine.ffmpeg(),'-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=160x90:rate=15','-f','lavfi','-i','sine=frequency=440','-t','2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(video)],check=True)
                headers={'Content-Type':'application/octet-stream','Origin':root,'X-Clipper-Key':app.TOKEN}
                record=json.load(client.open(urllib.request.Request(root+'/api/upload?name=test.mp4',data=video.read_bytes(),headers=headers)))['source']
                req=urllib.request.Request(root+'/media/'+record['id'],headers={'Range':'bytes=0-31'})
                response=client.open(req);self.assertEqual(response.status,206);self.assertEqual(len(response.read()),32)
                args={'source_id':record['id'],'mode':'manual','start':0,'end':2,'length':1,'count':1,'model':'tiny.en','fit':'contain','captions':False,'semantic':False}
                headers={'Content-Type':'application/json','Origin':root,'X-Clipper-Key':app.TOKEN}
                job=json.load(client.open(urllib.request.Request(root+'/api/create',data=json.dumps(args).encode(),headers=headers)))['job_id']
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    result=next(j for j in app.read_jobs() if j['id']==job)
                    if result['state'] not in ('queued','running'):break
                    time.sleep(.1)
                self.assertEqual(result['state'],'done',result['message']);self.assertEqual(len(result['clips']),1)
                result_file=engine.DATA/'exports'/job/'1'/'clip.mp4';meta=engine.probe(result_file)
                self.assertEqual((meta['width'],meta['height']),(720,1280));self.assertTrue(meta['audio'])
        finally:server.shutdown();server.server_close()
