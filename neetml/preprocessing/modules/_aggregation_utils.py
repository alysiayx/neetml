import logging
import pandas as pd
from collections import Counter

from ...utils.misc import (
    styled_print, 
    print_table,
)

from ...utils.constants import (
    MergeMetadata,
)

from .._utils import (
    remove_prefix,
)

from ...utils.logger_setup import (
    get_logger, 
)

logger = get_logger("data_processor")
# logger = logging.getLogger(__name__)   

def agg_values(x: pd.Series, col_name: str):
    """
    Aggregates column values based on the prefix or content of the column name.
    The aggregation rules are defined here.

    Parameters
    ----------
    x : pd.Series
        The column data to aggregate.
    col_name : str
        The name of the column being aggregated.

    Returns
    -------
    Aggregated value based on the specified rules.
    """
    # Check for numerical columns but exclude boolean values
    if pd.api.types.is_numeric_dtype(x) and not pd.api.types.is_bool_dtype(x):
        if col_name.startswith('ks2') or col_name.startswith('ks4'):
            # take the mean for unique and non-NA values
            return x.dropna().mean() if x.nunique(dropna=True) > 1 else x.iloc[0]
        elif 'rate' in col_name.lower() or '%' in col_name: # usually in attendance data
            return x.dropna().mean() if x.nunique(dropna=True) > 1 else x.iloc[0]
        else:
            return x.sum() if x.nunique(dropna=True) > 1 else x.iloc[0] # usually for attendance data
    # Aggregate non-numerical columns
    elif x.nunique(dropna=True) > 1:
        return ', '.join(sorted(dict.fromkeys(x.dropna().astype(str).unique())))
    else:
        return x.iloc[0]  # Take the first value if all values are the same

def check_agg_records(df: pd.DataFrame, stud_id_col: str) -> pd.DataFrame:
    """
    Checks for multiple records of the same student and validates the presence of required metadata columns.

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame containing student records.
    stud_id_col : str
        The column name representing student ID.

    Returns
    -------
    pd.DataFrame
        The subset of students with multiple records.
    
    Raises
    ------
    ValueError
        If required metadata columns are missing.

    Notes
    -----
    The required columns for aggregation are metadata columns added during the **merge step**.
    These metadata columns (prefixed with `_`) provide structural information:
    
    - `_y11_cohort`: Indicates the student's Year 11 cohort.
    - `_year_group`: Represents the student's academic year group.
    
    These columns should have been created in the **merge process**, and their absence may indicate an issue in upstream data processing.
    
    """
    
    # Required metadata columns that should be created during the merge process
    required_cols = {stud_id_col, MergeMetadata.Y11_COHORT, MergeMetadata.YEAR_GROUP}
    
    missing_cols = required_cols - set(df.columns)

    if missing_cols:
        raise ValueError(
            f"Missing required columns: {missing_cols}. These columns should have been created during the "
            "previous merge step. Ensure that the merged data includes these columns before aggregation."
        )
    
    group_key = list(required_cols)
    
    if MergeMetadata.PHASE in df.columns:
        group_key.append(MergeMetadata.PHASE)
    
    multi_record_studs = df[df.duplicated(subset=group_key, keep=False)]
    
    logger.info(
        f"Found {len(multi_record_studs)} rows need to be aggregrated, which impact {multi_record_studs[stud_id_col].nunique()} students' records.")
    
