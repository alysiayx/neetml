import pandas as pd
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict, Optional, Set, Union

from ...utils.constants import (
    FileMetadata,
    ColumnMetadata,
)

from ...utils.misc import (
    styled_print, 
    stringify_unique_values,
)

from ...utils.logger_setup import (
    get_logger, 
    log_with_border, 
)


logger = get_logger("data_processor")
# logger = logging.getLogger(__name__)  


def auto_curate_cohort_metadata(
    year_group: int = None, 
    uncurated_cohort_yg_ay: str = None, 
    cohort_y11_ay: str = None
) -> Tuple[Optional[int], Optional[str]]:
    """
    Perform auto-curation logic to update the Year Group and Cohort fields
    based on the Y11 Cohort.

    Auto-curation logic: 
        If year_group == 11 and the uncurated cohort year_group do not match cohort_y11_ay:
            • Update the year_group based on the difference of start dates.
            • Update the cohort to reflect the corrected year_group.
        If year_group != 11:
            • Calculate the correct cohort start and end year_group based on cohort_y11_ay and update the cohort.

    Parameters
    ----------
    year_group : int or None
        The year group extracted from the sheet name.
        E.g., `9` for Year 9, or `None` if the sheet name does not specify a year group.

    uncurated_cohort_yg_ay : str or None
        The uncurated cohort metadata string indicating the year group and academic year 
        when the cohort entry into this year group.
        Format: `"Y{group} YYYY - YYYY"`. 
        E.g., `"Y7 2018 - 2019"` indicates students who were in Year 7 during the 2018-2019 academic year,
        or `None` if this information is unavailable.

    cohort_y11_ay : str or None
        The academic year in which the cohort reached Year 11.
        Format: `"YYYY - YYYY"`.
        E.g., `"2022 - 2023"` represents the academic year when this cohort reached Year 11,
        or `None` if this information is missing.

    Returns
    -------
    year_group : int or None
        The validated or updated year group after applying auto-curation logic.
        E.g., `9` for Year 9, `11` if inferred from cohort alignment logic, or `None` if not determined.

    cohort_yg_ay : str or None
        The curated cohort entry string indicating the correct year group and academic year 
        of cohort entry.
        E.g., `"Y7 2018 - 2019"` if retained, or recalculated from `cohort_Y]11_ay` and `year_group`.
    """

    cohort_yg_ay = None
    
    if pd.notna(cohort_y11_ay):
        try:
            cohort_y11_ay_start, cohort_y11_ay_end = map(int, re.split(r'\s*-\s*', cohort_y11_ay))
            # cohort_y11_ay_start, cohort_y11_ay_end = map(int, cohort_y11_ay.replace(' - ', '-').split('-'))

            # Handle the case when the year cohort is None
            if pd.isna(uncurated_cohort_yg_ay):
                if pd.notna(year_group):
                    cohort_start = cohort_y11_ay_start - (11 - year_group)
                    cohort_end = cohort_y11_ay_end - (11 - year_group)
                    cohort_yg_ay = f'Y{int(year_group)} {int(cohort_start)} - {int(cohort_end)}'
                else:
                    # If year_group is also None, cannot compute year cohort, leave it as None
                    cohort_yg_ay = None
            else:
                # Normal auto-curation logic if year cohort is provided
                uncurated_cohort_date = uncurated_cohort_yg_ay.split(' ', 1)[-1]
                uncurated_start_year, uncurated_end_year = map(int, re.split(r'\s*-\s*', uncurated_cohort_date))
                # uncurated_start_year, uncurated_end_year = map(int, uncurated_cohort_date.replace(' - ', '-').split('-'))

                if year_group == 11 and (uncurated_start_year != cohort_y11_ay_start):
                    year_group = 11 - (cohort_y11_ay_start - uncurated_start_year)
                    cohort_yg_ay = f'Y{int(year_group)} {int(uncurated_start_year)} - {int(uncurated_end_year)}'
                elif year_group != 11 and (uncurated_start_year == cohort_y11_ay_start):
                    cohort_start = cohort_y11_ay_start - (11 - year_group)
                    cohort_end = cohort_y11_ay_end - (11 - year_group)
                    cohort_yg_ay = f'Y{int(year_group)} {int(cohort_start)} - {int(cohort_end)}'
                else:
                    cohort_yg_ay = f'Y{int(year_group)} {int(uncurated_start_year)} - {int(uncurated_end_year)}'

        except ValueError:
            cohort_yg_ay = uncurated_cohort_yg_ay

        if pd.notna(year_group):
            year_group = int(year_group)
    
    return year_group, cohort_yg_ay

