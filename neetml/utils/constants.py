from pathlib import Path
from rich import print

from ..config import NEETMLConfig
from .misc import parse_yaml

# ----------------------------------------------------------------------
# Default Path
# ----------------------------------------------------------------------
# PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent # suppose download from github repo

_SETTINGS = NEETMLConfig.load()
PROJECT_ROOT = _SETTINGS.project_root

# PKG_ROOT = Path(__file__).resolve().parent.parent

PKG_ROOT = PROJECT_ROOT / 'neetml'  # package root (where the neetml package is located)

BASE_DATA_DIR = _SETTINGS.get_path("data_dir")

# Logs
LOGS_DIR = PROJECT_ROOT / "logs"

DATA_MANIFEST_PATH = PKG_ROOT / "configs" / "data_manifest.yaml"
MODEL_CONFIG_PATH = PKG_ROOT / "configs" / "model_config.yaml"

# Define structured data directories
SRC_DATA_DIR = _SETTINGS.get_path("raw_dir")
SRC_META_DIR = _SETTINGS.get_path("raw_meta_dir")
EXT_DATA_DIR = _SETTINGS.get_path("external_dir")
SRC_COLSTD_DIR = _SETTINGS.get_path("interim_dir")
PROC_DATA_DIR = _SETTINGS.get_path("processed_dir")

# Define specific file paths
FILE_METADATA_PATH = _SETTINGS.get_path("file_meta_path")
COL_METADATA_PATH = _SETTINGS.get_path("col_meta_path")

# Additional processing folders (inside `02. processed`)
CLEAN_DATA_DIR = _SETTINGS.get_path("cleaned_dir")
MERGE_DATA_DIR = _SETTINGS.get_path("merged_dir")
LINK_DATA_DIR = _SETTINGS.get_path("linked_dir")
DERIVE_DATA_DIR = _SETTINGS.get_path("derived_dir")
AGG_DATA_DIR = _SETTINGS.get_path("aggregated_dir")

# # Create these directories if they don't exist
# for path in [CLEANED_DATA_PATH, MERGED_DATA_PATH, AGGREGATED_DATA_PATH]:
#     path.mkdir(parents=True, exist_ok=True)

# Store as constants for easy imports
DATA_PATHS = {
    'BASE_DATA_DIR': BASE_DATA_DIR,
    'SRC_DATA_DIR': SRC_DATA_DIR,
    'SRC_META_DIR': SRC_META_DIR,
    'EXT_DATA_DIR': EXT_DATA_DIR,
    
    'FILE_METADATA_PATH': FILE_METADATA_PATH,
    'COL_METADATA_PATH': COL_METADATA_PATH,
    
    'SRC_COLSTD_DIR': SRC_COLSTD_DIR,
    
    'PROC_DATA_DIR': PROC_DATA_DIR,
    'CLEAN_DATA_DIR': CLEAN_DATA_DIR,
    'MERGE_DATA_DIR': MERGE_DATA_DIR,
    'LINK_DATA_DIR': LINK_DATA_DIR,
    'DERIVE_DATA_DIR': DERIVE_DATA_DIR,
    'AGG_DATA_DIR': AGG_DATA_DIR,
}


# ----------------------------------------------------------------------
# Compare-School-Performance Download Constants
# Used for fetching school performance data from the Compare School 
# and College Performance (CSCP) Service.
# ----------------------------------------------------------------------
# Base URL for the LA-level download page
CSP_BASE_URL = (
    "https://www.compare-school-performance.service.gov.uk/download-data"
)

# A realistic browser User-Agent header to avoid being blocked
CSP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/117.0.0.0 Safari/537.36"
    )
}

# The default list of datatypes we will request
# CSP_DEFAULT_DATA_TYPES = [
#     "gias", "ks2", "ks4", "ks4prov", "ks5",
#     "ks4destination", "ks5destination", "ks5destinationhe",
#     "pupilabsence", "Census"
# ]
CSP_DEFAULT_DATA_TYPES = [
    "gias", "spine", "ofsted",  # contains ofsted ratings
    "ks2", "ks4",  
    # "ks5", "ks4destination", "ks5destination",
    # "ks5mathsci",
    "pupilabsence", "Census"
]

# a default Local Authority and output directory
# CSP_DEFAULT_LA_CODE     = "380"        # e.g. Bradford
CSP_DEFAULT_FOLDER_NAME = "school_performance"
CSP_DEFAULT_OUT_DIR      = EXT_DATA_DIR

