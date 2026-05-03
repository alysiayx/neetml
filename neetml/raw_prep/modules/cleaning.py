import logging
import pandas as pd
from pathlib import Path
from typing import Union, List, Literal, Dict, Set
from rich.console import Console
from rich.progress import Progress
from rich.panel import Panel

from ...utils.misc import (
    styled_print, 
    load_dataframe, 
    get_files_in_folder, 
    check_folder_file_count_equal,
    print_table,
)

from ...utils.constants import (
    STUD_ID_COL,
    NCCIS
)

from ...utils.logger_setup import (
    get_logger, 
    log_with_border, 
    log_line_break
)

from ..modules._metadata_utils import (
    update_col_metadata_entry,
    extract_col_metadata,
)

logger = get_logger("data_processor")
# logger = logging.getLogger(__name__) 

def remove_data(
    df: pd.DataFrame,
    stud_id_col: str = STUD_ID_COL,
    rm_nan_stud_id: bool = True,
    rm_nan_cols_threshold: Union[Literal[False], float] = 0.5,
    rm_dups_threshold: Union[Literal[False],
                                       float, Literal['first']] = False,
    rm_empty_cols: bool = True,
    rm_constant_cols: Union[False, Literal['local'], List[str]] = False,
    rm_problematic_ids: Union[Literal[False], int, List[int]] = False,
    rm_sensitive_cols: Union[None, List[str]] = None,
) -> pd.DataFrame:
    # BUG: rm_dups_threshold: the current code only calculates the missing value proportion for the first duplicate entry and does not account for the missing value proportion for each row of duplicate data.
    """
    Clean the DataFrame by performing the following actions:
    - Optionally remove duplicate rows based on a specified threshold.
    - Optionally remove columns with all NaN values.
    - Optionally remove columns with only one unique value (constant columns).
    - Optionally remove rows with NaN 'stud_id' values.
    - Optionally remove columns with more than a specified percentage of NaN values.
    - Optionally remove rows with problematic student IDs.
    - Optionally remove columns with sensitive information.

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame to clean.
    
    stud_id_col : str, optional
        The column name of the student ID, by default 'stud_id'.
        
    rm_nan_stud_id : bool, optional
        Flag to indicate if rows with NaN 'stud_id' should be removed, by default True.
        
    rm_nan_cols_threshold : Union[Literal[False], float], optional
        Threshold for the percentage of NaN values in a column to decide its removal. 
        If False, no columns are removed based on NaN values.
        
    rm_dups_threshold : Union[Literal[False], float, Literal['first']], optional
        If a float, removes duplicates if the percentage of NaN values in one of the duplicate rows 
        exceeds this threshold. If 'first', keeps the first instance. If False, no duplicates are removed.
        
    rm_empty_cols : bool, optional
        Flag to indicate if columns with all NaN values should be removed, by default True.
    
    rm_constant_cols: Union[False, Literal['local'], List[str]], optional
        Specifies whether to remove columns with constant values:
        - False: Do not remove constant columns.
        - 'List[str]: A list of column names to be removed.
        - 'local': Remove columns that have a single constant value within each file individually.
        
    rm_problematic_ids : Union[Literal[False], int, List[int]], optional
        Problematic student IDs to be removed. Can be False, a single ID, or a list of IDs.
    
    rm_sensitive_cols : Union[None, List[str]], optional
        List of sensitive column names to be removed, by default None.
    
    Returns
    -------
    pd.DataFrame
        The cleaned DataFrame.
    
    pd.DataFrame
        The DataFrame containing the removed data.
    """

    console = Console()
    removed_data = pd.DataFrame()
    
    ################################################ 
    # Report and remove columns with all NaN values
    if rm_empty_cols:
        nan_columns = df.columns[df.isna().all()].tolist()
        if nan_columns:
            styled_print(f"- Columns with all NaN values found and removed:", console=console)
            print(nan_columns)
            df = df.dropna(axis=1, how='all')

    ################################################ 
    # Report and remove duplicate rows
    duplicates = df[df.duplicated(keep=False)]
    if not duplicates.empty:
        styled_print(f"- Duplicate rows detected:", console=console)
        print_table(duplicates, console)

        if rm_dups_threshold == 'first':
            # Keep the first instance
            duplicates_to_remove = df[df.duplicated(keep='first')]
            removed_data = pd.concat([removed_data, duplicates_to_remove])
            df = df.drop(duplicates_to_remove.index)
            styled_print("- Keeping only the first instance of each duplicate row", console=console)
        # elif isinstance(rm_dups_threshold, float):
        #     # Compute NaN percentage for each duplicate row
        #     nan_percentage = duplicates.isna().sum(axis=1) / len(duplicates.columns)
        #     # Rows to remove because NaN percentage exceeds threshold
        #     indices_to_remove = nan_percentage[nan_percentage > rm_dups_threshold].index
        #     if not indices_to_remove.empty:
        #         removed_data = pd.concat([removed_data, df.loc[indices_to_remove]])
        #         df = df.drop(indices_to_remove)
        #         styled_print(
        #             f"- Duplicate rows with NaN values exceeding {rm_dups_threshold*100}% removed.",
        #             console=console
        #         )
        #     else:
        #         duplicates_to_remove = df[df.duplicated(keep='first')]
        #         removed_data = pd.concat([removed_data, duplicates_to_remove])
        #         df = df.drop(duplicates_to_remove.index)
        #         styled_print("- NaN threshold not exceeded; keeping the first instance of each duplicate row.", console=console)
        else:
            logger.warning('Duplicate rows found but were not removed as no valid removal condition was provided.')
    
    ################################################ 
    # Report and remove rows with missing 'stud_id'
    if rm_nan_stud_id and stud_id_col in df.columns:
        nan_stud_id_rows = df[df[stud_id_col].isna()]
        if not nan_stud_id_rows.empty:
            styled_print(f"- Rows with missing {stud_id_col} values detected:", console=console)
            print_table(nan_stud_id_rows, console=console)
            removed_data = pd.concat([removed_data, nan_stud_id_rows])
            df = df.dropna(subset=[stud_id_col])
            styled_print(f"- Rows with missing {stud_id_col} values have been removed.", console=console)

    ################################################ 
    # Remove rows with problematic student IDs
    if rm_problematic_ids is not False:
        if isinstance(rm_problematic_ids, int):
            rm_problematic_ids = [rm_problematic_ids]
        problematic_rows = df[df[stud_id_col].isin(rm_problematic_ids)]
        if not problematic_rows.empty:
            removed_data = pd.concat([removed_data, problematic_rows])
            df = df[~df[stud_id_col].isin(rm_problematic_ids)]
            styled_print(f"- Problematic student IDs found and removed:", console=console)
            print_table(problematic_rows, console=console)

    ################################################ 
    # Remove sensitive columns if they are present
    if rm_sensitive_cols:
        columns_to_remove = [col for col in rm_sensitive_cols if col in df.columns]
        if columns_to_remove:
            df = df.drop(columns=columns_to_remove)
            # styled_print(f"- Removing sensitive columns: {', '.join(columns_to_remove)}", console=console)
            styled_print("- Removing sensitive columns: ", console=console)
            print(columns_to_remove)
    
    ################################################       
    # Remove constant columns
    if rm_constant_cols:
        if rm_constant_cols == 'local':
            # Remove columns with a single unique value within this DataFrame
            constant_columns_local = [col for col in df.columns if df[col].nunique(dropna=False) == 1]
            if constant_columns_local:
                df = df.drop(columns=constant_columns_local)
                styled_print("- Removing locally constant columns: ", console=console)
                print(constant_columns_local)
        elif isinstance(rm_constant_cols, list):
            # Remove columns specified in the list
            constant_columns_global = [col for col in rm_constant_cols if col in df.columns]
            if constant_columns_global:
                df = df.drop(columns=constant_columns_global)
                styled_print("- Removing 'global' constant columns: ", console=console)
                print(constant_columns_global)
        else:
            logger.warning(f"Invalid value for rm_constant_cols: {rm_constant_cols}")
    
    ################################################ 
    # Report and remove columns with more than the specified percentage of NaN values
    if isinstance(rm_nan_cols_threshold, float):
        columns_to_remove = df.columns[df.isna().mean() > rm_nan_cols_threshold].tolist()
        if columns_to_remove:
            styled_print(
                f"- Removing {len(columns_to_remove)} column(s) with more than {rm_nan_cols_threshold*100:.0f}% missing values:",
                console=console
            )
            df = df.drop(columns=columns_to_remove)
            # styled_print(f"  Columns removed: {', '.join(columns_to_remove)}", console=console)
            print(columns_to_remove)
    
    if rm_nan_cols_threshold:
        # Calculate missing value ratio for each column
        missing_ratios = df.isna().mean()

        # Filter columns with more than 80% missing values
        columns_to_remove = missing_ratios[missing_ratios > 0.8]

        if not columns_to_remove.empty:
            # Create a DataFrame for better presentation
            missing_df = pd.DataFrame({
                'Column': columns_to_remove.index,
                'Missing Ratio (%)': (columns_to_remove.values * 100).round(2)
            }).sort_values(by='Missing Ratio (%)', ascending=False)
            
            logger.warning(
                f"{len(columns_to_remove)} column(s) have more than 80% missing values, consider removing them:"
            )

            styled_print("Columns with more than 80% missing values:")
            print_table(missing_df, group_records=False, num_cols='all', num_rows='all', console=console)
    
    ################################################ 
    # Find rows where 'stud_id' has duplicates
    duplicated_stud_id = df[df.duplicated(subset=[stud_id_col], keep=False)].sort_values(by=stud_id_col)
    num_dup_stud = len(df[df.duplicated(subset=[stud_id_col], keep='first')])
    if num_dup_stud > 0:
        logger.warning(f"Number of students have multiple records: {num_dup_stud}")
        styled_print(f"- Duplicate student IDs found. Consider merging them in the following process:", console=console)
        print_table(duplicated_stud_id, console=console)
    
    return df, removed_data

