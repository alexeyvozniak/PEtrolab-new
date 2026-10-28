"""Versioned, deterministic header interpretation; no unit or fuzzy imputation."""
from __future__ import annotations

from difflib import get_close_matches
import re
import unicodedata

DICTIONARY_VERSION = '2026.09.1'

# Atomic number order. Names are aliases, not new scientific components.
ELEMENT_DATA = '''H hydrogen водород
He helium гелий
Li lithium литий
Be beryllium бериллий
B boron бор
C carbon углерод
N nitrogen азот
O oxygen кислород
F fluorine фтор
Ne neon неон
Na sodium натрий
Mg magnesium магний
Al aluminium алюминий
Si silicon кремний
P phosphorus фосфор
S sulfur сера
Cl chlorine хлор
Ar argon аргон
K potassium калий
Ca calcium кальций
Sc scandium скандий
Ti titanium титан
V vanadium ванадий
Cr chromium хром
Mn manganese марганец
Fe iron железо
Co cobalt кобальт
Ni nickel никель
Cu copper медь
Zn zinc цинк
Ga gallium галлий
Ge germanium германий
As arsenic мышьяк
Se selenium селен
Br bromine бром
Kr krypton криптон
Rb rubidium рубидий
Sr strontium стронций
Y yttrium иттрий
Zr zirconium цирконий
Nb niobium ниобий
Mo molybdenum молибден
Tc technetium технеций
Ru ruthenium рутений
Rh rhodium родий
Pd palladium палладий
Ag silver серебро
Cd cadmium кадмий
In indium индий
Sn tin олово
Sb antimony сурьма
Te tellurium теллур
I iodine йод
Xe xenon ксенон
Cs caesium цезий
Ba barium барий
La lanthanum лантан
Ce cerium церий
Pr praseodymium празеодим
Nd neodymium неодим
Pm promethium прометий
Sm samarium самарий
Eu europium европий
Gd gadolinium гадолиний
Tb terbium тербий
Dy dysprosium диспрозий
Ho holmium гольмий
Er erbium эрбий
Tm thulium тулий
Yb ytterbium иттербий
Lu lutetium лютеций
Hf hafnium гафний
Ta tantalum тантал
W tungsten вольфрам
Re rhenium рений
Os osmium осмий
Ir iridium иридий
Pt platinum платина
Au gold золото
Hg mercury ртуть
Tl thallium таллий
Pb lead свинец
Bi bismuth висмут
Po polonium полоний
At astatine астат
Rn radon радон
Fr francium франций
Ra radium радий
Ac actinium актиний
Th thorium торий
Pa protactinium протактиний
U uranium уран
Np neptunium нептуний
Pu plutonium плутоний
Am americium америций
Cm curium кюрий
Bk berkelium берклий
Cf californium калифорний
Es einsteinium эйнштейний
Fm fermium фермий
Md mendelevium менделевий
No nobelium нобелий
Lr lawrencium лоуренсий
Rf rutherfordium резерфордий
Db dubnium дубний
Sg seaborgium сиборгий
Bh bohrium борий
Hs hassium хассий
Mt meitnerium мейтнерий
Ds darmstadtium дармштадтий
Rg roentgenium рентгений
Cn copernicium коперниций
Nh nihonium нихоний
Fl flerovium флеровий
Mc moscovium московий
Lv livermorium ливерморий
Ts tennessine теннессин
Og oganesson оганесон'''

ELEMENTS = tuple(line.split()[0] for line in ELEMENT_DATA.splitlines())
COMPONENTS = tuple('SiO2 TiO2 Al2O3 FeO FeOt Fe2O3 Fe2O3t MnO MgO CaO Na2O K2O P2O5 Cr2O3 NiO BaO SrO ZnO ZrO2 V2O3 V2O5 B2O3 Li2O CuO Cu2O SO2 SO3 H2O H2O+ H2O- CO2 Total LOI Nb2O5 Ta2O5 Y2O3 La2O3 Ce2O3 CeO2 Pr2O3 Nd2O3 Sm2O3 Eu2O3 Gd2O3 Tb2O3 Dy2O3 Ho2O3 Er2O3 Tm2O3 Yb2O3 Lu2O3 ThO2 UO2 U3O8 SnO2 HfO2'.split())
CANONICAL = ELEMENTS + COMPONENTS


def normalize(text):
    text = unicodedata.normalize('NFKC', str(text)).casefold().replace('−', '-')
    return re.sub(r'[\s.,_()[\]{}]', '', text)


NORMALIZED = {normalize(item): item for item in CANONICAL}
ALIASES = {normalize(alias): line.split()[0] for line in ELEMENT_DATA.splitlines() for alias in line.split()[1:]}
ALIASES.update({normalize(alias): canonical for canonical, aliases in {
    'Al': ['aluminum'], 'S': ['sulphur'], 'Cs': ['cesium'],
    'SiO2': ['silica', 'silicon dioxide', 'диоксид кремния', 'кремнезем'],
    'Al2O3': ['alumina', 'aluminium oxide', 'aluminum oxide'],
    'FeOt': ['FeO total', 'FeO tot', 'FeO*', 'total Fe as FeO'],
    'Fe2O3t': ['Fe2O3 total', 'Fe2O3 tot', 'Fe2O3*', 'total Fe as Fe2O3'],
    'Total': ['sum', 'summa', 'sum total', 'сумма', 'всего', 'итого'],
    'LOI': ['loss on ignition', 'ППП', 'потери при прокаливании'],
    'H2O': ['water'], 'CO2': ['carbon dioxide'],
}.items() for alias in aliases})

