"""IL disassembler with token resolution (methods, strings, members)."""
import struct, sys
import dotnetfile

NAMES1 = {
 0x00:'nop',0x01:'break',0x02:'ldarg.0',0x03:'ldarg.1',0x04:'ldarg.2',0x05:'ldarg.3',0x06:'ldloc.0',0x07:'ldloc.1',
 0x08:'ldloc.2',0x09:'ldloc.3',0x0A:'stloc.0',0x0B:'stloc.1',0x0C:'stloc.2',0x0D:'stloc.3',0x0E:'ldarg.s',0x0F:'ldarga.s',
 0x10:'starg.s',0x11:'ldloc.s',0x12:'ldloca.s',0x13:'stloc.s',0x14:'ldnull',0x15:'ldc.i4.m1',0x16:'ldc.i4.0',0x17:'ldc.i4.1',
 0x18:'ldc.i4.2',0x19:'ldc.i4.3',0x1A:'ldc.i4.4',0x1B:'ldc.i4.5',0x1C:'ldc.i4.6',0x1D:'ldc.i4.7',0x1E:'ldc.i4.8',0x1F:'ldc.i4.s',
 0x20:'ldc.i4',0x21:'ldc.i8',0x22:'ldc.r4',0x23:'ldc.r8',0x25:'dup',0x26:'pop',0x27:'jmp',0x28:'call',0x29:'calli',0x2A:'ret',
 0x2B:'br.s',0x2C:'brfalse.s',0x2D:'brtrue.s',0x2E:'beq.s',0x2F:'bge.s',0x30:'bgt.s',0x31:'ble.s',0x32:'blt.s',0x33:'bne.un.s',
 0x34:'bge.un.s',0x35:'bgt.un.s',0x36:'ble.un.s',0x37:'blt.un.s',0x38:'br',0x39:'brfalse',0x3A:'brtrue',0x3B:'beq',0x3C:'bge',
 0x3D:'bgt',0x3E:'ble',0x3F:'blt',0x40:'bne.un',0x41:'bge.un',0x42:'bgt.un',0x43:'ble.un',0x44:'blt.un',0x45:'switch',
 0x46:'ldind.i1',0x47:'ldind.u1',0x48:'ldind.i2',0x49:'ldind.u2',0x4A:'ldind.i4',0x4B:'ldind.u4',0x4C:'ldind.i8',0x4D:'ldind.i',
 0x4E:'ldind.r4',0x4F:'ldind.r8',0x50:'ldind.ref',0x51:'stind.ref',0x52:'stind.i1',0x53:'stind.i2',0x54:'stind.i4',0x55:'stind.i8',
 0x56:'stind.r4',0x57:'stind.r8',0x58:'add',0x59:'sub',0x5A:'mul',0x5B:'div',0x5C:'div.un',0x5D:'rem',0x5E:'rem.un',0x5F:'and',
 0x60:'or',0x61:'xor',0x62:'shl',0x63:'shr',0x64:'shr.un',0x65:'neg',0x66:'not',0x67:'conv.i1',0x68:'conv.i2',0x69:'conv.i4',
 0x6A:'conv.i8',0x6B:'conv.r4',0x6C:'conv.r8',0x6D:'conv.u4',0x6E:'conv.u8',0x6F:'callvirt',0x70:'cpobj',0x71:'ldobj',0x72:'ldstr',
 0x73:'newobj',0x74:'castclass',0x75:'isinst',0x76:'conv.r.un',0x79:'unbox',0x7A:'throw',0x7B:'ldfld',0x7C:'ldflda',0x7D:'stfld',
 0x7E:'ldsfld',0x7F:'ldsflda',0x80:'stsfld',0x81:'stobj',0x82:'conv.ovf.i1.un',0x83:'conv.ovf.i2.un',0x84:'conv.ovf.i4.un',
 0x85:'conv.ovf.i8.un',0x86:'conv.ovf.u1.un',0x87:'conv.ovf.u2.un',0x88:'conv.ovf.u4.un',0x89:'conv.ovf.u8.un',0x8A:'conv.ovf.i.un',
 0x8B:'conv.ovf.u.un',0x8C:'box',0x8D:'newarr',0x8E:'ldlen',0x8F:'ldelema',0x90:'ldelem.i1',0x91:'ldelem.u1',0x92:'ldelem.i2',
 0x93:'ldelem.u2',0x94:'ldelem.i4',0x95:'ldelem.u4',0x96:'ldelem.i8',0x97:'ldelem.i',0x98:'ldelem.r4',0x99:'ldelem.r8',
 0x9A:'ldelem.ref',0x9B:'stelem.i',0x9C:'stelem.i1',0x9D:'stelem.i2',0x9E:'stelem.i4',0x9F:'stelem.i8',0xA0:'stelem.r4',
 0xA1:'stelem.r8',0xA2:'stelem.ref',0xA3:'ldelem',0xA4:'stelem',0xA5:'unbox.any',0xB3:'conv.ovf.i1',0xB4:'conv.ovf.u1',
 0xB5:'conv.ovf.i2',0xB6:'conv.ovf.u2',0xB7:'conv.ovf.i4',0xB8:'conv.ovf.u4',0xB9:'conv.ovf.i8',0xBA:'conv.ovf.u8',
 0xBB:'refanyval',0xBC:'ckfinite',0xBD:'mkrefany',0xC2:'refanytype',0xC3:'readonly.',0xC6:'arglist',0xC7:'ceq',0xC8:'cgt',
 0xC9:'cgt.un',0xCA:'clt',0xCB:'clt.un',0xCC:'ldftn',0xCD:'ldvirtftn',0xD0:'ldtoken',0xD3:'ldloc',
 0xD4:'ldloca',0xD5:'stloc',0xD6:'localloc',0xDC:'endfault',0xDE:'leave',0xDF:'leave.s',0xFE:'prefix',
}
ONE = {
    0x00:0,0x01:0,0x02:0,0x03:0,0x04:0,0x05:0,0x06:0,0x07:0,0x08:0,0x09:0,0x0A:0,
    0x0B:0,0x0C:0,0x0D:0,0x0E:1,0x0F:1,0x10:1,0x11:1,0x12:1,0x13:1,0x14:0,0x15:0,0x16:0,0x17:0,0x18:0,0x19:0,0x1A:0,
    0x1B:0,0x1C:0,0x1D:0,0x1E:1,0x1F:1,0x20:4,0x21:8,0x22:4,0x23:8,0x24:0,0x25:0,0x26:0,0x27:4,0x28:4,0x29:0,0x2A:0,
    0x2B:1,0x2C:1,0x2D:1,0x2E:1,0x2F:1,0x30:0,0x31:0,0x32:0,0x33:0,0x34:0,0x35:0,0x36:0,0x37:0,0x38:4,0x39:4,0x3A:4,
    0x3B:4,0x3C:4,0x3D:4,0x3E:4,0x3F:4,0x40:4,0x41:4,0x42:4,0x43:4,0x44:4,0x45:'switch',0x46:0,0x47:0,0x48:0,0x49:0,0x4A:0,
    0x4B:0,0x4C:0,0x4D:0,0x4E:0,0x4F:0,0x50:0,0x51:0,0x52:0,0x53:0,0x54:0,0x55:0,0x56:0,0x57:0,0x58:0,0x59:0,0x5A:0,
    0x5B:0,0x5C:0,0x5D:0,0x5E:0,0x5F:0,0x60:0,0x61:0,0x62:0,0x63:0,0x64:0,0x65:0,0x66:0,0x67:0,0x68:0,0x69:0,0x6A:0,
    0x6B:0,0x6C:0,0x6D:0,0x6E:0,0x6F:4,0x70:4,0x71:4,0x72:4,0x73:4,0x74:4,0x75:4,0x76:0,0x77:0,0x78:0,0x79:4,0x7A:0,
    0x7B:4,0x7C:4,0x7D:4,0x7E:4,0x7F:4,0x80:4,0x81:4,0x82:0,0x83:0,0x84:0,0x85:0,0x86:0,0x87:0,0x88:0,0x89:0,0x8A:0,
    0x8B:0,0x8C:4,0x8D:4,0x8E:0,0x8F:4,0x90:0,0x91:0,0x92:0,0x93:0,0x94:0,0x95:0,0x96:0,0x97:0,0x98:0,0x99:0,0x9A:0,
    0x9B:0,0x9C:0,0x9D:0,0x9E:0,0x9F:0,0xA0:0,0xA1:0,0xA2:0,0xA3:4,0xA4:4,0xA5:4,0xA6:1,0xB3:0,0xB4:0,0xB5:0,0xB6:0,0xB7:0,
    0xB8:0,0xB9:0,0xBA:0,0xBB:0,0xBC:0,0xBD:0,0xBE:4,0xBF:4,0xC0:4,0xC1:4,0xC2:0,0xC3:0,0xC4:0,0xC5:0,0xC6:0,0xC7:0,
    0xC8:0,0xC9:0,0xCA:0,0xCB:0,0xCC:4,0xCD:4,0xCE:0,0xCF:0,0xD0:4,0xD6:0,0xD7:0,
    0xD8:0,0xD9:0,0xDA:0,0xDB:0,0xDC:0,0xDD:0,0xDE:4,0xDF:1,0xE0:0,
}
TWO = {0x00:0,0x01:0,0x02:0,0x03:0,0x04:0,0x05:0,0x06:4,0x07:4,0x08:4,0x09:4,0x0A:0,0x0B:0,0x0C:0,0x0D:0,0x0E:0,0x0F:0,
       0x09:2,0x0A:2,0x0B:2,0x0C:2,0x0D:2,0x0E:2,0x10:0,0x11:0,0x12:0,0x13:0,0x14:0,0x15:0,0x16:4,0x17:0,0x18:0,0x19:0,0x1A:0,0x1B:0,0x1C:4,0x1D:0,0x1E:0,0x1F:0}