def create_file_metadata_entry(
    data_category=None,
    file_name=None,
    cohort_y11_ay=None,
    sheet_name=None,
    year_group=None,
    cohort_yg_ay=None,
    uncurated_year_group=None,
    uncurated_cohort_yg_ay=None,
    row_counts=None,
    needs_review=None
):
    return {
        FileMetadata.CATEGORY: data_category,
        FileMetadata.FILE_NAME: file_name,
        FileMetadata.SHEET_NAME: sheet_name,
        FileMetadata.COHORT_Y11_AY: cohort_y11_ay,
        FileMetadata.YEAR_GRP: year_group,
        FileMetadata.COHORT_YG_AY: cohort_yg_ay,
        FileMetadata.RAW_YEAR_GRP: uncurated_year_group,
        FileMetadata.RAW_COHORT_ENTRY: uncurated_cohort_yg_ay,
        FileMetadata.ROW_COUNT: row_counts,
        FileMetadata.NEEDS_REVIEW: needs_review
    }

def update_col_metadata_entry(
    data_category: str = None,
    col_meta: Dict[str, dict] = None,
    raw_colnames: List[str] = None,
    std_colnames: List[str] = None,
    col_dtype: pd.Series = None,
    std_filename: str = None,
    raw_filename: str = None,
    col_unique_values: Dict[str, Set] = None,
) -> Dict[str, dict]:
    """
    Updates the col_meta dictionary with metadata for each column, including original and standardised names, 
    data types, unique values, and associated filenames. Organises column metadata by data category.

    Parameters
    ----------
    data_category : str, optional
        The data category under which the column metadata is stored.
    
    col_meta : Dict[str, dict], optional
        A dictionary where metadata for column names is organised by data category. Each entry maps a 
        data category to its columns' metadata, including original names, data types, unique values, and filenames.
        Defaults to an empty dictionary if not provided.
    
    raw_colnames : List[str], optional
        The list of original column names as they appear in the raw data.
    
    std_colnames : List[str], optional
        The list of standardised column names.
    
    col_dtype : pd.Series, optional
        A pandas Series mapping each column name to its data type.
    
    std_filename : str, optional
        The standardised filename associated with the data.
    
    raw_filename : str, optional
        The original filename from which the data originated.

    col_unique_values : Dict[str, Set], optional
        A dictionary mapping column names to their unique values (excluding NaN).

    Returns
    -------
    Dict[str, dict]
        The updated col_meta dictionary with added metadata entries for each standardised column name.
    """

    if col_meta is None:
        col_meta = {}

    # Ensure the outer key (data_category) exists in col_meta
    if data_category not in col_meta:
        col_meta[data_category] = {}
    
    # Exit early if neither raw_colnames nor std_colnames is provided
    if raw_colnames is None and std_colnames is None:
        logger.warning("No column name provided.")
        return col_meta

    # Ensure both lists have values or placeholders
    raw_colnames = [None] * len(std_colnames) if raw_colnames is None else raw_colnames
    std_colnames = [None] * len(raw_colnames) if std_colnames is None else std_colnames

    # Store pairs of (raw_colnames, std_colnames) and track data types and unique values
    for raw_colname, std_colname in zip(raw_colnames, std_colnames):
        dtype = re.sub(r'\[.*\]', '', str(col_dtype[std_colname])) if col_dtype is not None else None

        unique_values = col_unique_values.get(std_colname, set()) if col_unique_values else set()

        # If the column doesn't exist, create a record for it
        if std_colname not in col_meta[data_category]:
            col_meta[data_category][std_colname] = {
                'raw_colname': raw_colname, # TODO: future improvement: each std_colname can only correspond to one raw_colname.
                'first_dtype': dtype,
                'all_dtypes': [dtype] if dtype else [],
                'unique_values': unique_values,
                'filename': [std_filename] if std_filename else [],
                'raw_filename': [raw_filename] if raw_filename else []
            }
        else:
            # Update the dtype list if this dtype hasn't been recorded yet
            if dtype and dtype not in col_meta[data_category][std_colname]['all_dtypes']:
                col_meta[data_category][std_colname]['all_dtypes'].append(dtype)
            
            if col_meta[data_category][std_colname]['first_dtype'] == 'null':
                col_meta[data_category][std_colname]['first_dtype'] = dtype
              
            # Merge unique values
            col_meta[data_category][std_colname]['unique_values'].update(unique_values)
            
            # Update filename and raw_filename lists if necessary
            if std_filename and std_filename not in col_meta[data_category][std_colname]['filename']:
                col_meta[data_category][std_colname]['filename'].append(std_filename)
            
            if raw_filename and raw_filename not in col_meta[data_category][std_colname]['raw_filename']:
                col_meta[data_category][std_colname]['raw_filename'].append(raw_filename)

        # Sort the filenames within each entry for consistency
        col_meta[data_category][std_colname]["filename"] = sorted(
            set(col_meta[data_category][std_colname]["filename"])
        )

        col_meta[data_category][std_colname]["raw_filename"] = sorted(
            set(col_meta[data_category][std_colname]["raw_filename"])
        )
            
    return col_meta                

