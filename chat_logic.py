"""Routing and evidence for the current question, independent of presentation."""
import math
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from football import LEAGUES, clean_name, find_teams, team_display, recent_form
from fixtures import CUP_NAMES, CUP_ALIASES, read_fixtures, normalize_team, fixture_time, fixture_public, display_fixture_date


def language_of(message, history=None):
    plain=clean_name(message)
    if re.search(r'\b(what|when|where|which|who|why|how|predict|prediction|shots on target|yellow cards|thanks|thank|hello|hi|hey|explain|away|goals|injured|will|draw|please)\b', plain) and not re.search(r'\b(vad|nar|varfor|hur|vem|vilken|tror|tack|mal|skott)\b', plain):
        return 'en'
    if plain in ('ok','okay','btts','xg') and history:
        return language_of(history[-1].get('question',''))
    return 'sv'


def text(value, context=None, language='sv', **extra):
    return {'kind':'text','response':value,'context':context,'league':(context or {}).get('league'),'language':language,**extra}


def resolve(message, context, web):
    """Return named clubs in text order; context is used only for unnamed clubs."""
    hits=[]
    for code in LEAGUES:
        if web.model_path(code).exists():
            found=find_teams(message, web.get_state(code)['teams'], code)
            hits.extend((code,team) for team in found)
    if len(hits)==2 and hits[0][0]!=hits[1][0]:
        # find_teams across competitions loses order; aliases determine positions.
        from football import ALIASES
        plain=clean_name(message)
        def position(item):
            code,team=item
            aliases=[team]+[a for a,c in ALIASES[code].items() if c==team]
            positions=[m.start() for a in aliases for m in re.finditer(r'\b'+re.escape(a)+r'\b',plain)]
            return min(positions,default=999)
        hits.sort(key=position)
    explicit=[]
    plain=clean_name(message)
    # Longest competition names win: Europa Conference League is not Europa League.
    for code,names in CUP_ALIASES.items():
        if any(re.search(r'\b'+re.escape(n)+r'\b',plain) for n in names):explicit.append(code)
    for code,meta in LEAGUES.items():
        if clean_name(meta['name']) in plain:explicit.append(code)
    if len(hits)==2:
        home,away=hits
        if re.search(r'\b(?:borta|away)\s+(?:mot|against|at|hos)\b',plain) or re.search(r'\bat\b',plain):
            home,away=away,home
        code=explicit[0] if len(explicit)==1 else home[0] if home[0]==away[0] else 'UCL'
        return {'league':code,'home':home[1],'away':away[1]},hits,explicit
    if len(hits)==1:
        code,team=hits[0]
        if context and context.get('league') in (code,*CUP_NAMES) and team in (normalize_team(context.get('home') or '',context['league']),normalize_team(context.get('away') or '',context['league'])):
            return dict(context),hits,explicit
        return {'league':explicit[0] if len(explicit)==1 else code,'home':team,'away':None},hits,explicit
    if context and context.get('league') in (*LEAGUES,*CUP_NAMES):
        ctx=dict(context)
        if len(explicit)==1 and explicit[0]!=ctx['league']:
            ctx={'league':explicit[0],'home':None,'away':None}
        return ctx,hits,explicit
    return {'league':explicit[0],'home':None,'away':None} if len(explicit)==1 else None,hits,explicit


def evidence(context, hits, web):
    result={'teams':[], 'missing':['xG','lineups','injuries','player availability','tactical event data','second-half statistics'], 'prediction':None}
    if not context:return result
    result['competition']=CUP_NAMES.get(context['league'],LEAGUES.get(context['league'],{}).get('name'))
    targets=[t for t in (context.get('home'),context.get('away')) if t]
    for target in targets:
        for code in LEAGUES:
            if not web.model_path(code).exists():continue
            saved=web.get_state(code)
            key=normalize_team(target,context['league'])
            if key not in saved.get('teams',[]):continue
            games=saved.get('history',{}).get(key,[])
            snap=recent_form(games)
            row={'name':team_display(key,code),'league':code,'as_of':saved.get('last_match'),
                 'matches':len(games),'goals_for':sum(x[1] for x in games),'goals_against':sum(x[2] for x in games),
                 'points':sum(x[0] for x in games),'shots_on_target':snap['shots_on_target'],'yellow_cards':snap['yellow_cards']}
            result['teams'].append(row)
            break
    return result