# Store as constants for easy imports
CSP_CONFIGS = {
    'BASE_URL': CSP_BASE_URL,
    'HEADERS': CSP_HEADERS,
    'DEFAULT_DATA_TYPES': CSP_DEFAULT_DATA_TYPES,
    # 'DEFAULT_LA_CODE': CSP_DEFAULT_LA_CODE,
    'DEFAULT_OUT_DIR': CSP_DEFAULT_OUT_DIR,
    'FOLDER_NAME': CSP_DEFAULT_FOLDER_NAME
}

# define key columns of school info datasets and their data types (for schema application during processing)
# Format:
# CSP_SCHEMA = {
#     raw_col: {
#         "name": readable_name,
#         "dtype": target_dtype,
#     }
# }

CSP_BASIC_SCHEMA = {
    "URN": {"name": "urn", "dtype": "string"},
    "ESTAB": {"name": "estab_no", "dtype": "string"},
    # "LA": {"name": "la", "dtype": "Int64"},
    "LA": {"name": "la", "dtype": "string"},
    "SCHNAME": {"name": "estab_name", "dtype": "string"},
    "POSTCODE": {"name": "postcode", "dtype": "string"},
    "GENDER": {"name": "gender_type", "dtype": "category"},
    "NFTYPE": {"name": "school_type", "dtype": "category"}, # the type of school/college/institution
    # "SCHOOLTYPE": {"name": "type", "dtype": "category"}, # from school information
    # "SCHOOLTYPE": {"name": "school_sector_group", "dtype": "category"}, # from school census
    
    # Gender
    "NOR": {"name": "total_pupils", "dtype": "Int64"},
    "PNORG": {"name": "girls_pct", "dtype": "Float64"}, # Percentage of girls on roll
    "PNORB": {"name": "boys_pct", "dtype": "Float64"}, 
    
    # SEN/SEND
    "PSENELSE": {"name": "sen_pct", "dtype": "Float64"}, # Percentage of pupils with SEN
    "PSENELK": {"name": "sen_eal_pct", "dtype": "Float64"}, # Percentage of pupils with English as an additional language pnumeal. 

    # FSM
    "PNUMFSMEVER": {"name": "fsm_ever_pct", "dtype": "Float64"},
    "PNUMFSM": {"name": "fsm_pct", "dtype": "Float64"},
    
    # EAL/first-language
    "PNUMEAL": {"name": "eal_pct", "dtype": "Float64"}, # Percentage of total pupil with English as an additional language
    # "PNUMENGFL": {"name": "eng_fl_pct", "dtype": "Float64"}, # Percentage of total pupil whose first language was English
    "PNUMUNCFL": {"name": "unc_fl_pct", "dtype": "Float64"}, # Percentage of total pupil whose first language was unclassified

    "PPERSABS10": {"name": "persist_abs_pct", "dtype": "Float64"}, # Percent of Pupils who are Persistently Absent (missing over 10% of sessions).
    "PERCTOT": {"name": "overall_abs_pct", "dtype": "Float64"},

    "OFSTEDRATING": {"name": "ofsted_rating", "dtype": "category"},
    "Overall effectiveness": {"name": "ofsted_rating", "dtype": "category"},
}

