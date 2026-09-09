
# Testing NPC conversations

from __future__ import annotations

import struct
from typing import Callable, Dict, List, Optional, Tuple

from openshores.core.logging import get_logger
from openshores.protocol.atoms.aucomm import (
    _parse_aucomm_header,
    build_chat_aucomm_v4,
)
from openshores.protocol.rng import AuDice

from openshores.gameplay.natives.village import (
    ROLE_ADULT,
    ROLE_CHILD,
    ROLE_DOCTOR,
    ROLE_ELDER,
)

logger = get_logger(__name__)


VOICE_CHANNEL_INDEX = 2
VOICE_SCOPE = 15
VOICE_RANGE_BYTE = 0x00

VOICE_FLAGS = 0x4F

AUCOMM_TYPE_CHAT = 0x29
AUCOMM_TYPE_CHAT_CHOICE = 0x2B
AUCOMM_TYPE_CHAT_CONTINUED = 0x2C
AUCOMM_TYPE_HAIL_REPLY = 0x3E
AUCOMM_TYPE_HAIL_REQUEST = 0x3F

CONVERSATION_STORY_INSTANCE = 1

CHAT_TEXT_LIMIT = 256
CHAT_CONTINUED_LIMIT = 8192

GEO_PLACEHOLDER = "G"

GEO_EMPTY_FALLBACK = (
    "There are many beautiful hills and shores in the world.")


ADULT_EXHAUSTED = "I have work to do. Maybe we can chat another time."
WHAT = "What?"
ELDER_TIRED = "I grow tired. I must rest."
ELDER_TIRED_FINAL = "I am tired. I must rest now."
CHILD_TERMINAL = {
    6: "My mom is calling me. I have to go.",
    7: "Really, I have to go.",
    8: "Get away from me creep.",
}
CHILD_TERMINAL_FINAL = "MOM!"


GREET_ELDER = "Greetings avatar %s."
GREET_ELDER_BOUNTY = "Greetings avatar %s. I hear there is a price on your head."
GREET_CHILD = "Hi %s %s."
GREET_DEFAULT = "Greetings %s."


TERSE_HOMESICK = "I want to return to the green hills of home."

TERSE_BY_ROLE: Dict[int, Tuple[str, str, str]] = {
    ROLE_ADULT: (
        "Die %s.",
        "Go away %s. You are shunned from the village.",
        "Stop it %s. I will not speak to you.",
    ),
    ROLE_CHILD: (
        "Aiee! I am begging you %s. Spare me; I am too young to die.",
        "Don't hurt me %s, please. I am only a child.",
        "No %s. You are bad. Go away.",
    ),
    ROLE_ELDER: (
        "You have deeply alienated the people %s. A great deal of time must "
        "pass before their hearts will soften toward you.",
        "Leave the village %s. Go away from here; reflect upon your deeds. "
        "You are banished for a time.",
        "The people are troubled by your actions %s. You must show good "
        "behavior and compassion for a while.",
    ),
    ROLE_DOCTOR: (
        "You have cut the people deeply %s. Only time can heal this wound.",
        "Leave here %s. The people need time to heal.",
        "You have hurt the people %s. Be good for a while; let time be the "
        "cure.",
    ),
}


ADULT_LINES: Tuple[str, ...] = (
    "All things are made up of four basic elements: earth, water, fire, air.",
    "I love the wind.",
    "I like to take long walks through the tall grass. It is very peaceful.",
    "It is good to store lots of food before winter starts.",
    "The land is our home.",
    "When you are on the trail, conserve sweat not water. Drink your water; "
    "your body uses it efficiently and it's easier to carry that way.",
    "I caught a trout in a stream. His colors flashed in the sun. My brother "
    "spoke to me without words.",
    "Yesterday we rode our horses fast across the plains. Their hooves barely "
    "touched the ground. We became the wind.",
    "I enjoy the sound of fish jumping in calm shallows on a warm summer "
    "evening.",
    "When skinning an animal, be careful not to cut into the gut sack.",
    "Every animal has enough tannin in its brain to tan its own hide.",
    "River fish are best in the spring. In late summer they taste like mud.",
    "Be careful setting traps. They are dangerous.",
    "Nothing beats the thrill of skimming fast across smooth water in a "
    "sailboat.",
    "Seal blubber is oily enough to light on fire. It makes black sooty smoke "
    "that gets into everything but it will not harm you.",
    "Dead fall traps are easy to make and they can bring down large animals.",
    "Meat lasts longer in storage if it is salted and dried.",
    "Many things live by the sea, in and out of the water. It is the best "
    "place to find food all year around.",
    "Some rocks that fall from the sky are melted, but they will not melt or "
    "even glow in the hottest fire.",
    "Legends say there are beings who flit from place to place across the "
    "sky, in vehicles beyond our comprehension.",
    "I have seen lights moving across the night sky, in a different way than "
    "shooting stars or comets, as if they had a will of their own.",
    "Beware of plants with milky white sap. They are usually toxic.",
) + (GEO_PLACEHOLDER,) * 10

