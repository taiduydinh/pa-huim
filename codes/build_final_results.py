import csv, json, math, argparse
from pathlib import Path
from collections import defaultdict, Counter

parser=argparse.ArgumentParser(description='Consolidate the final PA-HUIM/BDA 2026 experiment matrix.')
parser.add_argument('root', nargs='?', default='MP6_Kazi', help='Path to the extracted MP6_Kazi project folder')
parser.add_argument('--out', default='data_rebuilt', help='Output directory for canonical CSV files')
args=parser.parse_args()
ROOT=Path(args.root).resolve()
OUT=Path(args.out).resolve(); OUT.mkdir(parents=True, exist_ok=True)
DATASETS=['foodmart','ecommerce','retail','fruithut','accidents','kosarak','chainstore','chicago_crimes']
ALGS=['efim','fhm','hui_miner','ulb_miner','upgrowthplus','d2hup']
FRACTIONS=[0.2,0.4,0.6,0.8,1.0]
# references
pa_thr={}; pa_scal={}; pa_thr_rows={}; pa_scal_rows={}
with open(ROOT/'pa_huim_results/pa_huim_threshold_results.csv',newline='',encoding='utf8') as f:
    for r in csv.DictReader(f):
        ds=r.get('dataset')
        if ds in DATASETS and r.get('status')=='ok':
            t=int(float(r['threshold_index']))
            pa_thr[(ds,t)]={'mu':int(float(r['min_utility'])),'patterns':int(float(r['pattern_count']))}
            pa_thr_rows[(ds,t)]=r
with open(ROOT/'pa_huim_results/pa_huim_scalability_results.csv',newline='',encoding='utf8') as f:
    for r in csv.DictReader(f):
        ds=r.get('dataset')
        if ds in DATASETS and r.get('status')=='ok':
            frac=round(float(r['size_fraction']),2)
            n=int(float(r.get('max_transactions') or r.get('read_transactions')))
            pa_scal[(ds,frac)]={'mu':int(float(r['min_utility'])),'n':n,'patterns':int(float(r['pattern_count']))}
            pa_scal_rows[(ds,frac)]=r
# observations
thr_obs=defaultdict(list); scal_obs=defaultdict(list)
for p in ROOT.rglob('baseline_huim_threshold_results.csv'):
    if 'pa_huim_results' in str(p): continue
    try:
        with p.open(newline='',encoding='utf8') as f:
            for r in csv.DictReader(f):
                alg=r.get('algorithm'); ds=r.get('dataset')
                if alg in ALGS and ds in DATASETS:
                    try:t=int(float(r['threshold_index']))
                    except:continue
                    rr=dict(r); rr['_src']=str(p.relative_to(ROOT)); rr['_kind']='csv'; thr_obs[(alg,ds,t)].append(rr)
    except Exception: pass
for p in ROOT.rglob('baseline_huim_scalability_results.csv'):
    if 'pa_huim_results' in str(p): continue
    try:
        with p.open(newline='',encoding='utf8') as f:
            for r in csv.DictReader(f):
                alg=r.get('algorithm'); ds=r.get('dataset')
                if alg in ALGS and ds in DATASETS:
                    try:frac=round(float(r['size_fraction']),2)
                    except:continue
                    rr=dict(r); rr['_src']=str(p.relative_to(ROOT)); rr['_kind']='csv'; scal_obs[(alg,ds,frac)].append(rr)
    except Exception: pass
# supplementary JSONs
json_files=list(ROOT.glob('*/results/*.json'))+list((ROOT/'speculative_accel').glob('*.json'))
mu2t={ds:{v['mu']:t for (dds,t),v in pa_thr.items() if dds==ds} for ds in DATASETS}
mun2f={ds:{(v['mu'],v['n']):f for (dds,f),v in pa_scal.items() if dds==ds} for ds in DATASETS}
for p in json_files:
    try:x=json.loads(p.read_text())
    except:continue
    rr=x.get('result',x)
    alg=x.get('algorithm') or rr.get('algorithm'); ds=x.get('dataset') or rr.get('dataset')
    if alg not in ALGS or ds not in DATASETS: continue
    mu_raw=x.get('min_utility') if x.get('min_utility') is not None else rr.get('min_utility')
    try: mu=int(mu_raw)
    except: continue
    n=x.get('max_transactions',rr.get('max_transactions'))
    if n in ('',None): n=None
    else:
        try:n=int(n)
        except:n=None
    r={**rr}; r['algorithm']=alg; r['dataset']=ds; r['min_utility']=str(mu); r['max_transactions']='' if n is None else str(n); r['_src']=str(p.relative_to(ROOT)); r['_kind']='json'; r['_case_id']=x.get('case_id','')
    if n is None:
        t=x.get('threshold_index') or mu2t.get(ds,{}).get(mu)
        if t: thr_obs[(alg,ds,int(t))].append(r)
    else:
        frac=mun2f.get(ds,{}).get((mu,n))
        if frac is not None: scal_obs[(alg,ds,frac)].append(r)
