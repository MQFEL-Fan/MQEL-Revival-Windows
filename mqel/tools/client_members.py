"""Client-JSON-Leser: Klassenname -> Membernamen (Update3-Binary).

Mit -t davor zusätzlich der JSON-Typ jedes Members, abgeleitet aus der
Lesefunktion, die der Client dafür aufruft (Thunks aufgelöst):
  python tools/client_members.py <exe> [-t] Klasse...
"""
import re,struct,sys,capstone
d=open(sys.argv[1],'rb').read()
pe=struct.unpack_from('<I',d,0x3c)[0]; osz=struct.unpack_from('<H',d,pe+20)[0]; ib=struct.unpack_from('<I',d,pe+52)[0]
n=struct.unpack_from('<H',d,pe+6)[0]
secs=[struct.unpack_from('<IIII',d,pe+24+osz+i*40+8) for i in range(n)]
va,rs,ro=struct.unpack_from('<III',d,pe+24+osz+12)
def off(v):
    for svs,sva,srs,sro in secs:
        if sva<=v-ib<sva+srs: return v-ib-sva+sro
def cstr(v):
    o=off(v)
    if o is None: return None
    e=d.find(b'\0',o,o+120); s=d[o:e]
    return s.decode('latin1') if e>o and all(32<=c<127 for c in s) else None
md=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_32)
# Lesefunktionen -> JSON-Typ (an CastleInfo/LeaderboardPage geeicht).
# Andere Ziele sind typ-eigene Leser, meist Enums (Zahl reicht).
KIND={0x122c0b0:'int',0x122c0d0:'float',0x122c940:'int-array',0x122bfc0:'bool',0x122ccc0:'object',
      0x122d0d0:'array',0x122a870:'array|null',0x122c960:'array|null',
      0x122ca00:'string',0x122c3a0:'date',0x122c680:'timespan'}
# Hilfsaufrufe vor dem eigentlichen Leser (Enum-Deskriptor bauen)
SKIP={0x493d8d,0x48c3a8}
def resolve(a):
    for _ in range(4):
        o=off(a)
        if o is None or d[o]!=0xe9: break
        a=a+5+struct.unpack_from('<i',d,o+1)[0]
    return a
TYPED='-t' in sys.argv
if TYPED: sys.argv.remove('-t')
def kind(a):
    a=resolve(a)
    return KIND.get(a, 'enum/eigen '+hex(a))
for cls in sys.argv[2:]:
    m=re.search(b'\0'+re.escape(cls.encode())+b'\0',d)
    sv=None
    for so in [m.start()+1] if m else []:
        for svs,sva,srs,sro in secs:
            if sro<=so<sro+srs: sv=ib+sva+so-sro
    if not sv: print(cls,'?'); continue
    for x in re.finditer(b'\x68'+re.escape(struct.pack('<I',sv)),d[ro:ro+rs]):
        a=ib+va+x.start()
        st=d.rfind(b'\xcc\x55\x8b\xec',ro,ro+x.start())+1
        code=d[st:ro+x.start()+5]; fa=ib+va+st-ro
        mem=[]
        if TYPED:  # ganze Funktion bis zum Padding
            end=d.find(b'\xcc\xcc\xcc',ro+x.start())
            code=d[st:end]
        cur=None
        for i in md.disasm(code,fa):
            if i.mnemonic=='mov' and i.op_str.startswith('ecx, 0x'):
                s=cstr(int(i.op_str.split(', ')[1],16))
                if s and s!=cls:
                    mem.append(s); cur=s
            elif TYPED and cur and i.mnemonic=='call' and i.op_str.startswith('0x'):
                t=resolve(int(i.op_str,16))
                if t in SKIP: continue
                mem[-1]=(cur,t); cur=None
        if not mem: continue
        if not TYPED: print(cls,hex(fa),mem); continue
        print(cls,hex(fa))
        for m in mem:
            if isinstance(m,tuple): print('  %-34s %s'%(m[0],kind(m[1])))
            else: print('  %-34s ?'%m)
