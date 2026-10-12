#!/usr/bin/env python3
"""Stage Sadzawka botanical-category products for review, never modify live catalog."""
import argparse, html, json, re, time, unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'catalog/exports/sadzawka-catalog-review.json'
QUEUE=ROOT/'catalog/exports/sadzawka-catalog-queue.json'
LIVE=ROOT/'catalog/exports/pilot-sadzawka.json'
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; GardenPlannerBot/1.0)'}
HOSTS={'sadzawka.pl','www.sadzawka.pl'}
# Only botanical departments, not thematic collections or accessories.
CATEGORIES={
 'Bodziszki':'https://sadzawka.pl/bodziszki',
 'Brunery':'https://sadzawka.pl/Brunery',
 'Ciemierniki':'https://sadzawka.pl/pl/c/Ciemierniki/194',
 'Cyklameny ogrodowe':'https://sadzawka.pl/pl/c/Cyklameny-ogrodowe/152',
 'Epimedia':'https://sadzawka.pl/pl/c/Epimedia/155',
 'Hosty':'https://sadzawka.pl/hosty',
 'Irysy':'https://sadzawka.pl/irysy',
 'Kokoryczki, dispora i jagodowce':'https://sadzawka.pl/pl/c/Kokoryczki%2C-dispora-i-jagodowce/134',
 'Konwalie':'https://sadzawka.pl/pl/c/Konwalie/108',
 'Liliowce':'https://sadzawka.pl/liliowce',
 'Martogony':'https://sadzawka.pl/pl/c/Martogony-mieszance/193',
 'Paprocie':'https://sadzawka.pl/paprocie',
 'Pierwiosnki':'https://sadzawka.pl/pl/c/Pierwiosnki/109',
 'Piwonie':'https://sadzawka.pl/piwonie',
 'Storczyki gruntowe':'https://sadzawka.pl/storczyki_gruntowe',
 'Trawy':'https://sadzawka.pl/trawy',
 'Trójlisty':'https://sadzawka.pl/trojlisty',
}
WATER=re.compile(r'(?i)\b(nymphaea|nelumbo|nymphoides|pistia|lemna|salvinia|azolla|hydrocharis|eichhornia|stratiotes|hippuris|myriophyllum|potamogeton|elodea|ceratophyllum)\b')
EXCLUDE=re.compile(r'(?i)\b(kolekcja|zestaw|komplet|naw[oó]z|kosz|koszyk|podpora|tabletki|preparat|mix odmian|mieszanka nasion)\b')

def normal(x):
 x=unicodedata.normalize('NFKC',x or '').translate(str.maketrans({'„':"'",'“':"'",'”':"'",'’':"'",'"':"'"}))
 return re.sub(r'\s+',' ',x).strip().casefold()

def title(raw):
 raw=' '.join(html.unescape(raw).split())
 name=re.split(r'\s+[-–]\s+',raw,1)[0].strip()
 if EXCLUDE.search(raw) or WATER.search(name) or not re.match(r'^[A-Z][a-zA-Z-]+(?:\s|$)',name) or not 6<=len(name)<=145:return ''
 return name

def safe(url):
 p=urlparse(url)
 if p.scheme!='https' or p.hostname not in HOSTS:return ''
 return urlunparse((p.scheme,p.netloc,p.path,'','',''))

def fetch(url):
 url=safe(url)
 if not url:raise ValueError('Invalid Sadzawka URL')
 with urlopen(Request(url,headers=HEADERS),timeout=25) as r:
  if 'text/html' not in r.headers.get('Content-Type','').lower():raise ValueError('Not HTML')
  return r.read(3000000).decode('utf-8','replace')

