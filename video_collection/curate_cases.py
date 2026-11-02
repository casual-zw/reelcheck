"""Build and independently review 50 atomic, video-derived fixed-evidence cases."""
import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from collect import DATA, ROOT, read_jsonl, write_jsonl, now
from fireworks_client import Fireworks, load, save, digest, set_request_limit
from grounded_labels import G, passages, BASE
from label import KIMI, QWEN, AUDITOR
from judge_schemas import obj, TEXT, BOOL
from evidence import fetch

B = G / 'benchmark'
PROTOCOL = 'curated50-v2'
# Indices identify the frozen all_review_candidates.json inventory. Subsets retain
# actual assertions, without adding counterfactuals to manufacture class balance.
PLAN = [
 (0, 'In the Unix-like shell context of the video, PATH lists directories used to find executable commands.'),
 (1, 'During PATH lookup, the first matching executable in directory order is the one selected.'),
 (2, 'Appending a directory to PATH can make an executable in that directory discoverable by the shell.'),
 (3, 'The BiVACOR artificial heart was first implanted in a patient in July 2024.'),
 (4, 'In 2025, an Australian patient became the first person discharged from hospital with the BiVACOR titanium artificial heart still implanted.'),
 (5, 'The BiVACOR artificial heart weighs 650 grams and can fit in the chest cavity of a 12-year-old.'),
 (7, 'The rock avalanche discussed in the clip was initially considered an earthquake.'),
 (12, 'Cape Verde goalkeeper Vozinha was 40 years old when he kept a clean sheet against Spain at the 2026 World Cup.'),
 (14, 'Cape Verde is an island country off the coast of Africa.'),
 (16, 'An AI technology leader said that a significant fraction of the power on Earth should be spent running AI compute.'),
 (19, 'Climate models predict a more El Niño-like average equatorial Pacific under warming, but observations in recent decades have trended in the opposite direction.'),
 (24, 'In the resistance-training study discussed in the clip, both feeding groups trained four times a week for eight weeks.'),
 (25, 'In the resistance-training study discussed in the clip, the intermittent-fasting group gained about four kilograms less on squat one-repetition maximum than the continuous-feeding group.'),
 (26, 'In the resistance-training study discussed in the clip, the intermittent-fasting group gained less body fat than the continuous-feeding group.'),
 (33, 'Millions of people participated in climate protests in 2019.'),
 (38, 'Dihydrogen monoxide is water.'),
 (45, 'At a United Nations conference in 1976, governments wrote that land could not be treated as an ordinary asset controlled by individuals.'),
 (46, '178 governments adopted Agenda 21, a plan addressing human activity and the environment.'),
 (47, 'Agenda 21 is a plan to get everyone off their land and into cities dependent on the state.'),
 (54, 'The 2024 copyright exemption permits bypassing software locks to repair commercial food-preparation equipment, including McDonald’s ice cream machines.'),
 (55, 'Taylor used digital locks in its ice cream machines that restricted owners’ ability to repair them independently.'),
 (57, 'The Jackson Hole Economic Symposium is an annual central-banking conference held in Jackson Hole, Wyoming.'),
 (59, 'Around 120 people typically attend the Jackson Hole Economic Symposium.'),
 (66, 'Emergency teams worked overnight at the site of the deadly Spanish train crash shown in the clip.'),
 (78, 'Spirulina, at 57 grams of protein per 100 grams, has the highest protein content per gram of any food.'),
 (79, 'Nutritional yeast can provide vitamin B12.'),
 (81, 'A driver was rescued from a sinking car in floodwaters in Australia in the incident shown in the clip.'),
 (82, 'The floodwater car rescue shown in the clip occurred on October 22 in Morayfield, Australia.'),
 (84, 'The New York event shown is the 36th annual Tompkins Square Halloween Dog Parade.'),
 (91, 'Muslim tradition instructs a judge not to pass judgment while angry.'),
 (99, 'Al Jazeera describes itself as the first independent news channel in the Arab world.'),
 (100, 'Al Jazeera was the only foreign broadcaster in Kabul when the United States attacked Afghanistan in 2001.'),
 (110, 'Mount Cameroon is an active volcano.'),
 (115, 'Menopause causes more marriages to end than infidelity does.'),
 (116, 'Wellness Nest Shilajit contains over 85 minerals that reduce stress and support deep sleep.'),
 (127, 'Donald Trump said bone spurs were the reason for his medical deferment from military service.'),
 (132, 'The Great Spine of Africa is a planned series of 200 expeditions assessing Africa’s rivers.'),
 (133, 'The expedition featured in the clip is the 77th of the Great Spine of Africa series.'),
 (134, 'The Great Spine of Africa proposal was presented to 50 Rolex executives.'),
 (135, 'Astronauts passed or kicked a soccer ball while floating in microgravity inside the space station in the event shown.'),
 (144, 'A chainsaw artist carves spooky pumpkin faces at Copenhagen’s Tivoli Gardens.'),
 (145, 'The artist chose to carve the featured pumpkin into a witch because it had a nose-like shape.'),
 (147, 'Tartar is hardened dental plaque.'),
 (148, 'A home mixture of baking soda and 3% hydrogen peroxide can dissolve the hardened dental plaque called tartar.'),
 (149, 'Going sugar-free, with no sugar or starches, gets rid of existing tartar.'),
 (22, 'Collagen supplements cost 20 times as much as alternative food sources of protein.'),
 (40, 'Performers in the interviewed woman’s princess-party business started at about $60 per hour and later earned about $75 to $80 per hour.'),
 (41, 'The interviewed woman could generate about $1,000 in party bookings by spending $10 to $50 on a Facebook advertisement.'),
 (9, 'Cape Cod’s gray seals disappeared regionally by the 1960s and recovered after protection under the 1972 Marine Mammal Protection Act.'),
 (60, 'Multiple peer-reviewed studies show that juggling increases white matter or axons in the brain.'),
]
EXTRA_URLS = {
 'youtube_-J7EWBYipqI':['https://www.gnu.org/software/bash/manual/html_node/Command-Search-and-Execution.html'],
 'youtube_3jetza8_OdA':['https://fullfact.org/online/agenda-21-2030-edward-griffin/', 'https://www.fao.org/4/v9929e/v9929E02.htm'],
 'youtube_F4zM5_04uA0':['https://api.nal.usda.gov/fdc/v1/food/169599?api_key=DEMO_KEY'],
 'youtube_SDkvFaHr8og':['https://volcano.si.edu/volcano.cfm?vn=224010'],
 'youtube_rMFuvyLE4gQ':['https://www.nidcr.nih.gov/health-info/oral-hygiene','https://www.nidcr.nih.gov/health-info/gum-disease'],
}
QUOTE_OVERRIDES = {
 38: 'Dihydrogen monoxide. Is that oxygen? No, that\'s water. Water, oh, water.',
 149: 'To ultimately get rid of the tartar, you want to go sugar-free. You don\'t want to consume sugar or starches in your diet.',
}
VERDICT = obj({'verdict':{'enum':['supported','contradicted','insufficient']},
 'passage_ids':{'type':'array','items':TEXT,'maxItems':4},
 'uncertainty_reason':{'enum':[None,'missing_evidence','conflicting_evidence','missing_context','stale_evidence']},
 'reason':{'type':'string','maxLength':600}})
