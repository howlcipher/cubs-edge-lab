"""Compact, deterministic publication projection of local measurements."""

import hashlib
import json


def verdict(candidate, result):
    if candidate == 'CALLUP':
        samples = [i for i in result if i.get('independent_level_sample')]
        measured = [i for i in samples if i.get('dated_splits') is not None]
        if not measured:
            return 'NOT ASSESSED', 'No game log availability was measured.'
        if not any(i['dated_splits'] > 0 for i in measured):
            return 'NOT FEASIBLE', 'No measured player returned dated logs.'
        return 'PARTIAL', ('The non-random sample is limited to one hitting '
                           'leader per season and level; population and '
                           'point-in-time availability remain unverified.')
    items = [i for i in result if i.get('candidate') == candidate
             and 'matched_events' in i]
    if not items:
        return 'NOT ASSESSED', 'No election or selection window was measured.'
    if not any(i['matched_events'] for i in items):
        return 'NOT FEASIBLE', 'No matches under the stated definition.'
    if candidate == 'MILBFA':
        return 'PARTIAL', ('Proxy counts measure team level and season play, '
                           'not minor-league contract status. Confirmed '
                           'minor-league-only election counts remain unknown.')
    return 'PARTIAL', ('Description-derived identifiers recover candidates; '
                       'coverage and draft phase require reconciliation to '
                       'an independent official selection list.')


def query_ref(query):
    encoded = json.dumps(query, sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def summarize(result):
    if result is None:
        return None
    summary = {'candidates': {}, 'failure_count': sum(
        'failure' in item for item in result)}
    for candidate in ('MILBFA', 'RULE5', 'CALLUP'):
        items = [i for i in result if i.get('candidate') == candidate]
        rows, examples = [], []
        for item in items:
            if candidate == 'CALLUP' and not item.get(
                    'independent_level_sample'):
                continue
            fields = {
                'MILBFA': ['season', 'matched_events', 'counts'],
                'RULE5': ['season', 'rows', 'matched_events',
                          'text_matched_events', 'window_union_matches',
                          'identifiers', 'r5_without_text', 'dr_with_text',
                          'dr_without_text'],
                'CALLUP': ['season', 'sport_id', 'dated_splits',
                           'through_june', 'first_date', 'last_date'],
            }[candidate]
            row = {k: item.get(k) for k in fields}
            row['query_refs'] = [query_ref(q) for q in
                                 [item['query']] +
                                 item.get('team_queries', []) +
                                 item.get('history_queries', [])]
            if candidate == 'CALLUP':
                row['sample_size'] = 1
                row['measured'] = int(item['dated_splits'] is not None)
                records = [{'player_id': item['sample_player']}]
            elif candidate == 'MILBFA':
                records = [e['event'] for e in item['evidence']]
            else:
                records = item['events']
            rows.append(row)
            for record in records[:5 - len(examples)]:
                examples.append({'record': record, 'query': item['query']})
        name, reason = verdict(candidate, result)
        summary['candidates'][candidate] = {
            'rows': rows, 'examples': examples,
            'verdict': name, 'reason': reason}
    return summary