class Scan(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True);self.h3=0;self.h1=0;self.a=None;self.products=[];self.links=[];self.meta={};self.head=[]
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='h3':self.h3+=1
  if tag=='h1':self.h1+=1
  if tag=='a':self.a=[a.get('href',''),[],bool(self.h3)]
  if tag=='meta':
   k=a.get('property') or a.get('name')
   if k and a.get('content'):self.meta[k.lower()]=a['content']
 def handle_data(self,data):
  if self.a:self.a[1].append(data)
  if self.h1:self.head.append(data)
 def handle_endtag(self,tag):
  if tag=='a' and self.a:
   href,words,product=self.a;label=' '.join(' '.join(words).split())
   self.links.append((href,label))
   if product:self.products.append((href,label))
   self.a=None
  if tag=='h3':self.h3=max(0,self.h3-1)
  if tag=='h1':self.h1=max(0,self.h1-1)

def category_page(url):
 s=Scan();s.feed(fetch(url))
 plants=[]
 for href,label in s.products:
  link=safe(urljoin(url,href));name=title(label)
  if link and name and '/pl/c/' not in urlparse(link).path:plants.append({'botanical_name':name,'source_url':link})
 pages=[]
 path=urlparse(url).path.rstrip('/')
 for href,label in s.links:
  link=safe(urljoin(url,href))
  if link!=url and re.fullmatch(r'(?:\d{1,3}|next|»|›|następna)',label.strip(),re.I):
   if urlparse(link).path.startswith(path+'/') or urlparse(link).path==path:pages.append(link)
 return plants,list(dict.fromkeys(pages))

def load(path,default):
 return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def identifier(name):
 base=unicodedata.normalize('NFKD',name).encode('ascii','ignore').decode('ascii').lower()
 base=re.sub(r'[^a-z0-9]+','-',base).strip('-')
 return base or 'unnamed-plant'

class DescriptionText(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True)
  self.parts=[]
  self.paragraphs=[]
  self.paragraph=None
  self.depth=0
 def handle_starttag(self,tag,attrs):
  if tag=='p':
   if self.paragraph is None:
    self.paragraph=[]
    self.depth=0
   else:self.depth+=1
  if tag in ('p','div','br','li','h1','h2','h3','h4','tr','dt','dd'):
   self.parts.append('\n')
 def handle_endtag(self,tag):
  if tag=='p' and self.paragraph is not None:
   if self.depth:self.depth-=1
   else:
    paragraph=' '.join(''.join(self.paragraph).split())
    if paragraph:self.paragraphs.append(paragraph)
    self.paragraph=None
  if tag in ('p','div','li','h1','h2','h3','h4','tr','dt','dd'):
   self.parts.append('\n')
 def handle_data(self,data):
  self.parts.append(data)
  if self.paragraph is not None:self.paragraph.append(data)
 def lines(self):
  return [' '.join(line.split()) for line in ''.join(self.parts).splitlines() if line.strip()]

FIELD_MAP={
 'rodzina':'family','stanowisko':'light','nasłonecznienie':'light',
 'wysokość':'height_cm_max','szerokość':'width_cm_max','średnica':'width_cm_max',
 'kwitnienie':'flowering','okres kwitnienia':'flowering',
 'gleba':'soil','podłoże':'soil','ziemia':'soil',
 'wilgotność':'moisture','wilgotność podłoża':'moisture',
 'mrozoodporność':'frost_resistance','strefa mrozoodporności':'hardiness_zone',
 'pokrój':'habit','liście':'foliage','ubarwienie kwiatów':'flower_color',
 'kolor kwiatów':'flower_color','barwa kwiatów':'flower_color',
 'pochodzenie':'origin','zapach':'fragrance'
}
RETAIL=re.compile(r'(?i)\b(cena|cenie|producent\w*|hodowc\w*|donicz\w*|pojemnik\w*|kod produktu|dostępn\w*|szt\.?|koszyk\w*|zamów\w*|zł)\b')
END=re.compile(r'(?i)^(opinie|zapytaj o produkt|poleć znajomemu|newsletter|koszyk|dodaj opinię)\b')
MONTHS={'I':1,'II':2,'III':3,'IV':4,'V':5,'VI':6,'VII':7,'VIII':8,'IX':9,'X':10,'XI':11,'XII':12}
MONTH_RU=['','январь','февраль','март','апрель','май','июнь','июль','август','сентябрь','октябрь','ноябрь','декабрь']

