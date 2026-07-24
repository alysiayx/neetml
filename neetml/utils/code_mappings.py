# Dicts that match codes to the labels in data.

activity_codes = {
    210: "Full-time education - school sixth-form",
    220: "Full-time education - sixth-form college",
    230: "Full-time education - further education",
    240: "Full-time education - higher education",
    250: "Part-time education",
    260: "Gap year students",
    270: "Full-time education - other",
    280: "Special post-16 institution",
    290: "Full-time education :custodial institution (juvenile offender)",
    310: "Apprenticeship",
    320: "Full-time employment with study (regulated qualification)",
    330: "Employment without training",
    340: "Employment with training (other)",
    350: "Temporary employment",
    360: "Part-time employment",
    380: "Self-employment",
    381: "Self-employment with study (regulated qualification)",
    550: "Work not for reward with study (regulated qualification)",
    410: "ESFA funded work-based learning",
    430: "Other training",
    440: "DWP training and support programme",
    450: "Traineeship",
    460: "Supported Internship",
    530: "Re-engagement provision",
    540: "Working not for reward",
    610: "Not yet ready for work or learning",
    615: "Start date agreed (other)",
    616: "Start date agreed (RPA compliant)",
    619: "Seeking employment, education or training",
    620: "Not available to labour market/learning - carer",
    630: "Not available to labour market/learning - teenage parent",
    640: "Not available to labour market/learning - illness",
    650: "Not available to labour market/learning - pregnancy",
    660: "Not available to labour market/learning - religious grounds",
    670: "Not available to labour market/learning - unlikely ever to be economically active",
    680: "Not available to labour market/learning - other reason",
    710: "Custody (young adult offender)",
    810: "Current situation not known",
    820: "Cannot be contacted - no current address",
    830: "Refused to disclose activity",
}

activity_codes_higher_level = {
    210: "Education",
    220: "Education",
    230: "Education",
    240: "Education",
    250: "Education",
    260: "Education",
    270: "Education",
    280: "Education",
    290: "Education",
    310: "Employment",
    320: "Employment",
    330: "Employment",
    340: "Employment",
    350: "Employment",
    360: "Employment",
    380: "Employment",
    381: "Employment",
    550: "Employment",
    410: "Training",
    430: "Training",
    440: "Training",
    450: "Training",
    460: "Training",
    530: "Re-engagement activites",
    540: "NEET",
    610: "NEET",
    615: "NEET",
    616: "NEET",
    619: "NEET",
    620: "NEET",
    630: "NEET",
    640: "NEET",
    650: "NEET",
    660: "NEET",
    670: "NEET",
    680: "NEET",
    710: "Other",
    810: "Situation unknown",
    820: "Situation unknown",
    830: "Situation unknown",
}

ethnicity = {
    "WHI": "White British",
    "WHR": "Irish",
    "WHT": "Irish Traveller",
    "WHE": "Other European Origin",
    "WHO": "White - Other",
    "MXC": "White + Black Caribbean",
    "MXF": "White + Black African",
    "MXA": "White + Asian",
    "MXO": "Other Shared Heritage",
    "BLC": "Black - Caribbean",
    "BLA": "Black - African",
    "BLO": "Black - Other",
    "IND": "Indian",
    "PAK": "Pakistani",
    "BAN": "Bangladeshi",
    "ASI": "Other Asian Origin",
    "CHI": "Chinese",
    "AOG": "Any Other Ethnic Origin",
    "AOA": "Arab",
    "X11": "~Info Not Obtained",
    "X12": "~Info Not Given",
    "X13": "~Refused to Provide",
    "WHG": "Gypsy/Roma",
    "AOA": "Arab",
    "BBRI": "Black British",
}

ks4_priorband_ptq_ee = {
    1: "below expected standard",
    2: "at expected standard",
    3: "higher standard",
    4: "Not available"
}

binary = {"Y": "Yes", "N": "No"}

gender = {"M": "Male", "F": "Female"}

senprovision = {"N": "No special education need", "K": "SEN Support", "E": "EHC plan"}

sentypes = {
    "SPLD": "Specifc Learning Difficulty",
    "MLD": "Moderate Learning Difficulty",
    "SLD": "Severe Learning Difficulty",
    "PMLD": "Profound & Mutiple Learning Difficulty",
    "SLCN": "Speech Language and Communication Needs",
    "HI": "Hearing Impairment",
    "VI": "Visual Impairment",
    "MSI": "Multi-Sensory Impairment",
    "PD": "Physical Disability",
    "ASD": "Autistic Spectrum Disorder",
    "OTH": "Other Difficulty/Disability",
    "SEMH": "Social, emotional and mental health",
    "NSA": "SEN support but no specialist assessment of type of need",
}

