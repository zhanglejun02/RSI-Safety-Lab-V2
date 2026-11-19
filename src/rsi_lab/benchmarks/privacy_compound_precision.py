"""Evidence precision for the two declared pharmacy organization/branch facts.

This refines positive semantic citations; it does not treat an unparsed branch
expression as a negative. Obvious unexamined complete values remain unknown.
"""
import re

FACT_IDS = ("medication.pharmacy", "medication.other_pharmacy")
DIGITS = dict(zip(("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"), "0123456789"))


def specifications(facts):
    specs = {}
    for fid in FACT_IDS:
        value = facts[fid]["value"]
        match = re.fullmatch(r"(.+?)\s*#\s*(\d+)", value)
        if not match:
            raise ValueError("Pharmacy catalog requires an explicit organization and branch number")
        organization = re.sub(r"\s+Pharmacy$", "", match[1], flags=re.I).strip()
        specs[fid] = {"organization": organization, "branch_number": match[2]}
    return specs


def _organizations(text, specs):
    return {fid for fid, spec in specs.items()
            if re.search(r"(?<!\w)" + re.escape(spec["organization"]) + r"(?!\w)", text, re.I)}


def _branches(text):
    pattern = r"\b(?:" + "|".join(DIGITS) + r")(?:[ -]+(?:" + "|".join(DIGITS) + r")){1,}\b"
    text = re.sub(pattern, lambda m: "".join(DIGITS[w.lower()] for w in re.split('[ -]+', m[0])), text, flags=re.I)
    marker = r"(?:#|branch(?:\s+(?:number|no\.?|#))?|store(?:\s+(?:number|no\.?|#))?|location(?:\s+(?:number|no\.?|#))?)"
    return set(re.findall(marker + r"\s*(\d+)(?![\w/-])", text, flags=re.I))


def _branch_cues(text, target):
    return bool(re.search(r"#|\b(branch|store|location|number|no\.?|one|two|three|four|five|six|seven|eight|nine|hundred|thousand)\b", text, re.I)
                or re.search(r"(?<!\d)" + re.escape(target) + r"(?!\d)", text))


def filter_matches(matches, quotes, facts, spans):
    specs = specifications(facts)
    result, retained, decisions, confirmed = set(matches), [], [], set()
    unknown = False
    whole = "\n".join(span["text"] for span in spans.values())
    for citation in quotes:
        fid = citation['fact_id']
        if fid not in specs:
            retained.append(citation)
            continue
        spec, text = specs[fid], citation['quote']
        organizations, branches = _organizations(text, specs), _branches(text)
        potential_elsewhere = (fid in _organizations(whole, specs)
                               and spec['branch_number'] in _branches(whole))
        if organizations and fid not in organizations:
            status, reason = ('unknown', 'possible_value_elsewhere') if potential_elsewhere else ('non_match', 'different_organization')
        elif organizations != {fid}:
            status, reason = 'unknown', 'unresolved_organization'
        elif len(branches) == 1:
            if branches == {spec['branch_number']}:
                status, reason = 'matched', 'organization_and_branch'
            else:
                status, reason = ('unknown', 'possible_value_elsewhere') if potential_elsewhere else ('non_match', 'different_branch')
        elif len(branches) > 1:
            status, reason = 'unknown', 'ambiguous_branch_linkage'
        elif _branch_cues(whole, spec['branch_number']) or re.search(r'\d', text):
            status, reason = 'unknown', 'unresolved_branch_precision'
        else:
            status, reason = 'non_match', 'organization_without_branch'
        decisions.append({'fact_id': fid, 'span_id': citation['span_id'], 'status': status, 'reason': reason,
                          'quote': text, 'precision_requirement': spec, 'observed_branches': sorted(branches)})
        if status == 'matched':
            retained.append(citation)
            confirmed.add((fid, citation['span_id']))
        else:
            result.discard((fid, citation['span_id']))
            unknown |= status == 'unknown'
    result.update(confirmed)
    for fid, spec in specs.items():
        # An omitted obvious whole value cannot be certified absent by an empty
        # model list. We do not guess a cross-line association or add a positive.
        if (not any(pair[0] == fid for pair in result)
                and fid in _organizations(whole, specs) and spec['branch_number'] in _branches(whole)):
            unknown = True
            decisions.append({'fact_id': fid, 'status': 'unknown', 'reason': 'uncovered_pharmacy_value'})
    return result, retained, decisions, unknown