def convert_field(key,value):
 if key in ('height_cm_max','width_cm_max'):
  m=re.search(r'(\d+(?:[.,]\d+)?)\s*(cm|m)\b',value,re.I)
  if not m:return None
  n=float(m.group(1).replace(',','.'))*(100 if m.group(2).lower()=='m' else 1)
  return round(n) if n.is_integer() else round(n,1)
 if key=='flowering':
  m=re.search(r'\b(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)\s*[-–—]\s*(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)\b',value,re.I)
  if m:
   a,b=(MONTHS[m.group(1).upper()],MONTHS[m.group(2).upper()])
   return MONTH_RU[a]+' — '+MONTH_RU[b]
 if key=='light':
  v=value.lower()
  if 'półcien' in v or 'półcień' in v: 
   if 'słonecz' in v:return 'солнце или полутень'
   return 'полутень'
  if 'cienist' in v or 'cień' in v:return 'тень'
  if 'słonecz' in v:return 'солнце'
 return value[:220]

BOTANICAL_PROSE=re.compile(r'(?i)(roślin|bylin|kwiat|liści|liść|pęd|papro|pokrój|kwit|ogr[oó]d|odmian|gleb|wilgot|cieni|słonec|mroz|wysokość)')
LABELLED=re.compile(r'^([^:]{2,42}):\s*(.{1,400})$')

PARAM_LABELS=re.compile(r'(?i)(?:rodzina|hodowca|stanowisko|nasłonecznienie|wysokość|szerokość|kwitnienie|gleba|podłoże|wilgotność|mrozoodporność)\\s*:')

def polish_first_paragraph(paragraphs):
 for paragraph in paragraphs:
  line=' '.join(paragraph.split())
  # Product specification tables are sometimes stored as a single <p> and
  # their <br> separators can disappear, e.g. Geraniaceaehodowca:.
  if len(PARAM_LABELS.findall(line))>=2:continue
  if len(line)<45 or RETAIL.search(line) or END.search(line):continue
  if LABELLED.match(line) or not BOTANICAL_PROSE.search(line):continue
  return line[:650].rstrip()
 return ''

def botanical_text(html_text,name):
 parser=DescriptionText();parser.feed(html_text)
 lines=parser.lines()
 start=next((i for i,line in enumerate(lines) if re.match(r'(?i)^rodzina\s*:',line)),None)
 if start is None:
  start=next((i for i,line in enumerate(lines) if re.match(r'(?i)^(stanowisko|wysokość|kwitnienie)\s*:',line)),None)
 if start is None:return {},polish_first_paragraph(parser.paragraphs)
 fields={}
 for line in lines[start:start+75]:
  if END.search(line) or line.lower().startswith(('rośnie w doniczce','rosnie w doniczce')):break
  m=LABELLED.match(line)
  if m:
   key=FIELD_MAP.get(m.group(1).lower().strip())
   if key and key not in fields and not RETAIL.search(m.group(1)):
    val=convert_field(key,m.group(2).strip())
    if val is not None:fields[key]=val
 return fields,polish_first_paragraph(parser.paragraphs)