def identify_globally_constant_columns(
    data_dir: Union[str, Path],
    consistency_cutoff: float = 0.8,
    missing_cutoff: float = 0.8,
    consider_missing: bool = True
) -> List[str]:
    """
   Identify columns that are "globally constant" based on whether they have 
    a single "top constant value" in at least `consistency_cutoff` fraction 
    of all files where they appear. Additionally, if a variable's overall global
    value distribution is dominated by missing values (i.e., the proportion of 
    missing values is equal to or exceeds `missing_cutoff`), the variable is excluded,
    if missing filtering is enabled.

    For each file:
    - If the column is constant (only one unique value), we record that value.
    - Otherwise, we record a special marker "NonConstant".
    
    After processing all files, we calculate the distribution of these 
    constant values (plus the "NonConstant" marker). The top constant value
    (the most frequent non-"NonConstant" value) is checked to see if it
    occurs in at least `consistency_cutoff` fraction of files. If it does, 
    the column is flagged as a globally constant column.

    Parameters
    ----------
    data_dir : Union[str, Path]
        Directory containing all data files.
    
    consistency_cutoff : float, optional
        The minimum fraction of all files in which one value must be the 
        column's sole occupant (i.e., a constant) for that column to be 
        considered globally constant. For example, a value of 0.8 (the default) 
        means at least 80% of files must have this column as a single 
        consistent value.
    
    missing_cutoff : float, optional
        The maximum allowed fraction of missing values in the global distribution 
        of a variable. If the proportion of "Missing" values is equal to or greater 
        than this cutoff and missing filtering is enabled, the variable is excluded.
        
    consider_missing : bool, optional
        If True (default), apply missing filtering based on `missing_cutoff`.
        If False, do not filter out variables based on missing values.
        Note: This setting does not apply to NCCIS and suspPermExcl data.


    Returns
    -------
    constant_columns : List[str]
        List of column names that are constant in all files where they appear 
        and have the same unique non-NaN value, with top constant value proportion 
        exceeding the threshold.
    """

    NON_CONSTANT_MARKER = "NonConstant"

    files = get_files_in_folder(folder_path=data_dir, recursive=True)
    
    variable_stats: Dict[str, Dict[str, Union[int, Set, List]]] = {}
    
    def calculate_distribution(values: List) -> pd.Series:
        """Return a normalised distribution series of the values."""
        counts = pd.Series(values).value_counts(normalize=True)
        return counts

    def format_distribution(counts: pd.Series) -> str:
        """Return a formatted string showing the top 5 values and an indication of how many were omitted."""
        top_5 = [f"{val} ({pct:.2%})" for val, pct in counts.head(5).items()]
        omitted_count = len(counts) - 5
        omitted_info = f"... ({omitted_count} more not shown)" if omitted_count > 0 else ""
        return ', '.join(top_5) + omitted_info

    if not files:
        styled_print(f'No files were found under {data_dir}.')
        return []

    with Progress() as progress:
        task = progress.add_task("[cyan bold]Scanning files...[/]", total=len(files))
        for file_path in files:
            progress.update(task, description=f"[cyan bold]Scanning: {file_path.name}[/]") 
            
            df = load_dataframe(file_path)
            
            columns = df.columns

            for col in columns:
                # Initialise stats if not already present
                if col not in variable_stats:
                    variable_stats[col] = {
                        'num_files_present': 0,
                        'num_files_constant': 0,
                        'unique_values': set(),
                        'constant_values': set(),
                        'constant_values_dist': [], # frequency of constant values
                        # 'unique_values_dist': [],
                        'all_values_dist': [] # the distribution of all values across all files
                    }

                # Update the number of files in which the variable appears
                variable_stats[col]['num_files_present'] += 1

                df[col].fillna('Missing', inplace=True)
                
                unique_values_set = set(df[col].unique())
                variable_stats[col]['unique_values'].update(unique_values_set)
                # variable_stats[col]['unique_values_dist'].extend(list(unique_values_set))
                variable_stats[col]['all_values_dist'].extend(df[col])
                
                # Check if the column is constant in this file
                if len(unique_values_set) == 1:
                    variable_stats[col]['num_files_constant'] += 1
                    variable_stats[col]['constant_values'].update(unique_values_set)
                    variable_stats[col]['constant_values_dist'].append(list(unique_values_set)[0])
                else:
                    variable_stats[col]['constant_values_dist'].append(NON_CONSTANT_MARKER)

            progress.advance(task)
        
        progress.update(
            task, 
            description="[green bold]✔ All files scanned![/]", 
            completed=len(files), 
            refresh=True
        )
    
    global_constant_columns = []
    remove_cols = []
    mid_range_cols_with_values = []

    for var, stats in variable_stats.items():
        if stats['unique_values'] == stats['constant_values'] == {"Missing"}:
            continue
        
        num_files_present = stats['num_files_present']
        num_files_constant = stats['num_files_constant']

        if num_files_present > 0:
            proportion_constant = num_files_constant / num_files_present
        else:
            proportion_constant = 0.0

        # Calculate distributions
        all_values_counts = calculate_distribution(stats['all_values_dist'])
        constant_values_counts = calculate_distribution(stats['constant_values_dist'])

        all_values_dist_str = format_distribution(all_values_counts)
        constant_values_dist_str = format_distribution(constant_values_counts)
        
        prop_constant_str = f"{proportion_constant*100:.1f}% ({num_files_constant} / {num_files_present})"
        
        if consider_missing:
            missing_prop = all_values_counts.get("Missing", 0)
            if missing_prop >= missing_cutoff:
                if not var.startswith((NCCIS.PREFIX, "suspPermExcl")): # exclude NCCIS and suspPermExcl
                    remove_cols.append((
                        var,
                        # num_files_present,
                        # num_files_constant,
                        all_values_dist_str,
                        constant_values_dist_str,
                        prop_constant_str
                    ))

        # Find the top non-"NonConstant" value in constant_values_dist
        constant_candidates = constant_values_counts[constant_values_counts.index != NON_CONSTANT_MARKER]
        top_constant_value_proportion = 0.0
        if not constant_candidates.empty:
            top_constant_value_proportion = constant_candidates.iloc[0]  # top proportion

        # Use the top constant value proportion to determine global constants
        if top_constant_value_proportion >= consistency_cutoff:
            # Skip columns that are completely "Missing" if that's considered empty
            global_constant_columns.append(var)
            remove_cols.append((
                var,
                # num_files_present,
                # num_files_constant,
                all_values_dist_str,
                constant_values_dist_str,
                prop_constant_str
            ))
        elif 0.5 <= top_constant_value_proportion < consistency_cutoff:
            if var not in {col[0] for col in remove_cols}:  
                # mid-range columns
                mid_range_cols_with_values.append((
                    var,
                    # num_files_present,
                    # num_files_constant,
                    all_values_dist_str,
                    constant_values_dist_str,
                    prop_constant_str
                ))
        # else: < 0.5, ignore

    # Define the columns for output
    printout_cols = [
        'Variable', 
        # 'Files Presented', 
        # 'Files Constant', 
        'Global Value Distribution', 
        'Constant Value Frequency', 
        'Proportion Of Constant Files'
    ]
    
    if remove_cols:
        df_g = pd.DataFrame(remove_cols, columns=printout_cols)
        df_g.drop_duplicates(inplace=True)
        
        styled_print(
            f'- The following {len(df_g)} variables are considered global constants as their top constant value proportion (> {consistency_cutoff*100}%) is satisfied'
            + (f', and their missing proportion exceeds {missing_cutoff*100}%.' if consider_missing else '.')
        )
        df_g['pct'] = df_g['Proportion Of Constant Files'].apply(lambda x: float(x.split('%')[0]))
        df_g = df_g.sort_values(by='pct', ascending=False).drop(columns='pct')
        print_table(df_g, num_rows=len(remove_cols))
    else:
        styled_print('No global constant variables found.')
    
    if mid_range_cols_with_values:
        styled_print(
            f'- The following {len(mid_range_cols_with_values)} variables have a mid-range top constant value proportion (i.e., > 50% but < {consistency_cutoff*100}%). '
            'These may warrant further review:'
        )
        df_m = pd.DataFrame(mid_range_cols_with_values, columns=printout_cols)
        df_m.drop_duplicates(inplace=True)
        df_m['pct'] = df_m['Proportion Of Constant Files'].apply(lambda x: float(x.split('%')[0]))
        df_m = df_m.sort_values(by='pct', ascending=False).drop(columns='pct')
        print_table(df_m, num_rows=len(mid_range_cols_with_values))
    else:
        styled_print(f'No mid-range variables found (> 50% but < {consistency_cutoff*100}%).')
        
    explanations = {
        "Global Value Distribution": (
            "This column shows the overall distribution of all values for the variable across all files, "
            "including missing values. For example, if 'Missing (82.3%)' is shown, it means that 82.3% "
            "of all occurrences of the variable across files are missing."
        ),
        "Constant Value Frequency": (
            "This column shows the distribution of constant values for the variable, representing the proportion "
            "of files in which the variable has a single consistent value. For example, if 'Missing (83.3%)' "
            "is shown, it means 83.3% of the files have the variable as a constant with the value 'Missing'."
        ),
        "Proportion Of Constant Files": (
            "This column indicates the proportion and count of files where the variable is constant. "
            "For example, '66.7% (4/6)' means the variable is constant in 4 out of 6 files (66.7%)."
        ),
    }
    
    for col_name, explanation in explanations.items():
        styled_print(f"{col_name}: {explanation}")

    return global_constant_columns

