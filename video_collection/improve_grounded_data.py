"""Reproducible, offline evidence-reference audit and paired packet diagnostics.

Does not alter the frozen grounded60 release or call a model/provider.
All decisions below are AI reviews of cached passages, not human verification.
"""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
BASE = ROOT / 'data/grounded60'
REV = ROOT / 'data/grounded60_v2'
CHALLENGE = ROOT / 'data/evidence_challenge18'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')

def lines(path, rows):
    path.write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in rows))

# Each alternative was reviewed against the entire claim, independently of which
# IDs a baseline happened to cite. Multiple IDs within one list mean conjunction.
AUDIT = {
 'video50_-J7EWBYipqI_c1': ([['p_3056463842f55c13'], ['p_abcf2286fca06377'], ['p_0b6a8ca4f39f4a22']], 'Each passage independently defines PATH lookup of executables in directories; corroborating all three is unnecessary.'),
 'video50_-J7EWBYipqI_c2': ([['p_51c6f2a024e48ab6'], ['p_0dfcb71531f8bbb2']], 'Both passages explicitly state that the first match in PATH directory order wins.'),
 'video50_-J7EWBYipqI_c3': ([['p_51c6f2a024e48ab6'], ['p_3056463842f55c13', 'p_3bc462e7cd1c31e2']], 'The first passage explains adding directories to make executables discoverable. The second alternative combines PATH semantics with the append command.'),
 'video50_0kbhxIwNYBA_c1': ([['p_f2d9d73657fad60f'], ['p_fa9bce9611efc7c9']], 'The abstract explicitly says both groups exercised four times weekly for eight weeks; the methods separately states the same training schedule.'),
 'video50_0kbhxIwNYBA_c2': ([['p_7e4e4c50ca5094dc'], ['p_6f08cf760b2b5e98'], ['p_ea4476f27a87d489']], 'Each passage reports squat 1RM gains 4.0 kg lower in TRE, with the same study and comparison. Duplicate abstract copies are alternatives.'),
 'video50_0kbhxIwNYBA_c3': ([['p_6f08cf760b2b5e98'], ['p_ea4476f27a87d489']], 'Each states FED added 1.4 kg more fat mass, establishing less fat gain in TRE.'),
 'video50_F4zM5_04uA0_c1': ([['p_625a6483e7b06e40']], 'The USDA record gives unsweetened dry gelatin 85.6 g protein per 100 g. One food exceeding the claimed 57 g refutes the universal highest-of-any-food assertion; a ranking of selected plant foods is unnecessary.'),
 'video50_rMFuvyLE4gQ_c1': ([['p_003082f519188dd7'], ['p_1aa9aac5b0de2b76'], ['p_12c05261ebef4d38']], 'Each clinical source passage explicitly identifies tartar as hardened plaque.'),
 'video50_rMFuvyLE4gQ_c2': ([['p_003082f519188dd7'], ['p_12c05261ebef4d38']], 'Each clinical passage says only professional cleaning removes tartar. This directly counters home dissolution. Peroxide clearance alone is not evidence of tartar removal or its impossibility.'),
 'video50_rMFuvyLE4gQ_c3': ([['p_003082f519188dd7'], ['p_12c05261ebef4d38']], 'Each says only professional cleaning removes existing tartar; reduced dietary sugar preventing future decay is a different outcome.'),
 'news10_serbia': ([['p_09fec9299b2d9207'], ['p_6030bc63bc8e0948']], 'Each dated passage identifies the student-led election victory and concession in October 2026. Two reports are corroboration, not a required conjunction.'),
 'news10_netanyahu_recycled': ([['p_cf7921c5a3005646'], ['p_2bf49015b653493d']], 'Each fact-check passage explicitly links this viral footage to Ahmed Dogan in Bulgaria in 2013. The standalone BBC account describes an old incident but cannot alone establish the footage match.'),
}