CHILD_LINES: Tuple[str, ...] = (
    "When you climb way up in the tall trees, the swaying of the trunk feels "
    "like you are flying.",
    "I can hold my breath for a long time. Do you think I can be a space man?",
    "Dad wants me to develop strict discipline and a high regard for sharing.",
    "When I picked my first berries and dug my first roots, they were given "
    "away to an elder. Mom said it was so I would learn to share my future "
    "successes.",
    "I like carrying water for the home. The elders always say the water "
    "tastes better, as if it held meat or berries.",
    "Everyone encourages me to not be lazy and to grow straight like a "
    "sapling.",
    "I am not supposed to speak to strangers.",
    "I want to be a space traveller some day.",
    "Some day I will be the elder of the village. Then I get to make the "
    "rules.",
    "I heard a scary story about a space monster once.",
    "It is safer near the village.",
    "If I had a space suit, I would be willing to travel.",
    "Mom is always worrying that I will get lost.",
    "Mom frets when we go swimming. How silly.",
    "Mom says not to swallow watermellon seeds or they will grow in my tummy.",
    "The fire is nice and warm but it can burn you.",
    "I sleep near the middle of the tent. That way the monsters cannot reach "
    "under the edge and grab me.",
    "Sometimes at night I stare up at the stars through the smoke hole in the "
    "tent.",
    "Do people really travel to other stars?",
)

ELDER_LINES: Tuple[str, ...] = (
    "The old Lakota was wise. He knew that man’s heart, away from nature, "
    "becomes hard; he knew that lack of respect for growing, living things "
    "soon led to a lack of respect for humans, too. So he kept his children "
    "close to nature’s softening influence.",
    "Inside us all, a battle rages between two wolves. One is evil and all "
    "things bad. The other is good and all things virtuous. The one that wins "
    "is the one you feed.",
    "Hold on to what is good, even if it is a handful of earth.",
    "Hold on to what you believe, even if it is a tree that stands by itself.",
    "Hold on to what you must do, even if it is a long way from here.",
    "Hold on to your life, even if it is easier to let go.",
    "Hold on to my hand, even if someday it is gone away from you.",
    "I salute the light within your eyes where the whole Universe dwells. For "
    "when you are at that center within you and I am at that place within me, "
    "we shall be one.",
    "You have to look deeper, way below the anger, the hurt, the hate, the "
    "jealosy, the self-pity, way down deeper where the dreams lie, son. Find "
    "your dream. It's the pursuit of the dream that heals you.",
    "I thank you, Wakantanka, for what you have given me.",
    "I am poor and naked, but I am the chief of the nation.",
    "We do not want riches but we do want to train our children right.",
    "Riches would do us no good. We could not take them with us to the other "
    "world.",
    "We do not want riches. We want peace and love.",
    "Hear me, my chiefs. I am tired. My heart is sick and sad. From where the "
    "sun now stands, I will fight no more forever.",
    "In our every deliberation, we must consider the impact of our decisions "
    "on the next seven generations.",
    "Children learn from what they see. We need to set an example of truth "
    "and action.",
    "When all the trees have been cut down, when all the animals have been "
    "hunted, when all the waters are polluted, when all the air is unsafe to "
    "breathe, only then will you discover you cannot eat money.",
    "Humankind has not woven the web of life. We are only one thread within "
    "it. Whatever we do to the web, we do to ourselves. All things are bound "
    "together. All things connect.",
    "When you know who you are; when your mission is clear and you burn with "
    "the inner fire of unbreakable will; no cold can touch your heart; no "
    "deluge can dampen your purpose. You know that you are alive.",
    "Eventually one gets to the Medicine Wheel to fulfill one's life.",
    "We live, we die, and like the grass and trees, renew ourselves from the "
    "soft earth of the grave. Stones crumble and decay, faiths grow old and "
    "they are forgotten, but new beliefs are born. The faith of the villages "
    "is dust now...but it will grow again...like the trees.",
    "The ground on which we stand is sacred ground. It is the dust and blood "
    "of our ancestors.",
    "Sometimes I go about pitying myself, and all the while I am being "
    "carried across the sky by beautiful clouds.",
    "A frog does not drink up the pond in which it lives.",
    "One does not sell the land people walk on.",
    "Between individuals, as between nations, peace means respect for the "
    "rights of others.",
    "When the white man discovered this country Indians were running it. No "
    "taxes no debt, women did all the work. White man thought he could "
    "improve on a system like this.",
    "Out of the Indian approach to life there came a great freedom, an "
    "intense and absorbing respect for life, enriching faith in a Supreme "
    "Power, and principles of truth, honesty, generosity, equity, and "
    "brotherhood as a guilde to mundane relations.",
    "Only to the white man was nature a wilderness and only to him was the "
    "land 'infested' with 'wild' animals and 'savage' people. To us it was "
    "tame, Earth was bountiful and we were surrounded with the blessings of "
    "the Great Mystery.",
    "Grown men can learn from the very little children for the hearts of the "
    "little children are pure. Therefore, the Great Spirit may show to them "
    "many things which older people miss.",
    "I am going to venture that the man who sat on the ground in his tipi "
    "meditating on life and its meaning, accepting the kinship of all "
    "creatures, and acknowledging unity with the universe of things was "
    "infusing into his being the true essence of civilization.",
    "It does not require many words to speak the truth.",
    "Is it wrong for me to love my own? Is it wicked for me because my skin "
    "is red? Because I am Sioux? Because I was born where my father lived? "
    "Because I would die for my people and my country? God made me an Indian.",
    "He who would do great things should not attempt them all alone.",
    "A very great vision is needed and the man who has it must follow it as "
    "the eagle seeks the deepest blue of the sky.",
    "I am a red man. If the Great Spirit had desired me to be a white man he "
    "would have made me so in the first place. He put in your heart certain "
    "wishes and plans, in my heart he put other and different desires. Each "
    "man is good in his sight. It is not necessary for Eagles to be Crows. We "
    "are poor...but we are free. No white man controls our footsteps. If we "
    "must die...we die defending our rights.",
    "When a white army battles Indians and wins, it is called a great "
    "victory, but if they lose it is called a massacre.",
    "Our land is more valuable than your money. It will last forever. It will "
    "not even perish by the flames of fire. As long as the sun shines and the "
    "waters flow, this land will be here to give life to men and animals.",
    "One thing to remember is to talk to the animals. If you do, they will "
    "talk back to you. But if you don't talk to the animals, they won't talk "
    "back to you, then you won't understand, and when you don't understand "
    "you will fear, and when you fear you will destroy the animals, and if "
    "you destroy the animals, you will destroy yourself.",
    "The strength of the fire, the taste of the salmon, the trail of the sun, "
    "and the life that never goes away, they speak to me. And my heart soars.",
)

