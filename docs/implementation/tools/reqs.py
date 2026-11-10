import re,os,sys,collections
A=sys.argv[1]+"/docs/architecture/"; OUT=sys.argv[1]+"/docs/implementation/REQUIREMENTS_TRACEABILITY.md"
SRC={"AI_RES_MVP_Capability_Matrix_v3.3.md":"DOC-009","AI_RES_Security_Controls_and_Requirements_v1.2.md":"DOC-020","AI_RES_Persistence_Implementation_Blueprint_v1.0.md":"DOC-072",
"AI_RES_PostgreSQL_Migration_and_Access_Strategy_v1.1.md":"DOC-068","AI_RES_Performance_Scalability_Resilience_Requirements_v1.0.md":"DOC-031","AI_RES_Resilience_and_Recovery_Requirements_v1.0.md":"DOC-032",
"AI_RES_Monitoring_and_Alerting_Requirements_v1.0.md":"DOC-025","AI_RES_Continuous_Improvement_Requirements_v1.3.md":"DOC-039","AI_RES_Threat_Model_v1.1.md":"DOC-017",
"AI_RES_Capacity_and_Load_Test_Plan_v1.0.md":"DOC-033","AI_RES_Authentication_and_Session_Management_v1.1.md":"DOC-023","AI_RES_Requirements_Lifecycle_v2.7.md":"DOC-003"}
IDRE=r'((?:UX-[A-Z]+|[A-Z]+-MVP|OBS-(?:MON|SEC|ALR)|PERSIST|SEC|AUTH|PERF|REL|DBM|CI|THR|LT|LC-DEC)-\d{2,3})'
MAP=[("API-MVP","S01, S02, S08, S09, S12"),("AUTH-MVP","S07"),("AUTH","S07; S37"),("SEC-MVP","S07; S37"),("SEC","S02–S37 (по области); S37 верификация"),
("DATA-MVP","S05, S06"),("INF-MVP","S03; S11; S13; S32"),("INT-MVP","S29"),("PROC-MVP","S12, S20–S32"),("RULE-MVP","S18"),("DEP-MVP","S23, S30"),
("WS-MVP","S35"),("UX-START","S20, S35"),("UX-MVP","S35, S36"),("UX-PLAN","S21, S36"),("UX-RESULT","S25, S36"),("UX-REQ","S26, S36"),("UX-DUR","S26, S36"),
("UX-SRC","S27, S36"),("UX-TRC","S30, S36"),("UX-ART","S31, S36"),("PERSIST","S04, S05"),("DBM","S04, S05, S32"),("PERF","S38"),("REL","S32, S38"),("LT","S38"),
("OBS-MON","S13"),("OBS-SEC","S13"),("OBS-ALR","S13"),("CI","S34 (MVP A0–A2); остальное post-MVP"),("THR","S03, S05, S07, S16, S17, S23, S37 (по области угрозы)"),("LC-DEC","S26")]
fam=lambda i:i.rsplit('-',1)[0]
stage=dict(MAP)
rows={}
for f,doc in SRC.items():
    lines=open(A+f).read().split('\n')
    for n,l in enumerate(lines):
        h=re.match(r'^###\s+'+IDRE+r'\s+—\s+(.+)$',l)
        m=re.match(r'^\| '+IDRE+r' \| ([^|]+)\|(?: ([^|]*)\|)?',l)
        if h:
            i,t,p=h.group(1),h.group(2).strip(),''
        elif m:
            i,t,p=m.group(1),m.group(2).strip(),(m.group(3) or '').strip()
        else:
            m=re.match(r'^(\s+)(?:REQ-)?'+IDRE+r'(\s+)(\S.*)$',l)
            if not m: continue
            i=m.group(2); start=len(l)-len(l.lstrip())+len(l.strip().split()[0])+len(m.group(3)); rest=m.group(4)
            parts=re.split(r'\s{2,}',rest); t=parts[0]; p=parts[1] if len(parts)>1 else ''
            k=n+1
            while k<len(lines) and lines[k].strip() and not re.match(r'^\s+'+IDRE,lines[k]):
                seg=lines[k][start:].split('  ')[0].strip() if len(lines[k])>start else ''
                if seg and not seg.startswith('-'): t+=' '+seg
                k+=1
        if i in rows or fam(i) not in stage: continue
        t=re.sub(r'\s+',' ',t).replace('|','/')[:110]
        st="DEFERRED (post-MVP)" if re.search(r'После MVP|FUTURE|post-MVP',p) else ("OPEN (не решено)" if p.startswith('Открыто') else "NOT_STARTED")
        rows[i]=(doc,t,p[:28] or '—',stage[fam(i)],st)
def key(i):
    f,n=i.rsplit('-',1); return (f,int(n))
c=collections.Counter(fam(i) for i in rows)
fams="\n".join(f"| {f} | {c.get(f,0)} | {s} |" for f,s in MAP)
body="\n".join(f"| {i} | {v[0]} | {v[1]} | {v[2]} | {v[3]} | {v[4]} |" for i,v in sorted(rows.items(),key=lambda x:key(x[0])))
open(OUT,'w').write(f"""# REQUIREMENTS_TRACEABILITY

Требования нормативных документов → этапы реализации → статус. Индекс сгенерирован из canonical документов Registry v4.1 (DOC-003, -009, -017, -020, -023, -025, -031, -032, -033, -039, -068, -072); {len(rows)} уникальных ID. Сопоставление выполнено на уровне семейств (G-14): при старте этапа исполнитель уточняет конкретные ID, указывает тесты и меняет статус (NOT_STARTED → IMPLEMENTED → TESTED → VERIFIED). TX-01…TX-09 (DOC-064 §8) — S05, S09, S12.

## 1. Семейства → этапы

| Семейство | Кол-во | Этапы |
|---|---|---|
{fams}

## 2. Индекс требований

| ID | Документ | Требование (кратко) | Приоритет/scope | Этапы | Статус |
|---|---|---|---|---|---|
{body}
""")
print(len(rows)); print(c)
