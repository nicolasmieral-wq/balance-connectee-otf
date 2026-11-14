import re, sys, math
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle
sys.path.insert(0,'.')
import generer_pcb as g
txt=open(sys.argv[1]).read()
fig,ax=plt.subplots(figsize=(7.5,10),dpi=160)
ax.add_patch(Rectangle((0,0),g.L_PCB,g.H_PCB,fc='#1f5a3a',ec='k'))
for x0,y0,x1,y1,w,l in re.findall(r'\(segment \(start ([\d.]+) ([\d.]+)\) \(end ([\d.]+) ([\d.]+)\) \(width ([\d.]+)\) \(layer "(\w\.Cu)"',txt):
    c='#e0533a' if l=='F.Cu' else '#4a8fe0'
    ax.plot([float(x0)-g.DX,float(x1)-g.DX],[float(y0)-g.DY,float(y1)-g.DY],color=c,lw=float(w)*4.2,solid_capstyle='round',alpha=0.9 if l=='F.Cu' else 0.75)
for x,y in re.findall(r'\(via \(at ([\d.]+) ([\d.]+)\)',txt):
    ax.add_patch(Circle((float(x)-g.DX,float(y)-g.DY),0.3,fc='#ddd',ec='k',lw=0.3))
for c in g.COMPOSANTS:
    s=c['fp']['silk']
    if s and c['ref'][0] in 'UJD':
        pts=[g.position_pastille(c,x,y) for x,y in ((s[0],s[1]),(s[2],s[3]))]
        xs=[p[0] for p in pts]; ys=[p[1] for p in pts]
        ax.add_patch(Rectangle((min(xs),min(ys)),abs(xs[1]-xs[0]),abs(ys[1]-ys[0]),fill=False,ec='white' if c['face']=='F' else '#9ad',lw=0.8,ls='-' if c['face']=='F' else '--'))
    if c['ref'].startswith('SW'):
        cx,cy=c['x']+6.25,c['y']+2.5
        ax.add_patch(Rectangle((cx-6,cy-6),12,12,fill=False,ec='white',lw=0.6))
        ax.text(cx,cy,c['val'],color='white',ha='center',va='center',fontsize=8)
    elif c['ref'][0]!='H':
        xs=[g.position_pastille(c,p[1],p[2]) for p in c['fp']['pads'] if p[0]]
        ax.text(sum(p[0] for p in xs)/len(xs),sum(p[1] for p in xs)/len(xs)+(0 if c['ref'] not in('J2','J3') else -1.6),c['ref'],color='yellow',fontsize=6.5,ha='center',va='center',weight='bold')
for p in g.pastilles():
    if p['forme']=='npth':
        ax.add_patch(Circle((p['x'],p['y']),p['w']/2,fc='black'))
    elif p['forme'] in ('circle',):
        ax.add_patch(Circle((p['x'],p['y']),p['w']/2,fc='#d9b44a',ec='none'))
    else:
        r=min(p['w'],p['h'])/2 if p['forme']=='oval' else 0.05
        ax.add_patch(FancyBboxPatch((p['x']-p['w']/2+r,p['y']-p['h']/2+r),p['w']-2*r,p['h']-2*r,boxstyle=f'round,pad={r}',fc='#d9b44a',ec='none'))
ax.set_xlim(-2,g.L_PCB+2); ax.set_ylim(g.H_PCB+2,-2); ax.set_aspect('equal'); ax.axis('off')
ax.set_title('Pavé balance OTF v0.1 — rouge : dessus, bleu : dessous',fontsize=9)
plt.savefig(sys.argv[2],bbox_inches='tight')
