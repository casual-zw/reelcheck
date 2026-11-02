"""Build real-video-derived development inputs; no synthetic claim mutations.

Claims are editorial paraphrases of publisher transcripts or creator descriptions.
This is not an automated video/transcript ingestion benchmark. No human gold labels.
"""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    rows=[]
    clips=[]
    notes=[]
    for filename in ('real_video_seed.json','real_video_light_seed.json'):
        seed=json.loads((ROOT/'data'/filename).read_text())
        by_clip={c['clip_id']:c for c in seed['clips']}
        clips.extend(seed['clips'])
        for p in seed['evidence']:
            assert hashlib.sha256(p['text'].encode()).hexdigest()==p['sha256']
        for claim in seed['claims']:
            clip=by_clip[claim['clip_id']]
            text=claim['claim_text']
            if claim['claim_id']=='sea_04':
                text=text.replace('when this video was published','in 2015')
            # All inspected packet passages, including relevant distractors, go to
            # every claim from this seed; no answer-conditioned evidence selection.
            rows.append({'case_id':'video_'+claim['claim_id'],'group_id':clip['clip_id'],
                'split':'development_real_video_seed','as_of':'2026-11-02',
                'claim_text':text,'evidence':seed['evidence'],
                'clip_url':clip['url'],'claim_origin':claim['claim_origin'],
                'timestamp':None,'human_label_status':'pending'})
            notes.append({'case_id':'video_'+claim['claim_id'],**claim,
                'claim_text_in_run':text,'note':'Review notes are excluded from model prompts.'})
    (ROOT/'data/real_video_inputs.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    (ROOT/'data/real_video_manifest.json').write_text(json.dumps({
        'case_count':len(rows),'clip_count':len(clips),'clips':clips,
        'claim_review_notes':notes,
        'limitations':['AI-authored paraphrases, not verified verbatim extraction.',
         'No speech timestamps or human truth labels.',
         'Seven claims from official untimed transcripts; two from a Short creator description.',
         'Evidence packets are manually assembled. Retrieval and full video understanding are not evaluated.',
         'Caltech evidence includes two explicitly marked editorial summaries alongside short direct excerpts.',
         'All claims from each clip stay grouped; nine claims are not nine independent source families.']},indent=2,ensure_ascii=False)+'\n')
    print(f'Built {len(rows)} development claims from {len(clips)} real videos; no invented timestamps or human labels.')


if __name__=='__main__':
    main()