def code_only(raw):
    raw = bytes(raw)
    if len(raw) < 8: return b''
    b0 = raw[0]
    if (b0 & 0x7) == 0x2:
        return raw[1:1 + (b0 >> 2)]
    hsz = ((struct.unpack('<H', raw[:2])[0] >> 12)) * 4
    csz = struct.unpack('<I', raw[4:8])[0]
    return raw[hsz:hsz + csz]

class Resolver:
    def __init__(self, pe):
        self.pe = pe
        T = pe.metadata_tables_lookup
        self.methoddefs = T['MethodDef'].table_rows if 'MethodDef' in T else []
        self.memberrefs = T['MemberRef'].table_rows if 'MemberRef' in T else []
        self.typerefs = T['TypeRef'].table_rows if 'TypeRef' in T else []
        self.typedefs = T['TypeDef'].table_rows if 'TypeDef' in T else []
        self.fields = T['Field'].table_rows if 'Field' in T else []
        self.assemblyrefs = T['AssemblyRef'].table_rows if 'AssemblyRef' in T else []
        # methoddef index -> (type, name)
        self.mdef_owner = {}
        cur = 0
        for ti, td in enumerate(self.typedefs):
            try: start = td.MethodList.value
            except Exception: continue
            # count determined by next typedef
        # simpler: build typedef names list
        self.typedef_names = []
        for td in self.typedefs:
            try:
                ns = pe.get_string(td.string_stream_references['TypeNamespace'])
                nm = pe.get_string(td.string_stream_references['TypeName'])
            except Exception:
                ns, nm = '?', '?'
            self.typedef_names.append(f'{ns}.{nm}' if ns else nm)
    def s(self, addr):
        try: return self.pe.get_string(addr)
        except Exception: return '?'
    def us(self, tok):
        try: return self.pe.get_user_string(tok & 0xFFFFFF)
        except Exception: return f'<US{tok:08x}>'
    def memberref_parent(self, coded):
        tag, idx = coded & 0x7, coded >> 3
        if tag == 0:
            if 1 <= idx <= len(self.typedef_names): return self.typedef_names[idx-1]
            return f'TypeDef?{idx}'
        if tag == 1: return self.typeref_name(idx)
        if tag == 3: return f'MethodDef?{idx}'
        if tag == 4: return f'TypeSpec?{idx}'
        return f'mrp{tag}:{idx}'
    def typeref_name(self, idx):
        if 1 <= idx <= len(self.typerefs):
            tr = self.typerefs[idx-1]
            ns = self.s(tr.string_stream_references.get('TypeNamespace'))
            nm = self.s(tr.string_stream_references.get('TypeName'))
            return f'{ns}.{nm}' if ns else nm
        return f'TypeRef?{idx}'
    def token(self, tok):
        tab = tok >> 24; idx = tok & 0xFFFFFF
        if tab == 0x70:
            return f'"{self.us(tok)}"'
        if tab == 0x0A:
            if 1 <= idx <= len(self.memberrefs):
                mr = self.memberrefs[idx-1]
                mn = self.s(mr.string_stream_references.get('Name'))
                cls = mr.Class.value
                owner = self.memberref_parent(cls)
                return f'{owner}::{mn}'
            return f'MemberRef?{idx}'
        if tab == 0x06:
            if 1 <= idx <= len(self.methoddefs):
                md = self.methoddefs[idx-1]
                mn = self.s(md.string_stream_references.get('Name'))
                return f'MethodDef#{idx}:{mn}'
            return f'MethodDef?{idx}'
        if tab == 0x04:
            if 1 <= idx <= len(self.fields):
                fr = self.fields[idx-1]
                fn = self.s(fr.string_stream_references.get('Name'))
                return f'Field#{idx}:{fn}'
            return f'Field?{idx}'
        if tab == 0x02:
            if 1 <= idx <= len(self.typedef_names):
                return self.typedef_names[idx-1]
            return f'TypeDef?{idx}'
        if tab == 0x01:
            return self.typeref_name(idx)
        if tab == 0x23:
            return f'AssemblyRef?...'
        return f'tok{tab:02x}:{idx}'

