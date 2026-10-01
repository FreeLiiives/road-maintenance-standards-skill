import datetime as dt
import importlib.util
from pathlib import Path
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / 'skills/road-maintenance-standards'
spec = importlib.util.spec_from_file_location('standards', SKILL / 'scripts/standards.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
URL = 'https://xxgk.mot.gov.cn/jigou/glj/202609/t20260924_1234567.html'
FEED = 'https://xxgk.mot.gov.cn/list.html'
BODY = '<html><title>交通运输部关于公路养护标准的公告</title><body>交通运输部 现发布测试标准（JTG/T 9999—2026），自2026年11月1日起施行。原测试标准（JTG H99—2009）同时废止。联系我们</body></html>'
LIST = f'<a href="{URL}">交通运输部关于发布公路养护标准的公告</a>'


class StandardsTests(unittest.TestCase):
    def test_relative_discovery_and_deduplication(self):
        self.assertEqual(m.discover(LIST + LIST, FEED), {URL: '交通运输部关于发布公路养护标准的公告'})
        self.assertEqual(len(m.discover(LIST.replace(URL, '/jigou/glj/202609/t20260924_1234567.html'), FEED)), 1)

    def test_untrusted_urls_rejected(self):
        for url in ['http://xxgk.mot.gov.cn/a', 'https://xxgk.mot.gov.cn.evil.test/a', 'https://localhost/a', 'file:///a', 'https://user:pass@xxgk.mot.gov.cn/a', 'https://xxgk.mot.gov.cn:8443/a']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                m.safe_url(url)

    def test_empty_or_blocked_feed_is_error(self):
        with self.assertRaises(ValueError):
            m.discover('<html>Access denied</html>', FEED)

    def test_error_page_not_accepted_as_standard(self):
        with self.assertRaises(ValueError):
            m.fingerprint('<title>Forbidden</title>' + 'error ' * 100)

    def test_hash_ignores_scripts_and_footer(self):
        a = m.fingerprint(BODY)
        b = m.fingerprint(BODY.replace('<body>', '<body><script>random123</script>').replace('联系我们', '联系我们 dynamic footer'))
        self.assertEqual(a['sha256'], b['sha256'])
        self.assertIn('废止', a['review_signals'])
        self.assertEqual(len(a['detected_codes']), 2)

    def test_meaningful_body_change_changes_hash(self):
        self.assertNotEqual(m.fingerprint(BODY)['sha256'], m.fingerprint(BODY.replace('11月1日', '12月1日'))['sha256'])

    def test_future_implementation(self):
        item = {'effective_date': '2026-11-01'}
        self.assertIn('尚未', m.date_state(item, dt.date(2026, 10, 1)))
        self.assertIn('仍需核验', m.date_state(item, dt.date(2026, 11, 1)))

    def test_catalog_provenance_and_unique_ids(self):
        catalog = m.read_json(SKILL / 'data/catalog.json')
        self.assertEqual(len({i['code'] for i in catalog}), len(catalog))
        for item in catalog:
            self.assertEqual(m.safe_url(item['source_url']), item['source_url'])
            dt.date.fromisoformat(item['effective_date'])
            dt.date.fromisoformat(item['verified_on'])
            self.assertEqual(item['latest_validity'], 'not_exhaustively_verified')

    def test_search_old_identifier_leads_to_replacement(self):
        rows = m.search(m.read_json(SKILL / 'data/catalog.json'), 'JTG/T E61—2014')
        self.assertEqual(rows[0]['code'], 'JTG/T 5212-2026')
        self.assertEqual(len(rows), 1)

    def test_yolo_mapping_and_unknown(self):
        catalog = m.read_json(SKILL / 'data/catalog.json')
        mapping = m.read_json(SKILL / 'data/yolo-labels.json')
        self.assertTrue(m.search(catalog, 'Pothole', mapping))
        self.assertEqual(m.search(catalog, 'Manhole', mapping), [])
        self.assertEqual(m.search(catalog, 'Other', mapping), [])

    def fixture(self, root):
        m.write_json(root / 'data/catalog.json', [{'source_url': URL}])
        m.write_json(root / 'data/sources.json', [{'id': 'test', 'url': FEED}])

    def test_sync_initial_unchanged_changed_and_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            content = {FEED: LIST, URL: BODY}
            initial = m.sync(root, content.__getitem__, '2026-10-01T00:00:00+00:00', delay=0)
            self.assertEqual([c['kind'] for c in initial['changes']], ['baseline'])
            same = m.sync(root, content.__getitem__, '2026-10-02T00:00:00+00:00', delay=0)
            self.assertEqual(same['changes'], [])
            content[URL] = BODY.replace('11月1日', '12月1日')
            changed = m.sync(root, content.__getitem__, '2026-10-03T00:00:00+00:00', delay=0)
            self.assertEqual(changed['changes'][0]['kind'], 'changed')
            previous = m.read_json(root / 'data/observations.json')['pages'][URL]
            del content[URL]
            failed = m.sync(root, content.__getitem__, '2026-10-04T00:00:00+00:00', delay=0)
            self.assertEqual(failed['failures'], 1)
            page = m.read_json(root / 'data/observations.json')['pages'][URL]
            self.assertEqual(page['sha256'], previous['sha256'])
            self.assertEqual(page['last_success'], previous['last_success'])
            self.assertEqual(page['fetch_status'], 'error')
            self.assertNotEqual(page['last_attempt'], page['last_success'])

    def test_candidates_never_auto_promote(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            m.write_json(root / 'data/catalog.json', [])
            content = {FEED: LIST, URL: BODY}
            m.sync(root, content.__getitem__, '2026-10-01T00:00:00+00:00', delay=0)
            self.assertEqual(m.read_json(root / 'data/catalog.json'), [])
            self.assertEqual(m.read_json(root / 'data/observations.json')['candidates'][URL]['review_status'], 'unreviewed')

    def test_all_failures_reported_without_erasing_catalog(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            def fail(url):
                raise TimeoutError('simulated network timeout')
            result = m.sync(root, fail, '2026-10-01T00:00:00+00:00', delay=0)
            self.assertEqual(result['failures'], 2)
            self.assertIn('失败', (root / 'reports/latest.md').read_text(encoding='utf-8'))
            self.assertEqual(len(m.read_json(root / 'data/catalog.json')), 1)

    def test_backlog_processed_across_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            m.write_json(root / 'data/catalog.json', [])
            url2 = URL.replace('1234567', '1234568')
            content = {FEED: LIST + LIST.replace(URL, url2), URL: BODY, url2: BODY}
            m.sync(root, content.__getitem__, '2026-10-01T00:00:00+00:00', max_new=1, delay=0)
            self.assertEqual(len(m.read_json(root / 'data/observations.json')['pages']), 1)
            m.sync(root, content.__getitem__, '2026-10-02T00:00:00+00:00', max_new=1, delay=0)
            self.assertEqual(len(m.read_json(root / 'data/observations.json')['pages']), 2)


if __name__ == '__main__':
    unittest.main()
