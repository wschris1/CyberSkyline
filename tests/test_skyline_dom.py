"""Run the rendered-page extractor against synthetic DOM boundary fixtures."""

import json
from pathlib import Path
import shutil
import subprocess
import unittest


EXTRACTOR = Path(__file__).resolve().parents[1] / 'bots/skyline_archive/dom_extract.js'
HARNESS = r'''
const fs = require('fs');
const vm = require('vm');
const fixture = JSON.parse(process.argv[2]);
const node = (value, counters = '') => ({
  textContent: value + counters,
  childNodes: [{nodeType: 3, textContent: value}, {nodeType: 1, textContent: counters}],
});
const cards = fixture.cards.map(card => ({
  getAttribute: () => card.href,
  querySelector: selector => selector === 'h3' ? node(card.name, card.counters) : null,
  textContent: card.name + card.counters,
}));
const menus = fixture.menus.map(value => ({querySelector: () => node(value)}));
const document = {
  querySelector: selector => selector === 'h1' ? node('NCL Fall 2026 Gymnasium', 'Guided Training') : null,
  querySelectorAll: selector => selector === 'a[href]' ? cards :
    selector === '[role="listbox"].ui.inline.dropdown' ? menus : [],
};
const extract = vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), {document, URL});
process.stdout.write(JSON.stringify(extract()));
'''


@unittest.skipUnless(shutil.which('node'), 'Node is needed for DOM fixture tests')
class ExtractorDiscoveryTests(unittest.TestCase):
    def extract(self, menus):
        fixture = dict(menus=menus, cards=[dict(
            href='/module/' + '1'*24 + '/' + '2'*24,
            name='Network Traffic Analysis', counters='11 Challenges66 Questions0% Completion')])
        result = subprocess.run(['node', '-e', HARNESS, str(EXTRACTOR), json.dumps(fixture)],
                                capture_output=True, text=True, timeout=5, check=True)
        return json.loads(result.stdout)

    def test_module_card_identity_excludes_nested_progress_counters(self):
        result = self.extract([])
        self.assertEqual(result['links'][0]['title'], 'Network Traffic Analysis')
        self.assertEqual(result['event'], 'NCL Fall 2026 Gymnasium')

    def test_category_available_before_challenge_selector_finishes_rendering(self):
        result = self.extract(['Network Traffic Analysis'])
        self.assertEqual(result['category'], 'Network Traffic Analysis')
        self.assertIsNone(result['challenge'])

    def test_incomplete_question_layout_keeps_discovery_metadata(self):
        result = self.extract(['Network Traffic Analysis', 'Synthetic capture (Easy)'])
        self.assertEqual(result['category'], 'Network Traffic Analysis')
        self.assertEqual(result['title'], 'Synthetic capture (Easy)')
        self.assertIsNone(result['challenge'])
        self.assertIsNotNone(result['issue'])