PROMPT = BASE + ''' Evaluate the exact atomic claim against ONLY the supplied evidence
packet. Do not use memory. supported requires every material part; contradicted requires
positive counterevidence, never just absence; otherwise insufficient. An apparent conflict
must be resolved by scope, source quality, dates or explicit correction, otherwise use
conflicting_evidence. An exact number cannot be replaced by a nearby number. Correlated
copies are not independent sources. Product marketing is not proof of health benefit.
You do not receive the source video or transcript: extraction is a separate stage.
Never treat the claim itself as evidence. Attribution claims are about what was said,
not the truth of the attributed proposition. Judge at
the supplied assertion date; later sources may establish earlier events retrospectively.
For decisive verdicts cite supplied passage IDs and use null uncertainty_reason. For
insufficient give a specific uncertainty_reason. Return a short reason, no deliberation.'''


def fetch_extra():
    urls=list(dict.fromkeys(u for us in EXTRA_URLS.values() for u in us))
    def one(url):
        path=G/'extra_sources'/(digest(url)+'.json')
        if not path.exists():save(path,fetch(url))
        return url,len(load(path)['text'])
    with ThreadPoolExecutor(6) as pool:
        jobs={pool.submit(one,u):u for u in urls}
        for future in as_completed(jobs):
            try:print(future.result(),flush=True)
            except Exception as e:print(jobs[future],type(e).__name__,flush=True)