def schedule_answer(message,ctx,hits,web,lang):
    plain=clean_name(message);code=ctx['league'];home,away=ctx.get('home'),ctx.get('away')
    named={t for _,t in hits}
    if len(hits)==1: home,away=hits[0][1],None
    rows=[f for f in read_fixtures(web.ROOT) if f['league']==code]
    def involved(f):
        pair=(normalize_team(f['home'],code),normalize_team(f['away'],code))
        if home and away:return set(pair)=={normalize_team(home,code),normalize_team(away,code)}
        return not home or normalize_team(home,code) in pair
    rows=[f for f in rows if involved(f)]
    now=datetime.now(timezone.utc)
    past=bool(re.search(r'\b(slutade|vann|resultatet|finished|won|ended|result|spelades|igar|yesterday)\b',plain))
    if re.search(r'\bdid\b.*\bfinish\b',plain):past=True
    date_match=re.search(r'\b(20\d{2}-\d{2}-\d{2})\b',message)
    target_day=None
    if date_match:
        try:target_day=datetime.fromisoformat(date_match[1]).date()
        except ValueError:return text('Datumet är ogiltigt.' if lang=='sv' else 'That date is invalid.',ctx,lang)
    if re.search(r'\b(imorgon|tomorrow)\b',plain):target_day=now.astimezone(ZoneInfo('Europe/Stockholm')).date()+timedelta(days=1)
    if re.search(r'\b(idag|today)\b',plain):target_day=now.astimezone(ZoneInfo('Europe/Stockholm')).date()
    if re.search(r'\b(igar|yesterday)\b',plain):target_day=now.astimezone(ZoneInfo('Europe/Stockholm')).date()-timedelta(days=1)
    if target_day:rows=[f for f in rows if (fixture_time(f).astimezone(ZoneInfo('Europe/Stockholm')) if f['status']!='SCHEDULED' else fixture_time(f)).date()==target_day]
    if past:rows=[f for f in rows if f['status']=='FINISHED']
    else:rows=[f for f in rows if f['status'] in ('TIMED','SCHEDULED','POSTPONED','IN_PLAY','PAUSED') and (fixture_time(f)>=now or fixture_time(f).date()==now.date() or f['status']=='POSTPONED')]
    rows.sort(key=fixture_time,reverse=past)
    exact=[f for f in rows if home and away and normalize_team(f['home'],code)==normalize_team(home,code)]
    if exact:rows=exact
    if not rows:
        pair=' – '.join(team_display(t,code) if code in LEAGUES else t.title() for t in (home,away) if t)
        time_note=(' det datumet' if lang=='sv' else ' on that date') if target_day else ''
        return text((f'Jag hittar ingen {"registrerad spelad" if past else "kommande"} match{time_note} för {pair or CUP_NAMES.get(code,LEAGUES.get(code,{}).get("name","tävlingen"))} i det hämtade schemat.' if lang=='sv' else f'No {"completed" if past else "upcoming"} match{time_note} for {pair or "this competition"} is available in the downloaded schedule.'),ctx,lang)
    chosen=rows[:5] if not (home and away) else rows[:1]
    selected=chosen[0];note=''
    if home and away and not exact:
        note=(f'I schemat är {selected["home"]} hemmalag.' if lang=='sv' else f'The schedule lists {selected["home"]} at home.')
    if selected['status']=='POSTPONED':
        return text((f'{selected["home"]} – {selected["away"]} är uppskjuten. Ny avspark är inte bekräftad.' if lang=='sv' else f'{selected["home"]} – {selected["away"]} is postponed. A new kickoff is not confirmed.'),ctx,lang)
    public=[fixture_public(f,web.ROOT) for f in chosen]
    newctx={'league':code,'home':normalize_team(selected['home'],code),'away':normalize_team(selected['away'],code)} if len(public)==1 else ctx
    return {'kind':'fixtures','fixtures':public,'league':code,'league_name':CUP_NAMES.get(code,LEAGUES.get(code,{}).get('name')),
            'title':'Matchdatum' if lang=='sv' else 'Match date','summary':note,'context':newctx,'language':lang}