DOCTOR_LINES: Tuple[str, ...] = (
    "I have studied the healing effects of many minerals and wild herbs.",
    "Do not put anything into your ear except your elbow.",
    "You are as healthy as a horse today.",
    "Eat an apple a day to keep me away.",
    "My nurse told me the man I just treated collapsed in the entrance to my "
    "tent. I told her to turn him around so it looks like he was just "
    "arriving.",
    "A mother complained that her daughter lies in bed all day and eats yeast "
    "and bees wax. I told her not to worry, the daughter would eventually "
    "rise and shine.",
    "I told a patient he had two weeks to live. He asked if he could have "
    "them in autumn.",
    "One out of four people is mentally unbalanced. Think of your 3 closest "
    "friends... If they seem okay, then you're the one.",
    "I became insane with long intervals of horrible sanity.",
    "Reality is the leading cause of stress amongst those in touch with it.",
    "Neurotics build castles in the air. Psychotics live in them. "
    "Psychiatrists are the people who collect the rent.",
    "Truly great madness cannot be achieved without significant intelligence.",
    "Most men are within a fingers breadth of going mad.",
    "The allergist voted to scratch it.",
    "The dermatologist prefers no rash moves.",
    "The psychiatrist thought it was madness.",
    "The radiologist could see right through it.",
    "The gastro enterologist had a gut feeling about it.",
    "The neurologist thought the administration had a lot of nerve.",
    "The obstetrician stated they were labouring under a misconception.",
    "The ophthalmologist considered the idea short sighted.",
    "The pathologist yelled, 'Over my dead body!'",
    "The paediatrician said, 'Grow up.'",
    "The plastic surgeon said, 'This puts a whole new face on the matter.'",
    "The podiatrist thought it was a step forward.",
    "The urologist felt the scheme wouldn't hold water.",
    "The surgeon decided to wash his hands of the whole thing.",
    "The anaesthesialogist thought the whole idea was a gas.",
    "The cardiologist didn't have the heart to say no.",
    "Damn! Page 47 of the manual is missing!",
    "Better save that. We will need it for the autopsy.",
    "Wait a minute, if this is his spleen, then what's that?",
    "...and could you stop that thing from beating; it's throwing my "
    "concentration off.",
    "Anyone see where I left that scalpel?",
    "Orthodox medicine has not found an answer to your complaint. However, "
    "luckily for you, I happen to be a quack.",
    "After a year in therapy my psychiatrist said to me, 'Maybe life isn't "
    "for everyone.'",
    "She got her looks from her father. He's a plastic surgeon.",
    "I'm not feeling very well, I need a doctor immediately. Ring the nearest "
    "golf course.",
    "The art of medicine is in amusing the patient while nature affects the "
    "cure.",
    "A woman went to a plastic surgeon and asked him to make her like a super "
    "model. He gave her a lobotomy.",
    "Whiskey is by far the most popular of all remedies that won't cure a "
    "cold.",
    "Anyone who goes to a psychiatrist should have his head examined.",
    "Never go to a doctor whose office plants have died.",
    "I'm always amazed to hear of crash victims so badly mutilated they have "
    "to be identified by their dental records. What I can't understand is, if "
    "they don't know who you are, how do they know who your dentist is?",
    "Do you know what you call a medical student who graduates at the bottom "
    "of their class? Doctor.",
    "When we remember that we are all mad, the mysteries disappear and life "
    "stands explained.",
    "Most people are born with genius, but most people only keep it a few "
    "minutes.",
    "When dealing with the insane, the best method is to pretend to be sane.",
    "To conquer others requires force; to conquer oneself requires "
    "enlightenment.",
)

