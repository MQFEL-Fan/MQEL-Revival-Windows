"""Find caller methods of a given (TypeRef-family, method name) MemberRef target.

Usage: callfinder.py <assembly> <OwnerTypeName-suffix> <MethodName>
Walks all method IL bodies, records call/callvirt/newobj tokens, resolves them.
"""
import pathlib, struct, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from ildump import ONE, TWO, code_only, Resolver


def walk(code):
    """Yield (offset, is_call_like, token)."""
    i, n = 0, len(code)
    while i < n:
        off = i
        op = code[i]; i += 1
        if op == 0xFE:
            if i >= n: break
            i += TWO.get(code[i], 0) + 1
            continue
        sz = ONE.get(op)
        if sz is None: break
        if sz == 'switch':
            if i + 4 > n: break
            i += 4 + struct.unpack('<I', code[i:i+4])[0] * 4
            continue
        if sz == 4 and op in (0x28, 0x6F, 0x73):
            yield off, op, struct.unpack('<I', code[i:i+4])[0]
        i += sz


def main():
    path, owner_suf, mname = sys.argv[1], sys.argv[2], sys.argv[3]
    import dotnetfile
    pe = dotnetfile.DotNetPE(path)
    r = Resolver(pe)
    # find MemberRef tokens matching owner suffix + method name
    targets = set()
    for idx, mref in enumerate(r.memberrefs, start=1):
        try:
            mn = pe.get_string(mref.string_stream_references.get('Name'))
        except Exception:
            continue
        if mn != mname:
            continue
        owner = r.memberref_parent(mref.Class.value)
        if owner.endswith(owner_suf) or owner_suf in owner:
            targets.add(0x0A000000 | idx)
    # find same-assembly MethodDef targets with owner check
    for t in pe.TypeDef.get_type_names_with_methods():
        full = f'{t.Namespace}.{t.Type}' if t.Namespace else t.Type
        if not (full.endswith(owner_suf) or owner_suf in full):
            continue
        # method row numbers: need global index; recompute via metadata order
    # global method index -> owner map
    T = pe.metadata_tables_lookup
    typedefs = T['TypeDef'].table_rows
    methoddefs = T['MethodDef'].table_rows
    starts = []
    for td in typedefs:
        try: starts.append(td.MethodList.value)
        except Exception: starts.append(1)
    for mi, md in enumerate(methoddefs):
        try:
            mn = pe.get_string(md.string_stream_references.get('Name'))
        except Exception:
            continue
        if mn != mname:
            continue
        for ti in range(len(starts)):
            lo = starts[ti]
            hi = starts[ti + 1] if ti + 1 < len(starts) else len(methoddefs) + 1
            if lo <= mi + 1 < hi:
                try:
                    ns = pe.get_string(typedefs[ti].string_stream_references.get('TypeNamespace'))
                    tn = pe.get_string(typedefs[ti].string_stream_references.get('TypeName'))
                except Exception:
                    ns, tn = '', '?'
                full = f'{ns}.{tn}' if ns else tn
                if full.endswith(owner_suf) or owner_suf in full:
                    targets.add(0x06000000 | (mi + 1))
                break
    print('target tokens:', [hex(t) for t in targets])
    for t in pe.TypeDef.get_type_names_with_methods():
        full = f'{t.Namespace}.{t.Type}' if t.Namespace else t.Type
        for m in t.Methods:
            code = code_only(m.RawBytes)
            if not code:
                continue
            for off, op, tok in walk(code):
                if tok in targets:
                    print(f'{full}.{m.Name} @ {off:04x} calls {r.token(tok)}')


if __name__ == '__main__':
    main()
