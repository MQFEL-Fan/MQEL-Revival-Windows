"""Decode CustomAttribute rows: parent (TypeDef/MethodDef), attribute type, blob strings."""
import re, struct, sys
import dotnetfile


def blob_strings(blob):
    return [m.group().decode('ascii') for m in re.finditer(rb'[\x20-\x7e]{4,}', blob)]


def main():
    path = sys.argv[1]
    filt = sys.argv[2] if len(sys.argv) > 2 else ''
    pe = dotnetfile.DotNetPE(path)
    T = pe.metadata_tables_lookup
    typedefs = T['TypeDef'].table_rows
    methoddefs = T['MethodDef'].table_rows
    memberrefs = T['MemberRef'].table_rows if 'MemberRef' in T else []
    typerefs = T['TypeRef'].table_rows if 'TypeRef' in T else []

    def s(addr):
        try:
            return pe.get_string(addr)
        except Exception:
            return '?'

    tdnames, method_names = [], []
    # method index ranges per typedef
    starts = []
    for td in typedefs:
        try:
            starts.append(td.MethodList.value)
        except Exception:
            starts.append(1)
        ns = s(td.string_stream_references.get('TypeNamespace'))
        nm = s(td.string_stream_references.get('TypeName'))
        tdnames.append(f'{ns}.{nm}' if ns else nm)
    for mi, md in enumerate(methoddefs):
        # find owner: last typedef with start <= mi+1
        owner = '?'
        for ti in range(len(starts)):
            lo = starts[ti]
            hi = starts[ti + 1] if ti + 1 < len(starts) else len(methoddefs) + 1
            if lo <= mi + 1 < hi:
                owner = tdnames[ti]
                break
        method_names.append(f'{owner}.{s(md.string_stream_references.get("Name"))}')

    def attr_type_name(typ_coded):
        tag, idx = typ_coded & 0x7, typ_coded >> 3
        if tag != 3:
            return f'catag{tag}:{idx}'
        idx -= 1
        if not (0 <= idx < len(memberrefs)):
            return 'MemberRef?'
        mr = memberrefs[idx]
        mn = s(mr.string_stream_references.get('Name'))
        cls = mr.Class.value
        tag, cidx = cls & 0x7, cls >> 3
        if tag == 1 and 1 <= cidx <= len(typerefs):
            tr = typerefs[cidx - 1]
            ns = s(tr.string_stream_references.get('TypeNamespace'))
            tn = s(tr.string_stream_references.get('TypeName'))
            return f'{ns}.{tn}::{mn}'
        return f'mrp{tag}:{cidx}::{mn}'

    # CustomAttribute.Parent coded index tags
    for row in T['CustomAttribute'].table_rows:
        parent = row.Parent.value
        tag, idx = parent & 0x1F, (parent >> 5) - 1
        if tag == 0 and 0 <= idx < len(tdnames):
            pname = tdnames[idx]
        elif tag == 5:
            # Decl: TypeDef or MethodDef (MethodDef table check by range is complex; try method table first if idx in range)
            pname = method_names[idx] if 0 <= idx < len(method_names) else f'Decl?{idx}'
            # disambiguate: CustomAttribute on types uses parent tag 0 usually; tag5 = Decl (used by old compilers for both?)
            # We'll print both candidates
            cand = tdnames[idx] if 0 <= idx < len(tdnames) else None
            if cand:
                pname = f'{pname} OR {cand}'
        else:
            pname = f'tag{tag}:{idx}'
        if filt and filt.lower() not in pname.lower():
            continue
        at = attr_type_name(row.Type.value)
        blob_idx = row.Value.value
        try:
            entry = pe.dotnet_blob_lookup.get(blob_idx)
            blob = bytes(entry.structure_fields.get('BlobData', b'')) if entry else b''
        except Exception:
            blob = b''
        print(f'{pname}\n    <- {at}  blob={blob_strings(blob)}')


if __name__ == '__main__':
    main()