LISTENER_PROMPTS: Tuple[str, ...] = (
    "What else is new?",
    "That is so interesting.",
    "You don't say.",
    "Hmm.",
    "Uh huh.",
    "Oh.",
    "Golly.",
    "Go on.",
    "Ooh.",
    "Gosh.",
    "Groovy.",
    "Cool.",
    "Awesome.",
    "Astounding.",
    "Excellent.",
    "I wondered.",
    "That's worth thinking about.",
    "It happens.",
    "It's been known to happen.",
    "Really?",
    "That is so profound.",
    "Pure wisdom.",
    "That sounds familiar.",
    "I heard that.",
    "Then what?",
    "Do you always feel this way?",
)

DOCTOR_HEAL_STEP = 4
DOCTOR_DYING = "Hold on to your life, even if it is easier to let go."
DOCTOR_PREGNANT = ("I see you are pregnant. Children are the jewels of your "
                   "crown when you grow old.")
DOCTOR_SEVERE = ("Your injuries are severe. These minerals and herbs will "
                 "relieve your suffering.")
DOCTOR_FIXED = ("This medicine will fix you up. It is made from local "
                "minerals and herbs.")
DOCTOR_HEALTHY = ("You look healthy to me. If you get hurt, I can heal your "
                  "wounds using local herbs and minerals.")

AILMENT_POISON, AILMENT_DISEASE, AILMENT_PARALYSIS = 1, 2, 3
AILMENT_PARASITE, AILMENT_ACID = 4, 5
AILMENT_LINES = {
    AILMENT_POISON: ("You are poisoned. These herbs will cure it.",
                     "You are poisoned. These herbs will help."),
    AILMENT_DISEASE: ("You have a disease. It could be contageous. Stay "
                      "comfortable and keep your health up.",) * 2,
    AILMENT_PARALYSIS: ("You have a paralysis of the muscles. It is not "
                        "serious. It will pass.",) * 2,
    AILMENT_PARASITE: ("A young %s lives inside your body. It will feed upon "
                       "you and grow. When it is ready, it will emerge. Keep "
                       "your health up; it will be painful.",) * 2,
    AILMENT_ACID: ("Acid is melting your flesh. This water will remove it. "
                   "Hold still.",
                   "Acid is melting your flesh. It looks bad; this water will "
                   "remove some of it."),
}

ROLE_LINES = {
    ROLE_ADULT: ADULT_LINES,
    ROLE_CHILD: CHILD_LINES,
    ROLE_ELDER: ELDER_LINES,
    ROLE_DOCTOR: DOCTOR_LINES,
}


_STATE: Dict[int, Dict[str, int]] = {}

_REPUTATION: Dict[Tuple[int, int], int] = {}

hp_provider: Optional[Callable] = None
bounty_provider: Optional[Callable] = None
msmr_provider: Optional[Callable] = None
ailment_provider: Optional[Callable] = None
heal_hook: Optional[Callable] = None


def reset_state(native_auid: Optional[int] = None) -> None:
    if native_auid is None:
        _STATE.clear()
        return
    _STATE.pop(int(native_auid) & 0xFFFFFFFF, None)


def _state(native_auid: int) -> Dict[str, int]:
    key = int(native_auid) & 0xFFFFFFFF
    st = _STATE.get(key)
    if st is None:
        st = {"interlocutor": 0, "counter": 0}
        _STATE[key] = st
    return st


def reputation(world_auid: int, player_auid: int) -> int:
    return int(_REPUTATION.get(
        (int(world_auid) & 0xFFFFFFFF, int(player_auid) & 0xFFFFFFFF), 0))


def has_contacted(world_auid: int, player_auid: int) -> bool:
    return ((int(world_auid) & 0xFFFFFFFF,
             int(player_auid) & 0xFFFFFFFF) in _REPUTATION)


def adjust_reputation(world_auid: int, player_auid: int, delta: int) -> int:
    key = (int(world_auid) & 0xFFFFFFFF, int(player_auid) & 0xFFFFFFFF)
    if key not in _REPUTATION:
        _REPUTATION[key] = int(delta)
    else:
        _REPUTATION[key] = max(-100, min(100, _REPUTATION[key] + int(delta)))
    return _REPUTATION[key]