# Evidence is kept byte-for-byte from source packets. Context lists have been
# read in full: none establishes or contradicts the complete target claim.
# Original = complete original packet; missing = context only; restored = the
# same context plus one minimal, reviewed decisive evidence set.
PAIRS = [
 ('video50_0kbhxIwNYBA_c2', ['p_7b1b97853addbfd2', 'p_fa9bce9611efc7c9'], ['p_7e4e4c50ca5094dc'], 'Study methods and conflict-of-interest text omit the magnitude and direction of the squat strength difference.'),
 ('video50_F4zM5_04uA0_c1', ['p_28116eb901131d61', 'p_781662ec73cfad6b', 'p_d41de8b721604ae3'], ['p_625a6483e7b06e40'], 'Selected-food and plant-food rankings cannot establish a universal maximum over every food. Removing gelatin removes the counterexample; it does not make the universal claim supported.'),
 ('news10_netanyahu_recycled', ['p_4afabcb0144545fb', 'p_d7ceb074f05a00fb'], ['p_2bf49015b653493d'], 'The historical BBC account alone has no link to the current viral video. The removed reverse-image-search passage supplies that identity link.'),
 ('news10_patterson', ['p_8408423b52bb0a02', 'p_875ce018a5ea0501'], ['p_24709dcc1f1228d6', 'p_ebbf22ce52d51481'], 'The court notice describes the appeals and original 33-year term, not the outcome. A hearing or published judgment is not proof of a particular disposition.'),
 ('news10_charles', ['p_6743abaeff8e197a', 'p_fba7edb429254e01', 'p_694d10d968036c64'], ['p_a47ea973859e5185', 'p_3dc6ef3c54124050'], 'A planned visit and parade establish context but cannot establish a subsequently occurring downpour.'),
 ('news10_apple', ['p_36bd5a0c56931b0c'], ['p_7400976f4da9fd0e'], 'The retained passage establishes the 12-core CPU but is cut before any GPU core count. The compound claim remains incomplete.'),
]

