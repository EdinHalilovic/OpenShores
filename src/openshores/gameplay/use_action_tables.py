
_HARDCODED_FOODS = {
    0x34:   ("Milk",          50),
    0x82:   ("Hay",           25),
    0x2f:   ("Chewy item",    30),
    0xe9:   ("Crunchy item",  30),
    0x14c:  ("Scrapple",      50),
    0x15b:  ("Ice cream",     60),
}

USE_DRINK_CIDS = frozenset({0x53, 0x34})

USE_STAMINA_RESET_CIDS = frozenset({0x53})

USE_TOGGLEABLE_CIDS = {
    0x48: "Environment Helmet",
    0x6a: "Power Armor Helmet (variant 1)",
    0x9a: "Power Armor Helmet (variant 2)",
    0x9c: "Power Armor Helmet (variant 3)",
    0x41: "Environment Suit Body (variant 1)",
    0x50: "Environment Suit Body (variant 2)",
    0x99: "Environment Suit Body (variant 3)",
    0x9b: "Environment Suit Body (variant 4)",
}

ENV_SUIT_BODY_CIDS = frozenset({0x41, 0x50, 0x99, 0x9b})
