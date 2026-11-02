"""Add five transcript-grounded claims to the audited grounded60 revision, offline."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd()
BASE=ROOT/'data/grounded60_v2'
OUT=ROOT/'data/grounded65'
def sha(b): return hashlib.sha256(b).hexdigest()
def read(p): return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
def write(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def lines(p,v): p.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in v))

SPECS=[
 ('news10_apple_neural','news10_apple',
  'The M6 in the newly announced 14-inch MacBook Pro has a dual 16-core Neural Engine.',
  'The M6 has a dual 16-core neural engine.', 'supported',
  [(0,'M6 makes the 14-inch MacBook Pro faster than ever',220)],
  'Apple explicitly identifies the Dual 16-core Neural Engine in this model. This does not assert a measured performance gain.'),
 ('news10_apple_wireless','news10_apple',
  'The newly announced 14-inch MacBook Pro with M6 supports Wi-Fi 7 and Bluetooth 6.',
  'get Wi-Fi 7 and Bluetooth 6.', 'supported',
  [(0,'Powerful connectivity :',500)],
  'The manufacturer explicitly specifies both wireless standards for the named model. No claim about the N1 component is inferred.'),
 ('news10_patterson_victims','news10_patterson',
  'Erin Patterson killed three relatives by serving them a meal containing death cap mushrooms.',
  'Erin Patterson killed three of her relatives after serving them a meal containing toxic death cat mushrooms.', 'supported',
  [(0,'Following a jury trial',500),(1,'Patterson was last year sentenced',650)],
  'The court identifies the three murder victims and the separate attempted-murder victim; the court report identifies the poisoned meal and death cap mushrooms. Both identity/count and mechanism are covered. ASR death cat is normalized to death cap using the corroborating report.'),
 ('news10_patterson_grounds','news10_patterson',
  'Patterson’s conviction appeal challenged evidentiary rulings, her cross-examination, and the jury’s accommodation arrangements.',
  "She appealed, challenging some of the evidence that was and wasn't allowed in the trial, as well as her cross-examination and the way the jury was held during deliberations.", 'supported',
  [(1,'In Patterson\'s conviction appeal',650),(1,"Patterson's lawyers argued mobile cell",800),(1,'The defence had accused senior prosecutor',650)],
  'The report separately describes the jury hotel objection, admitted/excluded evidence objections, and alleged unfair cross-examination. All three are needed for this compound claim; the claim concerns the grounds raised, not their validity.'),
 ('news10_stevens_never_met','news10_stevens',
  'Donald Trump had never met Haley Stevens before the November 2026 remarks in this clip.',
  "So I don't know Haley. I've never met Haley.", 'insufficient',
  [(0,'The president told reporters Sunday',900),(1,'Nov 01, 2026, 2:13 PM EST',1250)],
  'The clip establishes Trump asserted he had never met Stevens. The supplied reporting covers praise, an invitation, and a reported call, but no independently documented history of meetings. A phone call does not establish an in-person meeting. Neither support nor contradiction of the underlying historical assertion follows from this packet.'),
]

def main():
 OUT.mkdir(exist_ok=True)
 cases=read(BASE/'inputs.jsonl');refs=read(BASE/'reference_labels.jsonl');prov=read(BASE/'provenance.jsonl')
 membership=read(BASE/'membership.jsonl');groups=json.loads((BASE/'split_groups.json').read_text())
 sources=read(BASE/'source_snapshots.jsonl');by_source={s['evidence_id']:s for s in sources}
 parent_cases={c['case_id']:c for c in cases};new_cases=[];new_refs=[];reviews=[]
 for cid,parent,claim,transcript_quote,verdict,spans,reason in SPECS:
  packet_path=ROOT/f'data/latest_news10/packets/{parent}.json'
  packet=json.loads(packet_path.read_text());transcript=packet['media']['transcript']['text']
  assert transcript_quote in transcript, cid
  case=copy.deepcopy(parent_cases[parent]);case.update(case_id=cid,claim_text=claim,split='development_pending_review')
  selected=[];source_spans=[]
  for source_index,anchor,length in spans:
   source=packet['sources'][source_index]
   assert by_source[source['evidence_id']]['text']==source['text']
   start=source['text'].index(anchor);end=min(len(source['text']),start+length);text=source['text'][start:end]
   pid='p_'+sha((source['evidence_id']+':'+str(start)+':'+text).encode())[:16]
   p={'id':pid,'source_id':source['evidence_id'],'url':source['url'],'retrieved_date':source['retrieved_at'][:10],'text':text,'sha256':sha(text.encode())}
   selected.append(p);source_spans.append({'passage_id':pid,'source_id':source['evidence_id'],'start':start,'end':end})
  # Retain original topical context, adding source passages needed for the new claim.
  existing={p['id'] for p in case['evidence']}
  case['evidence'].extend(p for p in selected if p['id'] not in existing)
  gold={'case_id':cid,'verdict':verdict,'acceptable_evidence_sets':[[p['id'] for p in selected]] if verdict=='supported' else [[]],
   'uncertainty_reason':'missing_evidence' if verdict=='insufficient' else None,
   'slice':packet['video']['sampling_category'],'label_status':'AI_draft_pending_independent_human_review',
   'human_verified':False,'reason':reason,'agreement_status':'single_parent_agent_review'}
  if cid=='news10_apple_neural':
   gold['acceptable_evidence_sets'].extend([['p_7400976f4da9fd0e'],['p_11d9e9adda61c00d']])
  if cid=='news10_patterson_grounds':
   # The evidence-rulings passage also includes the cross-examination objection.
   gold['acceptable_evidence_sets'].append([selected[0]['id'],selected[1]['id']])
   gold['acceptable_evidence_sets'].append(['p_f77e3e9842b247a3',selected[1]['id']])
  for p in case['evidence']:
   assert p['text'] in by_source[p['source_id']]['text']
  video_path=ROOT/'data/videos'/f"{packet['video']['platform']}_{packet['video']['video_id']}.mp4"
  assert sha(video_path.read_bytes())==packet['media']['video_sha256']
  entry={'case_id':cid,'parent_case_id':parent,'video':packet['video'],'media':packet['media'],
   'claim_provenance':{'method':'automatic_transcript_claim_selection','transcript_quote':transcript_quote,
    'transcript_start_character':transcript.index(transcript_quote),'transcript_sha256':sha(transcript.encode()),
    'limitations':'ASR not independently audio-verified; no fabricated timestamp. See review reason for normalization.'},
   'packet_path':str(packet_path.relative_to(ROOT)),'packet_sha256':sha(packet_path.read_bytes()),
   'source_spans':source_spans,'human_verified':False}
  new_cases.append(case);new_refs.append(gold);prov.append(entry)
  membership.append({'case_id':cid,'source_release':'news_additional_claims5','parent_case_id':parent})
  matches=[g for g in groups if parent in g['case_ids']];assert len(matches)==1
  matches[0]['case_ids'].append(cid)
  reviews.append({'case_id':cid,'reviewer':'Codex parent agent','method':'transcript_and_cached_source_review',
   'verdict':verdict,'reason':reason,'human_verified':False,'paid_api_receipt':None,
   'input_sha256':sha(json.dumps(case,sort_keys=True,ensure_ascii=False).encode()),
   'decisive_passage_ids':[] if verdict=='insufficient' else [p['id'] for p in selected]})
 cases+=new_cases;refs+=new_refs
 for name,rows in [('inputs',cases),('reference_labels',refs),('provenance',prov),('membership',membership),('addition_reviews',reviews)]:lines(OUT/f'{name}.jsonl',rows)
 lines(OUT/'added_inputs.jsonl',new_cases);lines(OUT/'added_reference_labels.jsonl',new_refs)
 write(OUT/'split_groups.json',groups)
 for name in ['source_snapshots.jsonl','source_snapshot_variants.jsonl','evidence_audit.jsonl']:
  if (BASE/name).exists():shutil.copyfile(BASE/name,OUT/name)
 write(OUT/'parent_release_manifest.json',json.loads((BASE/'release_manifest.json').read_text()))
 sys.path.insert(0,str(ROOT/'data/grounded60/deepseek_baseline_2026-11-02/source_snapshot'))
 from reelcheck.__main__ import check_data
 from reelcheck.contract import validate
 check_data(cases)
 assert len({c['case_id'] for c in cases})==65
 assert cases[:60]==read(BASE/'inputs.jsonl') and refs[:60]==read(BASE/'reference_labels.jsonl')
 for case,gold,review in zip(new_cases,new_refs,reviews):
  emap={p['id']:p['text'] for p in case['evidence']}
  witness={'claim_text':case['claim_text'],'verdict':gold['verdict'],'uncertainty_reason':gold['uncertainty_reason'],
   'citations':[{'passage_id':i,'quote':emap[i]} for i in review['decisive_passage_ids']], 'explanation':gold['reason']}
  assert not validate(witness,case)
 overview={'cases':65,'distinct_videos':len({c['group_id'] for c in cases}),'added_claims':5,'additional_videos':0,
  'additional_claims_from_videos':3,'labels':{v:sum(g['verdict']==v for g in refs) for v in ['supported','contradicted','insufficient']},
  'new_paid_inference_calls':0,'new_claims_human_verified':False,'contract_changed':False,
  'parent_60_records_unchanged':True,'passages_match_source_snapshots':True,'three_source_video_hashes_verified':True}
 write(OUT/'overview.json',overview)
 write(OUT/'release_manifest.json',{'parent':'grounded60_v2','parent_inputs_sha256':sha((BASE/'inputs.jsonl').read_bytes()),
  'files':{p.name:sha(p.read_bytes()) for p in sorted(OUT.iterdir()) if p.is_file() and p.name!='release_manifest.json'}})
 print(json.dumps(overview,indent=2))
if __name__=='__main__':main()