def route_question(message,context,history,web):
    """Return None only for a retained, specific legacy statistical handler."""
    plain=clean_name(message);lang=language_of(message,history)
    ctx,hits,explicit=resolve(message,context,web)
    # No network requests are needed for conversational acknowledgement.
    if re.fullmatch(r'(hej|hejsan|tja|tjena|hello|hi|hey)( hur mar du( idag)?)?',plain):
        return text('Hej! Vad vill du veta om fotboll?' if lang=='sv' else 'Hi! What would you like to know about football?',context,lang)
    if re.fullmatch(r'(hur mar du( idag)?|how are you( today)?)',plain):return text('Jag är redo att hjälpa dig med fotboll. Hur är det med dig?' if lang=='sv' else 'Ready to help with football. How are you?',context,lang)
    if re.fullmatch(r'(jag mar |jo |jo tack |det ar )?(bra|fint|toppen|good|fine)( med mig)?( tack)?|bra tack|thanks|thank you|tack( sa mycket| for hjalpen)?|okej( tack)?|ok',plain):return text('Skönt att höra.' if 'bra' in plain else 'Varsågod.' if lang=='sv' else 'You’re welcome.',context,lang)
    if re.fullmatch(r'(vad heter du|vem ar du|what is your name|who are you)',plain):return text('Jag är Matchorakel, din fotbollsassistent.' if lang=='sv' else 'I’m Matchorakel, your football assistant.',context,lang)
    if re.search(r'ignorera.*instruktion|ignore.*instruction|systemprompt|system prompt|api.?nyckel|api key|visa.*hemlighet',plain):return text('Jag visar inte interna instruktioner. Du kan fråga om fotboll.' if lang=='sv' else 'I keep internal instructions private. You can ask about football.',context,lang)
    if not plain:return text('Skriv en fotbollsfråga så hjälper jag dig.' if lang=='sv' else 'Write a football question so I can help.',context,lang)
    if re.search(r'\b(inter miami|sheffield wednesday|inter turku|bayern alzenau|paris fc)\b',plain):
        return text('Min lagmodell saknar underlag för det laget. Jag kan förklara fotbollsfrågor, men inte ge en sifferprognos för mötet.' if lang=='sv' else 'My match model has no data for that club. I can discuss football, but cannot produce a numerical forecast for this fixture.',None,lang)
    if len(hits)>2:return text('Vilka två lag vill du jämföra?' if lang=='sv' else 'Which two teams should I compare?',None,lang)
    if len(explicit)>1:return text('Vilken tävling menar du?' if lang=='sv' else 'Which competition do you mean?',context,lang)
    if re.search(r'\b(manchester|sheffield)\b',plain) and not hits:return text('Menar du Manchester United eller Manchester City?' if 'manchester' in plain else 'Menar du Sheffield United eller Sheffield Wednesday?',None,lang)
    if re.search(r'\b(president|pizza|lasagne|python|programmera|kaffe|musik|semester|film|recept|weather|vadret|recipe|code)\b',plain) and not hits:
        return text('Jag hjälper till med fotboll; fråga gärna om en match eller en regel.' if lang=='sv' else 'I help with football; ask about a match or a rule.',None,lang,topic_reset=True)
    if re.search(r'\b(menade|istallet for)\b',plain) and context:return None
    if ctx and len(hits)==1 and ctx.get('home') and ctx.get('away') and re.search(r'\b(borta|away|hemma|home)\b',plain):
        target=hits[0][1]
        want_away=bool(re.search(r'\b(borta|away)\b',plain))
        if (ctx.get('away') if want_away else ctx.get('home'))!=target:ctx['home'],ctx['away']=ctx['away'],ctx['home']
    if ctx and not hits and re.search(r'andra matchen|other match|second match',plain):return text('Vilka lag spelar den andra matchen?' if lang=='sv' else 'Which teams are playing in the other match?',ctx,lang)
    # Validate client context against the current dataset, never trust arbitrary names.
    if ctx and ctx['league'] in LEAGUES:
        if not web.model_path(ctx['league']).exists():return text('Matchmodellen för ligan saknas på servern.' if lang=='sv' else 'The league model is unavailable on this server.',None,lang)
        known=web.get_state(ctx['league'])['teams']
        for field in ('home','away'):
            if ctx.get(field) and normalize_team(ctx[field],ctx['league']) not in known:ctx[field]=None
    if re.search(r'vinner (ligan|premier league|la liga|bundesliga|serie a|ligue 1)|wins? (?:the )?(league|premier league|la liga)',plain):
        return text('Jag saknar en modell för ligavinnare och aktuell tabell med återstående matcher. Mina prognoser gäller enskilda matcher.' if lang=='sv' else 'I have no league-winner model or current table with remaining fixtures. My predictions cover individual matches.',ctx,lang)
    forecast_query=bool(re.search(r'\b(vinner|prognos|prediction|predict|prediktion|slutar|slutresultat|tippar|tippa|resultattips|vinstchans|win|wins|scoreline|forecast|will.*end)\b',plain) or plain in ('vad tror du','vad tror du da','what do you think','hur manga mal da') or re.search(r'hur manga mal (blir|tror)|samma sak|same (match|prediction)|how many goals (will|do you)|hur manga mal gor',plain))
    if re.search(r'\bvad (tror|tippar) du$',plain):forecast_query=True
    schedule_query=bool(re.search(r'\b(spelades|nar|when|where|datum|date|avspark|kickoff|arena|venue|stadium|stadion|spelschema|schedule|kommande|upcoming|imorgon|tomorrow|idag|today|slutade|vann|finished|won|result|igar|yesterday)\b|\bvar spelas\b|\bvar spelar\b|\bvilken tid\b|\bnasta match',plain))
    if re.search(r'press|anfall|attack|defend|forsvar',plain) and not re.search(r'datum|avspark|kickoff|arena|venue|tomorrow|imorgon',plain):
        schedule_query=False
    if schedule_query:
        if ctx:return schedule_answer(message,ctx,hits,web,lang)
        return text('Vilket lag eller vilken tävling menar du?' if lang=='sv' else 'Which club or competition do you mean?',None,lang)
    facts=evidence(ctx,hits,web)
    targets=facts['teams']
    if len(hits)==1:targets=[r for r in targets if normalize_team(r['name'],r['league'])==hits[0][1]]
    prediction=None
    pair=bool(ctx and ctx.get('home') and ctx.get('away'))
    if pair and ctx['league'] in LEAGUES:
        try:prediction=web.predict_match(ctx['home'],ctx['away'],ctx['league'])
        except (ValueError,KeyError):prediction=None
    if prediction:
        facts['prediction']={k:prediction[k] for k in ('home','away','scoreline','probabilities','goal_markets','as_of')}
    from football import ALIASES
    remainder = plain
    club_names = [alias for code,team in hits for alias in [team,*[a for a,t in ALIASES[code].items() if t==team]]]
    for name in sorted(club_names,key=len,reverse=True):
        remainder=re.sub(r'\b'+re.escape(name)+r'\b',' ',remainder)
    for code in explicit:
        for name in CUP_ALIASES.get(code,(clean_name(LEAGUES.get(code,{}).get('name','')),)):
            if name:remainder=re.sub(r'\b'+re.escape(name)+r'\b',' ',remainder)
    remainder=re.sub(r'\b(mot|vs|v|moter|hemma|borta|home|away|at|against|och|and|i|in|fc|cf)\b',' ',remainder).strip()
    typo_only = bool(remainder) and all(any(find_teams(word,web.get_state(code)['teams'],code) for code,_ in hits) for word in remainder.split())
    short_pair=pair and len(hits)==2 and (not remainder or typo_only)
    if (forecast_query or short_pair) and not re.search(r'\b(skott|shots|kort|cards|malskytt|scorer|injured|skadad)\b|vem.*gor mal|who.*score',plain):
        if not pair:return text('Vilka två lag vill du ha en prediction för?' if lang=='sv' else 'Which two clubs should I predict?',ctx,lang)
        if ctx['league'] in CUP_NAMES:
            cup_fixture = next((f for f in read_fixtures(web.ROOT) if f['league']==ctx['league'] and normalize_team(f['home'],ctx['league'])==normalize_team(ctx['home'],ctx['league']) and normalize_team(f['away'],ctx['league'])==normalize_team(ctx['away'],ctx['league']) and f['status'] in ('TIMED','SCHEDULED') and fixture_time(f)>datetime.now(timezone.utc)), None)
            match = cup_fixture or {'league':ctx['league'],'home':ctx['home'],'away':ctx['away'],'utc_date':None,'status':None}
            answer=web.ucl_evidence([match], 'hur slutar matchen',ctx['league'])
            if answer.get('cards') and answer['cards'][0].get('value'):
                answer['response']='Prediction: '+answer['cards'][0]['value']+'. '+('Grov uppskattning från ligahistorik; cupstyrka och startelvor saknas.' if lang=='sv' else 'Rough estimate from domestic history; cup strength and lineups are unavailable.')
            answer['context']=ctx;answer['language']=lang
            return answer
        if not prediction:return text('Jag saknar tillräcklig matchhistorik för en sifferprognos för båda lagen.' if lang=='sv' else 'There is not enough match history for a numerical prediction for both clubs.',ctx,lang)
        prediction.update(kind='prediction',context=ctx,language=lang)
        score=prediction['scoreline'];prediction['response']=f'Prediction: {prediction["home"]} {score["home"]}–{score["away"]} {prediction["away"]}.'
        f=prediction['features'];home,away=prediction['home'],prediction['away']
        if lang=='sv':prediction['explanation']=f'{home} har gjort {f["home_scored"]} och släppt in {f["home_conceded"]} mål på de senaste fem ligamatcherna; {away} har gjort {f["away_scored"]} och släppt in {f["away_conceded"]}. '
        else:prediction['explanation']=f'{home} scored {f["home_scored"]} and conceded {f["home_conceded"]} in the last five league matches; {away} scored {f["away_scored"]} and conceded {f["away_conceded"]}. '
        extra=prediction.get('additional_factors') or {}
        if 'home_elo' in extra:
            prediction['explanation']+=(f'Även lagstyrka över längre tid och vilodagar ingår.' if lang=='sv' else 'Longer-term team strength and rest days also enter the model.')
        elif 'hemmaplan' in prediction['model']:
            prediction['explanation']+=('Modellen väger även in tidigare hemma- och bortamatcher.' if lang=='sv' else 'The model also uses previous home and away performances.')
        else:prediction['explanation']+=('Valideringen valde modellen med kortare formhistorik.' if lang=='sv' else 'Validation selected the model with recent form history.')
        if not prediction.get('fixture'):prediction['explanation']+=(' Mötesdatumet är inte bekräftat i mitt schema.' if lang=='sv' else 'The fixture date is not confirmed in my schedule.')
        return prediction
    metric='shots_on_target' if re.search(r'\b(skott|shots|avslut)\b',plain) else 'yellow_cards' if re.search(r'\b(kort|cards|varningar)\b',plain) else None
    player_question=bool(re.search(r'\b(raphinha|lewandowski|haaland|mbappe|salah|yamal|spelare|player|scorer|malskytt)\b|vem.*gor mal|who.*score',plain))
    if player_question or re.search(r'\b(skadad|skador|injured|injuries|avstangd|suspended|lineups|startelva)\b',plain):
        # Retain optional player CSV handling for explicit shots/cards.
        if metric and not re.search(r'skada|injur|avstang',plain) and ctx and ctx['league'] in LEAGUES:return None
        if re.search(r'\b(om|if)\b',plain):
            explanation='Om den spelaren saknas kan laget behöva ändra anfallsvägar och fördela avsluten annorlunda. Jag har ingen bekräftad frånvaro eller ersättarstatistik, så prognossiffrorna ändras inte.' if lang=='sv' else 'If that player is absent, attacking routes and shot distribution may change. Absence and replacement data are unverified, so the numerical prediction stays unchanged.'
        else:explanation='Jag saknar aktuell spelarhistorik, startelva och förväntade minuter för att välja en målskytt. Lagets målprognos räcker inte för att fördela målchanser mellan spelare.' if lang=='sv' else 'Current player history, lineups and expected minutes are missing, so I cannot pick a scorer from the team goal forecast alone.'
        return text(explanation,ctx,lang)
    if metric and targets and not re.search(r'\b(over|under|minst|far|blir|kommer|will|at least)\b',plain):
        label=('skott på mål' if metric=='shots_on_target' else 'gula kort') if lang=='sv' else ('shots on target' if metric=='shots_on_target' else 'yellow cards')
        lines=[]
        for row in targets:
            stat=row[metric]
            if stat and stat['matches']:
                avg=round(stat['total']/stat['matches'],1)
                lines.append(f'{row["name"]}: {stat["total"]} {label} på {stat["matches"]} registrerade matcher ({avg} per match).' if lang=='sv' else f'{row["name"]}: {stat["total"]} {label} in {stat["matches"]} recorded matches ({avg} per match).')
            else:lines.append(f'{row["name"]}: {label} saknas i underlaget.' if lang=='sv' else f'{row["name"]}: {label} are unavailable.')
        return text(' '.join(lines),ctx,lang)
    if re.search(r'\b(andra halvlek|second half|first half|forsta halvlek)\b',plain):return text('Jag har helmatchdata men ingen separat halvleksmodell. Helmatchens målprognos kan inte delas jämnt mellan halvlekarna.' if lang=='sv' else 'I have full-match data but no half-specific model. The full-match goal forecast cannot simply be split in half.',ctx,lang)
    advanced=bool(re.search(r'\b(offside|press|pressmonster|pressing|formation|taktik|tactics|transfers?|tranare|coach|tabell|table|xg|bollinnehav|possession|regler|rules|frispark|falsk nia|counterattack|omstallning)\b',plain))
    if advanced or not ctx:
        explanation=web.general_answer(message,facts,history)
        if explanation:return text(explanation,ctx,lang)
        from language_chat import request_error
        reason=request_error.get() or {}
        return {'kind':'error','error':('AI-tjänstens tillfälliga gräns är nådd. Försök igen senare.' if reason.get('code')==429 else 'AI-svaret kunde inte hämtas. Försök igen.') if lang=='sv' else 'The AI answer is unavailable. Please try again.','context':ctx,'language':lang}
    # Known statistics preserve the existing feature implementation.
    if lang=='sv' and (metric or re.search(r'\b(form|mal|poang|varfor|forsvar|inslappta|nollan|anfall|utvardering|log loss|brier|vanligast|sakrast|lapp|speltips)\b',plain)):
        return None
    explanation=web.general_answer(message,facts,history)
    if explanation:return text(explanation,ctx,lang)
    return {'kind':'error','error':'AI-svaret kunde inte hämtas. Försök igen.' if lang=='sv' else 'The AI answer is unavailable. Please try again.','context':ctx,'language':lang}
