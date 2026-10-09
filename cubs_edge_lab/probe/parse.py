"""Extract observations without imputing missing fields."""

import re
from datetime import date as calendar_date

from .client import MalformedResponseError


def transactions(payload):
    require_object(payload)
    rows = payload.get('transactions')
    if not isinstance(rows, list):
        raise MalformedResponseError('Missing transactions array')
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise MalformedResponseError('Invalid transaction')
        for key in ['person', 'fromTeam', 'toTeam']:
            require_object(row.get(key) or {})
        for key in ['date', 'description', 'typeCode', 'typeDesc']:
            if row.get(key) is not None and not isinstance(row[key], str):
                raise MalformedResponseError('Invalid transaction ' + key)
        result.append({
            'id': row.get('id'), 'date': row.get('date'),
            'player_id': (row.get('person') or {}).get('id'),
            'code': row.get('typeCode'),
            'type_desc': row.get('typeDesc'),
            'description': row.get('description'),
            'from_team': (row.get('fromTeam') or {}).get('id'),
            'to_team': (row.get('toTeam') or {}).get('id'),
        })
    return result


def innings_outs(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.[012]', value):
        raise MalformedResponseError('Invalid baseball innings: ' + str(value))
    innings, outs = value.split('.')
    return int(innings) * 3 + int(outs)


def stats(payload):
    require_object(payload)
    groups = payload.get('stats')
    if groups is None or groups == []:
        return None
    if not isinstance(groups, list):
        raise MalformedResponseError('Invalid stats array')
    result = []
    saw_splits = False
    for group in groups:
        require_object(group)
        require_object(group.get('group') or {})
        splits = group.get('splits')
        if splits is None:
            continue
        saw_splits = True
        if not isinstance(splits, list):
            raise MalformedResponseError('Invalid splits array')
        for split in splits:
            require_object(split)
            require_object(split.get('sport') or {})
            require_object(split.get('team') or {})
            date = split.get('date')
            if date is not None:
                try:
                    calendar_date.fromisoformat(date)
                except (ValueError, TypeError) as exc:
                    raise MalformedResponseError('Invalid game date') from exc
            stat = split.get('stat')
            if not isinstance(stat, dict):
                raise MalformedResponseError('Missing stat object')
            if 'inningsPitched' in stat:
                innings_outs(stat['inningsPitched'])
            result.append({
                'person_id': (split.get('person') or split.get('player') or {}).get('id'),
                'sport_id': (split.get('sport') or {}).get('id'),
                'team_id': (split.get('team') or {}).get('id'),
                'date': split.get('date'), 'stat': stat,
                'season': split.get('season'),
                'group': (group.get('group') or {}).get('displayName'),
            })
    if not saw_splits:
        return None
    return result


def teams_summary(payload):
    """Ids and league name counts. Missing league names stay null."""
    require_object(payload)
    rows = payload.get('teams')
    if not isinstance(rows, list):
        raise MalformedResponseError('Missing teams array')
    ids = []
    leagues = {}
    for team in rows:
        if not isinstance(team, dict):
            raise MalformedResponseError('Invalid team')
        if team.get('id') is not None:
            ids.append(team['id'])
        league = team.get('league') or {}
        if not isinstance(league, dict):
            raise MalformedResponseError('Invalid league')
        name = league.get('name')
        if name is not None and not isinstance(name, str):
            raise MalformedResponseError('Invalid league name')
        leagues[name] = leagues.get(name, 0) + 1
    counts = [{'name': name, 'count': leagues[name]}
              for name in sorted(leagues, key=lambda item: ''
                                 if item is None else item)]
    return {'ids': sorted(set(ids)), 'league_counts': counts}


def scoped_stats(payload, season, sport):
    rows = stats(payload)
    if rows is None:
        return {'splits': None, 'excluded_splits': None}
    selected = [r for r in rows if str(r['season']) == str(season)
                and r['sport_id'] == sport]
    return {'splits': selected, 'excluded_splits': len(rows) - len(selected)}


def require_object(value):
    if not isinstance(value, dict):
        raise MalformedResponseError("Expected an object")
