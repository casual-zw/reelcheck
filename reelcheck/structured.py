"""Select evidence IDs with JSON schema, then render source text deterministically.

This preserves the model's substantive judgment; it cannot repair a wrong verdict
or prove that a selected passage entails the claim. Whole passages are attached,
so quote-copying success in this mode is renderer behavior, not model skill.

Fireworks JSON-schema mode disables reasoning output. This is a generation-mode
change as well as a formatting change and must not be called a pure prompt ablation.
The mode was introduced after inspecting real-video development failures.
"""
from copy import deepcopy
import json

from .contract import REASONS, VERDICTS, validate
from .prompts import COMMON, CHECKLIST, public_input

MODE = 'citation_ids'
MODE_NOTE = ('JSON-schema generation with deterministic claim/quote rendering; '
             'Fireworks schema mode disables reasoning output. Quote validity is '
             'renderer-enforced, not evidence of semantic entailment.')
FIELDS = {'verdict', 'citation_ids', 'uncertainty_reason', 'explanation'}


def output_schema(case):
    ids = [p['id'] for p in case['evidence']]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate input passage IDs')
    item_schema = {'type': 'string', 'enum': ids} if ids else {'type': 'string'}
    return {
        'type': 'object', 'additionalProperties': False,
        'required': ['verdict', 'citation_ids', 'uncertainty_reason', 'explanation'],
        'properties': {
            'verdict': {'type': 'string', 'enum': sorted(VERDICTS)},
            'citation_ids': {'type': 'array', 'items': item_schema,
                             'uniqueItems': True, 'maxItems': len(ids)},
            'uncertainty_reason': {'type': ['string', 'null'], 'enum': [*sorted(REASONS), None]},
            'explanation': {'type': 'string', 'minLength': 1},
        },
    }


def structured_messages(case, system='B'):
    if system not in {'A', 'B', 'D'}:
        raise ValueError('citation_ids mode supports direct/checklist prompts, not requirement maps')
    semantics, marker, _ = COMMON.partition('Quote exact nonempty substrings')
    if not marker:
        raise ValueError('Common prompt contract boundary changed; review the structured prompt')
    contract = '''Return only a JSON object with exactly these four keys:
{"verdict":"supported|contradicted|insufficient", "citation_ids":["passage ID"],
 "uncertainty_reason":null, "explanation":"brief evidence-bounded explanation"}.
Evaluate the complete original claim, including every material qualifier. Select
only supplied passage IDs whose evidence justifies your verdict. Do not output
claim_text or quotation text: a deterministic renderer will copy the original claim
and selected passages verbatim. Do not repeat IDs. Decisive verdicts need citations.
For insufficient, uncertainty_reason must be missing_evidence, conflicting_evidence,
missing_context, or stale_evidence. For decisive verdicts it must be null.
'''
    checklist = CHECKLIST.replace('Verify every quote exists and supports its use.',
                                  'Verify every selected passage supports its use.') if system == 'D' else ''
    return [{'role': 'system', 'content': semantics + contract + checklist},
            {'role': 'user', 'content': json.dumps(public_input(case), ensure_ascii=False)}]


def request_config(variant, case):
    config = deepcopy(variant)
    parameters = dict(config.get('parameters', {}))
    if 'response_format' in parameters:
        raise ValueError('citation_ids mode owns response_format; remove the manual override')
    parameters['response_format'] = {'type': 'json_schema',
                                    'json_schema': {'name': 'Verification', 'schema': output_schema(case)}}
    config['parameters'] = parameters
    return config


def render_citation_ids(raw, case):
    """Render without repairing or changing verdict, reason, or explanation."""
    if not isinstance(raw, dict) or set(raw) != FIELDS:
        raise ValueError('Structured output must contain exactly the four required fields')
    if not isinstance(raw['verdict'], str) or raw['verdict'] not in VERDICTS:
        raise ValueError('Invalid structured verdict')
    ids = raw['citation_ids']
    if not isinstance(ids, list) or any(not isinstance(pid, str) for pid in ids):
        raise ValueError('citation_ids must be a list of strings')
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate citation IDs')
    passages = {p['id']: p['text'] for p in case['evidence']}
    if any(pid not in passages for pid in ids):
        raise ValueError('Unknown citation ID')
    output = {'claim_text': case['claim_text'], 'verdict': raw['verdict'],
              'citations': [{'passage_id': pid, 'quote': passages[pid]} for pid in ids],
              'uncertainty_reason': raw['uncertainty_reason'], 'explanation': raw['explanation']}
    errors = validate(output, case)
    if errors:
        raise ValueError('; '.join(errors))
    return output