def set_contacted(world_auid: int, player_auid: int, rep: int) -> None:
    key = (int(world_auid) & 0xFFFFFFFF, int(player_auid) & 0xFFFFFFFF)
    if key not in _REPUTATION:
        _REPUTATION[key] = int(rep)


def age_reputations(days: int) -> None:
    for key, val in list(_REPUTATION.items()):
        if val < 0:
            val += int(days)
            _REPUTATION[key] = 0 if val > 0 else val


def display_name(role: int, assigned_name: str) -> str:
    n = (assigned_name or "").strip()
    if not n:
        return "Indigenous"
    if int(role) == ROLE_ELDER:
        return "Elder %s" % n
    if int(role) == ROLE_DOCTOR:
        return "Healer %s" % n
    return n


def _qstr_be(text: str, limit: int = CHAT_TEXT_LIMIT) -> bytes:
    body = text[:limit].encode("utf-16-be")
    return struct.pack(">i", len(body)) + body


def _pkt(type_byte: int, tail: bytes, native_auid: int, native_name: str,
         target_auid: int) -> bytes:
    return build_chat_aucomm_v4(
        type_byte=int(type_byte),
        body_after_parent=tail,
        sender_auid_int=int(native_auid) & 0xFFFFFFFF,
        sender_name=native_name,
        target_auid_int=int(target_auid) & 0xFFFFFFFF,
        channel_index=VOICE_CHANNEL_INDEX,
        flags_byte=VOICE_FLAGS,
        range_byte=VOICE_RANGE_BYTE,
        scope=VOICE_SCOPE,
    )


def build_chat(text: str, native_auid: int, native_name: str,
               target_auid: int) -> bytes:
    if len(text) < CHAT_TEXT_LIMIT:
        return _pkt(AUCOMM_TYPE_CHAT, _qstr_be(text, CHAT_TEXT_LIMIT),
                    native_auid, native_name, target_auid)
    return _pkt(AUCOMM_TYPE_CHAT_CONTINUED,
                _qstr_be(text, CHAT_CONTINUED_LIMIT),
                native_auid, native_name, target_auid)


def build_choice(prompt: str, native_auid: int, native_name: str,
                 player_auid: int, choice_index: int = 0) -> bytes:
    tail = (bytes([int(choice_index) & 0xFF])
            + struct.pack(">i", CONVERSATION_STORY_INSTANCE)
            + _qstr_be(prompt, CHAT_TEXT_LIMIT)
            + struct.pack(">I", int(player_auid) & 0xFFFFFFFF))
    return _pkt(AUCOMM_TYPE_CHAT_CHOICE, tail,
                native_auid, native_name, player_auid)


def build_hail_reply(text: str, env_atom_auid: int, native_auid: int,
                     native_name: str, target_auid: int) -> bytes:
    tail = (struct.pack(">I", int(env_atom_auid) & 0xFFFFFFFF)
            + _qstr_be(text, CHAT_TEXT_LIMIT))
    return _pkt(AUCOMM_TYPE_HAIL_REPLY, tail,
                native_auid, native_name, target_auid)


def _dice(native_auid: int, counter: int) -> AuDice:
    return AuDice(((int(native_auid) * 0x9E3779B1)
                   ^ (int(counter) * 0x85EBCA6B)) & 0xFFFFFFFF)


def _roll_index(dice: AuDice, count: int) -> int:
    return int(dice.roll(1, int(count), -1))


def resolve_geo_line(_player_ll=None) -> str:
    return GEO_EMPTY_FALLBACK


def say_something(role: int, native_auid: int, native_name: str,
                  player_auid: int, counter: int) -> List[bytes]:
    lines = ROLE_LINES.get(int(role), ADULT_LINES)
    dice = _dice(native_auid, counter)
    line = lines[_roll_index(dice, len(lines))]
    if line == GEO_PLACEHOLDER:
        line = resolve_geo_line()
    if not line:
        return []
    prompt = LISTENER_PROMPTS[_roll_index(dice, len(LISTENER_PROMPTS))]
    return [
        build_chat(line, native_auid, native_name, player_auid),
        build_choice(prompt, native_auid, native_name, player_auid),
    ]


def _say_adult(native_auid: int, native_name: str, player_auid: int,
               counter: int) -> List[bytes]:
    if counter > 4:
        return [build_chat(ADULT_EXHAUSTED, native_auid, native_name,
                           player_auid)]
    return say_something(ROLE_ADULT, native_auid, native_name, player_auid,
                         counter)


def _say_child(native_auid: int, native_name: str, player_auid: int,
               counter: int) -> List[bytes]:
    if counter >= 9:
        return [build_chat(CHILD_TERMINAL_FINAL, native_auid, native_name,
                           player_auid)]
    if counter in CHILD_TERMINAL:
        return [build_chat(CHILD_TERMINAL[counter], native_auid, native_name,
                           player_auid)]
    return say_something(ROLE_CHILD, native_auid, native_name, player_auid,
                         counter)