CSP_KS_SCHEMA = {
    # KS2
    "READ_AVERAGE": {"name": "read_avg", "dtype": "Float64"},
    "MAT_AVERAGE": {"name": "math_avg", "dtype": "Float64"},
    # "GPS_AVERAGE": {"name": "gps_avg", "dtype": "Float64"},
    "READPROG": {"name": "read_prog", "dtype": "Float64"},
    # "WRITPROG": {"name": "write_prog", "dtype": "Float64"},
    "MATPROG": {"name": "math_prog", "dtype": "Float64"},
    "PTFSM6CLA1A": {"name": "fsm6_pct", "dtype": "Float64"}, # Percentage of key stage 2 disadvantaged
    # "PTMOBN": {"name": "mobile_pct", "dtype": "Float64"}, # Percentage of non-mobile pupils?
    "PTKS1GROUP_L": {"name": "ks1_low_pct", "dtype": "Float64"}, # Percentage of pupils starting Key Stage 4 in low Key Stage 1 attainment group
    "PTRWM_EXP": {"name": "rwm_exp_pct", "dtype": "Float64"}, # Percentage of pupils achieving expected standard in reading, writing and maths at Key Stage 2
    
    # KS4
    "KS2APS": {"name": "ks2_aps", "dtype": "Float64"}, # Key Stage 2 Average Points Score of Key Stage 4 cohort
    "PTPRIORLO": {"name": "prior_low_pct", "dtype": "Float64"},  # Percentage of pupils starting Key Stage 4 in low prior attainment band
    # "PTPRIORAVG": {"name": "prior_avg_pct", "dtype": "Float64"},  # Percentage of pupils starting Key Stage 4 in middle prior attainment band
    "ATT8SCR": {"name": "att8_score", "dtype": "Float64"}, # Average attainment 8 for the school
    "P8MEA": {"name": "p8_mea", "dtype": "Float64"},  # Progress 8 measure after adjustment for extreme scores
    # "PTL2BASICS_95": {"name": "l2_basics_95_pct", "dtype": "Float64"},  # Percentage of pupils achieving strong passes (grades 9-5) in both English and mathematics GCSEs
    # "EBACCAPS": {"name": "ebacc_aps_pct", "dtype": "Float64"},  # EBacc Average Point Score
}

def add_name_prefix(schema, prefix):
    return {
        raw_col: {
            **spec,
            "name": f"{prefix}{spec['name']}"
        }
        for raw_col, spec in schema.items()
    }

CSP_SRC_MAPPING = {
    "england_spine": {**CSP_BASIC_SCHEMA},
    "england_school_information": {
        **CSP_BASIC_SCHEMA,
        "SCHOOLTYPE": {"name": "school_type", "dtype": "category"}, # from school information
    },
    "england_ofsted-schools": {**CSP_BASIC_SCHEMA},
    "england_census": {
        **CSP_BASIC_SCHEMA,
        "SCHOOLTYPE": {"name": "school_sector_group", "dtype": "category"}, # from school census
    },
    "england_abs": {**CSP_BASIC_SCHEMA},
    "england_ks2final": {**CSP_BASIC_SCHEMA, **add_name_prefix(CSP_KS_SCHEMA, "ks2_")},
    "england_ks2revised": {**CSP_BASIC_SCHEMA, **add_name_prefix(CSP_KS_SCHEMA, "ks2_")},
    "england_ks4final": {**CSP_BASIC_SCHEMA, **add_name_prefix(CSP_KS_SCHEMA, "ks4_")},
    "england_ks4revised": {**CSP_BASIC_SCHEMA, **add_name_prefix(CSP_KS_SCHEMA, "ks4_")},
}


# # ----------------------------------------------------------------------
# # Get-Information-about-School Download Constants
# # ----------------------------------------------------------------------
# # Base URL for the download page

# GIAS_BASE_URL = (
#     "https://get-information-schools.service.gov.uk/Downloads"
# )

# GIAS_DEFAULT_DATA_TYPES = [
    
# ]

# GIAS_DEFAULT_FOLDER_NAME = "school_information"
# GIAS_DEFAULT_OUT_DIR      = EXT_DATA_DIR / GIAS_DEFAULT_FOLDER_NAME

# # Store as constants for easy imports
# GIAS_CONFIGS = {
#     'BASE_URL': GIAS_BASE_URL,
#     'HEADERS': CSP_HEADERS,
#     'DEFAULT_DATA_TYPES': GIAS_DEFAULT_DATA_TYPES,
#     # 'DEFAULT_LA_CODE': GIAS_DEFAULT_LA_CODE,
#     'DEFAULT_OUT_DIR': GIAS_DEFAULT_OUT_DIR,
#     'FOLDER_NAME': GIAS_DEFAULT_FOLDER_NAME
# }



# ----------------------------------------------------------------------
# Meta Class
# ----------------------------------------------------------------------

class FrozenClassMeta(type):
    
    """Metaclass to prevent modification of class attributes."""
    def __setattr__(cls, key, value):
        raise AttributeError(f"Cannot modify immutable attribute '{key}' in {cls.__name__}")

# ----------------------------------------------------------------------
# External Reference Data
# ----------------------------------------------------------------------