def check_agg_duplicate_records(df: pd.DataFrame, stud_id_col: str) -> pd.DataFrame:
    """
    Check for and handle duplicate student records based on the stud_id column.
    - Numeric columns are summed.
    - Non-numeric columns are merged into a comma-separated list of unique values.

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame containing the student data with possible duplicates.
        
    stud_id_col : str
        The name of the student ID column to use for setting the index.

    Returns
    -------
    pd.DataFrame
        A DataFrame where duplicate records are merged into one record per student.
    """
    # Set the index to the stud_id column
    df.set_index(stud_id_col, inplace=True)

    # Log initial information
    unique_ids_before = df.index.nunique()
    total_cols_before = df.shape[1]
    colname_before = list(df.columns)
    
    styled_print(f"Initial data shape: {df.shape}, number of unique IDs: {unique_ids_before}")
    
    problematic_report = pd.DataFrame(columns=["Student ID", "Similarity Score"]) # store problematic student ids
    
    # Check for duplicate student IDs
    if not df.index.is_unique:
        duplicates = df[df.index.duplicated(keep=False)]
        # differing_columns = duplicates.loc[:, duplicates.nunique(axis=0) > 1]

        logger.warning(f"Found {duplicates.shape[0]} duplicate rows for {duplicates.index.nunique()} students.")

        num_records = 2
        styled_print(f'- Before aggregation (showing the first {num_records} student records):')
        # only print the differeing columns (>= 2 unique values)
        print_table(
            df=duplicates, 
            rich_table=False,
            show_index=True, 
            num_rows='all', 
            num_cols='all', 
            num_records=num_records, 
            show_diffs_only=True,
        )
        
        # Aggregate duplicates (only if values are different)
        aggregated_duplicates = duplicates.groupby(duplicates.index).agg(
            lambda x: agg_values(x, col_name=x.name)
        )
        
        # Identify aggregated columns
        aggregated_columns = [
            col for col in duplicates.columns
            if (
                set(duplicates[col].dropna().apply(str).unique())
                != set(aggregated_duplicates[col].dropna().apply(str).unique())
            )
        ]
        
        styled_print(f'- After aggregation (showing the first {num_records} student records):')
        assert colname_before == list(aggregated_duplicates.columns)
        print_table(
            aggregated_duplicates[aggregated_columns],  # show only aggregated columns
            show_index=True, 
            num_rows='all', 
            num_cols='all', 
            num_records=num_records, 
            show_diffs_only=False,
            rich_table=False
        )            
        
        # Remove duplicates from the original DataFrame
        df = df[~df.index.duplicated(keep=False)]

        # Combine the aggregated duplicates back into the main DataFrame
        df = pd.concat([df, aggregated_duplicates])

        # Sort the final DataFrame by the index
        df = df.sort_index()

        # Log the resulting shape
        unique_ids_after = df.index.nunique()
        total_cols_after = df.shape[1]
        total_rows_after = df.shape[0]
        colname_after = list(df.columns)
        
        styled_print(f"Final data shape: {df.shape}, number of unique IDs: {unique_ids_after}")
        
        # Now we would like to find potentially problematic records
        # Define a similarity threshold (columns with identical values)
        similarity_threshold = 0.95

        # List to store problematic records
        problematic_records = []

        # Group duplicates by the student ID (index)
        for stud_id, group in duplicates.groupby(duplicates.index):
            # Check similarity across all columns (ignoring NaNs)
            similar_columns = [
                group[col].dropna().nunique() == 1 for col in group.columns if col != "stud_id"
            ]
            # Calculate the similarity ratio
            similarity_ratio = sum(similar_columns) / len(similar_columns)
            if similarity_ratio >= similarity_threshold:
                problematic_records.append((stud_id, similarity_ratio))

        if problematic_records:
            problematic_report = pd.DataFrame(
                problematic_records, 
                columns=["Student ID", "Similarity Score"]
            ).sort_values(by="Similarity Score", ascending=False)
   
            logger.warning(f"The following {problematic_report.shape[0]} students' records may be problematic as {similarity_threshold*100}% of their values are similar:")
            print_table(problematic_report.sort_values(by="Student ID"), 
                        group_records=False,
                        # num_rows='all',
                        )
            problematic_ids = problematic_report["Student ID"]
            print_table(duplicates.loc[duplicates.index.isin(problematic_ids)].sort_index(), 
                        group_records=False, 
                        show_diffs_only=False,
                        rich_table=False,
                        # num_rows='all',
                        # num_cols='all',
                        num_rows=6,
                        show_index=True
                        )
            
        # Validation checks
        assert unique_ids_after == total_rows_after, (
            f"Validation failed: Unique IDs ({unique_ids_after}) do not match total rows ({total_rows_after})."
        )
        assert total_cols_before == total_cols_after, (
            f"Validation failed: The number of columns in the aggregation data ({total_cols_after}) does not match "
            f"the original number of columns in the DataFrame ({total_cols_before}). Check the aggregation logic for discrepancies."
        )
        assert colname_before == colname_after, (
            f"Validation failed: Column names changed during aggregation.\n"
            f"Original columns: {colname_before}\n"
            f"Aggregated columns: {colname_after}"
        )

        styled_print("Validation passed: No unexpected duplicate handling issues.")
    else:
        styled_print(f"No duplicates found. Data shape: {df.shape}, Unique IDs: {df.index.nunique()}")

    # print_table(df, group_records=False, show_index=True)
    
    df.reset_index(inplace=True)
    df.rename(columns={"index": stud_id_col}, inplace=True)
    return df, problematic_report

def merge_equiv_columns(df: pd.DataFrame, stud_id_col: str) -> pd.DataFrame:
    all_columns = [remove_prefix(col) for col in df.columns]
    col_counts = Counter(all_columns)
    common_cols = [item for item, count in col_counts.items() if count > 1]
    
    if not common_cols:
        return df
    
    logger.warning(f"Found common column names across data sets: {common_cols}.")
    
    for common_col in common_cols:
        # Find all columns matching the common name (with prefixes)
        matching_cols = [col for col in df.columns if remove_prefix(col) == common_col]
        subset_df = df[matching_cols]

        # Check if all matching columns have identical values
        identical = subset_df.nunique(axis=1, dropna=False).eq(1).all()

        if identical:
            logger.info(f"Columns {matching_cols} are duplicates and identical. Keeping first column.")
            df[common_col] = subset_df.iloc[:, 0]
            df.drop(columns=matching_cols, inplace=True)
        else:
            # Check if columns are complementary (only one non-NA unique value)
            non_na_counts = subset_df.apply(lambda row: row.dropna().nunique(), axis=1)
            is_complementary = (non_na_counts <= 1).all()

            if is_complementary:
                logger.info(f"Columns {matching_cols} are complementary. Merging them into one column.")
                # Combine complementary columns into one
                df[common_col] = subset_df.bfill(axis=1).iloc[:, 0]
            else:
                if not all(col.startswith(('ks2', 'ks4')) for col in matching_cols): # check for non-ks2/ks4 cols
                    conflicting_rows = subset_df[non_na_counts > 1]
                    conflicting_rows = df.loc[conflicting_rows.index, [stud_id_col] + subset_df.columns.tolist()].drop_duplicates()
                    logger.warning(
                        f"Columns {matching_cols} have conflicting values in these rows:\n{conflicting_rows}"
                    )            
                    
    return df


