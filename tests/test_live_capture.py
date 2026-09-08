import json
import tempfile
import unittest
from pathlib import Path
import sys
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from capture_fpl import normalize, score_previous, RAW_STATS
from deadline_features import build_round

class LiveCaptureTests(unittest.TestCase):
    def test_normalize_uses_completed_fixtures_and_chronological_order(self):
        at='2026-09-08T10:00:00Z'
        bootstrap={'elements':[{'id':1,'team':1,'element_type':3,'web_name':'One'},
                               {'id':2,'team':2,'element_type':3,'web_name':'New'}]}
        fixtures=[{'id':99,'event':1,'team_h':1,'team_a':2,'finished':True,
            'team_h_score':1,'team_a_score':0,'kickoff_time':'2026-08-01T12:00:00Z'},
            {'id':1,'event':2,'team_h':1,'team_a':2,'finished':True,
            'team_h_score':2,'team_a_score':0,'kickoff_time':'2026-08-15T12:00:00Z'},
            {'id':3,'event':4,'team_h':1,'team_a':2,'finished':False,
            'team_h_score':None,'team_a_score':None,'kickoff_time':'2026-09-12T14:00:00Z'}]
        h=[]
        for f in fixtures:
            h.append({'fixture':f['id'],'kickoff_time':f['kickoff_time'],
                      **{c:float(f['id']) for c in RAW_STATS}})
        records={k:{'received_at':at} for k in ['bootstrap','fixtures','player_1','player_2']}
        reg,sch,ph,th=normalize(bootstrap,fixtures,{1:{'history':h},2:{'history':[]}},records,'2026-27')
        self.assertEqual(len(ph),2)
        features=build_round('2026-27',4,'2026-09-12T12:30:00Z',reg,sch,ph,th)
        self.assertEqual(features.query('player_id == 1').minutes_last1.iloc[0],1.)
        self.assertTrue(features.query('player_id == 2').minutes_last1.isna().all())

    def test_score_only_checked_events_and_valid_forecasts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            old=root/'capture_old'; old.mkdir()
            dest=root/'capture_new'; dest.mkdir()
            pd.DataFrame({'season':['2026-27'],'GW':[4],'player_id':[1],
                          'prediction':[3.]}).to_csv(old/'forecast.csv',index=False)
            (old/'manifest.json').write_text(json.dumps({'forecast_status':'experimental_frozen'}))
            histories={1:{'history':[{'round':4,'total_points':5},{'round':4,'total_points':2}]}}
            bootstrap={'events':[{'id':4,'finished':True,'data_checked':False}]}
            self.assertEqual(score_previous(root,dest,bootstrap,histories,'2026-27','now'),0)
            bootstrap['events'][0]['data_checked']=True
            self.assertEqual(score_previous(root,dest,bootstrap,histories,'2026-27','now'),1)
            self.assertEqual(pd.read_csv(dest/'observed_outcomes.csv').actual_points.iloc[0],7)
            (old/'manifest.json').write_text(json.dumps({'forecast_status':'invalid_written_after_deadline'}))
            self.assertEqual(score_previous(root,dest,bootstrap,histories,'2026-27','now'),0)

if __name__=='__main__':
    unittest.main()
