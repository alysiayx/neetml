import pandas as pd
import janitor

from ..utils.constants import (
    DEMOGR_COLS,
    DEPRIVATION_COLS,
    SEN_SUPPORT_COLS,
    CARE_VULNERABLE_COLS,
    SOCIOECONOMIC_COLS,
    ExtRefs
)


def get_background_cols(df: pd.DataFrame) -> dict:
    """
    Extract background columns from the dataframe, grouped by:
    - demographics
    - deprivation
    - SEN/support
    - care/vulnerable
    
    Returns a dictionary with keys:
    'all', 'demographics', 'deprivation', 'sen_support', 'care_vulnerable'
    """
    
    demogr_cols = [
        col for col in df.columns 
        if col in DEMOGR_COLS or any(key in col for key in DEMOGR_COLS)
    ]
    
    deprivation_cols = [
        col for col in df.columns 
        if col in DEPRIVATION_COLS or any(key in col for key in DEPRIVATION_COLS)
    ]
    
    sen_support_cols = [
        col for col in df.columns 
        if col in SEN_SUPPORT_COLS or any(key in col for key in SEN_SUPPORT_COLS)
    ]
    
    care_vulnerable_cols = [
        col for col in df.columns 
        if col in CARE_VULNERABLE_COLS or any(key in col for key in CARE_VULNERABLE_COLS)
    ]
    
    socioeconomic_cols = [
        col for col in df.columns 
        if col in SOCIOECONOMIC_COLS or any(key in col for key in SOCIOECONOMIC_COLS)
    ]
    
    all_bg_cols = list(
        set(demogr_cols + deprivation_cols + sen_support_cols + care_vulnerable_cols)
    )
    
    return {
        "all": all_bg_cols,
        "demographics": demogr_cols,
        "deprivation": deprivation_cols,
        "sen_support": sen_support_cols,
        "care_vulnerable": care_vulnerable_cols,
        "socioeconomic": socioeconomic_cols
    }
   