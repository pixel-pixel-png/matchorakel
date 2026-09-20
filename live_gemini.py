"""Opt-in real Gemini tests. Uses only the server's existing environment key.
Run locally on the configured server: python -m qa.live_gemini --limit 5
Successful responses are cached by prompt+model+instructions. Never logs secrets.
"""
import argparse,hashlib,json,os,time
from pathlib import Path
from language_chat import general_answer,build_payload,request_error
QUESTIONS=['Vad är offside?','Explain offside.','Vad betyder hög press?','Förklara en falsk nia.','Vad innebär xG?',
 'What is counterpressing?','Vad är en omställning?','Hur fungerar zonförsvar?','Hur fungerar manmarkering?',
 'Vad skiljer en ytter från en ytterback?','Vad gör en defensiv mittfältare?','Vad är skillnaden mellan skott och skott på mål?',
 'Varför hjälper spelbredd?','Vad är ett lågt försvarsblock?','Förklara överlapp på kanten.','What is an underlap?',
 'Varför är restförsvar viktigt?','Hur påverkar ett rött kort lagets organisation?','Vad innebär att spela mellan lagdelarna?',
 'Hur kan en anfallare hjälpa till i pressen?','Förklara andrabollar.','Vad betyder halvutrymme?',
 'När används en kort hörna?','What is a through ball?','Hur försvarar man en ledning?',
 'Vad betyder att stänga passningsvägar?','Varför lockar lag fram press?','Hur hjälper en målvakt speluppbyggnaden?',
 'Vad är en målspark?','Vilka risker finns med hög backlinje?']

def main():
 p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=5);p.add_argument('--pause',type=float,default=12);a=p.parse_args()
 if not os.environ.get('GEMINI_API_KEY','').strip():raise SystemExit('GEMINI_API_KEY saknas här. Sätt den direkt i servermiljön; dela den inte i chatten.')
 dest=Path('qa/results/live');dest.mkdir(parents=True,exist_ok=True);count=0
 for question in QUESTIONS:
  model,payload=build_payload(question,{'missing':['current statistics','injuries','lineups']},[])
  digest=hashlib.sha256(json.dumps([model,payload],sort_keys=True).encode()).hexdigest();path=dest/(digest+'.json')
  if path.exists():continue
  if count>=max(1,min(a.limit,30)):break
  answer=general_answer(question,{'missing':['current statistics','injuries','lineups']},[])
  record={'question':question,'model':model,'answer':answer,'error':request_error.get(),'manual_review_required':True}
  path.write_text(json.dumps(record,ensure_ascii=False,indent=2));print(question,'OK' if answer else 'FAILED');count+=1
  if not answer:break  # Do not consume the quota repeatedly after a failure.
  if count<a.limit:time.sleep(max(10,a.pause))
if __name__=='__main__':main()