# helper
excluded={('upgrowthplus','ecommerce',f) for f in FRACTIONS}
def priority(r):
    s=r.get('_src','')
    if r.get('_kind')=='json': return (0,s)
    if s.startswith('baseline_huim_results/'): return (1,s)
    if s.startswith('baseline_scalability/'): return (1,s)
    if s.startswith('backups/'): return (5,s)
    if s.startswith('reuse_t4_100_archive/'): return (6,s)
    return (2,s)
def is_correct_thr(r,ds,t):
    ref=pa_thr.get((ds,t))
    if not ref or r.get('status')!='ok': return False
    try:return int(float(r['min_utility']))==ref['mu'] and int(float(r['pattern_count']))==ref['patterns']
    except:return False
def is_correct_scal(r,ds,f):
    ref=pa_scal.get((ds,f))
    if not ref or r.get('status')!='ok': return False
    try:
        n=int(float(r.get('max_transactions') or r.get('read_transactions')))
        return int(float(r['min_utility']))==ref['mu'] and n==ref['n'] and int(float(r['pattern_count']))==ref['patterns']
    except:return False
# threshold strict predecessor classification
thr_state={}; thr_row={}; thr_raw_status={}
for alg in ALGS:
    for ds in DATASETS:
        blocked=False
        for t in range(10,0,-1):
            rows=thr_obs[(alg,ds,t)]
            good=[r for r in rows if is_correct_thr(r,ds,t)]
            has_timeout=any(r.get('status')=='timeout' for r in rows)
            has_skip=any(r.get('status')=='skipped_after_timeout' for r in rows)
            has_ok_bad=any(r.get('status')=='ok' for r in rows) and not good
            thr_raw_status[(alg,ds,t)]={'good':bool(good),'timeout':has_timeout,'skip':has_skip,'bad':has_ok_bad,'rows':rows}
            if blocked:
                thr_state[(alg,ds,t)]='skipped'
            elif good:
                thr_state[(alg,ds,t)]='correct'; thr_row[(alg,ds,t)]=sorted(good,key=priority)[0]
            elif has_timeout:
                thr_state[(alg,ds,t)]='timeout'; blocked=True
            elif has_skip:
                thr_state[(alg,ds,t)]='skipped'; blocked=True
            elif has_ok_bad:
                thr_state[(alg,ds,t)]='incorrect'
            else:
                thr_state[(alg,ds,t)]='pending'

# Reuse a successful direct/full scalability 100% execution for threshold T4 when the threshold
# sequence has reached T5 successfully. This is the identical full-data/minUtil task.
for alg in ALGS:
    for ds in DATASETS:
        key=(alg,ds,4)
        if thr_state[key]=='pending' and thr_state[(alg,ds,5)]=='correct':
            rows=scal_obs[(alg,ds,1.0)]
            good=[r for r in rows if is_correct_scal(r,ds,1.0)]
            if good:
                rr=dict(sorted(good,key=priority)[0]); rr['_reuse']='scale100->T4'
                thr_state[key]='correct'; thr_row[key]=rr

# scalability strict predecessor classification with T4 task reuse at 100%
scal_state={}; scal_row={}
for alg in ALGS:
    for ds in DATASETS:
        if alg=='upgrowthplus' and ds=='ecommerce':
            for f in FRACTIONS: scal_state[(alg,ds,f)]='excluded'
            continue
        blocked=False
        for f in FRACTIONS:
            key=(alg,ds,f)
            if blocked:
                scal_state[key]='skipped'; continue
            rows=scal_obs[key]
            good=[r for r in rows if is_correct_scal(r,ds,f)]
            has_timeout=any(r.get('status')=='timeout' for r in rows)
            has_skip=any(r.get('status')=='skipped_after_timeout' for r in rows)
            has_ok_bad=any(r.get('status')=='ok' for r in rows) and not good
            # At full fraction, same mining task as threshold T4. Reuse any raw T4 execution,
            # independent of threshold-sequence admissibility, provided scale 80% was reached.
            if f==1.0 and not good and not has_timeout and not has_skip and not has_ok_bad:
                t4rows=thr_obs[(alg,ds,4)]
                ref=pa_scal[(ds,1.0)]
                t4good=[]
                for r in t4rows:
                    if r.get('status')!='ok': continue
                    try:
                        if int(float(r['min_utility']))==ref['mu'] and int(float(r['pattern_count']))==ref['patterns']:
                            t4good.append(r)
                    except: pass
                if t4good:
                    good=[dict(sorted(t4good,key=priority)[0])]
                    good[0]['_reuse']='T4->scale100'
                    good[0]['max_transactions']=str(ref['n'])
                elif any(r.get('status')=='timeout' for r in t4rows):
                    has_timeout=True
            if good:
                scal_state[key]='correct'; scal_row[key]=sorted(good,key=priority)[0]
            elif has_timeout:
                scal_state[key]='timeout'; blocked=True
            elif has_skip:
                scal_state[key]='skipped'; blocked=True
            elif has_ok_bad:
                scal_state[key]='incorrect'
            else:
                scal_state[key]='pending'
