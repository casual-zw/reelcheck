"""Fail closed on stale reviews, altered evidence, broken provenance or label leakage."""
import hashlib
import json
import sys
from pathlib import Path
from collect import ROOT, DATA, read_jsonl
from fireworks_client import load, digest, save
from curate_cases import B, PROTOCOL, PROMPT, VERDICT, validate_vote


def verify_passage(p,s):
    assert digest(s['text'])==s['text_sha256'],'Source snapshot changed'
    assert p['source_text_sha256']==s['text_sha256'],'Wrong source hash'
    assert 0<=p['start']<p['end']<=len(s['text']),'Invalid source span'
    assert p['text']==s['text'][p['start']:p['end']],'Passage is not the exact source span'


def verify_request(receipt,record,case,review,audit=False):
    payload={'case':case}
    prompt=PROMPT
    if audit:
        payload['reviews']=[v['result'] for v in review['votes']]
        prompt+=' Reconcile the two independent reviews against the actual evidence, not by majority vote.'
    expected_run_id=PROTOCOL+':'+case['case_id']+(':reconcile' if audit else ':judge:'+str(review['votes'].index(record)))
    assert receipt['run_id']==expected_run_id,'Wrong protocol/run ID'
    bodies=[]
    for cap in ([3000,6000] if audit else [700,1400]):
        body={'model':record['model'],'messages':[
            {'role':'system','content':prompt+'\nJSON schema:\n'+json.dumps(VERDICT)},
            {'role':'user','content':json.dumps(payload)}],
            'temperature':0.6,'max_tokens':cap,
            'response_format':{'type':'json_schema','json_schema':{'name':'annotation','schema':VERDICT}},
            'reasoning_effort':'low' if audit else 'none'}
        bodies.append(body)
    assert any(receipt['input_sha256']==digest(body) and record['receipt']==digest({'body':body,'run_id':expected_run_id}) for body in bodies),'Request does not match fixed claim/evidence input'


def verify():
    cases=read_jsonl(B/'inputs.jsonl');refs=read_jsonl(B/'reference_labels.jsonl')
    provenance={p['case_id']:p for p in read_jsonl(B/'provenance.jsonl')}
    sources={s['evidence_id']:s for s in read_jsonl(B/'source_snapshots.jsonl')}
    ids=[c['case_id'] for c in cases]
    assert len(ids)==50 and len(set(ids))==50
    assert set(ids)==set(provenance)=={r['case_id'] for r in refs}
    byid={r['case_id']:r for r in refs};checked_videos=set();requests=set();passage_count=0
    for c in cases:
        assert set(c)=={'case_id','group_id','split','as_of','claim_text','evidence'},'Input field leakage'
        assert c['evidence'] and c['split']=='development_pending_review'
        p=provenance[c['case_id']];key=p['video_key'];ref=byid[c['case_id']]
        assert ref['input_sha256']==digest(c) and ref['human_verified'] is False
        assert p['claim_packet_sha256']==digest(load(DATA/'grounded/claims'/(key+'.json')))
        assert p['evidence_packet_sha256']==digest(load(DATA/'grounded/evidence'/(key+'.json')))
        if key not in checked_videos:
            assert hashlib.sha256((ROOT/p['video']['path']).read_bytes()).hexdigest()==p['video']['sha256']
            checked_videos.add(key)
        media=load(DATA/'bulk/media'/key/'prepared.json')
        assert media['video_sha256']==p['video']['sha256']
        quote=' '.join(p['transcript_quote'].split()).casefold()
        assert not quote or quote in ' '.join(media['transcript']['text'].split()).casefold()
        assert quote or p['frame_indices']
        for i in p['frame_indices']:assert (ROOT/media['frames'][i]['path']).is_file()
        known={e['passage_id']:e for e in p['passages']}
        assert len({e['id'] for e in c['evidence']})==len(c['evidence'])
        for e in c['evidence']:
            assert set(e)=={'id','source_id','url','retrieved_date','text','sha256'}
            assert hashlib.sha256(e['text'].encode()).hexdigest()==e['sha256']
            source=sources[e['source_id']];span=known[e['id']]
            verify_passage(span,source)
            assert e['text']==span['text'] and e['url']==span['url']
            if source.get('raw_json_path'):assert digest(load(ROOT/source['raw_json_path']))==source['raw_json_sha256']
            passage_count+=1
        review=load(B/'reviews'/(c['case_id']+'.json'))
        assert review['case_sha256']==digest(c) and review['provenance_sha256']==digest(p)
        assert len({v['model'] for v in review['votes']})==2
        final=review['reconciliation'] or review['votes'][0]
        assert final['result']['verdict']==ref['verdict']
        validate_vote(final['result'],c)
        for v in review['votes']+([review['reconciliation']] if review['reconciliation'] else []):
            receipt=load(DATA/'labeling/api'/(v['receipt']+'.json'))
            assert receipt['requested_model']==v['model'] and receipt['result']==v['result']
            verify_request(receipt,v,c,review,audit=v is review['reconciliation'])
            assert receipt.get('request_id') and receipt['request_id'] not in requests
            requests.add(receipt['request_id'])
        for es in ref['acceptable_evidence_sets']:
            assert set(es)<={e['id'] for e in c['evidence']}
            if ref['verdict']!='insufficient':assert es
    release=load(B/'release_manifest.json')
    for name,sha in release['files_sha256'].items():assert hashlib.sha256((B/name).read_bytes()).hexdigest()==sha
    # Run the real harness's data validator; does not invoke a model.
    sys.path.insert(0,str(ROOT/'Reelcheck'))
    from reelcheck.__main__ import check_data
    from reelcheck.prompts import public_input
    check_data(cases)
    assert all(set(public_input(c))=={'case_id','claim_text','as_of','evidence'} for c in cases)
    summary={'cases':50,'physical_videos_hash_verified':len(checked_videos),
        'exact_passage_occurrences_checked':passage_count,'unique_model_request_receipts':len(requests),
        'label_leakage_check':'passed','reelcheck_input_validation':'passed','human_verified':0,
        'scope':'Integrity and compatibility checks; not a proof of factual label correctness.'}
    save(B/'verification.json',summary);print(json.dumps(summary,indent=2))


if __name__=='__main__':verify()