UNIT_PATTERNS = (
    ('ppb', r'ppb'), ('ppm', r'ppm|мкг\s*/\s*г'),
    ('apfu', r'apfu|а\.?\s*е\.?\s*ф\.?'),
    ('at.%', r'(?:at\.?|atomic|атом\.?|ат\.?)\s*%'),
    ('mol%', r'(?:mol\.?|мол\.?)\s*%'),
    ('wt.%', r'(?:wt\.?|weight|mass|мас\.?|вес\.?)\s*%'),
    ('ratio', r'ratio'), ('epsilon', r'epsilon'), ('permil', r'‰|permil|per\s*mil'),
)


def split_unit(header):
    text = unicodedata.normalize('NFKC', str(header)).strip()
    for unit, pattern in UNIT_PATTERNS:
        # Suffix only; a chemical name containing a unit substring is not a unit.
        match = re.search(r'(?:\s|[,;\[(])?(' + pattern + r')\s*[\])]?\s*$', text, re.I)
        if match:
            return text[:match.start()].strip(' ,;[('), unit
    if text.endswith('%') or re.search(r'\(%\)\s*$', text):
        return text.rstrip(' )%').strip(' ,;[('), None
    return text, None


def recognize_analyte(header, project_aliases=None, *, fuzzy=False):
    raw = str(header)
    text, unit = split_unit(raw)
    token = normalize(text)
    result = {'raw_header': raw, 'canonical_field': None, 'unit': unit,
              'dictionary_version': DICTIONARY_VERSION, 'confidence': 'unresolved',
              'automatic': False, 'evidence': None, 'suggestions': []}
    if re.fullmatch(r'(?i)no\.|n\.\s*d\.|№|#', text.strip()):
        result['evidence'] = {'rule': 'ambiguous_nonchemical_abbreviation'}
        return result
    field, level = None, None
    if text in CANONICAL:
        field, level = text, 'exact_canonical'
    elif token in NORMALIZED:
        field, level = NORMALIZED[token], 'safe_normalization'
    elif token in ALIASES:
        field, level = ALIASES[token], 'known_alias'
    elif token in (project_aliases or {}):
        entry = project_aliases[token]
        candidate = entry.get('canonical_field') if isinstance(entry, dict) else None
        if candidate in CANONICAL and entry.get('confirmed') is True:
            field, level = candidate, 'project_alias'
    else:
        # Explicit mass+element notation only, never edit-distance chemistry.
        isotope = r'(\d{1,3})\s*[-^]?\s*([A-Za-z]{1,2})'
        ratio = re.fullmatch(isotope + r'\s*/\s*' + isotope + r'(?:\s*\((0|t|i)\))?', text)
        single = re.fullmatch(isotope, text) or re.fullmatch(r'([A-Za-z]{1,2})[-](\d{1,3})', text)
        epsilon = re.fullmatch(r'[εϵ]\s*([A-Za-z]{1,2})\s*(?:\((t|0|i)\))?', text)
        delta = re.fullmatch(r'[δΔ]\s*' + isotope, text)
        symbols = {s.casefold(): s for s in ELEMENTS}
        if ratio and ratio[2].casefold() in symbols and ratio[4].casefold() in symbols:
            field = f'{int(ratio[1])}{symbols[ratio[2].casefold()]}/{int(ratio[3])}{symbols[ratio[4].casefold()]}' + (f'({ratio[5]})' if ratio[5] else '')
            unit = unit or 'ratio'
        elif epsilon and epsilon[1].casefold() in symbols:
            field = f'ε{symbols[epsilon[1].casefold()]}' + (f'({epsilon[2]})' if epsilon[2] else '')
            unit = unit or 'epsilon'
        elif delta and delta[2].casefold() in symbols:
            field = f'δ{int(delta[1])}{symbols[delta[2].casefold()]}'
        elif single:
            mass, symbol = single.group(1, 2) if single[1].isdigit() else (single[2], single[1])
            if symbol.casefold() in symbols:
                field = f'{int(mass)}{symbols[symbol.casefold()]}'
        if field:
            level = 'deterministic_parser'
    if field:
        result.update(canonical_field=field, unit=unit, confidence=level, automatic=True,
                      evidence={'matched_text': text, 'rule': level})
    elif fuzzy and len(token) > 2:
        result['suggestions'] = list(dict.fromkeys(NORMALIZED[k] for k in get_close_matches(token, NORMALIZED, n=3, cutoff=.8)))
        if result['suggestions']:
            result['confidence'] = 'fuzzy_suggestion'
    return result


def confirmed_alias(raw_header, canonical_field):
    known = recognize_analyte(raw_header)
    if canonical_field not in CANONICAL:
        raise ValueError('Alias target must be a canonical component.')
    if known['automatic'] and known['canonical_field'] != canonical_field:
        raise ValueError('An alias cannot shadow a different canonical component.')
    text, _ = split_unit(raw_header)
    if not normalize(text):
        raise ValueError('Alias header is empty.')
    return normalize(text), {'raw_header': raw_header, 'canonical_field': canonical_field,
                             'confirmed': True, 'origin': 'user_confirmed', 'dictionary_version': DICTIONARY_VERSION}
