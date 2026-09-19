"""Manuell stresskontroll: 195 trestegsamtal med ett konstgjort schema.

Utfall märkt fri_chatt är en saknad språkmodell, inte ett trasigt API.
Kör inifrån matchorakel-mappen: py tests/manual_adversarial.py
"""
import sys
from pathlib import Path
project=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(project),str(project/'tests')]
from unittest.mock import patch
from test_chat import ChatTests

social=[
 'Hur lagar jag lasagne?', 'Kan du förklara Newtons andra lag?', 'Hur räknar jag derivatan av x^2?',
 'Jag ska resa till Spanien, har du tips?', 'Vad kan jag göra i helgen?', 'Skriv en dikt om hösten.',
 'Förklara en variabel i Python.', 'Vad är ett svart hål?', 'Hur fungerar en motor?',
 'Jag gillar pizza, gör du det?', 'Vad är det roligaste du vet?', 'Ge mig ett recept på pannkakor.',
 'Vad är skillnaden mellan kapital och intäkt?', 'Kan du hjälpa mig skriva ett CV?',
 'Förklara integraler som för en nybörjare.', 'Vilket är ditt favoritdjur?',
 'Ge mig tre idéer till min födelsedag.', 'Vad är en atom?', 'Hur tar man hand om en växt?',
 'Hur lär jag mig spanska?', 'Vad menas med opportunity cost?', 'Hur funkar en dator?',
 'Kan vi skriva en berättelse tillsammans?', 'Hur hittar jag motivation?',
 'Har du hört en bra låt nyligen?', 'Vad är ett bra mellanmål?', 'Säg något uppmuntrande.',
 'Hur tar jag mig till universitetet?', 'Vad bör jag laga till middag?',
 'Kan du hjälpa mig öva inför tentan?', 'Lär mig några ord på franska.',
 'Hur börjar jag träna på gymmet?', 'Vad är din åsikt om filmen?',
 'Jag såg en hund idag, vill du höra?', 'Kan vi prata om rymden?',
 'Vad är en primtal?', 'Hur blir jag bättre på att skriva?',
 'Hur många minuter är två timmar?', 'Vad heter Sveriges huvudstad?',
 'Hjälp mig planera en pluggdag.', 'Hur mår du när du är ledsen?',
 'Jag fick en gåva av min vän.', 'Berätta om en intressant bok.',
 'Kan du ge mig ett skämt om skolan?', 'Vad är ett isberg?',
]
venues=[
 'Vilken arena spelar Sevilla mot Barcelona på?', 'Vad heter arenan i Sevilla-Barca?',
 'Var går Sevilla och Barcelona av stapeln?', 'I vilken stadion spelar Sevilla hemma mot Barcelona?',
 'Är Sevilla-Barça på Sánchez-Pizjuán?', 'Sevilla vs Barcelona, arena?',
 'Sevilla-Barca imorgon, var spelar de?', 'Vad är spelplatsen för Sevilla mot Barcelona?',
 'Visa stadion för matchen Sevilla Barcelona.', 'På vilken plan spelar Sevilla och Barcelona?',
 'Sevillas hemmamatch mot Barça, vilken arena?', 'Kan du säga arenan för Sevilla Barcelona?',
 'Arenan för matchen med Sevilla hemma och Barca borta?', 'Är det Camp Nou i Sevilla-Barcelona?',
 'Var spelar Sevilla sin hemmamatch mot Barca?', 'Hemmaarenan inför Sevilla mot Barcelona?',
 'Sevilla Barcelona: spelplats?', 'Sevilla FC mot FC Barcelona, var?',
 'Vilken plats hålls Sevilla Barcelona?', 'På vilken arena är Sevilla-Barca-matchen?',
]
dates=[
 'När är Sevilla Barcelona?', 'När går avspark Sevilla-Barcelona?',
 'Vad är klockan för Sevilla mot Barca?', 'Vilken dag är Sevilla-Barcelona?',
 'När spelar Sevilla FC mot FC Barcelona?', 'Sevilla mot Barca, vilket datum?',
 'När går mötet Sevilla mot Barça?', 'Kan du ge starttiden för Sevilla Barcelona?',
 'Spelas Sevilla Barcelona imorgon?', 'Sevilla hemma mot Barca: när?',
 'Datum för Sevilla-Barcelona tack.', 'Vilken tid börjar Sevilla mot Barcelona?',
 'Sevilla vs Barcelona kommande matchdatum?', 'Dags för Sevilla mot Barca när?',
 'Sevilla-Barcelona, avspark?', 'Vilken kväll möts Sevilla och Barcelona?',
 'När spelar Sevilla och Barcelona sin match?', 'När är deras match: Sevilla Barcelona?',
 'Tid och datum för Sevilla mot Barcelona.', 'Sevilla möter Barça hemma, när sker det?',
]
switch=[
 'Nu vill jag fråga om Sevilla mot Barcelona i La Liga.',
 'Vi pratade om UCL men nu gäller Sevilla mot Barcelona.',
 'Byt till La Liga: Sevilla hemma mot Barça.',
 'Jag menade Sevilla mot Barcelona i spanska ligan.',
 'Nej inte Champions League, utan Sevilla mot Barcelona.',
 'Nu menar jag Barcelona mot Sevilla i ligan.',
 'Ta Sevilla Barcelona som en La Liga match.',
 'Varför blandar du in UCL när jag skriver Sevilla-Barcelona?',
 'Släpp CL, titta på Sevilla mot Barcelona.',
 'Jag frågar om liga, Sevilla vs Barca.',
 'Kan vi gå vidare med Sevilla-Barcelona i La Liga?',
 'Glöm PSG, nu spelar Sevilla mot Barcelona.',
 'UCL är klart. Nästa fråga gäller Sevilla och Barça.',
 'Nu gäller ligamatchen mellan Sevilla och Barcelona.',
 'Det är Sevilla som har hemmaplan mot Barcelona i La Liga.',
]
compound=[
 'Barcelona mot Real Madrid, vem vinner och vilka får gula kort?',
 'Vem vinner Sevilla mot Barca och varför?',
 'Hur många mål blir det i Sevilla Barca och hur många kort?',
 'Barcelona mot Madrid: odds och vad tror du om korten?',
 'Sevilla mot Barcelona, när spelas den och på vilken arena?',
 'Vem vinner Real Madrid mot Barcelona och hur är lagens form?',
 'Hur är Barcelonas form och hur många kort har de fått?',
 'Barcelona möter Sevilla, vem vinner och blir det över 2,5 mål?',
 'Sevilla mot Barca: vad är säkrast och när går matchen?',
 'Förklara modellen för Barcelona Madrid och hur säkra är resultaten?',
 'Inter mot Milan, vem vinner och vad är arenan?',
 'Hur många skott på mål för Barcelona och hur många gula kort?',
 'Sevilla Barcelona vem vinner och vad tycker du om min tentaplugg?',
 'Barca Madrid: vinnare, mål och kort?',
 'Vad är datumet och vad brukar hända med kort i Sevilla Barcelona?',
 'Hur ser Sevilla Barcelonas form ut och vem vinner?',
 'Vem vinner Barca Madrid och hur många mål blir det?',
 'Sevilla mot Barcelona, vem vinner och får Raphinha skott på mål?',
 'Barcelona Madrid: varför vinner de och vad säger historiken?',
 'Vilken arena är det för Sevilla Barca och hur är lagens form?',
]
social.extend(['Vad innebär demokrati?', 'Varför regnar det?', 'Hur kokar man ris?', 'Kan du skriva ett tackbrev?', 'Jag har börjat ett nytt jobb.', 'Hur många planeter har solsystemet?', 'Lär mig ett ord på japanska.', 'Kan du berätta en saga?', 'Vad borde jag se för film?', 'Vad är en algoritm?', 'Vad händer med ett batteri när det laddas?', 'Jag är nervös inför intervjun.', 'Vad betyder inflation?', 'Vad händer om jag blandar vatten och olja?', 'Hur sköter man en cykel?', 'Vad ska jag ge min vän i present?', 'Förklara Pythagoras sats.', 'Jag känner mig uttråkad.', 'Kan du hjälpa mig skriva ett personligt brev?', 'Varför är havet salt?', 'Hur sorterar man papper?', 'Berätta en gåta.', 'Vad är ditt favoritämne?', 'Ge mig ett träningspass för armar.', 'Kan du översätta hej till spanska?', 'Hur lär jag mig programmera?', 'Hur skriver man en uppsats?', 'Vad är stress?', 'Hur länge ska potatis koka?', 'Jag älskar att rita.', 'Hur räknar jag procent?', 'Vad är ett företag?', 'Hur fungerar fotosyntesen?', 'Skriv en födelsedagshälsning.', 'Kan vi prata om min katt?', 'Jag vill starta ett företag.', 'Vad är en ETF?', 'Kan du visa mig en gåta om matematik?', 'Vad betyder budget?', 'Ge mig ett rim på skola.', 'Hur fungerar växthuseffekten?', 'Varför blir löv gula?', 'Jag har svårt att sova.', 'Berätta om astronomi.', 'Hur skriver jag ett CV?', 'Vilket djur kan flyga högst?', 'Varför har vi årstider?', 'Vad är en vektor?', 'Kan du hjälpa mig med en presentation?', 'Hur pluggar man till en tenta?', 'Vilken bok borde jag läsa?', 'Vad är ett ordspråk?', 'Kan du skriva ett SMS till min vän?', 'Hur gör man en omelett?', 'Vad gör du på fritiden?', 'Vad är ett derivat?', 'Förklara Newtons lagar för mig.', 'Varför är is hal?', 'Hur håller jag ordning hemma?', 'Vad betyder balansräkning?', 'Hur hittar jag en bra hobby?', 'Jag blir orolig av nyheter.', 'Vad är klockan i Tokyo?', 'Hur lång är en kilometer?', 'Kan du hjälpa mig skriva en sång?', 'Jag fick ett meddelande från min kompis.', 'Vad händer när vatten fryser?', 'Vad är skillnaden mellan massa och vikt?', 'Hur räknas lön efter skatt?', 'Varför ler människor?', 'Lär mig grunderna i Excel.', 'Kan vi tala om min semester?', 'Vad är en jordbävning?', 'Ge mig en idé till middag med pasta.', 'Kan du berätta en rolig historia?'])
scenarios=[]
for label, prompts in [('fri_chatt',social),('arena',venues),('datum',dates),('ligabyte',switch),('flera_fragor',compound)]:
 for prompt in prompts: scenarios.append((label,prompt))