def main():
    cases = read(BASE/'inputs.jsonl'); gold = read(BASE/'reference_labels.jsonl')
    by_id = {c['case_id']: c for c in cases}
    original_gold = {g['case_id']: g for g in gold}
    updated = copy.deepcopy(gold); new_gold = {g['case_id']:g for g in updated}
    audit = []
    for cid, (alternatives, reason) in AUDIT.items():
        evidence = {p['id']:p for p in by_id[cid]['evidence']}
        assert all(set(a) <= evidence.keys() and a for a in alternatives)
        g = new_gold[cid]
        before = copy.deepcopy(g['acceptable_evidence_sets'])
        for alt in alternatives:
            if alt not in g['acceptable_evidence_sets']:
                g['acceptable_evidence_sets'].append(alt)
        # Original model receipt IDs stay in the original release, not falsely
        # attributed to a later parent-agent modification.
        g.pop('review_receipts', None)
        g['agreement_status'] = 'parent_agent_evidence_set_audit_pending_independent_review'
        g['additional_audit'] = True
        audit.append({'case_id':cid, 'before':before, 'after':g['acceptable_evidence_sets'],
                      'reason':reason, 'reviewer':'Codex parent agent', 'human_verified':False,
                      'method':'cached_passage_semantic_review', 'verdict_changed':False,
                      'reviewed_passages': [evidence[i] for i in sorted({i for a in alternatives for i in a})]})
    REV.mkdir(exist_ok=True)
    for name in ['inputs.jsonl','provenance.jsonl','source_snapshots.jsonl','source_snapshot_variants.jsonl','membership.jsonl','split_groups.json']:
        if (BASE/name).exists(): shutil.copyfile(BASE/name, REV/name)
    lines(REV/'reference_labels.jsonl',updated); lines(REV/'evidence_audit.jsonl',audit)
    write(REV/'parent_release_manifest.json',json.loads((BASE/'release_manifest.json').read_text()))

    CHALLENGE.mkdir(exist_ok=True)
    out_cases=[]; out_gold=[]; provenance=[]; groups=[]; witnesses=[]
    for cid, context_ids, decisive_ids, reason in PAIRS:
        parent = by_id[cid]; emap={p['id']:p for p in parent['evidence']}
        assert not set(context_ids)&set(decisive_ids)
        group_cases=[cid]
        for variant in ['original','missing','restored']:
            case=copy.deepcopy(parent)
            case['case_id']='ec18_'+sha((cid+':'+variant).encode())[:16]
            case['split']='development_pending_review'
            if variant!='original':
                ids=context_ids if variant=='missing' else context_ids+decisive_ids
                case['evidence']=[copy.deepcopy(emap[i]) for i in ids]
            g=copy.deepcopy(new_gold[cid]); g['case_id']=case['case_id']
            g.pop('input_sha256',None); g.pop('review_receipts',None)
            g['agreement_status']='single_parent_agent_packet_review'
            if variant=='missing':
                g.update(verdict='insufficient',uncertainty_reason='missing_evidence',acceptable_evidence_sets=[[]])
            elif variant=='restored':
                g['acceptable_evidence_sets']=[decisive_ids]
            g['reason']=reason if variant=='missing' else 'Original claim and source-grounded verdict retained; decisive evidence present. '+reason
            g['human_verified']=False
            out_cases.append(case);out_gold.append(g);group_cases.append(case['case_id'])
            provenance.append({'case_id':case['case_id'],'parent_case_id':cid,'variant':variant,
                'source_release':'grounded60','group_id':parent['group_id'],
                'reason':reason,'human_verified':False,'reviewer':'Codex parent agent',
                'removed_passage_ids':sorted(set(emap)-{p['id'] for p in case['evidence']}),
                'decisive_passage_ids':decisive_ids,'context_passage_ids':context_ids})
            # Reference outputs verify structural compatibility, not an LLM result.
            witnesses.append({'claim_text':case['claim_text'],'verdict':g['verdict'],
                'citations':[] if variant=='missing' else [{'passage_id':i,'quote':emap[i]['text']} for i in decisive_ids],
                'uncertainty_reason':g['uncertainty_reason'],'explanation':g['reason']})
        groups.append({'group_id':parent['group_id'],'case_ids':group_cases})
    lines(CHALLENGE/'inputs.jsonl',out_cases);lines(CHALLENGE/'reference_labels.jsonl',out_gold)
    lines(CHALLENGE/'provenance.jsonl',provenance)
    # Retain all sibling claims in each parent cluster as well as variants.
    combined_groups=copy.deepcopy(json.loads((BASE/'split_groups.json').read_text()))
    for group in groups:
        matches=[g for g in combined_groups if group['case_ids'][0] in g['case_ids']]
        assert len(matches)==1
        matches[0]['case_ids'].extend(group['case_ids'][1:])
    write(CHALLENGE/'split_groups_with_parents.json',combined_groups)
    used_sources={p['source_id'] for c in out_cases for p in c['evidence']}
    snapshots=read(BASE/'source_snapshots.jsonl')
    snapshot_by_id={s['evidence_id']:s for s in snapshots}
    for case in out_cases:
        for passage in case['evidence']:
            source=snapshot_by_id[passage['source_id']]
            assert passage['text'] in source['text'], passage['id']
            assert passage['url']==source['url']
    lines(CHALLENGE/'source_snapshots.jsonl', [s for s in snapshots if s['evidence_id'] in used_sources])

    sys.path.insert(0,str(BASE/'deepseek_baseline_2026-11-02/source_snapshot'))
    from reelcheck.contract import validate
    from reelcheck.__main__ import check_data
    from reelcheck.evaluation import score
    for dataset, refs in [(cases,updated),(out_cases,out_gold)]:
        check_data(dataset)
        assert len({c['case_id'] for c in dataset})==len(dataset)==len(refs)
        for case,g in zip(dataset,refs):
            assert case['case_id']==g['case_id'] and not g['human_verified']
            assert all(set(a)<={p['id'] for p in case['evidence']} for a in g['acceptable_evidence_sets'])
    for case,g,witness in zip(out_cases,out_gold,witnesses):
        assert not validate(witness,case)
        assert score({'output':witness,'execution_status':'completed'},case,g)['automated_proxy_success']
    rows=read(BASE/'deepseek_baseline_2026-11-02/runs.jsonl')
    comparison=[]
    for row in rows:
        cid=row['case_id']
        before=score(row,by_id[cid],original_gold[cid]);after=score(row,by_id[cid],new_gold[cid])
        comparison.append({'case_id':cid,'before':before,'after':after})
    lines(REV/'baseline_rescore_details.jsonl',comparison)
    report={'cases':60,'audited_reference_cases':len(audit),'verdict_changes':0,
      'inputs_byte_identical_to_parent': (REV/'inputs.jsonl').read_bytes()==(BASE/'inputs.jsonl').read_bytes(),
      'baseline_proxy_before':sum(c['before']['automated_proxy_success'] for c in comparison),
      'baseline_proxy_after':sum(c['after']['automated_proxy_success'] for c in comparison),
      'baseline_verdict_matches':sum(c['after']['exact_verdict_match'] for c in comparison),
      'new_paid_inference_calls':0,'human_verified':False,
      'interpretation':'Reference repair on development data; rescoring identical saved outputs is not a model improvement or independent evaluation.'}
    write(REV/'validation.json',report)
    write(CHALLENGE/'validation.json',{'cases':18,'parent_claims':6,'parent_videos':6,
      'labels':{v:sum(g['verdict']==v for g in out_gold) for v in ['supported','contradicted','insufficient']},
      'evidence_hashes_valid':True,'reference_witnesses_pass_contract':18,
      'paid_inference_calls':0,'live_evaluation_performed':False,'human_verified':False,
      'warning':'Structural checks do not establish semantic correctness; labels are parent-agent drafts.'})
    for directory in [REV,CHALLENGE]:
        write(directory/'release_manifest.json',{'parent_inputs_sha256':sha((BASE/'inputs.jsonl').read_bytes()),
          'parent_reference_sha256':sha((BASE/'reference_labels.jsonl').read_bytes()),
          'files':{p.name:sha(p.read_bytes()) for p in sorted(directory.iterdir()) if p.is_file() and p.name!='release_manifest.json'},
          'human_verified':False,'contract_changed':False})
    print(json.dumps(report,indent=2))

if __name__=='__main__': main()