def _say_elder(native_auid: int, native_name: str, player_auid: int,
               counter: int) -> List[bytes]:
    if counter < 2:
        return say_something(ROLE_ELDER, native_auid, native_name,
                             player_auid, counter)
    if counter == 2:
        out = [build_chat(ELDER_TIRED, native_auid, native_name, player_auid)]
        special = ""
        if special:
            out.append(build_chat(special, native_auid, native_name,
                                  player_auid))
        return out
    return [build_chat(ELDER_TIRED_FINAL, native_auid, native_name,
                       player_auid)]


def _say_doctor(native_auid: int, native_name: str, player_auid: int,
                counter: int) -> List[bytes]:
    out: List[bytes] = []

    def say(text: str) -> None:
        out.append(build_chat(text, native_auid, native_name, player_auid))

    hp = max_hp = None
    if hp_provider is not None:
        got = hp_provider(player_auid)
        if got:
            hp, max_hp = int(got[0]), int(got[1])

    if hp is not None and hp < 0:
        say(DOCTOR_DYING)
        return out

    if counter == 1 and _is_pregnant(player_auid):
        say(DOCTOR_PREGNANT)

    suppress = counter > 1
    seen = set()
    for kind, severe, name in _ailments(player_auid):
        cure, reduce_ = AILMENT_LINES.get(kind, ("", ""))
        if kind in (AILMENT_POISON, AILMENT_ACID):
            say(cure if not severe else reduce_)
            return out
        if suppress or kind in seen:
            continue
        seen.add(kind)
        if kind == AILMENT_PARASITE:
            say(cure % (name or "creature"))
        elif cure:
            say(cure)

    if hp is not None and max_hp is not None and hp < max_hp:
        if hp + DOCTOR_HEAL_STEP < max_hp:
            say(DOCTOR_SEVERE)
            new_hp = hp + DOCTOR_HEAL_STEP
        else:
            say(DOCTOR_FIXED)
            new_hp = max_hp
        if heal_hook is not None:
            heal_hook(player_auid, new_hp)
    else:
        say(DOCTOR_HEALTHY)

    out.extend(say_something(ROLE_DOCTOR, native_auid, native_name,
                             player_auid, counter))
    return out


def _is_pregnant(player_auid: int) -> bool:
    return False


def _ailments(player_auid: int):
    if ailment_provider is None:
        return ()
    return tuple(ailment_provider(player_auid) or ())


_SAY_BY_ROLE = {
    ROLE_ADULT: _say_adult,
    ROLE_CHILD: _say_child,
    ROLE_ELDER: _say_elder,
    ROLE_DOCTOR: _say_doctor,
}


def say(role: int, native_auid: int, native_name: str, player_auid: int,
        counter: int) -> List[bytes]:
    fn = _SAY_BY_ROLE.get(int(role), _say_adult)
    return fn(native_auid, native_name, player_auid, counter)


def terse_reply(role: int, player_name: str, rep: int,
                wrong_world: bool = False) -> Optional[str]:
    if wrong_world:
        return TERSE_HOMESICK
    rep = int(rep)
    if rep >= 0:
        return None
    band = 0 if rep < -9 else (1 if rep < -4 else 2)
    table = TERSE_BY_ROLE.get(int(role), TERSE_BY_ROLE[ROLE_ADULT])
    return table[band] % (player_name or "")


def greeting(role: int, player_name: str, bounty: float = 0.0,
             msmr: str = "") -> str:
    name = player_name or ""
    if int(role) == ROLE_ELDER:
        if float(bounty) > 0.0:
            return GREET_ELDER_BOUNTY % name
        return GREET_ELDER % name
    if int(role) == ROLE_CHILD:
        return GREET_CHILD % (msmr or "Mr", name)
    return GREET_DEFAULT % name


def _lookup_native(native_auid: int) -> Optional[dict]:
    from openshores.gameplay.natives import village as _nat
    return _nat._IDLE_BODIES.get(int(native_auid) & 0xFFFFFFFF)


def is_native(auid: int) -> bool:
    return _lookup_native(auid) is not None


def _assigned_name(body: dict) -> str:
    return str(body.get("name") or body.get("label") or "")


ADDRESS_RANGE_FT = 40.0


def pick_addressee(live_avatars: dict, player_auid: int) -> Optional[int]:
    from openshores.gameplay.natives import village as _nat
    entry = live_avatars.get(int(player_auid) & 0xFFFFFFFF) or {}
    pxyz = entry.get("xyz")
    if not pxyz:
        return None
    best = None
    best_d2 = float(ADDRESS_RANGE_FT) ** 2
    for auid, body in _nat._IDLE_BODIES.items():
        nxyz = body.get("xyz") or body.get("home")
        if not nxyz:
            continue
        d2 = sum((float(a) - float(b)) ** 2 for a, b in zip(pxyz, nxyz))
        if d2 <= best_d2:
            best_d2 = d2
            best = auid
    return best