IOD_CONFIGS = {
    2025: {
        "file": "File_7_IoD2025_All_Ranks_Scores_Deciles_Population_Denominators.csv",
        "oa_col": "LSOA code (2021)",
        "imd_decile_col": "Index of Multiple Deprivation (IMD) Decile (where 1 is most deprived 10% of LSOAs)"
    },
    2019: {
        "file": "File_7_-_All_IoD2019_Scores__Ranks__Deciles_and_Population_Denominators_3.csv",
        "oa_col": "LSOA code (2011)",
        "imd_decile_col": "Index of Multiple Deprivation (IMD) Decile (where 1 is most deprived 10% of LSOAs)"
    },
    2015: {
        "file": "File_7_ID_2015_All_ranks__deciles_and_scores_for_the_Indices_of_Deprivation__and_population_denominators.csv",
        "oa_col": "LSOA code (2011)",
        "imd_decile_col": "Index of Multiple Deprivation (IMD) Decile (where 1 is most deprived 10% of LSOAs)"
    }
}

class ExtRefs(metaclass=FrozenClassMeta):
    """
    Centralised registry for all external reference files used in the NEET project.
    This includes ONS Postcode Directory (ONSPD) lookups and all IoD/IMD datasets 
    across multiple years (2015, 2019, 2025).
    """

    # ------------------------------------------------------------------
    # ONSPD (ONS Postcode Directory)
    # Source:
    #   - https://geoportal.statistics.gov.uk/datasets/295e076b89b542e497e05632706ab429/about
    # ------------------------------------------------------------------
    ONSPD_VERSION = "AUG_2025"
    ONSPD_BD_FILE = f"ONSPD_{ONSPD_VERSION}_UK_BD.csv"
    ONSPD_LS_FILE = f"ONSPD_{ONSPD_VERSION}_UK_LS.csv"

    # Column names
    ONSPD_PCD_COL = "pcds"         # Postcode
    ONSPD_OA11_COL = "lsoa11cd"    # LSOA 2011 (official small area)
    ONSPD_OA21_COL = "lsoa21cd"    # LSOA 2021 (updated small area classification)

    # -------------------------------
    # IoD / IMD multi-version config
    # Source:
    #   - https://www.gov.uk/government/collections/english-indices-of-deprivation
    # -------------------------------
    IOD = IOD_CONFIGS  # attach dictionary

    # Tags
    IOD_SCORE_TAG = "Score"
    IOD_DECILE_TAG = "DECILE"
    IOD_EXCLUDE = {
        "IDACI",      # Income Deprivation Affecting Children Index
        "IDAOPI"      # Income Deprivation Affecting Older People Index
    }
    
    IMD_RENAME_MAP = {
        "Index of Multiple Deprivation (IMD) Score": "imd_score",
        "Index of Multiple Deprivation (IMD) Decile (where 1 is most deprived 10% of LSOAs)": "imd_decile",
        "Income Score (rate)": "income_rate",
        "Employment Score (rate)": "employment_rate",
        "Education, Skills and Training Score": "education_skills_score",
        "Health Deprivation and Disability Score": "health_disability_score",
        "Crime Score": "crime_score",
        "Barriers to Housing and Services Score": "housing_barriers_score",
        "Living Environment Score": "living_env_score",
        "Children and Young People Sub-domain Score": "children_young_people_sub_score",
        "Adult Skills Sub-domain Score": "adult_skills_sub_score",
        "Geographical Barriers Sub-domain Score": "geo_barriers_sub_score",
        "Wider Barriers Sub-domain Score": "wider_barriers_sub_score",
        "Indoors Sub-domain Score": "indoors_sub_score",
        "Outdoors Sub-domain Score": "outdoors_sub_score",
    }

    # -------------------------------
    # Accessor helpers for IoD/IMD config
    # -------------------------------
    @classmethod
    def iod_file(cls, year: int) -> str:
        return cls.IOD[year]["file"]

    @classmethod
    def iod_oa_col(cls, year: int) -> str:
        return cls.IOD[year]["oa_col"]

    @classmethod
    def imd_decile_col(cls, year: int) -> str:
        return cls.IOD[year]["imd_decile_col"]
    
    # -------------------------------
    # School information
    # -------------------------------
    SCHOOL_JOIN_KEYS = ("URN", "ESTAB") # used as key for merging, this should be the raw columns in the source files
    SCHOOL_SRC_MAPPING = CSP_SRC_MAPPING  # mapping of source files to their respective column schemas (for schema application during processing)
    SCHOOL_BASIC_SCHEMA = CSP_BASIC_SCHEMA # basic schema for school information datasets (e.g., spine, ofsted, census, abs)
    SCHOOL_YEAR_COL = "acad_end_year"
    SCHOOL_SAVE_NAME = "school_performance.parquet"
    

