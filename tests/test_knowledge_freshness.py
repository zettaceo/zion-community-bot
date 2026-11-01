import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone

from zion.knowledge import KnowledgeBase


class KnowledgeFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def row(self, name, **changes):
        value = dict(file=name+'.md', id=name, title=name,
            source_type='approved_test_projection', snapshot_date='2026-01-01',
            authority='synthetic-test', classification='PUBLIC', status='CURRENT',
            version='v1', source_identity=name, allowed_agents=['mimir'],
            supersedes=[], superseded_by=None, freshness='snapshot_only',
            valid_until=None, notes='Synthetic fixture only')
        value.update(changes)
        return value

    def load(self, *rows):
        for row in rows:
            (self.root / row['file']).write_text('# Taxas\nTaxas '+row['id']+'\n')
        (self.root / 'MANIFEST.md').write_text('```json\n'+json.dumps(
            dict(schema_version=2, sources=rows))+'\n```')
        return KnowledgeBase(self.root)

    def test_only_current_source_enters_context(self):
        rows = [self.row('current')]
        rows += [self.row(state.lower(), status=state) for state in
                 ('DRAFT', 'UNVERIFIED', 'SUPERSEDED', 'HISTORICAL', 'EXCLUDED')]
        kb = self.load(*rows)
        self.assertFalse(kb.load_errors)
        hits = kb.search('taxas', limit=10, agent_id='mimir')
        self.assertEqual([h.authority.source_id for h in hits], ['current'])

    def test_expiration_is_rechecked_without_reload(self):
        kb = self.load(self.row('expires', freshness='expires', valid_until='2026-10-20'))
        with patch('zion.knowledge.datetime') as clock:
            clock.now.return_value = datetime(2026,10,20,23,59,tzinfo=timezone.utc)
            self.assertTrue(kb.search('taxas', agent_id='mimir'))
            clock.now.return_value = datetime(2026,10,21,tzinfo=timezone.utc)
            self.assertFalse(kb.search('taxas', agent_id='mimir'))

    def test_reciprocal_supersession_never_promotes_old_source(self):
        kb = self.load(self.row('old', status='SUPERSEDED', superseded_by='new'),
                       self.row('new', supersedes=['old']))
        self.assertFalse(kb.load_errors)
        self.assertEqual([h.authority.source_id for h in kb.search('taxas', agent_id='mimir')], ['new'])
        self.assertEqual(kb.sources['new.md'].snapshot_date, '2026-01-01')

    def test_conflicts_cycles_and_unknown_links_fail_closed(self):
        cases = [
            (self.row('old', superseded_by='new'), self.row('new', supersedes=['old'])),
            (self.row('old', status='SUPERSEDED', superseded_by='new'), self.row('new')),
            (self.row('only', supersedes=['absent']),),
            (self.row('a', status='SUPERSEDED', supersedes=['b'], superseded_by='b'),
             self.row('b', status='SUPERSEDED', supersedes=['a'], superseded_by='a')),
            (self.row('a'), self.row('b', id='a')),
        ]
        for rows in cases:
            with self.subTest(rows=rows):
                kb = self.load(*rows)
                self.assertTrue(kb.load_errors)
                self.assertEqual(kb.chunks, [])

    def test_invalid_freshness_metadata_fails_closed(self):
        for changes in (dict(freshness='expires'), dict(freshness='forever'),
                        dict(freshness='expires', valid_until='2025-12-31'),
                        dict(snapshot_date='not-a-date'), dict(title=''),
                        dict(valid_until='2027-01-01')):
            with self.subTest(changes=changes):
                kb = self.load(self.row('bad', **changes))
                self.assertTrue(kb.load_errors)
                self.assertEqual(kb.chunks, [])
