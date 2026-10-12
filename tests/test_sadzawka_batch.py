"""Offline tests for category pagination, exclusions and persisted checkpoints."""
import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

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
    def test_unavailable_category_requeued(self):
        state=batch.initial_state(('Bodziszki',))
        review={'groups':['Bodziszki'],'records':[]}
        def fail(_):raise ConnectionError('offline')
        state,review=batch.collect(state,review,limit=2,page_limit=2,delay=0,fetcher=fail)
        self.assertEqual(len(review['records']),0)
        self.assertEqual(len(state['pages']),1)
        self.assertEqual(state['stats']['category_errors'],1)

if __name__=='__main__':unittest.main()
