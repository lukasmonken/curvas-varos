"""Reimplementação descartável das fórmulas reais, para auditoria F0."""
import openpyxl
rc=openpyxl.load_workbook('scratch/recalc/QUERY-AVILA.XLSX',data_only=True)
R={s.title:s for s in rc.worksheets}; R.update({'Dashboard':R['DASHBOARD'],'DI':R['DI'],'Inflação':R['INFLAÇÃO'],'CDS':R['CDS']})
MESES=['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']
def mq(mes,tri): return MESES.index(mes)+1, int(tri[0])
def interp_tab(vert,rates,nmax,step_from_vertices=False):
    # X/M column: flat before first vertex, incremental addition between, flat after last
    x=[None]*(nmax+1)
    v0=vert[0]
    for d in range(1,v0+1): x[d]=rates[0]
    for i in range(1,len(vert)):
        a,b=vert[i-1],vert[i]
        inc=(rates[i]-rates[i-1])/((b-a) if step_from_vertices else 126)
        for d in range(a+1,b): x[d]=x[d-1]+inc
        x[b]=rates[i]
    for d in range(vert[-1]+1,nmax+1): x[d]=x[d-1]
    return x
def accum(x,real_T):
    y=[None]*len(x)
    y[1]=real_T*(1+x[1])**(1/252)-1
    for d in range(2,len(x)): y[d]=(1+y[d-1])*(1+x[d])**(1/252)-1
    return y
def di_like(vert,rates,monthly,mes,tri,nmax):
    m,q=mq(mes,tri)
    Tp=1.0;Up=1.0
    qof=[1,1,1,2,2,2,3,3,3,4,4,4]
    for i in range(12):
        if qof[i]>q-1 and i+1<=m: Tp*=1+monthly[i]
        if qof[i]<q: Up*=1+monthly[i]
    x=interp_tab(vert,rates,nmax); y=accum(x,Tp)
    ytg=int((12-m)*(252/12))
    S26=y[ytg]; S27=(1+S26)*Up-1
    cuts=[ytg+252*k for k in range(11)]
    S=[(1+y[cuts[k]])/(1+y[cuts[k-1]])-1 for k in range(1,11)]
    E4_di=(1+S26)**(4/(5-q))-1
    return dict(x=x,y=y,ytg=ytg,S26=S26,S27=S27,fwd=S,E4_di=E4_di,Tp=Tp,Up=Up)
dash=R['Dashboard']
vI=[126*k for k in range(1,20)]
rI=[dash[f'C{r}'].value/100 for r in range(11,30)]
rD=[dash[f'F{r}'].value/100 for r in range(11,30)]
ipca=[dash[f'I{r}'].value for r in range(20,32)]
selic=[dash[f'L{r}'].value for r in range(20,32)]
inf=di_like(vI,rI,ipca,'Janeiro','1º Tri',3000)
di=di_like(vI,rD,selic,'Janeiro','1º Tri',2998)
vC=[126,252,504,756,1008,1260,1764,2520,5040]
rC=[dash[f'I{r}'].value/10000 for r in range(9,18)]
xc=interp_tab(vC,rC,5040,True); yc=accum(xc,1.0)
ytgc=62; cutsC=[ytgc+252*k for k in range(11)]
cds_fwd=[(1+yc[cutsC[k]])/(1+yc[cutsC[k-1]])-1 for k in range(1,11)]
cds_E4=(1+yc[62])**(252/62)-1
# compare to recalc
def chk(label,mine,sheet,cell):
    v=R[sheet][cell].value; print(f"{label:28s} mine={mine:.15g} recalc={v:.15g} diff={abs(mine-v):.2e}")
