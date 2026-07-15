import pandas as pd
import numpy as np
import re
import logging
import janitor
from pathlib import Path
from typing import Union
from tabulate import tabulate
from rich.progress import Progress

from ...utils.misc import (
    styled_print, 
    get_files_in_folder, 
    visible_files_count,
    load_dataframe,
    get_base_name,
    has_mixed_case_no_whitespace,
)

from ...utils.constants import (
    FileMetadata,
    NCCIS,
    POST16_CATEGORIES,
)

from ...utils.logger_setup import (
    get_logger, 
    log_with_border, 
)

from .._utils import (
    prefix_columns,
)

from ._metadata_utils import (
    update_col_metadata_entry,
    extract_col_metadata,
    compare_and_backup, 
)

from ._naming_utils import (
    standardise_colnames,
    standardise_filenames,
)

logger = get_logger("data_processor")
# logger = logging.getLogger(__name__)  

#############################################
# Main Functions
#############################################

def standardise_fnames_colnames(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    file_metadata: pd.DataFrame,
    file_metadata_path: Union[str, Path],
    col_metadata_path: Union[str, Path],
    file_naming_format: list,
    standardise_rules: list[dict],
    valid_cat: list,
    add_prefix: bool = True,
    overwrite: bool = False
) -> None:
    """
    Standardises file names and column names based on standardise_colnames_rule in YAML file.

    Parameters
    ----------
    input_path : Union[str, Path]
        Path to the folder containing the original data files.
    
    output_path : Union[str, Path]
        Path to the folder where the standardised files will be saved.
    
    file_metadata : pd.DataFrame
        DataFrame containing metadata about each file, including details like original 
        and standardised file names, sheet names, and other metadata attributes.
    
    file_metadata_path : Union[str, Path]
        Path to a CSV or XLSX file containing file metadata. If provided, this file is 
        loaded into `file_metadata` for use within the function.
        
    col_metadata_path : Union[str, Path]
        Path to the output Excel file where column metadata, including both original 
        and standardised column names, will be saved or updated.
    
    file_naming_format : list
        The order of components in the filename. 
        Options: ["data_category", "cohort_y11_ay", "cohort_yg_ay", "year_group"].
        Default: ["cohort_y11_ay", "data_category" , "year_group"].
    
    standardise_rules : list[dict]
        List of rename actions applied in order.  
        Each item is one of:
        * **{"replace": <str>, "to": <str>}** - simple find-&-substitute.  
        * **{"add_underscore_before_caps": true}** - insert "_" before capital letters.  
        * **{"to_lower": true}** - convert to lower-case.

        Omit for no renaming (defaults to []).

    valid_cat : list
        A list of valid data categories to consider.
    
    add_prefix: bool, optional
        If True, adds the corresponding data category as a column prefix when standardising column names. 
        Default is True.

    overwrite : bool, optional
        If True, allows overwriting of existing files in `output_path`. If False, 
        skips files that already exist, preventing overwriting.
        Default is False.

    Returns
    -------
    None
    
    """

    # log_with_border(logger, "Standardising filenames and column names...")
    
    file_metadata_backup = file_metadata.copy()

    # Create the output directory if it does not exist
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Remove any files from file_metadata that are marked as EXCLUDE in the data category.
    excluded_files = file_metadata[
        file_metadata[FileMetadata.CATEGORY].str.contains(FileMetadata.EXCLUDE, na=False)
    ]
    file_metadata = file_metadata.drop(excluded_files.index)
    
    # Check for duplicates based on [CATEGORY, COHORT_Y11_AY, YEAR_GRP]
    dup_mask = file_metadata.duplicated(subset=[FileMetadata.CATEGORY, FileMetadata.COHORT_Y11_AY, FileMetadata.YEAR_GRP], keep=False)
    if dup_mask.any():
        # If duplicates found, print the duplicate rows using tabulate and raise an error
        logger.error(f"Duplicate entries found in file metadata based on [{FileMetadata.CATEGORY}, {FileMetadata.COHORT_Y11_AY}, {FileMetadata.YEAR_GRP}]:")
        duplicate_rows = file_metadata[dup_mask]
        print(tabulate(duplicate_rows, headers='keys', tablefmt='fancy_outline'))
        raise ValueError(
            f"Please make sure only one table is used per cohort per {'/'.join(valid_cat)}."
            f"Duplicate rows have been highlighted in red in the Excel file. Please resolve them before proceeding (e.g., change corresponding 'Category' as {FileMetadata.EXCLUDE})."
        )
    
    if overwrite or not len(file_metadata) == visible_files_count(output_path):

        # Add a column for standardised file names
        if FileMetadata.STD_FILE_NAME not in file_metadata.columns:
            file_metadata[FileMetadata.STD_FILE_NAME] = None
        
        # Determine the columns to select based on file_naming_format
        columns_to_select = [FileMetadata.CATEGORY, FileMetadata.COHORT_Y11_AY]
        
        if 'cohort_yg_ay' in file_naming_format:
            columns_to_select.append(FileMetadata.COHORT_YG_AY)
        if 'year_group' in file_naming_format:
            columns_to_select.append(FileMetadata.YEAR_GRP)
        
        # Mapping of file names and sheet names to their standardised names from the file metadata DataFrame
        file_name_mapping = (
            file_metadata
            .set_index([FileMetadata.FILE_NAME, FileMetadata.SHEET_NAME])[columns_to_select]
            .to_dict("index")
        )

        # store original and standardised column names
        col_meta = {}
 
        files = get_files_in_folder(folder_path=input_path, recursive=True)
        
        with Progress() as progress:
            task = progress.add_task(
                "[cyan bold]Standardising filenames and column names...[/]", 
                total=len(files)
            )
            
            for file_path in files:
                progress.update(task, description=f"[cyan bold]Processing: {file_path.name}[/]") 

                raw_filename = file_path.name

                data_sources = []

                if file_path.suffix == '.xlsx':
                    xls = pd.ExcelFile(file_path)
                    for sheet_name in xls.sheet_names:
                        data_sources.append((file_path, sheet_name))
                elif file_path.suffix == '.csv':
                    data_sources.append((file_path, None))
                else:
                    logger.warning(f"Unsupported file extension: {file_path.suffix}")
                    continue
                
                for file_path, sheet_name in data_sources:
                    if sheet_name is None:
                        key = (raw_filename, np.nan)
                    else:
                        key = (raw_filename, sheet_name)

                    if key in file_name_mapping:
                        data_category = file_name_mapping[key][FileMetadata.CATEGORY]
                        cohort_y11_ay = file_name_mapping[key][FileMetadata.COHORT_Y11_AY]
                        cohort_yg_ay = (
                            file_name_mapping[key][FileMetadata.COHORT_YG_AY] 
                            if "cohort_yg_ay" in file_naming_format else None
                        )
                        year_group = (
                            file_name_mapping[key][FileMetadata.YEAR_GRP] 
                            if "year_group" in file_naming_format else None
                        )

                        if (isinstance(data_category, str) and '~' in data_category):
                            continue  # Skip processing if the file is marked as not used for training

                        if not pd.isna(data_category) and not pd.isna(cohort_y11_ay):
                            std_filename = standardise_filenames(
                                file_naming_format=file_naming_format, 
                                data_category=data_category, 
                                cohort_y11_ay=cohort_y11_ay, 
                                cohort_yg_ay=cohort_yg_ay, 
                                year_group=year_group
                            )
                            output_file_path = output_path / f"{std_filename}"

                            # Update file_metadata with the standardised file name
                            if sheet_name is None:
                                condition = (
                                    (file_metadata[FileMetadata.FILE_NAME] == raw_filename) &
                                    (file_metadata[FileMetadata.SHEET_NAME].isna())
                                )
                            else:
                                condition = (
                                    (file_metadata[FileMetadata.FILE_NAME] == raw_filename) &
                                    (file_metadata[FileMetadata.SHEET_NAME] == sheet_name)
                                )
                            file_metadata.loc[condition, FileMetadata.STD_FILE_NAME] = std_filename

                            if output_file_path.exists() and overwrite is False:
                                continue  # Skip processing if the output file already exists

                            df_original = load_dataframe(
                                file_path, 
                                # low_memory=False, 
                                sheet_name=sheet_name, 
                                dtype_backend="pyarrow"
                            )
                            df = df_original.copy()
                            
                            # Now have a look at if exists duplicate column names
                            
                            # Extract base column names by removing suffixes like '.1', '.2', etc.
                            # duplicates can be found in base column names
                            base_column_names = [get_base_name(col) for col in df.columns]
                            df.columns = base_column_names # Temporarily set columns to base names for processing
                            
                            # Identify duplicated base column names
                            duplicated_columns = pd.Series(base_column_names).duplicated(keep=False)
                            duplicated_base_names = pd.Series(base_column_names)[duplicated_columns].unique()
                            
                            if len(duplicated_base_names) > 0: # Found duplicated column names
                                logger.info(
                                    f"Duplicate columns found in {raw_filename}"
                                    f"{' - ' + sheet_name if sheet_name else ''}: {duplicated_base_names}"
                                )
                                for base_name in duplicated_base_names:
                                    # Get the indices of columns with this base name
                                    col_indices = [i for i, x in enumerate(base_column_names) if x == base_name]
                                    
                                    # Compare the columns
                                    cols_to_keep = []
                                    for idx in col_indices:
                                        col_data = df.iloc[:, idx]
                                        if col_data.isna().all():
                                            # Column is empty
                                            logger.info(f"Dropping empty duplicate column '{df.columns[idx]}' at index {idx}")
                                            continue  # Skip adding this column to cols_to_keep
                                        else:
                                            cols_to_keep.append(idx)
                                    
                                    # If multiple non-empty columns with the same base name exist,
                                    # decide how to handle them. For now, we'll keep the first non-empty one.
                                    if len(cols_to_keep) > 1:
                                        logger.warning(
                                            f"Multiple non-empty columns with base name '{base_name}'. They are {"" if df.iloc[:, cols_to_keep].nunique(axis=1).max() == 1 else "NOT"} identical. Keeping the first one."
                                        )
                                        cols_to_keep = cols_to_keep[:1]
                                    elif len(cols_to_keep) == 0: # all column with duplicate names are empty
                                        logger.warning(f"No non-empty columns with base name '{base_name}' found.")
                                        cols_to_keep = col_indices[0] # keep one column name
                                    
                                    # Reconstruct df by dropping the columns we don't want to keep
                                    cols_to_drop = [idx for idx in col_indices if idx not in cols_to_keep]
                                    df = df.iloc[:, [i for i in range(df.shape[1]) if i not in cols_to_drop]]
                                    df_original_ = df_original.iloc[:, [i for i in range(df_original.shape[1]) if i not in cols_to_drop]]
                                    
                                    # Update base_column_names after dropping columns
                                    base_column_names = df.columns.tolist()
                            else:
                                pass
                                # logger.info("No duplicate columns found based on base names.")
                            
                            # Standarise column names
                            mixed_case_columns = [col for col in df.columns if has_mixed_case_no_whitespace(col)]
                            if mixed_case_columns:
                                replace_values = [rule['replace'] for rule in standardise_rules if 'replace' in rule]
                                
                                unmatched_columns = [col for col in mixed_case_columns if not any(replace_value in col for replace_value in replace_values)]

                                if unmatched_columns:
                                    logger.warning(
                                        f"Mixed case column names found in {raw_filename}:\n"
                                        f"{mixed_case_columns}\n"
                                        "Consider manually adding replacement rules for them."
                                    )                   
                            
                            raw_colnames = df.columns
                            
                            df.columns = standardise_colnames(df.columns, standardise_rules)
                            
                            if add_prefix:
                                prefix = (
                                    data_category
                                    if data_category not in POST16_CATEGORIES 
                                    else NCCIS.PREFIX
                                )
                                df = prefix_columns(df, prefix)
                            
                            # Compute unique values for each column (excluding NaN)
                            col_unique_values = {}
                            for col in df.columns:
                                unique_vals = df[col].dropna().unique().tolist()
                                col_unique_values[col] = set(unique_vals)

                            # Update column metadata col_meta
                            col_meta = update_col_metadata_entry(
                                data_category=data_category,
                                col_meta=col_meta,
                                raw_colnames=raw_colnames,
                                std_colnames=df.columns,
                                col_dtype=df.dtypes,
                                std_filename=std_filename,
                                raw_filename=raw_filename,
                                col_unique_values=col_unique_values
                            )
                            
                            # print(df.dropna(axis=1, how='all').columns)
                            # Validation: df_original and df should be equal after adjusting columns
                            # TODO: need a better approach
                            try:
                                # First test: Assert that df_original and df are equal after adjusting columns
                                pd.testing.assert_frame_equal(
                                    df_original.dropna(axis=1, how="all"),
                                     df.dropna(axis=1, how="all").set_axis(
                                         df_original.dropna(axis=1, how="all").columns, 
                                         axis=1,
                                     ),
                                    check_exact=True,
                                )
                            except (ValueError, AssertionError):
                                # Second test: Assert that df_original (after dropping columns seems duplicated) and df are equal after adjusting columns
                                pd.testing.assert_frame_equal(
                                    df_original_.dropna(axis=1, how="all"),
                                     df.dropna(axis=1, how="all").set_axis(
                                         df_original_.dropna(axis=1, how="all").columns, 
                                         axis=1,
                                     ),
                                    check_exact=True,
                                )
                                del df_original_
                            except AssertionError:
                                # Third test: Check if the DataFrame values (ignoring column names) are equal
                                if not df_original.dropna(axis=1, how='all').equals(df.dropna(axis=1, how='all')):
                                    raise AssertionError("DataFrames are not equal in values either.")
                            
                            # pd.testing.assert_frame_equal(
                            #     df_original, df.set_axis(df_original.columns, axis=1), check_exact=True)
                            
                            # Write to Excel
                            with pd.ExcelWriter(output_file_path, engine='openpyxl') as writer:
                                df.to_excel(writer, sheet_name=sheet_name or 'Sheet1', index=False)
                        else:
                            logger.warning(
                                f"The data category and cohort information of '{raw_filename}"
                                f"{' - ' + sheet_name if sheet_name else ''}' should not be None."
                            )
                    else:
                        if sheet_name is None:
                            logger.info(f"Skipping unlisted file: {raw_filename}")
                        else:
                            logger.warning(f"Skipping unlisted sheet: {raw_filename} - {sheet_name}")
                
                progress.advance(task)
            
            progress.update(
                task,
                description="[green bold]✔ All files processed![/]",
                completed=len(files),
                refresh=True
            )
        
        # save metadata for columns
        # Potential BUG: only valid if standarised files are not created.
        if col_meta:
            extract_col_metadata(col_meta, col_metadata_path)

        
        # Add excluded files back to file_metadata; otherwise, excluded files will be removed from file_metadata,
        # and if we rerun STEP 2, the uncurated file metadata entries will be added back in.
        if not excluded_files.empty:
            file_metadata = pd.concat([file_metadata, excluded_files], ignore_index=True)
            file_metadata = file_metadata.sort_values(
                by=[FileMetadata.CATEGORY, FileMetadata.COHORT_Y11_AY, FileMetadata.YEAR_GRP]
            ).reset_index(drop=True)
        
        
        # Compare the original and updated file_metadata
        compare_and_backup(
            new_data=file_metadata, 
            old_data=file_metadata_backup, 
            target_path=file_metadata_path,
            backup_prefix="preclean"
        )

    styled_print("File standardisation process completed.", colour='magenta')

    return None