# ---------------------------------
# File Metadata
# ---------------------------------

class FileMetadata(metaclass=FrozenClassMeta):
    COHORT_YG_AY = "Year Group AY"                 # Cleaned "Y{n} YYYY - YYYY"
    YEAR_GRP = "Year Group"                        # E.g., 9, 10, 11
    CATEGORY = "Category"                          # Data category or type
    FILE_NAME = "File Name"                        # Original filename
    STD_FILE_NAME = "Standard File Name"           # Standardised filename (for logs etc.)
    NEEDS_REVIEW = "Needs Review"                  # Whether manual curation is required
    RAW_YEAR_GRP = "Raw Year Group"                # Uncleaned Year Group
    RAW_COHORT_ENTRY = "Raw Year Group AY"         # Uncleaned cohort info
    SHEET_NAME = "Sheet Name"                      # Sheet name from Excel file
    COHORT_Y11_AY = "Cohort Y11 AY"                # Academic year when cohort reached Y11
    ROW_COUNT = "Row Count"                        # Number of rows in the file
    EXCLUDE = "EXCLUDE"                            # Data category for excluded files; the value must match what is defined in the data mapping YAML.

# ---------------------------------
# Column Metadata
# ---------------------------------
class ColumnMetadata(metaclass=FrozenClassMeta):
    STD_NAME = "Column Name"  # Standardised column name
    SRC_NAME = "Source Column"  # Original column name before standardisation
    DATA_TYPE = "Data Type"  # Data type used when applying a schema
    CURATED_DTYPE = "Curated Data Type"
    RAW_DTYPE = "Uncurated Data Type"
    DETECTED_DTYPES = "Detected Data Types"  # All detected data types
    UNIQUE_COUNT = "Num Unique Values"  # Number of unique values in the column
    UNIQUE_VALUES = "Unique Values"  # Sampled unique values
    STD_FILE = "Filenames"  # Standardised file names where this column appears
    SRC_FILE = "Source Filenames"  # Original file names before standardisation
    DESCRIPTION = "Description"
    VALUES = "Values"

# ---------------------------------
# Metadata Columns (Generated during merge)
# ---------------------------------
class MergeMetadata(metaclass=FrozenClassMeta):
    """Defines metadata column names that are added during processing (e.g., merging, aggregation)."""

    COHORT_Y11_AY = "_cohort_y11_ay"  # Academic year when cohort reached Y11
    YEAR_GROUP = "_year_group"  # Academic year group
    ACAD_YEAR = "_acad_year"  # Academic year of the data (e.g., 2022-2023)
    RECORD_DATE = "_recorded_date" # Collect date of the dataset (set as acacdemic year when cohort reached Y11)
    PHASE = "_phase"  # Avaiable phase of the data (before spring of after spring)

# ---------------------------------
# Data Schema
# ---------------------------------    

