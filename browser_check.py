"""Real Chromium, local Flask, five viewport sizes and interaction checks."""
import argparse,json,sys,threading,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright,expect
from werkzeug.serving import make_server,WSGIRequestHandler
from qa.support import Sandbox
import app as web
class Quiet(WSGIRequestHandler):
 def log(self,*args,**kwargs):pass

def run(round_id):
 findings=[];checks=[]
 with Sandbox(),sync_playwright() as pw:
  server=make_server('127.0.0.1',0,web.app,threaded=True,request_handler=Quiet);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{server.server_port}'
  browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
  for width in (360,390,768,1024,1440):
   context=browser.new_context(viewport={'width':width,'height':900},device_scale_factor=1,permissions=['clipboard-read','clipboard-write'])
   page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   try:
    page.goto(url);expect(page).to_have_title('Matchorakel');page.locator('#message').wait_for();page.evaluate('document.fonts.ready');
    assert page.locator('#sendButton').is_disabled()
    assert page.locator('.welcome-line').is_visible()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    assert page.locator('#message').evaluate('(e)=>getComputedStyle(e).fontSize')=='16px'
    assert not any(x in page.locator('body').inner_text() for x in ['Matchanalys','Fem ligor och cuper','Fråga i samma chatt','MATCHORAKEL'])
    page.locator('#message').fill('Barcelona mot Sevilla');page.locator('#message').press('Enter');expect(page.locator('.prediction-line')).to_contain_text('Prediction: Barcelona')
    assert page.locator('.question').count()==1
    page.locator('.response').hover();page.locator('.copy-button').first.click();expect(page.locator('.copy-button').first).to_have_text('Kopierat');assert 'Prediction:' in page.evaluate('navigator.clipboard.readText()')
    assert page.locator('#sendButton').is_disabled()
    assert page.locator('.followup').count()<=1
    page.wait_for_timeout(250);page.screenshot(path=f'qa/results/prediction-{round_id}-{width}.png')
    page.locator('#message').fill('Hur många gula kort har lagen fått?');page.locator('#message').press('Enter');expect(page.locator('.answer-text').last).to_contain_text('gula kort')
    assert not any('kort' in t.lower() for t in page.locator('.followup').all_text_contents())
    page.reload();expect(page.locator('.question')).to_have_count(2)
    if width<=720:page.locator('#openSidebar').click()
    page.locator('#openMatches').click();expect(page.locator('#toolPanel')).to_be_visible();expect(page.locator('.match-row').first).to_be_visible()
    page.locator('[aria-label="Sök lag"]').fill('zzzz');expect(page.locator('.match-list')).to_contain_text('Inga matcher')
    page.locator('[aria-label="Sök lag"]').fill('Barcelona');page.locator('.favorite-button').first.click();assert page.locator('.favorite-button[aria-pressed="true"]').count()>0
    page.locator('#closePanel').click();page.locator('#openAbout').click();expect(page.locator('#toolPanel')).to_contain_text('Premier League');page.keyboard.press('Escape');expect(page.locator('#toolPanel')).not_to_be_visible()
    page.locator('.conversation-more').first.click();page.get_by_role('button',name='Ta bort',exact=True).click();page.get_by_role('button',name='Ångra',exact=True).click();expect(page.locator('.question')).to_have_count(2)
    page.locator('#newChat').click();expect(page.locator('.question')).to_have_count(0)
    page.locator('#message').fill('hej');page.locator('#message').press('Shift+Enter');assert page.locator('#message').input_value()=='hej\n'
    page.locator('#message').evaluate("el=>el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',isComposing:true,bubbles:true}))");assert page.locator('.question').count()==0
    page.screenshot(path=f'qa/results/empty-{round_id}-{width}.png')
    page.locator('#message').fill('Förklara offside');page.locator('#message').press('Enter');expect(page.locator('.retry-button')).to_be_visible();page.locator('.retry-button').click();expect(page.locator('.retry-button')).to_be_visible();assert page.locator('.question').count()==1
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.wait_for_timeout(300)
    page.screenshot(path=f'qa/results/round-{round_id}-{width}.png')
    # Stop, Enter spam, late answers and switching conversation during a request.
    if int(str(round_id).split('-')[0])>=2:
     if width<=720:page.locator('#openSidebar').click()
     page.locator('#newChat').click()
     held=[]
     page.route('**/chat',lambda route:held.append(route))
     page.locator('#message').fill('En långsam fråga om fotboll');page.locator('#message').press('Enter')
     expect(page.locator('#sendButton')).to_have_attribute('aria-label','Stoppa svar')
     page.locator('#message').press('Enter');assert page.locator('.question').count()==1
     page.locator('#sendButton').click();expect(page.locator('.error-response')).to_contain_text('stoppades')
     if width<=720:page.locator('#openSidebar').click()
     page.locator('#newChat').click();expect(page.locator('.question')).to_have_count(0)
     for route in held:
      try:route.fulfill(status=200,json={'kind':'text','response':'Ett försenat svar.'})
      except Exception:pass
     page.unroute('**/chat');assert 'försenat' not in page.locator('#chatContent').inner_text()
     page.locator('#message').fill('hej');page.locator('#message').press('Enter');expect(page.locator('.answer-text')).to_contain_text('Hej!')
     # Separate tab deletes history: no storage-event feedback loop or resurrection.
     other=context.new_page();other.goto(url);other.evaluate("localStorage.setItem('matchorakel-conversations-v1','[]')")
     expect(page.locator('.question')).to_have_count(0);assert other.evaluate("JSON.parse(localStorage.getItem('matchorakel-conversations-v1')).length")==0
     other.close()
    if width<=720:page.locator('#openSidebar').click()
    page.get_by_role('link',name='Modellresultat',exact=True).click();expect(page.locator('h1')).to_contain_text('modellerna');assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.goto(url+'/saknas');expect(page.locator('h1')).to_contain_text('Sidan finns inte');page.get_by_role('link',name='Till chatten',exact=False).click()
    assert not errors,errors
    checks.append({'width':width,'passed':True,'checks':23})
   except Exception as e:
    findings.append({'width':width,'error':str(e)[:900],'console':errors});page.screenshot(path=f'qa/results/round-{round_id}-{width}-failure.png')
   finally:context.close()
  browser.close();server.shutdown();thread.join(3)
 report={'round':round_id,'checks':checks,'failures':findings};Path(f'qa/results/browser-{round_id}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2));return bool(findings)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--round',default='1');args=p.parse_args();sys.exit(run(args.round))