def extract_col_metadata(
    col_meta: Dict[str, dict], 
    output_path: Union[str, Path],
) -> None:
    """
    Generates column metadata and saves it in an Excel file. 
    If the metadata file already exists, updates it with any new columns from col_meta 
    and creates a backup of the existing data to preserve previous metadata.

    Parameters
    ----------
    col_meta : Dict[str, dict]
        A dictionary containing metadata about columns, organised by data category. Each key 
        in the dictionary is a data category, and its corresponding value is another dictionary 
        with standardised column names as keys and metadata (original name, data types, filenames, etc.) as values.
    
    output_path : Union[str, Path]
        Path to the output Excel file where the column metadata will be saved. If the file 
        already exists, it will be updated with new data from col_meta, and a backup will be created.
    
    Returns
    -------
    None
        This function does not return a value. It writes or updates metadata in an Excel file 
        and saves a backup if updates are made.
    """
    
    if col_meta:
        # Check if the metadata file already exists
        if output_path.exists():
            # Load existing data from the Excel file
            existing_data = pd.read_excel(output_path, sheet_name=None)  # Read all sheets into a dictionary
        else:
            existing_data = {}
        
        mode = 'a' if Path(output_path).exists() else 'w'
        
        total_num_updates = 0
        with pd.ExcelWriter(
            output_path, 
            engine='openpyxl', 
            mode=mode, 
            if_sheet_exists='replace' if mode == 'a' else None
        ) as writer:
            # Iterate through each data category in col_meta
            for data_category, columns_dict in sorted(col_meta.items()):
                # Prepare data for the new DataFrame
                df_new = pd.DataFrame({
                    ColumnMetadata.STD_NAME: list(columns_dict.keys()),  # it should be standardised Column Name
                    ColumnMetadata.SRC_NAME: [v['raw_colname'] for v in columns_dict.values()],
                    ColumnMetadata.DATA_TYPE: [v['first_dtype'] for v in columns_dict.values()],
                    ColumnMetadata.DETECTED_DTYPES: [', '.join(v['all_dtypes']) for v in columns_dict.values()],
                    ColumnMetadata.UNIQUE_COUNT: [len(v['unique_values']) for v in columns_dict.values()],
                    ColumnMetadata.UNIQUE_VALUES: [stringify_unique_values(v['unique_values']) for v in columns_dict.values()],
                    ColumnMetadata.STD_FILE: [', '.join(v['filename']) for v in columns_dict.values()],  # Standardised Filenames
                    ColumnMetadata.SRC_FILE: [', '.join(v['raw_filename']) for v in columns_dict.values()]
                })

                # Check if this data_category already exists in the metadata file
                if data_category in existing_data:
                    df_existing = existing_data[data_category]
                    
                    if df_new[ColumnMetadata.SRC_NAME].isna().all(): # which means column names are standarised 
                        comparison_columns = [ColumnMetadata.STD_NAME]
                        df_new[ColumnMetadata.SRC_NAME] = df_new[ColumnMetadata.STD_NAME].map(
                            df_existing.set_index(ColumnMetadata.STD_NAME)[ColumnMetadata.SRC_NAME]
                        )
                    else:
                        # Compare keys will be both 'Column Name' and 'Source Column'
                        comparison_columns = [ColumnMetadata.STD_NAME, ColumnMetadata.SRC_NAME]
                    
                    if df_new[ColumnMetadata.SRC_FILE].replace('', float('NaN')).isna().all(): # which means filenames are standarised 
                        merged_df = df_new.merge(
                            df_existing[comparison_columns + [ColumnMetadata.SRC_FILE]],
                            on=comparison_columns,
                            how='left'
                        )
                        
                        df_new[ColumnMetadata.SRC_FILE] = merged_df[f'{ColumnMetadata.SRC_FILE}_y']

                    # Check if 'Source Column' and 'Column Name' columns are updated
                    df_existing_subset = df_existing[comparison_columns]
                    df_new_subset = df_new[comparison_columns]
                    
                    # Replace the sheet if 'Source Column' and 'Standardised Column Name' columns are updated
                    if not df_new_subset.equals(df_existing_subset):
                        # Need to update the file
                        total_num_updates += 1
                        df_metadata = df_new.copy()
                        logger.info(f"Updating sheet '{data_category}' in {output_path}")
                    else:
                        df_metadata = df_existing.copy()
                        logger.info(f"No updates found in sheet '{data_category}' in {output_path}")

                else:
                    # No existing data for this category; just write the new data
                    df_metadata = df_new.copy()
                    logger.info(f"Creating sheet '{data_category}' in {output_path}")

                # Ensure no duplicate entries for standardisation
                # assert df_metadata[ColumnMetadata.SRC_NAME].dropna().is_unique
                # assert df_metadata[ColumnMetadata.STD_NAME].dropna().is_unique
                if not df_metadata[ColumnMetadata.SRC_NAME].dropna().is_unique:
                    raise ValueError(f"Duplicate values found in {ColumnMetadata.SRC_NAME}. "
                                     "This indicates multiple standardised columns share the same source column.")

                if not df_metadata[ColumnMetadata.STD_NAME].dropna().is_unique:
                    raise ValueError(f"Duplicate values found in {ColumnMetadata.STD_NAME}. "
                                     "This indicates multiple standardised columns are using the same standardised name.")
                
                assert not df_metadata[ColumnMetadata.SRC_NAME].isna().all(), f"{ColumnMetadata.SRC_NAME} column is completely empty"
                assert not df_metadata[ColumnMetadata.STD_NAME].isna().all(), f"{ColumnMetadata.STD_NAME} column is completely empty"
                
                # Write the combined data to the Excel sheet
                df_metadata.to_excel(writer, sheet_name=data_category, index=False)
     
        # If updates were made, create a backup of the original file
        if total_num_updates > 0 and existing_data:
            create_backup(
                file_path=output_path,
                data=existing_data,
                prefix="pre_clean"
            )

        styled_print("Column metadata extraction process completed.", colour="magenta")
    
    return None