level_of_need = {
    1: "Intensive Support",
    2: "Extra Support",
    3: "Minimum Support",
}

characteristics = {
    "nccis_refugee_asylum_seeker": "Refugee/Asylum seeker",
    "nccis_substance_misuse": "Substance misuse (client disclosed)",
    "nccis_teenage_mother": "Teenage mother",
    "nccis_pregnancy": "Pregnant",
    "nccis_parent": "Parent",
    "nccis_care_leaver": "Care Leaver",
    "nccis_caring_for_own_child": "Caring for own child",
    "nccis_supervised_by_yots": "Supervised by YOT",
    "nccis_carer_not_own_child": "Carer not own child",
    "nccis_alternative_provision": "Alternative Provision",
    "nccis_looked_after_in_care": "Looked after / In care",
}

# Reference: GIAP 2023 v0.7 Metadata.xlsx
ks_nftype_map = {
    20: "Academy - Sponsor Led",
    21: "Community School",
    22: "Voluntary Aided School",
    23: "Voluntary Controlled School",
    24: "Foundation School",
    25: "City Technology College",
    26: "Community Special School",
    27: "Foundation Special School",
    28: "Non-Maintained Special School",
    29: "Independent School approved to take pupils with Special Educational Needs",
    30: "Independent",
    31: "Further Education Sector Institution",
    32: "Community Hospital School",
    33: "Foundation Hospital School",
    34: "Pupil Referral Unit",
    35: "6th Form Centre/Consortium",
    36: "Institution funded by other Government department",
    37: "Federation",
    38: "Special Colleges",
    39: "Other Independent Special School",
    41: "European Schools",
    42: "Playing for Success Centres",
    43: "Offshore Schools",
    44: "Overseas Schools/Service Children's Education",
    45: "Higher Education Institutions",
    46: "Welsh Establishment",
    47: "LA Nursery School",
    48: "Independent Special School",
    50: "Academy - Special School",
    51: "Academy - Converter",
    52: "Free School - Mainstream",
    53: "Special Free School",
    54: "British Overseas School",
    55: "Converter Special Academy",
    56: "Free School - Alternative Provision",
    57: "Free School - UTC",
    58: "Free School - Studio School",
    59: "Free School - 16-19",
    60: "International School",
    61: "Academy Converter",
    62: "Academy - Sponsor Led AP",
    63: "Academy 16-19 Converter",
    64: "Academy 16-19 Sponsor Led",
    97: "Alternative Provision",
    98: "Legacy types/Miscellaneous",
    99: "Secure Unit",
}


# References:
# https://www.ons.gov.uk/peoplepopulationandcommunity/culturalidentity/ethnicity/bulletins/ethnicgroupenglandandwales/census2021
# https://www.ethnicity-facts-figures.service.gov.uk/style-guide/ethnic-groups/
# https://assets.publishing.service.gov.uk/media/65256511244f8e000d8e734e/Children_in_need_census_2024_to_2025_guide_V1.1.pdf
# https://www.gov.uk/guidance/alternative-provision-ap-census/codes

# didn't use it
# ethnicity_codes = {
#     'White': { # Main category
#         'WBRI': 'English, Welsh, Scottish, Northern Irish or British', # DfE Main code: categories
#         'WIRI': 'Irish',
#         'WIRT': 'Traveller of Irish heritage',
#         'WROM': 'Gypsy or Roma',
#         'WOTH': 'Any other White background',
#     },
#     'Mixed or multiple ethnic groups': {
#         'MWBC': 'White and Black Caribbean',
#         'MWBA': 'White and Black African',
#         'MWAS': 'White and Asian',
#         'MOTH': 'Any other Mixed or multiple ethnic background',
#     },
#     'Asian or Asian British': {
#         'AIND': 'Indian',
#         'APKN': 'Pakistani',
#         'ABAN': 'Bangladeshi',
#         'CHNE': 'Chinese',
#         'AOTH': 'Any other Asian background',
#     },
#     'Black, Black British, Caribbean or African': {
#         'BCRB': 'Caribbean',
#         'BAFR': 'African',
#         'BOTH': 'Any other Black, Black British, or Caribbean background',
#     },
#     'Other ethnic group': {
#         'OOTH': 'Any other ethnic group',
#         'ARAB': 'Arab',  
#         'REFU': 'Refused',
#         'NOBT': 'Information not yet obtained',
#     }
# }
