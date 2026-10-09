"""Synthetic boundary tests and read-only recorded artifact verification."""

import unittest
from pathlib import Path

from cubs_edge_lab.probe.evidence import RecordedClient, project
from cubs_edge_lab.probe.probes import classify, rule_groups, rule_text, run
from cubs_edge_lab.probe.summary import verdict

ROOT = Path(__file__).resolve().parents[1]
QUERY = {'endpoint': 'https://example.invalid/stats', 'params': {}}


def sample(dated=3, player=1):
    return {'candidate': 'CALLUP', 'season': 2023, 'sport_id': 11,
            'independent_level_sample': True, 'sample_player': player,
            'dated_splits': dated, 'query': QUERY}


class VerdictTests(unittest.TestCase):
    def test_small_sample_never_feasible(self):
        # Even expanding a fixture cannot override the downgraded design.
        for count in [1, 19, 20, 28]:
            result = [sample(player=p) for p in range(count)]
            self.assertEqual(verdict('CALLUP', result)[0], 'PARTIAL')

    def test_missing_and_zero_logs_are_distinct(self):
        self.assertEqual(verdict('CALLUP', [sample(None)])[0], 'NOT ASSESSED')
        self.assertEqual(verdict('CALLUP', [sample(0)])[0], 'NOT FEASIBLE')
        self.assertEqual(verdict('CALLUP', [sample(), sample(None)])[0],
                         'PARTIAL')
        self.assertEqual(verdict('CALLUP', [])[0], 'NOT ASSESSED')

    def test_events_do_not_prove_completeness(self):
        for candidate in ['MILBFA', 'RULE5']:
            self.assertEqual(verdict(candidate, [])[0], 'NOT ASSESSED')
            item = {'candidate': candidate, 'matched_events': 0}
            self.assertEqual(verdict(candidate, [item])[0], 'NOT FEASIBLE')
            item['matched_events'] = 7
            self.assertEqual(verdict(candidate, [item])[0], 'PARTIAL')


class EvidenceTests(unittest.TestCase):
    def test_projection_retains_parser_inputs_only(self):
        value = {'people': [{'id': 7, 'birthDate': 'synthetic', 'stats': [
            {'splits': [{'season': '2023', 'sport': {'id': 11},
                         'stat': {'hits': 10}}]}]}]}
        result = project(value)
        self.assertNotIn('birthDate', result['people'][0])
        self.assertEqual(result['people'][0]['stats'][0]['splits'][0]['stat'],
                         {})

    def test_recorded_client_missing_query_is_failure(self):
        result = run(RecordedClient([]))
        self.assertTrue(result)
        self.assertTrue(all('failure' in i for i in result))


class ClassificationTests(unittest.TestCase):
    def event(self, player, team=None):
        return {'player_id': player, 'from_team': None, 'to_team': team}

    def history(self, sports):
        return {s: s in sports for s in [1, 11, 12, 13, 14, 16]}

    def test_agreement_disagreement_unresolved_and_mlb_precedence(self):
        events = [self.event(1, 10), self.event(2, 10),
                  self.event(3, 99), self.event(4, 20), self.event(5, 10)]
        histories = {1: self.history([11]), 2: self.history([1, 11]),
                     3: self.history([]), 4: self.history([1]), 5: {11: True}}
        counts, evidence = classify(events, {10: [11], 20: [1]}, histories)
        self.assertEqual(counts['minor_only_proxy'], 1)
        self.assertEqual(counts['agreement'], 2)
        self.assertEqual(counts['disagreement'], 1)
        self.assertEqual(counts['unresolved'], 2)
        self.assertEqual(evidence[1]['B'], 'mlb')
        self.assertIsNone(counts['confirmed_minor_contract_elections'])

    def test_rule5_derived_codes_and_non_rule_dr(self):
        rows = [{'code': code, 'type_desc': 'Synthetic draft', 'id': n,
                 'date': '2000-12-01', 'description': desc}
                for n, (code, desc) in enumerate([
                    ('DR', 'Selected in the Rule 5 draft'),
                    ('DR', 'Selected in Rule V minor league phase'),
                    ('DR', 'Amateur draft'), ('R5', 'Unexplained'),
                    ('OTHER', 'Synthetic Rule 5 selection')])]
        groups = rule_groups(rows)
        dr = next(g for g in groups if g['code'] == 'DR')
        self.assertEqual(dr['count'], 3)
        self.assertEqual(dr['rule_text_count'], 2)
        self.assertEqual(len(dr['non_rule_examples']), 1)
        identifiers = {g['code'] for g in groups if g['rule_text_count']}
        self.assertEqual(identifiers, {'DR', 'OTHER'})
        self.assertFalse(rule_text({'description': 'Rule 50'}))


if __name__ == '__main__':
    unittest.main()
