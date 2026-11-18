"""Build the complete HTTP API map from .NET Contracts assemblies.

For every [Service] interface: ServiceName, and per method: HTTP verb
(JsonGet/JsonPost/StreamGet/StreamPost/HtmlGet), Private flag, blob details.
Joins with XML-doc signatures by method name when available.
"""
import re, sys, xml.etree.ElementTree as ET
import dotnetfile


def s(pe, a):
    try:
        return pe.get_string(a)
    except Exception:
        return ''


def load(pe_path):
    pe = dotnetfile.DotNetPE(pe_path)
    T = pe.metadata_tables_lookup
    typedefs = T['TypeDef'].table_rows
    methoddefs = T['MethodDef'].table_rows
    memberrefs = T['MemberRef'].table_rows if 'MemberRef' in T else []
    typerefs = T['TypeRef'].table_rows if 'TypeRef' in T else []
    paramrows = T['Param'].table_rows if 'Param' in T else []

    tdnames = []
    starts = []
    for td in typedefs:
        ns = s(pe, td.string_stream_references.get('TypeNamespace'))
        nm = s(pe, td.string_stream_references.get('TypeName'))
        tdnames.append(f'{ns}.{nm}' if ns else nm)
        try:
            starts.append(td.MethodList.value)
        except Exception:
            starts.append(1)

    methods = []  # (owner_idx, name)
    # Param table ranges per method: MethodDef.ParamList gives start row (1-based)
    mstarts = []
    for md in methoddefs:
        try:
            mstarts.append(md.ParamList.value)
        except Exception:
            mstarts.append(1)
    for mi, md in enumerate(methoddefs):
        owner = None
        for ti in range(len(starts)):
            lo = starts[ti]
            hi = starts[ti + 1] if ti + 1 < len(starts) else len(methoddefs) + 1
            if lo <= mi + 1 < hi:
                owner = ti
                break
        # collect param names in sequence order
        plo = mstarts[mi]
        phi = mstarts[mi + 1] if mi + 1 < len(mstarts) else len(paramrows) + 1
        pnames = []
        for pi in range(plo - 1, phi - 1):
            if 0 <= pi < len(paramrows):
                pr = paramrows[pi]
                try:
                    seq = pr.Sequence.value
                except Exception:
                    seq = 0
                if seq == 0:
                    continue  # return-value marker row
                pnames.append((seq, s(pe, pr.string_stream_references.get('Name'))))
        pnames.sort()
        methods.append((owner, s(pe, md.string_stream_references.get('Name')),
                        [n for _, n in pnames]))

    # memberref owners for attribute type names
    mrowner = {}
    for i, m in enumerate(memberrefs):
        cls = m.Class.value
        tag, cidx = cls & 0x7, cls >> 3
        ow = '?'
        if tag == 1 and 1 <= cidx <= len(typerefs):
            t = typerefs[cidx - 1]
            ns = s(pe, t.string_stream_references.get('TypeNamespace'))
            tn = s(pe, t.string_stream_references.get('TypeName'))
            ow = f'{ns}.{tn}' if ns else tn
        mrowner[i + 1] = (ow, s(pe, m.string_stream_references.get('Name')))

    # custom attributes: parent tag 3 = TypeDef, tag 0 = MethodDef (dotnetfile numbering)
    type_attrs = {}    # typedef idx -> list of (attr_class, blob)
    method_attrs = {}  # methoddef idx -> list of (attr_class, blob)
    for row in T['CustomAttribute'].table_rows:
        p = row.Parent.value
        ptag, pidx = p & 0x1F, (p >> 5) - 1
        t = row.Type.value
        ttag, tidx = t & 0x7, (t >> 3) - 1
        aclass = '?'
        if ttag == 3 and (tidx + 1) in mrowner:
            aclass = mrowner[tidx + 1][0]
        e = pe.dotnet_blob_lookup.get(row.Value.value)
        blob = bytes(e.buffer) if e is not None else b''
        if ptag == 3 and 0 <= pidx < len(tdnames):
            type_attrs.setdefault(pidx, []).append((aclass, blob))
        elif ptag == 0 and 0 <= pidx < len(methods):
            method_attrs.setdefault(pidx, []).append((aclass, blob))
    return pe, tdnames, methods, type_attrs, method_attrs


def blob_named_strings(blob):
    """Extract readable ascii runs from a CA blob."""
    return [m.group().decode('ascii') for m in re.finditer(rb'[\x20-\x7e]{3,}', blob)]


def main():
    asm = sys.argv[1]
    only_service = len(sys.argv) > 2 and sys.argv[2] == '--services-only'
    pe, tdnames, methods, tattrs, mattrs = load(asm)

    # index methods per type
    by_type = {}
    for mi, (owner, name, pnames) in enumerate(methods):
        if owner is not None:
            by_type.setdefault(owner, []).append((mi, name, pnames))

    for ti, tname in enumerate(tdnames):
        sa = [a for a in tattrs.get(ti, []) if a[0].endswith('ServiceAttribute')]
        if not sa:
            continue
        svc_names = []
        priv_type = False
        for aclass, blob in tattrs.get(ti, []):
            if aclass.endswith('ServiceAttribute'):
                strs = blob_named_strings(blob)
                svc_names += [x for x in strs if x != 'ServiceName']
            if aclass.endswith('PrivateAttribute'):
                priv_type = True
        print(f'SERVICE {tname} ServiceName={svc_names} TypePrivate={priv_type}')
        if only_service:
            continue
        for mi, mname, pnames in by_type.get(ti, []):
            verbs = [a[0].split('.')[-1] for a in mattrs.get(mi, [])
                     if a[0].split('.')[-1] in ('JsonGetAttribute', 'JsonPostAttribute',
                                                'StreamGetAttribute', 'StreamPostAttribute',
                                                'HtmlGetAttribute')]
            priv = any(a[0].endswith('PrivateAttribute') for a in mattrs.get(mi, []))
            other = [a[0].split('.')[-1] + ':' + '|'.join(blob_named_strings(a[1]))
                     for a in mattrs.get(mi, []) if not a[0].endswith(
                         ('JsonGetAttribute', 'JsonPostAttribute', 'StreamGetAttribute',
                          'StreamPostAttribute', 'HtmlGetAttribute', 'PrivateAttribute'))]
            print('    ' + mname + '(' + ', '.join(pnames) + ') verbs=' + str(verbs) + ' private=' + str(priv) + ' other=' + str(other))


if __name__ == '__main__':
    main()
