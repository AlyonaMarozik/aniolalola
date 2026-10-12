"""Offline tests for category pagination, exclusions and persisted checkpoints."""
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
path=ROOT/'scripts/collect_sadzawka_batch.py'
spec=importlib.util.spec_from_file_location('sadzawka_batch',path)
batch=importlib.util.module_from_spec(spec)
spec.loader.exec_module(batch)
BASE='https://sadzawka.pl/bodziszki'
FIRST="""<html><body>
<h3><a href="/Geranium_test_1">Geranium test 'One' - bodziszek</a></h3>
<h3><a href="/Geranium_macrorrhizum_100">Geranium macrorrhizum - 100 sztuk</a></h3>
<a href="/bodziszki?page=2">2</a>
</body></html>"""
SECOND="""<html><body>
<h3><a href="/Geranium_test_2">Geranium test 'Two' - bodziszek</a></h3>
<a href="/bodziszki?page=1">1</a>
</body></html>"""

class BatchTests(unittest.TestCase):
    def test_pagination_and_bulk_exclusion(self):
        p,n=batch.parse_category(FIRST,BASE,BASE)
        self.assertEqual(len(p),1)
        self.assertEqual(p[0]['botanical_name'],"Geranium test 'One'")
        self.assertIn(BASE+'?page=2',n)
    def test_state_continues_without_duplicate_requests(self):
        pages={BASE:FIRST,BASE+'?page=2':SECOND}
        calls=[]
        def fetch(url):
            calls.append(url)
            return pages[url]
        def detail(item):
            return {'id':item['botanical_name'].lower().replace(' ','-'),
                    'botanical_name':item['botanical_name'],'description':'Polski opis rośliny',
                    'traits':{'light':'солнце'},'source_url':item['source_url']}
        state=batch.initial_state(('Bodziszki',))
        review={'groups':['Bodziszki'],'records':[]}
        with patch.object(batch.core,'detail',side_effect=detail):
            state,review=batch.collect(state,review,limit=1,page_limit=4,delay=0,fetcher=fetch)
            self.assertEqual(len(review['records']),1)
            self.assertEqual(state['stats']['records_total'],1)
            state,review=batch.collect(state,review,limit=2,page_limit=4,delay=0,fetcher=fetch)
            self.assertEqual(len(review['records']),2)
            self.assertEqual(len({x['id'] for x in review['records']}),2)
        self.assertEqual(calls.count(BASE),1)
        self.assertEqual(calls.count(BASE+'?page=2'),1)
    def test_category_failure_one_retry_then_manual_failed(self):
        state=batch.initial_state(('Bodziszki',))
        review={'groups':['Bodziszki'],'records':[]}
        calls=[]
        def fail(url):
            calls.append(url)
            raise ConnectionError('offline')
        state,review=batch.collect(state,review,limit=2,page_limit=2,delay=0,fetcher=fail)
        self.assertEqual(len(review['records']),0)
        self.assertEqual(calls,[BASE,BASE])
        self.assertEqual(state['pages'],[])
        self.assertEqual(state['failed'][0]['url'],BASE)
        self.assertEqual(state['failed'][0]['status'],'failed')
        self.assertEqual(state['stats']['category_errors'],1)
        batch.collect(state,review,limit=2,page_limit=2,delay=0,fetcher=fail)
        self.assertEqual(len(calls),2)

    def test_product_failure_once_retry_then_manual_failed(self):
        state=batch.initial_state(('Bodziszki',))
        state['pages']=[]
        state['pending']=[{'source_url':BASE+'/Geranium_test','botanical_name':'Geranium test','category':'Bodziszki'}]
        review={'groups':['Bodziszki'],'records':[]}
        calls=[]
        def failed_detail(item):
            calls.append(item['source_url'])
            raise TimeoutError('SSL handshake timeout')
        with patch.object(batch.core,'detail',side_effect=failed_detail):
            state,review=batch.collect(state,review,limit=2,delay=0)
            self.assertEqual(len(calls),2)
            self.assertEqual(len(state['failed']),1)
            self.assertEqual(state['failed'][0]['status'],'failed')
            self.assertEqual(state['failed'][0]['url'],BASE+'/Geranium_test')
            batch.collect(state,review,limit=2,delay=0)
        self.assertEqual(len(calls),2)

    def test_parse_error_does_not_retry(self):
        calls=[]
        def fail():
            calls.append(1)
            raise ValueError('bad HTML')
        with self.assertRaises(ValueError):batch.once_retry(fail,delay=0)
        self.assertEqual(len(calls),1)

    def test_category_labels_only_expected_botanical_genus(self):
        example='''<h3><a href="/Geranium_sanguineum">Geranium sanguineum</a></h3>
<h3><a href="/rosliny-cieniolubne">Rośliny cieniolubne</a></h3>
<h3><a href="/lilie-wodne-zimotrwale">Lilie wodne zimotrwałe</a></h3>
<h3><a href="/podpory-do-pnaczy">Podpory do pnączy</a></h3>'''
        plants,_=batch.parse_category(example,BASE,BASE,category='Bodziszki')
        self.assertEqual([p['botanical_name'] for p in plants],['Geranium sanguineum'])

    def test_http_503_retries_only_once(self):
        calls=[]
        def fail():
            calls.append(1)
            raise HTTPError(BASE,503,'Service Unavailable',{},None)
        with self.assertRaises(HTTPError):batch.once_retry(fail,delay=0)
        self.assertEqual(len(calls),2)

    def test_http_404_is_failed_without_retry(self):
        calls=[]
        def fail():
            calls.append(1)
            raise HTTPError(BASE,404,'Not Found',{},None)
        with self.assertRaises(HTTPError):batch.once_retry(fail,delay=0)
        self.assertEqual(len(calls),1)

    def test_checkpoint_migration_preserves_68_cards_and_failures(self):
        state=batch.initial_state(('Bodziszki',))
        state['completed']=[{'source_url':BASE+'/bad','category':'Bodziszki','status':'error'},
                            {'source_url':BASE+'/incomplete','category':'Bodziszki','status':'incomplete'}]
        state['errors']=[{'url':BASE+'/bad','error':'ssl error'},
                         {'url':BASE+'/incomplete','error':'missing description or traits'}]
        state['category_errors']=[{'url':BASE,'error':'SSL timeout'}]
        old_records=[{'id':'test-'+str(i),'botanical_name':'Plant '+str(i)} for i in range(68)]
        review={'groups':['Bodziszki'],'records':old_records}
        batch.migrate_checkpoint(state)
        self.assertEqual(len(review['records']),68)
        self.assertEqual(len(state['failed']),2)
        self.assertEqual(len(state['incomplete']),1)
        self.assertEqual(state['pages'],[])
        batch.migrate_checkpoint(state)
        self.assertEqual(len(state['failed']),2)
        self.assertEqual(len(state['incomplete']),1)

if __name__=='__main__':unittest.main()