def detail(item):
 html_page=fetch(item['source_url'])
 scan=Scan();scan.feed(html_page)
 meta=scan.meta
 name=title(meta.get('og:title') or ' '.join(scan.head)) or item['botanical_name']
 traits,body=botanical_text(html_page,name)
 description=body
 if not description:
  summary=' '.join(html.unescape(meta.get('og:description') or meta.get('description') or '').split())
  description=polish_first_paragraph([summary])
 record={'id':identifier(name),'botanical_name':name,'description':description,'traits':traits,
         'source_url':item['source_url'],'source':'sadzawka.pl',
         'sadzawka_category':item['category'],'data_quality':'product_page_auto_extracted_unreviewed',
         'trait_source_url':item['source_url'],'trait_quality':'auto_extracted_requires_review',
         'description_language':'pl','growth_3_5_10_years':None}
 img=safe(urljoin(item['source_url'],meta.get('og:image',''))) if meta.get('og:image') else ''
 if img and re.search(r'\.(?:jpe?g|png|webp)$',urlparse(img).path,re.I):
  record['image']={'url':img,'source_url':item['source_url'],'status':'meta_unverified'}
 return record

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument('--test-url',default='',help='Inspect one exact Sadzawka product URL without crawling or publishing')
 ap.add_argument('--limit',type=int,default=50)
 ap.add_argument('--delay',type=float,default=1.3)
 ap.add_argument('--pages-per-category',type=int,default=40)
 args=ap.parse_args()
 if args.test_url:
  u=safe(args.test_url)
  if not u:raise SystemExit('Test URL must be HTTPS on sadzawka.pl')
  record=detail({'source_url':u,'botanical_name':'Test plant','category':'manual_test'})
  OUT.parent.mkdir(parents=True,exist_ok=True)
  OUT.write_text(json.dumps({'source':'sadzawka.pl','mode':'single_product_test','records':[record]},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
  print(json.dumps({'mode':'single_product_test','name':record['botanical_name'],'traits':record['traits'],'description':record['description'],'image':record.get('image',{}).get('url')},ensure_ascii=False,indent=2))
  return
 if not 1<=args.limit<=200 or args.delay<1 or not 1<=args.pages_per_category<=60:raise SystemExit('Unsafe limits')
 q=load(QUEUE,{'pending':[],'completed':[],'page_errors':[],'category_pages':{}})
 staged=load(OUT,{'source':'sadzawka.pl','scope':'botanical terrestrial categories only','records':[],'skipped':[],'errors':[]})
 existing={normal(p.get('botanical_name')) for p in load(LIVE,{'records':[]})['records']}
 existing|={normal(p.get('botanical_name')) for p in staged['records']}
 urls={p['source_url'] for p in q['pending']+q['completed']}
 # Repeated runs retain the queue and review records. Never alter the live catalog.
 for cat,base in CATEGORIES.items():
  if cat in q['category_pages']:continue
  visited=set();pages=[base];failed=False;discovered=0
  while pages and len(visited)<args.pages_per_category:
   u=pages.pop(0)
   if u in visited:continue
   visited.add(u)
   try:
    items,more=category_page(u)
    discovered+=len(items)
    for p in items:
     if p['source_url'] not in urls:
      p['category']=cat;q['pending'].append(p);urls.add(p['source_url'])
    for link in more:
     if link not in visited and link not in pages:pages.append(link)
   except Exception as e:
    failed=True
    q['page_errors'].append({'category':cat,'url':u,'error':str(e)[:200]})
   time.sleep(args.delay)
  # Keep failed/empty/incomplete categories retryable rather than silently marking them done.
  if not failed and not pages and discovered:
   q['category_pages'][cat]=len(visited)
 processed=0;added=0
 while q['pending'] and processed<args.limit:
  item=q['pending'].pop(0);processed+=1
  try:
   rec=detail(item);key=normal(rec['botanical_name'])
   if key in existing:staged['skipped'].append({'name':rec['botanical_name'],'reason':'duplicate','url':item['source_url']})
   elif not title(rec['botanical_name']):staged['skipped'].append({'reason':'excluded','url':item['source_url']})
   else:staged['records'].append(rec);existing.add(key);added+=1
  except Exception as e:staged['errors'].append({'url':item['source_url'],'error':str(e)[:200]})
  q['completed'].append(item);time.sleep(args.delay)
 staged['last_run_at']=datetime.now(timezone.utc).isoformat()
 staged['stats']={'staged':len(staged['records']),'added_this_run':added,'processed_this_run':processed,'remaining':len(q['pending']),'skipped':len(staged['skipped']),'errors':len(staged['errors']),'category_errors':len(q['page_errors'])}
 OUT.parent.mkdir(parents=True,exist_ok=True)
 OUT.write_text(json.dumps(staged,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 QUEUE.write_text(json.dumps(q,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(staged['stats'],ensure_ascii=False))
if __name__=='__main__':main()
