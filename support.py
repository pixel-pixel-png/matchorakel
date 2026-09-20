"""Synthetic, reproducible test data. Never loaded by the production entry point."""
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import app as web

TEAMS={'PL':['arsenal','chelsea','man united','man city','tottenham','sheffield united'],
       'LL':['barcelona','sevilla','real madrid','atletico madrid','athletic bilbao','real sociedad','real betis'],
       'BL':['bayern munich','dortmund','leverkusen'], 'SA':['inter','milan','juventus','roma'],
       'L1':['paris sg','marseille','lyon']}
PAIRS={'PL':('Arsenal','Chelsea'),'LL':('Barcelona','Sevilla'),'BL':('Bayern','Dortmund'),
       'SA':('Inter','Milan'),'L1':('PSG','Marseille')}
class TestModel:
    classes_=('H','D','A')
    def predict_proba(self,rows):return [[.512,.273,.215] for _ in range(len(rows))]
class Sandbox:
    def __enter__(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'data').mkdir();(self.root/'artifacts').mkdir();self.states={}
        fixtures=[]
        for code,teams in TEAMS.items():
            (self.root/'artifacts'/f'model_{code}.joblib').touch()
            hist={team:[(3 if (i+j)%3==0 else 1 if (i+j)%3==1 else 0,1+(i+j)%3,(i+j)%2,3+(i+j)%4,1+(i+j)%3) for j in range(5)] for i,team in enumerate(teams)}
            self.states[code]={'teams':teams,'history':hist,'last_match':'2026-09-14','model':TestModel(),'model_name':'Testmodell',
                'event_history':{team:[{'total_goals':2+i%4,'goals_scored':1+i%3,'both_scored':1,'shots':2+i%6,'cards':i%5} for i in range(20)] for team in teams}}
            fixtures.extend([{'league':code,'home':teams[0],'away':teams[1],'utc_date':'2099-10-21T19:00:00Z','status':'TIMED','venue':'Test Arena','source':'synthetic test data','synced_at':'2099-09-01T00:00:00Z'},
                {'league':code,'home':teams[1],'away':teams[0],'utc_date':'2099-11-21T00:00:00Z','status':'SCHEDULED','venue':None,'source':'synthetic test data'},
                {'league':code,'home':teams[0],'away':teams[1],'utc_date':'2025-09-01T19:00:00Z','status':'FINISHED','score':{'home':2,'away':1},'source':'synthetic test data'}])
        for code in ('UCL','CDR','EL','FAC','UECL','DFB','CIT'):
            fixtures.append({'league':code,'home':'FC Barcelona','away':'Paris Saint-Germain FC' if code in ('UCL','EL','UECL') else 'Sevilla FC','utc_date':'2099-10-20T19:00:00Z','status':'TIMED','venue':None,'source':'synthetic test data'})
        (self.root/'data'/'fixtures.json').write_text(json.dumps({'fixtures':fixtures}))
        self.patches=[patch.object(web,'ROOT',self.root),patch.object(web,'get_state',side_effect=lambda code:self.states[code]),patch.object(web,'PUBLIC_SITE',False)]
        for p in self.patches:p.start()
        self.client=web.app.test_client();return self
    def __exit__(self,*args):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
