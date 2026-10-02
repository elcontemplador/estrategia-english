"""End-to-end authorship rendering using fictional, isolated local fixtures."""
import contextlib, io, json, re, tempfile, unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import build
from release_gate import editorial_fingerprint

class AuthorshipBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='estrategia-authorship-test-')
        self.root = Path(self.tmp.name).resolve()
        (self.root/'content/en').mkdir(parents=True)
        (self.root/'assets').mkdir()
        Image.new('RGB', (756,502), '#1e1e20').save(self.root/'assets/estrategia-header.png')
        config=json.loads((build.ROOT/'site.json').read_text(encoding='utf-8-sig'))
        config.update(base_url='https://example.test/archive/',human_approval='approved',training_policy='allow')
        (self.root/'site.json').write_text(json.dumps(config),encoding='utf-8')
    def tearDown(self):
        self.tmp.cleanup()
    def article(self,n,people=None,unknown=False):
        raw='# Fictional test essay\n\nSynthetic content for a local test.\n'
        author={'name':'; '.join(p['name'] for p in people) if people else 'Single test author','url':None}
        if unknown:author={'name':None,'url':None}
        meta={'issue_number':n,'title':'Fictional test essay','description':'Local test only','author':author,'original_url':'https://example.test/spanish/','original_date':'2025-01-01','topics':['government'],'genre':'analysis','human_approval':'approved','assisted_review_status':'passed','english_publication_date':'2026-01-01'}
        if people is not None:meta['authors']=people
        meta['assisted_review_hash']=meta['human_approval_hash']=editorial_fingerprint(raw.encode(),meta)
        (self.root/f'content/en/{n:03}.md').write_bytes(raw.encode('utf-8'))
        (self.root/f'content/en/{n:03}.json').write_text(json.dumps(meta),encoding='utf-8')
    def run_build(self,mode):
        with patch.object(build,'ROOT',self.root),patch('sys.argv',['build.py','--mode',mode]),contextlib.redirect_stdout(io.StringIO()):
            build.main()
        return self.root/('dist' if mode=='public' else 'preview')
    def schema(self,out,n):
        text=(out/f'essays/{n:03}/index.html').read_text(encoding='utf-8')
        return text,json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>',text,re.S).group(1))
    def test_eight_coauthors_and_single_author_in_public_outputs(self):
        people=[{'name':f'Test author {i}','url':f'https://example.test/person/{i}'} for i in range(1,9)]
        self.article(1,people);self.article(2)
        out=self.run_build('public');text,schema=self.schema(out,1)
        self.assertEqual([p['name'] for p in schema['author']],[p['name'] for p in people])
        heading=text.split('<header class="article-heading">')[1].split('</header>')[0]
        self.assertIn('<span>Authors</span>',heading)
        for i, person in enumerate(people, 1):
            self.assertIn('href="/archive/people/test-author-'+str(i)+'/"',heading)
            self.assertIn(person['name'],heading)
        self.assertEqual(next(r for r in json.loads((out/'catalog.json').read_text(encoding='utf-8'))['articles'] if r['id']=='001')['authors'],people)
        ns={'a':'http://www.w3.org/2005/Atom'};entries=sorted(ET.parse(out/'feed.xml').findall('a:entry',ns),key=lambda entry:entry.find('a:id',ns).text)
        self.assertEqual([x.text for x in entries[0].findall('a:author/a:name',ns)],[p['name'] for p in people])
        self.assertEqual([x.text for x in entries[0].findall('a:author/a:uri',ns)],[p['url'] for p in people])
        self.assertEqual(len(entries[1].findall('a:author',ns)),1)
        self.assertIsInstance(self.schema(out,2)[1]['author'],dict)
    def test_unattributed_review_does_not_invent_person(self):
        self.article(1,unknown=True);out=self.run_build('review');text,schema=self.schema(out,1)
        self.assertNotIn('author',schema);self.assertIn('Byline not stated in original',text)
        self.assertEqual(len(ET.parse(out/'feed.xml').findall('{http://www.w3.org/2005/Atom}entry')),0)

if __name__=='__main__':unittest.main()