def save_excel(data: Union[pd.DataFrame, Dict[str, pd.DataFrame]], path: Path) -> None:
    """Save a DataFrame or dict of DataFrames to an Excel file."""
    path = Path(path)
    if isinstance(data, pd.DataFrame):
        data.to_excel(path, index=False)
    elif isinstance(data, dict):
        with pd.ExcelWriter(path, engine="openpyxl", mode="w") as writer:
            for sheet_name, df in data.items():
                df.to_excel(writer, sheet_name=sheet_name, index=False)
    else:
        raise TypeError("Data must be a DataFrame or a dict of DataFrames")

def create_backup(file_path: Path, data: Union[pd.DataFrame, Dict[str, pd.DataFrame]], prefix="backup") -> Path:
    """Create a timestamped backup of a DataFrame or dict of DataFrames."""
    # Filename suffix
    # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:20]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = file_path.with_name(
        f"{file_path.stem}_{prefix}_{timestamp}{file_path.suffix}"
    )
    
    save_excel(data, backup_path)
    logger.info(f"Old file backed up to {backup_path}")
    
    return backup_path

def compare_and_backup(
    new_data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
    old_data: Union[pd.DataFrame, Dict[str, pd.DataFrame]],
    target_path: str | Path,
    backup_prefix: str = "backup",
    save_new_data=True,
) -> bool:
    """
    Compare new and old data (DataFrame or dict of DataFrames). 
    If they differ:
      1. Create a timestamped backup of the old data.
      2. Save the new data to the target path.

    Parameters
    ----------
    new_data : DataFrame or dict[str, DataFrame]
        Updated content to save.
    old_data : DataFrame or dict[str, DataFrame]
        Previous content to compare against.
    target_path : str or Path
        Path where the new file should be saved.
    backup_prefix : str, default "backup"
        Prefix for the backup file name.
    save_new_data : bool, default True
        if True, save new data to xlsx file.

    Returns
    -------
    bool
        True if differences detected and backup+save performed, 
        False otherwise.
    """
    target_path = Path(target_path)

    def _data_equal(d1, d2) -> bool:
        if isinstance(d1, dict) and isinstance(d2, dict):
            # If the set of sheet names differ, there is a change
            if d1.keys() != d2.keys():
                return False
            
            # Compare sheet by sheet
            for sheet in d1:
                old_df = d1[sheet].copy().fillna("")
                new_df = d2[sheet].copy().fillna("")
        
                 # If the content differs, it's a change
                if not old_df.equals(new_df):
                    return False
                
                # If they have different shapes or columns, it's a change
                if old_df.shape != new_df.shape or list(old_df.columns) != list(new_df.columns):
                    return True

            return True
        
        elif isinstance(d1, pd.DataFrame) and isinstance(d2, pd.DataFrame):
            return d1.equals(d2)
        
        else:
            raise TypeError("Both inputs must be DataFrames or dict of DataFrames")

    if not _data_equal(new_data, old_data):
        # backup old data
        create_backup(target_path, old_data, prefix=backup_prefix)
        
        if save_new_data:
            # save new data
            save_excel(new_data, target_path)
            logger.info(f"Updated file saved to {target_path}")

        return True
    else:
        logger.info("No changes detected. File not updated.")
        return False
    
