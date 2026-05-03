import logging
import pandas as pd
import re
from pathlib import Path
from typing import Literal, Dict, Union
from rich.console import Console
from rich.progress import Progress
from rich.panel import Panel

from ...utils.misc import (
    styled_print, 
    load_dataframe, 
    print_table,
)

from ...utils.constants import (
    FileMetadata,
    MergeMetadata,
    POST16_CATEGORIES,
    NCCIS
)

from ...utils.logger_setup import (
    get_logger, 
    log_line_break,
    log_with_border
)
from .._utils import (
    resolve_column_name,
)

from ._merging_utils import (
    append_metadata_cols,
    apply_schema_to_dataframe,
    merge_files_for_cohort,
    validate_merged_data,
    group_dfs_by_colsim,
    get_merge_status,
    save_current_status,
    load_previous_status,
    diff_status,
    print_status_diff,
    merge_one_item_group
)


logger = get_logger("data_processor")
# logger = logging.getLogger(__name__)  

def merge_data(
    stud_id_col: str,
    nccis_append_start_yg: int,
    input_path: Union[str, Path],
    data_schema: Dict[str, pd.DataFrame],
    file_metadata: pd.DataFrame,
    output_path: Union[str, Path],
    valid_cat:list[str],
    group_by: Literal["cohort_yg_ay", "cohort_y11_ay"] = "cohort_yg_ay",
    group_sim_cutoff: float = 0.7,
    group_subset_cutoff: float = 0.5,
    grouping_strategy: Literal["flexible", "strict"] = "strict",
    save_tmp_outputs: bool = False,
    overwrite: bool = False,
) -> None:
    """
    Merge data by Cohort using 'stud_id' and if needed, one additional school-related column pair.
    
    The merging logic is as follows:
    1. Start with one dataset and iteratively merge others in the same Cohort.
    2. Attempt to merge on 'stud_id' alone. If that isn't sufficient, try predefined candidate pairs 
       of school-related columns to find a unique match key. Choose the key that yields the most matches.
    3. After merging, reorder columns and remove identical duplicate rows (based on all columns except 'stud_id').
    
    If group_by="cohort_yg_ay": (To be validated)
      1. Merge all files that do not have a Cohort (e.g. 'sepGuarantee').
      2. Merge all files by Cohort, then save each Cohort's result directly to output_path.
         (The parameter save_tmp_outputs is inconsequential here, unless
          you want to separate them into a subfolder. You can adjust as needed.)

    If group_by="cohort_y11_ay":
      1. Merge all files by Y11 Cohort.
         - If save_tmp_outputs=True:
             * Save each Cohort-level merged file to 'intermediate/' folder under output_path.
             * Optionally also keep them in memory (all_data). Or you can skip that.
         - If save_tmp_outputs=False:
             * Keep all merged results in memory only (all_data), do not write them.
      2. If we reach the Y11 Cohort merging step but all_data is empty:
         - Attempt to read all Cohort files from the 'intermediate/' folder. 
           (This implies we rely on the user having set save_tmp_outputs=True.)
      3. Merge across all Y11 Cohort-level data frames by Year Group, generating the final files.
  
    if group_by=False:
      Merge all files into one single file without grouping by Cohort or Y11 Cohort.

    Parameters
    ----------
    stud_id_col: str
        The column name for student ID in the data.

    nccis_append_start_yg : int
        The starting year group for appending NCCIS data.

    input_path : Union[str, Path], optional
        Path to the directory containing the cleaned data files.
      
    data_schema : Dict[str, pd.DataFrame]
        A mapping from Data Category names to their corresponding schema (as a DataFrame).
    
    file_metadata : pd.DataFrame
        A DataFrame containing metadata about the files to be merged, including:

    output_path : Union[str, Path]
        Path where the merged data will be saved.
        
    group_by : {"cohort_yg_ay", "year_group"}, default "cohort_yg_ay"
        - "cohort_yg_ay": stop after Cohort merges.
        - "year_group": merge by Cohort, then (optionally) load them from intermediate folder,
          merge by Year Group, and save final outputs.

    group_sim_cutoff : float, optional
        Minimum proportion of common columns to consider DataFrames as part of the same group (default is 0.7).
        Only validate if group_by="cohort_y11_ay".
    
    group_subset_cutoff : float, optional
        Minimum similarity required to merge groups where one DataFrame's columns are a strict subset of another (default is 0.5).
        Only validate if group_by="cohort_y11_ay".

    grouping_strategy : Literal["strict", "flexible", "balanced"], optional
        - "strict" (default): Groups only based on column similarity threshold.
        - "flexible": Merges groups if one DataFrame's columns are a strict subset of another.
        - "balanced": Merges groups if subset relation exists AND similarity is >= `subset_cutoff`.
        
    save_tmp_outputs : bool, default False
        If True and group_by="year_group", saves each Cohort's merged file into an 'intermediate' 
        subfolder under output_path. If later you need to load from disk (when in-memory data is empty),
        the code can retrieve them from that folder.

    valid_cat : list
        A list of valid data categories to consider. 
    
    overwrite : bool, default False
        Whether to overwrite existing merged files if they already exist.

    Raises
    ------
    ValueError
        - If no suitable school column pair is found for merging when 'stud_id' alone is insufficient.
        - If the merged dataset fails the post-merge validation against the original input datasets.
    """

    # log_with_border(logger, "Starting data merging process...")
    
    # ----------------------------------------------------------------------
    # Set paths
    # ----------------------------------------------------------------------
    
    # Create an "intermediate" folder if needed
    intermediate_folder = output_path / "intermediate"
    intermediate_folder.mkdir(parents=True, exist_ok=True)
    status_file = output_path / "merge_status.json"

    # ----------------------------------------------------------------------
    # Filter out EXCLUDE and empty categories
    # ----------------------------------------------------------------------
    file_metadata = file_metadata.dropna(subset=[FileMetadata.CATEGORY])
    file_metadata = file_metadata[~file_metadata[FileMetadata.CATEGORY].str.contains(FileMetadata.EXCLUDE, na=False)]
    
    # ----------------------------------------------------------------------
    # KS2 should be merged into corresponding Year 7-11 cohort data
    # ----------------------------------------------------------------------
    # extract KS2 files
    ks2_mask = file_metadata[FileMetadata.CATEGORY].str.contains('ks2', na=False)
    
    # Expand KS2 data to target Year Groups (7-11)
    target_year_groups = range(7, 12)  # Year 7 to Year 11

    ks2_expanded = [
        file_metadata.loc[ks2_mask].assign(
            **{
                FileMetadata.YEAR_GRP: int(year),
                FileMetadata.COHORT_YG_AY: file_metadata.loc[ks2_mask, FileMetadata.COHORT_YG_AY].str.replace(
                    r'Y(\d+)\s(\d{4})\s*-\s*(\d{4})',
                    lambda x: f"Y{year} {int(x.group(2)) + (year - 6)} - {int(x.group(3)) + (year - 6)}",
                    regex=True
                )
            }
        )
        for year in target_year_groups
    ]

    file_metadata = pd.concat([file_metadata.loc[~ks2_mask]] + ks2_expanded, ignore_index=True)
  
    file_metadata = file_metadata.sort_values(by=[FileMetadata.YEAR_GRP, FileMetadata.CATEGORY])
     
    # ----------------------------------------------------------------------
    # Merge All Sep Guarantee (NCCIS Sep) and NCCIS (NCCIS Mar) data
    # ----------------------------------------------------------------------
    for category, cat_info in file_metadata[
        file_metadata[FileMetadata.CATEGORY].isin(POST16_CATEGORIES)
    ].groupby(FileMetadata.CATEGORY, sort=True):
        recorded_date = cat_info[FileMetadata.COHORT_Y11_AY]
        
        # Check if recorded_date contains missing values
        if recorded_date.isna().any():
            raise ValueError(
                f"Missing 'Y11 Cohort'/recorded date for category '{category}'. "
                "If 'Year Cohort' is missing, 'Y11 Cohort'/recorded date must be provided."
            )
        
        # Extract years
        years = []
        for item in recorded_date:
            # Extract all numerical parts (i.e., year)
            year = re.findall(r'\d+', item)
            
            # Validate there is exactly one year
            if len(year) > 1:
                year = [y for y in year if len(y) == 4]
                if len(year) > 1:
                    raise ValueError(
                        f"Invalid date: '{item}'. Found multiple years: {year}. Supported formats are:\n"
                        "- Y11 cohort format (e.g., '2024 Mar') for data without an associated year group (e.g., 'nccis' or 'sepGuarantee').\n"
                        "- Year span format (e.g., '2018 - 2019') for data with year cohort."
                    )
            elif len(year) == 0:
                # No valid year found
                raise ValueError(
                    f"Invalid item: '{item}'. No valid year detected. Supported formats are:\n"
                    "- Y11 cohort format (e.g., '2024 Mar') for data without an associated year cohort (e.g., 'nccis' or 'sepGuarantee').\n"
                    "- Year span format (e.g., '2018 - 2019') for data with year cohort."
                )
            
            # Append the extracted year
            years.append(int(year[0]))
        
        if save_tmp_outputs:
            cat_output_path = intermediate_folder / f"{category}_{min(years)}-{max(years)}.xlsx"
        else:
            cat_output_path = output_path / f"{category}_{min(years)}-{max(years)}.xlsx"

        if not cat_output_path.exists() or overwrite:
            logger.info(f"Merge data without corresponding year cohort by category: {category}...")
            
            merged_df = None
            
            for _, row in cat_info.iterrows():
                file_name = row[FileMetadata.STD_FILE_NAME]
                file_path = input_path / file_name
                
                styled_print(f"Reading file: {file_name}", colour='light_magenta')
                # df = load_dataframe(file_path, dtype_backend='pyarrow')
                df = load_dataframe(file_path)
               
                styled_print(f"- This dataset has a size of {df.shape} and includes records for {df[stud_id_col].nunique()} students.")
                styled_print(f"- Number of students have multiple records: {df[stud_id_col].duplicated().sum()}.")
                
                df = df.replace(to_replace=r'&', value='and', regex=True)
               
                # Append metadata
                df = append_metadata_cols(
                    df=df,
                    **{
                        MergeMetadata.RECORD_DATE: row[FileMetadata.COHORT_Y11_AY],
                    }
                )

                if merged_df is None:
                    merged_df = df
                else:
                    merged_df = pd.concat([merged_df, df])
            
            sort_key = resolve_column_name(
                [stud_id_col, 'age', NCCIS.ACADEMIC_AGE],
                merged_df.columns,
                NCCIS.PREFIX
            )
            
            merged_df.sort_values(by=sort_key, inplace=True)
                                
            merged_df.drop_duplicates(inplace=True) # not necessary
            merged_df.dropna(axis=1, how="all", inplace=True) # not necessary
            merged_df = merged_df[sorted(merged_df.columns, key=lambda col: col.startswith('_'))]
         
            # Apply data schema if provided
            if data_schema:
                merged_df = apply_schema_to_dataframe(
                    df=merged_df, 
                    data_category=category, 
                    data_schema=data_schema,
                    # is_category_prefix=True,
                    # dtype_backend='pyarrow'
                )
            
            validate_merged_data(merged_df)

            styled_print(f"The size of merged data is {merged_df.shape}:")
            styled_print(f"- Number of students have multiple records: {merged_df[stud_id_col].duplicated().sum()}.")
            print_table(merged_df, group_records=False, num_cols='all')
            
            duplicates = merged_df[merged_df[stud_id_col].duplicated(keep=False)]
            if duplicates.shape[0] > 0:
                styled_print("- Following students have multiple records:")
                print_table(duplicates, group_records=False, num_cols='all')
            
            # merged_df.to_parquet(cat_output_path.with_suffix('.parquet'), engine='pyarrow', index=False)
            merged_df.to_parquet(cat_output_path.with_suffix('.parquet'), index=False)
            merged_df.to_excel(cat_output_path, index=False) # some missing value may be explicity save as string <NA>
 
            logger.info(
                f"Merged data has size {merged_df.shape} for {merged_df[stud_id_col].nunique()} students "
                f"and has been saved to {cat_output_path}"
            )
            
            log_line_break(logger)    
        else:
           logger.info(f"{category} data has been merged and saved...")     

    # ----------------------------------------------------------------------
    # Merge data by Year Cohort (exclude files where have no associate Cohort)
    # Example of Year Cohort is: Y8 2018 - 2019
    # ----------------------------------------------------------------------
    all_data = [] # store (cohort_y11_ay, year_group, merged_df)

    for cohort_yg_ay, cohort_info in file_metadata.groupby(FileMetadata.COHORT_YG_AY, sort=False):
        cohort_y11_ay = cohort_info[FileMetadata.COHORT_Y11_AY].unique()
        year_group = int(cohort_info[FileMetadata.YEAR_GRP].dropna().unique()[0])
        
        if len(cohort_y11_ay) > 1:
            print_table(cohort_info, group_records=False, num_cols='all')
            raise ValueError(f"This year cohort {cohort_yg_ay} should only have one associated Year 11 cohort but found multiple: {cohort_y11_ay}")

        cohort_y11_ay = cohort_y11_ay[0].replace(" ", "")
     
        cohort_output_path = intermediate_folder / f"{cohort_y11_ay}_Y{year_group}.xlsx" if save_tmp_outputs else output_path / f"{cohort_y11_ay}_Y{year_group}.xlsx"
        
        if not cohort_output_path.exists() or overwrite:
            logger.info(f"Merging files for Cohort: {cohort_yg_ay} (Associated Y11 Cohort: {cohort_y11_ay})")
            
            # Create a mapping of category -> first matching file
            nccis_file_map = {
                category: next(
                    (file for file in sorted(cohort_output_path.parent.iterdir()) 
                     if category in file.name and file.suffix == ".parquet"), 
                    next(
                        (file for file in sorted(cohort_output_path.parent.iterdir()) 
                         if category in file.name and file.suffix in {".xlsx", ".csv"}), 
                        None
                    )
                )
                for category in POST16_CATEGORIES
            }
                        
            merged_data_group = merge_files_for_cohort(
                cohort_yg_ay=cohort_yg_ay,
                cohort_info=cohort_info,
                input_path=input_path,
                data_schema=data_schema,
                stud_id_col=stud_id_col,
                # nccis_march_data=load_dataframe(nccis_file_map[NCCIS.MAR_VER], dtype_backend='pyarrow'),
                # nccis_sept_data=load_dataframe(nccis_file_map[NCCIS.SEP_VER], dtype_backend='pyarrow')
                nccis_march_data=load_dataframe(nccis_file_map[NCCIS.MAR_VER]),
                nccis_sept_data=load_dataframe(nccis_file_map[NCCIS.SEP_VER]),
                nccis_append_start_yg=nccis_append_start_yg,
            )
            
            for year_group, academic_age, merged_df in merged_data_group:
                styled_print(
                    f"The size of merged data for Year 11 Cohort {cohort_yg_ay} at Academic Age {academic_age} "
                    f"(Year Group {year_group}) is {merged_df.shape}:"
                )
                
                styled_print(f"- Number of students have multiple records: {merged_df[stud_id_col].duplicated().sum()}.")
                
                print_table(merged_df, group_records=False, num_cols='all', num_rows=20)
                duplicates = merged_df[merged_df[stud_id_col].duplicated(keep=False)]
                
                if duplicates.shape[0] > 0:
                    styled_print("- Following students have multiple records:")
                    print_table(duplicates, group_records=False, num_cols='all')

                if academic_age >= 16:
                    cohort_output_path = cohort_output_path.with_name(f"{cohort_y11_ay}_Y{year_group}.xlsx")
                
                validate_merged_data(merged_df)
                
                if group_by == "cohort_yg_ay" or save_tmp_outputs:
                    # merged_df.to_parquet(cohort_output_path.with_suffix('.parquet'), engine='pyarrow', index=False)
                    merged_df.to_parquet(cohort_output_path.with_suffix('.parquet'), index=False)
                    merged_df.to_excel(cohort_output_path, index=False)
                else:
                    all_data.append((cohort_y11_ay, year_group, merged_df))
                
                logger.info(
                    f"Merged data has size {merged_df.shape} for {merged_df[stud_id_col].nunique()} students in Cohort {cohort_yg_ay} "
                    f"and has been saved to {cohort_output_path}"
                )

                log_line_break(logger)

    current_status = get_merge_status(cohort_output_path.parent)
    if not status_file.exists():
        save_current_status(current_status, status_file)
            
    # ----------------------------------------------------------------------
    # Merge data
    # if group_by="cohort_y11_ay": by Y11 Cohort, split if columns differ significantly
    # else if group_by==False: merge all data into one file
    # ----------------------------------------------------------------------
    if save_tmp_outputs:
        current_status = get_merge_status(intermediate_folder)
    else:
        current_status = get_merge_status(output_path)
    
    previous_status = load_previous_status(status_file)
    
    diff = diff_status(previous_status, current_status, mtime_tol=1.0)
    
    output_parquet_files = list(output_path.glob("*.parquet"))
    output_exists = len(output_parquet_files) > 0
    
    if all(not v for v in diff.values()) and output_exists and not overwrite:
        logger.info("No changes detected and output files exist. Skipping merge process.")
        styled_print("Data merging process completed successfully.", colour='magenta')
        return
    else:
        logger.info("Changes detected or output files missing. Proceeding with merge process...")
        print_status_diff(diff)
    
    
    if not all_data and save_tmp_outputs:
        all_data = []
        
        logger.info(f"Read files from {intermediate_folder}.")
        
        excel_files = sorted(intermediate_folder.glob("*.xlsx"))
        parquet_files = sorted(intermediate_folder.glob("*.parquet"))
        
        # Define the expected filename pattern (YYYY-YYYY_YX)
        expected_pattern = re.compile(r"(\d{4}-\d{4})_Y(\d+)")
        
        # # Filter only files that match the pattern
        # excel_files = [file for file in excel_files if expected_pattern.search(file.name)]
        # parquet_files = [file for file in parquet_files if expected_pattern.search(file.name)]

        # Choose files based on availability
        data_files = parquet_files if parquet_files else excel_files
        file_type = "Parquet" if parquet_files else "Excel"

        with Progress() as progress:
            task = progress.add_task("[cyan]Reading files...", total=len(data_files))
            
            for file in data_files:
                fname = file.name
                progress.update(task, description=f"[cyan]Reading: {fname}")

                # Example filename: "2018-2019_Y7.xlsx"
                match = expected_pattern.match(fname)
                
                if not match:
                    logger.warning(f"Skipping file with unexpected format: {fname}")
                    continue  # Skip files that do not match the expected format

                if match:
                    cohort_y11_ay = match.group(1)  # Extracts "2018-2019"
                    yg = int(match.group(2))     # Extracts "7" (Year Group as integer)
                else:
                    raise ValueError(
                        f"Failed to extract Y11 Cohort and Year Group from the filename '{fname}'. "
                        f"Expected format: 'YYYY-YYYY_YX.xlsx' (e.g., '2018-2019_Y7.xlsx')."
                    )

                df_read = load_dataframe(
                    file, 
                    # dtype_backend='pyarrow', 
                    **(
                        {"dtype": str, "na_filter": False} 
                        if file_type == "Excel" else {}
                    )
                )
                
                all_data.append((cohort_y11_ay, yg, df_read))
                progress.update(task, advance=1)
        
            progress.update(task, description="[green bold]✔ All files processed![/]", completed=len(data_files), refresh=True)
    
    all_data.sort(
        key=lambda x: (int(x[0].split('-')[0]), x[1])  # Sort by (first year of Y11 Cohort, Year Group)
    )
    
    if group_by == "cohort_y11_ay":
        
        logger.info("Preparing to merge data by Y11 Cohort...")
        
        groups = group_dfs_by_colsim(
            df_list=all_data, 
            sim_cutoff=group_sim_cutoff, 
            subset_cutoff=group_subset_cutoff,
            grouping_strategy=grouping_strategy
        )

        for group_id, group_items in groups.items():
            cohorts = {cohort_y11_ay for cohort_y11_ay, _, _ in group_items}
            
            logger.info(f"Processing Group {group_id} with Cohorts: {', '.join(sorted(cohorts))}")
            
            for cohort_y11_ay, yg, df in group_items:
                merged_df = merge_one_item_group(
                    items=group_items,
                    stud_id_col=stud_id_col,
                    output_path=output_path,
                    data_schema=data_schema,
                    group_id=group_id,
                    valid_cat=valid_cat,
                    save_tmp_outputs=save_tmp_outputs,
                    save_colcov_dirname="intermediate_colcov",
                )
            
        
    elif group_by == False:
        logger.info("Merging all data into one file without grouping by Y11 Cohort...")
        
        merged_df = merge_one_item_group(
            items=all_data,
            stud_id_col=stud_id_col,
            output_path=output_path,
            data_schema=data_schema,
            valid_cat=valid_cat,
            save_tmp_outputs=save_tmp_outputs,
            save_colcov_dirname="intermediate_colcov",
        )
        
    else:
        raise ValueError(f"Unsupported group_by option: {group_by}. Supported options are 'cohort_y11_ay', 'cohort_yg_ay', and False.")
            

    
    current_status = get_merge_status(cohort_output_path.parent)
    save_current_status(current_status, status_file)       
    
    styled_print("Data merging process completed successfully.", colour='magenta')
    