# summary
summary={}
for alg in ALGS:
    c=Counter()
    for ds in DATASETS:
        for t in range(10,0,-1): c[thr_state[(alg,ds,t)]]+=1
        for f in FRACTIONS: c[scal_state[(alg,ds,f)]]+=1
    summary[alg]=c
allc=Counter({'correct':120})
for c in summary.values(): allc.update(c)
print('Per algorithm:')
print('pa_huim',dict(Counter(correct=120)))
for alg in ALGS: print(alg,dict(summary[alg]))
print('TOTAL',dict(allc),'sum',sum(allc.values()))
print('\nTimeout threshold:')
for k,v in sorted(thr_state.items()):
    if v=='timeout': print(k)
print('Timeout scalability:')
for k,v in sorted(scal_state.items()):
    if v=='timeout': print(k)
print('Pending:')
for k,v in sorted({**thr_state,**scal_state}.items(), key=lambda kv:str(kv[0])):
    if v=='pending': print(k)
# write csv
fields=['experiment','algorithm','dataset','setting','threshold_index','size_fraction','min_utility','max_transactions','status','runtime_ms','peak_memory_mb','pattern_count','candidate_count','source','reuse']
with open(OUT/'canonical_final.csv','w',newline='',encoding='utf8') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    for (ds,t),r in sorted(pa_thr_rows.items()):
        if ds in DATASETS:
            w.writerow(dict(experiment='threshold',algorithm='pa_huim',dataset=ds,setting=f'T{t}',threshold_index=t,size_fraction='',min_utility=r['min_utility'],max_transactions='',status='correct',runtime_ms=r['runtime_ms'],peak_memory_mb=r['peak_memory_mb'],pattern_count=r['pattern_count'],candidate_count=r.get('candidate_count',''),source='pa_huim_results/pa_huim_threshold_results.csv',reuse=''))
    for (ds,fr),r in sorted(pa_scal_rows.items()):
        if ds in DATASETS:
            w.writerow(dict(experiment='scalability',algorithm='pa_huim',dataset=ds,setting=f'{int(fr*100)}%',threshold_index='',size_fraction=fr,min_utility=r['min_utility'],max_transactions=r.get('max_transactions') or r.get('read_transactions'),status='correct',runtime_ms=r['runtime_ms'],peak_memory_mb=r['peak_memory_mb'],pattern_count=r['pattern_count'],candidate_count=r.get('candidate_count',''),source='pa_huim_results/pa_huim_scalability_results.csv',reuse=''))
    for (alg,ds,t),st in sorted(thr_state.items()):
        rr=thr_row.get((alg,ds,t),{})
        w.writerow(dict(experiment='threshold',algorithm=alg,dataset=ds,setting=f'T{t}',threshold_index=t,size_fraction='',min_utility=pa_thr[(ds,t)]['mu'],max_transactions='',status=st,runtime_ms=rr.get('runtime_ms',''),peak_memory_mb=rr.get('peak_memory_mb',''),pattern_count=rr.get('pattern_count',''),candidate_count=rr.get('candidate_count',''),source=rr.get('_src',''),reuse=rr.get('_reuse','')))
    for (alg,ds,fr),st in sorted(scal_state.items()):
        rr=scal_row.get((alg,ds,fr),{})
        ref=pa_scal[(ds,fr)]
        w.writerow(dict(experiment='scalability',algorithm=alg,dataset=ds,setting=f'{int(fr*100)}%',threshold_index='',size_fraction=fr,min_utility=ref['mu'],max_transactions=ref['n'],status=st,runtime_ms=rr.get('runtime_ms',''),peak_memory_mb=rr.get('peak_memory_mb',''),pattern_count=rr.get('pattern_count',''),candidate_count=rr.get('candidate_count',''),source=rr.get('_src',''),reuse=rr.get('_reuse','')))
# status summary csv
with open(OUT/'status_summary.csv','w',newline='',encoding='utf8') as f:
    w=csv.writer(f); w.writerow(['algorithm','correct','timeout','skipped','excluded','incorrect','pending','total'])
    w.writerow(['PA-HUIM',120,0,0,0,0,0,120])
    for alg in ALGS:
        c=summary[alg]; w.writerow([alg,c['correct'],c['timeout'],c['skipped'],c['excluded'],c['incorrect'],c['pending'],sum(c.values())])
    w.writerow(['TOTAL',allc['correct'],allc['timeout'],allc['skipped'],allc['excluded'],allc['incorrect'],allc['pending'],sum(allc.values())])