def parse_hail_request(body: bytes) -> Optional[dict]:
    try:
        hdr, p = _parse_aucomm_header(body)
        empire_id = struct.unpack(">i", body[p:p + 4])[0]
        p += 4
        gb = body[p]
        p += 1
        text = ""
        if gb & 0x80:
            ln = struct.unpack(">i", body[p:p + 4])[0]
            p += 4
            if ln > 0:
                text = body[p:p + ln].decode("utf-16-be", errors="replace")
        hdr = dict(hdr)
        hdr.update(from_empire=empire_id, from_galaxy=gb & 0x7F, text=text)
        return hdr
    except Exception as exc:
        logger.warning(
            "Malformed AuCommHailRequest from a client; hail dropped: %r "
            "hex=%s", exc, body[:48].hex() if body else "")
        return None


def on_hail(player_auid: int, native_auid: int, player_name: str,
            env_atom_auid: int = 0) -> List[bytes]:
    body = _lookup_native(native_auid)
    if body is None:
        return []
    role = int(body.get("role", ROLE_ADULT))
    world_auid = int(body.get("world_auid", 0))
    name = display_name(role, _assigned_name(body))
    player_auid = int(player_auid) & 0xFFFFFFFF
    native_auid = int(native_auid) & 0xFFFFFFFF

    terse = terse_reply(role, player_name, reputation(world_auid, player_auid))
    if terse is not None:
        return [build_hail_reply(terse, env_atom_auid or world_auid,
                                 native_auid, name, player_auid)]

    st = _state(native_auid)
    out: List[bytes] = []
    if st["interlocutor"] != player_auid:
        st["interlocutor"] = player_auid
        st["counter"] = 0
        bounty = 0.0
        if bounty_provider is not None:
            bounty = float(bounty_provider(player_auid) or 0.0)
        msmr = ""
        if msmr_provider is not None:
            msmr = str(msmr_provider(player_auid) or "")
        out.append(build_hail_reply(
            greeting(role, player_name, bounty, msmr),
            env_atom_auid or world_auid, native_auid, name, player_auid))

    st["counter"] += 1
    out.extend(say(role, native_auid, name, player_auid, st["counter"]))
    return out


def on_conversation_choice(player_auid: int, native_auid: int,
                           choice: int) -> List[bytes]:
    body = _lookup_native(native_auid)
    if body is None:
        return []
    role = int(body.get("role", ROLE_ADULT))
    name = display_name(role, _assigned_name(body))
    player_auid = int(player_auid) & 0xFFFFFFFF
    native_auid = int(native_auid) & 0xFFFFFFFF

    if int(choice) != 0:
        return [build_chat(WHAT, native_auid, name, player_auid)]

    st = _state(native_auid)
    if st["interlocutor"] != player_auid:
        st["interlocutor"] = player_auid
    st["counter"] += 1
    return say(role, native_auid, name, player_auid, st["counter"])


