
from __future__ import annotations

import logging
import struct

logger = logging.getLogger(__name__)

ECO_NAMES = ['Carnivorous', 'Herbivorous', 'Omnivorous', 'Scavenging']
PHYLA     = ['Insectoid', 'Reptilian', 'Glabrian', 'Avian',
             'Furrian', 'Crustacean', 'Aquarian', 'Amphibian']


def decode_species(dna: bytes | None) -> str:
    if not dna or len(dna) < 20:
        return ''

    dword0 = struct.unpack_from('<I', dna, 0)[0]
    dword1 = struct.unpack_from('<I', dna, 4)[0]
    dword4 = struct.unpack_from('<I', dna, 16)[0]

    eco_role = (dword1 >> 6) & 3
    phylum   = dword4 & 7

    b10 = bool((dword1 >> 10) & 1)
    b11 = bool(dword1 & 0x800)
    b12 = bool((dword1 >> 12) & 1)
    has_legs  = bool(dword0 & 0x0300)
    has_wings = bool(dword0 & 0x60000)

    if b11 and b10 and has_legs and has_wings and b12:
        loco = 'Triphibious '
    elif (dword1 & 0x1800) == 0x1800:
        loco = 'Amphibious '
    elif b11 and b10 and has_legs and has_wings:
        loco = 'Aquaerial '
    elif b10 and has_legs and has_wings:
        loco = 'Aerial '
    elif b11:
        loco = 'Aquatic '
    else:
        loco = ''

    prefix = 'Subterranean ' if (dword1 & 0x2000) else ''

    eco_str = ECO_NAMES[eco_role] if eco_role < len(ECO_NAMES) else f'Eco{eco_role}'
    phy_str = PHYLA[phylum]       if phylum   < len(PHYLA)      else f'Phylum{phylum}'

    return prefix + loco + eco_str + ' ' + phy_str


def decode_eco_role(dna: bytes | None) -> str:
    if not dna or len(dna) < 8:
        return ''
    dword1 = struct.unpack_from('<I', dna, 4)[0]
    idx = (dword1 >> 6) & 3
    return ECO_NAMES[idx] if idx < len(ECO_NAMES) else f'Eco{idx}'


def decode_phylum(dna: bytes | None) -> str:
    if not dna or len(dna) < 20:
        return ''
    dword4 = struct.unpack_from('<I', dna, 16)[0]
    idx = dword4 & 7
    return PHYLA[idx] if idx < len(PHYLA) else f'Phylum{idx}'


def is_exoskeletal(dna: bytes | None) -> bool:
    if not dna or len(dna) < 20:
        return False
    dword4 = struct.unpack_from('<I', dna, 16)[0]
    phylum = dword4 & 7
    return phylum in (0, 5)


if __name__ == '__main__':
    sample = bytes.fromhex('7a9d60651450611672004b6c5474c562627606692d4c4e00')
    logger.debug("Species : %r", decode_species(sample))
    logger.debug("Eco : %r", decode_eco_role(sample))
    logger.debug("Phylum : %r", decode_phylum(sample))
    logger.debug("Exo : %s", is_exoskeletal(sample))