class ColumnSchema(metaclass=FrozenClassMeta):
    # Manually curated data types for columns
    # The column names are not standardised 
    
    STRING_COLS = {'stud_id', 'school_leaving_year'}
    
    UNORDERED_CATEGORY_COLS = {
        'urn', 'estab_no.', 'establishment', 'estab', 'estab_id', 'school', 'gender',
        'ethnicity', 'language', 'sen_provision', 'sen_need1', 'sen_need2', 'sen',
        'exclusion_category', 'exclusion_reason_2', 'exclusion_reason_1', 'sen_exclusion',
        'exclusion_reason_1_desc', 'la', 'la_9code', 'laestab', 'toe_code', 'nftype',
        'urn_ac', 'amdpupil', 'sentype', 'ks1group', 'ealgrp', 'ks4_gender', 'ks4_la',
        'ks4_la_9code', 'ks4_estab', 'ks4_laestab', 'ks4_urn', 'ks4_urn_ac',
        'ks4_toe_code', 'ks4_nftype', 'ks4_new_type', 'ks4_newer_type', 'ks4_ncn',
        'ks4_amdflag', 'ks4_earlyt_e', 'ks4_norflage', 'ks4_priorband_ptq_ee',
        'ks4_ealgrp_ptq_ee', 'support_level', 'destination', 'school_code', 'prev_dest',
        'enrol_status', 'writtaoutcome', 'matspeccon', 'gpsspeccon', 'ward',
        'stat_school', 'nccis_code', 'sex_code', 'calculated_sex_code',
        'establishment_type', 'ks4_pdfecn',
        'nc_year_actual', 'readlevta', 'writlevta', 'readlev', 'englevta', 'mattier',
        'matlev', 'matlevta', 'scilevta', 'gpslev', 'readoutcome', 'matoutcome', 'gpsoutcome',
        'readspeccon', 'scitaoutcome', 'mattaoutcome', 'readtaoutcome',
        'ks1average_grp', 'ks1average_grp_p', 'ks4_apger_91', 'ks4_apdra_91', 'ks4_apmus_91', 
        'ks4_apmft_91', 'ks4_apita_91', 'ks4_apara_91', 'ks4_appan_91', 'exclusion_reason_3',
        'ethnic_origin'
    }

    ORDERED_CATEGORY_COLS = {
        'yeargrp', 'ncy', 'nc_year', 'nc_year_actual', 'acadyr', 'examyear_re',
        'examyear_gps', 'examyear_ma', 'ks4_yeargrp', 'ks4_priorband_ptq_ee',
        'ks4_ks2eng24p_ptq_ee', 'ks4_ks2mat24p_ptq_ee', 'ks4_examcat_ptq_ee',
        'ks4_hgmath_91', 'ks4_apelit_91', 'ks4_apfood_91', 'ks4_apart_91', 'ks4_aphis_91', 'ks4_apgeo_91', 'ks4_apfre_91',
        'ks4_apbus_91', 'ks4_aprs_91', 'ks4_appe_91', 'ks4_apphy_91', 'ks4_apche_91', 'ks4_apbio_91', 'ks4_apspan_91', 'ks4_apmat_91', 'ks4_apeng_91', 'ks4_apstat_91', 'ks4_apcombsci_91', 'ks4_apurd_91'
    }  # Not fully implemented for now

    DATETIME_COLS = {'date_of_birth', 'open_ac', 'start_date', 'neet_start_date', 'created',
                     'support_start_date', 'confirmed_date', 'review_date', 'predicted_end', 'due_lapse'}

    NUMERIC_COLS = {'readscore', 'readscore_nospeccon', 'matscore',
                    'matscore_nospeccon', 'gpsscore', 'gpsscore_nospeccon', 'ks4_appol_91'}

    FLOAT_COLS = {'coronavirus_(x)%', 'ks4_ebptsmat_ptq_ee',
                  'ks4_ebptslan_ptq_ee', 'ks4_ebac5', 'ks4_ebac6'}
    
    BOOLEAN_VALUES = {"0", "1", "true", "false", "yes", "no", "y", "n"}

# ---------------------------------
# Student ID Column
# ---------------------------------    

STUD_ID_COL = "stud_id"

# ---------------------------------
# Post-16 Destination Data
# ---------------------------------

class NCCIS(metaclass=FrozenClassMeta):
    # Core columns (unstandarised name)
    ACADEMIC_AGE = "academic_age"  
    CONFIRMED_DATE = "confirmed_date"
    CODE = "nccis_code"
    POSTCODE = "nccis_postcode"

    # Data categories defined in the data_config.yaml
    SEP_VER = "sepGuarantee"  # September Guarantee data category
    MAR_VER = "nccis"  # March NCCIS data category

    # Prefix used for data processing or standardization
    PREFIX = "nccis"

POST16_CATEGORIES = {
    NCCIS.SEP_VER, NCCIS.MAR_VER
}

# ---------------------------------
# Prediction Target Column
# ---------------------------------

# Prediction Target Column
TARGET_COL = NCCIS.CODE

# ---------------------------------
# Drop (Standarised) Columns
# ---------------------------------
# Identify columns that should be removed from the merged dataset 
# due to quality issues or redundancy.