chk('DI E4 (2026 Dash)',di['E4_di'],'DI','E4'); chk('DI S26',di['S26'],'DI','S26'); chk('DI S27',di['S27'],'DI','S27')
for k,c in enumerate('FGHIJKLMNO'): chk(f'DI {c}4',di['fwd'][k],'DI',f'{c}4')
chk('INF S26',inf['S26'],'Inflação','S26'); chk('INF S27',inf['S27'],'Inflação','S27')
for k,c in enumerate('FGHIJKLMNO'): chk(f'INF {c}4',inf['fwd'][k],'Inflação',f'{c}4')
chk('CDS E4',cds_E4,'CDS','E4'); chk('CDS J9',yc[62],'CDS','J9')
for k,c in enumerate('FGHIJKLMNO'): chk(f'CDS {c}4',cds_fwd[k],'CDS',f'{c}4')
mx=max(abs(di['y'][d]-R['DI'][f'Y{d+2}'].value) for d in range(1,2999)); print('DI Y col max diff',mx)
mx=max(abs(inf['y'][d]-R['Inflação'][f'Y{d+2}'].value) for d in range(1,3001)); print('INF Y col max diff',mx)
mx=max(abs(yc[d]-R['CDS'][f'N{d+7}'].value) for d in range(1,5041)); print('CDS N col max diff',mx)
# E10
E10=[('DI x(127)',di['x'][127],0.1332783571),('DI Acum1',di['y'][1],0.01210233742),('DI Acum127',di['y'][127],0.07743467076),('DI Acum231',di['y'][231],0.1347318473),('DI Acum504',di['y'][504],0.3039766),
('INF x(253)',inf['x'][253],0.06479265079),('INF Acum1',inf['y'][1],0.003550109048),('INF Acum231',inf['y'][231],0.06276345587),('INF Acum253',inf['y'][253],0.06860711517),('INF Acum504',inf['y'][504],0.1337749986),
('CDS x(127)',xc[127],0.004573888889),('CDS Acum62',yc[62],0.0011216976),('CDS Acum127',yc[127],0.00229904919)]
print('--- E10 pontos')
for l,m,e in E10: print(f"{l:14s} recalc={m:.15g} E10={e} diff={abs(m-e):.2e} {'OK' if abs(m-e)<1e-8 else 'SPEC_DIVERGENCE(>1e-8)'}")
exp_di=[0.1367704582,0.1397224171,0.1411788478,0.1419084912,0.1421659309,0.1421324179,0.1419262871,0.1416246573,0.1413084536,0.141248]
exp_in=[0.06170699177,0.05921274213,0.05975990725,0.06048500357,0.06101641848,0.06138540302,0.06165391388,0.06186391725,0.0620259023,0.062054]
exp_c=[0.005040834358,0.006465717867,0.008248988388,0.0104101213,0.01254379297,0.01460425996,0.01663378424,0.01820592628,0.01958959306,0.0209406778]
print('--- E10 anuais (2027..2036) max diff', max(abs(a-b) for a,b in zip(di['fwd'],exp_di)), max(abs(a-b) for a,b in zip(inf['fwd'],exp_in)), max(abs(a-b) for a,b in zip(cds_fwd,exp_c)))
for y,(a,b) in enumerate(zip(di['fwd'],exp_di)): 
    if abs(a-b)>1e-8: print(' DI',2027+y,a,b)
for y,(a,b) in enumerate(zip(inf['fwd'],exp_in)):
    if abs(a-b)>1e-8: print(' INF',2027+y,a,b)
print('CDS 2026 E4 vs 1º vértice:',cds_E4, rC[0], abs(cds_E4-rC[0]))
# Cenário: abas em Setembro/3º Tri (para ilustrar anualização DI!E4)
for mes,tri in [('Agosto','3º Tri'),('Setembro','3º Tri')]:
    d=di_like(vI,rD,selic,mes,tri,2998); i=di_like(vI,rI,ipca,mes,tri,3000)
    print(f'Cenário {mes}/{tri}: ytg={d["ytg"]} DI S26={d["S26"]:.6f} DI E4(anualizado)={d["E4_di"]:.6f} DI S27(ano civil)={d["S27"]:.6f} | INF S26={i["S26"]:.6f} INF S27={i["S27"]:.6f} | DI 2027={d["fwd"][0]:.6f} INF 2027={i["fwd"][0]:.6f}')
# trimestrais
for q,cell in enumerate(['S3','S4','S5','S6']):
    print('tri',q+1,R['Inflação'][cell].value,R['DI'][cell].value)
# Spot repricing check (E6.1)
print('INF acc504 (no realized)', (1+inf['y'][504])/(1+inf['y'][1])*(1+rI[0])**(1/252)-1, 'spot', (1+rI[3])**2-1)
print('DI acc504 (no realized)', (1+di['y'][504])/1.0116-1, 'spot', (1+rD[3])**2-1)
