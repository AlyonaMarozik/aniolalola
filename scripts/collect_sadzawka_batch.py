#!/usr/bin/env python3
"""Incremental botanical product collection. GitHub artifacts persist state, not git commits."""
import argparse
import json
import re
import time
import ssl
import socket
from urllib.error import HTTPError, URLError
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
import collect_sadzawka_catalog as core

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'catalog/exports/sadzawka-catalog-review.json'
QUEUE=ROOT/'catalog/exports/sadzawka-catalog-queue.json'
FIRST_GROUPS=('Bodziszki','Hosty','Paprocie','Piwonie')
BULK=re.compile(r'(?i)\b(?:\d+\s*(?:szt(?:uk)?|sadzonek|pack|pakiet)|zestaw|komplet|kolekcja|mix|mieszanka)\b')
GENERA={
    'Bodziszki':re.compile(r'^Geranium\\b',re.I),
    'Hosty':re.compile(r'^Hosta\\b',re.I),
    'Paprocie':re.compile(r'^(?:Adiantum|Asplenium|Arachniodes|Athyrium|Blechnum|Cyrtomium|Dryopteris|Polystichum|Polypodium|Osmunda|Matteuccia|Pteridium|Thelypteris|Onoclea|Woodsia|Cystopteris|Gymnocarpium|Phyllitis|Woodwardia|Osmundastrum|Deparia|Cheilanthes|Pellaea|Polypodiodes|Dennstaedtia|Diplazium|Cryptogramma)\\b',re.I),
    'Piwonie':re.compile(r'^Paeonia\\b',re.I),
}
EXCLUDED_PAGE=re.compile(r'(?i)(?:/(?:pl/c|category|kategoria|collections?)/|(?:lilie[-_ ]?wodne|rosliny[-_ ]?cieniolubne|podpory|akcesoria))')
PAGENO=re.compile(r'^\s*(?:\d{1,3}|następna|dalej|next|»|›)\s*$',re.I)

class Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.heading_depth=0
        self.active=None
        self.links=[]
    def handle_starttag(self,tag,attrs):
        props=dict(attrs)
        if tag=='h3':self.heading_depth+=1
        if tag=='a':
            self.active={'href':props.get('href',''),'label':[],
                         'product':self.heading_depth>0 or
                         any(v in ('productname','product-name') for v in props.get('class','').split()),
                         'rel':props.get('rel','')}
    def handle_data(self,data):
        if self.active:self.active['label'].append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.active:
            self.active['label']=' '.join(' '.join(self.active['label']).split())
            self.links.append(self.active)
            self.active=None
        if tag=='h3':self.heading_depth=max(0,self.heading_depth-1)

def page_url(link,base):
    parsed=urlparse(urljoin(base,link))
    if parsed.scheme!='https' or parsed.hostname not in core.HOSTS:return ''
    return urlunparse((parsed.scheme,parsed.netloc,parsed.path,'',parsed.query,''))

def transient(exc):
    if isinstance(exc, HTTPError):
        return exc.code==429 or 500<=exc.code<=599
    return isinstance(exc,(URLError,TimeoutError,socket.timeout,ConnectionError,ssl.SSLError,ConnectionResetError))

def once_retry(operation,delay=1.3):
    # One initial attempt plus exactly ONE retry for transient transport failures.
    try:return operation()
    except Exception as exc:
        if not transient(exc):raise
        if delay:time.sleep(delay)
        return operation()

def failed(state,url,category,reason,kind='network'):
    entry={'url':url,'category':category,'status':'failed','kind':kind,'error':str(reason)[:250]}
    if not any(item['url']==url for item in state['failed']):
        state['failed'].append(entry)
    return entry

def migrate_checkpoint(state):
    # Convert previous-run error entries to a durable manual-review list.
    state.setdefault('failed',[])
    state.setdefault('incomplete',[])
    existing_errors={x.get('url'):x.get('error','unknown error') for x in state.get('errors',[])}
    for item in state.get('completed',[]):
        if item.get('status')=='error':
            item['status']='failed'
            failed(state,item['source_url'],item.get('category',''),existing_errors.get(item['source_url'],'legacy error'))
        elif item.get('status')=='incomplete':
            if not any(x['url']==item['source_url'] for x in state['incomplete']):
                state['incomplete'].append({'url':item['source_url'],'category':item.get('category',''),'status':'incomplete','reason':existing_errors.get(item['source_url'],'missing required fields')})
    # Previously failed category pages used to be requeued; remove those once
    # transferred to the manual-review list instead of retrying indefinitely.
    for item in state.get('category_errors',[]):
        failed(state,item['url'],next((p['category'] for p in state.get('pages',[]) if p['url']==item['url']),''),item.get('error','legacy category error'))
    failed_pages={x['url'] for x in state['failed']}
    state['pages']=[p for p in state.get('pages',[]) if p['url'] not in failed_pages]
    return state

def parse_category(html_text,url,base,category=None):
    parser=Links();parser.feed(html_text)
    candidates=[];pages=[]
    basepath=urlparse(base).path.rstrip('/')
    for link in parser.links:
        href=page_url(link['href'],url)
        if not href:continue
        label=link['label']
        name=core.title(label)
        if link['product'] and name and not BULK.search(label) and (category is None or GENERA.get(category,re.compile(r'(?!)')).search(name)):
            # Do not interpret pagination/category links as plant pages.
            if not EXCLUDED_PAGE.search(urlparse(href).path) and href!=url:
                product=core.safe(href)
                if product:candidates.append({'botanical_name':name,'source_url':product})
        if PAGENO.match(label) or link.get('rel')=='next':
            parsed=urlparse(href)
            if (parsed.path==basepath or parsed.path.startswith(basepath+'/')) and href!=url:
                pages.append(href)
    unique=lambda rows,key:list({key(r):r for r in reversed(rows)}.values())[::-1]
    return unique(candidates,lambda x:x['source_url']),list(dict.fromkeys(pages))