def disasm(pe, code):
    r = Resolver(pe)
    i, n, out = 0, len(code), []
    while i < n:
        off = i
        op = code[i]; i += 1
        if op == 0xFE:
            op2 = code[i]; i += 1
            sz = TWO.get(op2, 0)
            extra = f' {code[i:i+sz].hex()}' if sz else ''
            out.append(f'{off:04x} FE{op2:02x}{extra}')
            i += sz
            continue
        name = NAMES1.get(op, f'{op:02x}?')
        sz = ONE.get(op)
        if sz is None:
            out.append(f'{off:04x} {name} <unknown-size STOP>')
            break
        if sz == 'switch':
            cnt = struct.unpack('<I', code[i:i+4])[0]; i += 4
            out.append(f'{name} [{cnt}]')
            i += cnt * 4
            continue
        raw = code[i:i+sz]; i += sz
        if sz == 4 and op in (0x28,0x6F,0x73,0x72,0x74,0x75,0x7B,0x7C,0x7D,0x7E,0x7F,0x80,0x70,0x71,0x8C,0x8D,0xA3,0xA4,0xA5,0xCC,0xCD,0xD1,0xC0,0xC1,0xBE,0xBF):
            tok = struct.unpack('<I', raw)[0]
            if op == 0x72:
                operand = f'"{r.us(tok)}"'
            else:
                operand = r.token(tok)
            out.append(f'{off:04x} {name} {operand}')
        elif sz in (1,2,4,8):
            val = int.from_bytes(raw, 'little', signed=(op in (0x1F,0x20,0x2B,0x2C,0x2D,0x2E,0x2F,0x38,0x39,0x3A,0x3B,0x3C,0x3D,0x3E,0x3F,0x40,0x41,0x42,0x43,0x44)))
            if op in (0x2B,0x2C,0x2D,0x2E,0x2F,0x38,0x39,0x3A,0x3B,0x3C,0x3D,0x3E,0x3F,0x40,0x41,0x42,0x43,0x44):
                out.append(f'{off:04x} {name} -> {i+val:04x}')
            else:
                out.append(f'{off:04x} {name} {val}')
        else:
            out.append(f'{off:04x} {name}')
    return out

def main():
    path, tfilter, mfilter = sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ''
    pe = dotnetfile.DotNetPE(path)
    for t in pe.TypeDef.get_type_names_with_methods():
        full = f'{t.Namespace}.{t.Type}' if t.Namespace else t.Type
        if tfilter.lower() not in full.lower(): continue
        for m in t.Methods:
            if mfilter.lower() not in m.Name.lower(): continue
            print(f'===== {full}.{m.Name} =====')
            code = code_only(m.RawBytes)
            if not code:
                print('  (no body)')
                continue
            for line in disasm(pe, code):
                print('  ' + line)

if __name__ == '__main__':
    main()
