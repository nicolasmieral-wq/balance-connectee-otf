"""Contrôle indépendant du fichier .kicad_pcb : isolements entre nets et continuité."""
import re, sys, math, itertools
from collections import defaultdict
txt=open(sys.argv[1]).read()
nets={int(a):b for a,b in re.findall(r"\(net (\d+) \"([^\"]*)\"\)\n",txt)}
segs=[(float(a),float(b),float(c),float(d),float(w),l,int(n)) for a,b,c,d,w,l,n in re.findall(r'\(segment \(start ([\d.]+) ([\d.]+)\) \(end ([\d.]+) ([\d.]+)\) \(width ([\d.]+)\) \(layer "(\w\.Cu)"\) \(net (\d+)\)',txt)]
vias=[(float(a),float(b),int(n)) for a,b,n in re.findall(r'\(via \(at ([\d.]+) ([\d.]+)\) \(size [\d.]+\) \(drill [\d.]+\) \(layers "F.Cu" "B.Cu"\) \(net (\d+)\)',txt)]
sys.path.insert(0,'.')
import generer_pcb as g
pads=g.pastilles()
def dseg(px,py,x0,y0,x1,y1):
    vx,vy=x1-x0,y1-y0; l2=vx*vx+vy*vy
    t=0 if l2==0 else max(0,min(1,((px-x0)*vx+(py-y0)*vy)/l2))
    return math.hypot(px-x0-t*vx,py-y0-t*vy)
def segseg(a,b):
    return min(dseg(a[0],a[1],*b[:4]),dseg(a[2],a[3],*b[:4]),dseg(b[0],b[1],*a[:4]),dseg(b[2],b[3],*a[:4]))
# objets en coordonnées circuit
S=[(x0-g.DX,y0-g.DY,x1-g.DX,y1-g.DY,w,l,n) for x0,y0,x1,y1,w,l,n in segs]
V=[(x-g.DX,y-g.DY,n) for x,y,n in vias]
P=[(p, g.NET_ID.get(p['net'],-1) if p['net'] else -1) for p in pads]
def dpad(p,x,y):
    import numpy as np
    return float(g.dist_pastille(p,np.array(x),np.array(y)))
pire=9
for a,b in itertools.combinations(S,2):
    if a[5]!=b[5] or a[6]==b[6]: continue
    d=segseg(a,b)-a[4]/2-b[4]/2; pire=min(pire,d)
    if d<g.ISOLEMENT-1e-3: print('piste/piste',nets[a[6]],nets[b[6]],round(d,3),a[:2])
for s in S:
    for p,n in P:
        if n==s[6]: continue
        # distance segment-pastille approchée par échantillonnage
        k=max(2,int(math.hypot(s[2]-s[0],s[3]-s[1])/0.02))
        d=min(dpad(p,s[0]+(s[2]-s[0])*i/k,s[1]+(s[3]-s[1])*i/k) for i in range(k+1))-s[4]/2
        lim = 0.25 if p['forme']=='npth' else g.ISOLEMENT
        pire=min(pire,d)
        if d<lim-1e-3: print('piste/pastille',nets[s[6]],p['ref'],p['num'],round(d,3))
for v in V:
    for s in S:
        if s[6]==v[2]: continue
        d=dseg(v[0],v[1],*s[:4])-g.VIA/2-s[4]/2; pire=min(pire,d)
        if d<g.ISOLEMENT-1e-3: print('via/piste',nets[v[2]],nets[s[6]],round(d,3))
    for p,n in P:
        if n==v[2]: continue
        d=dpad(p,v[0],v[1])-g.VIA/2; pire=min(pire,d)
        if d<g.ISOLEMENT-1e-3: print('via/pastille',nets[v[2]],p['ref'],round(d,3))
for a,b in itertools.combinations(V,2):
    if a[2]!=b[2] and math.hypot(a[0]-b[0],a[1]-b[1])-g.VIA<g.ISOLEMENT: print('via/via')
print('isolement minimal', round(pire,3), 'mm')
# continuité : union-find sur pastilles/segments/vias
par={}
def f(x):
    while par.setdefault(x,x)!=x: x=par[x]
    return x
def u(a,b): par[f(a)]=f(b)
objs=[('s',i) for i in range(len(S))]+[('v',i) for i in range(len(V))]+[('p',i) for i in range(len(P))]
for i,s in enumerate(S):
    for j,t in enumerate(S[:i]):
        if s[6]==t[6] and s[5]==t[5] and segseg(s,t)<1e-3: u(('s',i),('s',j))
    for j,v in enumerate(V):
        if v[2]==s[6] and min(math.hypot(v[0]-s[0],v[1]-s[1]),math.hypot(v[0]-s[2],v[1]-s[3]))<1e-3: u(('s',i),('v',j))
    for j,(p,n) in enumerate(P):
        if n==s[6] and min(dpad(p,s[0],s[1]),dpad(p,s[2],s[3]))<=0: u(('s',i),('p',j))
for j,(p,n) in enumerate(P):
    for i,v in enumerate(V):
        if n==v[2] and dpad(p,v[0],v[1])<=0: u(('v',i),('p',j))
groupes=defaultdict(set)
for j,(p,n) in enumerate(P):
    if n>0: groupes[n].add(f(('p',j)))
mauvais=[nets[n] for n,gs in groupes.items() if len(gs)>1]
print('nets incomplets :', mauvais or 'aucun', '|', len(S),'segments',len(V),'vias')
for a,b in itertools.combinations(P,2):
    pa,na=a; pb,nb=b
    if na==nb and na>0: continue
    if math.hypot(pa['x']-pb['x'],pa['y']-pb['y'])>6: continue
    import numpy as np
    k=60; d=9
    for i in range(k):
        t=2*math.pi*i/k
        # point du contour de pb le plus proche approx : échantillonne le contour de pb
    xs=np.linspace(pb['x']-pb['w']/2,pb['x']+pb['w']/2,30); ys=np.linspace(pb['y']-pb['h']/2,pb['y']+pb['h']/2,30)
    X,Y=np.meshgrid(xs,ys); m=g.dist_pastille(pb,X,Y)<=0
    d=float(g.dist_pastille(pa,X[m],Y[m]).min()) if m.any() else 9
    if d<g.ISOLEMENT-0.02: print('pastille/pastille',pa['ref'],pa['num'],pb['ref'],pb['num'],round(d,3))
print('contrôle pastilles terminé')