DROP_COLS = {
    "census_estab", # Less accurate and prone to human errors compared to "attendance_school" (e.g., "Hazelbeck School" vs. "Hazelbeck Special School")
    # "ks4_idaci"
    "nccis_rec_no",
    "nccis_ethnic_origin", # use census_ethnicity instead
    "nccis_date_of_birth", # half of them are missing and seems not accurate as census data
    "nccis_gender", # seems not accurate as census data,
    "ks2_gender", # use census data instead, as some students have gender records that conflict with the census data.
    "ks4_gender", # use census data instead, as some students have gender records that conflict with the census data.
    "nccis_sex_code", # use census data instead, as some students have gender records that conflict with the census data.
    "nccis_calculated_sex_code", # use census data instead, as some students have gender records that conflict with the census data.
    "nccis_establishment_type", # only two people have this record
}

# ----------------------------------------------------------------------
# Possible (Unstandardised) School Columns (e.g., School/Establishment ID or Name)
# ----------------------------------------------------------------------
# Column names for schools may vary across different datasets.
# For example:
# - In attendance data, the column "estab" may represent the establishment number.
# - In census data, "estab" may instead refer to the establishment name.

SCHOOL_ID_COLS = {
    'urn', 'estab_no', 'estab', 'estab_id', 'laestab', 
    'school_code', 'stat_school', 'school', 'establishment',
    'urn_ac',
}

EXCLUDED_SCHOOL_TERMS = {
    'age'
}

# ----------------------------------------------------------------------
# Demographics (e.g., gender, ethnicity, birth year, language)
# These are personal, fixed, intrinsic attributes
# ----------------------------------------------------------------------

DEMOGR_COLS = {
    'gender', 'ethnic_origin', 'sex_code', 'calculated_sex_code',
    'date_of_birth', 'language', 'ethnicity', 
    
    # # derived columns
    # 'ethnic_main_group'
}

# ----------------------------------------------------------------------
# Deprivation (socioeconomic disadvantage, FSM, deprivation indices)
# These relate to family/household economic situation
# ----------------------------------------------------------------------

DEPRIVATION_COLS = {
    # from original data
    'fsm', 'fsm6', 'fsm6_p', 'fsme_on_census_day', 
    'idaci', 
    
    # from IMD
    'imd19', 'imd', 
    
    # from IoD
    "index_of_multiple_deprivation_imd_score",
    "education_skills_and_training_score",
    "health_deprivation_and_disability_score",
    "crime_score",
    "barriers_to_housing_and_services_score",
    "living_environment_score",
}

# ----------------------------------------------------------------------
# SEN / Support (special education needs or similar provision)
# These reflect education-specific needs
# ----------------------------------------------------------------------

SEN_SUPPORT_COLS = {
    'send', 'sen_provision', 'sen_need1', 'sen_need2',
    'sen_unit_indicator', 'resourced_provision_indicator',
    'ehcp', 'sen_support',  # includes education, health and care plan
}

# ----------------------------------------------------------------------
# Care / Vulnerable (looked after child, young parent, asylum seeker, etc)
# These relate to social care or vulnerability status
# ----------------------------------------------------------------------

CARE_VULNERABLE_COLS = {
    'looked_after_incare', 'care_leaver', 
    'refugee_asylum_seeker', 'caring_for_own_child', 
    'carer_not_own_child', 'substance_misuse', 
    'supervised_by_yots', 'pregnancy', 'parent', 
    'teenage_mother', 'alternative_provision',
}

# ----------------------------------------------------------------------
# Socioeconomic Background
# ----------------------------------------------------------------------

SOCIOECONOMIC_COLS = (
    DEPRIVATION_COLS 
    | SEN_SUPPORT_COLS 
    | CARE_VULNERABLE_COLS
)

# ----------------------------------------------------------------------
# Valid Data Categories
# ----------------------------------------------------------------------

DATA_MANIFEST = parse_yaml(DATA_MANIFEST_PATH)
DATA_CATEGORIES = [
    key for key in DATA_MANIFEST.keys()
    if not DATA_MANIFEST[key].get("is_meta", True) and key != FileMetadata.EXCLUDE
]

CATEGORY_PREFIX_MAP = {
    cfg.get("data_category", key): key  # category : prefix
    for key, cfg in DATA_MANIFEST.items()
    if not cfg.get("is_meta", True) and key != FileMetadata.EXCLUDE
}

# ----------------------------------------------------------------------
# Prefix of extended columns from public datasets
# ----------------------------------------------------------------------

EXT_COL_PREFIX = "ext"

# ----------------------------------------------------------------------
# Prefix of coluns derived from original columns
# ----------------------------------------------------------------------

DER_COL_PREFIX = "der"