def clean_data(
    input_path: Union[str, Path] = None,
    stud_id_col: str = STUD_ID_COL,
    rm_nan_stud_id: bool = True,
    rm_nan_cols_threshold: Union[Literal[False], float] = 0.5,
    rm_dups_threshold: Union[Literal[False],
                                       float, Literal['first']] = False,
    rm_empty_cols: bool = True,
    rm_constant_cols: Union[Literal[False], Literal['global'], Literal['local']] = 'local',
    constant_consistency: float = 0.8,
    consider_missing: bool = False,
    missing_cutoff: float = 0.8,
    rm_problematic_ids: Union[Literal[False], int, List[int]] = False,
    rm_sensitive_cols: List[str] = None,
    output_path: Union[str, Path] = None,
    col_metadata_path: Union[str, Path] = None,
    file_naming_format: List[str] = None,
    overwrite: bool = None
) -> None:
    """
    Clean the data by performing the following actions:
    - Read all .xlsx / .csv files from the specified or default raw data path.
    - Remove duplicates and NaN values based on the given thresholds.
    - Remove specified sensitive columns if they exist in the data.
    - Save the cleaned data to the output directory.

    Parameters
    ----------
    input_path : Union[str, Path], optional
        Path to the directory containing the raw data files. Uses default path if not provided.
    
    stud_id_col : str, optional
        Name of the column containing student IDs. Defaults to 'stud_id'.
    
    rm_nan_stud_id : bool, optional
        If True, removes rows with NaN 'stud_id' values. Default is True.
    
    rm_nan_cols_threshold : Union[Literal[False], float], optional
        If set, removes columns with a higher proportion of NaN values than the threshold. 
        Set to False to skip this. Default is 0.5.
    
    rm_dups_threshold : Union[Literal[False], float, Literal['first']], optional
        If 'first', keeps the first instance of duplicates. If a float, removes duplicates
        if the percentage of NaN values in a duplicate row exceeds this threshold. Default is False.
    
    rm_empty_cols : bool, optional
        If True, removes columns with all NaN values. Default is True.
    
    rm_problematic_ids : Union[Literal[False], int, List[int]], optional
        List of specific student IDs to remove from the data. Default is False (no IDs removed).
    
    rm_constant_cols : Union[False, 'global', 'local'], optional
        Specifies whether to remove columns with constant values:
        - False: Do not remove constant columns.
        - 'global': Remove columns that have a single constant value across all files in the folder.
        - 'local': Remove columns that have a single constant value within each file individually.
    
    constant_consistency : float, optional
        The minimum fraction of files in which a column must have a single 
        dominant constant value for it to be considered globally constant.
        Only valid if rm_constant_cols = 'global'.
        Default is 0.8 (80%).
    
    missing_cutoff : float, optional
        The maximum allowed fraction of missing values in the global distribution 
        of a variable. If the proportion of "Missing" values is equal to or greater 
        than this cutoff and missing filtering is enabled, the variable is excluded.
        Only valid if rm_constant_cols = 'global' and consider_missing = True.
        Default is 0.8 (80%).
        
    consider_missing : bool, optional
        If True (default), apply missing filtering based on `missing_cutoff`.
        If False, do not filter out variables based on missing values.
        Only valid if rm_constant_cols = 'global'.
    
    sensitive_cols : List[str], optional
        List of column names that contain sensitive information (e.g., 'surname', 'forename')
        and should be removed from the dataset if present. Default is None.
    
    output_path : Union[str, Path], optional
        Path to the directory where cleaned data will be saved. Uses default path if not provided.
    
    col_metadata_path : Union[str, Path], optional
        Path to save column metadata after cleaning. Uses default path if not provided.
    
    file_naming_format : list, optional
        The order of components in the filename. 
        Options: ["data_category", "cohort_y11_ay", "cohort_yg_ay", "year_group"].
        Default: ["cohort_y11_ay", "data_category" , "year_group"].
    
    overwrite : bool, optional
        If True, existing cleaned files are overwritten. Uses default setting if not provided.

    Returns
    -------
    None
    """

    # log_with_border(logger, "Starting the data cleaning process...")
    
    removed_data_path = output_path.parent / (output_path.name + "_discarded")
    removed_data_path.mkdir(parents=True, exist_ok=True)        

    if overwrite or not check_folder_file_count_equal(input_path, output_path):
    
        if rm_constant_cols == 'global':
            constant_columns = identify_globally_constant_columns(
                data_dir=input_path,
                consistency_cutoff=constant_consistency,
                missing_cutoff=missing_cutoff,
                consider_missing=consider_missing
            )
        
        col_meta_cleaned = {}
                    
        files = get_files_in_folder(folder_path=input_path, recursive=True)

        with Progress() as progress:
            task = progress.add_task("[cyan bold]Cleaning files...[/]", total=len(files))
            for file_path in files:

                output_file_path = output_path / file_path.name
                removed_data_file_path = removed_data_path / file_path.name

                if output_file_path.exists() and not overwrite:
                    continue
                    
                logger.info(f"Now cleaning {file_path}...")
                
                df = load_dataframe(file_path, dtype_backend='pyarrow') # can read .csv or .xlsx, but each .xlsx should only have a single sheet

                # Count rows and columns before cleaning
                rows_before = len(df)
                cols_before = df.shape[1]

                # Clean the DataFrame
                df_cleaned, removed_data = remove_data(
                    df,
                    stud_id_col=stud_id_col,
                    rm_nan_stud_id=rm_nan_stud_id,
                    rm_nan_cols_threshold=rm_nan_cols_threshold,
                    rm_dups_threshold=rm_dups_threshold,
                    rm_empty_cols=rm_empty_cols,
                    rm_constant_cols=constant_columns if rm_constant_cols == 'global' else rm_constant_cols,
                    rm_problematic_ids=rm_problematic_ids,
                    rm_sensitive_cols=rm_sensitive_cols
                )
                
                # Save removed data
                if not removed_data.empty:
                    removed_data.to_excel(removed_data_file_path, index=True)
                    logger.info(f"Removed data saved to {removed_data_file_path}")
                
                # Count rows and columns after cleaning
                rows_after = len(df_cleaned)
                cols_after = df_cleaned.shape[1]
                
                # Compute unique values for each column (excluding NaN)
                col_unique_values = {}
                for col in df.columns:
                    unique_vals = df[col].dropna().unique().tolist()
                    col_unique_values[col] = set(unique_vals)
                
                # Create column metadata
                col_meta_cleaned = update_col_metadata_entry(
                                data_category=file_path.stem.split('_')[file_naming_format.index("data_category")],
                                col_meta=col_meta_cleaned,
                                std_colnames=df_cleaned.columns,
                                col_dtype=df_cleaned.dtypes,
                                std_filename=file_path.name,
                                col_unique_values=col_unique_values,
                                )
                
                # Save cleaned DataFrame
                df_cleaned.to_excel(output_file_path, index=False)
                
                logger.info(f"Cleaned data saved to {output_file_path}")
                logger.info(
                    f"Rows before cleaning: {rows_before}, Rows after cleaning: {rows_after}, "
                    f"Rows removed: {rows_before - rows_after}"
                )
                logger.info(
                    f"Columns before cleaning: {cols_before}, Columns after cleaning: {cols_after}, "
                    f"Columns removed: {cols_before - cols_after}"
                )
              
                # Add a line break
                log_line_break(logger)
                
                # Advance progress
                progress.advance(task)
            
            progress.update(task, description="[green bold]✔ All files processed![/]", refresh=True)
            
        # update column metadata, remove the column name that not exist in cleaned data
        extract_col_metadata(col_meta_cleaned, col_metadata_path)
    
    styled_print("Data cleaning process completed.", colour='magenta')
    return None
    