def _selftest() -> int:
    fails = 0

    def check(cond, what):
        nonlocal fails
        if not cond:
            fails += 1
            logger.error("Fail: %s", what)

    check(len(ADULT_LINES) == 0x20, "ADULT_LINES == 32")
    check(len(CHILD_LINES) == 19, "CHILD_LINES == 19")
    check(len(ELDER_LINES) == 0x29, "ELDER_LINES == 41")
    check(len(DOCTOR_LINES) == 0x31, "DOCTOR_LINES == 49")
    check(len(LISTENER_PROMPTS) == 26, "LISTENER_PROMPTS == 26")
    check(ADULT_LINES.count(GEO_PLACEHOLDER) == 10, "10 'G' placeholders")

    check(ELDER_LINES[0].count("’") == 2, "elder line 1 keeps U+2019")
    check(ELDER_LINES[0].encode("utf-8").count(b"\xe2\x80\x99") == 2,
          "elder line 1 UTF-8 E2 80 99 x2")

    check("watermellon" in CHILD_LINES[14], "child 'watermellon'")
    check("anaesthesialogist" in DOCTOR_LINES[27], "doctor 'anaesthesialogist'")
    check("jealosy" in ELDER_LINES[8], "elder 'jealosy'")
    check("guilde" in ELDER_LINES[28], "elder 'guilde'")
    check("contageous" in AILMENT_LINES[AILMENT_DISEASE][0],
          "doctor 'contageous'")

    for role, tbl in ROLE_LINES.items():
        for c in range(1, 40):
            i = _roll_index(_dice(0x7B000000 + role, c), len(tbl))
            check(0 <= i < len(tbl), "role %d index %d in range" % (role, i))
            j = _roll_index(_dice(0x7B000000 + role, c),
                            len(LISTENER_PROMPTS))
            check(0 <= j < 26, "prompt index %d in range" % j)

    check(greeting(ROLE_ELDER, "Bob") == "Greetings avatar Bob.",
          "elder greeting")
    check(greeting(ROLE_ELDER, "Bob", bounty=5.0)
          == "Greetings avatar Bob. I hear there is a price on your head.",
          "elder bounty greeting")
    check(greeting(ROLE_DOCTOR, "Bob") == "Greetings Bob.",
          "doctor uses the default greeting")
    check(greeting(ROLE_ADULT, "Bob") == "Greetings Bob.", "adult greeting")
    check(greeting(ROLE_CHILD, "Bob", msmr="Mr") == "Hi Mr Bob.",
          "child greeting")

    check(display_name(ROLE_ELDER, "Kaya") == "Elder Kaya", "Elder decoration")
    check(display_name(ROLE_DOCTOR, "Kaya") == "Healer Kaya",
          "Healer decoration")
    check(display_name(ROLE_ADULT, "Kaya") == "Kaya", "adult undecorated")
    check(display_name(ROLE_ADULT, "") == "Indigenous", "empty -> Indigenous")

    check(terse_reply(ROLE_ADULT, "Bob", 0) is None, "rep 0 -> no terse reply")
    check(terse_reply(ROLE_ADULT, "Bob", -1) == "Stop it Bob. I will not "
          "speak to you.", "adult band 3")
    check(terse_reply(ROLE_ADULT, "Bob", -10) == "Die Bob.", "adult band 1")
    check(terse_reply(ROLE_CHILD, "Bob", -10).startswith("Aiee!"),
          "child band 1")
    check(terse_reply(ROLE_ELDER, "Bob", -10).startswith("You have deeply"),
          "elder band 1")
    check(terse_reply(ROLE_DOCTOR, "Bob", -10).startswith("You have cut"),
          "doctor band 1")
    check(terse_reply(ROLE_ADULT, "Bob", 0, wrong_world=True)
          == TERSE_HOMESICK, "wrong world -> homesick")
    check(terse_reply(ROLE_ADULT, "B", -9) == TERSE_BY_ROLE[ROLE_ADULT][1]
          % "B", "-9 is band 2")
    check(terse_reply(ROLE_ADULT, "B", -5) == TERSE_BY_ROLE[ROLE_ADULT][1]
          % "B", "-5 is band 2")
    check(terse_reply(ROLE_ADULT, "B", -4) == TERSE_BY_ROLE[ROLE_ADULT][2]
          % "B", "-4 is band 3")

    _REPUTATION.clear()
    check(adjust_reputation(1, 2, -200) == -200, "first insert unclamped")
    check(adjust_reputation(1, 2, -50) == -100, "update clamps to -100")
    age_reputations(30)
    check(reputation(1, 2) == -70, "negative rep decays toward zero")
    _REPUTATION.clear()
    set_contacted(1, 2, 10)
    set_contacted(1, 2, 1)
    check(reputation(1, 2) == 10, "SetContacted never overwrites")
    check(reputation(9, 9) == 0, "absent reputation is 0")
    _REPUTATION.clear()

    reset_state()
    e = _say_elder(0x7B000002, "Elder Kaya", 0x1234, 1)
    check(len(e) == 2, "elder exchange 1 = line + choice")
    e2 = _say_elder(0x7B000002, "Elder Kaya", 0x1234, 2)
    check(len(e2) == 1, "elder exchange 2 = tired line only, no choice")
    e3 = _say_elder(0x7B000002, "Elder Kaya", 0x1234, 3)
    check(len(e3) == 1, "elder exchange 3+ = final tired line")
    a = _say_adult(0x7B000000, "Nayat", 0x1234, 5)
    check(len(a) == 1, "adult past cap = brush-off only")
    check(len(_say_child(0x7B000001, "Tam", 0x1234, 6)) == 1, "child 6")
    check(len(_say_child(0x7B000001, "Tam", 0x1234, 99)) == 1, "child MOM!")
    check(len(_say_child(0x7B000001, "Tam", 0x1234, 3)) == 2, "child 3")
    d = _say_doctor(0x7B000003, "Healer Ana", 0x1234, 50)
    check(len(d) >= 2, "doctor has no exchange cap")

    from openshores.protocol.atoms.aucomm import \
        build_chat_aucomm_v4
    tail_probe = (bytes([0])
                  + struct.pack(">i", CONVERSATION_STORY_INSTANCE)
                  + _qstr_be("Go on.")
                  + struct.pack(">I", 0x1234))
    check(tail_probe[1:5] == b"\x00\x00\x00\x01",
          "choice tail storyId == 1 (live-conversation sentinel)")

    logger.info("native_conversation selftest: %s",
                "OK" if not fails else "%d FAILURE(S)" % fails)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_selftest())
