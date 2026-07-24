import logging
import pandas as pd
import numpy as np
import re
import json
from pathlib import Path
from typing import List, Literal, Tuple, Dict
from datetime import datetime
from dateutil import parser
from collections import defaultdict
import networkx as nx
from rich.console import Console
from rich.panel import Panel
from matplotlib.colors import ListedColormap

from ...utils.misc import (
    styled_print, 
    load_dataframe, 
    print_table,
    assert_no_object_columns,
)

from ...utils.constants import (
    FileMetadata,
    ColumnMetadata,
    MergeMetadata,
    DATA_CATEGORIES,
    STUD_ID_COL,
    SCHOOL_ID_COLS,
    EXCLUDED_SCHOOL_TERMS,
    TARGET_COL,
    POST16_CATEGORIES,
    DROP_COLS,
    NCCIS
)

from ...utils.logger_setup import (
    get_logger, 
    log_line_break,
    log_with_border
)
from .._utils import (
    resolve_column_name,
    prefix_columns
)

from ...utils.misc import (
    styled_print, 
    load_dataframe, 
    print_table,
    plot_col_coverage,
    plot_group_heatmap
)


logger = get_logger("data_processor")
# logger = logging.getLogger(__name__)  


def append_metadata_cols(
    df: pd.DataFrame, 
    **metadata: Dict[str, any]
) -> pd.DataFrame:
    """
    Append metadata columns dynamically to a DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        The original DataFrame to which metadata columns will be appended.
    metadata : dict
        A dictionary where keys are column names (as strings) and values are the corresponding data to be added.
        Column names that do not start with an underscore ('_') will be automatically prefixed with one.

    Returns
    -------
    pd.DataFrame
        The updated DataFrame with the specified metadata columns appended.
    """
    for col_name, value in metadata.items():
        col_name = col_name if col_name.startswith("_") else f"_{col_name}"
        df[col_name] = value
        df[col_name] = df[col_name].astype(str)

    return df