def initial_state(groups):
    return {'schema_version':1,'groups':list(groups),
            'pages':[{'category':cat,'base':core.CATEGORIES[cat],'url':core.CATEGORIES[cat]} for cat in groups],
            'visited_pages':[],'pending':[],'completed':[],'errors':[],'category_errors':[],'failed':[],'incomplete':[],
            'stats':{}}

def collect(state,review,limit=100,page_limit=45,delay=1.3,fetcher=core.fetch):
    if state['groups']!=review.get('groups'):raise ValueError('State and review group mismatch')
    migrate_checkpoint(state)
    known={item['source_url'] for item in state['pending']+state['completed']}
    seen={core.normal(rec.get('botanical_name')) for rec in review['records']}
    # Existing live cards should not be recrawled or duplicated in staged output.
    if core.LIVE.exists():
        known_names={core.normal(rec.get('botanical_name')) for rec in core.load(core.LIVE,{'records':[]})['records']}
    else:known_names=set()
    pages_done=0
    while (state['pending'] or state['pages']) and len(review['records'])<limit:
        if not state['pending'] and state['pages']:
            if pages_done>=page_limit:break
            current=state['pages'].pop(0)
            if current['url'] in state['visited_pages']:continue
            try:
                plants,more=parse_category(once_retry(lambda:fetcher(current['url']),delay),current['url'],current['base'],current['category'])
                for item in plants:
                    if item['source_url'] not in known:
                        item['category']=current['category']
                        state['pending'].append(item)
                        known.add(item['source_url'])
                for link in more:
                    if link not in state['visited_pages'] and not any(p['url']==link for p in state['pages']):
                        state['pages'].append({**current,'url':link})
                state['visited_pages'].append(current['url'])
            except Exception as exc:
                state['category_errors'].append({'url':current['url'],'error':str(exc)[:180]})
                failed(state,current['url'],current['category'],exc,'network' if transient(exc) else 'category_parse')
                # Do not stop the queue or retry this page automatically.
                pages_done+=1
                continue
            pages_done+=1
            if delay:time.sleep(delay)
            continue
        item=state['pending'].pop(0)
        try:
            rec=once_retry(lambda:core.detail(item),delay)
            key=core.normal(rec['botanical_name'])
            if not key or key in seen or key in known_names:
                state['completed'].append({**item,'status':'duplicate'})
            elif not rec.get('description') or not rec.get('traits'):
                state['incomplete'].append({'url':item['source_url'],'category':item['category'],'status':'incomplete','reason':'missing description or traits'})
                state['completed'].append({**item,'status':'incomplete'})
            else:
                review['records'].append(rec)
                seen.add(key)
                state['completed'].append({**item,'status':'saved'})
        except Exception as exc:
            failed(state,item['source_url'],item['category'],exc,'network' if transient(exc) else 'product_parse')
            state['completed'].append({**item,'status':'failed'})
        if len(state['completed'])%10==0:
            print(json.dumps({'progress':len(state['completed']),'saved':len(review['records']),
                              'failed':len(state['failed']),'incomplete':len(state['incomplete'])},ensure_ascii=False),flush=True)
        if delay:time.sleep(delay)
    state['stats']={'attempted_total':len(state['completed']),'records_total':len(review['records']),
                    'queued':len(state['pending']),'pages_pending':len(state['pages']),
                    'pages_visited':len(state['visited_pages']),'errors':len(state['errors']),
                    'category_errors':len(state['category_errors']),
                    'failed':len(state['failed']),'incomplete':len(state['incomplete']),
                    'saved_by_category':{cat:sum(r.get('sadzawka_category')==cat for r in review['records']) for cat in state['groups']}}
    return state,review

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--limit',type=int,default=100)
    parser.add_argument('--page-limit',type=int,default=45)
    parser.add_argument('--delay',type=float,default=1.3)
    parser.add_argument('--groups',default=','.join(FIRST_GROUPS))
    args=parser.parse_args()
    groups=tuple(x.strip() for x in args.groups.split(','))
    if not groups or any(x not in core.CATEGORIES for x in groups):raise SystemExit('Unknown botanical group')
    if not 1<=args.limit<=200 or not 1<=args.page_limit<=80 or args.delay<1.2:
        raise SystemExit('Unsafe request limits')
    if QUEUE.exists() and OUTPUT.exists():
        state=json.loads(QUEUE.read_text(encoding='utf-8'))
        review=json.loads(OUTPUT.read_text(encoding='utf-8'))
        if tuple(state['groups'])!=groups:raise SystemExit('Cannot change groups when continuing a batch')
    elif not QUEUE.exists() and not OUTPUT.exists():
        state=initial_state(groups)
        review={'schema_version':1,'source':'sadzawka.pl','groups':list(groups),'records':[]}
    else:
        raise SystemExit('One checkpoint file is missing: refusing to reset progress')
    state,review=collect(state,review,args.limit,args.page_limit,args.delay)
    OUTPUT.parent.mkdir(parents=True,exist_ok=True)
    OUTPUT.write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    QUEUE.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(state['stats'],ensure_ascii=False))
if __name__=='__main__':main()
