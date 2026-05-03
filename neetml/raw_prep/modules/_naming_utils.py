import pandas as pd
import re
import logging
import janitor

from ...utils.misc import (
    add_underscore_before_caps,
)

from ...utils.logger_setup import (
    get_logger, 
    log_with_border, 
)

logger = get_logger("data_processor")
# logger = logging.getLogger(__name__)  


def standardise_colnames(column_names, rules):
    # Apply replacement rules to column names
    for rule in rules:
        if 'replace' in rule and 'to' in rule:
            column_names = [col.replace(rule['replace'], rule['to']) for col in column_names]
            
        # # remove underscore around '%'
        # column_names = [col.replace('_%', '%').replace('%_', '%') for col in column_names]
        
        # # remove underscore around '*'
        # column_names = [col.replace('_*', '*').replace('*_', '*') for col in column_names]
        
        # column_names = [col.replace('[', '').replace(']', '') for col in column_names]
        
        if 'add_underscore_before_caps' in rule and rule['add_underscore_before_caps']:
            
            column_names = [add_underscore_before_caps(col) for col in column_names]
            
        if 'to_lower' in rule and rule['to_lower']:
            column_names = [col.lower() for col in column_names]
    
    # additional cleaning: convert to lowercase, replace spaces with underscores, and remove some special characters
    column_names = janitor.clean_names(
        pd.DataFrame(columns=column_names), 
        strip_underscores=True
    ).columns.tolist()
    
    return column_names

def standardise_filenames(
    file_naming_format: list,
    data_category: str, 
    cohort_y11_ay: str, 
    cohort_yg_ay: str = None, 
    year_group: str = None,
) -> str:
    """
    Standardise file name based on data category, Y11 cohort, and year cohort / year group.

    Parameters
    ----------
    file_naming_format : list
        The order of components in the filename. 
        Options: ["data_category", "cohort_y11_ay", "cohort_yg_ay", "year_group"].
    
    data_category : str
        The category of the data (e.g., attendance, nccis).
    
    cohort_y11_ay : str
        The Y11 cohort information (e.g., 2018-2019).
    
    cohort_yg_ay : str, optional
        The cohort year information (e.g., Y6 2015-2016).
    
    year_group : str, optional
        The year group information (e.g., Y6).
    
    Returns
    -------
    str
        The standardised file name.
    
    Raises
    ------
        ValueError
        If both cohort_yg_ay and year_group are provided, or if their values conflict.
    """
    
    # -----------------------
    # Validation steps:
    if "cohort_yg_ay" in file_naming_format and not cohort_yg_ay:
        raise ValueError(
            "file_naming_format specifies 'year cohort', but no year cohort value is provided."
        )

    if "year_group" in file_naming_format and not year_group:
        raise ValueError(
            "file_naming_format specifies 'year_group', but no year_group value is provided."
        )
    
    # -----------------------
    
    # Replace spaces with hyphens for all components
    components = {
        "data_category": data_category.replace(' ', '-'),
        "cohort_y11_ay": cohort_y11_ay.replace(' ', '-'),
        "cohort_yg_ay": cohort_yg_ay.replace(' ', '-').lower() if pd.notna(cohort_yg_ay) else None,
        "year_group": f"Y{int(year_group)}" if pd.notna(year_group) else None,
    }
    
    # Build the filename based on the naming format
    file_name = "_".join(
        components[key] for key in file_naming_format if components.get(key)
    )

    # Remove any multiple hyphens and append file extension
    file_name = re.sub(r'-+', '-', file_name) + ".xlsx"
    
    return file_name

