import json,math,pathlib,sys,tempfile,threading,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import engine,app
class IndependentTests(unittest.TestCase):
    def test_sentence_boundaries_and_overlap(self):
        segments=[{'start':i*4,'end':i*4+3.8,'text':f'Why this important lesson works because practice matters number {i}.','words':[]} for i in range(20)]
        clips=engine.rank_highlights(segments,0,80,15,5,'practice',threading.Event(),lambda *a:None,semantic=False)
        self.assertGreater(len(clips),0)
        for clip in clips:self.assertGreater(clip['end'],clip['start']);self.assertLessEqual(clip['end'],80)
        for i,left in enumerate(clips):
            for right in clips[i+1:]:self.assertLessEqual(max(0,min(left['end'],right['end'])-max(left['start'],right['start'])),min(left['end']-left['start'],right['end']-right['start'])*.15)
    def test_caption_timing_and_filter_injection(self):
        segments=[{'start':10,'end':14,'text':'bad {\\an8} text','words':[]}]
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder);engine.write_captions(segments,11,13,path)
            srt=(path/'captions.srt').read_text();ass=(path/'captions.ass').read_text()
            self.assertIn('00:00:00,000 --> 00:00:02,000',srt)
            self.assertNotIn('{\\an8}',ass)
    def test_timestamp_rollover(self):
        self.assertEqual(engine.timestamp(59.9999),'00:01:00,000')
        self.assertEqual(engine.timestamp(3599.9999,True),'1:00:00.00')
    def test_numeric_validation(self):
        for value in ('nan','inf',-1,1001):
            with self.assertRaises(ValueError):app.number(value,'test',0,1000)
    def test_opaque_ids(self):
        for value in ('../private','a'*31,None):
            with self.assertRaises(ValueError):app.jid(value)
    def test_cancel_subprocess(self):
        event=threading.Event();event.set()
        with self.assertRaises(engine.Cancelled):engine.command([sys.executable,'-c','import time;time.sleep(20)'],event)
    def test_no_speech_candidates(self):
        with self.assertRaises(ValueError):engine.rank_highlights([],0,30,10,1,'',threading.Event(),lambda *a:None,semantic=False)
if __name__=='__main__':unittest.main()
