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
  querySelector: () => null,
});
const heading = (value, counters) => {
  const label = node(value, counters);
  return fixture.nested ? {textContent: label.textContent, childNodes: [label],
    querySelector: selector => selector === ':scope > .content' ? label : null} : label;
};
const cards = fixture.cards.map(card => ({
  getAttribute: () => card.href,
  querySelector: selector => selector === 'h3' ? heading(card.name, card.counters) : null,
  textContent: card.name + card.counters,
}));
const menus = fixture.menus.map(value => ({querySelector: () => node(value)}));
const textNode = textContent => ({nodeType: 3, textContent});
const element = (tagName, childNodes = []) => ({
  tagName, childNodes, nodeType: 1, style: {},
  children: childNodes.filter(n => n.nodeType === 1),
  get textContent() { return childNodes.map(n => n.textContent).join(''); },
  getAttribute: () => null,
  querySelectorAll: () => [],
});
const prompt = element('DIV', [textNode('Input: '), element('CODE', [textNode('412042')])]);
prompt.style.padding = '0px';
const description = element('DIV', [prompt]);
const question = element('TD', [element('DIV', [textNode('Q1 - 5 points')]),
  textNode('What is the decoded hex value?')]);
const response = element('TD', [textNode('PRIVATE SAVED ANSWER')]);
response.classList = {contains: value => ['center', 'aligned'].includes(value)};
const row = element('TR', [question, response]);
row.getAttribute = () => 'synthetic-question-id';
const table = {querySelectorAll: selector => selector === ':scope > tbody > tr[data-value]' ? [row] : []};
const document = {
  querySelector: selector => selector === 'h1' ? node('NCL Fall 2026 Gymnasium', 'Guided Training') : null,
  querySelectorAll: selector => selector === 'a[href]' ? cards :
    selector === '[role="listbox"].ui.inline.dropdown' ? menus :
    fixture.complete && selector === '.ui.basic.segment.body:not(.fat)' ? [description] :
    fixture.complete && selector === '.ui.basic.segment.fat.tall.body > table' ? [table] : [],
};
const extract = vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), {document, URL});
process.stdout.write(JSON.stringify(extract()));
'''


@unittest.skipUnless(shutil.which('node'), 'Node is needed for DOM fixture tests')
class ExtractorDiscoveryTests(unittest.TestCase):
    def extract(self, menus, nested=False, complete=False):
        fixture = dict(menus=menus, nested=nested, complete=complete, cards=[dict(
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

    def test_semantic_ui_card_content_excludes_nested_subheader_counts(self):
        result = self.extract([], nested=True)
        self.assertEqual(result['links'][0]['title'], 'Network Traffic Analysis')

    def test_incomplete_question_layout_keeps_discovery_metadata(self):
        result = self.extract(['Network Traffic Analysis', 'Synthetic capture (Easy)'])
        self.assertEqual(result['category'], 'Network Traffic Analysis')
        self.assertEqual(result['title'], 'Synthetic capture (Easy)')
        self.assertIsNone(result['challenge'])
        self.assertIsNotNone(result['issue'])

    def test_extracted_question_reaches_verifier_without_table_delimiter(self):
        from bots.skyline_archive.verify_worker import check
        result = self.extract(['Cryptography', 'Synthetic decode (Easy)'], complete=True)
        question = result['challenge']['questions'][0]
        self.assertNotIn('|', question)
        self.assertNotIn('PRIVATE SAVED ANSWER', json.dumps(result))
        outcome = check(dict(question=question, instructions=result['challenge']['prompt'],
                             files=[], answer='A B', root=str(EXTRACTOR.parent)))
        self.assertEqual(outcome['outcome'], 'Verified correct')


LEADERBOARD_HARNESS = r'''
const fs = require('fs'), vm = require('vm');
const hidden = process.argv[2] === 'hidden';
const node = (textContent, visible = true) => ({textContent, getClientRects: () => visible ? [{}] : []});
const cells = ['12', 'Synthetic Team', '500', '90.00%', 'one minute ago', '50.00%'].map(s => node(s));
const row = {getAttribute: () => 'synthetic-team-id', querySelector: () => ({}), querySelectorAll: () => cells};
const table = {...node('', !hidden), querySelectorAll: s => s === 'thead th' ?
  ['Rank', 'Handle', 'Points', 'Accuracy', 'Last Correct Submission', 'Completion'].map(s => node(s)) : [row]};
const document = {querySelector: () => null, querySelectorAll: s => s === 'table' ? [table] :
  s === 'h2' ? [node('Synthetic Competition')] : s === '[role="status"]' ? [node('Rank: 12 / 120')] : []};
const extract = vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'),
  {document, getComputedStyle: () => ({visibility:'visible'})});
process.stdout.write(JSON.stringify(extract()));
'''


@unittest.skipUnless(shutil.which('node'), 'Node is needed for DOM fixture tests')
class LeaderboardDOMTests(unittest.TestCase):
    def extract(self, hidden=False):
        path=EXTRACTOR.with_name('leaderboard_dom.js')
        result=subprocess.run(['node','-e',LEADERBOARD_HARNESS,str(path),'hidden' if hidden else 'visible'],
                              capture_output=True,text=True,check=True,timeout=5)
        return json.loads(result.stdout)

    def test_visible_rank_table_keeps_identity_and_complete_cells(self):
        snapshot=self.extract()
        row=snapshot['tables'][0]['rows'][0]
        self.assertEqual(row['id'],'synthetic-team-id')
        self.assertEqual(row['cells'][2],'500')
        self.assertTrue(row['own'])
        self.assertEqual(snapshot['statuses'],['Rank: 12 / 120'])

    def test_hidden_previous_tab_is_not_counted_twice(self):
        self.assertEqual(self.extract(hidden=True)['tables'],[])
