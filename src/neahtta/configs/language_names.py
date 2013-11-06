# -*- encoding: utf-8 -*-
"""This handles language name translation, and ISO transforms. When
adding new languages for dictionaries, their names will need to appear
here; and when adding new languages as internationalisation languages,
their names will need to be here too.

1. NAMES - Pairs of ISOs and language names marked for translation, such
   that a line appears in each *.po file, where the names will be
   translated

2. LOCALISATION_NAMES_BY_LANGUAGE - Pairs of ISOs and language names in
   the language itself. These names will be used in the localisations menu on the site.

3. ISO_TRANSFORMS - sometimes ISOs need to be transformed between
   2-character format and 3-character format, so if a language has a
   2-character version, we need the other as well.

"""

from flaskext.babel import lazy_gettext as _
NAMES = dict([
    # sanit
    ('sme', _(u"North Sámi")),
    ('se', _(u"North Sámi")),
    ('SoMe', _(u"North Sámi (#SoMe)")),
    ('en', _(u"English")),

    # baakoeh
    ('sma', _(u"South Sámi")),

    # kyv
    ('kpv', _(u"Komi")),

    # sanat
    ('fkv', _(u"Kven")),
    ('liv', _(u"Livonian")),
    ('olo', _(u"Olonetsian")),
    ('izh', _(u"Izhorian")),
    ('est', _(u"Estonian")),

    # valks
    ('myv', _(u"Erzya Mordvin")),
    ('mdf', _(u"Moksha")),
    ('fra', _(u"French")),

    # muter
    ('mrj', _(u"Western Mari")),
    ('mhr', _(u"Eastern Mari")),

    # vada
    ('yrk', _(u"Nenets")),

    # saan
    ('sms', _(u"Skolt Sámi")),

    # pikiskwewina
    ('crk', _(u"Plains Cree")),

    # guusaaw
    ('hdn', _(u"Northern Haida")),

    # target languages
    ('fin', _(u"Finnish")),
    ('nob', _(u"Norwegian")),

    ('ru', _(u"Russian")),
    ('rus', _(u"Russian")),

    ('fi', _(u"Finnish")),
    ('no', _(u"Norwegian")),
    ('nob', _(u"Norwegian")),
    ('lv', _(u"Latvian")),
    ('lav', _(u"Latvian")),
    ('eng', _(u"English")),
    ('hdn', _(u"Haida")),
    ('fra', _(u"French")),
])

LOCALISATION_NAMES_BY_LANGUAGE = dict([
    ('sme', u"Davvisámegiella"),
    ('se', u"Davvisámegiella"),
    ('sma', u"Åarjelsaemien gïele"),
    ('ru', u"Руский"),
    ('olo', u"Livvin kieli"),
    ('no', u"Norsk"),
    ('myv', u"Эрзянь кель"),
    ('mdf', u"Мокшень кяль"),
    ('mrj', u"Кырык мары йӹлмӹ"),
    ('yrk', u"Ненэць вада"),
    ('lv', u"Latviešu valoda"),
    ('lav', u"Latviešu valoda"),
    ('liv', u"Līvõ kēļ"),
    ('kpv', u"Коми кыв"),
    ('izh', u"Ižoran keel"),
    ('fkv', u"Kveenin kieli"),
    ('fi', u"Suomi"),
    ('eng', u"English"),
    ('est', u"Estonian"),
    ('sms', u"sääˊmǩiõll"),
    ('hdn', u"X̲aat Kíl"),
    ('en', u"English"),
    ('fr', u"Français"),
])

# Only put the exceptional ISOs here
ISO_TRANSFORMS = dict([
    ('se', 'sme'),
    ('no', 'nob'),
    ('fi', 'fin'),
    ('en', 'eng'),
    ('et', 'est'),
    ('lv', 'lav'),
    ('en', 'eng'),
    ('fr', 'fra'),
])