def build():
    inventory=load(G/'all_review_candidates.json')
    rows={r['key']:r for r in read_jsonl(DATA/'downloaded_manifest.jsonl')}
    cases=[]; provenance=[]; sources={}
    for index,text in PLAN:
        item=inventory[index];key=item['key'];old=item['claim'];row=rows[key]
        packet=load(G/'evidence'/(key+'.json'))
        pp=list(packet['passages'])
        ss=list(packet['sources'])
        for url in EXTRA_URLS.get(key,[]):
            path=G/'extra_sources'/(digest(url)+'.json')
            if not path.exists():raise ValueError('Missing extra source: '+url)
            s=load(path);ss.append(s)
            pp+=passages(s,[{'text':text,'search_query':text,'kind':'factual'}])
        pp=list({p['passage_id']:p for p in pp}.values())
        for s in ss:sources[s['evidence_id']]=s
        date=row.get('upload_date','20261102'); date=f'{date[:4]}-{date[4:6]}-{date[6:8]}'
        cid=f"video50_{key.removeprefix('youtube_')}_{old['claim_id']}"
        cases.append({'case_id':cid,'group_id':key,'split':'development_pending_review',
            'as_of':date,'claim_text':text,'evidence':[{'id':p['passage_id'],
            'source_id':p['source_id'],'url':p['url'],'retrieved_date':p['retrieved_at'][:10],
            'text':p['text'],'sha256':hashlib.sha256(p['text'].encode()).hexdigest()} for p in pp]})
        provenance.append({'case_id':cid,'video_key':key,'original_claim_id':old['claim_id'],
            'original_claim_text':old['text'],'claim_text':text,'transformation':'Atomic subset or contextualized paraphrase; original retained; no synthetic counterfactual.',
            'video':row,'transcript_quote':QUOTE_OVERRIDES.get(index,old['transcript_quote']),
            'original_transcript_quote':old['transcript_quote'],'frame_indices':old['frame_indices'],
            'prepared_media_path':str((DATA/'bulk/media'/key/'prepared.json').relative_to(ROOT)),
            'role':old['role'],'basis':old['basis'],'human_verified':False,
            'claim_packet_sha256':digest(load(G/'claims'/(key+'.json'))),
            'evidence_packet_sha256':digest(packet),'passages':pp})
    assert len(cases)==50 and len({c['case_id'] for c in cases})==50
    B.mkdir(parents=True,exist_ok=True)
    write_jsonl(B/'inputs.jsonl',cases);write_jsonl(B/'provenance.jsonl',provenance)
    write_jsonl(B/'source_snapshots.jsonl',list(sources.values()))
    save(B/'build_manifest.json',{'protocol':PROTOCOL,'at':now(),'inputs_sha256':digest(cases),
        'provenance_sha256':digest(provenance),'inventory_sha256':digest(inventory),
        'human_verified':False,'case_count':len(cases)})
    print('Built',len(cases),'cases from',len({c['group_id'] for c in cases}),'videos')


def validate_vote(v,case):
    ids={p['id'] for p in case['evidence']}
    assert set(v['passage_ids'])<=ids,'Unknown evidence ID'
    if v['verdict']=='insufficient':assert v['uncertainty_reason'] is not None
    else:assert v['passage_ids'] and v['uncertainty_reason'] is None


def judge_one(case,provenance):
    # Keep source-video assertions out of evidence verification, structurally.
    payload={'case':case}
    votes=[]
    for i,model in enumerate([KIMI,QWEN]):
        result,receipt=Fireworks().json(model,PROMPT,json.dumps(payload),VERDICT,
            PROTOCOL+':'+case['case_id']+':judge:'+str(i),max_tokens=700,
            reasoning_effort='none',max_output_limit=1400)
        try:validate_vote(result,case);valid=True
        except AssertionError:valid=False
        votes.append({'model':model,'receipt':receipt,'result':result,'contract_valid':valid})
    # A third review is conditional to bound cost. It cannot overwrite original votes.
    results=[v['result'] for v in votes]
    audit=None
    high_risk={'video50_F4zM5_04uA0_c1','video50_SDkvFaHr8og_c3','video50_e-KfK159yFs_c2'}
    if results[0]['verdict']!=results[1]['verdict'] or not all(v['contract_valid'] for v in votes) or case['case_id'] in high_risk:
        result,receipt=Fireworks().json(AUDITOR,PROMPT+' Reconcile the two independent reviews against the actual evidence, not by majority vote.',
            json.dumps({**payload,'reviews':results}),VERDICT,PROTOCOL+':'+case['case_id']+':reconcile',
            max_tokens=3000,reasoning_effort='low',max_output_limit=6000)
        validate_vote(result,case);audit={'model':AUDITOR,'receipt':receipt,'result':result}
    save(B/'reviews'/(case['case_id']+'.json'),{'case_id':case['case_id'],
        'case_sha256':digest(case),'provenance_sha256':digest(provenance),'votes':votes,'reconciliation':audit})
    print('Reviewed',case['case_id'],[v['verdict'] for v in results],audit['result']['verdict'] if audit else '',flush=True)


def judge():
    cases=read_jsonl(B/'inputs.jsonl');provenance={p['case_id']:p for p in read_jsonl(B/'provenance.jsonl')}
    set_request_limit(12); failures=[]
    with ThreadPoolExecutor(8) as pool:
        jobs={pool.submit(judge_one,c,provenance[c['case_id']]):c['case_id'] for c in cases}
        for f in as_completed(jobs):
            try:f.result()
            except Exception as e:failures.append({'case_id':jobs[f],'error':str(e)})
    save(B/'failures.json',failures)
    if failures:raise SystemExit(str(failures))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['fetch_extra','build','judge'])
    args=parser.parse_args();globals()[args.command]()
