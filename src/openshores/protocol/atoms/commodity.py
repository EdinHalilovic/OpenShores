
from __future__ import annotations


_WPN_RANGED_PISTOL  = (50, 0xf, 25, 0, 0, 0, 0)
_WPN_RANGED_RIFLE   = (75, 0xf, 50, 0, 0, 0, 0)
_WPN_RANGED_SHOTGUN = (30, 0xf, 80, 0, 0, 0, 0)
_WPN_RANGED_LASER_P = (50, 0xf, 25, 0, 0, 0, 0)
_WPN_RANGED_LASER_R = (75, 0xf, 50, 0, 0, 0, 0)


_AMMO_CAPACITY_BY_CID = {
    116: (0, 0),
    31:  (15, 0),
    32:  (30, 0),
    117: (8,  0),
    292: (30, 0),
    296: (20, 20),
    305: (15, 15),
}


_BW_HANDHELD = 0x0
_NEWCOND_STD = 100
_STACK_1     = 1

# Temporary fix for weapons, also how to create custom commodities, see Forage Specimen

_COMMODITY_OVERRIDES_DEFAULT = [
    (116, 0x301, 20, 0, 0, "Knife",        ":data/c_Knife.png",        ":data/mKnife.3dsN",
        0,   0,  _BW_HANDHELD, _NEWCOND_STD, 1, 1, _STACK_1, 0.5,
        (0,0,0,0,0,0,0)),
    (31,  0x101, 25, 5, 0, "Pistol",       ":data/c_Pistol.png",       ":data/mPistol.3dsN",
        10,  0,  _BW_HANDHELD, _NEWCOND_STD, 2, 2, _STACK_1, 1.5,
        _WPN_RANGED_PISTOL),
    (32,  0x101, 25, 5, 0, "Rifle",        ":data/c_Rifle.png",        ":data/mRifle.3dsN",
        75,  0,  _BW_HANDHELD, _NEWCOND_STD, 3, 2, _STACK_1, 4.0,
        _WPN_RANGED_RIFLE),
    (117, 0x101, 25, 5, 0, "Shotgun",      ":data/c_Shotgun.png",      ":data/mShotgun.3dsN",
        118, 0,  _BW_HANDHELD, _NEWCOND_STD, 3, 2, _STACK_1, 5.0,
        _WPN_RANGED_SHOTGUN),
    (292, 0x101, 25, 5, 0, "Калашников",   ":data/c_AK47.png",         ":data/mAK47.3dsN",
        75,  0,  _BW_HANDHELD, _NEWCOND_STD, 3, 2, _STACK_1, 4.5,
        _WPN_RANGED_RIFLE),
    (296, 0x101, 25, 5, 5, "Laser Rifle",  ":data/c_LaserRifle.png",   ":data/mLaserRifle.3ds",
        4,   0,  _BW_HANDHELD, _NEWCOND_STD, 3, 2, _STACK_1, 3.5,
        _WPN_RANGED_LASER_R),
    (305, 0x101, 25, 5, 5, "Laser Pistol", ":data/c_LaserPistol.png",  ":data/mLaserPistol.3ds",
        4,   0,  _BW_HANDHELD, _NEWCOND_STD, 2, 2, _STACK_1, 2.0,
        _WPN_RANGED_LASER_P),
    (0x145, 0x01, 0, 0, 0, "Forage Specimen",
        ":data/c_Seed.png", ":data/mSeed.3dsN",
        0,   0,  _BW_HANDHELD, _NEWCOND_STD, 1, 1, 99, 0.05,
        (0,0,0,0,0,0,0)),
]