def remove_metadata_cols(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove metadata columns (columns prefixed with an underscore '_') from a DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame from which metadata columns will be removed.

    Returns
    -------
    pd.DataFrame
        The updated DataFrame with the metadata columns removed.
    """
    # Identify columns that start with '_'
    metadata_cols = [col for col in df.columns if col.startswith("_")]
    
    df = df.drop(columns=metadata_cols)
    
    return df

def apply_schema_to_dataframe(
    df: pd.DataFrame,
    data_schema: Dict[str, pd.DataFrame],
    data_category: str = None,
    is_merged: bool = False,
    is_category_prefix: bool = False,
    dtype_backend: str = None
) -> pd.DataFrame:
    """
    Apply the data schema to a DataFrame and convert column data types accordingly.

    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame to which the schema will be applied.
        
    data_category : str, optional
        The data category for which the schema is applied.

    data_schema: Dict[str, pd.DataFrame]
        The schema containing curated data types.
        
    is_merged : bool, optional
        Whether df is merged.
        If True, concatenate schemas.
    
    is_category_prefix : bool, optional
        Whether the column names in the DataFrame include the data category as a prefix.
        If True, the data category is inferred from the column prefixes.

    Returns
    -------
    pd.DataFrame
        The DataFrame with curated data types applied.
    """
    
    if is_merged:
        # # Extract possible data categories from the column prefixes
        # data_categories = {
        #     col.split("_")[0] for col in df.columns if "_" in col
        # }
        
        data_categories = DATA_CATEGORIES
        
        if len(data_categories) == 0:
            raise ValueError("No data category detected.")
        
        styled_print(f"Valid data categories: {data_categories}")
        
        # Concatenate schemas and conditionally add prefix to 'Column Name'
        schema_df = pd.concat(
            [
                data_schema[category].assign(
                    **{ColumnMetadata.STD_NAME: lambda x: x[ColumnMetadata.STD_NAME].apply(
                        lambda col: f"{category}_{col}" if not col.startswith(f"{category}_") else col # add prefix
                    )}
                )
                for category in data_categories if category in data_schema
            ],
            ignore_index=True 
        )
    else:
        if data_category not in data_schema:
            raise ValueError(f"Data category '{data_category}' not found in the schema.")
    
        # Retrieve the schema for the specific data category
        if is_category_prefix:
            schema_df = data_schema[data_category].assign(
                **{
                    ColumnMetadata.STD_NAME: lambda x: x[ColumnMetadata.STD_NAME].apply(
                        lambda col: f"{data_category}_{col}" if not col.startswith(f"{data_category}_") else col
                    )
                }
            )
        else:
            schema_df = data_schema[data_category]

    # Ensure required columns exist in the schema
    required_columns = {ColumnMetadata.STD_NAME, ColumnMetadata.DATA_TYPE}
    if not required_columns.issubset(schema_df.columns):
        raise ValueError(f"The schema must contain the columns: {', '.join(required_columns)}.")

    # Iterate through the schema and apply the curated data types
    for _, row in schema_df.iterrows():
        col_name = row[ColumnMetadata.STD_NAME]
        curated_dtype = row[ColumnMetadata.DATA_TYPE]
        
        if col_name in df.columns:
            original_values = df[col_name].copy()
            
            missing_values = ["nan", "", "<NA>", "None", "NULL", "N/A"]
            regex_patterns = [fr"(?i)^{val}$" for val in missing_values]  # ^$ ensures exact matches

            try:
                if curated_dtype == 'datetime': 
                    # TODO: consider using from dataprep.clean import clean_date; clean_date(df, 'date', output_format='YYYY-MM-DD') instead
                    
                    original_values = df[col_name]
                  
                    # Convert to datetime while handling mixed formats
                    def parse_and_format_date(date):
                        try:
                            if pd.notna(date):  # Ensure the value is not NaN
                                
                                # remove timestamp
                                if isinstance(date, str):
                                    # Remove any trailing 'Z' (indicating UTC)
                                    date = date.rstrip('Z')
                                    if 'T' in date:
                                        # ISO 8601 format: e.g., 2018-09-01T00:00:00.000Z
                                        date = date.split('T')[0]  # Extract the part before 'T'
                                    
                                    # Remove unnecessary timestamp parts (e.g., ' 00:00:00')
                                    date = ' '.join(part for part in date.split() if ':' not in part)   
            
                                # Handle ambiguous date formats like '04/01/2022'
                                if isinstance(date, str) and re.match(r'^\d{2}/\d{2}/\d{4}$', date):
                                    # Assume DD/MM/YYYY format
                                    return datetime.strptime(date, '%d/%m/%Y').strftime('%Y-%m-%d')
        
                                 # Handle 'Aug-00', 'Aug-99' edge case
                                if isinstance(date, str) and re.match(r'^[A-Za-z]{3}-\d{2}$', date):
                                    current_year = datetime.now().year
                                    year_suffix = int(date[-2:])
                                    if year_suffix + 2000 > current_year:
                                        century = "19"
                                    else:
                                        century = "20"
                                    date = f"01-{date[:4]}{century}{date[-2:]}" # force day to be 01
                                
                                parsed_date = parser.parse(str(date), default=parser.parse("1970-01-01"))  # Use dateutil to parse the date
                                return parsed_date.strftime('%Y-%m-%d')  # Format to 'YYYY-MM-DD'
                        except (ValueError, TypeError) as e:
                            logger.warning(f"Error parsing date: {date} -> {str(e)}") 
                            return pd.NaT 

                    df[col_name] = df[col_name].apply(parse_and_format_date)
                    
                    # **Validation: check for '1970' in the formatted column**
                    contains_1970 = df[col_name].str.contains('1970', na=False)
                    if contains_1970.any():
                        raise ValueError(f"🚨 Unexpected transformation in column '{col_name}'.\n"
                                 f"Original Values:\n{original_values[contains_1970]}\n"
                                 f"Transformed Values:\n{df[col_name][contains_1970]}")
                    
                    # **Validation: check for NaN in the formatted column**
                    contains_na = original_values.isna()  # Check for NaN in the original column
                    converted_to_na = df[col_name].isna()  # Check for NaN after conversion
                    
                    # Check if original value contains numerical characters (e.g., '2024-01', 'Apr 2003')
                    contains_num = original_values.astype(str).str.contains(r'\d', na=False, regex=True)  # Regex to detect digits

                    # Identify problematic rows where original values are not NaN but converted to NaN
                    problematic_indices = df[~contains_na & contains_num & converted_to_na].index

                    if problematic_indices.any():
                        # Raise error with detailed information
                        raise ValueError(f"🚨 Unexpected NaN conversion in column '{col_name}'\n"
                                 f"Affected rows:\n{original_values.loc[problematic_indices]}")
                    
                    # df[col_name] = pd.to_datetime(df[col_name], format='%Y-%m-%d').dt.date # convert it to datetime64[ns]      
                    df[col_name] = pd.to_datetime(df[col_name], format='%Y-%m-%d')
                                               
                elif curated_dtype == 'boolean':
                    df[col_name] = (
                        df[col_name]
                        .astype(str)  # Ensure all values are strings
                        .str.strip()  # Remove leading/trailing whitespace
                        .str.lower()  # Convert to lowercase for uniformity
                        .replace({'yes': True, 'true': True, 'y': True, 
                                  'no': False, 'false': False, 'n': False, 
                                  '1': True, '0': False, '1.0': True, '0.0': False})
                        .replace(to_replace=regex_patterns, value=pd.NA, regex=True)
                    )
                    # df[col_name] = df[col_name].apply(lambda x: pd.NA if x not in {True, False} else x) # the output will be True and False
                    df[col_name] = df[col_name].astype('boolean')
                    
                elif curated_dtype == 'numeric':
                    df[col_name] = pd.to_numeric(df[col_name], errors='coerce')
                elif curated_dtype == 'category':
                    unique_values = df[col_name].dropna().unique()
                    # Check if all non-null values are numeric (integer-like)
                    if all(pd.api.types.is_numeric_dtype(type(val)) for val in unique_values):
                        df[col_name] = (
                            pd.to_numeric(df[col_name], errors="coerce")
                            .astype("Int64")
                            .astype(str) # so the numerical cateogry won't loss when save to parquet
                            .str.strip()
                            .str.lower()
                            .replace(to_replace=regex_patterns, value=pd.NA, regex=True)
                            .astype("category")
                        )
                    else:
                        df[col_name] = (
                            df[col_name]
                            .astype(str) # just in case it contains mixed types (e.g., '1' and 1)
                            .str.strip()
                            # .str.title()
                            .apply(lambda x: x.title() if " " in x else x)  # Apply title case only if multiple words are present
                            .replace(to_replace=regex_patterns, value=pd.NA, regex=True)
                            .astype("category")
                        )
                else:
                    if curated_dtype == 'string':
                        unique_values = df[col_name].dropna().unique()
                        if all(pd.api.types.is_numeric_dtype(type(val)) for val in unique_values):
                            # Ensure numerical labels (stored as strings) remain as integers instead of being converted to float (e.g., "1" → 1.0).
                            df[col_name] = df[col_name].astype("Int64")
                                                 
                    df[col_name] = (
                        df[col_name]
                        .astype(curated_dtype)
                    )
            
            except (ValueError, TypeError) as e:
                # **Fallback mechanism for Int64**
                if curated_dtype.lower() in {'int64', 'double', 'float64'}:
                    try:
                        df[col_name] = df[col_name].astype('Float64')
                        logger.warning(f"{col_name} should be converted to Float64 instead of {curated_dtype}.")
                    except (ValueError, TypeError) as e:
                        try:
                            df[col_name] = pd.to_numeric(df[col_name], errors='coerce')
                            logger.warning(f"{col_name} should be converted to numeric instead of {curated_dtype}.")
                        except (ValueError, TypeError) as e:
                            # **Hard fail after all attempts fail**
                            error_message = (f"❌ ERROR processing column '{col_name}' with expected type '{curated_dtype}'.\n"
                                 f"Original values:\n{df[col_name].value_counts(dropna=False)}\n"
                                 f"Error Details: {str(e)}")
                            raise ValueError(error_message)
                else:
                    error_message = (f"❌ ERROR processing column '{col_name}' with expected type '{curated_dtype}'.\n"
                         f"Original values:\n{df[col_name].value_counts(dropna=False)}\n"
                         f"Error Details: {str(e)}")
                    raise ValueError(error_message)
            
            # Identify rows where a non-empty value became empty
            changed_to_empty = (original_values.notna() & original_values.astype(str).str.strip().ne("")) & df[col_name].isna()
            
            if changed_to_empty.any():
                result_df = pd.DataFrame({
                    "Before Conversion": original_values[changed_to_empty],
                    "After Conversion": df[col_name][changed_to_empty]
                })
                
                error_message = (
                    f"Some values in '{col_name}' became empty after converting them to {curated_dtype}.\n"
                    f"{result_df}\n"
                )
                
                if curated_dtype.lower() in {'category', 'string'}:                 
                    raise ValueError(error_message)
                else:
                    logger.warning(error_message)
            
            # Identify rows where an empty value became non-empty
            changed_to_non_empty = (original_values.isna() | original_values.astype(str).str.strip().eq("")) & df[col_name].notna()

            if changed_to_non_empty.any():
                result_df = pd.DataFrame({
                    "Before Conversion": original_values[changed_to_non_empty],
                    "After Conversion": df[col_name][changed_to_non_empty]
                })

                error_message = (
                    f"Some empty values in '{col_name}' became non-empty after converting them to {curated_dtype}.\n"
                    f"{result_df}\n"
                )
                                     
                if curated_dtype.lower() in {'category', 'string'}:                 
                    raise ValueError(error_message)
                else:
                    logger.warning(error_message)
    
    # missing_values = {"nan", "", "<NA>", "None", "NULL", "N/A"}
    # df.replace(to_replace=list(missing_values), value=pd.NA, inplace=True, regex=True)
    # df = df.map(lambda x: pd.NA if pd.isna(x) else x)
    
    # Convert dtypes to the most appropriate type
    df = df.convert_dtypes()
    
    if dtype_backend == 'pyarrow':
        df = df.convert_dtypes(dtype_backend="pyarrow")
   
    assert_no_object_columns(df)
    return df

def validate_merged_data(merged_df: pd.DataFrame) -> None:
    """
    Validate the merged DataFrame to ensure:
    1. No duplicate rows exist.
    2. No fully empty (all NaN) columns exist.
    
    The merging process should not introduce unexpected transformations, so 
    the merged data should already be cleaned.

    Parameters
    ----------
    merged_df : pd.DataFrame
        The DataFrame to validate.

    Raises
    ------
    ValueError
        If duplicate rows or fully empty columns are found.
    """
    # Check for duplicate rows
    duplicate_rows = merged_df[merged_df.duplicated()]
    if not duplicate_rows.empty:
        raise ValueError(
            f"❌ Found {len(duplicate_rows)} duplicate rows in the merged DataFrame.\n"
            f"Data used for merging should be pre-cleaned, ensuring that merging does not introduce duplicates.\n"
            f"Merged values should remain unchanged, and no duplicate rows should exist.\n"
            f"🔍 Example duplicates:\n{duplicate_rows.head()}"
        )

    # Check for fully empty columns (all values are missing)
    empty_cols = [col for col in merged_df.columns if merged_df[col].isna().all()]
    if empty_cols:
        logger.warning(
            f"❌ Found {len(empty_cols)} fully empty columns in the merged DataFrame.\n"
            f"Data used for merging should be pre-cleaned, ensuring that no transformations occur post-merge.\n"
            f"No column should be entirely missing after merging.\n"
            f"BUT this may be expected if data is not available for this academic age, especially for NCCIS data.\n"
            f"Empty columns: {empty_cols}"
        )
    
    assert_no_object_columns(merged_df)

    logger.info("Merged DataFrame passed validation: No duplicates, No fully empty columns. No object columns")

# # quick but inaccurate version
# def consolidate_student_records(df: pd.DataFrame, stud_id_col: str) -> pd.DataFrame:
#     """
#     Aggregates student records for a student only if all columns have a single unique non-missing value.
#     Otherwise, retain the original records for that student.
    
#     Parameters
#     ----------
#     df : pd.DataFrame
#         The DataFrame containing student records to be processed.
#     stud_id_col : str
#         The column name representing the student ID.

#     Returns
#     -------
#     pd.DataFrame
#         A DataFrame where records are aggregated only if possible, otherwise kept as-is.
#     """
#     def can_aggregate(group):
#         # Check if each column has at most one unique non-missing value
#         is_single_value = group.nunique(dropna=True) <= 1
#         if is_single_value.all():
#             # Combine all rows into a single row
#             result = group.iloc[0].copy()
#             for i in range(1, len(group)):
#                 result = result.combine_first(group.iloc[i])
#             return pd.DataFrame([result])  # Return as a single-row DataFrame
#         else:
#             # Return the original group if it cannot be aggregated
#             return group

#     # Group by student ID and process each group
#     aggregated_df = df.groupby(stud_id_col, group_keys=False).apply(can_aggregate)
#     return aggregated_df.reset_index(drop=True)



# slow but more accurate version
def consolidate_student_records(df: pd.DataFrame, stud_id_col: str) -> pd.DataFrame:
    """
    Aggregates student records for a student by checking row pairs iteratively
    for compatibility (i.e., mutually exclusive non-missing values).
    
    Parameters
    ----------
    df : pd.DataFrame
        The DataFrame containing student records to be processed.
    stud_id_col : str
        The column name representing the student ID.

    Returns
    -------
    pd.DataFrame
        A DataFrame where compatible records are aggregated iteratively.
    """
    def merge_rows(row1, row2):
        """Merge two rows, taking non-missing values from both."""
        return row1.fillna(row2)

    def process_group(group):
        """Process a single group by merging compatible rows iteratively."""
        result_rows = []
        remaining_rows = group.copy()

        while not remaining_rows.empty:
            # Take the first row as the starting point
            current_row = remaining_rows.iloc[0]
            remaining_rows = remaining_rows.iloc[1:]
            
            # Check compatibility with remaining rows
            for idx in remaining_rows.index:
                next_row = remaining_rows.loc[idx]
                # is_compatible = (
                #     pd.concat([current_row, next_row], axis=1, ignore_index=True) # Combine rows as columns
                #     .apply(lambda col: col.dropna().nunique() <= 1, axis=1) # Check unique values per row excluding NaNs
                #     .all()
                # )
                
                overlap = current_row.notna() & next_row.notna()
                
                # if is_compatible:
                if (current_row[overlap] == next_row[overlap]).all():
                    # Merge rows and drop the matched row
                    current_row = merge_rows(current_row, next_row)
                    remaining_rows = remaining_rows.drop(idx)

            # Add the fully merged row to the results
            result_rows.append(current_row)

        return pd.DataFrame(result_rows)

    # Group by student ID and process each group
    num_rows = len(df)
    aggregated_df = df.groupby(stud_id_col, group_keys=False).apply(process_group).reset_index(drop=True)
    
    num_aggregated_rows = len(aggregated_df)
    
    assert num_aggregated_rows <= num_rows, f"Expected at most {num_rows} rows after aggregation, but got {num_aggregated_rows} rows."
    
    logger.info(f"Aggregated {num_rows - num_aggregated_rows} rows out of {num_rows} total rows.")
    logger.warning('Data types may be changed after aggregation, please double-check.')
    
    # # Convert the dtypes back to the original dtypes
    # for col in aggregated_df.columns:
    #     if col in df:
    #         aggregated_df[col] = aggregated_df[col].astype(df[col])
    
    return aggregated_df

def preprocess_nccis_data(
    nccis_data: pd.DataFrame, 
    stud_id_col: str = STUD_ID_COL
) -> pd.DataFrame:
    """Sort, deduplicate, and rank NCCIS data per student with adjusted ranks."""
    
    required_cols = [stud_id_col, NCCIS.ACADEMIC_AGE, NCCIS.CONFIRMED_DATE]

    # Resolve column names (add or remove prefix)
    resolved_cols = resolve_column_name(required_cols, nccis_data.columns, NCCIS.PREFIX)

    # Identify any missing columns
    missing_keys = [key for key, resolved in zip(required_cols, resolved_cols) if resolved is None]

    if missing_keys:
        raise ValueError(f"Missing required columns in NCCIS data: {missing_keys}")
    
    sort_keys = resolve_column_name(
        [NCCIS.ACADEMIC_AGE, NCCIS.CONFIRMED_DATE], 
        nccis_data.columns, 
        NCCIS.PREFIX
    )
    
    drop_dup_keys = resolve_column_name(
        [stud_id_col, NCCIS.ACADEMIC_AGE], 
        nccis_data.columns, 
        NCCIS.PREFIX
    )
    
    # Sort data by academic age and confirmed date
    sorted_data = (
        nccis_data
        .sort_values(by=sort_keys, ascending=[True, False])
        .drop_duplicates(subset=drop_dup_keys, keep="first")
        # .assign(rank=lambda df: df.groupby(stud_id_col)[NCCIS.ACADEMIC_AGE].rank(method="first", ascending=True))
    )
        
    return sorted_data

def preprocess_school_cols(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """
    Preprocess a column by:
    - Converting to lowercase
    - Removing leading "the"
    - Stripping whitespace
    
    Handles both 'object' and 'category' column types.
    """
    if col in df.columns:
        # Check if column is categorical
        is_category = pd.api.types.is_categorical_dtype(df[col])

        # Temporarily convert category to string if necessary
        if is_category:
            df[col] = df[col].astype(str)
            missing_values = ["nan", "", "<NA>", "None", "NULL", "N/A"]
            regex_patterns = [fr"(?i)^{val}$" for val in missing_values]  # ^$ ensures exact matches
            df.replace(to_replace=regex_patterns, value=np.nan, inplace=True, regex=True)

        try:
            df[col] = (
                df[col]
                .str.lower()  # Convert to lowercase
                .str.replace(r'^\s*the\s+', '', case=False, regex=True)  # Remove leading "the"
                .str.strip()  # Strip whitespace
            )
        except:
            raise ValueError(f"Error preprocessing column {col} with {df[col].dtype} dtype.")

        # # Convert back to category if it was originally categorical
        # if is_category:
        #     df[col] = df[col].astype('category')
    else:
        print(f"Warning: Column '{col}' not found in DataFrame!")

    return df

def merge_with_best_key(
    merged_df: pd.DataFrame, 
    df: pd.DataFrame, 
    stud_id_col: str = STUD_ID_COL, 
    excluded_terms: list = EXCLUDED_SCHOOL_TERMS,
    school_id_cols: list = SCHOOL_ID_COLS,
    data_category: str = "this data category",
    cohort_yg_ay: str = "this year cohort",
    file_name: str = "this file",
) -> pd.DataFrame:
    """
    Merge two DataFrames by identifying the best key combination when `stud_id` alone is insufficient.

    Parameters:
    - merged_df: DataFrame (existing dataset to merge into)
    - df: DataFrame (new dataset to merge)
    - stud_id_col: str (column name for student ID)
    - excluded_terms: list (terms to exclude from column matching, default EXCLUDED_SCHOOL_TERMS)
    - school_id_cols: list (school-related column identifiers for dynamic matching, default SCHOOL_ID_COLS)
    - data_category: str (data category, optional for logging)
    - cohort_yg_ay: str (year cohort, optional for logging)
    - file_name: str (file name, optional for error handling/logging)

    Returns:
    - merged_df: DataFrame (result of the merge)
    """
    
    # Check if stud_id alone can be used
    stud_id_unique_left = not merged_df.duplicated(subset=[stud_id_col]).any()
    stud_id_unique_right = not df.duplicated(subset=[stud_id_col]).any()

    if stud_id_unique_left and stud_id_unique_right:
        # use stud_id
        merged_df = pd.merge(
            merged_df, 
            df, 
            on=stud_id_col, 
            how='outer', 
            suffixes=('', '_dup')
        )
    else:
        # Need to find a suitable school column pair
        left_cols = merged_df.columns
        right_cols = df.columns
        
        left_school_cols = [
            col for col in left_cols 
            if any(c in col for c in school_id_cols) and not any(excl in col for excl in excluded_terms)
        ]

        right_school_cols = [
            col for col in right_cols 
            if any(c in col for c in school_id_cols) and not any(excl in col for excl in excluded_terms)
        ]

        school_cols = left_school_cols + right_school_cols

        candidate_results = []
        for left_school_col in left_school_cols:
            for right_school_col in right_school_cols:
                left_merge_key = [stud_id_col, left_school_col]
                right_merge_key = [stud_id_col, right_school_col]
                
                # Let's measure how well they match by counting rows present in both
                sorted_left = merged_df[left_merge_key].sort_values(by=left_merge_key)
                sorted_right = df[right_merge_key].sort_values(by=right_merge_key)

                sorted_left = preprocess_school_cols(sorted_left, left_school_col)
                sorted_right = preprocess_school_cols(sorted_right, right_school_col)

                try:
                    # Let's measure how well they match by counting rows present in both
                    # TODO: This may not very accurate
                    comparison = pd.merge(
                        sorted_left,
                        sorted_right,
                        how="outer", 
                        left_on=left_merge_key,
                        right_on=right_merge_key,
                        indicator=True
                    )
                    
                    match_count = (comparison['_merge'] == 'both').sum()
                    candidate_results.append((left_school_col, right_school_col, match_count))
                except:
                    pass                                

        if candidate_results:
            # Choose the pair with the highest both_count
            best_left_col, best_right_col, best_count = max(candidate_results, key=lambda x: x[2])
            
            logger.info(
                f"For Year Cohort {cohort_yg_ay}, the best merge key pair to merge {data_category} is ({stud_id_col}, {best_left_col}) on the left and "
                f"({stud_id_col}, {best_right_col}) on the right with {best_count} matched rows."
            )

            # Now merge with the chosen best pair
            merged_df = pd.merge(
                merged_df,
                df,
                how='outer',
                left_on=[stud_id_col, best_left_col],
                right_on=[stud_id_col, best_right_col],
                suffixes=('', '_dup')
            )
           
            # Define columns order: Student ID → School columns → Age/Year Group → Remaining
            columns_order = (
                [stud_id_col] + 
                [col for col in school_cols if col in merged_df.columns] + 
                [col for col in merged_df.columns if any(keyword in col.lower() for keyword in ["age", "ncy"])] + 
                [col for col in merged_df.columns if col not in ([stud_id_col] + school_cols + 
                                                                  [col for col in merged_df.columns if any(keyword in col.lower() for keyword in ["age", "ncy"])])] 
            )

            # Reorder the DataFrame
            merged_df = merged_df[columns_order]
        
        else:
            # Check if stud_id alone can be used
            if stud_id_unique_right:
                # use stud_id
                if not merged_df[stud_id_col].isin(df[stud_id_col]).all():
                    missing_count = len(merged_df[~merged_df[stud_id_col].isin(df[stud_id_col])])
                    logger.warning(f'{missing_count} students only contain {data_category} data.')
                
                # Add a helper column to uniquely rank duplicates in merged_df
                merged_df['merge_rank'] = merged_df.groupby(stud_id_col).cumcount()

                # Perform the merge, ensuring only the first instance of each stud_id_col in merged_df is used
                merged_df_tmp = pd.merge(
                    merged_df[merged_df['merge_rank'] == 0],
                    df,
                    on=stud_id_col,
                    how='outer',
                    suffixes=('', '_dup'),
                )
                merged_df = pd.concat(
                    [merged_df_tmp, merged_df[merged_df['merge_rank'] != 0]],
                    ignore_index=True
                )
                merged_df.drop(columns=['merge_rank'], inplace=True)    
            else:
                raise ValueError(
                    f"For Year Cohort {cohort_yg_ay}, cannot find any suitable school column key pair to merge with {stud_id_col}. "
                    f"The {stud_id_col} column in {file_name} is also not unique."
                    "Merging cannot proceed uniquely."
                )
    
    logger.warning("Data types may changed after merge two DataFrames by identifying the best key combination when `stud_id` alone is insufficient.")
    
    return merged_df

def append_nccis_data(
    school_data: pd.DataFrame,
    nccis_sept_data: pd.DataFrame,
    nccis_march_data: pd.DataFrame,
    stud_id_col: str = STUD_ID_COL,
    start_year_group: int = 11, # 15 is Year 11 age, 16 is Year 12 age, 17 is Year 13
    max_academic_age: int = 24
) -> List[Tuple[int, int, pd.DataFrame]]:
    """
    Process alternating training and target datasets from Year 11 (academic age 15) up to a specified maximum academic age.

    Args:
        school_data: Education data (e.g., KS2, KS4, attendance, exclusion, and census).
        nccis_sept_data: NCCIS September demographics data.
        nccis_march_data: NCCIS March demographics data.
        stud_id_col: Column name for student IDs.
        start_year_group: Starting year group to process (default: 11).
        max_academic_age: Maximum academic age to process (default: 24).

    Returns:
        A list of tuples [(year_group, academic_age, merged_data)].
    """
    
    nccis_academic_age = resolve_column_name(
        NCCIS.ACADEMIC_AGE, 
        nccis_march_data.columns,
        NCCIS.PREFIX
    )
    
    min_academic_age = nccis_sept_data[nccis_academic_age].min()
    year_group = start_year_group # Year 11 corresponds to academic age 15, Year 12 to 16, etc.  
    start_academic_age = year_group + 4
    
    if start_academic_age < min_academic_age:
        logger.warning(
            f"The specified `start_year_group` ({start_year_group}) corresponds to academic age {start_academic_age} lower than the minimum academic age "
            f"({min_academic_age}) available in the NCCIS dataset. However, NCCIS data for academic age {min_academic_age} will be "
            f"appended beginning with Year {start_year_group} (corresponding to academic age {start_academic_age}). "
            f"If you want to align with the dataset's actual range, set the `start_year_group` to the one corresponding to academic age {min_academic_age}."
        )
        current_academic_age = min_academic_age
    else:
        current_academic_age = start_academic_age
    
    max_academic_age = max(current_academic_age, min(nccis_march_data[nccis_academic_age].max(), max_academic_age))
    year_group_data = []
    
    # Remove duplicate records if necessary
    if nccis_sept_data.duplicated(subset=[stud_id_col, nccis_academic_age]).any():
        nccis_sept_data = preprocess_nccis_data(nccis_sept_data, stud_id_col)
    
    if nccis_march_data.duplicated(subset=[stud_id_col, nccis_academic_age]).any():
        nccis_march_data = preprocess_nccis_data(nccis_march_data, stud_id_col)
   
    # remove the meta cols (column name with prefix '_')
    nccis_sept_data = remove_metadata_cols(nccis_sept_data)
    nccis_march_data = remove_metadata_cols(nccis_march_data)

    # add prefix of each column
    nccis_sept_data = prefix_columns(nccis_sept_data, prefix=NCCIS.PREFIX)
    nccis_march_data = prefix_columns(nccis_march_data, prefix=NCCIS.PREFIX)
  
    while current_academic_age + 1 <= max_academic_age:
        merged_data = []
        merged_data_list = []
        merged_phase_data = []
        
        valid_students = school_data[stud_id_col].unique()
        logger.info(f"Found {len(valid_students)} students at the academic age of {current_academic_age}.")
        
        # Phase 1: September -> March (pre-spring)
        # NCCIS September data is merged as training data, with NCCIS March as the target.
        # Phase 2: March -> September (post-spring)
        # NCCIS March data replaces September data and serves as the training set, with next-year September as the target.
        
        for phase_label, training_source, target_source in [
            ("pre-spring", nccis_sept_data, nccis_march_data),
            ("post-spring", nccis_march_data, nccis_sept_data)
        ]:
            train_data = training_source[
                (training_source[nccis_academic_age] == current_academic_age) &
                (training_source[stud_id_col].isin(valid_students))
            ]
            
            logger.info(f"{train_data[stud_id_col].nunique()} studnets have NCCIS records at the academic age of {current_academic_age}")

            target_data = target_source[
                (target_source[nccis_academic_age] == (current_academic_age if phase_label == "pre-spring" else current_academic_age + 1)) &
                (target_source[stud_id_col].isin(valid_students))
            ][[stud_id_col, TARGET_COL]]
            
            if train_data.empty or target_data.empty:
                logger.warning(f"No sufficient data for academic age {current_academic_age} in phase {phase_label}. Skipping...")
                continue
            
            if phase_label == "pre-spring":
                logger.info(
                    f"Phase 1: September -> March | Academic Age: {current_academic_age} | "
                    f"Training Data: NCCIS September | Target Data: NCCIS March"
                )
            else:
                logger.info(
                    f"Phase 2: March -> September | Academic Age: {current_academic_age} | "
                    f"Training Data: NCCIS March | Target Data: Next-year NCCIS September"
                )

            if TARGET_COL in train_data.columns:
                # Rename the target column in training data to avoid confusion
                # Consider remove TARGET_COL from training data if it is not needed
                logger.warning(
                    f"Renaming {TARGET_COL} in training data to {TARGET_COL}_latest to avoid confusion with target data. "
                    f"Consider removing {TARGET_COL} from training data if it is not needed."
                )
                train_data.rename(columns={TARGET_COL: f"{TARGET_COL}_latest"}, inplace=True)
            
            # Merge training data with Year 11 school data
            # - For students under 18, perform a **left join** to keep all Year 11 students
            #   and merge their NCCIS records from the following academic year when available.
            # - For students aged 18 or older, perform an **inner join** since Local Authorities (LAs) 
            #   are not required to track and report their activity unless they have an EHC plan.

            training_data = pd.merge(
                school_data, train_data, on=stud_id_col, how="left" if current_academic_age <= 17 else "inner"
            )

            missing_students = set(school_data[stud_id_col]) - set(target_data[stud_id_col])

            if missing_students:
                logger.warning(
                    f"{len(missing_students)} students haven't Sep Guarantee / NCCIS Sep data at the academic age of {current_academic_age}.\n"
                    f"Example missing IDs: {list(missing_students)[:5]}"
                )

            merged_phase_data = pd.merge(training_data, target_data, on=stud_id_col, how="left")
            
            # _validate_merged_data(merged_phase_data)

            merged_phase_data.drop_duplicates(inplace=True)
            merged_phase_data.dropna(axis=1, how="all", inplace=True)
            merged_phase_data.sort_values(by=stud_id_col, inplace=True)
            
            # -----------------------
            # Aggregation step: 
            # Some students have multiple records where all columns (excluding the student ID) contain identical values. 
            # To avoid inflating the dataset, we aggregate such records by retaining only one unique
            # representation of the student's data. However, if even one column has differing   
            # values across records, all records for that student are retained without aggregation.

            merged_phase_data = consolidate_student_records(df=merged_phase_data, stud_id_col=stud_id_col)

            # -----------------------
            if not merged_phase_data.empty:
                merged_phase_data[MergeMetadata.PHASE] = phase_label
                
                # print_table(merged_phase_data, num_cols='all', num_rows=5, show_index=False, title=f"Year {year_group} (Academic Age {current_academic_age}, Phase: {phase_label})", group_records=False)

                # # TODO: hard-coded column names for temporary testing
                # print_table(merged_phase_data[['stud_id', 'nccis_academic_age', 'nccis_age', 'nccis_code_latest', 'nccis_code']], title=f"Year {year_group} (Academic Age {current_academic_age}, Phase: {phase_label})", group_records=False)
                
                merged_data_list.append(merged_phase_data)

        if merged_data_list:
            merged_data = pd.concat(merged_data_list, ignore_index=True)
            # _validate_merged_data(merged_data)
            merged_data.drop_duplicates(inplace=True)
            merged_data.dropna(axis=1, how="all", inplace=True)
            merged_data.sort_values(by=stud_id_col, inplace=True)
            
            print_table(
                merged_data, num_cols='all', num_rows=5, show_index=False,
                title=f"Year {year_group} (Academic Age {current_academic_age}, All Phases)", group_records=False
            )
            year_group_data.append((year_group, current_academic_age, merged_data))
        
        current_academic_age += 1
        year_group += 1
        
        log_line_break(logger)     
     
    return year_group_data

def merge_files_for_cohort(
    cohort_yg_ay: str,
    cohort_info: pd.DataFrame,
    input_path: Path,
    data_schema: Dict[str, pd.DataFrame],
    stud_id_col: str,
    nccis_sept_data: pd.DataFrame,
    nccis_march_data: pd.DataFrame,
    nccis_append_start_yg: int = 11, # 15 is Year 11 age, 16 is Year 12 age, 17 is Year 13
) -> pd.DataFrame:
    """
    Merge data by Year Cohort using 'stud_id' and if needed, one additional school-related column pair.
    
    The merging logic is as follows:
    1. Start with one dataset and iteratively merge others in the same Cohort.
    2. Attempt to merge on 'stud_id' alone. If that isn't sufficient, try predefined candidate pairs 
       of school-related columns to find a unique match key. Choose the key that yields the most matches.
    3. After merging, reorder columns and remove identical duplicate rows (based on all columns except 'stud_id').

    Validation Requirement:
    After merging and applying the aggregation step, we validate that original data values remain unchanged. 
    That is, for any record in the final merged data that originated from a given source dataset:
    - The columns from that source dataset match exactly the values in the original dataset after identical transformations.
    """
    
    merged_df = None
    ks4 = None
    original_dfs = {}
    merged_data_group = []
    
    year_group = int(cohort_info[FileMetadata.YEAR_GRP].dropna().unique()[0])
    
    nccis_sept_data = preprocess_nccis_data(nccis_sept_data, stud_id_col)
    nccis_march_data = preprocess_nccis_data(nccis_march_data, stud_id_col)
    
    for i, (_, row) in enumerate(cohort_info.iterrows(), start=1):
        file_name = row[FileMetadata.STD_FILE_NAME]
        file_path = input_path / file_name
        
        styled_print(f"Reading file: {file_name}", colour='light_magenta')
        try:
            # df = load_dataframe(file_path, dtype_backend='pyarrow')
            df = load_dataframe(file_path)
        except:
            # df = load_dataframe(file_name, dtype_backend='pyarrow')
            df = load_dataframe(file_path)

        styled_print(f"- This dataset has a size of {df.shape} and includes records for {df[stud_id_col].nunique()} students.")
        styled_print(f"- Number of students have multiple records: {df[stud_id_col].duplicated().sum()}.")

        # Replace '&' with 'and' across all columns to fix some data quality issues
        # Some school names use '&' to represent 'and', while others use 'and' directly. This creates an inconsistency in school names.
        # This step should be done before apply data schema to dataframe.
        df = df.replace(to_replace=r'&', value='and', regex=True)
        
        data_category = row[FileMetadata.CATEGORY]
        
        # Apply data schema if provided
        if data_schema:
            df = apply_schema_to_dataframe(
                df=df, 
                data_category=data_category, 
                data_schema=data_schema,
                # dtype_backend='pyarrow'
            )   
       
        # Add prefix to avoid name conflicts (except for stud_id)
        # Note: We assume schema application doesn't alter data in a non-reversible way.
        prefix = (
            data_category
            if data_category not in POST16_CATEGORIES 
            else NCCIS.PREFIX
        )
        # df.columns = [
        #     col if col == stud_id_col or col.startswith(prefix) or col in possible_school_cols 
        #     else f"{prefix}{col}" for col in df.columns
        # ]
        
        df = prefix_columns(df, prefix=prefix)
        original_dfs[data_category] = df
        
        if data_category == 'ks4':
            logger.info(f'KS4 data will be merged in corresponding Y{nccis_append_start_yg} cohort later.')
            ks4 = df.copy()
            if i != len(cohort_info): # if KS4 is not the last file,
                continue
                
        
        # -------------------------------------------------------
        # Process school performance data
        # Y7 - Y10: ks2, census, attendance, suspension/exclusion
        # -------------------------------------------------------
        if merged_df is None:
            merged_df = df
        else:
            if data_category != 'ks4':
                merged_df = merge_with_best_key(
                    merged_df=merged_df, 
                    df=df,
                    data_category=data_category,
                    cohort_yg_ay=cohort_yg_ay,
                    file_name=file_name
                )
        
        # -------------------------------------------------------
        # Process NCCIS data
        # -------------------------------------------------------
        if i == len(cohort_info): # append NCCIS data when last file is processed
            logger.info(f"Processing NCCIS data for Year Cohort {cohort_yg_ay}...")
            # Check if all students exist in NCCIS data
            missing_students = set(merged_df[stud_id_col]) - set(nccis_march_data[stud_id_col])

            if missing_students:
                logger.warning(
                    f"{len(missing_students)} students haven't been found in NCCIS data.\n"
                    f"Consider entering 'Unknown' as their destination.\n"
                    f"Example missing IDs: {list(missing_students)[:5]}"
                )
            
            # find academic age column
            academic_age = resolve_column_name(
                    NCCIS.ACADEMIC_AGE, 
                    nccis_march_data.columns,
                    NCCIS.PREFIX
                )
            
            if year_group <= 11: # pre-16, add target column
                if year_group == 11:
                    school_data = merged_df # store school data (ks, y11 census + attendance + exclusion)
                    
                logger.info(f"Adding target column (NCCIS Code at Academic Age 16) for Year Cohort {cohort_yg_ay}...")
                
                y12_dest = nccis_march_data[nccis_march_data[academic_age] == 16]
                # _check_mismatched_academic_age(y12_dest[y12_dest[stud_id_col].isin(merged_df[stud_id_col])])
                
                # target = y12_dest[[stud_id_col, academic_age, TARGET_COL]]
                target = y12_dest[[stud_id_col, TARGET_COL]]
                
                missing_target = set(merged_df[stud_id_col]) - set(target[stud_id_col]) - missing_students
                
                if missing_target:
                    logger.warning(
                    f"{len(missing_students)} students haven't NCCIS records at the academic age of 16.\n"
                    f"Consider entering 'Unknown' as their destination.\n"
                    f"Example missing IDs: {list(missing_target)[:5]}"
                )
                
                merged_df = pd.merge(
                    merged_df, 
                    target, 
                    on=stud_id_col, 
                    how='left', 
                )
                
                merged_data_group.append((year_group, year_group + 4, merged_df))
            
            if year_group == 11: 
                # Starting generating Year 11+ data:
                # - This step combines Year 11 school performance data (e.g., Attendance, Exclusion, KS2, KS4) 
                #   with NCCIS data (both September and March versions) for students aged 16-24.
                # - Each academic age undergoes two phases:
                #   - **Phase 1 (September -> March)**: NCCIS September data is merged as training data, with NCCIS March as the target.
                #   - **Phase 2 (March -> September)**: NCCIS March data replaces September data and serves as the training set, with next-year September as the target.
                # - This cycle continues for each academic age until the maximum age limit is reached.
                
                # -------------------------------------------------------
                # Merge KS4 to Y11 or Y12
                # -------------------------------------------------------
                if ks4 is not None:
                    school_data = merge_with_best_key(
                        merged_df=school_data, 
                        df=ks4,
                        data_category='ks4',
                        cohort_yg_ay=cohort_yg_ay,
                    )
                    logger.info(f'KS4 has been merged to corresponding Y{year_group}.')
                    if year_group < 12:
                        logger.warning("KS4 data is collected in Year 12 but it will only available after Year 12 onwards. Consider merging it to Y12+ cohort.")
                else:
                    logger.info(f'KS4 not available for this cohort.')
                    
                # -------------------------------------------------------
                # Generate Y11+ Data
                # -------------------------------------------------------            
                y11_plus_data = append_nccis_data(
                    school_data=school_data, 
                    nccis_sept_data=nccis_sept_data, 
                    nccis_march_data=nccis_march_data, 
                    stud_id_col=stud_id_col,
                    max_academic_age=nccis_march_data[academic_age].max(),
                    start_year_group=nccis_append_start_yg, # 15 is Year 11 age, 16 is Year 12 age, 17 is Year 13
                )
                
                merged_data_group.extend(y11_plus_data)

        # -------------------------------------------------------

    for idx, (year_group, academic_age, merged_df) in enumerate(merged_data_group):
                    
        # -------------------------------------------------------
        # Validation Step (academic age < 18)
        # -------------------------------------------------------
        if academic_age < 18:
            for dcategory, original_df in original_dfs.items():
                if dcategory == "ks4" and academic_age < 16:
                    logger.info(f"Skipping KS4 validation for academic age {academic_age} as KS4 data is only available in Y11 (or Y12) and later.")
                    continue
                    
                # original_df.dropna(axis=1, how="all", inplace=True)
                cols = original_df.columns
                select_students = original_df[stud_id_col]
                select_merged_df = merged_df[merged_df[stud_id_col].isin(select_students)][cols]
                original_df.sort_values(by=stud_id_col, inplace=True)
           
                def fill_and_convert(df):
                    df_filled = df.astype(object).replace({pd.NA: '', np.nan: '', 'nan': '', '<NA>': '', pd.NaT: ''})
                    df_filled = df_filled.applymap(lambda x: str(x) if pd.notna(x) else '')
                    return df_filled

                original_df_filled = fill_and_convert(original_df)
                select_merged_df_filled = fill_and_convert(select_merged_df)

                # Find rows in original_df not in merged_df
                missing_rows = pd.merge(
                    original_df_filled, 
                    select_merged_df_filled, 
                    how="outer", 
                    indicator=True
                ).query('_merge == "left_only"').drop(columns="_merge")

                # # Find rows in merged_df not in original_df
                # extra_rows = pd.merge(
                #     merged_df, 
                #     original_df, 
                #     how="outer", 
                #     indicator=True
                # ).query('_merge == "left_only"').drop(columns="_merge")

                if not missing_rows.empty:
                    logger.warning(f"{len(missing_rows)} rows in original data but not in merged data:")
                    print_table(missing_rows.sort_values(by=stud_id_col), group_records=False, num_cols='all')
                    
                    styled_print('Compare with merged data:')
                    merged_subset = select_merged_df_filled[select_merged_df_filled[stud_id_col].isin(missing_rows[stud_id_col])]
                     
                    print_table(
                        merged_subset.sort_values(by=stud_id_col),
                        group_records=False, 
                        num_cols='all'
                    )
                    
                    raise ValueError(f"Validation failed for {dcategory} data for academic age {academic_age}.")
        
        # -------------------------------------------------------
        
        drop_cols = DROP_COLS.intersection(merged_df.columns)
        if drop_cols:
            merged_df.drop(columns=[col for col in drop_cols], inplace=True)
            logger.info(f"Removed columns: {drop_cols}")
        
        # -------------------------------------------------------
        # Aggregation step: 
        # Some students have multiple records where all columns (excluding the student ID) contain identical values. 
        # To avoid inflating the dataset, we aggregate such records by retaining only one unique
        # representation of the student's data. However, if even one column has differing   
        # values across records, all records for that student are retained without aggregation.
        # -------------------------------------------------------
        merged_df = consolidate_student_records(df=merged_df, stud_id_col=stud_id_col)
        
        assert merged_df is not None, f"Merged DataFrame is None for year_group={year_group}, academic_age={academic_age}."
        
        # Apply data schema if provided
        # Merging or concatenating DataFrames may alter column data types
        if data_schema:
            merged_df = apply_schema_to_dataframe(
                df=merged_df, 
                data_schema=data_schema,
                is_merged=True,
                # dtype_backend='pyarrow'
            )
       
        # -------------------------------------------------------
        
        if stud_id_col in merged_df.columns:
            merged_df.drop_duplicates(inplace=True)
            merged_df.dropna(axis=1, how="all", inplace=True)
            merged_df.sort_values(by=stud_id_col, inplace=True)
            
            # Reorder columns to place the student ID column first, only if it's not already the first column
            if merged_df.columns[0] != stud_id_col:
                columns_order = (
                    [stud_id_col] +  # Ensure Student ID is first
                    [col for col in merged_df.columns if any(keyword in col.lower() for keyword in ["age", "ncy"])] +  
                    [col for col in merged_df.columns if col not in ([stud_id_col] + 
                                                                      [col for col in merged_df.columns if any(keyword in col.lower() for keyword in ["age", "ncy"])])]
                )
                merged_df = merged_df[columns_order]
            
            merged_df = merged_df[sorted(merged_df.columns, key=lambda col: col.startswith('_'))]
            
            validate_merged_data(merged_df)            

        merged_data_group[idx] = (year_group, academic_age, merged_df)
         
    return merged_data_group

def group_dfs_by_colsim(
    df_list: List[Tuple[str, int, pd.DataFrame]],  
    sim_cutoff: float = 0.7,
    subset_cutoff: float = 0.5,
    grouping_strategy: Literal["strict", "flexible", "balanced"] = "strict"
) -> Dict[int, List[Tuple[str, int, pd.DataFrame]]]:
    """
    Group DataFrames (with metadata like cohort and year group) by column name similarity using graph connectivity.

    Parameters
    ----------
    df_list : list of tuple
        A list of tuples where each tuple contains (cohort_y11_ay, year_group, DataFrame).
        - cohort_y11_ay: The academic year cohort (e.g., "2018-2019").
        - year_group: The school year group (e.g., 7, 8, 9).
        - DataFrame: The actual data.

    sim_cutoff : float, optional
        Minimum proportion of common columns required to consider two DataFrames as part of the same group (default is 0.7).
    
    subset_cutoff : float, optional
        Minimum similarity required to merge groups where one DataFrame's columns are a strict subset of another (default is 0.5).

    grouping_strategy : Literal["strict", "flexible", "balanced"], optional
        - "strict" (default): Groups only based on column similarity threshold.
        - "flexible": Merges groups if one DataFrame's columns are a strict subset of another.
        - "balanced": Merges groups if subset relation exists AND similarity is >= `subset_cutoff`.

    Returns
    -------
    groups : dict
        A dictionary where keys are group numbers, and values are lists of tuples 
        containing (cohort_y11_ay, year_group, DataFrame) for each group.
    """
    
    # # optional
    # df_list.sort(
    #     key=lambda x: (int(x[0].split('-')[0]), x[1])  # Sort by (first year of Y11 Cohort, Year Group)
    # )

    # Create an undirected graph where nodes represent DataFrames
    graph = nx.Graph()

    # Add nodes to the graph
    for i, (cohort_y11_ay, yg, df) in enumerate(df_list):
        graph.add_node(i, metadata=(cohort_y11_ay, yg), dataframe=df)

    # Compare DataFrames for column similarity and create edges
    for i in range(len(df_list)):
        y11_cohort_a, yg_a, df_a = df_list[i]

        for j in range(i + 1, len(df_list)):  # Ensure unique comparisons (j > i)
            y11_cohort_b, yg_b, df_b = df_list[j]

            # Compute column similarity
            columns_a, columns_b = set(df_a.columns), set(df_b.columns)
            common_columns = len(columns_a & columns_b)
            union_columns = len(columns_a | columns_b)
            similarity = common_columns / union_columns if union_columns > 0 else 0

            if grouping_strategy == "flexible":
                # Merge if similarity meets threshold OR one column set is a subset of another
                if similarity >= sim_cutoff or columns_a.issubset(columns_b) or columns_b.issubset(columns_a):
                    graph.add_edge(i, j)

            elif grouping_strategy == "balanced":
                # Merge only if subset condition is met AND similarity >= subset_threshold
                if similarity >= sim_cutoff or (
                    similarity >= subset_cutoff and (columns_a.issubset(columns_b) or columns_b.issubset(columns_a))
                ):
                    graph.add_edge(i, j)

            else:  # "strict"
                if similarity >= sim_cutoff:
                    graph.add_edge(i, j)

    # Find connected components (groups of similar DataFrames)
    groups = defaultdict(list)
    for group_id, component in enumerate(nx.connected_components(graph)):
        for node in component:
            metadata = graph.nodes[node]['metadata']  # (cohort_y11_ay, yg)
            dataframe = graph.nodes[node]['dataframe']
            groups[group_id].append((*metadata, dataframe))  # Unpack cohort_y11_ay, yg

    # Sort groups by first year of cohort_y11_ay, then by year_group (yg)
    groups = {
        group_id: sorted(
            group, 
            key=lambda x: (int(x[0].split('-')[0]), x[1])  # Sort by first year of cohort_y11_ay, then by yg
        ) 
        for group_id, group in groups.items()
    }
    
    return groups

def get_merge_status(intermediate_folder):
    files = sorted(intermediate_folder.glob("*.xlsx")) + sorted(intermediate_folder.glob("*.parquet"))
    return {file.name: file.stat().st_mtime for file in files}

def load_previous_status(status_file):
    if status_file.exists():
        with open(status_file, "r") as f:
            return json.load(f)
    return {}

def save_current_status(status, status_file):
    with open(status_file, "w") as f:
        json.dump(status, f, indent=4)

def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).isoformat(sep=" ", timespec="seconds")

def diff_status(
    prev: dict[str, float],
    curr: dict[str, float],
    *,
    mtime_tol: float = 0.0,
    ignore_exts: set[str] | None = None,
) -> dict:
    """
    Compare two status dicts {filename: mtime}.
    ignore_exts: extensions to ignore, e.g. {".png", ".jpg"}
    """
    ignore_exts = {e.lower() for e in (ignore_exts or set())}

    def keep(name: str) -> bool:
        return Path(name).suffix.lower() not in ignore_exts

    prev_f = {k: v for k, v in prev.items() if keep(k)}
    curr_f = {k: v for k, v in curr.items() if keep(k)}

    prev_keys = set(prev_f)
    curr_keys = set(curr_f)

    added = sorted(curr_keys - prev_keys)
    removed = sorted(prev_keys - curr_keys)

    modified = []
    for k in sorted(prev_keys & curr_keys):
        if abs(curr_f[k] - prev_f[k]) > mtime_tol:
            modified.append(
                {
                    "file": k,
                    "prev_mtime": prev_f[k],
                    "curr_mtime": curr_f[k],
                    "prev_time": _fmt_ts(prev_f[k]),
                    "curr_time": _fmt_ts(curr_f[k]),
                    "delta_seconds": curr_f[k] - prev_f[k],
                }
            )

    return {"added": added, "removed": removed, "modified": modified}

def print_status_diff(diff: dict) -> None:
    if not diff["added"] and not diff["removed"] and not diff["modified"]:
        # print("No changes detected.")
        return

    if diff["added"]:
        logger.debug("Added:")
        for f in diff["added"]:
            logger.debug(f"  + {f}")

    if diff["removed"]:
        logger.debug("Removed:")
        for f in diff["removed"]:
            logger.debug(f"  - {f}")

    if diff["modified"]:
        logger.debug("Modified:")
        for item in diff["modified"]:
            logger.debug(
                f"  * {item['file']}\n"
                f"    {item['prev_time']}  ->  {item['curr_time']}  "
                f"(Δ {item['delta_seconds']:.0f}s)"
            )


def merge_one_item_group(
    items,
    *,
    group_id=None,
    console=None,
    output_path=None,
    data_schema=None,
    stud_id_col="stud_id",
    save_tmp_outputs=False,
    valid_cat=None,
    save_colcov_dirname="intermediate_colcov",
):
    """
    items: iterable of (cohort_y11_ay, yg, df)
    """
    console = console or Console()

    df_records = []
    merged_group = []

    items = list(items) 

    # Extract all column sets in the group
    all_columns = [set(d.columns) for _, _, d in items]
    
    # Find common columns across all DataFrames in the group
    common_cols = set.intersection(*all_columns) if all_columns else set()

    console.print(
        Panel(
            "; ".join(sorted(common_cols)),
            title=f"{len(common_cols)} Common Columns"
                  + (f" of Group {group_id}" if group_id is not None else ""),
            border_style="cyan",
        )
    )

    # per-item processing
    for cohort_y11_ay, yg, df in items:
        logger.debug(
            f"Processing Year 11 Cohort {cohort_y11_ay} at Year Group {yg} with data shape {df.shape}..."
        )
        unique_cols = sorted(set(df.columns) - common_cols) # Find extra columns
        
        df_records.append({
            "Y11 Cohort": cohort_y11_ay,
            "Year Group": yg,
            "Total Columns": len(df.columns),
            "Extra Columns Count": len(unique_cols),
            # "Extra Columns": ", ".join(unique_cols) # too many extra columns
        })

        # Calculate the academic year of this cohort
        acad_start_year = int(cohort_y11_ay.split("-")[0]) + (yg - 11)

        # Append metadata
        df = append_metadata_cols(
            df=df,
            **{
                MergeMetadata.COHORT_Y11_AY: cohort_y11_ay,
                MergeMetadata.YEAR_GROUP: yg,
                MergeMetadata.ACAD_YEAR: str(acad_start_year) + f"-{acad_start_year + 1}",
            }
        )

        merged_group.append(df)

    # merging
    merged_df = pd.concat(merged_group, ignore_index=True)
    
    merged_df = merged_df[sorted(merged_df.columns, key=lambda col: col.startswith('_'))]
    
    merged_df.drop_duplicates(inplace=True)
    
    if data_schema:
        merged_df = apply_schema_to_dataframe(
            df=merged_df, 
            data_schema=data_schema,
            is_merged=True,
        )

    start_year = end_year = None
    
    if stud_id_col in merged_df.columns:
        merged_df["_y11_start_year"] = merged_df[MergeMetadata.COHORT_Y11_AY].str.split("-").str[0].astype(int) # Extract first year
        merged_df["_y11_end_year"] = merged_df[MergeMetadata.COHORT_Y11_AY].str.split("-").str[1].astype(int) 
        merged_df.sort_values(by=[stud_id_col, "_y11_start_year", MergeMetadata.YEAR_GROUP], inplace=True)
        start_year = merged_df["_y11_start_year"].min()
        end_year = merged_df["_y11_end_year"].max()
        merged_df.drop(columns=["_y11_start_year", "_y11_end_year"], inplace=True) 

    
    print_table(
        pd.DataFrame(df_records),
        group_records=False,
        num_cols='all',
        num_rows='all',
        title=(f"Group {group_id}" if group_id is not None else "All Data"),
        wrap_in_panel=True,
        console=console
    )
    
    print_table(merged_df, group_records=False, num_cols='all', num_rows=20, console=console)

    validate_merged_data(merged_df)
    
     # merged_df.to_excel(output_path / f"{start_year}-{end_year}_group{group_id}.xlsx", index=False) # it is unsuitable for large data

    if output_path is not None and start_year is not None and end_year is not None:
        merged_df.to_parquet(
            output_path / (
                f"{start_year}-{end_year}"
                + (f"_group{group_id}" if group_id is not None else "")
                + ".parquet"
            ),
            # engine="pyarrow",
            index=False
        )

        logger.info(
            f"Data of {len(merged_df[stud_id_col].drop_duplicates())} "
            f"in {(f'group {group_id}' if group_id is not None else 'all data')} "
            f"can be merged into a {merged_df.shape} DataFrame."
        )

        save_colcov_dir = output_path / save_colcov_dirname
        save_colcov_dir.mkdir(parents=True, exist_ok=True)

        plot_group_heatmap(
            df=merged_df,
            index_col=MergeMetadata.COHORT_Y11_AY,
            columns_col=MergeMetadata.YEAR_GROUP,
            values_col=stud_id_col,
            x_label="Year group",
            y_label="Y11 Cohort",
            aggfunc="nunique",
            title="Student count by Cohort and Year group",
            output_file=str(
                (save_colcov_dir if save_tmp_outputs else output_path)
                / (f"g{group_id}_stud_dist.jpg" if group_id is not None else "all_stud_dist.jpg")
            )
        )

        cmap = ListedColormap(["white", "#8da0cb"])
        
        # plotting column coverage
        if valid_cat:
            max_year_group = merged_df[MergeMetadata.YEAR_GROUP].astype(int).max()
            for prefix in sorted(valid_cat):
                print(f"Check the column presence of {prefix} data")
                plot_col_coverage(
                    merged_df,
                    prefix=f"{prefix}",
                    cmap=cmap,
                    max_year_group=max_year_group,
                    figsize=(25, 15),
                    verbose=True,
                    save_excel=True,
                    output_file=str(
                        (save_colcov_dir if save_tmp_outputs else output_path)
                        / (f"g{group_id}_{prefix}_colcov.jpg" if group_id is not None else f"all_{prefix}_colcov.jpg")
                    )
                )

    return merged_df