assert len(scenarios)>=190
results=[]
with patch('language_chat.ollama_model',return_value=None):
 t=ChatTests('test_compound_question_and_friend_chat');t.setUp()
 for label,prompt in scenarios:
  first=t.ask('Vilka är kommande UCL matcher?')
  second=t.ask(prompt,first.get('context'))
  third=t.ask('Jag mår bra tack',second.get('context') if not second.get('topic_reset') else None)
  full=' '.join(str(second.get(key,'')) for key in ('response','title','summary'))
  if label=='fri_chatt': issue=('fri konversation kräver' in full.lower() or second.get('league')=='UCL')
  elif label=='arena': issue=not (second.get('kind') in ('fixtures','combined','text') and (second.get('fixtures') and any(x.get('venue') for x in second['fixtures']) or 'sánchez-pizjuán' in full.lower() or second.get('kind')=='combined' and any(part.get('fixture') or part.get('fixtures') for part in second.get('parts',[]))))
  elif label=='datum': issue=second.get('kind') not in ('fixtures','combined')
  elif label=='ligabyte': issue=(second.get('context') or {}).get('league')!='LL' and second.get('league')!='LL'
  else: issue=second.get('kind')!='combined'
  if 'skönt' not in third.get('response','').lower(): issue=True
  results.append((label,prompt,issue,second.get('kind'),second.get('league'),full[:100]))
 t.tearDown()
print('Conversations',len(results),'issues',sum(row[2] for row in results))
for label in ['fri_chatt','arena','datum','ligabyte','flera_fragor']:
 section=[r for r in results if r[0]==label]
 print(label, sum(r[2] for r in section),'/',len(section))
 for row in [r for r in section if r[2]][:5]:print(' ',row[1],' => ',row[3],row[4],row[5])
